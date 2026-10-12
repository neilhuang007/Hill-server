"""The IT packet includes the chosen campus, excluding unrelated private files."""
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


class DeploymentAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.campus = self.root / 'runtime/chosen-campus'
        self.output = self.root / 'runtime/handoff/test.zip'
        for folder in ('ops/handoff', 'runtime/assets', 'docs/research', 'runtime/chosen-campus/region'):
            (self.root / folder).mkdir(parents=True)
        self.hub = b'pinned hub archive'
        (self.root / 'runtime/assets/hub.zip').write_bytes(self.hub)
        (self.root / 'ops/install-server.sh').write_text(
            f'HUB_ARCHIVE_NAME="hub.zip"\nHUB_SHA256="{hashlib.sha256(self.hub).hexdigest()}"\n')
        (self.root / 'ops/handoff/README.txt').write_text('IT setup instructions')
        (self.campus / 'region/r.0.0.mca').write_bytes(bytes(8192))
        (self.campus / 'hill-campus-template.yml').write_text('revision: selected-campus\n')
        for private in ('.env', 'runtime/assets/credentials.env', 'docs/research/internal.md',
                        'AGENTS.md', 'runtime/chosen-campus/operator-notes.txt'):
            (self.root / private).write_text('PRIVATE SENTINEL')
        (self.campus / 'playerdata').mkdir()
        (self.campus / 'playerdata/private.dat').write_text('PRIVATE SENTINEL')

    def test_packet_is_allowlisted_and_checksums_verify_every_payload(self):
        ASSETS.package(self.root, self.output, self.campus)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual({'assets/hub.zip', 'README.txt', 'SHA256SUMS',
                              'world-templates/hill_people_template/region/r.0.0.mca',
                              'world-templates/hill_people_template/hill-campus-template.yml'},
                             set(archive.namelist()))
            self.assertEqual(self.hub, archive.read('assets/hub.zip'))
            for line in archive.read('SHA256SUMS').decode().splitlines():
                digest, name = line.split('  ', 1)
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
            self.assertTrue(all(b'PRIVATE SENTINEL' not in archive.read(name) for name in archive.namelist()))

    def test_wrong_hub_or_empty_campus_does_not_create_packet(self):
        hub = self.root / 'runtime/assets/hub.zip'
        hub.write_bytes(b'unreviewed revision')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            ASSETS.package(self.root, self.output, self.campus)
        hub.write_bytes(self.hub)
        (self.campus / 'region/r.0.0.mca').unlink()
        with self.assertRaisesRegex(ValueError, 'no region'):
            ASSETS.package(self.root, self.output, self.campus)
        self.assertFalse(self.output.exists())

    def test_previous_handoff_is_preserved(self):
        ASSETS.package(self.root, self.output, self.campus)
        previous = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            ASSETS.package(self.root, self.output, self.campus)
        self.assertEqual(previous, self.output.read_bytes())

    def test_output_must_stay_in_ignored_handoff_directory(self):
        with self.assertRaisesRegex(ValueError, 'runtime/handoff'):
            ASSETS.package(self.root, self.root / 'publish.zip', self.campus)

    def test_next_revision_can_have_more_regions_and_optional_poi(self):
        (self.campus / 'region/r.1.0.mca').write_bytes(bytes(8192))
        (self.campus / 'poi').mkdir()
        (self.campus / 'poi/r.0.0.mca').write_bytes(bytes(8192))
        ASSETS.package(self.root, self.output, self.campus)
        with zipfile.ZipFile(self.output) as archive:
            self.assertIn('world-templates/hill_people_template/region/r.1.0.mca', archive.namelist())
            self.assertIn('world-templates/hill_people_template/poi/r.0.0.mca', archive.namelist())

    def test_truncated_and_nested_templates_are_rejected(self):
        (self.campus / 'region/r.0.0.mca').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'truncated'):
            ASSETS.package(self.root, self.output, self.campus)
        (self.campus / 'region/r.0.0.mca').write_bytes(bytes(8192))
        (self.campus / 'dimensions').mkdir()
        with self.assertRaisesRegex(ValueError, 'flat template'):
            ASSETS.package(self.root, self.output, self.campus)


if __name__ == '__main__':
    unittest.main()
