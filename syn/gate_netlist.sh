#!/bin/sh
# Gate-level simulation netlist of a routed point, for switching-activity capture (M3).
#   sh gate_netlist.sh build/sweep-or26rc-rep2/pulp-16 build/gate/pulp-16
# 1. OpenROAD writes the routed netlist (routed.odb, after CTS, repair and routing: every buffer
#    and clock-tree cell that the power analysis will see) as routed.v.
# 2. Yosys builds each cell's logic from the Sky130 liberty functions (read_liberty without -lib;
#    -ignore_miss_func skips the cells with no function, such as the dlclkp clock gate, which these
#    netlists do not use) and writes the cell models as modules next to the unchanged routed
#    netlist. Not flattening keeps every routed net under its own name in the top module (flatten
#    plus opt_clean renamed most of them after cell ports), which is what the power analysis
#    matches activity on. The result, gate.v, is plain Verilog for Verilator; the harness traces
#    the top module only. Tap cells (power-only, no logic) are deleted first; any other cell
#    without a model stops the run.
set -e
SRC=$1; OUT=$2
OPENROAD=${OPENROAD_ROUTE:-/usr/bin/openroad}
YOSYS=${YOSYS:-$HOME/tools/oss-cad-suite/bin/yosys}
LIB=${LIB:-$HOME/tools/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib}
mkdir -p $OUT
printf 'read_db %s/routed.odb\nwrite_verilog %s/routed.v\n' "$SRC" "$OUT" > $OUT/export.tcl
$OPENROAD -exit $OUT/export.tcl > $OUT/export.log 2>&1
$YOSYS -q -l $OUT/yosys.log -p "read_liberty -ignore_miss_func $LIB; read_verilog $OUT/routed.v; delete t:sky130_fd_sc_hd__tapvpwrvgnd_1; hierarchy -check -top cv32e40p_core; tee -q -o $OUT/stat.txt stat; write_verilog -noattr $OUT/gate.v"
grep -E '^=== |Number of cells' $OUT/stat.txt | tail -2
