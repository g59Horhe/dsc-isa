# Synthesis-only area, Sky130 HD

    make convert     sv2v -> build/cv32e40p.v (about one second)
    make all         flat synthesis, COREV_PULP=0 and 1 -> build/{base,pulp}/area.txt
    make attrib      per-module attribution -> build/attrib_area.txt
    make hier        plain hierarchical pass (for comparison only; see below)

Tools, overridable on the make command line:

    SV2V   ~/tools/sv2v-Linux/sv2v                 zachjs/sv2v v0.0.13 release binary
    YOSYS  ~/tools/oss-cad-suite/bin/yosys         OSS CAD Suite 2026-10-23, Yosys 0.70
    LIB    ~/tools/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib
           from The-OpenROAD-Project/OpenROAD-flow-scripts, flow/platforms/sky130hd/lib

Notes that cost time:

- sv2v handles CV32E40P in one pass with no manual fixes once
  `register_file_latch.sv` is excluded (it redefines `cv32e40p_register_file`).
- A plain hierarchical synthesis (`make hier`) is wrong for the RV32IMC
  configuration: the dot-product datapath survives in the multiplier because
  the decoder's constants do not cross module boundaries. Use the flat numbers
  for totals and `make attrib` for per-module attribution.
- No OpenROAD here yet; the OSS CAD Suite ships yosys but not openroad or sta.
- Yosys warns about `raddr_*_i` range selects (FPU address bit with FPU off) and
  one inferred latch (the clock gate). Both expected.
