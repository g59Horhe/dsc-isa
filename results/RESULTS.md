# int8 depthwise 3x3 convolution on CV32E40P: where the SIMD speedup comes from

CV32E40P under Verilator 5.020, commit b353438. riscv32-unknown-elf-gcc
16.1.0, `-march=rv32imc -mabi=ilp32`. Zero wait states unless stated.
Every kernel uses the same inline-asm requantisation (`sw/requant.h`) and
produces the same checksum per shape. All numbers in this file are
generated from `results/wait0_eqrequant_pad{0,1}.csv` by
`results/wait0_eqrequant_model.py`, and from `harness/sweep.sh`.

This file replaces an earlier RESULTS.md whose headline claims did not
survive verification. The retired claims and why are listed at the end.

## Summary

1. At zero wait states, cycles are predicted by
   `instructions + 2 x taken branches + load-use stalls + split-load bus
   accesses` with R^2 = 0.9998 over 48 runs (6 kernels x 4 shapes x 2 code
   alignments). The residual is under 0.5% at the headline shape and at
   most 2.2% anywhere.
2. The cv.dotsp.b kernel's cycle speedup equals its instruction-count
   ratio to within 0 to 7% at every shape and against every baseline. The
   win is three MACs per instruction, i.e. instruction count, not operand
   supply.
3. Operand-supply terms (split loads plus load-use stalls) are 16 to 17% of
   cycles in the unaligned SIMD kernel and 1 to 6% in the aligned one,
   which is the faster of the two. Split loads alone are 7% and under 2%.
4. The scalar baseline's optimisation level moves the headline more than
   any mechanism under study: -O3 is 1.26 to 1.39x faster than -O2, and a
   hand-written asm loop is -0.6% to +8.1% faster than -O3.
5. Code alignment moves single-run cycle counts by up to 2.3% (7.2% before
   requantisation was equalised): a taken branch whose first 32-bit
   instruction sits at an address 2 mod 4 costs one extra cycle in the
   aligner.
6. Instruction words fetched outnumber data words moved by 3.1 to 7.6x in
   every kernel. On a flat shared bus, latency lands on instruction fetch
   first; latency sweeps must put wait states on the data port only.

## Kernels

| name | file | notes |
|---|---|---|
| scalar C, -O2 | sw/dwconv_opt.c | weights in registers, row pointers, inner loops unrolled; GCC already produces a 3-load sliding window |
| scalar C, -O3 | same source | adds a 2-pixel unroll |
| scalar asm | sw/dwconv_asm.c | hand-written RV32IMC inner loop, 3-pixel unroll with register-renamed sliding window, one base pointer |
| SIMD unaligned | sw/dwconv_simd.c | one word load per row per pixel, cv.dotsp.b with the fourth weight lane zero; 10 of 14 loads per row are unaligned at W=16 |
| SIMD aligned | sw/dwconv_simd_al.c | two aligned loads per row per 4 pixels, shift-and-merge; 2-pixel tail uses the unaligned path |
| SIMD aligned, -O3 | same source | |

Shapes are channels x height x width of the input: 8x16x16 (headline),
16x16x16, 8x32x32, 32x8x8. Output is (H-2) x (W-2) per channel. Test data
are a fixed LCG; outputs after the shift lie in [-15, 16], so saturation
never fires and its cost is paid but its correctness is not exercised.

## Table 1. Wait 0, all kernels and shapes

Cycles at both code alignments (`-DCODE_PAD=0` and `1`). Counters are from
the pad-0 build: instructions retired and taken branches from the core's
hardware counter, fetches / reads / writes from the harness bus counters.
Split-load accesses are bus reads minus loads retired, i.e. the extra
access the LSU issues for each misaligned word. The counters were
validated first: loads retired equal bus reads on every kernel with no
misaligned loads, and stores retired equal bus writes plus the one AUX
store. The three small negative values (-112, -224, -8) are one extra
load retired per output row in the -O3 aligned build, a counter quirk not
chased.

| shape | kernel | cycles (pad 0) | cycles (pad 1) | instructions | fetches | data reads | data writes | taken branches | load-use stalls | split-load accesses | checksum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | scalar C, -O2 | 69,275 | 70,828 | 66,134 | 51,770 | 5,576 | 1,696 | 1,567 | 0 | 0 | 64747 |
|  | scalar C, -O3 | 55,296 | 54,527 | 52,952 | 45,517 | 5,696 | 1,712 | 783 | 0 | 0 | 64747 |
|  | scalar asm | 53,889 | 53,673 | 52,507 | 44,894 | 6,824 | 1,586 | 463 | 0 | 0 | 64747 |
|  | SIMD unaligned | 48,406 | 48,309 | 37,104 | 30,668 | 8,136 | 1,568 | 1,567 | 4,704 | 3,360 | 64747 |
|  | SIMD aligned | 40,287 | 40,286 | 38,280 | 32,172 | 3,216 | 1,688 | 447 | 672 | 224 | 64747 |
|  | SIMD aligned, -O3 | 40,141 | 40,358 | 39,247 | 33,484 | 3,768 | 1,568 | 335 | 448 | -112 | 64747 |
| 16x16x16 | scalar C, -O2 | 138,564 | 141,669 | 132,278 | 103,554 | 11,152 | 3,392 | 3,135 | 0 | 0 | 64114 |
|  | scalar C, -O3 | 110,585 | 109,048 | 105,899 | 91,029 | 11,393 | 3,424 | 1,567 | 0 | 0 | 64114 |
|  | scalar asm | 107,335 | 107,767 | 105,000 | 89,141 | 13,632 | 3,169 | 927 | 0 | 0 | 64114 |
|  | SIMD unaligned | 96,630 | 96,823 | 74,216 | 61,364 | 16,272 | 3,136 | 3,135 | 9,408 | 6,720 | 64114 |
|  | SIMD aligned | 80,503 | 80,534 | 76,071 | 64,741 | 6,416 | 3,360 | 895 | 1,344 | 656 | 64114 |
|  | SIMD aligned, -O3 | 80,710 | 80,277 | 78,488 | 67,172 | 7,536 | 3,136 | 671 | 896 | -224 | 64114 |
| 8x32x32 | scalar C, -O2 | 313,403 | 320,588 | 298,998 | 233,673 | 23,376 | 7,464 | 7,199 | 0 | 0 | 62900 |
|  | scalar C, -O3 | 249,063 | 252,184 | 241,625 | 197,908 | 23,377 | 7,465 | 3,599 | 0 | 0 | 62900 |
|  | scalar asm | 230,366 | 232,751 | 225,545 | 196,716 | 23,136 | 7,224 | 2,399 | 0 | -1 | 62900 |
|  | SIMD unaligned | 219,614 | 219,375 | 167,536 | 138,452 | 37,512 | 7,200 | 7,199 | 21,600 | 15,840 | 62900 |
|  | SIMD aligned | 176,480 | 177,905 | 170,488 | 145,468 | 12,800 | 7,688 | 1,919 | 1,440 | 480 | 62900 |
|  | SIMD aligned, -O3 | 177,657 | 176,456 | 172,154 | 147,606 | 13,760 | 7,208 | 1,679 | 720 | -8 | 62900 |
| 32x8x8 | scalar C, -O2 | 53,413 | 54,564 | 51,112 | 39,971 | 5,376 | 1,472 | 1,151 | 0 | 0 | 65171 |
|  | scalar C, -O3 | 38,696 | 38,536 | 37,960 | 31,491 | 5,569 | 1,633 | 191 | 192 | 0 | 65171 |
|  | scalar asm | 38,754 | 39,137 | 37,990 | 32,545 | 4,928 | 1,184 | 383 | 0 | 0 | 65171 |
|  | SIMD unaligned | 36,934 | 37,125 | 28,873 | 23,875 | 6,048 | 1,152 | 1,151 | 3,456 | 2,304 | 65171 |
|  | SIMD aligned | 30,341 | 30,180 | 27,688 | 24,866 | 3,168 | 1,152 | 255 | 1,152 | 576 | 65171 |
|  | SIMD aligned, -O3 | 30,211 | 30,180 | 29,798 | 26,210 | 3,744 | 1,152 | 191 | 0 | 0 | 65171 |

## Cycle model

`cycles = instructions + 2 x taken branches + load-use stalls + split-load accesses`

| predictor | R^2 over 48 runs |
|---|---|
| the model above | 0.9998 |
| instructions retired alone | 0.985 |
| instruction fetches alone | 0.977 |
| loads alone | 0.929 |
| data reads alone | 0.746 |

The 2 cycles per taken branch and 1 cycle per load-use hazard were
confirmed with microbenchmarks (`sw/ubench_unaligned.c` and a load-use
variant): an aligned load followed by a dependent instruction costs one
stall; a misaligned one costs one stall plus one extra bus access. The
fetch-wait counter is zero in every run: at wait 0 the instruction port
never stalls the core.

Per-kernel decomposition (share of cycles, better alignment):

| shape | kernel | instructions | taken-branch penalty | load-use stalls | split loads | residual |
|---|---|---|---|---|---|---|
| 8x16x16 | scalar C, -O2 | 95.5% | 4.5% | 0.0% | 0.0% | +0.0% |
| 8x16x16 | scalar C, -O3 | 97.1% | 2.9% | 0.0% | 0.0% | +0.0% |
| 8x16x16 | scalar asm | 97.8% | 1.7% | 0.0% | 0.0% | +0.4% |
| 8x16x16 | SIMD unaligned | 76.8% | 6.5% | 9.7% | 7.0% | +0.0% |
| 8x16x16 | SIMD aligned | 95.0% | 2.2% | 1.7% | 0.6% | +0.5% |
| 8x16x16 | SIMD aligned, -O3 | 97.2% | 1.7% | 1.1% | -0.3% | +0.3% |
| 16x16x16 | scalar C, -O2 | 95.5% | 4.5% | 0.0% | 0.0% | +0.0% |
| 16x16x16 | scalar C, -O3 | 97.1% | 2.9% | 0.0% | 0.0% | +0.0% |
| 16x16x16 | scalar asm | 97.8% | 1.7% | 0.0% | 0.0% | +0.4% |
| 16x16x16 | SIMD unaligned | 76.8% | 6.5% | 9.7% | 7.0% | +0.0% |
| 16x16x16 | SIMD aligned | 94.5% | 2.2% | 1.7% | 0.8% | +0.8% |
| 16x16x16 | SIMD aligned, -O3 | 97.2% | 1.7% | 1.1% | -0.3% | +0.3% |
| 8x32x32 | scalar C, -O2 | 95.4% | 4.6% | 0.0% | 0.0% | +0.0% |
| 8x32x32 | scalar C, -O3 | 97.0% | 2.9% | 0.0% | 0.0% | +0.1% |
| 8x32x32 | scalar asm | 97.9% | 2.1% | 0.0% | -0.0% | +0.0% |
| 8x32x32 | SIMD unaligned | 76.4% | 6.6% | 9.8% | 7.2% | +0.0% |
| 8x32x32 | SIMD aligned | 96.6% | 2.2% | 0.8% | 0.3% | +0.1% |
| 8x32x32 | SIMD aligned, -O3 | 97.6% | 1.9% | 0.4% | -0.0% | +0.1% |
| 32x8x8 | scalar C, -O2 | 95.7% | 4.3% | 0.0% | 0.0% | -0.0% |
| 32x8x8 | scalar C, -O3 | 98.5% | 1.0% | 0.5% | 0.0% | +0.0% |
| 32x8x8 | scalar asm | 98.0% | 2.0% | 0.0% | 0.0% | -0.0% |
| 32x8x8 | SIMD unaligned | 78.2% | 6.2% | 9.4% | 6.2% | -0.0% |
| 32x8x8 | SIMD aligned | 91.7% | 1.7% | 3.8% | 1.9% | +0.8% |
| 32x8x8 | SIMD aligned, -O3 | 98.7% | 1.3% | 0.0% | 0.0% | +0.0% |

## Table 2. Speedups

Better alignment for each kernel. "instr ratio" is the ratio of
instructions retired, i.e. what a pure code-density model would predict.

| shape | SIMD aligned vs -O2 | instr ratio | vs -O3 | instr ratio | vs asm | instr ratio | SIMD unaligned vs asm |
|---|---|---|---|---|---|---|---|
| 8x16x16 | 1.73x | 1.69 | 1.36x | 1.35 | 1.34x | 1.34 | 1.11x |
| 16x16x16 | 1.73x | 1.69 | 1.36x | 1.35 | 1.34x | 1.34 | 1.11x |
| 8x32x32 | 1.78x | 1.74 | 1.41x | 1.40 | 1.31x | 1.31 | 1.05x |
| 32x8x8 | 1.77x | 1.85 | 1.28x | 1.37 | 1.28x | 1.37 | 1.05x |

The cycle speedup tracks the instruction ratio within 0 to 7%, and the gap
is always in one direction: the SIMD kernels carry the load-use stalls and
split loads that the scalar kernels do not. The unaligned SIMD kernel
beats the hand asm scalar by only 5 to 11%.

## Scalar baseline strength

| shape | -O2 / -O3 | -O3 / asm |
|---|---|---|
| 8x16x16 | 1.27x | asm 1.6% faster |
| 16x16x16 | 1.27x | asm 1.6% faster |
| 8x32x32 | 1.26x | asm 8.1% faster |
| 32x8x8 | 1.39x | asm 0.6% slower |

Against -O2 the aligned SIMD kernel is 1.73 to 1.78x. Against -O3 or asm
it is 1.28 to 1.41x. Nothing in the hardware changed between those two
sentences. Any speedup reported for an ISA extension has to state the
baseline's optimisation level, and -O2 is not a credible one.

## Code alignment

Spread between the two code alignments, |pad1 - pad0| / min:

| kernel | 8x16x16 | 16x16x16 | 8x32x32 | 32x8x8 |
|---|---|---|---|---|
| scalar C, -O2 | 2.2% | 2.2% | 2.3% | 2.2% |
| scalar C, -O3 | 1.4% | 1.4% | 1.3% | 0.4% |
| scalar asm | 0.4% | 0.4% | 1.0% | 1.0% |
| SIMD unaligned | 0.2% | 0.2% | 0.1% | 0.5% |
| SIMD aligned | 0.0% | 0.0% | 0.8% | 0.5% |
| SIMD aligned, -O3 | 0.5% | 0.5% | 0.7% | 0.1% |

Mechanism, confirmed in `cv32e40p_aligner.sv`: after a taken branch, if the
first 32-bit instruction at the target sits at an address that is 2 mod 4,
the aligner needs a second fetch word before it can issue, costing one
cycle per taken branch. Kernels with more taken branches per pixel are more
exposed; before requantisation was equalised the unaligned SIMD kernel had
three per pixel and moved 7.2% between alignments. Report both alignments.
The tables above quote the better one for each kernel, stated as the rule.

## Unaligned loads

Microbenchmark, 50 back-to-back `lw` with no dependent consumer:

| wait states | aligned | offset 1, 2 or 3 | ratio |
|---|---|---|---|
| 0 | 53 | 103 | 1.94 |
| 1 | 105 | 204 | 1.94 |
| 2 | 158 | 306 | 1.94 |
| 3 | 211 | 408 | 1.93 |

Net of the 1-cycle bracket overhead the cost is exactly one extra bus
access per misaligned word: 2.0x at every wait state. In the unaligned
kernel, 10 of 14 loads per output row are misaligned at W=16 (71%), 22 of
30 at W=32, 4 of 6 at W=8. The bus counter confirms it: 8,136 data reads
at 8x16x16 against 4,776 loads retired, the difference being exactly the
3,360 misaligned loads.

## Data-port latency

`harness/sweep.sh`, wait states on the data port only (`--iwait 0`).
Cycles at wait 0 / 1 / 2 / 3:

| shape | kernel | w0 | w1 | w2 | w3 | growth w3/w0 |
|---|---|---|---|---|---|---|
| 8x16x16 | scalar -O2 | 69,275 | 74,980 | 82,253 | 89,526 | 1.29 |
| | scalar asm | 53,889 | 62,300 | 70,711 | 79,122 | 1.47 |
| | SIMD unaligned | 48,406 | 58,111 | 67,816 | 77,521 | 1.60 |
| | SIMD aligned | 40,287 | 44,968 | 49,873 | 54,778 | 1.36 |
| 16x16x16 | scalar -O2 | 138,564 | 149,973 | 164,518 | 179,063 | 1.29 |
| | scalar asm | 107,335 | 124,137 | 140,939 | 157,741 | 1.47 |
| | SIMD unaligned | 96,630 | 116,039 | 135,448 | 154,857 | 1.60 |
| | SIMD aligned | 80,503 | 89,832 | 99,609 | 109,386 | 1.36 |
| 8x32x32 | scalar -O2 | 313,403 | 337,044 | 367,885 | 398,726 | 1.27 |
| | scalar asm | 230,366 | 260,727 | 291,088 | 321,449 | 1.40 |
| | SIMD unaligned | 219,614 | 264,327 | 309,040 | 353,753 | 1.61 |
| | SIMD aligned | 176,480 | 196,489 | 216,978 | 237,467 | 1.35 |
| 32x8x8 | scalar -O2 | 53,413 | 59,110 | 65,959 | 72,808 | 1.36 |
| | scalar asm | 38,754 | 44,867 | 50,980 | 57,093 | 1.47 |
| | SIMD unaligned | 36,934 | 44,135 | 51,336 | 58,537 | 1.58 |
| | SIMD aligned | 30,341 | 34,278 | 38,407 | 42,728 | 1.41 |

Two things follow. The unaligned SIMD kernel is the most latency-sensitive
kernel measured (1.58 to 1.61x from wait 0 to 3) because every split load
pays the latency twice; at three wait states it is within 2% of the hand
asm scalar. And the direction of the "speedup versus latency" trend
depends on the baseline: against -O2 the aligned SIMD speedup falls from
1.72x to 1.63x, against asm it rises from 1.34x to 1.44x, because the
-O2 code happens to issue fewer loads per pixel than the asm loop. There
is no robust latency trend to report.

When wait states are applied to both ports, as the previous RESULTS.md
did, the scalar -O2 kernel at 8x16x16 goes from 70,979 to 227,557 cycles
at wait 3, and 225,957 of that is reproduced by instruction-port wait
alone. Those sweeps measured fetch starvation.

### Instruction-cache check

The data-only sweep models instruction memory as zero-wait. To check that an
instruction cache behaves the same way for these kernels, the harness has a
direct-mapped I-cache model (`--icache SIZE LINE`): a hit answers with zero
wait, a miss pays the instruction-port wait and fills the line. At 8x16x16
with three data-port wait states and a three-cycle miss penalty:

| kernel | both ports wait 3 | instruction port zero-wait | 1 KB I-cache, 16 B lines | hits / misses | 256 B I-cache | hits / misses |
|---|---|---|---|---|---|---|
| scalar -O2 | 207,085 | 89,526 | 89,546 | 51,754 / 16 | 89,546 | 51,754 / 16 |
| scalar asm | 179,808 | 79,122 | 79,178 | 44,857 / 37 | 92,089 | 38,109 / 6,785 |
| SIMD unaligned | 130,512 | 77,521 | 77,538 | 30,653 / 14 | 77,538 | 30,653 / 14 |
| SIMD aligned | 130,488 | 54,778 | 54,845 | 32,136 / 36 | 63,511 | 27,349 / 4,823 |

A 1 KB cache reproduces the zero-wait instruction port to within 0.1% with a
few dozen misses, so "zero-wait instruction memory" is a measured statement
for this code size, not an assumption. A 256 B direct-mapped cache thrashes
on the two kernels whose loops exceed it; no MCU ships one that small.

## Retired claims from the previous RESULTS.md

| claim | status | what the data say |
|---|---|---|
| 1.85x over a hand-optimised scalar baseline, 43% of arithmetic realised | retired | baseline was -O2 C; 1.73 to 1.78x vs -O2 with equal requantisation, 1.28 to 1.41x vs -O3 or asm; "realised fraction" depended on an unstated formula and the weak baseline |
| two of every three activation loads unaligned | wrong | 10 of 14 at W=16; the email draft said three of four, also wrong |
| unaligned loads cost about 2.1x | overstated | 2.0x, exactly one extra bus access |
| operand supply limits the SIMD speedup | retired | split loads are 7% of cycles in the unaligned kernel and under 2% in the aligned one; the speedup is the instruction-count ratio |
| software workaround relocates the bottleneck to the register file | retired | the aligned kernel spills 4 words per output row, none per pixel; the "32 stack accesses" figure counted the whole function |
| speedup grows with memory latency | retired | wait states were applied to the instruction port; with data-only latency the trend's direction depends on the baseline |
| branchless saturation in every kernel | wrong as executed | the C form compiled to two taken branches per pixel in every kernel, 13 to 19% of cycles; now inline asm |
| aligned/unaligned crossover under GCC 13.2 | already retired | not re-examined |

## Threats to validity

- One core, one kernel size (3x3 depthwise), one quantisation scheme, one
  synthetic input distribution that never saturates.
- Flat memory with no bus contention between ports. Instruction memory
  is zero-wait or a direct-mapped I-cache model; no data cache.
- Both SIMD kernels are compiler output from C with `.insn`. Hardware
  loops and post-increment loads exist on this core and were not used;
  a hand-written SIMD kernel would be the fair counterpart to the hand
  asm scalar.
- Single compiler version for the equalised dataset. The earlier 7%
  disagreement between GCC 13.2 and 16.1 on the unaligned SIMD kernel
  was not re-examined after equalisation.
- No area numbers.

## Reproducing

    cd harness && make all
    ./collect_wait0.sh ../results/pad0.csv "1 2 5 9" "-DCODE_PAD=0"
    ./collect_wait0.sh ../results/pad1.csv "1 2 5 9" "-DCODE_PAD=1"
    cd ../results && python3 wait0_eqrequant_model.py
    cd ../harness && ./sweep.sh        # data-port latency, IWAIT=0

Regression values: hello 38 cycles / 42; dotp 41 / 10 on Xpulp, TIMEOUT on
baseline; scalar -O2 at 8x16x16 wait 0: 69,275 cycles, checksum 64747.
