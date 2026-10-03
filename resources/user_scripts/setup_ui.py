#!/usr/bin/env python3
"""Prepare the pinned UI dependency and npm packages before compiling Helium."""
import argparse
from pathlib import Path
import shutil
import subprocess

UI_REVISION = '27b61261db77096d1c2611cbd0bfab0286528494'


def run(*command, cwd):
    subprocess.run(command, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update-lock', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    bun = shutil.which('bun')
    if not bun:
        raise SystemExit('Install Bun with mise, then run this script again.')
    vendor = root / 'vendor/ui'
    if not vendor.exists():
        vendor.parent.mkdir(exist_ok=True)
        run('git', 'clone', '--no-checkout', 'https://github.com/da-facility/ui.git', str(vendor), cwd=root)
        run('git', 'checkout', '--detach', UI_REVISION, cwd=vendor)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=vendor, text=True).strip()
    if revision != UI_REVISION:
        raise SystemExit('The cached UI dependency differs from the pinned revision.')
    if not (vendor / 'dist/index.js').exists():
        run(bun, 'install', '--frozen-lockfile', cwd=vendor)
        run(bun, 'run', 'build', cwd=vendor)
    flags = [] if args.update_lock else ['--frozen-lockfile']
    run(bun, 'install', *flags, cwd=root)


if __name__ == '__main__':
    main()
