#!/bin/sh
# Run inside the storage rescue shell. Read-only diagnostics, no format/repair.
set -eu
grep -qx PARTNAME=USERDATA /sys/class/block/sda25/uevent
[ "$(blockdev --getro /dev/sda)" = 1 ]
[ "$(blockdev --getro /dev/sda25)" = 1 ]
MNT=/mnt/crownlte-android-ro
mkdir -p "$MNT"
mount -t f2fs -o ro,norecovery /dev/sda25 "$MNT"
trap 'umount "$MNT"' EXIT HUP INT TERM
grep " $MNT " /proc/mounts
ls -ld "$MNT/unencrypted"
if command -v lsattr >/dev/null 2>&1; then
    lsattr -d "$MNT/unencrypted"
fi
df -h "$MNT"
echo CROWNLTE_F2FS_READONLY_OK
