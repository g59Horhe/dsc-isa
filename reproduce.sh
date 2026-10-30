#!/bin/bash
# Reproduce every dataset, flow output, table and paper in this repository.
#
#   ./reproduce.sh                 run every default stage in order (about 20 minutes after the simulators are built)
#   ./reproduce.sh sims collect    run the named stages only
#   ./reproduce.sh list            print the stages
#
# Stages, with the times measured on a fresh clone (one laptop, Verilator -j4):
#   sims      build the CV32E40P (RV32IMC, Xpulp) and Ibex (2-, 3-stage) simulators   ~5 min
#   check     README regression values (hello, dotp)                                 seconds
#   validate  harness event counts against the cores' CSR counters                  15 s
#   collect   every wait-0 counter dataset in results/ (CV32E40P)                    3 min
#   ibex      the scalar datasets on Ibex 2- and 3-stage                             1 min
#   sweeps    data-port and instruction-port latency sweeps                          30 s
#   align     the branch-target alignment term (rebuilds 368 binaries)               1 min
#   questions the reviewer questions that run binaries: both-port wait states (Q4),  15 s (+ one build)
#             the alignment term at prefetch FIFO depth 4 (Q3, builds a patched core)
#   syn       Sky130 synthesis: flat totals, per-module attribution, Ibex            1.5 min
#   place     OpenROAD placement and timing repair, both configurations              3.5 min
#   models    the result scripts (markdown tables), manuscript table fragments;      1 min
#             pulpnn_clip_loops.py (Q1) rebuilds PULP-NN with CORE-V GCC when it is present
#   papers    both manuscripts, if paper/ is present (it is not in the public repository)
#   compare   diff every regenerated CSV and flow output against the committed one   seconds
# Not in the defaults (./reproduce.sh energy): the gate-level energy stage, about 1.5 hours; it
# needs the routed sweep (make -C syn sweep, about 3.5 hours; syn/build/sweep-or26rc-rep2 is committed).
#
# Regenerated data goes to results/repro/ and syn/build/; the committed files are
# not overwritten, so `compare` can report differences. To adopt a regenerated
# dataset, copy it over the committed file and rerun models.
#
# Tool locations (see README.md): RISCV_BIN (riscv32-unknown-elf-*), SV2V, YOSYS, LIB,
# OPENROAD, STA, TLEF, LEF, TRACKS (syn/Makefile variables), VENV_PYTHON,
# MOBILENET_TFLITE, MOBILENET_IMAGE, COREV_BIN (riscv32-corev-elf-*), OPENROAD_ROUTE, FST2VCD.
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
K_IBEX_DW5OS="dw5_os_asm_rv|sw/dwconv5_os_asm.c|-O2"
# PULP-NN (sw/pulpnn/, upstream GCC with the CORE-V SIMD and ALU extensions): library build and shape-specialised build
PNF="-O3+-Isw/pulpnn/include+-Wno-error=int-conversion+-fno-tree-loop-distribute-patterns"
EVPN="1 2 5 6 7 9"                # PULP-NN runs also count stores (split stores) and jumps
COREV_BIN=${COREV_BIN:-$HOME/tools/corev-gcc/bin}   # CORE-V GCC 14.1 (corev-openhw-gcc-ubuntu2204-20240530), for the PULP-NN builds with hardware loops
# sweep.sh takes sources relative to sw/
S_DEC="scalar_rv|dwconv_asm.c|-O2 scalar_xp|dwconv_asm.c|-O2+$XP unal_rv|dwconv_simd_asm.c|-O2 unal_xp|dwconv_simd_asm.c|-O2+$XP al_rv|dwconv_simd_al_asm.c|-O2 al_xp|dwconv_simd_al_asm.c|-O2+$XP"
S_IF="scalar_rv|dwconv_asm.c|-O2+$CL scalar_xp|dwconv_asm.c|-O2+$XP+$CL unal_rv|dwconv_simd_asm.c|-O2+$CL unal_xp|dwconv_simd_asm.c|-O2+$XP+$CL al_rv|dwconv_simd_al_asm.c|-O2+$CL al_xp|dwconv_simd_al_asm.c|-O2+$XP+$CL"
S_IF_PW="pw_rv|pwconv_asm.c|-O2+$CL pw_xp|pwconv_asm.c|-O2+$XP+$CL pws_rv|pwconv_simd_asm.c|-O2+$CL pws_xp|pwconv_simd_asm.c|-O2+$XP+$CL"

stage_sims()    { log sims; make -C harness all && make -C harness_ibex all; }
stage_check()   { log check; (cd sw && make run-hello && make run-dotp); }
stage_validate() { log validate; (cd results && python3 counter_validation.py > /dev/null && cp counter_validation.txt ../$OUT/); }   # harness event counts against the CSR counters
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
  # review round R: the baseline's saturation idiom and -Os (results/saturation_model.py). Zbb-style saturation
  # (REQUANT_ZBB: srai with Xpulp's 32-bit cv.max and cv.min, bounds in registers) in every hand kernel, synthetic
  # and real data; a not-taken-branch fast path (REQUANT_BRANCH) in the RV32IMC-control hand kernels, synthetic and
  # real data; the C kernels at -Os.
  ZB="-DREQUANT_ZBB=1"; BR="-DREQUANT_BRANCH=1"
  collect zbb_dw3 "$DW" "scalar_asm_rv|sw/dwconv_asm.c|-O2+$ZB scalar_asm_xp|sw/dwconv_asm.c|-O2+$XP+$ZB simd_unal_asm_rv|sw/dwconv_simd_asm.c|-O2+$ZB simd_unal_asm_xp|sw/dwconv_simd_asm.c|-O2+$XP+$ZB simd_al_asm_rv|sw/dwconv_simd_al_asm.c|-O2+$ZB simd_al_asm_xp|sw/dwconv_simd_al_asm.c|-O2+$XP+$ZB"
  collect zbb_dw5 "$DW" "dw5_asm_rv|sw/dwconv5_asm.c|-O2+$ZB dw5_asm_xp|sw/dwconv5_asm.c|-O2+$XP+$ZB dw5_simd_rv|sw/dwconv5_simd_asm.c|-O2+$ZB dw5_simd_xp|sw/dwconv5_simd_asm.c|-O2+$XP+$ZB dw5_os_asm_rv|sw/dwconv5_os_asm.c|-O2+$ZB dw5_os_asm_xp|sw/dwconv5_os_asm.c|-O2+$XP+$ZB"
  collect zbb_pw "$PW" "pw_asm_rv|sw/pwconv_asm.c|-O2+$ZB pw_asm_xp|sw/pwconv_asm.c|-O2+$XP+$ZB pw_simd_asm_rv|sw/pwconv_simd_asm.c|-O2+$ZB pw_simd_asm_xp|sw/pwconv_simd_asm.c|-O2+$XP+$ZB"
  REAL_HDR_PREFIX=real/dw3 collect zbb_real_dw3 "$DW" "scalar_asm_rv|sw/dwconv_asm.c|-O2+$ZB scalar_asm_xp|sw/dwconv_asm.c|-O2+$XP+$ZB simd_unal_asm_rv|sw/dwconv_simd_asm.c|-O2+$ZB simd_unal_asm_xp|sw/dwconv_simd_asm.c|-O2+$XP+$ZB simd_al_asm_rv|sw/dwconv_simd_al_asm.c|-O2+$ZB simd_al_asm_xp|sw/dwconv_simd_al_asm.c|-O2+$XP+$ZB"
  REAL_HDR_PREFIX=real/pw  collect zbb_real_pw "$PW" "pw_asm_rv|sw/pwconv_asm.c|-O2+$ZB pw_asm_xp|sw/pwconv_asm.c|-O2+$XP+$ZB pw_simd_asm_rv|sw/pwconv_simd_asm.c|-O2+$ZB pw_simd_asm_xp|sw/pwconv_simd_asm.c|-O2+$XP+$ZB"
  collect branch_dw3 "$DW" "scalar_asm_rv|sw/dwconv_asm.c|-O2+$BR simd_unal_asm_rv|sw/dwconv_simd_asm.c|-O2+$BR simd_al_asm_rv|sw/dwconv_simd_al_asm.c|-O2+$BR"
  collect branch_dw5 "$DW" "dw5_asm_rv|sw/dwconv5_asm.c|-O2+$BR dw5_simd_rv|sw/dwconv5_simd_asm.c|-O2+$BR dw5_os_asm_rv|sw/dwconv5_os_asm.c|-O2+$BR"
  collect branch_pw "$PW" "pw_asm_rv|sw/pwconv_asm.c|-O2+$BR pw_simd_asm_rv|sw/pwconv_simd_asm.c|-O2+$BR"
  REAL_HDR_PREFIX=real/dw3 collect branch_real_dw3 "$DW" "scalar_asm_rv|sw/dwconv_asm.c|-O2+$BR simd_unal_asm_rv|sw/dwconv_simd_asm.c|-O2+$BR simd_al_asm_rv|sw/dwconv_simd_al_asm.c|-O2+$BR"
  REAL_HDR_PREFIX=real/pw  collect branch_real_pw "$PW" "pw_asm_rv|sw/pwconv_asm.c|-O2+$BR pw_simd_asm_rv|sw/pwconv_simd_asm.c|-O2+$BR"
  collect Os_dw "$DW" "scalar_Os|sw/dwconv_opt.c|-Os simd_unal_Os|sw/dwconv_simd.c|-Os simd_al_Os|sw/dwconv_simd_al.c|-Os dw5_C_Os|sw/dwconv5.c|-Os"
  collect Os_pw "$PW" "pw_C_Os|sw/pwconv.c|-Os pw_simd_C_Os|sw/pwconv_simd.c|-Os"
  # PULP-NN: upstream GCC (pulpnn), CORE-V GCC without (pulpnncv0) and with (pulpnncv) hardware loops and post-increment;
  # each as a library build (PULPNN_LIB=1) and shape-specialised (_spec)
  for v in "pulpnn|1|rv32imc_xcvsimd_xcvalu|riscv32-unknown-elf-" "pulpnn_spec|0|rv32imc_xcvsimd_xcvalu|riscv32-unknown-elf-" \
           "pulpnncv0|1|rv32imc_xcvsimd_xcvalu|$COREV_BIN/riscv32-corev-elf-" "pulpnncv0_spec|0|rv32imc_xcvsimd_xcvalu|$COREV_BIN/riscv32-corev-elf-" \
           "pulpnncv|1|rv32imc_xcvsimd_xcvalu_xcvhwlp_xcvmem|$COREV_BIN/riscv32-corev-elf-" "pulpnncv_spec|0|rv32imc_xcvsimd_xcvalu_xcvhwlp_xcvmem|$COREV_BIN/riscv32-corev-elf-"; do
    IFS='|' read -r n L X CROSS <<< "$v"; export CROSS; F="$PNF+-march=$X+-DPULPNN_LIB=$L"
    if [ ! -x "${CROSS}gcc" ] && ! command -v "${CROSS}gcc" > /dev/null; then echo "!! ${CROSS}gcc not found, skipping $n"; continue; fi
    EV="$EVPN" collect ${n}_dw3 "$DW" "pulpnn_dw3|sw/pulpnn_dw3.c|$F"; EV="$EVPN" collect ${n}_dw5 "$DW" "pulpnn_dw5|sw/pulpnn_dw5.c|$F"
    EV="$EVPN" collect ${n}_pw "$PW" "pulpnn_pw|sw/pulpnn_pw.c|$F"
    EV="$EVPN" REAL_HDR_PREFIX=real/dw3 collect ${n}_real_dw3 "$DW" "pulpnn_dw3|sw/pulpnn_dw3.c|$F"
    EV="$EVPN" REAL_HDR_PREFIX=real/pw collect ${n}_real_pw "$PW" "pulpnn_pw|sw/pulpnn_pw.c|$F"
  done
  unset CROSS
}
stage_ibex()    { log ibex; for c in ibex2 ibex3; do collect_ibex $c dw3 "$DW" "$K_IBEX_DW3"; collect_ibex $c dw5 "$DW" "$K_IBEX_DW5"; collect_ibex $c dw5os "$DW" "$K_IBEX_DW5OS"; collect_ibex $c pw "$PW" "$K_IBEX_PW"; done; }
stage_sweeps()  {
  log sweeps
  KERNELS="$S_DEC" harness/sweep.sh > $OUT/decomp_latency_sweep.txt
  { for iw in 0 1 2 3; do echo "### IWAIT=$iw"; WAITS=0 IWAIT=$iw SHAPES="8:16:16 32:8:8" KERNELS="$S_IF" harness/sweep.sh; WAITS=0 IWAIT=$iw SHAPES="16:16:8:8" KERNELS="$S_IF_PW" harness/sweep.sh; done; } > $OUT/ifetch_latency_sweep.txt
}
stage_align()   { log align; (cd results && python3 align_term.py > ../$OUT/align_term.txt) && cp results/wait0_align.csv $OUT/; }
stage_questions() {   # Q4: the cycle model with wait states on both ports (96 runs); Q3: the alignment term with prefetch FIFO depth 4 (patched RTL copy in harness/obj_fifo4/)
  log questions
  (cd results && BOTH_PORTS_OUT=../$OUT/both_ports.csv python3 both_ports_model.py > ../$OUT/both_ports_model.md || echo "!! both_ports_model.py failed")
  (cd results && python3 align_rule_check.py > ../$OUT/align_rule_check.md || echo "!! align_rule_check.py failed")
}
stage_syn()     { log syn; make -C syn all attrib timing && make -C syn/ibex all; }   # timing = unplaced-netlist OpenSTA, kept as the negative example
stage_place()   { log place; make -C syn net-base-area net-pulp-area && make -C syn place-base place-pulp; }
stage_models()  {
  log models
  (cd results && for s in wait0_eqrequant_model.py wait0_decomp_model.py wait0_pw_model.py wait0_dw5_model.py dw5_os_model.py summary_kernels.py clip_model.py real_data_model.py block_model.py area_table.py pulpnn_model.py energy_model.py shapley_baselines.py time_adjusted.py saturation_model.py; do python3 $s > ../$OUT/${s%.py}.md || echo "!! $s failed"; done; $VENV_PYTHON ibex_model.py > ../$OUT/ibex_model.md || echo "!! ibex_model.py failed (needs numpy)")
  if [ -x "$COREV_BIN/riscv32-corev-elf-gcc" ]; then (cd results && COREV_BIN=$COREV_BIN python3 pulpnn_clip_loops.py > ../$OUT/pulpnn_clip_loops.md || echo "!! pulpnn_clip_loops.py failed"); else echo "!! $COREV_BIN/riscv32-corev-elf-gcc not found, skipping pulpnn_clip_loops.py"; fi
  [ -d paper ] && (cd results && python3 clip_model.py --latex ../paper/tab_decomp.tex --no-zbb > /dev/null && python3 area_table.py --latex ../paper/tab_area.tex > /dev/null)
  VENV_PYTHON=$VENV_PYTHON python3 results/paper_tables.py
}
stage_energy()  {   # M3: routed netlists to gate level (syn/gate_netlist.sh), gate-level harnesses, switching activity and power (about an hour)
  log energy
  for pt in base-16 pulp-16 base-11.5 pulp-14.5; do (cd syn && sh gate_netlist.sh build/sweep-or26rc-rep2/$pt build/gate/$pt) && make -C harness gate PT=$pt || return 1; done
  (cd results && ENERGY_OUT=../$OUT/energy_runs.csv python3 energy_runs.py)   # needs the routed sweep (make -C syn sweep); not in the default stages
}
stage_papers()  {
  log papers
  [ -d paper ] || { echo "paper/ is not part of the public repository; manuscript tables are in results/paper_gen"; return 0; }
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
for fn in ('wait0_align.csv', 'both_ports.csv'):
    if os.path.exists(f'{out}/{fn}'):
        same = open(f'{out}/{fn}').read() == open(f'results/{fn}').read(); print(f'{fn:36s} {"identical" if same else "DIFFERS"}'); bad += not same
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
STAGES="sims check validate collect ibex sweeps align questions syn place models papers compare"
[ $# -gt 0 ] && STAGES="$*"
[ "$STAGES" = list ] && { echo "sims check validate collect ibex sweeps align questions syn place models papers compare"; echo "not in the defaults: energy (needs the routed sweep, make -C syn sweep)"; exit 0; }
for st in $STAGES; do stage_$st || echo "!! stage $st reported an error"; done
log done
