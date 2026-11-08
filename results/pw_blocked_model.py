#!/usr/bin/env python3
"""Pointwise convolution beyond 16 input channels (review round R7, 2026-11-01): results/wait0_pwb_pad{0,1}.csv.
The register-resident pointwise kernels hold one pixel's input channels in registers and exist for CI = 8 and 16;
every MobileNetV1 pointwise layer has CI >= 32. The blocked kernels (sw/gen_pwconv_blk_asm.py) take the input
channels in blocks, the scalar kernel 16 per block, the SIMD kernel up to 64 (as 16 words), and carry int32
partial sums between blocks in a CO-word buffer. The same 2^3 grid (datapath, control, clip) at 32, 64 and 128
input channels, CO = 16, 8x8 pixels, against the register-resident kernels at 16x16x8x8. Each kernel at its better
code alignment. Run from results/; with --latex PATH also writes the paper's table."""
import collections, csv, itertools, math, sys
def load(base, p):
    d = collections.defaultdict(dict)
    for r in csv.DictReader(l for l in open(f'{base}_pad{p}.csv') if not l.startswith('DONE')):
        d[(r['shape'], r['kernel'])][r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    return d
ALIGN = {(r['shape'], r['kernel'], int(r['pad'])): r for r in csv.DictReader(open('wait0_align.csv'))}
def both(base): return [load(base, p) for p in (0, 1)]
def best(D, s, k):
    p = min((0, 1), key=lambda p: D[p][(s, k)]['cycles']); v = dict(D[p][(s, k)], pad=p)
    a = ALIGN[(s, k, p)]; v['split'] = v['dread'] - v['ev5']
    v['model'] = v['ev1'] + 2 * v['ev9'] + v['ev2'] + v['split'] + int(a['ba']) + int(a['jumps'])
    return v
def shapley(cyc):   # as in clip_model.py
    val = lambda S: math.log(cyc[(0, 0, 0)] / cyc[S]); out = []
    for i in range(3):
        tot = 0.0
        for perm in itertools.permutations(range(3)):
            S = [0, 0, 0]
            for j in perm[:perm.index(i)]: S[j] = 1
            S0 = tuple(S); S[i] = 1; tot += val(tuple(S)) - val(S0)
        out.append(math.exp(tot / 6))
    return out
def cells(D, s, sc, si, ctl=('rv', 'xp'), clip=('', '_clip')):   # (datapath, control, clip) -> cycles
    return {(d, c, k): best(D, s, f"{(sc, si)[d]}_{ctl[c]}{clip[k]}")['cycles'] for d in (0, 1) for c in (0, 1) for k in (0, 1)}
B = both('wait0_pwb'); R = [load(f'wait0_{n}', p) for n in ('pw', 'clip_pw') for p in (0, 1)]
R = [{**R[0], **R[2]}, {**R[1], **R[3]}]
SH = ['32x16x8x8', '64x16x8x8', '128x16x8x8']; REF = '16x16x8x8'
macs = lambda s: (lambda ci, co, h, w: ci * co * h * w)(*map(int, s.split('x')))
rows = []
for s, D, sc, si in [(REF, R, 'pw_asm', 'pw_simd_asm')] + [(s, B, 'pwb_asm', 'pwb_simd_asm') for s in SH]:
    chk = {v['chk'] for (sh, k), v in D[0].items() if sh == s} | {v['chk'] for (sh, k), v in D[1].items() if sh == s}
    g = cells(D, s, sc, si); sh = shapley(g); h = best(D, s, f'{sc}_rv'); f = best(D, s, f'{si}_xp_clip')
    o3 = min(D[p][(s, 'pw_C_O3')]['cycles'] for p in (0, 1)); o2 = min(D[p][(s, 'pw_C_O2')]['cycles'] for p in (0, 1))
    outs = macs(s) // int(s.split('x')[0])
    rows.append(dict(s=s, kind='register-resident' if s == REF else 'blocked', chk=chk, o2=o2, o3=o3, hand=h['cycles'], full=f['cycles'],
                     sp=h['cycles'] / f['cycles'], sp3=o3 / f['cycles'], ir=h['ev1'] / f['ev1'], sh=sh, cpm_h=h['cycles'] / macs(s), cpm_f=f['cycles'] / macs(s),
                     ld_h=h['ev5'] / outs, ld_f=f['ev5'] / outs, st_h=h['dwrite'] / outs, st_f=f['dwrite'] / outs,
                     first=(g[(0, 0, 0)] / g[(1, 0, 0)], g[(0, 0, 0)] / g[(0, 1, 0)], g[(0, 0, 0)] / g[(0, 0, 1)]),
                     last=(g[(0, 1, 1)] / g[(1, 1, 1)], g[(1, 0, 1)] / g[(1, 1, 1)], g[(1, 1, 0)] / g[(1, 1, 1)]),
                     exact=all(best(D, s, f"{(sc, si)[d]}_{c}{k}")['model'] == best(D, s, f"{(sc, si)[d]}_{c}{k}")['cycles'] for d in (0, 1) for c in ('rv', 'xp') for k in ('', '_clip'))))
print("## Pointwise beyond 16 input channels: the grid with the input channels in blocks\n")
print("| shape (CIxCOxHxW) | kernels | checksums | C -O2 | C -O3 | hand scalar | full Xpulp | vs hand | vs -O3 | instr. ratio | Shapley dp | ctl | clip | cycles/MAC hand / full | loads per output hand / full | stores per output hand / full | Eq. 1 exact (8 cells) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print(f"| {r['s']} | {r['kind']} | {'/'.join(sorted(r['chk']))} | {r['o2']:,} | {r['o3']:,} | {r['hand']:,} | {r['full']:,} | {r['sp']:.2f}x | {r['sp3']:.2f}x | {r['ir']:.2f} | "
          f"{r['sh'][0]:.2f}x | {r['sh'][1]:.2f}x | {r['sh'][2]:.2f}x | {r['cpm_h']:.2f} / {r['cpm_f']:.2f} | {r['ld_h']:.2f} / {r['ld_f']:.2f} | {r['st_h']:.2f} / {r['st_f']:.2f} | {r['exact']} |")
print("\nadded first (to the hand scalar kernel) / added last (on top of the other two), datapath, control, clip:\n")
for r in rows: print(f"- {r['s']}: first {' / '.join(f'{x:.2f}x' for x in r['first'])}; last {' / '.join(f'{x:.2f}x' for x in r['last'])}")
bl = rows[1:]
print(f"\nblocked, 32 to 128 input channels: full Xpulp {min(r['sp'] for r in bl):.2f}x to {max(r['sp'] for r in bl):.2f}x over the hand scalar kernel "
      f"(register-resident, 16 input channels: {rows[0]['sp']:.2f}x); Shapley datapath {min(r['sh'][0] for r in bl):.2f}x to {max(r['sh'][0] for r in bl):.2f}x, "
      f"control {min(r['sh'][1] for r in bl):.2f}x to {max(r['sh'][1] for r in bl):.2f}x, clip {min(r['sh'][2] for r in bl):.2f}x to {max(r['sh'][2] for r in bl):.2f}x; "
      f"C -O3 is {min(r['o3'] / r['hand'] for r in bl):.2f}x to {max(r['o3'] / r['hand'] for r in bl):.2f}x the hand kernel's cycles (GCC unrolls the 16-channel loop fully, not the longer ones)")
if '--latex' in sys.argv:
    L = ["% generated by results/pw_blocked_model.py --latex; do not edit", "\\begin{tabular}{lrrrrrrr}", "\\toprule",
         "$C_{in}$ & hand & full Xpulp & speedup & dp & ctl & clip & cyc/MAC \\\\", "\\midrule"]
    for r in rows:
        L.append(f"{r['s'].split('x')[0]}{'$^*$' if r['kind'] != 'blocked' else ''} & {r['hand']:,} & {r['full']:,} & {r['sp']:.2f}\\x & {r['sh'][0]:.2f}\\x & {r['sh'][1]:.2f}\\x & {r['sh'][2]:.2f}\\x & {r['cpm_f']:.2f} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]
    path = sys.argv[sys.argv.index('--latex') + 1]; open(path, 'w').write("\n".join(L) + "\n"); print(f"wrote {path}")
