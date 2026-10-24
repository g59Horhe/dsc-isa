/* One depthwise-separable block on real MobileNetV1 data: depthwise 3x3
 * (CH channels, HxW, channel-first) -> ReLU6 requantisation -> layout
 * change to channel-last -> pointwise 1x1 (CI = CH -> CO).
 *
 * Stages are the existing kernels, included as source with their statics
 * renamed. Build options:
 *   -DBLOCK_SIMD=1     SIMD hand kernels (dwconv_simd_asm.c, pwconv_simd_asm.c);
 *                      default: C kernels (dwconv_opt.c, pwconv.c)
 *   -DBLOCK_FUSED=1    the depthwise stage writes channel-last directly with a
 *                      strided store (OSTRIDE = CH), no separate transform
 *   -DXPULP_CTRL=1 -DREQUANT_CLIP=1 as usual for the asm stages
 * Always REAL_DATA with -DREAL_HDR=real/block_16x16x16_16.h, which defines
 * REAL_SHIFT (depthwise) and PW_REAL_SHIFT (pointwise).
 * Returns the pointwise checksum; the depthwise checksum is reported on AUX.
 */
#define REAL_DATA 1
#define NO_MAIN
#ifndef BLOCK_SIMD
#define BLOCK_SIMD 0
#endif
#ifndef BLOCK_FUSED
#define BLOCK_FUSED 0
#endif
#define CH 16
#define H 16
#define W 16
#define CO 16
#define PWP ((16 - 2) * (16 - 2))   /* literal: H and W are redefined for the pointwise stage below */

/* pointwise input/output arrays, declared first so the depthwise stage can
   target them when fused */
#include "bench.h"
#include "requant.h"        /* act_t, out_t, data header via REAL_HDR */
static act_t pw_input[PWP][CH] __attribute__((aligned(4)));
static signed char pw_weight[CO][CH] __attribute__((aligned(4)));
static out_t pw_output[PWP][CO];

/* ---- depthwise stage ---- */
#if BLOCK_FUSED
#define OSTRIDE CH
#define DW_OUT_PTR(ch) ((out_t *)&pw_input[0][0] + (ch))
#endif
#if BLOCK_SIMD
#include "dwconv_simd_asm.c"
static void dw_run(void) { dwconv_simd_asm(); }
#else
#include "dwconv_opt.c"
static void dw_run(void) { dwconv_opt(); }
#endif
/* capture the depthwise stage's symbols before the pointwise include renames them */
static void dw_init(void) { init_data(); }
static out_t *const dw_out_base = &output[0][0][0];
static const act_t *const dw_in_base = &input[0][0][0];
static const signed char *const dw_w_base = &weight[0][0][0];

/* ---- pointwise stage: rename everything the second kernel defines ---- */
#undef H
#undef W
#undef XS
#undef S_
#define H (16 - 2)
#define W (16 - 2)
#define CI CH
#define PW_EXTERNAL_DATA
#define input pw_input
#define weight pw_weight
#define output pw_output
#define rng_state pw_rng_state
#define rnd pw_rnd
#define init_data pw_init_data_unused
#define checksum pw_checksum
#define real_weight pw_real_weight
#undef SHIFT
#define SHIFT PW_REAL_SHIFT
/* requant() was instantiated with the depthwise shift; give the pointwise stage its own */
static inline unsigned char pw_requant(int acc) {
    int t, u; asm (REQUANT_ASM("%0", "%1", "%2") : "+r"(acc), "=&r"(t), "=&r"(u)); return (unsigned char)acc;
}
#define requant pw_requant
#if BLOCK_SIMD
#include "pwconv_simd_asm.c"
#define PW_RUN pwconv_simd_asm
#else
#include "pwconv.c"
#define PW_RUN pwconv
#endif
#undef input
#undef weight
#undef output

/* channel-first [CH][OH][OW] -> channel-last [P][CH] */
static void transform(void) {
    const out_t *src = dw_out_base;
    for (int c = 0; c < CH; c++)
        for (int p = 0; p < PWP; p++) pw_input[p][c] = src[c * PWP + p];
}

int main(void) {
    BENCH_PAD();
    dw_init();
    for (int i = 0; i < CO * CH; i++) (&pw_weight[0][0])[i] = pw_real_weight[i];
    CYC_START();
    dw_run();
#if !BLOCK_FUSED
    transform();
#endif
    PW_RUN();
    CYC_STOP();
#ifdef BLOCK_DEBUG
    { unsigned int si = 0, sw_ = 0; for (int i = 0; i < CH * 16 * 16; i++) si += dw_in_base[i]; for (int i = 0; i < CH * 9; i++) sw_ += (int)dw_w_base[i];
      *(volatile unsigned int *)0x1000000C = si; *(volatile unsigned int *)0x1000000C = sw_; }
    { unsigned int a = 0, b = 0, c = 0;
      for (int i = 0; i < CH * PWP; i++) a += dw_out_base[i];
      for (int i = 0; i < CH * PWP; i++) b += ((const out_t *)&pw_input[0][0])[i];
      for (int i = 0; i < CO * PWP; i++) c += ((const out_t *)&pw_output[0][0])[i];
      *(volatile unsigned int *)0x1000000C = a; *(volatile unsigned int *)0x1000000C = b; *(volatile unsigned int *)0x1000000C = c; }
#endif
    /* depthwise checksum on AUX for verification */
    unsigned int s1 = 0; const out_t *q = BLOCK_FUSED ? (const out_t *)&pw_input[0][0] : dw_out_base;
    for (int i = 0; i < CH * PWP; i++) s1 += q[i];
    *(volatile unsigned int *)0x1000000C = s1 & 0xFFFF;
    return pw_checksum();
}
