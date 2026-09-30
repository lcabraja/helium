#!/usr/bin/env python3
"""Failure and source-integrity checks for the local publisher."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from prepare_release_tree import patch_paths, read_git_files
from release import Release, SPARKLE_NS, digest_config, feed_version


class ReleaseTests(unittest.TestCase):
    def test_build_numbers_ignore_display_version(self):
        xml = f'<rss xmlns:sparkle="{SPARKLE_NS}"><channel><item><sparkle:version>12</sparkle:version><sparkle:shortVersionString>0.18.1.1</sparkle:shortVersionString></item><item><sparkle:version>9</sparkle:version></item></channel></rss>'
        self.assertEqual(feed_version(xml), 12)
        with self.assertRaises(ValueError):
            feed_version(xml.replace('>12<', '>193dd00<'))

    def test_config_hash_is_independent_of_key_order(self):
        self.assertEqual(digest_config({'a': 1, 'b': 2}), digest_config({'b': 2, 'a': 1}))

    def test_git_originals_preserve_binary_and_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = b'\x00\xff\r\n\x00binary'
            (root / 'binary').write_bytes(binary)
            subprocess.run(['git', 'init', '-q', root], check=True)
            subprocess.run(['git', '-C', root, 'add', '.'], check=True)
            subprocess.run(['git', '-C', root, '-c', 'user.name=Test', '-c',
                            'user.email=test@example.invalid', 'commit', '-qm', 'base'], check=True)
            (root / 'binary').write_bytes(b'modified')
            self.assertEqual(dict(read_git_files(root, ['binary', 'missing'])),
                             {'binary': binary, 'missing': None})

    def test_added_patch_path_stays_new_even_when_later_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            patch = Path(folder) / 'example.patch'
            patch.write_text('--- /dev/null\n+++ b/new.cc\n@@ -0,0 +1 @@\n+x\n'
                             '--- a/new.cc\n+++ b/new.cc\n@@ -1 +1 @@\n-x\n+y\n')
            self.assertEqual(patch_paths([patch]), {'new.cc': False})
            patch.write_text('--- a/a\n+++ b/../../outside\n')
            with self.assertRaises(ValueError):
                patch_paths([patch])

    def test_upload_failure_never_changes_feed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = root / 'site'
            (site / 'mac').mkdir(parents=True)
            old_feed = site / 'mac/appcast-arm64.xml'
            old_feed.write_bytes(b'previous signed feed')
            candidate = root / 'new.xml'
            candidate.write_bytes(b'new signed feed')
            release = Release({'repository': 'lcabraja/helium', 'pages_branch': 'gh-pages',
                               'update_origin': 'https://lcabraja.github.io/helium/'}, root, root, 1)
            release.site = site
            release.site_revision = 'abc'
            release.api = Mock(return_value=[])
            commands = []

            def run(*command, **unused):
                commands.append(command)
                if 'ls-remote' in command:
                    return 'abc\trefs/heads/gh-pages\n'
                if command[:3] == ('gh', 'release', 'upload'):
                    raise RuntimeError('upload failed')
                return ''

            release.run = run
            with self.assertRaisesRegex(RuntimeError, 'upload failed'):
                release.publish({'tag': 'macos-2', 'source_revision': 'def',
                                 'display_version': '0.18.1.1', 'build_number': 2},
                                root / 'new.zip', candidate, root / 'notes.md')
            self.assertEqual(old_feed.read_bytes(), b'previous signed feed')
            self.assertFalse(any('push' in command for command in commands))

    def test_competing_publisher_stops_before_release_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release = Release({'repository': 'lcabraja/helium', 'pages_branch': 'gh-pages',
                               'update_origin': 'https://lcabraja.github.io/helium/'}, root, root, 1)
            release.site = root
            release.site_revision = 'old'
            release.run = Mock(return_value='new\trefs/heads/gh-pages\n')
            release.api = Mock()
            with self.assertRaisesRegex(ValueError, 'Another release'):
                release.publish({}, root / 'new.zip', root / 'new.xml', root / 'notes.md')
            release.api.assert_not_called()

    def test_draft_from_another_commit_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release = Release({'repository': 'lcabraja/helium', 'pages_branch': 'gh-pages',
                               'update_origin': 'https://lcabraja.github.io/helium/'}, root, root, 1)
            release.site = root
            release.run = Mock(return_value='')
            release.api = Mock(return_value=[{'tag_name': 'macos-2', 'draft': True,
                                             'target_commitish': 'other'}])
            with self.assertRaisesRegex(ValueError, 'another source commit'):
                release.publish({'tag': 'macos-2', 'source_revision': 'ours',
                                 'display_version': '0.18.1.1', 'build_number': 2},
                                root / 'new.zip', root / 'new.xml', root / 'notes.md')
            self.assertFalse(any(call.args[:3] == ('gh', 'release', 'upload')
                                 for call in release.run.call_args_list))


if __name__ == '__main__':
    unittest.main()
