/* Pointwise 1x1 convolution -- plain C, the scalar baseline. */
#include "pw_common.h"
static void pwconv(void) {
    for (int p = 0; p < P; p++) {
        const signed char *x = input[p];
        for (int o = 0; o < CO; o++) {
            const signed char *w = weight[o];
            int acc = 0;
            for (int c = 0; c < CI; c++) acc += x[c] * w[c];
            output[p][o] = requant(acc);
        }
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); pwconv(); CYC_STOP(); return checksum(); }
