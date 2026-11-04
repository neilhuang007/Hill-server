"""Verify immutable clickable artwork reconstruction and number targets without opening Minecraft."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw


def readJson(path):
    return json.loads(path.read_text(encoding='utf-8'))


def hit(row, x):
    cursor = 0
    for part in row['segments']:
        if cursor + part['width'] + 1 > x:
            return part['label']
        cursor += part['width'] + 1 - 1
    return 0


def verify(assets):
    spec = importlib.util.spec_from_file_location('officialMap', Path(__file__).with_name('build-official-campus-map.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    manifest = readJson(assets / 'campus-map-labels.json')
    packPath = assets / 'campus-pack.zip'
    if hashlib.sha1(packPath.read_bytes()).hexdigest() != manifest['packSha1']:
        raise ValueError('The label manifest belongs to another resource pack.')
    result = {'packSha1': manifest['packSha1'], 'packBytes': packPath.stat().st_size, 'views': {}}
    with zipfile.ZipFile(packPath) as pack:
        providers = json.loads(pack.read('assets/hill175/font/campus/map_labels.json'))['providers']
        if providers[0] != {'type': 'space', 'advances': {manifest['gapGlyph']: -1}}:
            raise ValueError('The font does not compensate bitmap advances.')
        glyphs = {provider['chars'][0]: provider for provider in providers[1:]}
        for name, view in manifest['views'].items():
            result['views'][name] = verifyView(assets, builder, pack, glyphs, name, view)
    if sorted(result['views']['full']['numbers']) != list(range(1, 52)):
        raise ValueError('The complete official map must expose all 51 numbered labels.')
    result['passed'] = True
    return result


def verifyView(assets, builder, pack, glyphs, name, view):
    sourceName = 'campus-map.png' if name == 'full' else 'campus-core.png'
    with Image.open(assets / sourceName) as source:
        expected = builder.fitSquare(source, 360)
    reconstructed = Image.new('RGB', (360, 360))
    if len(view['rows']) != 40:
        raise ValueError('The map must contain forty rows.')
    blankChecks = 0
    for index, row in enumerate(view['rows']):
        if row['y'] != index * 9:
            raise ValueError('A map row is out of order.')
        cursor = 0
        for part in row['segments']:
            provider = glyphs[part['glyph']]
            if part['x'] != cursor or provider['height'] != 9 or provider['ascent'] != 7:
                raise ValueError('Bitmap placement or baseline differs from its hit metadata.')
            texture = 'assets/hill175/textures/' + provider['file'].split(':', 1)[1]
            with Image.open(io.BytesIO(pack.read(texture))) as bitmap:
                if bitmap.size != (part['width'], 9) or bitmap.convert('RGBA').getchannel('A').getextrema() != (255, 255):
                    raise ValueError('Glyph metrics would differ from the manifest.')
                reconstructed.paste(bitmap, (cursor, row['y']))
            if part['label'] == 0 and part['width'] > 2:
                if hit(row, cursor + part['width'] / 2) != 0:
                    raise ValueError('Blank artwork gained a number action.')
                blankChecks += 1
            cursor += part['width']
        if cursor != 360:
            raise ValueError('Map rows must cover exactly 360 pixels.')
    if expected.tobytes() != reconstructed.tobytes():
        raise ValueError('The font image does not reconstruct the supplied illustration exactly.')
    for label in view['labels']:
        if hit(view['rows'][int(label['centerY']) // 9], label['centerX']) != label['number']:
            raise ValueError(f'Printed label {label["number"]} selects another target.')
    overlay(assets.parent, name, expected, view['labels'])
    return {'numbers': [label['number'] for label in view['labels']], 'labelCentersPassed': len(view['labels']),
            'blankCentersPassed': blankChecks, 'pixelsReconstructed': 360 * 360,
            'imageSha256': hashlib.sha256(reconstructed.tobytes()).hexdigest()}


def overlay(folder, name, image, labels):
    canvas = image.resize((1440, 1440), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(canvas)
    for label in labels:
        box = [coordinate * 4 for coordinate in label['bounds']]
        draw.rectangle(box, outline='#fa2245', width=2)
        x, y = round(label['centerX'] * 4), round(label['centerY'] * 4)
        draw.line((x - 4, y, x + 4, y), fill='#ffdd00', width=1)
        draw.line((x, y - 4, x, y + 4), fill='#ffdd00', width=1)
    canvas.save(folder / ('labels-' + name + '-overlay.png'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    options = parser.parse_args()
    result = verify(options.assets)
    report = options.assets.parent / 'labels-verification.json'
    report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
