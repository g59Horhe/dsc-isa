# OpenROAD: floorplan, placement, DRV repair (buffering/resizing), placement-based
# parasitics, then timing. Gives placement-aware pre-CTS, pre-route numbers for a
# yosys-mapped netlist; the raw netlist's unbuffered high-fanout nets make plain
# STA meaningless (see sta.tcl note).
# env: TLEF, LEF, LIB, NETLIST, TOP, PERIOD_NS, UTIL (core utilisation %), OUT
read_lef $::env(TLEF)
read_lef $::env(LEF)
read_liberty $::env(LIB)
read_verilog $::env(NETLIST)
link_design $::env(TOP)
create_clock -name clk -period $::env(PERIOD_NS) [get_ports clk_i]
set_input_delay 0 -clock clk [delete_from_list [all_inputs] [get_ports clk_i]]
set_output_delay 0 -clock clk [all_outputs]
set_false_path -from [get_ports rst_ni]
initialize_floorplan -utilization $::env(UTIL) -aspect_ratio 1.0 -core_space 2.0 -site unithd
source $::env(TRACKS)
place_pins -hor_layers met3 -ver_layers met2
set_wire_rc -signal -layer met2
set_wire_rc -clock  -layer met3
global_placement -density 0.65 -timing_driven
estimate_parasitics -placement
repair_design
detailed_placement
estimate_parasitics -placement
puts "=== design area ==="
report_design_area
puts "=== register to register, after placement and DRV repair ==="
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] -fields {fanout cap slew} -digits 3 -group_count 1
puts "WORST_SLACK_R2R [format %.3f [worst_slack -max]]"
puts "=== repair_timing toward the target period ==="
repair_timing -setup
estimate_parasitics -placement
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] -digits 3 -group_count 1
puts "WORST_SLACK_AFTER_REPAIR [format %.3f [worst_slack -max]]"
report_design_area
