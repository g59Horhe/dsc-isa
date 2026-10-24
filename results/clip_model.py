#!/usr/bin/env python3
"""Clip requantisation (cv.clip / cv.clipu) added to the decomposition: for each
kernel family, the Xpulp speedup split into datapath (cv.dotsp.b), control
(hardware loop + post-increment), and saturation (cv.clip), from
results/wait0_{decomp,pw,dw5}_pad{0,1}.csv and results/wait0_clip_*_pad{0,1}.csv.
Run from results/."""
import csv, collections, glob, re
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v['ev1']; v['ldstall'] = v['ev2']; v['loads'] = v['ev5']; v['brtaken'] = v['ev9']
        v['split'] = v['dread'] - v['loads']; v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['resid'] = v['cycles'] - v['pred']
    return d
def merge(*fns):
    out = [collections.OrderedDict(), collections.OrderedDict()]
    for base in fns:
        for p in (0, 1): out[p].update(load(f'{base}_pad{p}.csv'))
    return out
fam = {
 '3x3 depthwise': (merge('wait0_decomp', 'wait0_clip_dw3'), 'scalar_asm_rv', 'scalar_asm_xp', 'simd_unal_asm_rv', 'simd_unal_asm_xp', 'simd_unal_asm_rv_clip', 'simd_unal_asm_xp_clip', 'scalar_asm_rv_clip', 'scalar_asm_xp_clip', lambda s: (lambda c, h, w: c * (h - 2) * (w - 2))(*map(int, s.split('x'))), 'wait0_eqrequant', 'scalar_O3'),
 '5x5 depthwise': (merge('wait0_dw5', 'wait0_clip_dw5'), 'dw5_asm_rv', 'dw5_asm_xp', 'dw5_simd_rv', 'dw5_simd_xp', 'dw5_simd_rv_clip', 'dw5_simd_xp_clip', 'dw5_asm_rv_clip', 'dw5_asm_xp_clip', lambda s: (lambda c, h, w: c * (h - 4) * (w - 4))(*map(int, s.split('x'))), 'wait0_dw5', 'dw5_C_O3'),
 '1x1 pointwise': (merge('wait0_pw', 'wait0_clip_pw'), 'pw_asm_rv', 'pw_asm_xp', 'pw_simd_asm_rv', 'pw_simd_asm_xp', 'pw_simd_asm_rv_clip', 'pw_simd_asm_xp_clip', 'pw_asm_rv_clip', 'pw_asm_xp_clip', lambda s: (lambda ci, co, h, w: co * h * w)(*map(int, s.split('x'))), 'wait0_pw', 'pw_C_O3'),
}
worst = 0; chkbad = 0
for name, (D, s_rv, s_xp, v_rv, v_xp, v_rvc, v_xpc, s_rvc, s_xpc, outs, o3base, o3k) in fam.items():
    O3 = merge(o3base)
    best = lambda s, k: min(D[0][(s, k)], D[1][(s, k)], key=lambda v: v['cycles'])
    shapes = []; [shapes.append(k[0]) for k in D[0] if k[0] not in shapes]
    print(f"\n### {name}\n")
    print("| shape | scalar -O3 | scalar asm | + clip | + hw loop/post-inc | + both | SIMD asm | + clip | + hw loop/post-inc | + both (full Xpulp) | full Xpulp vs -O3 | vs scalar asm | instr ratio vs scalar asm | clip saves per output | model residual, full |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in shapes:
        c = lambda k: best(s, k)['cycles']; o3 = min(O3[0][(s, o3k)]['cycles'], O3[1][(s, o3k)]['cycles'])
        full = best(s, v_xpc); n = outs(s)
        for k in (v_rvc, v_xpc, s_rvc, s_xpc):
            for p in (0, 1):
                v = D[p][(s, k)]; worst = max(worst, abs(v['resid']) / v['cycles'])
                if D[p][(s, k)]['chk'] != D[p][(s, s_rv)]['chk']: chkbad += 1
        print(f"| {s} | {o3:,} | {c(s_rv):,} | {c(s_rvc):,} | {c(s_xp):,} | {c(s_xpc):,} | {c(v_rv):,} | {c(v_rvc):,} | {c(v_xp):,} | {c(v_xpc):,} | {o3/c(v_xpc):.2f}x | {c(s_rv)/c(v_xpc):.2f}x | {best(s, s_rv)['instr']/full['instr']:.2f} | {(c(v_xp)-c(v_xpc))/n:.2f} | {full['resid']/full['cycles']:+.1%} |")
    s0 = shapes[0]; c = lambda k: best(s0, k)['cycles']
    print(f"\n{name}, {s0}, multiplicative decomposition relative to scalar asm (RV32IMC control, branch-free saturation):")
    print(f"  datapath (cv.dotsp.b) alone        {c(s_rv)/c(v_rv):.2f}x")
    print(f"  control alone (scalar)              {c(s_rv)/c(s_xp):.2f}x")
    print(f"  clip alone (scalar)                 {c(s_rv)/c(s_rvc):.2f}x")
    print(f"  SIMD + control                      {c(s_rv)/c(v_xp):.2f}x")
    print(f"  SIMD + clip                         {c(s_rv)/c(v_rvc):.2f}x")
    print(f"  SIMD + control + clip (full Xpulp)  {c(s_rv)/c(v_xpc):.2f}x   = cycles/MAC {c(v_xpc)/ {'3x3 depthwise': 14112, '5x5 depthwise': 28800, '1x1 pointwise': 16384}[name]:.2f}")
    print(f"  clip on top of SIMD + control       {c(v_xp)/c(v_xpc):.2f}x")
print(f"\nmax |model residual| over clip runs: {worst:.1%}; checksum mismatches vs branch-free kernels: {chkbad}")
# real data with clip
try:
    R3 = merge('wait0_clip_real_dw3'); R1 = merge('wait0_clip_real_pw')
    exp = {}
    for h in glob.glob('../sw/real/*.h'):
        m = re.search(r'/(syn_)?(dw3|pw)_([0-9x]+)\.h$', h); c = re.search(r'#define REAL_CHECKSUM (\d+)', open(h).read())
        if not m[1]: exp[(m[2], m[3])] = int(c[1])
    bad = sum(int(v['chk']) != exp[(f, k[0])] for f, R in (('dw3', R3), ('pw', R1)) for p in (0, 1) for k, v in R[p].items())
    print(f"real-data clip runs: {sum(len(R[p]) for R in (R3, R1) for p in (0,1))} runs, checksum mismatches: {bad}")
    for f, R, syn in (('dw3', R3, merge('wait0_clip_dw3')), ('pw', R1, merge('wait0_clip_pw'))):
        diffs = [R[p][k]['cycles'] - syn[p][k]['cycles'] for p in (0, 1) for k in R[p]]
        n = [ (lambda c,h,w: c*(h-2)*(w-2))(*map(int,k[0].split('x'))) if f=='dw3' else (lambda ci,co,h,w: co*h*w)(*map(int,k[0].split('x'))) for p in (0,1) for k in R[p]]
        per = [d / m for d, m in zip(diffs, n)]
        print(f"  {f}: real-data clip cycles minus synthetic clip cycles, per output: min {min(per):+.2f} max {max(per):+.2f} (expected 0 for clip: both modes are 2 instructions)")
except FileNotFoundError as e:
    print("real-data clip files missing:", e)
