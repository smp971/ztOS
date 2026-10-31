#!/usr/bin/env python3
"""Copy a verified root image as a new Android file; never flash a partition."""
import argparse
import re
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--build-root", type=Path, required=True)
    ap.add_argument("--replace-sha256", help="replace only this exact earlier prototype, retaining it as .previous")
    args = ap.parse_args()
    serial = args.serial

    def adb(*parts, capture=True):
        return subprocess.run([args.adb, "-s", serial, *parts], check=True,
                              capture_output=capture, text=True).stdout

    def shell(command):
        return adb("shell", command).strip()

    root = args.build_root
    if "CROWN_ROOT_IMAGE_VERIFIED" not in (root / "rootfs-check.log").read_text():
        raise SystemExit("Local image checks have not finished")
    digest = (root / "crownlte-root.sha256").read_text().split()[0]
    compressed_digest = (root / "crownlte-root-gzip.sha256").read_text().split()[0]
    if shell("getprop ro.product.device") != "crownlte" or shell("getprop ro.product.model") != "SM-N960F":
        raise SystemExit("Wrong phone")
    if shell("id -u") != "0" or shell("getprop sys.boot_completed") != "1":
        raise SystemExit("Requires booted Android with root ADB")
    directory = "/data/unencrypted/ztos"
    target = directory + "/crownlte-root.img"
    replacing = args.replace_sha256
    if replacing and not re.fullmatch(r"[0-9a-f]{64}", replacing):
        raise SystemExit("Invalid replacement digest")
    transfer = target + (".next.gz" if replacing else ".gz")
    guard = f"test ! -L {target}; test -f {target}; test ! -e {target}.previous" if replacing else f"test ! -e {target}"
    shell(f"set -e; test -d /data/unencrypted; test ! -L {directory}; {guard}; "
          f"test ! -e {target}.part; test ! -e {transfer}; mkdir -p {directory}; chmod 700 {directory}")
    if replacing and shell(f"sha256sum {target}").split()[0] != replacing:
        raise SystemExit("Existing prototype does not match the replacement digest")
    print("Copying new compressed image file through USB", flush=True)
    adb("push", str(root / "crownlte-root.img.gz"), transfer, capture=False)
    if shell(f"sha256sum {transfer}").split()[0] != compressed_digest:
        raise SystemExit("USB compressed image hash mismatch")
    print("USB copy verified; expanding new image file", flush=True)
    shell(f"set -e; set -C; gzip -dc {transfer} > {target}.part; sync")
    if shell(f"stat -c %s {target}.part") != "10737418240":
        raise SystemExit("Expanded image size mismatch")
    if shell(f"sha256sum {target}.part").split()[0] != digest:
        raise SystemExit("Expanded image hash mismatch")
    if replacing:
        if shell(f"sha256sum {target}").split()[0] != replacing:
            raise SystemExit("Existing prototype changed during transfer")
        shell(f"set -e; test ! -e {target}.previous; chmod 444 {target}.part; "
              f"mv {target} {target}.previous; mv {target}.part {target}; sync")
    else:
        shell(f"set -e; test ! -e {target}; chmod 444 {target}.part; mv {target}.part {target}; sync")
    print("PHONE_ROOT_IMAGE_VERIFIED " + digest, flush=True)


if __name__ == "__main__":
    main()
