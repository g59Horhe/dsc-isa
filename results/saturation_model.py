#!/usr/bin/env python3
"""The baseline's saturation idiom and optimisation level (review round R, 2026-10-30).
Three sets beside the committed grid, from the same kernels built with -DREQUANT_ZBB=1, -DREQUANT_BRANCH=1 or -Os
(sw/requant.h documents the two modes):
  wait0_zbb_{dw3,dw5,pw} and wait0_zbb_real_{dw3,pw}: a Zbb-style srai; max; min saturation in every hand kernel, with
    Xpulp's cv.max and cv.min (32-bit, one cycle, as Zbb's) and the bounds in registers, synthetic and real data;
  wait0_branch_{dw3,dw5,pw} and wait0_branch_real_{dw3,pw}: a not-taken-branch fast path with the clamp out of line,
    RV32IMC-control hand kernels only (hardware-loop bodies may not branch), synthetic and real data;
  wait0_Os_{dw,pw}: the C kernels at -Os.
Tables: the Shapley grid with Zbb in the non-clip cells, the branchy cells, and -Os against -O2, -O3 and the hand kernels.
Run from results/."""
import csv, collections, itertools, math, os, sys
R = os.path.dirname(os.path.abspath(__file__)); M = R
def load(fn):
    d = collections.defaultdict(dict)
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        if r['value'] in ('BUILDFAIL', 'RUNFAIL', 'HWLOOPFAIL') or 'FAIL' in r['value']: raise SystemExit(f'FAIL in {fn}: {r}')
        d[(r['shape'], r['kernel'])][r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    return d
def sets(base, where):   # -> {(shape,kernel): [(cycles, chk) per pad]}
    out = collections.defaultdict(list)
    for p in (0, 1):
        for k, v in load(f'{where}/{base}_pad{p}.csv').items(): out[k].append((v['cycles'], v['chk'], v.get('ev1')))
    return out
C = {}   # committed
for b in ('wait0_decomp', 'wait0_clip_dw3', 'wait0_dw5', 'wait0_clip_dw5', 'wait0_dw5os', 'wait0_pw', 'wait0_clip_pw', 'wait0_eqrequant',
          'wait0_real_dw3', 'wait0_clip_real_dw3', 'wait0_real_pw', 'wait0_clip_real_pw'):
    C[b] = sets(b, R)
N = {}
for b, f in (('zbb_dw3', 'wait0_zbb_dw3'), ('zbb_dw5', 'wait0_zbb_dw5'), ('zbb_pw', 'wait0_zbb_pw'), ('zbb_real_dw3', 'wait0_zbb_real_dw3'), ('zbb_real_pw', 'wait0_zbb_real_pw'), ('br_dw3', 'wait0_branch_dw3'), ('br_dw5', 'wait0_branch_dw5'), ('br_pw', 'wait0_branch_pw'),
             ('br_real_dw3', 'wait0_branch_real_dw3'), ('br_real_pw', 'wait0_branch_real_pw'), ('Os_dw', 'wait0_Os_dw'), ('Os_pw', 'wait0_Os_pw')):
    if os.path.exists(f'{M}/{f}_pad0.csv') and os.path.exists(f'{M}/{f}_pad1.csv'): N[b] = sets(f, M)
best = lambda d, s, k: min(c for c, _, _ in d[(s, k)])
instr = lambda d, s, k: min(d[(s, k)], key=lambda x: x[0])[2]
def chk_ok(new, ref, s, k, kref=None):
    a = {c for _, c, _ in new[(s, k)]}; b = {c for _, c, _ in ref[(s, kref or k)]}
    return a == b
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
DW = ['8x16x16', '16x16x16', '8x32x32', '32x8x8']; PW = ['16x16x8x8', '8x8x16x16', '16x32x8x8', '16x16x16x16']
nout = {'3x3': lambda s: (lambda c, h, w: c * (h - 2) * (w - 2))(*map(int, s.split('x'))), '5x5': lambda s: (lambda c, h, w: c * (h - 4) * (w - 4))(*map(int, s.split('x'))),
        'pw': lambda s: (lambda ci, co, h, w: co * h * w)(*map(int, s.split('x')))}
# family: (shapes, nofilter-set, clip-set, zbb-set, br-set, scalar_rv, scalar_xp, simd_rv, simd_xp, suffix for clip kernels)
FAM = {'3x3': (DW, 'wait0_decomp', 'wait0_clip_dw3', 'zbb_dw3', 'br_dw3', 'scalar_asm_rv', 'scalar_asm_xp', 'simd_unal_asm_rv', 'simd_unal_asm_xp', '_clip'),
       '5x5': (DW, 'wait0_dw5os', 'wait0_dw5os', 'zbb_dw5', 'br_dw5', 'dw5_os_asm_rv', 'dw5_os_asm_xp', 'dw5_simd_rv', 'dw5_simd_xp', '_clip'),
       'pw': (PW, 'wait0_pw', 'wait0_clip_pw', 'zbb_pw', 'br_pw', 'pw_asm_rv', 'pw_asm_xp', 'pw_simd_asm_rv', 'pw_simd_asm_xp', '_clip')}
def cell(fam, s, feat, sat):   # feat=(dp, ctl); sat in 'bf','clip','zbb','br'
    shapes, nf, cl, zb, br, srv, sxp, drv, dxp, suf = FAM[fam]
    k = [[srv, sxp], [drv, dxp]][feat[0]][feat[1]]
    if sat == 'bf':
        d = C['wait0_dw5'] if (fam == '5x5' and feat[0]) else C[nf]; return best(d, s, k)
    if sat == 'clip':
        d = C['wait0_clip_dw5'] if (fam == '5x5' and feat[0]) else C[cl]; return best(d, s, k + suf)
    if sat == 'zbb': return best(N[zb], s, k)
    if sat == 'br': return best(N[br], s, k)
print('# Saturation idiom and -Os\n')
if 'zbb_dw3' in N:
    # checksums
    bad = []
    for fam, (shapes, nf, cl, zb, br, srv, sxp, drv, dxp, suf) in FAM.items():
        for s in shapes:
            for k in (srv, sxp, drv, dxp):
                ref = C['wait0_dw5'] if (fam == '5x5' and k.startswith('dw5_simd')) else C[nf]
                if not chk_ok(N[zb], ref, s, k): bad.append((fam, s, k))
    print(f'Zbb cells: checksums equal the committed branch-free cells: {"all" if not bad else bad}\n')
    print('## A. Zbb-style saturation (srai; cv.max; cv.min = 3 instructions, bounds in registers) as the saturation of every non-clip cell\n')
    print('| kernel | shape | scalar bf | scalar Zbb | scalar clip | full Xpulp | vs bf | vs Zbb | Shapley (Zbb grid): dp | ctl | clip over Zbb | bf->Zbb added first | Zbb->clip added last |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for fam, (shapes, *_ ) in FAM.items():
        for s in shapes:
            g = {(dp, ct, cl): cell(fam, s, (dp, ct), 'clip' if cl else 'zbb') for dp in (0, 1) for ct in (0, 1) for cl in (0, 1)}
            sh = shapley(g); bf = cell(fam, s, (0, 0), 'bf'); z = g[(0, 0, 0)]; full = g[(1, 1, 1)]
            print(f"| {fam} | {s} | {bf:,} | {z:,} | {g[(0,0,1)]:,} | {full:,} | {bf/full:.2f}x | {z/full:.2f}x | {sh[0]:.2f}x | {sh[1]:.2f}x | {sh[2]:.2f}x | {bf/z:.2f}x | {g[(1,1,0)]/full:.2f}x |")
    print('\nPer output, Zbb against branch-free, scalar RV32IMC-control cell (cycles per output saved; 6 instructions per output, less\n'
          'one li of the upper bound per asm block, which is once per output row, and one per output in the C row tails of the\n'
          '3x3 kernels at width 16):')
    for fam, (shapes, *_ ) in FAM.items():
        print(' ', fam, [round((cell(fam, s, (0,0), 'bf') - cell(fam, s, (0,0), 'zbb')) / nout[fam](s), 2) for s in shapes])
if 'zbb_real_dw3' in N:
    print('\n## A2. Zbb-style saturation on real MobileNetV1 data (the clamp is exercised: 40 to 65% of outputs at 0, up to 7% at 255)\n')
    print('| kernel | shape | scalar bf (real) | scalar Zbb (real) | saved / output | full Xpulp (real) | speedup vs bf | vs Zbb | checksum |')
    print('|---|---|---|---|---|---|---|---|---|')
    for fam, rs, rc, zs, srv, dxp in (('3x3', 'wait0_real_dw3', 'wait0_clip_real_dw3', 'zbb_real_dw3', 'scalar_asm_rv', 'simd_unal_asm_xp_clip'),
                                      ('pw', 'wait0_real_pw', 'wait0_clip_real_pw', 'zbb_real_pw', 'pw_asm_rv', 'pw_simd_asm_xp_clip')):
        for s in FAM[fam][0]:
            bf = best(C[rs], s, srv); z = best(N[zs], s, srv); full = best(C[rc], s, dxp)
            ok = all(chk_ok(N[zs], C[rs], s, k) for k in {kk for (ss, kk) in N[zs] if ss == s})
            print(f"| {fam} | {s} | {bf:,} | {z:,} | {(bf-z)/nout[fam](s):.2f} | {full:,} | {bf/full:.2f}x | {z/full:.2f}x | {'equal, all cells' if ok else 'DIFFERS'} |")
if 'br_dw3' in N:
    bad = []
    for fam, (shapes, nf, cl, zb, br, srv, sxp, drv, dxp, suf) in FAM.items():
        for s in shapes:
            for k in (srv, drv):
                ref = C['wait0_dw5'] if (fam == '5x5' and k.startswith('dw5_simd')) else C[nf]
                if not chk_ok(N[br], ref, s, k): bad.append((fam, s, k))
    print(f'\nBranchy cells, synthetic: checksums equal the committed cells: {"all" if not bad else bad}\n')
    print('## B. Not-taken-branch saturation in the RV32IMC-control hand kernels, synthetic data (never saturates)\n')
    print('| kernel | shape | scalar bf | scalar branchy | saved / output | SIMD rv bf | SIMD rv branchy | full Xpulp | speedup vs bf scalar | vs branchy scalar |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for fam, (shapes, *_ ) in FAM.items():
        for s in shapes:
            bf = cell(fam, s, (0,0), 'bf'); b = cell(fam, s, (0,0), 'br'); sbf = cell(fam, s, (1,0), 'bf'); sb = cell(fam, s, (1,0), 'br'); full = cell(fam, s, (1,1), 'clip')
            print(f"| {fam} | {s} | {bf:,} | {b:,} | {(bf-b)/nout[fam](s):.2f} | {sbf:,} | {sb:,} | {full:,} | {bf/full:.2f}x | {b/full:.2f}x |")
if 'br_real_dw3' in N:
    print('\n## C. The same on real MobileNetV1 data (40 to 65% of outputs take the zero clamp)\n')
    print('| kernel | shape | scalar bf (real) | scalar branchy (real) | cost / output | SIMD rv bf | SIMD rv branchy | full Xpulp (real) | speedup vs bf | vs branchy | checksum |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for fam, rs, rc, brs, srv, drv, dxp in (('3x3', 'wait0_real_dw3', 'wait0_clip_real_dw3', 'br_real_dw3', 'scalar_asm_rv', 'simd_unal_asm_rv', 'simd_unal_asm_xp_clip'),
                                            ('pw', 'wait0_real_pw', 'wait0_clip_real_pw', 'br_real_pw', 'pw_asm_rv', 'pw_simd_asm_rv', 'pw_simd_asm_xp_clip')):
        for s in FAM[fam][0]:
            bf = best(C[rs], s, srv); b = best(N[brs], s, srv); sbf = best(C[rs], s, drv); sb = best(N[brs], s, drv); full = best(C[rc], s, dxp)
            ok = chk_ok(N[brs], C[rs], s, srv) and chk_ok(N[brs], C[rs], s, drv)
            print(f"| {fam} | {s} | {bf:,} | {b:,} | {(b-bf)/nout[fam](s):+.2f} | {sbf:,} | {sb:,} | {full:,} | {bf/full:.2f}x | {b/full:.2f}x | {'equal' if ok else 'DIFFERS'} |")
if 'Os_dw' in N:
    print('\n## D. -Os baselines (GCC 16.1), all shapes, better alignment\n')
    print('| kernel | shape | -O2 | -Os | -O3 | hand | -Os/-O3 | -O2/-Os | hand vs -Os | SIMD C -Os | SIMD C -O2 |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    E = C['wait0_eqrequant']; D5 = C['wait0_dw5']; P = C['wait0_pw']
    for s in DW:
        o2, o3, h = best(E, s, 'scalar_O2'), best(E, s, 'scalar_O3'), best(E, s, 'scalar_asm'); os_ = best(N['Os_dw'], s, 'scalar_Os')
        print(f"| 3x3 | {s} | {o2:,} | {os_:,} | {o3:,} | {h:,} | {os_/o3:.2f}x | {o2/os_:.2f}x | {os_/h:.2f}x | unal {best(N['Os_dw'], s, 'simd_unal_Os'):,} / al {best(N['Os_dw'], s, 'simd_al_Os'):,} | {best(E, s, 'simd_unal'):,} / {best(E, s, 'simd_al'):,} |")
    for s in DW:
        o2, o3, h = best(D5, s, 'dw5_C_O2'), best(D5, s, 'dw5_C_O3'), best(C['wait0_dw5os'], s, 'dw5_os_asm_rv'); os_ = best(N['Os_dw'], s, 'dw5_C_Os')
        print(f"| 5x5 | {s} | {o2:,} | {os_:,} | {o3:,} | {h:,} | {os_/o3:.2f}x | {o2/os_:.2f}x | {os_/h:.2f}x | | |")
    for s in PW:
        o2, o3, h = best(P, s, 'pw_C_O2'), best(P, s, 'pw_C_O3'), best(P, s, 'pw_asm_rv'); os_ = best(N['Os_pw'], s, 'pw_C_Os')
        print(f"| pw | {s} | {o2:,} | {os_:,} | {o3:,} | {h:,} | {os_/o3:.2f}x | {o2/os_:.2f}x | {os_/h:.2f}x | {best(N['Os_pw'], s, 'pw_simd_C_Os'):,} | {best(P, s, 'pw_simd_C_O2'):,} |")
    bad = [(s, k) for s in DW for k in ('scalar_Os',) if not chk_ok(N['Os_dw'], E, s, k, 'scalar_O3')] + [(s, 'dw5_C_Os') for s in DW if not chk_ok(N['Os_dw'], D5, s, 'dw5_C_Os', 'dw5_C_O3')] + [(s, 'pw_C_Os') for s in PW if not chk_ok(N['Os_pw'], P, s, 'pw_C_Os', 'pw_C_O3')]
    print(f'\n-Os checksums equal the -O3 ones: {"all" if not bad else bad}')
