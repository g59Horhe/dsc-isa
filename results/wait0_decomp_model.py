#!/usr/bin/env python3
"""Decomposition of the Xpulp speedup into datapath (cv.dotsp.b) and
control/addressing (hardware loop + post-increment) contributions, from the
hand-written kernel pairs in results/wait0_decomp_pad{0,1}.csv. Run from results/."""
import csv, collections
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v.pop('ev1'); v['ldstall'] = v.pop('ev2'); v['loads'] = v.pop('ev5'); v['brtaken'] = v.pop('ev9')
        v['split'] = v['dread'] - v['loads']; v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['resid'] = v['cycles'] - v['pred']
    return d
P = {p: load(f'wait0_decomp_pad{p}.csv') for p in (0, 1)}
try:   # five-term model: the branch-target alignment term, measured per run by align_term.py
    _A = {(r['shape'], r['kernel'], int(r['pad'])): int(r['ba']) for r in csv.DictReader(open('wait0_align.csv'))}
except FileNotFoundError:
    _A = {}
for _p in (0, 1):
    for _k, _v in P[_p].items(): _v['ba'] = _A.get((_k[0], _k[1], _p), 0); _v['pred'] += _v['ba']; _v['resid'] = _v['cycles'] - _v['pred']
keys = list(P[0]); shapes = []; [shapes.append(k[0]) for k in keys if k[0] not in shapes]
best = lambda s, k: min(P[0][(s, k)], P[1][(s, k)], key=lambda v: v['cycles'])
names = {'scalar_asm_rv': 'scalar asm, RV32IMC control', 'scalar_asm_xp': 'scalar asm, Xpulp control', 'simd_unal_asm_rv': 'SIMD unaligned asm, RV32IMC control',
         'simd_unal_asm_xp': 'SIMD unaligned asm, Xpulp control', 'simd_al_asm_rv': 'SIMD aligned asm, RV32IMC control', 'simd_al_asm_xp': 'SIMD aligned asm, Xpulp control'}
print("| shape | kernel | cycles (pad 0) | cycles (pad 1) | instructions | fetches | data reads | taken branches | load-use stalls | split-load accesses | model residual | checksum |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for s in shapes:
    for i, k in enumerate([k for k in keys if k[0] == s]):
        a, b = P[0][k], P[1][k]; v = min((a, b), key=lambda v: abs(v['resid']))
        print(f"| {s if i == 0 else ''} | {names[k[1]]} | {a['cycles']:,} | {b['cycles']:,} | {a['instr']:,} | {a['ifetch']:,} | {a['dread']:,} | {a['brtaken']:,} | {a['ldstall']:,} | {a['split']:,} | {v['resid'] / v['cycles']:+.1%} | {a['chk']} |")
print()
print("| shape | control only (scalar) | datapath only (unaligned) | datapath only (aligned) | both (unaligned) | both (aligned) | control gain on top of SIMD (unaligned) | control gain on top of SIMD (aligned) |")
print("|---|---|---|---|---|---|---|---|")
for s in shapes:
    c = lambda k: best(s, k)['cycles']
    print(f"| {s} | {c('scalar_asm_rv') / c('scalar_asm_xp'):.2f}x | {c('scalar_asm_rv') / c('simd_unal_asm_rv'):.2f}x | {c('scalar_asm_rv') / c('simd_al_asm_rv'):.2f}x | {c('scalar_asm_rv') / c('simd_unal_asm_xp'):.2f}x | {c('scalar_asm_rv') / c('simd_al_asm_xp'):.2f}x | {c('simd_unal_asm_rv') / c('simd_unal_asm_xp'):.2f}x | {c('simd_al_asm_rv') / c('simd_al_asm_xp'):.2f}x |")
print()
print("instruction-count ratios, same cells:")
for s in shapes:
    c = lambda k: best(s, k)['instr']
    print(f"  {s}: control {c('scalar_asm_rv') / c('scalar_asm_xp'):.2f}  datapath unal {c('scalar_asm_rv') / c('simd_unal_asm_rv'):.2f}  al {c('scalar_asm_rv') / c('simd_al_asm_rv'):.2f}  both unal {c('scalar_asm_rv') / c('simd_unal_asm_xp'):.2f}  al {c('scalar_asm_rv') / c('simd_al_asm_xp'):.2f}")
print("\nalignment spread per kernel (max over shapes):")
for k in names: print(f"  {names[k]}: {max(abs(P[0][(s, k)]['cycles'] - P[1][(s, k)]['cycles']) / min(P[0][(s, k)]['cycles'], P[1][(s, k)]['cycles']) for s in shapes):.1%}")
print("\nmax |model residual| over all runs:", f"{max(abs(v['resid']) / v['cycles'] for p in (0, 1) for v in P[p].values()):.1%}")
