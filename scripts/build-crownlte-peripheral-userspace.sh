#!/bin/bash
set -euo pipefail
B=${1:?native build directory required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT="$B/crown-peripherals-userspace"
mkdir -p "$OUT"
aarch64-linux-gnu-gcc -shared -fPIC -nostdlib -fno-stack-protector \
    -Wl,-soname,libhardware_legacy.so \
    -o "$OUT/libhardware_legacy.so" \
    "$REPO/devices/samsung-crownlte/tools/legacy-wakelock.c"
aarch64-linux-gnu-gcc -O2 -Wall -Wextra \
    -o "$OUT/ztoscsf-sensord" "$REPO/ztmetro/sensord/ztoscsf-sensord.c" -lm
