#!/usr/bin/env python3
"""Generate sw/pwconv_asm.c and sw/pwconv_simd_asm.c: hand-written pointwise
1x1 convolution inner loops with explicit unrolled bodies for CI in {8, 16},
each with RV32IMC control (XPULP_CTRL=0) and Xpulp control (XPULP_CTRL=1).
Run from the repository root: python3 sw/gen_pwconv_asm.py"""

def scalar_body(ci, xp):
    L = []
    lb = lambda i: (f'LB_INC("%[w{i%2}]", "%[wp]", "1")' if xp else f'"lb %[w{i%2}],{i}(%[wp])\\n"')
    L.append(lb(0))
    for i in range(ci):
        if i + 1 < ci: L.append(lb(i + 1))                 # weight load one ahead of its multiply
        L.append('"mul %[acc],%[a0],%[w0]\\n"' if i == 0 else f'"mul %[t],%[a{i}],%[w{i%2}]\\n add %[acc],%[acc],%[t]\\n"')
    L.append('REQUANT_ASM("%[acc]", "%[t]", "%[u]")')
    L.append('SB_INC("%[acc]", "%[op]", "1")' if xp else '"sb %[acc],0(%[op])\\n"')
    n = ci + 1 + 2 * (ci - 1) + 9 + 1
    return "\n              ".join(L), n

def simd_body(ci, xp):
    nw = ci // 4
    loads = [(f'LW_INC("%[w{k}]", "%[wp]", "4")' if xp else f'"lw %[w{k}],{4*k}(%[wp])\\n"') for k in range(nw)]
    ops = ['DOTSP("%[acc]", "%[x0]", "%[w0]")'] + [f'SDOTSP("%[acc]", "%[x{k}]", "%[w{k}]")' for k in range(1, nw)]
    L = loads + ops + ['REQUANT_ASM("%[acc]", "%[t]", "%[u]")', 'SB_INC("%[acc]", "%[op]", "1")' if xp else '"sb %[acc],0(%[op])\\n"']
    return "\n              ".join(L), 2 * nw + 9 + 1

HDR = '''/* Pointwise 1x1 convolution -- hand-written {kind} inner loop.
 *
 * {desc}
 * The output-channel loop body is generated for CI = 8 and 16 (see
 * sw/gen_pwconv_asm.py); other CI values fall back to a compile error.
 * XPULP_CTRL=0: RV32IMC control (immediate-offset loads, addi + bne).
 * XPULP_CTRL=1: hardware loop over output channels, post-increment loads
 *               and stores.
 */
#include "pw_common.h"
#include "xpulp.h"
#ifndef XPULP_CTRL
#define XPULP_CTRL 0
#endif
'''

def block(ci, xp, decl, preload, body, n, outs):
    return f'''#if CI == {ci} && XPULP_CTRL == {xp}
        {decl}
        {"int cnt = CO;" if xp else "const signed char *wend = wp + CO * CI;"}
        asm volatile (
              {"XPULP_ASM_BEGIN" if xp else ""}
              {preload}
              {f'HWLOOP0("%[cnt]", "{n+1}")   /* {n} instructions in the body */' if xp else '"1:\\n"'}
              {body}
              {"" if xp else f'"addi %[wp],%[wp],{ci}\\n addi %[op],%[op],1\\n bne %[wp],%[wend],1b\\n"'}
              {"XPULP_ASM_END" if xp else ""}
              : [wp]"+r"(wp), [op]"+r"(op), [acc]"=&r"(acc), [t]"=&r"(t), [u]"=&r"(u), {outs}
              : [xp]"r"(xp_), {'[cnt]"r"(cnt)' if xp else '[wend]"r"(wend)'}
              : "memory");
#endif
'''

# ---------------- scalar ----------------
s = HDR.format(kind="scalar", desc="The CI activations of one pixel are held in registers across all CO output\n * channels (register blocking); each output costs CI weight loads, CI\n * multiplies, CI-1 adds, the shared requantisation and one store. Weight\n * loads are issued one ahead of their multiply.")
s += '''
static void pwconv_asm(void) {
    for (int p = 0; p < P; p++) {
        const signed char *xp_ = input[p];
        const signed char *wp = &weight[0][0];
        signed char *op = &output[p][0];
        int acc, t, u, w0, w1;
'''
for ci in (8, 16):
    decl = "int " + ", ".join(f"a{i}" for i in range(ci)) + ";"
    preload = "\n              ".join(f'"lb %[a{i}],{i}(%[xp])\\n"' for i in range(ci))
    outs = '[w0]"=&r"(w0), [w1]"=&r"(w1),\n                ' + ", ".join(f'[a{i}]"=&r"(a{i})' for i in range(ci))
    for xp in (1, 0):
        body, n = scalar_body(ci, xp); s += block(ci, xp, decl, preload, body, n, outs)
s += '''#if !((CI == 8 || CI == 16))
#error "pwconv_asm: CI must be 8 or 16"
#endif
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); pwconv_asm(); CYC_STOP(); return checksum(); }
'''
open('sw/pwconv_asm.c', 'w').write(s)

# ---------------- SIMD ----------------
s = HDR.format(kind="cv.dotsp.b", desc="The CI/4 activation words of one pixel are held in registers across all CO\n * output channels; each output costs CI/4 aligned weight-word loads, one\n * cv.dotsp.b plus CI/4-1 accumulating cv.sdotsp.b, the shared\n * requantisation and one store. All four lanes carry data.")
s += '''#define DOTSP(rd, rs1, rs2)  ".insn r 0x7b, 0x1, 0x48, " rd ", " rs1 ", " rs2 "\\n"   /* cv.dotsp.b  rd  = dot */
#define SDOTSP(rd, rs1, rs2) ".insn r 0x7b, 0x1, 0x54, " rd ", " rs1 ", " rs2 "\\n"   /* cv.sdotsp.b rd += dot */

static void pwconv_simd_asm(void) {
    for (int p = 0; p < P; p++) {
        const signed char *xp_ = input[p];
        const signed char *wp = &weight[0][0];
        signed char *op = &output[p][0];
        int acc, t, u; unsigned int w0, w1, w2, w3; (void)w2; (void)w3;
'''
for ci in (8, 16):
    nw = ci // 4
    decl = "unsigned int " + ", ".join(f"x{i}" for i in range(nw)) + ";"
    preload = "\n              ".join(f'"lw %[x{i}],{4*i}(%[xp])\\n"' for i in range(nw))
    outs = ", ".join(f'[w{k}]"=&r"(w{k})' for k in range(nw)) + ",\n                " + ", ".join(f'[x{i}]"=&r"(x{i})' for i in range(nw))
    for xp in (1, 0):
        body, n = simd_body(ci, xp); s += block(ci, xp, decl, preload, body, n, outs)
s += '''#if !((CI == 8 || CI == 16))
#error "pwconv_simd_asm: CI must be 8 or 16"
#endif
    }
}
int main(void) { BENCH_PAD(); init_data(); CYC_START(); pwconv_simd_asm(); CYC_STOP(); return checksum(); }
'''
open('sw/pwconv_simd_asm.c', 'w').write(s)
print("wrote sw/pwconv_asm.c and sw/pwconv_simd_asm.c")
