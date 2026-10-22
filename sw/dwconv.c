/* int8 depthwise 3x3 convolution -- plain C baseline.
 *
 * This is the denominator for the whole study: no custom instructions, no
 * SIMD, nothing the compiler cannot do with RV32IMC. Every later variant is
 * measured against it.
 *
 * Shape follows a MobileNet-style depthwise layer: one 3x3 kernel per input
 * channel, no cross-channel accumulation. That is what makes the arithmetic
 * intensity so low and the operand supply interesting -- each weight is
 * reused across the whole spatial map, and each activation is read by up to
 * nine output pixels.
 *
 * Quantisation is the usual TinyML form: int8 operands, int32 accumulator,
 * arithmetic right shift back to int8 with saturation.
 */

#include "bench.h"

#define CH   8        /* channels              */
#define H    16       /* input height          */
#define W    16       /* input width           */
#define K    3        /* kernel size           */
#define OH   (H - K + 1)
#define OW   (W - K + 1)
#define SHIFT 7       /* requantisation shift  */

static signed char input[CH][H][W];
static signed char weight[CH][K][K];
static signed char output[CH][OH][OW];

/* Deterministic pseudo-random fill. Same data on every run and on every
   variant, so checksums are directly comparable. */
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

/* The kernel under measurement. */
static void dwconv(void) {
    for (int c = 0; c < CH; c++) {
        for (int oy = 0; oy < OH; oy++) {
            for (int ox = 0; ox < OW; ox++) {
                int acc = 0;
                for (int ky = 0; ky < K; ky++)
                    for (int kx = 0; kx < K; kx++)
                        acc += (int)input[c][oy + ky][ox + kx]
                             * (int)weight[c][ky][kx];
                output[c][oy][ox] = requant(acc);
            }
        }
    }
}

int main(void) {
    init_data();

    CYC_START();
    dwconv();
    CYC_STOP();

    /* Checksum: every variant must produce the same value, or the
       comparison is meaningless. */
    int sum = 0;
    for (int c = 0; c < CH; c++)
        for (int y = 0; y < OH; y++)
            for (int x = 0; x < OW; x++)
                sum += output[c][y][x];
    return sum & 0xFFFF;
}
