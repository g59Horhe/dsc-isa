#!/usr/bin/env python3
"""Validate the harness-integrated event counts against the cores' CSR counters.

Since 2026-10-27 the counter datasets take every event count from the EVENTS line
of the harness: the core's own performance-counter event signals, integrated over
the measured window of the measured binary. This script checks that this is the
same quantity the CSR counter reports. For each kernel family it builds an
instrumented binary (-DPERF_EVENT=e, which programs the counter and stores its
delta as an AUX word), runs it, and compares the CSR reading with the harness's
count of event e in that same run. Writes results/counter_validation.txt.
Run from results/."""
import os, re, subprocess, tempfile, collections
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RISCV_BIN = os.environ.get('RISCV_BIN', '/opt/riscv/bin')
GCC = f'{RISCV_BIN}/riscv32-unknown-elf-gcc'; OBJCOPY = f'{RISCV_BIN}/riscv32-unknown-elf-objcopy'
XP, CL = '-DXPULP_CTRL=1', '-DREQUANT_CLIP=1'
KERNELS = [  # (source, flags, shape defines), one representative per family and control/saturation variant
    ('sw/dwconv_opt.c', '-O2', '-DCH=8 -DH=16 -DW=16'), ('sw/dwconv_opt.c', '-O3', '-DCH=8 -DH=16 -DW=16'),
    ('sw/dwconv_asm.c', '-O2', '-DCH=8 -DH=16 -DW=16'), ('sw/dwconv_simd_al.c', '-O3', '-DCH=8 -DH=16 -DW=16'),
    ('sw/dwconv_simd_asm.c', f'-O2 {XP} {CL}', '-DCH=8 -DH=16 -DW=16'), ('sw/dwconv_simd_al_asm.c', f'-O2 {XP}', '-DCH=8 -DH=16 -DW=16'),
    ('sw/dwconv5_os_asm.c', '-O2', '-DCH=8 -DH=16 -DW=16'), ('sw/dwconv5_simd_asm.c', f'-O2 {XP} {CL}', '-DCH=8 -DH=16 -DW=16'),
    ('sw/pwconv.c', '-O3', '-DCI=16 -DCO=16 -DH=8 -DW=8'), ('sw/pwconv_simd_asm.c', f'-O2 {XP} {CL}', '-DCI=16 -DCO=16 -DH=8 -DW=8')]
CORES = [('CV32E40P', f'{ROOT}/harness/obj_pulp/Vcv32e40p_core', [1, 2, 5, 9], ''),
         ('Ibex 2-stage', f'{ROOT}/harness_ibex/obj_ibex2/Vibex_top', [1, 2, 4, 5, 6, 8, 9, 10], '-DIBEX_COUNTERS'),
         ('Ibex 3-stage', f'{ROOT}/harness_ibex/obj_ibex3/Vibex_top', [1, 2, 4, 5, 6, 8, 9, 10], '-DIBEX_COUNTERS')]
def run(sim, src, flags):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([GCC, '-I', 'sw', '-march=rv32imc_zicsr', '-mabi=ilp32', '-nostdlib', '-nostartfiles', *flags.split(), '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', f'{d}/x.elf'], cwd=ROOT, check=True, capture_output=True)
        subprocess.run([OBJCOPY, '-O', 'binary', f'{d}/x.elf', f'{d}/x.bin'], check=True)
        with open(f'{d}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{d}/x.bin'], cwd=ROOT, check=True, stdout=h)
        return subprocess.run([sim, '--hex', f'{d}/x.hex', '--cycles', '50000000', '--wait', '0'], capture_output=True, text=True, check=True).stdout
lines = ['harness event count minus CSR counter reading, same instrumented binary, per core and event (all kernels below)', '']
summary = []
for core, sim, events, cflags in CORES:
    if core != 'CV32E40P': kernels = [k for k in KERNELS if 'XPULP' not in k[1] and 'simd' not in k[0]]   # Ibex runs the scalar kernels only
    else: kernels = KERNELS
    diffs = collections.defaultdict(list)
    for src, opt, shp in kernels:
        for e in events:
            out = run(sim, src, f'{opt} {shp} {cflags} -DPERF_EVENT={e}')
            aux = int(re.search(r'AUX (\d+)', out)[1]); h = int(re.search(rf'\bev{e}=(\d+)', out)[1])
            diffs[e].append(h - aux)
    for e in events:
        d = diffs[e]; summary.append((core, e, min(d), max(d), len(d)))
        lines.append(f'{core:13s} ev{e:<2d} {len(d):2d} kernels  difference min {min(d):+d}  max {max(d):+d}')
lines.append(''); lines.append('kernels: ' + '; '.join(f'{s.split("/")[-1]} {o}' for s, o, _ in KERNELS))
open(os.path.join(ROOT, 'results', 'counter_validation.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
