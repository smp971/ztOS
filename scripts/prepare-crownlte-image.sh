#!/bin/bash
# Validate and compress only the locally built prototype image. No phone access.
set -euo pipefail
B=${1:?absolute native build directory required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
IMAGE="$B/rootfs-build/crownlte/root.img"
[ "$(stat -c %s "$IMAGE")" = 10737418240 ] || { echo 'Expected 10 GiB prototype image'; exit 1; }
R=$(mktemp -d "$B/image-check.XXXXXX")
cleanup() { mountpoint -q "$R" && umount "$R"; rmdir "$R"; }
trap cleanup EXIT
mount -o loop,rw "$IMAGE" "$R"
DEVSRC="$REPO/devices/samsung-crownlte"
ch() { chroot "$R" /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/bin HOME=/root LANG=C.UTF-8 "$@"; }
. "$DEVSRC/layer.sh"
# DrvFS checkouts can report 0777 for tracked overlay files and directories.
# Normalize the generated Linux image, preserving sticky temporary directories.
find "$R" -xdev -type d -perm /0022 ! -perm -1000 -exec chmod go-w {} +
find "$R" -xdev -type f -perm /0022 -exec chmod go-w {} +
find "$R/etc/systemd" -type f \( -name '*.service' -o -name '*.timer' -o -name '*.conf' \) -exec chmod a-x {} +
chmod 755 "$R/etc/sudoers.d"
ch visudo -c
ch sudo -l -U zerone
for unit in zrnperfd zrn-sleepd ztoscoresensorframework waydroid-container ztos-waydroid-images; do
    [ "$(readlink "$R/etc/systemd/system/$unit.service")" = /dev/null ]
done
[ -f "$R/usr/local/bin/ztmetro" ]
[ -f "$R/usr/lib/systemd/systemd" ]
grep -q 'codename = "samsung-crownlte"' "$R/vendor/ztos/manifest.toml"
grep -q '^ExecStartPost=$' "$R/etc/systemd/system/zboot-usb-gadget.service.d/90-crownlte-test.conf"
sync
umount "$R"
e2fsck -fn "$IMAGE"
sha256sum "$IMAGE" > "$B/crownlte-root.sha256"
gzip -1 -c "$IMAGE" > "$B/crownlte-root.img.gz"
sha256sum "$B/crownlte-root.img.gz" > "$B/crownlte-root-gzip.sha256"
echo 'CROWN_ROOT_IMAGE_VERIFIED'
