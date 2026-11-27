#!/usr/bin/env python3
"""Prepare a Crown-only SCORE module; keep DSP faults from retrying in IRQ."""
import argparse
import importlib.util
from pathlib import Path
import shutil

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--stock-dtb', required=True, type=Path)
ap.add_argument('--output', required=True, type=Path)
a = ap.parse_args()
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', repo / 'scripts/verify-crownlte.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
t = v.fdt(a.stock_dtb.read_bytes())
v.require(b'Crown' in t['/'].get('model', b''), 'not Crown')
p = t['/score@16D00000']
v.require(v.cells(p['reg']) == [0, 0x16d00000, 0x100000], 'SCORE registers differ')
v.require(v.cells(p['interrupts']) == [0, 222, 0], 'SCORE IRQ differs')
for name, address in [('16C20000', 0x16c20000), ('16C30000', 0x16c30000)]:
    v.require(v.cells(t['/sysmmu@' + name]['reg']) == [0, address, 0x9000], 'SCORE SYSMMU differs')
v.require(not a.output.exists(), 'output exists')
a.output.mkdir(parents=True)
for f in (repo / 'score/driver').iterdir():
    if f.suffix in ('.c', '.h') or f.name == 'Makefile':
        shutil.copy2(f, a.output / f.name)
f = a.output / 'zrn_score_board.c'
s = f.read_text()
anchor = '\tint irq = score_irq();'
v.require(s.count(anchor) == 1, 'SCORE board initializer changed')
s = s.replace(anchor, '\tint irq;\n\n\tif (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n\tirq = score_irq();')
f.write_text(s)
f = a.output / 'score_interface.c'
s = f.read_text()
anchor = '''\t\t\tscore_system_halt(itf->system);
\t\t\tif (++itf->faults > ZRN_SCORE_MAX_FAULTS ||
\t\t\t\t\tscore_system_boot(itf->system))
\t\t\t\tzrn_score_interface_fault(itf);'''
v.require(s.count(anchor) == 1, 'SCORE fault handler changed')
s = s.replace(anchor, '''\t\t\t/* No firmware boot or reset loop in hard IRQ on Crown.
\t\t\t * Mask the DSP and reject work until a controlled restart. */
\t\t\tzrn_score_interface_fault(itf);''')
f.write_text(s)
f = a.output / 'score_firmware.c'
f.write_text(f.read_text().replace('"score/', '"crownlte/score/'))
f = a.output / 'Makefile'
f.write_text(f.read_text().replace('zrn-score', 'crown-score'))
print('Crown SCORE resources verified; module restricted to Crown; IRQ faults stop the DSP interface')
