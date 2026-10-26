#!/usr/bin/env python3
"""Depthwise 5x5: table, cycle model, and speedups from
results/wait0_dw5_pad{0,1}.csv. Run from results/."""
import csv, collections
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v.pop('ev1'); v['ldstall'] = v.pop('ev2'); v['loads'] = v.pop('ev5'); v['brtaken'] = v.pop('ev9')
        v['split'] = v['dread'] - v['loads']; v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['resid'] = v['cycles'] - v['pred']
    return d
P = {p: load(f'wait0_dw5_pad{p}.csv') for p in (0, 1)}
try:   # five-term model: the branch-target alignment term, measured per run by align_term.py
    _A = {(r['shape'], r['kernel'], int(r['pad'])): int(r['ba']) for r in csv.DictReader(open('wait0_align.csv'))}
except FileNotFoundError:
    _A = {}
for _p in (0, 1):
    for _k, _v in P[_p].items(): _v['ba'] = _A.get((_k[0], _k[1], _p), 0); _v['pred'] += _v['ba']; _v['resid'] = _v['cycles'] - _v['pred']
keys = list(P[0]); shapes = []; [shapes.append(k[0]) for k in keys if k[0] not in shapes]
names = {'dw5_C_O2': 'scalar C, -O2', 'dw5_C_O3': 'scalar C, -O3', 'dw5_asm_rv': 'scalar asm, RV32IMC ctrl', 'dw5_asm_xp': 'scalar asm, Xpulp ctrl',
         'dw5_simd_rv': 'SIMD unaligned asm, RV32IMC ctrl', 'dw5_simd_xp': 'SIMD unaligned asm, Xpulp ctrl'}
best = lambda s, k: min(P[0][(s, k)], P[1][(s, k)], key=lambda v: v['cycles'])
def macs(s):
    ch, h, w = map(int, s.split('x')); return ch * (h - 4) * (w - 4) * 25
print("| shape | kernel | cycles (pad 0) | cycles (pad 1) | cycles/MAC | instructions | data reads | data writes | taken branches | load-use stalls | split-load accesses | model residual | checksum |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for s in shapes:
    for i, k in enumerate([k for k in keys if k[0] == s]):
        a, b = P[0][k], P[1][k]; v = min((a, b), key=lambda v: abs(v['resid']))
        print(f"| {s if i == 0 else ''} | {names[k[1]]} | {a['cycles']:,} | {b['cycles']:,} | {min(a['cycles'],b['cycles'])/macs(s):.2f} | {a['instr']:,} | {a['dread']:,} | {a['dwrite']:,} | {a['brtaken']:,} | {a['ldstall']:,} | {a['split']:,} | {v['resid'] / v['cycles']:+.1%} | {a['chk']} |")
print()
print("| shape | -O2 / -O3 | -O3 / asm | SIMD (Xpulp ctrl) vs scalar -O3 | vs scalar asm | instr ratio vs asm | datapath only | control only (scalar) | control on top of SIMD | split-load share of best |")
print("|---|---|---|---|---|---|---|---|---|---|")
for s in shapes:
    c = lambda k: best(s, k)['cycles']; n = lambda k: best(s, k)['instr']; bx = best(s, 'dw5_simd_xp')
    print(f"| {s} | {c('dw5_C_O2')/c('dw5_C_O3'):.2f}x | {c('dw5_C_O3')/c('dw5_asm_rv'):.2f}x | {c('dw5_C_O3')/c('dw5_simd_xp'):.2f}x | {c('dw5_asm_rv')/c('dw5_simd_xp'):.2f}x | {n('dw5_asm_rv')/n('dw5_simd_xp'):.2f} | {c('dw5_asm_rv')/c('dw5_simd_rv'):.2f}x | {c('dw5_asm_rv')/c('dw5_asm_xp'):.2f}x | {c('dw5_simd_rv')/c('dw5_simd_xp'):.2f}x | {bx['split']/bx['cycles']:.1%} |")
print("\nmax |model residual| over all runs:", f"{max(abs(v['resid']) / v['cycles'] for p in (0, 1) for v in P[p].values()):.1%}")
print("alignment spread (max over shapes):", {names[k]: f"{max(abs(P[0][(s, k)]['cycles'] - P[1][(s, k)]['cycles']) / min(P[0][(s, k)]['cycles'], P[1][(s, k)]['cycles']) for s in shapes):.1%}" for k in names})
