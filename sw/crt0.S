# Minimal startup for the CV32E40P harness. No OS, no newlib.
# Sets the stack, zeroes .bss, calls main(), reports the return value
# by storing it to the magic halt address.

    .section .text.start
    .globl _start
_start:
    la      sp, _stack_top
#if REQUANT_ZBB
    # Zbb-style saturation (sw/requant.h): one clamp bound lives in tp for the whole program; GCC never
    # allocates tp and nothing here uses TLS
#ifdef REAL_DATA
    li      tp, 255
#else
    li      tp, -128
#endif
#endif

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
