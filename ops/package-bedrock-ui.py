#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow>=11,<12", "PyYAML>=6,<7"]
# ///
"""Build the optional Bedrock campus map pack from the same measured catalog as Java.

Run: uv run --script ops/package-bedrock-ui.py
Install the resulting .mcpack in plugins/Geyser-Spigot/packs/, then restart Geyser.
Generated PNGs and archives remain in build/; only source assets belong in Git.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw, ImageFont
import yaml

projectRoot = Path(__file__).resolve().parents[1]
sourceRoot = projectRoot / "server-assets/hill-bedrock-ui"
defaultCatalog = projectRoot / "src/main/resources/hill-buildings.yml"
mapTitle = "Hill Campus Map"


@dataclass(frozen=True)
class Building:
    id: str
    name: str
    mapNumber: int
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[float, float]:
        minX, minZ, maxX, maxZ = self.bounds
        return (minX + (maxX - minX) // 2, minZ + (maxZ - minZ) // 2)


def readCatalog(catalogPath: Path) -> list[Building]:
    catalog = yaml.safe_load(catalogPath.read_text(encoding="utf-8"))
    if catalog.get("coordinate-frame") != "hill-local-east-south-2x":
        raise ValueError("The map requires the measured Hill east/south coordinate frame.")
    buildings = [readBuilding(buildingId, value) for buildingId, value in catalog["buildings"].items()]
    if not buildings or len({building.mapNumber for building in buildings}) != len(buildings):
        raise ValueError("The map requires a nonempty catalog with unique map numbers.")
    return sorted(buildings, key=lambda building: (building.mapNumber, building.name))


def readBuilding(buildingId: str, value: dict) -> Building:
    bounds = tuple(value["bounds-xz"])
    if len(bounds) != 4 or any(type(coordinate) is not int for coordinate in bounds):
        raise ValueError(f"Invalid measured bounds for {buildingId}.")
    if bounds[0] > bounds[2] or bounds[1] > bounds[3]:
        raise ValueError(f"Reversed measured bounds for {buildingId}.")
    return Building(buildingId, value["name"], int(value["map-number"]), bounds)


def mapView(buildings: list[Building], north: bool) -> dict:
    selected = [building for building in buildings if (building.bounds[3] < -500) == north]
    if not selected:
        raise ValueError("The catalog must include both central campus and northern athletics.")
    padding = 65
    bounds = [min(building.bounds[0] for building in selected) - padding,
              min(building.bounds[1] for building in selected) - padding,
              max(building.bounds[2] for building in selected) + padding,
              max(building.bounds[3] for building in selected) + padding]
    return {"name": "north" if north else "central", "bounds": bounds,
            "layoutSize": [145, 60] if north else [340, 150], "buildings": selected}


def project(view: dict, point: tuple[float, float]) -> tuple[float, float]:
    minX, minZ, maxX, maxZ = view["bounds"]
    return ((point[0] - minX) / (maxX - minX), (point[1] - minZ) / (maxZ - minZ))


def pinPositions(view: dict) -> dict[str, tuple[float, float]]:
    """Separate crowded targets, preserving the measured footprint with a leader line."""
    width, height = view["layoutSize"]
    positions = {}
    for building in view["buildings"]:
        desired = project(view, building.center)
        candidates = pinCandidates(desired, width, height)
        chosen = next((point for point in candidates if isClear(point, positions.values(), width, height)), None)
        if chosen is None:
            raise ValueError(f"Cannot place a readable map target for {building.id}.")
        positions[building.id] = chosen
    return positions


def pinCandidates(desired: tuple[float, float], width: int, height: int) -> list[tuple[float, float]]:
    candidates = [desired]
    for radius in range(8, 129, 4):
        count = max(8, int(2 * math.pi * radius / 4))
        candidates.extend((desired[0] + math.cos(step * 2 * math.pi / count) * radius / width,
                           desired[1] + math.sin(step * 2 * math.pi / count) * radius / height)
                          for step in range(count))
    return [point for point in candidates if 10 / width <= point[0] <= 1 - 10 / width
            and 10 / height <= point[1] <= 1 - 10 / height]


def isClear(point: tuple[float, float], occupied, width: int, height: int) -> bool:
    return all(abs(point[0] - other[0]) * width >= 20 or abs(point[1] - other[1]) * height >= 20
               for other in occupied)


def drawMap(view: dict, positions: dict) -> Image.Image:
    width, height = [value * 4 for value in view["layoutSize"]]
    image = Image.new("RGB", (width, height), (198, 219, 205))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, width - 3, height - 3), outline=(74, 83, 62), width=3)
    for building in view["buildings"]:
        minX, minZ, maxX, maxZ = building.bounds
        topLeft, bottomRight = project(view, (minX, minZ)), project(view, (maxX, maxZ))
        rectangle = (topLeft[0] * width, topLeft[1] * height, bottomRight[0] * width, bottomRight[1] * height)
        draw.rectangle(rectangle, fill=(224, 214, 177), outline=(74, 83, 62), width=3)
        drawLeader(draw, view, building, positions[building.id], width, height)
    draw.polygon([(width - 29, 13), (width - 38, 38), (width - 20, 38)], fill=(25, 52, 77))
    draw.text((width - 36, 41), "N", font=font(21), fill=(25, 52, 77))
    return image


def drawLeader(draw: ImageDraw.ImageDraw, view: dict, building: Building, point: tuple, width: int, height: int):
    center = project(view, building.center)
    start, end = (center[0] * width, center[1] * height), (point[0] * width, point[1] * height)
    draw.line((start, end), fill=(48, 87, 106), width=3)
    draw.ellipse((start[0] - 4, start[1] - 4, start[0] + 4, start[1] + 4), fill=(25, 52, 77))


def font(size: int):
    for filename in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(filename).is_file():
            return ImageFont.truetype(filename, size)
    return ImageFont.load_default(size=size)


def pngBytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def pinTexture(isHover: bool) -> bytes:
    image = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(image)
    fill = (247, 200, 87, 255) if isHover else (25, 52, 77, 255)
    draw.rounded_rectangle((2, 2, 61, 61), radius=17, fill=fill, outline=(246, 242, 225, 255), width=4)
    return pngBytes(image)


def mapControls(view: dict, positions: dict, indexes: dict[str, int]) -> dict:
    controls = [{"chart": {"type": "image", "size": ["100%", "100%"],
                            "texture": f"textures/hill175/{view['name']}_map", "layer": 1}}]
    for building in view["buildings"]:
        index, point = indexes[building.id], positions[building.id]
        controls.append({f"pin{index}@hill_campus.map_pin": {
            "collection_index": index, "$button_text": str(building.mapNumber),
            "$button_tts_header": building.name, "$focus_id": f"hillPin{index}",
            "$tooltip_offset": [0 if point[0] < 0.5 else -134, 18 if point[1] < 0.65 else -36],
            "$focus_override_right": f"hillList{index}",
            "offset": [f"{point[0] * 100:.5f}% - 8px", f"{point[1] * 100:.5f}% - 8px"]}})
    return {"type": "panel", "collection_name": "form_buttons", "controls": controls}


def listControls(buildings: list[Building]) -> dict:
    controls = []
    for index, building in enumerate(buildings):
        controls.append({f"building{index}@hill_campus.list_button": {
            "collection_index": index, "$button_tts_header": building.name,
            "$focus_id": f"hillList{index}", "$focus_override_left": f"hillPin{index}",
            "$focus_override_up": f"hillList{index - 1}" if index else "hillBack",
            "$focus_override_down": f"hillList{index + 1}" if index + 1 < len(buildings) else "hillBack",
            "$button_focus_precedence": 10 if index == 0 else 0}})
    return {"type": "stack_panel", "size": ["100%", "100%c"], "orientation": "vertical",
            "anchor_from": "top_left", "anchor_to": "top_left", "collection_name": "form_buttons",
            "controls": controls}


def sourceFiles() -> dict[str, bytes]:
    return {path.relative_to(sourceRoot).as_posix(): path.read_bytes()
            for path in sourceRoot.rglob("*.json")}


def buildFiles(catalogPath: Path) -> tuple[dict[str, bytes], dict, dict]:
    buildings = readCatalog(catalogPath)
    indexes = {building.id: index for index, building in enumerate(buildings)}
    files, images, locations = sourceFiles(), {}, []
    screen = json.loads(files["ui/hill_campus.json"])
    for north in (False, True):
        view = mapView(buildings, north)
        positions = pinPositions(view)
        images[view["name"]] = drawMap(view, positions)
        files[f"textures/hill175/{view['name']}_map.png"] = pngBytes(images[view["name"]])
        screen[f"{view['name']}_map"] = mapControls(view, positions, indexes)
        locations.extend(locationRows(view, positions, indexes))
    screen["building_list"] = listControls(buildings)
    screen["map_screen"]["controls"][-2]["back@hill_campus.form_button"]["collection_index"] = len(buildings)
    files["ui/hill_campus.json"] = jsonBytes(screen)
    files["textures/hill175/map_pin.png"] = pinTexture(False)
    files["textures/hill175/map_pin_hover.png"] = pinTexture(True)
    files["textures/hill175/screen_background.png"] = pngBytes(Image.new("RGB", (4, 4), (17, 33, 48)))
    metadata = {"title": mapTitle, "catalogSha256": hashlib.sha256(catalogPath.read_bytes()).hexdigest(),
                "coordinateFrame": "hill-local-east-south-2x", "backIndex": len(buildings),
                "buttons": sorted(locations, key=lambda location: location["index"])}
    files["hill-campus-map.json"] = jsonBytes(metadata)
    return files, metadata, images


def locationRows(view: dict, positions: dict, indexes: dict) -> list[dict]:
    return [{"index": indexes[building.id], "id": building.id, "name": building.name,
             "mapNumber": building.mapNumber, "boundsXz": list(building.bounds),
             "view": view["name"], "viewBoundsXz": view["bounds"],
             "footprintCenter": list(project(view, building.center)), "pinPosition": list(positions[building.id])}
            for building in view["buildings"]]


def jsonBytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def preview(metadata: dict, images: dict) -> Image.Image:
    """An authoring preview only; native Bedrock rendering still requires manual review."""
    image = Image.new("RGB", (1440, 900), (17, 33, 48))
    draw = ImageDraw.Draw(image)
    draw.text((30, 22), mapTitle, font=font(32), fill="white")
    draw.text((30, 67), "Choose a numbered pin or a building name.", font=font(20), fill=(185, 207, 221))
    rectangles = {"central": (30, 123, 925, 650), "north": (30, 675, 410, 825)}
    for name, rectangle in rectangles.items():
        image.paste(images[name].resize((rectangle[2] - rectangle[0], rectangle[3] - rectangle[1])), rectangle[:2])
    drawPreviewPins(draw, metadata, rectangles)
    draw.text((440, 684), "ATHLETICS / NORTH\n19 Kipp Pavilion (draft)\n25 Lehrman Pavilion\n26 Madden / Puccio (approx.)",
              font=font(21), fill=(185, 207, 221), spacing=10)
    drawPreviewList(draw, metadata)
    draw.rounded_rectangle((30, 851, 180, 889), radius=5, fill=(231, 232, 224))
    draw.text((78, 859), "Back", font=font(22), fill=(17, 33, 48))
    draw.text((650, 862), "Choose a building, then start your project.", font=font(20), fill=(185, 207, 221))
    return image


def drawPreviewPins(draw: ImageDraw.ImageDraw, metadata: dict, rectangles: dict):
    for building in metadata["buttons"]:
        x1, y1, x2, y2 = rectangles[building["view"]]
        pinX, pinY = building["pinPosition"]
        x, y = x1 + pinX * (x2 - x1), y1 + pinY * (y2 - y1)
        draw.rounded_rectangle((x - 20, y - 20, x + 20, y + 20), radius=9,
                               fill=(25, 52, 77), outline=(246, 242, 225), width=2)
        label = str(building["mapNumber"])
        draw.text((x, y), label, anchor="mm", font=font(21), fill="white")


def drawPreviewList(draw: ImageDraw.ImageDraw, metadata: dict):
    for index, building in enumerate(metadata["buttons"][:10]):
        top = 123 + index * 68
        draw.rounded_rectangle((950, top, 1407, top + 62), radius=4, fill=(224, 229, 224))
        label = f"{building['mapNumber']}  {building['name']}"
        words, lines = label.split(), [""]
        for word in words:
            if len(lines[-1] + word) > 37: lines.append("")
            lines[-1] += word + " "
        draw.multiline_text((966, top + 9), "\n".join(lines), font=font(19), fill=(17, 33, 48), spacing=3)
    draw.text((1068, 814), f"Scroll for all {len(metadata['buttons'])} buildings", font=font(20), fill=(185, 207, 221))


def package(catalogPath: Path, outputPath: Path) -> dict:
    files, metadata, images = buildFiles(catalogPath)
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(outputPath, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            member = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, data)
    previewPath = outputPath.with_suffix(".preview.png")
    preview(metadata, images).save(previewPath)
    outputPath.with_suffix(".mapping.json").write_bytes(jsonBytes(metadata))
    return {"archive": str(outputPath), "sha256": hashlib.sha256(outputPath.read_bytes()).hexdigest(),
            "preview": str(previewPath), "buildings": len(metadata["buttons"]),
            "catalogSha256": metadata["catalogSha256"], "backIndex": metadata["backIndex"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=defaultCatalog)
    parser.add_argument("--output", type=Path, default=projectRoot / "build/bedrock-ui/hill-campus-ui.mcpack")
    options = parser.parse_args()
    print(json.dumps(package(options.catalog, options.output), indent=2))
