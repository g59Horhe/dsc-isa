#!/usr/bin/env python3
"""Summarise a yosys `stat -liberty -json` file: total area, NAND2 equivalents,
and the ten largest cell types. Usage: area.py stat.json NAND2_AREA"""
import json, sys
d = json.load(open(sys.argv[1])); nand2 = float(sys.argv[2])
top = d["design"] if "design" in d else list(d["modules"].values())[0]
area = top.get("area", 0.0); cells = top.get("num_cells", 0)
print(f"cells      {cells}")
print(f"area       {area:,.1f} um^2")
print(f"NAND2 eq   {area/nand2:,.0f}")
by = top.get("num_cells_by_type", {})
for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:10]:
    print(f"  {k:<40} {v}")
