#!/bin/bash
# Build a userspace/RAM test kit only. Never access a phone or its partitions.
set -euo pipefail
B=${1:?native build directory required}
FIRMWARE=${2:?private vendor firmware directory required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
KERNEL="$B/linux-7.1/out"
KIT="$B/connectivity-kit"
[ ! -e "$KIT" ] || { echo 'Kit output already exists'; exit 1; }
python3 "$REPO/scripts/verify-crownlte-firmware.py" "$FIRMWARE"
make -C "$KERNEL" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules_prepare
for MODULE in crown-bt crown-modem-revcc; do
    make -C "$KERNEL" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
        M="$B/$MODULE" KBUILD_EXTRA_SYMBOLS="$KERNEL/vmlinux.symvers" -j8 modules
done
mkdir -p "$KIT/usr/local/lib/crownlte" "$KIT/usr/lib/firmware/brcm" "$KIT/usr/local/sbin"
for PACKAGE in "$B/bluez-packages/"*.pkg.tar.xz; do
    STATUS=$(gpg --homedir "$B/rootfs-inputs/gnupg" --status-fd 1 \
        --verify "$PACKAGE.sig" "$PACKAGE" 2>/dev/null)
    grep -q 'VALIDSIG 68B3537F39A313B3E574D06777193F152BDBE6A6' <<< "$STATUS"
    tar --exclude='./.*' --exclude='.[A-Z]*' --exclude='etc/bluetooth/main.conf' -xJf "$PACKAGE" -C "$KIT"
done
install -m644 "$B/crown-bt/crown-bt.ko" "$B/crown-modem-revcc/zrn-modem.ko" "$KIT/usr/local/lib/crownlte/"
install -m644 "$FIRMWARE/bcm4361B2_semco.hcd" "$KIT/usr/lib/firmware/brcm/BCM.samsung,crownlte.hcd"
install -m644 "$FIRMWARE/bcm4361B2_semco.hcd" "$KIT/usr/lib/firmware/brcm/BCM4361B2.hcd"
install -m755 "$REPO/scripts/probe-crownlte-modem.py" "$KIT/usr/local/sbin/"
install -m755 "$REPO/devices/samsung-crownlte/tools/crown-bluetooth" \
    "$REPO/devices/samsung-crownlte/tools/crown-bluetooth-ready" "$KIT/usr/local/sbin/"
mkdir -p "$KIT/etc/systemd/system/bluetooth.service.d" "$KIT/etc/systemd/system/multi-user.target.wants"
cat > "$KIT/etc/systemd/system/crown-bluetooth.service" <<'UNIT'
[Unit]
Description=Crown Bluetooth board and UART transport
[Service]
ExecStart=/usr/local/sbin/crown-bluetooth
UNIT
cat > "$KIT/etc/systemd/system/crown-bluetooth-ready.service" <<'UNIT'
[Unit]
Description=Crown Bluetooth firmware and board address
Requires=crown-bluetooth.service
After=crown-bluetooth.service
Before=bluetooth.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/crown-bluetooth-ready
RemainAfterExit=yes
TimeoutStartSec=120
UNIT
cat > "$KIT/etc/systemd/system/bluetooth.service.d/90-crownlte.conf" <<'UNIT'
[Unit]
Requires=crown-bluetooth-ready.service
After=crown-bluetooth-ready.service
UNIT
ln -s /usr/lib/systemd/system/bluetooth.service "$KIT/etc/systemd/system/multi-user.target.wants/bluetooth.service"
printf 'crownlte-radios-v1\n' > "$KIT/usr/local/lib/crownlte/kit-version"
tar -czf "$B/crownlte-connectivity-kit.tar.gz" -C "$KIT" .
(cd "$B" && sha256sum crownlte-connectivity-kit.tar.gz > crownlte-connectivity-kit.sha256)
echo CROWN_CONNECTIVITY_KIT_READY
