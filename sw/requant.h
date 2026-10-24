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

static inline signed char requant(int acc) {
    int t, u;
    asm (REQUANT_ASM("%0", "%1", "%2") : "+r"(acc), "=&r"(t), "=&r"(u));
    return (signed char)acc;
}
#endif /* REAL_DATA */
#endif
