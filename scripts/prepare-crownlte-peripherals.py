#!/usr/bin/env python3
"""Prepare isolated haptic and sensor-hub modules after checking stock wiring."""
import argparse
import importlib.util
import shutil
import hashlib
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--stock-dtb', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
ap.add_argument('--hub-patch', type=Path, required=True, help='Crown patch matched to the original kernel')
a = ap.parse_args()
r = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', r / 'scripts/verify-crownlte.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
t = v.fdt(a.stock_dtb.read_bytes())
v.require(b'Crown' in t['/']['model'], 'not Crown')
ph = {v.cells(d['phandle'])[0]: p for p, d in t.items() if 'phandle' in d}
v.require(v.cells(t['/pwm@10510000']['reg']) == [0, 0x10510000, 0x1000], 'PWM differs')
v.require(t['/pinctrl@10430000/vib-pwm']['samsung,pins'] == b'gpp3-1\0', 'PWM pin differs')
v.require(t['/pinctrl@10430000/motor-boost-en']['samsung,pins'] == b'gpg1-7\0', 'motor enable differs')
v.require(v.cells(t['/haptic']['haptic,period'])[0] == 48828, 'motor period differs')
v.require(v.cells(t['/haptic']['haptic,reg2']) == [0x82], 'motor mode differs')
hub = '/spi@13AC0000/BCM4773@0'
for prop, bank, pin in [('ssp-host-req', 'gpa1', 7), ('ssp-mcu-req', 'gph0', 5),
                        ('ssp-mcu-resp', 'gph0', 4), ('ssp-batch-wake-irq', 'gpa0', 5),
                        ('ssp-shub-int', 'gpa4', 0)]:
    g = v.cells(t[hub][prop])
    v.require(ph[g[0]].endswith('/' + bank) and g[1] == pin, 'hub GPIO differs: ' + prop)
v.require(not a.output.exists(), 'output exists')
patch = a.hub_patch.read_bytes()
v.require(len(patch) == 851282 and hashlib.sha256(patch).hexdigest() ==
          '4c68dfd8822648b86f7461bb30f537fbda48a04e02268b23610fd0d94b530120',
          'hub patch is not the verified Crown stock patch')
a.output.mkdir(parents=True)
h = a.output / 'haptic'; h.mkdir()
s = (r / 'haptics/zrn_haptic_main.c').read_text(encoding='utf-8')
s = s.replace('#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/of.h>')
s = s.replace('#define DUTY_PERCENT\t95', '#define DUTY_PERCENT\t83')
anchor = '\th = devm_kzalloc(dev, sizeof(*h), GFP_KERNEL);'
v.require(s.count(anchor) == 1, 'haptic initializer changed')
s = s.replace(anchor, '\tif (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n' + anchor)
(h / 'crown-haptic.c').write_text(s)
(h / 'Kbuild').write_text('obj-m += crown-haptic.o\n')
shutil.copytree(r / 'sensors/driver', a.output / 'sensorhub')
p = a.output / 'sensorhub/zrn_bbd_board.c'
s = p.read_text(encoding='utf-8')
s = s.replace('#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/of.h>')
anchor = '\tgph0 = ioremap(GPH0_BASE, 0x100);'
v.require(s.count(anchor) == 1, 'hub board initializer changed')
s = s.replace(anchor, '\tif (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n\n' + anchor)
p.write_text(s)
compat = a.output / 'sensorhub/zrn_compat.h'
s = compat.read_text().replace('#define CONFIG_SENSORS_SSP_STAR 1', '#define CONFIG_SENSORS_SSP_CROWN 1')
compat.write_text(s.replace('#define ANDROID_VERSION 90000', '#define ANDROID_VERSION 100000'))
p = a.output / 'sensorhub/bbd.c'
s = p.read_text(); start = s.index('static unsigned char bbd_patch[] = {')
end = s.index('\n};', start)
s = s[:start] + 'static unsigned char bbd_patch[] = {\n#include "crown_patch.inc"' + s[end:]
p.write_text(s)
(a.output / 'sensorhub/crown_patch.inc').write_text(',\n'.join(
    ','.join(f'0x{x:02x}' for x in patch[i:i+32]) for i in range(0, len(patch), 32)) + ',0x00\n')
print('Crown haptic and BCM4773 wiring validated; isolated sources prepared')
