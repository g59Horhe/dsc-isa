/* Branch-target alignment microbenchmark for the cycle model's Ba term.
 *
 * A loop of N iterations with three instructions per iteration: one 32-bit
 * addi, one 16-bit nop (written as a raw half-word so .option norvc keeps
 * everything else 32-bit), one 32-bit bne back to the label. VARIANT moves
 * the label and the nop:
 *   0: target 0 mod 4, 32-bit instruction at the target          (no penalty expected)
 *   1: target 2 mod 4, 32-bit instruction at the target          (rule A: +1 cycle per iteration)
 *   2: target 2 mod 4, 16-bit at the target, 32-bit at 0 mod 4   (rule C would charge it; A and B not)
 *   3: target 0 mod 4, 16-bit at the target, 32-bit at 2 mod 4   (rule B would charge it; A and C not)
 * Instruction count and taken-branch count are identical in all four, so
 * cycles(variant) - cycles(0) is the aligner penalty times N. */
#include "bench.h"
#ifndef VARIANT
#define VARIANT 0
#endif
#ifndef N
#define N 1000
#endif
#define CNOP ".2byte 0x0001\n"
int main(void) {
    int n = N;
    CYC_START();
    asm volatile(
        ".option push\n.option norvc\n.balign 4\n"
#if VARIANT == 0
        "1:\n addi %0,%0,-1\n" CNOP " bne %0,zero,1b\n"
#elif VARIANT == 1
        CNOP "1:\n addi %0,%0,-1\n" CNOP " bne %0,zero,1b\n"
#elif VARIANT == 2
        CNOP "1:\n" CNOP " addi %0,%0,-1\n bne %0,zero,1b\n"
#else
        "1:\n" CNOP " addi %0,%0,-1\n bne %0,zero,1b\n"
#endif
        ".option pop\n" : "+r"(n) : : "memory");
    CYC_STOP();
    return VARIANT;
}
