#!/usr/bin/env python3
"""Prepare the operator-supplied Stoneborn UI textures; never extract arbitrary ZIP paths."""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from gallery_minecraft_font import prepareMinecraftFont


def prepareAssets(archivePath, outputDirectory, minecraftClient=None):
    outputDirectory.mkdir(parents=True, exist_ok=True)
    selections = {
        "stone.png": ("assets/minecraft/textures/gui/options_background.png", None),
        "wood.png": ("assets/minecraft/textures/gui/hanging_signs/oak.png", (1, 6, 15, 15)),
        "parchment.png": ("assets/minecraft/textures/gui/book.png", (40, 20, 145, 160)),
        "button.png": ("assets/minecraft/textures/gui/sprites/widget/button.png", None),
        "button-active.png": ("assets/minecraft/textures/gui/sprites/widget/button_highlighted.png", None),
        "button-disabled.png": ("assets/minecraft/textures/gui/sprites/widget/button_disabled.png", None),
        "frame.png": ("assets/minecraft/textures/gui/sprites/widget/slot_frame.png", None),
        "divider.png": ("assets/minecraft/textures/gui/container/inventory.png", (0, 0, 176, 6)),
        "footer-divider.png": ("assets/minecraft/textures/gui/container/inventory.png", (0, 162, 176, 166)),
        "divider-left.png": ("assets/minecraft/textures/gui/container/inventory.png", (0, 0, 12, 8)),
        "divider-center.png": ("assets/minecraft/textures/gui/container/inventory.png", (72, 0, 104, 6)),
        "divider-right.png": ("assets/minecraft/textures/gui/container/inventory.png", (164, 0, 176, 8)),
        "divider-fill.png": ("assets/minecraft/textures/gui/container/inventory.png", (12, 0, 72, 6)),
        "footer-divider-left.png": ("assets/minecraft/textures/gui/container/inventory.png", (0, 158, 12, 166)),
        "footer-divider-center.png": ("assets/minecraft/textures/gui/container/inventory.png", (72, 162, 104, 166)),
        "footer-divider-right.png": ("assets/minecraft/textures/gui/container/inventory.png", (164, 158, 176, 166)),
        "footer-divider-fill.png": ("assets/minecraft/textures/gui/container/inventory.png", (12, 162, 72, 166)),
        "crest.png": ("pack.png", None),
        "arrow-next.png": ("assets/minecraft/textures/gui/sprites/widget/page_forward.png", None),
        "arrow-back.png": ("assets/minecraft/textures/gui/sprites/widget/page_backward.png", None),
    }
    # Keep the demonstration window's ornaments at their native pixel scale.
    window = "assets/minecraft/textures/gui/demo_background.png"
    selections.update({
        "window-tl.png": (window, (0, 0, 8, 8)),
        "window-tr.png": (window, (240, 0, 248, 8)),
        "window-bl.png": (window, (0, 158, 8, 166)),
        "window-br.png": (window, (240, 158, 248, 166)),
        "window-tc.png": (window, (112, 0, 136, 6)),
        "window-bc.png": (window, (112, 160, 136, 166)),
        "window-top.png": (window, (24, 0, 25, 4)),
        "window-bottom.png": (window, (24, 162, 25, 166)),
        "window-left.png": (window, (0, 24, 4, 25)),
        "window-right.png": (window, (244, 24, 248, 25)),
    })
    with ZipFile(archivePath) as archive:
        for outputName, (sourceName, cropBox) in selections.items():
            entry = archive.getinfo(sourceName)
            if entry.file_size > 1024 * 1024:
                raise ValueError("Unexpectedly large Stoneborn UI source image.")
            sourceBytes = archive.read(entry)
            image = Image.open(BytesIO(sourceBytes))
            if image.width > 1024 or image.height > 1024:
                raise ValueError("Unexpected Stoneborn UI source dimensions.")
            image = image.convert("RGBA")
            if cropBox:
                image = image.crop(cropBox)
                image.save(outputDirectory / outputName, optimize=True)
            else:
                (outputDirectory / outputName).write_bytes(sourceBytes)
    with archivePath.open("rb") as source:
        archiveHash = hashlib.file_digest(source, "sha256").hexdigest()
    manifest = {
        "source": archivePath.name,
        "sha256": archiveHash,
        "author": "Sindavar",
        "sourceUrl": "https://modrinth.com/resourcepack/stoneborn",
        "notice": "STONEBORN by Sindavar, all rights reserved. Operator-supplied artwork for local preview; archive and artwork remain outside Git.",
        "files": {name: {"source": source, "crop": crop} for name, (source, crop) in selections.items()},
    }
    if minecraftClient:
        manifest["font"] = prepareMinecraftFont(minecraftClient, outputDirectory)
        manifest["items"] = prepareCampusItemIcons(minecraftClient, outputDirectory)
    (outputDirectory / "asset-source.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(selections)} UI textures in {outputDirectory}")


def prepareCampusItemIcons(minecraftClient, outputDirectory):
    """Copy original item pixels from the supplied game client, without redrawing them."""
    items = ("compass_16", "map", "trial_key", "ender_pearl")
    files = {}
    with ZipFile(minecraftClient) as client:
        for item in items:
            source = f"assets/minecraft/textures/item/{item}.png"
            entry = client.getinfo(source)
            if entry.file_size > 1024 * 1024:
                raise ValueError("Unexpectedly large Minecraft item texture.")
            name = f"item-{item}.png"
            (outputDirectory / name).write_bytes(client.read(entry))
            files[name] = source
    return {"source": minecraftClient.name, "author": "Mojang", "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Operator-supplied Stoneborn ZIP")
    parser.add_argument("--output", type=Path, default=Path("runtime/gallery-assets"), help="Private runtime gallery asset directory")
    parser.add_argument("--minecraft-client", type=Path, help="Local Minecraft Java client JAR supplying the inherited bitmap Latin font")
    arguments = parser.parse_args()
    if not arguments.archive.is_file():
        parser.error("The supplied resource-pack archive does not exist.")
    minecraftClient = arguments.minecraft_client or defaultMinecraftClient()
    if minecraftClient and not minecraftClient.is_file():
        parser.error("The supplied Minecraft client archive does not exist.")
    prepareAssets(arguments.archive, arguments.output, minecraftClient)


def defaultMinecraftClient():
    candidates = [Path.home() / "AppData/Roaming/.minecraft/versions/1.21.11/1.21.11.jar",
                  Path.home() / ".minecraft/versions/1.21.11/1.21.11.jar"]
    return next((path for path in candidates if path.is_file()), None)


if __name__ == "__main__":
    main()
