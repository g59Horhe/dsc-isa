#!/usr/bin/env python3
"""Hand-assemble a small RV32I program for the CV32E40P harness.

Emits one hex word per line on stdout; the harness loads these at 0x80.
This exists so the harness can be tested before riscv-gnu-toolchain is
installed. Once the toolchain is up, use objcopy output instead.
"""

def R(f7, rs2, rs1, f3, rd, op=0x33):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def I(imm, rs1, f3, rd, op=0x13):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def S(imm, rs2, rs1, f3, op=0x23):
    return ((((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15)
            | (f3 << 12) | ((imm & 0x1F) << 7) | op)

def U(imm20, rd, op=0x37):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | op

addi = lambda rd, rs1, imm: I(imm, rs1, 0, rd)
add  = lambda rd, rs1, rs2: R(0x00, rs2, rs1, 0, rd)
sub  = lambda rd, rs1, rs2: R(0x20, rs2, rs1, 0, rd)
lui  = lambda rd, imm20:    U(imm20, rd)
sw   = lambda rs2, rs1, imm: S(imm, rs2, rs1, 0b010)

HALT_HI = 0x10000   # store to 0x10000000 ends the simulation

PROGRAM = [
    addi(5, 0, 42),      # x5 = 42
    addi(6, 0, 1),       # x6 = 1
    add(7, 5, 6),        # x7 = 43
    lui(8, HALT_HI),     # x8 = 0x10000000
    sw(7, 8, 0),         # report 43 and halt
    I(0, 0, 0, 0, 0x6F), # jal x0,0  (spin; unreachable)
]

if __name__ == "__main__":
    for w in PROGRAM:
        print("%08x" % w)
