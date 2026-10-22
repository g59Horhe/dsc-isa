/* int8 depthwise 3x3 convolution -- cv.dotsp.b with aligned loads only.
 *
 * Requires COREV_PULP=1.
 *
 * The unaligned variant (dwconv_simd.c) loads a fresh word per output
 * pixel, so two in three are misaligned and the LSU splits them into two
 * bus accesses. This version trades that penalty for shift-and-merge work.
 *
 * Four consecutive output pixels need activation bytes a0..a5 from each
 * row. Two aligned word loads cover a0..a7:
 *
 *     w0 = {a0,a1,a2,a3}      w1 = {a4,a5,a6,a7}
 *
 * and the four windows come out by shifting:
 *
 *     pixel 0:  w0                        -> {a0,a1,a2,*}
 *     pixel 1:  w0 >> 8                   -> {a1,a2,a3,0}
 *     pixel 2:  (w0 >> 16) | (w1 << 16)   -> {a2,a3,a4,a5}
 *     pixel 3:  (w0 >> 24) | (w1 <<  8)   -> {a3,a4,a5,a6}
 *
 * The fourth lane is always multiplied by a zero weight, so whatever lands
 * there is harmless.
 *
 * Two aligned loads plus six shift/or ops per row per four pixels, versus
 * four unaligned loads. Whether that is a win is the measurement.
 *
 * OW is 14, so the 4-wide loop covers 12 pixels and the last two fall back
 * to the unaligned path.
 */

#include "bench.h"

#ifndef CH
#define CH   8
#endif
#ifndef H
#define H    16
#endif
#ifndef W
#define W    16
#endif
#define K    3
#define OH   (H - K + 1)
#define OW   (W - K + 1)
#define SHIFT 7

static signed char input[CH][H][W] __attribute__((aligned(4)));
static signed char weight[CH][K][K];
static signed char output[CH][OH][OW];

static inline int cv_dotsp_b(unsigned int a, unsigned int b) {
    int r;
    asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2"
                  : "=r"(r) : "r"(a), "r"(b));
    return r;
}

static unsigned int rng_state;
static int rnd(void) {
    rng_state = rng_state * 1103515245u + 12345u;
    return (int)((rng_state >> 16) & 0xFF) - 128;
}

static void init_data(void) {
    rng_state = 1;
    for (int c = 0; c < CH; c++) {
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                input[c][y][x] = (signed char)(rnd() >> 2);
        for (int i = 0; i < K; i++)
            for (int j = 0; j < K; j++)
                weight[c][i][j] = (signed char)(rnd() >> 3);
    }
}

/* Branchless saturation.
 *
 * The obvious form --
 *     if (acc >  127) acc =  127;
 *     if (acc < -128) acc = -128;
 * -- puts two data-dependent branches on the per-output-pixel path. How
 * often they are taken depends on the test data, and on CV32E40P a taken
 * branch costs extra cycles. Measured effect: using the branching form
 * shifted the aligned/unaligned cycle ratio by up to 10% and made the
 * result appear to depend on channel count when it does not.
 *
 * Benchmarks of quantised kernels that saturate with branches are partly
 * measuring their input distribution. Use this form instead. */
static signed char requant(int acc) {
    acc >>= SHIFT;
    acc = acc ^ ((acc ^  127) & -(acc >  127));
    acc = acc ^ ((acc ^ -128) & -(acc < -128));
    return (signed char)acc;
}

static inline unsigned int pack3(int a, int b, int c) {
    return ((unsigned)(a & 0xFF))
         | ((unsigned)(b & 0xFF) << 8)
         | ((unsigned)(c & 0xFF) << 16);
}

static void dwconv_simd_al(void) {
    for (int ch = 0; ch < CH; ch++) {
        const signed char *wp = &weight[ch][0][0];
        const unsigned int wr0 = pack3(wp[0], wp[1], wp[2]);
        const unsigned int wr1 = pack3(wp[3], wp[4], wp[5]);
        const unsigned int wr2 = pack3(wp[6], wp[7], wp[8]);

        signed char *op = &output[ch][0][0];

        for (int oy = 0; oy < OH; oy++) {
            const signed char *r0 = &input[ch][oy + 0][0];
            const signed char *r1 = &input[ch][oy + 1][0];
            const signed char *r2 = &input[ch][oy + 2][0];

            int ox = 0;

            /* 4 output pixels per iteration, aligned loads only. */
            for (; ox + 4 <= OW; ox += 4) {
                const unsigned int *p0 = (const unsigned int *)(const void *)(r0 + ox);
                const unsigned int *p1 = (const unsigned int *)(const void *)(r1 + ox);
                const unsigned int *p2 = (const unsigned int *)(const void *)(r2 + ox);

                unsigned int a0l = p0[0], a0h = p0[1];
                unsigned int a1l = p1[0], a1h = p1[1];
                unsigned int a2l = p2[0], a2h = p2[1];

                int acc;

                acc = cv_dotsp_b(a0l, wr0)
                    + cv_dotsp_b(a1l, wr1)
                    + cv_dotsp_b(a2l, wr2);
                *op++ = requant(acc);

                acc = cv_dotsp_b(a0l >> 8, wr0)
                    + cv_dotsp_b(a1l >> 8, wr1)
                    + cv_dotsp_b(a2l >> 8, wr2);
                *op++ = requant(acc);

                acc = cv_dotsp_b((a0l >> 16) | (a0h << 16), wr0)
                    + cv_dotsp_b((a1l >> 16) | (a1h << 16), wr1)
                    + cv_dotsp_b((a2l >> 16) | (a2h << 16), wr2);
                *op++ = requant(acc);

                acc = cv_dotsp_b((a0l >> 24) | (a0h << 8), wr0)
                    + cv_dotsp_b((a1l >> 24) | (a1h << 8), wr1)
                    + cv_dotsp_b((a2l >> 24) | (a2h << 8), wr2);
                *op++ = requant(acc);
            }

            /* Tail: OW is not a multiple of 4. */
            for (; ox < OW; ox++) {
                unsigned int a0 = *(const unsigned int *)(const void *)(r0 + ox);
                unsigned int a1 = *(const unsigned int *)(const void *)(r1 + ox);
                unsigned int a2 = *(const unsigned int *)(const void *)(r2 + ox);
                int acc = cv_dotsp_b(a0, wr0)
                        + cv_dotsp_b(a1, wr1)
                        + cv_dotsp_b(a2, wr2);
                *op++ = requant(acc);
            }
        }
    }
}

int main(void) {
    init_data();

    CYC_START();
    dwconv_simd_al();
    CYC_STOP();

    int sum = 0;
    for (int c = 0; c < CH; c++)
        for (int y = 0; y < OH; y++)
            for (int x = 0; x < OW; x++)
                sum += output[c][y][x];
    return sum & 0xFFFF;
}
