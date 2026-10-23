/* Cycle measurement for the CV32E40P harness.
 *
 * The harness watches for stores to four magic addresses:
 *   0x10000000  halt, and report the stored word
 *   0x10000004  start the cycle counter
 *   0x10000008  stop it
 *   0x1000000C  print the stored word as "AUX <n>"
 *
 * Bracketing the measured region in the program itself keeps reset,
 * fetch-enable and crt0 out of the number. The harness prints:
 *   MEASURED <n> cycles (wait_states=<w> iwait=<i>) dread=<r> dwrite=<w> ifetch=<f>
 *
 * Optional: compile with -DPERF_EVENT=<bit> to program CV32E40P's single
 * hardware performance counter (mhpmcounter3) with that event and report
 * the delta over the measured region on an AUX line. Event bits, from
 * cv32e40p_core.sv hpm_events[]:
 *   1 instructions retired     2 load-use stalls      3 jump-register stalls
 *   4 fetch-wait cycles        5 loads                6 stores
 *   7 jumps                    8 branches             9 taken branches
 *  10 compressed instructions
 * PERF_EVENT builds need -march=rv32imc_zicsr for the csr instructions.
 * The CSR accesses add about ten cycles inside the bracket, so take cycle
 * counts from builds without PERF_EVENT.
 */
#ifndef BENCH_H
#define BENCH_H

/* Optional -DCODE_PAD=<n> inserts n compressed nops at the top of main.
 * On CV32E40P a loop whose first word straddles a 32-bit boundary after a
 * taken back-edge costs 2 extra cycles per iteration, so measure each
 * kernel at both code alignments (CODE_PAD=0 and 1) and report both. */
#ifdef CODE_PAD
#define BENCH_XS_(x) BENCH_S_(x)
#define BENCH_S_(x) #x
#define BENCH_PAD() asm volatile (".rept " BENCH_XS_(CODE_PAD) "\n c.nop\n .endr")
#else
#define BENCH_PAD() do {} while (0)
#endif

#ifdef PERF_EVENT
static unsigned int perf_start_;
static inline unsigned int perf_read_(void) {
    unsigned int v; asm volatile ("csrr %0, 0xB03" : "=r"(v)); return v;
}
#define CYC_START() do { \
    asm volatile ("csrw 0x323, %0" : : "r"(1u << (PERF_EVENT))); \
    asm volatile ("csrw 0x320, zero"); \
    (*(volatile int *)0x10000004 = 1); \
    perf_start_ = perf_read_(); } while (0)
#define CYC_STOP() do { \
    unsigned int perf_end_ = perf_read_(); \
    (*(volatile int *)0x10000008 = 1); \
    (*(volatile unsigned int *)0x1000000C = perf_end_ - perf_start_); } while (0)
#else
#define CYC_START() (*(volatile int *)0x10000004 = 1)
#define CYC_STOP()  (*(volatile int *)0x10000008 = 1)
#endif

#endif
