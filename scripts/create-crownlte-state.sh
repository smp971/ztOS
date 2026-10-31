#!/bin/bash
# Create a new filesystem FILE on the build machine. Never format a phone block.
set -euo pipefail
B=${1:?native build directory required}
IMAGE="$B/crownlte-state.img"
[ ! -e "$IMAGE" ] && [ ! -e "$IMAGE.gz" ] || { echo 'State output already exists; refusing replacement'; exit 1; }
SEED=$(mktemp -d "$B/state-seed.XXXXXX")
mkdir "$SEED/upper" "$SEED/work"
printf 'crownlte-overlay-v1\n' > "$SEED/.ztos-state-version"
mke2fs -q -t ext4 -L ZTOS_CROWN_STATE -m 0 -E lazy_itable_init=0,lazy_journal_init=0 -d "$SEED" "$IMAGE" 4G
rmdir "$SEED/upper" "$SEED/work"
rm "$SEED/.ztos-state-version"
rmdir "$SEED"
e2fsck -fn "$IMAGE"
sha256sum "$IMAGE" > "$B/crownlte-state.sha256"
gzip -1 -c "$IMAGE" > "$IMAGE.gz"
sha256sum "$IMAGE.gz" > "$B/crownlte-state-gzip.sha256"
echo CROWN_STATE_IMAGE_READY
