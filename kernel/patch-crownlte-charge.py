#!/usr/bin/env python3
"""Keep MAX77705 input-current writes consistent with the driver's readback."""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / 'drivers/power/supply/max77705_charger.c'
source = path.read_text()
old = '\tregval = clamp_val(val, clamp_min, clamp_max) / div;\n'
new = old + ('\t/* CHGIN encodes N steps as N - 1 (see get_input_current). */\n'
             '\tif (fidx == MAX77705_CHG_CHGIN_LIM && regval)\n'
             '\t\tregval--;\n')
if '--restore' in sys.argv[2:]:
    if new in source:
        path.write_text(source.replace(new, old))
    raise SystemExit(0)
if new not in source:
    if source.count(old) != 1:
        raise SystemExit('MAX77705 current setter changed; inspect before patching')
    source = source.replace(old, new)
    path.write_text(source)
print('Crown MAX77705 input-current encoding prepared')
