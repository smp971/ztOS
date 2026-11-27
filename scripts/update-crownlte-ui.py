#!/usr/bin/python3
"""Apply a locally compiled Crown UI update, with persistent-kit rollback.

Runs on the phone as root. Does not flash BOOT or update hardware daemons.
The base OS image keeps its own version; this updates the shell and native
apps. A systemd timer restores the previous UI unless --accept is called.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

BASE = Path('/run/ztos-host/unencrypted/ztos')
KIT = BASE / 'crownlte-connectivity-kit.tar.gz'
MANIFEST = BASE / 'crownlte-connectivity-kit.sha256'
UI = {
    'ztmetro': 'usr/local/bin/ztmetro',
    'ztmetro-session': 'usr/local/bin/ztmetro-session',
    'apps/ztapps': 'usr/local/bin/ztapps',
    'settings/ztsettings': 'usr/local/bin/ztsettings',
    'devtest/zrndevtest': 'usr/local/bin/zrndevtest',
    'devices/ztdevices': 'usr/local/bin/ztdevices',
    'files/ztfiles': 'usr/local/bin/ztfiles',
    'sound/ztsound': 'usr/local/bin/ztsound',
    'power/ztpower': 'usr/local/bin/ztpower',
    'osial/ztosial': 'usr/local/bin/ztosial',
    'camera/ztcamera': 'usr/local/bin/ztcamera',
    'store/ztstore': 'usr/local/bin/ztstore',
    'notifyd/ztnotifyd': 'usr/local/bin/ztnotifyd',
    'phone/ztphone': 'usr/local/bin/ztphone',
    'messages/ztmessages': 'usr/local/bin/ztmessages',
    'contacts/ztcontacts': 'usr/local/bin/ztcontacts',
    'splash/ztos-splash': 'usr/local/bin/ztos-splash',
    'auth/ztos-polkit-agent': 'usr/local/bin/ztos-polkit-agent',
    'sounds/ztos-sounds': 'usr/local/bin/ztos-sounds',
    'browser/superscan': 'usr/local/lib/crownlte/browser/superscan.bin',
}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.crown-new')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def guard():
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    if b'samsung,crownlte' not in Path('/proc/device-tree/compatible').read_bytes().split(b'\0'):
        raise SystemExit('Not a Crown')
    if run('findmnt', '-n', '-o', 'SOURCE', '/run/ztos-host') != '/dev/sda25':
        raise SystemExit('Unexpected host filesystem')
    run('mountpoint', '-q', '/run/ztos-state')
    for part in ('/dev/sda3', '/dev/sda10', '/dev/sda11', '/dev/sda12', '/dev/sda18', '/dev/sda19'):
        if run('blockdev', '--getro', part) != '1':
            raise SystemExit('Protected partition is writable: ' + part)


def restart_shell():
    Path('/run/greetd.run').unlink(missing_ok=True)
    run('systemctl', 'restart', 'greetd')


def backup_path(text):
    p = Path(text).resolve()
    parent = (BASE / 'ui-updates').resolve()
    if p.parent != parent or not (p / 'record.json').is_file():
        raise SystemExit('Not a recorded Crown UI backup')
    return p


def restore(backup):
    record = json.loads((backup / 'record.json').read_text())
    for item in record['files']:
        rel = item['path']
        if rel not in set(UI.values()) | {'usr/local/share/ztos/crown-ui-update.json'}:
            raise SystemExit('Unexpected rollback destination')
        target = Path('/') / rel
        if item['existed']:
            saved = backup / 'files' / rel
            if sha(saved) != item['previous_sha256']:
                raise SystemExit('Rollback file hash mismatch')
            atomic(target, saved.read_bytes(), item['mode'])
        else:
            target.unlink(missing_ok=True)
    if sha(backup / 'kit.tar.gz') != record['old_kit_sha256']:
        raise SystemExit('Rollback kit hash mismatch')
    atomic(KIT, (backup / 'kit.tar.gz').read_bytes(), 0o600)
    atomic(MANIFEST, (backup / 'kit.sha256').read_bytes(), 0o600)
    os.sync()
    restart_shell()
    print('PREVIOUS_CROWN_UI_RESTORED')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--build', type=Path)
    group.add_argument('--rollback', type=Path)
    group.add_argument('--auto-rollback', type=Path, help='timer rollback, skipped after acceptance')
    group.add_argument('--accept', type=Path)
    args = ap.parse_args()
    guard()
    if args.accept:
        backup = backup_path(args.accept)
        record = json.loads((backup / 'record.json').read_text())
        for item in record['files']:
            if sha(Path('/') / item['path']) != item['new_sha256']:
                raise SystemExit('Installed file hash mismatch')
        atomic(backup / 'accepted', b'accepted\n', 0o600)
        run('systemctl', 'stop', record['timer'] + '.timer')
        print('CROWN_UI_UPDATE_ACCEPTED')
        return
    if args.rollback or args.auto_rollback:
        backup = backup_path(args.rollback or args.auto_rollback)
        if args.rollback or not (backup / 'accepted').exists():
            restore(backup)
        return

    build = args.build.resolve()
    if not (build.parent / 'BUILD_OK').is_file():
        raise SystemExit('Native build/tests are not marked successful')
    old_sha = sha(KIT)
    if MANIFEST.read_text().split()[0] != old_sha:
        raise SystemExit('Current kit hash mismatch')
    if shutil.disk_usage(BASE).free < KIT.stat().st_size * 4 + 128 * 1024 * 1024:
        raise SystemExit('Insufficient host storage for rollback')
    if shutil.disk_usage('/run/ztos-state').free < 256 * 1024 * 1024:
        raise SystemExit('Insufficient persistent state storage')
    version = run(str(build / 'ztmetro'), '--version')
    if not version.startswith('ztMETRO 0.2.3 '):
        raise SystemExit('Unexpected shell version')
    payload = {}
    for source, rel in UI.items():
        data = (build / source).read_bytes()
        script = source == 'ztmetro-session'
        if not script and (data[:4] != b'\x7fELF' or data[18:20] != b'\xb7\x00'):
            raise SystemExit('Non-ARM64 payload: ' + source)
        if script and not data.startswith(b'#!/bin/sh'):
            raise SystemExit('Invalid session script')
        payload[rel] = (data, 0o755)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = BASE / 'ui-updates' / stamp
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    metadata = {'shell': version, 'upstream': '2360ba9ba5b34952d18faa33002f32bee018bebc',
                'applied_utc': stamp, 'scope': 'shell and native apps; base image and hardware services retained'}
    payload['usr/local/share/ztos/crown-ui-update.json'] = (json.dumps(metadata, indent=2).encode(), 0o644)
    record = {'files': [], 'old_kit_sha256': old_sha, 'timer': 'crown-ui-rollback-' + stamp.lower()}
    shutil.copy2(KIT, backup / 'kit.tar.gz')
    shutil.copy2(MANIFEST, backup / 'kit.sha256')
    for rel, (data, mode) in payload.items():
        target = Path('/') / rel
        if target.is_symlink():
            raise SystemExit('Destination is a symlink: ' + rel)
        item = {'path': rel, 'existed': target.exists(), 'mode': mode,
                'new_sha256': hashlib.sha256(data).hexdigest()}
        if target.exists():
            saved = backup / 'files' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            item['mode'] = target.stat().st_mode & 0o777
            item['previous_sha256'] = sha(saved)
        record['files'].append(item)
    atomic(backup / 'record.json', json.dumps(record, indent=2).encode(), 0o600)
    shutil.copy2(__file__, backup / 'apply.py')
    os.chmod(backup / 'apply.py', 0o700)
    next_kit = backup / 'new-kit.tar.gz'
    with tarfile.open(KIT, 'r:gz') as old, tarfile.open(next_kit, 'w:gz') as new:
        for member in old:
            name = member.name.removeprefix('./').rstrip('/')
            if name in payload:
                continue
            new.addfile(member, old.extractfile(member) if member.isfile() else None)
        for rel, (data, mode) in payload.items():
            member = tarfile.TarInfo('./' + rel); member.size = len(data); member.mode = mode
            new.addfile(member, io.BytesIO(data))
    run('systemd-run', '--unit=' + record['timer'], '--on-active=240s',
        '/usr/bin/python3', str(backup / 'apply.py'), '--auto-rollback', str(backup))
    try:
        for rel, (data, mode) in payload.items():
            atomic(Path('/') / rel, data, mode)
        atomic(KIT, next_kit.read_bytes(), 0o600)
        digest = sha(KIT)
        atomic(MANIFEST, (digest + '  ' + KIT.name + '\n').encode(), 0o600)
        os.sync()
        restart_shell()
    except Exception:
        restore(backup)
        raise
    print(json.dumps({'backup': str(backup), 'version': version, 'kit_sha256': digest,
                      'rollback_after_seconds': 240}, indent=2))


if __name__ == '__main__':
    main()
