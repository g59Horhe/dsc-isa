/* Unaligned word-load microbenchmark: 50 lw from buf+OFF, back-to-back,
   no dependent consumer. EMPTY=1 measures bracket overhead only. */
#include "bench.h"
#ifndef OFF
#define OFF 0
#endif
static unsigned char buf[256] __attribute__((aligned(16)));
int main(void) {
    unsigned char *p = buf + OFF;
    CYC_START();
#ifndef EMPTY
    asm volatile(".rept 50\n lw t0, 0(%0)\n .endr" : : "r"(p) : "t0", "memory");
#endif
    CYC_STOP();
    return OFF;
}
