"""Exercise cs through a real terminal, with a small documented database."""

import fcntl
from collections import deque
import curses
import gzip
import json
import os
from pathlib import Path
import pty
import select
import signal
import shlex
import struct
import sys
import tempfile
import termios
import subprocess
import time
import unittest

from command_search_index import write_database
from test_search_session import session
from test_terminal import Terminal


EDITOR = Path(__file__).with_name('command_search.py')


class QueryInputTests(unittest.TestCase):
    def test_buffered_text_is_edited_before_new_terminal_input(self):
        from command_search import coalesce_query_input
        class Input:
            def __init__(self):
                self.keys = deque('t')
            def nodelay(self, enabled):
                pass
            def get_wch(self):
                if self.keys:
                    return self.keys.popleft()
                raise curses.error()
        line, cursor, immediate = coalesce_query_input(Input(), '', 0, 'h', deque('os'))
        self.assertEqual((line, cursor, immediate), ('host', 4, False))

    def test_buffered_control_key_is_left_for_the_main_event_loop(self):
        from command_search import coalesce_query_input
        class Input:
            def nodelay(self, enabled):
                pass
            def get_wch(self):
                raise AssertionError('new input must wait for the buffered control key')
        keys = deque(['o', '\x12', 'x'])
        line, cursor, immediate = coalesce_query_input(Input(), '', 0, 'h', keys)
        self.assertEqual((line, cursor, immediate), ('ho', 2, False))
        self.assertEqual(list(keys), ['\x12', 'x'])


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


class GatedSearchTerminal(SearchTerminal):
    """Hold the real background database call until the test releases it."""
    def __init__(self, query='', fixed_clock=False):
        super().__init__(query)
        self.gate = self.path / 'release-search'
        script = f'''
import sys,time
from pathlib import Path
import command_search
from command_search_index import DatabaseSearchIndex
from search_scheduler import HybridSearch
original = DatabaseSearchIndex.search_background
def gated(self, query, cancelled):
    while not Path({str(self.gate)!r}).exists() and not cancelled():
        time.sleep(.002)
    return original(self, query, cancelled)
DatabaseSearchIndex.search_background = gated
if {fixed_clock!r}:
    command_search.HybridSearch = lambda backend: HybridSearch(backend, clock=lambda: 0.0)
sys.argv = {self.shell[1:]!r}
sys.exit(command_search.main())
'''
        self.shell = [sys.executable, '-B', '-c', script]


class SearchTerminalTests(unittest.TestCase):
    def test_pasted_text_ending_in_a_partial_word_keeps_the_idle_delay(self):
        with GatedSearchTerminal(fixed_clock=True) as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'reach x')
            terminal.wait_for(b'Waiting for typing to pause')
            self.assertNotIn(b'Searching...', terminal.output)
            terminal.send(b' ')
            terminal.wait_for(b'Searching...')
            terminal.send(b'\x03')
            terminal.wait_for(b'\x1b[?1049l')

    def test_backtracking_after_pending_enter_follows_the_buffered_draft(self):
        with GatedSearchTerminal('reach') as terminal:
            terminal.wait_for(b'Searching...')
            terminal.send(b'\x1bOB\rhost\x12')
            # Keep the query blocked while all of the burst reaches the editor.
            time.sleep(.05)
            start = len(terminal.output)
            terminal.gate.touch()
            terminal.wait_for(b'FROZEN RESULTS', start)
            terminal.send(b'\r\r')
            terminal.wait_for_draft(b'ping host')

    def test_terminal_disconnect_exits_without_relying_on_sighup(self):
        for pending in (False, True):
            with self.subTest(pending=pending):
                fixture = GatedSearchTerminal('network') if pending else SearchTerminal('network')
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
                process = subprocess.Popen(fixture.shell, stdin=slave, stdout=slave, stderr=slave,
                                           env=dict(os.environ, TERM='xterm'))
                os.close(slave)
                try:
                    marker = b'Searching...' if pending else b'13 matches'
                    output = b''
                    deadline = time.monotonic() + 5
                    while marker not in output and time.monotonic() < deadline:
                        if select.select([master], [], [], .1)[0]:
                            output += os.read(master, 8192)
                    self.assertIn(marker, output)
                    os.close(master)
                    master = None
                    process.wait(timeout=2)
                finally:
                    if master is not None:
                        os.close(master)
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                    fixture.directory.cleanup()

    def test_space_dispatches_even_when_the_idle_clock_has_not_advanced(self):
        with GatedSearchTerminal(fixed_clock=True) as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'reach')
            terminal.wait_for(b'Waiting for typing to pause')
            terminal.send(b' ')
            terminal.wait_for(b'Searching...')
            terminal.gate.touch()
            terminal.wait_for(b'Test network reachability')
            terminal.send(b'\x04')
            terminal.wait_for(b'\x1b[?1049l')

    def test_typing_and_cancel_work_while_the_database_is_blocked(self):
        with GatedSearchTerminal('network') as terminal:
            terminal.wait_for(b'Searching...')
            start = len(terminal.output)
            terminal.send(b'\x15zzresponsive')
            terminal.wait_for(b'zzresponsive', start)
            self.assertFalse(terminal.gate.exists())
            terminal.send(b'\x03')
            terminal.wait_for(b'\x1b[?1049l')
            self.assertEqual(terminal.process.wait(timeout=5), 130)

    def test_pending_enter_uses_current_results_and_preserves_following_draft_text(self):
        with GatedSearchTerminal('network') as terminal:
            terminal.wait_for(b'Searching...')
            terminal.send(b'\x15reach\x1bOB\r')
            terminal.send(b'example.invalid\r')
            self.assertNotIn(b'FROZEN REFERENCE', terminal.output)
            terminal.gate.touch()
            terminal.wait_for_draft(b'ping example.invalid')
            self.assertEqual(terminal.process.wait(timeout=5), 0)

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

    def test_ctrl_c_during_repeated_redraws_always_cancels(self):
        for _ in range(80):
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

    def test_switching_commands_resets_reference_selection_without_a_crash(self):
        with SearchTerminal('network') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\rping ')
            terminal.wait_for(b'LIVE COMPLETION')
            terminal.send(b'\x1b[17~\x1bOA\x1b[17~\x15docker stop ')
            terminal.wait_for(b'FROZEN REFERENCE - docker stop')
            terminal.send(b'\x1b[17~\r\r')
            terminal.wait_for_draft(b'docker stop ')
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_recipe_shows_the_next_required_step(self):
        with SearchTerminal('paced') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\x1bOB\r')
            terminal.wait_for(b'Next: -i')
            terminal.send(b'\x03')
            terminal.wait_for(b'\x1b[?1049l')
            self.assertEqual(terminal.process.wait(timeout=5), 130)

    def test_literal_pipeline_draft_can_be_returned_without_execution(self):
        with SearchTerminal('network') as terminal:
            terminal.wait_for(b'LIVE SEARCH')
            terminal.send(b'\rping host | cat\r')
            terminal.wait_for_draft(b'ping host | cat')
            self.assertEqual(terminal.process.wait(timeout=5), 0)

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

    def check_shell_handoff(self, shell, cancel=False, vi_pause=False):
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
                setup = (f'COMMAND_SEARCH_EXECUTABLE={shlex.quote(str(wrapper))} source '
                         f'{shlex.quote(str(integration))}')
                if vi_pause:
                    setup = 'set -o vi; ' + setup + '; ' + setup
                terminal.send((setup + '\r').encode())
                terminal.wait_for(b'TEST> ', start)
                terminal.send('empty café\x18'.encode())
                if vi_pause:
                    time.sleep(.8)
                terminal.send(b'\x07')
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

    def test_bash_vi_mode_search_prefix_survives_a_pause_and_repeated_sourcing(self):
        bash = '/opt/homebrew/bin/bash' if Path('/opt/homebrew/bin/bash').exists() else '/bin/bash'
        major = subprocess.check_output([bash, '-c', 'printf "%s" "${BASH_VERSINFO[0]}"'], text=True)
        if int(major) < 5:
            self.skipTest('requires Bash 5+')
        self.check_shell_handoff([bash, '--noprofile', '--norc', '-i'], vi_pause=True)

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
