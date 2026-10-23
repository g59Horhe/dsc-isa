#!/usr/bin/env python3
"""Cross-kernel summary at wait 0: what the same Xpulp extension is worth on
3x3 depthwise, 5x5 depthwise and 1x1 pointwise, from the three datasets.
Headline shapes: 8x16x16 (3x3), 8x16x16 (5x5), 16x16x8x8 (1x1). Run from results/."""
import csv, collections
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value'])
    for v in d.values():
        v['instr'] = v['ev1']; v['loads'] = v['ev5']; v['split'] = v['dread'] - v['loads']
    return d
def best(ds, s, k): return min((ds[0][(s, k)], ds[1][(s, k)]), key=lambda v: v['cycles'])
D3 = [load(f'wait0_decomp_pad{p}.csv') for p in (0, 1)]; E3 = [load(f'wait0_eqrequant_pad{p}.csv') for p in (0, 1)]
D5 = [load(f'wait0_dw5_pad{p}.csv') for p in (0, 1)]; D1 = [load(f'wait0_pw_pad{p}.csv') for p in (0, 1)]
rows = [
  ("3x3 depthwise, 8x16x16", 14112, "3 of 4", best(E3, '8x16x16', 'scalar_O3'), best(D3, '8x16x16', 'scalar_asm_rv'), best(D3, '8x16x16', 'simd_unal_asm_rv'), best(D3, '8x16x16', 'simd_unal_asm_xp')),
  ("5x5 depthwise, 8x16x16", 28800, "5 of 8", best(D5, '8x16x16', 'dw5_C_O3'), best(D5, '8x16x16', 'dw5_asm_rv'), best(D5, '8x16x16', 'dw5_simd_rv'), best(D5, '8x16x16', 'dw5_simd_xp')),
  ("1x1 pointwise, 16x16x8x8", 16384, "4 of 4", best(D1, '16x16x8x8', 'pw_C_O3'), best(D1, '16x16x8x8', 'pw_asm_rv'), best(D1, '16x16x8x8', 'pw_simd_asm_rv'), best(D1, '16x16x8x8', 'pw_simd_asm_xp')),
]
print("| kernel | MACs | lanes used | scalar -O3 c/MAC | hand scalar c/MAC | best SIMD c/MAC | extension vs -O3 | vs hand scalar | instr ratio vs hand | datapath only | control on top of SIMD | SIMD loads/MAC | split-load share of best |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for name, macs, lanes, o3, asm, srv, sxp in rows:
    print(f"| {name} | {macs:,} | {lanes} | {o3['cycles']/macs:.2f} | {asm['cycles']/macs:.2f} | {sxp['cycles']/macs:.2f} | {o3['cycles']/sxp['cycles']:.2f}x | {asm['cycles']/sxp['cycles']:.2f}x | {asm['instr']/sxp['instr']:.2f} | {asm['cycles']/srv['cycles']:.2f}x | {srv['cycles']/sxp['cycles']:.2f}x | {sxp['loads']/macs:.2f} | {sxp['split']/sxp['cycles']:.1%} |")
