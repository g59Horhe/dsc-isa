/* Pointwise 1x1 convolution -- hand-written cv.dotsp.b inner loop.
 *
 * The CI/4 activation words of one pixel are held in registers across all CO
 * output channels; each output costs CI/4 aligned weight-word loads, one
 * cv.dotsp.b plus CI/4-1 accumulating cv.sdotsp.b, the shared
 * requantisation and one store. All four lanes carry data.
 * The output-channel loop body is generated for CI = 8 and 16 (see
 * sw/gen_pwconv_asm.py); other CI values fall back to a compile error.
 * XPULP_CTRL=0: RV32IMC control (immediate-offset loads, addi + bne).
 * XPULP_CTRL=1: hardware loop over output channels, post-increment loads
 *               and stores.
 */
#include "pw_common.h"
#include "xpulp.h"
#ifndef XPULP_CTRL
#define XPULP_CTRL 0
#endif
#define DOTSP(rd, rs1, rs2)  ".insn r 0x7b, 0x1, 0x48, " rd ", " rs1 ", " rs2 "\n"   /* cv.dotsp.b  rd  = dot */
#define SDOTSP(rd, rs1, rs2) ".insn r 0x7b, 0x1, 0x54, " rd ", " rs1 ", " rs2 "\n"   /* cv.sdotsp.b rd += dot */

static void pwconv_simd_asm(void) {
    for (int p = 0; p < P; p++) {
        const signed char *xp_ = input[p];
        const signed char *wp = &weight[0][0];
        signed char *op = &output[p][0];
        int acc, t, u; unsigned int w0, w1, w2, w3; (void)w2; (void)w3;
#if CI == 8 && XPULP_CTRL == 1
        unsigned int x0, x1;
        int cnt = CO;
        asm volatile (
              XPULP_ASM_BEGIN
              "lw %[x0],0(%[xp])\n"
              "lw %[x1],4(%[xp])\n"
              HWLOOP0("%[cnt]", "15")   /* 14 instructions in the body */
              LW_INC("%[w0]", "%[wp]", "4")
              LW_INC("%[w1]", "%[wp]", "4")
              DOTSP("%[acc]", "%[x0]", "%[w0]")
              SDOTSP("%[acc]", "%[x1]", "%[w1]")
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              SB_INC("%[acc]", "%[op]", "1")
              
              XPULP_ASM_END
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1),
                [x0]"=&r"(x0), [x1]"=&r"(x1)
              : [xp]"r"(xp_), [cnt]"r"(cnt)
              : "memory");
#endif
#if CI == 8 && XPULP_CTRL == 0
        unsigned int x0, x1;
        const signed char *wend = wp + CO * CI;
        asm volatile (
              
              "lw %[x0],0(%[xp])\n"
              "lw %[x1],4(%[xp])\n"
              "1:\n"
              "lw %[w0],0(%[wp])\n"
              "lw %[w1],4(%[wp])\n"
              DOTSP("%[acc]", "%[x0]", "%[w0]")
              SDOTSP("%[acc]", "%[x1]", "%[w1]")
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              "sb %[acc],0(%[op])\n"
              "addi %[wp],%[wp],8\n addi %[op],%[op],1\n bne %[wp],%[wend],1b\n"
              
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1),
                [x0]"=&r"(x0), [x1]"=&r"(x1)
              : [xp]"r"(xp_), [wend]"r"(wend)
              : "memory");
#endif
#if CI == 16 && XPULP_CTRL == 1
        unsigned int x0, x1, x2, x3;
        int cnt = CO;
        asm volatile (
              XPULP_ASM_BEGIN
              "lw %[x0],0(%[xp])\n"
              "lw %[x1],4(%[xp])\n"
              "lw %[x2],8(%[xp])\n"
              "lw %[x3],12(%[xp])\n"
              HWLOOP0("%[cnt]", "19")   /* 18 instructions in the body */
              LW_INC("%[w0]", "%[wp]", "4")
              LW_INC("%[w1]", "%[wp]", "4")
              LW_INC("%[w2]", "%[wp]", "4")
              LW_INC("%[w3]", "%[wp]", "4")
              DOTSP("%[acc]", "%[x0]", "%[w0]")
              SDOTSP("%[acc]", "%[x1]", "%[w1]")
              SDOTSP("%[acc]", "%[x2]", "%[w2]")
              SDOTSP("%[acc]", "%[x3]", "%[w3]")
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              SB_INC("%[acc]", "%[op]", "1")
              
              XPULP_ASM_END
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1), [w2]"=&r"(w2), [w3]"=&r"(w3),
                [x0]"=&r"(x0), [x1]"=&r"(x1), [x2]"=&r"(x2), [x3]"=&r"(x3)
              : [xp]"r"(xp_), [cnt]"r"(cnt)
              : "memory");
#endif
#if CI == 16 && XPULP_CTRL == 0
        unsigned int x0, x1, x2, x3;
        const signed char *wend = wp + CO * CI;
        asm volatile (
              
              "lw %[x0],0(%[xp])\n"
              "lw %[x1],4(%[xp])\n"
              "lw %[x2],8(%[xp])\n"
              "lw %[x3],12(%[xp])\n"
              "1:\n"
              "lw %[w0],0(%[wp])\n"
              "lw %[w1],4(%[wp])\n"
              "lw %[w2],8(%[wp])\n"
              "lw %[w3],12(%[wp])\n"
              DOTSP("%[acc]", "%[x0]", "%[w0]")
              SDOTSP("%[acc]", "%[x1]", "%[w1]")
              SDOTSP("%[acc]", "%[x2]", "%[w2]")
              SDOTSP("%[acc]", "%[x3]", "%[w3]")
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              "sb %[acc],0(%[op])\n"
              "addi %[wp],%[wp],16\n addi %[op],%[op],1\n bne %[wp],%[wend],1b\n"
              
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1), [w2]"=&r"(w2), [w3]"=&r"(w3),
                [x0]"=&r"(x0), [x1]"=&r"(x1), [x2]"=&r"(x2), [x3]"=&r"(x3)
              : [xp]"r"(xp_), [wend]"r"(wend)
              : "memory");
#endif
#if !((CI == 8 || CI == 16))
#error "pwconv_simd_asm: CI must be 8 or 16"
#endif
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); pwconv_simd_asm(); CYC_STOP(); return checksum(); }
