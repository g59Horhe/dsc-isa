# Minimal startup for the CV32E40P harness. No OS, no newlib.
# Sets the stack, zeroes .bss, calls main(), reports the return value
# by storing it to the magic halt address.

    .section .text.start
    .globl _start
_start:
    la      sp, _stack_top

    la      t0, _bss_start
    la      t1, _bss_end
1:  bge     t0, t1, 2f
    sw      zero, 0(t0)
    addi    t0, t0, 4
    j       1b
2:
    call    main

    li      t0, 0x10000000      # magic halt address
    sw      a0, 0(t0)           # report main()'s return value

3:  j       3b                  # unreachable
