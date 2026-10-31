#!/usr/bin/env python3
"""Build the Crown prototype root image on Linux; never access a phone.

Uses the shared installer, the Crown device layer and a signed Arch Linux ARM
tarball already downloaded under <build-root>/rootfs-inputs/. Login credentials
are generated into a private local file, outside the source repository.
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib
    sys.modules["tomllib"] = tomllib

FINGERPRINT = "68B3537F39A313B3E574D06777193F152BDBE6A6"
REPO = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build-root", type=Path, required=True)
    ap.add_argument("--size-gb", type=int, default=10)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--resume-config", action="store_true",
                    help="resume after a failed device layer, using the already built userspace")
    args = ap.parse_args()
    work = args.build_root.resolve()
    inputs = work / "rootfs-inputs"
    tarball = inputs / "alarm.tar.gz"
    signature = inputs / "alarm.tar.gz.sig"
    result = subprocess.run(["gpg", "--homedir", str(inputs / "gnupg"), "--batch",
                             "--status-fd=1", "--verify", str(signature), str(tarball)],
                            capture_output=True, text=True)
    valid = [line.split() for line in result.stdout.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")]
    if result.returncode or not any(FINGERPRINT in (line[2], line[-1]) for line in valid):
        sys.exit("Arch rootfs signature is not valid for the pinned build key: " + result.stderr)
    print("Arch Linux ARM rootfs signature verified", flush=True)

    credentials = work / "crownlte-login.json"
    if credentials.exists():
        login = json.loads(credentials.read_text())
    else:
        login = {"user": "zerone", "password": secrets.token_urlsafe(18)}
        fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(login, stream)
    sys.path.insert(0, str(REPO / "installer"))
    from ztos_installer import build
    build.WORK = work / "rootfs-build"
    build.PKGCACHE = work / "pkg-cache"
    build.TARBALL = tarball
    mke2fs = "/usr/bin/mke2fs" if Path("/usr/bin/mke2fs").exists() else "/usr/sbin/mke2fs"
    version = subprocess.run([mke2fs, "-V"], capture_output=True, text=True, check=True)
    match = re.search(r"mke2fs (\d+)\.(\d+)", version.stderr)
    if not match:
        sys.exit("Cannot determine mke2fs version")
    if tuple(map(int, match.groups())) < (1, 47):
        # Older e2fsprogs has no orphan_file feature, even as a disabled flag.
        build.STAGE = build.STAGE.replace(" -O ^orphan_file", "")
    image_path = build.WORK / "crownlte" / "root.img"
    if image_path.exists() and image_path.stat().st_size == 0:
        image_path.unlink()
    if args.resume_config:
        if args.fresh:
            ap.error("--resume-config cannot be combined with --fresh")
        root = build.WORK / "crownlte" / "root"
        for required in (".ztos-unpacked", "usr/local/bin/ztmetro", "usr/local/bin/superscan", "usr/lib/libztos-ial.so"):
            if not (root / required).exists():
                sys.exit(f"Cannot resume: missing {root / required}")
        # Recreate the isolated mount/chroot setup, then reapply the device layer
        # and finish configuration. Do not download or rebuild the existing OS.
        setup = build.STAGE[build.STAGE.index('mount --bind "$R" "$R"'):build.STAGE.index('if [ "$TARGET" = starlte ]')]
        build.STAGE = 'set -eu\nstep() { echo "STEP $*"; }\nR=$ROOTFS\numask 022\n' + setup + build.STAGE[build.STAGE.index('DEVICE_UNITS='):]
    settings = build.Settings(target="crownlte", user=login["user"], password=login["password"],
                              hostname="ztos-note9", timezone="Europe/Bucharest",
                              size_gb=args.size_gb, fresh=args.fresh)
    image = build.build(settings)
    print(f"Crown root image built: {image}", flush=True)
    print(f"Private login file: {credentials}", flush=True)


if __name__ == "__main__":
    main()
