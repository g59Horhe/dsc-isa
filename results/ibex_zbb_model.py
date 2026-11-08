#!/usr/bin/env python3
"""Zbb on Ibex (review round R4, 2026-10-31): the standard Zbb max and min on a core that has them.
Ibex built with RV32B=1 (RV32BBalanced, which includes Zbb) runs the RV32IMC hand scalar kernels of the three
families with the branch-free saturation and with srai; max; min (-DREQUANT_ZBB=1 -DZBB_STD=1, the standard
encodings; bounds in registers as on CV32E40P), both pipelines, both alignments, synthetic and real data.
Collector sets wait0_ibex{2,3}b_{bf,zbb}{,_real}_{dw3,dw5os,pw}_pad{0,1}.csv. Checks: the RV32B=1 core runs the
branch-free binaries in the cycles of the committed RV32B=0 runs (wait0_ibex{2,3}_*); every Zbb checksum equals
the branch-free one (real data clamp). Area: syn/ibex/wb{0,1}{,b}/stat.json. Run from results/."""
import csv, collections, json, os, subprocess
def load(fn):
    d = collections.defaultdict(dict)
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d[(r['shape'], r['kernel'])][r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    return d
DW = ['8x16x16', '16x16x16', '8x32x32', '32x8x8']; PW = ['16x16x8x8', '8x8x16x16', '16x32x8x8', '16x16x16x16']
FAM = [('3x3', 'dw3', 'scalar_asm_rv', DW, lambda c, h, w: c * (h - 2) * (w - 2), 'dw3'), ('5x5', 'dw5os', 'dw5_os_asm_rv', DW, lambda c, h, w: c * (h - 4) * (w - 4), None),
       ('1x1', 'pw', 'pw_asm_rv', PW, lambda ci, co, h, w: co * h * w, 'pw')]
best = lambda sets, s, k: min(sets[p][(s, k)]['cycles'] for p in (0, 1))
print('# Zbb on Ibex\n')
same = bad = 0
for core, ref in (('ibex2b', 'ibex2'), ('ibex3b', 'ibex3')):
    print(f'\n## {core} (RV32B=1), cycles at the better alignment\n')
    print('| kernel | shape | branch-free | Zbb | saved per output | speedup | data |\n|---|---|---|---|---|---|---|')
    for fam, tag, k, shapes, nout, real in FAM:
        for data in ('syn',) + (('real',) if real else ()):
            sfx = '_real' if data == 'real' else ''
            B = [load(f'wait0_{core}_bf{sfx}_{tag}_pad{p}.csv') for p in (0, 1)]; Z = [load(f'wait0_{core}_zbb{sfx}_{tag}_pad{p}.csv') for p in (0, 1)]
            if data == 'syn':   # the RV32B=1 core against the committed RV32B=0 runs of the same binaries
                R = [load(f'wait0_{ref}_{tag}_pad{p}.csv') for p in (0, 1)]
                for p in (0, 1):
                    for s in shapes:
                        same += B[p][(s, k)]['cycles'] == R[p][(s, k)]['cycles']; bad += B[p][(s, k)]['cycles'] != R[p][(s, k)]['cycles']
            for s in shapes:
                for p in (0, 1): bad += Z[p][(s, k)]['chk'] != B[p][(s, k)]['chk']
                b, z = best(B, s, k), best(Z, s, k); n = nout(*map(int, s.split('x')))
                print(f'| {fam} | {s} | {b:,} | {z:,} | {(b - z) / n:.2f} | {b / z:.2f}x | {data} |')
print(f'\nbranch-free binaries on RV32B=1 against RV32B=0: {same} runs identical in cycles; mismatches (cycles or Zbb checksums): {bad}')
def ge(path):
    if not os.path.exists(path): return None
    out = subprocess.run(['python3', '../syn/area.py', path, '3.7536'], capture_output=True, text=True).stdout
    for l in out.splitlines():
        if 'NAND2' in l or 'GE' in l: return l.strip()
    return out.splitlines()[0] if out else None
print('\n## Area, Sky130 HD, synthesis (yosys), same flow as the RV32B=0 cores\n')
import re
for wb, lab in (('wb0', '2-stage'), ('wb1', '3-stage')):
    a0, a1 = ge(f"../syn/ibex/{wb}/stat.json"), ge(f"../syn/ibex/{wb}b/stat.json")
    g0, g1 = (int(re.search(r'([\d,]+)\s*$', x)[1].replace(',', '')) for x in (a0, a1))
    print(f'{lab} ({wb}): RV32B=0 {g0:,} GE; RV32B=1 {g1:,} GE; the bitmanip option adds {g1 - g0:,} GE, {(g1 - g0) / g0:.1%}')
