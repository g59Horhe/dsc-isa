/* Shared definitions for the pointwise (1x1) convolution kernels.
 *
 * Layout is channel-last so that CI consecutive input channels of one pixel
 * are contiguous: input[P][CI], weight[CO][CI], output[P][CO], with
 * P = H*W pixels. Each output is a CI-long dot product, requantised with
 * the shared requant.h. CI and CO are multiples of 4 and the arrays are
 * 4-byte aligned, so every SIMD word load is aligned and all four lanes
 * carry data. Same LCG data as the depthwise kernels.
 */
#ifndef PW_COMMON_H
#define PW_COMMON_H
#include "bench.h"
#include "requant.h"
#ifndef CI
#define CI 16
#endif
#ifndef CO
#define CO 16
#endif
#ifndef H
#define H 8
#endif
#ifndef W
#define W 8
#endif
#define P (H * W)
static act_t input[P][CI]  __attribute__((aligned(4)));
static signed char weight[CO][CI] __attribute__((aligned(4)));
static out_t output[P][CO];
static unsigned int rng_state;
static int rnd(void) { rng_state = rng_state * 1103515245u + 12345u; return (int)((rng_state >> 16) & 0xFF) - 128; }
#ifdef REAL_DATA
#include "real_init.h"
REAL_INIT(input, P*CI, weight, CO*CI)
#else
static void init_data(void) {
    rng_state = 1;
    for (int p = 0; p < P; p++) for (int c = 0; c < CI; c++) input[p][c] = (signed char)(rnd() >> 2);
    for (int o = 0; o < CO; o++) for (int c = 0; c < CI; c++) weight[o][c] = (signed char)(rnd() >> 3);
}
#endif
static int checksum(void) {
    int sum = 0;
    for (int p = 0; p < P; p++) for (int o = 0; o < CO; o++) sum += output[p][o];
    return sum & 0xFFFF;
}
#endif
