"""Trace the actual local Minecraft bitmap glyphs into a private browser font."""

import hashlib
import json
from io import BytesIO
from zipfile import ZipFile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from PIL import Image


def glyphFromBitmap(bitmap, ascent, pixelScale):
    pen = TTGlyphPen(None)
    for row in range(bitmap.height):
        for start, end in pixelRuns(bitmap, row):
            addPixelRun(pen, start, end, row, ascent, pixelScale)
    return pen.glyph()


def pixelRuns(bitmap, row):
    start = None
    for column in range(bitmap.width + 1):
        isFilled = column < bitmap.width and bitmap.getpixel((column, row)) >= 128
        if isFilled and start is None:
            start = column
        if not isFilled and start is not None:
            yield start, column
            start = None


def addPixelRun(pen, start, end, row, ascent, pixelScale):
    left, right = round(start * pixelScale), round(end * pixelScale)
    top, bottom = round(ascent - row * pixelScale), round(ascent - (row + 1) * pixelScale)
    pen.moveTo((left, bottom))
    pen.lineTo((left, top))
    pen.lineTo((right, top))
    pen.lineTo((right, bottom))
    pen.closePath()


def isGalleryCharacter(codepoint):
    return 32 <= codepoint <= 591 or 8208 <= codepoint <= 8250 or 8592 <= codepoint <= 8595


def providerGlyphs(archive, provider):
    texture = "assets/minecraft/textures/" + provider["file"].split(":", 1)[1]
    sourceBytes = archive.read(texture)
    image = Image.open(BytesIO(sourceBytes)).convert("RGBA").getchannel("A")
    rows = provider["chars"]
    cellWidth, cellHeight = image.width // len(rows[0]), image.height // len(rows)
    pixelScale = 128 * provider.get("height", 8) / cellHeight
    ascent = provider["ascent"] * 128
    cells = ((row, column, ord(character)) for row, characters in enumerate(rows)
             for column, character in enumerate(characters) if isGalleryCharacter(ord(character)))
    for rowIndex, columnIndex, codepoint in cells:
        left, top = columnIndex * cellWidth, rowIndex * cellHeight
        bitmap = image.crop((left, top, left + cellWidth, top + cellHeight))
        bounds = bitmap.getbbox()
        if bounds:
            advance = round(bounds[2] * pixelScale) + 128
            yield codepoint, glyphFromBitmap(bitmap, ascent, pixelScale), advance, round(bounds[0] * pixelScale)


def mergeProvider(archive, provider, glyphs, metrics, characterMap):
    for codepoint, glyph, advance, leftBearing in providerGlyphs(archive, provider):
        if codepoint in characterMap:
            continue
        name = f"uni{codepoint:04X}"
        characterMap[codepoint] = name
        glyphs[name], metrics[name] = glyph, (advance, leftBearing)


def prepareMinecraftFont(clientArchive, outputDirectory):
    glyphs = {".notdef": TTGlyphPen(None).glyph(), "space": TTGlyphPen(None).glyph()}
    metrics = {".notdef": (768, 0), "space": (512, 0)}
    characterMap = {32: "space", 160: "space"}
    definitionPath = "assets/minecraft/font/include/default.json"
    with ZipFile(clientArchive) as archive:
        definition = json.loads(archive.read(definitionPath))
        for provider in definition["providers"]:
            if provider["type"] != "bitmap":
                continue
            mergeProvider(archive, provider, glyphs, metrics, characterMap)
        sources = bitmapSources(archive, definition)
    saveBrowserFont(glyphs, metrics, characterMap, outputDirectory / "minecraft.woff2")
    with clientArchive.open("rb") as source:
        archiveHash = hashlib.file_digest(source, "sha256").hexdigest()
    return {"client": clientArchive.name, "clientSha256": archiveHash, "definition": definitionPath,
            "output": "minecraft.woff2", "glyphCount": len(characterMap), "bitmapSources": sources,
            "method": "Exact opaque pixel runs traced from original Minecraft bitmap providers; original advance and baseline metrics. Local preview only; no font binary in Git."}


def bitmapSources(archive, definition):
    sources = {}
    for provider in definition["providers"]:
        if provider["type"] != "bitmap":
            continue
        path = "assets/minecraft/textures/" + provider["file"].split(":", 1)[1]
        sources[path] = hashlib.sha256(archive.read(path)).hexdigest()
    return sources


def saveBrowserFont(glyphs, metrics, characterMap, outputPath):
    builder = FontBuilder(1024, isTTF=True)
    builder.setupGlyphOrder(list(glyphs))
    builder.setupCharacterMap(characterMap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=1280, descent=-256, lineGap=0)
    builder.setupNameTable({"familyName": "Minecraft Bitmap Local", "styleName": "Regular",
                            "uniqueFontIdentifier": "MinecraftBitmapLocal-1", "fullName": "Minecraft Bitmap Local",
                            "psName": "MinecraftBitmapLocal", "version": "Version 1.0",
                            "copyright": "Glyph artwork from the operator's local Minecraft Java client. Not bundled for redistribution."})
    builder.setupOS2(sTypoAscender=1280, sTypoDescender=-256, sTypoLineGap=0, usWinAscent=1280, usWinDescent=256)
    builder.setupPost()
    builder.setupMaxp()
    builder.font["gasp"] = newTable("gasp")
    builder.font["gasp"].gaspRange = {65535: 1}
    builder.font.flavor = "woff2"
    builder.font.save(outputPath)
