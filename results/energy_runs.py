#!/usr/bin/env python3
"""Gate-level energy runs (M3): every kernel at its headline shape, on the routed netlists, with the
switching activity of its measured window. Run from results/; writes results/energy_runs.csv (one row
per run, appended, so an interrupted run resumes).

For each run:
  1. build the binary exactly as harness/collect_wait0.sh does, at the kernel's better code alignment in
     the committed dataset;
  2. run it on the RTL harness of the same core (obj_base or obj_pulp) for the reference counts;
  3. run it on the gate-level harness of the routed point (harness/obj_gate_<pt>, make gate PT=<pt>)
     with --fst over the measured window; cycles, data reads and writes, instruction fetches and the
     checksum must equal the RTL run's exactly, and on the Xpulp core the committed dataset's;
  4. stream the FST through fst2vcd into OpenROAD (syn/power.tcl: routed.odb, routed.spef, the point's
     clock period) through a named pipe, so no VCD is written, and record the power, the annotated and
     unannotated pin counts. The FST is deleted after the run.
Energy = total power x cycles x period; energy_model.py turns the CSV into tables."""
import csv, os, re, subprocess, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RISCV_BIN = os.environ.get('RISCV_BIN', '/opt/riscv/bin')
FST2VCD = os.environ.get('FST2VCD', os.path.expanduser('~/tools/oss-cad-suite/bin/fst2vcd'))
OPENROAD = os.environ.get('OPENROAD_ROUTE', '/usr/bin/openroad')
SWEEP = 'syn/build/sweep-or26rc-rep2'
OUT = os.environ.get('ENERGY_OUT', os.path.join(ROOT, 'results', 'energy_runs.csv'))   # reproduce.sh writes to results/repro/
XP, CL = '-DXPULP_CTRL=1', '-DREQUANT_CLIP=1'
DW, PW = '-DCH=8 -DH=16 -DW=16', '-DCI=16 -DCO=16 -DH=8 -DW=8'
# family, data, shape, defines, real-data header, [(role, source, cflags, dataset, dataset kernel)]
KERNELS = [
  ('dw3', 'syn', '8x16x16', DW, None, [('O3', 'sw/dwconv_opt.c', '-O3', 'wait0_eqrequant', 'scalar_O3'),
      ('hand', 'sw/dwconv_asm.c', '-O2', 'wait0_decomp', 'scalar_asm_rv'), ('full', 'sw/dwconv_simd_asm.c', f'-O2 {XP} {CL}', 'wait0_clip_dw3', 'simd_unal_asm_xp_clip')]),
  ('dw5', 'syn', '8x16x16', DW, None, [('O3', 'sw/dwconv5.c', '-O3', 'wait0_dw5', 'dw5_C_O3'),
      ('hand', 'sw/dwconv5_os_asm.c', '-O2', 'wait0_dw5os', 'dw5_os_asm_rv'), ('full', 'sw/dwconv5_simd_asm.c', f'-O2 {XP} {CL}', 'wait0_clip_dw5', 'dw5_simd_xp_clip')]),
  ('pw', 'syn', '16x16x8x8', PW, None, [('O3', 'sw/pwconv.c', '-O3', 'wait0_pw', 'pw_C_O3'),
      ('hand', 'sw/pwconv_asm.c', '-O2', 'wait0_pw', 'pw_asm_rv'), ('full', 'sw/pwconv_simd_asm.c', f'-O2 {XP} {CL}', 'wait0_clip_pw', 'pw_simd_asm_xp_clip')]),
  ('dw3', 'real', '8x16x16', DW, 'real/dw3_8x16x16.h', [('O3', 'sw/dwconv_opt.c', '-O3', 'wait0_real_dw3', 'scalar_O3'),
      ('hand', 'sw/dwconv_asm.c', '-O2', 'wait0_real_dw3', 'scalar_asm_rv'), ('full', 'sw/dwconv_simd_asm.c', f'-O2 {XP} {CL}', 'wait0_clip_real_dw3', 'simd_unal_asm_xp_clip')]),
  ('pw', 'real', '16x16x8x8', PW, 'real/pw_16x16x8x8.h', [('O3', 'sw/pwconv.c', '-O3', 'wait0_real_pw', 'pw_C_O3'),
      ('hand', 'sw/pwconv_asm.c', '-O2', 'wait0_real_pw', 'pw_asm_rv'), ('full', 'sw/pwconv_simd_asm.c', f'-O2 {XP} {CL}', 'wait0_clip_real_pw', 'pw_simd_asm_xp_clip')]),
]
POINTS = [('iso', 'base-16', 16.0, 'pulp-16', 16.0), ('fast', 'base-11.5', 11.5, 'pulp-14.5', 14.5)]
FIELDS = ['point', 'core', 'pt', 'period_ns', 'family', 'data', 'shape', 'role', 'pad', 'cycles', 'dread', 'dwrite', 'ifetch',
          'chk', 'dataset_cycles', 'annotated', 'unannotated', 'p_internal', 'p_switching', 'p_leakage', 'p_total']

def dataset_cycles(base, kernel, shape):
    out = {}
    for p in (0, 1):
        for r in csv.DictReader(l for l in open(os.path.join(ROOT, 'results', f'{base}_pad{p}.csv')) if not l.startswith('DONE')):
            if r['shape'] == shape and r['kernel'] == kernel and r['event'] == 'cycles': out[p] = (int(r['value']), r['chk'])
    return out
def measured(out):
    m = re.search(r'MEASURED (\d+) cycles .*dread=(\d+) dwrite=(\d+) ifetch=(\d+)', out); v = re.search(r'value = (\d+)', out)
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4]), v[1]) if m and v else None

done = set()
if os.path.exists(OUT):
    for r in csv.DictReader(open(OUT)): done.add((r['point'], r['core'], r['family'], r['data'], r['role']))
new = not os.path.exists(OUT)
fo = open(OUT, 'a', newline=''); w = csv.DictWriter(fo, fieldnames=FIELDS)
if new: w.writeheader(); fo.flush()
tmp = tempfile.mkdtemp(prefix='energy_')
for point, bpt, bper, ppt, pper in POINTS:
    for fam, data, shape, defs, hdr, roles in KERNELS:
        for role, src, cf, dset, dk in roles:
            ds = dataset_cycles(dset, dk, shape); pad = min(ds, key=lambda p: (ds[p][0], p))
            for core, pt, per in (('base', bpt, bper), ('pulp', ppt, pper)):
                if role == 'full' and core == 'base': continue   # Xpulp code does not run on the base core
                if (point, core, fam, data, role) in done: continue
                real = f'-DREAL_DATA=1 -DREAL_HDR={hdr}' if hdr else ''
                cmd = [f'{RISCV_BIN}/riscv32-unknown-elf-gcc', '-I', 'sw', '-march=rv32imc', '-mabi=ilp32', '-nostdlib', '-nostartfiles',
                       *cf.split(), f'-DCODE_PAD={pad}', *real.split(), *defs.split(), '-T', 'sw/link.ld', 'sw/crt0.S', src, '-o', f'{tmp}/x.elf']
                subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
                subprocess.run([f'{RISCV_BIN}/riscv32-unknown-elf-objcopy', '-O', 'binary', f'{tmp}/x.elf', f'{tmp}/x.bin'], check=True)
                with open(f'{tmp}/x.hex', 'w') as h: subprocess.run(['python3', 'sw/bin2hex.py', f'{tmp}/x.bin'], cwd=ROOT, check=True, stdout=h)
                rtl = measured(subprocess.run([f'{ROOT}/harness/obj_{core}/Vcv32e40p_core', '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0'],
                                              capture_output=True, text=True, check=True).stdout)
                fst = f'{tmp}/w.fst'
                gate = measured(subprocess.run([f'{ROOT}/harness/obj_gate_{pt}/Vcv32e40p_core', '--hex', f'{tmp}/x.hex', '--cycles', '50000000', '--wait', '0',
                                                '--fst', fst, '--fst-hp', str(int(round(per * 500)))], capture_output=True, text=True, check=True).stdout)
                assert rtl and gate == rtl, (point, core, fam, data, role, rtl, gate)   # the routed netlist runs the binary exactly as the RTL
                if core == 'pulp': assert rtl[0] == ds[pad][0] and rtl[4] == ds[pad][1], (fam, data, role, rtl, ds[pad])
                fifo = f'{tmp}/v.fifo'; os.mkfifo(fifo)
                conv = subprocess.Popen(f'"{FST2VCD}" "{fst}" > "{fifo}" 2>/dev/null', shell=True)
                env = dict(os.environ, DIR=f'{SWEEP}/{pt}', PERIOD_NS=str(per), VCD=fifo)
                pr = subprocess.run([OPENROAD, '-exit', 'syn/power.tcl'], cwd=ROOT, env=env, capture_output=True, text=True).stdout
                conv.wait(); os.remove(fifo); os.remove(fst)
                g = lambda k: float(re.search(rf'^{k} (\S+)', pr, re.M)[1])
                ann = int(re.search(r'^vcd\s+(\d+)', pr, re.M)[1]); una = int(re.search(r'^unannotated\s+(\d+)', pr, re.M)[1])
                w.writerow(dict(point=point, core=core, pt=pt, period_ns=per, family=fam, data=data, shape=shape, role=role, pad=pad,
                                cycles=gate[0], dread=gate[1], dwrite=gate[2], ifetch=gate[3], chk=gate[4], dataset_cycles=ds[pad][0],
                                annotated=ann, unannotated=una, p_internal=g('POWER_INTERNAL'), p_switching=g('POWER_SWITCHING'),
                                p_leakage=g('POWER_LEAKAGE'), p_total=g('POWER_TOTAL'))); fo.flush()
                print(point, core, fam, data, role, 'pad', pad, gate[0], 'cycles', f"{g('POWER_TOTAL')*1e3:.3f} mW", flush=True)
print('done')
