# Note9 functional bring-up

## Live diagnosis and userspace update: 2026-11-27

OSIAL hardware follow-up: **eleven of thirteen interfaces now answer on D-Bus**.
The Crown manifest/module and private persistent kit add Sensors1, Lights1 and
Accel1 to the earlier eight-interface update. This interface count describes
responding APIs; brightness, suspend and other individual features can still
report unavailable. CallAudio1 and Android1 remain unserved.

After a Lineage Recovery → System restart, the unchanged Crown hub module
reported ready and published live light, acceleration, gyroscope, pressure and
proximity samples. Native sensord was updated to 0.2.3 so all five streams work
through the current control protocol. Sensors1 reports lux, acceleration in
m/s², binary proximity, and explicitly named raw gyro/pressure readings whose
scales remain unverified. Expired motion samples and a stopped daemon are
rejected. Recovery is a confirmed workaround on this phone; reliable hub
initialization after an independent cold boot is still unresolved.

The Crown-only RGB module uses the verified stock wiring and limits its
current setting to code 5. The user confirmed red, green and blue physically.
The notification LED and its service are included in the private kit. The
torch chip accepts register writes, but the first bounded test produced no
visible light. The second test at stock minimum current has no physical
confirmation. Its temporary module was turned off and unloaded; no torch
capability or boot service is claimed.

SCORE passed real 16×16 matrix calculations at its existing 33 MHz boot clock:
integer Q16 gave 0/256 wrong results, and fractional Q16 matched the DSP's
floor-per-product reference for all 256 results. No clock or voltage writes
were made. The Crown module rejects non-Crown boards and stops its interface
on a DSP IRQ fault instead of retrying firmware boot in hard IRQ. The boot
service checks the exact kernel configuration, firmware hashes, power/SYSMMU
state and clock selection, then repeats both arithmetic tests before creating
the readiness marker used by OSIAL. This establishes accelerator bring-up,
not application inference integration or faster compositor rendering. Access
remains restricted to system services. Never unload the SCORE module live.

Devices and Services now prefers a device-specific catalogue and uses Crown
units, driver nodes and readiness checks. A detected driver is described as
available rather than proof that the complete feature works; failed units
are still shown. The GTK portal's missing Wayland activation environment was
fixed, and the non-nested shell now publishes that environment on startup.
A Crown user-unit drop-in reconnects the GTK portal after a broken display
connection, with bounded retries. An injected backend-process failure recovered
automatically without restarting the compositor. Both system and user failed-
unit lists were empty after that check.
The wlroots 0.20 listener teardown assertion was fixed; the native regression
test covers both partially initialized and normally attached backends.

Fourteen on-phone IAL adapter tests and three SCORE admission/parser tests
passed. Native backend-cleanup, launch, authentication and keyboard checks
passed. This update retains the running #16 kernel, base image, BOOT and
Android partitions. The feature kit is persistent but its latest additions
still need acceptance after a planned reboot; no extra phone reboot was made
just to install these modules and userspace changes.

The earlier Haptics1, Modem1 and AudioDevice1 integration remains in place.
Haptics discovers its input device again if the module loads after IAL starts,
avoiding an ordering dependency on boot. Modem state comes from the running
Shannon daemon and CP state; controls use its nonblocking, bounded FIFO
protocol. Signal bars are 0..5, mapped to 0..100. Offline CP or a stopped daemon
does not reuse a stale connected state. AudioDevice exposes the actual Crown
driver's recovery/codec counters; calibration and speaker protection report
false, and call routing remains unvalidated with CP VSS disabled.

The user confirmed both physical OSIAL vibrations and the earlier eight
connected interfaces on screen. Subsequent live queries still report SIM
ready/home/4G. OSIAL's description
identifies Accel1 as model-inference hardware (SCORE), distinct from Panfrost,
and explains that an answering interface can still have unavailable features.

Call audio is still disabled (`cp_vss=0`). The stock DT's VSS size/offset and
the running CP's VSS/parameter offsets match the driver's expected layout;
that read-only check does not validate the DSP mapping or voice route. Those
paths and a user-authorized real call still need testing. Android/Binder
requires a kernel build with Binder enabled; enabling a userspace manifest is
insufficient. Display1 and Sleep1 answer queries but native HA8 brightness and
suspend remain unavailable.

App-menu follow-up: the installed Settings and ZrnDevTest binaries lacked
desktop entries, so they could appear as built-in Start tiles but not in the
all-apps list. Their entries are now included in the native install, Crown UI
updater/rollback and persistent kit. Crown also exposes the already installed
Chromium browser with native Wayland, alongside Superscan; WhatsApp's separate
headless profile is unchanged. Desktop validation passed and the running
indexer rebuilt the list from 22 to 25 applications. The compositor reloaded
it without a session restart or phone reboot.

Follow-up on the same day: one CP-only reset recovered the physically inserted
SIM1. Subsequent checks reported `sim=ready`, `registered=home`, `tech=4G`
and an assigned IPv4 context. HTTPS attempts had no receive traffic; the user
then clarified that the SIM has no active data option, so Internet service is
not an acceptance result and no further mobile traffic tests were made.

`crown-modem-check.service` now provides one bounded SIM-detection retry per
boot, after initial settling. It does nothing for a ready SIM, an active or
incoming call, an active data context, or an unknown state. The real ready-SIM
path and the disruptive-operation guards were checked. After a controlled
power-off and user restart, SIM1 registered home on 4G automatically; the
boot check logged `CROWN_SIM_READY_NO_RESET`. This is one successful boot,
not an extended LTE reliability or Internet test. The service uses Wants
rather than Requires so stopping the old
network daemon during recovery does not stop its own recovery process.

Sensor transport tests with bit-banged SPI and a slower hardware prescaler
also failed. The default hardware transport, prescaler 3 and supply-cut off
were restored. A controlled power-off and user restart also failed to recover
the hub. SPI tracing showed only zero reply bytes before patch download.
LHD successfully opens the power-control paths, raises GPS_PWR_EN, and LDO37
reads enabled (`ec`). The installed hub module is byte-identical to the
October working module; both wake-lock shims have identical function code.
These checks locate the failure in hub startup/transport, but do not prove
which signal, clock or retained chip state causes it. No additional speculative
PMIC writes or repeated phone restarts were made.

The optional sensor readiness wait now runs inside the service's main
process, rather than `ExecStartPre`: missing sensors no longer delay
multi-user/graphical startup for up to 60 seconds. Live service activation
returned in 0.06 s while the compositor remained running. A failed hub is
still reported as unavailable, and the wrapper has a bounded wait and no
restart loop. Configuration-file permissions copied from DrvFS have been
normalized. The local RC bundles target this already prepared phone; they are
neither complete fresh-install images nor declared stable phone releases.

This observation supersedes the October hardware status below where it differs.
SSH and COM35 both work from Windows. The earlier read-only snapshot, before
the hardware follow-up above, established:

| Area | Earlier observation |
| --- | --- |
| Boot | Kernel `7.1.0-ztos-crownlte-rescue`, build #16; radios stage with persistent state. Stored BOOT matches the complete `crownlte-state.img` prefix; full partition SHA256 is `a1ac6a9a476f3481a3ad61f5fc55e52e47ad625948690b74f0b4eb33aa91e96d`. This identifies stored BOOT, not a separate measured-boot attestation. |
| Root/storage | Read-only ext4 base plus writable ext4 state and overlay root. After restart: 3.4 GiB state space and 83 GiB host space free. The 10 GiB base image's SHA256 was reverified live. |
| Memory/battery | About 5.38 GiB RAM visible. After restart: battery 100%, full, 29.6 C; charge-current and USB-input limits both read 1 A. |
| UI/GPU | ztMETRO runs with Panfrost GLES on Mali-G72 MC18. The user confirmed display, touch and app launch before and after the update. Native panel brightness remains unavailable; pixels are dimmed in the compositor. |
| Wi-Fi/BT | Wi-Fi associated and bound HTTPS probe returned 200. Bluetooth adapter powered; no new paired-audio test. |
| Audio/input | ALSA speaker and microphone devices, PipeWire output/filter and Note9 microphone present. Touch, keys and haptic input device present. No S Pen input device. Physical audio/haptics confirmation remains the October result. |
| Modem | SIM ready, home registration and 4G after one CP-only recovery, then automatically after the full shutdown/restart. IPv4 context assigned. Mobile Internet and call audio remain unvalidated. |
| Sensors/GNSS | Hub not ready, including after shutdown/restart. All-zero SPI replies and LHD autobaud timeouts. No current sensor samples or GNSS fix. Default transport restored; diagnostic tracing disabled. |

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
or modem firmware update was performed. Subsequent shutdown/restart confirmed
the new UI, kit and writable state return automatically. The user confirmed
the interface and touch again after this boot. Backup UI and kit remain on
the phone under `/unencrypted/ztos/ui-updates/20261127T063103Z` (as seen from
the host mount). Kernel/display presentation and sensor startup still require
hardware work.

Only hardware-tested results count as working. Original Android partitions
and calibration backups must be retained; no calls or messages are sent
without the user's specific instruction. Batch kernel changes to minimize
reboots. Current storage: test-14 BOOT, read-only base plus 4 GiB state image.

| Area | Confirmed | Remaining acceptance |
| --- | --- | --- |
| Telephony | SIM, automatic modem boot, home registration and 4G on the November shutdown/restart | Extended LTE reliability, IP data with an active option, microphone-to-modem and call audio |
| Display | HA8 boot framebuffer, Panfrost, about 45–50 FPS | Native display presentation, real brightness, improved measured frame time |
| Power | Gauge, 1 A limits, clean shutdown, persistent state | Suspend/resume, wake, idle consumption and thermal controls |
| Bluetooth audio | BlueZ controller, firmware, discovery, audio endpoints | Pairing and playback with physical headphones/speaker; user has none available |
| Note9 inputs | Touch and keys; live sensor streams after recovery; user-confirmed RGB LED; earlier microphone and haptics | Reliable cold-start hub initialization, gyro/pressure scaling, rotation integration, S Pen and calibration |
| Dual boot | Original Lineage BOOT/recovery backups and preserved partitions | Explicit boot selection, reliable return to each OS, persistent choice |
| Cameras/GPS | Stock device information and original vendor firmware available | Camera sensor/ISP pipeline, sensor hub/GNSS transport and real satellite fix |

## Historical hardware tests: 2026-10-30 to 2026-10-31

The results below describe those tests, not the current sensor-hub state.

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
