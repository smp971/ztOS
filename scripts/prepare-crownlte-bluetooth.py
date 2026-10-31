#!/usr/bin/env python3
"""Prepare the Bluetooth board module after checking Crown's stock wiring."""
import argparse
import importlib.util
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--stock-dtb', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
args = ap.parse_args()
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', root / 'scripts/verify-crownlte.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
t = v.fdt(args.stock_dtb.read_bytes())
v.require(b'Crown' in t['/'].get('model', b''), 'stock DTB is not Crown')
v.require(v.cells(t['/uart@10840000']['reg']) == [0, 0x10840000, 0x100], 'unexpected Bluetooth UART')
v.require(v.cells(t['/uart@10840000']['interrupts']) == [0, 422, 0], 'unexpected UART interrupt')
phandles = {v.cells(d['phandle'])[0]: p for p, d in t.items() if 'phandle' in d}
gpios = v.cells(t['/bluetooth']['gpios'])
wiring = [(phandles[gpios[i]], gpios[i + 1]) for i in range(0, len(gpios), 3)]
v.require(wiring == [('/hsi2c@10930000/pcal6524@22', 7),
                     ('/pinctrl@10430000/gpg2', 0),
                     ('/pinctrl@14050000/gpa2', 3)], 'Bluetooth GPIO wiring differs')
v.require(v.cells(t['/hsi2c@10930000/pcal6524@22']['reg']) == [0x22], 'unexpected GPIO expander')
if args.output.exists():
    raise SystemExit('Output already exists')
args.output.mkdir(parents=True)
source = (root / 'bluetooth/driver/zrn-bt.c').read_text()
anchor = '\tif (!(test_skip & 8))\n'
v.require(source.count(anchor) == 1, 'Bluetooth board initializer changed')
source = source.replace(anchor, '\tif (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n\n' + anchor)
(args.output / 'crown-bt.c').write_text(source)
(args.output / 'Kbuild').write_text('obj-m += crown-bt.o\n')
print('Crown Bluetooth UART, interrupt and GPIO wiring checked; sources prepared')
