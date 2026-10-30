/* Jump-cost microbenchmark for the cycle model (unconditional jumps: jal, jalr).
 *
 * A loop of N iterations, all 32-bit instructions at 0 mod 4 targets (no
 * aligner term). VARIANT:
 *   0: addi, bne                                  (baseline: 2 instructions, 1 taken branch)
 *   1: addi, jal to the next-but-one word, nop, bne  (one jal per iteration, skipping a nop)
 *   2: addi, jal ra to a stub that returns (jalr), bne (a call and a return per iteration)
 * The nop in variant 1 is never executed, so instructions per iteration are
 * 3 in variant 1 and 4 in variant 2. Cost per jump =
 *   (cycles(variant) - cycles(0) - N * (extra instructions)) / (N * jumps per iteration).
 * Event 7 (jumps) in the harness EVENTS line counts them. */
#include "bench.h"
#ifndef VARIANT
#define VARIANT 0
#endif
#ifndef N
#define N 1000
#endif
int main(void) {
    int n = N;
    CYC_START();
    asm volatile(
        ".option push\n.option norvc\n.balign 4\n"
#if VARIANT == 0
        "1:\n addi %0,%0,-1\n bne %0,zero,1b\n"
#elif VARIANT == 1
        "1:\n addi %0,%0,-1\n jal zero,2f\n nop\n2:\n bne %0,zero,1b\n"
#else
        " j 1f\n"
        "3:\n jalr zero,0(ra)\n"
        "1:\n addi %0,%0,-1\n jal ra,3b\n bne %0,zero,1b\n"
#endif
        ".option pop\n" : "+r"(n) : : "ra", "memory");
    CYC_STOP();
    return VARIANT;
}
