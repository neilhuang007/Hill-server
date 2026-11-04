import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image, ImageChops


root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('campusMapPack', root / 'ops/build-campus-map-pack.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CampusMapPackTest(unittest.TestCase):
    def fixture(self, folder):
        imagePath = folder / 'aerial.png'
        Image.new('RGB', (100, 100), '#336644').save(imagePath)
        buildingsPath = folder / 'buildings.yml'
        buildingsPath.write_text('coordinate-frame: hill-local-east-south-2x\nbuildings:\n'
                                '  chapel:\n    name: Chapel\n    bounds-xz: [2, 2, 4, 4]\n', encoding='utf-8')
        return imagePath, buildingsPath

    def testPackIsDeterministicAndTilesReassembleTheDisplayedMap(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            imagePath, buildingsPath = self.fixture(folder)
            first, second = folder / 'first', folder / 'second'
            builder.build(imagePath, buildingsPath, first, 'Fixture', [0, 0, 9, 9])
            builder.build(imagePath, buildingsPath, second, 'Fixture', [0, 0, 9, 9])
            self.assertEqual((first / 'campus-pack.zip').read_bytes(), (second / 'campus-pack.zip').read_bytes())
            reassembled = Image.new('RGB', (576, 320))
            with zipfile.ZipFile(first / 'campus-pack.zip') as archive:
                for slot in range(45):
                    name = f'campus/tile_{slot}'
                    tile = Image.open(io.BytesIO(archive.read(f'assets/hill175/textures/item/{name}.png')))
                    reassembled.paste(tile, (slot % 9 * 64, slot // 9 * 64))
                    item = json.loads(archive.read(f'assets/hill175/items/{name}.json'))
                    self.assertEqual(f'hill175:item/{name}', item['model']['model'])
                    self.assertTrue(item['oversized_in_gui'])
                self.assertEqual(137, len(archive.namelist()))
            self.assertIsNone(ImageChops.difference(reassembled, Image.open(first / 'campus-map.png')).getbbox())
            with self.assertRaises(ValueError):
                builder.build(imagePath, buildingsPath, first, 'Fixture', [0, 0, 9, 9])

    def testWrongAspectRatioCannotSilentlyMisregisterSelection(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            imagePath, buildingsPath = self.fixture(folder)
            with self.assertRaises(ValueError):
                builder.build(imagePath, buildingsPath, folder / 'output', 'Fixture', [0, 0, 19, 9])


if __name__ == '__main__':
    unittest.main()
