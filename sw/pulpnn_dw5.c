/* PULP-NN's pulp_nn_depthwise_generic, unchanged (sw/pulpnn/), on this study's
 * KxK depthwise data from dw_common.h (K = 5 by default; synthetic int8 data,
 * so PULPNN_SIGNED is on, see pmsis.h). The kernel also does (K*K)&3 MACs per
 * output in plain C with the activation typed uint8_t; for int8 activations
 * the include below is wrapped in #define uint8_t int8_t, which retypes the
 * kernel's activation, buffer and output bytes (lb for lbu, same cost) without
 * editing its source. Valid convolution: no padding,
 * stride 1. Per output column the kernel copies a K-wide strip of the input
 * into bufferC (K * (H + 1) bytes), then takes (K*K)>>2 four-lane dot products
 * and (K*K)&3 scalar MACs per output. Output is HWC; the checksum sums the same
 * values as the other dw5 kernels'.
 *
 * Build: -O3 -Isw/pulpnn/include -march=rv32imc_xcvsimd_xcvalu
 * -Wno-error=int-conversion.
 */
#include <stdint.h>
#include "dw_common.h"
#define PULPNN_SIGNED 1
#define uint8_t int8_t
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
void pulp_nn_depthwise_generic(const uint8_t *, uint8_t *, const int8_t *, uint8_t *, const int8_t *, uint8_t *, int32_t *,
                               int32_t *, uint16_t, uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t,
                               const uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t,
                               const uint16_t, const uint16_t, const uint16_t, const uint16_t, int8_t, int8_t) PN_NOIPA;
#include "pulpnn/src/pulp_nn_depthwise_generic.c"
#include "pulpnn/pulp_nn_quant.c"   /* under the same #define: pulp_nn_utils.h has no include guard */
#undef uint8_t

static unsigned char out_hwc[OH][OW][CH];
static unsigned char strip[K * (H + 1)] __attribute__((aligned(4)));

int main(void) {
    BENCH_PAD();
    init_data();
    CYC_START();
    pulp_nn_depthwise_generic((int8_t *)input, (int8_t *)strip, NULL, (int8_t *)&out_hwc[0][0][0], &weight[0][0][0], NULL,
                              NULL, NULL, 1, SHIFT, W, H, CH, OW, OH, CH, K, K, 0, 0, 0, 0, 1, 1, 0, 0);
    CYC_STOP();
    int sum = 0;
    for (int y = 0; y < OH; y++) for (int x = 0; x < OW; x++) for (int c = 0; c < CH; c++) sum += (signed char)out_hwc[y][x][c];
    return sum & 0xFFFF;
}
