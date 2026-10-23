/* Pointwise 1x1 convolution -- cv.dotsp.b from C, GCC-scheduled.
 * Four input channels per word, all four lanes used, all loads aligned. */
#include "pw_common.h"
static inline int cv_dotsp_b(unsigned int a, unsigned int b) {
    int r; asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r;
}
static void pwconv_simd(void) {
    for (int p = 0; p < P; p++) {
        const unsigned int *x = (const unsigned int *)(const void *)input[p];
        for (int o = 0; o < CO; o++) {
            const unsigned int *w = (const unsigned int *)(const void *)weight[o];
            int acc = 0;
            for (int c = 0; c < CI / 4; c++) acc += cv_dotsp_b(x[c], w[c]);
            output[p][o] = requant(acc);
        }
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); pwconv_simd(); CYC_STOP(); return checksum(); }
