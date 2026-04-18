with open('FFmpeg/libavcodec/aarch64/h264_slothy_a55.S') as f:
    content = f.read()

def replace_exact(content, old, new):
    count = content.count(old)
    if count != 1:
        raise ValueError("Expected 1 occurrence, found %d for:\n%s" % (count, old[:200]))
    return content.replace(old, new)

ALL_8 = (
    "        stp     d8,  d9,  [sp, #-64]!\n"
    "        stp     d10, d11, [sp, #16]\n"
    "        stp     d12, d13, [sp, #32]\n"
    "        stp     d14, d15, [sp, #48]\n"
)

ALL_8_RESTORE = (
    "        ldp     d14, d15, [sp, #48]\n"
    "        ldp     d12, d13, [sp, #32]\n"
    "        ldp     d10, d11, [sp, #16]\n"
    "        ldp     d8,  d9,  [sp], #64\n"
)

SIX_REGS = (
    "        stp     d8,  d9,  [sp, #-48]!\n"
    "        stp     d12, d13, [sp, #16]\n"
    "        stp     d14, d15, [sp, #32]\n"
)

SIX_REGS_RESTORE = (
    "        ldp     d14, d15, [sp, #32]\n"
    "        ldp     d12, d13, [sp, #16]\n"
    "        ldp     d8,  d9,  [sp], #48\n"
)

FIVE_REGS = (
    "        stp     d8,  d9,  [sp, #-48]!\n"
    "        stp     d12, d13, [sp, #16]\n"
    "        str     d14, [sp, #32]\n"
)

FIVE_REGS_RESTORE = (
    "        ldr     d14, [sp, #32]\n"
    "        ldp     d12, d13, [sp, #16]\n"
    "        ldp     d8,  d9,  [sp], #48\n"
)

# For inserting restore before ret, use "ret\nendfunc\n\nfunction NEXT" as unique anchor
def add_restore_before_ret_endfunc(content, next_func, restore):
    old = "        ret\nendfunc\n\nfunction " + next_func
    new = restore + "        ret\nendfunc\n\nfunction " + next_func
    return replace_exact(content, old, new)

# For inserting restore before "ret\nendfunc" at end of file
def add_restore_before_ret_endfunc_eof(content, restore):
    old = "        ret\nendfunc\n"
    # Count to make sure unique - should be 1 occurrence at the end
    count = content.count(old)
    if count != 1:
        raise ValueError("ret+endfunc at EOF: found %d occurrences" % count)
    return content.replace(old, restore + "        ret\nendfunc\n")

# 1. put_h264_qpel8_v_lowpass_neon prologue (already done by previous run)
if SIX_REGS in content and "function put_h264_qpel8_v_lowpass_neon" in content:
    # Check if already patched
    marker = "function put_h264_qpel8_v_lowpass_neon, export=1\n" + SIX_REGS
    if marker in content:
        print("1a. put_h264_qpel8_v_lowpass_neon prologue: already done")
    else:
        content = replace_exact(content,
            "function put_h264_qpel8_v_lowpass_neon, export=1\n"
            "        ld1 {v21.8B}, [x1], x3",
            "function put_h264_qpel8_v_lowpass_neon, export=1\n" +
            SIX_REGS +
            "        ld1 {v21.8B}, [x1], x3"
        )
        print("1a. put_h264_qpel8_v_lowpass_neon prologue: done")

# Check current state
marker = "function put_h264_qpel8_v_lowpass_neon, export=1\n" + SIX_REGS
if marker not in content:
    raise ValueError("put_h264_qpel8_v_lowpass_neon prologue not in content!")

# 1b. put_h264_qpel8_v_lowpass_neon epilogue
if SIX_REGS_RESTORE + "        ret\nendfunc\n\nfunction avg_h264_qpel8_v_lowpass_neon" not in content:
    content = add_restore_before_ret_endfunc(content, "avg_h264_qpel8_v_lowpass_neon", SIX_REGS_RESTORE)
    print("1b. put_h264_qpel8_v_lowpass_neon epilogue: done")
else:
    print("1b. put_h264_qpel8_v_lowpass_neon epilogue: already done")

# 2a. avg_h264_qpel8_v_lowpass_neon prologue
if "function avg_h264_qpel8_v_lowpass_neon, export=1\n" + ALL_8 not in content:
    content = replace_exact(content,
        "function avg_h264_qpel8_v_lowpass_neon, export=1\n"
        "        ld1 {v25.8B}, [x1], x3",
        "function avg_h264_qpel8_v_lowpass_neon, export=1\n" +
        ALL_8 +
        "        ld1 {v25.8B}, [x1], x3"
    )
    print("2a. avg_h264_qpel8_v_lowpass_neon prologue: done")
else:
    print("2a. avg_h264_qpel8_v_lowpass_neon prologue: already done")

# 2b. avg epilogue
if ALL_8_RESTORE + "        ret\nendfunc\n\nfunction put_h264_qpel8_hv_lowpass_neon_top" not in content:
    content = add_restore_before_ret_endfunc(content, "put_h264_qpel8_hv_lowpass_neon_top", ALL_8_RESTORE)
    print("2b. avg_h264_qpel8_v_lowpass_neon epilogue: done")
else:
    print("2b. avg_h264_qpel8_v_lowpass_neon epilogue: already done")

# 3a. put_h264_qpel8_hv_lowpass_neon_top prologue
if "function put_h264_qpel8_hv_lowpass_neon_top, export=1\n" + ALL_8 not in content:
    content = replace_exact(content,
        "function put_h264_qpel8_hv_lowpass_neon_top, export=1\n"
        "        movz            w12, #20, lsl #16\n",
        "function put_h264_qpel8_hv_lowpass_neon_top, export=1\n" +
        ALL_8 +
        "        movz            w12, #20, lsl #16\n"
    )
    print("3a. put_h264_qpel8_hv_lowpass_neon_top prologue: done")
else:
    print("3a. put_h264_qpel8_hv_lowpass_neon_top prologue: already done")

# 3b. hv_lowpass_top epilogue
if ALL_8_RESTORE + "        ret\nendfunc\n\nfunction put_h264_qpel16_h_lowpass_neon" not in content:
    content = add_restore_before_ret_endfunc(content, "put_h264_qpel16_h_lowpass_neon", ALL_8_RESTORE)
    print("3b. put_h264_qpel8_hv_lowpass_neon_top epilogue: done")
else:
    print("3b. put_h264_qpel8_hv_lowpass_neon_top epilogue: already done")

# 4a. put_h264_qpel8_h_lowpass_neon prologue
if "function put_h264_qpel8_h_lowpass_neon, export=1\n" + ALL_8 not in content:
    # Find the exact first instruction line
    import re
    m = re.search(r'function put_h264_qpel8_h_lowpass_neon, export=1\n(        ld1 \{v14\.8B, v15\.8B\}[^\n]+\n)', content)
    if not m:
        raise ValueError("Could not find h_lowpass first instruction")
    first_line = m.group(1)
    content = replace_exact(content,
        "function put_h264_qpel8_h_lowpass_neon, export=1\n" + first_line,
        "function put_h264_qpel8_h_lowpass_neon, export=1\n" + ALL_8 + first_line
    )
    print("4a. put_h264_qpel8_h_lowpass_neon prologue: done")
else:
    print("4a. put_h264_qpel8_h_lowpass_neon prologue: already done")

# 4b. h_lowpass epilogue
if ALL_8_RESTORE + "        ret\nendfunc\n\nfunction put_h264_qpel16_v_lowpass_l2_neon" not in content:
    content = add_restore_before_ret_endfunc(content, "put_h264_qpel16_v_lowpass_l2_neon", ALL_8_RESTORE)
    print("4b. put_h264_qpel8_h_lowpass_neon epilogue: done")
else:
    print("4b. put_h264_qpel8_h_lowpass_neon epilogue: already done")

# 5a. put_h264_qpel8_v_lowpass_l2_neon prologue
if "function put_h264_qpel8_v_lowpass_l2_neon, export=1\n" + ALL_8 not in content:
    content = replace_exact(content,
        "function put_h264_qpel8_v_lowpass_l2_neon, export=1\n"
        "        ld1 {v13.8B}, [x1], x3",
        "function put_h264_qpel8_v_lowpass_l2_neon, export=1\n" +
        ALL_8 +
        "        ld1 {v13.8B}, [x1], x3"
    )
    print("5a. put_h264_qpel8_v_lowpass_l2_neon prologue: done")
else:
    print("5a. put_h264_qpel8_v_lowpass_l2_neon prologue: already done")

# 5b. v_lowpass_l2 epilogue
if ALL_8_RESTORE + "        ret\nendfunc\n\nfunction ff_h264_idct_add_neon" not in content:
    content = add_restore_before_ret_endfunc(content, "ff_h264_idct_add_neon", ALL_8_RESTORE)
    print("5b. put_h264_qpel8_v_lowpass_l2_neon epilogue: done")
else:
    print("5b. put_h264_qpel8_v_lowpass_l2_neon epilogue: already done")

# 6. ff_h264_idct_add_neon (v8 v9 v11 v13 v15 + x29)
NEW_IDCT_PROLOGUE = (
    "        sub     sp,  sp,  #48\n"
    "        stp     d8,  d9,  [sp]\n"
    "        stp     d11, d13, [sp, #16]\n"
    "        str     d15, [sp, #32]\n"
    "        str     x29, [sp, #40]\n"
    "        sxtw x29, w2"
)
NEW_IDCT_EPILOGUE = (
    "        ldp     d8,  d9,  [sp]\n"
    "        ldp     d11, d13, [sp, #16]\n"
    "        ldr     d15, [sp, #32]\n"
    "        ldr     x29, [sp, #40]\n"
    "        add     sp,  sp,  #48\n"
)

if "        sub     sp,  sp,  #48\n" not in content:
    content = replace_exact(content,
        "        stp     x29, xzr, [sp, #-16]!\n"
        "        sxtw x29, w2",
        NEW_IDCT_PROLOGUE
    )
    print("6a. ff_h264_idct_add_neon prologue: done")
else:
    print("6a. ff_h264_idct_add_neon prologue: already done")

if "        ldp     x29, xzr, [sp], #16\n" in content:
    content = replace_exact(content,
        "        ldp     x29, xzr, [sp], #16\n"
        "        ret\n"
        "endfunc\n"
        "\n"
        "function ff_h264_idct8_add_neon",
        NEW_IDCT_EPILOGUE +
        "        ret\n"
        "endfunc\n"
        "\n"
        "function ff_h264_idct8_add_neon"
    )
    print("6b. ff_h264_idct_add_neon epilogue: done")
else:
    print("6b. ff_h264_idct_add_neon epilogue: already done")

# 7a. ff_h264_idct8_add_neon prologue
if "function ff_h264_idct8_add_neon, export=1\n.global" in content:
    # Check if already patched
    marker = "        AARCH64_VALID_CALL_TARGET\n" + ALL_8 + "        movi"
    if marker not in content:
        content = replace_exact(content,
            "        AARCH64_VALID_CALL_TARGET\n"
            "        movi            v19.8h,   #0",
            "        AARCH64_VALID_CALL_TARGET\n" +
            ALL_8 +
            "        movi            v19.8h,   #0"
        )
        print("7a. ff_h264_idct8_add_neon prologue: done")
    else:
        print("7a. ff_h264_idct8_add_neon prologue: already done")

# 7b. ff_h264_idct8_add_neon epilogue
if ALL_8_RESTORE + "        ret\nendfunc\n\nfunction ff_put_h264_chroma_mc8_neon" not in content:
    content = add_restore_before_ret_endfunc(content, "ff_put_h264_chroma_mc8_neon", ALL_8_RESTORE)
    print("7b. ff_h264_idct8_add_neon epilogue: done")
else:
    print("7b. ff_h264_idct8_add_neon epilogue: already done")

# 8a. ff_put_h264_chroma_mc8_neon prologue
if "function ff_put_h264_chroma_mc8_neon, export=1\n" + FIVE_REGS not in content:
    content = replace_exact(content,
        "function ff_put_h264_chroma_mc8_neon, export=1\n"
        "        prfm            pldl1strm, [x1]\n",
        "function ff_put_h264_chroma_mc8_neon, export=1\n" +
        FIVE_REGS +
        "        prfm            pldl1strm, [x1]\n"
    )
    print("8a. ff_put_h264_chroma_mc8_neon prologue: done")
else:
    print("8a. ff_put_h264_chroma_mc8_neon prologue: already done")

# 8b. chroma ret 1 (before "// --- fallback paths")
anchor1 = "        st1 {v30.8B}, [x0], x2\n        ret\n\n        // --- fallback paths"
if FIVE_REGS_RESTORE + "        ret\n\n        // --- fallback paths" not in content:
    content = replace_exact(content,
        "        st1 {v30.8B}, [x0], x2\n"
        "        ret\n"
        "\n"
        "        // --- fallback paths",
        "        st1 {v30.8B}, [x0], x2\n" +
        FIVE_REGS_RESTORE +
        "        ret\n"
        "\n"
        "        // --- fallback paths"
    )
    print("8b. chroma ret1: done")
else:
    print("8b. chroma ret1: already done")

# 8c. chroma ret 2 (before "4:")
if FIVE_REGS_RESTORE + "        ret\n\n4:      ld1" not in content:
    content = replace_exact(content,
        "        b.gt            3b\n"
        "        ret\n"
        "\n"
        "4:      ld1",
        "        b.gt            3b\n" +
        FIVE_REGS_RESTORE +
        "        ret\n"
        "\n"
        "4:      ld1"
    )
    print("8c. chroma ret2: done")
else:
    print("8c. chroma ret2: already done")

# 8d. chroma ret 3 (before "5:")
if FIVE_REGS_RESTORE + "        ret\n\n5:      ld1" not in content:
    content = replace_exact(content,
        "        b.gt            4b\n"
        "        ret\n"
        "\n"
        "5:      ld1",
        "        b.gt            4b\n" +
        FIVE_REGS_RESTORE +
        "        ret\n"
        "\n"
        "5:      ld1"
    )
    print("8d. chroma ret3: done")
else:
    print("8d. chroma ret3: already done")

# 8e. chroma ret 4 (at endfunc - end of file)
if FIVE_REGS_RESTORE + "        ret\nendfunc\n" not in content:
    content = replace_exact(content,
        "        b.gt            5b\n"
        "        ret\n"
        "endfunc\n",
        "        b.gt            5b\n" +
        FIVE_REGS_RESTORE +
        "        ret\n"
        "endfunc\n"
    )
    print("8e. chroma ret4: done")
else:
    print("8e. chroma ret4: already done")

with open('FFmpeg/libavcodec/aarch64/h264_slothy_a55.S', 'w') as f:
    f.write(content)
print("File written successfully.")
