# OpenROAD: detailed routing alone, from a route.tcl global-route checkpoint
# (OUT/grt.odb and OUT/route.guide). It shows the design routes with zero DRC
# violations; timing stays as route.tcl reported it, since without OpenRCX rules
# for Sky130 the parasitics would again come from the global routes.
# env: OUT, THREADS
read_db $::env(OUT)/grt.odb
set_thread_count $::env(THREADS)
detailed_route -guide $::env(OUT)/route.guide -bottom_routing_layer met1 -top_routing_layer met5 -output_drc $::env(OUT)/drc.rpt -verbose 1
puts "DRC_VIOLATIONS [expr {[file exists $::env(OUT)/drc.rpt] ? [llength [regexp -all -inline {violation type} [read [open $::env(OUT)/drc.rpt]]]] : -1}]"
write_db $::env(OUT)/routed.odb
