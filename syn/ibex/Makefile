# Ibex (third_party/ibex at 8f4c75c5) synthesis-only area at Sky130 HD, same
# flow as ../Makefile for CV32E40P. Configuration as in harness_ibex/Makefile:
# RV32IMC, single-cycle multiplier, FF register file, 10 counters, BTALU.
#   make wb0   2-stage (WritebackStage=0)      make wb1   3-stage
SV2V  ?= $(HOME)/tools/sv2v-Linux/sv2v
YOSYS ?= $(HOME)/tools/oss-cad-suite/bin/yosys
LIB   ?= $(HOME)/tools/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib
NAND2_AREA ?= 3.7536
IBEX = ../../third_party/ibex
FLIST = ../../harness_ibex/ibex.f
INCS = -I$(IBEX)/vendor/lowrisc_ip/ip/prim/rtl -I$(IBEX)/vendor/lowrisc_ip/dv/sv/dv_utils -I$(IBEX)/rtl -I../../harness_ibex/gen
PARAMS = -set RV32M 3 -set RV32B 0 -set RegFile 0 -set MHPMCounterNum 10 -set ICache 0 -set PMPEnable 0 -set BranchTargetALU 1

.PHONY: all wb0 wb1 clean
all: wb0 wb1
ibex.v: $(FLIST)
	$(SV2V) $(INCS) -DSYNTHESIS -DYOSYS $(addprefix ../../,$(shell cat $(FLIST))) -w $@
	python3 strip_sim.py $@

wb0 wb1: ibex.v
	mkdir -p $@
	$(YOSYS) -q -l $@/yosys.log -p "read_verilog -sv -DSYNTHESIS ibex.v; chparam $(PARAMS) -set WritebackStage $(subst wb,,$@) ibex_top; hierarchy -check -top ibex_top; proc; flatten -wb; opt -full; memory -nomap; opt_clean; synth -top ibex_top -run coarse:; opt -full; techmap; opt -fast; dfflibmap -liberty $(LIB); abc -liberty $(LIB); opt_clean -purge; tee -q -o $@/stat.json stat -liberty $(LIB) -json"
	python3 ../area.py $@/stat.json $(NAND2_AREA) | head -3
clean:
	rm -rf ibex.v wb0 wb1
