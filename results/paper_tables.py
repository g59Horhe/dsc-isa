#!/usr/bin/env python3
"""Generate every table fragment and figure data file for the journal manuscript
(paper/tc/paper_tc.tex, kept outside the public repository) from the committed data: results/*.csv (counters),
results/wait0_align.csv (alignment term), results/*_sweep.txt (latency sweeps),
syn/build (area, placement), the result scripts (clip_model.py, area_table.py,
block_model.py, ibex_model.py) and sw/real/gen_real_data.py (real-data statistics).
Nothing in the manuscript's tables is typed by hand. Run from anywhere:
    python3 results/paper_tables.py [--out DIR]
Writes DIR/*.tex and DIR/*.dat; DIR defaults to paper/tc/gen when that
directory exists next to the repository root, else results/paper_gen."""
import csv, collections, glob, math, itertools, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
RES = os.path.join(ROOT, 'results')
GEN = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else (os.path.join(ROOT, 'paper', 'tc', 'gen') if os.path.isdir(os.path.join(ROOT, 'paper', 'tc')) else os.path.join(RES, 'paper_gen'))
os.makedirs(GEN, exist_ok=True)
VENV = os.environ.get('VENV_PYTHON', os.path.expanduser('~/tools/venv/bin/python'))   # python with numpy, Pillow, ai-edge-litert
MODEL = os.environ.get('MOBILENET_TFLITE', os.path.expanduser('~/tools/models/mobilenet_v1_1.0_224_quant.tflite'))
IMAGE = os.environ.get('MOBILENET_IMAGE', os.path.expanduser('~/tools/models/grace_hopper.jpg'))
DW = ['8x16x16', '16x16x16', '8x32x32', '32x8x8']; PW = ['16x16x8x8', '8x8x16x16', '16x32x8x8', '16x16x16x16']

# ---------------------------------------------------------------- data loading (same definitions as the result scripts)
ALIGN = {}
if os.path.exists(f'{RES}/wait0_align.csv'):
    ALIGN = {(r['shape'], r['kernel'], int(r['pad'])): int(r['ba']) for r in csv.DictReader(open(f'{RES}/wait0_align.csv'))}
def load(base, p):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(f'{RES}/{base}_pad{p}.csv') if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value']) if r['value'].lstrip('-').isdigit() else r['value']
        d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    for k, v in d.items():
        v['instr'] = v['ev1']; v['ldstall'] = v['ev2']; v['loads'] = v['ev5']; v['brtaken'] = v['ev9']
        v['split'] = v['dread'] - v['loads']; v['ba'] = ALIGN.get((k[0], k[1], p), 0)
        v['pred4'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']; v['pred'] = v['pred4'] + v['ba']
        v['resid4'] = v['cycles'] - v['pred4']; v['resid'] = v['cycles'] - v['pred']; v['pad'] = p
    return d
def merge(*bases):
    out = [collections.OrderedDict(), collections.OrderedDict()]
    for b in bases:
        for p in (0, 1): out[p].update(load(b, p))
    return out
def best(D, s, k): return min(D[0][(s, k)], D[1][(s, k)], key=lambda v: v['cycles'])
E = merge('wait0_eqrequant')
D3 = merge('wait0_decomp', 'wait0_clip_dw3'); D5 = merge('wait0_dw5', 'wait0_clip_dw5', 'wait0_dw5os'); D1 = merge('wait0_pw', 'wait0_clip_pw')
# family: (data, shapes, O3 kernel, hand scalar cells (rv, xp, rv_clip, xp_clip), SIMD cells (rv, xp, rv_clip, xp_clip), MAC count fn, outputs fn, activation words per output)
FAM = collections.OrderedDict([
  ('3\\x3 dw', dict(D=D3, shapes=DW, o3=('wait0_eqrequant', 'scalar_O3'), s=('scalar_asm_rv', 'scalar_asm_xp', 'scalar_asm_rv_clip', 'scalar_asm_xp_clip'),
                    v=('simd_unal_asm_rv', 'simd_unal_asm_xp', 'simd_unal_asm_rv_clip', 'simd_unal_asm_xp_clip'),
                    macs=lambda s: (lambda c, h, w: c * (h - 2) * (w - 2) * 9)(*map(int, s.split('x'))), outs=lambda s: (lambda c, h, w: c * (h - 2) * (w - 2))(*map(int, s.split('x'))), aw=3)),
  ('5\\x5 dw', dict(D=D5, shapes=DW, o3=('wait0_dw5', 'dw5_C_O3'), s=('dw5_os_asm_rv', 'dw5_os_asm_xp', 'dw5_os_asm_rv_clip', 'dw5_os_asm_xp_clip'),
                    v=('dw5_simd_rv', 'dw5_simd_xp', 'dw5_simd_rv_clip', 'dw5_simd_xp_clip'),
                    macs=lambda s: (lambda c, h, w: c * (h - 4) * (w - 4) * 25)(*map(int, s.split('x'))), outs=lambda s: (lambda c, h, w: c * (h - 4) * (w - 4))(*map(int, s.split('x'))), aw=10)),
  ('1\\x1 pw', dict(D=D1, shapes=PW, o3=('wait0_pw', 'pw_C_O3'), s=('pw_asm_rv', 'pw_asm_xp', 'pw_asm_rv_clip', 'pw_asm_xp_clip'),
                    v=('pw_simd_asm_rv', 'pw_simd_asm_xp', 'pw_simd_asm_rv_clip', 'pw_simd_asm_xp_clip'),
                    macs=lambda s: (lambda ci, co, h, w: ci * co * h * w)(*map(int, s.split('x'))), outs=lambda s: (lambda ci, co, h, w: co * h * w)(*map(int, s.split('x'))), aw=4)),
])
O3D = {'wait0_eqrequant': E, 'wait0_dw5': D5, 'wait0_pw': D1}
def o3cyc(f, s): base, k = f['o3']; return min(O3D[base][p][(s, k)]['cycles'] for p in (0, 1))
def shapley(cyc):
    val = lambda S: math.log(cyc[(0, 0, 0)] / cyc[S]); out = []
    for i in range(3):
        tot = 0.0
        for perm in itertools.permutations(range(3)):
            S = [0, 0, 0]
            for j in perm[:perm.index(i)]: S[j] = 1
            S0 = tuple(S); S[i] = 1; tot += val(tuple(S)) - val(S0)
        out.append(math.exp(tot / 6))
    return out
def grid(f, s):
    D = f['D']; c = lambda k: best(D, s, k)['cycles']; sv, vv = f['s'], f['v']
    return {(0,0,0): c(sv[0]), (0,1,0): c(sv[1]), (0,0,1): c(sv[2]), (0,1,1): c(sv[3]), (1,0,0): c(vv[0]), (1,1,0): c(vv[1]), (1,0,1): c(vv[2]), (1,1,1): c(vv[3])}

# ---------------------------------------------------------------- LaTeX helpers
def esc(s): return str(s).replace('%', '\\%').replace('_', '\\_').replace('&', '\\&')
def X(v, nd=2): return f"{v:.{nd}f}\\x"
def P(v, nd=1): return f"{100*v:.{nd}f}\\%"
def N(v): return f"{v:,}"
def write_tab(name, colspec, header, rows, note=None, size=None, prehead=None):
    L = [f"% generated by results/paper_tables.py; do not edit"]
    if size: L.append(size)
    L += [f"\\begin{{tabular}}{{{colspec}}}", "\\toprule"]
    if prehead: L.append(prehead + " \\\\")
    L += [" & ".join(header) + " \\\\", "\\midrule"]
    for r in rows:
        L.append("\\midrule" if r == 'MIDRULE' else " & ".join(r) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]
    open(f'{GEN}/{name}.tex', 'w').write("\n".join(L) + "\n")
def write_dat(name, header, rows):
    with open(f'{GEN}/{name}.dat', 'w') as f:
        f.write(" ".join(header) + "\n")
        for r in rows: f.write(" ".join(str(x) for x in r) + "\n")
def md_tables(text):
    """all markdown tables in text -> list of (header, rows) with cells as strings"""
    out = []; cur = None
    for l in text.splitlines():
        if l.startswith('|'):
            cells = [c.strip() for c in l.strip().strip('|').split('|')]
            if all(re.fullmatch(r'-+', c) for c in cells): continue
            if cur is None: cur = (cells, []); out.append(cur)
            else: cur[1].append(cells)
        else: cur = None
    return out
def run(cmd, cwd=RES): return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout

# ---------------------------------------------------------------- B. wait-0 table, 3x3 equalised set
rows = []
names = {'scalar_O2': 'scalar C \\texttt{-O2}', 'scalar_O3': 'scalar C \\texttt{-O3}', 'scalar_asm': 'scalar asm', 'simd_unal': 'SIMD unaligned C', 'simd_al': 'SIMD aligned C', 'simd_al_O3': 'SIMD aligned C \\texttt{-O3}'}
for s in DW:
    for i, k in enumerate(names):
        a, b = E[0][(s, k)], E[1][(s, k)]; v = min((a, b), key=lambda v: v['cycles'])
        rows.append([s.replace('x', '\\x') if i == 0 else '', names[k], N(a['cycles']), N(b['cycles']), N(a['instr']), N(a['dread']), N(a['brtaken']), N(a['ldstall']), N(a['split']), N(a['ba']), f"{v['resid']/v['cycles']:+.1%}".replace('%', '\\%')])
    if s != DW[-1]: rows.append('MIDRULE')
write_tab('tab_wait0_dw3', 'llrrrrrrrrr', ['shape', 'kernel', 'cycles, pad 0', 'pad 1', '$I$', 'reads', '$B_t$', '$S_{lu}$', '$A_{split}$', '$B_a$', 'resid.'], rows)

# ---------------------------------------------------------------- C. model fit statistics
def r2(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys)); sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    b = sxy / sxx; a = my - b * mx; return 1 - sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / syy
hw = []
for base, pat in (('wait0_decomp', 'asm'), ('wait0_clip_dw3', 'asm'), ('wait0_dw5', 'dw5_asm|dw5_simd'), ('wait0_clip_dw5', 'dw5_asm|dw5_simd'), ('wait0_dw5os', 'dw5_os'), ('wait0_pw', 'pw_asm|pw_simd_asm'), ('wait0_clip_pw', 'pw_asm|pw_simd_asm')):
    for p in (0, 1):
        for k, v in load(base, p).items():
            if re.search(pat, k[1]): hw.append(v)
eq = [v for p in (0, 1) for v in E[p].values()]
distinct = hw + [v for p in (0, 1) for k, v in E[p].items() if k[1] != 'scalar_asm']
fullx = [v for base in ('wait0_clip_dw3', 'wait0_clip_dw5', 'wait0_clip_pw') for p in (0, 1) for k, v in load(base, p).items() if k[1].endswith('_xp_clip') and 'simd' in k[1]]   # full Xpulp: SIMD + hardware loops + clip
def stats(rs, label):
    ys = [v['cycles'] for v in rs]; e4 = [abs(v['resid4']) / v['cycles'] for v in rs]; e5 = [abs(v['resid']) / v['cycles'] for v in rs]
    return [label, str(len(rs)), f"{r2([v['pred4'] for v in rs], ys):.4f}", P(sum(e4) / len(e4), 2), P(max(e4), 2), f"{r2([v['pred'] for v in rs], ys):.4f}", P(sum(e5) / len(e5), 2), P(max(e5), 2)]
rows = [stats(eq, 'equalised 3\\x3 set'), stats(hw, 'hand-written, 3 families'),
        stats(fullx, '\\quad full Xpulp only'), stats(distinct, 'all distinct')]
ys = [v['cycles'] for v in eq]
rows.append(['$I$ alone, equalised set', str(len(eq)), f"{r2([v['instr'] for v in eq], ys):.4f}", '', '', '', '', ''])
write_tab('tab_modelfit', 'lrrrrrrr', ['run set', '$n$', '$R^2_4$', 'mean', 'max', '$R^2_5$', 'mean', 'max'], rows)
# residual histogram data
bins = [0, 0.0025, 0.005, 0.01, 0.02, 0.04, 0.08]
lab = ['0--0.25', '0.25--0.5', '0.5--1', '1--2', '2--4', '4--8']
h4 = [sum(bins[i] <= abs(v['resid4']) / v['cycles'] < bins[i + 1] for v in distinct) for i in range(6)]
h5 = [sum(bins[i] <= abs(v['resid']) / v['cycles'] < bins[i + 1] for v in distinct) for i in range(6)]
write_dat('fig_resid', ['bin', 'four', 'five'], [[lab[i], h4[i], h5[i]] for i in range(6)])

# ---------------------------------------------------------------- E. baseline strength and alignment spread, all families and shapes
rows = []
o2k = {'3\\x3 dw': ('wait0_eqrequant', 'scalar_O2'), '5\\x5 dw': ('wait0_dw5', 'dw5_C_O2'), '1\\x1 pw': ('wait0_pw', 'pw_C_O2')}
for name, f in FAM.items():
    for i, s in enumerate(f['shapes']):
        base, k2 = o2k[name]; Dd = O3D[base]; o2 = min(Dd[p][(s, k2)]['cycles'] for p in (0, 1)); o3 = o3cyc(f, s)
        h = best(f['D'], s, f['s'][0])['cycles']
        sp = lambda Dd, k: abs(Dd[0][(s, k)]['cycles'] - Dd[1][(s, k)]['cycles']) / min(Dd[0][(s, k)]['cycles'], Dd[1][(s, k)]['cycles'])
        rows.append([name if i == 0 else '', s.replace('x', '\\x'), N(o2), N(o3), N(h), X(o2 / o3), f"{o3/h-1:+.1%}".replace('%', '\\%'), P(sp(Dd, k2)), P(sp(Dd, f['o3'][1])), P(sp(f['D'], f['s'][0]))])
    if name != '1\\x1 pw': rows.append('MIDRULE')
write_tab('tab_baseline', 'llrrrrrrrr', ['kernel', 'shape', '\\texttt{-O2}', '\\texttt{-O3}', 'hand', '\\texttt{-O2}/\\texttt{-O3}', 'hand vs \\texttt{-O3}', 'spread \\texttt{-O2}', '\\texttt{-O3}', 'hand'], rows)

# ---------------------------------------------------------------- G. decomposition over all shapes
rows = []; figrows = []
for name, f in FAM.items():
    for i, s in enumerate(f['shapes']):
        g = grid(f, s); sh = shapley(g); D = f['D']; b = best(D, s, f['s'][0]); fx = best(D, s, f['v'][3]); o3 = o3cyc(f, s)
        rows.append([name if i == 0 else '', s.replace('x', '\\x'), N(b['cycles']), N(fx['cycles']), X(o3 / fx['cycles']), X(b['cycles'] / fx['cycles']), f"{b['instr']/fx['instr']:.2f}", X(b['pred'] / fx['pred']),
                     X(sh[0]), X(sh[1]), X(sh[2]), P(fx['split'] / fx['cycles']), f"{fx['cycles']/f['macs'](s):.2f}"])
        if i == 0:
            af = (g[(0,0,0)]/g[(1,0,0)], g[(0,0,0)]/g[(0,1,0)], g[(0,0,0)]/g[(0,0,1)]); al = (g[(0,1,1)]/g[(1,1,1)], g[(1,0,1)]/g[(1,1,1)], g[(1,1,0)]/g[(1,1,1)])
            for j, feat in enumerate(('datapath', 'control', 'clip')):
                figrows.append([f"{name.replace(chr(92)+'x', 'x').replace(' ', '')}-{feat}", f"{af[j]:.3f}", f"{sh[j]:.3f}", f"{al[j]:.3f}"])
    if name != '1\\x1 pw': rows.append('MIDRULE')
write_tab('tab_decomp_all', 'llrrrrrrrrrrr', ['kernel', 'shape', 'hand cycles', 'full Xpulp', 'vs \\texttt{-O3}', 'vs hand', 'instr.\\ ratio', 'Eq.~1 both', 'Shapley dp', 'ctl', 'clip', 'split share', 'cyc/MAC'], rows)
write_dat('fig_decomp', ['cell', 'first', 'shapley', 'last'], figrows)

# ---------------------------------------------------------------- H. 5x5 two baselines
rows = []
for s in DW:
    c = lambda k: best(D5, s, k)['cycles']; rw, os_ = best(D5, s, 'dw5_asm_rv'), best(D5, s, 'dw5_os_asm_rv'); o3 = o3cyc(FAM['5\\x5 dw'], s)
    rows.append([s.replace('x', '\\x'), N(o3), N(rw['cycles']), N(os_['cycles']), N(rw['brtaken']), N(os_['brtaken']), N(rw['ldstall']), N(os_['ldstall']), N(rw['dwrite']), N(os_['dwrite']), X(rw['cycles'] / os_['cycles']), X(o3 / os_['cycles']), X(rw['cycles'] / c('dw5_simd_xp_clip')), X(os_['cycles'] / c('dw5_simd_xp_clip'))])
write_tab('tab_dw5', 'lrrrrrrrrrrrrr', ['shape', '\\texttt{-O3}', 'row-wise', 'out.-stat.', '$B_t$ rw', 'os', '$S_{lu}$ rw', 'os', 'stores rw', 'os', 'rw / os', '\\texttt{-O3} / os', 'Xpulp vs rw', 'vs os'], rows)

# ---------------------------------------------------------------- I. data-port latency sweep
sw = {}
for l in open(f'{RES}/decomp_latency_sweep.txt'):
    m = re.match(r'(\S+)\s+(scalar_rv|scalar_xp|unal_rv|unal_xp|al_rv|al_xp)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', l)
    if m: sw[(m[1], m[2])] = [int(m[i]) for i in range(3, 7)]
kmap = {'scalar_rv': ('scalar_asm_rv', 'scalar, RV32IMC ctl'), 'scalar_xp': ('scalar_asm_xp', 'scalar, Xpulp ctl'), 'unal_rv': ('simd_unal_asm_rv', 'SIMD unaligned, RV32IMC ctl'),
        'unal_xp': ('simd_unal_asm_xp', 'SIMD unaligned, Xpulp ctl'), 'al_rv': ('simd_al_asm_rv', 'SIMD aligned, RV32IMC ctl'), 'al_xp': ('simd_al_asm_xp', 'SIMD aligned, Xpulp ctl')}
rows = []; figrows = [[w] for w in range(4)]
for s in DW:
    for i, (k, (kk, lab)) in enumerate(kmap.items()):
        cyc = sw[(s, k)]; a = D3[0][(s, kk)]; acc = a['dread'] + a['dwrite']
        err = max(abs(cyc[w] - cyc[0] - w * acc) for w in range(1, 4))
        rows.append([s.replace('x', '\\x') if i == 0 else '', lab, N(cyc[0]), N(cyc[1]), N(cyc[2]), N(cyc[3]), N(acc), N(err)])
        if s == '8x16x16':
            for w in range(4): figrows[w].append(cyc[w])
    if s != DW[-1]: rows.append('MIDRULE')
write_tab('tab_latency', 'llrrrrrr', ['shape', 'kernel', '$w=0$', '1', '2', '3', 'reads+writes', 'max error'], rows)
write_dat('fig_latency', ['w'] + list(kmap), figrows)

# ---------------------------------------------------------------- J. instruction-port latency sweep
iw = {}; cur = None
for l in open(f'{RES}/ifetch_latency_sweep.txt'):
    m = re.match(r'### IWAIT=(\d)', l)
    if m: cur = int(m[1]); continue
    m = re.match(r'(\S+)\s+(\S+)\s+(\d+)\s+\d+', l)
    if m and cur is not None: iw[(m[1], m[2], cur)] = int(m[3])
rows = []; figrows = [[w] for w in range(4)]; pairs = [('scalar', 'scalar_rv', 'scalar_xp'), ('SIMD unaligned', 'unal_rv', 'unal_xp'), ('SIMD aligned', 'al_rv', 'al_xp')]
shapes_iw = sorted(set(k[0] for k in iw), key=lambda s: (len(s), s))
for s in shapes_iw:
    for lab, rv, xp in pairs:
        if (s, rv, 0) not in iw: continue
        r = [iw[(s, rv, w)] for w in range(4)]; x = [iw[(s, xp, w)] for w in range(4)]
        rows.append([s.replace('x', '\\x'), lab] + [N(v) for v in r] + [N(v) for v in x] + [f"{x[w]/r[w]:.2f}" for w in range(4)])
        if s == '8x16x16':
            for w in range(4): figrows[w].append(f"{x[w]/r[w]:.3f}")
write_tab('tab_ifetch', 'llrrrrrrrrrrrr', ['shape', 'kernel', 'RV32IMC $w_i{=}0$', '1', '2', '3', 'Xpulp $w_i{=}0$', '1', '2', '3', 'ratio 0', '1', '2', '3'], rows)
write_dat('fig_ifetch', ['w', 'scalar', 'unal', 'al'], figrows)

# ---------------------------------------------------------------- K. area: headline table from area_table.py, per-module table from attrib_area.txt
run(['python3', 'area_table.py', '--latex', f'{GEN}/tab_area.tex']); run(['python3', 'clip_model.py', '--latex', f'{GEN}/tab_decomp.tex'])
rows = []; other = [0, 0, 0]; mods = []
for l in open(f'{ROOT}/syn/build/attrib_area.txt'):
    m = re.match(r'(cv32e40p_core\S*|design total)\s+([\d,]+)\s+([\d,]+)\s+(-?[\d,]+)', l)
    if not m: continue
    name = m[1].replace('cv32e40p_core_o_', '').replace('cv32e40p_core', 'untagged (created by opt)'); b, p_, d = (int(m[i].replace(',', '')) for i in (2, 3, 4))
    if name == 'design total': total = (b, p_, d)
    else: mods.append((name, b, p_, d))
for name, b, p_, d in mods:
    if abs(d) >= 50: rows.append([esc(name), N(b), N(p_), f"{d:+,}", f"{d/total[2]:.0%}".replace('%', '\\%')])
    else: other = [other[0] + b, other[1] + p_, other[2] + d]
rows.append(['other modules', N(other[0]), N(other[1]), f"{other[2]:+,}", f"{other[2]/total[2]:.0%}".replace('%', '\\%')])
rows.append('MIDRULE'); rows.append(['total, attribution pass', N(total[0]), N(total[1]), f"{total[2]:+,}", ''])
write_tab('tab_modules', 'lrrrr', ['module of origin', 'RV32IMC GE', 'Xpulp GE', 'delta GE', 'share'], rows)

# ---------------------------------------------------------------- L. real-data statistics (generator stdout)
rows = []
try:
    tmp = os.path.join(GEN, 'realgen'); os.makedirs(tmp, exist_ok=True)
    out = run([VENV, 'sw/real/gen_real_data.py', MODEL, IMAGE, tmp], cwd=ROOT)
    for l in out.splitlines():
        m = re.match(r'\s+(dw3|pw) (\S+): checksum=(\d+) (.*)', l)
        if not m: continue
        k = re.match(r'out mean=([\d.]+) zeros=([\d.]+)% sat255=([\d.]+)% neg->0=([\d.]+)% act mean=([\d.]+)(?: act zeros=([\d.]+)%)? \|w\| mean=([\d.]+) max=(\d+)', m[4])
        if not k: continue
        rows.append([f"{m[1]} {m[2].replace('x', chr(92)+'x')}", k[2] + '\\%', k[3] + '\\%', k[4] + '\\%', (k[6] + '\\%') if k[6] else '--', k[8]])
    for h in ('dw3_8x16x16', 'pw_16x16x8x8', 'block_16x16x16_16'):
        assert open(f'{tmp}/{h}.h').read() == open(f'{ROOT}/sw/real/{h}.h').read(), f'regenerated header differs: {h}'
    m = re.search(r'block: dw M=([\d.]+) \(2\^-2 ([+-]\d+)%\) clipped=(\d+); pw M=([\d.]+) \(2\^-5 ([+-]\d+)%\)', out)
except Exception as e:
    print('real-data statistics skipped:', e)
if rows: write_tab('tab_real', 'lrrrrr', ['layer, shape', 'outputs 0', 'at 255', 'negative', 'act.\\ 0', 'max $|w|$'], rows)

# ---------------------------------------------------------------- M. block (block_model.py stdout)
bt = md_tables(run(['python3', 'block_model.py']))
hdr, brows = bt[0]
bshort = lambda n: esc(n).replace('SIMD asm, RV32IMC ctrl', 'SIMD, RV32IMC ctl').replace('SIMD + hw loops', 'SIMD + loops').replace('full Xpulp (+ clip)', 'full Xpulp').replace('C -O3', 'C \\texttt{-O3}').replace('fused store', 'fused')
rows = [[bshort(r[0]), N(min(int(c.replace(',', '')) for c in r[1].split(' / '))), r[2], N(int(r[3].replace(',', ''))), N(int(r[6].replace(',', ''))), esc(r[8])] for r in brows]
write_tab('tab_block', 'lrrrrr', ['block variant', 'cycles', 'cyc/MAC', '$I$', '$B_t$', 'resid.'], rows)

# ---------------------------------------------------------------- N. Ibex (ibex_model.py stdout), headline shapes
it = md_tables(run([VENV, 'ibex_model.py']))
hdr, irows = it[0]; head = {'8x16x16', '16x16x8x8'}
short = lambda n: n.replace(' depthwise', ' dw').replace(' pointwise', ' pw').replace('C -O2', 'C \\texttt{-O2}').replace('C -O3', 'C \\texttt{-O3}')
rows = [[short(r[0]), r[1].replace('x', '\\x'), N(int(r[2].replace(',', ''))), N(int(r[3].replace(',', ''))), N(int(r[4].replace(',', ''))), N(int(r[5].replace(',', ''))), r[6], r[7], esc(r[8])] for r in irows if r[1] in head]
write_tab('tab_ibex', 'llrrrrrrl', ['kernel', 'shape', '$I$', 'CV32E40P', 'Ibex 2-st.', 'Ibex 3-st.', 'Ibex2/CV', 'Ibex3/CV', 'spread CV / Ibex2 / Ibex3'], rows)
hdr, jrows = it[1]
rows = [[short(r[0]), r[1].replace('x', '\\x')] + [c.replace('x', '\\x') for c in r[2:]] for r in jrows if r[1] in head]
write_tab('tab_ibex_ratio', 'llrrrrrr', ['kernel', 'shape', 'CV', 'Ibex2', 'Ibex3', 'CV', 'Ibex2', 'Ibex3'], rows, prehead=' & & \\multicolumn{3}{c}{\\texttt{-O2} / \\texttt{-O3}} & \\multicolumn{3}{c}{\\texttt{-O3} / hand}')
print('wrote', sorted(os.listdir(GEN)))
