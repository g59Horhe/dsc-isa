#!/usr/bin/env python3
"""Area and timing table for RESULTS.md and the paper, from the committed flow
outputs: syn/build/{base,pulp}/area.txt (flat synthesis), syn/build/attrib_area.txt
(per-module attribution pass), syn/build/place-{base,pulp}/openroad.txt (OpenROAD
placement + repair_timing at the 10 ns target; placed area) and
syn/build/sweep-or26rc-rep2/penalty.csv (syn/sweep_table.py --stats-csv on the
routed clock sweep; period with extracted parasitics). Nothing here is typed by hand.
Run from results/.  --latex PATH writes paper/tab_area.tex."""
import csv, re, sys
NAND2 = 3.7536; PERIOD = 10.0
B = '../syn/build'
SWEEP = f'{B}/sweep-or26rc-rep2/penalty.csv'
def routed():
    """shortest achieved period per core and the floor-pairs penalty range, extracted parasitics"""
    st = {r['statistic']: r for r in csv.DictReader(open(SWEEP)) if r['parasitics'] == 'rcx'}
    s = st['shortest achieved period, any target']
    return dict(base=float(s['base_ns']), pulp=float(s['pulp_ns']),
                lo=float(st['floor pairs, lowest']['penalty_pct']), hi=float(st['floor pairs, highest']['penalty_pct']))
def flat(cfg): return int(re.search(r'NAND2 eq\s+([\d,]+)', open(f'{B}/{cfg}/area.txt').read())[1].replace(',', ''))
def place(cfg):
    t = open(f'{B}/place-{cfg}/openroad.txt').read()
    slack = float(re.findall(r'WORST_SLACK_AFTER_REPAIR (-?[\d.]+)', t)[-1])
    area = float(re.findall(r'Design area (\d+) u\^2', t)[-1])
    rep = t[t.index('=== repair_timing toward the target period ==='):]
    body = rep[rep.index('clock network delay'):rep.index('data arrival time')]
    stages = len(re.findall(r'^\s+[\d.]+\s+[\d.]+ [v^] \S+/\S+ \(', body, re.M)) - 3   # combinational cells only: minus the launching flop's CLK and Q lines and the capturing D line
    return dict(slack=slack, area=area, ge=area / NAND2, period=PERIOD - slack, stages=stages)
attrib = {}
for l in open(f'{B}/attrib_area.txt'):
    m = re.match(r'(cv32e40p_core\S*|design total)\s+([\d,]+)\s+([\d,]+)\s+(-?[\d,]+)', l)
    if m: attrib[m[1].replace('cv32e40p_core_o_', '').replace('cv32e40p_core', 'untagged')] = int(m[4].replace(',', ''))
tot_attrib = attrib.pop('design total')
fb, fp = flat('base'), flat('pulp'); pb, pp = place('base'), place('pulp'); rt = routed()
groups = [('dot-product multiplier', ['mult']), ('SIMD ALU (carries clip and all vector ops; upper bound for clip)', ['alu']),
          ('register file, third read port', ['register_file']), ('hardware-loop registers', ['hwloop_regs']),
          ('controller + decoder', ['controller', 'decoder']), ('ID stage', ['id_stage'])]
rows = [(lab, sum(attrib[m] for m in ms)) for lab, ms in groups]
other = tot_attrib - sum(v for _, v in rows); listed = sum(v for _, v in rows)
n_other = len(attrib) - sum(len(ms) for _, ms in groups)
rows.append((f'other ({n_other} modules: aligner, CSRs, untagged, prefetch, ...)', other))
loops = attrib['hwloop_regs'] + attrib['controller'] + attrib['decoder']
print(f"| configuration | synthesis GE (flat) | placed GE | shortest routed period, extracted | Fmax |")
print("|---|---|---|---|---|")
for n, f, p, t in (('RV32IMC', fb, pb, rt['base']), ('Xpulp', fp, pp, rt['pulp'])):
    print(f"| {n} | {f:,} | {p['ge']:,.0f} | {t:.2f} ns | {1e3/t:.1f} MHz |")
print(f"| delta | +{fp-fb:,} (+{fp/fb-1:.1%}) | +{pp['ge']-pb['ge']:,.0f} (+{pp['ge']/pb['ge']-1:.1%}) | +{rt['pulp']/rt['base']-1:.1%} | {rt['base']/rt['pulp']-1:+.1%} |")
print(f"\nperiod penalty over every pairing of a base and an Xpulp floor target: +{rt['lo']:.1f}% to +{rt['hi']:.1f}%")
# routed cell area (OpenROAD "Design area" after the post-route repair), from the sweep's per-target rows
SW = [r for r in csv.DictReader(open(f'{B}/sweep-or26rc-rep2/sweep.csv')) if r['area_um2']]
A = {(r['cfg'], float(r['target_ns'])): float(r['area_um2']) for r in SW}
def shortest(cfg): return min((r for r in SW if r['cfg'] == cfg and r['period_rcx']), key=lambda r: float(r['period_rcx']))
sb, sp = shortest('base'), shortest('pulp')
pen = sorted(100 * (A[('pulp', t)] / A[('base', t)] - 1) for (c, t) in A if c == 'base' and ('pulp', t) in A)
print(f"routed cell area, Xpulp over RV32IMC at the same target: {pen[0]:+.1f}% to {pen[-1]:+.1f}% over the {len(pen)} common targets; "
      f"+{100*(A[('pulp',16.0)]/A[('base',16.0)]-1):.1f}% at 16 ns ({A[('base',16.0)]:,.0f} / {A[('pulp',16.0)]:,.0f} um^2); "
      f"at the shortest-period points ({sb['target_ns']} / {sp['target_ns']} ns targets) {A[('base', float(sb['target_ns']))]:,.0f} / {A[('pulp', float(sp['target_ns']))]:,.0f} um^2, "
      f"+{100*(A[('pulp', float(sp['target_ns']))]/A[('base', float(sb['target_ns']))]-1):.1f}%; shortest-period targets 11.0 to 12.0 ns: "
      + ", ".join(f"+{100*(A[('pulp',t)]/A[('base',t)]-1):.1f}%" for t in (11.0, 11.5, 12.0)))
print(f"placement flow (place.tcl, pre-CTS, pre-route, superseded for timing): slack at {PERIOD:.0f} ns {pb['slack']:.2f} / {pp['slack']:.2f} ns, "
      f"period {pb['period']:.2f} / {pp['period']:.2f} ns (+{pp['period']/pb['period']-1:.1%}), path stages {pb['stages']} / {pp['stages']}")
print(f"\nattribution of the extension's synthesis area, grouped (delta {tot_attrib:,} GE in the attribution pass; {fp-fb:,} GE flat, {(fp-fb)/tot_attrib-1:+.1%} apart):\n")
print("| group (modules of origin) | delta GE | share of attribution delta |\n|---|---|---|")
for lab, v in rows: print(f"| {lab} | {v:+,} | {v/tot_attrib:.0%} |")
print(f"| **total, attribution pass** | **{tot_attrib:+,}** | |")
print(f"\nhwloop_regs + controller + decoder = {loops:,} GE; with id_stage {loops + attrib['id_stage']:,} GE. "
      f"SIMD ALU {attrib['alu']:,} GE = {attrib['alu']/loops:.0%} of the first, {attrib['alu']/(loops+attrib['id_stage']):.0%} of the second.")
print(f"listed rows (six groups) sum to {listed:,}; the other {n_other} modules sum to {other:,} GE: " + ', '.join(f"{m} {attrib[m]:+,}" for m in sorted(attrib, key=lambda m: -abs(attrib[m])) if m not in sum((ms for _, ms in groups), [])))
if '--latex' in sys.argv:
    path = sys.argv[sys.argv.index('--latex') + 1]
    L = ["% generated by results/area_table.py --latex; do not edit", "\\begingroup\\setlength{\\tabcolsep}{4pt}", "\\begin{tabular}{lrr}", "\\toprule", " & RV32IMC & Xpulp \\\\", "\\midrule",
         f"synthesis (flat), GE & {fb:,} & {fp:,} (+{fp/fb-1:.1%}) \\\\".replace('%', '\\%'),
         f"placed, GE & {pb['ge']:,.0f} & {pp['ge']:,.0f} (+{pp['ge']/pb['ge']-1:.1%}) \\\\".replace('%', '\\%'),
         f"routed min.\\ period, extracted & {rt['base']:.2f}\\,ns & {rt['pulp']:.2f}\\,ns (+{rt['pulp']/rt['base']-1:.1%}) \\\\".replace('%', '\\%'),
         f"period penalty, floor pairs & \\multicolumn{{2}}{{r}}{{+{rt['lo']:.1f} to +{rt['hi']:.1f}\\%}} \\\\", "\\midrule",
         "\\multicolumn{3}{l}{\\textit{synthesis delta by module of origin}} \\\\",
         f"\\multicolumn{{3}}{{l}}{{\\textit{{({tot_attrib:,} GE attribution pass; {fp-fb:,} GE flat; {abs((fp-fb)/tot_attrib-1):.1%} apart)}}}} \\\\".replace('%', '\\%')]
    short = ['dot-product multiplier', 'SIMD ALU (carries clip: upper bound)', 'register file, third read port', 'hardware-loop registers', 'controller + decoder', 'ID stage', f'other ({n_other} modules)']
    for (lab, v), s in zip(rows, short): L.append(f"{s} & \\multicolumn{{2}}{{r}}{{{v:+,} ({v/tot_attrib:.0%})}} \\\\".replace('%)', '\\%)'))
    L += ["\\bottomrule", "\\end{tabular}", "\\endgroup"]
    open(path, 'w').write("\n".join(L) + "\n"); print(f"wrote {path}")
