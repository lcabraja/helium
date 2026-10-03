#!/usr/bin/env python3
"""Build and publish a signed macOS fork release locally, without a CI build."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from prepare_release_tree import prepare

ROOT = Path(__file__).resolve().parents[2]
SPARKLE_NS = 'http://www.andymatuschak.org/xml-namespaces/sparkle'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def feed_version(data):
    versions = [element.text for element in ET.fromstring(data).iter(
        '{' + SPARKLE_NS + '}version')]
    if any(not value or not value.isdecimal() for value in versions):
        raise ValueError('Our update feed must contain integer build numbers')
    return max([int(value) for value in versions], default=0)


class Release:
    def __init__(self, config, platform, work, jobs, key_file=None):
        self.config = config
        self.platform = platform
        self.source = platform / 'build/src'
        self.work = work
        self.jobs = jobs
        self.key_file = key_file.resolve() if key_file else None
        self.log = None
        self.site = None
        self.site_revision = None
        self.original_feed = None
        self.feed_url = config['update_origin'] + 'mac/appcast-arm64.xml'

    def run(self, *command, capture=False, cwd=None):
        command = [str(arg) for arg in command]
        if self.log:
            self.log.write('$ ' + ' '.join(command) + '\n')
            self.log.flush()
        result = subprocess.run(command, cwd=cwd, check=False, text=True,
                                stdout=subprocess.PIPE if capture else self.log,
                                stderr=self.log)
        if result.returncode:
            raise RuntimeError(f'{command[0]} failed with exit {result.returncode}; see release.log')
        return result.stdout if capture else None

    def api(self, endpoint, payload=None):
        command = ['gh', 'api', endpoint]
        if payload is not None:
            payload_path = self.work / 'api-request.json'
            payload_path.write_text(json.dumps(payload))
            command += ['--method', 'POST', '--input', str(payload_path)]
        return json.loads(self.run(*command, capture=True))

    def pages_request(self, payload=None):
        command = ['gh', 'api', f'repos/{self.config["repository"]}/pages']
        if payload is not None:
            payload_path = self.work / 'api-request.json'
            payload_path.write_text(json.dumps(payload))
            command += ['--method', 'POST', '--input', str(payload_path)]
        if self.log:
            self.log.write('$ ' + ' '.join(command) + '\n')
            self.log.flush()
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode and self.log:
            self.log.write(result.stderr)
        return result

    def ensure_pages(self):
        expected = {'branch': self.config['pages_branch'], 'path': '/'}
        result = self.pages_request()
        if result.returncode and 'HTTP 404' in result.stderr:
            created = self.pages_request({'source': expected, 'build_type': 'legacy'})
            # GitHub can enable Pages between inspection and creation. Read
            # its configuration again instead of treating that conflict as a
            # failed publication or replacing an existing site's settings.
            if created.returncode and 'HTTP 409' not in created.stderr:
                raise RuntimeError('Could not enable GitHub Pages; see release.log')
            for attempt in range(3):
                result = self.pages_request()
                if not result.returncode or 'HTTP 404' not in result.stderr:
                    break
                if attempt < 2:
                    time.sleep(1)
        if result.returncode:
            raise RuntimeError('Could not inspect GitHub Pages; feed branch was pushed')
        pages = json.loads(result.stdout)
        if pages.get('source') != expected or pages.get('build_type') != 'legacy':
            raise ValueError('Existing Pages source differs; refusing to replace another site')

    def preflight(self, allow_dirty=False):
        if sys.platform != 'darwin':
            raise ValueError('Local releases require macOS with Xcode')
        for name in ('gh', 'git', 'xcrun', 'codesign'):
            if not shutil.which(name):
                raise FileNotFoundError(f'Missing {name}')
        if not (self.source / '.git').exists():
            raise ValueError('Use a prepared Git-based Chromium workspace; see README.md')
        actual = self.run('git', '-C', self.source, 'show', 'HEAD:chrome/VERSION', capture=True)
        version = '.'.join(line.split('=', 1)[1] for line in actual.strip().splitlines())
        if version != (ROOT / 'chromium_version.txt').read_text().strip():
            raise ValueError('Prepared Chromium version does not match this repository')
        origin = self.run('git', '-C', ROOT, 'remote', 'get-url', 'origin', capture=True).strip()
        expected = self.config['repository']
        if origin not in (f'https://github.com/{expected}', f'https://github.com/{expected}.git',
                          f'git@github.com:{expected}.git'):
            raise ValueError('Origin must be the configured fork, never upstream')
        if not allow_dirty and self.run('git', '-C', ROOT, 'status', '--porcelain', capture=True):
            raise ValueError('Commit the repository changes before making a release')
        identities = self.run('security', 'find-identity', '-v', '-p', 'codesigning', capture=True)
        matching = [line for line in identities.splitlines()
                    if self.config['certificate_sha1'] in line]
        if len(matching) != 1 or f"({self.config['team_id']})" not in matching[0]:
            raise ValueError('Configured Developer ID identity is not available in Keychain')
        if 'Developer ID Application:' not in matching[0]:
            raise ValueError('A Developer ID Application certificate is required')

    def tools(self):
        version = self.config['sparkle_tools_version']
        directory = self.platform / f'build/local-release-tools/Sparkle-{version}'
        marker = directory / 'verified-sha256.txt'
        expected = self.config['sparkle_tools_sha256']
        if not marker.is_file() or marker.read_text().strip() != expected:
            if directory.exists():
                raise ValueError(f'Unverified Sparkle tool directory: {directory}')
            directory.parent.mkdir(parents=True, exist_ok=True)
            archive = directory.parent / f'Sparkle-{version}.tar.xz'
            url = f'https://github.com/sparkle-project/Sparkle/releases/download/{version}/Sparkle-{version}.tar.xz'
            self.run('curl', '--fail', '--location', '--silent', '--show-error', url, '-o', archive)
            if sha256(archive) != expected:
                raise ValueError('Sparkle tool download checksum mismatch')
            with tempfile.TemporaryDirectory(prefix='sparkle-tools-', dir=directory.parent) as temporary:
                staging = Path(temporary) / 'distribution'
                staging.mkdir()
                with tarfile.open(archive) as contents:
                    contents.extractall(staging, filter='data')
                (staging / marker.name).write_text(expected + '\n')
                staging.rename(directory)
        if self.key_file:
            self.verify_key_file()
        else:
            public = self.run(directory / 'bin/generate_keys', '--account',
                              self.config['sparkle_account'], '-p', capture=True).strip()
            if public != self.config['sparkle_public_key']:
                raise ValueError('Sparkle Keychain key does not match the embedded public key')
        return directory / 'bin'

    def verify_key_file(self):
        # A file is an explicit fallback for builders without unattended
        # Keychain access. Check its public identity before generating a feed.
        if self.key_file.stat().st_mode & 0o077:
            raise ValueError('The private key file must have owner-only permissions')
        seed = base64.b64decode(self.key_file.read_text().strip(), validate=True)
        if len(seed) != 32:
            raise ValueError('The private key file must contain a Sparkle Ed25519 seed')
        openssl = Path('/opt/homebrew/opt/openssl@3/bin/openssl')
        if not openssl.exists():
            openssl = shutil.which('openssl')
        if not openssl:
            raise FileNotFoundError('Key-file validation requires OpenSSL 3')
        # The secret is sent through stdin, never a process argument or log.
        private_der = bytes.fromhex('302e020100300506032b657004220420') + seed
        result = subprocess.run([str(openssl), 'pkey', '-inform', 'DER', '-pubout', '-outform', 'DER'],
                                input=private_der, capture_output=True, check=True)
        if base64.b64encode(result.stdout[-32:]).decode() != self.config['sparkle_public_key']:
            raise ValueError('The private key file does not match the embedded public key')

    def signing_args(self):
        if self.key_file:
            return ['--ed-key-file', str(self.key_file)]
        return ['--account', self.config['sparkle_account']]

    def checkout_site(self):
        self.site = self.work / 'site'
        self.site.mkdir(exist_ok=True)
        self.run('git', 'init', '-q', self.site)
        self.run('git', '-C', self.site, 'remote', 'add', 'origin',
                 f"https://github.com/{self.config['repository']}.git")
        branch = self.config['pages_branch']
        refs = self.run('git', '-C', self.site, 'ls-remote', 'origin',
                        f'refs/heads/{branch}', capture=True).strip()
        if refs:
            self.run('git', '-C', self.site, 'fetch', '--depth=1', 'origin', branch)
            self.run('git', '-C', self.site, 'checkout', '-q', '-b', branch, 'FETCH_HEAD')
            self.site_revision = self.run('git', '-C', self.site, 'rev-parse', 'HEAD', capture=True).strip()
        else:
            self.run('git', '-C', self.site, 'checkout', '--orphan', branch)
        feed = self.site / 'mac/appcast-arm64.xml'
        if feed.exists():
            self.original_feed = feed.read_bytes()
            return feed_version(self.original_feed)
        return 0

    def allocate_build(self, published):
        counter = self.platform / 'build/local-release-counter.txt'
        previous = int(counter.read_text()) if counter.exists() else 0
        number = max(published, previous) + 1
        pending = counter.with_suffix('.tmp')
        pending.write_text(str(number) + '\n')
        pending.replace(counter)
        return number

    def build(self, number):
        print('Replaying source patches and translations...', flush=True)
        chromium_revision = prepare(ROOT, self.platform, self.work, sys.executable, self.run)
        print('Preparing the pinned user-scripts manager dependencies...', flush=True)
        self.run(sys.executable, self.source / 'components/helium_user_scripts/setup_ui.py',
                 cwd=self.source)
        print('Configuring and building Helium with Sparkle...', flush=True)
        args = '\n'.join(path.read_text() for path in (
            ROOT / 'flags.gn', self.platform / 'flags.macos.gn', ROOT / 'docs/macos-development.gn'))
        args += '\nenable_sparkle = true\nsparkle_automatic_checks = true\n'
        args += 'sparkle_ed_key = ' + json.dumps(self.config['sparkle_public_key']) + '\n'
        args += 'helium_browser_update_origin = ' + json.dumps(self.config['update_origin']) + '\n'
        (self.source / 'out/Default/args.gn').write_text(args)
        self.run(self.source / 'buildtools/mac/gn', 'gen', 'out/Default',
                 '--fail-on-unused-args', cwd=self.source)
        os.environ['SISO_PATH'] = str(self.source / 'third_party/siso/cipd/siso')
        self.run('caffeinate', '-i', sys.executable, 'third_party/depot_tools/autoninja.py',
                 '-C', 'out/Default', f'-j{self.jobs}', 'chrome', 'chrome/installer/mac:mac', cwd=self.source)
        revision = self.run('git', '-C', ROOT, 'rev-parse', 'HEAD', capture=True).strip()
        tag = f'macos-{number}'
        archive_name = f'Helium-Fork-arm64-{number}-{revision[:7]}.zip'
        package = self.work / 'package'
        print('Signing, notarizing and verifying the release...', flush=True)
        self.run(sys.executable, ROOT / 'packaging/macos/sign_app.py',
                 '--chromium-src', self.source, '--source-app', self.source / 'out/Default/Helium.app',
                 '--output-dir', package, '--identity', self.config['certificate_sha1'],
                 '--team-id', self.config['team_id'], '--bundle-id', self.config['bundle_id'],
                 '--profile-dir', self.config['profile_directory'],
                 '--notary-profile', self.config['notary_profile'], '--build-number', number,
                 '--feed-url', self.feed_url, '--public-key', self.config['sparkle_public_key'],
                 '--archive-name', archive_name)
        metadata = json.loads((package / 'package-metadata.json').read_text())
        metadata.update({'source_revision': revision, 'chromium_revision': chromium_revision,
                         'platform_revision': self.run('git', '-C', self.platform, 'rev-parse', 'HEAD', capture=True).strip(),
                         'tag': tag, 'archive_name': archive_name,
                         'repository': self.config['repository'], 'build_number': number,
                         'minimum_macos': '15.0', 'architecture': 'arm64',
                         'xcode': self.run('xcodebuild', '-version', capture=True).strip(),
                         'config_sha256': digest_config(self.config)})
        (self.work / 'release-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        return metadata

    def verify(self, metadata):
        if metadata['config_sha256'] != digest_config(self.config):
            raise ValueError('Release configuration changed; rebuild before publishing')
        if metadata['repository'] != self.config['repository'] or not metadata['notarized']:
            raise ValueError('Only notarized releases for this fork may be published')
        package = self.work / 'package'
        archive = package / metadata['archive_name']
        if sha256(archive) != metadata['archive_sha256']:
            raise ValueError('Release archive checksum mismatch')
        extraction = self.work / 'verify-archive'
        if extraction.exists():
            shutil.rmtree(extraction)
        self.run('ditto', '-x', '-k', archive, extraction)
        app = extraction / 'Helium Fork.app'
        self.run('codesign', '--verify', '--deep', '--strict', app)
        self.run('xcrun', 'stapler', 'validate', app)
        self.run('spctl', '--assess', '--type', 'execute', app)
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        for key, expected in (
                ('CFBundleIdentifier', self.config['bundle_id']),
                ('CrProductDirName', self.config['profile_directory']),
                ('SUPublicEDKey', self.config['sparkle_public_key']),
                ('SUFeedURL', self.feed_url), ('CFBundleVersion', str(metadata['build_number']))):
            if info.get(key) != expected:
                raise ValueError(f'Incorrect release property: {key}')
        self.run('codesign', '--verify', '-R',
                 f'=identifier "{self.config["bundle_id"]}" and anchor apple generic and certificate leaf[subject.OU] = "{self.config["team_id"]}"', app)
        return archive

    def generate_feed(self, metadata, archive, tools):
        folder = self.work / 'appcast'
        folder.mkdir(exist_ok=True)
        staged = folder / archive.name
        if not staged.exists():
            os.link(archive, staged)
        feed = folder / 'appcast-arm64.xml'
        if self.original_feed:
            feed.write_bytes(self.original_feed)
        elif feed.exists():
            feed.unlink()
        prefix = f"https://github.com/{self.config['repository']}/releases/download/{metadata['tag']}/"
        self.run(tools / 'generate_appcast', *self.signing_args(),
                 '--download-url-prefix', prefix, '--maximum-deltas', '0', '-o', feed, folder)
        # Verify the generated feed and archive signature using Sparkle itself.
        self.run(tools / 'sign_update', *self.signing_args(), '--verify', feed)
        root = ET.fromstring(feed.read_bytes())
        items = root.findall('./channel/item')
        item = next((item for item in items if item.findtext('{' + SPARKLE_NS + '}version')
                     == str(metadata['build_number'])), None)
        if item is None or feed_version(feed.read_bytes()) != metadata['build_number']:
            raise ValueError('The generated feed does not advertise this build')
        enclosure = item.find('enclosure')
        if enclosure is None or enclosure.get('url') != prefix + archive.name:
            raise ValueError('The feed download URL is incorrect')
        if int(enclosure.get('length', '0')) != archive.stat().st_size:
            raise ValueError('The feed download size is incorrect')
        self.run(tools / 'sign_update', *self.signing_args(), '--verify',
                 archive, enclosure.get('{' + SPARKLE_NS + '}edSignature'))
        return feed

    def publish(self, metadata, archive, feed, notes):
        repo = self.config['repository']
        branch = self.config['pages_branch']
        remote = self.run('git', '-C', self.site, 'ls-remote', 'origin',
                          f'refs/heads/{branch}', capture=True).strip()
        current = remote.split()[0] if remote else None
        if current != self.site_revision:
            raise ValueError('Another release changed the feed. Retry --publish-only to merge it.')
        number = metadata['build_number']
        existing = self.api(f'repos/{repo}/releases?per_page=100')
        release = next((item for item in existing if item['tag_name'] == metadata['tag']), None)
        assets = [archive, archive.with_suffix('.sha256'), self.work / 'release-metadata.json']
        if release is None:
            self.run('gh', 'release', 'create', metadata['tag'], '--repo', repo, '--draft',
                     '--target', metadata['source_revision'], '--title',
                     f"Helium Fork {metadata['display_version']} · build {number}", '--notes-file', notes)
            self.run('gh', 'release', 'upload', metadata['tag'], *assets, '--repo', repo)
        elif release['draft']:
            if release['target_commitish'] != metadata['source_revision']:
                raise ValueError('This draft belongs to another source commit; allocate a new build')
            for asset in release.get('assets', []):
                if asset['name'] == archive.name and asset.get('digest') != 'sha256:' + metadata['archive_sha256']:
                    raise ValueError('Another build already uploaded this archive name; do not replace it')
            self.run('gh', 'release', 'upload', metadata['tag'], *assets, '--repo', repo, '--clobber')
        # A retry after a Pages failure reuses the public archive unchanged.
        # Publishing the archive first prevents clients receiving a feed with
        # missing downloads. A later Pages failure leaves the old feed usable.
        if release is None or release['draft']:
            self.run('gh', 'release', 'edit', metadata['tag'], '--repo', repo, '--draft=false', '--latest')
        download = self.work / 'verify-download.zip'
        url = f'https://github.com/{repo}/releases/download/{metadata["tag"]}/{archive.name}'
        self.run('curl', '--fail', '--location', '--silent', '--show-error', '--retry', '3', url, '-o', download)
        if sha256(download) != metadata['archive_sha256']:
            raise ValueError('Public download checksum mismatch; feed was not updated')
        download.unlink()
        target = self.site / 'mac/appcast-arm64.xml'
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(feed, target)
        (self.site / '.nojekyll').touch()
        (self.site / 'index.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Helium Fork updates</title>'
            '<h1>Helium Fork updates</h1><p>Apple Silicon, macOS 15 or newer.</p>'
            f'<p><a href="{url}">Download build {number}</a></p>'
            f'<p><a href="https://github.com/{repo}/releases">Release history</a></p>')
        self.run('git', '-C', self.site, 'add', '.')
        if self.run('git', '-C', self.site, 'status', '--porcelain', capture=True).strip():
            self.run('git', '-C', self.site, 'commit', '-m', f'Publish Helium Fork macOS build {number}')
            # Never force-push the feed. A competing publication must be reviewed.
            self.run('git', '-C', self.site, 'push', 'origin', f'HEAD:refs/heads/{branch}')
        self.ensure_pages()
        print('Waiting for GitHub Pages to serve the signed feed...', flush=True)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.feed_url + f'?build={number}', timeout=15) as response:
                    published = response.read()
                if published == feed.read_bytes():
                    (self.work / 'published.json').write_text(json.dumps(
                        {'release': f'https://github.com/{repo}/releases/tag/{metadata["tag"]}',
                         'feed': self.feed_url, 'build': number}, indent=2) + '\n')
                    print(f'Release published: https://github.com/{repo}/releases/tag/{metadata["tag"]}\n'
                          f'Update feed: {self.feed_url}', flush=True)
                    return
            except (OSError, ValueError):
                pass
            time.sleep(10)
        raise RuntimeError('GitHub Pages has not served the new feed yet. Check the Pages deployment; no rebuild is needed.')


def digest_config(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform-tree', type=Path, default=ROOT.parent)
    parser.add_argument('--work-dir', type=Path, help='New output directory for this run')
    parser.add_argument('--jobs', type=int, default=10)
    parser.add_argument('--notes-file', type=Path, help='Public release notes, Markdown')
    parser.add_argument('--sparkle-key-file', type=Path,
                        help='Explicit owner-only private-key backup instead of Keychain signing')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--build-only', action='store_true', help='Build/notarize without publishing')
    mode.add_argument('--prepare-only', action='store_true', help='Replay sources without building or publishing')
    mode.add_argument('--publish-only', type=Path, help='Publish an existing successful build directory')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    config = json.loads((ROOT / 'packaging/macos/release-config.json').read_text())
    platform = args.platform_tree.resolve()
    os.environ.setdefault('DEPOT_TOOLS_UPDATE', '0')
    os.environ.setdefault('VPYTHON_BYPASS', 'manually managed python not supported by chrome operations')
    os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
    os.environ.setdefault('DEVELOPER_DIR', '/Applications/Xcode.app/Contents/Developer')
    work = args.publish_only or args.work_dir or (
        platform.parent / 'artifacts/local-releases' / time.strftime('%Y%m%d-%H%M%S'))
    work = work.resolve()
    if not args.publish_only:
        work.mkdir(parents=True, exist_ok=False)
    if args.publish_only and not (work / 'release-metadata.json').is_file():
        parser.error('--publish-only requires a completed build directory')
    print(f'Release output and log: {work}', flush=True)
    release = Release(config, platform, work, args.jobs, args.sparkle_key_file)
    lock_path = platform / 'build/local-release.lock'
    with lock_path.open('a') as lock, (work / 'release.log').open('a') as log:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release.log = log
        release.preflight(allow_dirty=args.prepare_only or bool(args.publish_only))
        if args.prepare_only:
            prepare(ROOT, platform, work, sys.executable, release.run)
            return
        tools = release.tools()
        if args.publish_only and (work / 'site').exists():
            shutil.rmtree(work / 'site')
        latest = release.checkout_site()
        if args.publish_only:
            metadata = json.loads((work / 'release-metadata.json').read_text())
            if metadata['build_number'] < latest:
                raise ValueError('This build is older than the current feed')
        else:
            # A published release must identify a commit that actually exists
            # in our GitHub repository before we spend time compiling it.
            revision = release.run('git', '-C', ROOT, 'rev-parse', 'HEAD', capture=True).strip()
            release.api(f"repos/{config['repository']}/commits/{revision}")
            metadata = release.build(release.allocate_build(latest))
        archive = release.verify(metadata)
        feed = release.generate_feed(metadata, archive, tools)
        notes = work / 'release-notes.md'
        if args.notes_file:
            shutil.copyfile(args.notes_file, notes)
        elif not notes.exists():
            notes.write_text(f"Helium Fork {metadata['display_version']}, build {metadata['build_number']}.\n\n"
                             f"Source: {metadata['source_revision']}\n\n"
                             'Developer ID signed, notarized and stapled. Apple Silicon, macOS 15 or newer.\n')
        if args.build_only:
            print(f'Build verified. Publish without rebuilding:\n{ROOT}/packaging/macos/release.sh --publish-only {work}', flush=True)
            return
        release.publish(metadata, archive, feed, notes)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f'Release stopped: {error}', file=sys.stderr)
        sys.exit(1)
