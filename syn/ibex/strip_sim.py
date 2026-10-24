#!/usr/bin/env python3
"""Remove the simulation-only `initial` blocks (plusargs, $readmemh, $display)
that sv2v carries over from the generic RAM models in lowRISC prim; yosys
cannot resolve $value$plusargs. Usage: strip_sim.py file.v (in place)."""
import re, sys
p = sys.argv[1]; s = open(p).read()
s2, n = re.subn(r'\tinitial begin : sv2v_autoblock_\d+\n(?:\t\t.*\n)+?\tend\n', '\t/* simulation-only initial block removed for synthesis */\n', s)
open(p, 'w').write(s2); print(f"{p}: removed {n} initial blocks, {s2.count('$value$plusargs')} plusargs remain")
