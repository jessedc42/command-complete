"""Exercise cs through a real terminal, with a small documented database."""

import fcntl
import gzip
import json
from pathlib import Path
import signal
import shlex
import struct
import sys
import tempfile
import termios
import subprocess
import unittest

from command_search_index import write_database
from test_search_session import session
from test_terminal import Terminal


EDITOR = Path(__file__).with_name('command_search.py')


class SearchTerminal(Terminal):
    def __init__(self, query=''):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        source = session().index
        source.catalog.commands['touch'] = {'description': 'Create empty files.', 'flags': {}}
        catalog = self.path / 'catalog.json.gz'
        with gzip.open(catalog, 'wt') as f:
            json.dump({'commands': source.catalog.commands}, f)
        database = self.path / 'search.db'
        write_database(database, source.catalog, source.metadata)
        super().__init__(shell=[sys.executable, str(EDITOR), '--catalog', str(catalog),
                                '--database', str(database), '--', query])

    def __exit__(self, *args):
        super().__exit__(*args)
        self.directory.cleanup()


class SearchTerminalTests(unittest.TestCase):
    def test_typing_filters_search_and_selecting_returns_an_editable_draft(self):
        with SearchTerminal() as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'reach')
            terminal.wait_for(b'Test network reachability')
            terminal.send(b'\x1bOB\r')
            terminal.wait_for(b'LIVE COMPLETION')
            terminal.send(b'example.invalid\r')
            terminal.wait_for_draft(b'ping example.invalid')
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_manual_freeze_waits_for_complete_path(self):
        with SearchTerminal('network') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\r')
            terminal.wait_for(b'FROZEN RESULTS')
            terminal.send(b'docker ')
            terminal.send(b'stop ')
            terminal.wait_for(b'LIVE COMPLETION')
            terminal.send(b'demo\r')
            terminal.wait_for_draft(b'docker stop demo')

    def test_f6_selects_a_frozen_flag_and_returns_focus_to_the_draft(self):
        with SearchTerminal('network') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\rping ')
            terminal.wait_for(b'LIVE COMPLETION')
            terminal.send(b'\x1b[17~\x1bOB\x1bOC\r')
            terminal.wait_for(b'Enter Count')
            terminal.send(b'4\r\r')
            terminal.wait_for_draft(b'ping -c 4 ')

    def test_guided_combination_prompts_each_value_before_returning(self):
        with SearchTerminal('paced') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\x1bOB\r')
            terminal.wait_for(b'Enter Count')
            terminal.send(b'4\r')
            terminal.wait_for(b'Enter Seconds')
            terminal.send(b'0.5\r\r')
            terminal.wait_for_draft(b'ping -c 4 -i 0.5 ')

    def test_ctrl_r_returns_through_both_stages(self):
        with SearchTerminal('network') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\rping ')
            terminal.wait_for(b'LIVE COMPLETION')
            start = len(terminal.output)
            terminal.send(b'\x12')
            terminal.wait_for(b'FROZEN RESULTS', start)
            start = len(terminal.output)
            terminal.send(b'\x12')
            terminal.wait_for(b'LIVE SEARCH', start)
            terminal.send(b'\x03')
            terminal.wait_for(b'\x1b[?1049l')
            self.assertEqual(terminal.process.wait(timeout=5), 130)

    def test_small_terminal_resize_keeps_cancel_working(self):
        with SearchTerminal('network') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\rping ')
            terminal.wait_for(b'LIVE COMPLETION')
            fcntl.ioctl(terminal.master, termios.TIOCSWINSZ, struct.pack('HHHH', 8, 34, 0, 0))
            terminal.process.send_signal(signal.SIGWINCH)
            terminal.send(b'\x03')
            terminal.wait_for(b'\x1b[?1049l')
            self.assertEqual(terminal.process.wait(timeout=5), 130)

    def test_queued_navigation_after_typing_is_not_inserted_as_unicode(self):
        with SearchTerminal() as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'reach\x1bOB\r')
            terminal.wait_for(b'LIVE COMPLETION')
            terminal.send(b'example.invalid\r')
            terminal.wait_for_draft(b'ping example.invalid')

    def test_quoted_shell_syntax_is_returned_as_literal_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'must-not-exist'
            with SearchTerminal('reach') as terminal:
                terminal.wait_for(b'LIVE SEARCH')
                terminal.send(b'\x1bOB\r')
                terminal.wait_for(b'LIVE COMPLETION')
                value = f"'$(touch {marker})'"
                terminal.send(value.encode() + b'\r')
                terminal.wait_for_draft(('ping ' + value).encode())
                self.assertFalse(marker.exists())

    def check_shell_handoff(self, shell, cancel=False):
        integration = EDITOR.with_name('shell-integration.sh')
        fixture = SearchTerminal()
        try:
            wrapper = fixture.path / 'command-search'
            # Remove the fixture's trailing empty query so user input remains exact.
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.join(fixture.shell[:-2]) + ' "$@"\n')
            wrapper.chmod(0o755)
            marker = fixture.path / 'marker-é'
            with Terminal(shell=shell) as terminal:
                terminal.wait_for(b'TEST> ')
                start = len(terminal.output)
                terminal.send((f'COMMAND_SEARCH_EXECUTABLE={shlex.quote(str(wrapper))} source '
                               f'{shlex.quote(str(integration))}\r').encode())
                terminal.wait_for(b'TEST> ', start)
                terminal.send('empty café\x18\x07'.encode())
                terminal.wait_for(b'LIVE SEARCH')
                if cancel:
                    terminal.send(b'\x04')
                    terminal.wait_for(b'\x1b[?1049l')
                    terminal.wait_for('empty café'.encode(), terminal.output.index(b'\x1b[?1049l'))
                else:
                    terminal.send(b'\x1bOB\r')
                    terminal.wait_for(b'LIVE COMPLETION')
                    argument = shlex.quote(str(marker)).encode()
                    terminal.send(argument + b'\r')
                    terminal.wait_for(b'\x1b[?1049l')
                    # Readline may display UTF-8 bytes as octal escapes in locale C.
                    # Verify the actual returned filename by editing and executing below.
                    terminal.wait_for(b'TEST> touch ', terminal.output.index(b'\x1b[?1049l'))
                    self.assertFalse(marker.exists())
                    start = len(terminal.output)
                    terminal.send(b'-edited\r')
                    terminal.wait_for(b'TEST> ', start)
                    self.assertTrue(marker.with_name('marker-é-edited').exists())
                    self.assertFalse(marker.exists())
        finally:
            fixture.directory.cleanup()

    def test_bash_hotkey_seeds_query_and_returns_unicode_draft_without_executing(self):
        bash = '/opt/homebrew/bin/bash' if Path('/opt/homebrew/bin/bash').exists() else '/bin/bash'
        major = subprocess.check_output([bash, '-c', 'printf "%s" "${BASH_VERSINFO[0]}"'], text=True)
        if int(major) < 5:
            self.skipTest('requires Bash 5+')
        self.check_shell_handoff([bash, '--noprofile', '--norc', '-i'])

    def test_bash_byte_locale_returns_unicode_draft_with_cursor_at_end(self):
        bash = '/opt/homebrew/bin/bash' if Path('/opt/homebrew/bin/bash').exists() else '/bin/bash'
        major = subprocess.check_output([bash, '-c', 'printf "%s" "${BASH_VERSINFO[0]}"'], text=True)
        if int(major) < 5:
            self.skipTest('requires Bash 5+')
        self.check_shell_handoff(['/usr/bin/env', 'LC_ALL=C', bash, '--noprofile', '--norc', '-i'])

    def test_bash_search_cancel_restores_original_query(self):
        bash = '/opt/homebrew/bin/bash' if Path('/opt/homebrew/bin/bash').exists() else '/bin/bash'
        major = subprocess.check_output([bash, '-c', 'printf "%s" "${BASH_VERSINFO[0]}"'], text=True)
        if int(major) < 5:
            self.skipTest('requires Bash 5+')
        self.check_shell_handoff([bash, '--noprofile', '--norc', '-i'], cancel=True)

    @unittest.skipUnless(Path('/bin/zsh').exists(), 'requires zsh')
    def test_zsh_hotkey_returns_editable_unicode_draft(self):
        self.check_shell_handoff(['/bin/zsh', '-f', '-i'])

    @unittest.skipUnless(Path('/bin/zsh').exists(), 'requires zsh')
    def test_zsh_search_cancel_restores_original_unicode_query(self):
        self.check_shell_handoff(['/bin/zsh', '-f', '-i'], cancel=True)


if __name__ == '__main__':
    unittest.main()
