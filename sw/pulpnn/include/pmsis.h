/*
 * pmsis.h: stand-in for the PULP SDK header that PULP-NN's kernels include,
 * for one CV32E40P core built with upstream GCC (-march=rv32imc_xcvsimd_xcvalu).
 * Not part of PULP-NN. The kernels are compiled unchanged; everything they
 * need from the SDK is here:
 *
 *  - v4s / v4u, the 4 x 8-bit vector types;
 *  - one core: pi_core_id() is 0, NUM_CORES is 1, the team barrier is empty,
 *    so each kernel's chunking covers all channels or rows;
 *  - the RI5CY (XpulpV2) builtins the four kernels use, mapped to GCC's
 *    CORE-V builtins, which emit the same operations under CV32E40P's cv.*
 *    encodings (checked against sw/xpulp.h):
 *      __builtin_pulp_sdotusp4(a, b, c)  cv.sdotusp.b  c += a(u8) . b(s8)
 *      __builtin_pulp_clipu_r(x, 255)    cv.clipu x, 9 clamp(x, 0, 255)
 *      __builtin_pulp_clipu(x, 0, 255)   cv.clipu x, 9
 *      __builtin_pulp_shuffleb(a, m)     cv.shuffle.b
 *      __builtin_pulp_fl1(x)             index of the highest set bit
 *
 * PULPNN_SIGNED=1 (the synthetic datasets, int8 activations and outputs):
 * the u8 x s8 dot product becomes cv.sdotsp.b (s8 x s8, same cost) and the
 * 0..255 clip becomes cv.clip x, 8 (-128..127), matching requant.h. These two
 * mappings are the only departure from PULP-NN's arithmetic, and they apply
 * only in this mode.
 *
 * Upstream GCC has no CORE-V hardware-loop or post-increment support, so the
 * kernels' loops compile to RV32IMC control; PULP's own GCC fork would emit
 * cv.setup and post-increment loads here.
 */
#ifndef PMSIS_SHIM_H
#define PMSIS_SHIM_H
#include <stdint.h>
#include <stddef.h>

typedef int8_t  v4s __attribute__((vector_size(4)));
typedef uint8_t v4u __attribute__((vector_size(4)));

#define NUM_CORES 1
static inline int pi_core_id(void) { return 0; }
#define pi_cl_team_barrier(id) do { } while (0)

#define PN_U32(x) ((uint32_t)(x))
/* PULPNN_NOCLIP=1 (reviewer question Q1): saturate with the study's branch-free sequence
 * (sw/requant.h without its shift) instead of cv.clip/cv.clipu, to measure clip's value
 * inside PULP-NN. */
static inline int pn_sat_u8(int x) {   /* clamp(x, 0, 255): 7 instructions, no branch */
    int t; __asm__ ("srai %1,%0,31\n xori %1,%1,-1\n and %0,%0,%1\n sltiu %1,%0,256\n addi %1,%1,-1\n or %0,%0,%1\n andi %0,%0,255" : "+r"(x), "=&r"(t)); return x; }
static inline int pn_sat_s8(int x) {   /* clamp(x, -128, 127): 8 instructions, no branch */
    int t, u; __asm__ ("addi %1,%0,128\n sltiu %1,%1,256\n addi %1,%1,-1\n srai %2,%0,31\n xori %2,%2,127\n xor %2,%2,%0\n and %2,%2,%1\n xor %0,%0,%2" : "+r"(x), "=&r"(t), "=&r"(u)); return x; }
#if PULPNN_NOCLIP && PULPNN_SIGNED
#define __builtin_pulp_sdotusp4(a, b, c) ((int)__builtin_riscv_cv_simd_sdotsp_b(PN_U32(a), PN_U32(b), (c)))
#define __builtin_pulp_clipu_r(x, m)     pn_sat_s8(x)
#define __builtin_pulp_clipu(x, lo, hi)  pn_sat_s8(x)
#elif PULPNN_NOCLIP
#define __builtin_pulp_sdotusp4(a, b, c) ((int)__builtin_riscv_cv_simd_sdotusp_b(PN_U32(a), PN_U32(b), (c)))
#define __builtin_pulp_clipu_r(x, m)     pn_sat_u8(x)
#define __builtin_pulp_clipu(x, lo, hi)  pn_sat_u8(x)
#elif PULPNN_SIGNED
#define __builtin_pulp_sdotusp4(a, b, c) ((int)__builtin_riscv_cv_simd_sdotsp_b(PN_U32(a), PN_U32(b), (c)))
#define __builtin_pulp_clipu_r(x, m)     __builtin_riscv_cv_alu_clip((x), 127)
#define __builtin_pulp_clipu(x, lo, hi)  __builtin_riscv_cv_alu_clip((x), 127)
#else
#define __builtin_pulp_sdotusp4(a, b, c) ((int)__builtin_riscv_cv_simd_sdotusp_b(PN_U32(a), PN_U32(b), (c)))
#define __builtin_pulp_clipu_r(x, m)     __builtin_riscv_cv_alu_clipu((x), (m))
#define __builtin_pulp_clipu(x, lo, hi)  __builtin_riscv_cv_alu_clipu((x), (hi))
#endif
#define __builtin_pulp_shuffleb(a, m)    ((v4s)__builtin_riscv_cv_simd_shuffle_b(PN_U32(a), PN_U32(m)))
#define __builtin_pulp_fl1(x)            (31 - __builtin_clz(x))
#endif
