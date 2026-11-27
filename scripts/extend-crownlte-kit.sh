#!/bin/bash
# Extend the already verified radios kit with validated live media audio and
# modem startup. This only writes host build outputs, never phone partitions.
set -euo pipefail
B=${1:?native build directory required}
FW=${2:?private Crown audio firmware directory required}
REPO=$(cd "$(dirname "$0")/.." && pwd)
KIT="$B/connectivity-kit"
[ "$(cat "$KIT/usr/local/lib/crownlte/kit-version")" = crownlte-radios-v1 ]
python3 - "$FW" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
expected = {
 'calliope_sram.bin': 'b24bf5fa2385dfddc34da0f301151db3ecea44285cd5300b8f4391e883be2bce',
 'calliope_dram.bin': '2c26b1c4d40a6d7dc485aa98342424a504697adcdfdc714e48fc1ed31cf50bdb',
 'calliope_iva.bin': '238fac89ea42c3bf2da78200d0c795f3b9d70c6ef9794e48096839faf5f22428',
}
for name, digest in expected.items():
    if hashlib.sha256((p / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Crown firmware mismatch: {name}')
PY
gpg --homedir "$B/rootfs-inputs/gnupg" --status-fd 1 --verify \
 "$B/audio-packages/lsp-plugins-ladspa-1.2.35-1-aarch64.pkg.tar.xz.sig" \
 "$B/audio-packages/lsp-plugins-ladspa-1.2.35-1-aarch64.pkg.tar.xz" 2>/dev/null | \
 grep -q 'VALIDSIG 68B3537F39A313B3E574D06777193F152BDBE6A6'
mkdir -p "$KIT/usr/local/lib/crownlte/audio" "$KIT/usr/lib/ladspa"
install -m644 "$B/crown-audio-modules/"*.ko "$KIT/usr/local/lib/crownlte/audio/"
install -m644 "$FW/"calliope*.bin "$KIT/usr/lib/firmware/"
install -m644 "$B/audio-userspace/usr/lib/ladspa/lsp-plugins-ladspa.so" "$KIT/usr/lib/ladspa/"
cp -a "$REPO/devices/samsung-crownlte/overlay/etc/." "$KIT/etc/"
mkdir -p "$KIT/usr/local/share/applications" "$KIT/usr/local/bin"
cp -a "$REPO/devices/samsung-crownlte/overlay/usr/local/share/applications/." "$KIT/usr/local/share/applications/"
install -m644 "$REPO/ztmetro/settings/ztsettings.desktop" "$REPO/ztmetro/devtest/zrndevtest.desktop" "$KIT/usr/local/share/applications/"
install -m755 "$REPO/devices/samsung-crownlte/tools/crown-media.py" "$KIT/usr/local/bin/crown-media"
# Preserve the installed ARM64 browser; the Crown launcher only changes its
# buffer-layout environment. Never replace this payload with a host executable.
(cd "$B/crown-browser" && sha256sum -c superscan.bin.sha256)
python3 - "$B/crown-browser/superscan.bin" <<'PY'
import pathlib, sys
header = pathlib.Path(sys.argv[1]).read_bytes()[:20]
if header[:4] != b'\x7fELF' or header[18:20] != b'\xb7\x00':
    raise SystemExit('Crown browser payload is not an ARM64 ELF')
PY
mkdir -p "$KIT/usr/local/lib/crownlte/browser"
install -m755 "$B/crown-browser/superscan.bin" "$KIT/usr/local/lib/crownlte/browser/"
install -m755 "$REPO/devices/samsung-crownlte/tools/crown-superscan" "$KIT/usr/local/bin/superscan"
for name in crown-audio crown-modem-prepare crown-modem-boot crown-modem-check crown-sensorhub crown-sensord crown-haptic; do
    install -m755 "$REPO/devices/samsung-crownlte/tools/$name" "$KIT/usr/local/sbin/$name"
done
install -m755 "$REPO/devices/samsung-crownlte/tools/crown-diagnose.py" "$KIT/usr/local/sbin/crown-diagnose"
mkdir -p "$KIT/vendor/ztos/ial"
install -m644 "$REPO/devices/samsung-crownlte/vendor/ztos/manifest.toml" "$KIT/vendor/ztos/manifest.toml"
install -m644 "$REPO/devices/samsung-crownlte/vendor/ztos/ial/crownlte.py" "$KIT/vendor/ztos/ial/crownlte.py"

# Only the Crown-patched hub module is accepted: never ship the STAR default.
PERIPHERALS="$B/crown-peripherals-v2/sensorhub"
grep -q 'crown_patch.inc' "$PERIPHERALS/bbd.c"
mkdir -p "$KIT/usr/local/lib/crownlte/peripherals"
install -m644 "$PERIPHERALS/zrn-bbd.ko" "$KIT/usr/local/lib/crownlte/peripherals/"
install -m644 "$B/crown-peripherals/haptic/crown-haptic.ko" "$KIT/usr/local/lib/crownlte/peripherals/"
install -m644 "$B/crown-peripherals-userspace/libhardware_legacy.so" "$KIT/usr/local/lib/crownlte/peripherals/"
install -m755 "$B/crown-peripherals-userspace/ztoscsf-sensord" "$KIT/usr/local/sbin/"
cat > "$KIT/etc/systemd/system/crown-audio.service" <<'UNIT'
[Unit]
Description=Crown media audio with MAX98512 revision detection
Before=greetd.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/crown-audio
RemainAfterExit=yes
TimeoutStartSec=30
[Install]
WantedBy=multi-user.target
UNIT
cat > "$KIT/etc/systemd/system/crown-modem-prepare.service" <<'UNIT'
[Unit]
Description=Crown modem runtime and RAM calibration copy
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/crown-modem-prepare
RemainAfterExit=yes
TimeoutStartSec=60
UNIT
cat > "$KIT/etc/systemd/system/crown-modem-boot.service" <<'UNIT'
[Unit]
Description=Crown CP secure firmware boot
Requires=crown-modem-prepare.service
After=crown-modem-prepare.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/crown-modem-boot
RemainAfterExit=yes
TimeoutStartSec=50
UNIT
cat > "$KIT/etc/systemd/system/crown-network.service" <<'UNIT'
[Unit]
Description=Crown modem networking daemon
Requires=crown-modem-boot.service
After=crown-modem-boot.service
[Service]
ExecStart=/usr/local/sbin/ztoscorenetworkingd
ExecStartPost=/usr/local/sbin/crown-network-select
Restart=no
[Install]
WantedBy=multi-user.target
UNIT
cat > "$KIT/usr/local/sbin/crown-network-select" <<'SH'
#!/bin/sh
set -eu
exec python3 - <<'PY'
import errno, os, time
from pathlib import Path
for tick in range(30):
    try:
        status = Path('/run/ztoscorenetworking/status').read_text()
        if 'sim=ready\n' not in status:
            time.sleep(1)
            continue
        fd = os.open('/run/ztoscorenetworking.ctl', os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b'at AT+COPS=0\n')
        finally:
            os.close(fd)
        break
    except OSError as e:
        if e.errno not in (errno.ENOENT, errno.ENXIO):
            raise
        time.sleep(1)
else:
    raise SystemExit('Modem control channel or SIM not ready')
PY
SH
chmod 755 "$KIT/usr/local/sbin/crown-network-select"
for name in crown-audio crown-network crown-modem-check crown-sensorhub crown-sensord crown-haptic; do
    ln -sfn "/etc/systemd/system/$name.service" "$KIT/etc/systemd/system/multi-user.target.wants/$name.service"
done
# DrvFS source checkouts may report 0777. Configuration must not inherit that.
find "$KIT/etc" -type d -exec chmod 755 {} +
find "$KIT/etc" -type f -exec chmod 644 {} +
find "$KIT/usr/local/share/applications" -type f -exec chmod 644 {} +
find "$KIT/usr/local/share/applications" -type d -exec chmod 755 {} +
tar --owner=0 --group=0 --numeric-owner -czf "$B/crownlte-connectivity-kit-next.tar.gz" -C "$KIT" .
(cd "$B" && sha256sum crownlte-connectivity-kit-next.tar.gz > crownlte-connectivity-kit-next.sha256)
echo CROWN_EXTENDED_KIT_READY
