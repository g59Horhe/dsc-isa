#!/bin/bash
# usage: collect.sh <outcsv> <events: "" for plain only>
export PATH=/opt/riscv/bin:$PATH
cd /home/georgedessa/research/dsc-isa
S=/tmp/claude-1000/-home-georgedessa-research-dsc-isa/a6b0f359-2847-43be-add4-44977818d1d6/scratchpad
OUT=$1; EVENTS=$2; EXTRA=$3; D=$(mktemp -d $S/cXXXX)
SIM=harness/obj_pulp/Vcv32e40p_core
echo "shape,kernel,event,value,chk" > $OUT
for shape in 8:16:16 16:16:16 8:32:32 32:8:8; do IFS=: read -r CH H W <<< "$shape"
 for spec in "scalar_O2:sw/dwconv_opt.c:-O2" "scalar_O3:sw/dwconv_opt.c:-O3" "scalar_asm:sw/dwconv_asm.c:-O2" "simd_unal:sw/dwconv_simd.c:-O2" "simd_al:sw/dwconv_simd_al.c:-O2" "simd_al_O3:sw/dwconv_simd_al.c:-O3"; do
  IFS=: read -r name src opt <<< "$spec"
  for e in plain $EVENTS; do
   if [ $e = plain ]; then arch=rv32imc; def=""; else arch=rv32imc_zicsr; def="-DPERF_EVENT=$e"; fi
   riscv32-unknown-elf-gcc -I sw -march=$arch -mabi=ilp32 -nostdlib -nostartfiles $opt $def $EXTRA -DCH=$CH -DH=$H -DW=$W -T sw/link.ld sw/crt0.S $src -o $D/x.elf 2>/dev/null || { echo "$shape,$name,$e,BUILDFAIL," >> $OUT; continue; }
   riscv32-unknown-elf-objcopy -O binary $D/x.elf $D/x.bin && python3 sw/bin2hex.py $D/x.bin > $D/x.hex
   r=$($SIM --hex $D/x.hex --cycles 50000000 --wait 0); chk=$(echo "$r" | grep -oP 'value = \K[0-9]+')
   if [ $e = plain ]; then
     m=$(echo "$r" | grep MEASURED)
     for f in cycles:'MEASURED \K[0-9]+' dread:'dread=\K[0-9]+' dwrite:'dwrite=\K[0-9]+' ifetch:'ifetch=\K[0-9]+'; do IFS=: read -r k p <<< "$f"; echo "${CH}x${H}x${W},$name,$k,$(echo "$m" | grep -oP "$p"),$chk" >> $OUT; done
   else echo "${CH}x${H}x${W},$name,ev$e,$(echo "$r" | grep -oP 'AUX \K[0-9]+'),$chk" >> $OUT; fi
  done
 done
done
rm -rf $D; echo DONE >> $OUT
