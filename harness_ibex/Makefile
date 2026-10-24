# Ibex (lowRISC, third_party/ibex at 8f4c75c5) under Verilator, same memory
# protocol and magic addresses as the CV32E40P harness.
#
#   make ibex2   2-stage pipeline (WritebackStage=0) -> obj_ibex2/Vibex_top
#   make ibex3   3-stage pipeline (WritebackStage=1) -> obj_ibex3/Vibex_top
#
# Configuration: RV32I, M (single-cycle multiplier, like CV32E40P), C, no B,
# flip-flop register file, no ICache, no PMP, 10 hardware performance counters
# (Ibex's fixed events 3..12). ibex.f is the file list derived from the fusesoc
# ibex_simple_system target (lowRISC fusesoc fork); gen/ holds the primgen
# wrappers that fusesoc generates (prim_pkg, prim_buf, prim_flop, ...).
VERILATOR ?= verilator
IBEX = ../third_party/ibex
SRCS = $(addprefix ../,$(shell cat ibex.f))
INCS = -I$(IBEX)/vendor/lowrisc_ip/ip/prim/rtl -I$(IBEX)/vendor/lowrisc_ip/dv/sv/dv_utils -I$(IBEX)/rtl -Igen
# Enum parameters by value (ibex_pkg: RV32M None=0 Slow=1 Fast=2 SingleCycle=3; RV32BNone=0; RegFileFF=0); ENUMVALUE warning disabled for them.
PARAMS = -GRV32M=3 -GRV32B=0 -GRegFile=0 -GMHPMCounterNum=10 -GICache=0 -GPMPEnable=0 -GBranchTargetALU=1
VFLAGS = --cc --exe --build -j 4 -Wno-fatal -Wno-WIDTH -Wno-UNOPTFLAT -Wno-ENUMVALUE --top-module ibex_top $(INCS) $(PARAMS)

.PHONY: all ibex2 ibex3 clean
all: ibex2 ibex3
ibex2:
	$(VERILATOR) $(VFLAGS) -GWritebackStage=0 --Mdir obj_ibex2 $(SRCS) sim_main.cpp
ibex3:
	$(VERILATOR) $(VFLAGS) -GWritebackStage=1 --Mdir obj_ibex3 $(SRCS) sim_main.cpp
clean:
	rm -rf obj_ibex2 obj_ibex3
