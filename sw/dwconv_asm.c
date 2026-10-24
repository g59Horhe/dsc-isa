/* int8 depthwise 3x3 convolution -- hand-written RV32IMC inner loop.
 *
 * Same shape, data and checksum as dwconv_opt.c. Sliding window: three new
 * byte loads per output pixel, the three columns rotated by register
 * renaming across a 3-pixel unroll (no mv), one base pointer with
 * compile-time row offsets, loop control once per three pixels.
 * Requantisation comes from requant.h and is identical to the C kernels.
 * The OW mod 3 tail is handled in C.
 *
 * XPULP_CTRL=1 replaces the loop control and addressing with Xpulp features:
 * one hardware loop for the pixel loop (no counter, no branch) and
 * post-increment byte loads and stores (no pointer arithmetic). Arithmetic
 * is unchanged, so the difference isolates control and addressing.
 */
#include "bench.h"
#include "requant.h"
#include "xpulp.h"

#ifndef XPULP_CTRL
#define XPULP_CTRL 0   /* 1: hardware loop + post-increment loads/stores (COREV_PULP=1) */
#endif

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

#define XS(x) S_(x)
#define S_(x) #x
#define W1   XS(W)
#define W1p1 XS(W+1)
#define W1p2 XS(W+2)
#define W1p3 XS(W+3)
#define W1p4 XS(W+4)
#define W2   XS(2*W)
#define W2p1 XS(2*W+1)
#define W2p2 XS(2*W+2)
#define W2p3 XS(2*W+3)
#define W2p4 XS(2*W+4)

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

/* One output pixel from three column registers per row. acc result, t/u scratch. */
#define PIX(A0,A1,A2,B0,B1,B2,C0,C1,C2,OFF) \
  "mul %[acc]," A0 ",%[w0]\n mul %[t]," A1 ",%[w1]\n add %[acc],%[acc],%[t]\n" \
  "mul %[t]," A2 ",%[w2]\n add %[acc],%[acc],%[t]\n" \
  "mul %[t]," B0 ",%[w3]\n add %[acc],%[acc],%[t]\n mul %[t]," B1 ",%[w4]\n add %[acc],%[acc],%[t]\n" \
  "mul %[t]," B2 ",%[w5]\n add %[acc],%[acc],%[t]\n" \
  "mul %[t]," C0 ",%[w6]\n add %[acc],%[acc],%[t]\n mul %[t]," C1 ",%[w7]\n add %[acc],%[acc],%[t]\n" \
  "mul %[t]," C2 ",%[w8]\n add %[acc],%[acc],%[t]\n" \
  REQUANT_ASM("%[acc]", "%[t]", "%[u]") \
  STORE(OFF)

#if XPULP_CTRL
#define STORE(OFF) SB_INC("%[acc]", "%[op]", "1")
#define LOAD3(A, B, C, OFF) LBA_INC(A, "%[r0]", "1") LBA_INC(B, "%[r1]", "1") LBA_INC(C, "%[r2]", "1")
#else
#define STORE(OFF) "sb %[acc]," OFF "(%[op])\n"
#define LOAD3(A, B, C, OFF) LBA " " A "," XS(OFF) "(%[p])\n " LBA " " B "," XS(W+OFF) "(%[p])\n " LBA " " C "," XS(2*W+OFF) "(%[p])\n"
#endif

static void dwconv_asm(void) {
    for (int c = 0; c < CH; c++) {
        const signed char *wp = &weight[c][0][0];
        int w0 = wp[0], w1 = wp[1], w2 = wp[2], w3 = wp[3], w4 = wp[4],
            w5 = wp[5], w6 = wp[6], w7 = wp[7], w8 = wp[8];
        out_t *op = &output[c][0][0];
        for (int oy = 0; oy < OH; oy++) {
            const act_t *p = &input[c][oy][0];
            const act_t *pend = p + (OW / 3) * 3;
            int a0, a1, a2, b0, b1, b2, c0, c1, c2, acc, t, u;
#if XPULP_CTRL
            const act_t *r0 = p + 2, *r1 = p + W + 2, *r2 = p + 2 * W + 2;
            int cnt = OW / 3;
            asm volatile (
              XPULP_ASM_BEGIN
              LBA " %[a0],-2(%[r0])\n " LBA " %[a1],-1(%[r0])\n " LBA " %[b0],-2(%[r1])\n " LBA " %[b1],-1(%[r1])\n"
              LBA " %[c0],-2(%[r2])\n " LBA " %[c1],-1(%[r2])\n"
              HWLOOP0("%[cnt]", RQ_XS(3*(21+RQ_N)+1))   /* 3 pixels x (3 loads + 18 + requant) + 1 */
              LOAD3("%[a2]","%[b2]","%[c2]",2)
              PIX("%[a0]","%[a1]","%[a2]","%[b0]","%[b1]","%[b2]","%[c0]","%[c1]","%[c2]","0")
              LOAD3("%[a0]","%[b0]","%[c0]",3)
              PIX("%[a1]","%[a2]","%[a0]","%[b1]","%[b2]","%[b0]","%[c1]","%[c2]","%[c0]","1")
              LOAD3("%[a1]","%[b1]","%[c1]",4)
              PIX("%[a2]","%[a0]","%[a1]","%[b2]","%[b0]","%[b1]","%[c2]","%[c0]","%[c1]","2")
              XPULP_ASM_END
              : [r0]"+r"(r0), [r1]"+r"(r1), [r2]"+r"(r2), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u),
                [a0]"=&r"(a0), [a1]"=&r"(a1), [a2]"=&r"(a2), [b0]"=&r"(b0), [b1]"=&r"(b1),
                [b2]"=&r"(b2), [c0]"=&r"(c0), [c1]"=&r"(c1), [c2]"=&r"(c2)
              : [cnt]"r"(cnt), [w0]"r"(w0), [w1]"r"(w1), [w2]"r"(w2), [w3]"r"(w3),
                [w4]"r"(w4), [w5]"r"(w5), [w6]"r"(w6), [w7]"r"(w7), [w8]"r"(w8)
              : "memory");
            (void)pend; (void)p;
#else
            asm volatile (
              LBA " %[a0],0(%[p])\n " LBA " %[a1],1(%[p])\n " LBA " %[b0]," W1 "(%[p])\n " LBA " %[b1]," W1p1 "(%[p])\n"
              LBA " %[c0]," W2 "(%[p])\n " LBA " %[c1]," W2p1 "(%[p])\n"
              "1:\n"
              LOAD3("%[a2]","%[b2]","%[c2]",2)
              PIX("%[a0]","%[a1]","%[a2]","%[b0]","%[b1]","%[b2]","%[c0]","%[c1]","%[c2]","0")
              LOAD3("%[a0]","%[b0]","%[c0]",3)
              PIX("%[a1]","%[a2]","%[a0]","%[b1]","%[b2]","%[b0]","%[c1]","%[c2]","%[c0]","1")
              LOAD3("%[a1]","%[b1]","%[c1]",4)
              PIX("%[a2]","%[a0]","%[a1]","%[b2]","%[b0]","%[b1]","%[c2]","%[c0]","%[c1]","2")
              "addi %[p],%[p],3\n addi %[op],%[op],3\n bne %[p],%[pend],1b\n"
              : [p]"+r"(p), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u),
                [a0]"=&r"(a0), [a1]"=&r"(a1), [a2]"=&r"(a2), [b0]"=&r"(b0), [b1]"=&r"(b1),
                [b2]"=&r"(b2), [c0]"=&r"(c0), [c1]"=&r"(c1), [c2]"=&r"(c2)
              : [pend]"r"(pend), [w0]"r"(w0), [w1]"r"(w1), [w2]"r"(w2), [w3]"r"(w3),
                [w4]"r"(w4), [w5]"r"(w5), [w6]"r"(w6), [w7]"r"(w7), [w8]"r"(w8)
              : "memory");
#endif
            for (int ox = (OW / 3) * 3; ox < OW; ox++) {
                const act_t *r0 = &input[c][oy][ox], *r1 = r0 + W, *r2 = r0 + 2 * W;
                int s = r0[0]*w0 + r0[1]*w1 + r0[2]*w2 + r1[0]*w3 + r1[1]*w4 + r1[2]*w5
                      + r2[0]*w6 + r2[1]*w7 + r2[2]*w8;
                *op++ = requant(s);
            }
        }
    }
}

int main(void) {
    BENCH_PAD();
    init_data();
    CYC_START();
    dwconv_asm();
    CYC_STOP();
    int sum = 0;
    for (int c = 0; c < CH; c++)
        for (int y = 0; y < OH; y++)
            for (int x = 0; x < OW; x++)
                sum += output[c][y][x];
    return sum & 0xFFFF;
}
