# SPDX-License-Identifier: GPL-2.0-only
# Read-only, loop-root prototype. Run inside the installer mount namespace.
install -d "$R/vendor/ztos"
cp -a "$DEVSRC/vendor/ztos/." "$R/vendor/ztos/"
printf '# Root is prepared by the Crown initramfs; Android USERDATA stays read-only.\n' > "$R/etc/fstab"
install -d "$R/etc/ztos"
cat > "$R/etc/ztos/session.env" <<'ENV'
export WLR_RENDERER_ALLOW_SOFTWARE=1
export WLR_NO_HARDWARE_CURSORS=1
export WLR_RENDERER=gles2
export GBM_ALWAYS_SOFTWARE=1
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=kms_swrast
ENV
install -d "$R/etc/systemd/sleep.conf.d" "$R/etc/systemd/logind.conf.d"
cat > "$R/etc/systemd/sleep.conf.d/90-crownlte.conf" <<'SLEEP'
[Sleep]
AllowSuspend=no
AllowHibernation=no
AllowHybridSleep=no
AllowSuspendThenHibernate=no
SLEEP
cat > "$R/etc/systemd/logind.conf.d/90-crownlte.conf" <<'LOGIND'
[Login]
HandlePowerKey=ignore
HandleSuspendKey=ignore
IdleAction=ignore
LOGIND
install -d "$R/etc/systemd/system/zboot-usb-gadget.service.d"
cat > "$R/etc/systemd/system/zboot-usb-gadget.service.d/90-crownlte-test.conf" <<'UNIT'
[Service]
# Keep the bounded test armed until the host confirms this userspace is healthy.
ExecStartPost=
UNIT
sed -i 's/Galaxy S9 Arch Linux ARM/Galaxy Note9 ztOS prototype/; s/"starlte"/"crownlte"/' "$R/usr/local/sbin/zboot-usb-gadget"
for unit in ztoscoresensorframework ztos-update-check.timer zrnperfd zrn-sleepd \
        waydroid-container ztos-waydroid-images systemd-suspend.service \
        systemd-hibernate.service systemd-hybrid-sleep.service systemd-suspend-then-hibernate.service \
        systemd-fsck-root.service ztos-fs-recovery-reset.service ztos-fs-recovery-rollback.service; do
    case "$unit" in *.*) ;; *) unit="$unit.service" ;; esac
    # Some upstream units are installed directly in /etc, where systemctl mask
    # refuses to replace an existing regular file. This is a new image tree.
    ln -sfn /dev/null "$R/etc/systemd/system/$unit"
done
# Generic recovery assumes a writable partition root and a Samsung CACHE block.
# This prototype has a RAM overlay; preserve logs and let the boot deadline fire.
for unit in emergency rescue; do
    install -d "$R/etc/systemd/system/$unit.service.d"
    cat > "$R/etc/systemd/system/$unit.service.d/90-crownlte-test.conf" <<'RECOVERY'
[Service]
ExecStart=
ExecStart=/usr/bin/sleep infinity
RECOVERY
done
ch passwd -l root >/dev/null
DEVICE_UNITS="zboot-usb-gadget systemd-networkd serial-getty@ttyGS0"
