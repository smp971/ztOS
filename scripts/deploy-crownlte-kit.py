#!/usr/bin/env python3
"""Update the verified kit on a Crown running writable state, retaining rollback."""
import argparse
import hashlib
import json
import paramiko
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--credentials', type=Path, required=True)
ap.add_argument('--kit', type=Path, required=True)
ap.add_argument('--apply-running', action='store_true')
a = ap.parse_args()
digest = hashlib.sha256(a.kit.read_bytes()).hexdigest()
manifest = a.kit.with_suffix('').with_suffix('.sha256')
if not manifest.exists() or manifest.read_text().split() != [digest, a.kit.name]:
    raise SystemExit('Local kit manifest mismatch')
c = json.loads(a.credentials.read_text())
s = paramiko.SSHClient(); s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    s.connect('172.16.42.1', username=c['user'], password=c['password'],
              timeout=5, look_for_keys=False, allow_agent=False)
    _, out, _ = s.exec_command("tr '\\000' '\\n' < /proc/device-tree/compatible | head -n1")
    if out.read().strip() != b'samsung,crownlte':
        raise SystemExit('Target is not Crown')
    staged = '/home/zerone/crown-kit-' + digest[:12] + '.tar.gz'
    ftp = s.open_sftp()
    try:
        ftp.put(str(a.kit), staged); ftp.chmod(staged, 0o600)
    finally:
        ftp.close()
    script = '''set -eu
dir=/run/ztos-host/unencrypted/ztos
test -d /run/ztos-state/upper
test "$(findmnt -n -T "$dir" -o SOURCE)" = /dev/sda25
findmnt -n -T "$dir" -o OPTIONS | tr , '\n' | grep -qx rw
test -d "$dir"; test ! -L "$dir"
cd "$dir"
kit=crownlte-connectivity-kit.tar.gz
check=crownlte-connectivity-kit.sha256
test ! -L "$kit"; test ! -L "$check"
sha256sum -c "$check"
old=$(sha256sum "$kit"); old=${old%% *}
case "$old" in *[!0-9a-f]*|'') exit 1;; esac
test "${#old}" = 64
backup="$kit.previous-$old"
backup_check="$check.previous-$old"
if [ ! -e "$backup" ]; then cp -p "$kit" "$backup"; cp -p "$check" "$backup_check"; fi
test "$(sha256sum "$backup" | cut -d' ' -f1)" = "$old"
cp STAGED "$kit.part"
test "$(sha256sum "$kit.part" | cut -d' ' -f1)" = DIGEST
printf '%s  %s\n' DIGEST "$kit" > "$check.part"
chmod 600 "$kit.part" "$check.part"
sync
mv "$kit.part" "$kit"
if ! mv "$check.part" "$check"; then
    cp -p "$backup" "$kit"; cp -p "$backup_check" "$check"; sync; exit 1
fi
sync
sha256sum -c "$check"
APPLY
rm -f STAGED
echo CROWN_KIT_UPDATED_WITH_ROLLBACK
'''.replace('STAGED', staged).replace('DIGEST', digest)
    script = script.replace('APPLY', 'tar -xzf "$kit" -C /\nsystemctl daemon-reload' if a.apply_running else ':')
    stdin, stdout, stderr = s.exec_command("sudo -k -S -p '' sh -s", timeout=60)
    stdin.write(c['password'] + '\n' + script); stdin.flush(); stdin.channel.shutdown_write()
    output = stdout.read(); errors = stderr.read(); code = stdout.channel.recv_exit_status()
    print(output.decode(), end='')
    if code:
        raise SystemExit(errors.decode() or f'Deployment failed: {code}')
finally:
    s.close()
