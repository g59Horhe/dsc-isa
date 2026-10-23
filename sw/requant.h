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
#ifndef SHIFT
#define SHIFT 7
#endif
#define RQ_XS(x) RQ_S(x)
#define RQ_S(x) #x

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
#endif
