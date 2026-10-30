import csv, collections, sys
S='.'
def load(fn):
    d=collections.OrderedDict()
    for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE')):
        d.setdefault((r['shape'],r['kernel']),{})[r['event']]=int(r['value']) if r['value'].isdigit() else r['value']
        d[(r['shape'],r['kernel'])]['chk']=r['chk']
    for v in d.values():
        v['instr']=v.pop('ev1'); v['ldstall']=v.pop('ev2'); v['loads']=v.pop('ev5'); v['brtaken']=v.pop('ev9')
        v['split']=v['dread']-v['loads']
        v['pred']=v['instr']+2*v['brtaken']+v['ldstall']+v['split']; v['resid']=v['cycles']-v['pred']
    return d
P={p:load(f"{S}/wait0_eqrequant_pad{p}.csv") for p in (0,1)}
keys=list(P[0].keys())
print("=== Wait 0, branchless requant in every kernel. cycles at both code alignments; counters from pad0 ===")
hdr=f"{'shape':<9}{'kernel':<11}{'cyc pad0':>9}{'cyc pad1':>9}{'instr':>8}{'ifetch':>8}{'dread':>7}{'dwrite':>7}{'brtaken':>8}{'ldstall':>8}{'split':>6}{'resid0':>7}{'resid1':>7}{'chk':>6}"
print(hdr); last=None
for k in keys:
    a,b=P[0][k],P[1][k]
    if k[0]!=last and last: print()
    last=k[0]
    print(f"{k[0]:<9}{k[1]:<11}{a['cycles']:>9}{b['cycles']:>9}{a['instr']:>8}{a['ifetch']:>8}{a['dread']:>7}{a['dwrite']:>7}{a['brtaken']:>8}{a['ldstall']:>8}{a['split']:>6}{a['resid']:>7}{b['resid']:>7}{a['chk']:>6}")
print("\n=== alignment sensitivity: |pad1-pad0|/min ===")
for k in keys:
    a,b=P[0][k]['cycles'],P[1][k]['cycles']; print(f"{k[0]:<9}{k[1]:<11} {abs(a-b)/min(a,b)*100:5.1f}%")
print("\n=== speedups (using the better alignment for each kernel), and instruction-count ratios ===")
shapes=sorted(set(k[0] for k in keys), key=lambda s: keys.index((s,'scalar_O2')))
print(f"{'shape':<9}{'SIMD-al vs O2':>14}{'vs O3':>8}{'vs asm':>8}{'instr O2/al':>12}{'instr asm/al':>13}{'unal vs asm':>12}")
for s in shapes:
    best=lambda k: min(P[0][(s,k)]['cycles'],P[1][(s,k)]['cycles'])
    al=min(best('simd_al'),best('simd_al_O3')); 
    print(f"{s:<9}{best('scalar_O2')/al:>14.2f}{best('scalar_O3')/al:>8.2f}{best('scalar_asm')/al:>8.2f}{P[0][(s,'scalar_O2')]['instr']/P[0][(s,'simd_al')]['instr']:>12.2f}{P[0][(s,'scalar_asm')]['instr']/P[0][(s,'simd_al')]['instr']:>13.2f}{best('scalar_asm')/best('simd_unal'):>12.2f}")
print("\n=== cycle decomposition, pad with smaller residual, 8x16x16 ===")
for k in [k for k in keys if k[0]=='8x16x16']:
    v=min((P[0][k],P[1][k]),key=lambda v:abs(v['resid']))
    c=v['cycles']; print(f"{k[1]:<11} instr {v['instr']/c*100:5.1f}%  2*brtaken {2*v['brtaken']/c*100:5.1f}%  ldstall {v['ldstall']/c*100:5.1f}%  split {v['split']/c*100:5.1f}%  resid {v['resid']/c*100:5.1f}%")
def r2(xs,ys):
    n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
    sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys)); sxx=sum((x-mx)**2 for x in xs); syy=sum((y-my)**2 for y in ys)
    b=sxy/sxx; a=my-b*mx; return 1-sum((y-(a+b*x))**2 for x,y in zip(xs,ys))/syy
allv=[v for p in (0,1) for v in P[p].values()]; ys=[v['cycles'] for v in allv]
print("\n=== R^2 over all 48 runs ===")
for x in ['instr','ifetch','loads','dread','dwrite','pred']: print(f"{x:<8} R2={r2([v[x] for v in allv],ys):.4f}")
print(f"max |resid|/cycles = {max(abs(v['resid'])/v['cycles'] for v in allv)*100:.1f}%")
ape=[abs(v['resid'])/v['cycles'] for v in allv]
print(f"coefficients fixed from microbenchmarks (not fitted): mean |resid|/cycles = {sum(ape)/len(ape)*100:.2f}% (MAPE), max {max(ape)*100:.2f}%, over {len(allv)} runs")
try:   # five-term model: + Ba, the branch-target alignment term measured per run by results/align_term.py
    A={(r['shape'],r['kernel'],int(r['pad'])):int(r['ba']) for r in csv.DictReader(open(f"{S}/wait0_align.csv"))}
    J={(r['shape'],r['kernel'],int(r['pad'])):int(r['jumps']) for r in csv.DictReader(open(f"{S}/wait0_align.csv"))}
    for p in (0,1):
        for k,v in P[p].items(): v['pred5']=v['pred']+A[(k[0],k[1],p)]; v['pred6']=v['pred5']+J[(k[0],k[1],p)]
    ape5=[abs(v['cycles']-v['pred5'])/v['cycles'] for v in allv]; ape6=[abs(v['cycles']-v['pred6'])/v['cycles'] for v in allv]
    print(f"with the alignment term Ba (cycles = I + 2 Bt + Slu + Asplit + Ba): R2={r2([v['pred5'] for v in allv],ys):.4f}, mean |resid| {sum(ape5)/len(ape5)*100:.2f}%, max {max(ape5)*100:.2f}%")
    print(f"with Ba and the jump term J (cycles = I + 2 Bt + Slu + Asplit + Ba + J): mean |resid| {sum(ape6)/len(ape6)*100:.3f}%, max {max(ape6)*100:.3f}%, exact {sum(v['cycles']==v['pred6'] for v in allv)} of {len(allv)}")
except FileNotFoundError: pass

# ---------------------------------------------------------------- markdown tables for RESULTS.md
# Counters and cycles in every row come from the same binary (harness EVENTS line, see
# harness/collect_wait0.sh). "Better alignment" picks, per kernel, the code alignment with
# fewer cycles; the counters quoted with it come from that same run.
NAMES = {'scalar_O2': 'scalar C, -O2', 'scalar_O3': 'scalar C, -O3', 'scalar_asm': 'scalar asm', 'simd_unal': 'SIMD unaligned', 'simd_al': 'SIMD aligned', 'simd_al_O3': 'SIMD aligned, -O3'}
try:
    BA = {(r['shape'], r['kernel'], int(r['pad'])): int(r['ba']) for r in csv.DictReader(open(f"{S}/wait0_align.csv"))}
    JA = {(r['shape'], r['kernel'], int(r['pad'])): int(r['jumps']) for r in csv.DictReader(open(f"{S}/wait0_align.csv"))}
except FileNotFoundError:
    BA = {}; JA = {}
for p in (0, 1):   # pred5/resid5: the full model, with Ba and J
    for k, v in P[p].items(): v['ba'] = BA.get((k[0], k[1], p), 0); v['j'] = JA.get((k[0], k[1], p), 0); v['pred5'] = v['pred'] + v['ba'] + v['j']; v['resid5'] = v['cycles'] - v['pred5']
bestrun = lambda s, k: min(P[0][(s, k)], P[1][(s, k)], key=lambda v: v['cycles'])
print("\n## markdown: Table 1\n")
print("| shape | kernel | cycles (pad 0) | cycles (pad 1) | instructions | fetches | data reads | data writes | taken branches | load-use stalls | split-load accesses | checksum |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for s in shapes:
    for i, k in enumerate(NAMES):
        a, b = P[0][(s, k)], P[1][(s, k)]
        print(f"| {s if i == 0 else ''} | {NAMES[k]} | {a['cycles']:,} | {b['cycles']:,} | {a['instr']:,} | {a['ifetch']:,} | {a['dread']:,} | {a['dwrite']:,} | {a['brtaken']:,} | {a['ldstall']:,} | {a['split']:,} | {a['chk']} |")
print("\n## markdown: predictors\n")
print("| predictor | R^2 over 48 runs |\n|---|---|")
for lab, key in (("five-term model (with the alignment term)", 'pred5'), ("four-term model (without it)", 'pred'), ("instructions retired alone", 'instr'), ("instruction fetches alone", 'ifetch'), ("loads alone", 'loads'), ("data reads alone", 'dread')):
    print(f"| {lab} | {r2([v[key] for v in allv], ys):.4f} |")
print("\n## markdown: per-kernel shares\n")
print("| shape | kernel | instructions | taken-branch penalty | load-use stalls | split loads | alignment term | residual |")
print("|---|---|---|---|---|---|---|---|")
for s in shapes:
    for k in NAMES:
        v = bestrun(s, k); c = v['cycles']
        print(f"| {s} | {NAMES[k]} | {v['instr']/c:.1%} | {2*v['brtaken']/c:.1%} | {v['ldstall']/c:.1%} | {v['split']/c:.1%} | {v['ba']/c:.1%} | {v['resid5']/c:+.1%} |")
print("\n## markdown: Table 2\n")
print("| shape | SIMD aligned vs -O2 | instr ratio | vs -O3 | instr ratio | vs asm | instr ratio | SIMD unaligned vs asm |")
print("|---|---|---|---|---|---|---|---|")
for s in shapes:
    al = min(bestrun(s, 'simd_al'), bestrun(s, 'simd_al_O3'), key=lambda v: v['cycles'])
    o2, o3, asm, un = (bestrun(s, k) for k in ('scalar_O2', 'scalar_O3', 'scalar_asm', 'simd_unal'))
    print(f"| {s} | {o2['cycles']/al['cycles']:.2f}x | {o2['instr']/al['instr']:.2f} | {o3['cycles']/al['cycles']:.2f}x | {o3['instr']/al['instr']:.2f} | {asm['cycles']/al['cycles']:.2f}x | {asm['instr']/al['instr']:.2f} | {asm['cycles']/un['cycles']:.2f}x |")
