#!/bin/bash
# Native ARM64 build using the prepared, exact running-kernel configuration.
set -euo pipefail
B=${1:?native build directory required}
STOCK=${2:?stock Crown DTB required}
FW=${3:?private Crown camera1 SCORE firmware directory required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
K="$B/linux-7.1"
MODULE="$B/crown-score"
python3 "$REPO/scripts/prepare-crownlte-score.py" --stock-dtb "$STOCK" --output "$MODULE"
args=(ARCH=arm64)
if [ -n "${CROSS_COMPILE:-}" ]; then args+=("CROSS_COMPILE=$CROSS_COMPILE"); fi
make -C "$K" O=out "${args[@]}" M="$MODULE" \
    KBUILD_EXTRA_SYMBOLS="$K/out/vmlinux.symvers" -j2 modules
"${CROSS_COMPILE:-}gcc" -O2 "$REPO/score/tools/scoremm.c" -o "$MODULE/scoremm"
python3 - "$K/out/.config" "$MODULE" "$FW" <<'PY'
import hashlib
from pathlib import Path
import sys
config, output, firmware = map(Path, sys.argv[1:])
lines = sorted(line for line in config.read_text().splitlines() if line.startswith('CONFIG_'))
(output / 'kernel-config.sha256').write_text(hashlib.sha256(('\n'.join(lines) + '\n').encode()).hexdigest() + '\n')
expected = {
    'score_mc_pmw.bin': 'd01323063d6c5e229c92eab302df421001acfa68461c447c5c748e1c40d2ebe6',
    'score_mc_dmb.bin': 'a9eb295ae0c799e01af904334752479b8e3dfbcca5db2d29fef8aa62db27f027',
    'score_kc1_pmw.bin': '998151a00fab5f6c671e2c928f5d0a20b12f0f2bcb8c7c9cb982b180177f70c4',
    'score_kc1_dmb.bin': '3e87ee4b4b1b0e537ff7e79ca95c6e8729b593627d6a5055f9ba518de1695432',
}
for name, digest in expected.items():
    if hashlib.sha256((firmware / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Untested Crown SCORE firmware: ' + name)
(output / 'firmware.sha256').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(expected.items())))
PY
echo CROWN_SCORE_BUILT_NOT_YET_HARDWARE_VERIFIED
