#!/usr/bin/env python3
"""Validate Crown stock speaker wiring before preparing the live audio module."""
import argparse
import importlib.util
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--stock-dtb', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', root / 'scripts/verify-crownlte.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
t = v.fdt(a.stock_dtb.read_bytes())
v.require(b'Crown' in t['/'].get('model', b''), 'not a Crown stock DTB')
def check(path, prop, expected):
    v.require(v.cells(t[path][prop]) == expected, f'unexpected {path}:{prop}')
check('/abox@398786560', 'reg', [0, 0x17c50000, 0x10000, 0, 0x17c10000, 0x10000, 0, 0x17d00000, 0x31000])
check('/abox_gic@399441920', 'reg', [0, 0x17cf1000, 0x1000, 0, 0x17cf2000, 0x1004])
check('/abox_gic@399441920', 'interrupts', [0, 76, 0])
amp = '/hsi2c@108C0000/max98512@39'
for prop, value in [('reg', [0x39]), ('maxim,sub_reg', [0x3a]),
                    ('maxim,spk-gain', [5]), ('maxim,spk-gain-rcv', [1]),
                    ('maxim,digital-gain-rcv', [0x34]), ('maxim,mono_stereo', [1])]:
    check(amp, prop, value)
ph = {v.cells(d['phandle'])[0]: p for p, d in t.items() if 'phandle' in d}
codec = '/spi@10470000/cs47l93@0'
reset = v.cells(t[codec]['reset-gpios'])
v.require(ph[reset[0]] == '/pinctrl@10430000/gpg1' and reset[1:] == [0, 0], 'codec reset differs')
for prop, rail, voltage in [('AVDD-supply', 'LDO33', 1800000), ('DCVDD-supply', 'LDO34', 1200000)]:
    path = ph[v.cells(t[codec][prop])[0]]
    v.require(path.endswith('/' + rail), 'codec supply differs')
    check(path, 'regulator-min-microvolt', [voltage])
    check(path, 'regulator-max-microvolt', [voltage])
for prop, pin in [('gpio_scl', 4), ('gpio_sda', 5)]:
    cells = v.cells(t['/hsi2c@108C0000'][prop])
    v.require(ph[cells[0]] == '/pinctrl@10830000/gpp4' and cells[1] == pin, 'amplifier GPIO mismatch')
v.require(not a.output.exists(), 'output exists')
a.output.mkdir(parents=True)
source = (root / 'audio/driver/snd-zrn-abox.c').read_text()
anchor = '\tINIT_DELAYED_WORK(&gear_work, gear_tell);'
v.require(source.count(anchor) == 1, 'audio initializer changed')
source = source.replace(anchor, '\tif (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n\n' + anchor)
source = source.replace('amp_i2c = { .udelay = 5 }', 'amp_i2c = { .udelay = 25 }')
mapping = '''/* MAX98512 revision B register translation, from the phone's GPL driver:
 * LineageOS/android_kernel_samsung_universal9810, commit
 * 5a2dd7d6f3a05168d2f1303c3b29e9e9fa39b781, max98512_remap_reg().
 * Copyright (C) 2017 Maxim Integrated Products, GPL-2.0-or-later.
 */
static bool crown_amp_rev_b[2];
static u16 crown_amp_reg(u8 addr, u16 reg)
{
    if (!crown_amp_rev_b[addr == AMP_R]) return reg;
    if (reg >= 0x0020 && reg <= 0x0028) return reg + 3;
    if (reg >= 0x002b && reg <= 0x004c) return reg + 1;
    if (reg >= 0x004f && reg <= 0x0053) return reg + 2;
    if (reg >= 0x0058 && reg <= 0x005f) return reg - 2;
    if (reg >= 0x0070 && reg <= 0x007f) return reg - 18;
    if (reg >= 0x0080 && reg <= 0x008d) return reg - 13;
    if (reg == 0x0400) return 0x0500;
    if (reg == 0x0401) return 0x0501;
    if (reg == 0x0402) return 0x0600;
    return reg;
}

'''
anchor = 'static void amp_write(u8 addr, u16 reg, u8 val)'
v.require(source.count(anchor) == 1, 'amplifier writer changed')
source = source.replace(anchor, mapping + anchor)
source = source.replace('u8 buf[3] = { reg >> 8, reg & 0xff, val };',
                        'u16 mapped = crown_amp_reg(addr, reg);\n\tu8 buf[3] = { mapped >> 8, mapped & 0xff, val };')
source = source.replace('u8 address[2] = { reg >> 8, reg & 0xff }, value;',
                        'u16 mapped = crown_amp_reg(addr, reg);\n\tu8 address[2] = { mapped >> 8, mapped & 0xff }, value;')
anchor = '\tret = snd_card_new(dev, SNDRV_DEFAULT_IDX1, "ZrnAbox", THIS_MODULE, 0, &card);'
v.require(source.count(anchor) == 1, 'ALSA card creation changed')
source = source.replace(anchor, '''
    if (!amp_bus) { ret = -ENODEV; goto err; }
    for (i = 0; i < 2; i++) {
        int addr = i ? AMP_R : AMP_L;
        int revision = amp_read(addr, 0x0402);
        if (revision < 0x40 || revision > 0x4f) {
            revision = amp_read(addr, 0x0600);
            if (revision < 0x40 || revision > 0x4f) {
                pr_err("snd-crown-abox: unknown amplifier revision at %02x\\n", addr);
                ret = -ENODEV; goto err;
            }
            crown_amp_rev_b[i] = true;
        }
        pr_info("snd-crown-abox: amplifier %02x revision %02x, map %s\\n",
                addr, revision, crown_amp_rev_b[i] ? "B" : "A");
    }
''' + anchor)
source = source.replace('Galaxy S9 speakers', 'Galaxy Note9 speakers')
(a.output / 'snd-crown-abox.c').write_text(source)
(a.output / 'Kbuild').write_text('obj-m += snd-crown-abox.o\n')
print('Crown ABOX, IRQ and stereo speaker wiring validated; module prepared')
