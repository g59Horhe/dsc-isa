#!/usr/bin/env python3
"""Clip requantisation (cv.clip / cv.clipu) added to the decomposition: for each
kernel family, the Xpulp speedup split into datapath (cv.dotsp.b), control
(hardware loop + post-increment), and saturation (cv.clip), from
results/wait0_{decomp,pw,dw5}_pad{0,1}.csv and results/wait0_clip_*_pad{0,1}.csv.
All eight cells of the datapath x control x clip grid exist, so the script also
prints the exact Shapley attribution of log-speedup to the three features (the
order-independent split; the product of the three factors is the full speedup),
beside the order-dependent added-first and added-last values, the baseline's
non-instruction cycle share, the cycle model applied to both sides, MACs per
activation word, and the model error over every hand-written run.
Run from results/.  --latex PATH writes the paper's decomposition table; --no-zbb leaves out the Zbb rows (conference version)."""
import csv, collections, glob, re, math, itertools, sys
LATEX = sys.argv[sys.argv.index('--latex') + 1] if '--latex' in sys.argv else None
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for v in d.values():
        v['instr'] = v['ev1']; v['ldstall'] = v['ev2']; v['loads'] = v['ev5']; v['brtaken'] = v['ev9']
        v['split'] = v['dread'] - v['loads']; v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['resid'] = v['cycles'] - v['pred']
    return d
try:   # branch-target alignment term Ba and jump term J, measured per run by results/align_term.py
    ALIGN = {(r['shape'], r['kernel'], int(r['pad'])): int(r['ba']) for r in csv.DictReader(open('wait0_align.csv'))}
    JMP = {(r['shape'], r['kernel'], int(r['pad'])): int(r['jumps']) for r in csv.DictReader(open('wait0_align.csv'))}
except FileNotFoundError:
    ALIGN = {}; JMP = {}
def align(d, p):
    """six-term model: add Ba (redirects whose target is a 32-bit instruction at 2 mod 4) and J (one cycle per jump) when measured"""
    for k, v in d.items():
        v['ba'] = ALIGN.get((k[0], k[1], p), 0); v['j'] = JMP.get((k[0], k[1], p), 0); v['pred'] += v['ba'] + v['j']; v['resid'] = v['cycles'] - v['pred']
    return d
def merge(*fns):
    out = [collections.OrderedDict(), collections.OrderedDict()]
    for base in fns:
        for p in (0, 1): out[p].update(align(load(f'{base}_pad{p}.csv'), p))
    return out
fam = {
 '3x3 depthwise': (merge('wait0_decomp', 'wait0_clip_dw3'), 'scalar_asm_rv', 'scalar_asm_xp', 'simd_unal_asm_rv', 'simd_unal_asm_xp', 'simd_unal_asm_rv_clip', 'simd_unal_asm_xp_clip', 'scalar_asm_rv_clip', 'scalar_asm_xp_clip', lambda s: (lambda c, h, w: c * (h - 2) * (w - 2))(*map(int, s.split('x'))), 'wait0_eqrequant', 'scalar_O3', 3, 14112),
 # 5x5 scalar cells: the output-stationary kernel (sw/dwconv5_os_asm.c), the stronger of the two hand
 # baselines (dw5_os_model.py); the row-wise kernel's cells stay in the CSVs for the comparison.
 '5x5 depthwise': (merge('wait0_dw5', 'wait0_clip_dw5', 'wait0_dw5os'), 'dw5_os_asm_rv', 'dw5_os_asm_xp', 'dw5_simd_rv', 'dw5_simd_xp', 'dw5_simd_rv_clip', 'dw5_simd_xp_clip', 'dw5_os_asm_rv_clip', 'dw5_os_asm_xp_clip', lambda s: (lambda c, h, w: c * (h - 4) * (w - 4))(*map(int, s.split('x'))), 'wait0_dw5', 'dw5_C_O3', 10, 28800),
 '1x1 pointwise': (merge('wait0_pw', 'wait0_clip_pw'), 'pw_asm_rv', 'pw_asm_xp', 'pw_simd_asm_rv', 'pw_simd_asm_xp', 'pw_simd_asm_rv_clip', 'pw_simd_asm_xp_clip', 'pw_asm_rv_clip', 'pw_asm_xp_clip', lambda s: (lambda ci, co, h, w: co * h * w)(*map(int, s.split('x'))), 'wait0_pw', 'pw_C_O3', 4, 16384),
}
# act_words: activation word loads per output in the best SIMD kernel, from the kernel structure
# (3x3: one word per kernel row; 5x5: two words per kernel row; 1x1: CI/4 = 4 words at CI = 16).
# macs: MACs at the headline shape.
def shapley(cyc):
    """cyc: dict (d, c, k) -> cycles over the 2^3 grid. Returns the three Shapley factors on
    log-speedup relative to (0,0,0), exponentiated; their product is cyc[000]/cyc[111]."""
    val = lambda S: math.log(cyc[(0, 0, 0)] / cyc[S])
    out = []
    for i in range(3):
        tot = 0.0
        for perm in itertools.permutations(range(3)):
            S = [0, 0, 0]
            for j in perm[:perm.index(i)]: S[j] = 1
            S0 = tuple(S); S[i] = 1; tot += val(tuple(S)) - val(S0)
        out.append(math.exp(tot / 6))
    return out
TEX = collections.OrderedDict()   # row label -> list of per-family cell strings
worst = 0; chkbad = 0
for name, (D, s_rv, s_xp, v_rv, v_xp, v_rvc, v_xpc, s_rvc, s_xpc, outs, o3base, o3k, act_words, macs) in fam.items():
    O3 = merge(o3base)
    best = lambda s, k: min(D[0][(s, k)], D[1][(s, k)], key=lambda v: v['cycles'])
    shapes = []; [shapes.append(k[0]) for k in D[0] if k[0] not in shapes]
    print(f"\n### {name}\n")
    print("| shape | scalar -O3 | scalar asm | + clip | + hw loop/post-inc | + both | SIMD asm | + clip | + hw loop/post-inc | + both (full Xpulp) | full Xpulp vs -O3 | vs scalar asm | instr ratio vs scalar asm | clip saves per output: cycles | instructions | model residual, full |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in shapes:
        c = lambda k: best(s, k)['cycles']; o3 = min(O3[0][(s, o3k)]['cycles'], O3[1][(s, o3k)]['cycles'])
        full = best(s, v_xpc); n = outs(s)
        for k in (v_rvc, v_xpc, s_rvc, s_xpc):
            for p in (0, 1):
                v = D[p][(s, k)]; worst = max(worst, abs(v['resid']) / v['cycles'])
                if D[p][(s, k)]['chk'] != D[p][(s, s_rv)]['chk']: chkbad += 1
        print(f"| {s} | {o3:,} | {c(s_rv):,} | {c(s_rvc):,} | {c(s_xp):,} | {c(s_xpc):,} | {c(v_rv):,} | {c(v_rvc):,} | {c(v_xp):,} | {c(v_xpc):,} | {o3/c(v_xpc):.2f}x | {c(s_rv)/c(v_xpc):.2f}x | {best(s, s_rv)['instr']/full['instr']:.2f} | {(c(v_xp)-c(v_xpc))/n:.2f} | {(D[0][(s, v_xp)]['instr']-D[0][(s, v_xpc)]['instr'])/n:.2f} | {full['resid']/full['cycles']:+.1%} |")
    s0 = shapes[0]; c = lambda k: best(s0, k)['cycles']
    cyc = {(0,0,0): c(s_rv), (0,1,0): c(s_xp), (0,0,1): c(s_rvc), (0,1,1): c(s_xpc),
           (1,0,0): c(v_rv), (1,1,0): c(v_xp), (1,0,1): c(v_rvc), (1,1,1): c(v_xpc)}
    sh = shapley(cyc); full = best(s0, v_xpc); base = best(s0, s_rv)
    # Zbb-style saturation (srai; cv.max; cv.min, bounds in registers; results/saturation_model.py) in the non-clip cells: wait0_zbb_* sets
    ZB = {'3x3 depthwise': 'wait0_zbb_dw3', '5x5 depthwise': 'wait0_zbb_dw5', '1x1 pointwise': 'wait0_zbb_pw'}[name]
    try:
        if '--no-zbb' in sys.argv: raise FileNotFoundError   # the conference table has no room for the Zbb rows
        Z = merge(ZB); z = lambda k: min(Z[0][(s0, k)]['cycles'], Z[1][(s0, k)]['cycles'])
        cycz = dict(cyc); cycz.update({(0,0,0): z(s_rv), (0,1,0): z(s_xp), (1,0,0): z(v_rv), (1,1,0): z(v_xp)}); shz = shapley(cycz)
    except FileNotFoundError:
        shz = None
    o3 = min(O3[0][(s0, o3k)]['cycles'], O3[1][(s0, o3k)]['cycles'])
    print(f"\n{name}, {s0}, speedup over scalar asm (RV32IMC control, branch-free saturation); order-dependent values:\n")
    print("| component set | speedup over scalar asm |\n|---|---|")
    for lab, v in (("datapath (cv.dotsp.b) alone", c(s_rv)/c(v_rv)), ("control alone (scalar)", c(s_rv)/c(s_xp)), ("clip alone (scalar)", c(s_rv)/c(s_rvc)),
                   ("SIMD + control", c(s_rv)/c(v_xp)), ("SIMD + clip", c(s_rv)/c(v_rvc)), ("control + clip (scalar)", c(s_rv)/c(s_xpc)),
                   ("SIMD + control + clip (full Xpulp)", c(s_rv)/c(v_xpc))):
        print(f"| {lab} | {v:.2f}x |")
    print(f"| cycles per MAC, full Xpulp | {c(v_xpc)/macs:.2f} |")
    print(f"\n{name}, {s0}, the three features added first (to scalar asm), added last (on top of the other two), and the Shapley value over all 3! orders (product = full speedup):\n")
    print("| feature | added first | added last | Shapley |\n|---|---|---|---|")
    af = (c(s_rv)/c(v_rv), c(s_rv)/c(s_xp), c(s_rv)/c(s_rvc)); al = (c(s_xpc)/c(v_xpc), c(v_rvc)/c(v_xpc), c(v_xp)/c(v_xpc))
    for i, lab in enumerate(("datapath", "control", "clip")): print(f"| {lab} | {af[i]:.2f}x | {al[i]:.2f}x | {sh[i]:.2f}x |")
    print(f"| product | | | {sh[0]*sh[1]*sh[2]:.2f}x (measured {c(s_rv)/c(v_xpc):.2f}x) |")
    if shz: print(f"\n{name}, {s0}, the same grid with a Zbb-style three-instruction saturation in every non-clip cell (wait0_zbb_*): full Xpulp {cycz[(0,0,0)]/cycz[(1,1,1)]:.2f}x over the Zbb scalar kernel; Shapley datapath {shz[0]:.2f}x, control {shz[1]:.2f}x, clip over Zbb {shz[2]:.2f}x")
    bshare = 1 - base['instr'] / base['cycles']
    print(f"\n{name}, {s0}: measured speedup {c(s_rv)/c(v_xpc):.2f}x; instruction ratio {base['instr']/full['instr']:.2f}; "
          f"instruction ratio with the split-load cost on the accelerated side only {base['instr']/(full['instr']+full['split']):.2f}; "
          f"cycle model applied to both sides {base['pred']/full['pred']:.2f}; baseline non-instruction share {bshare:.1%} "
          f"({2*base['brtaken']:,} taken-branch cycles, {base['ldstall']:,} load-use stalls, {base['split']:,} split accesses, {base['resid']:,} residual); "
          f"full-Xpulp split-load share {full['split']/full['cycles']:.1%}; activation words loaded {outs(s0)*act_words:,} = {macs/(outs(s0)*act_words):.2f} MACs per activation word (loads retired {full['loads']:,})")
    if name.startswith('5x5'):   # the row-wise hand kernel (dwconv5_asm.c), the 5x5 baseline before the output-stationary one
        rw = best(s0, 'dw5_asm_rv'); meas = rw['cycles'] / full['cycles']; short = rw['instr'] / (full['instr'] + full['split'])
        print(f"{name}, {s0}, row-wise hand baseline: measured speedup {meas:.2f}x; instruction ratio with the split-load cost on the accelerated side only "
              f"{short:.2f}, {1 - short / meas:.1%} below it; non-instruction cycles {rw['cycles'] - rw['instr']:,} = {1 - rw['instr'] / rw['cycles']:.1%} of its {rw['cycles']:,}, "
              f"of which {2 * rw['brtaken']:,} taken-branch cycles and {rw['ldstall']:,} load-use stalls = {(2 * rw['brtaken'] + rw['ldstall']) / rw['cycles']:.1%}")
    sp = [D[p][(s0, s_rv)]['cycles'] / D[p][(s0, v_xpc)]['cycles'] for p in (0, 1)]
    spo = [O3[p][(s0, o3k)]['cycles'] / D[p][(s0, v_xpc)]['cycles'] for p in (0, 1)]
    print(f"{name}, {s0}: with both kernels at the same code alignment the speedup over scalar asm is {min(sp):.2f}x to {max(sp):.2f}x (pad 0, pad 1: {sp[0]:.2f}x, {sp[1]:.2f}x) and over -O3 {min(spo):.2f}x to {max(spo):.2f}x; the quoted value pairs each kernel's better alignment")
    cs = [(D[p][(s0, a)]['cycles'] - D[p][(s0, b)]['cycles']) / outs(s0) for p in (0, 1) for a, b in ((s_rv, s_rvc), (s_xp, s_xpc), (v_rv, v_rvc), (v_xp, v_xpc))]
    ci = [(D[p][(s0, a)]['instr'] - D[p][(s0, b)]['instr']) / outs(s0) for p in (0, 1) for a, b in ((s_rv, s_rvc), (s_xp, s_xpc), (v_rv, v_rvc), (v_xp, v_xpc))]
    print(f"{name}, {s0}: clip saves {min(ci):.3f} to {max(ci):.3f} instructions and {min(cs):.3f} to {max(cs):.3f} cycles per output over the four cell pairs and both alignments")
    short = {'3x3 depthwise': '3\\x3 dw', '5x5 depthwise': '5\\x5 dw', '1x1 pointwise': '1\\x1 pw'}[name]
    for lab, v in (("\\textit{Shapley value, order removed}", None), ("\\quad datapath", f"{sh[0]:.2f}\\x"), ("\\quad control (hw loop, post-incr.)", f"{sh[1]:.2f}\\x"), ("\\quad clip", f"{sh[2]:.2f}\\x"),
                   ("\\textit{added first, to the scalar kernel}", None), ("\\quad datapath alone", f"{af[0]:.2f}\\x"), ("\\quad control alone", f"{af[1]:.2f}\\x"), ("\\quad clip alone", f"{af[2]:.2f}\\x"),
                   ("\\textit{added last, on top of the other two}", None), ("\\quad datapath, last", f"{al[0]:.2f}\\x"), ("\\quad control, last", f"{al[1]:.2f}\\x"), ("\\quad clip, last", f"{al[2]:.2f}\\x"),
                   ("\\textit{Zbb min/max saturation in the non-clip cells}", None if shz else "__skip__"), ("\\quad full Xpulp vs Zbb scalar", f"{cycz[(0,0,0)]/cycz[(1,1,1)]:.2f}\\x" if shz else "__skip__"),
                   ("\\quad datapath, Zbb grid", f"{shz[0]:.2f}\\x" if shz else "__skip__"), ("\\quad control, Zbb grid", f"{shz[1]:.2f}\\x" if shz else "__skip__"), ("\\quad clip over Zbb", f"{shz[2]:.2f}\\x" if shz else "__skip__"),
                   ("\\midrule", None),
                   ("full Xpulp vs hand scalar", f"{c(s_rv)/c(v_xpc):.2f}\\x"), ("full Xpulp vs C \\texttt{-O3}", f"{o3/c(v_xpc):.2f}\\x"),
                   ("instruction ratio vs hand scalar", f"{base['instr']/full['instr']:.2f}"), ("Eq.~\\ref{eq:model} on both kernels", f"{base['pred']/full['pred']:.2f}\\x"),
                   ("baseline cycles that are stalls", f"{bshare:.1%}".replace('%', '\\%')), ("split-load share, full Xpulp", f"{full['split']/full['cycles']:.1%}".replace('%', '\\%')),
                   ("cycles per MAC, full Xpulp", f"{c(v_xpc)/macs:.2f}"), ("MACs per activation word", f"{macs/(outs(s0)*act_words):.1f}")):
        TEX.setdefault(lab, []).append(v)
    TEX.setdefault('__heads__', []).append(short)
print(f"\nmax |model residual| over clip runs: {worst:.1%}; checksum mismatches vs branch-free kernels: {chkbad}")
# cycle-model error over every hand-written run of the three families (synthetic data, both alignments)
hw = []
for base, pat in (('wait0_decomp', 'asm'), ('wait0_clip_dw3', 'asm'), ('wait0_dw5', 'dw5_asm|dw5_simd'), ('wait0_clip_dw5', 'dw5_asm|dw5_simd'), ('wait0_dw5os', 'dw5_os'), ('wait0_pw', 'pw_asm|pw_simd_asm'), ('wait0_clip_pw', 'pw_asm|pw_simd_asm')):
    for p in (0, 1):
        for k, v in align(load(f'{base}_pad{p}.csv'), p).items():
            if re.search(pat, k[1]): hw.append((base, k, v))
ape4 = [abs(v['resid'] + v['ba'] + v['j']) / v['cycles'] for _, _, v in hw]; ape5 = [abs(v['resid'] + v['j']) / v['cycles'] for _, _, v in hw]; ape6 = [abs(v['resid']) / v['cycles'] for _, _, v in hw]
w4 = max(hw, key=lambda t: abs(t[2]['resid'] + t[2]['ba'] + t[2]['j']) / t[2]['cycles'])
fullx = [t for t in hw if t[1][1].endswith('_xp_clip') and 'simd' in t[1][1]]   # full Xpulp: SIMD datapath + hardware loops/post-increment + clip
fam_of = lambda k: '5x5 depthwise' if k.startswith('dw5') else ('1x1 pointwise' if k.startswith('pw') else '3x3 depthwise')
print("\nhand-written runs by family and variant (each: 4 shapes x 2 alignments):\n")
print("| family | kernels | runs | of which full Xpulp |\n|---|---|---|---|")
for fam in ('3x3 depthwise', '5x5 depthwise', '1x1 pointwise'):
    ks = sorted({t[1][1] for t in hw if fam_of(t[1][1]) == fam})
    print(f"| {fam} | {', '.join(ks)} | {sum(fam_of(t[1][1]) == fam for t in hw)} | {sum(fam_of(t[1][1]) == fam for t in fullx)} |")
print(f"| total | | {len(hw)} | {len(fullx)} |")
print(f"cycle model over all {len(hw)} hand-written runs (three families, with and without clip, both alignments): four terms mean |residual| {sum(ape4)/len(ape4):.2%}, max {max(ape4):.2%} ({w4[1][1]} {w4[1][0]} {w4[0]}_pad?); "
      f"with the alignment term Ba ({sum(1 for _, _, v in hw if v['ba'])} runs have Ba > 0) mean {sum(ape5)/len(ape5):.2%}, max {max(ape5):.2%}; "
      f"with Ba and the jump term J ({sum(1 for _, _, v in hw if v['j'])} runs have J > 0) mean {sum(ape6)/len(ape6):.3%}, max {max(ape6):.2%}, exact {sum(v['resid'] == 0 for _, _, v in hw)}; "
      f"full-Xpulp kernels only ({len(fullx)} runs): max {max(abs(v['resid'])/v['cycles'] for _, _, v in fullx):.2%}")
# clip's saving in executed instructions per output, every hand-written kernel with and without clip, all shapes and both alignments
CLIP_PAIRS = [('wait0_decomp', 'wait0_clip_dw3', ['scalar_asm_rv', 'scalar_asm_xp', 'simd_unal_asm_rv', 'simd_unal_asm_xp', 'simd_al_asm_rv', 'simd_al_asm_xp'], 3),
              ('wait0_dw5', 'wait0_clip_dw5', ['dw5_asm_rv', 'dw5_asm_xp', 'dw5_simd_rv', 'dw5_simd_xp'], 5),
              ('wait0_dw5os', 'wait0_dw5os', ['dw5_os_asm_rv', 'dw5_os_asm_xp'], 5),
              ('wait0_pw', 'wait0_clip_pw', ['pw_asm_rv', 'pw_asm_xp', 'pw_simd_asm_rv', 'pw_simd_asm_xp'], 1)]
def n_out(s, k): f = list(map(int, s.split('x'))); return f[1] * f[2] * f[3] if k == 1 else f[0] * (f[1] - k + 1) * (f[2] - k + 1)
sav = []
for nb, cb, ks, k in CLIP_PAIRS:
    for p in (0, 1):
        A, C = load(f'{nb}_pad{p}.csv'), load(f'{cb}_pad{p}.csv')
        sav += [(A[key]['instr'] - C[(key[0], key[1] + '_clip')]['instr']) / n_out(key[0], k) for key in A if key[1] in ks]
other = [x for x in sav if abs(x - 7) > 1e-9]
print(f"clip saves exactly 7 executed instructions per output in {len(sav) - len(other)} of {len(sav)} kernel pairs (all shapes, both alignments); "
      f"the other {len(other)}: {min(other):.2f} to {max(other):.2f}")
if LATEX:
    heads = TEX.pop('__heads__')
    L = ["% generated by results/clip_model.py --latex; do not edit", "\\begin{tabular}{lccc}", "\\toprule", " & " + " & ".join(heads) + " \\\\", "\\midrule"]
    for lab, cells in TEX.items():
        if "__skip__" in cells: continue
        if lab == "\\midrule": L.append("\\midrule")
        elif cells[0] is None: L.append(f"\\multicolumn{{4}}{{l}}{{{lab}}} \\\\")
        else: L.append(f"{lab} & " + " & ".join(cells) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]
    open(LATEX, 'w').write("\n".join(L) + "\n"); print(f"wrote {LATEX}")
# real data with clip
try:
    R3 = merge('wait0_clip_real_dw3'); R1 = merge('wait0_clip_real_pw')
    exp = {}
    for h in glob.glob('../sw/real/*.h'):
        m = re.search(r'/(syn_)?(dw3|pw)_([0-9x]+)\.h$', h)
        if m is None: continue   # block_*.h and other headers are not single-layer sources
        c = re.search(r'#define REAL_CHECKSUM (\d+)', open(h).read())
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
