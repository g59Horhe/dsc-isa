#!/usr/bin/env python3
"""Where the cost of carrying Xpulp unused goes (review round R7, 2026-11-01): the hand-written scalar kernels of the
three families at their headline shapes, the same binary on the RV32IMC and the Xpulp routed netlists at 16 ns
(the iso point of energy_runs.py), with OpenROAD's power report split into its cell groups: sequential (flip-flops
and latches), combinational, and clock (the clock tree's buffers and inverters, with the clock pins they drive).
The run is energy_runs.py's: build at the better code alignment, RTL run, gate-level run with --fst (cycles, bus
counts and checksum must equal the RTL run's), the FST streamed through fst2vcd into syn/power.tcl. The routed
netlists keep no module names (the attribution pass of the area table is a separate synthesis), so a per-module
split is not available here. Also counts the flip-flops and latches of each netlist.
Writes results/energy_groups.csv (resumes) and prints the table. Run from results/; about ten minutes."""
import csv, os, re, subprocess, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RISCV_BIN = os.environ.get('RISCV_BIN', '/opt/riscv/bin')
FST2VCD = os.environ.get('FST2VCD', os.path.expanduser('~/tools/oss-cad-suite/bin/fst2vcd'))
OPENROAD = os.environ.get('OPENROAD_ROUTE', '/usr/bin/openroad')
SWEEP = 'syn/build/sweep-or26rc-rep2'; PER = 16.0
OUT = os.environ.get('ENERGY_GROUPS_OUT', os.path.join(ROOT, 'results', 'energy_groups.csv'))   # reproduce.sh writes to results/repro/
DW, PW = '-DCH=8 -DH=16 -DW=16', '-DCI=16 -DCO=16 -DH=8 -DW=8'
KERNELS = [('dw3', '8x16x16', DW, 'sw/dwconv_asm.c', 'wait0_decomp', 'scalar_asm_rv'), ('dw5', '8x16x16', DW, 'sw/dwconv5_os_asm.c', 'wait0_dw5os', 'dw5_os_asm_rv'),
           ('pw', '16x16x8x8', PW, 'sw/pwconv_asm.c', 'wait0_pw', 'pw_asm_rv')]
GROUPS = ('Sequential', 'Combinational', 'Clock')
def better_pad(base, kernel, shape):
    c = {}
    for p in (0, 1):
        for r in csv.DictReader(l for l in open(os.path.join(ROOT, 'results', f'{base}_pad{p}.csv')) if not l.startswith('DONE')):
            if r['shape'] == shape and r['kernel'] == kernel and r['event'] == 'cycles': c[p] = int(r['value'])
    return min(c, key=lambda p: (c[p], p))
def measured(out):
    m = re.search(r'MEASURED (\d+) cycles .*dread=(\d+) dwrite=(\d+) ifetch=(\d+)', out); v = re.search(r'value = (\d+)', out)
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4]), v[1]) if m and v else None
def flops(pt):   # flip-flops and latches in the routed netlist the gate-level harness was built from
    t = open(os.path.join(ROOT, 'syn', 'build', 'gate', pt, 'gate.v')).read()
    return len(re.findall(r'^\s*sky130_fd_sc_hd__(?:e?df\w*|dl\w*)\s', t, re.M))
done = set()
if os.path.exists(OUT): done = {(r['family'], r['core']) for r in csv.DictReader(open(OUT))}
new = not os.path.exists(OUT); fo = open(OUT, 'a', newline='')
F = ['family', 'core', 'pt', 'cycles', 'chk'] + [f'{g.lower()}_{k}' for g in GROUPS + ('Total',) for k in ('internal', 'switching', 'leakage', 'total')]
w = csv.DictWriter(fo, fieldnames=F)
if new: w.writeheader(); fo.flush()
tmp = tempfile.mkdtemp(prefix='egroups_')
for fam, shape, defs, src, dset, dk in KERNELS:
    pad = better_pad(dset, dk, shape)
    for core, pt in (('base', 'base-16'), ('pulp', 'pulp-16')):
        if (fam, core) in done: continue
        subprocess.run([f'{RISCV_BIN}/riscv32-unknown-elf-gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles', '-O2', f'-DCODE_PAD={pad}',
                        *defs.split(), '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', f'{tmp}/x.elf'], cwd=ROOT, check=True, capture_output=True)
        subprocess.run([f'{RISCV_BIN}/riscv32-unknown-elf-objcopy', '-O', 'binary', f'{tmp}/x.elf', f'{tmp}/x.bin'], check=True)
        with open(f'{tmp}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{tmp}/x.bin'], cwd=ROOT, check=True, stdout=h)
        rtl = measured(subprocess.run([f'{ROOT}/harness/obj_{core}/Vcv32e40p_core', '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0'], capture_output=True, text=True, check=True).stdout)
        fst = f'{tmp}/w.fst'
        gate = measured(subprocess.run([f'{ROOT}/harness/obj_gate_{pt}/Vcv32e40p_core', '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0',
                                        '--fst', fst, '--fst-hp', str(int(round(PER * 500)))], capture_output=True, text=True, check=True).stdout)
        assert rtl and gate == rtl, (fam, core, rtl, gate)
        fifo = f'{tmp}/v.fifo'; os.mkfifo(fifo)
        conv = subprocess.Popen(f'"{FST2VCD}" "{fst}" > "{fifo}" 2>/dev/null', shell=True)
        env = dict(os.environ, DIR=f'{SWEEP}/{pt}', PERIOD_NS=str(PER), VCD=fifo)
        pr = subprocess.run([OPENROAD, '-exit', 'syn/power.tcl'], cwd=ROOT, env=env, capture_output=True, text=True).stdout
        conv.wait(); os.remove(fifo); os.remove(fst)
        row = dict(family=fam, core=core, pt=pt, cycles=gate[0], chk=gate[4])
        for g in GROUPS + ('Total',):
            m = re.search(rf'^{g}\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', pr, re.M)
            for k, v in zip(('internal', 'switching', 'leakage', 'total'), m.groups()): row[f'{g.lower()}_{k}'] = float(v)
        w.writerow(row); fo.flush(); print(fam, core, gate[0], 'cycles', f"{row['total_total']*1e3:.3f} mW", flush=True)
fo.close()
R = {(r['family'], r['core']): {k: (float(v) if k.endswith(('internal', 'switching', 'leakage', 'total')) else v) for k, v in r.items()} for r in csv.DictReader(open(OUT))}
fb, fp = flops('base-16'), flops('pulp-16')
print(f"\nflip-flops and latches: RV32IMC {fb:,}, Xpulp {fp:,} ({fp/fb-1:+.0%})")
print("\n| kernel | group | RV32IMC (mW) | Xpulp (mW) | change | share of the increase | Xpulp internal / switching change |")
print("|---|---|---|---|---|---|---|")
for fam in ('dw3', 'dw5', 'pw'):
    b, p = R[(fam, 'base')], R[(fam, 'pulp')]; inc = p['total_total'] - b['total_total']
    for g in [x.lower() for x in GROUPS] + ['total']:
        bt, pt_ = b[f'{g}_total'], p[f'{g}_total']
        print(f"| {fam} | {g} | {bt*1e3:.3f} | {pt_*1e3:.3f} | {pt_/bt-1:+.1%} | {(pt_-bt)/inc:.0%} | {p[f'{g}_internal']/b[f'{g}_internal']-1:+.1%} / "
              f"{(p[f'{g}_switching']/b[f'{g}_switching']-1) if b[f'{g}_switching'] else float('nan'):+.1%} |")
    print(f"| {fam} | leakage, absolute | {b['total_leakage']*1e9:.1f} nW | {p['total_leakage']*1e9:.1f} nW | | | |")
print("\nliberty: ~/tools/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib (typical corner, 25 C, 1.80 V), syn/power.tcl")
