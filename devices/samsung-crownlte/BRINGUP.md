# Note9 functional bring-up

## Live diagnosis and userspace update: 2026-11-27

Follow-up on the same day: one CP-only reset recovered the physically inserted
SIM1. Subsequent checks reported `sim=ready`, `registered=home`, `tech=4G`
and an assigned IPv4 context. HTTPS attempts had no receive traffic; the user
then clarified that the SIM has no active data option, so Internet service is
not an acceptance result and no further mobile traffic tests were made.

`crown-modem-check.service` now provides one bounded SIM-detection retry per
boot, after initial settling. It does nothing for a ready SIM, an active or
incoming call, an active data context, or an unknown state. The real ready-SIM
path and the disruptive-operation guards were checked. Cold-boot acceptance
is pending. The service uses Wants rather than Requires so stopping the old
network daemon during recovery does not stop its own recovery process.

Sensor transport tests with bit-banged SPI and a slower hardware prescaler
also failed. The default hardware transport, prescaler 3 and supply-cut off
were restored. A full power-off test is the next hardware acceptance step;
repeated warm-reset attempts did not recover the hub. Configuration-file
permissions copied from DrvFS have been normalized in the candidate kit.
The local `crownlte-0.2.3-rc1` bundle is a candidate for this already prepared
phone, not a complete fresh-install image or a declared stable release.

This observation supersedes the October hardware status below where it differs.
SSH and COM35 both work from Windows. A read-only snapshot established:

| Area | Current observation |
| --- | --- |
| Boot | Kernel `7.1.0-ztos-crownlte-rescue`, build #16; radios stage with persistent state. Stored BOOT matches the complete `crownlte-state.img` prefix; full partition SHA256 is `a1ac6a9a476f3481a3ad61f5fc55e52e47ad625948690b74f0b4eb33aa91e96d`. This identifies stored BOOT, not a separate measured-boot attestation. |
| Root/storage | Read-only ext4 base plus writable ext4 state and overlay root. About 3.5 GiB state space and 83 GiB host space free at the initial snapshot. |
| Memory/battery | About 5.38 GiB RAM visible, 4.36 GiB available initially. Battery 16%, charging, 29.6 C; constant-charge limit 1 A, input limit 875 mA. |
| UI/GPU | ztMETRO runs with Panfrost GLES on Mali-G72 MC18. The user confirmed display, touch and app launch before and after the update. Native panel brightness remains unavailable; pixels are dimmed in the compositor. |
| Wi-Fi/BT | Wi-Fi associated and bound HTTPS probe returned 200. Bluetooth adapter powered; no new paired-audio test. |
| Audio/input | ALSA speaker and microphone devices, PipeWire output/filter and Note9 microphone present. Touch, keys and haptic input device present. No S Pen input device. Physical audio/haptics confirmation remains the October result. |
| Modem | Daemon and CP respond, but `AT+CPIN?` returns `SIM not inserted` although the user confirms a SIM is physically inserted. Registration denied and no data session. SIM detection is the immediate telephony problem; the October home/EDGE result is historical. |
| Sensors/GNSS | Hub not ready. LHD download times out and MCU_RESP stays high. One normal reload and one bounded LDO37 supply-cycle test did not recover it. Supply-cut parameter restored off and failed sensor services stopped after diagnosis. No current sensor data or GNSS fix confirmed. |

Upstream `2360ba9` (0.2.3) was combined with the Crown port in the separate
`codex/note9-upstream-0.2.3` worktree. The new `ztoscoru` name is excluded from
generic auto-start on Crown, keeping unvalidated S9 components off. The fresh
image layer now uses the previously validated Panfrost session settings, and
its IAL manifest describes the known battery and rumble device.

Native shell/app/browser compilation succeeded on the phone. The launch,
authentication and keyboard tests passed after linking their DotMatrix
dependencies and updating the stale cursor-dot drag expectation to the
upstream behavior. The shell and native apps were installed with
`scripts/update-crownlte-ui.py`, preserving hardware daemons and BOOT. The user
confirmed the new interface works; the persistent kit hash was verified and
automatic UI rollback was cancelled. The running shell reports
`ztMETRO 0.2.3 (2360ba9-crownlte) (wlroots 0.20.2)`.

This is a shell/native-app update. `/etc/os-release` still describes the
0.2.0-BETA-1 base image; no full base-image replacement, PIN/vault activation,
modem firmware update or phone reboot was performed. Boot persistence of the
new kit has not been retested with a full reboot. Backup UI and kit remain on
the phone under `/unencrypted/ztos/ui-updates/20261127T063103Z` (as seen from
the host mount). Kernel/display presentation, sensor cold start and SIM
detection require separate hardware work.

Only hardware-tested results count as working. Original Android partitions
and calibration backups must be retained; no calls or messages are sent
without the user's specific instruction. Batch kernel changes to minimize
reboots. Current storage: test-14 BOOT, read-only base plus 4 GiB state image.

| Area | Confirmed | Remaining acceptance |
| --- | --- | --- |
| Telephony | SIM, automatic modem boot, home registration; transient LTE | Stable LTE, IP data, microphone-to-modem and call audio |
| Display | HA8 boot framebuffer, Panfrost, about 45–50 FPS | Native display presentation, real brightness, improved measured frame time |
| Power | Gauge, 1 A limits, clean shutdown, persistent state | Suspend/resume, wake, idle consumption and thermal controls |
| Bluetooth audio | BlueZ controller, firmware, discovery, audio endpoints | Pairing and playback with physical headphones/speaker; user has none available |
| Note9 inputs | Touch and keys; user-confirmed microphone and physical haptics; accelerometer, gyro, pressure, proximity and ambient-light samples | Rotation integration, S Pen events, calibration |
| Dual boot | Original Lineage BOOT/recovery backups and preserved partitions | Explicit boot selection, reliable return to each OS, persistent choice |
| Cameras/GPS | Stock device information and original vendor firmware available | Camera sensor/ISP pipeline, sensor hub/GNSS transport and real satellite fix |

Test 15: user authorized a local five-second microphone recording and playback,
followed by deletion. CS47L93 returned ID 0x6371/revision 1; 48 kHz stereo
capture completed, and the user confirmed clear speech. The temporary recording
was deleted without copying it off the phone. PipeWire source integration and
automatic capture-module settings are installed in the persistent kit.

Sensor bring-up uses the Crown Q firmware from the original kernel, not the
STAR firmware embedded in the generic transport. The extracted 851,282-byte
patch matches SHA256 `4c68dfd8822648b86f7461bb30f537fbda48a04e02268b23610fd0d94b530120`;
it also matches the original Android kernel byte-for-byte. SSP reports chip
0x55 and firmware 19121600. A six-second sample returned 32 samples each from
accelerometer, gyro and pressure, two proximity records and five light records.
The Crown sensor-hub and sensor services are installed and active. Only their
LHD process uses the compatibility library; the Android libraries stay intact.
The service holds a Linux sleep inhibitor because this compatibility library
does not yet implement Android SystemSuspend wake locks. Deep suspend remains
pending. Native panel brightness and physical rotation are separate acceptance
tests; receiving light/acceleration does not establish those features.

The stock GPS engine can load using the original tethering/i18n APEX payloads
and a private uevent compatibility prototype. Its native bridge has reached
HAL start, but a test produced SIGBUS and no NMEA/fix was established. GPS test
services are bounded and are not enabled at boot. Do not mark GNSS working.

Test 16 adds two independent desktop apps, leaving the existing streaming Music
app intact. Local Music scans `~/Music`, supports an additional persistent file
list, sequential playback, pause, seek and volume through mpv/PipeWire. Voice
Recorder captures only after an explicit Record press, saves private WAV files
in `~/Documents/Recordings`, finalizes on Save or window close, and offers
playback and confirmed deletion. Low storage and a one-hour recording limit
stop capture. The microphone is the previously validated `crown-microphone`
PipeWire node. Button haptics use the shell's existing strength preferences.

The installed kit now includes the validated Crown haptic module and its boot
service. Live activation succeeded without a reboot; the shell already holds
the haptic event device open. On-device tests passed UI construction, WAV
finalization using a synthetic recorder process, and real mpv/PipeWire playback,
pause and seek of temporary silence. Test audio was deleted automatically;
these tests did not capture the physical microphone. The recorder starts on
Wayland and both desktop entries are indexed. The user confirmed that the
interface displays correctly and physical microphone recording/playback work.
Settings/data remain in the existing writable state
image; this update did not change BOOT or original Android partitions.

Test 17 fixes SuperScan's black window with a Crown-only launcher setting
`PAN_MESA_DEBUG=noafbc,linear` for the browser and its WebKit children. Before
the change the compositor repeatedly rejected buffers with `EGL_BAD_MATCH`.
The user confirmed the local HTML test page became visible with this setting.
The installed entry point now applies it automatically; a subsequent launch
through that entry point produced zero new EGL_BAD_MATCH errors in the checked
interval. Panfrost GLES and WebKit direct frames remain active; the sandbox is
unchanged. The original ARM64 ELF is preserved under the Crown browser library
directory (SHA256 `3374b19cb8f564386b49fe61c32f8ab6e703a6f4d9963f92f06fd0a7e9041a37`).
The launcher and ELF are in the persistent kit. No phone reboot was required.
