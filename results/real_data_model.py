#!/usr/bin/env python3
"""Real MobileNetV1 data vs synthetic LCG data through the identical REAL_DATA
code path (uint8 activations, int8 weights, shift from the real layer,
clamp 0..255). Verifies checksums against sw/real/*.h and compares cycles
run by run. Run from results/."""
import csv, collections, re, glob
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']) if r['value'].isdigit() else r['value']; d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    return d
expected = {}
for h in glob.glob('../sw/real/*.h'):
    m = re.search(r'/(syn_)?(dw3|pw)_([0-9x]+)\.h$', h)
    if m is None: continue   # block_*.h is not a single-layer source
    c = re.search(r'#define REAL_CHECKSUM (\d+)', open(h).read())
    expected[(('syn_' if m[1] else 'real_') + m[2], m[3])] = int(c[1])
names = {'scalar_O3': 'scalar C -O3', 'scalar_asm_rv': 'scalar asm, RV32IMC ctrl', 'scalar_asm_xp': 'scalar asm, Xpulp ctrl', 'simd_unal_asm_rv': 'SIMD unaligned asm, RV32IMC ctrl',
         'simd_unal_asm_xp': 'SIMD unaligned asm, Xpulp ctrl', 'simd_al_asm_rv': 'SIMD aligned asm, RV32IMC ctrl', 'simd_al_asm_xp': 'SIMD aligned asm, Xpulp ctrl',
         'pw_C_O3': 'scalar C -O3', 'pw_asm_rv': 'scalar asm, RV32IMC ctrl', 'pw_asm_xp': 'scalar asm, Xpulp ctrl', 'pw_simd_asm_rv': 'SIMD asm, RV32IMC ctrl', 'pw_simd_asm_xp': 'SIMD asm, Xpulp ctrl'}
bad = 0; rows = []
for fam, title in (('dw3', 'Depthwise 3x3, MobilenetV1 Conv2d_3_depthwise, shift 4'), ('pw', 'Pointwise 1x1, MobilenetV1 Conv2d_1_pointwise, shift 5')):
    R = {p: load(f'wait0_real_{fam}_pad{p}.csv') for p in (0, 1)}; Y = {p: load(f'wait0_syn_{fam}_pad{p}.csv') for p in (0, 1)}
    print(f"\n### {title}\n")
    print("| shape | kernel | cycles, real data (pad 0 / pad 1) | cycles, synthetic data, same code | difference | checksum real / expected | checksum synthetic / expected |")
    print("|---|---|---|---|---|---|---|")
    for k in R[0]:
        s, kn = k; er = expected[('real_' + fam, s)]; ey = expected[('syn_' + fam, s)]
        cr = (R[0][k]['cycles'], R[1][k]['cycles']); cy = (Y[0][k]['cycles'], Y[1][k]['cycles'])
        okr = int(R[0][k]['chk']) == er and int(R[1][k]['chk']) == er; oky = int(Y[0][k]['chk']) == ey and int(Y[1][k]['chk']) == ey
        bad += (not okr) + (not oky) + (cr != cy)
        print(f"| {s} | {names[kn]} | {cr[0]:,} / {cr[1]:,} | {cy[0]:,} / {cy[1]:,} | {cr[0]-cy[0]:+d} / {cr[1]-cy[1]:+d} | {R[0][k]['chk']} / {er} {'ok' if okr else 'MISMATCH'} | {Y[0][k]['chk']} / {ey} {'ok' if oky else 'MISMATCH'} |")
print(f"\nmismatches (checksum or cycle difference): {bad}")
# compare real-mode cycles with the signed-int8 synthetic runs: the only code difference is the 8- vs 9-instruction requant
D3 = {p: load(f'wait0_decomp_pad{p}.csv') for p in (0, 1)}; E3 = {p: load(f'wait0_eqrequant_pad{p}.csv') for p in (0, 1)}; P1 = {p: load(f'wait0_pw_pad{p}.csv') for p in (0, 1)}
R3 = load('wait0_real_dw3_pad0.csv'); R1 = load('wait0_real_pw_pad0.csv')
print("\n### Real-data cycles against the signed-int8 synthetic runs (pad 0): the real-data clamp is one instruction shorter per output\n")
print("| shape | kernel | int8 synthetic cycles | real-data cycles | difference | outputs | difference per output |")
print("|---|---|---|---|---|---|---|")
for (s, k), v in R3.items():
    ch, h, w = map(int, s.split('x')); n = ch * (h - 2) * (w - 2)
    base = E3[0][(s, k)]['cycles'] if k == 'scalar_O3' else D3[0][(s, k)]['cycles']
    print(f"| {s} | {names[k]} | {base:,} | {v['cycles']:,} | {v['cycles']-base:+,} | {n:,} | {(v['cycles']-base)/n:+.2f} |")
for (s, k), v in R1.items():
    ci, co, h, w = map(int, s.split('x')); n = co * h * w; base = P1[0][(s, k)]['cycles']
    print(f"| {s} | {names[k]} | {base:,} | {v['cycles']:,} | {v['cycles']-base:+,} | {n:,} | {(v['cycles']-base)/n:+.2f} |")
