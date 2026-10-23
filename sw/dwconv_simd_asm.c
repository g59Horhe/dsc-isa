/* int8 depthwise 3x3 -- cv.dotsp.b, unaligned loads, hand-written inner loop.
 *
 * Same arithmetic as dwconv_simd.c (one word load per row per pixel, three
 * dot products, fourth weight lane zero). Loads are scheduled ahead of their
 * dot products so there is no load-use stall. Requantisation from requant.h.
 *
 * XPULP_CTRL=0: RV32IMC control, one base pointer, addi + bne per pixel.
 * XPULP_CTRL=1: hardware loop over the row, post-increment load and store.
 */
#include "bench.h"
#include "requant.h"
#include "xpulp.h"
#ifndef XPULP_CTRL
#define XPULP_CTRL 0
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

static signed char input[CH][H][W];
static signed char weight[CH][K][K];
static signed char output[CH][OH][OW];

static unsigned int rng_state;
static int rnd(void) { rng_state = rng_state * 1103515245u + 12345u; return (int)((rng_state >> 16) & 0xFF) - 128; }
static void init_data(void) {
    rng_state = 1;
    for (int c = 0; c < CH; c++) {
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) input[c][y][x] = (signed char)(rnd() >> 2);
        for (int i = 0; i < K; i++) for (int j = 0; j < K; j++) weight[c][i][j] = (signed char)(rnd() >> 3);
    }
}
static inline unsigned int pack3(int a, int b, int c) {
    return ((unsigned)(a & 0xFF)) | ((unsigned)(b & 0xFF) << 8) | ((unsigned)(c & 0xFF) << 16);
}
#define DOTSP(rd, rs1, rs2) ".insn r 0x7b, 0x1, 0x48, " rd ", " rs1 ", " rs2 "\n"
#define MAC3 \
  DOTSP("%[a]", "%[a]", "%[w0]") DOTSP("%[b]", "%[b]", "%[w1]") DOTSP("%[c]", "%[c]", "%[w2]") \
  "add %[a],%[a],%[b]\n add %[a],%[a],%[c]\n" \
  REQUANT_ASM("%[a]", "%[t]", "%[u]")

static void dwconv_simd_asm(void) {
    for (int ch = 0; ch < CH; ch++) {
        const signed char *wp = &weight[ch][0][0];
        const unsigned int w0 = pack3(wp[0], wp[1], wp[2]);
        const unsigned int w1 = pack3(wp[3], wp[4], wp[5]);
        const unsigned int w2 = pack3(wp[6], wp[7], wp[8]);
        signed char *op = &output[ch][0][0];
        for (int oy = 0; oy < OH; oy++) {
            const signed char *p = &input[ch][oy][0];
            unsigned int a, b, c; int t, u;
#if XPULP_CTRL
            int cnt = OW;
            asm volatile (
              XPULP_ASM_BEGIN
              HWLOOP0("%[cnt]", "19")          /* 3 loads + 3 dotsp + 2 add + 9 requant + 1 store = 18, + 1 */
              LW_INC("%[a]", "%[p]", "1")
              "lw %[b]," XS(W-1) "(%[p])\n lw %[c]," XS(2*W-1) "(%[p])\n"
              MAC3
              SB_INC("%[a]", "%[op]", "1")
              XPULP_ASM_END
              : [p]"+r"(p), [op]"+r"(op), [a]"=&r"(a), [b]"=&r"(b), [c]"=&r"(c), [t]"=&r"(t), [u]"=&r"(u)
              : [cnt]"r"(cnt), [w0]"r"(w0), [w1]"r"(w1), [w2]"r"(w2)
              : "memory");
#else
            const signed char *pend = p + OW;
            asm volatile (
              "1:\n"
              "lw %[a],0(%[p])\n lw %[b]," XS(W) "(%[p])\n lw %[c]," XS(2*W) "(%[p])\n"
              MAC3
              "sb %[a],0(%[op])\n addi %[p],%[p],1\n addi %[op],%[op],1\n bne %[p],%[pend],1b\n"
              : [p]"+r"(p), [op]"+r"(op), [a]"=&r"(a), [b]"=&r"(b), [c]"=&r"(c), [t]"=&r"(t), [u]"=&r"(u)
              : [pend]"r"(pend), [w0]"r"(w0), [w1]"r"(w1), [w2]"r"(w2)
              : "memory");
#endif
        }
    }
}

int main(void) {
    BENCH_PAD();
    init_data();
    CYC_START(); dwconv_simd_asm(); CYC_STOP();
    int sum = 0;
    for (int c = 0; c < CH; c++) for (int y = 0; y < OH; y++) for (int x = 0; x < OW; x++) sum += output[c][y][x];
    return sum & 0xFFFF;
}
