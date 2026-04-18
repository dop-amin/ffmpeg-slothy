#!/usr/bin/env python3
import subprocess
import argparse
import re
import os
import json
import statistics
from datetime import datetime
from pathlib import Path

VARIANTS = {
    "baseline": "./ffmpeg_baseline",
    "min":      "./ffmpeg_min",
}

INPUT = "../ToS-4k-1920.mov"


def build_ffmpeg_args(duration=None):
    args = ["-benchmark"]
    if duration:
        args += ["-t", str(duration)]
    args += ["-i", INPUT, "-an", "-threads", "1",  "-filter_threads", "1", 
             "-thread_queue_size", "0",
             "-flags:v", "+low_delay",
             "-f", "null", "-"]
    return args


def build_cmd(binary, duration=None):
    return [binary] + build_ffmpeg_args(duration)


def parse_bench_line(output):
    m = re.search(
        r"bench:\s+utime=([\d.]+)s\s+stime=([\d.]+)s\s+rtime=([\d.]+)s",
        output
    )
    if not m:
        return None
    return {
        "utime": float(m.group(1)),
        "stime": float(m.group(2)),
        "rtime": float(m.group(3)),
    }


def run_once(binary, log_path, duration=None):
    cmd = ["taskset", "-c", "0"] + build_cmd(binary, duration)
    with open(log_path, "w") as f:
        f.write("# " + " ".join(cmd) + "\n\n")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        f.write(result.stdout)
    return parse_bench_line(result.stdout)


def stats(values):
    if len(values) < 2:
        return {"mean": values[0], "stdev": 0.0, "min": values[0], "max": values[0]}
    return {
        "mean":  statistics.mean(values),
        "stdev": statistics.stdev(values),
        "min":   min(values),
        "max":   max(values),
    }


def main():
    parser = argparse.ArgumentParser(description="FFmpeg H264 decode benchmark")
    parser.add_argument("-n", "--runs", type=int, default=5,
                        help="Number of runs per variant (default: 5)")
    parser.add_argument("-o", "--outdir", type=str, default="bench_results",
                        help="Parent directory for results (default: bench_results)")
    parser.add_argument("-t", "--duration", type=int, default=None,
                        help="Decode only first N seconds (default: full file)")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.outdir) / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write the command template
    cmd_file = run_dir / "command.txt"
    with open(cmd_file, "w") as f:
        for name, binary in VARIANTS.items():
            cmd = ["taskset", "-c", "0"] + build_cmd(binary, args.duration)
            f.write(f"# {name}\n")
            f.write(" ".join(cmd) + "\n\n")

    print(f"Results directory: {run_dir}")
    print(f"Runs per variant:  {args.runs}")
    if args.duration:
        print(f"Duration limit:    {args.duration}s")
    print()

    results = {name: [] for name in VARIANTS}

    # Interleaved runs
    for i in range(1, args.runs + 1):
        for name, binary in VARIANTS.items():
            log_path = run_dir / f"{name}_run{i:02d}.log"
            print(f"[{i}/{args.runs}] {name} ... ", end="", flush=True)
            parsed = run_once(binary, log_path, args.duration)
            if parsed is None:
                print("FAILED (no bench line found)")
            else:
                results[name].append(parsed)
                print(f"utime={parsed['utime']:.2f}s  rtime={parsed['rtime']:.2f}s")

    # Compute summary
    summary = {}
    for name, runs in results.items():
        if not runs:
            continue
        utimes = [r["utime"] for r in runs]
        summary[name] = {
            "utime": stats(utimes),
            "raw": runs,
        }

    # Speedup
    if "baseline" in summary and "min" in summary:
        base_mean = summary["baseline"]["utime"]["mean"]
        min_mean  = summary["min"]["utime"]["mean"]
        speedup   = base_mean / min_mean
        summary["speedup_min_vs_baseline"] = round(speedup, 4)

    summary_path = run_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print table
    print(f"\n{'Variant':<12} {'mean utime':>12} {'stdev':>8} {'min':>8} {'max':>8}")
    print("-" * 52)
    for name, s in summary.items():
        if name == "speedup_min_vs_baseline":
            continue
        u = s["utime"]
        print(f"{name:<12} {u['mean']:>11.2f}s {u['stdev']:>7.2f}s "
              f"{u['min']:>7.2f}s {u['max']:>7.2f}s")

    if "speedup_min_vs_baseline" in summary:
        print(f"\nSpeedup (min vs baseline): {summary['speedup_min_vs_baseline']:.4f}x")

    print(f"\nSummary written to: {summary_path}")


if __name__ == "__main__":
    main()