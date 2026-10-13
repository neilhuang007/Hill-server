"""Designated map folders and the server program list are validated as data."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('world_check', REPO / 'ops/check-world-template.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class WorldTemplateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.map = Path(self.temp.name) / 'hill_hub'
        (self.map / 'dimensions/minecraft/overworld/region').mkdir(parents=True)
        (self.map / 'level.dat').write_bytes(b'level')
        self.region = self.map / 'dimensions/minecraft/overworld/region/r.0.0.mca'
        self.region.write_bytes(bytes(8192))

    def place(self, text):
        (self.map / 'hill-world.yml').write_text(text, encoding='utf-8')

    def test_current_and_older_save_layouts_are_accepted_without_a_name_or_hash(self):
        CHECK.validate(self.map)
        older = Path(self.temp.name) / 'any name'
        (older / 'region').mkdir(parents=True)
        (older / 'level.dat').write_bytes(b'level')
        (older / 'region/r.-1.0.mca').write_bytes(bytes(8192))
        (older / 'region/r.0.0.mca').write_bytes(b'')  # Saves contain untouched, empty regions.
        CHECK.validate(older)

    def test_zip_nested_or_empty_folders_are_refused(self):
        nested = Path(self.temp.name) / 'nested'
        (nested / 'My World').mkdir(parents=True)
        (nested / 'My World/level.dat').write_bytes(b'level')
        with self.assertRaisesRegex(ValueError, 'directly inside'):
            CHECK.validate(nested)
        self.region.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'no region data'):
            CHECK.validate(self.map)
        self.region.write_bytes(b'partial')
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            CHECK.validate(self.map)
        with self.assertRaisesRegex(ValueError, 'existing directory'):
            CHECK.validate(Path(self.temp.name) / 'missing')

    def test_placement_accepts_the_documented_form(self):
        self.place('# Exhibition hub\n'
                   'spawn: [70.5, 66.1, 42.5, 0.0, 0.0]\n'
                   'npcs:\n'
                   '  journey: [70.5, 67.0, 70.5, 180.0, 0.0]  # upper landing\n'
                   '  survival: [70, 66, -31]\n')
        CHECK.validate(self.map)

    def test_placement_typos_fail_before_the_server_is_stopped(self):
        for text in ('spwan: [1, 2, 3]\n', 'spawn: [1, 2]\n', 'spawn: [1, 2, 3, 4]\n', 'spawn: 1, 2, 3\n',
                     'npcs:\n  guide: [1, 2, 3]\n', 'npcs: [1, 2, 3]\n', '  journey: [1, 2, 3]\n',
                     'spawn: [1, 2, 3]\nspawn: [4, 5, 6]\n', 'spawn: [1, two, 3]\n'):
            self.place(text)
            with self.assertRaises(ValueError, msg=text):
                CHECK.validate(self.map)

    @unittest.skipIf(os.name == 'nt', 'symbolic links need elevation on Windows')
    def test_links_are_refused(self):
        (self.map / 'region').symlink_to(self.region.parent)
        with self.assertRaisesRegex(ValueError, 'Links'):
            CHECK.validate(self.map)


@unittest.skipIf(os.name == 'nt', 'the loader is sourced by the Linux installer')
class ServerBinariesTest(unittest.TestCase):
    def load(self, manifest: Path, expression: str = 'echo "${PAPER_SHA256} ${CHUNKY_FILENAME}"'):
        return subprocess.run(
            ['bash', '-c', 'set -euo pipefail; source "$1"; load_server_binaries "$2"; ' + expression, 'bash',
             str(REPO / 'ops/load-server-binaries.sh'), str(manifest)],
            capture_output=True, text=True, cwd=manifest.parent)

    def test_checked_in_list_loads(self):
        result = self.load(REPO / 'server-assets/server-binaries.env')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(result.stdout, r'^[0-9a-f]{64} [A-Za-z0-9._-]+\.jar\n$')

    def test_list_is_data_and_never_executed(self):
        text = (REPO / 'server-assets/server-binaries.env').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'server-binaries.env'
            for change in (text.replace('PAPER_URL=https://', 'PAPER_URL=$(touch executed)https://'),
                           text + 'touch executed\n', text + 'EXTRA_URL=https://example.invalid/x\n',
                           text + 'PAPER_SHA256=' + 'a' * 64 + '\n',
                           '\n'.join(line for line in text.splitlines() if not line.startswith('CHUNKY_SHA512='))):
                manifest.write_text(change, encoding='utf-8')
                result = self.load(manifest)
                self.assertNotEqual(0, result.returncode, change[-80:])
                self.assertFalse((Path(folder) / 'executed').exists())


if __name__ == '__main__':
    unittest.main()
