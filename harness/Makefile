# CV32E40P under Verilator -- baseline (RV32IMC) and Xpulp configurations.
#
# Point CORE at your cv32e40p checkout, e.g.
#   make CORE=../third_party/cv32e40p run
#
# Targets:
#   make base    build COREV_PULP=0  -> obj_base/Vcv32e40p_core
#   make pulp    build COREV_PULP=1  -> obj_pulp/Vcv32e40p_core
#   make run     build both, run test.hex on both

CORE ?= ../third_party/cv32e40p
VERILATOR ?= verilator

# cv32e40p_top.sv and cv32e40p_fp_wrapper.sv are excluded: the wrapper needs
# the external cvfpu submodule and top.sv includes it. cv32e40p_core is the
# top module instead. The clock gate lives in bhv/, not rtl/.
SRCS = \
  $(CORE)/rtl/include/cv32e40p_pkg.sv \
  $(CORE)/rtl/include/cv32e40p_apu_core_pkg.sv \
  $(CORE)/rtl/include/cv32e40p_fpu_pkg.sv \
  $(filter-out %fp_wrapper.sv %cv32e40p_top.sv,$(wildcard $(CORE)/rtl/*.sv)) \
  $(CORE)/bhv/cv32e40p_sim_clock_gate.sv

# -Wno-BLKANDNBLK: cs_registers mixes blocking/non-blocking assignment on the
# performance counters (mhpmcounter_q). Real RTL smell, harmless here.
VFLAGS = --cc --exe --build -j 4 -Wno-fatal -Wno-BLKANDNBLK \
         --top-module cv32e40p_core \
         -I$(CORE)/rtl/include -I$(CORE)/rtl

.PHONY: all base pulp run clean

all: base pulp

base:
	$(VERILATOR) $(VFLAGS) --Mdir obj_base -GCOREV_PULP=0 public.vlt $(SRCS) sim_main.cpp

pulp:
	$(VERILATOR) $(VFLAGS) --Mdir obj_pulp -GCOREV_PULP=1 public.vlt $(SRCS) sim_main.cpp

test.hex: assemble.py
	python3 assemble.py > test.hex

run: base pulp test.hex
	@echo "=== COREV_PULP=0 (baseline RV32IMC) ==="
	@./obj_base/Vcv32e40p_core --hex test.hex --cycles 100000
	@echo "=== COREV_PULP=1 (Xpulp) ==="
	@./obj_pulp/Vcv32e40p_core --hex test.hex --cycles 100000

clean:
	rm -rf obj_base obj_pulp test.hex
