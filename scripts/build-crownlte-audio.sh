#!/bin/bash
# Build live sound modules without changing the running kernel or its output.
set -euo pipefail
B=${1:?native build directory required}
STOCK=${2:?stock DTB required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
K="$B/linux-7.1"
O="$K/out-crown-audio"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
mkdir -p "$O"
cp "$K/out/.config" "$O/.config"
"$K/scripts/config" --file "$O/.config" -m SOUND -m SND -e SND_DRIVERS -m SND_DUMMY -m SND_PCM -d SND_SOC -d SND_USB -d SND_HRTIMER -d SND_OSSEMUL -d SND_SEQUENCER -d SND_PCI -d SND_HDA -d SND_SPI -d SND_ARM -d SND_VIRTIO
make -s -C "$K" O="$O" olddefconfig
python3 - "$K/out/.config" "$O/.config" <<'PY'
import sys
def config(p):
    return dict(line.strip().split('=', 1) for line in open(p) if line.startswith('CONFIG_'))
old, new = map(config, sys.argv[1:])
changed = [(k, old.get(k), new.get(k)) for k in old.keys() | new.keys() if old.get(k) != new.get(k)]
for k, before, after in changed:
    if not (k.startswith('CONFIG_SND') or k in ('CONFIG_SOUND', 'CONFIG_AC97_BUS')):
        raise SystemExit(f'Unexpected configuration change: {k}: {before} -> {after}')
print('Only modular ALSA configuration added:', len(changed), 'symbols')
PY
make -s -j4 -C "$K" O="$O" modules_prepare
# In-tree single-module modpost reads vmlinux.o, not KBUILD_EXTRA_SYMBOLS.
# The built-in objects are exactly those of the running kernel.
ln -sfn "$K/out/vmlinux.o" "$O/vmlinux.o"
make -s -j4 -C "$K" O="$O" KBUILD_EXTRA_SYMBOLS="$K/out/vmlinux.symvers" sound/soundcore.ko sound/core/snd.ko sound/core/snd-timer.ko sound/core/snd-pcm.ko
BUILD=$(mktemp -d "$B/crown-audio-build.XXXXXX")
MODULE="$BUILD/source"
python3 "$REPO/scripts/prepare-crownlte-audio.py" --stock-dtb "$STOCK" --output "$MODULE"
make -s -j4 -C "$K" O="$O" M="$MODULE" modules
mkdir -p "$B/crown-audio-modules"
cp "$O/sound/soundcore.ko" "$O"/sound/core/snd{,-timer,-pcm}.ko "$MODULE/snd-crown-abox.ko" "$B/crown-audio-modules/"
echo CROWN_AUDIO_MODULES_READY
