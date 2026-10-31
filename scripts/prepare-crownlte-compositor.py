#!/usr/bin/env python3
"""Prepare an isolated compositor copy for Crown graphics A/B measurements."""
import argparse
import shutil
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
root = Path(__file__).resolve().parents[1]
if a.output.exists():
    raise SystemExit('Output exists')
a.output.mkdir(parents=True)
for name in ('ztmetro.c', 'background-apps.h', 'ztos-user.h', 'demoloop/stop-key.h', 'auth/prompt.c'):
    p = a.output / name
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'ztmetro' / name, p)
p = a.output / 'ztmetro.c'
s = p.read_text(encoding='utf-8')
anchor = '\tsetenv("PAN_MESA_DEBUG", "noafbc,linear", true);'
if s.count(anchor) != 1:
    raise SystemExit('Compositor initialization changed')
s = s.replace(anchor, '''\t/* Crown-only build: permit a measured texture-layout comparison. */
\tconst char *crown_pan_debug = getenv("ZTMETRO_PAN_DEBUG");
\tsetenv("PAN_MESA_DEBUG", crown_pan_debug ? crown_pan_debug : "noafbc,linear", true);''')
p.write_bytes(s.encode('utf-8'))
(a.output / 'build.sh').write_bytes(b'''#!/bin/sh
set -eu
cd /home/zerone/crown-compositor
PKGS="wlroots-0.20 wayland-server xkbcommon cairo pangocairo librsvg-2.0 gdk-pixbuf-2.0 pixman-1 libdrm egl glesv2"
gcc -O2 -std=c11 -Wall -Wno-unused-parameter -DWLR_USE_UNSTABLE -DHAVE_ZTOS_IAL -I. $(pkg-config --cflags $PKGS ztos-ial) -o ztmetro-crown ztmetro.c $(pkg-config --libs $PKGS) $(pkg-config --libs --static ztos-ial) -lm -lpthread
''')
print('Isolated Crown compositor source prepared')
