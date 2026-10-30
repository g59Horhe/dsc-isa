/* PULP-NN's pulp_nn_depthwise_3x3_s1, unchanged (sw/pulpnn/), on this study's
 * 3x3 depthwise data: input [CH][H][W], weight [CH][3][3], valid convolution.
 *
 * The kernel reads CHW and writes HWC. It supports only p_l = p_r = 1 (with
 * zero padding its row pointer drifts two bytes per row): it computes all W
 * columns of each of the OH = H - 2 rows, zero-padded left and right, so it
 * does W/OW times the outputs of the valid kernels (16/14 at W = 16).
 * Columns 1..W-2 are the valid outputs and the checksum covers only those;
 * compare per output, not per call. Requantisation:
 * flag_relu = flag_batch_norm = 0 gives clip(acc >> out_shift), the same as
 * requant.h. The checksum is the same sum as the other dw3 kernels', which
 * does not depend on the output layout.
 *
 * Build: -O3 -Isw/pulpnn/include -march=rv32imc_xcvsimd_xcvalu
 * -Wno-error=int-conversion; REAL_DATA as for the other kernels. Without
 * REAL_DATA, PULPNN_SIGNED maps the dot product and clip to their int8 forms
 * (pmsis.h).
 */
#include "bench.h"
#include "requant.h"
#ifndef REAL_DATA
#define PULPNN_SIGNED 1
#endif
/* the kernel names its channel-count parameter CH, which -DCH=... would rewrite */
#pragma push_macro("CH")
#undef CH
/* PULPNN_LIB=1 (default): compiled as a library would be. noipa on a
 * redeclaration (the definition is unchanged) stops GCC inlining the kernel or
 * specialising it for this call's constant shape, which a separately compiled
 * PULP-NN never sees. PULPNN_LIB=0 lets GCC specialise it, as the hand kernels
 * are specialised by their -D shape constants. */
#ifndef PULPNN_LIB
#define PULPNN_LIB 1
#endif
#if PULPNN_LIB
#define PN_NOIPA __attribute__((noipa))
#else
#define PN_NOIPA
#endif
#include <stdint.h>
void pulp_nn_depthwise_3x3_s1(uint8_t *, uint8_t *, int, int, int, int, int, int8_t *, int8_t, uint16_t,
                              int32_t *, int32_t *, int, int, unsigned int *) PN_NOIPA;
#include "pulpnn/src/pulp_nn_depthwise_3x3_s1.c"
#include "pulpnn/pulp_nn_quant.c"
#pragma pop_macro("CH")
#ifndef CH
#define CH 8
#endif
#ifndef H
#define H 16
#endif
#ifndef W
#define W 16
#endif
#define K 3
#define OH (H - K + 1)
#define OW (W - K + 1)

static act_t input[CH][H][W] __attribute__((aligned(4)));
static signed char weight[CH][K][K];
static unsigned char output[OH][W][CH] __attribute__((aligned(4)));

static unsigned int rng_state;
static int rnd(void) { rng_state = rng_state * 1103515245u + 12345u; return (int)((rng_state >> 16) & 0xFF) - 128; }
#ifdef REAL_DATA
#include "real_init.h"
REAL_INIT(input, CH*H*W, weight, CH*K*K)
#else
static void init_data(void) {
    rng_state = 1;
    for (int c = 0; c < CH; c++) {
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) input[c][y][x] = (signed char)(rnd() >> 2);
        for (int i = 0; i < K; i++) for (int j = 0; j < K; j++) weight[c][i][j] = (signed char)(rnd() >> 3);
    }
}
#endif

int main(void) {
    BENCH_PAD();
    init_data();
    CYC_START();
    pulp_nn_depthwise_3x3_s1((uint8_t *)input, &output[0][0][0], H, W, CH, 1, 1,
                             &weight[0][0][0], SHIFT, 1, NULL, NULL, 0, 0, NULL);
    CYC_STOP();
    int sum = 0;
    for (int y = 0; y < OH; y++) for (int x = 1; x <= OW; x++) for (int c = 0; c < CH; c++) sum += (out_t)output[y][x][c];
    return sum & 0xFFFF;
}
