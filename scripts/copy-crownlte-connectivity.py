#!/usr/bin/env python3
"""Copy a new, verified connectivity kit file through Crown's existing recovery."""
import argparse
import hashlib
import subprocess
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--adb', required=True)
ap.add_argument('--serial', required=True)
ap.add_argument('--build-root', type=Path, required=True)
ap.add_argument('--kit', type=Path, help='replacement kit; installed under the canonical name')
ap.add_argument('--replace-existing', action='store_true')
args = ap.parse_args()


def adb(*parts):
    result = subprocess.run([args.adb, '-s', args.serial, *parts], check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def shell(command):
    return adb('shell', command)


kit = args.kit or args.build_root / 'crownlte-connectivity-kit.tar.gz'
manifest = args.build_root / 'crownlte-connectivity-kit.sha256'
digest = hashlib.sha256(kit.read_bytes()).hexdigest()
if not args.kit and manifest.read_text().split() != [digest, kit.name]:
    raise SystemExit('Local kit checksum differs')
if adb('get-state') != 'recovery' or shell('id -u') != '0':
    raise SystemExit('Requires root Lineage Recovery ADB')
if shell('getprop ro.product.device') != 'crownlte' or shell('getprop ro.product.model') != 'SM-N960F':
    raise SystemExit('Unexpected phone')
if shell('readlink -f /dev/block/by-name/USERDATA') != '/dev/block/sda25':
    raise SystemExit('Unexpected USERDATA mapping')
shell("set -e; ! grep -q ' /data ' /proc/mounts; mount -t f2fs -o rw,noatime,nodiscard /dev/block/sda25 /data")
directory = '/data/unencrypted/ztos'
target = directory + '/crownlte-connectivity-kit.tar.gz'
check = directory + '/' + manifest.name
try:
    shell(f'set -e; test -d {directory}; test ! -L {directory}; '
          f'test ! -L {target}; test ! -e {target}.part; '
          f'test ! -L {check}; test ! -e {check}.part')
    previous = None
    if args.replace_existing:
        shell(f'set -e; test -f {target}; test -f {check}; cd {directory}; sha256sum -c {manifest.name}')
        previous = shell('sha256sum ' + target).split()[0]
        if len(previous) != 64 or any(c not in '0123456789abcdef' for c in previous):
            raise SystemExit('Invalid previous checksum')
        backup = target + '.previous-' + previous[:12]
        backup_check = check + '.previous-' + previous[:12]
        shell(f'set -e; test ! -e {backup}; test ! -e {backup_check}; '
              f'cp -p {target} {backup}; cp -p {check} {backup_check}; sync')
        if shell('sha256sum ' + backup).split()[0] != previous:
            raise SystemExit('Previous kit backup differs')
    else:
        shell(f'set -e; test ! -e {target}; test ! -e {check}')
    adb('push', str(kit), target + '.part')
    shell(f"printf '%s  crownlte-connectivity-kit.tar.gz\n' {digest} > {check}.part")
    if shell('sha256sum ' + target + '.part').split()[0] != digest:
        raise SystemExit('Phone kit checksum differs')
    if shell('cat ' + check + '.part').split() != [digest, 'crownlte-connectivity-kit.tar.gz']:
        raise SystemExit('Phone checksum manifest differs')
    try:
        shell(f'set -e; chmod 600 {target}.part {check}.part; '
              f'mv {target}.part {target}; mv {check}.part {check}; sync; '
              f'cd {directory}; sha256sum -c {manifest.name}')
    except Exception:
        if previous:
            shell(f'set -e; cp -p {backup} {target}; cp -p {backup_check} {check}; sync')
        raise
    print('Crown connectivity kit copied and verified; no partition formatted')
finally:
    shell('sync; umount /data')
