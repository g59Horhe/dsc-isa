#!/usr/bin/env python3
"""Instruction-cache check (RESULTS.md, "Instruction-cache check"; review round R5, 2026-10-31: all six kernels
of the equalised 3x3 set, scripted). At 8x16x16 with three data-port wait states: both ports at three wait
states, a zero-wait instruction port, and a direct-mapped instruction cache of 1 KB and 256 B with 16-byte
lines whose miss pays three instruction-port wait states. Code footprint: the 1 KB cache's misses times the
line size, which are all compulsory because every kernel's measured code fits in 1 KB.
No -DCODE_PAD, which is the pad-0 layout. Run from results/ (a few seconds)."""
import os, re, subprocess, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GCC = os.environ.get('RISCV_BIN', '/opt/riscv/bin') + '/riscv32-unknown-elf-'
SIM = f'{ROOT}/harness/obj_pulp/Vcv32e40p_core'
K = [('scalar -O2', 'sw/dwconv_opt.c', '-O2'), ('scalar -O3', 'sw/dwconv_opt.c', '-O3'), ('scalar asm', 'sw/dwconv_asm.c', '-O2'),
     ('SIMD unaligned', 'sw/dwconv_simd.c', '-O2'), ('SIMD aligned', 'sw/dwconv_simd_al.c', '-O2'), ('SIMD aligned -O3', 'sw/dwconv_simd_al.c', '-O3')]
MEM = [['--wait', '3'], ['--wait', '3', '--iwait', '0'], ['--wait', '3', '--iwait', '3', '--icache', '1024', '16'],
       ['--wait', '3', '--iwait', '3', '--icache', '256', '16']]
def run(hexf, args):
    out = subprocess.run([SIM, '--hex', hexf, '--cycles', '50000000', *args], capture_output=True, text=True, check=True).stdout
    ic = re.search(r'hits=(\d+) misses=(\d+)', out)
    return int(re.search(r'MEASURED (\d+)', out)[1]), (int(ic[1]), int(ic[2])) if ic else None
print('| kernel | both ports wait 3 | instruction port zero-wait | 1 KB I-cache, 16 B lines | hits / misses | 256 B I-cache | hits / misses | vs zero-wait, 1 KB |')
print('|---|---|---|---|---|---|---|---|')
worst = 0; foot = []
with tempfile.TemporaryDirectory() as d:
    for lab, src, opt in K:
        e = f'{d}/x'
        subprocess.run([GCC + 'gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', *opt.split(),
                        '-DCH=8', '-DH=16', '-DW=16', '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', e + '.elf'], cwd=ROOT, check=True, capture_output=True)
        subprocess.run([GCC + 'objcopy', '-O', 'binary', e + '.elf', e + '.bin'], check=True)
        with open(e + '.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', e + '.bin'], cwd=ROOT, check=True, stdout=h)
        (b, _), (z, _), (c1, h1), (c2, h2) = (run(e + '.hex', a) for a in MEM)
        worst = max(worst, (c1 - z) / z); foot.append(h1[1])
        print(f'| {lab} | {b:,} | {z:,} | {c1:,} | {h1[0]:,} / {h1[1]:,} | {c2:,} | {h2[0]:,} / {h2[1]:,} | {(c1 - z) / z:+.3%} |')
print(f'\n1 KB I-cache against the zero-wait instruction port, all six kernels: within {worst:.2%}; code footprints '
      f'{16 * min(foot)} to {16 * max(foot)} bytes ({min(foot)} to {max(foot)} compulsory misses; no line is evicted at 1 KB)')
