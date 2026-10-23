/* Depthwise KxK (default 5x5) -- plain C scalar baseline in the dwconv_opt.c
 * style: weights hoisted into a local array once per channel, row pointers
 * advanced per pixel, tap loops left to the compiler. */
#include "dw_common.h"
static void dwconv_k(void) {
    for (int c = 0; c < CH; c++) {
        int w[K * K];
        for (int i = 0; i < K * K; i++) w[i] = (&weight[c][0][0])[i];
        signed char *op = &output[c][0][0];
        for (int oy = 0; oy < OH; oy++) {
            const signed char *r = &input[c][oy][0];
            for (int ox = 0; ox < OW; ox++) {
                int acc = 0;
                for (int ky = 0; ky < K; ky++)
                    for (int kx = 0; kx < K; kx++) acc += r[ky * W + ox + kx] * w[ky * K + kx];
                *op++ = requant(acc);
            }
        }
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); dwconv_k(); CYC_STOP(); return checksum(); }
