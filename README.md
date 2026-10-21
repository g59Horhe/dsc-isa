# Operand supply for depthwise separable convolution on constrained RISC-V

Work in progress. Measuring what it costs, in area and cycles, to add
multiply-accumulate hardware to a single-issue in-order RISC-V core for
int8 depthwise separable convolution, and where the operand-supply
mechanism rather than the multiplier count becomes the limit.

Everything here runs on open tools. The point is that the numbers can be
reproduced, not that they come from the best available PDK.

## Status

Infrastructure works end to end. No measurements yet.

| Step | State |
|---|---|
| CV32E40P elaborates under Verilator | done |
| Baseline (`COREV_PULP=0`) builds and runs | done |
| Xpulp (`COREV_PULP=1`) builds and runs | done |
| Bare-metal C flow, no libc | done |
| Custom instructions via `.insn` | done |
| Cycle counting between markers | not started |
| Memory wait states | not started |
| int8 depthwise conv kernel | not started |
| Sky130 + OpenROAD synthesis | not started |

## Layout

    harness/        Verilator C++ testbench and build
    sw/             bare-metal programs, linker script, crt0
    third_party/    CV32E40P submodule
    results/        measurements (empty)

## Quick start

    cd harness && make all        # builds obj_base/ and obj_pulp/
    cd ../sw   && make run-hello  # expect: HALT at cycle 38, value = 42
                  make run-dotp   # expect: 10 on Xpulp, TIMEOUT on baseline

The toolchain must be on PATH:

    export PATH=/opt/riscv/bin:$PATH

## Verified results

Recorded 2026-10-21. These are the regression checks; if any changes,
something in the environment moved.

    hello  (both configs)    HALT at cycle 38, value = 42
    dotp   COREV_PULP=1      HALT at cycle 41, value = 10
    dotp   COREV_PULP=0      TIMEOUT after 5000 cycles

The timeout is the expected result, not a failure. `cv.dotsp.b` is illegal
without the extension, so the core traps to mtvec (left at 0 by the
harness) and spins. If this ever passes on the baseline, the build is wrong.

## Environment

| Component | Version |
|---|---|
| Verilator | 5.020 |
| riscv32-unknown-elf-gcc | 16.1.0 (built from riscv-gnu-toolchain) |
| Toolchain config | `--with-arch=rv32imc --with-abi=ilp32` |
| CV32E40P | commit `b353438ff469c030c89f6804f3b24a2852880e8b` |
| OS | Linux |

Confirm the submodule with `git submodule status`. Update this table
whenever any of it changes, including on a different machine.

## Why CV32E40P

One codebase gives both ends of the comparison. `COREV_PULP` is a plain
parameter: 0 is RV32IMC, 1 adds the Xpulp extensions including the int8
SIMD dot products (`cv.dotsp.b`, `cv.dotup.b`, `cv.dotusp.b`). That makes
the baseline and the strongest published reference point differ by a
parameter rather than by a core, a node, and a research group.

It is also the same RI5CY lineage as XpulpNN and RI5CY-Accel, so area and
cycle numbers are comparable to both without a translation argument.

## Four things CV32E40P needs under Verilator

Documented here because none of it is obvious and all of it cost time.

1. `cv32e40p_fp_wrapper.sv` needs the external cvfpu submodule. Excluded —
   there is no FPU in this study.
2. `cv32e40p_top.sv` includes the FP wrapper, so it is excluded too, and
   `cv32e40p_core` is the top module instead.
3. The clock gate is in `bhv/`, not `rtl/`. Add
   `bhv/cv32e40p_sim_clock_gate.sv` explicitly.
4. `cs_registers` mixes blocking and non-blocking assignment on
   `mhpmcounter_q`. Verilator rejects this by default; `-Wno-BLKANDNBLK`
   is the workaround. It is a genuine RTL smell, not a Verilator bug — if
   anything odd shows up around the performance counters after synthesis,
   start here.

## Custom instructions without a custom toolchain

Upstream GCC does not know the `cv.*` mnemonics, and the PULP GCC fork is
not worth the maintenance. `.insn` with raw encodings works:

    asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2"
                  : "=r"(r) : "r"(a), "r"(b));      // cv.dotsp.b

Encodings are in `third_party/cv32e40p/docs/source/instruction_set_extensions.rst`.
The same approach will carry any custom instruction added later, so no
toolchain work is needed for the rest of the project.

## Known gaps

**The memory model is perfect.** Every request is granted in one cycle, no
wait states. Real MCU memory stalls, and since this study is specifically
about operand supply, the memory model shapes the answer. Configurable
wait states are needed before any cycle count means anything, and whatever
is used must be reported.

**Cycle counts include startup.** The harness counts from reset. Benchmarks
need markers the program writes itself so the measured region excludes
reset and fetch-enable.

**`COREV_PULP=1` has only been exercised by one instruction.** Building is
not the same as being correct across the extension.

## References

The operand-supply problem is not new. Cite these, do not rediscover them.

- Atasu et al., *Optimizing Instruction-set Extensible Processors under
  Data Bandwidth Constraints*, DATE 2007. Design-space exploration of
  operand supply with full place-and-route at UMC 130nm. 4.3x speedup at
  35% area on 2 read / 1 write ports.
- Pozzi & Ienne, *Exploiting Pipelining to Relax Register-File Port
  Constraints of Instruction-Set Extensions*, CASES 2005.
- Biswas et al., *Introduction of Architecturally Visible Storage in
  Instruction Set Extensions*, IEEE TCAD 26(3), 2007. Weight-stationary
  storage under another name; port-count vs area measured.
- Galuzzi & Bertels, *The Instruction-Set Extension Problem: A Survey*,
  ACM TRETS 4(2), 2011.
- Schuiki et al., *Stream Semantic Registers*, IEEE TC 70(2), 2021.
  11% area on RI5CY. arXiv:1911.08356.
- Garofalo et al., *XpulpNN*, DATE 2020.
- Liu et al., *Convex*, HP3C 2024. Weight storage and activation reuse on
  E203. No area numbers reported.
- Wang et al., *Optimizing CNN Computation Using RISC-V Custom Instruction
  Sets for Edge Platforms*, IEEE TC 73(5), 2024. RI5CY-Accel, TSMC 90nm,
  area 3.09M to 6.44M units.
