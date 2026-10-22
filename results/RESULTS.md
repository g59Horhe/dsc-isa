# Scalar baselines: int8 depthwise 3x3 convolution

CV32E40P, COREV_PULP=0, GCC -O2, no custom instructions.
8 channels, 16x16 input, 3x3 kernel, 14x14 output. 14,112 MACs.
Checksum 64747 (0xfceb) for both versions -- same arithmetic, same result.

## Naive vs hand-optimised

| wait | naive | optimised | speedup | naive c/MAC | opt c/MAC |
|---|---|---|---|---|---|
| 0 | 202,792 | 70,858 | 2.86x | 14.37 | 5.02 |
| 1 | 364,554 | 114,548 | 3.18x | 25.83 | 8.12 |
| 2 | 524,879 | 169,482 | 3.10x | 37.19 | 12.01 |
| 3 | 725,972 | 225,960 | 3.21x | 51.44 | 16.01 |

**The optimised version is the denominator.** Measuring custom hardware
against the naive version would credit it with a 2.86x speedup that comes
entirely from writing better C.

## What changed

Three source-level changes, no hardware, no SIMD, no intrinsics:

1. Nine weights hoisted into registers once per channel. In depthwise conv
   they are constant across the whole spatial map; GCC reloaded them on
   every MAC in the naive version.
2. Three row pointers walked with increments instead of recomputing
   addresses from [c][y][x] on every access.
3. 3x3 loops fully unrolled, removing loop control from the MAC path.

GCC then software-pipelines the result, loading the next pixel's
activations while multiplying the current one.

## What is left

Roughly nine byte loads per output pixel against nine multiplies. Every
activation is loaded fresh even though adjacent output pixels share six of
their nine inputs. The compiler cannot exploit this -- each `lb` is a
separate byte access it cannot prove redundant.

That residual sliding-window reuse is what a line buffer or weight-
stationary unit exists to capture, and 5.02 cycles/MAC is the number any
such mechanism now has to beat.

## Second-order result

The speedup grows with memory latency: 2.86x at zero wait states, 3.21x at
three. Hoisting the weights removes memory traffic, which matters more when
memory is slower. Any mechanism that reduces operand traffic should show
the same trend, and the slope is itself a measurement.

## Next

1. cv.dotsp.b version -- four MACs per instruction, operands packed into
   words. Tests whether supply or arithmetic binds once the multiplier is
   four times wider.
2. Sweep across wait states; the ranking of mechanisms may differ by
   memory latency.
3. Synthesis: area of baseline vs each variant, Sky130 + OpenROAD.
