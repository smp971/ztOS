# Galaxy Note9 SM-N960F: initial mainline bring-up

Status: **ztOS graphical prototype boots, displays its interface and accepts
touch input; phone hardware integration is incomplete**.
For the current tested feature status, see [BRINGUP.md](BRINGUP.md). Later
stages add Panfrost graphics, Wi-Fi, audio/microphone, sensors, haptics and
persistent state; the read-only and software-rendering descriptions below
document the earlier bring-up stages. This is source for an experimental port,
not a ready-to-flash release or a tested general-purpose installer.
The first port was based on ztOS commit `d049080cc2d8e04e8bd4fb40f18f0be19160de61`
and its pinned S9+ submodule. The 0.2.3 integration branch uses upstream
`2360ba9ba5b34952d18faa33002f32bee018bebc`; its shell and native apps were
tested live on Note9 on 2026-11-27, with the existing kernel/base image.
The updated interface, touch, persistent state and automatic SIM/home/4G
registration survived a controlled shutdown and user restart. The sensor hub
now supplies live samples after a recovery-to-system restart, but independent
cold-start reliability remains unresolved. RGB notification light is physically
confirmed and SCORE passed integer/fractional arithmetic tests at its existing
boot clock. Eleven OSIAL interfaces answer; the latest feature kit still needs
post-reboot acceptance. The optional sensor readiness wait does not hold up
graphical startup. Call audio, Android/Binder,
cameras, S Pen, GNSS and suspend still need hardware work or validation.
No S9 prebuilt image is suitable for this device. Crown requires its staged
build scripts and private hardware inputs, rather than a stock S9 install.

## Hardware read from the connected phone

- SM-N960F, `crownlte`, Exynos 9810, 6 GB RAM, 128 GB storage.
- Bootloader `N960FXXU9FVH1`, board revision 28 (DTBH range starts at 26).
- Initially running LineageOS `24.0-20260913-UNOFFICIAL-crownlte`, Android 17,
  kernel `4.9.337-ies-20139-gf7f24703e9ea`.
- Existing recovery: Lineage Recovery from the same build.
- Panel `SDC_910047`, `s6e3ha8_crown_a3_s0`, 1440 x 2960.
- Touch firmware `LSI_y771`, `tsp_sec/y771_crown*.fw`, I2C address 0x48,
  controller at 0x104b0000, 4096 x 4096 coordinates.
- Firmware RAM reservations match the S9+ base except RKP: Crown reserves
  `0xaf600000..0xb1a00000` (36 MiB), rather than `0xaf800000..0xb1000000`.
- Boot framebuffer address `0xcc000000`. All five RAM banks match the S9+.
- Modem daemon `/vendor/bin/cbd`, sensor-hub daemon `/vendor/bin/hw/lhd`.
  Their presence does not establish compatibility with ztOS's Android shim.

The Samsung SEC touchscreen driver in LineageOS's universal9810 tree at
`5a2dd7d6f3a05168d2f1303c3b29e9e9fa39b781` uses the same basic 8-byte coordinate
event format and 0x60/0x61 event-read commands as mainline's S6SY761 driver.
The live Crown DT also confirms LDO35 at 1.8 V and LDO43 at 3.0 V. This is a
shared implementation candidate. Hardware tests below subsequently verified
controller binding, single-finger events and graphical navigation.

Device dumps and identity/calibration backups stay outside this repository,
in the workspace's `device-backups/crownlte` directory.
They contain private device data and must not be published.

Read-only storage inspection in Lineage Recovery confirmed an F2FS USERDATA
partition and an accessible `/unencrypted` directory without the encrypted-inode
flag. The system stage now boots a loop-mounted ext4 image there, preserving
LineageOS and user files. Android F2FS and the image stay read-only under Linux;
an overlay in RAM holds the prototype session's changes.

## First hardware test, 2026-10-29

The USB-stage image with SHA-256
`0319e3b0264e8826ab84043417bd97afe729e6b832fab5a71dfc9553f002fa68`
was written to BOOT with readback verification. It booted Linux
`7.1.0-ztos-crownlte-rescue` and reached the initramfs:

- All eight CPUs online (`0-7`), 5513 MiB reported available to the system.
- USB CDC-ACM serial shell and CDC-NCM network both operational on Windows.
- Telnet commands worked at 172.16.42.1; host received 172.16.42.2 by DHCP.
- DRM boot framebuffer registered as `exynosdrmfb`, 1440 x 2960. The person
  at the phone confirmed Linux text was visible during both hardware tests.
- No UFS block devices were exposed in this stage, as intended.
- The 120-second deadline returned the phone to Lineage Recovery.
- Recovery ADB needed enabling again after that reboot. The complete original
  BOOT backup was then restored and verified against SHA-256
  `0248031a15bd46003e50a584b297318336f1041b8958c3bb5b76cc19fc88556b`.
  No USERDATA or RECOVERY partition was written. Android subsequently reported
  `sys.boot_completed=1`, the original LineageOS version and its 4.9.337 kernel.

Nonfatal log messages include an exynos-clkout probe returning -22 and
"Initramfs unpacking failed: junk at the end of compressed archive". The latter
occurs with the inherited 20-byte empty external gzip ramdisk; the built-in
initramfs booted successfully. These remain to be cleaned up separately.

## First image

This stage leaves UFS, charging, touch, GPU, DECON and WLAN disabled. It uses
the bootloader framebuffer and the shared USB PHY/gadget support. It does not
mount, format or write Android filesystems. The existing recovery is retained.
uniLoader and the kernel arm Samsung's recovery reboot reason and watchdog.
The initramfs stays in USB rescue, with a 120-second deadline that is not
cancelled merely by entering the rescue shell. The deadline was verified on
this device in test 1; hardware button recovery remains needed
if the early watchdog does not execute.

Linux host prerequisites: standard kernel build tools, an aarch64 GCC cross
compiler, Python 3, device-tree compiler, cpio, gzip. Use a native Linux
filesystem for the kernel tree under WSL, rather than DrvFs.

Prepare `ZTOS_BUILD_DIR/linux-7.1` from the verified upstream tarball and
`ZTOS_BUILD_DIR/busybox-arm64` using
`third_party/s9plus/scripts/build/fetch_busybox.py`. Initialise submodules.
`ZTOS_BOOT_REFERENCE` must point to this Note9's verified RECOVERY backup.

```sh
CROSS_COMPILE=aarch64-linux-gnu- \
ZTOS_BUILD_DIR=/root/ztos-crownlte-build \
ZTOS_BOOT_REFERENCE=/absolute/path/to/crownlte/RECOVERY.img \
ZTOS_JOBS=4 \
bash scripts/build-boot.sh crownlte-rescue \
  --device crownlte --no-ufs --fallback recovery

python3 scripts/verify-crownlte.py \
  --stock-dtb /absolute/path/to/crownlte/running.dtb \
  --dtb /root/ztos-crownlte-build/linux-7.1/out/arch/arm64/boot/dts/exynos/exynos9810-crownlte-zt.dtb \
  --reference /absolute/path/to/crownlte/RECOVERY.img \
  --image out/crownlte-rescue.img
```

Verification checks the real RAM map, firmware reservations, recovery fallback,
disabled unvalidated hardware, boot-image ID, Samsung DTBH, embedded target DTB,
rescue command line and BOOT partition size. It does not prove bootability.

On the Windows host, `scripts/crownlte-boot-test.ps1` defaults to `-Mode Inspect`.
It requires the ADB executable and backup directory, and performs no write in
that mode. `-Mode BootTest` explicitly writes only BOOT and reboots; `-Mode Restore`
writes the original full BOOT backup and stays in recovery. Both write modes
verify the uploaded payload and partition readback. Recovery ADB must be enabled
in the phone's menu first. No USERDATA or RECOVERY write is implemented.

## Storage probe image

After the original BOOT has been restored, the next bounded rescue test can be
built with `--device crownlte --crown-stage storage --fallback recovery` (omit
`--no-ufs`). This enables UFS, F2FS and loop devices, while leaving touch, GPU,
DECON, charging and WLAN disabled. The initramfs sets detected UFS disks
read-only before starting the rescue shell and does not mount a filesystem.
Use `--stage storage` for the verifier and `-StorageTest` for the PowerShell
inspection/test command. A successful compile is not a successful storage test.

Hardware test 2 used image SHA-256
`ff323ba98fc8332769b4371d0b05e5dda064a0011ee2238d7dd60eeb06e90cab`.
UFS detected the Samsung KLUDG4U1EA device, all five LUNs and the expected
partition map. `/dev/sda25` reported `PARTNAME=USERDATA`. Both the whole disk
and USERDATA reported read-only state 1, and all other UFS disks were also
protected. A read-only, no-recovery F2FS mount was refused because the filesystem
has the casefold feature and the first storage build lacked `CONFIG_UNICODE`.
The build now enables Unicode and fscrypt support; test 3 below validates the
corrected image. No filesystem was mounted or written in test 2.
The deadline again returned the phone to recovery. The complete original BOOT
was restored with a matching readback hash, and recovery pstore was saved.
The driver also logged an invalid alternate GPT and
used the primary GPT; no partition-table repair was attempted.

Hardware test 3 used the corrected storage image with SHA-256
`ceec1bc53d799e14413de174c1714b58951c4a4ed5666675caa01ee1c0ab2cfd`.
F2FS mounted successfully with `ro,norecovery`, and `/unencrypted` was readable.
The filesystem reported 112.2 GiB total and 110.8 GiB available. The check then
unmounted it. The read-only storage path is therefore tested on mainline; a
loop-backed ztOS root filesystem remains to be built and tested.

## Experimental touch stage

`--device crownlte --crown-stage touch --touch --fallback recovery` additionally
enables the Y771 node and ACPM rail handling. `kernel/patch-crownlte-touch.py`
adds the experimental `samsung,s6sy771` match to the shared touchscreen driver,
the DT binding and the ACPM reprobe logic. The original S6SY761 match is retained.
The helper is checked for idempotence and source drift. Storage remains protected
read-only and the same 120-second deadline applies. Use `--stage touch` or
PowerShell `-TouchTest` when verifying. Hardware results follow below.

Hardware test 4 used SHA-256
`339b6f75cb05e0600193497170ab9adc94b2d77cf6774abf9323e221cfcfe417`.
The controller bound after one LDO power cycle. A 45-second evdev recording of
the person's taps and swipes contained 2913 events, 15 contacts and 15 releases,
657 X samples (441..3414), 641 Y samples (1497..3265), and 694 synchronization
frames. Single-finger tapping and swiping are tested; simultaneous multi-touch,
edge accuracy, S Pen and suspend/resume remain untested. BOOT was restored with
matching readback and the phone was rebooted to LineageOS.

## System prototype

`scripts/build-crownlte-root.py --build-root /root/ztos-crownlte-build` builds a
separate ext4 image from an Arch Linux ARM rootfs whose detached signature must
match the pinned build key. Credentials are generated into a private file outside
the repository. The Crown layer uses software rendering and disables unvalidated
power management, modem, audio, sensors, Android integration and update services.

`--device crownlte --crown-stage system --touch --fallback recovery` builds the
matching bounded boot test. It requires an image at
`/unencrypted/ztos/crownlte-root.img` inside Android USERDATA. Initramfs protects
UFS read-only, mounts F2FS with `ro,norecovery`, attaches the image read-only and
mounts ext4 with `ro,noload`. A RAM overlay holds all session changes. This stage
must never use the generic installer instruction to overwrite USERDATA.
Use verifier `--stage system` and PowerShell `-SystemTest` for this stage.
The 10 GiB image has been built and passed an offline `e2fsck -fn` check.
Hardware test 5 booted systemd and USB SSH from the image. `findmnt` confirmed
that `/` was a writable RAM overlay and Android USERDATA remained F2FS
`ro,norecovery`. The compositor found the DRM output at 1440x2960 and the Y771
input device, but EGL initialization failed and its Pixman fallback hit a GLES2
assertion. The display interface is therefore not yet working. The phone returned
to recovery automatically; original BOOT was restored and Lineage boot completed.

Test 5 boot image SHA-256:
`6f79dfe498658a048d444b7bee6d3a6dfdb69b47bbb2ba6cf3af256f11c0bbc1`.
Root image SHA-256:
`63d85be63713260f9b7a696b266013a499ade4d87c346c7903bc0d73af8a339b`.
The corrected root image forces GBM software mode as well as llvmpipe, explicitly
requests GLES2, and normalizes DrvFS overlay permissions (test 5's world-writable
sudoers directory prevented administrative diagnostics).

Hardware test 6 used the same verified boot image and root image SHA-256
`80279518950db35fb5d10e8e66967f2db6ccc35e7dcc946b97056c3f3e6f1817`.
EGL 1.5 and OpenGL ES 3.2 initialized with llvmpipe (Mesa 26.2.6). ztMETRO
started Wayland with six tiles at 1440x2960, and systemd reported no failed
units. The person at the phone confirmed that the interface appeared and
responded to touch. Logs recorded Start/Back navigation and opening Settings.
This is a software-rendered prototype: input lag warnings (26–82 ms), touch
runtime-PM underflow warnings, missing optional wallpapers and the absence of a
backlight control remain. GPU acceleration, modem/calls, Wi-Fi, audio, charging,
sensors, cameras, S Pen and suspend are not validated.

### Default test boot (explicitly requested after test 6)

Add `--crown-persistent` to the system-stage build to set `zboot.deadman=0`
and `zboot.persistent=1`. This disables only the two-minute session deadline;
the panic/watchdog recovery fallback and the read-only Android/base mounts stay
in place. A clean reboot uses the normal Samsung reboot mode. Recovery itself
is retained. Verification requires `--stage system --persistent` and the
PowerShell helper requires `-SystemTest -PersistentTest`.

When replacing an already installed bounded test, pass `-PreviousImage` with
that saved test image. The helper validates it and checks that the complete
current BOOT partition equals that image plus the unchanged original partition
tail. An unrelated current BOOT is refused. The normal Restore operation still
restores the original Lineage BOOT when explicitly requested.

This is a default **test** system, not a completed phone integration. The RAM
overlay is discarded on reboot, so session settings and newly installed apps
do not persist. No Android partition is formatted or replaced.

The default-test BOOT installed after test 6 has SHA-256
`25d20a8db3dc04486329c16a584472ae8a61cc07b3d24f109cd1a0b11222bd11`.
Its partition readback matched, it booted Linux build #8, and ztMETRO initialized
with llvmpipe/OpenGL again. Original Lineage BOOT remains in the private backups;
it was deliberately not restored after this user-requested installation.
At uptime 173.78 seconds, `/proc/cmdline` confirmed `zboot.deadman=0` and
`zboot.persistent=1`; greetd and SSH were active, there were no failed systemd
units, and Android F2FS remained `ro,norecovery` beneath the RAM overlay.

`scripts/prepare-crownlte-image.sh /root/ztos-crownlte-build` reapplies the Crown
layer to the new local image, checks service masks and filesystem integrity,
then records hashes and compresses it. It never accesses a phone.
`scripts/copy-crownlte-root.py` requires the ADB path, explicit serial and local
build directory; it requires booted root Android ADB, refuses existing target
files, and compares hashes after transfer and decompression. It creates an
ordinary file under `/data/unencrypted/ztos/`, without flashing USERDATA.
The compressed transfer file is retained until testing is complete.
`--replace-sha256` permits replacing only an exact known earlier prototype and
retains that image as `.previous`; it still refuses unrelated existing files.

### GPU and storage follow-up

Hardware tests 8 and 9 brought up Panfrost on the Mali-G72 MC18. The UI
reported hardware OpenGL ES 3.1, and the person at the phone confirmed correct
display and touch. The Crown GPU stage uses a single 260 MHz / 950 mV OPP and
overrides the base image's software-rendering environment in RAM. Test 9 made
this the default test boot, with the session deadline disabled. This does not
make user data persistent.

A separate 4 GiB ext4 state image has been created and copied as an ordinary
file under Android's unencrypted directory. It is not mounted or used by the
current boot. Android F2FS and the base root image remain read-only.

Test 10 added an exit ramfs intended to detach the overlay, loop devices and
host filesystem before reboot. Its first shutdown did not pass: pstore recorded
`departing root remains mounted`, followed by a return to ztOS consistent with
a watchdog reset. The diagnostic retry located a host mount that systemd had
relocated under `/run/shutdown/mounts/`; the original path lookup missed it.
The corrected script finds that mount by its block device. An isolated native
Linux test using a relocated ext4 host, an attached file-backed loop device,
a separate PID namespace and a harmless final-power mock passed. Test 11
installed the corrected image and booted with GPU and greetd active. Its
shutdown still needs hardware verification; persistent writes remain disabled.

Wi-Fi firmware and Crown calibration candidates have been collected privately;
the correct board selection remains to be verified. Telephony and a Lineage
kexec handoff are not validated. The original recovery and Lineage boot backup
are retained.

### Crown modem probe (test 11)

`scripts/prepare-crownlte-modem.py --stock-dtb <private-running.dtb>
--sys-rev <measured-strap-value> --output <new-native-source-directory>` prepares a separate copy of the modem
module sources. It derives the three modem nodes and 21 I/O devices from the
Crown stock DTB, checks mailbox/shared-memory layout, preserves Crown's revision
`028`, replaces vendor interrupt defaults with level-high and removes foreign
GPIO phandles. The resulting module refuses a non-Crown machine and uses the
EUR option region. The generic S9 module sources are not replaced. The required
`--sys-rev` is the GPIO strap value, not `model_info-system_rev`: on this phone,
stock GPIO order is gpg3[3,2,1,0], then gpg1[5,4,3,2], with samples
0,0,1,1,0,0,1,1 giving `0xCC`. These were read with input-only GPIO v2 line
requests. The first test module omitted this override and sent revision zero;
the board strap override is needed before treating registration as validated.

Run its `mkoverlay.sh` with an explicit DTC, prepare the matching kernel with
`make modules_prepare`, then build using `M=<new-native-source-directory>`.
When the kernel was built only as an Image, pass its `vmlinux.symvers` through
`KBUILD_EXTRA_SYMBOLS`; do not suppress unresolved-symbol errors. Test 11 built
and loaded the module against `7.1.0-ztos-crownlte-rescue` with no dependencies.
Mailbox, shared memory and the `umts_*` / `rmnet0` through `rmnet7` interfaces
initialized.

The phone's own `cbd` ran in a temporary Android chroot using read-only SYSTEM
and VENDOR plus the runtime APEX payload. It booted the modem to ONLINE.
Only RAM working copies of EFS/CPEFS were prepared; original UFS devices stayed
read-only. CPEFS is not yet integrated into the chroot. A bounded transient
service stopped cbd after 45 seconds; the modem remained ONLINE.

`scripts/probe-crownlte-modem.py` opens both IPC channels, RFS and the AT router,
then issues only status queries. Hardware replies included `CPIN: READY`,
signal `CSQ: 13,0` and a detected PLMN. LTE/packet registration was still
searching (`CEREG: 0,2`, `CGREG: 0,2`), with no circuit registration. This is
the initial modem/SIM result, before correcting the board strap revision.

The running modem node was then updated through a small Crown-only OF overlay
to use `zrn,sys_rev = <0xCC>`. Only the CP was restarted through cbd; the AP
and graphical session remained running. The kernel confirmed `sys_rev:204`.
The ztOS networking daemon was started in a transient unit, with mobile data
disabled. After automatic operator selection, its status reported
`sim=ready`, `registered=home`, `tech=4G`, `bars=5`, `data=0`, `data_on=0`.
The later check still reported home registration and identified Vodafone RO,
but technology had changed to EDGE (`tech=E`). Stable LTE is not established.
The corrected full module was also rebuilt with the strap override embedded
for future boots, avoiding the extra live overlay. No calls or SMS were sent.
Voice/audio and packet data are not validated, and modem setup is not yet
installed as an automatic boot service. The current driver and chroot are
session-local.

### Radios, battery and media audio (tests 12–13)

The installed `radios` image is SHA-256
`990ce26e5756f2127ba9e4201b08e6379f1413033e4c59ec9120bc3733e0d024`;
the full padded BOOT readback was
`4993e7d01f85cd0b4d7aa35f5ad2b957cd7dbfa9da8834756ff27de44075997f`.
It boots ztOS without a test timer and extracts a checksum-verified connectivity
kit into the RAM overlay. User data persistence is still disabled.

BCM4361 PCIe Wi-Fi initialized with Crown r02b NVRAM and the phone's firmware;
NetworkManager scanning returned 29 results. Association, Internet access and
long-term reliability have not been tested. Bluetooth UART firmware loaded,
the factory address was read from EFS mounted read-only, and BlueZ powered the
controller. A bounded discovery scan saw nearby devices. Pairing and Bluetooth
audio are untested. Bluetooth readiness waits for firmware completion before
issuing management commands, avoiding an early HCI query during download.

MAX170xx fuel-gauge and MAX77705 charger reporting are active. The final check
reported 99%, 31.5 C, good health, and both input and constant-charge limits at
1,000,000 uA. Actual charging current can be lower, especially near full charge.
The charger encoding correction accounts for the CHGIN register's +1 step.
The initial charging service refuses to enable charging outside 0–43 C; this
is an initial check, not a newly implemented continuous thermal controller.
Factory capacity/calibration values were not rewritten.

Media audio was brought up live, without another phone reboot. The ABOX DSP
loaded the phone's three `calliope_*.bin` files and produced ALSA period IRQs.
The first S9-compatible amplifier map produced no audible output. Both Crown
MAX98512 amplifiers instead report revision 0x43 at register 0x0600, requiring
the revision-B map from LineageOS universal9810 commit
`5a2dd7d6f3a05168d2f1303c3b29e9e9fa39b781`. The Crown preparation script adds
per-amplifier revision detection, refuses unknown revisions, and translates
register addresses using that GPL driver. The user confirmed a clear test tone
after the fix. A PipeWire crossover/high-pass/limiter and IRQ buffer settings
were subsequently activated in RAM. Microphone capture, headphones and call
audio remain unvalidated; the live module uses `capture=0 cp_vss=0`.

`scripts/build-crownlte-audio.sh` builds a separate modular ALSA output against
the running kernel's configuration and built-in exports. It never replaces
the flashed kernel and does not suppress unresolved-symbol errors.
`scripts/extend-crownlte-kit.sh` prepares an extended host-side kit containing
the matched modules, verified private firmware, signed ALARM LADSPA package,
audio settings and modem startup units. After the user requested installation,
the extended kit (SHA-256
`04b659a2af1fb15a291f4eda2e40f2994a102643a37126f637205c2783373f86`)
was installed through recovery with the previous kit and manifest backed up.
The phone rebooted into the same radios BOOT image. Audio and modem services
started automatically; the final check reported SIM ready, home registration,
4G and five bars. MPV completed a generated three-second music test through
PipeWire at 48 kHz stereo. The user had previously confirmed both filtered
tones and interface sounds. The installed kit survives reboot; writable
personal data storage is still disabled.

After the radios reboot, the modem required manual live initialization because
its old setup had been in RAM. It returned to ONLINE with SIM ready, home
registration, 4G and five bars. Later checks retained home registration/five
bars but reported EDGE. Packet data remained inactive. The new automatic modem
units reproduce the tested runtime layout with a RAM copy of original EFS;
their complete startup sequence was subsequently verified after installation.
An early operator-selection request returned SIM-busy/unknown errors, but
the modem subsequently registered without manual intervention.

The shutdown helper now tolerates loop devices that systemd has already
autocleared. During the installation recovery transition, pmsg recorded
`CROWN_STORAGE_CLEAN_SHUTDOWN`, confirming this shutdown path completed.
Writable persistent user data still needs its own mount and shutdown testing.

### Writable state and functional networking (test 14)

The installed image is now SHA-256
`7ac0753b2f7bd3be895767a0b4a11160b2646ddb0c7b547ba9f228c6cdcc66cb`,
with full padded BOOT readback
`a1ac6a9a476f3481a3ad61f5fc55e52e47ad625948690b74f0b4eb33aa91e96d`.
The checksum-verified kit installed with it is
`675c74be1a50264be8e8546665e3df50dd037400a0968033d1e2e565190d847a`.
The previous BOOT image and connectivity kits remain available for recovery.

`--crown-state` explicitly adds
`zboot.statefile=/unencrypted/ztos/crownlte-state.img`. Verification and the
recovery boot helper require an explicit `--writable-state` / `-WritableState`
selection. The existing 4 GiB ext4 file was verified against its original
checksum, checked without repair, and seeded with the current user's settings
through recovery. No phone partition was formatted or resized.

The base image remains read-only. Only USERDATA is writable at the partition
level; EFS, BOOT, RECOVERY, RADIO, SYSTEM, VENDOR and the other Android
partitions retain block-layer read-only flags. Linux's whole-disk RO flag must
be cleared to allow a writable child partition, so each child is protected
individually before USERDATA is allowed to write. The modem guards check the
specific original firmware/calibration partitions, including the separate
read-only CPEFS copy, instead of requiring the entire sda disk to be RO.

The overlay's upper/work directories now reside in `/run/ztos-state`, backed
by the ext4 file on Android F2FS. About 3.8 GiB was available after setup.
An isolated shutdown test exercised two loop devices, a writable state
filesystem and relocated host mount, then verified the saved content and a
clean filesystem check. On the phone, a random user file in Music and a
corresponding setting retained their exact SHA-256 after an ordinary reboot.
This establishes basic user-file and settings persistence, not power-loss
reliability or a finished dual-boot selector.

Wi-Fi associated automatically after reboot using the saved profile, and an
HTTPS request explicitly bound to the Wi-Fi interface returned HTTP 200.
Audio, Bluetooth, graphical login and modem services remained active.
Charging retained the 1 A limit. Bluetooth pairing and call audio are still
unvalidated.

The networking startup helper now uses nonblocking FIFO opens and waits for
SIM readiness: its old blocking write could wait indefinitely on a stale FIFO
during a daemon restart. The CP boot helper resets a previously ONLINE CP
before waiting for a new secure boot, avoiding a false successful restart.
This only restarts the modem, not the AP. CPEFS is now exposed at its stock
read-only path in the temporary Android runtime.

LTE instability remains unresolved. Status queries confirmed an actual loss
of EPS registration while GSM/EDGE home registration remained available, with
no observed modem crash in the checked logs. Authenticated APN experiments
did not establish packet data; the original APN preference was restored.
Data-activation tests were bounded and stopped afterward. The incomplete
RFS service and intermittently unanswered IPC data requests need further
investigation; a specific root cause of LTE fallback has not been proven.

### Graphics measurements

The compositor uses Mali-G72 MC18/Panfrost, not software rendering, at
1440x2960. The GPU remains capped at the initial 260 MHz operating point;
the PMIC setting read back as 950 mV. Repeated home/app-list transitions
averaged about 20–23 ms per frame, with about 1–2 ms of drawing, 2–3 ms of
GPU completion and a short asynchronous commit. This suggests the presentation
path needs profiling before increasing GPU clocks.

An isolated compositor build allowed AFBC-layout comparisons without modifying
the shared compositor source. AFBC with repacking disabled, RGB565 selection
and big-core affinity did not improve the measured transitions. The original
compositor and environment were restored; none of these experiments is
installed as a performance improvement. The boot-framebuffer path still
copies the displayed image; native Crown display takeover remains open.

Investigation also found repeated `pm_runtime_put()` calls in the built touch
driver, introduced by a non-idempotent suspend patch on repeated builds.
`kernel/patch-touch-suspend.py` now scopes its open-function replacement and
normalizes input-close to one release. Applying it twice to the actual affected
source produced identical output with exactly one close release. This source
fix is prepared for the next kernel build; the installed test-14 image predates
it, and no further phone reboot was performed for this fix.

## Remaining work

1. Extend persistent-state shutdown, low-space and recovery testing, then validate required phone capabilities
   individually. Keep the tested loop-backed rootfs and dedicated state file while
   preserving Android. Replacing USERDATA requires an explicit choice and a
   separate backup of user files.
2. Fix Y771 runtime-PM usage warnings and extend testing to multi-touch, edges
   and suspend/resume; the stock SEC protocol and single-finger input work.
3. Validate display takeover on the HA8 panel. S9 HA6 brightness/calibration,
   self-mask and sleep sequences must not be sent to the Crown panel.
4. Expand the Crown ztOSIAL layer only after hardware validation. Rebuild any
   required modules against this kernel, rather than loading prebuilt S9 modules.
5. Extend Wi-Fi association, Bluetooth pairing, charging and media-audio tests;
   extend reliability testing of the installed automatic audio/modem kit. Validate call
   audio, packet data and sensor hub separately.
   S Pen, cameras and suspend remain separate bring-up tasks.
