#!/usr/bin/env python3
"""Misaligned word loads and stores (review round R7: the store coefficient of A_split, measured rather than inferred).
50 back-to-back lw (sw/ubench_unaligned.c) or sw (sw/ubench_unaligned_store.c) at byte offset 0 to 3, against the
empty bracket, at 0 to 3 data-port wait states. Prints cycles and bus accesses per instruction above the bracket.
Run from results/ (a few seconds)."""
import os, re, subprocess, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GCC = os.environ.get('RISCV_BIN', '/opt/riscv/bin') + '/riscv32-unknown-elf-'
SIM = f'{ROOT}/harness/obj_pulp/Vcv32e40p_core'
def run(src, flags, wait, d):
    subprocess.run([GCC + 'gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', '-O2', *flags, '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', f'{d}/x.elf'], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([GCC + 'objcopy', '-O', 'binary', f'{d}/x.elf', f'{d}/x.bin'], check=True)
    with open(f'{d}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{d}/x.bin'], cwd=ROOT, check=True, stdout=h)
    m = subprocess.run([SIM, '--hex', f'{d}/x.hex', '--cycles', '1000000', '--wait', str(wait)], capture_output=True, text=True, check=True).stdout
    m = re.search(r'MEASURED (\d+).*', m)[0]
    return int(re.search(r'MEASURED (\d+)', m)[1]), int(re.search(r'dread=(\d+)', m)[1]), int(re.search(r'dwrite=(\d+)', m)[1])
print('| access | offset | wait states | cycles per instruction above the bracket | bus reads per instruction | bus writes per instruction |')
print('|---|---|---|---|---|---|')
extra = {}; acc = {}
with tempfile.TemporaryDirectory() as d:
    for lab, src in (('lw', 'sw/ubench_unaligned.c'), ('sw', 'sw/ubench_unaligned_store.c')):
        for w in range(4):
            e = run(src, ['-DEMPTY=1'], w, d)
            for off in range(4):
                c, r, wr = run(src, [f'-DOFF={off}'], w, d)
                cy, rd, wt = (c - e[0]) / 50, (r - e[1]) / 50, (wr - e[2]) / 50
                extra[(lab, off, w)] = cy; acc[(lab, off, w)] = rd + wt
                print(f'| {lab} | {off} | {w} | {cy:.2f} | {rd:.2f} | {wt:.2f} |')
for lab in ('lw', 'sw'):
    pen0 = {off: extra[(lab, off, 0)] - extra[(lab, 0, 0)] for off in (1, 2, 3)}
    acc1 = {(off, w): acc[(lab, off, w)] - acc[(lab, 0, w)] for off in (1, 2, 3) for w in range(4)}
    print(f"\n{lab}: misaligned (offset 1 to 3) against aligned: extra bus accesses per instruction {min(acc1.values()):.2f} to {max(acc1.values()):.2f} at 0 to 3 wait states; "
          f"extra cycles at zero wait states {min(pen0.values()):.2f} to {max(pen0.values()):.2f}")
print(f"\nloads and stores take the same cycles at every offset and wait state: {all(extra[('lw', o, w)] == extra[('sw', o, w)] for o in range(4) for w in range(4))}")
