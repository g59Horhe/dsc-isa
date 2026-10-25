#!/bin/bash
# Reproduce every dataset, flow output, table and paper in this repository.
#
#   ./reproduce.sh                 run every stage in order (about 25 minutes after the simulators are built)
#   ./reproduce.sh sims collect    run the named stages only
#   ./reproduce.sh list            print the stages
#
# Stages, with the times measured on a fresh clone (one laptop, Verilator -j4):
#   sims      build the CV32E40P (RV32IMC, Xpulp) and Ibex (2-, 3-stage) simulators   ~5 min
#   check     README regression values (hello, dotp)                                 seconds
#   collect   every wait-0 counter dataset in results/ (CV32E40P)                    10 min
#   ibex      the scalar datasets on Ibex 2- and 3-stage                             5 min
#   sweeps    data-port and instruction-port latency sweeps                          30 s
#   align     the branch-target alignment term (rebuilds 304 binaries)               1 min
#   syn       Sky130 synthesis: flat totals, per-module attribution, Ibex            1.5 min
#   place     OpenROAD placement and timing repair, both configurations              3.5 min
#   models    the result scripts (markdown tables), paper table fragments            seconds
#   papers    both manuscripts (pdflatex + bibtex)                                   seconds
#   compare   diff every regenerated CSV and flow output against the committed one   seconds
#
# Regenerated data goes to results/repro/ and syn/build/; the committed files are
# not overwritten, so `compare` can report differences. To adopt a regenerated
# dataset, copy it over the committed file and rerun models.
#
# Tool locations (see README.md): RISCV_BIN (riscv32-unknown-elf-*), SV2V, YOSYS, LIB,
# OPENROAD, STA, TLEF, LEF, TRACKS (syn/Makefile variables), VENV_PYTHON,
# MOBILENET_TFLITE, MOBILENET_IMAGE.
set -u
cd "$(dirname "$0")"
ROOT=$PWD; OUT=results/repro; mkdir -p $OUT
export RISCV_BIN=${RISCV_BIN:-/opt/riscv/bin}; export PATH=$RISCV_BIN:$PATH
VENV_PYTHON=${VENV_PYTHON:-$HOME/tools/venv/bin/python}; [ -x "$VENV_PYTHON" ] || VENV_PYTHON=python3
EV="1 2 5 9"                      # CV32E40P counter events: instructions, load-use stalls, loads, taken branches
EVI="1 2 4 5 6 8 9 10"            # Ibex fixed counters
DW="8:16:16 16:16:16 8:32:32 32:8:8"; PW="16:16:8:8 8:8:16:16 16:32:8:8 16:16:16:16"
XP="-DXPULP_CTRL=1"; CL="-DREQUANT_CLIP=1"
log() { printf '\n== %s  (%s)\n' "$*" "$(date +%H:%M:%S)"; }
collect() {   # collect <name> <shapes> <kernels> [extra cflags] : both code alignments
  local name=$1 shapes=$2 kernels=$3 extra=${4:-}
  for p in 0 1; do SHAPES="$shapes" KERNELS="$kernels" harness/collect_wait0.sh $OUT/wait0_${name}_pad$p.csv "$EV" "-DCODE_PAD=$p $extra"; done
  if grep -q 'FAIL' $OUT/wait0_${name}_pad*.csv; then echo "!! FAIL rows in $name"; return 1; fi
  return 0
}
collect_ibex() {
  local core=$1 name=$2 shapes=$3 kernels=$4
  for p in 0 1; do SIM=harness_ibex/obj_$core/Vibex_top SHAPES="$shapes" KERNELS="$kernels" harness/collect_wait0.sh $OUT/wait0_${core}_${name}_pad$p.csv "$EVI" "-DCODE_PAD=$p -DIBEX_COUNTERS"; done
}
# kernel lists, one per committed dataset (names must match the CSVs)
K_EQ="scalar_O2|sw/dwconv_opt.c|-O2 scalar_O3|sw/dwconv_opt.c|-O3 scalar_asm|sw/dwconv_asm.c|-O2 simd_unal|sw/dwconv_simd.c|-O2 simd_al|sw/dwconv_simd_al.c|-O2 simd_al_O3|sw/dwconv_simd_al.c|-O3"
K_DEC="scalar_asm_rv|sw/dwconv_asm.c|-O2 scalar_asm_xp|sw/dwconv_asm.c|-O2+$XP simd_unal_asm_rv|sw/dwconv_simd_asm.c|-O2 simd_unal_asm_xp|sw/dwconv_simd_asm.c|-O2+$XP simd_al_asm_rv|sw/dwconv_simd_al_asm.c|-O2 simd_al_asm_xp|sw/dwconv_simd_al_asm.c|-O2+$XP"
K_DEC_CLIP="scalar_asm_rv_clip|sw/dwconv_asm.c|-O2+$CL scalar_asm_xp_clip|sw/dwconv_asm.c|-O2+$XP+$CL simd_unal_asm_rv_clip|sw/dwconv_simd_asm.c|-O2+$CL simd_unal_asm_xp_clip|sw/dwconv_simd_asm.c|-O2+$XP+$CL simd_al_asm_rv_clip|sw/dwconv_simd_al_asm.c|-O2+$CL simd_al_asm_xp_clip|sw/dwconv_simd_al_asm.c|-O2+$XP+$CL"
K_DW5="dw5_C_O2|sw/dwconv5.c|-O2 dw5_C_O3|sw/dwconv5.c|-O3 dw5_asm_rv|sw/dwconv5_asm.c|-O2 dw5_asm_xp|sw/dwconv5_asm.c|-O2+$XP dw5_simd_rv|sw/dwconv5_simd_asm.c|-O2 dw5_simd_xp|sw/dwconv5_simd_asm.c|-O2+$XP"
K_DW5_CLIP="dw5_asm_rv_clip|sw/dwconv5_asm.c|-O2+$CL dw5_asm_xp_clip|sw/dwconv5_asm.c|-O2+$XP+$CL dw5_simd_rv_clip|sw/dwconv5_simd_asm.c|-O2+$CL dw5_simd_xp_clip|sw/dwconv5_simd_asm.c|-O2+$XP+$CL"
K_DW5OS="dw5_os_asm_rv|sw/dwconv5_os_asm.c|-O2 dw5_os_asm_xp|sw/dwconv5_os_asm.c|-O2+$XP dw5_os_asm_rv_clip|sw/dwconv5_os_asm.c|-O2+$CL dw5_os_asm_xp_clip|sw/dwconv5_os_asm.c|-O2+$XP+$CL"
K_PW="pw_C_O2|sw/pwconv.c|-O2 pw_C_O3|sw/pwconv.c|-O3 pw_asm_rv|sw/pwconv_asm.c|-O2 pw_asm_xp|sw/pwconv_asm.c|-O2+$XP pw_simd_C_O2|sw/pwconv_simd.c|-O2 pw_simd_C_O3|sw/pwconv_simd.c|-O3 pw_simd_asm_rv|sw/pwconv_simd_asm.c|-O2 pw_simd_asm_xp|sw/pwconv_simd_asm.c|-O2+$XP"
K_PW_CLIP="pw_asm_rv_clip|sw/pwconv_asm.c|-O2+$CL pw_asm_xp_clip|sw/pwconv_asm.c|-O2+$XP+$CL pw_simd_asm_rv_clip|sw/pwconv_simd_asm.c|-O2+$CL pw_simd_asm_xp_clip|sw/pwconv_simd_asm.c|-O2+$XP+$CL"
K_REAL_DW3="scalar_O3|sw/dwconv_opt.c|-O3 scalar_asm_rv|sw/dwconv_asm.c|-O2 scalar_asm_xp|sw/dwconv_asm.c|-O2+$XP simd_unal_asm_rv|sw/dwconv_simd_asm.c|-O2 simd_unal_asm_xp|sw/dwconv_simd_asm.c|-O2+$XP simd_al_asm_rv|sw/dwconv_simd_al_asm.c|-O2 simd_al_asm_xp|sw/dwconv_simd_al_asm.c|-O2+$XP"
K_REAL_PW="pw_C_O3|sw/pwconv.c|-O3 pw_asm_rv|sw/pwconv_asm.c|-O2 pw_asm_xp|sw/pwconv_asm.c|-O2+$XP pw_simd_asm_rv|sw/pwconv_simd_asm.c|-O2 pw_simd_asm_xp|sw/pwconv_simd_asm.c|-O2+$XP"
K_BLOCK="blk_C_O3|sw/block.c|-O3 blk_C_O3_fused|sw/block.c|-O3+-DBLOCK_FUSED=1 blk_simd_rv|sw/block.c|-O2+-DBLOCK_SIMD=1 blk_simd_rv_fused|sw/block.c|-O2+-DBLOCK_SIMD=1+-DBLOCK_FUSED=1 blk_simd_xp|sw/block.c|-O2+-DBLOCK_SIMD=1+$XP blk_simd_xp_fused|sw/block.c|-O2+-DBLOCK_SIMD=1+$XP+-DBLOCK_FUSED=1 blk_full|sw/block.c|-O2+-DBLOCK_SIMD=1+$XP+$CL blk_full_fused|sw/block.c|-O2+-DBLOCK_SIMD=1+$XP+$CL+-DBLOCK_FUSED=1"
K_IBEX_DW3="scalar_O2|sw/dwconv_opt.c|-O2 scalar_O3|sw/dwconv_opt.c|-O3 scalar_asm_rv|sw/dwconv_asm.c|-O2"
K_IBEX_DW5="dw5_C_O2|sw/dwconv5.c|-O2 dw5_C_O3|sw/dwconv5.c|-O3 dw5_asm_rv|sw/dwconv5_asm.c|-O2"
K_IBEX_PW="pw_C_O2|sw/pwconv.c|-O2 pw_C_O3|sw/pwconv.c|-O3 pw_asm_rv|sw/pwconv_asm.c|-O2"
# sweep.sh takes sources relative to sw/
S_DEC="scalar_rv|dwconv_asm.c|-O2 scalar_xp|dwconv_asm.c|-O2+$XP unal_rv|dwconv_simd_asm.c|-O2 unal_xp|dwconv_simd_asm.c|-O2+$XP al_rv|dwconv_simd_al_asm.c|-O2 al_xp|dwconv_simd_al_asm.c|-O2+$XP"
S_IF="scalar_rv|dwconv_asm.c|-O2+$CL scalar_xp|dwconv_asm.c|-O2+$XP+$CL unal_rv|dwconv_simd_asm.c|-O2+$CL unal_xp|dwconv_simd_asm.c|-O2+$XP+$CL al_rv|dwconv_simd_al_asm.c|-O2+$CL al_xp|dwconv_simd_al_asm.c|-O2+$XP+$CL"
S_IF_PW="pw_rv|pwconv_asm.c|-O2+$CL pw_xp|pwconv_asm.c|-O2+$XP+$CL pws_rv|pwconv_simd_asm.c|-O2+$CL pws_xp|pwconv_simd_asm.c|-O2+$XP+$CL"

stage_sims()    { log sims; make -C harness all && make -C harness_ibex all; }
stage_check()   { log check; (cd sw && make run-hello && make run-dotp); }
stage_collect() {
  log collect
  collect eqrequant "$DW" "$K_EQ";            collect decomp "$DW" "$K_DEC";        collect clip_dw3 "$DW" "$K_DEC_CLIP"
  collect dw5 "$DW" "$K_DW5";                  collect clip_dw5 "$DW" "$K_DW5_CLIP"; collect dw5os "$DW" "$K_DW5OS"
  collect pw "$PW" "$K_PW";                    collect clip_pw "$PW" "$K_PW_CLIP"
  REAL_HDR_PREFIX=real/dw3     collect real_dw3 "$DW" "$K_REAL_DW3";      REAL_HDR_PREFIX=real/syn_dw3 collect syn_dw3 "$DW" "$K_REAL_DW3"
  REAL_HDR_PREFIX=real/dw3     collect clip_real_dw3 "$DW" "$K_DEC_CLIP"
  REAL_HDR_PREFIX=real/pw      collect real_pw "$PW" "$K_REAL_PW";        REAL_HDR_PREFIX=real/syn_pw collect syn_pw "$PW" "$K_REAL_PW"
  REAL_HDR_PREFIX=real/pw      collect clip_real_pw "$PW" "$K_PW_CLIP"
  collect block "16:16:16" "$K_BLOCK" "-DREAL_HDR=real/block_16x16x16_16.h"
}
stage_ibex()    { log ibex; for c in ibex2 ibex3; do collect_ibex $c dw3 "$DW" "$K_IBEX_DW3"; collect_ibex $c dw5 "$DW" "$K_IBEX_DW5"; collect_ibex $c pw "$PW" "$K_IBEX_PW"; done; }
stage_sweeps()  {
  log sweeps
  KERNELS="$S_DEC" harness/sweep.sh > $OUT/decomp_latency_sweep.txt
  { for iw in 0 1 2 3; do echo "### IWAIT=$iw"; WAITS=0 IWAIT=$iw SHAPES="8:16:16 32:8:8" KERNELS="$S_IF" harness/sweep.sh; WAITS=0 IWAIT=$iw SHAPES="16:16:8:8" KERNELS="$S_IF_PW" harness/sweep.sh; done; } > $OUT/ifetch_latency_sweep.txt
}
stage_align()   { log align; (cd results && python3 align_term.py > ../$OUT/align_term.txt) && cp results/wait0_align.csv $OUT/; }
stage_syn()     { log syn; make -C syn all attrib && make -C syn/ibex all; }
stage_place()   { log place; make -C syn net-base-area net-pulp-area && make -C syn place-base place-pulp; }
stage_models()  {
  log models
  (cd results && for s in wait0_eqrequant_model.py wait0_decomp_model.py wait0_pw_model.py wait0_dw5_model.py dw5_os_model.py summary_kernels.py clip_model.py real_data_model.py block_model.py area_table.py; do python3 $s > ../$OUT/${s%.py}.md || echo "!! $s failed"; done; $VENV_PYTHON ibex_model.py > ../$OUT/ibex_model.md || echo "!! ibex_model.py failed (needs numpy)")
  (cd results && python3 clip_model.py --latex ../paper/tab_decomp.tex > /dev/null && python3 area_table.py --latex ../paper/tab_area.tex > /dev/null)
  VENV_PYTHON=$VENV_PYTHON python3 paper/tc/mktables.py
}
stage_papers()  {
  log papers
  (cd paper && pdflatex -interaction=nonstopmode paper.tex > /dev/null && bibtex paper > /dev/null && pdflatex -interaction=nonstopmode paper.tex > /dev/null && pdflatex -interaction=nonstopmode paper.tex | grep 'Output written')
  (cd paper/tc && pdflatex -interaction=nonstopmode paper_tc.tex > /dev/null && bibtex paper_tc > /dev/null && pdflatex -interaction=nonstopmode paper_tc.tex > /dev/null && pdflatex -interaction=nonstopmode paper_tc.tex | grep 'Output written')
}
stage_compare() {
  log compare
  python3 - "$OUT" <<'EOF'
import csv, glob, os, re, sys
out = sys.argv[1]; bad = 0
def rows(fn): return {(r['shape'], r['kernel'], r['event']): r['value'] for r in csv.DictReader(l for l in open(fn) if not l.startswith('DONE'))}
for fn in sorted(glob.glob(f'{out}/wait0_*_pad?.csv')):
    ref = 'results/' + os.path.basename(fn)
    if not os.path.exists(ref): print(f'{fn}: no committed counterpart'); continue
    a, b = rows(fn), rows(ref); d = [k for k in a if b.get(k) != a[k]] + [k for k in b if k not in a]
    print(f'{os.path.basename(fn):36s} {len(a):4d} rows  {"identical" if not d else f"{len(d)} differences, e.g. {d[0]} {a.get(d[0])} vs {b.get(d[0])}"}'); bad += bool(d)
for fn in ('decomp_latency_sweep.txt', 'ifetch_latency_sweep.txt'):
    if os.path.exists(f'{out}/{fn}'):
        a = sorted(l.split() for l in open(f'{out}/{fn}') if re.match(r'\d', l)); b = sorted(l.split() for l in open(f'results/{fn}') if re.match(r'\d', l))
        print(f'{fn:36s} {"identical" if a == b else "DIFFERS"}'); bad += a != b
if os.path.exists(f'{out}/wait0_align.csv'):
    same = open(f'{out}/wait0_align.csv').read() == open('results/wait0_align.csv').read(); print(f'{"wait0_align.csv":36s} {"identical" if same else "DIFFERS"}'); bad += not same
def ge(fn, pat):
    m = re.search(pat, open(fn).read()); return m and m.group(1)
for cfg in ('base', 'pulp'):
    print(f'synthesis {cfg:5s} NAND2 eq: {ge(f"syn/build/{cfg}/area.txt", r"NAND2 eq\s+([\d,]+)")} (committed value is in git: git show HEAD:syn/build/{cfg}/area.txt)')
if os.path.exists('syn/build/attrib_area.txt'):
    print('attribution delta GE:', ge('syn/build/attrib_area.txt', r'design total\s+[\d,]+\s+[\d,]+\s+([\d,]+)'), '(committed 24,218; reproduces to within about 20 GE)')
for cfg in ('base', 'pulp'):
    f = f'syn/build/place-{cfg}/openroad.txt'
    if os.path.exists(f): print(f'placement {cfg:5s} slack after repair:', ge(f, r'WORST_SLACK_AFTER_REPAIR (-?[\d.]+)'), 'area:', ge(f, r'Design area (\d+)'), '(committed: see git show HEAD:' + f + ')')
print('\nsummary:', 'all compared datasets identical' if not bad else f'{bad} dataset(s) differ')
EOF
}
STAGES="sims check collect ibex sweeps align syn place models papers compare"
[ $# -gt 0 ] && STAGES="$*"
[ "$STAGES" = list ] && { echo "sims check collect ibex sweeps align syn place models papers compare"; exit 0; }
for st in $STAGES; do stage_$st || echo "!! stage $st reported an error"; done
log done
