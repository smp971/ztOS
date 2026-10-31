#!/usr/bin/env python3
"""Watch the bounded boot test and collect read-only USB serial diagnostics.

Requires pyserial on the Windows host. Does not flash or restore any partition.
"""
import argparse
import subprocess
import time
from pathlib import Path

import serial
from serial.tools import list_ports


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--seconds", type=int, default=210)
    ap.add_argument("--passive", action="store_true", help="read serial without sending rescue-shell commands")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    deadline, previous, collected = time.monotonic() + args.seconds, None, False
    command = ("stty -echo 2>/dev/null; PS1=; echo __CROWN_BEGIN__; uname -a; "
               "cat /proc/device-tree/model; echo; cat /proc/cmdline; "
               "cat /run/zboot.log; cat /proc/partitions; "
               "dmesg; echo __CROWN_''DONE__\n")
    while time.monotonic() < deadline:
        result = subprocess.run([args.adb, "devices", "-l"], capture_output=True, text=True, timeout=10)
        devices = result.stdout.strip()
        if devices != previous:
            print(devices, flush=True)
            previous = devices
            with (args.output / "adb-events.txt").open("a", encoding="utf-8") as stream:
                stream.write(f"{time.time():.3f}\n{devices}\n")
        if "\trecovery" in devices or " recovery " in devices:
            print("Recovery ADB returned. Collect pstore and restore the original BOOT next.", flush=True)
            return
        if "unauthorized" in devices:
            print("ADB requires enabling/authorization on the recovery screen.", flush=True)
            return
        if not collected:
            ports = [p for p in list_ports.comports() if p.vid == 0x1D6B and p.pid == 0x0104]
            for port in ports:
                print(f"Rescue USB serial found: {port.device}", flush=True)
                try:
                    with serial.Serial(port.device, baudrate=115200, timeout=1, write_timeout=3) as connection:
                        if not args.passive:
                            connection.write(b"\n")
                            time.sleep(1)
                            connection.read(connection.in_waiting)
                            connection.write(command.encode())
                        log, until = bytearray(), min(deadline, time.monotonic() + 25)
                        while time.monotonic() < until:
                            log.extend(connection.read(connection.in_waiting or 1))
                            if b"__CROWN_DONE__" in log:
                                break
                        (args.output / "rescue-serial.log").write_bytes(log)
                        collected = args.passive or b"__CROWN_DONE__" in log
                        print(f"Serial diagnostics: {len(log)} bytes; complete={collected}", flush=True)
                except (OSError, serial.SerialException) as error:
                    print(f"Serial connection: {error}", flush=True)
        time.sleep(3)
    print("Observation deadline reached. Check the screen and use hardware recovery if needed.", flush=True)


if __name__ == "__main__":
    main()
