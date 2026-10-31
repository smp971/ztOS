#!/usr/bin/env python3
"""Prepare a Crown-specific modem module source tree; never access a phone."""
import argparse
import importlib.util
import shutil
import struct
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stock-dtb', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--sys-rev', type=lambda s: int(s, 0), required=True,
                    help='board strap value read from the stock modem GPIO ordering')
    args = ap.parse_args()
    if not 0 <= args.sys_rev <= 255:
        raise SystemExit('Board strap revision must fit its 8-bit mailbox field')
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('crown_verify', root / 'scripts/verify-crownlte.py')
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    tree = verify.fdt(args.stock_dtb.read_bytes())
    if b'Crown' not in tree['/'].get('model', b''):
        raise SystemExit('Stock DTB must describe Crown')
    wanted = (b'samsung,exynos-shd-ipc-mailbox\0', b'samsung,exynos-shm_ipc\0',
              b'sec_modem,modem_pdata\0')
    paths = []
    for compatible in wanted:
        matches = [p for p, props in tree.items() if props.get('compatible') == compatible]
        if len(matches) != 1:
            raise SystemExit(f'Expected exactly one modem node: {compatible!r}')
        paths += matches
    mailbox, shmem, modem = paths
    if tree[mailbox]['reg'] != struct.pack('>III', 0, 0x14170000, 0x180):
        raise SystemExit('Unexpected mailbox register range')
    expected = {'shmem,cp_size': 0x7900000, 'shmem,vss_size': 0x700000,
                'shmem,ipc_offset': 0x8000000, 'shmem,ipc_size': 0x500000,
                'shmem,zmb_offset': 0x8500000, 'shmem,zmb_size': 0xb00000}
    for key, value in expected.items():
        if tree[shmem].get(key) != struct.pack('>I', value):
            raise SystemExit(f'Unexpected Crown shared memory: {key}')
    children = [p for p in tree if p.startswith(modem + '/iodevs/')]
    if len(children) != 21:
        raise SystemExit('Expected 21 stock modem I/O devices')
    if args.output.exists():
        raise SystemExit('Output already exists; refusing replacement')
    shutil.copytree(root / 'modem/zrn-modem', args.output)
    lines = ['/dts-v1/;', '/plugin/;', '/ {', 'fragment@0 {', 'target-path = "/";', '__overlay__ {']
    # Only board revision is copied from the root. No identity/chosen data.
    for key in ('model_info-system_rev', 'model_info-hw_rev'):
        value = tree['/'][key]
        lines.append(f'{key} = [{value.hex(" ")}];')

    def emit(path):
        lines.append(path.rsplit('/', 1)[-1] + ' {')
        if path == modem:
            lines.append(f'zrn,sys_rev = <{args.sys_rev}>;')
        for key, value in tree[path].items():
            # Stock GPIO phandles belong to another tree. As in the upstream
            # module, omit only revision GPIOs and local phandle declarations.
            if key in ('phandle', 'linux,phandle', 'gpios', 'pinctrl-names'):
                continue
            if key.startswith('pinctrl-') or key.endswith('-gpios') or key == 'interrupt-parent':
                raise SystemExit(f'Unresolved reference in modem node: {path}:{key}')
            if key == 'interrupts':
                cells = list(struct.unpack('>' + 'I' * (len(value) // 4), value))
                if len(cells) % 3:
                    raise SystemExit('Invalid GIC interrupt specifier')
                for i in range(2, len(cells), 3):
                    if cells[i] == 0:
                        cells[i] = 4  # vendor default is mainline level-high
                value = struct.pack('>' + 'I' * len(cells), *cells)
            lines.append(f'{key} = [{value.hex(" ")}];' if value else f'{key};')
        for child in tree:
            if child.rsplit('/', 1)[0] == path:
                emit(child)
        lines.append('};')

    for path in paths:
        emit(path)
    lines += ['};', '};', '};']
    (args.output / 'zrn-modem-overlay.dts').write_text('\n'.join(lines) + '\n')
    board = args.output / 'zrn_board.c'
    content = board.read_text()
    content = content.replace('ret = zrn_shm_find_memory();',
        'if (!of_machine_is_compatible("samsung,crownlte"))\n\t\treturn -ENODEV;\n\n\tret = zrn_shm_find_memory();')
    board.write_text(content)
    kbuild = args.output / 'Kbuild'
    kbuild.write_text(kbuild.read_text().replace('KOR', 'EUR'))
    print('Crown modem sources prepared: 21 I/O devices; hardware test pending')


if __name__ == '__main__':
    main()
