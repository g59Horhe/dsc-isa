#!/usr/bin/env python3
"""Depthwise 5x5, output-stationary scalar baseline (sw/dwconv5_os_asm.c) against
the row-wise sliding hand kernel (sw/dwconv5_asm.c) and C -O3, from
results/wait0_dw5os_pad{0,1}.csv, results/wait0_dw5_pad{0,1}.csv and
results/wait0_clip_dw5_pad{0,1}.csv. Answers the weak-baseline objection:
the first hand kernel matched -O3 within 1%, which proved only that it was
as good as the compiler. Run from results/."""
import csv, collections
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v['ev1']; v['ldstall'] = v['ev2']; v['loads'] = v['ev5']; v['brtaken'] = v['ev9']
        v['split'] = v['dread'] - v['loads']; v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['resid'] = v['cycles'] - v['pred']
    return d
P = [collections.OrderedDict(), collections.OrderedDict()]
for base in ('wait0_dw5', 'wait0_clip_dw5', 'wait0_dw5os'):
    for p in (0, 1): P[p].update(load(f'{base}_pad{p}.csv'))
shapes = []; [shapes.append(k[0]) for k in P[0] if k[0] not in shapes]
best = lambda s, k: min(P[0][(s, k)], P[1][(s, k)], key=lambda v: v['cycles'])
def macs(s):
    ch, h, w = map(int, s.split('x')); return ch * (h - 4) * (w - 4) * 25
def outs(s):
    ch, h, w = map(int, s.split('x')); return ch * (h - 4) * (w - 4)
names = [('dw5_C_O3', 'scalar C, -O3'), ('dw5_asm_rv', 'row-wise asm, RV32IMC ctrl'), ('dw5_asm_xp', 'row-wise asm, Xpulp ctrl'),
         ('dw5_os_asm_rv', 'output-stationary asm, RV32IMC ctrl'), ('dw5_os_asm_xp', 'output-stationary asm, Xpulp ctrl'),
         ('dw5_os_asm_rv_clip', 'output-stationary asm, RV32IMC ctrl, clip'), ('dw5_os_asm_xp_clip', 'output-stationary asm, Xpulp ctrl, clip'),
         ('dw5_simd_xp_clip', 'SIMD unaligned asm, Xpulp ctrl, clip (full Xpulp)')]
print("| shape | kernel | cycles (pad 0) | cycles (pad 1) | cycles/MAC | instructions per output | data reads | data writes | taken branches | load-use stalls | model residual | checksum |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
bad = 0
for s in shapes:
    for i, (k, n) in enumerate(names):
        a, b = P[0][(s, k)], P[1][(s, k)]; v = min((a, b), key=lambda v: abs(v['resid']))
        if a['chk'] != P[0][(s, 'dw5_asm_rv')]['chk'] or b['chk'] != P[0][(s, 'dw5_asm_rv')]['chk']: bad += 1
        print(f"| {s if i == 0 else ''} | {n} | {a['cycles']:,} | {b['cycles']:,} | {min(a['cycles'], b['cycles'])/macs(s):.2f} | {a['instr']/outs(s):.1f} | {a['dread']:,} | {a['dwrite']:,} | {a['brtaken']:,} | {a['ldstall']:,} | {v['resid']/v['cycles']:+.1%} | {a['chk']} |")
print()
print("| shape | output-stationary vs row-wise | vs -O3 | full Xpulp vs row-wise | vs output-stationary | vs -O3 | instr ratio vs output-stationary | control alone (output-stationary) | clip alone (output-stationary) | datapath alone vs output-stationary |")
print("|---|---|---|---|---|---|---|---|---|---|")
for s in shapes:
    c = lambda k: best(s, k)['cycles']; n = lambda k: best(s, k)['instr']
    print(f"| {s} | {c('dw5_asm_rv')/c('dw5_os_asm_rv'):.2f}x | {c('dw5_C_O3')/c('dw5_os_asm_rv'):.2f}x | {c('dw5_asm_rv')/c('dw5_simd_xp_clip'):.2f}x | {c('dw5_os_asm_rv')/c('dw5_simd_xp_clip'):.2f}x | {c('dw5_C_O3')/c('dw5_simd_xp_clip'):.2f}x | {n('dw5_os_asm_rv')/n('dw5_simd_xp_clip'):.2f} | {c('dw5_os_asm_rv')/c('dw5_os_asm_xp'):.2f}x | {c('dw5_os_asm_rv')/c('dw5_os_asm_rv_clip'):.2f}x | {c('dw5_os_asm_rv')/c('dw5_simd_rv'):.2f}x |")
s = shapes[0]; rw, os_ = best(s, 'dw5_asm_rv'), best(s, 'dw5_os_asm_rv')
print(f"\n{s}: row-wise {rw['cycles']:,} cycles = {rw['instr']:,} instructions + {2*rw['brtaken']:,} taken-branch cycles + {rw['ldstall']:,} load-use stalls ({rw['dwrite']:,} stores); "
      f"output-stationary {os_['cycles']:,} = {os_['instr']:,} + {2*os_['brtaken']:,} + {os_['ldstall']:,} ({os_['dwrite']:,} stores, {os_['loads']:,} loads = {os_['loads']/outs(s):.0f} per output). "
      f"Instructions per output {rw['instr']/outs(s):.1f} vs {os_['instr']/outs(s):.1f}; cycles per output {rw['cycles']/outs(s):.1f} vs {os_['cycles']/outs(s):.1f}.")
print(f"checksum mismatches against the row-wise kernel: {bad}; max |model residual| over the output-stationary runs: "
      f"{max(abs(v['resid'])/v['cycles'] for p in (0, 1) for k, v in P[p].items() if k[1].startswith('dw5_os')):.2%}")
