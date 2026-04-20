#!/usr/bin/env python3
"""
Compare checkasm --bench output across two binaries.
Usage:
    python3 checkasm_bench.py [options]

Examples:
    python3 checkasm_bench.py                          # all groups, both binaries
    python3 checkasm_bench.py -g h264dsp h264qpel      # specific groups
    python3 checkasm_bench.py --threshold 3.0          # only show >3% changes
    python3 checkasm_bench.py --no-taskset             # skip taskset pinning
"""
import subprocess
import argparse
import re
import json
import statistics
from datetime import datetime
from pathlib import Path

BINARIES = {
    "baseline": "./checkasm_baseline",
    "min":      "./checkasm_min",
}

# All available h264 groups in checkasm
ALL_GROUPS = ["h264dsp", "h264qpel", "h264chroma", "h264pred"]

CPU_CORE = "0"


def run_checkasm(binary, groups, taskset=True, seed=12345):
    """Run checkasm --bench for the given groups, return raw stdout."""
    cmd = []
    if taskset:
        cmd += ["taskset", "-c", CPU_CORE]
    cmd += [binary, "--bench", "--test=h264*", "--runs=10", f"{seed}"]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return " ".join(cmd), result.stdout


def parse_checkasm_output(output):
    """
    Parse lines like:
      h264_idct4_add_8bpp_neon:                               66.9 ( 1.50x)
    Returns dict: name -> {cycles, speedup}
    """
    results = {}
    for line in output.splitlines():
        m = re.match(r"^\s*(\S+?):\s+([\d.]+)\s+\(\s*([\d.]+)x\)", line)
        if m:
            results[m.group(1)] = {
                "cycles":  float(m.group(2)),
                "speedup": float(m.group(3)),
            }
    return results


def compare(baseline, variant, threshold):
    """
    For each function present in both, compute delta%.
    Returns list of dicts sorted by delta% ascending (best improvements first).
    """
    rows = []
    all_keys = sorted(set(baseline) | set(variant))
    for k in all_keys:
        if k not in baseline or k not in variant:
            continue
        b = baseline[k]["cycles"]
        v = variant[k]["cycles"]
        pct = (v - b) / b * 100
        rows.append({
            "name":          k,
            "baseline_cyc":  b,
            "variant_cyc":   v,
            "delta_pct":     pct,
            "baseline_spdup": baseline[k]["speedup"],
            "variant_spdup":  variant[k]["speedup"],
        })
    rows.sort(key=lambda r: r["delta_pct"])
    return rows


def color(pct, threshold):
    """ANSI color: green=improvement, red=regression, grey=neutral."""
    if pct < -threshold:
        return "\033[32m"   # green
    if pct > threshold:
        return "\033[31m"   # red
    return "\033[90m"       # grey


RESET = "\033[0m"


def print_table(rows, threshold, show_all):
    filtered = [r for r in rows if abs(r["delta_pct"]) > threshold] if not show_all else rows
    if not filtered:
        print(f"  (no changes above {threshold}% threshold)")
        return

    header = f"  {'Function':<50} {'Base cyc':>10} {'Var cyc':>10} {'Δ%':>8}  {'Base spdup':>11} {'Var spdup':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in filtered:
        c = color(r["delta_pct"], threshold)
        sign = "+" if r["delta_pct"] > 0 else ""
        print(
            f"  {r['name']:<50} "
            f"{r['baseline_cyc']:>10.1f} "
            f"{r['variant_cyc']:>10.1f} "
            f"{c}{sign}{r['delta_pct']:>7.1f}%{RESET}  "
            f"{r['baseline_spdup']:>10.2f}x "
            f"{r['variant_spdup']:>9.2f}x"
        )

    imps = [r for r in filtered if r["delta_pct"] < -threshold]
    regs = [r for r in filtered if r["delta_pct"] > threshold]
    print(f"\n  Improvements: {len(imps)}  Regressions: {len(regs)}  "
          f"(threshold ±{threshold}%)")

    if imps:
        best = min(imps, key=lambda r: r["delta_pct"])
        print(f"  Best improvement: {best['name']}  {best['delta_pct']:+.1f}%")
    if regs:
        worst = max(regs, key=lambda r: r["delta_pct"])
        print(f"  Worst regression: {worst['name']}  {worst['delta_pct']:+.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Compare checkasm --bench across two binaries")
    parser.add_argument("-g", "--groups", nargs="+", default=ALL_GROUPS,
                        help=f"checkasm groups to bench (default: {' '.join(ALL_GROUPS)})")
    parser.add_argument("--threshold", type=float, default=2.0,
                        help="Highlight changes above this %% (default: 2.0)")
    parser.add_argument("--show-all", action="store_true",
                        help="Show all functions, not just those above threshold")
    parser.add_argument("--no-taskset", action="store_true",
                        help="Don't pin to CPU core via taskset")
    parser.add_argument("--seed", type=int, default=12345,
                        help="checkasm random seed (default: 12345)")
    parser.add_argument("-o", "--outdir", type=str, default="checkasm_results",
                        help="Output directory for logs and JSON (default: checkasm_results)")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.outdir) / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    use_taskset = not args.no_taskset
    print(f"Groups:    {', '.join(args.groups)}")
    print(f"Threshold: ±{args.threshold}%")
    print(f"Core:      {CPU_CORE if use_taskset else 'unpinned'}")
    print(f"Results:   {run_dir}\n")

    raw = {}
    parsed = {}

    for name, binary in BINARIES.items():
        print(f"Running {name} ({binary}) ...", flush=True)
        cmd_str, output = run_checkasm(binary, args.groups,
                                       taskset=use_taskset, seed=args.seed)

        log_path = run_dir / f"{name}.log"
        with open(log_path, "w") as f:
            f.write(f"# {cmd_str}\n\n")
            f.write(output)

        raw[name] = output
        parsed[name] = parse_checkasm_output(output)
        print(f"  -> {len(parsed[name])} functions parsed, log: {log_path}")

    # Compare
    rows = compare(parsed["baseline"], parsed["min"], args.threshold)

    print(f"\n{'='*80}")
    print(f"  baseline vs min  —  {len(rows)} functions in common")
    print(f"{'='*80}")
    print_table(rows, args.threshold, args.show_all)

    # Per-group breakdown
    for group in args.groups:
        group_rows = [r for r in rows if group.replace("h264", "h264_") in r["name"]
                      or r["name"].startswith(group.replace("h264", "h264_"))
                      or any(r["name"].startswith(p) for p in [
                          "h264_idct", "h264_h_loop", "h264_v_loop",  # h264dsp
                          "put_h264_qpel", "avg_h264_qpel",           # h264qpel
                          "put_h264_chroma", "avg_h264_chroma",        # h264chroma
                          "pred8x8", "pred16x16",                      # h264pred
                      ] if group in {
                          "h264dsp":    ["h264_idct", "h264_h_loop", "h264_v_loop"],
                          "h264qpel":   ["put_h264_qpel", "avg_h264_qpel"],
                          "h264chroma": ["put_h264_chroma", "avg_h264_chroma"],
                          "h264pred":   ["pred8x8", "pred16x16"],
                      }.get(group, []))]

    # Save JSON
    summary = {
        "timestamp": ts,
        "groups": args.groups,
        "threshold": args.threshold,
        "functions": rows,
        "counts": {
            "total":        len(rows),
            "improvements": len([r for r in rows if r["delta_pct"] < -args.threshold]),
            "regressions":  len([r for r in rows if r["delta_pct"] > args.threshold]),
            "neutral":      len([r for r in rows if abs(r["delta_pct"]) <= args.threshold]),
        }
    }
    summary_path = run_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nJSON summary: {summary_path}")


if __name__ == "__main__":
    main()