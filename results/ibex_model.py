#!/usr/bin/env python3
"""Second core: lowRISC Ibex (RV32IMC, single-cycle multiplier, FF register
file; 2-stage and 3-stage pipelines) running the same scalar binaries as
CV32E40P. Compares cycles, checks instruction counts are identical, measures
baseline-flag and code-alignment sensitivity on each core, and fits a cycle
model from Ibex's counters (minstret, data-side wait, instruction-side wait,
loads, stores, branches, taken branches, compressed). Run from results/."""
import csv, collections, itertools
def load(fn, ibex):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v['ev1']; v['brtaken'] = v['ev9']; v['loads'] = v['ev5']; v['stores'] = v['ev6'] - 1 if 'ev6' in v else v['dwrite']   # the harness window includes the stop-marker store
        if ibex: v['dwait'] = v['ev2']; v['iwait'] = v['ev4']; v['br'] = v['ev8']; v['comp'] = v['ev10']
        else: v['ldstall'] = v['ev2']
    return d
# kernel -> (CV32E40P dataset, kernel name, Ibex dataset tag); the first three are -O2, -O3, hand; for 5x5 the hand
# kernel is the output-stationary one (the paper's baseline), and the row-wise kernel follows as a fourth entry
fams = [('3x3 depthwise', {'scalar_O2': ('wait0_eqrequant', 'scalar_O2', 'dw3'), 'scalar_O3': ('wait0_eqrequant', 'scalar_O3', 'dw3'), 'scalar_asm_rv': ('wait0_decomp', 'scalar_asm_rv', 'dw3')}),
        ('5x5 depthwise', {'dw5_C_O2': ('wait0_dw5', 'dw5_C_O2', 'dw5'), 'dw5_C_O3': ('wait0_dw5', 'dw5_C_O3', 'dw5'), 'dw5_os_asm_rv': ('wait0_dw5os', 'dw5_os_asm_rv', 'dw5os'), 'dw5_asm_rv': ('wait0_dw5', 'dw5_asm_rv', 'dw5')}),
        ('1x1 pointwise', {'pw_C_O2': ('wait0_pw', 'pw_C_O2', 'pw'), 'pw_C_O3': ('wait0_pw', 'pw_C_O3', 'pw'), 'pw_asm_rv': ('wait0_pw', 'pw_asm_rv', 'pw')})]
names = {'scalar_O2': 'C -O2', 'scalar_O3': 'C -O3', 'scalar_asm_rv': 'hand asm', 'dw5_C_O2': 'C -O2', 'dw5_C_O3': 'C -O3', 'dw5_os_asm_rv': 'hand asm, output-stationary', 'dw5_asm_rv': 'hand asm, row-wise', 'pw_C_O2': 'C -O2', 'pw_C_O3': 'C -O3', 'pw_asm_rv': 'hand asm'}
def gather(kmap):
    I2, I3, CV = {0: {}, 1: {}}, {0: {}, 1: {}}, {0: {}, 1: {}}
    for k, (base, ck, tag) in kmap.items():
        for p in (0, 1):
            for D, fn, ib in ((CV, f'{base}_pad{p}.csv', False), (I2, f'wait0_ibex2_{tag}_pad{p}.csv', True), (I3, f'wait0_ibex3_{tag}_pad{p}.csv', True)):
                for (s, kk), v in load(fn, ib).items():
                    if kk == ck: D[p][(s, k)] = v
    shapes = []; [shapes.append(s) for (s, _) in I2[0] if s not in shapes]
    return I2, I3, CV, shapes
allrows = {'ibex2': [], 'ibex3': []}; mism = 0
print("| kernel | shape | instructions | CV32E40P cycles | Ibex 2-stage cycles | Ibex 3-stage cycles | Ibex2 / CV | Ibex3 / CV | alignment spread CV / Ibex2 / Ibex3 |")
print("|---|---|---|---|---|---|---|---|---|")
for fam, kmap in fams:
    I2, I3, CV, shapes = gather(kmap)
    for s in shapes:
        for k in kmap:
            cv = [CV[p][(s, k)] for p in (0, 1)]; i2 = [I2[p][(s, k)] for p in (0, 1)]; i3 = [I3[p][(s, k)] for p in (0, 1)]
            if not (cv[0]['instr'] == i2[0]['instr'] == i3[0]['instr']): mism += 1
            if not (cv[0]['chk'] == i2[0]['chk'] == i3[0]['chk']): mism += 100
            b = lambda L: min(x['cycles'] for x in L); sp = lambda L: abs(L[0]['cycles'] - L[1]['cycles']) / b(L)
            print(f"| {fam}, {names[k]} | {s} | {cv[0]['instr']:,} | {b(cv):,} | {b(i2):,} | {b(i3):,} | {b(i2)/b(cv):.2f} | {b(i3)/b(cv):.2f} | {sp(cv):.1%} / {sp(i2):.1%} / {sp(i3):.1%} |")
            for p in (0, 1): allrows['ibex2'].append(i2[p]); allrows['ibex3'].append(i3[p])
print(f"\ninstruction-count or checksum mismatches between cores: {mism}")
# -O2/-O3 and hand asm on each core
print("\n| kernel | shape | -O2 / -O3: CV32E40P | Ibex2 | Ibex3 | -O3 / hand asm: CV32E40P | Ibex2 | Ibex3 |")
print("|---|---|---|---|---|---|---|---|")
for fam, kmap in fams:
    I2, I3, CV, shapes = gather(kmap)
    ks = list(kmap)
    for hand, label in ((ks[2], fam),) + (((ks[3], fam + ', row-wise hand'),) if len(ks) > 3 else ()):
        for s in shapes:
            r = []
            for D in (CV, I2, I3):
                b = lambda k: min(D[p][(s, k)]['cycles'] for p in (0, 1)); r.append((b(ks[0]) / b(ks[1]), b(ks[1]) / b(hand)))
            print(f"| {label} | {s} | {r[0][0]:.2f}x | {r[1][0]:.2f}x | {r[2][0]:.2f}x | {r[0][1]:.2f}x | {r[1][1]:.2f}x | {r[2][1]:.2f}x |")
# cycle model fit for Ibex: least squares cycles = instr + a*dwait + b*iwait + c*brtaken + d*(loads+stores)
def lstsq(X, y, cyc):
    import numpy as np
    A = np.array(X, float); b = np.array(y, float); c = np.array(cyc, float); coef, *_ = np.linalg.lstsq(A, b, rcond=None); pred = A @ coef
    ss = ((b - pred) ** 2).sum(); tot = ((b - b.mean()) ** 2).sum(); return coef, 1 - ss / tot, max(abs(b - pred) / c)
try:
    import numpy
    for v in ('ibex2', 'ibex3'):
        rows = allrows[v]; y = [r['cycles'] - r['instr'] for r in rows]
        X = [[r['dwait'], r['iwait'], r['brtaken']] for r in rows]
        coef, R2, worst = lstsq(X, y, [r['cycles'] for r in rows])
        print(f"\n{v}: least squares, cycles - instructions = {coef[0]:.2f} x data-side wait + {coef[1]:.2f} x instruction-side wait + {coef[2]:.2f} x taken branches   (R^2 of the stall part {R2:.4f}, worst |residual| {worst*100:.1f}% of cycles, {len(rows)} runs)")
        for name, f in [("instr + dwait + iwait", lambda r: r['instr'] + r['dwait'] + r['iwait']),
                        ("instr + dwait + 2 x taken branches", lambda r: r['instr'] + r['dwait'] + 2 * r['brtaken']),
                        ("instr + dwait + taken branches + 0.35 x iwait", lambda r: r['instr'] + r['dwait'] + r['brtaken'] + 0.35 * r['iwait']),
                        ("instr + dwait + 1.5 x taken branches", lambda r: r['instr'] + r['dwait'] + 1.5 * r['brtaken'])]:
            err = [(r['cycles'] - f(r)) / r['cycles'] for r in rows]
            print(f"  fixed form cycles = {name}: max |error| {max(abs(e) for e in err)*100:.1f}%, mean {sum(abs(e) for e in err)/len(err)*100:.1f}%, mean signed {sum(err)/len(err)*100:+.1f}%")
except ImportError:
    print("numpy not available for the fit; run with ~/tools/venv/bin/python")
