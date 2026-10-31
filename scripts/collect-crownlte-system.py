#!/usr/bin/env python3
"""Collect a bounded Crown system test over USB SSH; never disarm its timer."""
import argparse
import json
import time
from pathlib import Path

import paramiko


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--credentials", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    login = json.loads(args.credentials.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    end = time.monotonic() + 180
    connected = False
    while time.monotonic() < end:
        client = paramiko.SSHClient()
        # This isolated USB prototype regenerates host keys in its RAM overlay.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect("172.16.42.1", username=login["user"], password=login["password"],
                           timeout=3, banner_timeout=3, auth_timeout=3,
                           look_for_keys=False, allow_agent=False)
            connected = True
            command = """date; uptime; uname -a; cat /proc/cmdline; findmnt /; findmnt /run/ztos-host;
systemctl --failed --no-pager; systemctl status greetd zboot-usb-gadget sshd --no-pager;
loginctl list-sessions; ls -l /dev/dri; cat /run/zboot.log;
journalctl -b -n 350 --no-pager; dmesg | tail -150;
cat /home/zerone/.local/state/ztmetro.log 2>/dev/null
"""
            stdin, stdout, stderr = client.exec_command("sudo -k -S -p '' sh -s", timeout=25)
            stdin.write(login["password"] + "\n" + command)
            stdin.flush()
            stdin.channel.shutdown_write()
            stamp = int(time.time())
            (args.output / f"system-{stamp}.log").write_bytes(stdout.read() + stderr.read())
            print("System SSH log captured", flush=True)
        except (OSError, paramiko.SSHException, EOFError):
            pass
        finally:
            client.close()
        time.sleep(5)
    if not connected:
        raise SystemExit("No userspace SSH connection during this bounded test")


if __name__ == "__main__":
    main()
