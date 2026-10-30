# KLayout macro: open a DEF with the Sky130 HD LEFs. Run as
#   DEF=path/to/file.def klayout -rm view_def.py
import os, pya
home = os.path.expanduser('~/tools/sky130')
opt = pya.LoadLayoutOptions()
cfg = opt.lefdef_config
cfg.read_lef_with_def = False
cfg.lef_files = [home + '/sky130_fd_sc_hd.tlef', home + '/sky130_fd_sc_hd_merged.lef']
for d in os.environ['DEF'].split(':'):
    pya.Application.instance().main_window().load_layout(d, opt, 1)
