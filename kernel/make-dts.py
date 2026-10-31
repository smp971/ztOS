#!/usr/bin/env python3
"""Derive the Galaxy S9 (starlte, SM-G960N) device tree from the S9+ port's.

  make-dts.py <exynos9810-star2lte.dts> <out.dts> [--ufs] [--power] [--touch]
              [--gpu] [--decon] [--wlan] [--fallback boot|recovery]

The two phones share the board design; what differs is listed here, and every
edit is asserted, so a changed upstream file fails the build instead of
silently producing an S9+ tree.

  memory     4 GB: the bank at 0x9_00000000 does not exist (bootloader FDT)
  battery    3000 mAh, 4.35 V float (stock battery,chg_float_voltage = 4350)
  fallback   which INFORM3 magic the kernel arms first thing. "boot" means a
             watchdog reset or panic comes up from BOOT; "recovery" from
             RECOVERY. Point it at whichever one holds TWRP.

Blocks are off unless asked for, because a read into a gated or unpowered
block on this SoC is a silent bus hang rather than an error:

  --ufs      the UFS host (the root filesystem lives there)
  --power    MAX77705 PMIC, charger and fuel gauge
  --touch    the S6SY761 touch controller (its rails are cycled by s9p-acpm)
  --gpu      Mali-G72, its power domain and the G3D clock provider
  --decon    DECON scanout, taking the display from the bootloader framebuffer
  --wlan     the PCIe root complex the BCM4361 sits on
"""
import argparse
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--device", choices=("starlte", "crownlte"), default="starlte")
ap.add_argument("--crown-stage", choices=("usb", "storage", "touch", "system", "gpu", "radios"), default="usb")
ap.add_argument("--ufs", action="store_true")
ap.add_argument("--power", action="store_true")
ap.add_argument("--touch", action="store_true")
ap.add_argument("--gpu", action="store_true")
ap.add_argument("--decon", action="store_true")
ap.add_argument("--wlan", action="store_true")
ap.add_argument("--fallback", choices=("boot", "recovery"), default="boot")
args = ap.parse_args()

if args.device == "crownlte":
    # The connected SM-N960F has a Y771 controller and an HA8 Crown panel.
    # Neither the S6SY761 binding nor the S9 brightness tables are validated.
    if args.decon or (args.crown_stage != "radios" and (args.power or args.wlan)):
        ap.error("crownlte does not yet support these hardware switches")
    if args.gpu != (args.crown_stage in ("gpu", "radios")):
        ap.error("crownlte GPU requires the explicit gpu stage")
    if args.ufs != (args.crown_stage != "usb"):
        ap.error("crownlte: --ufs requires an explicit storage/touch stage")
    if args.touch != (args.crown_stage in ("touch", "system", "gpu", "radios")):
        ap.error("crownlte: --touch requires the explicit --crown-stage touch")
    if args.fallback != "recovery":
        ap.error("crownlte requires --fallback recovery to preserve the way back")
    if args.crown_stage == "radios" and not (args.power and args.wlan):
        ap.error("crownlte radios stage requires --power and --wlan")

s = Path(args.src).read_text()


def sub(old, new, count=1):
    global s
    if s.count(old) != count:
        sys.exit(f"make-dts: expected {count}x {old!r}, found {s.count(old)}")
    s = s.replace(old, new)


def enable(marker, count=1):
    """Turn on a node the S9+ build switches with a sed of its own."""
    sub(f'status = "disabled"; /* {marker}-STATUS */',
        f'status = "okay"; /* {marker}-STATUS */', count)


def disable(anchor, count=1):
    """Turn off a node that is on in the source, after its last property."""
    sub(anchor, anchor + '\n\t\t\tstatus = "disabled";', count)


model = "Samsung Galaxy Note9 (SM-N960F)" if args.device == "crownlte" else "Samsung Galaxy S9 (SM-G960N)"
sub('model = "Samsung Galaxy S9+ (SM-G965F)";', f'model = "{model}";')
sub('compatible = "samsung,star2lte", "samsung,exynos9810";',
    f'compatible = "samsung,{args.device}", "samsung,exynos9810";')

if args.device == "crownlte":
    # Read from this SM-N960F's live FDT: the protected RKP region is larger
    # than the S9+'s. Letting the page allocator use any of it is unsafe.
    sub("rkp@af800000 {", "rkp@af600000 {")
    sub("reg = <0x0 0xaf800000 0x1800000>;", "reg = <0x0 0xaf600000 0x2400000>;")
    sub('compatible = "samsung,s6sy761";', 'compatible = "samsung,s6sy771";')

if args.device == "starlte":
    sub("""		      <0x8 0x80000000 0x80000000>,
		      <0x9 0x00000000 0x80000000>;""",
    """		      <0x8 0x80000000 0x80000000>;""")

capacity, energy, current = (4000000, 15400000, 1000000) if args.device == "crownlte" else (3000000, 11550000, 1500000)
sub("energy-full-design-microwatt-hours = <13480000>;", f"energy-full-design-microwatt-hours = <{energy}>;")
sub("charge-full-design-microamp-hours = <3500000>;", f"charge-full-design-microamp-hours = <{capacity}>;")
sub("voltage-max-design-microvolt = <4400000>;", "voltage-max-design-microvolt = <4350000>;")
sub("constant-charge-current-max-microamp = <2150000>;", f"constant-charge-current-max-microamp = <{current}>;")
sub("constant-charge-voltage-max-microvolt = <4400000>;", "constant-charge-voltage-max-microvolt = <4350000>;")

if args.fallback == "boot":
    sub("<0x1406080c 0x12345674>,	/* PMU INFORM3 = recovery */",
        "<0x1406080c 0x12345670>,	/* PMU INFORM3 = normal boot: TWRP sits on BOOT */")

if args.ufs:
    enable("UFS", count=2)
if args.gpu:
    enable("GPU")
    if args.device == "crownlte":
        # Initial hardware probe stays at the lowest stock frequency, 260 MHz.
        start = s.index('\n\t\t\topp-455000000 {')
        end = s.index('\n\t\t};', start)
        s = s[:start] + s[end:]
if args.decon:
    enable("DECON")
if args.wlan:
    enable("WLAN")
    s += '''
/* PCI restores endpoint configuration in resume_noirq. Restore its GPIO
 * providers first, including WL_REG_ON and PERST# mux/data registers. */
&pinctrl_fsys1 { samsung,noirq-resume; };
&pinctrl_peric0 { samsung,noirq-resume; };
'''

if not args.power:
    disable("""			interrupt-controller;
			#interrupt-cells = <1>;""")
    disable("""			interrupt-parent = <&max77705>;
			interrupts = <0>;""")
    disable("""			interrupt-parent = <&max77705>;
			interrupts = <2>;""")

if not args.touch:
    disable("			touchscreen-size-y = <4096>;")

if not args.gpu:
    # A power domain with no consumer is powered off by genpd, and that
    # sequence is only validated with the GPU running.
    sub("""		#power-domain-cells = <0>;
		label = "G3D";""", """		#power-domain-cells = <0>;
		label = "G3D";
		status = "disabled";""")
    sub("""		clock-output-names = "g3d";""", """		clock-output-names = "g3d";
		status = "disabled";""")

Path(args.out).write_text(s)
print("make-dts: {} (ufs={} power={} touch={} gpu={} decon={} wlan={} fallback={})".format(
    args.out, args.ufs, args.power, args.touch, args.gpu, args.decon, args.wlan, args.fallback))
