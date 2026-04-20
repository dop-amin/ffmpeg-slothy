# slothy.mk — build and benchmark SLOTHY-optimized FFmpeg variants
#
# Expected directory layout:
#   <wrapper>/
#     slothy.mk             (this file)
#     bench.py
#     checkasm_bench.py
#     monitor_freq.sh
#     FFmpeg/               (FFmpeg source tree)
#
# Usage:
#   make -f slothy.mk build-baseline       # build baseline ffmpeg + checkasm
#   make -f slothy.mk build-min            # build SLOTHY+min ffmpeg + checkasm
#   make -f slothy.mk build                # build both variants
#
#   make -f slothy.mk bench-checkasm       # run checkasm comparison (all h264 groups)
#   make -f slothy.mk bench-checkasm-dsp   # run checkasm for h264dsp only
#   make -f slothy.mk bench-checkasm-qpel  # run checkasm for h264qpel only
#   make -f slothy.mk bench-decode-short   # decode benchmark, 60s clip
#   make -f slothy.mk bench-decode-full    # decode benchmark, full file
#   make -f slothy.mk bench                # run checkasm + 60s decode
#
#   make -f slothy.mk check-freq           # verify CPU frequency is locked
#   make -f slothy.mk clean                # remove built binaries
#   make -f slothy.mk help                 # show this help

# ---------------------------------------------------------------------------
# Configuration — override on command line, e.g.:
#   make -f slothy.mk INPUT=/path/to/other.mov RUNS=10 bench-decode-short
# ---------------------------------------------------------------------------

WRAPPER_DIR  := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
FFMPEG_DIR   := $(WRAPPER_DIR)FFmpeg
INPUT        ?= $(WRAPPER_DIR)ToS-4k-1920.mov
CPU_CORE     ?= 0
RUNS         ?= 5
DURATION     ?= 60
JOBS         ?= $(shell nproc)

BENCH_SCRIPT     := $(WRAPPER_DIR)bench.py
CHECKASM_SCRIPT  := $(WRAPPER_DIR)checkasm_bench.py

# Binaries land in wrapper dir
FFMPEG_BASELINE   := $(WRAPPER_DIR)ffmpeg_baseline
FFMPEG_MIN        := $(WRAPPER_DIR)ffmpeg_min
CHECKASM_BASELINE := $(WRAPPER_DIR)checkasm_baseline
CHECKASM_MIN      := $(WRAPPER_DIR)checkasm_min

# Common configure flags shared by both variants
CONFIGURE_COMMON := \
    --disable-everything \
    --enable-decoder=h264 \
    --enable-decoder=aac \
    --enable-demuxer=mov \
    --enable-protocol=file \
    --enable-muxer=null \
    --enable-encoder=wrapped_avframe \
    --enable-bsf=h264_mp4toannexb \
    --disable-linux-perf

# Extra flags for the optimized variant
CONFIGURE_MIN_EXTRA := --extra-cflags="-DH264_SLOTHY_A55_OPT"

# Optional debug symbols — override with: make -f slothy.mk ... DEBUG=1
DEBUG_FLAGS := $(if $(DEBUG),--extra-cflags="-g" --extra-ldflags="-g")

# ---------------------------------------------------------------------------
# Phony targets
# ---------------------------------------------------------------------------

.PHONY: all build build-baseline build-min \
        bench bench-checkasm bench-checkasm-dsp bench-checkasm-qpel \
        bench-decode-short bench-decode-full \
        check-freq clean help

all: help

# ---------------------------------------------------------------------------
# Build targets
# ---------------------------------------------------------------------------

build: build-baseline build-min

build-baseline:
	@echo "=== Configuring baseline ==="
	cd $(FFMPEG_DIR) && ./configure $(CONFIGURE_COMMON) $(DEBUG_FLAGS)
	@echo "=== Building baseline ==="
	$(MAKE) -C $(FFMPEG_DIR) -j$(JOBS)
	cp $(FFMPEG_DIR)/ffmpeg $(FFMPEG_BASELINE)
	$(MAKE) -C $(FFMPEG_DIR) -j$(JOBS) tests/checkasm/checkasm
	cp $(FFMPEG_DIR)/tests/checkasm/checkasm $(CHECKASM_BASELINE)
	@echo "=== Built: $(FFMPEG_BASELINE) $(CHECKASM_BASELINE) ==="

build-min:
	@echo "=== Configuring min (SLOTHY A55 + spill removal) ==="
	cd $(FFMPEG_DIR) && ./configure $(CONFIGURE_COMMON) $(CONFIGURE_MIN_EXTRA) $(DEBUG_FLAGS)
	@echo "=== Building min ==="
	$(MAKE) -C $(FFMPEG_DIR) -j$(JOBS)
	cp $(FFMPEG_DIR)/ffmpeg $(FFMPEG_MIN)
	$(MAKE) -C $(FFMPEG_DIR) -j$(JOBS) tests/checkasm/checkasm
	cp $(FFMPEG_DIR)/tests/checkasm/checkasm $(CHECKASM_MIN)
	@echo "=== Built: $(FFMPEG_MIN) $(CHECKASM_MIN) ==="

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

$(FFMPEG_BASELINE):
	@echo "ERROR: $(FFMPEG_BASELINE) not found. Run: make -f slothy.mk build-baseline"
	@exit 1

$(FFMPEG_MIN):
	@echo "ERROR: $(FFMPEG_MIN) not found. Run: make -f slothy.mk build-min"
	@exit 1

$(CHECKASM_BASELINE):
	@echo "ERROR: $(CHECKASM_BASELINE) not found. Run: make -f slothy.mk build-baseline"
	@exit 1

$(CHECKASM_MIN):
	@echo "ERROR: $(CHECKASM_MIN) not found. Run: make -f slothy.mk build-min"
	@exit 1

# ---------------------------------------------------------------------------
# Frequency check
# ---------------------------------------------------------------------------

check-freq:
	@freq=$$(cat /sys/devices/system/cpu/cpu$(CPU_CORE)/cpufreq/scaling_cur_freq 2>/dev/null); \
	if [ "$$freq" != "1800000" ]; then \
	    echo "WARNING: CPU$(CPU_CORE) frequency is $$freq Hz, not 1800000."; \
	    echo "Lock it with:"; \
	    echo "  for cpu in 0 1 2 3; do"; \
	    echo "    echo 1800000 | sudo tee /sys/devices/system/cpu/cpu\$${cpu}/cpufreq/scaling_min_freq"; \
	    echo "    echo 1800000 | sudo tee /sys/devices/system/cpu/cpu\$${cpu}/cpufreq/scaling_max_freq"; \
	    echo "  done"; \
	    exit 1; \
	else \
	    echo "CPU$(CPU_CORE) frequency: $$freq Hz (OK)"; \
	fi

# ---------------------------------------------------------------------------
# checkasm benchmarks
# ---------------------------------------------------------------------------

bench-checkasm: check-freq $(CHECKASM_BASELINE) $(CHECKASM_MIN)
	@echo "=== checkasm comparison: all h264 groups ==="
	cd $(WRAPPER_DIR) && python3 $(CHECKASM_SCRIPT) -g h264dsp h264qpel h264chroma h264pred

bench-checkasm-dsp: check-freq $(CHECKASM_BASELINE) $(CHECKASM_MIN)
	@echo "=== checkasm comparison: h264dsp ==="
	cd $(WRAPPER_DIR) && python3 $(CHECKASM_SCRIPT) -g h264dsp

bench-checkasm-qpel: check-freq $(CHECKASM_BASELINE) $(CHECKASM_MIN)
	@echo "=== checkasm comparison: h264qpel ==="
	cd $(WRAPPER_DIR) && python3 $(CHECKASM_SCRIPT) -g h264qpel

# ---------------------------------------------------------------------------
# Decode benchmarks
# ---------------------------------------------------------------------------

bench-decode-short: check-freq $(FFMPEG_BASELINE) $(FFMPEG_MIN)
	@echo "=== Decode benchmark: $(DURATION)s clip, $(RUNS) runs ==="
	cd $(WRAPPER_DIR) && python3 $(BENCH_SCRIPT) -t $(DURATION) -n $(RUNS)

bench-decode-full: check-freq $(FFMPEG_BASELINE) $(FFMPEG_MIN)
	@echo "=== Decode benchmark: full file, $(RUNS) runs ==="
	cd $(WRAPPER_DIR) && python3 $(BENCH_SCRIPT) -n $(RUNS)

bench: bench-checkasm bench-decode-short

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean:
	rm -f $(FFMPEG_BASELINE) $(FFMPEG_MIN) $(CHECKASM_BASELINE) $(CHECKASM_MIN)
	@echo "Removed binaries. FFmpeg source tree untouched."
	@echo "To clean the FFmpeg source tree: make -C $(FFMPEG_DIR) clean"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:
	@echo ""
	@echo "slothy.mk — build and benchmark SLOTHY-optimized FFmpeg (H.264, A55)"
	@echo ""
	@echo "Layout:  $(WRAPPER_DIR)"
	@echo "FFmpeg:  $(FFMPEG_DIR)"
	@echo ""
	@echo "Build:"
	@echo "  build               Build both variants"
	@echo "  build-baseline      Build upstream baseline"
	@echo "  build-min           Build SLOTHY+min variant"
	@echo ""
	@echo "Benchmark:"
	@echo "  bench               checkasm + 60s decode"
	@echo "  bench-checkasm      checkasm all h264 groups"
	@echo "  bench-checkasm-dsp  checkasm h264dsp only"
	@echo "  bench-checkasm-qpel checkasm h264qpel only"
	@echo "  bench-decode-short  Decode benchmark ($(DURATION)s)"
	@echo "  bench-decode-full   Decode benchmark (full file)"
	@echo ""
	@echo "Utilities:"
	@echo "  check-freq          Verify CPU$(CPU_CORE) frequency is locked to 1.8 GHz"
	@echo "  clean               Remove built binaries"
	@echo ""
	@echo "Overridable variables:"
	@echo "  INPUT=$(INPUT)"
	@echo "  CPU_CORE=$(CPU_CORE)"
	@echo "  RUNS=$(RUNS)"
	@echo "  DURATION=$(DURATION)s"
	@echo "  JOBS=$(JOBS)"
	@echo ""