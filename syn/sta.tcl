# OpenSTA timing on a yosys-mapped netlist (standalone sta binary).
# env: LIB (liberty), NETLIST (verilog), TOP, PERIOD_NS
# Unplaced, unbuffered netlist: high-fanout nets (reset, decoder outputs) carry
# their full pin capacitance with no buffer tree, so absolute delays are
# pessimistic. Reported separately: register-to-register paths (the core's
# own logic depth), and paths from inputs / to outputs excluding rst_ni.
read_liberty $::env(LIB)
read_verilog $::env(NETLIST)
link_design $::env(TOP)
create_clock -name clk -period $::env(PERIOD_NS) [get_ports clk_i]
set_input_delay 0 -clock clk [delete_from_list [all_inputs] [get_ports clk_i]]
set_output_delay 0 -clock clk [all_outputs]
set_false_path -from [get_ports rst_ni]
puts "=== register to register ==="
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] -fields {fanout cap slew} -digits 3 -group_count 1
puts "=== input to register (rst_ni excluded) ==="
report_checks -path_delay max -from [delete_from_list [all_inputs] [get_ports {clk_i rst_ni}]] -to [all_registers -data_pins] -digits 3 -group_count 1
puts "=== register to output ==="
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_outputs] -digits 3 -group_count 1
puts "WORST_SLACK_NO_RST [format %.3f [worst_slack -max]]"
