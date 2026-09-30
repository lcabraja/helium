#!/usr/bin/env python3
"""Replay maintained patches without discarding the local Chromium build cache.

This works with a prepared Git-based platform workspace. Chromium upgrades and
DEPS downloads still use the platform's normal preparation procedure.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path


def digest(path):
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def series(directory):
    return [directory / line.split('#', 1)[0].strip()
            for line in (directory / 'series').read_text().splitlines()
            if line.split('#', 1)[0].strip()]


def patch_paths(patches):
    paths = {}
    for patch in patches:
        lines = patch.read_text().splitlines()
        for before, after in zip(lines, lines[1:]):
            if not before.startswith('--- ') or not after.startswith('+++ '):
                continue
            old = before[4:].split()[0]
            new = after[4:].split()[0]
            name = (new if new != '/dev/null' else old).split('/', 1)[1]
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError(f'Unsafe patch path: {name}')
            paths.setdefault(name, old != '/dev/null')
    return paths


def original_repository(source, name):
    repo = (source / name).parent
    while not (repo / '.git').exists():
        if repo == source:
            raise ValueError(f'No Git base for {name}')
        repo = repo.parent
    return repo


def read_git_files(repository, names):
    """Read original blobs in one Git process, including binary resources."""
    requests = [f'HEAD:{name}' for name in names]
    data = subprocess.run(['git', '-C', str(repository), 'cat-file', '--batch'],
                          input=('\n'.join(requests) + '\n').encode(),
                          capture_output=True, check=True).stdout
    offset = 0
    for name in names:
        end = data.index(b'\n', offset)
        header = data[offset:end].split()
        offset = end + 1
        if header[-1] == b'missing':
            yield name, None
            continue
        if header[1] != b'blob':
            raise ValueError(f'Expected a file, got {header[1]!r}: {name}')
        size = int(header[2])
        yield name, data[offset:offset + size]
        offset += size + 1


def cached_original(cache, name):
    if name.startswith('third_party/ublock/'):
        with zipfile.ZipFile(cache / 'ublock-origin-1.75.0.zip') as archive:
            return archive.read('uBlock0.chromium/' + name[len('third_party/ublock/'):])
    if name.startswith('third_party/sparkle/'):
        with tarfile.open(cache / 'sparkle-v2.10.0.tar.gz') as archive:
            suffix = '/' + name[len('third_party/sparkle/'):]
            matches = [member for member in archive.getmembers()
                       if member.name.endswith(suffix) and member.isfile()]
            if len(matches) == 1:
                return archive.extractfile(matches[0]).read()
    raise FileNotFoundError(f'No pristine source for {name}; prepare the matching platform workspace')


def prepare(repository, platform, run_dir, python, run):
    source = platform / 'build/src'
    state_path = platform / 'build/local-release-source.json'
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    patches = series(repository / 'patches') + series(platform / 'patches')
    if (source / 'chrome/test/data/webui').exists():
        patches += [repository / 'docs' / name for name in (
            'container-tabs-webui-tests.patch', 'macos-development-webui-tests.patch',
            'macos-development-cpp-tests.patch')]
    paths = patch_paths(patches)
    paths.update({name: True for name in previous.get('files', {}) if name not in paths})
    # All localization inputs must share the same fingerprint substitutions.
    tracked = run('git', '-C', source, 'ls-files', capture=True).splitlines()
    paths.update({name: True for name in tracked if name.endswith(('.grd', '.grdp', '.xtb'))})
    paths['chrome/VERSION'] = True
    paths['OWNERS'] = True
    revision = run('git', '-C', source, 'rev-parse', 'HEAD', capture=True).strip()
    if previous and previous['chromium_revision'] != revision:
        raise ValueError('Chromium changed; prepare a fresh platform workspace before releasing')
    substitution_inputs = {name: digest(repository / name) for name in (
        'domain_regex.list', 'domain_substitution.list', 'utils/name_substitution_utils.py')}
    if previous and previous['substitution_inputs'] != substitution_inputs:
        raise ValueError('Global substitutions changed; prepare a fresh platform workspace')
    for name, expected in previous.get('files', {}).items():
        if digest(source / name) != expected:
            raise ValueError(f'Generated source has local edits: {name}. Maintain the change in a patch first.')

    with tempfile.TemporaryDirectory(prefix='helium-source-', dir=run_dir) as temporary:
        fixture = Path(temporary)
        # Seed GRIT support before replaying patches, so a patch to GRIT itself
        # cannot be overwritten by a copy from the previous prepared tree.
        shutil.copytree(source / 'tools/grit', fixture / 'tools/grit', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        grouped = {}
        for name, needs_base in paths.items():
            if needs_base:
                origin = original_repository(source, name)
                grouped.setdefault(origin, {})[str((source / name).relative_to(origin))] = name
        for origin, files in grouped.items():
            for relative, content in read_git_files(origin, files):
                name = files[relative]
                if content is None:
                    # A removed added-file patch has no original blob.
                    if name in previous.get('files', {}) and name not in patch_paths(patches):
                        continue
                    content = cached_original(platform / 'build/download_cache', name)
                path = fixture / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

        patch_bin = shutil.which('gpatch') or shutil.which('patch')
        if not patch_bin:
            raise FileNotFoundError('GNU patch is required; brew install gpatch')
        for patch in patches:
            run(patch_bin, '--batch', '--forward', '--fuzz=0', '--no-backup-if-mismatch',
                '-p1', '-d', fixture, '-i', patch)
        subset = run_dir / 'domain-substitution-subset.list'
        subset.write_text('\n'.join(name for name in (repository / 'domain_substitution.list')
                                     .read_text().splitlines() if (fixture / name).is_file()) + '\n')
        run(python, repository / 'utils/domain_substitution.py', 'apply', '-r',
            repository / 'domain_regex.list', '-f', subset, fixture)
        run(python, repository / 'utils/name_substitution.py', '--sub', '-t', fixture)
        run(python, repository / 'utils/i18n_apply.py', '-t', fixture)
        run(python, repository / 'utils/helium_version.py', '--tree', repository,
            '--platform-tree', platform, '--chromium-tree', fixture)
        run(python, repository / 'utils/generate_resources.py',
            repository / 'resources/generate_resources.txt', repository / 'resources')
        for root, listing in ((platform, 'platform_resources.txt'),
                              (repository, 'helium_resources.txt')):
            for line in (root / 'resources' / listing).read_text().splitlines():
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                resource, target = line.split()
                paths[target] = True
                dest = fixture / target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / 'resources' / resource, dest)

        # Only copy changed files, so Ninja/Siso can keep incremental outputs.
        hashes = {}
        changed = []
        backup = run_dir / 'previous-source'
        for name in sorted(paths):
            current = source / name
            candidate = fixture / name
            hashes[name] = digest(candidate)
            if digest(current) == hashes[name]:
                continue
            if current.is_file():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(current, saved)
            if candidate.is_file():
                mode = current.stat().st_mode & 0o777 if current.exists() else 0o644
                current.parent.mkdir(parents=True, exist_ok=True)
                pending = current.with_name(current.name + '.release-new')
                shutil.copyfile(candidate, pending)
                pending.chmod(mode)
                os.replace(pending, current)
            elif current.exists():
                current.unlink()
            changed.append(name)
        state = {'chromium_revision': revision, 'substitution_inputs': substitution_inputs,
                 'files': hashes}
        pending = state_path.with_suffix('.tmp')
        pending.write_text(json.dumps(state, indent=2) + '\n')
        pending.replace(state_path)
        (run_dir / 'source-changes.json').write_text(json.dumps(changed, indent=2) + '\n')
        print(f'Replayed {len(patches)} patches; updated {len(changed)} source files.', flush=True)
    return revision
