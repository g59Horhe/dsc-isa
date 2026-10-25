#!/usr/bin/env python3
"""Branch-target alignment term for the cycle model.

A taken branch, jump or hardware-loop return whose target is a 32-bit
instruction at an address 2 mod 4 costs one extra cycle in the CV32E40P
aligner: the fetched word holds only the lower half of the instruction. This
script measures that term, Ba, for every hand-written run and the 48
equalised-requantisation runs: it rebuilds each binary exactly as
harness/collect_wait0.sh does (and asserts the cycle count matches the
committed CSV), runs it with --redir to get the histogram of non-sequential
instruction fetches (word addresses) in the measured window, resolves each
redirect to its target PC with the ELF's disassembly, and counts the
redirects whose target satisfies the rule. Three candidate rules are
evaluated against all runs (see flagged()); rule A above fits best and is
written. Output: results/wait0_align.csv (shape,kernel,pad,cycles,redirects,
ba,ba_rule_a,ba_rule_b,ba_rule_c) and the residuals with and without the
term. Run from results/.
cycles = I + 2 Bt + Slu + Asplit + Ba."""
import csv, collections, os, re, subprocess, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GCC = '/opt/riscv/bin/riscv32-unknown-elf-gcc'; OBJCOPY = '/opt/riscv/bin/riscv32-unknown-elf-objcopy'; OBJDUMP = '/opt/riscv/bin/riscv32-unknown-elf-objdump'
SIM = f'{ROOT}/harness/obj_pulp/Vcv32e40p_core'
DW = ['8x16x16', '16x16x16', '8x32x32', '32x8x8']; PW = ['16x16x8x8', '8x8x16x16', '16x32x8x8', '16x16x16x16']
XP = '-DXPULP_CTRL=1'; CL = '-DREQUANT_CLIP=1'
def grid(prefix_rv, src, suffix='', clip=False):
    out = {}
    for ctl, flag in (('rv', ''), ('xp', XP)):
        out[f'{prefix_rv}_{ctl}{suffix}'] = (src, f'-O2 {flag} {CL if clip else ""}'.strip())
    return out
SETS = [  # (csv base, shapes, {kernel: (source, cflags)})
  ('wait0_eqrequant', DW, {'scalar_O2': ('sw/dwconv_opt.c', '-O2'), 'scalar_O3': ('sw/dwconv_opt.c', '-O3'), 'scalar_asm': ('sw/dwconv_asm.c', '-O2'),
                           'simd_unal': ('sw/dwconv_simd.c', '-O2'), 'simd_al': ('sw/dwconv_simd_al.c', '-O2'), 'simd_al_O3': ('sw/dwconv_simd_al.c', '-O3')}),
  ('wait0_decomp', DW, {**grid('scalar_asm', 'sw/dwconv_asm.c'), **grid('simd_unal_asm', 'sw/dwconv_simd_asm.c'), **grid('simd_al_asm', 'sw/dwconv_simd_al_asm.c')}),
  ('wait0_clip_dw3', DW, {**grid('scalar_asm', 'sw/dwconv_asm.c', '_clip', True), **grid('simd_unal_asm', 'sw/dwconv_simd_asm.c', '_clip', True), **grid('simd_al_asm', 'sw/dwconv_simd_al_asm.c', '_clip', True)}),
  ('wait0_dw5', DW, {**grid('dw5_asm', 'sw/dwconv5_asm.c'), **grid('dw5_simd', 'sw/dwconv5_simd_asm.c')}),
  ('wait0_clip_dw5', DW, {**grid('dw5_asm', 'sw/dwconv5_asm.c', '_clip', True), **grid('dw5_simd', 'sw/dwconv5_simd_asm.c', '_clip', True)}),
  ('wait0_dw5os', DW, {**grid('dw5_os_asm', 'sw/dwconv5_os_asm.c'), **grid('dw5_os_asm', 'sw/dwconv5_os_asm.c', '_clip', True)}),
  ('wait0_pw', PW, {**grid('pw_asm', 'sw/pwconv_asm.c'), **grid('pw_simd_asm', 'sw/pwconv_simd_asm.c')}),
  ('wait0_clip_pw', PW, {**grid('pw_asm', 'sw/pwconv_asm.c', '_clip', True), **grid('pw_simd_asm', 'sw/pwconv_simd_asm.c', '_clip', True)}),
]
BR = {'beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu', 'beqz', 'bnez', 'blez', 'bgez', 'bltz', 'bgtz', 'j', 'jal', 'c.j', 'c.jal', 'c.beqz', 'c.bnez'}
def load(fn):
    d = collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'], r['kernel']), {})[r['event']] = int(r['value'])
    for v in d.values():
        v['instr'] = v['ev1']; v['ldstall'] = v['ev2']; v['loads'] = v['ev5']; v['brtaken'] = v['ev9']; v['split'] = v['dread'] - v['loads']
        v['pred'] = v['instr'] + 2 * v['brtaken'] + v['ldstall'] + v['split']
    return d
def disasm(elf):
    """addr -> length, and the set of static redirect targets (branch/jump targets, hardware-loop starts)."""
    ln = {}; targets = set()
    for l in subprocess.run([OBJDUMP, '-d', elf], capture_output=True, text=True, check=True).stdout.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$', l)
        if not m: continue
        a = int(m[1], 16); word = int(m[2], 16); n = len(m[2]) // 2; ln[a] = n
        if m[3] in BR:
            t = re.search(r'([0-9a-f]+)\s*<', m[4]) or re.search(r'([0-9a-f]{8})\s*$', m[4])
            if t: targets.add(int(t[1], 16))
        if n == 4 and (word & 0x707f) == 0x402b and ((word >> 7) & 0x1f) == 14: targets.add(a + 4)   # cv.setup loop 0: lpstart = PC + 4
    return ln, targets
# Three candidate rules for which redirect targets pay the aligner cycle, tested against all runs below:
#   A: the instruction at the target is 32-bit and the target address is 2 mod 4 (the target word holds
#      only its lower half, so the aligner waits one cycle for the next word);
#   B: the first 32-bit instruction reached from the target, skipping compressed ones, is at 2 mod 4;
#   C: the target address is 2 mod 4, whatever the instruction.
def flagged(pc, ln, rule):
    if pc not in ln: return False
    if rule == 'A': return pc % 4 == 2 and ln[pc] == 4
    if rule == 'C': return pc % 4 == 2
    while ln.get(pc) == 2: pc += 2
    return pc % 4 == 2 if pc in ln else False
RULES = 'ABC'
def resolve(word, ln, targets):
    cands = [c for c in (word, word + 2) if c in ln]
    hit = [c for c in cands if c in targets]
    return (hit or cands or [word])[0]
def shape_defs(s):
    f = s.split('x')
    return ['-DCI=%s' % f[0], '-DCO=%s' % f[1], '-DH=%s' % f[2], '-DW=%s' % f[3]] if len(f) == 4 else ['-DCH=%s' % f[0], '-DH=%s' % f[1], '-DW=%s' % f[2]]
rows = []; tmp = tempfile.mkdtemp(prefix='align_')
for base, shapes, kernels in SETS:
    P = {p: load(f'{base}_pad{p}.csv') for p in (0, 1)}
    for s in shapes:
        for k, (src, cf) in kernels.items():
            for p in (0, 1):
                elf = f'{tmp}/x.elf'; v = P[p][(s, k)]
                cmd = [GCC, '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', *cf.split(), f'-DCODE_PAD={p}', *shape_defs(s), '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', elf]
                subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
                subprocess.run([OBJCOPY, '-O', 'binary', elf, f'{tmp}/x.bin'], check=True)
                with open(f'{tmp}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{tmp}/x.bin'], cwd=ROOT, check=True, stdout=h)
                r = subprocess.run([SIM, '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0', '--redir', f'{tmp}/redir.txt'], capture_output=True, text=True, check=True).stdout
                cyc = int(re.search(r'MEASURED (\d+)', r)[1])
                assert cyc == v['cycles'], (base, s, k, p, cyc, v['cycles'])   # the rebuilt binary must reproduce the committed count
                ln, targets = disasm(elf)
                nred = 0; ba = {r: 0 for r in RULES}
                for l in open(f'{tmp}/redir.txt'):
                    w, n = l.split(); w = int(w, 16); n = int(n); nred += n; t = resolve(w, ln, targets)
                    for r in RULES:
                        if flagged(t, ln, r): ba[r] += n
                rows.append(dict(base=base, shape=s, kernel=k, pad=p, cycles=cyc, redirects=nred, **{f'ba_{r.lower()}': ba[r] for r in RULES}, **{x: v[x] for x in ('instr', 'brtaken', 'ldstall', 'split', 'pred')}))
def err(rs, col): return [abs(r['cycles'] - r['pred'] - r[col]) / r['cycles'] for r in rs]
# the equalised set's scalar_asm is the same source and flags as the decomposition set's scalar_asm_rv (identical binaries and
# cycle counts), so the union has 8 fewer distinct runs than the sum
distinct = [r for r in rows if not (r['base'] == 'wait0_eqrequant' and r['kernel'] == 'scalar_asm')]
print(f"rule | mean |resid| | max | runs over 1% ({len(distinct)} distinct runs); sw/ubench_align.c confirms rule A: +1 cycle per iteration only with a 32-bit instruction at a 2 mod 4 target")
for r in RULES:
    e = err(distinct, f'ba_{r.lower()}'); print(f"{r} | {sum(e)/len(e):.2%} | {max(e):.2%} | {sum(x > 0.01 for x in e)}")
BEST = min(RULES, key=lambda r: sum(err(distinct, f'ba_{r.lower()}')))
for r in rows: r['ba'] = r[f'ba_{BEST.lower()}']
print(f"rule {BEST} written as ba")
with open('wait0_align.csv', 'w') as f:
    f.write('shape,kernel,pad,cycles,redirects,ba,ba_rule_a,ba_rule_b,ba_rule_c\n')
    for r in rows: f.write(f"{r['shape']},{r['kernel']},{r['pad']},{r['cycles']},{r['redirects']},{r['ba']},{r['ba_a']},{r['ba_b']},{r['ba_c']}\n")
def stats(rs, label):
    old = [abs(r['cycles'] - r['pred']) / r['cycles'] for r in rs]; new = [abs(r['cycles'] - r['pred'] - r['ba']) / r['cycles'] for r in rs]
    print(f"{label}: {len(rs)} runs; four-term model mean |resid| {sum(old)/len(old):.2%} max {max(old):.2%}; with the alignment term mean {sum(new)/len(new):.2%} max {max(new):.2%}; "
          f"runs over 1%: {sum(x > 0.01 for x in old)} -> {sum(x > 0.01 for x in new)}; runs with Ba > 0: {sum(r['ba'] > 0 for r in rs)}")
hw = [r for r in rows if r['base'] != 'wait0_eqrequant']; eq = [r for r in rows if r['base'] == 'wait0_eqrequant']
stats(eq, 'equalised 3x3 set (6 kernels x 4 shapes x 2 alignments)'); stats(hw, 'hand-written runs (three families, with and without clip)'); stats(distinct, 'all distinct runs (equalised scalar_asm = decomposition scalar_asm_rv, counted once)')
print("\n| run | cycles | I | 2Bt | Slu | Asplit | redirects | Ba | residual, four terms | residual, five terms |\n|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(rows, key=lambda r: -abs(r['cycles'] - r['pred']) / r['cycles'])[:12]:
    print(f"| {r['kernel']} {r['shape']} pad{r['pad']} | {r['cycles']:,} | {r['instr']:,} | {2*r['brtaken']:,} | {r['ldstall']:,} | {r['split']:,} | {r['redirects']:,} | {r['ba']:,} | {(r['cycles']-r['pred'])/r['cycles']:+.2%} | {(r['cycles']-r['pred']-r['ba'])/r['cycles']:+.2%} |")
