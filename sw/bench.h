/* Cycle measurement for the CV32E40P harness.
 *
 * The harness watches for stores to three magic addresses:
 *   0x10000000  halt, and report the stored word
 *   0x10000004  start the cycle counter
 *   0x10000008  stop it
 *
 * Bracketing the measured region in the program itself keeps reset,
 * fetch-enable and crt0 out of the number. The harness prints:
 *   MEASURED <n> cycles (wait_states=<w>)
 */
#ifndef BENCH_H
#define BENCH_H

#define CYC_START() (*(volatile int *)0x10000004 = 1)
#define CYC_STOP()  (*(volatile int *)0x10000008 = 1)

#endif
