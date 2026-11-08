/* Unaligned word-store microbenchmark (review round R7): 50 sw to buf+OFF, back-to-back, the
   counterpart of ubench_unaligned.c for stores. EMPTY=1 measures bracket overhead only. */
#include "bench.h"
#ifndef OFF
#define OFF 0
#endif
static unsigned char buf[256] __attribute__((aligned(16)));
int main(void) {
    unsigned char *p = buf + OFF;
    CYC_START();
#ifndef EMPTY
    asm volatile(".rept 50\n sw zero, 0(%0)\n .endr" : : "r"(p) : "memory");
#endif
    CYC_STOP();
    return OFF;
}
