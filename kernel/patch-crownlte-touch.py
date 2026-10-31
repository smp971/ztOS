#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare experimental Y771 binding support; never powers a real device.

Only apply for a separately selected Crown touch bring-up build. The shared
8-byte protocol and LDO35/LDO43 rails have been checked against Samsung's
universal9810 driver and this phone's DT. Hardware probing remains untested.
"""
import sys
from pathlib import Path


def replace(path, old, new):
    text = path.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        sys.exit(f"crownlte-touch: source drift at {path}")
    path.write_text(text.replace(old, new, 1))


if len(sys.argv) != 2:
    sys.exit("usage: patch-crownlte-touch.py <kernel-tree>")
root = Path(sys.argv[1])
replace(root / "drivers/input/touchscreen/s6sy761.c",
        '\t{ .compatible = "samsung,s6sy761", },',
        '\t{ .compatible = "samsung,s6sy761", },\n'
        '\t{ .compatible = "samsung,s6sy771", },')
replace(root / "drivers/soc/samsung/s9p-acpm.c",
        '\treturn dev->of_node &&\n'
        '\t       of_device_is_compatible(dev->of_node, "samsung,s6sy761");',
        '\treturn dev->of_node &&\n'
        '\t       (of_device_is_compatible(dev->of_node, "samsung,s6sy761") ||\n'
        '\t        of_device_is_compatible(dev->of_node, "samsung,s6sy771"));')
replace(root / "Documentation/devicetree/bindings/input/touchscreen/samsung,s6sy761.yaml",
        '  compatible:\n    const: samsung,s6sy761\n',
        '  compatible:\n    enum:\n      - samsung,s6sy761\n      - samsung,s6sy771\n')
print("crownlte-touch: experimental Y771 binding and rail reprobe prepared")
