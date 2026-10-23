#!/bin/bash
# usage: collect_wait0.sh <outcsv> <events: "" for plain only> [extra cflags]
# KERNELS env var overrides the kernel list: entries "name|source|cflags" separated by spaces;
# write "+" for a space inside cflags, e.g. "-O2+-DXPULP_CTRL=1".
export PATH=/opt/riscv/bin:$PATH
cd "$(dirname "$0")/.."
S=/tmp/claude-1000/-home-georgedessa-research-dsc-isa/a6b0f359-2847-43be-add4-44977818d1d6/scratchpad
OUT=$1; EVENTS=$2; EXTRA=$3; D=$(mktemp -d $S/cXXXX)
SIM=harness/obj_pulp/Vcv32e40p_core
echo "shape,kernel,event,value,chk" > $OUT
SHAPES=${SHAPES:-"8:16:16 16:16:16 8:32:32 32:8:8"}   # CH:H:W for depthwise, CI:CO:H:W for pointwise
for shape in $SHAPES; do
 IFS=: read -r f1 f2 f3 f4 <<< "$shape"
 if [ -n "$f4" ]; then DEFS="-DCI=$f1 -DCO=$f2 -DH=$f3 -DW=$f4"; SNAME="${f1}x${f2}x${f3}x${f4}"; else DEFS="-DCH=$f1 -DH=$f2 -DW=$f3"; SNAME="${f1}x${f2}x${f3}"; fi
 KERNELS=${KERNELS:-"scalar_O2|sw/dwconv_opt.c|-O2 scalar_O3|sw/dwconv_opt.c|-O3 scalar_asm|sw/dwconv_asm.c|-O2 simd_unal|sw/dwconv_simd.c|-O2 simd_al|sw/dwconv_simd_al.c|-O2 simd_al_O3|sw/dwconv_simd_al.c|-O3"}
 for spec in $KERNELS; do
  IFS='|' read -r name src opt <<< "$spec"; opt=${opt//+/ }   # "+" in cflags stands for a space
  for e in plain $EVENTS; do
   if [ $e = plain ]; then arch=rv32imc; def=""; else arch=rv32imc_zicsr; def="-DPERF_EVENT=$e"; fi
   riscv32-unknown-elf-gcc -I sw -march=$arch -mabi=ilp32 -nostdlib -nostartfiles $opt $def $EXTRA $DEFS -T sw/link.ld sw/crt0.S $src -o $D/x.elf 2>/dev/null || { echo "$shape,$name,$e,BUILDFAIL," >> $OUT; continue; }
   case "$opt" in *XPULP_CTRL=1*) python3 harness/check_hwloop.py $D/x.elf > /dev/null || { echo "$shape,$name,$e,HWLOOPFAIL," >> $OUT; continue; };; esac
   riscv32-unknown-elf-objcopy -O binary $D/x.elf $D/x.bin && python3 sw/bin2hex.py $D/x.bin > $D/x.hex
   r=$($SIM --hex $D/x.hex --cycles 50000000 --wait 0); chk=$(echo "$r" | grep -oP 'value = \K[0-9]+')
   if [ $e = plain ]; then
     m=$(echo "$r" | grep MEASURED)
     for f in cycles:'MEASURED \K[0-9]+' dread:'dread=\K[0-9]+' dwrite:'dwrite=\K[0-9]+' ifetch:'ifetch=\K[0-9]+'; do IFS=: read -r k p <<< "$f"; echo "$SNAME,$name,$k,$(echo "$m" | grep -oP "$p"),$chk" >> $OUT; done
   else echo "$SNAME,$name,ev$e,$(echo "$r" | grep -oP 'AUX \K[0-9]+'),$chk" >> $OUT; fi
  done
 done
done
rm -rf $D; echo DONE >> $OUT
