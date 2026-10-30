/* Depthwise 5x5 -- output-stationary hand-written scalar baseline.
 *
 * Answers the weak-baseline objection to dwconv5_asm.c, whose row-wise
 * sliding kernel keeps the accumulator row in memory (one lw/add/sw per
 * pixel per kernel row, five taken branches per output). Here the
 * accumulator lives in a register for the whole output pixel; for each of
 * the five kernel rows the five weights are reloaded (five lb, so the 25
 * weights never need to be resident) and the five input bytes loaded, then
 * five multiplies and adds. Per output: 50 byte loads, 25 mul, 24 add (the
 * first product initialises the accumulator), requantisation, one store,
 * one taken branch; no accumulator traffic and no load-use stall, because
 * every load is five instructions ahead of its consumer.
 *
 * Same data, layout, checksum and requantisation (requant.h) as the other
 * 5x5 kernels. XPULP_CTRL=0: RV32IMC control (addi + bne per output).
 * XPULP_CTRL=1: one hardware loop per output row and a post-increment
 * store; the loads keep their immediate offsets off one row pointer, which
 * is advanced by a plain addi inside the loop body. -DREQUANT_CLIP=1 swaps
 * the saturation for cv.clip as in every other kernel.
 */
#include "dw_common.h"
#include "xpulp.h"
#ifndef XPULP_CTRL
#define XPULP_CTRL 0
#endif
#if K != 5
#error "written for K == 5"
#endif
#define XS(x) S_(x)
#define S_(x) #x
#define LOADS(ky) \
  "lb %[w0]," XS(ky*5+0) "(%[wp])\n lb %[w1]," XS(ky*5+1) "(%[wp])\n lb %[w2]," XS(ky*5+2) "(%[wp])\n lb %[w3]," XS(ky*5+3) "(%[wp])\n lb %[w4]," XS(ky*5+4) "(%[wp])\n" \
  "lb %[x0]," XS(ky*W+0) "(%[p])\n lb %[x1]," XS(ky*W+1) "(%[p])\n lb %[x2]," XS(ky*W+2) "(%[p])\n lb %[x3]," XS(ky*W+3) "(%[p])\n lb %[x4]," XS(ky*W+4) "(%[p])\n"
#define MACS \
  "mul %[t],%[x1],%[w1]\n add %[acc],%[acc],%[t]\n mul %[t],%[x2],%[w2]\n add %[acc],%[acc],%[t]\n" \
  "mul %[t],%[x3],%[w3]\n add %[acc],%[acc],%[t]\n mul %[t],%[x4],%[w4]\n add %[acc],%[acc],%[t]\n"
#define ROW(ky) LOADS(ky) "mul %[t],%[x0],%[w0]\n add %[acc],%[acc],%[t]\n" MACS
/* 19 + 4 x 20 = 99 arithmetic and load instructions per output, then RQ_N for requantisation */
#define BODY LOADS(0) "mul %[acc],%[x0],%[w0]\n" MACS ROW(1) ROW(2) ROW(3) ROW(4) REQUANT_ASM("%[acc]", "%[t]", "%[u]")
#define OUTS [p]"+r"(p), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), \
             [w0]"=&r"(w0), [w1]"=&r"(w1), [w2]"=&r"(w2), [w3]"=&r"(w3), [w4]"=&r"(w4), \
             [x0]"=&r"(x0), [x1]"=&r"(x1), [x2]"=&r"(x2), [x3]"=&r"(x3), [x4]"=&r"(x4)

static void dwconv5_os(void) {
    for (int c = 0; c < CH; c++) {
        const signed char *wp = &weight[c][0][0];
        signed char *op = &output[c][0][0];
        for (int oy = 0; oy < OH; oy++) {
            const signed char *p = &input[c][oy][0];
            int acc, t, u, w0, w1, w2, w3, w4, x0, x1, x2, x3, x4;
#if XPULP_CTRL == 1
            int cnt = OW;
            asm volatile (
              RQ_INIT("%[u]")
              XPULP_ASM_BEGIN
              HWLOOP0("%[cnt]", RQ_XS(101+RQ_N+1))   /* body: 101 + RQ_N instructions */
              BODY
              SB_INC("%[acc]", "%[op]", "1")
              "addi %[p],%[p],1\n"
              XPULP_ASM_END
              : OUTS
              : [cnt]"r"(cnt), [wp]"r"(wp)
              : "memory");
#else
            const signed char *pend = p + OW;
            asm volatile (
              RQ_INIT("%[u]")
              "1:\n"
              BODY
              "sb %[acc],0(%[op])\n"
              "addi %[op],%[op],1\n"
              "addi %[p],%[p],1\n"
              "bne %[p],%[pend],1b\n"
              : OUTS
              : [wp]"r"(wp), [pend]"r"(pend)
              : "memory");
#endif
        }
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); dwconv5_os(); CYC_STOP(); return checksum(); }
