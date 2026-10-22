#!/bin/bash
# Shape sweep across kernel variants and memory latencies.
# All kernels use branchless saturation; see the note in requant().
cd "$(dirname "$0")/../sw" || exit 1
GCC=${GCC:-riscv32-unknown-elf-gcc}
OBJCOPY=${OBJCOPY:-riscv32-unknown-elf-objcopy}
SIM=../harness/obj_pulp/Vcv32e40p_core
WAITS=${WAITS:-"0 1 2 3"}
SHAPES=${SHAPES:-"8:16:16 16:16:16 8:32:32 32:8:8"}

printf "%-10s %-16s" shape kernel
for w in $WAITS; do printf "%9s" "w$w"; done
printf "%9s\n" chk
for shape in $SHAPES; do
  IFS=: read -r CH H W <<< "$shape"
  for k in dwconv_opt dwconv_simd dwconv_simd_al; do
    $GCC -I. -march=rv32imc -mabi=ilp32 -nostdlib -nostartfiles -O2 \
      -DCH=$CH -DH=$H -DW=$W -T link.ld crt0.S $k.c -o /tmp/s.elf 2>/dev/null || continue
    $OBJCOPY -O binary /tmp/s.elf /tmp/s.bin
    python3 bin2hex.py /tmp/s.bin > /tmp/s.hex
    printf "%-10s %-16s" "${CH}x${H}x${W}" "$k"
    chk=""
    for w in $WAITS; do
      r=$($SIM --hex /tmp/s.hex --cycles 50000000 --wait $w 2>/dev/null)
      c=$(echo "$r" | grep -oP 'MEASURED \K[0-9]+')
      chk=$(echo "$r" | grep -oP 'value = \K[0-9]+')
      printf "%9s" "${c:-TO}"
    done
    printf "%9s\n" "$chk"
  done
  echo
done
