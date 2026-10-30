#!/usr/bin/env python3
"""PULP-NN as the accelerated baseline, and the cycle model on code it was not fitted to.

PULP-NN's depthwise 3x3, depthwise generic (5x5) and pointwise kernels (sw/pulpnn/, unchanged) run
on the same data as this study's kernels, in six builds: two compilers, each with and without the
specialisation that the hand kernels get from their -D shape constants.
  gcc16       upstream GCC 16.1, -march=rv32imc_xcvsimd_xcvalu (SIMD dot product and clip; upstream
              GCC has no CORE-V hardware loops or post-increment)
  corev       CORE-V GCC 14.1 (OpenHW/Embecosm, corev-openhw-gcc 20240530), same -march
  corev+hwlp  CORE-V GCC 14.1, -march=..._xcvhwlp_xcvmem: compiler-generated hardware loops and
              post-increment / register-indexed loads and stores, as PULP-NN is meant to be built
each as lib (PULPNN_LIB=1: noipa, compiled as a separate library would be) and spec (PULPNN_LIB=0).
Inputs: results/wait0_{pulpnn,pulpnncv0,pulpnncv}{,_spec}_{dw3,dw5,pw,real_dw3,real_pw}_pad{0,1}.csv
and the committed datasets for the study's kernels. Every PULP-NN checksum must equal the study's
full-Xpulp kernel's on the same data.

Table 1: cycles per valid MAC (the 3x3 kernel also computes the two zero-padded edge columns, so it
does W/(W-2) times the outputs), each kernel at its better code alignment.
Table 2: speedups over -O3 C and over the hand scalar kernel, study kernel against the PULP-NN builds.
Table 3: the cycle model, cycles = I + 2 Bt + Slu + Asplit + Ba, on every PULP-NN run, with two
terms the study's kernels never exercise: Asplit also counts split stores (dwrite - stores), and
J, one cycle per jump (jal, jalr; event 7), fixed by sw/ubench_jump.c (1,000 jal: +1,000 cycles
beyond the instruction count; 1,000 call-return pairs: +2,001 for 2,001 jumps). Ba is measured as
in align_term.py: each binary is rebuilt as harness/collect_wait0.sh builds it (the cycle count
must match the CSV), run with --redir, and the taken redirects to a 32-bit instruction at an
address 2 mod 4 are counted. The table also gives the static count of hardware-loop setups and
CORE-V loads/stores in each build, to show what the compiler emitted. Run from results/.
--latex PATH writes the paper's table (headline shapes: cycles per valid MAC and speedup over -O3)."""
import csv, collections, os, re, subprocess, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RISCV_BIN = os.environ.get('RISCV_BIN', '/opt/riscv/bin')
COREV_BIN = os.environ.get('COREV_BIN', os.path.expanduser('~/tools/corev-gcc/bin'))
SIM = f'{ROOT}/harness/obj_pulp/Vcv32e40p_core'
PNF = '-O3 -Isw/pulpnn/include -Wno-error=int-conversion -fno-tree-loop-distribute-patterns'
DW = ['8x16x16', '16x16x16', '8x32x32', '32x8x8']; PW = ['16x16x8x8', '8x8x16x16', '16x32x8x8', '16x16x16x16']
GNU = (f'{RISCV_BIN}/riscv32-unknown-elf-', 'rv32imc_xcvsimd_xcvalu')
COREV0 = (f'{COREV_BIN}/riscv32-corev-elf-', 'rv32imc_xcvsimd_xcvalu')
COREV = (f'{COREV_BIN}/riscv32-corev-elf-', 'rv32imc_xcvsimd_xcvalu_xcvhwlp_xcvmem')
BUILDS = [  # label, dataset prefix, PULPNN_LIB, (tool prefix, -march)
  ('gcc16 lib', 'wait0_pulpnn', 1, GNU), ('gcc16 spec', 'wait0_pulpnn_spec', 0, GNU),
  ('corev lib', 'wait0_pulpnncv0', 1, COREV0), ('corev spec', 'wait0_pulpnncv0_spec', 0, COREV0),
  ('corev+hwlp lib', 'wait0_pulpnncv', 1, COREV), ('corev+hwlp spec', 'wait0_pulpnncv_spec', 0, COREV),
]
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        v = d.setdefault((r['shape'], r['kernel']), {}); v[r['event']] = int(r['value']); v['chk'] = r['chk']
    return d
def both(base): return [load(f'{base}_pad{p}.csv') for p in (0, 1)]
def best(ds, s, k): return min((ds[0][(s, k)], ds[1][(s, k)]), key=lambda v: v['cycles'])
def dw_macs(k): return lambda s: (lambda c, h, w: c * (h - k + 1) * (w - k + 1) * k * k)(*map(int, s.split('x')))
FAMILIES = [  # name, file tag, shapes, MACs, (study full-Xpulp dataset, kernel), (hand scalar), (-O3 C)
  ('3x3 depthwise', 'dw3', DW, dw_macs(3), ('wait0_clip_dw3', 'simd_unal_asm_xp_clip'), ('wait0_decomp', 'scalar_asm_rv'), ('wait0_eqrequant', 'scalar_O3')),
  ('5x5 depthwise', 'dw5', DW, dw_macs(5), ('wait0_clip_dw5', 'dw5_simd_xp_clip'), ('wait0_dw5os', 'dw5_os_asm_rv'), ('wait0_dw5', 'dw5_C_O3')),
  ('1x1 pointwise', 'pw', PW, lambda s: (lambda a, b, h, w: a * b * h * w)(*map(int, s.split('x'))), ('wait0_clip_pw', 'pw_simd_asm_xp_clip'), ('wait0_pw', 'pw_asm_rv'), ('wait0_pw', 'pw_C_O3')),
]

# ---- tables 1 and 2
T1, T2 = [], []
HEAD = {'dw3': '8x16x16', 'dw5': '8x16x16', 'pw': '16x16x8x8'}; LX = {}   # headline shapes, for --latex
for name, f, shapes, macs, (oc, ok), (hc, hk), (o3c, o3k) in FAMILIES:
    O, H, O3 = both(oc), both(hc), both(o3c)
    P = {b: both(f'{base}_{f}') for b, base, _, _ in BUILDS}
    for s in shapes:
        m = macs(s); o, h, o3 = best(O, s, ok), best(H, s, hk), best(O3, s, o3k)
        pn = {b: best(P[b], s, f'pulpnn_{f}') for b in P}
        if s == HEAD[f]: LX[f] = dict(m=m, o3=o3['cycles'], study=o['cycles'], **{b: pn[b]['cycles'] for b in P})
        T1.append(f"| {name} | {s} | {o3['cycles']/m:.2f} | {h['cycles']/m:.2f} | {o['cycles']/m:.2f} | " + ' | '.join(f"{pn[b]['cycles']/m:.2f}" for b in P) + ' |')
        T2.append(f"| {name} | {s} | {o3['cycles']/o['cycles']:.2f}x / {h['cycles']/o['cycles']:.2f}x | " +
                  ' | '.join(f"{o3['cycles']/pn[b]['cycles']:.2f}x / {h['cycles']/pn[b]['cycles']:.2f}x" for b in P) + ' |')
cols = [b for b, *_ in BUILDS]
print("cycles per valid MAC, better alignment:\n")
print("| kernel | shape | -O3 C | hand scalar | study full Xpulp | " + ' | '.join(f'PULP-NN {b}' for b in cols) + ' |')
print('|' + '---|' * (5 + len(cols))); print('\n'.join(T1))
print("\nspeedup over -O3 C / over the hand scalar kernel:\n")
print("| kernel | shape | study full Xpulp | " + ' | '.join(f'PULP-NN {b}' for b in cols) + ' |')
print('|' + '---|' * (3 + len(cols))); print('\n'.join(T2))
nchk = 0
for f, oc, ok, shapes in (('dw3', 'wait0_clip_dw3', 'simd_unal_asm_xp_clip', DW), ('dw5', 'wait0_clip_dw5', 'dw5_simd_xp_clip', DW), ('pw', 'wait0_clip_pw', 'pw_simd_asm_xp_clip', PW),
                          ('real_dw3', 'wait0_clip_real_dw3', 'simd_unal_asm_xp_clip', DW), ('real_pw', 'wait0_clip_real_pw', 'pw_simd_asm_xp_clip', PW)):
    O = both(oc)
    for _, base, _, _ in BUILDS:
        P = both(f'{base}_{f}')
        for p in (0, 1):
            for s in shapes:
                got, want = P[p][(s, f"pulpnn_{f.replace('real_', '')}")]['chk'], O[p][(s, ok)]['chk']
                assert got == want, (base, f, s, p, got, want); nchk += 1
print(f"\nchecksums: all {nchk} PULP-NN runs equal the study's full-Xpulp kernel on the same data (synthetic and real, both alignments, all six builds)")

# ---- table 3: the cycle model on PULP-NN
BR = {'beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu', 'beqz', 'bnez', 'blez', 'bgez', 'bltz', 'bgtz', 'j', 'jal', 'c.j', 'c.jal', 'c.beqz', 'c.bnez', 'jr', 'c.jr', 'ret', 'jalr', 'c.jalr'}
def disasm(objdump, elf):   # as align_term.py: instruction lengths, static redirect targets, CORE-V op counts
    ln = {}; targets = set(); ops = collections.Counter()
    for l in subprocess.run([objdump, '-d', elf], capture_output=True, text=True, check=True).stdout.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$', l)
        if not m: continue
        a = int(m[1], 16); ln[a] = len(m[2]) // 2
        if m[3].startswith('cv.setup') or m[3].startswith('cv.start'): ops['setup'] += 1
        if re.match(r'cv\.(l|s)[bhw]u?$', m[3]): ops['ldst'] += 1
        if m[3] in BR:
            t = re.search(r'([0-9a-f]+)\s*<', m[4]) or re.search(r'([0-9a-f]{8})\s*$', m[4])
            if t: targets.add(int(t[1], 16))
    return ln, targets, ops
def resolve(word, ln, targets):
    cands = [c for c in (word, word + 2) if c in ln]; hit = [c for c in cands if c in targets]
    return (hit or cands or [word])[0]
def shape_defs(s):
    f = s.split('x')
    return ['-DCI=%s' % f[0], '-DCO=%s' % f[1], '-DH=%s' % f[2], '-DW=%s' % f[3]] if len(f) == 4 else ['-DCH=%s' % f[0], '-DH=%s' % f[1], '-DW=%s' % f[2]]
tmp = tempfile.mkdtemp(prefix='pulpnn_'); rows = []
for _, f, shapes, *_ in FAMILIES:
    for b, base, lib, (tp, march) in BUILDS:
        P = both(f'{base}_{f}')
        for s in shapes:
            for p in (0, 1):
                v = P[p][(s, f'pulpnn_{f}')]; elf = f'{tmp}/x.elf'
                cmd = [f'{tp}gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', *PNF.split(), f'-march={march}', f'-DPULPNN_LIB={lib}',
                       f'-DCODE_PAD={p}', *shape_defs(s), '-T', 'sw/link.ld', 'sw/crt0.S', f'sw/pulpnn_{f}.c', '-o', elf]
                subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
                subprocess.run([f'{tp}objcopy', '-O', 'binary', elf, f'{tmp}/x.bin'], check=True)
                with open(f'{tmp}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{tmp}/x.bin'], cwd=ROOT, check=True, stdout=h)
                r = subprocess.run([SIM, '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0', '--redir', f'{tmp}/redir.txt'], capture_output=True, text=True, check=True).stdout
                cyc = int(re.search(r'MEASURED (\d+)', r)[1]); assert cyc == v['cycles'], (base, f, s, p, cyc, v['cycles'])
                ln, targets, ops = disasm(f'{tp}objdump', elf); ba = 0
                for l in open(f'{tmp}/redir.txt'):
                    w, n = l.split(); t = resolve(int(w, 16), ln, targets)
                    if t in ln and t % 4 == 2 and ln[t] == 4: ba += int(n)
                sl, ss, j = v['dread'] - v['ev5'], max(v['dwrite'] - v['ev6'], 0), v['ev7']
                pred4 = v['ev1'] + 2 * v['ev9'] + v['ev2'] + sl
                rows.append(dict(f=f, b=b, s=s, p=p, cyc=cyc, pred4=pred4, ss=ss, ba=ba, j=j, res=cyc - pred4 - ss - ba - j, **ops))
print("\ncycle model on PULP-NN, per family and build (8 runs each: 4 shapes x 2 alignments). First pair of residual\n"
      "columns: I + 2 Bt + Slu + split loads only; second: plus split stores, Ba and J. Static counts per binary:\n"
      "hardware-loop setups and CORE-V loads/stores (post-increment or register-indexed) in the whole program:\n")
print("| kernel | build | hwloop setups | CORE-V ld/st | split stores (max) | Ba (max) | jumps (max) | mean resid, four terms | max | mean resid, full model | max | runs over 1% |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for _, f, *_ in FAMILIES:
    for b, *_ in BUILDS:
        rs = [r for r in rows if r['f'] == f and r['b'] == b]
        e4 = [abs(r['cyc'] - r['pred4']) / r['cyc'] for r in rs]; e = [abs(r['res']) / r['cyc'] for r in rs]
        rng = lambda k: (lambda a, z: f'{a}' if a == z else f'{a}-{z}')(min(r.get(k, 0) for r in rs), max(r.get(k, 0) for r in rs))
        print(f"| {f} | {b} | {rng('setup')} | {rng('ldst')} | {max(r['ss'] for r in rs)} | {max(r['ba'] for r in rs)} | {max(r['j'] for r in rs)} | "
              f"{sum(e4)/len(e4):.2%} | {max(e4):.2%} | {sum(e)/len(e):.2%} | {max(e):.2%} | {sum(x > 0.01 for x in e)} |")
e = [abs(r['res']) / r['cyc'] for r in rows]
print(f"\nall {len(rows)} PULP-NN runs: mean |resid| {sum(e)/len(e):.2%}, max {max(e):.2%}; largest residuals (cycles):",
      ', '.join(f"{r['f']} {r['b']} {r['s']} pad{r['p']} {r['res']:+d}" for r in sorted(rows, key=lambda r: -abs(r['res']))[:4]))
if '--latex' in sys.argv:
    path = sys.argv[sys.argv.index('--latex') + 1]
    fams = ['dw3', 'dw5', 'pw']
    def cell(f, k): v = LX[f]; return f"{v[k]/v['m']:.2f} ({v['o3']/v[k]:.2f}\\x)"
    L = ["% generated by results/pulpnn_model.py --latex; do not edit", "\\begingroup\\setlength{\\tabcolsep}{3pt}", "\\begin{tabular}{lrrr}", "\\toprule",
         " & 3\\x3 dw & 5\\x5 dw & 1\\x1 pw \\\\", "\\midrule",
         "\\texttt{-O3} C & " + ' & '.join(f"{LX[f]['o3']/LX[f]['m']:.2f}" for f in fams) + " \\\\",
         "this study, full Xpulp & " + ' & '.join(cell(f, 'study') for f in fams) + " \\\\", "\\midrule",
         "\\multicolumn{4}{l}{\\textit{PULP-NN, unchanged kernels}} \\\\"]
    for b, lab in (('gcc16 lib', 'GCC 16, library build'), ('gcc16 spec', 'GCC 16, shape-specialised'),
                   ('corev lib', 'CORE-V GCC 14'), ('corev+hwlp lib', 'CORE-V GCC 14, hw loops, post-inc')):
        L.append(f"{lab} & " + ' & '.join(cell(f, b) for f in fams) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}", "\\endgroup"]
    open(path, 'w').write("\n".join(L) + "\n"); print(f"wrote {path}")

