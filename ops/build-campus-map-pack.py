"""Prepare fixed campus image assets for the native Java map menu.

Example: uv run --with pillow --with pyyaml python ops/build-campus-map-pack.py
  --image <registered aerial PNG> --buildings src/main/resources/hill-buildings.yml
  --output runtime/campus-map-v60 --revision V60

The image must cover the inclusive bounds at a uniform pixel scale, with north
at the top. It is a reference aerial, not an image of the Minecraft build.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw, ImageFont
import yaml


def jsonBytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def pngBytes(image):
    output = io.BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()


def projection(bounds, tileSize):
    minX, minZ, maxX, maxZ = bounds
    scale = min(9 * tileSize / (maxX - minX + 1), 5 * tileSize / (maxZ - minZ + 1))
    width, depth = (maxX - minX + 1) * scale, (maxZ - minZ + 1) * scale
    return scale, (9 * tileSize - width) / 2, (5 * tileSize - depth) / 2


def readBuildings(path, bounds):
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if data.get('coordinate-frame') != 'hill-local-east-south-2x':
        raise ValueError('Building coordinates do not use the measured campus frame.')
    return data['buildings']


def drawMap(image, buildings, bounds, tileSize=64):
    canvas = Image.new('RGB', (tileSize * 9, tileSize * 5), '#182b27')
    scale, offsetX, offsetZ = projection(bounds, tileSize)
    width = round((bounds[2] - bounds[0] + 1) * scale)
    depth = round((bounds[3] - bounds[1] + 1) * scale)
    canvas.paste(image.convert('RGB').resize((width, depth), Image.Resampling.LANCZOS), (round(offsetX), round(offsetZ)))
    draw = ImageDraw.Draw(canvas)
    for building in buildings.values():
        minX, minZ, maxX, maxZ = building['bounds-xz']
        rect = [(offsetX + (minX - bounds[0]) * scale, offsetZ + (minZ - bounds[1]) * scale),
                (offsetX + (maxX + 1 - bounds[0]) * scale, offsetZ + (maxZ + 1 - bounds[1]) * scale)]
        draw.rectangle(rect, outline='#f8e4a1', width=1)
    draw.text((14, 12), 'N', fill='#f8e4a1', font=ImageFont.load_default(size=20))
    draw.line((21, 55, 21, 37), fill='#f8e4a1', width=2)
    draw.polygon([(21, 33), (16, 41), (26, 41)], fill='#f8e4a1')
    draw.text((11, tileSize * 5 - 36), 'AERIAL', fill='#d2dfd6', font=ImageFont.load_default(size=10))
    draw.text((11, tileSize * 5 - 22), 'REFERENCE', fill='#d2dfd6', font=ImageFont.load_default(size=10))
    return canvas


def packFiles(canvas, tileSize):
    files = {'pack.mcmeta': jsonBytes({'pack': {'description': 'Hill campus aerial selection map',
                                                'min_format': [88, 0], 'max_format': [97, 1]}}),
             'pack.png': pngBytes(canvas.resize((128, 71), Image.Resampling.LANCZOS))}
    for slot in range(45):
        x, y = slot % 9 * tileSize, slot // 9 * tileSize
        name = f'campus/tile_{slot}'
        files[f'assets/hill175/textures/item/{name}.png'] = pngBytes(canvas.crop((x, y, x + tileSize, y + tileSize)))
        files[f'assets/hill175/items/{name}.json'] = jsonBytes({'model': {'type': 'minecraft:model', 'model': f'hill175:item/{name}'},
                                                              'oversized_in_gui': True})
        files[f'assets/hill175/models/item/{name}.json'] = jsonBytes({
            'parent': 'minecraft:item/generated', 'textures': {'layer0': f'hill175:item/{name}'},
            'gui_light': 'front', 'display': {'gui': {'rotation': [0, 0, 0], 'translation': [0, 0, 0], 'scale': [1.125, 1.125, 1]}}})
    return files


def build(imagePath, buildingsPath, output, revision, bounds):
    if any((output / name).exists() for name in ('campus-pack.zip', 'campus-map.png', 'campus-map-source.json')):
        raise ValueError('Choose a new output folder to preserve previous prepared map assets.')
    expectedRatio = (bounds[2] - bounds[0] + 1) / (bounds[3] - bounds[1] + 1)
    with Image.open(imagePath) as source:
        if abs(source.width / source.height - expectedRatio) > 0.0001:
            raise ValueError('The registered image dimensions do not match the supplied world bounds.')
        image = source.convert('RGB')
    buildings = readBuildings(buildingsPath, bounds)
    canvas = drawMap(image, buildings, bounds)
    files = packFiles(canvas, 64)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / 'campus-pack.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    (output / 'campus-map.png').write_bytes(pngBytes(canvas))
    digest = hashlib.sha1((output / 'campus-pack.zip').read_bytes()).hexdigest()
    manifest = {'revision': revision, 'description': 'Registered aerial reference with measured building outlines',
                'image': str(imagePath.resolve()), 'imageSha256': hashlib.sha256(imagePath.read_bytes()).hexdigest(),
                'buildingCatalogSha256': hashlib.sha256(buildingsPath.read_bytes()).hexdigest(),
                'boundsXzInclusive': list(bounds), 'columns': 9, 'rows': 5, 'north': 'top', 'tilePixels': 64,
                'packSha1': digest, 'resourceFormats': [[88, 0], [97, 1]]}
    (output / 'campus-map-source.json').write_bytes(jsonBytes(manifest))
    print(json.dumps({'output': str(output.resolve()), 'sha1': digest, 'tiles': 45}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--buildings', type=Path, default=Path('src/main/resources/hill-buildings.yml'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--bounds', nargs=4, type=int, default=[-576, -1600, 1471, 415], metavar=('MIN_X', 'MIN_Z', 'MAX_X', 'MAX_Z'))
    args = parser.parse_args()
    build(args.image, args.buildings, args.output, args.revision, args.bounds)
