#!/usr/bin/env python3
"""Reviewer question Q2: how much do the 5x5 Shapley values depend on the scalar baseline?
The three features (datapath = SIMD dot product, control = hardware loops and post-increment,
clip) over the full 2^3 grid, exactly as clip_model.py computes them, with the scalar corner of
the grid taken from either 5x5 hand kernel: row-wise (dwconv5_asm.c, the first baseline) or
output-stationary (dwconv5_os_asm.c, the paper's baseline). The SIMD corner is the same kernel
family either way. Every cell at its better code alignment. Run from results/."""
import csv, collections, itertools, math
def load(fn):
    d = collections.defaultdict(dict)
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')): d[(r['shape'], r['kernel'])][r['event']] = int(r['value'])
    return d
def both(base): return [load(f'{base}_pad{p}.csv') for p in (0, 1)]
DS = {}
for b in ('wait0_dw5', 'wait0_clip_dw5', 'wait0_dw5os'):
    for p, d in enumerate(both(b)):
        for k, v in d.items(): DS.setdefault(k, []).append(v['cycles'])
cyc = lambda s, k: min(DS[(s, k)])
def shapley(c):
    val = lambda S: math.log(c[(0, 0, 0)] / c[S]); out = []
    for i in range(3):
        tot = 0.0
        for perm in itertools.permutations(range(3)):
            S = [0, 0, 0]
            for j in perm[:perm.index(i)]: S[j] = 1
            S0 = tuple(S); S[i] = 1; tot += val(tuple(S)) - val(S0)
        out.append(math.exp(tot / 6))
    return out
SIMD = {(0, 0): 'dw5_simd_rv', (1, 0): 'dw5_simd_xp', (0, 1): 'dw5_simd_rv_clip', (1, 1): 'dw5_simd_xp_clip'}
BASE = {'row-wise': {(0, 0): 'dw5_asm_rv', (1, 0): 'dw5_asm_xp', (0, 1): 'dw5_asm_rv_clip', (1, 1): 'dw5_asm_xp_clip'},
        'output-stationary': {(0, 0): 'dw5_os_asm_rv', (1, 0): 'dw5_os_asm_xp', (0, 1): 'dw5_os_asm_rv_clip', (1, 1): 'dw5_os_asm_xp_clip'}}
print("| shape | scalar baseline | baseline cycles | full speedup | Shapley: datapath | control | clip | added first: control | clip | added last: control | clip |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for s in ['8x16x16', '16x16x16', '8x32x32', '32x8x8']:
    for bname, sc in BASE.items():
        c = {(0, ct, cl): cyc(s, sc[(ct, cl)]) for ct in (0, 1) for cl in (0, 1)}
        c.update({(1, ct, cl): cyc(s, SIMD[(ct, cl)]) for ct in (0, 1) for cl in (0, 1)})
        sh = shapley(c)
        print(f"| {s} | {bname} | {c[(0,0,0)]:,} | {c[(0,0,0)]/c[(1,1,1)]:.2f}x | {sh[0]:.2f}x | {sh[1]:.2f}x | {sh[2]:.2f}x | "
              f"{c[(0,0,0)]/c[(0,1,0)]:.2f}x | {c[(0,0,0)]/c[(0,0,1)]:.2f}x | {c[(1,0,1)]/c[(1,1,1)]:.2f}x | {c[(1,1,0)]/c[(1,1,1)]:.2f}x |")
print("\nClip ranks above control in the Shapley value when the clip column exceeds the control column.")
