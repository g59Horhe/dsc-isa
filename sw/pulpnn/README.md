# PULP-NN kernels (third-party)

From [pulp-platform/pulp-nn](https://github.com/pulp-platform/pulp-nn) at
commit `288d06b7e36e8e7fe7f1d7c986161bf7c85fc952` (2023-10-18), `32bit/`
tree. Apache License 2.0 (`LICENSE`); Copyright (C) 2018-2020 University of
Bologna. Cite Garofalo et al., "PULP-NN: accelerating quantized neural
networks on parallel ultra-low-power RISC-V processors", Phil. Trans. R. Soc.
A 378 (2020), doi:10.1098/rsta.2019.0155.

Copied unchanged (`cmp` against the commit):

- `src/pulp_nn_depthwise_3x3_s1.c`, `src/pulp_nn_depthwise_generic.c`,
- `src/pulp_nn_pointwise_HoWo_parallel.c`, `src/pulp_nn_matmul.c`,
- `include/pulp_nn_utils.h`, `include/pulp_nn_kernels.h`.

Added here, not PULP-NN:

- `include/pmsis.h`, the SDK stand-in: types, one core, and the builtin mapping
  to CV32E40P's cv.* instructions; read its header comment;
- `pulp_nn_quant.c`, the two requantisation helpers the kernels reference,
  copied verbatim from `pulp_nn_utils.c`.

The drivers are `sw/pulpnn_dw3.c`, `sw/pulpnn_dw5.c` and `sw/pulpnn_pw.c`.
Build flags: `-O3 -Isw/pulpnn/include -march=rv32imc_xcvsimd_xcvalu
-Wno-error=int-conversion -fno-tree-loop-distribute-patterns`.
- `-Wno-error=int-conversion`: `pulp_nn_depthwise_generic.c` keeps a pointer
  in an `int`, which GCC 14 and later reject by default.
- `-fno-tree-loop-distribute-patterns`: stops GCC calling `memset`, as there
  is no libc.

What each driver does around the unchanged kernel:

- **`PULPNN_LIB=1` (default):** each kernel entry point is redeclared
  `noipa`, so it is compiled as a separately built library would be, not
  specialised for the call's constant shape. `PULPNN_LIB=0` lets GCC
  specialise it. At these shapes the difference is up to 2.7x in cycles.
- **3x3:** `pulp_nn_depthwise_3x3_s1` works only with left/right padding 1:
  with 0 its row pointer drifts by two bytes per row. The driver therefore
  calls it with padding 1 and checks the W-2 interior columns, which equal the
  valid convolution. The kernel computes W/(W-2) times the outputs of the
  study's valid kernels. The kernel's `CH` parameter clashes with `-DCH`,
  hence a `push_macro`.
- **5x5, synthetic int8 data:** the generic kernel does (K*K)&3 MACs per
  output in plain C on a `uint8_t` activation. The driver includes it under
  `#define uint8_t int8_t`, which retypes those bytes. The load becomes `lb`
  instead of `lbu`, at the same cost; the cycle counts with and without the
  define are identical.

## Builds and compilers

`reproduce.sh` collects six builds:
- **Upstream GCC 16.1** (`-march=rv32imc_xcvsimd_xcvalu`), which has no
  CORE-V hardware loops or post-increment.
- **CORE-V GCC 14.1** (`~/tools/corev-gcc`, set `COREV_BIN`), without and
  with `_xcvhwlp_xcvmem`, which make the compiler generate `cv.setup`
  hardware loops and post-increment or register-indexed loads and stores.
  CORE-V GCC is OpenHW's toolchain built by Embecosm: the
  `corev-openhw-gcc-ubuntu2204-20240530` package, sha256
  `f4c79749ac4b870e01f55bf29ae29aeaa468b3c96cfa31391a85737d9ebf2160`,
  the CV32E40Pv2 sign-off build.

Each compiler's builds come with `PULPNN_LIB=1` and `0`.

Its opcode table matches the encodings in `sw/xpulp.h`. CORE-V GCC 14
emits identical code for `PULPNN_LIB=0` and `1`, because it does not
specialise these kernels either way.

