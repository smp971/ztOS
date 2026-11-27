#!/usr/bin/env python3
"""Prepare Note9-only light modules after checking its saved stock wiring."""
import argparse
import importlib.util
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--stock-dtb', required=True, type=Path)
ap.add_argument('--output', required=True, type=Path)
a = ap.parse_args()
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', repo / 'scripts/verify-crownlte.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
t = v.fdt(a.stock_dtb.read_bytes())
v.require(b'Crown' in t['/'].get('model', b''), 'not a Crown stock DTB')
ph = {v.cells(p['phandle'])[0]: name for name, p in t.items() if 'phandle' in p}
flash = next((n for n, p in t.items() if p.get('compatible') == b's2mpb02,s2mpb02mfd\0'), '')
v.require(bool(flash), 'Crown camera PMIC not found')
v.require(v.cells(t[flash]['reg']) == [0x59], 'camera PMIC address differs')
parent = flash.rsplit('/', 1)[0]
for prop, pin in (('gpio_scl', 0), ('gpio_sda', 1)):
    cells = v.cells(t[parent][prop])
    v.require(ph[cells[0]].endswith('/gpp6') and cells[1] == pin, 'camera PMIC GPIOs differ')
for prop, bank, pin in (('torch1-gpio', 'gpg2', 4), ('flash1-gpio', 'gpg3', 5)):
    cells = v.cells(t[flash + '/torch'][prop])
    v.require(ph[cells[0]].endswith('/' + bank) and cells[1] == pin, 'torch selector differs')
table = v.cells(t[flash + '/torch/leds2']['torch_table'])
v.require(table and max(table) == 9, 'Crown user torch table differs')
v.require(t['/rgb']['rgb-name'] == b'led_w\0led_r\0led_g\0led_b\0', 'Crown RGB channels differ')
v.require(v.cells(t['/rgb']['normal_powermode_current_uu']) == [10], 'Crown RGB current differs')
v.require(not a.output.exists(), 'output already exists')
a.output.mkdir(parents=True)
for name in ('led', 'flash'):
    source = (repo / f'leds/zrn-{name}.c').read_text()
    source = source.replace('#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/of.h>')
    anchor = '\tregmap = devm_regmap_init_i2c' if name == 'led' else '\tgpiod_add_lookup_table(&flash_gpios);'
    v.require(source.count(anchor) == 1, 'light driver probe changed')
    source = source.replace(anchor, '\tif (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n\n' + anchor)
    if name == 'led':
        source = source.replace('static unsigned int max_percent = 60;', 'static unsigned int max_percent = 2;')
        source = source.replace('clamp(max_percent, 1u, 100u)', 'clamp(max_percent, 1u, 2u)')
        source = source.replace('(default 60)', '(capped at 2)')
        source = source.replace('dev_get_regmap(&pdev->dev, NULL)', 'dev_get_regmap(pdev->dev.parent, NULL)')
    else:
        source = source.replace('torch.max_brightness = CUR1_TORCH;', 'torch.max_brightness = 9;')
    source = source.replace('Galaxy S9', 'Galaxy Note9')
    (a.output / f'crown-{name}.c').write_text(source)
(a.output / 'Makefile').write_text('obj-m += crown-led.o\nobj-m += crown-flash.o\n')
print('Crown RGB/torch wiring verified; RGB current capped at code 5, torch at stock user code 9')
