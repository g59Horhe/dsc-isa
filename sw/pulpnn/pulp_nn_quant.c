/*
 * pulp_nn_quant.c: the two functions of PULP-NN's 32bit/src/pulp_nn_utils.c
 * that the ported kernels reference, copied verbatim (lines 35-45 and 148-156
 * at commit 288d06b7e3; Copyright (C) 2018-2020 University of Bologna,
 * Apache License 2.0, see LICENSE). The rest of pulp_nn_utils.c (im2col via
 * MCHAN DMA, sub-byte conversions, pooling helpers) is not used. With
 * flag_relu = flag_batch_norm = 0 the kernels never call these; they are
 * here so the kernels link unchanged.
 */
#include "pmsis.h"
#include "pulp_nn_utils.h"

uint8_t __attribute__((always_inline)) pulp_nn_bn_quant_u8 (
  int32_t phi,
  int32_t k,
  int32_t lambda,
  int8_t  d
) {
  int32_t integer_image_phi = (k * phi) + lambda;
  int32_t x = (integer_image_phi) >> d;
  uint8_t res = __builtin_pulp_clipu_r(x,255);
  return res;
}

uint8_t __attribute__((always_inline)) pulp_nn_quant_u8(
  int32_t phi,
  int16_t m,
  int8_t  d
) {
  int16_t x = (m * phi) >> d;
  uint8_t res = __builtin_pulp_clipu_r(x,255);
  return res;
}
