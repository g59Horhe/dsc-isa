#!/bin/bash
# Shape sweep across kernel variants and memory latencies.
# All kernels share the inline-asm requantisation in sw/requant.h.
# Wait states apply to the data port only unless IWAIT is set.
cd "$(dirname "$0")/../sw" || exit 1
GCC=${GCC:-riscv32-unknown-elf-gcc}
OBJCOPY=${OBJCOPY:-riscv32-unknown-elf-objcopy}
SIM=../harness/obj_pulp/Vcv32e40p_core
WAITS=${WAITS:-"0 1 2 3"}
IWAIT=${IWAIT:-0}   # instruction-port wait states; default 0 so the sweep measures data latency, not fetch starvation
SHAPES=${SHAPES:-"8:16:16 16:16:16 8:32:32 32:8:8"}

printf "%-10s %-16s" shape kernel
for w in $WAITS; do printf "%9s" "w$w"; done
printf "%9s\n" chk
for shape in $SHAPES; do
  IFS=: read -r CH H W <<< "$shape"
  for k in dwconv_opt dwconv_asm dwconv_simd dwconv_simd_al; do
    $GCC -I. -march=rv32imc -mabi=ilp32 -nostdlib -nostartfiles -O2 \
      -DCH=$CH -DH=$H -DW=$W -T link.ld crt0.S $k.c -o /tmp/s.elf 2>/dev/null || continue
    $OBJCOPY -O binary /tmp/s.elf /tmp/s.bin
    python3 bin2hex.py /tmp/s.bin > /tmp/s.hex
    printf "%-10s %-16s" "${CH}x${H}x${W}" "$k"
    chk=""
    for w in $WAITS; do
      r=$($SIM --hex /tmp/s.hex --cycles 50000000 --wait $w --iwait $IWAIT 2>/dev/null)
      c=$(echo "$r" | grep -oP 'MEASURED \K[0-9]+')
      chk=$(echo "$r" | grep -oP 'value = \K[0-9]+')
      printf "%9s" "${c:-TO}"
    done
    printf "%9s\n" "$chk"
  done
  echo
done
