# Note9 functional bring-up

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
