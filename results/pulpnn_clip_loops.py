#!/usr/bin/env python3
"""Reviewer question Q1: does clip still outrank the loop hardware inside PULP-NN?
PULP-NN's unchanged kernels (sw/pulpnn/), built with CORE-V GCC 14.1 as a library (PULPNN_LIB=1),
over a 2x2 grid: hardware loops and post-increment off or on (-march ..._xcvhwlp_xcvmem), and
clip on (cv.clip/cv.clipu, PULP-NN as written) or off (PULPNN_NOCLIP=1: the study's branch-free
saturation in pmsis.h). The dot product is on in every cell. Synthetic data at the headline shapes,
each cell at its better code alignment; every checksum must equal the study's full-Xpulp kernel's.
Per family: cycles of the four cells, each feature added first and added last, and the two-feature
Shapley value (the geometric mean of the two orders). Run from results/; builds and runs (a minute)."""
import csv, collections, math, os, re, subprocess, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
COREV = os.environ.get('COREV_BIN', os.path.expanduser('~/tools/corev-gcc/bin')) + '/riscv32-corev-elf-'
SIM = f'{ROOT}/harness/obj_pulp/Vcv32e40p_core'
F = [('dw3', 'sw/pulpnn_dw3.c', '-DCH=8 -DH=16 -DW=16', 'wait0_clip_dw3', 'simd_unal_asm_xp_clip', '8x16x16'),
     ('dw5', 'sw/pulpnn_dw5.c', '-DCH=8 -DH=16 -DW=16', 'wait0_clip_dw5', 'dw5_simd_xp_clip', '8x16x16'),
     ('pw', 'sw/pulpnn_pw.c', '-DCI=16 -DCO=16 -DH=8 -DW=8', 'wait0_clip_pw', 'pw_simd_asm_xp_clip', '16x16x8x8')]
BASE = '-O3 -Isw/pulpnn/include -Wno-error=int-conversion -fno-tree-loop-distribute-patterns -DPULPNN_LIB=1'
def study_chk(ds, k, s):
    for r in csv.DictReader(l for l in open(f'{ROOT}/results/{ds}_pad0.csv') if not l.startswith('DONE')):
        if r['shape'] == s and r['kernel'] == k and r['event'] == 'cycles': return r['chk']
tmp = tempfile.mkdtemp(); print("| kernel | no loops, no clip | clip only | loops only | both | clip added first | clip added last | loops added first | loops added last | Shapley: clip | loops |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for fam, src, defs, ds, sk, shape in F:
    want = study_chk(ds, sk, shape); c = {}
    for loops in (0, 1):
        for clip in (0, 1):
            march = 'rv32imc_xcvsimd_xcvalu' + ('_xcvhwlp_xcvmem' if loops else '')
            best = None
            for pad in (0, 1):
                subprocess.run([COREV + 'gcc', '-I', 'sw', '-mabi=ilp32', '-nostdlib', '-nostartfiles', *BASE.split(), f'-march={march}', f'-DPULPNN_NOCLIP={1 - clip}',
                                f'-DCODE_PAD={pad}', *defs.split(), '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', f'{tmp}/x.elf'], cwd=ROOT, check=True, capture_output=True)
                subprocess.run([COREV + 'objcopy', '-O', 'binary', f'{tmp}/x.elf', f'{tmp}/x.bin'], check=True)
                with open(f'{tmp}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{tmp}/x.bin'], cwd=ROOT, check=True, stdout=h)
                o = subprocess.run([SIM, '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0'], capture_output=True, text=True, check=True).stdout
                cyc = int(re.search(r'MEASURED (\d+)', o)[1]); chk = re.search(r'value = (\d+)', o)[1]
                assert chk == want, (fam, loops, clip, pad, chk, want)
                best = cyc if best is None else min(best, cyc)
            c[(loops, clip)] = best
    cf, cl = c[(0, 0)] / c[(0, 1)], c[(1, 0)] / c[(1, 1)]; lf, ll = c[(0, 0)] / c[(1, 0)], c[(0, 1)] / c[(1, 1)]
    print(f"| {fam} {shape} | {c[(0,0)]:,} | {c[(0,1)]:,} | {c[(1,0)]:,} | {c[(1,1)]:,} | {cf:.2f}x | {cl:.2f}x | {lf:.2f}x | {ll:.2f}x | "
          f"{math.sqrt(cf * cl):.2f}x | {math.sqrt(lf * ll):.2f}x |")
print("\nEvery cell's checksum equals the study's full-Xpulp kernel on the same data.")
