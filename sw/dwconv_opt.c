/* int8 depthwise 3x3 convolution -- hand-optimised scalar.
 *
 * Same shape, same data, same checksum as dwconv.c. No custom instructions,
 * no SIMD. Everything here is available on plain RV32IMC.
 *
 * Three changes from the naive version:
 *   1. Weights hoisted into registers once per channel. In depthwise conv
 *      the nine weights are constant across the whole spatial map, so
 *      reloading them per MAC (which GCC did) is pure waste.
 *   2. Row pointers walked with increments instead of recomputed from
 *      [c][y][x] indices, removing the two address adds per MAC.
 *   3. The 3x3 inner loops fully unrolled, removing loop control from the
 *      MAC path entirely.
 *
 * This is the honest denominator. Any speedup claimed for custom hardware
 * has to be measured against this, not against naive C.
 */

#include "bench.h"
#include "requant.h"   /* shared saturating requantisation; also act_t/out_t */

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
#ifndef SHIFT
#define SHIFT 7
#endif
#ifndef DW_OUT_PTR
#define DW_OUT_PTR(ch) (&output[ch][0][0])   /* block.c redirects this into the pointwise input */
#endif
#ifndef OSTRIDE
#define OSTRIDE 1
#endif

static act_t input[CH][H][W] __attribute__((aligned(4)));
static signed char weight[CH][K][K];
static out_t output[CH][OH][OW];

static unsigned int rng_state;
static int rnd(void) {
    rng_state = rng_state * 1103515245u + 12345u;
    return (int)((rng_state >> 16) & 0xFF) - 128;
}

#ifdef REAL_DATA
#include "real_init.h"
REAL_INIT(input, CH*H*W, weight, CH*K*K)
#else
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
#endif


static void dwconv_opt(void) {
    for (int c = 0; c < CH; c++) {
        const signed char *wp = &weight[c][0][0];

        /* Nine weights live in registers for the whole channel. */
        const int w00 = wp[0], w01 = wp[1], w02 = wp[2];
        const int w10 = wp[3], w11 = wp[4], w12 = wp[5];
        const int w20 = wp[6], w21 = wp[7], w22 = wp[8];

        out_t *op = DW_OUT_PTR(c);

        for (int oy = 0; oy < OH; oy++) {
            /* Three row pointers, advanced by one byte per output pixel. */
            const act_t *r0 = &input[c][oy + 0][0];
            const act_t *r1 = &input[c][oy + 1][0];
            const act_t *r2 = &input[c][oy + 2][0];

            for (int ox = 0; ox < OW; ox++) {
                int acc = r0[0] * w00 + r0[1] * w01 + r0[2] * w02
                        + r1[0] * w10 + r1[1] * w11 + r1[2] * w12
                        + r2[0] * w20 + r2[1] * w21 + r2[2] * w22;
#if OSTRIDE == 1
                *op++ = requant(acc);            /* unchanged default: the measured baseline */
#else
                *op = requant(acc); op += OSTRIDE;
#endif
                r0++; r1++; r2++;
            }
        }
    }
}

#ifndef NO_MAIN
int main(void) {
    BENCH_PAD();
    init_data();

    CYC_START();
    dwconv_opt();
    CYC_STOP();

    int sum = 0;
    for (int c = 0; c < CH; c++)
        for (int y = 0; y < OH; y++)
            for (int x = 0; x < OW; x++)
                sum += output[c][y][x];
    return sum & 0xFFFF;
}
#endif
