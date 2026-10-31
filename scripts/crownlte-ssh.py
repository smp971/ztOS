#!/usr/bin/env python3
"""Run a saved diagnostic script over the Crown USB link, keeping login private."""
import argparse
import json
import sys
from pathlib import Path

import paramiko


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--credentials", type=Path, required=True)
    ap.add_argument("--script", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--sudo", action="store_true")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()
    login = json.loads(args.credentials.read_text())
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect("172.16.42.1", username=login["user"], password=login["password"],
                       timeout=5, banner_timeout=5, auth_timeout=5,
                       look_for_keys=False, allow_agent=False)
        _, check, _ = client.exec_command("tr '\\000' '\\n' < /proc/device-tree/compatible | head -n1", timeout=5)
        if check.read().strip() != b"samsung,crownlte":
            raise SystemExit("USB target is not Crown")
        command = "sudo -k -S -p '' sh -s" if args.sudo else "sh -s"
        stdin, stdout, stderr = client.exec_command(command, timeout=args.timeout)
        payload = args.script.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode()
        if args.sudo:
            payload = (login["password"] + "\n").encode() + payload
        stdin.write(payload)
        stdin.flush()
        stdin.channel.shutdown_write()
        data, errors = stdout.read(), stderr.read()
        status = stdout.channel.recv_exit_status()
        if args.output:
            args.output.write_bytes(data)
        else:
            sys.stdout.buffer.write(data)
        sys.stderr.buffer.write(errors)
        raise SystemExit(status)
    finally:
        client.close()


if __name__ == "__main__":
    main()
