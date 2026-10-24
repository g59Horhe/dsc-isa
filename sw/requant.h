/* Shared requantisation: arithmetic right shift by SHIFT, saturate to int8.
 *
 * Written as inline asm so that every kernel executes the identical
 * instruction sequence. GCC turns the C "branchless" XOR form back into
 * compare-and-branch, and the two taken branches per pixel it emits cost
 * more cycles than the operand-supply effect under study. A fast-path form
 * with a not-taken branch is not expressible in inline asm: the saturating
 * case has to live out of line, and the assembler then inverts the branch
 * into bnez+j, which is taken again.
 *
 * Nine instructions, no branch, data-independent. Result is the saturated
 * value: acc ^ ((acc ^ sat) & mask), with mask = -1 when out of range.
 *
 * REQUANT_ASM(acc, t, u): acc is in/out, t and u are scratch registers.
 *
 * -DREQUANT_CLIP=1 replaces the saturation with the Xpulp clip instruction
 * (cv.clip for int8, cv.clipu for 0..255 in REAL_DATA mode): two
 * instructions instead of nine or eight. COREV_PULP=1 only.
 */
#ifndef REQUANT_H
#define REQUANT_H
#define RQ_XS(x) RQ_S(x)
#define RQ_S(x) #x

#ifdef REAL_DATA
#define RH_S(x) #x
#define RH_XS(x) RH_S(x)
#include RH_XS(REAL_HDR)   /* defines REAL_SHIFT, REAL_CHECKSUM, real_input[], real_weight[] */
/* Real-data mode (-DREAL_DATA=1 -include sw/real/<kernel>_<shape>.h): uint8
 * activations with zero point 0, int8 weights, shift REAL_SHIFT from the
 * layer's real multiplier, output = clamp(acc >> shift, 0, 255), which is
 * ReLU6 in the quantised domain. Eight instructions, no branch. */
typedef unsigned char act_t;
typedef unsigned char out_t;
#undef SHIFT
#define SHIFT REAL_SHIFT
#if REQUANT_CLIP
/* Xpulp cv.clipu rD, rs1, Is2: rD = clamp(rs1, 0, 2^(Is2-1)-1); Is2 = 9 -> 0..255.
 * R-type, opcode 0x2b, funct3 011, funct7 0x39, Is2 in the rs2 field (x9). */
#define RQ_N 2
#define REQUANT_ASM(acc, t, u) \
  "srai " acc "," acc "," RQ_XS(SHIFT) "\n" \
  ".insn r 0x2b, 0x3, 0x39, " acc ", " acc ", x9\n"
#else
#define RQ_N 8   /* instructions in REQUANT_ASM; hardware-loop body lengths use it */
#define REQUANT_ASM(acc, t, u) \
  "srai " acc "," acc "," RQ_XS(SHIFT) "\n" \
  "srai " t "," acc ",31\n" \
  "xori " t "," t ",-1\n" \
  "and " acc "," acc "," t "\n" \
  "sltiu " t "," acc ",256\n" \
  "addi " t "," t ",-1\n" \
  "or " acc "," acc "," t "\n" \
  "andi " acc "," acc ",255\n"
#endif /* REQUANT_CLIP */
static inline unsigned char requant(int acc) {
    int t, u;
    asm (REQUANT_ASM("%0", "%1", "%2") : "+r"(acc), "=&r"(t), "=&r"(u));
    return (unsigned char)acc;
}
#else
typedef signed char act_t;
typedef signed char out_t;
#ifndef SHIFT
#define SHIFT 7
#endif
#if REQUANT_CLIP
/* Xpulp cv.clip rD, rs1, Is2: rD = clamp(rs1, -2^(Is2-1), 2^(Is2-1)-1); Is2 = 8 -> int8.
 * R-type, opcode 0x2b, funct3 011, funct7 0x38, Is2 in the rs2 field (x8). */
#define RQ_N 2
#define REQUANT_ASM(acc, t, u) \
  "srai " acc "," acc "," RQ_XS(SHIFT) "\n" \
  ".insn r 0x2b, 0x3, 0x38, " acc ", " acc ", x8\n"
#else
#define RQ_N 9   /* instructions in REQUANT_ASM; hardware-loop body lengths use it */
#define REQUANT_ASM(acc, t, u) \
  "srai " acc "," acc "," RQ_XS(SHIFT) "\n" \
  "addi " t "," acc ",128\n" \
  "sltiu " t "," t ",256\n" \
  "addi " t "," t ",-1\n" \
  "srai " u "," acc ",31\n" \
  "xori " u "," u ",127\n" \
  "xor " u "," u "," acc "\n" \
  "and " u "," u "," t "\n" \
  "xor " acc "," acc "," u "\n"
#endif /* REQUANT_CLIP */

static inline signed char requant(int acc) {
    int t, u;
    asm (REQUANT_ASM("%0", "%1", "%2") : "+r"(acc), "=&r"(t), "=&r"(u));
    return (signed char)acc;
}
#endif /* REAL_DATA */
#endif
