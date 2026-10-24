/* Pointwise 1x1 convolution -- hand-written scalar inner loop.
 *
 * The CI activations of one pixel are held in registers across all CO output
 * channels (register blocking); each output costs CI weight loads, CI
 * multiplies, CI-1 adds, the shared requantisation and one store. Weight
 * loads are issued one ahead of their multiply.
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

static void pwconv_asm(void) {
    for (int p = 0; p < P; p++) {
        const act_t *xp_ = input[p];
        const signed char *wp = &weight[0][0];
        out_t *op = &output[p][0];
        int acc, t, u, w0, w1;
#if CI == 8 && XPULP_CTRL == 1
        int a0, a1, a2, a3, a4, a5, a6, a7;
        int cnt = CO;
        asm volatile (
              XPULP_ASM_BEGIN
              LBA " %[a0],0(%[xp])\n"
              LBA " %[a1],1(%[xp])\n"
              LBA " %[a2],2(%[xp])\n"
              LBA " %[a3],3(%[xp])\n"
              LBA " %[a4],4(%[xp])\n"
              LBA " %[a5],5(%[xp])\n"
              LBA " %[a6],6(%[xp])\n"
              LBA " %[a7],7(%[xp])\n"
              HWLOOP0("%[cnt]", RQ_XS(24+RQ_N+1))   /* body: 24+RQ_N instructions */
              LB_INC("%[w0]", "%[wp]", "1")
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[acc],%[a0],%[w0]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a1],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a2],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a3],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a4],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a5],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a6],%[w0]\n add %[acc],%[acc],%[t]\n"
              "mul %[t],%[a7],%[w1]\n add %[acc],%[acc],%[t]\n"
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              SB_INC("%[acc]", "%[op]", "1")
              
              XPULP_ASM_END
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1),
                [a0]"=&r"(a0), [a1]"=&r"(a1), [a2]"=&r"(a2), [a3]"=&r"(a3), [a4]"=&r"(a4), [a5]"=&r"(a5), [a6]"=&r"(a6), [a7]"=&r"(a7)
              : [xp]"r"(xp_), [cnt]"r"(cnt)
              : "memory");
#endif
#if CI == 8 && XPULP_CTRL == 0
        int a0, a1, a2, a3, a4, a5, a6, a7;
        const signed char *wend = wp + CO * CI;
        asm volatile (
              
              LBA " %[a0],0(%[xp])\n"
              LBA " %[a1],1(%[xp])\n"
              LBA " %[a2],2(%[xp])\n"
              LBA " %[a3],3(%[xp])\n"
              LBA " %[a4],4(%[xp])\n"
              LBA " %[a5],5(%[xp])\n"
              LBA " %[a6],6(%[xp])\n"
              LBA " %[a7],7(%[xp])\n"
              "1:\n"
              "lb %[w0],0(%[wp])\n"
              "lb %[w1],1(%[wp])\n"
              "mul %[acc],%[a0],%[w0]\n"
              "lb %[w0],2(%[wp])\n"
              "mul %[t],%[a1],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],3(%[wp])\n"
              "mul %[t],%[a2],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],4(%[wp])\n"
              "mul %[t],%[a3],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],5(%[wp])\n"
              "mul %[t],%[a4],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],6(%[wp])\n"
              "mul %[t],%[a5],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],7(%[wp])\n"
              "mul %[t],%[a6],%[w0]\n add %[acc],%[acc],%[t]\n"
              "mul %[t],%[a7],%[w1]\n add %[acc],%[acc],%[t]\n"
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              "sb %[acc],0(%[op])\n"
              "addi %[wp],%[wp],8\n addi %[op],%[op],1\n bne %[wp],%[wend],1b\n"
              
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1),
                [a0]"=&r"(a0), [a1]"=&r"(a1), [a2]"=&r"(a2), [a3]"=&r"(a3), [a4]"=&r"(a4), [a5]"=&r"(a5), [a6]"=&r"(a6), [a7]"=&r"(a7)
              : [xp]"r"(xp_), [wend]"r"(wend)
              : "memory");
#endif
#if CI == 16 && XPULP_CTRL == 1
        int a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15;
        int cnt = CO;
        asm volatile (
              XPULP_ASM_BEGIN
              LBA " %[a0],0(%[xp])\n"
              LBA " %[a1],1(%[xp])\n"
              LBA " %[a2],2(%[xp])\n"
              LBA " %[a3],3(%[xp])\n"
              LBA " %[a4],4(%[xp])\n"
              LBA " %[a5],5(%[xp])\n"
              LBA " %[a6],6(%[xp])\n"
              LBA " %[a7],7(%[xp])\n"
              LBA " %[a8],8(%[xp])\n"
              LBA " %[a9],9(%[xp])\n"
              LBA " %[a10],10(%[xp])\n"
              LBA " %[a11],11(%[xp])\n"
              LBA " %[a12],12(%[xp])\n"
              LBA " %[a13],13(%[xp])\n"
              LBA " %[a14],14(%[xp])\n"
              LBA " %[a15],15(%[xp])\n"
              HWLOOP0("%[cnt]", RQ_XS(48+RQ_N+1))   /* body: 48+RQ_N instructions */
              LB_INC("%[w0]", "%[wp]", "1")
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[acc],%[a0],%[w0]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a1],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a2],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a3],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a4],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a5],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a6],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a7],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a8],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a9],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a10],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a11],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a12],%[w0]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w0]", "%[wp]", "1")
              "mul %[t],%[a13],%[w1]\n add %[acc],%[acc],%[t]\n"
              LB_INC("%[w1]", "%[wp]", "1")
              "mul %[t],%[a14],%[w0]\n add %[acc],%[acc],%[t]\n"
              "mul %[t],%[a15],%[w1]\n add %[acc],%[acc],%[t]\n"
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              SB_INC("%[acc]", "%[op]", "1")
              
              XPULP_ASM_END
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1),
                [a0]"=&r"(a0), [a1]"=&r"(a1), [a2]"=&r"(a2), [a3]"=&r"(a3), [a4]"=&r"(a4), [a5]"=&r"(a5), [a6]"=&r"(a6), [a7]"=&r"(a7), [a8]"=&r"(a8), [a9]"=&r"(a9), [a10]"=&r"(a10), [a11]"=&r"(a11), [a12]"=&r"(a12), [a13]"=&r"(a13), [a14]"=&r"(a14), [a15]"=&r"(a15)
              : [xp]"r"(xp_), [cnt]"r"(cnt)
              : "memory");
#endif
#if CI == 16 && XPULP_CTRL == 0
        int a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15;
        const signed char *wend = wp + CO * CI;
        asm volatile (
              
              LBA " %[a0],0(%[xp])\n"
              LBA " %[a1],1(%[xp])\n"
              LBA " %[a2],2(%[xp])\n"
              LBA " %[a3],3(%[xp])\n"
              LBA " %[a4],4(%[xp])\n"
              LBA " %[a5],5(%[xp])\n"
              LBA " %[a6],6(%[xp])\n"
              LBA " %[a7],7(%[xp])\n"
              LBA " %[a8],8(%[xp])\n"
              LBA " %[a9],9(%[xp])\n"
              LBA " %[a10],10(%[xp])\n"
              LBA " %[a11],11(%[xp])\n"
              LBA " %[a12],12(%[xp])\n"
              LBA " %[a13],13(%[xp])\n"
              LBA " %[a14],14(%[xp])\n"
              LBA " %[a15],15(%[xp])\n"
              "1:\n"
              "lb %[w0],0(%[wp])\n"
              "lb %[w1],1(%[wp])\n"
              "mul %[acc],%[a0],%[w0]\n"
              "lb %[w0],2(%[wp])\n"
              "mul %[t],%[a1],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],3(%[wp])\n"
              "mul %[t],%[a2],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],4(%[wp])\n"
              "mul %[t],%[a3],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],5(%[wp])\n"
              "mul %[t],%[a4],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],6(%[wp])\n"
              "mul %[t],%[a5],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],7(%[wp])\n"
              "mul %[t],%[a6],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],8(%[wp])\n"
              "mul %[t],%[a7],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],9(%[wp])\n"
              "mul %[t],%[a8],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],10(%[wp])\n"
              "mul %[t],%[a9],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],11(%[wp])\n"
              "mul %[t],%[a10],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],12(%[wp])\n"
              "mul %[t],%[a11],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],13(%[wp])\n"
              "mul %[t],%[a12],%[w0]\n add %[acc],%[acc],%[t]\n"
              "lb %[w0],14(%[wp])\n"
              "mul %[t],%[a13],%[w1]\n add %[acc],%[acc],%[t]\n"
              "lb %[w1],15(%[wp])\n"
              "mul %[t],%[a14],%[w0]\n add %[acc],%[acc],%[t]\n"
              "mul %[t],%[a15],%[w1]\n add %[acc],%[acc],%[t]\n"
              REQUANT_ASM("%[acc]", "%[t]", "%[u]")
              "sb %[acc],0(%[op])\n"
              "addi %[wp],%[wp],16\n addi %[op],%[op],1\n bne %[wp],%[wend],1b\n"
              
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), [w0]"=&r"(w0), [w1]"=&r"(w1),
                [a0]"=&r"(a0), [a1]"=&r"(a1), [a2]"=&r"(a2), [a3]"=&r"(a3), [a4]"=&r"(a4), [a5]"=&r"(a5), [a6]"=&r"(a6), [a7]"=&r"(a7), [a8]"=&r"(a8), [a9]"=&r"(a9), [a10]"=&r"(a10), [a11]"=&r"(a11), [a12]"=&r"(a12), [a13]"=&r"(a13), [a14]"=&r"(a14), [a15]"=&r"(a15)
              : [xp]"r"(xp_), [wend]"r"(wend)
              : "memory");
#endif
#if !((CI == 8 || CI == 16))
#error "pwconv_asm: CI must be 8 or 16"
#endif
    }
}
#ifndef NO_MAIN
int main(void) { BENCH_PAD(); init_data(); CYC_START(); pwconv_asm(); CYC_STOP(); return checksum(); }
#endif
