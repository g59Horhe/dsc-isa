# Synthesis-only area for CV32E40P on Sky130 HD, via sv2v + Yosys.
#
#   make convert            sv2v -> build/cv32e40p.v
#   make base               COREV_PULP=0 -> build/base/stat.txt, area.json
#   make pulp               COREV_PULP=1 -> build/pulp/stat.txt, area.json
#   make all                both
#
# Tools: SV2V (zachjs/sv2v binary), YOSYS (oss-cad-suite or distro), and a
# Sky130 HD liberty file. Defaults assume ~/tools; override on the command
# line. Area is reported in um^2 and in NAND2 equivalents
# (sky130_fd_sc_hd__nand2_1 = 3.7536 um^2).
#
# register_file_latch.sv is excluded (use the flip-flop register file);
# fp_wrapper and top are excluded as in the Verilator harness.

CORE  ?= ../third_party/cv32e40p
SV2V  ?= $(HOME)/tools/sv2v-Linux/sv2v
YOSYS ?= $(HOME)/tools/oss-cad-suite/bin/yosys
LIB   ?= $(HOME)/tools/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib
NAND2_AREA ?= 3.7536

SRCS = $(CORE)/rtl/include/cv32e40p_pkg.sv \
       $(CORE)/rtl/include/cv32e40p_apu_core_pkg.sv \
       $(CORE)/rtl/include/cv32e40p_fpu_pkg.sv \
       $(filter-out %fp_wrapper.sv %cv32e40p_top.sv %register_file_latch.sv,$(wildcard $(CORE)/rtl/*.sv)) \
       $(CORE)/bhv/cv32e40p_sim_clock_gate.sv

.PHONY: all convert base pulp clean

all: base pulp

convert: build/cv32e40p.v

build/cv32e40p.v: $(SRCS)
	mkdir -p build
	$(SV2V) -I$(CORE)/rtl/include -I$(CORE)/rtl $(SRCS) -w $@

base: build/cv32e40p.v
	mkdir -p build/base
	$(YOSYS) -q -l build/base/yosys.log -p "read_verilog -sv build/cv32e40p.v; chparam -set COREV_PULP 0 cv32e40p_core; script synth.ys; dfflibmap -liberty $(LIB); abc -liberty $(LIB); opt_clean -purge; tee -o build/base/stat.txt stat -liberty $(LIB); tee -q -o build/base/stat.json stat -liberty $(LIB) -json"
	python3 area.py build/base/stat.json $(NAND2_AREA) > build/base/area.txt; cat build/base/area.txt

pulp: build/cv32e40p.v
	mkdir -p build/pulp
	$(YOSYS) -q -l build/pulp/yosys.log -p "read_verilog -sv build/cv32e40p.v; chparam -set COREV_PULP 1 cv32e40p_core; script synth.ys; dfflibmap -liberty $(LIB); abc -liberty $(LIB); opt_clean -purge; tee -o build/pulp/stat.txt stat -liberty $(LIB); tee -q -o build/pulp/stat.json stat -liberty $(LIB) -json"
	python3 area.py build/pulp/stat.json $(NAND2_AREA) > build/pulp/area.txt; cat build/pulp/area.txt

clean:
	rm -rf build

# Hierarchical pass: no flatten, so stat reports area per module. Slightly
# larger totals than the flat pass (no cross-module optimisation); use it for
# attribution, not for the headline number.
hier-base hier-pulp: build/cv32e40p.v
	$(eval CFG := $(subst hier-,,$@))
	$(eval PULP := $(if $(filter pulp,$(CFG)),1,0))
	mkdir -p build/hier-$(CFG)
	$(YOSYS) -q -l build/hier-$(CFG)/yosys.log -p "read_verilog -sv build/cv32e40p.v; chparam -set COREV_PULP $(PULP) cv32e40p_core; hierarchy -check -top cv32e40p_core; proc; opt -full; memory -nomap; opt_clean; synth -top cv32e40p_core -run coarse:; opt -full; dfflibmap -liberty $(LIB); abc -liberty $(LIB); opt_clean -purge; tee -q -o build/hier-$(CFG)/stat.json stat -liberty $(LIB) -json"

hier: hier-base hier-pulp
	python3 hier_area.py build/hier-base/stat.json build/hier-pulp/stat.json $(NAND2_AREA) | tee build/hier_area.txt

# Attribution pass: tag every cell with its module of origin, flatten so the
# COREV_PULP constants propagate and dead logic is removed, then partition the
# surviving cells back into per-origin submodules before mapping. Totals match
# the flat pass; per-module numbers show where the extension's area lives.
# Order matters: a later tag overrides an earlier one, so alu_div comes after
# alu. Two patterns per module: plain name, and parameterised name (yosys
# appends \PARAM=... after the module name for some instances).
MODS = aligner alu alu_div apu_disp compressed_decoder controller cs_registers decoder ex_stage ff_one fifo hwloop_regs id_stage if_stage int_controller load_store_unit mult obi_interface popcnt prefetch_buffer prefetch_controller register_file sleep_unit clock_gate
TAG = setattr -set submod \"o_core\" cv32e40p_core/c:*; $(foreach m,$(MODS),setattr -set submod \"o_$(m)\" *cv32e40p_$(m)/c:*; setattr -set submod \"o_$(m)\" *cv32e40p_$(m)?*/c:*;)

attrib-base attrib-pulp: build/cv32e40p.v
	$(eval CFG := $(subst attrib-,,$@))
	$(eval PULP := $(if $(filter pulp,$(CFG)),1,0))
	mkdir -p build/attrib-$(CFG)
	$(YOSYS) -q -l build/attrib-$(CFG)/yosys.log -p "read_verilog -sv build/cv32e40p.v; chparam -set COREV_PULP $(PULP) cv32e40p_core; hierarchy -check -top cv32e40p_core; proc; $(TAG) flatten -wb; opt; opt_clean; submod; hierarchy -top cv32e40p_core; synth -top cv32e40p_core -run coarse:; opt -full; techmap; opt -fast; dfflibmap -liberty $(LIB); abc -liberty $(LIB); opt_clean -purge; tee -q -o build/attrib-$(CFG)/stat.json stat -liberty $(LIB) -json"

attrib: attrib-base attrib-pulp
	python3 hier_area.py build/attrib-base/stat.json build/attrib-pulp/stat.json $(NAND2_AREA) | tee build/attrib_area.txt

# ---------------------------------------------------------------------------
# Timing. Two mappings per configuration: area-oriented (abc default, the
# numbers in the area tables) and delay-oriented (abc -D target, in ps).
# OpenSTA (the sta binary from the litex-hub conda openroad package, ~/tools/eda)
# reports the critical path of the mapped netlist against PERIOD_NS.
STA ?= $(HOME)/tools/eda/bin/sta
ABC_D    ?= 8000        # ps, delay target for the delay-oriented mapping
PERIOD_NS ?= 10

net-%: build/cv32e40p.v
	$(eval CFG := $(word 1,$(subst -, ,$*)))
	$(eval MAP := $(word 2,$(subst -, ,$*)))
	$(eval PULP := $(if $(filter pulp,$(CFG)),1,0))
	$(eval ABCOPT := $(if $(filter delay,$(MAP)),-D $(ABC_D),))
	mkdir -p build/net-$*
	$(YOSYS) -q -l build/net-$*/yosys.log -p "read_verilog -sv build/cv32e40p.v; chparam -set COREV_PULP $(PULP) cv32e40p_core; script synth.ys; dfflibmap -liberty $(LIB); abc $(ABCOPT) -liberty $(LIB); opt_clean -purge; tee -q -o build/net-$*/stat.json stat -liberty $(LIB) -json; write_verilog -noattr build/net-$*/netlist.v"
	python3 area.py build/net-$*/stat.json $(NAND2_AREA) | head -3

sta-%: net-%
	LIB=$(LIB) NETLIST=build/net-$*/netlist.v TOP=cv32e40p_core PERIOD_NS=$(PERIOD_NS) $(STA) -exit sta.tcl > build/net-$*/sta.txt 2>&1; grep -E "WORST_SLACK|TNS|slack \(|data arrival time" build/net-$*/sta.txt | tail -5

timing: sta-base-area sta-pulp-area sta-base-delay sta-pulp-delay
	@for c in base-area pulp-area base-delay pulp-delay; do printf "%-12s " $$c; python3 area.py build/net-$$c/stat.json $(NAND2_AREA) | grep "NAND2" | tr '\n' ' '; grep WORST_SLACK build/net-$$c/sta.txt; done

# Placement-aware timing (OpenROAD: floorplan, global/detailed placement, DRV
# repair, placement parasitics, repair_timing). Uses the area-mapped netlists.
OPENROAD ?= $(HOME)/tools/eda/bin/openroad
TLEF  ?= $(HOME)/tools/sky130/sky130_fd_sc_hd.tlef
LEF   ?= $(HOME)/tools/sky130/sky130_fd_sc_hd_merged.lef
TRACKS ?= $(HOME)/tools/sky130/make_tracks.tcl
UTIL  ?= 45
place-%:
	mkdir -p build/place-$*
	TLEF=$(TLEF) LEF=$(LEF) LIB=$(LIB) TRACKS=$(TRACKS) NETLIST=build/net-$*-area/netlist.v TOP=cv32e40p_core PERIOD_NS=$(PERIOD_NS) UTIL=$(UTIL) $(OPENROAD) -exit place.tcl > build/place-$*/openroad.txt 2>&1; grep -E "WORST_SLACK|Design area|ERROR" build/place-$*/openroad.txt | tail -6
