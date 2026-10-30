#!/usr/bin/env python3
"""Time-adjusted speedups: the full-Xpulp cycle speedups of summary_kernels.py
divided by the Xpulp/base clock-period ratio of each penalty statistic in a
clock sweep's penalty CSV (syn/sweep_table.py --stats-csv). Run from results/.

Usage: python3 time_adjusted.py [penalty.csv] [--parasitics rcx|grt]
       (default ../syn/build/sweep-or26rc-rep2/penalty.csv, rcx)

The ratio is pulp_ns / base_ns where the CSV has both periods, else
1 + penalty_pct / 100 (the floor-pairs rows, rounded to 0.01%)."""
import contextlib, csv, io, sys
with contextlib.redirect_stdout(io.StringIO()):
    from summary_kernels import rows   # prints its table on import
args = [a for a in sys.argv[1:] if not a.startswith('--') and a not in ('rcx', 'grt')]
path = args[0] if args else '../syn/build/sweep-or26rc-rep2/penalty.csv'
src = sys.argv[sys.argv.index('--parasitics') + 1] if '--parasitics' in sys.argv else 'rcx'
stats = [r for r in csv.DictReader(open(path)) if r['parasitics'] == src]
def ratio(r): return float(r['pulp_ns']) / float(r['base_ns']) if r['base_ns'] else 1 + float(r['penalty_pct']) / 100
names = [n.split(',')[0] for n, *_ in rows]
print(f"Time-adjusted full-Xpulp speedups, {src} parasitics ({path})\n")
print("| period statistic | period ratio | " + " | ".join(f"{n} vs -O3 | vs hand" for n in names) + " |")
print("|---|---|" + "---|---|" * len(names))
cyc = [(o3['cycles'] / sxc['cycles'], asm['cycles'] / sxc['cycles']) for _, _, _, o3, asm, _, _, sxc in rows]
print("| cycles only | 1 | " + " | ".join(f"{a:.2f}x | {b:.2f}x" for a, b in cyc) + " |")
for r in stats:
    k = ratio(r)
    print(f"| {r['statistic']} | {k:.4f} | " + " | ".join(f"{a / k:.2f}x | {b / k:.2f}x" for a, b in cyc) + " |")
