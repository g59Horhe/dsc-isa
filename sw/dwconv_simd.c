/* int8 depthwise 3x3 convolution -- cv.dotsp.b (Xpulp SIMD dot product).
 *
 * Requires COREV_PULP=1.
 *
 * One cv.dotsp.b does four signed 8-bit products and sums them. A 3x3
 * depthwise window is three rows of three taps, so each row becomes one
 * dot product with the fourth lane zeroed in the weight word:
 *
 *     weights packed once per channel:  {w0, w1, w2, 0}
 *     activations loaded as a word:     {a0, a1, a2, a3}
 *
 * The fourth activation byte is whatever follows in memory; it multiplies
 * by zero and contributes nothing. That is what lets a plain word load
 * serve a 3-tap window.
 *
 * The catch: consecutive output pixels slide the window by one byte, so
 * two out of every three loads are unaligned. CV32E40P supports those but
 * splits them into two bus accesses, roughly doubling load cost. Whether
 * the 3-MACs-per-instruction win survives that penalty is the measurement.
 */

#include "bench.h"

#define CH   8
#define H    16
#define W    16
#define K    3
#define OH   (H - K + 1)
#define OW   (W - K + 1)
#define SHIFT 7

static signed char input[CH][H][W];
static signed char weight[CH][K][K];
static signed char output[CH][OH][OW];

static inline int cv_dotsp_b(unsigned int a, unsigned int b) {
    int r;
    asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2"
                  : "=r"(r) : "r"(a), "r"(b));
    return r;
}

static unsigned int rng_state;
static int rnd(void) {
    rng_state = rng_state * 1103515245u + 12345u;
    return (int)((rng_state >> 16) & 0xFF) - 128;
}

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

static signed char requant(int acc) {
    acc >>= SHIFT;
    if (acc >  127) acc =  127;
    if (acc < -128) acc = -128;
    return (signed char)acc;
}

/* Pack three signed bytes plus a zero lane into a word. */
static inline unsigned int pack3(int a, int b, int c) {
    return ((unsigned)(a & 0xFF))
         | ((unsigned)(b & 0xFF) << 8)
         | ((unsigned)(c & 0xFF) << 16);
}

static void dwconv_simd(void) {
    for (int ch = 0; ch < CH; ch++) {
        const signed char *wp = &weight[ch][0][0];

        /* Three packed weight words, built once per channel. */
        const unsigned int wr0 = pack3(wp[0], wp[1], wp[2]);
        const unsigned int wr1 = pack3(wp[3], wp[4], wp[5]);
        const unsigned int wr2 = pack3(wp[6], wp[7], wp[8]);

        signed char *op = &output[ch][0][0];

        for (int oy = 0; oy < OH; oy++) {
            const signed char *r0 = &input[ch][oy + 0][0];
            const signed char *r1 = &input[ch][oy + 1][0];
            const signed char *r2 = &input[ch][oy + 2][0];

            for (int ox = 0; ox < OW; ox++) {
                unsigned int a0 = *(const unsigned int *)(const void *)r0;
                unsigned int a1 = *(const unsigned int *)(const void *)r1;
                unsigned int a2 = *(const unsigned int *)(const void *)r2;

                int acc = cv_dotsp_b(a0, wr0)
                        + cv_dotsp_b(a1, wr1)
                        + cv_dotsp_b(a2, wr2);

                *op++ = requant(acc);
                r0++; r1++; r2++;
            }
        }
    }
}

int main(void) {
    init_data();

    CYC_START();
    dwconv_simd();
    CYC_STOP();

    int sum = 0;
    for (int c = 0; c < CH; c++)
        for (int y = 0; y < OH; y++)
            for (int x = 0; x < OW; x++)
                sum += output[c][y][x];
    return sum & 0xFFFF;
}
