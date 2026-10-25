# Where an ISA extension's speedup comes from

A counter-validated measurement of the Xpulp extension on CV32E40P for the
three kernels of a MobileNet depthwise-separable block, with area and timing
at Sky130, real MobileNetV1 data, and a second core (lowRISC Ibex). Open tools
throughout; every table in `results/RESULTS.md` and in both papers is
generated from the committed data by the scripts in this repository.

- `results/RESULTS.md`: every result, with the tables and the commands behind them.
- `paper/paper.pdf`: six-page conference version. `paper/tc/paper_tc.pdf`: journal version.

## Reproducing

    git clone --recursive https://github.com/g59Horhe/dsc-isa.git
    cd dsc-isa
    ./reproduce.sh            # all stages, about 30 minutes
    ./reproduce.sh list       # stage names; run any subset, e.g. ./reproduce.sh sims check collect compare

Regenerated datasets go to `results/repro/` and are not copied over the
committed files; the `compare` stage diffs them. What should come out:

| quantity | expected reproduction |
|---|---|
| every counter CSV in `results/` (cycles, counters, checksums) | identical, row for row |
| latency sweeps (`results/*_sweep.txt`) | identical |
| alignment term (`results/wait0_align.csv`) | identical |
| synthesis totals, flat (`syn/build/{base,pulp}/area.txt`) | identical: 43,771 and 68,703 GE |
| per-module attribution (`syn/build/attrib_area.txt`) | delta within about 20 GE of 24,218 (ABC varies between checkouts; no derived figure moves) |
| placement (`syn/build/place-*/openroad.txt`) | identical: slack $-1.521$ / $-2.984$ ns after repair, 187,770 / 297,737 um^2 |

Two quick checks before anything else (`./reproduce.sh sims check`):

    hello  (both configs)    HALT at cycle 38, value = 42
    dotp   COREV_PULP=1      HALT at cycle 41, value = 10
    dotp   COREV_PULP=0      TIMEOUT after 5000 cycles      (expected: cv.dotsp.b is illegal there)

After any collector run, grep the CSV for `FAIL` before analysing it; a
build failure becomes a `BUILDFAIL` row, not an error.

### Prerequisites

| component | version used | where |
|---|---|---|
| Verilator | 5.020 | distribution package |
| riscv32-unknown-elf-gcc | 16.1.0, built from riscv-gnu-toolchain with `--with-arch=rv32imc --with-abi=ilp32` | `RISCV_BIN` (default `/opt/riscv/bin`) |
| sv2v | 0.0.13 | `SV2V` (default `~/tools/sv2v-Linux/sv2v`) |
| Yosys | 0.70+201, OSS CAD Suite 2026-10-23 | `YOSYS` (default `~/tools/oss-cad-suite/bin/yosys`) |
| OpenROAD and OpenSTA | litex-hub conda `openroad` package (`micromamba create -p ~/tools/eda -c litex-hub -c conda-forge openroad`) | `OPENROAD`, `STA` (default `~/tools/eda/bin/`) |
| Sky130 HD | `sky130_fd_sc_hd__tt_025C_1v80.lib`, `sky130_fd_sc_hd.tlef`, `sky130_fd_sc_hd_merged.lef`, `make_tracks.tcl` from the open PDK | `LIB`, `TLEF`, `LEF`, `TRACKS` (default `~/tools/sky130/`) |
| Python | 3.12; a venv with numpy 2.5, Pillow 13, ai-edge-litert 2.3 for `ibex_model.py` and the real-data generator | `VENV_PYTHON` (default `~/tools/venv/bin/python`) |
| MobileNetV1 model | `mobilenet_v1_1.0_224_quant.tflite`, sha256 `ecc3a67c47c5a609ec35f6a58a7d97532834e43df4cb7d3f1204a8164b7d20dd` | `MOBILENET_TFLITE` (default `~/tools/models/`) |
| test image | `grace_hopper.jpg`, sha256 `a8ca6d734765703b09728ab47fe59f473d93ae3967fc24c7c0288c3c7adb7130` | `MOBILENET_IMAGE` (default `~/tools/models/`) |
| TeX Live | pdflatex, bibtex, IEEEtran, booktabs, pgfplots | on `PATH` |
| CV32E40P | submodule at `b353438` | `third_party/cv32e40p` |
| Ibex | submodule at `8f4c75c5` | `third_party/ibex` |

The counter datasets need only Verilator and the RISC-V toolchain. The real-data
headers are committed, so the model and image are needed only to regenerate them
(the journal table generator does, and checks the result against the committed
headers). The `syn/Makefile` variables are overridden on the command line or in
the environment.

### Stage times

Measured on a fresh clone on one laptop, Verilator with `-j4`: the four
simulator builds about 5 minutes; all CV32E40P counter datasets 10 minutes;
the Ibex datasets 5 minutes; the two sweeps 30 seconds; the alignment term 1
minute (it rebuilds 304 binaries and asserts each reproduces its committed
cycle count); synthesis with attribution 1.5 minutes; placement 75 seconds per
configuration; models and papers seconds. The whole sequence after the
simulators is about 25 minutes.

## Layout

    harness/        Verilator testbench for CV32E40P, collect_wait0.sh (counters), sweep.sh (latency), check_hwloop.py
    harness_ibex/   the same testbench for Ibex 2- and 3-stage, with the generated prim wrappers
    sw/             bare-metal kernels, requant.h (shared saturation), xpulp.h (.insn encodings), real/ (MobileNetV1 headers and generator)
    results/        counter CSVs, sweep outputs, the model scripts, RESULTS.md
    syn/            sv2v + Yosys synthesis and attribution, OpenROAD placement (place.tcl), Ibex synthesis; build/ holds the committed flow outputs
    paper/          conference manuscript; paper/tc/ journal manuscript with its table generator
    third_party/    CV32E40P and Ibex submodules

Simulator flags: `--hex`, `--cycles`, `--wait N` (data port), `--iwait N`
(instruction port), `--icache SIZE LINE`, `--redir FILE` (histogram of
non-sequential instruction fetches, for the alignment term). The MEASURED line
carries data reads, data writes and instruction fetches for the bracketed
region. `-DPERF_EVENT=<bit>` with `-march=rv32imc_zicsr` reports one hardware
counter; `-DCODE_PAD=<n>` shifts code alignment by n compressed nops; both
alignments are measured for every number. See `sw/bench.h`.

## Why CV32E40P

One codebase gives both ends of the comparison. `COREV_PULP` is a plain
parameter: 0 is RV32IMC, 1 adds the Xpulp extension including the int8 SIMD
dot products (`cv.dotsp.b`, `cv.dotup.b`, `cv.dotusp.b`), hardware loops,
post-increment addressing and clip. Baseline and extension differ by a
parameter rather than by a core, a node and a research group.

## Four things CV32E40P needs under Verilator

1. `cv32e40p_fp_wrapper.sv` needs the external cvfpu submodule. Excluded;
   there is no FPU in this study.
2. `cv32e40p_top.sv` includes the FP wrapper, so it is excluded too, and
   `cv32e40p_core` is the top module.
3. The clock gate is in `bhv/`, not `rtl/`. Add
   `bhv/cv32e40p_sim_clock_gate.sv` explicitly.
4. `cs_registers` mixes blocking and non-blocking assignment on
   `mhpmcounter_q`. Verilator rejects this by default; `-Wno-BLKANDNBLK`
   is the workaround. The counters read correctly: loads retired matched bus
   reads exactly on every kernel.

Ibex: drive reset as a falling edge. `ibex_top` gates the core clock until
fetch is enabled, so a reset held low from time zero is never sampled and the
core comes up in user mode. Enum parameters go to Verilator as integers with
`-Wno-ENUMVALUE`.

## Custom instructions without a custom toolchain

Upstream GCC does not know the `cv.*` mnemonics. `.insn` with raw encodings
works:

    asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2"
                  : "=r"(r) : "r"(a), "r"(b));      // cv.dotsp.b

Encodings are in `third_party/cv32e40p/docs/source/instruction_set_extensions.rst`
and collected in `sw/xpulp.h`. Hardware loops need `.balign 4` before
`.option norvc`, a constant `cv.setup` immediate, and
`harness/check_hwloop.py` after every build.

## Method rules learned the hard way

- State the baseline's compiler flags. `-O3` is 1.26 to 2.6x faster than
  `-O2` on these kernels, and a hand kernel that matches `-O3` within 1% can
  still lose 17 to 32% to a different loop order (the 5x5 case).
- Put requantisation in inline assembly. GCC compiles "branchless" C
  saturation into taken branches worth 13 to 19% of cycles.
- Put wait states on the data port only (`--iwait 0`); with both ports waited
  the core is fetch-starved and a sweep measures instruction count.
- Measure both code alignments. A taken branch to a 32-bit instruction at an
  address 2 mod 4 costs one aligner cycle; it is the fifth term of the cycle
  model and is counted per run.
- Validate counters against the bus before using them, and checksum every
  variant against an independent model of the arithmetic.

## References

- Atasu et al., *Optimizing Instruction-set Extensible Processors under Data
  Bandwidth Constraints*, DATE 2007.
- Pozzi and Ienne, *Exploiting Pipelining to Relax Register-File Port
  Constraints of Instruction-Set Extensions*, CASES 2005.
- Biswas, Dutt, Pozzi and Ienne, *Introduction of Architecturally Visible
  Storage in Instruction Set Extensions*, IEEE TCAD 26(3), 2007.
- Galuzzi and Bertels, *The Instruction-Set Extension Problem: A Survey*,
  ACM TRETS 4(2), 2011.
- Schuiki et al., *Stream Semantic Registers*, IEEE TC 70(2), 2021.
- Garofalo et al., *XpulpNN*, DATE 2020.
- Liu et al., *Convex: A RISC-V Instruction Set Extension Scheme for
  Accelerating Convolution Operations on MCUs*, HP3C 2024.
- Wang et al., *Optimizing CNN Computation Using RISC-V Custom Instruction
  Sets for Edge Platforms*, IEEE TC 73(5), 2024 (RI5CY-Accel, evaluated on an FPGA).
- Lu et al., *Design and FPGA Evaluation of a Multi-Operand Extension
  Mechanism for Tightly Coupled RISC-V Processors*, Electronics 15(19), 2026.
