#!/usr/bin/env python3
"""Verify Xpulp hardware loops in an ELF: for every cv.setup, decode lpstart,
lpend and check the body is 32-bit aligned, contains no compressed
instructions and no branches or jumps, has >= 3 instructions, and that lpend
lands on an instruction boundary. Exit 1 on any violation.
Usage: check_hwloop.py <elf> [objdump]"""
import re, subprocess, sys
elf = sys.argv[1]; objdump = sys.argv[2] if len(sys.argv) > 2 else "riscv32-unknown-elf-objdump"
lines = subprocess.run([objdump, "-d", elf], capture_output=True, text=True).stdout.splitlines()
ins = []
for l in lines:
    m = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)(.*)", l)
    if m: ins.append((int(m[1], 16), m[2], m[3], m[4].strip()))
ok = True; found = 0
for i, (pc, hexw, mn, ops) in enumerate(ins):
    if len(hexw) != 8: continue
    w = int(hexw, 16)
    if w & 0x7f != 0x2b or (w >> 12) & 7 != 4: continue
    funct4 = (w >> 8) & 0xf; L = (w >> 7) & 1
    if funct4 not in (0b0110, 0b0111): continue            # setupi / setup only
    found += 1; uimm = w >> 20; start = pc + 4; end = pc + (uimm << 2)
    body = [x for x in ins if start <= x[0] < end]
    problems = []
    if pc % 4: problems.append("setup not 32-bit aligned")
    if start % 4 or end % 4: problems.append("start/end not 32-bit aligned")
    if not any(x[0] == end for x in ins): problems.append("lpend is not an instruction boundary")
    if len(body) < 3: problems.append(f"body has {len(body)} < 3 instructions")
    if any(len(x[1]) == 4 for x in body): problems.append("compressed instruction in body")
    if any(x[2].startswith(("b", "j")) for x in body): problems.append("branch/jump in body")
    print(f"cv.setup{'i' if funct4 == 6 else ''} L={L} at {pc:#x}: lpstart={start:#x} lpend={end:#x} body={len(body)} instr"
          + (": " + "; ".join(problems) if problems else ": ok"))
    ok &= not problems
if not found: print("no hardware loop setup found"); ok = False
sys.exit(0 if ok else 1)
