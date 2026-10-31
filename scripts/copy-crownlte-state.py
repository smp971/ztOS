#!/usr/bin/env python3
"""Stage a new state filesystem file using the phone's existing recovery kernel."""
import argparse
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--build-root", type=Path, required=True)
    args = ap.parse_args()

    def adb(*parts, capture=True):
        return subprocess.run([args.adb, "-s", args.serial, *parts], check=True,
                              capture_output=capture, text=True).stdout

    def shell(command):
        return adb("shell", command).strip()

    root = args.build_root
    if "CROWN_STATE_IMAGE_READY" not in (root / "state-image-build.log").read_text():
        raise SystemExit("State image preparation has not finished")
    digest = (root / "crownlte-state.sha256").read_text().split()[0]
    gzip_digest = (root / "crownlte-state-gzip.sha256").read_text().split()[0]
    if adb("get-state").strip() != "recovery" or shell("id -u") != "0":
        raise SystemExit("Requires root Lineage Recovery ADB")
    if shell("getprop ro.product.device") != "crownlte" or shell("getprop ro.product.model") != "SM-N960F":
        raise SystemExit("Unexpected phone")
    if shell("readlink -f /dev/block/by-name/USERDATA") != "/dev/block/sda25":
        raise SystemExit("Unexpected USERDATA mapping")
    shell("set -e; ! grep -q ' /data ' /proc/mounts; test -d /data; "
          "mount -t f2fs -o rw,noatime,nodiscard /dev/block/sda25 /data")
    try:
        target = "/data/unencrypted/ztos/crownlte-state.img"
        shell(f"set -e; test -d /data/unencrypted/ztos; test ! -L /data/unencrypted/ztos; "
              f"test ! -e {target}; test ! -e {target}.part; test ! -e /tmp/crownlte-state.img.gz")
        adb("push", str(root / "crownlte-state.img.gz"), "/tmp/crownlte-state.img.gz", capture=False)
        if shell("sha256sum /tmp/crownlte-state.img.gz").split()[0] != gzip_digest:
            raise SystemExit("Compressed state transfer hash mismatch")
        print("Expanding new 4 GiB state file; Android partitions are retained", flush=True)
        shell(f"set -e; set -C; gzip -dc /tmp/crownlte-state.img.gz > {target}.part; sync")
        if shell(f"stat -c %s {target}.part") != "4294967296":
            raise SystemExit("State image size mismatch")
        if shell(f"sha256sum {target}.part").split()[0] != digest:
            raise SystemExit("State image readback hash mismatch")
        shell(f"set -e; test ! -e {target}; chmod 600 {target}.part; mv {target}.part {target}; sync")
        print("PHONE_STATE_FILE_VERIFIED " + digest, flush=True)
    finally:
        shell("sync; umount /data")


if __name__ == "__main__":
    main()
