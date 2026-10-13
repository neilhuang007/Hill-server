"""The IT packet includes the chosen campus and maps, excluding unrelated private files."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location(
    'deployment_assets', Path(__file__).resolve().parents[1] / 'ops/package-deployment-assets.py')
ASSETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSETS)

HUB = 'world-templates/hill_hub'
LOBBY = 'world-templates/hill_auth'


class DeploymentAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.campus = self.root / 'runtime/chosen-campus'
        self.hub = self.root / 'runtime/chosen-hub'
        self.lobby = self.root / 'runtime/chosen-lobby'
        self.output = self.root / 'runtime/handoff/test.zip'
        for folder in ('ops/handoff', 'runtime/assets', 'docs/research', 'runtime/chosen-campus/region',
                       'runtime/chosen-hub/dimensions/minecraft/overworld/region', 'runtime/chosen-hub/playerdata',
                       'runtime/chosen-lobby/region'):
            (self.root / folder).mkdir(parents=True)
        (self.root / 'ops/handoff/README.txt').write_text('IT setup instructions')
        (self.campus / 'region/r.0.0.mca').write_bytes(bytes(8192))
        (self.campus / 'hill-campus-template.yml').write_text('revision: selected-campus\n')
        (self.hub / 'level.dat').write_bytes(b'hub level')
        (self.hub / 'dimensions/minecraft/overworld/region/r.0.0.mca').write_bytes(bytes(8192))
        (self.hub / 'hill-world.yml').write_text('spawn: [70.5, 66.1, 42.5, 0.0, 0.0]\n')
        (self.lobby / 'level.dat').write_bytes(b'lobby level')
        (self.lobby / 'region/r.0.0.mca').write_bytes(bytes(8192))
        for private in ('.env', 'runtime/assets/credentials.env', 'docs/research/internal.md',
                        'AGENTS.md', 'runtime/chosen-campus/operator-notes.txt',
                        'runtime/chosen-hub/operator-notes.txt', 'runtime/chosen-hub/playerdata/owner.dat',
                        'runtime/chosen-hub/session.lock'):
            (self.root / private).write_text('PRIVATE SENTINEL')
        (self.campus / 'playerdata').mkdir()
        (self.campus / 'playerdata/private.dat').write_text('PRIVATE SENTINEL')

    def test_packet_is_allowlisted_and_checksums_verify_every_payload(self):
        ASSETS.package(self.root, self.output, self.campus, self.hub)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual({'README.txt', 'SHA256SUMS',
                              f'{HUB}/level.dat', f'{HUB}/hill-world.yml',
                              f'{HUB}/dimensions/minecraft/overworld/region/r.0.0.mca',
                              'world-templates/hill_people_template/region/r.0.0.mca',
                              'world-templates/hill_people_template/hill-campus-template.yml'},
                             set(archive.namelist()))
            for line in archive.read('SHA256SUMS').decode().splitlines():
                digest, name = line.split('  ', 1)
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
            self.assertTrue(all(b'PRIVATE SENTINEL' not in archive.read(name) for name in archive.namelist()))

    def test_lobby_is_packaged_only_when_explicitly_selected(self):
        ASSETS.package(self.root, self.output, self.campus, self.hub, self.lobby)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(b'lobby level', archive.read(f'{LOBBY}/level.dat'))
            self.assertIn(f'{LOBBY}/region/r.0.0.mca', archive.namelist())

    def test_incomplete_hub_or_empty_campus_does_not_create_packet(self):
        (self.hub / 'level.dat').unlink()
        with self.assertRaisesRegex(ValueError, 'level.dat'):
            ASSETS.package(self.root, self.output, self.campus, self.hub)
        (self.hub / 'level.dat').write_bytes(b'hub level')
        (self.hub / 'hill-world.yml').write_text('spwan: [1, 2, 3]\n')
        with self.assertRaisesRegex(ValueError, 'unknown entry'):
            ASSETS.package(self.root, self.output, self.campus, self.hub)
        (self.hub / 'hill-world.yml').unlink()
        (self.campus / 'region/r.0.0.mca').unlink()
        with self.assertRaisesRegex(ValueError, 'no region'):
            ASSETS.package(self.root, self.output, self.campus, self.hub)
        self.assertFalse(self.output.exists())

    def test_previous_handoff_is_preserved(self):
        ASSETS.package(self.root, self.output, self.campus, self.hub)
        previous = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            ASSETS.package(self.root, self.output, self.campus, self.hub)
        self.assertEqual(previous, self.output.read_bytes())

    def test_output_must_stay_in_ignored_handoff_directory(self):
        with self.assertRaisesRegex(ValueError, 'runtime/handoff'):
            ASSETS.package(self.root, self.root / 'publish.zip', self.campus, self.hub)

    def test_next_revision_can_have_more_regions_and_optional_poi(self):
        (self.campus / 'region/r.1.0.mca').write_bytes(bytes(8192))
        (self.campus / 'poi').mkdir()
        (self.campus / 'poi/r.0.0.mca').write_bytes(bytes(8192))
        ASSETS.package(self.root, self.output, self.campus, self.hub)
        with zipfile.ZipFile(self.output) as archive:
            self.assertIn('world-templates/hill_people_template/region/r.1.0.mca', archive.namelist())
            self.assertIn('world-templates/hill_people_template/poi/r.0.0.mca', archive.namelist())

    def test_truncated_and_nested_templates_are_rejected(self):
        (self.campus / 'region/r.0.0.mca').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'truncated'):
            ASSETS.package(self.root, self.output, self.campus, self.hub)
        (self.campus / 'region/r.0.0.mca').write_bytes(bytes(8192))
        (self.campus / 'dimensions').mkdir()
        with self.assertRaisesRegex(ValueError, 'flat template'):
            ASSETS.package(self.root, self.output, self.campus, self.hub)


if __name__ == '__main__':
    unittest.main()
