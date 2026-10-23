#!/usr/bin/env python3
"""Per-module area from two hierarchical yosys `stat -liberty -json` files
(base, pulp). Module names are normalised by stripping the $paramod$<hash>\\
prefix so the two configurations line up. Yosys reports a module's area
including its submodule instances, so each module's own area is recovered by
subtracting its children. Usage: hier_area.py base.json pulp.json NAND2_AREA"""
import json, sys
def norm(n): return n.split("\\")[-1]
def load(fn):
    d = json.load(open(fn)); mods = {norm(n): m for n, m in d["modules"].items()}
    incl = {n: m.get("area", 0.0) for n, m in mods.items()}
    kids = {n: {norm(k): c for k, c in m.get("num_cells_by_type", {}).items() if norm(k) in mods} for n, m in mods.items()}
    own = {n: incl[n] - sum(incl[k] * c for k, c in kids[n].items()) for n in mods}
    return own, d["design"]["area"]
a, ta = load(sys.argv[1]); b, tb = load(sys.argv[2]); nand2 = float(sys.argv[3])
names = sorted(set(a) | set(b), key=lambda n: -(b.get(n, 0) - a.get(n, 0)))
print(f"{'module (own cells)':<30}{'base GE':>10}{'pulp GE':>10}{'delta GE':>10}{'delta %':>9}{'share of delta':>15}")
for n in names:
    x, y = a.get(n, 0) / nand2, b.get(n, 0) / nand2
    if x < 1 and y < 1: continue
    print(f"{n:<30}{x:>10,.0f}{y:>10,.0f}{y-x:>10,.0f}{((y-x)/x*100 if x else float('nan')):>8.0f}%{(y-x)/((tb-ta)/nand2)*100:>14.0f}%")
print(f"{'design total':<30}{ta/nand2:>10,.0f}{tb/nand2:>10,.0f}{(tb-ta)/nand2:>10,.0f}{(tb-ta)/ta*100:>8.0f}%")
print(f"check: sum of own areas base={sum(a.values())/nand2:,.0f} pulp={sum(b.values())/nand2:,.0f} GE (should equal design totals)")
