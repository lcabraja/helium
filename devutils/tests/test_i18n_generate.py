# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Regression tests for messages extracted from patch context and additions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import i18n_generate

sys.path.pop(0)


def test_inline_context_does_not_capture_next_message():
    """A complete context message must close before the next addition."""
    hunk = ''' <message name="OLD" desc="Old">Existing label</message>
+<message name="NEW" desc="New">
+  New label
+</message>
 <message name="AFTER" desc="After">Another label</message>'''
    assert list(i18n_generate.extract_strings_from_hunk(hunk)) == [('NEW', 'New', None, 'New label')
                                                                   ]


def test_inline_additions_and_modified_body():
    """Extract single-line additions and changes within an existing message."""
    hunk = '''+<message name="ONE" desc="One">One line</message>
 <message name="CHANGED" desc="Changed" meaning="label">
-  Before
+  After <ph name="COUNT">$1<ex>2</ex></ph>
 </message>
 <message name="UNTOUCHED" desc="Untouched">No change</message>'''
    assert list(i18n_generate.extract_strings_from_hunk(hunk)) == [
        ('ONE', 'One', None, 'One line'),
        ('CHANGED', 'Changed', 'label', 'After <ph name="COUNT">$1<ex>2</ex></ph>')
    ]


def test_multiline_metadata_and_partial_context():
    """Ignore incomplete old messages and preserve metadata changes."""
    hunk = '''   An old fragment
 </message>
 <message name="META"
-  desc="Old description"
+  desc="New description"
   meaning="test">
   Body on closing line</message>'''
    assert list(i18n_generate.extract_strings_from_hunk(hunk)) == [('META', 'New description',
                                                                    'test', 'Body on closing line')]


def test_clean_messages_preserve_literal_plus():
    """Onboarding XML has no diff prefixes, including a literal plus sign."""
    source = '''<message name="PLUS" desc="Plus">
+1 item
</message>'''
    assert list(i18n_generate.extract_strings_from_hunk(source, clean=True)) == [('PLUS', 'Plus',
                                                                                  None, '+1 item')]


def test_angle_bracket_in_description():
    """A quoted angle bracket is not the end of the opening tag."""
    hunk = ''' +<message name="SIZE" desc="Shown when size > 30MB">
+  Too large
+</message>'''.lstrip()
    assert list(i18n_generate.extract_strings_from_hunk(hunk)) == [
        ('SIZE', 'Shown when size > 30MB', None, 'Too large')
    ]


def test_added_literal_plus_and_blank_line():
    """Remove just one diff marker and retain blank lines inside a message."""
    hunk = '''+<message name="TEXT" desc="Text">
++1 item
+
+Another line
+</message>'''
    assert list(i18n_generate.extract_strings_from_hunk(hunk)) == [('TEXT', 'Text', None,
                                                                    '+1 item\n\nAnother line')]
