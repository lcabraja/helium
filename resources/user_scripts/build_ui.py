#!/usr/bin/env python3
"""Bundle the manager and generate the component extension's packaged assets."""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import zlib


def icon(path):
    size = 128
    lines = [((48, 38), (23, 64)), ((23, 64), (48, 90)),
             ((80, 38), (105, 64)), ((105, 64), (80, 90)),
             ((72, 30), (56, 98))]

    def distance(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
        return ((x - a[0] - t * dx) ** 2 + (y - a[1] - t * dy) ** 2) ** .5

    data = bytearray()
    for y in range(size):
        data.append(0)
        for x in range(size):
            coverage = max(0, min(1, 4.5 - min(distance(x, y, a, b) for a, b in lines)))
            data.extend((int(104 + 141 * coverage), int(121 + 124 * coverage),
                         int(219 + 26 * coverage), 255))

    def chunk(kind, value):
        return struct.pack('!I', len(value)) + kind + value + struct.pack('!I', zlib.crc32(kind + value))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 6, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(data)) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if not (root / 'node_modules/acorn/package.json').exists():
        raise SystemExit(f'Prepare dependencies first: python3 {root}/setup_ui.py')
    bun = shutil.which('bun')
    if not bun:
        raise SystemExit('Bun is required. Activate the mise build environment.')
    subprocess.run([bun, 'run', 'build'], cwd=root, check=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ('manager.js', 'manager.css', 'background.js'):
        shutil.copyfile(root / 'dist' / name, args.out / name)
    for name in ('manifest.json', 'manager.html'):
        shutil.copyfile(root / name, args.out / name)
    icon(args.out / 'icon.png')


if __name__ == '__main__':
    main()
