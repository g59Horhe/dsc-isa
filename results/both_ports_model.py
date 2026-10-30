#!/usr/bin/env python3
"""Reviewer question Q4: the cycle model with wait states on both ports at once.
The six kernels of the equalised 3x3 set at 8x16x16 (each at its better alignment at zero wait),
run on the RTL harness at every combination of 0 to 3 data-port wait states (w_d) and 0 to 3
instruction-port wait states (w_i): 96 runs. Three candidate models, each from the single-port
measurements only, against the measured cycles:
  additive  cycles(0,0) + w_d (reads + writes) + w_i * fetches   (every wait costs a stall)
  ports     cycles(0, w_i) + w_d (reads + writes)                 (the measured instruction-port
            curve, plus the data-port identity of Section VIII on top)
  max       max(cycles(w_d, 0), cycles(0, w_i))                   (full overlap)
Builds and runs the binaries itself (minutes). Run from results/; writes both_ports.csv
(BOTH_PORTS_OUT overrides the path; reproduce.sh writes to results/repro/)."""
import csv, os, re, subprocess, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GCC = os.environ.get('RISCV_BIN', '/opt/riscv/bin') + '/riscv32-unknown-elf-'
SIM = f'{ROOT}/harness/obj_pulp/Vcv32e40p_core'
OUT = os.environ.get('BOTH_PORTS_OUT', os.path.join(ROOT, 'results', 'both_ports.csv'))
K = [('scalar_O2', 'sw/dwconv_opt.c', '-O2'), ('scalar_O3', 'sw/dwconv_opt.c', '-O3'), ('scalar_asm', 'sw/dwconv_asm.c', '-O2'),
     ('simd_unal', 'sw/dwconv_simd.c', '-O2'), ('simd_al', 'sw/dwconv_simd_al.c', '-O2'), ('simd_al_O3', 'sw/dwconv_simd_al.c', '-O3')]
def run(hexf, wd, wi):
    o = subprocess.run([SIM, '--hex', hexf, '--cycles', '50000000', '--wait', str(wd), '--iwait', str(wi)], capture_output=True, text=True, check=True).stdout
    m = re.search(r'MEASURED (\d+) .*dread=(\d+) dwrite=(\d+) ifetch=(\d+)', o); return tuple(map(int, m.groups()))
tmp = tempfile.mkdtemp(); rows = []
for name, src, cf in K:
    best = None
    for pad in (0, 1):
        subprocess.run([GCC + 'gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', *cf.split(), f'-DCODE_PAD={pad}',
                        '-DCH=8', '-DH=16', '-DW=16', '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', f'{tmp}/{pad}.elf'], cwd=ROOT, check=True, capture_output=True)
        subprocess.run([GCC + 'objcopy', '-O', 'binary', f'{tmp}/{pad}.elf', f'{tmp}/{pad}.bin'], check=True)
        with open(f'{tmp}/{pad}.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{tmp}/{pad}.bin'], cwd=ROOT, check=True, stdout=h)
        c0 = run(f'{tmp}/{pad}.hex', 0, 0)
        if best is None or c0[0] < best[1][0]: best = (pad, c0)
    pad, (c00, rd, wr, fe) = best; hexf = f'{tmp}/{pad}.hex'
    M = {(wd, wi): run(hexf, wd, wi)[0] for wd in range(4) for wi in range(4)}
    for (wd, wi), cyc in sorted(M.items()):
        rows.append(dict(kernel=name, pad=pad, wd=wd, wi=wi, cycles=cyc, accesses=rd + wr, fetches=fe,
                         additive=c00 + wd * (rd + wr) + wi * fe, ports=M[(0, wi)] + wd * (rd + wr), max=max(M[(wd, 0)], M[(0, wi)])))
with open(OUT, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
both = [r for r in rows if r['wd'] > 0 and r['wi'] > 0]
print(f"{len(rows)} runs; {len(both)} with both ports waited. Error of each model on those runs:\n")
print("| model | mean |error| | max |error| | worst run |\n|---|---|---|---|")
for m in ('additive', 'ports', 'max'):
    e = [(abs(r[m] - r['cycles']) / r['cycles'], r) for r in both]; worst = max(e, key=lambda x: x[0])
    print(f"| {m} | {sum(x for x, _ in e)/len(e):.2%} | {worst[0]:.2%} | {worst[1]['kernel']} w_d={worst[1]['wd']} w_i={worst[1]['wi']} |")
print("\n| kernel | w_d=w_i=3 cycles | instruction port only (0,3) | data port only (3,0) | ports model | additive |")
print("|---|---|---|---|---|---|")
for name, *_ in K:
    r = {(x['wd'], x['wi']): x for x in rows if x['kernel'] == name}
    print(f"| {name} | {r[(3,3)]['cycles']:,} | {r[(0,3)]['cycles']:,} | {r[(3,0)]['cycles']:,} | {r[(3,3)]['ports']:,} | {r[(3,3)]['additive']:,} |")
