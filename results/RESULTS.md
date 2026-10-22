# Baseline measurement: int8 depthwise 3x3 convolution

CV32E40P, COREV_PULP=0, plain C at -O2, no custom instructions.
Layer: 8 channels, 16x16 input, 3x3 kernel, valid padding -> 14x14 output.
14,112 MACs per layer.

## Cycles vs memory latency

| wait states | measured cycles | cycles/MAC | vs wait=0 |
|---|---|---|---|
| 0 | 202,792 | 14.37 | --- |
| 1 | 364,554 | 25.83 | +80% |
| 2 | 524,879 | 37.19 | +159% |
| 3 | 725,972 | 51.44 | +258% |

Checksum 64747 (0xfceb) in every case. Identical cycle counts on
COREV_PULP=1 with the same binary, confirming the parameter does not
change baseline behaviour.

## Why 14 cycles for one multiply

The compiled inner loop (one MAC per iteration):

    186:  add   a4,a0,a5      address of input byte
    18a:  add   a2,a1,a5      address of weight byte
    18e:  lb    a4,0(a4)      load activation
    192:  lb    a2,0(a2)      load weight
    196:  addi  a5,a5,1       loop counter
    198:  mul   a4,a4,a2      <-- the actual MAC
    19c:  add   a3,a3,a4      accumulate
    19e:  bne   a5,a6,186     loop

Eight instructions per MAC. Four of them -- two address computations and
two byte loads -- are operand supply. The multiply is one instruction out
of eight, and the core has a single-cycle multiplier, so arithmetic is not
the limit by any measure.

Note the weight is reloaded on every MAC even though it is constant across
the whole spatial map for a given channel. GCC did not hoist it. That is
the reuse the weight-stationary mechanism exists to capture.

## What this does and does not establish

Establishes: for this workload on this core, operand supply dominates.
The wait-state sweep makes it quantitative -- three wait states nearly
quadruple the cost, which would not happen if the kernel were
arithmetic-bound.

Does not establish: that custom hardware is worth it. This baseline is
naive C with array indexing. A hand-written pointer-walking version with
hoisted weights should be substantially faster, and that is the honest
denominator for any speedup claim. Both numbers must be reported.

## Next

1. Hand-optimised scalar baseline: pointer increments, weights in
   registers, inner loop unrolled. Expect a large fraction of the 14.37
   to disappear without any hardware change.
2. cv.dotsp.b version: four MACs per instruction, but operands must be
   packed into words. Measures whether supply or arithmetic binds once
   the multiplier is four times wider.
3. Sweep both across wait states 0-3. The answer to "which mechanism
   wins" is likely to differ by memory latency, which is itself a result.
