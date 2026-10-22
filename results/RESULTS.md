# Operand supply limits realised SIMD speedup on depthwise convolution

CV32E40P under Verilator. int8 depthwise 3x3, branchless saturation.
All variants produce identical checksums per shape, so the comparison is
of identical arithmetic.

Primary numbers: riscv32-unknown-elf-gcc 16.1.0. A second toolchain
(13.2.0) was used as a cross-check; where the two disagree it is noted.

## Result 1: roughly 45% of available arithmetic is realised

`cv.dotsp.b` computes three useful MACs per instruction (fourth lane
zeroed for a 3-tap window). Available arithmetic speedup: 3.00x.

| shape | opt scalar | best SIMD | speedup | realised |
|---|---|---|---|---|
| 8x16x16 | 70,979 | 38,279 | 1.85x | 43% |
| 16x16x16 | 145,079 | 78,087 | 1.86x | 43% |
| 8x32x32 | 328,045 | 166,176 | 1.97x | 49% |
| 32x8x8 | 55,657 | 29,639 | 1.88x | 44% |

Stable across a 4x range in channel count and 16x in spatial size.
GCC 13.2 gives 39-43% on the same shapes, so the figure is mildly
compiler-sensitive but the conclusion is not.

**Widening the multiplier three-fold returns under two-fold, because the
operand path was not widened with it.**

### Mechanism

Measured separately: an unaligned word load on CV32E40P costs about 2.1x
an aligned one (853 vs 402 cycles for 50 loads). The LSU splits a
misaligned word into two bus accesses.

Two of every three activation loads are unaligned, because consecutive
output pixels slide the 3-tap window by one byte and a word-aligned load
serves only every fourth pixel.

### Full measurement grid

Cycles, branchless saturation, GCC 16.1.0:

| shape | kernel | w0 | w1 | w2 | w3 |
|---|---|---|---|---|---|
| 8x16x16 | scalar | 70,979 | 114,699 | 169,620 | 227,557 |
| | SIMD unaligned | 48,408 | 77,580 | 110,826 | 143,064 |
| | SIMD aligned | 38,279 | 65,044 | 96,553 | 128,399 |
| 16x16x16 | scalar | 145,079 | 230,008 | 339,885 | 452,849 |
| | SIMD unaligned | 96,840 | 155,196 | 221,699 | 286,185 |
| | SIMD aligned | 78,087 | 134,939 | 199,936 | 264,485 |
| 8x32x32 | scalar | 328,045 | 518,742 | 766,841 | 1,022,108 |
| | SIMD unaligned | 204,984 | 309,075 | 441,770 | 574,944 |
| | SIMD aligned | 166,176 | 285,684 | 426,370 | 568,728 |
| 32x8x8 | scalar | 55,657 | 88,811 | 131,153 | 174,550 |
| | SIMD unaligned | 37,096 | 59,468 | 85,074 | 110,104 |
| | SIMD aligned | 29,639 | 51,593 | 75,853 | 100,497 |

Checksums: 64747, 64114, 62900, 65171.

## Result 2: the software workaround relocates the bottleneck

Loading two aligned words per four output pixels and shifting to extract
the windows avoids unaligned access entirely. It is faster at every shape
and latency measured here.

But it is not free. Stack accesses in the compiled kernel:

    SIMD unaligned:  10-12
    SIMD aligned:    32

Six activation words plus three weight words plus three row pointers and
the output pointer exceed comfortable register pressure, so GCC spills.
Spills are memory traffic and scale with wait states exactly like the
penalty they were introduced to avoid.

The aligned advantage shrinks monotonically with latency in every shape
and both compilers -- 0.791 to 0.897 at 8x16x16, 0.811 to 0.989 at
8x32x32 -- which is the spill traffic becoming more expensive.

**The software fix moves the bottleneck from the load/store unit to the
register file rather than removing it.** That is a measured argument for
architecturally visible storage: a weight-stationary unit or line buffer
consumes neither LSU bandwidth nor architectural registers. Biswas et al.
(IEEE TCAD 26(3), 2007) made the same architectural case for AFU-resident
memory; the effect reappears here in a RISC-V SIMD context.

## Result 3 (methodology): saturation branches contaminate the measurement

The obvious requantisation,

    if (acc >  127) acc =  127;
    if (acc < -128) acc = -128;

places two data-dependent branches on the per-output-pixel path. How often
they are taken depends on the input distribution, and taken branches cost
cycles on CV32E40P.

Measured at 16 channels, 16x16, GCC 13.2:

    branching requant:   aligned/unaligned ratio 0.783
    branchless requant:  aligned/unaligned ratio 0.859

A 10% shift, and it produced an apparent dependence on channel count that
vanishes entirely once the branches are removed.

**Benchmarks of quantised kernels that saturate with branches are partly
measuring their test data.** All kernels here use branchless saturation.

## Not reproducible: the aligned/unaligned crossover

Under GCC 13.2, the aligned variant became *slower* than the unaligned one
at two or more wait states for W=16 shapes, and the ratio exceeded 1.0.
Under GCC 16.1 this does not occur at any shape or latency tested; aligned
wins throughout, though the margin narrows.

The underlying mechanism (spill traffic scaling with latency) is present
in both compilers and the convergence trend is robust. The inversion
itself is not, and is reported here only as an observation under one
toolchain. It should not be treated as a finding.

## Threats to validity

- Register pressure is GCC's allocation decision, not an architectural
  limit. Hand-written assembly might spill less. This is the single
  largest unresolved threat to Result 2.
- Flat memory model with uniform wait states; no cache, no bursts.
- Scalar baseline varies ~0.7% between GCC 13.2 and 16.1; SIMD unaligned
  agrees to 0.03% at some shapes and differs by 7% at others.
- One kernel size (3x3), one quantisation scheme, one core.
- No area numbers yet. Cycle results alone are half a trade-off.

## Reproducing

    cd harness && make all
    ./sweep.sh

Environment: Verilator 5.020, CV32E40P commit b353438,
riscv32-unknown-elf-gcc 16.1.0, -march=rv32imc -mabi=ilp32 -O2.
