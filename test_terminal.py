"""Exercise the interactive editor through a UNIX pseudoterminal."""

import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import shlex
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest


EDITOR = Path(__file__).with_name("command_complete.py")
SHELL_INTEGRATION = EDITOR.with_name("shell-integration.sh")


def claim_terminal():
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


class Terminal:
    def __enter__(self):
        self.master, slave = pty.openpty()
        self.output = b""
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
        arguments = [sys.executable, str(EDITOR), "--", self.draft]
        env = dict(os.environ, TERM="xterm")
        if self.shell:
            arguments = self.shell
            env.update(PS1="TEST> ", HISTFILE="/dev/null")
        try:
            self.process = subprocess.Popen(
                arguments, stdin=slave, stdout=slave, stderr=slave, env=env,
                preexec_fn=claim_terminal if self.shell else None,
            )
        finally:
            os.close(slave)
        return self

    def __init__(self, draft="", shell=None):
        self.draft = draft
        self.shell = shell

    def __exit__(self, *_):
        if self.process.poll() is None:
            if self.shell:
                os.killpg(self.process.pid, 9)
            else:
                self.process.kill()
        self.process.wait(timeout=5)
        os.close(self.master)

    def send(self, keys):
        os.write(self.master, keys)

    def wait_for(self, text, start=0):
        deadline = time.monotonic() + 5
        while text not in self.output[start:]:
            timeout = max(0, deadline - time.monotonic())
            if not select.select([self.master], [], [], timeout)[0]:
                raise AssertionError(f"{text!r} missing from terminal output {self.output!r}")
            try:
                chunk = os.read(self.master, 8192)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                chunk = b""
            if not chunk:
                raise AssertionError(f"{text!r} missing from terminal output {self.output!r}")
            self.output += chunk

    def wait_for_draft(self, draft):
        leave_screen = b"\x1b[?1049l"
        self.wait_for(leave_screen)
        self.wait_for(draft + b"\r\n", self.output.index(leave_screen) + len(leave_screen))


class TerminalTests(unittest.TestCase):
    def test_tab_completes_a_unique_match(self):
        with Terminal("aws eks update-kub") as terminal:
            terminal.wait_for(b"Ctrl+C cancel")
            terminal.send(b"\t\r")
            terminal.wait_for_draft(b"aws eks update-kubeconfig ")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_down_selects_a_match_and_enter_leaves_it_editable(self):
        with Terminal("kubectl get pods --all") as terminal:
            terminal.wait_for(b"Ctrl+C cancel")
            terminal.wait_for(b"Matches (2)")
            terminal.wait_for(b"--allow-missing-template-keys")
            terminal.send(b"\x1bOB\x1bOB\r")
            terminal.send(b"--namespace=demo\r")
            terminal.wait_for_draft(b"kubectl get pods --allow-missing-template-keys --namespace=demo")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_typing_filters_suggestions_and_down_accepts_without_tab(self):
        with Terminal("kubectl get pods --all") as terminal:
            terminal.wait_for(b"Matches (2)")
            terminal.send(b"-n\x1bOB\r\r")
            terminal.wait_for_draft(b"kubectl get pods --all-namespaces ")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_enter_returns_draft_with_unselected_suggestions(self):
        with Terminal("kubectl get pods --all") as terminal:
            terminal.wait_for(b"Matches (2)")
            terminal.send(b"\r")
            terminal.wait_for_draft(b"kubectl get pods --all")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_page_keys_move_by_a_screen_of_matches(self):
        draft = "aws "
        candidates = subprocess.check_output(
            [sys.executable, str(EDITOR), "--matches", draft],
        ).splitlines()
        with Terminal(draft) as terminal:
            terminal.wait_for(b"Matches (")
            terminal.send(b"\x1b[6~\x1b[6~\x1b[5~\r\r")
            terminal.wait_for_draft(b"aws " + candidates[21] + b" ")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_nc_keeps_unlisted_arguments_and_advances_the_hint(self):
        with Terminal("nc ") as terminal:
            terminal.wait_for(b"Argument: Host")
            terminal.send(b"unlisted.invalid ")
            # Curses can keep the final "t" already drawn by "Host".
            terminal.wait_for(b"Por")
            terminal.send(b"15432\r")
            terminal.wait_for_draft(b"nc unlisted.invalid 15432")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_nc_shows_named_values_and_preserves_hand_typed_flags(self):
        with Terminal("nc -w ") as terminal:
            terminal.wait_for(b"Argument: Timeout in seconds")
            terminal.send(b"3 -l -z\r")
            terminal.wait_for_draft(b"nc -w 3 -l -z")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_nc_probe_count_hint_comes_from_installed_catalog(self):
        with Terminal("nc -L ") as terminal:
            terminal.wait_for(b"Argument: Number of probes")
            terminal.send(b"3\r")
            terminal.wait_for_draft(b"nc -L 3")
            self.assertEqual(terminal.process.wait(timeout=5), 0)

    def test_enter_returns_literal_shell_text_without_executing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "would-have-executed"
            draft = f"touch {marker}"
            with Terminal(draft) as terminal:
                terminal.wait_for(b"Ctrl+C cancel")
                terminal.send(b"\r")
                terminal.wait_for_draft(draft.encode())
                self.assertEqual(terminal.process.wait(timeout=5), 0)
            self.assertFalse(marker.exists())

    @unittest.skipUnless(Path("/bin/zsh").exists(), "requires macOS zsh")
    def test_zsh_returns_a_completed_draft_to_the_edit_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "marker"
            draft = shlex.join(["touch", str(marker)]).encode()
            with Terminal(shell=["/bin/zsh", "-f", "-i"]) as terminal:
                terminal.wait_for(b"TEST> ")
                before_source = len(terminal.output)
                terminal.send(f"source {shlex.quote(str(SHELL_INTEGRATION))}\r".encode())
                terminal.wait_for(b"TEST> ", before_source)
                terminal.send(b"touch \x07")
                terminal.wait_for(b"Enter return text")
                terminal.send(draft.removeprefix(b"touch ") + b"\r")
                terminal.wait_for(b"\x1b[?1049l")
                after_editor = terminal.output.index(b"\x1b[?1049l")
                terminal.wait_for(draft, after_editor)
                self.assertFalse(marker.exists())
                terminal.send(b"-edited\r")
                terminal.wait_for(b"TEST> ", len(terminal.output))
                self.assertTrue(marker.with_name("marker-edited").exists())
                self.assertFalse(marker.exists())

    @unittest.skipUnless(Path("/bin/zsh").exists(), "requires macOS zsh")
    def test_zsh_cancel_restores_the_original_draft(self):
        with Terminal(shell=["/bin/zsh", "-f", "-i"]) as terminal:
            terminal.wait_for(b"TEST> ")
            before_source = len(terminal.output)
            terminal.send(f"source {shlex.quote(str(SHELL_INTEGRATION))}\r".encode())
            terminal.wait_for(b"TEST> ", before_source)
            terminal.send(b"nc -L \x07")
            terminal.wait_for(b"Argument: Number of probes")
            terminal.send(b"12\x04")
            leave_screen = b"\x1b[?1049l"
            terminal.wait_for(leave_screen)
            after_editor = terminal.output.index(leave_screen) + len(leave_screen)
            terminal.wait_for(b"TEST> nc -L", after_editor)
            self.assertNotIn(b"nc -L 12", terminal.output[after_editor:])
            before_reopen = len(terminal.output)
            terminal.send(b"\x07")
            terminal.wait_for(b"Argument: Number of probes", before_reopen)
            terminal.send(b"\x04")
