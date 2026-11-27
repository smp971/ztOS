#!/usr/bin/python3
"""Read-only Crown snapshot. Run as root for boot hashes and the full journal.

No services are started/restarted, and no device settings are written. The
JSON records a timestamp and boot ID so saved evidence cannot be mistaken for
a later live observation. Network identities and modem identifiers are omitted.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def read(path, limit=262144):
    try:
        with open(path, 'rb') as f:
            return f.read(limit).decode(errors='replace').strip()
    except OSError as e:
        return {'error': str(e)}


def redact(text):
    text = re.sub(r'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', '[MAC]', text)
    text = re.sub(r'\b\d{15,16}\b', '[identifier]', text)
    return re.sub(r'(?i)((?:androidboot\.)?(?:serialno|serial|imei|imsi|iccid)=)\S+', r'\1[redacted]', text)


def run(*args, timeout=12, env=None):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, 'LC_ALL': 'C', **(env or {})})
        return {'exit': p.returncode, 'stdout': redact(p.stdout[-131072:]),
                'stderr': redact(p.stderr[-4096:])}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error': str(e)}


def shell_state():
    result = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal() or read(entry / 'comm') != 'ztmetro':
            continue
        env = read(entry / 'environ')
        if isinstance(env, str):
            env = [x for x in env.split('\0') if x.startswith((
                'WLR_', 'PAN_', 'GBM_', 'LIBGL_', 'GALLIUM_', 'MESA_', 'WAYLAND_DISPLAY='))]
        renderer = []
        log = entry / 'fd/1'
        try:
            target = log.resolve()
            if target.is_file() and target.name.startswith('ztmetro.log'):
                with target.open('rb') as stream:
                    stream.seek(max(0, target.stat().st_size - 1024 * 1024))
                    renderer = [redact(line) for line in stream.read().decode(errors='replace').splitlines()
                                if re.search(r'GLES renderer|GL_RENDERER|OpenGL renderer|GL renderer:|renderer: Mali|renderer: llvmpipe', line)][-5:]
        except OSError:
            pass
        result.append({'pid': int(entry.name), 'executable': str((entry / 'exe').resolve()),
                       'environment': env, 'renderer_log': renderer,
                       'status': read(entry / 'status', 8192)})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--hash-boot', action='store_true', help='read and hash BOOT without writing it')
    ap.add_argument('--boot-prefix-bytes', type=int, action='append', default=[],
                    help='also hash this image-length prefix of stored BOOT (repeatable)')
    args = ap.parse_args()
    if any(n < 1 or n > 64 * 1024 * 1024 for n in args.boot_prefix_bytes):
        ap.error('BOOT prefix lengths must be between 1 byte and 64 MiB')
    if args.boot_prefix_bytes and not args.hash_boot:
        ap.error('--boot-prefix-bytes requires --hash-boot')
    compatible = read('/proc/device-tree/compatible')
    if not isinstance(compatible, str) or 'samsung,crownlte' not in compatible.split('\0'):
        raise SystemExit('Refusing a target that is not samsung,crownlte')
    cmdline = read('/proc/cmdline')
    data = {
        'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'boot_id': read('/proc/sys/kernel/random/boot_id'),
        'device': {'compatible': compatible, 'model': read('/proc/device-tree/model')},
        'kernel': run('uname', '-a'), 'os_release': read('/etc/os-release'),
        'cmdline': redact(cmdline) if isinstance(cmdline, str) else cmdline,
        'uptime': read('/proc/uptime'), 'memory': read('/proc/meminfo'),
        'mounts': run('findmnt', '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'),
        'storage': run('df', '-hT'), 'block_devices': run('lsblk', '-o', 'NAME,SIZE,RO,FSTYPE,MOUNTPOINTS'),
        'failed_units': run('systemctl', '--failed', '--no-pager', '--plain'),
        'current_boot_errors': run('journalctl', '-b', '-p', 'err', '--no-pager', '-n', '80'),
        'kernel_log': run('dmesg', '--level=err,warn'),
        'services': run('systemctl', 'show', '-p', 'Id,ActiveState,SubState,Result,ExecMainStatus',
                        'greetd', 'sshd', 'NetworkManager', 'bluetooth', 'crown-audio',
                        'crown-sensorhub', 'crown-sensord', 'crown-haptic', 'crown-network', 'ztos-iald'),
        'shell': shell_state(), 'inputs': read('/proc/bus/input/devices'),
        'sound_cards': read('/proc/asound/cards'), 'sound_devices': read('/proc/asound/pcm'),
        'video_devices': sorted(str(p) for pattern in ('video*', 'media*') for p in Path('/dev').glob(pattern)),
        'wifi': run('nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device', 'status'),
        'bluetooth_powered': run('busctl', 'get-property', 'org.bluez', '/org/bluez/hci0',
                                 'org.bluez.Adapter1', 'Powered'),
    }
    data['battery'] = {str(p): read(p) for p in Path('/sys/class/power_supply').glob('*/uevent')}
    data['drm'] = [{
        'name': p.name, 'driver': str((p / 'device/driver').resolve()),
        **{key: read(p / key) for key in ('status', 'enabled', 'modes') if (p / key).exists()},
    } for p in Path('/sys/class/drm').iterdir() if p.name != 'version']
    status = read('/run/ztoscorenetworking/status')
    keys = {'sim', 'bars', 'registered', 'tech', 'data', 'data_on'}
    data['modem'] = {k: v for line in status.splitlines() if '=' in line
                     for k, v in [line.split('=', 1)] if k in keys} if isinstance(status, str) else status
    shells = data['shell']
    if shells:
        pid = shells[0]['pid']
        data['wayland_sockets'] = run('find', '/run/user', '-maxdepth', '2', '-type', 's', '-name', 'wayland-*')
        data['shell_open_devices'] = run('ls', '-l', f'/proc/{pid}/fd')
    if os.geteuid() == 0:
        try:
            import pwd
            user = pwd.getpwnam('zerone')
            data['pipewire'] = run('runuser', '-u', user.pw_name, '--', 'env',
                                   f'XDG_RUNTIME_DIR=/run/user/{user.pw_uid}', 'wpctl', 'status')
        except KeyError:
            pass
    if args.hash_boot:
        h = hashlib.sha256()
        prefixes = sorted(set(args.boot_prefix_bytes))
        prefix_hashes = {}
        offset = 0
        try:
            with open('/dev/sda10', 'rb') as f:
                while True:
                    size = min(1024 * 1024, prefixes[0] - offset) if prefixes else 1024 * 1024
                    chunk = f.read(size)
                    if not chunk:
                        break
                    h.update(chunk)
                    offset += len(chunk)
                    if prefixes and offset == prefixes[0]:
                        prefix_hashes[str(prefixes.pop(0))] = h.hexdigest()
            data['stored_boot_sha256'] = h.hexdigest()
            data['stored_boot_prefix_sha256'] = prefix_hashes
            data['stored_boot_note'] = 'Identifies stored BOOT; does not prove it equals the image loaded at startup.'
        except OSError as e:
            data['stored_boot_sha256'] = {'error': str(e)}
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
