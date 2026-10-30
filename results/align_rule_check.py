#!/usr/bin/env python3
"""Reviewer question Q3: is the branch-target alignment term B_a a property of the aligner alone?
Runs sw/ubench_align.c (1,000 iterations, four layouts of the loop's target) on the RTL harness with
zero-wait instruction memory, 1 to 3 instruction-port wait states, and a 1 KB direct-mapped
instruction cache with a three-cycle miss, on two cores: the default CV32E40P (prefetch FIFO depth 2)
and the same RTL with FIFO_DEPTH = 4 in cv32e40p_prefetch_buffer.sv. The second core is built here
from a patched copy of the RTL in harness/obj_fifo4/ (git-ignored); the submodule is not touched.
Run from results/ (a few minutes the first time, for the build)."""
import os, re, shutil, subprocess
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GCC = os.environ.get('RISCV_BIN', '/opt/riscv/bin') + '/riscv32-unknown-elf-'
CORE = f'{ROOT}/third_party/cv32e40p'; F4 = f'{ROOT}/harness/obj_fifo4'
SIMS = {'2 (default)': f'{ROOT}/harness/obj_pulp/Vcv32e40p_core', '4': f'{F4}/obj/Vcv32e40p_core'}
if not os.path.exists(SIMS['4']):
    shutil.rmtree(F4, ignore_errors=True); os.makedirs(F4)
    for d in ('rtl', 'bhv'): shutil.copytree(f'{CORE}/{d}', f'{F4}/{d}')
    p = f'{F4}/rtl/cv32e40p_prefetch_buffer.sv'; s = open(p).read()
    a = 'localparam FIFO_DEPTH                     = 2;'; assert s.count(a) == 1; open(p, 'w').write(s.replace(a, a.replace('= 2;', '= 4;')))
    srcs = [f'{F4}/rtl/include/{f}' for f in ('cv32e40p_pkg.sv', 'cv32e40p_apu_core_pkg.sv', 'cv32e40p_fpu_pkg.sv')]
    srcs += sorted(f'{F4}/rtl/{f}' for f in os.listdir(f'{F4}/rtl') if f.endswith('.sv') and f not in ('cv32e40p_fp_wrapper.sv', 'cv32e40p_top.sv'))
    srcs.append(f'{F4}/bhv/cv32e40p_sim_clock_gate.sv')
    subprocess.run(['verilator', '--cc', '--exe', '--build', '-j', '4', '-Wno-fatal', '-Wno-BLKANDNBLK', '--top-module', 'cv32e40p_core',
                    f'-I{F4}/rtl/include', f'-I{F4}/rtl', '--Mdir', f'{F4}/obj', '-GCOREV_PULP=1', f'{ROOT}/harness/public.vlt', *srcs,
                    f'{ROOT}/harness/sim_main.cpp'], check=True, capture_output=True)
hexes = []
for v in range(4):
    e = f'{F4}/a{v}'
    subprocess.run([GCC + 'gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', '-O2', f'-DVARIANT={v}',
                    '-T', 'sw/link.ld', 'sw/crt0.S', 'sw/ubench_align.c', '-o', e + '.elf'], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([GCC + 'objcopy', '-O', 'binary', e + '.elf', e + '.bin'], check=True)
    with open(e + '.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', e + '.bin'], cwd=ROOT, check=True, stdout=h)
    hexes.append(e + '.hex')
MEM = [('zero wait', []), ('1 instruction wait state', ['--iwait', '1']), ('2 instruction wait states', ['--iwait', '2']),
       ('3 instruction wait states', ['--iwait', '3']), ('1 KB I-cache, 3-cycle miss', ['--iwait', '3', '--icache', '1024', '16'])]
print("| prefetch FIFO depth | instruction memory | aligned | 32-bit at 2 mod 4 | 16-bit at 2 mod 4 | 32-bit after a 16-bit | aligner cycles per iteration |")
print("|---|---|---|---|---|---|---|")
for depth, sim in SIMS.items():
    for lab, args in MEM:
        c = [int(re.search(r'MEASURED (\d+)', subprocess.run([sim, '--hex', h, '--cycles', '200000', '--wait', '0', *args],
                                                              capture_output=True, text=True, check=True).stdout)[1]) for h in hexes]
        print(f"| {depth} | {lab} | {c[0]:,} | {c[1]:,} | {c[2]:,} | {c[3]:,} | {(c[1] - c[0]) / 1000:.3f} |")
