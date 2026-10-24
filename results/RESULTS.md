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
   most 2.2% anywhere. The coefficients are fixed from microbenchmarks, not
   fitted; the mean absolute error is 0.57% over those 48 runs and 0.73%
   (maximum 6.4%) over the 256 hand-written-kernel runs of all three
   families. A fifth term, Ba = redirects whose target is a 32-bit
   instruction at an address 2 mod 4 (the aligner penalty, counted from
   the harness's fetch stream by `results/align_term.py`), brings those
   to 0.09% / 0.74% (R^2 1.0000) and 0.14% / 1.81%.
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
   aligner. Counted per run, it is the fifth term of the cycle model
   (point 1).
6. Instruction words fetched outnumber data words moved by 3.1 to 7.6x in
   every kernel. On a flat shared bus, latency lands on instruction fetch
   first; latency sweeps must put wait states on the data port only.
7. Sky130 synthesis: the RV32IMC core is 43.8 kGE, the full Xpulp
   extension adds 57%. Half of that is the dot-product multiplier.
8. Decomposed with hand-written kernel pairs: the dot-product datapath is
   worth 1.26 to 1.37x on its own; hardware loops and post-increment
   addressing are worth 1 to 5% on an unrolled scalar loop and 21 to 24%
   on a short SIMD loop. The fastest kernel, unaligned SIMD with Xpulp
   control, is 1.65x over the hand scalar and 2.13x over the original -O2
   C baseline at zero wait states, and split loads are 10% of its cycles.
   A data wait state costs exactly one cycle per bus access, so the
   aligned kernel overtakes it from two wait states.
9. On pointwise 1x1 convolution the same extension is worth 3.4x against a
   -O3 or hand scalar baseline, with the cycle speedup again equal to the
   instruction ratio. Four lanes, aligned loads and activation reuse take
   the datapath's own contribution from 1.3x to 2.7x. -O2 to -O3 is worth
   2.5x on that scalar kernel.
10. On 5x5 depthwise the extension (without clip) is worth 3.5x against -O3
   and 3.0x against the best hand scalar kernel; the datapath alone 2.6x.
   Split loads are 19 to 20% of the best kernel's cycles, the largest
   operand-supply share measured. The first hand scalar kernel (row-wise,
   accumulator row in memory) matched -O3 within 1%; an output-stationary
   kernel that keeps the accumulator in a register and reloads five weights
   per kernel row is 17 to 32% faster than both, and is the 5x5 baseline
   from here on. Matching the compiler did not make the first one strong.
11. Real MobileNetV1 weights and activations (two layers, cropped to the
   measured shapes) give cycle counts identical to synthetic data through
   the same code path in 95 of 96 runs, and one cycle per output less than
   the int8 synthetic runs, as the shorter clamp predicts. Over half the
   real outputs clamp to zero; nothing on the measured path depends on it.
12. With cv.clip replacing the branch-free saturation, the complete Xpulp
   extension is worth 2.5x (3x3), 4.3x (5x5) and 5.4x (1x1) against -O3,
   and 2.5x, 3.6x and 5.4x against the best hand scalar kernels, 0.73 to
   1.53 cycles per MAC. Clip is worth 1.2 to 1.6x added last, on top of
   SIMD and hardware loops, and 1.1 to 1.4x by Shapley value over the 2^3
   feature grid against 1.1 to 1.2x for the loop hardware; it beats the loop
   hardware on all three kernels in every view, for at most 2.7 kGE (the
   SIMD ALU, an upper bound) against the loop hardware's 4.2 kGE. Against
   the row-wise 5x5 baseline the loop hardware had been ahead by Shapley
   value (1.21x vs 1.13x): its apparent value was that baseline's five
   branches per output.
13. Behind instruction memory with wait states the core is fetch-bound and
   cycles follow instruction words fetched. Hardware-loop bodies cannot be
   compressed, so hardware loops and post-increment then cost 14 to 16% on
   the scalar kernel and 2 to 4% on aligned SIMD, and still save 20 to 26%
   on the short unaligned SIMD loop. The control term's sign depends on the
   instruction memory.
14. After placement and repair in OpenROAD, area overhead is 58.6% (57% at
   synthesis) and the extension lengthens the critical path by 12.7%,
   through the ALU result forwarding network into the dot-product operand
   register. Wall-clock speedups are the cycle speedups divided by 1.13:
   2.2x / 3.8x / 4.8x against -O3, 2.2x / 3.2x / 4.8x against the hand
   baselines.
15. A whole depthwise-separable block on real data composes exactly from
   its stages (3 cycles off the sum). The layout change between them costs
   21% of the accelerated block and the extension does not touch it; a
   strided store in the depthwise kernel removes it for free. Block
   speedup: 3.3x to 4.1x over -O3 C depending on who fuses.
16. On a second core, lowRISC Ibex, the same binaries run with identical
   instruction counts; cycles are 1.05 to 1.27x (2-stage) and 0.90 to 1.00x
   (3-stage) of CV32E40P's. The baseline-flag and code-alignment effects
   reproduce at the same magnitude, and the cycle model keeps its structure
   with core-specific stall terms. Two RV32IMC cores synthesise to within
   0.5% of each other; the Xpulp extension is more than half of either.

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

The coefficients are fixed from the microbenchmarks below, not fitted, so
the R^2 is that of a fixed-form prediction. Mean absolute error 0.57%,
maximum 2.24%, over the 48 runs; 0.73% and 6.4% over the 256 hand-written
kernel runs of all three families, with and without clip
(`results/clip_model.py`).

### Fifth term: branch-target alignment

The residual of the four-term model is the aligner effect of the code
alignment section: a taken branch, jump or hardware-loop return whose
target is a 32-bit instruction at an address 2 mod 4 costs one cycle,
because the fetched word holds only its lower half. `harness/sim_main.cpp
--redir <file>` writes the histogram of non-sequential instruction fetches
(word addresses) in the measured window; `results/align_term.py` rebuilds
every hand-written and equalised run (304; the rebuilt binary must
reproduce the committed cycle count, which it does in every case), resolves
each redirect to its target PC from the ELF, and counts the penalised
redirects, Ba. Three rules for which targets pay were tested against all
304 runs; rule A is the one above and is used:

rule | mean |resid| | max | runs over 1% (all 304 runs)
A | 0.13% | 1.81% | 5
B | 0.24% | 3.17% | 15
C | 0.26% | 3.17% | 17
rule A written as ba
equalised 3x3 set (6 kernels x 4 shapes x 2 alignments): 48 runs; four-term model mean |resid| 0.57% max 2.24%; with the alignment term mean 0.09% max 0.74%; runs over 1%: 9 -> 0; runs with Ba > 0: 42
hand-written runs (three families, with and without clip): 256 runs; four-term model mean |resid| 0.73% max 6.36%; with the alignment term mean 0.14% max 1.81%; runs over 1%: 52 -> 5; runs with Ba > 0: 144
all: 304 runs; four-term model mean |resid| 0.71% max 6.36%; with the alignment term mean 0.13% max 1.81%; runs over 1%: 61 -> 5; runs with Ba > 0: 186

With Ba the model is `cycles = I + 2 x taken branches + load-use stalls +
split-load accesses + Ba`: R^2 1.0000 (four decimals), mean 0.09%, maximum
0.74% over the 48 runs; mean 0.14%, maximum 1.81% over the 256 hand-written
runs, where the five runs still above 1% are 3x3 SIMD kernels, four of
them at 32x8x8. `results/wait0_align.csv` holds Ba per run and the model
scripts add it when the file is present; every residual quoted below is
five-term. Worst four-term runs:

| run | cycles | I | 2Bt | Slu | Asplit | redirects | Ba | residual, four terms | residual, five terms |
|---|---|---|---|---|---|---|---|---|---|
| pw_simd_asm_rv_clip 8x8x16x16 pad0 | 28,165 | 22,280 | 4,094 | 0 | 0 | 2,047 | 1,792 | +6.36% | -0.00% |
| pw_simd_asm_rv_clip 16x32x8x8 pad1 | 35,333 | 29,256 | 4,094 | 0 | 0 | 2,047 | 1,984 | +5.61% | -0.00% |
| pw_simd_asm_rv_clip 16x16x16x16 pad0 | 71,687 | 59,656 | 8,190 | 0 | 0 | 4,095 | 3,840 | +5.36% | +0.00% |
| pw_simd_asm_rv_clip 16x16x8x8 pad1 | 17,924 | 14,918 | 2,046 | 0 | 0 | 1,023 | 960 | +5.36% | +0.00% |
| simd_unal_asm_rv_clip 8x32x32 pad0 | 139,222 | 101,784 | 14,398 | 0 | 15,840 | 7,199 | 7,199 | +5.17% | +0.00% |
| simd_unal_asm_rv_clip 16x16x16 pad1 | 61,221 | 45,303 | 6,270 | 0 | 6,720 | 3,135 | 2,927 | +4.78% | +0.00% |
| simd_unal_asm_rv_clip 32x8x8 pad0 | 23,428 | 17,703 | 2,302 | 0 | 2,304 | 1,151 | 1,120 | +4.78% | -0.00% |
| simd_unal_asm_rv_clip 8x16x16 pad1 | 30,614 | 22,664 | 3,134 | 0 | 3,360 | 1,567 | 1,456 | +4.76% | +0.00% |
| pw_simd_asm_rv 8x8x16x16 pad0 | 42,501 | 36,616 | 4,094 | 0 | 0 | 2,047 | 1,792 | +4.21% | -0.00% |
| pw_simd_asm_rv 16x32x8x8 pad0 | 49,669 | 43,592 | 4,094 | 0 | 0 | 2,047 | 1,984 | +3.99% | -0.00% |
| pw_simd_asm_rv 16x16x16x16 pad0 | 100,359 | 88,328 | 8,190 | 0 | 0 | 4,095 | 3,840 | +3.83% | +0.00% |
| pw_simd_asm_rv 16x16x8x8 pad1 | 25,092 | 22,086 | 2,046 | 0 | 0 | 1,023 | 960 | +3.83% | +0.00% |


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

## Area: Sky130 HD, synthesis

Flow: sv2v 0.0.13 converts the SystemVerilog to Verilog, Yosys 0.70 (OSS
CAD Suite 2026-10-23) synthesises `cv32e40p_core` with the generic `synth`
flow and maps to `sky130_fd_sc_hd__tt_025C_1v80.lib` with `dfflibmap` and
`abc`. No timing constraints at this stage; placement-aware area and
timing follow in the next section. Flip-flop register
file; FPU excluded; the behavioural clock gate is a latch plus AND.
`syn/Makefile` reproduces everything in under a minute. Gate equivalents
use `sky130_fd_sc_hd__nand2_1` = 3.7536 um^2.

| configuration | cells | area (um^2) | GE | flops |
|---|---|---|---|---|
| COREV_PULP=0 (RV32IMC) | 19,989 | 164,298 | 43,771 | 2,128 |
| COREV_PULP=1 (Xpulp) | 33,418 | 257,885 | 68,703 | 2,479 |
| delta | | | +24,932 | +351 |

The whole Xpulp extension costs 57% of the RV32IMC core at this flow. That
is the entire extension: SIMD ALU and dot products, hardware loops,
post-increment addressing, bit manipulation, and the third register read
port they need. XpulpNN's reported ~11% is for its NN additions on top of
an Xpulp core, so the two numbers are not comparable, and this is why the
literature's 11% / 35% / 108% spread needed a controlled measurement.

### Where the extension's area lives

Per-module attribution. Every cell is tagged with its module of origin
before flattening; the design is flattened so the COREV_PULP constants
propagate and dead logic is removed; the surviving cells are partitioned
back into per-origin modules (`submod`) before mapping. A plain
hierarchical synthesis cannot do this: without flattening, the multiplier
keeps its dot-product datapath in both configurations (21 kGE either way)
because the decoder's constant zeros never cross the module boundary.

| module of origin | RV32IMC (GE) | Xpulp (GE) | delta (GE) | delta | share of delta |
|---|---|---|---|---|---|
| mult | 8,637 | 20,777 | 12,140 | 141% | 50% |
| alu | 2,866 | 5,554 | 2,688 | 94% | 11% |
| register_file | 15,319 | 17,540 | 2,221 | 14% | 9% |
| hwloop_regs | 0 | 2,088 | 2,088 | nan% | 9% |
| id_stage | 4,147 | 6,060 | 1,912 | 46% | 8% |
| controller | 514 | 2,031 | 1,518 | 295% | 6% |
| decoder | 697 | 1,309 | 612 | 88% | 3% |
| aligner | 826 | 1,404 | 578 | 70% | 2% |
| cs_registers | 6,958 | 7,211 | 253 | 4% | 1% |
| (untagged, created by opt) | 373 | 568 | 195 | 52% | 1% |
| prefetch_controller | 580 | 669 | 89 | 15% | 0% |
| ex_stage | 270 | 274 | 4 | 1% | 0% |
| fifo | 770 | 774 | 4 | 1% | 0% |
| compressed_decoder | 315 | 319 | 4 | 1% | 0% |
| ff_one | 105 | 106 | 1 | 1% | 0% |
| alu_div | 2,006 | 1,995 | -12 | -1% | -0% |
| load_store_unit | 1,375 | 1,360 | -14 | -1% | -0% |
| if_stage | 1,148 | 1,086 | -62 | -5% | -0% |
| **total** | **47,969** | **72,187** | **24,218** | **50%** | |

Grouped for the paper (`results/area_table.py`), with the rows that the
named groups leave out collected under "other":

Attribution of the extension's synthesis area, grouped (delta 24,218 GE in the attribution pass; 24,932 GE flat, +2.9% apart):

| group (modules of origin) | delta GE | share of attribution delta |
|---|---|---|
| dot-product multiplier | +12,140 | 50% |
| SIMD ALU (carries clip and all vector ops; upper bound for clip) | +2,688 | 11% |
| register file, third read port | +2,221 | 9% |
| hardware-loop registers | +2,088 | 9% |
| controller + decoder | +2,130 | 9% |
| ID stage | +1,912 | 8% |
| other (18 modules: aligner, CSRs, untagged, prefetch, ...) | +1,039 | 4% |
| **total, attribution pass** | **+24,218** | |

hwloop_regs + controller + decoder = 4,218 GE; with id_stage 6,130 GE. SIMD ALU 2,688 GE = 64% of the first, 44% of the second.
listed rows (six groups) sum to 23,179; the other 18 modules sum to 1,039 GE: aligner +578, cs_registers +253, untagged +195, prefetch_controller +89, if_stage -62, load_store_unit -14, alu_div -12, ex_stage +4, fifo +4, compressed_decoder +4, ff_one +1, popcnt +0, obi_interface +0, clock_gate +0, sleep_unit +0, prefetch_buffer +0, int_controller +0, core +0

Totals in this pass are 10% above the flat pass because the partition
blocks cross-origin optimisation in ABC; the delta, 24,218 GE, is within
2.9% of the flat pass's 24,932 GE. Yosys reports undriven-wire warnings after partitioning
(x0 write-enable bit and similar), not investigated further.

Half of the extension is the dot-product multiplier (+12.1 kGE).
Hardware-loop registers, controller and decoder together are +4.2 kGE,
17% (+6.1 kGE, 25%, with the ID stage's growth); the SIMD ALU, which
carries cv.clip and every other vector operation, is +2.7 kGE, 64% of
that grouping and an upper bound for clip's own cost. The register
file grows by 2.2 kGE because the third read port is dead logic without
the extension. The cv.dotsp.b kernel in this study uses the multiplier and
nothing else from the extension: it gains 1.28 to 1.41x in cycles against
a -O3 or asm scalar baseline for a 12.1 kGE (28%) multiplier plus whatever
share of decoder and register-file growth one attributes to it, and 57% if
the whole extension is counted. Hardware loops and post-increment
addressing are measured separately in the decomposition section below.

## Timing and placement

Static timing on the raw synthesised netlist is not meaningful: the
netlist has no buffer trees, so a minimum-size gate driving a few hundred
pins shows a 15 ns slew, and both configurations report 22 to 29 ns
register-to-register paths dominated by such nets (`syn/sta.tcl`, kept as
the negative example). The numbers below come from OpenROAD
(`syn/place.tcl`): floorplan at 45% target utilisation on the sky130hd
site, pin placement, timing-driven global placement, DRV repair
(buffering and resizing), detailed placement, placement-based parasitics,
then `repair_timing` against a 10 ns clock. Pre-CTS, pre-route; the
reset is a false path (it would be a synchronised tree in a real system).

| configuration | synthesis GE (flat) | placed GE | worst reg-to-reg slack at 10 ns | estimated minimum period | estimated Fmax | path stages |
|---|---|---|---|---|---|---|
| RV32IMC | 43,771 | 50,024 | -1.52 ns | 11.52 ns | 86.8 MHz | 45 |
| Xpulp | 68,703 | 79,320 | -2.98 ns | 12.98 ns | 77.0 MHz | 57 |
| delta | +24,932 (+57.0%) | +29,296 (+58.6%) | | +12.7% | -11.3% | |

Generated by `results/area_table.py` from the OpenROAD logs (period = 10 ns
minus the post-repair worst slack; path stages count combinational cells
between the launching and capturing flops). Placed area 187,770 and 297,737
um^2, utilisation 52% in both configurations.

Three things follow.

- **Synthesis tracks placement.** The area overhead is 57% at synthesis
  and 58.6% after placement with buffering and resizing. The 14% absolute
  growth from synthesis to placement is the same in both configurations.
  The synthesis-only attribution table above can be read as placed area to
  within two points.
- **The extension costs 11 to 13% of clock frequency** in this flow. Both
  critical paths start at the EX-stage operator register, run through the
  ALU adder's carry chain (the maj3 cells), the result forwarding mux, and
  end at a multiplier operand register in EX; the Xpulp path ends at the
  dot-product operand register and is 12 stages longer, because the
  forwarding network has one more source and the operand mux is wider.
  This is a forwarding-path cost, not a multiplier cost.
- **Wall-clock speedups are the cycle speedups divided by 1.13.** The full
  extension's 2.5x / 4.3x / 5.4x in cycles against -O3 become 2.2x / 3.8x /
  4.8x in time on this core (2.5x / 3.6x / 5.4x against the hand baselines
  become 2.2x / 3.2x / 4.8x) if the two configurations are each clocked at their
  own limit. Every speedup elsewhere in this document is a cycle ratio;
  this is the correction.

Caveats: one PDK and one flow; pre-CTS and pre-route, so absolute periods
will move after clock tree and routing (ORFS results for cores of this
size at sky130hd land in the same 10 to 16 ns range); `repair_timing` did
not close at 10 ns in either configuration, so the minimum period is read
from residual slack rather than found by search; register-to-register
paths only, the I/O paths depend on the system around the core.

## Decomposition: datapath versus control and addressing

Xpulp is three separable things on this core: the SIMD dot-product
datapath (cv.dotsp.b), hardware loops, and post-increment loads and
stores. The kernels above use only the first. To attribute the speedup
and the area, six hand-written kernels form a 2x3 grid: scalar, SIMD with
unaligned loads, SIMD with aligned loads, each with RV32IMC control
(addi + bne, one base pointer) and with Xpulp control (one hardware loop
per output row, post-increment load and store, no pointer arithmetic). The
arithmetic and the requantisation are identical within each pair. Loads
are scheduled ahead of their consumers, so no kernel has a load-use stall
except the aligned pair's shift-and-merge path. All six are verified for
checksum and, for the Xpulp variants, for hardware-loop legality
(`harness/check_hwloop.py`: aligned start and end, no compressed
instructions, no branches, lpend on an instruction boundary) and for being
illegal on the RV32IMC build.

Encodings used (`sw/xpulp.h`): cv.setup via `.insn i 0x2b, 0x4, x14, cnt,
words`; cv.lb / cv.lw post-increment via `.insn i 0x0b`; cv.sb
post-increment via `.insn s 0x2b`. GAS does not accept a label difference
as the `.insn` immediate, so the loop length is a constant checked after
the build.

| shape | kernel | cycles (pad 0) | cycles (pad 1) | instructions | fetches | data reads | taken branches | load-use stalls | split-load accesses | model residual | checksum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | scalar asm, RV32IMC control | 53,889 | 53,673 | 52,507 | 44,894 | 6,824 | 463 | 0 | 0 | +0.4% | 64747 |
|  | scalar asm, Xpulp control | 52,562 | 52,330 | 51,956 | 50,727 | 7,048 | 127 | 0 | 0 | +0.4% | 64747 |
|  | SIMD unaligned asm, RV32IMC control | 40,245 | 41,590 | 33,640 | 33,476 | 8,136 | 1,567 | 0 | 3,360 | +0.3% | 64747 |
|  | SIMD unaligned asm, Xpulp control | 32,519 | 32,638 | 29,049 | 29,109 | 8,136 | 111 | 0 | 3,360 | -0.3% | 64747 |
|  | SIMD aligned asm, RV32IMC control | 39,078 | 39,407 | 37,235 | 34,557 | 3,096 | 351 | 672 | 336 | +0.3% | 64747 |
|  | SIMD aligned asm, Xpulp control | 37,840 | 37,735 | 36,228 | 35,990 | 3,096 | 127 | 672 | 336 | +0.4% | 64747 |
| 16x16x16 | scalar asm, RV32IMC control | 107,335 | 107,767 | 105,000 | 89,141 | 13,632 | 927 | 0 | 0 | +0.4% | 64114 |
|  | scalar asm, Xpulp control | 104,648 | 105,112 | 103,673 | 101,236 | 14,080 | 255 | 0 | 0 | +0.4% | 64114 |
|  | SIMD unaligned asm, RV32IMC control | 80,454 | 83,173 | 67,255 | 66,916 | 16,272 | 3,135 | 0 | 6,720 | +0.3% | 64114 |
|  | SIMD unaligned asm, Xpulp control | 65,030 | 65,239 | 57,848 | 58,181 | 16,272 | 223 | 0 | 6,720 | +0.0% | 64114 |
|  | SIMD aligned asm, RV32IMC control | 78,151 | 78,792 | 74,458 | 69,109 | 6,192 | 703 | 1,344 | 672 | +0.3% | 64114 |
|  | SIMD aligned asm, Xpulp control | 75,657 | 75,448 | 72,443 | 71,975 | 6,192 | 255 | 1,344 | 672 | +0.3% | 64114 |
| 8x32x32 | scalar asm, RV32IMC control | 230,366 | 232,751 | 225,545 | 196,716 | 23,136 | 2,399 | 0 | -1 | +0.0% | 62900 |
|  | scalar asm, Xpulp control | 220,055 | 220,288 | 219,329 | 219,524 | 23,385 | 239 | 240 | 0 | +0.0% | 62900 |
|  | SIMD unaligned asm, RV32IMC control | 189,622 | 182,423 | 152,184 | 152,140 | 37,512 | 7,199 | 0 | 15,840 | +0.0% | 62900 |
|  | SIMD unaligned asm, Xpulp control | 147,391 | 147,144 | 130,825 | 131,268 | 37,512 | 239 | 0 | 15,840 | -0.2% | 62900 |
|  | SIMD aligned asm, RV32IMC control | 174,320 | 176,255 | 168,521 | 157,237 | 12,312 | 1,695 | 1,440 | 720 | +0.1% | 62900 |
|  | SIMD aligned asm, Xpulp control | 166,648 | 167,121 | 163,714 | 162,997 | 12,312 | 255 | 1,440 | 720 | +0.2% | 62900 |
| 32x8x8 | scalar asm, RV32IMC control | 38,754 | 39,137 | 37,990 | 32,545 | 4,928 | 383 | 0 | 0 | -0.0% | 65171 |
|  | scalar asm, Xpulp control | 38,370 | 38,593 | 37,991 | 37,793 | 5,216 | 191 | 192 | 0 | -0.5% | 65171 |
|  | SIMD unaligned asm, RV32IMC control | 30,403 | 31,492 | 25,767 | 25,441 | 6,048 | 1,151 | 0 | 2,304 | +0.1% | 65171 |
|  | SIMD unaligned asm, Xpulp control | 25,220 | 25,381 | 22,504 | 22,658 | 6,048 | 191 | 0 | 2,304 | -0.0% | 65171 |
|  | SIMD aligned asm, RV32IMC control | 31,237 | 31,366 | 28,714 | 26,468 | 3,168 | 255 | 1,152 | 576 | +0.9% | 65171 |
|  | SIMD aligned asm, Xpulp control | 30,821 | 30,982 | 28,330 | 27,588 | 3,168 | 255 | 1,152 | 576 | +0.8% | 65171 |

Speedups, better alignment per kernel, all relative to the hand-written
scalar kernel with RV32IMC control:

| shape | control only (scalar) | datapath only (unaligned) | datapath only (aligned) | both (unaligned) | both (aligned) | control gain on top of SIMD (unaligned) | control gain on top of SIMD (aligned) |
|---|---|---|---|---|---|---|---|
| 8x16x16 | 1.03x | 1.33x | 1.37x | 1.65x | 1.42x | 1.24x | 1.04x |
| 16x16x16 | 1.03x | 1.33x | 1.37x | 1.65x | 1.42x | 1.24x | 1.04x |
| 8x32x32 | 1.05x | 1.26x | 1.32x | 1.57x | 1.38x | 1.24x | 1.05x |
| 32x8x8 | 1.01x | 1.27x | 1.24x | 1.54x | 1.26x | 1.21x | 1.01x |

Instruction-count ratios for the same cells: control alone 1.00 to 1.03;
datapath alone 1.47 to 1.56 (unaligned) and 1.32 to 1.41 (aligned); both
1.69 to 1.82 (unaligned) and 1.34 to 1.44 (aligned).

What the grid says:

- **Control and addressing on their own are worth 1 to 5%** on the scalar
  kernel. A 3-pixel unroll already amortises the loop overhead, so a
  hardware loop and post-increment addressing remove about one instruction
  per pixel. The Xpulp scalar kernel also fetches 13% more instruction
  words because hardware-loop bodies may not contain compressed
  instructions; at zero wait states that is free, on a fetch-limited bus it
  would not be.
- **The datapath alone is worth 1.26 to 1.37x**, in line with the
  compiler-generated kernels once their saturation branches were
  equalised.
- **Control on top of the unaligned SIMD kernel is worth 1.21 to 1.24x**,
  far more than on the scalar kernel, because that loop body is 18
  instructions per pixel and the removed addi/addi/bne plus the 2-cycle
  taken-branch penalty were a fifth of it. On the aligned kernel, whose
  body covers four pixels, control is worth 1 to 5% again.
- **The fastest kernel is unaligned SIMD with Xpulp control**: 32,519
  cycles at 8x16x16, 1.65x over the hand scalar and 2.13x over the -O2 C
  baseline the project started from. It beats the aligned variant, which
  the earlier results had as the better one; the shift-and-merge
  instructions cost more than the split loads they avoid once the loop
  overhead is gone.
- **Split loads are 10% of the fastest kernel's cycles.** With control
  overhead and load-use stalls removed, the gap between its 1.81
  instruction ratio and its 1.65 cycle ratio is entirely the 3,360 extra
  bus accesses. Operand supply is not the first-order story, but in the
  best kernel it is now the largest remaining one.

### Decomposition under data-port latency

`harness/sweep.sh` with the six hand-written kernels, wait states on the
data port only, instruction port zero-wait:

| shape | kernel | w0 | w1 | w2 | w3 | reads + writes | max error of cycles(0) + w x accesses |
|---|---|---|---|---|---|---|---|
| 8x16x16 | scalar, RV32IMC ctrl | 53,889 | 62,300 | 70,711 | 79,122 | 8,410 | 3 cycles |
|  | scalar, Xpulp ctrl | 52,562 | 61,429 | 70,304 | 79,179 | 8,874 | 7 cycles |
|  | SIMD unaligned, RV32IMC ctrl | 40,245 | 49,950 | 59,655 | 69,360 | 9,704 | 3 cycles |
|  | SIMD unaligned, Xpulp ctrl | 32,519 | 42,224 | 51,929 | 61,634 | 9,704 | 3 cycles |
|  | SIMD aligned, RV32IMC ctrl | 39,078 | 43,519 | 48,072 | 52,737 | 4,664 | 334 cycles |
|  | SIMD aligned, Xpulp ctrl | 37,840 | 42,281 | 46,834 | 51,499 | 4,664 | 334 cycles |
| 16x16x16 | scalar, RV32IMC ctrl | 107,335 | 124,137 | 140,939 | 157,741 | 16,801 | 3 cycles |
|  | scalar, Xpulp ctrl | 104,648 | 122,362 | 140,092 | 157,822 | 17,729 | 15 cycles |
|  | SIMD unaligned, RV32IMC ctrl | 80,454 | 99,863 | 119,272 | 138,681 | 19,408 | 3 cycles |
|  | SIMD unaligned, Xpulp ctrl | 65,030 | 84,439 | 103,848 | 123,257 | 19,408 | 3 cycles |
|  | SIMD aligned, RV32IMC ctrl | 78,151 | 87,032 | 96,137 | 105,466 | 9,328 | 670 cycles |
|  | SIMD aligned, Xpulp ctrl | 75,657 | 84,538 | 93,643 | 102,972 | 9,328 | 670 cycles |
| 8x32x32 | scalar, RV32IMC ctrl | 230,366 | 260,727 | 291,088 | 321,449 | 30,360 | 3 cycles |
|  | scalar, Xpulp ctrl | 220,055 | 250,674 | 281,293 | 311,912 | 30,618 | 3 cycles |
|  | SIMD unaligned, RV32IMC ctrl | 189,622 | 234,335 | 279,048 | 323,761 | 44,712 | 3 cycles |
|  | SIMD unaligned, Xpulp ctrl | 147,391 | 192,104 | 236,817 | 281,530 | 44,712 | 3 cycles |
|  | SIMD aligned, RV32IMC ctrl | 174,320 | 193,353 | 212,626 | 232,139 | 19,512 | 718 cycles |
|  | SIMD aligned, Xpulp ctrl | 166,648 | 185,681 | 204,954 | 224,467 | 19,512 | 718 cycles |
| 32x8x8 | scalar, RV32IMC ctrl | 38,754 | 44,867 | 50,980 | 57,093 | 6,112 | 3 cycles |
|  | scalar, Xpulp ctrl | 38,370 | 44,835 | 51,300 | 57,765 | 6,464 | 3 cycles |
|  | SIMD unaligned, RV32IMC ctrl | 30,403 | 37,604 | 44,805 | 52,006 | 7,200 | 3 cycles |
|  | SIMD unaligned, Xpulp ctrl | 25,220 | 32,421 | 39,622 | 46,823 | 7,200 | 3 cycles |
|  | SIMD aligned, RV32IMC ctrl | 31,237 | 35,174 | 39,303 | 43,624 | 4,320 | 574 cycles |
|  | SIMD aligned, Xpulp ctrl | 30,821 | 34,758 | 38,887 | 43,208 | 4,320 | 574 cycles |

On this core a data wait state is almost never overlapped with execution:
the identity cycles(w) = cycles(0) + w x (reads + writes) holds to within
3 cycles for the scalar and unaligned kernels over all wait states and
shapes, and to within one cycle per output row per wait state for the
aligned pair, whose C tail has one load the next instruction does not
consume. The latency dimension therefore adds almost no information beyond
the access counts already in the tables, which is why the wait-0 tables
carry the counts.

Two consequences. The control-and-addressing gain on the scalar kernel
vanishes with latency, because post-increment addressing issues a few
more loads per row; at three wait states the Xpulp scalar kernel is
level with or marginally behind the RV32IMC one. And the choice of
fastest SIMD kernel depends on latency. Aligned over unaligned, both with
Xpulp control (below 1.00 means aligned is faster):

| shape | w0 | w1 | w2 | w3 |
|---|---|---|---|---|
| 8x16x16 | 1.16 | 1.00 | 0.90 | 0.84 |
| 16x16x16 | 1.16 | 1.00 | 0.90 | 0.84 |
| 8x32x32 | 1.13 | 0.97 | 0.87 | 0.80 |
| 32x8x8 | 1.22 | 1.07 | 0.98 | 0.92 |

The unaligned kernel wins at zero wait states, the two are level at one,
and the aligned kernel wins from two. This is the crossover the earlier
RESULTS.md reported under GCC 13.2 and then retired as compiler
dependent; measured with hand-written kernels and data-only latency, it
is real, and its position follows directly from the access counts: the
unaligned kernel issues 8,136 reads to the aligned kernel's 3,096 at
8x16x16, so each wait state costs it 5,040 more cycles.

Paired with the area attribution: the dot-product multiplier (+12.1 kGE,
28% of the base core) buys 1.26 to 1.37x; hardware-loop registers, controller and
decoder (+4.2 kGE, 10%) buy 1 to 5% on a well-unrolled scalar loop and
21 to 24% on a short SIMD loop; the SIMD ALU (+2.7 kGE) carries cv.clip,
measured in the saturation section below at 1.2 to 1.6x on top of both.
The bit-manipulation and other decode paths are unused by every kernel.

## Pointwise 1x1 convolution

The second kernel of a depthwise-separable block. Channel-last layout,
`input[P][CI]`, `weight[CO][CI]`, `output[P][CO]`; each output is a
CI-long dot product with the shared requantisation. Unlike the 3x3
depthwise kernel, every SIMD word load is aligned and all four lanes carry
data, and the CI activations of a pixel are reused across all CO outputs.
Shapes are CI x CO x H x W; MACs are 16,384, 16,384, 32,768 and 65,536.
Checksums were reproduced by an independent Python model; no output
saturates. Kernels (`sw/pwconv*.c`, hand-written bodies generated by
`sw/gen_pwconv_asm.py`): plain C at -O2 and -O3; C with cv.dotsp.b at -O2
and -O3; hand scalar asm holding the pixel's activations in registers,
with RV32IMC and with Xpulp control; hand SIMD asm holding the pixel's
activation words in registers and accumulating with cv.sdotsp.b, with
both controls.

| shape (CIxCOxHxW) | kernel | cycles (pad 0) | cycles (pad 1) | cycles/MAC | instructions | data reads | taken branches | load-use stalls | model residual | checksum |
|---|---|---|---|---|---|---|---|---|---|---|
| 16x16x8x8 | scalar C, -O2 | 164,227 | 179,650 | 10.02 | 131,461 | 32,768 | 16,383 | 0 | +0.0% | 64922 |
|  | scalar C, -O3 | 65,857 | 64,834 | 3.96 | 62,918 | 17,408 | 1,023 | 2,048 | -1.7% | 64922 |
|  | SIMD C, -O2 | 60,740 | 63,812 | 3.71 | 48,454 | 8,192 | 4,095 | 4,096 | +0.0% | 64922 |
|  | SIMD C, -O3 | 31,298 | 31,361 | 1.91 | 25,157 | 4,352 | 1,023 | 4,096 | -0.0% | 64922 |
|  | scalar asm, RV32IMC ctrl | 64,836 | 65,796 | 3.96 | 62,790 | 17,408 | 1,023 | 0 | +0.0% | 64922 |
|  | scalar asm, Xpulp ctrl | 59,973 | 59,909 | 3.66 | 59,847 | 17,408 | 63 | 0 | +0.0% | 64922 |
|  | SIMD asm, RV32IMC ctrl | 24,132 | 25,092 | 1.47 | 22,086 | 4,352 | 1,023 | 0 | +0.0% | 64922 |
|  | SIMD asm, Xpulp ctrl | 19,206 | 19,270 | 1.17 | 19,143 | 4,352 | 63 | 0 | -0.3% | 64922 |
| 8x8x16x16 | scalar C, -O2 | 196,100 | 181,764 | 11.09 | 148,998 | 32,768 | 16,383 | 0 | +0.0% | 64321 |
|  | scalar C, -O3 | 79,001 | 79,256 | 4.82 | 67,709 | 15,681 | 255 | 10,782 | +0.0% | 64321 |
|  | SIMD C, -O2 | 46,853 | 47,108 | 2.86 | 38,664 | 4,608 | 2,047 | 4,096 | -0.0% | 64321 |
|  | SIMD C, -O3 | 28,949 | 28,949 | 1.77 | 27,927 | 528 | 255 | 512 | +0.0% | 64321 |
|  | scalar asm, RV32IMC ctrl | 81,157 | 82,949 | 4.95 | 77,064 | 18,432 | 2,047 | 0 | -0.0% | 64321 |
|  | scalar asm, Xpulp ctrl | 71,941 | 71,685 | 4.38 | 71,176 | 18,432 | 255 | 0 | +0.4% | 64321 |
|  | SIMD asm, RV32IMC ctrl | 42,501 | 40,709 | 2.48 | 36,616 | 4,608 | 2,047 | 0 | -0.0% | 64321 |
|  | SIMD asm, Xpulp ctrl | 31,237 | 31,493 | 1.91 | 30,728 | 4,608 | 255 | 0 | -0.0% | 64321 |
| 16x32x8x8 | scalar C, -O2 | 328,068 | 358,851 | 10.01 | 262,536 | 65,536 | 32,767 | 0 | -0.0% | 64783 |
|  | scalar C, -O3 | 128,323 | 130,370 | 3.92 | 124,230 | 33,792 | 2,047 | 8,192 | -4.7% | 64783 |
|  | SIMD C, -O2 | 121,157 | 127,301 | 3.70 | 96,585 | 16,384 | 8,191 | 8,192 | -0.0% | 64783 |
|  | SIMD C, -O3 | 62,082 | 62,019 | 1.89 | 49,734 | 8,448 | 2,047 | 8,192 | -0.0% | 64783 |
|  | scalar asm, RV32IMC ctrl | 130,307 | 128,323 | 3.92 | 124,233 | 33,793 | 2,047 | 0 | -0.0% | 64783 |
|  | scalar asm, Xpulp ctrl | 118,339 | 118,275 | 3.61 | 118,217 | 33,793 | 63 | 0 | -0.0% | 64783 |
|  | SIMD asm, RV32IMC ctrl | 49,669 | 47,685 | 1.46 | 43,592 | 8,448 | 2,047 | 0 | -0.0% | 64783 |
|  | SIMD asm, Xpulp ctrl | 37,700 | 37,636 | 1.15 | 37,512 | 8,448 | 63 | 0 | +0.2% | 64783 |
| 16x16x16x16 | scalar C, -O2 | 656,901 | 718,341 | 10.02 | 525,830 | 131,072 | 65,535 | 0 | +0.0% | 63819 |
|  | scalar C, -O3 | 268,292 | 271,877 | 4.09 | 251,654 | 69,888 | 4,095 | 8,192 | +0.1% | 63819 |
|  | SIMD C, -O2 | 255,239 | 242,951 | 3.71 | 193,801 | 32,768 | 16,383 | 16,384 | +0.0% | 63819 |
|  | SIMD C, -O3 | 125,442 | 125,187 | 1.91 | 100,613 | 17,408 | 4,095 | 16,384 | +0.0% | 63819 |
|  | scalar asm, RV32IMC ctrl | 259,592 | 263,432 | 3.96 | 251,402 | 69,889 | 4,095 | 0 | +0.0% | 63819 |
|  | scalar asm, Xpulp ctrl | 240,136 | 239,880 | 3.66 | 239,626 | 69,888 | 255 | 0 | +0.0% | 63819 |
|  | SIMD asm, RV32IMC ctrl | 100,359 | 96,519 | 1.47 | 88,328 | 17,408 | 4,095 | 0 | +0.0% | 63819 |
|  | SIMD asm, Xpulp ctrl | 76,807 | 77,063 | 1.17 | 76,552 | 17,408 | 255 | 0 | -0.3% | 63819 |

| shape | -O2 / -O3 | -O3 / asm | SIMD asm (Xpulp ctrl) vs scalar -O3 | vs scalar asm | instr ratio vs asm | datapath only | control only (scalar) | control on top of SIMD |
|---|---|---|---|---|---|---|---|---|
| 16x16x8x8 | 2.53x | 1.00x | 3.38x | 3.38x | 3.28 | 2.69x | 1.08x | 1.26x |
| 8x8x16x16 | 2.30x | 0.97x | 2.53x | 2.60x | 2.51 | 1.99x | 1.13x | 1.30x |
| 16x32x8x8 | 2.56x | 1.00x | 3.41x | 3.41x | 3.31 | 2.69x | 1.08x | 1.27x |
| 16x16x16x16 | 2.45x | 1.03x | 3.49x | 3.38x | 3.28 | 2.69x | 1.08x | 1.26x |

- **The extension is worth 3.4x here against 1.4x on depthwise**, and the
  cycle speedup again equals the instruction ratio (3.28 to 3.31 against
  3.38 to 3.49 in cycles, the small excess being the scalar kernel's own
  taken branches). Same core, same multiplier, same area. Four lanes
  instead of three, aligned loads instead of split ones, and one weight
  load per four MACs instead of one activation load per three, together
  change the datapath's own contribution from 1.3x to 2.7x at CI = 16.
- **Control and addressing are worth 1.26 to 1.30x on top of the SIMD
  kernel** and 8 to 13% on the scalar one, the same pattern as depthwise:
  the shorter the loop body, the more a hardware loop and post-increment
  addressing are worth.
- **-O2 to -O3 is worth 2.3 to 2.6x on the scalar C kernel.** At -O2 GCC
  reloads the activation inside the channel loop and takes a branch per
  element; at -O3 it vectorises the reduction and matches the hand asm to
  within 3%. A pointwise speedup quoted against -O2 C would be inflated by
  a factor of 2.5 before the hardware is involved.
- **Code alignment moves the -O2 scalar kernel by 9.4%**, one cycle per
  taken branch at one branch per output element, the largest alignment
  effect measured in this study. Hand kernels with hardware loops move by
  under 1%.
- The cycle model holds to 0.4% on every hand-written kernel; the
  compiler-generated -O3 kernels deviate by up to 4.7%, which has not been
  chased.
- Best case: 1.15 cycles per MAC at CI = 16, against 2.30 for the best
  depthwise kernel.

## Depthwise 5x5 convolution

Same layout, data and checksum scheme as the 3x3 kernels, K = 5
(`sw/dw_common.h`). Kernels: plain C in the dwconv_opt.c style
(`sw/dwconv5.c`); hand scalar asm (`sw/dwconv5_asm.c`, generated by
`sw/gen_dwconv5_asm.py`) using row-wise sliding accumulation, since 25
weights plus a 25-byte window do not fit the register file: per output row,
each of the five kernel rows is swept with its five weights in registers
and a 5-wide sliding window, the first row storing into an int32
accumulator row and the other four accumulating, and the row is
requantised at the end; hand SIMD asm with unaligned loads
(`sw/dwconv5_simd_asm.c`): per pixel and kernel row two word loads at ox
and ox+4 carry taps 0..3 and tap 4, ten loads issued before one cv.dotsp.b
and nine accumulating cv.sdotsp.b. Five of eight lanes carry data. Both
hand kernels in both control variants. Checksums match the independent
model; no output saturates.

| shape | kernel | cycles (pad 0) | cycles (pad 1) | cycles/MAC | instructions | data reads | data writes | taken branches | load-use stalls | split-load accesses | model residual | checksum |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | scalar C, -O2 | 338,613 | 320,373 | 11.12 | 257,591 | 57,800 | 1,352 | 28,991 | 0 | 0 | +1.5% | 64862 |
|  | scalar C, -O3 | 156,762 | 156,570 | 5.44 | 139,793 | 41,904 | 4,376 | 1,343 | 14,088 | 0 | +0.0% | 64862 |
|  | scalar asm, RV32IMC ctrl | 162,501 | 157,421 | 5.47 | 137,935 | 15,840 | 6,912 | 6,719 | 5,760 | 0 | +0.2% | 64862 |
|  | scalar asm, Xpulp ctrl | 123,431 | 123,615 | 4.29 | 116,617 | 15,840 | 6,912 | 383 | 5,760 | 0 | +0.2% | 64862 |
|  | SIMD unaligned asm, RV32IMC ctrl | 49,828 | 49,923 | 1.73 | 38,886 | 20,384 | 1,176 | 1,151 | 0 | 8,640 | +0.0% | 64862 |
|  | SIMD unaligned asm, Xpulp ctrl | 44,563 | 44,460 | 1.54 | 35,727 | 20,480 | 1,184 | 95 | 0 | 8,640 | -0.0% | 64862 |
| 16x16x16 | scalar C, -O2 | 677,203 | 640,723 | 11.12 | 515,159 | 115,600 | 2,704 | 57,983 | 0 | 0 | +1.5% | 64854 |
|  | scalar C, -O3 | 313,160 | 313,544 | 5.44 | 279,594 | 83,808 | 8,752 | 2,687 | 28,192 | 0 | +0.0% | 64854 |
|  | scalar asm, RV32IMC ctrl | 314,838 | 324,998 | 5.47 | 275,863 | 31,680 | 13,824 | 13,439 | 11,520 | 0 | +0.2% | 64854 |
|  | scalar asm, Xpulp ctrl | 247,224 | 246,856 | 4.29 | 233,417 | 31,680 | 13,824 | 767 | 11,520 | 0 | +0.2% | 64854 |
|  | SIMD unaligned asm, RV32IMC ctrl | 99,604 | 99,795 | 1.73 | 77,717 | 40,752 | 2,336 | 2,303 | 0 | 17,280 | +0.0% | 64854 |
|  | SIMD unaligned asm, Xpulp ctrl | 88,884 | 89,061 | 1.54 | 71,206 | 40,944 | 2,352 | 191 | 0 | 17,280 | +0.0% | 64854 |
| 8x32x32 | scalar C, -O2 | 1,734,262 | 1,834,422 | 11.06 | 1,394,999 | 313,800 | 6,472 | 156,991 | 0 | 0 | +1.5% | 62512 |
|  | scalar C, -O3 | 831,750 | 831,558 | 5.30 | 742,973 | 219,056 | 20,376 | 6,463 | 75,656 | 0 | +0.0% | 62512 |
|  | scalar asm, RV32IMC ctrl | 835,159 | 853,759 | 5.33 | 723,167 | 72,816 | 37,641 | 37,183 | 31,360 | 0 | +0.8% | 62512 |
|  | scalar asm, Xpulp ctrl | 642,959 | 643,399 | 4.10 | 609,808 | 72,800 | 37,632 | 895 | 31,360 | 0 | +0.0% | 62512 |
|  | SIMD unaligned asm, RV32IMC ctrl | 267,815 | 268,038 | 1.71 | 208,232 | 109,985 | 6,297 | 6,271 | 0 | 47,040 | +0.0% | 62512 |
|  | SIMD unaligned asm, Xpulp ctrl | 237,592 | 237,375 | 1.51 | 190,105 | 110,217 | 6,305 | 223 | 0 | 47,040 | +0.0% | 62512 |
| 32x8x8 | scalar C, -O2 | 149,413 | 156,837 | 11.67 | 119,462 | 26,400 | 1,312 | 13,567 | 0 | 0 | +1.9% | 65080 |
|  | scalar C, -O3 | 77,289 | 77,961 | 6.04 | 69,864 | 21,440 | 3,808 | 1,279 | 4,768 | 0 | +0.1% | 65080 |
|  | scalar asm, RV32IMC ctrl | 79,557 | 77,925 | 6.09 | 69,351 | 10,880 | 3,072 | 2,815 | 2,560 | 0 | +0.5% | 65080 |
|  | scalar asm, Xpulp ctrl | 62,984 | 63,208 | 4.92 | 59,402 | 10,881 | 3,072 | 511 | 2,560 | 0 | +0.0% | 65080 |
|  | SIMD unaligned asm, RV32IMC ctrl | 24,837 | 24,772 | 1.94 | 19,879 | 9,985 | 640 | 511 | 0 | 3,840 | +0.1% | 65080 |
|  | SIMD unaligned asm, Xpulp ctrl | 22,597 | 22,438 | 1.75 | 18,472 | 9,985 | 640 | 127 | 0 | 3,840 | +0.0% | 65080 |

| shape | -O2 / -O3 | -O3 / asm | SIMD (Xpulp ctrl) vs scalar -O3 | vs scalar asm | instr ratio vs asm | datapath only | control only (scalar) | control on top of SIMD | split-load share of best |
|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | 2.05x | 0.99x | 3.52x | 3.54x | 3.87 | 3.16x | 1.28x | 1.12x | 19.4% |
| 16x16x16 | 2.05x | 0.99x | 3.52x | 3.54x | 3.87 | 3.16x | 1.28x | 1.12x | 19.4% |
| 8x32x32 | 2.09x | 1.00x | 3.50x | 3.52x | 3.81 | 3.12x | 1.30x | 1.13x | 19.8% |
| 32x8x8 | 1.93x | 0.99x | 3.44x | 3.47x | 3.78 | 3.15x | 1.24x | 1.10x | 17.1% |

- **The extension is worth 3.5x on 5x5**, against 1.4x on 3x3, with the
  same multiplier. Two reasons, and the counters separate them. The
  datapath alone is 3.2x because ten word loads feed 25 MACs (0.41 loads
  per MAC against 0.34 for 3x3, but with 2.5x more MACs per load-dot pair
  the instruction count per MAC halves). And the scalar baseline is weak
  at 5.4 cycles per MAC against 3.9 for 3x3, because 25 weights plus the
  window exceed the register file and the accumulator has to live in
  memory: 6,912 data writes against 1,586 for the 3x3 hand kernel. That is
  an operand-supply limit in the architecturally-visible-storage sense,
  on the scalar side.
- **The hand scalar kernel matches -O3 to within 1%.** GCC's -O3 code
  takes 14,088 load-use stalls but issues fewer stores; the hand kernel
  avoids the stalls and pays for accumulator traffic. An earlier version
  zeroed the accumulator row with a loop that GCC turned into a memset
  call at one shape; the fix, a store-only first kernel row, is what is
  measured here.
- **Split loads are 19 to 20% of the best kernel's cycles**, the largest
  operand-supply share in this study. The instruction ratio over the hand
  scalar is 3.87; the cycle ratio is 3.54; the entire gap is 8,640 extra
  bus accesses. With hardware loops removing the control overhead, split
  loads are the dominant remaining cost of this kernel.
- **Control on top of SIMD is 1.10 to 1.13x**, less than for 3x3 (1.24x),
  because the 5x5 body is 30 instructions per pixel rather than 18; on
  the scalar kernel it is 1.24 to 1.30x because the row-sweep body is 20.
- Best case: 1.51 to 1.54 cycles per MAC.

### Output-stationary scalar baseline

The row-wise hand kernel above matched -O3 within 1%, which a reviewer
rightly read as evidence against a gross deficiency only. The other loop
order, `sw/dwconv5_os_asm.c`, keeps the accumulator in a register for the
whole output pixel and reloads the five weights of each kernel row (five
`lb`) beside the five input bytes: 50 loads, 25 mul, 24 add, requantise,
store, one taken branch per output, no accumulator traffic and no
load-use stall. It exists in the same four scalar cells as the other
hand kernels (RV32IMC / Xpulp control, branch-free / clip) and matches
every checksum. Generated by `results/dw5_os_model.py` from
`results/wait0_dw5os_pad{0,1}.csv`:

| shape | kernel | cycles (pad 0) | cycles (pad 1) | cycles/MAC | instructions per output | data reads | data writes | taken branches | load-use stalls | model residual | checksum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | scalar C, -O3 | 156,762 | 156,570 | 5.44 | 121.3 | 41,904 | 4,376 | 1,343 | 14,088 | +0.0% | 64862 |
|  | row-wise asm, RV32IMC ctrl | 162,501 | 157,421 | 5.47 | 119.7 | 15,840 | 6,912 | 6,719 | 5,760 | +0.0% | 64862 |
|  | row-wise asm, Xpulp ctrl | 123,431 | 123,615 | 4.29 | 101.2 | 15,840 | 6,912 | 383 | 5,760 | +0.2% | 64862 |
|  | output-stationary asm, RV32IMC ctrl | 131,675 | 132,819 | 4.57 | 112.3 | 57,600 | 1,152 | 1,151 | 0 | -0.0% | 64862 |
|  | output-stationary asm, Xpulp ctrl | 127,454 | 127,358 | 4.42 | 110.4 | 57,600 | 1,152 | 95 | 0 | +0.1% | 64862 |
|  | output-stationary asm, RV32IMC ctrl, clip | 123,611 | 124,755 | 4.29 | 105.3 | 57,600 | 1,152 | 1,151 | 0 | -0.0% | 64862 |
|  | output-stationary asm, Xpulp ctrl, clip | 119,390 | 119,294 | 4.14 | 103.4 | 57,600 | 1,152 | 95 | 0 | +0.1% | 64862 |
|  | SIMD unaligned asm, Xpulp ctrl, clip (full Xpulp) | 36,499 | 36,396 | 1.26 | 24.0 | 20,480 | 1,184 | 95 | 0 | -0.0% | 64862 |
| 16x16x16 | scalar C, -O3 | 313,160 | 313,544 | 5.44 | 121.4 | 83,808 | 8,752 | 2,687 | 28,192 | +0.0% | 64854 |
|  | row-wise asm, RV32IMC ctrl | 314,838 | 324,998 | 5.47 | 119.7 | 31,680 | 13,824 | 13,439 | 11,520 | +0.0% | 64854 |
|  | row-wise asm, Xpulp ctrl | 247,224 | 246,856 | 4.29 | 101.3 | 31,680 | 13,824 | 767 | 11,520 | +0.2% | 64854 |
|  | output-stationary asm, RV32IMC ctrl | 265,618 | 263,330 | 4.57 | 112.3 | 115,200 | 2,304 | 2,303 | 0 | -0.0% | 64854 |
|  | output-stationary asm, Xpulp ctrl | 254,691 | 254,883 | 4.42 | 110.5 | 115,200 | 2,304 | 191 | 0 | +0.1% | 64854 |
|  | output-stationary asm, RV32IMC ctrl, clip | 249,490 | 247,202 | 4.29 | 105.3 | 115,200 | 2,304 | 2,303 | 0 | -0.0% | 64854 |
|  | output-stationary asm, Xpulp ctrl, clip | 238,563 | 238,755 | 4.14 | 103.5 | 115,200 | 2,304 | 191 | 0 | +0.1% | 64854 |
|  | SIMD unaligned asm, Xpulp ctrl, clip (full Xpulp) | 72,756 | 72,933 | 1.26 | 23.9 | 40,944 | 2,352 | 191 | 0 | +0.0% | 64854 |
| 8x32x32 | scalar C, -O3 | 831,750 | 831,558 | 5.30 | 118.5 | 219,056 | 20,376 | 6,463 | 75,656 | +0.0% | 62512 |
|  | row-wise asm, RV32IMC ctrl | 835,159 | 853,759 | 5.33 | 115.3 | 72,816 | 37,641 | 37,183 | 31,360 | +0.0% | 62512 |
|  | row-wise asm, Xpulp ctrl | 642,959 | 643,399 | 4.10 | 97.2 | 72,800 | 37,632 | 895 | 31,360 | +0.0% | 62512 |
|  | output-stationary asm, RV32IMC ctrl | 715,741 | 722,005 | 4.56 | 112.1 | 313,600 | 6,272 | 6,271 | 0 | +0.0% | 62512 |
|  | output-stationary asm, Xpulp ctrl | 691,551 | 691,327 | 4.41 | 110.2 | 313,600 | 6,272 | 223 | 0 | -0.0% | 62512 |
|  | output-stationary asm, RV32IMC ctrl, clip | 671,837 | 678,101 | 4.28 | 105.1 | 313,600 | 6,272 | 6,271 | 0 | +0.0% | 62512 |
|  | output-stationary asm, Xpulp ctrl, clip | 647,647 | 647,423 | 4.13 | 103.2 | 313,600 | 6,272 | 223 | 0 | -0.0% | 62512 |
|  | SIMD unaligned asm, Xpulp ctrl, clip (full Xpulp) | 193,688 | 193,471 | 1.23 | 23.3 | 110,217 | 6,305 | 223 | 0 | +0.0% | 62512 |
| 32x8x8 | scalar C, -O3 | 77,289 | 77,961 | 6.04 | 136.5 | 21,440 | 3,808 | 1,279 | 4,768 | +0.1% | 65080 |
|  | row-wise asm, RV32IMC ctrl | 79,557 | 77,925 | 6.09 | 135.5 | 10,880 | 3,072 | 2,815 | 2,560 | +0.0% | 65080 |
|  | row-wise asm, Xpulp ctrl | 62,984 | 63,208 | 4.92 | 116.0 | 10,881 | 3,072 | 511 | 2,560 | +0.0% | 65080 |
|  | output-stationary asm, RV32IMC ctrl | 59,206 | 59,494 | 4.63 | 113.5 | 25,600 | 512 | 511 | 0 | +0.0% | 65080 |
|  | output-stationary asm, Xpulp ctrl | 57,447 | 57,319 | 4.48 | 111.5 | 25,600 | 512 | 127 | 0 | -0.2% | 65080 |
|  | output-stationary asm, RV32IMC ctrl, clip | 55,622 | 55,910 | 4.35 | 106.5 | 25,600 | 512 | 511 | 0 | +0.0% | 65080 |
|  | output-stationary asm, Xpulp ctrl, clip | 53,863 | 53,735 | 4.20 | 104.5 | 25,600 | 512 | 127 | 0 | -0.2% | 65080 |
|  | SIMD unaligned asm, Xpulp ctrl, clip (full Xpulp) | 19,013 | 18,854 | 1.47 | 29.1 | 9,985 | 640 | 127 | 0 | +0.0% | 65080 |

| shape | output-stationary vs row-wise | vs -O3 | full Xpulp vs row-wise | vs output-stationary | vs -O3 | instr ratio vs output-stationary | control alone (output-stationary) | clip alone (output-stationary) | datapath alone vs output-stationary |
|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | 1.20x | 1.19x | 4.33x | 3.62x | 4.30x | 4.69 | 1.03x | 1.07x | 2.64x |
| 16x16x16 | 1.20x | 1.19x | 4.33x | 3.62x | 4.30x | 4.70 | 1.03x | 1.07x | 2.64x |
| 8x32x32 | 1.17x | 1.16x | 4.32x | 3.70x | 4.30x | 4.82 | 1.04x | 1.07x | 2.67x |
| 32x8x8 | 1.32x | 1.31x | 4.13x | 3.14x | 4.10x | 3.94 | 1.03x | 1.06x | 2.39x |

8x16x16: row-wise 157,421 cycles = 137,935 instructions + 13,438 taken-branch cycles + 5,760 load-use stalls (6,912 stores); output-stationary 131,675 = 129,375 + 2,302 + 0 (1,152 stores, 57,600 loads = 50 per output). Instructions per output 119.7 vs 112.3; cycles per output 136.7 vs 114.3.
checksum mismatches against the row-wise kernel: 0; max |model residual| over the output-stationary runs: 0.24%

The output-stationary kernel is 17 to 32% faster than the row-wise one and
16 to 31% faster than -O3, with fewer instructions per output (112 against
120) and, more to the point, 2,302 taken-branch cycles and no load-use
stalls where the row-wise kernel paid 13,438 and 5,760 for its accumulator
traffic. Two loads per MAC is the price of not holding 25 weights, and it
is cheaper than five branches per output on this core. It is the 5x5
scalar baseline in the cross-kernel summary, the clip section and the
paper; the extension's speedup over the best scalar code on 5x5 is 3.6x,
not 4.3x (which stands against -O3). The row-wise kernel's rows stay in
the tables above for the record.

## Cross-kernel summary

Headline shapes, better alignment, zero wait states:

| kernel | MACs | lanes used | scalar -O3 c/MAC | hand scalar c/MAC | SIMD + hw loop c/MAC | full Xpulp (+ clip) c/MAC | full Xpulp vs -O3 | vs hand scalar | instr ratio vs hand | datapath only | control on top of SIMD | clip on top of that | SIMD loads/MAC | split-load share of full |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3x3 depthwise, 8x16x16 | 14,112 | 3 of 4 | 3.86 | 3.80 | 2.30 | 1.53 | 2.53x | 2.49x | 2.91 | 1.33x | 1.24x | 1.51x | 0.34 | 15.6% |
| 5x5 depthwise, 8x16x16 | 28,800 | 5 of 8 | 5.44 | 4.57 | 1.54 | 1.26 | 4.30x | 3.62x | 4.69 | 2.64x | 1.12x | 1.22x | 0.41 | 23.7% |
| 1x1 pointwise, 16x16x8x8 | 16,384 | 4 of 4 | 3.96 | 3.96 | 1.17 | 0.73 | 5.39x | 5.39x | 5.24 | 2.69x | 1.26x | 1.60x | 0.27 | 0.0% |

Three kernels, one core, one 57% extension. The same silicon returns 2.5x
on 3x3 depthwise, 4.3x on 5x5 depthwise and 5.4x on 1x1 pointwise against
-O3 C once all of it is used (dot product, hardware loop, post-increment,
clip), and 2.5x, 3.6x and 5.4x against the best hand scalar kernels. In
every case the cycle model applied to both kernels reproduces the speedup
(2.47 / 3.62 / 5.36 predicted against 2.49 / 3.62 / 5.39 measured); the gap
to the bare instruction ratio is the split-load cost on the accelerated
side and the baseline's own taken branches, 2.2%, 1.7% and 3.2% of its
cycles, on the other. The variation comes from lane utilisation, from
the number of MACs each load feeds, and from whether the scalar baseline
fits its working set in the register file (the 5x5 scalar kernel pays two
loads per MAC against 0.5 for 3x3). A single speedup number for an
ISA extension on "the depthwise-separable block" would be wrong by a factor
of two depending on which half of the block it was measured on.

## Saturation: the clip instructions

Xpulp includes cv.clip and cv.clipu, one-instruction saturation to a
signed or unsigned power-of-two range. Every kernel above paid a nine
instruction (int8) or eight instruction (unsigned) branch-free sequence
for the same operation, between a third and a half of the short SIMD loop
bodies. `-DREQUANT_CLIP=1` replaces it with `srai` plus `cv.clip 8` (int8)
or `cv.clipu 9` (0..255): two instructions. Encodings from the spec
(R-type, opcode 0x2b, funct3 011, funct7 0x38 / 0x39, the range in the rs2
field), semantics verified on the core at the boundaries and illegal on
the RV32IMC build. Hardware-loop lengths follow RQ_N, so every clip build
passes the loop check; all 240 clip runs match their checksums, synthetic
and real.

Clip is an Xpulp feature like the others, so it is a third component in the
decomposition. The 5x5 scalar cells are the output-stationary kernel
(above); the row-wise kernel's clip runs are in `wait0_clip_dw5_pad{0,1}.csv`. Applied alone to the scalar kernel it measures saturation
cost; applied on top of SIMD and hardware loops it completes the extension.
Better alignment per kernel, zero wait states, cycles:

### 3x3 depthwise

| shape | scalar -O3 | scalar asm | + clip | + hw loop/post-inc | + both | SIMD asm | + clip | + hw loop/post-inc | + both (full Xpulp) | full Xpulp vs -O3 | vs scalar asm | instr ratio vs scalar asm | clip saves per output | model residual, full |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | 54,527 | 53,673 | 42,585 | 52,330 | 41,354 | 40,245 | 29,269 | 32,519 | 21,543 | 2.53x | 2.49x | 2.91 | 7.00 | -0.5% |
| 16x16x16 | 109,048 | 107,335 | 85,159 | 104,648 | 82,696 | 80,454 | 58,502 | 65,030 | 43,078 | 2.53x | 2.49x | 2.93 | 7.00 | +0.0% |
| 8x32x32 | 249,063 | 230,366 | 179,966 | 220,055 | 169,655 | 182,423 | 132,023 | 147,144 | 96,744 | 2.57x | 2.38x | 2.80 | 7.00 | -0.2% |
| 32x8x8 | 38,536 | 38,754 | 30,690 | 38,370 | 30,306 | 30,403 | 22,339 | 25,220 | 17,317 | 2.23x | 2.24x | 2.63 | 6.86 | +1.1% |

3x3 depthwise, 8x16x16, speedup over scalar asm (RV32IMC control, branch-free saturation); order-dependent values:

| component set | speedup over scalar asm |
|---|---|
| datapath (cv.dotsp.b) alone | 1.33x |
| control alone (scalar) | 1.03x |
| clip alone (scalar) | 1.26x |
| SIMD + control | 1.65x |
| SIMD + clip | 1.83x |
| control + clip (scalar) | 1.30x |
| SIMD + control + clip (full Xpulp) | 2.49x |
| cycles per MAC, full Xpulp | 1.53 |

3x3 depthwise, 8x16x16, the three features added first (to scalar asm), added last (on top of the other two), and the Shapley value over all 3! orders (product = full speedup):

| feature | added first | added last | Shapley |
|---|---|---|---|
| datapath | 1.33x | 1.92x | 1.58x |
| control | 1.03x | 1.36x | 1.16x |
| clip | 1.26x | 1.51x | 1.36x |
| product | | | 2.49x (measured 2.49x) |

3x3 depthwise, 8x16x16: measured speedup 2.49x; instruction ratio 2.91; instruction ratio with the split-load cost on the accelerated side only 2.45; cycle model applied to both sides 2.47; baseline non-instruction share 2.2% (926 taken-branch cycles, 0 load-use stalls, 0 split accesses, 128 residual); full-Xpulp split-load share 15.6%; activation words loaded 4,704 = 3.00 MACs per activation word (loads retired 4,776)

### 5x5 depthwise

| shape | scalar -O3 | scalar asm | + clip | + hw loop/post-inc | + both | SIMD asm | + clip | + hw loop/post-inc | + both (full Xpulp) | full Xpulp vs -O3 | vs scalar asm | instr ratio vs scalar asm | clip saves per output | model residual, full |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8x16x16 | 156,570 | 131,675 | 123,611 | 127,358 | 119,294 | 49,828 | 41,764 | 44,460 | 36,396 | 4.30x | 3.62x | 4.69 | 7.00 | -0.0% |
| 16x16x16 | 313,160 | 263,330 | 247,202 | 254,691 | 238,563 | 99,604 | 83,476 | 88,884 | 72,756 | 4.30x | 3.62x | 4.70 | 7.00 | +0.0% |
| 8x32x32 | 831,558 | 715,741 | 671,837 | 691,327 | 647,423 | 267,815 | 223,911 | 237,375 | 193,471 | 4.30x | 3.70x | 4.82 | 7.00 | +0.0% |
| 32x8x8 | 77,289 | 59,206 | 55,622 | 57,319 | 53,735 | 24,772 | 21,188 | 22,438 | 18,854 | 4.10x | 3.14x | 3.94 | 7.00 | +0.0% |

5x5 depthwise, 8x16x16, speedup over scalar asm (RV32IMC control, branch-free saturation); order-dependent values:

| component set | speedup over scalar asm |
|---|---|
| datapath (cv.dotsp.b) alone | 2.64x |
| control alone (scalar) | 1.03x |
| clip alone (scalar) | 1.07x |
| SIMD + control | 2.96x |
| SIMD + clip | 3.15x |
| control + clip (scalar) | 1.10x |
| SIMD + control + clip (full Xpulp) | 3.62x |
| cycles per MAC, full Xpulp | 1.26 |

5x5 depthwise, 8x16x16, the three features added first (to scalar asm), added last (on top of the other two), and the Shapley value over all 3! orders (product = full speedup):

| feature | added first | added last | Shapley |
|---|---|---|---|
| datapath | 2.64x | 3.28x | 2.93x |
| control | 1.03x | 1.15x | 1.09x |
| clip | 1.07x | 1.22x | 1.14x |
| product | | | 3.62x (measured 3.62x) |

5x5 depthwise, 8x16x16: measured speedup 3.62x; instruction ratio 4.69; instruction ratio with the split-load cost on the accelerated side only 3.57; cycle model applied to both sides 3.62; baseline non-instruction share 1.7% (2,302 taken-branch cycles, 0 load-use stalls, 0 split accesses, -2 residual); full-Xpulp split-load share 23.7%; activation words loaded 11,520 = 2.50 MACs per activation word (loads retired 11,840)

### 1x1 pointwise

| shape | scalar -O3 | scalar asm | + clip | + hw loop/post-inc | + both | SIMD asm | + clip | + hw loop/post-inc | + both (full Xpulp) | full Xpulp vs -O3 | vs scalar asm | instr ratio vs scalar asm | clip saves per output | model residual, full |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16x16x8x8 | 64,834 | 64,836 | 57,668 | 59,909 | 52,740 | 24,132 | 16,964 | 19,206 | 12,038 | 5.39x | 5.39x | 5.24 | 7.00 | -0.5% |
| 8x8x16x16 | 79,001 | 81,157 | 66,821 | 71,685 | 57,349 | 40,709 | 26,373 | 31,237 | 16,901 | 4.67x | 4.80x | 4.70 | 7.00 | -0.0% |
| 16x32x8x8 | 128,323 | 128,323 | 113,987 | 118,275 | 103,939 | 47,685 | 33,349 | 37,636 | 23,300 | 5.51x | 5.51x | 5.36 | 7.00 | -0.0% |
| 16x16x16x16 | 268,292 | 259,592 | 230,920 | 239,880 | 211,208 | 96,519 | 67,847 | 76,807 | 48,135 | 5.57x | 5.39x | 5.25 | 7.00 | -0.5% |

1x1 pointwise, 16x16x8x8, speedup over scalar asm (RV32IMC control, branch-free saturation); order-dependent values:

| component set | speedup over scalar asm |
|---|---|
| datapath (cv.dotsp.b) alone | 2.69x |
| control alone (scalar) | 1.08x |
| clip alone (scalar) | 1.12x |
| SIMD + control | 3.38x |
| SIMD + clip | 3.82x |
| control + clip (scalar) | 1.23x |
| SIMD + control + clip (full Xpulp) | 5.39x |
| cycles per MAC, full Xpulp | 0.73 |

1x1 pointwise, 16x16x8x8, the three features added first (to scalar asm), added last (on top of the other two), and the Shapley value over all 3! orders (product = full speedup):

| feature | added first | added last | Shapley |
|---|---|---|---|
| datapath | 2.69x | 4.38x | 3.37x |
| control | 1.08x | 1.41x | 1.21x |
| clip | 1.12x | 1.60x | 1.32x |
| product | | | 5.39x (measured 5.39x) |

1x1 pointwise, 16x16x8x8: measured speedup 5.39x; instruction ratio 5.24; instruction ratio with the split-load cost on the accelerated side only 5.24; cycle model applied to both sides 5.36; baseline non-instruction share 3.2% (2,046 taken-branch cycles, 0 load-use stalls, 0 split accesses, 0 residual); full-Xpulp split-load share 0.0%; activation words loaded 4,096 = 4.00 MACs per activation word (loads retired 4,352)

Clip saves exactly 7.00 cycles per output in every cell (6.86 at one 3x3
shape, where the removed instructions changed a branch target's alignment).
The five-term model residual on the full-Xpulp kernels is under 1.9%.

What changes:

- **The full extension is worth 2.5x, 4.3x and 5.4x** against -O3 on the
  three kernels, against 1.7x, 3.5x and 3.4x without clip, and 2.5x, 3.6x
  and 5.4x against the best hand scalar kernels. The instruction ratios over
  the hand kernels are 2.9, 4.7 and 5.2; the gap to the cycle ratios is split loads on the
  accelerated side, now 16% and 24% of the depthwise kernels' cycles because
  everything else got cheaper, and the baseline's own stalls on the other
  (2.2%, 1.7% and 3.2% of its cycles); the cycle model applied to both
  kernels gives 2.47, 3.62 and 5.36.
- **Clip is worth more than hardware loops on every kernel, in every
  view.** The value of a feature depends on when it is added. Added last,
  on top of the other two, clip is 1.51x (3x3), 1.22x (5x5) and 1.60x (1x1)
  against control's 1.36x, 1.15x and 1.41x; added first, to the scalar
  kernel, clip is 1.26x, 1.07x and 1.12x against control's 1.03x, 1.03x and
  1.08x. The Shapley value over all six orders (exact, since all eight cells
  of the grid are measured) is clip 1.36x, 1.14x and 1.32x against control
  1.16x, 1.09x and 1.21x. Against the row-wise 5x5 kernel, control had been
  worth 1.28x added first and ahead of clip by Shapley value (1.21x vs
  1.13x): that kernel took five taken branches per output, and the loop
  hardware's apparent value was the baseline's branches. The area
  comparison is a bound: clip lives in the SIMD ALU (+2.7 kGE, which
  also carries every other vector operation, so an upper bound), the loop
  hardware in hwloop_regs, controller and decoder (+4.2 kGE; +6.1 kGE with
  the ID stage), so clip costs at most 64% of the loop hardware.
- **The best kernel is now below one cycle per MAC**: 0.73 on pointwise,
  1.26 on 5x5, 1.53 on 3x3.
- The earlier sections' "fastest kernel" and "split-load share" numbers
  stand for the extension without clip and are superseded here.

## Hardware loops under instruction-fetch latency

Hardware-loop bodies may not contain compressed instructions, so the Xpulp
control variants are larger in code and fetch more words. At zero wait
states that costs nothing. Flash-based microcontrollers execute from
instruction memory with wait states while data sits in zero-wait SRAM, so
the opposite corner of the memory model matters too: instruction port
with 0 to 3 wait states, data port zero-wait, all kernels with clip
(`harness/sweep.sh` with `WAITS=0 IWAIT=n`).

| kernel | shape | RV32IMC ctrl, IWAIT 0 / 1 / 2 / 3 | Xpulp ctrl, IWAIT 0 / 1 / 2 / 3 | Xpulp / RV32IMC at IWAIT 0 | at IWAIT 1 | 2 | 3 | fetch words Xpulp / RV32IMC (8x16x16) |
|---|---|---|---|---|---|---|---|---|
| scalar | 8x16x16 | 43,025 / 69,866 / 104,799 / 139,732 | 41,586 / 79,740 / 119,610 / 159,480 | 0.97 | 1.14 | 1.14 | 1.14 | 1.14 |
| SIMD unaligned | 8x16x16 | 29,269 / 45,223 / 67,834 / 90,445 | 21,543 / 36,265 / 54,397 / 72,529 | 0.74 | 0.80 | 0.80 | 0.80 | 0.76 |
| SIMD aligned | 8x16x16 | 28,110 / 48,842 / 73,095 / 97,460 | 26,856 / 50,363 / 75,376 / 100,501 | 0.96 | 1.03 | 1.03 | 1.03 | 1.02 |
| scalar | 32x8x8 | 30,690 / 51,265 / 76,897 / 102,529 | 30,306 / 59,458 / 89,187 / 118,916 | 0.99 | 1.16 | 1.16 | 1.16 |  |
| SIMD unaligned | 32x8x8 | 23,428 / 36,996 / 55,494 / 73,992 | 17,317 / 29,190 / 43,785 / 58,380 | 0.74 | 0.79 | 0.79 | 0.79 |  |
| SIMD aligned | 32x8x8 | 23,173 / 38,151 / 56,939 / 75,919 | 22,757 / 39,622 / 59,145 / 78,860 | 0.98 | 1.04 | 1.04 | 1.04 |  |
| pointwise scalar | 16x16x8x8 | 57,668 / 98,692 / 148,038 / 197,384 | 52,740 / 105,221 / 157,832 / 210,443 | 0.91 | 1.07 | 1.07 | 1.07 |  |
| pointwise SIMD | 16x16x8x8 | 16,964 / 31,620 / 47,430 / 63,240 | 12,038 / 23,816 / 35,724 / 47,632 | 0.71 | 0.75 | 0.75 | 0.75 |  |

From one instruction-port wait state on, the core is fetch-bound and
cycles are proportional to instruction words fetched: the Xpulp / RV32IMC
ratios at IWAIT 1 to 3 are identical to two decimals and equal the
fetch-word ratios measured at zero wait. Hardware loops and post-increment
then *cost* 14 to 16% on the scalar kernel and 2 to 4% on the aligned SIMD
kernel, because the non-compressed body outweighs the removed instructions.
On the unaligned SIMD kernel, where control was a fifth of the body, they
still save 20 to 26%. The same holds on pointwise.

The decomposition's control term therefore has a sign that depends on the
instruction memory: +3 to +30% with zero-wait instruction memory, -16 to
+26% behind a flash with wait states. Compressed-instruction support inside
hardware-loop bodies, which CV32E40P excludes by specification, would
remove the penalty; a one-line constraint in the ISA document is a
first-order effect on fetch-limited systems.

## Real weights and activations

The synthetic LCG data never saturate. To test the kernels on the data they
are meant for, `sw/real/gen_real_data.py` runs quantised MobileNetV1
(mobilenet_v1_1.0_224_quant.tflite, 2018-08-02; top-1 class 653 on
grace_hopper.jpg, as expected) under the LiteRT interpreter with all
intermediate tensors preserved, and exports:

- depthwise 3x3: input activations and weights of
  MobilenetV1/Conv2d_3_depthwise (56x56x128, stride 1), cropped to the
  four measured shapes at the top-left corner and the first CH channels;
- pointwise 1x1: MobilenetV1/Conv2d_1_pointwise (112x112, 32 -> 64),
  cropped to the first CI = 16 input channels (the hand kernels are
  generated for CI in 8, 16), so each output is a partial sum.

The model is mobilenet_v1_1.0_224_quant: width multiplier 1.0, uint8
asymmetric. The measured shapes are crops of the model's tensors (the first
CH or CI channels, a top-left spatial window), not a smaller model.
Activations are post-ReLU6 with zero point 0 and are used as unsigned
bytes; weights have a per-layer zero point and become int8 by subtracting
it exactly (one weight per layer in the whole tensor falls outside int8
and is clipped; none in the crops the single-layer kernels use, one of 144
in the block's depthwise crop, 135 -> 127), so the kernels' inputs are the
model's own tensors. The real requantisation multiplier is within 3% of a power of
two for both layers (0.0605 vs 2^-4, 0.0304 vs 2^-5), so the kernels keep a
shift. Output = clamp(acc >> shift, 0, 255), which is ReLU6 in the
quantised domain. Rounding is truncation. Because the multiplier is a
power of two and the rounding truncates, the outputs are not bit-exact
model outputs; the checksums are verified against the generator's model of
the same arithmetic, and cycle counts do not depend on it (next
subsection).

This needs a second arithmetic mode, `-DREAL_DATA=1`: unsigned activation
loads, cv.dotusp.b / cv.sdotusp.b (unsigned x signed) in place of
cv.dotsp.b / cv.sdotsp.b (same encoding class, same cost), and an
eight-instruction branch-free clamp to 0..255 in place of the
nine-instruction symmetric saturation. Every kernel in this section runs in
that mode. Checksums are verified against the independent model in the
generator for all 96 runs.

Real-data statistics with the shift above:

| layer, shape | activations zero | outputs clamped to 0 | outputs at 255 | mean output | max weight |
|---|---|---|---|---|---|
| dw3 8x16x16 | 43% | 61% | 0.1% | 17.0 | 27 |
| dw3 16x16x16 | 40% | 57% | 0.5% | 23.7 | 53 |
| dw3 8x32x32 | 44% | 65% | 0.1% | 16.7 | 27 |
| dw3 32x8x8 | 30% | 53% | 2.3% | 32.0 | 53 |
| pw 16x16x8x8 | | 59% | 0.8% | 25.1 | 59 |
| pw 8x8x16x16 | | 40% | 0.0% | 23.7 | 33 |
| pw 16x32x8x8 | | 58% | 6.9% | 43.9 | 120 |
| pw 16x16x16x16 | | 57% | 0.7% | 28.1 | 59 |

Over half the outputs take the clamp path. With the branching
requantisation the project started with, that would have been a
data-dependent cost of several cycles per output.

### Data independence

The LCG data of the synthetic runs, converted to unsigned bytes, was pushed
through the identical REAL_DATA code path (`sw/real/syn_*.h`). Cycles for
real and synthetic data, same binary:

| shape | kernel | cycles, real data (pad 0 / pad 1) | cycles, synthetic data, same code | difference | checksum real / expected | checksum synthetic / expected |
|---|---|---|---|---|---|---|
| 8x16x16 | scalar C -O3 | 52,953 / 53,722 | 52,953 / 53,722 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 8x16x16 | scalar asm, RV32IMC ctrl | 52,324 / 52,108 | 52,324 / 52,108 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 8x16x16 | scalar asm, Xpulp ctrl | 50,765 / 50,997 | 50,765 / 50,997 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 8x16x16 | SIMD unaligned asm, RV32IMC ctrl | 40,024 / 38,679 | 40,024 / 38,679 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 8x16x16 | SIMD unaligned asm, Xpulp ctrl | 30,953 / 31,072 | 30,953 / 31,072 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 8x16x16 | SIMD aligned asm, RV32IMC ctrl | 37,632 / 37,721 | 37,632 / 37,721 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 8x16x16 | SIMD aligned asm, Xpulp ctrl | 36,281 / 36,162 | 36,281 / 36,162 | +0 / +0 | 26589 / 26589 ok | 9826 / 9826 ok |
| 16x16x16 | scalar C -O3 | 107,436 / 105,899 | 107,436 / 105,899 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 16x16x16 | scalar asm, RV32IMC ctrl | 104,219 / 104,651 | 104,219 / 104,651 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 16x16x16 | scalar asm, Xpulp ctrl | 101,996 / 101,532 | 101,996 / 101,532 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 16x16x16 | SIMD unaligned asm, RV32IMC ctrl | 80,039 / 77,320 | 80,039 / 77,320 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 16x16x16 | SIMD unaligned asm, Xpulp ctrl | 61,896 / 62,105 | 61,896 / 62,105 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 16x16x16 | SIMD aligned asm, RV32IMC ctrl | 75,241 / 75,434 | 75,241 / 75,434 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 16x16x16 | SIMD aligned asm, Xpulp ctrl | 72,314 / 72,523 | 72,314 / 72,523 | +0 / +0 | 8777 / 8777 ok | 9921 / 9921 ok |
| 8x32x32 | scalar C -O3 | 244,988 / 241,867 | 244,988 / 241,867 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 8x32x32 | scalar asm, RV32IMC ctrl | 223,140 / 225,539 | 223,140 / 225,539 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 8x32x32 | scalar asm, Xpulp ctrl | 213,085 / 212,852 | 213,085 / 212,852 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 8x32x32 | SIMD unaligned asm, RV32IMC ctrl | 175,225 / 182,424 | 175,225 / 182,424 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 8x32x32 | SIMD unaligned asm, Xpulp ctrl | 140,193 / 139,946 | 140,193 / 139,946 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 8x32x32 | SIMD aligned asm, RV32IMC ctrl | 167,129 / 169,042 | 167,129 / 169,042 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 8x32x32 | SIMD aligned asm, Xpulp ctrl | 159,930 / 159,443 | 159,930 / 159,443 | +0 / +0 | 54966 / 54966 ok | 39212 / 39212 ok |
| 32x8x8 | scalar C -O3 | 37,768 / 37,928 | 37,768 / 37,928 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |
| 32x8x8 | scalar asm, RV32IMC ctrl | 37,985 / 37,602 | 37,985 / 37,602 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |
| 32x8x8 | scalar asm, Xpulp ctrl | 37,442 / 37,219 | 37,442 / 37,219 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |
| 32x8x8 | SIMD unaligned asm, RV32IMC ctrl | 29,220 / 30,371 | 29,220 / 30,371 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |
| 32x8x8 | SIMD unaligned asm, Xpulp ctrl | 24,260 / 24,037 | 24,260 / 24,037 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |
| 32x8x8 | SIMD aligned asm, RV32IMC ctrl | 30,277 / 30,022 | 30,277 / 30,022 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |
| 32x8x8 | SIMD aligned asm, Xpulp ctrl | 29,638 / 29,861 | 29,638 / 29,861 | +0 / +0 | 36837 / 36837 ok | 30193 / 30193 ok |

| shape | kernel | cycles, real data (pad 0 / pad 1) | cycles, synthetic data, same code | difference | checksum real / expected | checksum synthetic / expected |
|---|---|---|---|---|---|---|
| 16x16x8x8 | scalar C -O3 | 64,832 / 63,809 | 64,832 / 63,809 | +0 / +0 | 25723 / 25723 ok | 62339 / 62339 ok |
| 16x16x8x8 | scalar asm, RV32IMC ctrl | 64,770 / 63,810 | 64,770 / 63,810 | +0 / +0 | 25723 / 25723 ok | 62339 / 62339 ok |
| 16x16x8x8 | scalar asm, Xpulp ctrl | 58,946 / 58,882 | 58,946 / 58,882 | +0 / +0 | 25723 / 25723 ok | 62339 / 62339 ok |
| 16x16x8x8 | SIMD asm, RV32IMC ctrl | 24,066 / 23,106 | 24,066 / 23,106 | +0 / +0 | 25723 / 25723 ok | 62339 / 62339 ok |
| 16x16x8x8 | SIMD asm, Xpulp ctrl | 18,178 / 18,242 | 18,178 / 18,242 | +0 / +0 | 25723 / 25723 ok | 62339 / 62339 ok |
| 8x8x16x16 | scalar C -O3 | 77,215 / 76,960 | 76,960 / 77,215 | +255 / -255 | 48479 / 48479 ok | 61712 / 61712 ok |
| 8x8x16x16 | scalar asm, RV32IMC ctrl | 80,905 / 79,113 | 80,905 / 79,113 | +0 / +0 | 48479 / 48479 ok | 61712 / 61712 ok |
| 8x8x16x16 | scalar asm, Xpulp ctrl | 69,638 / 69,894 | 69,638 / 69,894 | +0 / +0 | 48479 / 48479 ok | 61712 / 61712 ok |
| 8x8x16x16 | SIMD asm, RV32IMC ctrl | 40,454 / 38,662 | 40,454 / 38,662 | +0 / +0 | 48479 / 48479 ok | 61712 / 61712 ok |
| 8x8x16x16 | SIMD asm, Xpulp ctrl | 29,190 / 29,446 | 29,190 / 29,446 | +0 / +0 | 48479 / 48479 ok | 61712 / 61712 ok |
| 16x32x8x8 | scalar C -O3 | 128,324 / 126,277 | 128,324 / 126,277 | +0 / +0 | 24406 / 24406 ok | 52008 / 52008 ok |
| 16x32x8x8 | scalar asm, RV32IMC ctrl | 128,264 / 126,280 | 128,264 / 126,280 | +0 / +0 | 24406 / 24406 ok | 52008 / 52008 ok |
| 16x32x8x8 | scalar asm, Xpulp ctrl | 116,296 / 116,232 | 116,296 / 116,232 | +0 / +0 | 24406 / 24406 ok | 52008 / 52008 ok |
| 16x32x8x8 | SIMD asm, RV32IMC ctrl | 47,621 / 45,637 | 47,621 / 45,637 | +0 / +0 | 24406 / 24406 ok | 52008 / 52008 ok |
| 16x32x8x8 | SIMD asm, Xpulp ctrl | 35,589 / 35,653 | 35,589 / 35,653 | +0 / +0 | 24406 / 24406 ok | 52008 / 52008 ok |
| 16x16x16x16 | scalar C -O3 | 263,944 / 268,039 | 263,944 / 268,039 | +0 / +0 | 49666 / 49666 ok | 56729 / 56729 ok |
| 16x16x16x16 | scalar asm, RV32IMC ctrl | 259,085 / 255,245 | 259,085 / 255,245 | +0 / +0 | 49666 / 49666 ok | 56729 / 56729 ok |
| 16x16x16x16 | scalar asm, Xpulp ctrl | 235,532 / 235,788 | 235,532 / 235,788 | +0 / +0 | 49666 / 49666 ok | 56729 / 56729 ok |
| 16x16x16x16 | SIMD asm, RV32IMC ctrl | 96,264 / 92,424 | 96,264 / 92,424 | +0 / +0 | 49666 / 49666 ok | 56729 / 56729 ok |
| 16x16x16x16 | SIMD asm, Xpulp ctrl | 72,712 / 72,968 | 72,712 / 72,968 | +0 / +0 | 49666 / 49666 ok | 56729 / 56729 ok |

95 of 96 pairs are identical to the cycle. The exception is the
compiler-generated pointwise -O3 kernel at 8x8x16x16, where the two
alignment builds swap values (76,960 and 77,215): the two data headers
produced a 2-byte shift in GCC's code placement, and the 255-cycle
difference is one cycle per taken branch, the alignment effect already
described. Nothing on the measured path depends on data values. That is a
property of the branch-free requantisation, and it is what makes the
real-data numbers comparable with the synthetic ones.

### Real-data cycles against the int8 synthetic runs

The only code difference between the two modes is the requantisation, nine
instructions for symmetric int8 and eight for the unsigned clamp, so the
expected difference is one cycle per output:

| shape | kernel | int8 synthetic cycles | real-data cycles | difference | outputs | difference per output |
|---|---|---|---|---|---|---|
| 8x16x16 | scalar C -O3 | 55,296 | 52,953 | -2,343 | 1,568 | -1.49 |
| 8x16x16 | scalar asm, RV32IMC ctrl | 53,889 | 52,324 | -1,565 | 1,568 | -1.00 |
| 8x16x16 | scalar asm, Xpulp ctrl | 52,562 | 50,765 | -1,797 | 1,568 | -1.15 |
| 8x16x16 | SIMD unaligned asm, RV32IMC ctrl | 40,245 | 40,024 | -221 | 1,568 | -0.14 |
| 8x16x16 | SIMD unaligned asm, Xpulp ctrl | 32,519 | 30,953 | -1,566 | 1,568 | -1.00 |
| 8x16x16 | SIMD aligned asm, RV32IMC ctrl | 39,078 | 37,632 | -1,446 | 1,568 | -0.92 |
| 8x16x16 | SIMD aligned asm, Xpulp ctrl | 37,840 | 36,281 | -1,559 | 1,568 | -0.99 |
| 16x16x16 | scalar C -O3 | 110,585 | 107,436 | -3,149 | 3,136 | -1.00 |
| 16x16x16 | scalar asm, RV32IMC ctrl | 107,335 | 104,219 | -3,116 | 3,136 | -0.99 |
| 16x16x16 | scalar asm, Xpulp ctrl | 104,648 | 101,996 | -2,652 | 3,136 | -0.85 |
| 16x16x16 | SIMD unaligned asm, RV32IMC ctrl | 80,454 | 80,039 | -415 | 3,136 | -0.13 |
| 16x16x16 | SIMD unaligned asm, Xpulp ctrl | 65,030 | 61,896 | -3,134 | 3,136 | -1.00 |
| 16x16x16 | SIMD aligned asm, RV32IMC ctrl | 78,151 | 75,241 | -2,910 | 3,136 | -0.93 |
| 16x16x16 | SIMD aligned asm, Xpulp ctrl | 75,657 | 72,314 | -3,343 | 3,136 | -1.07 |
| 8x32x32 | scalar C -O3 | 249,063 | 244,988 | -4,075 | 7,200 | -0.57 |
| 8x32x32 | scalar asm, RV32IMC ctrl | 230,366 | 223,140 | -7,226 | 7,200 | -1.00 |
| 8x32x32 | scalar asm, Xpulp ctrl | 220,055 | 213,085 | -6,970 | 7,200 | -0.97 |
| 8x32x32 | SIMD unaligned asm, RV32IMC ctrl | 189,622 | 175,225 | -14,397 | 7,200 | -2.00 |
| 8x32x32 | SIMD unaligned asm, Xpulp ctrl | 147,391 | 140,193 | -7,198 | 7,200 | -1.00 |
| 8x32x32 | SIMD aligned asm, RV32IMC ctrl | 174,320 | 167,129 | -7,191 | 7,200 | -1.00 |
| 8x32x32 | SIMD aligned asm, Xpulp ctrl | 166,648 | 159,930 | -6,718 | 7,200 | -0.93 |
| 32x8x8 | scalar C -O3 | 38,696 | 37,768 | -928 | 1,152 | -0.81 |
| 32x8x8 | scalar asm, RV32IMC ctrl | 38,754 | 37,985 | -769 | 1,152 | -0.67 |
| 32x8x8 | scalar asm, Xpulp ctrl | 38,370 | 37,442 | -928 | 1,152 | -0.81 |
| 32x8x8 | SIMD unaligned asm, RV32IMC ctrl | 30,403 | 29,220 | -1,183 | 1,152 | -1.03 |
| 32x8x8 | SIMD unaligned asm, Xpulp ctrl | 25,220 | 24,260 | -960 | 1,152 | -0.83 |
| 32x8x8 | SIMD aligned asm, RV32IMC ctrl | 31,237 | 30,277 | -960 | 1,152 | -0.83 |
| 32x8x8 | SIMD aligned asm, Xpulp ctrl | 30,821 | 29,638 | -1,183 | 1,152 | -1.03 |
| 16x16x8x8 | scalar C -O3 | 65,857 | 64,832 | -1,025 | 1,024 | -1.00 |
| 16x16x8x8 | scalar asm, RV32IMC ctrl | 64,836 | 64,770 | -66 | 1,024 | -0.06 |
| 16x16x8x8 | scalar asm, Xpulp ctrl | 59,973 | 58,946 | -1,027 | 1,024 | -1.00 |
| 16x16x8x8 | SIMD asm, RV32IMC ctrl | 24,132 | 24,066 | -66 | 1,024 | -0.06 |
| 16x16x8x8 | SIMD asm, Xpulp ctrl | 19,206 | 18,178 | -1,028 | 1,024 | -1.00 |
| 8x8x16x16 | scalar C -O3 | 79,001 | 77,215 | -1,786 | 2,048 | -0.87 |
| 8x8x16x16 | scalar asm, RV32IMC ctrl | 81,157 | 80,905 | -252 | 2,048 | -0.12 |
| 8x8x16x16 | scalar asm, Xpulp ctrl | 71,941 | 69,638 | -2,303 | 2,048 | -1.12 |
| 8x8x16x16 | SIMD asm, RV32IMC ctrl | 42,501 | 40,454 | -2,047 | 2,048 | -1.00 |
| 8x8x16x16 | SIMD asm, Xpulp ctrl | 31,237 | 29,190 | -2,047 | 2,048 | -1.00 |
| 16x32x8x8 | scalar C -O3 | 128,323 | 128,324 | +1 | 2,048 | +0.00 |
| 16x32x8x8 | scalar asm, RV32IMC ctrl | 130,307 | 128,264 | -2,043 | 2,048 | -1.00 |
| 16x32x8x8 | scalar asm, Xpulp ctrl | 118,339 | 116,296 | -2,043 | 2,048 | -1.00 |
| 16x32x8x8 | SIMD asm, RV32IMC ctrl | 49,669 | 47,621 | -2,048 | 2,048 | -1.00 |
| 16x32x8x8 | SIMD asm, Xpulp ctrl | 37,700 | 35,589 | -2,111 | 2,048 | -1.03 |
| 16x16x16x16 | scalar C -O3 | 268,292 | 263,944 | -4,348 | 4,096 | -1.06 |
| 16x16x16x16 | scalar asm, RV32IMC ctrl | 259,592 | 259,085 | -507 | 4,096 | -0.12 |
| 16x16x16x16 | scalar asm, Xpulp ctrl | 240,136 | 235,532 | -4,604 | 4,096 | -1.12 |
| 16x16x16x16 | SIMD asm, RV32IMC ctrl | 100,359 | 96,264 | -4,095 | 4,096 | -1.00 |
| 16x16x16x16 | SIMD asm, Xpulp ctrl | 76,807 | 72,712 | -4,095 | 4,096 | -1.00 |

Hand-written kernels with hardware loops land on -1.00 per output to the
cycle. The others scatter by up to one cycle per output around it, which is
the taken-branch alignment effect moving between builds. The speedups in
the rest of this document carry over to real MobileNet data unchanged;
nothing in them was an artefact of the synthetic distribution.

## One block: depthwise into pointwise with the layout change

The two halves of a depthwise-separable block disagree on layout: the
depthwise kernels produce channel-first data, the pointwise kernel wants
channel-last. `sw/block.c` composes the two stages from the kernel sources
(renamed statics, `NO_MAIN`) on real data from MobilenetV1 Conv2d_1
depthwise and pointwise, 16 channels, 16x16 input, 14x14 x 16 output
(`sw/real/block_16x16x16_16.h`; depthwise multiplier 0.292 approximated by
2^-2, 14% low; pointwise 2^-5, 3% high; both stage checksums verified).
Two ways to cross the layout boundary: a scalar byte transpose between the
stages, or the depthwise stage storing channel-last directly through a
strided store (`OSTRIDE = CH`, `DW_OUT_PTR`), which costs nothing extra
on either ISA because the store already advances a pointer.

| block variant | cycles (pad 0 / pad 1) | cycles/MAC | instructions | data reads | data writes | taken branches | split loads | model residual | checksum (pw) |
|---|---|---|---|---|---|---|---|---|---|
| C -O3, transform | 339,691 / 332,079 | 4.24 | 310,120 | 70,026 | 9,938 | 7,837 | -1 | +0.0% | 596 |
| C -O3, fused store | 311,611 / 313,014 | 3.97 | 294,388 | 66,906 | 6,818 | 4,702 | -1 | +0.5% | 596 |
| SIMD asm, RV32IMC ctrl, transform | 172,864 / 176,190 | 2.20 | 144,394 | 32,736 | 9,408 | 9,405 | 6,720 | +1.7% | 596 |
| SIMD asm, RV32IMC ctrl, fused | 153,738 / 148,079 | 1.89 | 128,614 | 29,600 | 6,272 | 6,270 | 6,720 | +0.1% | 596 |
| SIMD + hw loops, transform | 139,837 / 139,628 | 1.78 | 125,774 | 32,736 | 9,408 | 3,553 | 6,720 | -0.1% | 596 |
| SIMD + hw loops, fused | 117,967 / 117,758 | 1.50 | 110,190 | 29,600 | 6,272 | 418 | 6,720 | -0.2% | 596 |
| full Xpulp (+ clip), transform | 102,205 / 101,996 | 1.30 | 88,142 | 32,736 | 9,408 | 3,553 | 6,720 | -0.2% | 596 |
| full Xpulp (+ clip), fused | 80,335 / 80,126 | 1.02 | 72,558 | 29,600 | 6,272 | 418 | 6,720 | -0.3% | 596 |

| quantity | value |
|---|---|
| layout transform, scalar C, cost in cycles (C -O3 block) | 20,468 = 6.2% of that block |
| layout transform cost in the full-Xpulp block | 21,870 = 21.4% of that block |
| full Xpulp fused vs C -O3 with transform | 4.14x |
| full Xpulp fused vs C -O3 fused | 3.89x |
| full Xpulp with transform vs C -O3 with transform | 3.26x |
| datapath only (SIMD asm, RV32IMC ctrl, fused) vs C -O3 fused | 2.10x |
| + hardware loops | 1.26x |
| + clip | 1.47x |
| fused full-Xpulp block vs sum of standalone stages (43,080 + 37,049) | -3 cycles |

- **Composition is exact.** The fused full-Xpulp block takes 80,335 cycles;
  the two stages measured alone take 43,080 + 37,049 = 80,129. The cycle
  model and the per-kernel numbers add. Three cycles of difference.
- **The layout transform is worth 21% of the accelerated block and 6% of
  the scalar one**, and the extension does nothing for it: about 21,000
  cycles either way. Quoting the kernel speedups for the block without
  accounting for it would overstate by 27%. Fusing it away is free when the
  depthwise kernel has a store stride, a software decision, not a hardware
  one.
- **Block-level numbers:** the full extension is 4.14x over -O3 C if the
  accelerated code fuses the layout and the baseline does not, 3.89x if
  both fuse, 3.26x if neither does. The kernel-level 2.5x (depthwise) and
  5.4x (pointwise) bracket all three, weighted by where the block spends
  its MACs (36% depthwise, 64% pointwise).
- Cycles per MAC for the whole block: 3.97 scalar, 1.02 full Xpulp fused.

## Second core: lowRISC Ibex

Everything above is one core. To separate what belongs to CV32E40P from
what belongs to the class of in-order single-issue embedded RISC-V cores,
the scalar kernels were run unmodified on lowRISC Ibex (third_party/ibex at
8f4c75c5, 2024-12-20), configured as RV32IMC with a single-cycle
multiplier, flip-flop register file, no instruction cache or PMP, branch
target ALU, and ten hardware performance counters, in both its pipeline
options: 2-stage (default) and 3-stage (WritebackStage). Ibex has no Xpulp,
so this is the scalar side only: the C kernels at -O2 and -O3 and the hand
asm kernels, three families, four shapes, both code alignments. Same
Verilator harness (`harness_ibex/`), same memory model, same binaries,
same magic addresses; Ibex's counters are fixed-event (data-side wait,
instruction-side wait, loads, stores, branches, taken branches, compressed)
and were validated the same way, loads retired against bus reads and stores
against bus writes.

One harness detail cost an afternoon and belongs here as a time-zero
simulation artefact, not as core behaviour: ibex_top gates the core clock
until fetch is enabled, so a reset held low from time zero produces neither
a falling reset edge nor a clock edge under the gate, and the
asynchronous-reset flops never evaluate. The privilege level then keeps its
power-on value, user mode, and every machine-mode CSR read traps. The
harness drives reset as a falling edge, which is what silicon always sees.

### Cycles, same binaries

| kernel | shape | instructions | CV32E40P cycles | Ibex 2-stage cycles | Ibex 3-stage cycles | Ibex2 / CV | Ibex3 / CV | alignment spread CV / Ibex2 / Ibex3 |
|---|---|---|---|---|---|---|---|---|
| 3x3 depthwise, C -O2 | 8x16x16 | 66,134 | 69,275 | 74,981 | 67,708 | 1.08 | 0.98 | 2.2% / 2.1% / 2.3% |
| 3x3 depthwise, C -O3 | 8x16x16 | 52,952 | 54,527 | 61,153 | 53,744 | 1.12 | 0.99 | 1.4% / 1.3% / 1.4% |
| 3x3 depthwise, hand asm | 8x16x16 | 52,507 | 53,673 | 61,621 | 53,210 | 1.15 | 0.99 | 0.4% / 0.4% / 0.4% |
| 3x3 depthwise, C -O2 | 16x16x16 | 132,278 | 138,564 | 149,974 | 135,429 | 1.08 | 0.98 | 2.2% / 2.1% / 2.3% |
| 3x3 depthwise, C -O3 | 16x16x16 | 105,899 | 109,048 | 122,299 | 107,481 | 1.12 | 0.99 | 1.4% / 1.3% / 1.4% |
| 3x3 depthwise, hand asm | 16x16x16 | 105,000 | 107,335 | 123,210 | 106,408 | 1.15 | 0.99 | 0.4% / 0.4% / 0.4% |
| 3x3 depthwise, C -O2 | 8x32x32 | 298,998 | 313,403 | 337,045 | 306,204 | 1.08 | 0.98 | 2.3% / 2.1% / 2.3% |
| 3x3 depthwise, C -O3 | 8x32x32 | 241,625 | 249,063 | 276,307 | 245,464 | 1.11 | 0.99 | 1.3% / 1.1% / 1.3% |
| 3x3 depthwise, hand asm | 8x32x32 | 225,545 | 230,366 | 258,328 | 227,967 | 1.12 | 0.99 | 1.0% / 0.9% / 1.0% |
| 3x3 depthwise, C -O2 | 32x8x8 | 51,112 | 53,413 | 59,111 | 52,262 | 1.11 | 0.98 | 2.2% / 1.9% / 2.2% |
| 3x3 depthwise, C -O3 | 32x8x8 | 37,960 | 38,536 | 45,356 | 38,345 | 1.18 | 1.00 | 0.4% / 0.4% / 0.4% |
| 3x3 depthwise, hand asm | 32x8x8 | 37,990 | 38,754 | 44,484 | 38,371 | 1.15 | 0.99 | 1.0% / 0.9% / 1.0% |
| 5x5 depthwise, C -O2 | 8x16x16 | 257,591 | 320,373 | 350,535 | 291,382 | 1.09 | 0.91 | 5.7% / 5.2% / 6.3% |
| 5x5 depthwise, C -O3 | 8x16x16 | 139,793 | 156,570 | 187,420 | 155,227 | 1.20 | 0.99 | 0.1% / 0.1% / 0.1% |
| 5x5 depthwise, hand asm | 8x16x16 | 137,935 | 157,421 | 167,695 | 150,702 | 1.07 | 0.96 | 3.2% / 3.0% / 3.4% |
| 5x5 depthwise, C -O2 | 16x16x16 | 515,159 | 640,723 | 701,045 | 582,740 | 1.09 | 0.91 | 5.7% / 5.2% / 6.3% |
| 5x5 depthwise, C -O3 | 16x16x16 | 279,594 | 313,160 | 374,842 | 310,473 | 1.20 | 0.99 | 0.1% / 0.1% / 0.1% |
| 5x5 depthwise, hand asm | 16x16x16 | 275,863 | 314,838 | 335,384 | 301,399 | 1.07 | 0.96 | 3.2% / 3.0% / 3.4% |
| 5x5 depthwise, C -O2 | 8x32x32 | 1,394,999 | 1,734,262 | 1,897,544 | 1,577,271 | 1.09 | 0.91 | 5.8% / 5.3% / 6.4% |
| 5x5 depthwise, C -O3 | 8x32x32 | 742,973 | 831,558 | 988,872 | 825,095 | 1.19 | 0.99 | 0.0% / 0.0% / 0.0% |
| 5x5 depthwise, hand asm | 8x32x32 | 723,167 | 835,159 | 877,074 | 797,976 | 1.05 | 0.96 | 2.2% / 2.1% / 2.3% |
| 5x5 depthwise, C -O2 | 32x8x8 | 119,462 | 149,413 | 163,559 | 135,846 | 1.09 | 0.91 | 5.0% / 4.5% / 5.5% |
| 5x5 depthwise, C -O3 | 32x8x8 | 69,864 | 77,289 | 96,491 | 76,010 | 1.25 | 0.98 | 0.9% / 0.7% / 0.9% |
| 5x5 depthwise, hand asm | 32x8x8 | 69,351 | 77,925 | 86,503 | 75,110 | 1.11 | 0.96 | 2.1% / 1.9% / 2.2% |
| 1x1 pointwise, C -O2 | 16x16x8x8 | 131,461 | 164,227 | 181,637 | 147,844 | 1.11 | 0.90 | 9.4% / 8.5% / 10.4% |
| 1x1 pointwise, C -O3 | 16x16x8x8 | 62,918 | 64,834 | 82,244 | 63,811 | 1.27 | 0.98 | 1.6% / 1.2% / 1.6% |
| 1x1 pointwise, hand asm | 16x16x8x8 | 62,790 | 64,836 | 82,246 | 63,813 | 1.27 | 0.98 | 1.5% / 1.2% / 1.5% |
| 1x1 pointwise, C -O2 | 8x8x16x16 | 148,998 | 181,764 | 200,198 | 165,381 | 1.10 | 0.91 | 7.9% / 7.2% / 8.7% |
| 1x1 pointwise, C -O3 | 8x8x16x16 | 67,709 | 79,001 | 85,748 | 78,746 | 1.09 | 1.00 | 0.3% / 0.3% / 0.3% |
| 1x1 pointwise, hand asm | 8x8x16x16 | 77,064 | 81,157 | 99,591 | 79,110 | 1.23 | 0.97 | 2.2% / 1.8% / 2.3% |
| 1x1 pointwise, C -O2 | 16x32x8x8 | 262,536 | 328,068 | 362,886 | 295,301 | 1.11 | 0.90 | 9.4% / 8.5% / 10.4% |
| 1x1 pointwise, C -O3 | 16x32x8x8 | 124,230 | 128,323 | 162,117 | 126,276 | 1.26 | 0.98 | 1.6% / 1.3% / 1.6% |
| 1x1 pointwise, hand asm | 16x32x8x8 | 124,233 | 128,323 | 162,118 | 126,276 | 1.26 | 0.98 | 1.5% / 1.2% / 1.6% |
| 1x1 pointwise, C -O2 | 16x16x16x16 | 525,830 | 656,901 | 726,535 | 591,366 | 1.11 | 0.90 | 9.4% / 8.5% / 10.4% |
| 1x1 pointwise, C -O3 | 16x16x16x16 | 251,654 | 268,292 | 330,246 | 264,197 | 1.23 | 0.98 | 1.3% / 1.1% / 1.4% |
| 1x1 pointwise, hand asm | 16x16x16x16 | 251,402 | 259,592 | 329,485 | 255,497 | 1.27 | 0.98 | 1.5% / 1.2% / 1.5% |

Instruction counts and checksums are identical across all three cores in
all 72 run pairs, which they must be: the counters count the same binary.
Cycle counts are not. Ibex's 2-stage pipeline takes 1.05 to 1.27x the
cycles of CV32E40P on the same code, because every load and store stalls a
cycle there; the 3-stage pipeline hides that and comes out at 0.90 to
1.00x, slightly faster than CV32E40P on branch-heavy -O2 code because its
branch target ALU takes a cycle off taken branches.

### Do the methodology results transfer

| kernel | shape | -O2 / -O3: CV32E40P | Ibex2 | Ibex3 | -O3 / hand asm: CV32E40P | Ibex2 | Ibex3 |
|---|---|---|---|---|---|---|---|
| 3x3 depthwise | 8x16x16 | 1.27x | 1.23x | 1.26x | 1.02x | 0.99x | 1.01x |
| 3x3 depthwise | 16x16x16 | 1.27x | 1.23x | 1.26x | 1.02x | 0.99x | 1.01x |
| 3x3 depthwise | 8x32x32 | 1.26x | 1.22x | 1.25x | 1.08x | 1.07x | 1.08x |
| 3x3 depthwise | 32x8x8 | 1.39x | 1.30x | 1.36x | 0.99x | 1.02x | 1.00x |
| 5x5 depthwise | 8x16x16 | 2.05x | 1.87x | 1.88x | 0.99x | 1.12x | 1.03x |
| 5x5 depthwise | 16x16x16 | 2.05x | 1.87x | 1.88x | 0.99x | 1.12x | 1.03x |
| 5x5 depthwise | 8x32x32 | 2.09x | 1.92x | 1.91x | 1.00x | 1.13x | 1.03x |
| 5x5 depthwise | 32x8x8 | 1.93x | 1.70x | 1.79x | 0.99x | 1.12x | 1.01x |
| 1x1 pointwise | 16x16x8x8 | 2.53x | 2.21x | 2.32x | 1.00x | 1.00x | 1.00x |
| 1x1 pointwise | 8x8x16x16 | 2.30x | 2.33x | 2.10x | 0.97x | 0.86x | 1.00x |
| 1x1 pointwise | 16x32x8x8 | 2.56x | 2.24x | 2.34x | 1.00x | 1.00x | 1.00x |
| 1x1 pointwise | 16x16x16x16 | 2.45x | 2.20x | 2.24x | 1.03x | 1.00x | 1.03x |

- **Baseline optimisation level**: -O2 to -O3 is worth 1.22 to 1.36x on
  3x3, 1.70 to 1.92x on 5x5, and 2.1 to 2.3x on 1x1 on Ibex, against 1.26
  to 1.39x, 1.93 to 2.09x and 2.3 to 2.6x on CV32E40P. Same direction,
  same order, slightly smaller because Ibex's stall structure penalises the
  -O3 code's extra loads.
- **Code alignment**: the spread between the two alignments is the same on
  all three cores to within half a point, 2% on the 3x3 -O2 kernel, 5 to
  6% on the 5x5 -O2 kernel, 8.5 to 10.4% on the pointwise -O2 kernel. The
  mechanism is the same: a taken branch whose first 32-bit instruction
  straddles a fetch word costs one extra cycle, on any core that fetches
  aligned words through a prefetch buffer.
- **Hand asm versus -O3**: within 3% on both cores at all shapes but two,
  where the hand scalar's design choices interact with the pipeline: the
  row-wise 5x5 kernel gains 12% on the 2-stage Ibex because its stores do
  not stall differently from -O3's loads, and the pointwise asm loses 14%
  at 8x8x16x16 on the same core.
- **The cycle model** transfers in structure, not in coefficients. On
  CV32E40P the counters expose load-use stalls and split loads directly and
  the model holds to under 1%. Ibex's counters expose data-side wait
  cycles, which account for the memory stalls exactly (coefficient 0.99),
  but fold the branch penalty into an instruction-side wait counter that
  overlaps with other stalls (coefficient 0.35). The best fixed-form model,
  cycles = instructions + data-side wait + 1.5 x taken branches, fits to a
  mean 1.2% and a maximum 4.5% on the 2-stage core, 1.7% and 7.3% on the
  3-stage; the 1.5 is the alignment effect averaged. A core's counters
  determine how exact its cycle model can be.

```
ibex2: least squares, cycles - instructions = 0.99 x data-side wait + 0.35 x instruction-side wait + 0.98 x taken branches   (R^2 of the stall part 0.9898, worst |residual| 5.7% of cycles, 72 runs)
fixed form cycles = instr + dwait + iwait: max |error| 8.5%, mean 1.6%, mean signed -0.0%
fixed form cycles = instr + dwait + 2 x taken branches: max |error| 9.0%, mean 1.7%, mean signed -1.7%
fixed form cycles = instr + dwait + taken branches + 0.35 x iwait: max |error| 6.1%, mean 1.4%, mean signed -0.2%
fixed form cycles = instr + dwait + 1.5 x taken branches: max |error| 4.5%, mean 1.2%, mean signed -0.2%
ibex3: least squares, cycles - instructions = 0.96 x data-side wait + 0.34 x instruction-side wait + 0.97 x taken branches   (R^2 of the stall part 0.9468, worst |residual| 7.1% of cycles, 72 runs)
fixed form cycles = instr + dwait + iwait: max |error| 10.4%, mean 2.2%, mean signed -0.3%
fixed form cycles = instr + dwait + 2 x taken branches: max |error| 11.1%, mean 2.3%, mean signed -2.3%
fixed form cycles = instr + dwait + taken branches + 0.35 x iwait: max |error| 7.5%, mean 1.9%, mean signed -0.5%
fixed form cycles = instr + dwait + 1.5 x taken branches: max |error| 7.3%, mean 1.7%, mean signed -0.5%
```

### Area

Same sv2v and yosys flow as the CV32E40P numbers (`syn/ibex/Makefile`):

| core | configuration | cells | GE |
|---|---|---|---|
| CV32E40P | RV32IMC | 19,989 | 43,771 |
| Ibex | RV32IMC, 2-stage | 19,625 | 43,548 |
| Ibex | RV32IMC, 3-stage | 20,215 | 44,746 |
| CV32E40P | RV32IMC + Xpulp | 33,418 | 68,703 |

Two independently designed RV32IMC cores land within 0.5% of each other in
synthesised area, and the 3-stage pipeline costs 2.8%. The Xpulp extension
costs more than half of either baseline core. Ibex here carries ten 40-bit
counters against CV32E40P's one 64-bit counter, which inflates its number
slightly; neither has been placed.

What this does not show: anything about the extension on another core, and
that remains the limit of the study.

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

- One core for the extension; two cores (CV32E40P, Ibex in two pipeline
  configurations) for the scalar baselines, the alignment and flag effects
  and the cycle model. Three kernels (3x3 and 5x5 depthwise, 1x1
  pointwise). Real
  data from one image and two MobileNetV1 layers, with the pointwise
  input channels cropped to 16; 5x5 has no real-data source in MobileNetV1
  and stays synthetic. Power-of-two requantisation, truncating rounding;
  the block's depthwise shift is 14% off the real multiplier. One block
  shape. No compressed-instruction variant of the hardware-loop kernels is
  possible on this core.
- Flat memory with no bus contention between ports. Instruction memory
  is zero-wait or a direct-mapped I-cache model; no data cache.
- Energy and power are not measured. A Verilator activity trace on the
  placed netlist with OpenROAD's power report would give an estimate.
- The 5x5 scalar baseline is the better of two hand-written loop orders
  (row-wise with the accumulator row in memory, and output-stationary with
  weights reloaded); other orders, such as keeping two weight rows
  resident, were not tried. The row-wise kernel matched -O3 within 1% and
  still lost 17 to 32% to the other order, so "matches the compiler" is
  not evidence of a strong baseline. The output-stationary kernel has not
  been run on Ibex.
- The compiler-generated SIMD kernels in Tables 1 and 2 carry load-use
  stalls a hand schedule avoids; the decomposition section has the
  hand-written counterparts.
- Single compiler version for the equalised dataset. The earlier 7%
  disagreement between GCC 13.2 and 16.1 on the unaligned SIMD kernel
  was not re-examined after equalisation.
- Area and timing are placement-aware but pre-CTS and pre-route, Sky130 HD
  only, one flow. Minimum period is read from residual slack at a 10 ns
  target.

## Reproducing

    cd harness && make all
    ./collect_wait0.sh ../results/pad0.csv "1 2 5 9" "-DCODE_PAD=0"
    ./collect_wait0.sh ../results/pad1.csv "1 2 5 9" "-DCODE_PAD=1"
    cd ../results && python3 wait0_eqrequant_model.py
    cd ../harness && ./sweep.sh        # data-port latency, IWAIT=0
    cd ../syn && make all attrib       # Sky130 area, flat and per-module
    make timing                        # yosys netlists + OpenSTA (raw netlist; see caveat)
    make place-base place-pulp         # OpenROAD placement, repair, timing
    cd ../harness && KERNELS="scalar_asm_rv|sw/dwconv_asm.c|-O2 scalar_asm_xp|sw/dwconv_asm.c|-O2+-DXPULP_CTRL=1 ..." \
      ./collect_wait0.sh ../results/decomp_pad0.csv "1 2 5 9" "-DCODE_PAD=0"   # decomposition grid
    SHAPES="16:16:8:8 8:8:16:16 16:32:8:8 16:16:16:16" KERNELS="pw_C_O3|sw/pwconv.c|-O3 ..." \
      ./collect_wait0.sh ../results/pw_pad0.csv "1 2 5 9" "-DCODE_PAD=0"       # pointwise
    SHAPES="8:16:16 16:16:16 8:32:32 32:8:8" KERNELS="dw5_C_O3|sw/dwconv5.c|-O3 ..." \
      ./collect_wait0.sh ../results/dw5_pad0.csv "1 2 5 9" "-DCODE_PAD=0"      # 5x5
    KERNELS="dw5_os_asm_rv|sw/dwconv5_os_asm.c|-O2 dw5_os_asm_xp|sw/dwconv5_os_asm.c|-O2+-DXPULP_CTRL=1 ..." \
      ./collect_wait0.sh results/wait0_dw5os_pad0.csv "1 2 5 9" "-DCODE_PAD=0"   # 5x5 output-stationary baseline
    REAL_HDR_PREFIX=real/dw3 KERNELS="scalar_asm_xp|sw/dwconv_asm.c|-O2+-DXPULP_CTRL=1 ..." \
      ./collect_wait0.sh ../results/real_dw3_pad0.csv "1 2 5 9" "-DCODE_PAD=0"  # real data
    KERNELS="simd_unal_asm_xp_clip|sw/dwconv_simd_asm.c|-O2+-DXPULP_CTRL=1+-DREQUANT_CLIP=1 ..." \
      ./collect_wait0.sh ../results/clip_dw3_pad0.csv "1 2 5 9" "-DCODE_PAD=0"   # clip
    for iw in 0 1 2 3; do WAITS=0 IWAIT=$iw KERNELS="..." ./sweep.sh; done   # instruction-port latency
    SHAPES=16:16:16 KERNELS="blk_full_fused|sw/block.c|-O2+-DBLOCK_SIMD=1+-DXPULP_CTRL=1+-DREQUANT_CLIP=1+-DBLOCK_FUSED=1 ..." \
      ./collect_wait0.sh ../results/block_pad0.csv "1 2 5 9" "-DCODE_PAD=0 -DREAL_HDR=real/block_16x16x16_16.h"   # block
    cd ../harness_ibex && make all && cd ../harness && \
      SIM=harness_ibex/obj_ibex2/Vibex_top KERNELS="scalar_O2|sw/dwconv_opt.c|-O2 ..." \
      ./collect_wait0.sh ../results/ibex2_dw3_pad0.csv "1 2 4 5 6 8 9 10" "-DCODE_PAD=0 -DIBEX_COUNTERS"  # second core
    cd ../syn/ibex && make all                                                     # Ibex area
    cd ../results && python3 wait0_decomp_model.py && python3 wait0_pw_model.py \
      && python3 wait0_dw5_model.py && python3 dw5_os_model.py && python3 summary_kernels.py && python3 real_data_model.py \
      && python3 clip_model.py --latex ../paper/tab_decomp.tex && python3 area_table.py --latex ../paper/tab_area.tex \
      && python3 block_model.py && ~/tools/venv/bin/python ibex_model.py
    cd ../results && python3 align_term.py      # Ba per run (rebuilds and reruns 304 binaries, ~5 min); run before the model scripts
    cd ../paper && pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper   # tables are \input from the generated fragments

Real-data headers: `~/tools/venv/bin/python sw/real/gen_real_data.py <model.tflite> <image> sw/real`
(needs numpy, Pillow, ai-edge-litert; the headers are committed, so this is
only needed to change the layer or the image).

Regression values: hello 38 cycles / 42; dotp 41 / 10 on Xpulp, TIMEOUT on
baseline; scalar -O2 at 8x16x16 wait 0: 69,275 cycles, checksum 64747.
