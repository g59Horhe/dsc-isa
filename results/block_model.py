#!/usr/bin/env python3
"""One depthwise-separable block on real MobileNetV1 data (Conv2d_1 depthwise ->
pointwise, 16 channels, 16x16 -> 14x14 -> 16 outputs): stage composition, the
layout transform, and fusion by strided store. From results/wait0_block_pad{0,1}.csv.
Run from results/."""
import csv, collections
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault(r['kernel'], {})[r['event']] = int(r['value']); d[r['kernel']]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v['ev1']; v['ldstall'] = v['ev2']; v['loads'] = v['ev5']; v['brtaken'] = v['ev9']
        v['split'] = v['dread'] - v['loads']; v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['resid'] = v['cycles'] - v['pred']
    return d
P = {p: load(f'wait0_block_pad{p}.csv') for p in (0, 1)}
best = lambda k: min(P[0][k], P[1][k], key=lambda v: v['cycles'])
names = {'blk_C_O3': 'C -O3, transform', 'blk_C_O3_fused': 'C -O3, fused store', 'blk_simd_rv': 'SIMD asm, RV32IMC ctrl, transform', 'blk_simd_rv_fused': 'SIMD asm, RV32IMC ctrl, fused',
         'blk_simd_xp': 'SIMD + hw loops, transform', 'blk_simd_xp_fused': 'SIMD + hw loops, fused', 'blk_full': 'full Xpulp (+ clip), transform', 'blk_full_fused': 'full Xpulp (+ clip), fused'}
MACS = 16 * 14 * 14 * 9 + 196 * 16 * 16
print(f"MACs: depthwise {16*14*14*9:,} + pointwise {196*16*16:,} = {MACS:,}\n")
print("| block variant | cycles (pad 0 / pad 1) | cycles/MAC | instructions | data reads | data writes | taken branches | split loads | model residual | checksum (pw) |")
print("|---|---|---|---|---|---|---|---|---|---|")
for k in P[0]:
    a, b = P[0][k], P[1][k]; v = min((a, b), key=lambda v: abs(v['resid']))
    print(f"| {names[k]} | {a['cycles']:,} / {b['cycles']:,} | {min(a['cycles'],b['cycles'])/MACS:.2f} | {a['instr']:,} | {a['dread']:,} | {a['dwrite']:,} | {a['brtaken']:,} | {a['split']:,} | {v['resid']/v['cycles']:+.1%} | {a['chk']} |")
c = lambda k: best(k)['cycles']
print("\n| quantity | value |\n|---|---|")
print(f"| layout transform, scalar C, cost in cycles (C -O3 block) | {c('blk_C_O3')-c('blk_C_O3_fused'):,} = {(c('blk_C_O3')-c('blk_C_O3_fused'))/c('blk_C_O3'):.1%} of that block |")
print(f"| layout transform cost in the full-Xpulp block | {c('blk_full')-c('blk_full_fused'):,} = {(c('blk_full')-c('blk_full_fused'))/c('blk_full'):.1%} of that block |")
print(f"| full Xpulp fused vs C -O3 with transform | {c('blk_C_O3')/c('blk_full_fused'):.2f}x |")
print(f"| full Xpulp fused vs C -O3 fused | {c('blk_C_O3_fused')/c('blk_full_fused'):.2f}x |")
print(f"| full Xpulp with transform vs C -O3 with transform | {c('blk_C_O3')/c('blk_full'):.2f}x |")
print(f"| datapath only (SIMD asm, RV32IMC ctrl, fused) vs C -O3 fused | {c('blk_C_O3_fused')/c('blk_simd_rv_fused'):.2f}x |")
print(f"| + hardware loops | {c('blk_simd_rv_fused')/c('blk_simd_xp_fused'):.2f}x |")
print(f"| + clip | {c('blk_simd_xp_fused')/c('blk_full_fused'):.2f}x |")
print(f"| fused full-Xpulp block vs sum of standalone stages (43,080 + 37,049) | {c('blk_full_fused') - 80129:+,} cycles |")
