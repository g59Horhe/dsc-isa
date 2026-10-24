#!/usr/bin/env python3
"""Cross-kernel summary at wait 0: what the same Xpulp extension is worth on
3x3 depthwise, 5x5 depthwise and 1x1 pointwise, from the three datasets.
Headline shapes: 8x16x16 (3x3), 8x16x16 (5x5), 16x16x8x8 (1x1). Full Xpulp = cv.dotsp.b + hardware loop + post-increment + cv.clip. Run from results/."""
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
O5 = [load(f'wait0_dw5os_pad{p}.csv') for p in (0, 1)]   # 5x5 hand scalar = output-stationary kernel, the stronger baseline (dw5_os_model.py)
C3 = [load(f'wait0_clip_dw3_pad{p}.csv') for p in (0, 1)]; C5 = [load(f'wait0_clip_dw5_pad{p}.csv') for p in (0, 1)]; C1 = [load(f'wait0_clip_pw_pad{p}.csv') for p in (0, 1)]
rows = [
  ("3x3 depthwise, 8x16x16", 14112, "3 of 4", best(E3, '8x16x16', 'scalar_O3'), best(D3, '8x16x16', 'scalar_asm_rv'), best(D3, '8x16x16', 'simd_unal_asm_rv'), best(D3, '8x16x16', 'simd_unal_asm_xp'), best(C3, '8x16x16', 'simd_unal_asm_xp_clip')),
  ("5x5 depthwise, 8x16x16", 28800, "5 of 8", best(D5, '8x16x16', 'dw5_C_O3'), best(O5, '8x16x16', 'dw5_os_asm_rv'), best(D5, '8x16x16', 'dw5_simd_rv'), best(D5, '8x16x16', 'dw5_simd_xp'), best(C5, '8x16x16', 'dw5_simd_xp_clip')),
  ("1x1 pointwise, 16x16x8x8", 16384, "4 of 4", best(D1, '16x16x8x8', 'pw_C_O3'), best(D1, '16x16x8x8', 'pw_asm_rv'), best(D1, '16x16x8x8', 'pw_simd_asm_rv'), best(D1, '16x16x8x8', 'pw_simd_asm_xp'), best(C1, '16x16x8x8', 'pw_simd_asm_xp_clip')),
]
print("| kernel | MACs | lanes used | scalar -O3 c/MAC | hand scalar c/MAC | SIMD + hw loop c/MAC | full Xpulp (+ clip) c/MAC | full Xpulp vs -O3 | vs hand scalar | instr ratio vs hand | datapath only | control on top of SIMD | clip on top of that | SIMD loads/MAC | split-load share of full |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for name, macs, lanes, o3, asm, srv, sxp, sxc in rows:
    print(f"| {name} | {macs:,} | {lanes} | {o3['cycles']/macs:.2f} | {asm['cycles']/macs:.2f} | {sxp['cycles']/macs:.2f} | {sxc['cycles']/macs:.2f} | {o3['cycles']/sxc['cycles']:.2f}x | {asm['cycles']/sxc['cycles']:.2f}x | {asm['instr']/sxc['instr']:.2f} | {asm['cycles']/srv['cycles']:.2f}x | {srv['cycles']/sxp['cycles']:.2f}x | {sxp['cycles']/sxc['cycles']:.2f}x | {sxc['loads']/macs:.2f} | {sxc['split']/sxc['cycles']:.1%} |")
