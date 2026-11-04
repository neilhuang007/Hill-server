import importlib.util
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
import zipfile

import pymupdf
from PIL import Image


spec = importlib.util.spec_from_file_location('officialCampusMap', Path(__file__).resolve().parents[1] / 'ops/build-official-campus-map.py')
official = importlib.util.module_from_spec(spec)
spec.loader.exec_module(official)


def dialogBounds(item, model):
    """26.3 ItemTransform.apply and GuiItemRenderState.calculateOversizedItemBounds.

    The widget's 256 pixel dimensions allocate space but do not scale its item.
    Local model transformation follows legacy display centering in the pose stack.
    OfficialMapDialogBounds.java checks these calculations against actual client classes.
    """
    display = model['display']['gui']
    if display['rotation'] != [0, 0, 0]:
        raise ValueError('The official illustration must remain front facing.')
    local = item['model'].get('transformation', {})
    if local.get('left_rotation', [0, 0, 0, 1]) != [0, 0, 0, 1] or local.get('right_rotation', [0, 0, 0, 1]) != [0, 0, 0, 1]:
        raise ValueError('The official illustration must not rotate inside its model.')
    scale, translation = local.get('scale', [1, 1, 1]), local.get('translation', [0, 0, 0])
    points = []
    for x, y in ((0, 0), (1, 0), (1, 1), (0, 1)):
        point = [x, y]
        for axis in range(2):
            centered = translation[axis] + scale[axis] * point[axis] - 0.5
            legacyScale = max(-4, min(4, display['scale'][axis]))
            legacyOffset = max(-5, min(5, display['translation'][axis] / 16))
            point[axis] = centered * legacyScale + legacyOffset
        points.append(point)
    minX, maxX = min(point[0] for point in points), max(point[0] for point in points)
    minY, maxY = min(point[1] for point in points), max(point[1] for point in points)
    width, height = math.ceil((maxX - minX) * 16), math.ceil((maxY - minY) * 16)
    if not item.get('oversized_in_gui') or (width <= 16 and height <= 16):
        return [0, 0, 16, 16]
    left, top = math.floor(minX * 16) + 8, 8 - math.floor(maxY * 16)
    return [left, top, left + width, top + height]


class OfficialCampusMapTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.pdf = self.folder / 'official.pdf'
        with pymupdf.open() as document:
            page = document.new_page(width=612, height=792)
            page.draw_rect(pymupdf.Rect(115, 118, 512, 515), color=None, fill=(0.2, 0.5, 0.8))
            for number, x, y in ((28, 140, 143), (6, 300, 400)):
                page.draw_circle(pymupdf.Point(x, y), 5, color=None, fill=(0, 0.18, 0.35))
                page.insert_text((x - 2, y + 1.5), str(number), fontsize=5, color=(1, 1, 1))
            document.save(self.pdf)

    def build(self, output, fullBounds=official.fullCrop):
        return official.build(self.pdf, output, fullBounds=fullBounds, labelOrder=(28, 6))

    def testAssetsAreReproducibleAndDoNotReplaceUnrelatedInventoryTextures(self):
        first, second = self.folder / 'first', self.folder / 'second'
        manifest = self.build(first)
        self.build(second)
        self.assertEqual((first / 'campus-pack.zip').read_bytes(), (second / 'campus-pack.zip').read_bytes())
        with zipfile.ZipFile(first / 'campus-pack.zip') as archive:
            self.assertIn('assets/hill175/font/campus/map_labels.json', archive.namelist())
            self.assertFalse(any(name.startswith('assets/minecraft/') for name in archive.namelist()))
            metadata = json.loads(archive.read('pack.mcmeta'))['pack']
            self.assertEqual([88, 0], metadata['min_format'])
            self.assertEqual([97, 1], metadata['max_format'])
            for name in ('official_full', 'official_core'):
                item = json.loads(archive.read(f'assets/hill175/items/campus/{name}.json'))
                self.assertEqual(f'hill175:item/campus/{name}', item['model']['model'])
        self.assertEqual(list(official.fullCrop), manifest['fullCropPoints'])
        self.assertEqual(official.sourceUrl, manifest['sourceUrl'])

    def testDialogArtworkActuallyFillsItsAllocated256PixelBody(self):
        for name in ('official_full', 'official_core'):
            with self.subTest(model=name):
                files = official.itemFiles(name, Image.new('RGB', (1024, 1024), 'white'))
                item = json.loads(files[f'assets/hill175/items/campus/{name}.json'])
                model = json.loads(files[f'assets/hill175/models/item/campus/{name}.json'])
                self.assertEqual([0, 0, 256, 256], dialogBounds(item, model),
                                 'Dialog dimensions reserve space; the model must fill it in the native item pipeline.')

    def testClickableMapIncludesExactImageRowsAndLabelHitAreas(self):
        output = self.folder / 'labels'
        self.build(output)
        labels = json.loads((output / 'campus-map-labels.json').read_text(encoding='utf-8'))
        self.assertEqual(360, labels['width'])
        self.assertEqual(40, len(labels['views']['full']['rows']))
        self.assertEqual(hashlib.sha1((output / 'campus-pack.zip').read_bytes()).hexdigest(), labels['packSha1'])
        with zipfile.ZipFile(output / 'campus-pack.zip') as pack:
            providers = json.loads(pack.read('assets/hill175/font/campus/map_labels.json'))['providers']
            self.assertEqual({'\uf8ff': -1}, providers[0]['advances'])
            glyphs = {provider['chars'][0]: provider for provider in providers[1:]}
            for viewName, view in labels['views'].items():
                imageName = 'campus-map.png' if viewName == 'full' else 'campus-core.png'
                with Image.open(output / imageName) as source:
                    expected = official.fitSquare(source, 360)
                reconstructed = Image.new('RGB', (360, 360))
                for row in view['rows']:
                    cursor = 0
                    for part in row['segments']:
                        provider = glyphs[part['glyph']]
                        self.assertLessEqual(part['width'], 128, 'Each glyph must fit the native 256 pixel font atlas.')
                        self.assertEqual(9, provider['height'])
                        self.assertEqual(7, provider['ascent'])
                        self.assertEqual(cursor, part['x'])
                        texture = 'assets/hill175/textures/' + provider['file'].split(':')[1]
                        with Image.open(io.BytesIO(pack.read(texture))) as bitmap:
                            self.assertEqual((part['width'], 9), bitmap.size)
                            reconstructed.paste(bitmap, (cursor, row['y']))
                        cursor += part['width'] + 1 - 1
                    self.assertEqual(360, cursor)
                self.assertEqual(expected.tobytes(), reconstructed.tobytes())
                for label in view['labels']:
                    row = view['rows'][int(label['centerY']) // 9]
                    cursor, hit = 0, 0
                    for part in row['segments']:
                        if cursor + part['width'] + 1 > label['centerX']:
                            hit = part['label']
                            break
                        cursor += part['width'] + 1 - 1
                    self.assertEqual(label['number'], hit)

    def testCropAndHeldImagePreserveTheSuppliedArtwork(self):
        output = self.folder / 'assets'
        self.build(output)
        with pymupdf.open(self.pdf) as document:
            expected = official.renderCrop(document[0], official.fullCrop)
        with Image.open(output / 'campus-map.png') as actual:
            self.assertEqual((1588, 1588), actual.size)
            self.assertEqual(expected.tobytes(), actual.tobytes())
        with Image.open(output / 'campus-held.png') as held:
            self.assertEqual((128, 128), held.size)
            self.assertEqual(official.fitSquare(expected, 128).tobytes(), held.tobytes())
        letterboxed = official.fitSquare(Image.new('RGB', (200, 100), 'navy'), 128)
        self.assertEqual((255, 255, 255), letterboxed.getpixel((64, 31)))
        self.assertEqual((0, 0, 128), letterboxed.getpixel((64, 32)))
        self.assertEqual((0, 0, 128), letterboxed.getpixel((64, 95)))
        self.assertEqual((255, 255, 255), letterboxed.getpixel((64, 96)))

    def testPreparedAssetsAreImmutableAndInvalidCropsFailBeforeWriting(self):
        output = self.folder / 'assets'
        self.build(output)
        original = (output / 'campus-pack.zip').read_bytes()
        with self.assertRaises(ValueError):
            self.build(output)
        self.assertEqual(original, (output / 'campus-pack.zip').read_bytes())
        invalid = self.folder / 'invalid'
        with self.assertRaises(ValueError):
            self.build(invalid, (0, 0, 999, 999))
        self.assertFalse(invalid.exists())


if __name__ == '__main__':
    unittest.main()
