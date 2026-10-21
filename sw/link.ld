/* CV32E40P harness memory map.
   Harness loads the image at 0x80 and gives 64 KB of flat memory.
   Stack grows down from the top; a store to 0x10000000 halts the sim. */
MEMORY
{
  RAM (rwx) : ORIGIN = 0x00000080, LENGTH = 64K - 0x80
}

_stack_top = ORIGIN(RAM) + LENGTH(RAM) - 16;

SECTIONS
{
  .text : {
    *(.text.start)      /* crt0 first, so entry is at 0x80 */
    *(.text*)
    *(.rodata*)
  } > RAM

  .data : {
    *(.data*)
    *(.sdata*)
  } > RAM

  .bss : {
    _bss_start = .;
    *(.bss*)
    *(.sbss*)
    *(COMMON)
    _bss_end = .;
  } > RAM

  _end = .;
}
