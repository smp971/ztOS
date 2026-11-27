#!/bin/bash
# Build against the prepared running-kernel tree; no kernel configuration edits.
set -euo pipefail
B=${1:?native build directory required}
STOCK=${2:?stock Crown DTB required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
K="$B/linux-7.1"
MODULE="$B/crown-lights"
python3 "$REPO/scripts/prepare-crownlte-lights.py" --stock-dtb "$STOCK" --output "$MODULE"
args=(ARCH=arm64)
if [ -n "${CROSS_COMPILE:-}" ]; then args+=("CROSS_COMPILE=$CROSS_COMPILE"); fi
make -C "$K" O=out "${args[@]}" \
    M="$MODULE" KBUILD_EXTRA_SYMBOLS="$K/out/vmlinux.symvers" -j2 modules
echo CROWN_LIGHT_MODULES_BUILT
# Only the physically validated RGB module is installed automatically.
