# Power of a routed point over a measured window, from gate-level switching activity (M3).
# env: DIR (routed point: routed.odb, routed.spef), PERIOD_NS, VCD (from the gate-level harness,
# --fst --fst-hp, converted with fst2vcd), optional LIB, SCOPE (default TOP/cv32e40p_core)
# Prints the annotation coverage, the power report and POWER_TOTAL/_INTERNAL/_SWITCHING/_LEAKAGE in W.
set lib [expr {[info exists ::env(LIB)] ? $::env(LIB) : "$::env(HOME)/tools/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib"}]
set scope [expr {[info exists ::env(SCOPE)] ? $::env(SCOPE) : "TOP/cv32e40p_core"}]
read_liberty $lib
read_db $::env(DIR)/routed.odb
read_spef $::env(DIR)/routed.spef
create_clock -name clk -period $::env(PERIOD_NS) [get_ports clk_i]
set_propagated_clock [all_clocks]
read_vcd -scope $scope $::env(VCD)
report_activity_annotation
report_power -digits 6
# total, internal, switching, leakage of the whole design, from the report's Total row
set rep [sta::design_power [sta::cmd_scene]]
puts "POWER_INTERNAL [lindex $rep 0]"
puts "POWER_SWITCHING [lindex $rep 1]"
puts "POWER_LEAKAGE [lindex $rep 2]"
puts "POWER_TOTAL [lindex $rep 3]"
