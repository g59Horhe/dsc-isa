/* Xpulp control and addressing instructions via .insn (COREV_PULP=1 only).
 * Encodings from docs/source/instruction_set_extensions.rst.
 *
 *   LB_INC(rd, rs1, imm)   cv.lb  rd,(rs1),imm   rd = sext(mem8[rs1]);  rs1 += imm
 *   LW_INC(rd, rs1, imm)   cv.lw  rd,(rs1),imm   rd = mem32[rs1];       rs1 += imm
 *   SB_INC(rs2, rs1, imm)  cv.sb  rs2,(rs1),imm  mem8[rs1] = rs2;       rs1 += imm
 *   SW_INC(rs2, rs1, imm)  cv.sw  rs2,(rs1),imm  mem32[rs1] = rs2;      rs1 += imm
 *   HWLOOP0(cnt, words)    cv.setup 0, cnt, uimmL   with uimmL = words (a string)
 *
 * cv.setup L, rs1, uimmL: lpstart = PC+4, lpend = PC + (uimmL << 2), count = rs1.
 * rd field carries funct4=0111 and L, so rd = x14 for loop 0. The end
 * address is the instruction after the body, so uimmL = body instructions + 1
 * (body is all 32-bit instructions). GAS does not accept a label
 * difference as the .insn immediate, so the count is a constant; verify it
 * after building with harness/check_hwloop.py <elf>.
 *
 * Hardware-loop body rules (corev_hw_loop.rst): 32-bit aligned start and
 * end, no compressed instructions, no branches, at least 3 instructions,
 * entered only from the top. Wrap the whole asm block in XPULP_ASM_BEGIN /
 * XPULP_ASM_END. The .balign must come before .option norvc: with RVC
 * disabled the assembler can only pad with 4-byte nops and cannot fix a
 * 2-byte misalignment. Everything between the balign and the cv.setup must
 * then be 32-bit instructions (lb/lw/li are; keep c.* out).
 */
#ifndef XPULP_H
#define XPULP_H
#define LB_INC(rd, rs1, imm)  ".insn i 0x0b, 0x0, " rd ", " rs1 ", " imm "\n"
#define LW_INC(rd, rs1, imm)  ".insn i 0x0b, 0x2, " rd ", " rs1 ", " imm "\n"
#define SB_INC(rs2, rs1, imm) ".insn s 0x2b, 0x0, " rs2 ", " imm "(" rs1 ")\n"
#define SW_INC(rs2, rs1, imm) ".insn s 0x2b, 0x2, " rs2 ", " imm "(" rs1 ")\n"
#define HWLOOP0(cnt, words)   ".insn i 0x2b, 0x4, x14, " cnt ", " words "\n"
#define XPULP_ASM_BEGIN       ".option push\n.balign 4\n.option norvc\n"
#define XPULP_ASM_END         ".option pop\n"
#endif
