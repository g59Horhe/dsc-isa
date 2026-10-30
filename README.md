# Where an ISA extension's speedup comes from

A counter-validated measurement of the Xpulp extension on CV32E40P for the
three kernels of a MobileNet depthwise-separable block, with area and timing
at Sky130, real MobileNetV1 data, and a second core (lowRISC Ibex). Open tools
throughout; every table in `results/RESULTS.md` and in the papers written from it is
generated from the committed data by the scripts in this repository
(`results/paper_tables.py` writes the manuscript tables and figure data to
`results/paper_gen/`).

- `results/RESULTS.md`: every result, with the tables and the commands behind them.

## Reproducing

    git clone --recursive https://github.com/g59Horhe/dsc-isa.git
    cd dsc-isa
    ./reproduce.sh            # all stages, about 20 minutes
    ./reproduce.sh list       # stage names; run any subset, e.g. ./reproduce.sh sims check collect compare

Regenerated datasets go to `results/repro/` and are not copied over the
committed files; the `compare` stage diffs them. What should come out:

| quantity | expected reproduction |
|---|---|
| every counter CSV in `results/` (cycles, counters, checksums) | identical, row for row |
| latency sweeps (`results/*_sweep.txt`) | identical |
| alignment term (`results/wait0_align.csv`) | identical |
| saturation-idiom and `-Os` sets (`results/wait0_{zbb,branch,Os}_*.csv`) | identical, row for row |
| both-port wait-state runs (`results/both_ports.csv`) | identical |
| synthesis totals, flat (`syn/build/{base,pulp}/area.txt`) | identical: 43,771 and 68,703 GE |
| per-module attribution (`syn/build/attrib_area.txt`) | delta within about 20 GE of 24,218 (ABC varies between checkouts; no derived figure moves) |
| placement (`syn/build/place-*/openroad.txt`) | identical: slack $-1.521$ / $-2.984$ ns after repair, 187,770 / 297,737 um^2 |
| unplaced-netlist STA (`syn/build/net-*/sta.txt`) | register-to-register arrival 22.0 / 29.1 ns (area-mapped) and 26.7 / 29.9 ns (delay-mapped): not meaningful, kept as the negative example |

Two stages are not in the default run because of their length. The routed
timing sweep (`make -C syn sweep`: CTS, routing, extraction and post-route
repair at 32 clock targets, about 3.5 hours) is committed as
`syn/build/sweep-or26rc-rep2/` (`sweep.csv`, `penalty.csv`, `run.sh` and the
32 `openroad.txt` logs). The energy stage (`./reproduce.sh energy`, about 1.5
hours) exports four of its routed points to gate level, builds a traced
simulator for each and runs the power analysis; its output is
`results/energy_runs.csv`.

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
| Yosys | 0.70+201, OSS CAD Suite 2026-10-23; its `fst2vcd` serves the energy stage | `YOSYS` (default `~/tools/oss-cad-suite/bin/yosys`), `FST2VCD` |
| OpenROAD and OpenSTA, 2022 build | litex-hub conda `openroad` package (`micromamba create -p ~/tools/eda -c litex-hub -c conda-forge openroad`); placement and timing repair (`place.tcl`) and the unplaced-netlist STA | `OPENROAD`, `STA` (default `~/tools/eda/bin/`) |
| OpenROAD 26Q2 | `26Q2-1164-g08f67ee5ec`, the Precision Innovations .deb (vaultlink.precisioninno.com); CTS, routing, extraction and post-route repair (`route.tcl`, `make sweep`) and the power analysis (`power.tcl`) | `OPENROAD_ROUTE` (default `/usr/bin/openroad`) |
| Sky130 HD wire RC | OpenROAD-flow-scripts `flow/platforms/sky130hd/`: `setRC.tcl`, sha256 `6aeade350bf498177ea61506db8849a064a71848b05c18ad6a6e1fc5d62c962a`, and `rcx_patterns.rules`, sha256 `d5bd9b1077ceac9929416abca272a6d52e51cd9a575453a31d129817bb286476`. The tech LEF's wire capacitance is about half the calibrated value, so timing uses these | `RC_TCL`, `RCX_RULES` (default `~/tools/openroad-26q2/rcx/`) |
| riscv32-corev-elf-gcc | 14.1.0, Embecosm `corev-openhw-gcc-ubuntu2204-20240530` from buildbot.embecosm.com, tarball sha256 `f4c79749ac4b870e01f55bf29ae29aeaa468b3c96cfa31391a85737d9ebf2160`; the only compiler here that emits CORE-V hardware loops and post-increment, used for the PULP-NN datasets `wait0_pulpnncv*` and `pulpnn_clip_loops.py`, which are skipped when it is absent | `COREV_BIN` (default `~/tools/corev-gcc/bin`) |
| Sky130 HD | `sky130_fd_sc_hd__tt_025C_1v80.lib`, `sky130_fd_sc_hd.tlef`, `sky130_fd_sc_hd_merged.lef`, `make_tracks.tcl` from the open PDK | `LIB`, `TLEF`, `LEF`, `TRACKS` (default `~/tools/sky130/`) |
| Python | 3.12; a venv with numpy 2.5, Pillow 13, ai-edge-litert 2.3 for `ibex_model.py` and the real-data generator | `VENV_PYTHON` (default `~/tools/venv/bin/python`) |
| MobileNetV1 model | `mobilenet_v1_1.0_224_quant.tflite`, sha256 `ecc3a67c47c5a609ec35f6a58a7d97532834e43df4cb7d3f1204a8164b7d20dd` | `MOBILENET_TFLITE` (default `~/tools/models/`) |
| test image | `grace_hopper.jpg`, sha256 `a8ca6d734765703b09728ab47fe59f473d93ae3967fc24c7c0288c3c7adb7130` | `MOBILENET_IMAGE` (default `~/tools/models/`) |
| TeX Live | pdflatex, bibtex, IEEEtran, booktabs, pgfplots | on `PATH` |
| CV32E40P | submodule at `b353438` | `third_party/cv32e40p` |
| Ibex | submodule at `8f4c75c5` | `third_party/ibex` |

The counter datasets need only Verilator and the RISC-V toolchain, except the
PULP-NN datasets built with CORE-V GCC. The routed sweep needs OpenROAD 26Q2 and
the RC files; the energy stage needs those and `fst2vcd`. The real-data
headers are committed, so the model and image are needed only to regenerate them
(`results/paper_tables.py` does, and checks the result against the committed
headers). The `syn/Makefile` variables are overridden on the command line or in
the environment.

### Stage times

Measured on a fresh clone on one laptop, Verilator with `-j4`: the four
simulator builds about 5 minutes; all CV32E40P counter datasets 2 minutes and
the Ibex datasets 1 minute (one build per run); the two sweeps 30 seconds; the alignment term 1
minute (it rebuilds 368 binaries and asserts each reproduces its committed
cycle count); the `questions` stage (96 both-port runs, and the alignment
microbenchmark on a patched core it builds) 15 seconds, plus a few minutes the
first time for that core's Verilator build; synthesis with attribution
1.5 minutes; placement 75 seconds per configuration; models about a minute
(`pulpnn_clip_loops.py` rebuilds PULP-NN 24 times) and papers seconds. The
whole default sequence after the simulators is about 20 minutes. Outside the
defaults, the routed sweep takes about 3.5 hours (32 targets, 4 jobs of 4
threads) and the energy stage about 1.5 hours (four gate-level simulator builds
20 minutes, 50 traced runs with power analysis 75 minutes).

## Layout

    harness/        Verilator testbench for CV32E40P, collect_wait0.sh (counters), sweep.sh (latency), check_hwloop.py, gate-level build (make gate)
    harness_ibex/   the same testbench for Ibex 2- and 3-stage, with the generated prim wrappers
    sw/             bare-metal kernels, requant.h (shared saturation), xpulp.h (.insn encodings), real/ (MobileNetV1 headers and generator)
    results/        counter CSVs, sweep outputs, the model scripts, RESULTS.md
    syn/            sv2v + Yosys synthesis and attribution, OpenROAD placement (place.tcl), CTS, routing and extraction (route.tcl, make sweep),
                    gate-level netlists and power (gate_netlist.sh, power.tcl), Ibex synthesis; build/ holds the committed flow outputs
    third_party/    CV32E40P and Ibex submodules

Simulator flags: `--hex`, `--cycles`, `--wait N` (data port), `--iwait N`
(instruction port), `--icache SIZE LINE`, `--redir FILE` (histogram of
non-sequential instruction fetches, for the alignment term). The MEASURED line
carries data reads, data writes and instruction fetches for the bracketed
region; the EVENTS line carries the core's performance-counter events (ev1 to
ev10, numbered as in `sw/bench.h`), integrated by the harness over the same
window, so every counter comes from the binary whose cycles are reported.
`-DPERF_EVENT=<bit>` with `-march=rv32imc_zicsr` still programs the CSR counter
and reports it as an AUX word; `results/counter_validation.py` uses it to check
the EVENTS counts. `-DCODE_PAD=<n>` shifts code alignment by n compressed nops;
both alignments are measured for every number. `sw/requant.h` holds the one
saturation sequence every kernel uses, and its review modes: `-DREQUANT_CLIP=1`
(`cv.clip`), `-DREQUANT_ZBB=1` (a three-instruction Zbb-style min/max
saturation, two one-cycle ALU stand-ins since the core has no Zbb; cycles only
on data that saturate) and `-DREQUANT_BRANCH=1` (a not-taken-branch fast path
with the clamp out of line; not for hardware-loop bodies). A gate-level build
(`make -C harness gate PT=<point>`, from a routed netlist of the sweep) has no
EVENTS line and takes two more flags: `--fst FILE` records the core's nets over
the measured window, and `--fst-hp PS` sets the half clock period so that trace
times are real time.

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
- Validate counters against the bus before using them, and take them from
  the binary whose cycles you report. An instrumented build that reads the
  CSR counter is a different binary: GCC may compile it differently and its
  layout shifts. Checksum every variant against an independent model of the
  arithmetic.

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

## Licence

The code in this repository (harness, kernels, flows, scripts) is licensed
under the Apache License 2.0 (see `LICENSE`). The measured data and the
results document (`results/*.csv`, `results/*.txt`, `syn/build`,
`results/RESULTS.md`) are licensed under CC BY 4.0: reuse them with
attribution to this repository. CV32E40P and Ibex in `third_party/` carry
their own licences.

Copyright 2026 George Jefferson Dessa.
