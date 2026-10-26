#!/bin/bash
# usage: collect_wait0.sh <outcsv> <events: "" for plain only> [extra cflags]
# Every value in a row comes from one binary: cycles and bus traffic from the MEASURED
# line, event counts evN from the EVENTS line (the core's counter event signals,
# integrated by the harness over the same window). No instrumented builds are made;
# results/counter_validation.py checks the EVENTS counts against the CSR counters.
# KERNELS env var overrides the kernel list: entries "name|source|cflags" separated by spaces;
# write "+" for a space inside cflags, e.g. "-O2+-DXPULP_CTRL=1".
export PATH=${RISCV_BIN:-/opt/riscv/bin}:$PATH   # riscv32-unknown-elf toolchain
cd "$(dirname "$0")/.."
# REAL_HDR_PREFIX=real/dw3 (relative to sw/) adds -DREAL_DATA=1 -DREAL_HDR=<prefix>_<shape>.h
OUT=$1; EVENTS=$2; EXTRA=$3
D=$(mktemp -d)
SIM=${SIM:-harness/obj_pulp/Vcv32e40p_core}   # e.g. SIM=harness_ibex/obj_ibex2/Vibex_top
echo "shape,kernel,event,value,chk" > $OUT
SHAPES=${SHAPES:-"8:16:16 16:16:16 8:32:32 32:8:8"}   # CH:H:W for depthwise, CI:CO:H:W for pointwise
for shape in $SHAPES; do
 IFS=: read -r f1 f2 f3 f4 <<< "$shape"
 REALF=""; [ -n "$REAL_HDR_PREFIX" ] && REALF="-DREAL_DATA=1 -DREAL_HDR=${REAL_HDR_PREFIX}_$(echo $shape | tr : x).h"
 if [ -n "$f4" ]; then DEFS="-DCI=$f1 -DCO=$f2 -DH=$f3 -DW=$f4"; SNAME="${f1}x${f2}x${f3}x${f4}"; else DEFS="-DCH=$f1 -DH=$f2 -DW=$f3"; SNAME="${f1}x${f2}x${f3}"; fi
 KERNELS=${KERNELS:-"scalar_O2|sw/dwconv_opt.c|-O2 scalar_O3|sw/dwconv_opt.c|-O3 scalar_asm|sw/dwconv_asm.c|-O2 simd_unal|sw/dwconv_simd.c|-O2 simd_al|sw/dwconv_simd_al.c|-O2 simd_al_O3|sw/dwconv_simd_al.c|-O3"}
 for spec in $KERNELS; do
  IFS='|' read -r name src opt <<< "$spec"; opt=${opt//+/ }   # "+" in cflags stands for a space
  arch=rv32imc
  riscv32-unknown-elf-gcc -I sw -march=$arch -mabi=ilp32 -nostdlib -nostartfiles $opt $EXTRA $REALF $DEFS -T sw/link.ld sw/crt0.S $src -o $D/x.elf 2>/dev/null || { for e in plain $EVENTS; do echo "$shape,$name,$e,BUILDFAIL," >> $OUT; done; continue; }
  case "$opt" in *XPULP_CTRL=1*) python3 harness/check_hwloop.py $D/x.elf > /dev/null || { echo "$shape,$name,plain,HWLOOPFAIL," >> $OUT; continue; };; esac
  riscv32-unknown-elf-objcopy -O binary $D/x.elf $D/x.bin && python3 sw/bin2hex.py $D/x.bin > $D/x.hex
  r=$($SIM --hex $D/x.hex --cycles 50000000 --wait 0); chk=$(echo "$r" | grep -oP 'value = \K[0-9]+')
  m=$(echo "$r" | grep MEASURED); evl=$(echo "$r" | grep '^EVENTS')
  [ -n "$m" ] && [ -n "$evl" ] || { echo "$shape,$name,plain,RUNFAIL," >> $OUT; continue; }
  for f in cycles:'MEASURED \K[0-9]+' dread:'dread=\K[0-9]+' dwrite:'dwrite=\K[0-9]+' ifetch:'ifetch=\K[0-9]+'; do IFS=: read -r k p <<< "$f"; echo "$SNAME,$name,$k,$(echo "$m" | grep -oP "$p"),$chk" >> $OUT; done
  for e in $EVENTS; do echo "$SNAME,$name,ev$e,$(echo "$evl" | grep -oP "\bev$e=\K[0-9]+"),$chk" >> $OUT; done
 done
done
rm -rf $D; echo DONE >> $OUT
