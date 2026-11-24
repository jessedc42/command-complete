from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


INSTALLER = Path(__file__).with_name('install_commands.py')


class InstallationTests(unittest.TestCase):
    def test_unrelated_cs_is_preserved_without_partial_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'cs').write_text('an unrelated program')
            result = subprocess.run([sys.executable, str(INSTALLER), '--bin-dir', tmp], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'already exists', result.stderr)
            self.assertEqual((directory / 'cs').read_text(), 'an unrelated program')
            self.assertFalse((directory / 'command-search').exists())
            self.assertFalse((directory / 'command-complete').exists())

    def test_repeated_installation_provides_working_versioned_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(2):
                subprocess.run([sys.executable, str(INSTALLER), '--bin-dir', tmp], check=True, capture_output=True)
            self.assertEqual(subprocess.check_output([str(Path(tmp) / 'cs'), '--version'], text=True).strip(),
                             'command-search 0.5.0')
            self.assertEqual(subprocess.check_output([str(Path(tmp) / 'command-complete'), '--version'], text=True).strip(),
                             'command-complete 0.5.0')


if __name__ == '__main__':
    unittest.main()
