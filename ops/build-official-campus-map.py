"""Prepare the supplied official campus illustration without redrawing its artwork.

Example: uv run --with pillow --with pymupdf python ops/build-official-campus-map.py
  --pdf runtime/campus-map-official-20261103/FY26CampusMap_Labeled.pdf
  --output runtime/campus-map-official-20261103/assets

Crop coordinates are PDF points measured from the top left of page one.
The illustration is oblique and does not define a Minecraft coordinate projection.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import zipfile

import pymupdf
from PIL import Image, ImageOps


sourceUrl = 'https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf'
fullCrop = (115, 118, 512, 515)
coreCrop = (190, 274, 466, 514)
renderScale = 4
resourceFormats = [[88, 0], [97, 1]]
dialogPixels = 256
labelPixels = 360
rowHeight = 9
maxSegmentWidth = 128
mapFont = 'hill175:campus/map_labels'
gapGlyph = '\uf8ff'
officialPdfSha256 = 'a815cf8e058df9bdbb2997fba3a272249508e7175c536b907f984e9966477e59'
# Printed numbers read from the supplied PDF's raster labels, sorted by extracted circle center Y then X.
# The exact PDF hash is required before this source specific transcription may be used.
officialLabelOrder = (28, 24, 27, 23, 25, 26, 22, 21, 20, 19, 51, 35, 18, 33, 34, 9, 32, 10, 31, 46,
                      11, 36, 15, 17, 8, 14, 47, 30, 37, 13, 29, 12, 2, 1, 7, 6, 50, 3, 43, 42, 40, 16,
                      4, 44, 5, 41, 39, 45, 38, 48, 49)


def jsonBytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def pngBytes(image):
    output = io.BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()


def renderCrop(page, crop):
    region = pymupdf.Rect(crop)
    if region.is_empty or region.is_infinite or not page.rect.contains(region):
        raise ValueError('The illustration crop must be a nonempty rectangle inside the PDF page.')
    pixels = page.get_pixmap(matrix=pymupdf.Matrix(renderScale, renderScale), clip=region,
                             colorspace=pymupdf.csRGB, alpha=False)
    return Image.frombytes('RGB', (pixels.width, pixels.height), pixels.samples)


def fitSquare(image, size):
    if size < 1:
        raise ValueError('Image size must be positive.')
    fitted = ImageOps.contain(image.convert('RGB'), (size, size), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (size, size), 'white')
    canvas.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return canvas


def itemFiles(name, image):
    identifier = 'campus/' + name
    # Dialog item dimensions reserve space; the client still renders a 16 pixel item.
    # ItemTransform centers the generated unit quad before this local matrix in the
    # pose stack. With GUI Y inverted, translation (0, 1-scale) fills the body at (0, 0).
    scale = dialogPixels / 16
    transformation = {'translation': [0, 1 - scale, 0], 'scale': [scale, scale, 1],
                      'left_rotation': [0, 0, 0, 1], 'right_rotation': [0, 0, 0, 1]}
    return {
        f'assets/hill175/textures/item/{identifier}.png': pngBytes(fitSquare(image, 1024)),
        f'assets/hill175/items/{identifier}.json': jsonBytes({
            'model': {'type': 'minecraft:model', 'model': f'hill175:item/{identifier}',
                      'transformation': transformation},
            'oversized_in_gui': True}),
        f'assets/hill175/models/item/{identifier}.json': jsonBytes({
            'parent': 'minecraft:item/generated', 'textures': {'layer0': f'hill175:item/{identifier}'},
            'gui_light': 'front',
            'display': {'gui': {'rotation': [0, 0, 0], 'translation': [0, 0, 0], 'scale': [1, 1, 1]}}}),
    }


def componentBounds(mask, start, width):
    pending = [start]
    mask[start] = 0
    left = right = start % width
    top = bottom = start // width
    count = 0
    while pending:
        index = pending.pop()
        x, y = index % width, index // width
        left, right, top, bottom = min(left, x), max(right, x), min(top, y), max(bottom, y)
        count += 1
        neighbors = (index - 1 if x else -1, index + 1 if x + 1 < width else -1, index - width, index + width)
        for neighbor in neighbors:
            if 0 <= neighbor < len(mask) and mask[neighbor]:
                mask[neighbor] = 0
                pending.append(neighbor)
    return (left, top, right + 1, bottom + 1), count


def extractLabelCircles(image, bounds, numbers):
    pixels = image.convert('RGB').tobytes()
    channels = zip(pixels[0::3], pixels[1::3], pixels[2::3])
    mask = bytearray(r < 40 and 15 < g < 95 and 45 < b < 155 and b > 1.2 * g for r, g, b in channels)
    circles = []
    for start in range(len(mask)):
        if not mask[start]:
            continue
        box, area = componentBounds(mask, start, image.width)
        width, height = box[2] - box[0], box[3] - box[1]
        if 20 <= width <= 55 and 20 <= height <= 55 and 0.85 < width / height < 1.15 and area > width * height * 0.50:
            circles.append(box)
    circles.sort(key=lambda box: (box[1] + box[3], box[0] + box[2]))
    if len(circles) != len(numbers) or len(set(numbers)) != len(numbers):
        raise ValueError(f'Expected {len(numbers)} distinct numbered circles, found {len(circles)}. Review the supplied PDF.')
    return [{'number': number, 'pdfBounds': [box[0] / renderScale + bounds[0], box[1] / renderScale + bounds[1],
                                           box[2] / renderScale + bounds[0], box[3] / renderScale + bounds[1]]}
            for number, box in zip(numbers, circles)]


def projectLabels(circles, image, crop):
    fitted = ImageOps.contain(image, (labelPixels, labelPixels), Image.Resampling.LANCZOS)
    scaleX, scaleY = fitted.width / image.width * renderScale, fitted.height / image.height * renderScale
    offsetX, offsetY = (labelPixels - fitted.width) // 2, (labelPixels - fitted.height) // 2
    labels = []
    for circle in circles:
        left, top, right, bottom = circle['pdfBounds']
        if left < crop[0] or top < crop[1] or right > crop[2] or bottom > crop[3]:
            continue
        x1, x2 = offsetX + (left - crop[0]) * scaleX, offsetX + (right - crop[0]) * scaleX
        y1, y2 = offsetY + (top - crop[1]) * scaleY, offsetY + (bottom - crop[1]) * scaleY
        labels.append({'number': circle['number'], 'centerX': round((x1 + x2) / 2, 4),
                       'centerY': round((y1 + y2) / 2, 4),
                       'bounds': [max(0, math.floor(x1) - 1), max(0, math.floor(y1 / rowHeight) * rowHeight),
                                  min(labelPixels, math.ceil(x2) + 1), min(labelPixels, math.ceil(y2 / rowHeight) * rowHeight)]})
    resolveLabelOverlaps(labels)
    return sorted(labels, key=lambda label: label['number'])


def resolveLabelOverlaps(labels):
    for firstIndex, first in enumerate(labels):
        for second in labels[firstIndex + 1:]:
            a, b = first['bounds'], second['bounds']
            if max(a[0], b[0]) >= min(a[2], b[2]) or max(a[1], b[1]) >= min(a[3], b[3]):
                continue
            left, right = sorted((first, second), key=lambda label: (label['centerX'], label['number']))
            split = math.floor((left['centerX'] + right['centerX']) / 2)
            if left['centerX'] < split <= right['centerX']:
                left['bounds'][2] = min(left['bounds'][2], split)
                right['bounds'][0] = max(right['bounds'][0], split)
                continue
            upper, lower = sorted((first, second), key=lambda label: (label['centerY'], label['number']))
            splitY = round((upper['centerY'] + lower['centerY']) / (2 * rowHeight)) * rowHeight
            if not upper['centerY'] < splitY <= lower['centerY']:
                raise ValueError(f'Labels {first["number"]} and {second["number"]} cannot be separated at 360 pixels.')
            upper['bounds'][3] = min(upper['bounds'][3], splitY)
            lower['bounds'][1] = max(lower['bounds'][1], splitY)


def rowSegments(labels, y):
    active = sorted((label for label in labels if label['bounds'][1] <= y < label['bounds'][3]),
                    key=lambda label: label['bounds'][0])
    segments, x = [], 0
    for label in active:
        left, _, right, _ = label['bounds']
        if left < x or right <= left:
            raise ValueError('Numbered label regions overlap or have no clickable width.')
        if left > x:
            segments.append({'x': x, 'width': left - x, 'label': 0})
        segments.append({'x': left, 'width': right - left, 'label': label['number']})
        x = right
    if x < labelPixels:
        segments.append({'x': x, 'width': labelPixels - x, 'label': 0})
    # Native FontTexture uses a 256 pixel atlas. Keep every glyph comfortably inside it.
    return [{'x': part['x'] + offset, 'width': min(maxSegmentWidth, part['width'] - offset), 'label': part['label']}
            for part in segments for offset in range(0, part['width'], maxSegmentWidth)]


def clickableFont(fullImage, coreImage, circles, fullBounds, coreBounds):
    files, providers = {}, [{'type': 'space', 'advances': {gapGlyph: -1}}]
    manifest = {'schema': 1, 'width': labelPixels, 'rowHeight': rowHeight, 'font': mapFont,
                'gapGlyph': gapGlyph, 'views': {}}
    codepoint = 0xe000
    for name, image, crop in (('full', fullImage, fullBounds), ('core', coreImage, coreBounds)):
        canvas, rows = fitSquare(image, labelPixels), []
        labels = projectLabels(circles, image, crop)
        for y in range(0, labelPixels, rowHeight):
            segments = rowSegments(labels, y)
            for segment in segments:
                if codepoint >= ord(gapGlyph):
                    raise ValueError('The map requires more private font glyphs than its reserved range.')
                glyph, texture = chr(codepoint), f'font/campus/segment_{codepoint:04x}.png'
                segment['glyph'] = glyph
                files['assets/hill175/textures/' + texture] = pngBytes(canvas.crop((segment['x'], y, segment['x'] + segment['width'], y + rowHeight)))
                providers.append({'type': 'bitmap', 'file': 'hill175:' + texture, 'height': rowHeight, 'ascent': 7, 'chars': [glyph]})
                codepoint += 1
            rows.append({'y': y, 'segments': segments})
        manifest['views'][name] = {'height': labelPixels, 'rows': rows, 'labels': labels}
        validateLabelCenters(manifest['views'][name])
    files['assets/hill175/font/campus/map_labels.json'] = jsonBytes({'providers': providers})
    return files, manifest


def validateLabelCenters(view):
    for label in view['labels']:
        row = view['rows'][int(label['centerY']) // rowHeight]
        matched = next((part['label'] for part in row['segments']
                        if part['x'] <= label['centerX'] < part['x'] + part['width']), 0)
        if matched != label['number']:
            raise ValueError(f'The center of printed label {label["number"]} resolves to {matched}.')


def resourcePack(fullImage, coreImage, fontFiles=None):
    files = {
        'pack.mcmeta': jsonBytes({'pack': {'description': 'The Hill School official FY26 campus illustration',
                                          'min_format': resourceFormats[0], 'max_format': resourceFormats[1]}}),
        'pack.png': pngBytes(fitSquare(fullImage, 128)),
        **itemFiles('official_full', fullImage), **itemFiles('official_core', coreImage),
        **(fontFiles or {}),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return output.getvalue()


def provenance(pdfPath, pageSize, crops, images, pack):
    return {
        'description': 'Official FY26 illustrated campus map, faithfully cropped from the supplied PDF',
        'sourceUrl': sourceUrl, 'sourcePdf': pdfPath.name,
        'sourcePdfSha256': hashlib.sha256(pdfPath.read_bytes()).hexdigest(),
        'page': 1, 'pageSizePoints': pageSize, 'cropCoordinateOrigin': 'top-left',
        'fullCropPoints': list(crops[0]), 'coreCropPoints': list(crops[1]), 'renderDpi': 72 * renderScale,
        'projection': 'oblique illustration; no world coordinate projection or player cursor',
        'images': {name: {'pixels': list(image.size), 'sha256': hashlib.sha256(pngBytes(image)).hexdigest()}
                   for name, image in images.items()},
        'itemModels': ['hill175:campus/official_full', 'hill175:campus/official_core'],
        'dialogBodyPixels': [dialogPixels, dialogPixels],
        'dialogArtworkBoundsPixels': [0, 0, dialogPixels, dialogPixels],
        'itemTransformSpecification': 'https://feedback.minecraft.net/hc/en-us/articles/44551668333837-Minecraft-Java-Edition-26-1',
        'packSha1': hashlib.sha1(pack).hexdigest(), 'packSha256': hashlib.sha256(pack).hexdigest(),
        'resourceFormats': resourceFormats,
    }


def build(pdfPath, output, fullBounds=fullCrop, coreBounds=coreCrop, labelOrder=None):
    if output.exists():
        raise ValueError('Choose a new output folder to preserve previously prepared official map assets.')
    if labelOrder is None and hashlib.sha256(pdfPath.read_bytes()).hexdigest() != officialPdfSha256:
        raise ValueError('Number transcription is verified only for the supplied FY26 PDF. Review labels before using another document.')
    with pymupdf.open(pdfPath) as document:
        if document.page_count != 1:
            raise ValueError('The supplied official campus map must contain exactly one page.')
        page = document[0]
        fullImage, coreImage = renderCrop(page, fullBounds), renderCrop(page, coreBounds)
        pageSize = [page.rect.width, page.rect.height]
    images = {'campus-map.png': fullImage, 'campus-core.png': coreImage,
              'campus-held.png': fitSquare(fullImage, 128)}
    circles = extractLabelCircles(fullImage, fullBounds, officialLabelOrder if labelOrder is None else labelOrder)
    fontFiles, labels = clickableFont(fullImage, coreImage, circles, fullBounds, coreBounds)
    pack = resourcePack(fullImage, coreImage, fontFiles)
    if len(pack) >= 8 * 1024 * 1024:
        raise ValueError('The official campus resource pack exceeds the 8 MB limit.')
    labels['packSha1'] = hashlib.sha1(pack).hexdigest()
    manifest = provenance(pdfPath, pageSize, (fullBounds, coreBounds), images, pack)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.official-campus-map-', dir=output.parent) as staging:
        stage = Path(staging)
        for name, image in images.items():
            (stage / name).write_bytes(pngBytes(image))
        (stage / 'campus-pack.zip').write_bytes(pack)
        (stage / 'campus-map-source.json').write_bytes(jsonBytes(manifest))
        (stage / 'campus-map-labels.json').write_bytes(jsonBytes(labels))
        (stage / 'campus-map-label-source.json').write_bytes(jsonBytes({'pdfSha256': manifest['sourcePdfSha256'],
            'method': 'Navy circle connected components with visually verified printed number transcription', 'labels': circles}))
        stage.rename(output)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    result = build(options.pdf, options.output)
    print(json.dumps({'output': str(options.output.resolve()), 'packSha1': result['packSha1'],
                      'itemModels': result['itemModels']}, indent=2))
