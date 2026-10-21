# Bare-metal software for the CV32E40P harness

No OS, no newlib, no libc. `crt0.S` sets the stack, zeroes `.bss`, calls
`main()`, and reports the return value by storing it to 0x10000000, which
the harness treats as a halt.

## Verified results

    make run-hello    -> HALT at cycle 38, value = 42
    make run-dotp     -> COREV_PULP=1: HALT at cycle 41, value = 10
                         COREV_PULP=0: TIMEOUT

The timeout on the baseline core is the point: `cv.dotsp.b` is an illegal
instruction there, so the core traps to mtvec (left at 0 by the harness)
and spins. If this ever *passes* on the baseline, something is wrong with
your build -- the instruction is being decoded when it shouldn't be.

## Emitting Xpulp instructions without a custom toolchain

Upstream riscv-gnu-toolchain does not know the `cv.*` mnemonics. Use
`.insn` with the raw encoding instead of chasing the PULP GCC fork:

    asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2"
                  : "=r"(r) : "r"(a), "r"(b));

cv.dotsp.b, from docs/source/instruction_set_extensions.rst:

    [31:25] = 0x48    [24:20] = rs2   [19:15] = rs1
    [14:12] = 0x1     [11:7]  = rd    [6:0]   = 0x7b

It computes the sum of four signed 8-bit products:

    rD = rs1[7:0]*rs2[7:0] + rs1[15:8]*rs2[15:8]
       + rs1[23:16]*rs2[23:16] + rs1[31:24]*rs2[31:24]

Other encodings are in the same table: cv.dotup.b (unsigned),
cv.dotusp.b (mixed), and the .sc / .sci scalar and scalar-immediate
variants. Same opcode 0x7b, different funct3/funct7.

## Memory map

    0x00000080   image load address, entry point
    0x0000fff0   stack top (grows down)
    0x10000000   magic halt -- store here to end the simulation
    64 KB total flat memory, no wait states

## Known gap

The harness grants every memory request in one cycle. Real MCU memory
stalls. Since the whole study is about operand supply, add configurable
wait states before trusting any cycle counts, and record what was used.
