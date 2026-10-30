# Write a route.tcl checkpoint as DEF for viewing in KLayout with the Sky130 LEFs.
# env: ODB (checkpoint), DEF (output)
read_db $::env(ODB)
write_def $::env(DEF)
