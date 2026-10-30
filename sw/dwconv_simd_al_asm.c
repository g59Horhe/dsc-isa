/* int8 depthwise 3x3 -- cv.dotsp.b, aligned loads only, hand-written.
 *
 * Same arithmetic as dwconv_simd_al.c: two aligned word loads per row per
 * four output pixels, windows extracted by shift-and-merge, fourth weight
 * lane zero. Requantisation from requant.h. The OW mod 4 tail uses the
 * unaligned C path.
 *
 * XPULP_CTRL=0: RV32IMC control, addi + bne per four pixels.
 * XPULP_CTRL=1: hardware loop over the row, post-increment load and stores.
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

static act_t input[CH][H][W] __attribute__((aligned(4)));
static signed char weight[CH][K][K];
static out_t output[CH][OH][OW];

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
static inline unsigned int pack3(int a, int b, int c) {
    return ((unsigned)(a & 0xFF)) | ((unsigned)(b & 0xFF) << 8) | ((unsigned)(c & 0xFF) << 16);
}
static inline int cv_dotsp_b(unsigned int a, unsigned int b) {
    int r; asm volatile (".insn r 0x7b, 0x1, " DOT_FUNCT7 ", %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r;
}
/* dot products of the three window words in x,y,z, sum into x, requantise */
#define MAC3 \
  DOTSP("%[x]", "%[x]", "%[w0]") DOTSP("%[y]", "%[y]", "%[w1]") DOTSP("%[z]", "%[z]", "%[w2]") \
  "add %[x],%[x],%[y]\n add %[x],%[x],%[z]\n" \
  REQUANT_ASM("%[x]", "%[t]", "%[u]")
/* window words for pixel k from (lo, hi) of each row */
#define WIN1 "srli %[x],%[l0],8\n srli %[y],%[l1],8\n srli %[z],%[l2],8\n"
#define WIN2 "srli %[x],%[l0],16\n slli %[t],%[h0],16\n or %[x],%[x],%[t]\n" \
             "srli %[y],%[l1],16\n slli %[t],%[h1],16\n or %[y],%[y],%[t]\n" \
             "srli %[z],%[l2],16\n slli %[t],%[h2],16\n or %[z],%[z],%[t]\n"
#define WIN3 "srli %[x],%[l0],24\n slli %[t],%[h0],8\n or %[x],%[x],%[t]\n" \
             "srli %[y],%[l1],24\n slli %[t],%[h1],8\n or %[y],%[y],%[t]\n" \
             "srli %[z],%[l2],24\n slli %[t],%[h2],8\n or %[z],%[z],%[t]\n"
#define WIN0 "mv %[x],%[l0]\n mv %[y],%[l1]\n mv %[z],%[l2]\n"

static void dwconv_simd_al_asm(void) {
    for (int ch = 0; ch < CH; ch++) {
        const signed char *wp = &weight[ch][0][0];
        const unsigned int w0 = pack3(wp[0], wp[1], wp[2]);
        const unsigned int w1 = pack3(wp[3], wp[4], wp[5]);
        const unsigned int w2 = pack3(wp[6], wp[7], wp[8]);
        out_t *op = &output[ch][0][0];
        for (int oy = 0; oy < OH; oy++) {
            const act_t *p = &input[ch][oy][0];
            unsigned int l0, h0, l1, h1, l2, h2, x, y, z; int t, u;
#if XPULP_CTRL
            int cnt = OW / 4;
            asm volatile (
              RQ_INIT("%[u]")
              XPULP_ASM_BEGIN
              HWLOOP0("%[cnt]", RQ_XS(55+4*RQ_N))   /* 6 loads + 24 window ops + 4 x (5 + requant + 1), + 1 */
              LW_INC("%[l0]", "%[p]", "4")
              "lw %[h0],0(%[p])\n lw %[l1]," XS(W-4) "(%[p])\n lw %[h1]," XS(W) "(%[p])\n"
              "lw %[l2]," XS(2*W-4) "(%[p])\n lw %[h2]," XS(2*W) "(%[p])\n"
              WIN0 MAC3 SB_INC("%[x]", "%[op]", "1")
              WIN1 MAC3 SB_INC("%[x]", "%[op]", "1")
              WIN2 MAC3 SB_INC("%[x]", "%[op]", "1")
              WIN3 MAC3 SB_INC("%[x]", "%[op]", "1")
              XPULP_ASM_END
              : [p]"+r"(p), [op]"+r"(op), [l0]"=&r"(l0), [h0]"=&r"(h0), [l1]"=&r"(l1), [h1]"=&r"(h1),
                [l2]"=&r"(l2), [h2]"=&r"(h2), [x]"=&r"(x), [y]"=&r"(y), [z]"=&r"(z), [t]"=&r"(t), [u]"=&r"(u)
              : [cnt]"r"(cnt), [w0]"r"(w0), [w1]"r"(w1), [w2]"r"(w2)
              : "memory");
#else
            const act_t *pend = p + (OW / 4) * 4;
            asm volatile (
              RQ_INIT("%[u]")
              "1:\n"
              "lw %[l0],0(%[p])\n lw %[h0],4(%[p])\n lw %[l1]," XS(W) "(%[p])\n lw %[h1]," XS(W+4) "(%[p])\n"
              "lw %[l2]," XS(2*W) "(%[p])\n lw %[h2]," XS(2*W+4) "(%[p])\n"
              WIN0 MAC3 "sb %[x],0(%[op])\n"
              WIN1 MAC3 "sb %[x],1(%[op])\n"
              WIN2 MAC3 "sb %[x],2(%[op])\n"
              WIN3 MAC3 "sb %[x],3(%[op])\n"
              "addi %[p],%[p],4\n addi %[op],%[op],4\n bne %[p],%[pend],1b\n"
              : [p]"+r"(p), [op]"+r"(op), [l0]"=&r"(l0), [h0]"=&r"(h0), [l1]"=&r"(l1), [h1]"=&r"(h1),
                [l2]"=&r"(l2), [h2]"=&r"(h2), [x]"=&r"(x), [y]"=&r"(y), [z]"=&r"(z), [t]"=&r"(t), [u]"=&r"(u)
              : [pend]"r"(pend), [w0]"r"(w0), [w1]"r"(w1), [w2]"r"(w2)
              : "memory");
#endif
            /* tail: unaligned path, identical in both variants */
            for (int ox = (OW / 4) * 4; ox < OW; ox++) {
                const act_t *r0 = &input[ch][oy][ox];
                int acc = cv_dotsp_b(*(const unsigned int *)(const void *)r0, w0)
                        + cv_dotsp_b(*(const unsigned int *)(const void *)(r0 + W), w1)
                        + cv_dotsp_b(*(const unsigned int *)(const void *)(r0 + 2 * W), w2);
                *op++ = requant(acc);
            }
        }
    }
}

int main(void) {
    BENCH_PAD();
    init_data();
    CYC_START(); dwconv_simd_al_asm(); CYC_STOP();
    int sum = 0;
    for (int c = 0; c < CH; c++) for (int y = 0; y < OH; y++) for (int x = 0; x < OW; x++) sum += output[c][y][x];
    return sum & 0xFFFF;
}
