#!/usr/bin/env python3
"""Stride-2 3x3 depthwise convolution (review round R4, 2026-10-31). The 3x3 kernels built with -DSTRIDE=2
(sw/dwconv_opt.c, dwconv_asm.c, dwconv_simd_asm.c, dwconv_simd_al_asm.c; the stride-1 builds are byte-identical
to before) at four shapes whose rows hold at least one 4-pixel group, both alignments: wait0_s2_dw3_pad{0,1}.csv.
Checks every checksum against an independent Python model of the arithmetic, and reports, per shape, the full
extension's speedup over the hand scalar kernel and over -O3, the Shapley values over the 2^3 grid with each SIMD
formulation, the split-load share of the full-Xpulp kernel and the aligned/unaligned ratio. The cycle model on
these runs is in align_term.py (stride-2 group). Run from results/."""
import csv, collections, itertools, math
SHAPES = ['8x16x16', '32x16x16', '8x32x32', '16x32x32']; S = 2; K = 3
def reference(CH, H, W, stride):
    """Checksum of the int8 3x3 depthwise convolution on the kernels' synthetic data: >> 7, clamp to int8."""
    st = [1]
    def rnd():
        st[0] = (st[0] * 1103515245 + 12345) & 0xFFFFFFFF
        return ((st[0] >> 16) & 0xFF) - 128
    inp = [[[0] * W for _ in range(H)] for _ in range(CH)]; wt = [[[0] * K for _ in range(K)] for _ in range(CH)]
    for c in range(CH):
        for y in range(H):
            for x in range(W): inp[c][y][x] = rnd() >> 2
        for i in range(K):
            for j in range(K): wt[c][i][j] = rnd() >> 3
    OH, OW = (H - K) // stride + 1, (W - K) // stride + 1; tot = 0
    for c in range(CH):
        for oy in range(OH):
            for ox in range(OW):
                acc = sum(inp[c][oy * stride + i][ox * stride + j] * wt[c][i][j] for i in range(K) for j in range(K))
                tot += max(-128, min(127, acc >> 7))
    return tot & 0xFFFF
def load(fn):
    d = collections.defaultdict(dict)
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d[(r['shape'], r['kernel'])][r['event']] = int(r['value']); d[(r['shape'], r['kernel'])]['chk'] = r['chk']
    return d
P = [load(f'wait0_s2_dw3_pad{p}.csv') for p in (0, 1)]
assert reference(8, 16, 16, 1) == 64747   # the reference reproduces the committed stride-1 checksum
ref = {s: reference(*map(int, s.split('x')), S) for s in SHAPES}
bad = sum(int(P[p][k]['chk']) != ref[k[0]] for p in (0, 1) for k in P[p])
print(f'# Stride-2 3x3 depthwise\n\n{sum(len(x) for x in P)} runs; checksum mismatches against the Python reference: {bad}\n')
best = lambda s, k: min((P[p][(s, k)] for p in (0, 1)), key=lambda v: v['cycles'])
def shapley(c):
    val = lambda T: math.log(c[(0, 0, 0)] / c[T]); out = []
    for i in range(3):
        t = 0.0
        for perm in itertools.permutations(range(3)):
            T = [0, 0, 0]
            for j in perm[:perm.index(i)]: T[j] = 1
            a = tuple(T); T[i] = 1; t += val(tuple(T)) - val(a)
        out.append(math.exp(t / 6))
    return out
print('| shape | SIMD formulation | full Xpulp | vs hand | vs -O3 | hand vs -O3 | Shapley: datapath | control | clip | split share | aligned / unaligned |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for s in SHAPES:
    c = lambda k: best(s, k)['cycles']
    for simd in ('simd_unal_asm', 'simd_al_asm'):
        g = {(0, 0, 0): c('scalar_asm_rv'), (0, 1, 0): c('scalar_asm_xp'), (0, 0, 1): c('scalar_asm_rv_clip'), (0, 1, 1): c('scalar_asm_xp_clip'),
             (1, 0, 0): c(simd + '_rv'), (1, 1, 0): c(simd + '_xp'), (1, 0, 1): c(simd + '_rv_clip'), (1, 1, 1): c(simd + '_xp_clip')}
        f = best(s, simd + '_xp_clip'); sh = shapley(g)
        print(f"| {s} | {'unaligned' if 'unal' in simd else 'aligned'} | {g[(1,1,1)]:,} | {g[(0,0,0)]/g[(1,1,1)]:.2f}x | {c('scalar_O3')/g[(1,1,1)]:.2f}x | "
              f"{c('scalar_O3')/c('scalar_asm_rv'):.2f}x | {sh[0]:.2f}x | {sh[1]:.2f}x | {sh[2]:.2f}x | {(f['dread'] - f['ev5'])/f['cycles']:.1%} | "
              f"{c('simd_al_asm_xp_clip')/c('simd_unal_asm_xp_clip'):.2f} |")
# review round R5: why the speedup over the hand kernel grows at stride 2. Per output, at the better alignment, the hand
# scalar kernel against the full-Xpulp unaligned kernel, stride 1 (wait0_decomp, wait0_clip_dw3) against stride 2,
# at the two stride-1 shapes that are also stride-2 shapes.
D1 = [load(f'wait0_decomp_pad{p}.csv') | load(f'wait0_clip_dw3_pad{p}.csv') for p in (0, 1)]
print('\nPer output (loads: retired load instructions):\n\n| shape | kernel | stride 1: cycles | loads | stride 2: cycles | loads |\n|---|---|---|---|---|---|')
for s in ('8x16x16', '8x32x32'):
    ch, h, w = map(int, s.split('x')); n1, n2 = ch * (h - 2) * (w - 2), ch * ((h - 3) // 2 + 1) * ((w - 3) // 2 + 1)
    for k, lab in (('scalar_asm_rv', 'hand scalar'), ('simd_unal_asm_xp_clip', 'full Xpulp, unaligned')):
        a = min((D1[p][(s, k)] for p in (0, 1)), key=lambda v: v['cycles']); b = best(s, k)
        print(f"| {s} | {lab} | {a['cycles']/n1:.2f} | {a['ev5']/n1:.2f} | {b['cycles']/n2:.2f} | {b['ev5']/n2:.2f} |")
