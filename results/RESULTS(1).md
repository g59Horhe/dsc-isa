# Operand supply limits realised SIMD speedup

CV32E40P. 8 channels, 16x16 input, 3x3 depthwise, 14x14 output.
14,112 MACs. Checksum 64747 for all three variants -- identical arithmetic.

## Headline

| wait | naive | optimised scalar | cv.dotsp.b | vs optimised | SIMD c/MAC |
|---|---|---|---|---|---|
| 0 | 202,792 | 70,858 | 45,176 | 1.57x | 3.20 |
| 1 | 364,554 | 114,548 | 68,308 | 1.68x | 4.84 |
| 2 | 524,879 | 169,482 | 97,642 | 1.74x | 6.92 |
| 3 | 725,972 | 225,960 | 127,200 | 1.78x | 9.01 |

cv.dotsp.b computes three useful MACs per instruction (fourth lane zeroed
for a 3-tap window). Available arithmetic speedup: 3.00x.
Realised speedup over the optimised scalar baseline: 1.57x.

**28% of the arithmetic capability is realised. The rest is lost to
operand supply.**

## Where it goes

Two of every three activation loads are unaligned. Consecutive output
pixels slide the 3-tap window by one byte, so a word-aligned load serves
only every fourth pixel.

Measured cost of unaligned access on CV32E40P (50 word loads):

    aligned:    402 cycles
    unaligned:  853 cycles      ~2.1x

The LSU splits a misaligned word into two bus accesses. Widening the
arithmetic three-fold did not widen the supply path, so the supply path
became the limit.

## Second-order result

Speedup over the scalar baseline grows with memory latency: 1.57x at zero
wait states, 1.78x at three. The SIMD version issues fewer load
instructions in total, so it suffers less as each load gets more
expensive. The gap widens exactly where supply pressure is highest.

The same trend appeared between naive and optimised scalar (2.86x to
3.21x). Any mechanism that reduces operand traffic should show it, and
the slope is a measurement in its own right.

## Why this matters

Published ISA-extension papers report arithmetic capability and end-to-end
speedup, rarely the gap between them, and almost never across memory
latencies. XpulpNN reports ~11% area overhead; RI5CY-Accel reports ~108%;
neither is comparable to the other because the cores, nodes, baselines and
workloads all differ.

This measurement is on one core, one workload, one open toolchain, with a
hand-optimised denominator and an identical checksum across variants. It
says: a 3x-wide MAC unit returns 1.57x on this workload because the
operand path was not widened with it.

## Threats

- One workload, one layer shape. Larger channel counts or different kernel
  sizes may shift the balance.
- Scalar baseline is compiler-version sensitive (~0.7% between GCC 13.2
  and 16.1 on the optimised version; the naive version was identical).
- The harness memory model is a flat array with uniform wait states. No
  cache, no burst behaviour.
- Alignment handling is left to the LSU. Restructuring the loop to process
  four output pixels per aligned load is an obvious alternative and is not
  yet measured.

## Next

1. Aligned variant: process 4 output pixels per load, shifting to realign.
   Tests whether the unaligned penalty can be traded for shift
   instructions profitably.
2. Weight-stationary and line-buffer mechanisms in RTL.
3. Area: Sky130 + OpenROAD for baseline and each variant.
