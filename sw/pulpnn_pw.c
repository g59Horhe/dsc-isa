/* PULP-NN's pulp_nn_pointwise_HoWo_parallel and pulp_nn_matmul, unchanged
 * (sw/pulpnn/), on this study's pointwise data from pw_common.h: input [P][CI],
 * weight [CO][CI], output [P][CO], the layout PULP-NN uses. 1x1 kernel, no
 * padding, stride 1, no bias; flag_relu = flag_batch_norm = 0 gives
 * clip(acc >> out_shift), the same as requant.h. The matmul computes two
 * pixels by four output channels per inner loop (eight accumulators).
 *
 * Build: -O3 -Isw/pulpnn/include -march=rv32imc_xcvsimd_xcvalu; REAL_DATA as
 * for the other kernels. Without REAL_DATA, PULPNN_SIGNED maps the dot
 * product and clip to their int8 forms (pmsis.h).
 */
#include "pw_common.h"
#ifndef REAL_DATA
#define PULPNN_SIGNED 1
#endif
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
uint8_t *pulp_nn_matmul(const int8_t *, uint8_t *, uint16_t, uint16_t, uint16_t, uint16_t, int32_t *, int32_t *,
                        const int8_t *, uint8_t *, uint8_t *, int, int) PN_NOIPA;
void pulp_nn_pointwise_HoWo_parallel(const uint8_t *, uint8_t *, const int8_t *, uint8_t *, const int8_t *, int32_t *,
                                     int32_t *, const uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t,
                                     const uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t,
                                     const uint16_t, const uint16_t, const uint16_t, const uint16_t, const uint16_t, int, int)
                                     PN_NOIPA;
#include "pulpnn/src/pulp_nn_matmul.c"
#include "pulpnn/src/pulp_nn_pointwise_HoWo_parallel.c"
#include "pulpnn/pulp_nn_quant.c"

int main(void) {
    BENCH_PAD();
    init_data();
    CYC_START();
    pulp_nn_pointwise_HoWo_parallel((uint8_t *)input, NULL, NULL, (uint8_t *)output, &weight[0][0], NULL, NULL,
                                    1, SHIFT, W, H, CI, W, H, CO, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0);
    CYC_STOP();
    return checksum();
}
