#!/usr/bin/env python3
"""Read modem/SIM status on Crown; never place calls, send SMS or enable data."""
import argparse
import os
import select
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--settle-seconds', type=int, choices=range(0, 61), default=3, metavar='0..60')
    args = ap.parse_args()
    if Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0] != b'samsung,crownlte':
        raise SystemExit('Not a Crown phone')
    flags = os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC
    channels = []
    try:
        # The modem completes CP_START only once both RIL endpoints are open.
        for name in ('umts_ipc0', 'umts_ipc1', 'umts_rfs0', 'umts_router'):
            channels.append(os.open('/dev/' + name, flags))
        time.sleep(args.settle_seconds)
        router = channels[-1]
        for command in ('AT', 'AT+CPIN?', 'AT+CFUN?', 'AT+COPS?', 'AT+CREG?', 'AT+CGREG?', 'AT+CEREG?', 'AT+CSQ'):
            print(command, flush=True)
            os.write(router, command.encode('ascii') + b'\r')
            deadline = time.monotonic() + 5
            result = bytearray()
            while time.monotonic() < deadline:
                ready, _, _ = select.select([router], [], [], min(0.5, max(0, deadline - time.monotonic())))
                if not ready:
                    continue
                try:
                    data = os.read(router, 8192)
                except BlockingIOError:
                    continue
                if not data:
                    break
                result.extend(data)
                if b'\nOK' in result or b'ERROR' in result:
                    break
            print(result.decode('ascii', errors='backslashreplace') if result else '(no response)', flush=True)
    finally:
        for descriptor in reversed(channels):
            os.close(descriptor)


if __name__ == '__main__':
    main()
