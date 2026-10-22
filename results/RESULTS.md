# The software fix relocates the bottleneck instead of removing it

CV32E40P, COREV_PULP=1. 8 channels, 16x16 input, 3x3 depthwise.
14,112 MACs. Checksum 64747 for every variant.

## Four variants

| wait | naive | opt scalar | SIMD unaligned | SIMD aligned |
|---|---|---|---|---|
| 0 | 202,792 | 70,858 | 45,176 | **38,969** |
| 1 | 364,554 | 114,548 | 68,308 | **67,420** |
| 2 | 524,879 | 169,482 | **97,642** | 99,961 |
| 3 | 725,972 | 225,960 | **127,200** | 132,590 |

**The ranking inverts between one and two wait states.**

## Why

The unaligned variant loads one word per output pixel per row. Two in
three are misaligned, and the LSU splits those into two bus accesses
(measured separately at ~2.1x for a word load).

The aligned variant loads two aligned words per row per four output pixels
and shifts to extract the four windows. Half the load instructions, none
misaligned.

It wins at low latency. It loses at high latency, because of this:

    stack accesses in the compiled kernel
      SIMD unaligned:  12
      SIMD aligned:    32

Six activation words, three weight words, three row pointers and the
output pointer exceed what the register file holds comfortably. GCC
spills. Spills are memory accesses, so they scale with wait states
exactly like the unaligned penalty they were introduced to avoid -- and
at two or more wait states they cost more.

## What this means for the hardware

The software workaround does not remove the operand-supply bottleneck. It
moves it from the load/store unit to the register file.

That is a measured argument for architecturally visible storage rather
than an assumed one. A weight-stationary unit or line buffer holds
operands without consuming architectural registers, so it is the only one
of the three approaches that addresses both pressures at once. Biswas et
al. (IEEE TCAD 26(3), 2007) made the same architectural argument for
AFU-resident memory; this is the same effect appearing in a RISC-V SIMD
context twenty years later.

## What it means for the methodology

There is no single answer to "which approach is fastest". It depends on
memory latency, and the crossover sits inside the range real MCUs occupy.

Published ISA-extension papers generally report one memory configuration
and one speedup number. If the ranking of approaches can invert between
zero and two wait states on the same core, same workload and same
compiler, then a single-configuration result is a point on an unlabelled
curve.

## Threats

- One layer shape, one channel count.
- Register pressure is GCC's allocation, not a hardware limit. A hand-
  written assembly version might spill less. The direction of the effect
  is robust; the exact crossover point is not.
- Flat memory model with uniform wait states. No cache, no bursts.
- The aligned variant handles OW=14 as 12 + a 2-pixel unaligned tail,
  so it is not purely aligned.

## Next

1. Hand-written assembly for the aligned variant, to separate the
   register-pressure effect from GCC's allocator.
2. Weight-stationary and line-buffer mechanisms in RTL.
3. Area: Sky130 + OpenROAD, baseline vs each variant.
