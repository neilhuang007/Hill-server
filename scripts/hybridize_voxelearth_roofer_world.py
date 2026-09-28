#!/usr/bin/env python3
"""Hybridize a VoxelEarth Anvil world with clean Roofer LoD2 buildings.

This script treats the VoxelEarth world as the terrain source of truth. It
copies that world, clears only the vertical volumes occupied by known Hill
building footprints, and stamps deterministic Roofer-derived building shells
and roofs into the copy.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import shutil
import sys
import time
import zlib
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator

import nbtlib
import numpy as np
from nbtlib import tag
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as geometry_transform, unary_union
from shapely.prepared import prep


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_WORLD = (
    REPO_ROOT
    / "runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831"
    / "paper-runtime-wallclean-v7-1226"
    / "hill_school_voxelearth_full_groundfallback_v11_1xg64_20260831_1346"
)
DEFAULT_ROOFER_CITYJSON = (
    REPO_ROOT
    / "runtime/campus-reconstruction/roofer-chapel-trial"
    / "campus-model/hill-campus-roofer.city.json"
)
DEFAULT_ROOFER_OVERLAY_NPZ = (
    REPO_ROOT
    / "runtime/campus-reconstruction/roofer-chapel-trial"
    / "roofer-building-overlay-1m/hill-campus-roofer-lod22-buildings-only-1m.npz"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "runtime/campus-reconstruction/hybrid-voxelearth-ground-roofer-buildings"
)
DEFAULT_OSM_SITE_FEATURES = (
    REPO_ROOT / "runtime/campus-data/gis/osm--75.63850-40.24338--75.61808-40.26086.json"
)
DEFAULT_VANILLA_ATLAS = (
    REPO_ROOT
    / "runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831"
    / "src/minecraft-plugin/src/main/resources/vanilla.atlas"
)
DEFAULT_CAMPUS_SURFACES = DEFAULT_VANILLA_ATLAS.parent / "hill-campus-surfaces.geojson"
DEFAULT_CAMPUS_BUILDINGS = DEFAULT_VANILLA_ATLAS.parent / "hill-campus-buildings.geojson"
DEFAULT_CAMPUS_BOUNDARY = DEFAULT_VANILLA_ATLAS.parent / "hill-campus-boundary.geojson"
VANILLA_ATLAS_CANDIDATES = (
    DEFAULT_VANILLA_ATLAS,
    REPO_ROOT / "runtime/tools/VoxelEarth/minecraft-plugin/src/main/resources/vanilla.atlas",
    REPO_ROOT / "runtime/tools/voxelizer-research/VoxelEarth/minecraft-plugin/src/main/resources/vanilla.atlas",
)
MATERIAL_ATLAS_PATH: Path | None = None

AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
AIR = "minecraft:air"
GROUND_CATEGORY_BLOCKS = {
    1: "minecraft:grass_block",
    2: "minecraft:water",
    3: "minecraft:smooth_stone",
    4: "minecraft:smooth_stone",
    5: "minecraft:dirt",
}
SANDLIKE_REPLACEMENT_BLOCK = "minecraft:grass_block"
SANDLIKE_TOP_BLOCKS = {
    "minecraft:sand",
    "minecraft:red_sand",
    "minecraft:sandstone",
    "minecraft:cut_sandstone",
    "minecraft:smooth_sandstone",
    "minecraft:red_sandstone",
    "minecraft:cut_red_sandstone",
    "minecraft:smooth_red_sandstone",
    "minecraft:suspicious_sand_0",
    "minecraft:suspicious_sand_1",
    "minecraft:suspicious_sand_2",
    "minecraft:suspicious_sand_3",
}
GROUND_OR_NOISE_PARTS = (
    "air",
    "grass",
    "dirt",
    "water",
    "leaves",
    "log",
    "sapling",
    "flower",
    "moss_block",
)
NOISY_DARK_BLOCKS = {
    "minecraft:blackstone",
    "minecraft:black_concrete",
    "minecraft:black_concrete_powder",
    "minecraft:black_terracotta",
    "minecraft:black_wool",
    "minecraft:coal_block",
    "minecraft:obsidian",
    "minecraft:crying_obsidian",
    "minecraft:polished_blackstone",
    "minecraft:polished_blackstone_bricks",
    "minecraft:sculk",
}
OVERWORLD_WOOD_PREFIXES = (
    "acacia",
    "bamboo",
    "birch",
    "cherry",
    "dark_oak",
    "jungle",
    "mangrove",
    "oak",
    "spruce",
)
SAFE_EXACT_MATERIALS = {
    "andesite",
    "bricks",
    "brown_concrete",
    "brown_terracotta",
    "calcite",
    "clay",
    "coarse_dirt",
    "cobbled_deepslate",
    "cobblestone",
    "cut_copper",
    "cut_red_sandstone",
    "cut_sandstone",
    "deepslate",
    "deepslate_bricks",
    "deepslate_tiles",
    "diorite",
    "dirt",
    "exposed_cut_copper",
    "glass",
    "granite",
    "grass_block",
    "gray_concrete",
    "gray_terracotta",
    "light_gray_concrete",
    "light_gray_terracotta",
    "mossy_cobblestone",
    "mossy_stone_bricks",
    "mud",
    "mud_bricks",
    "oxidized_cut_copper",
    "packed_mud",
    "polished_andesite",
    "polished_deepslate",
    "polished_diorite",
    "polished_granite",
    "quartz_block",
    "quartz_bricks",
    "quartz_pillar",
    "red_concrete",
    "red_sandstone",
    "red_terracotta",
    "rooted_dirt",
    "sandstone",
    "smooth_sandstone",
    "smooth_stone",
    "stone",
    "stone_bricks",
    "terracotta",
    "weathered_cut_copper",
    "white_concrete",
    "white_terracotta",
}
FACADE_EXCLUDED_EXACT_MATERIALS = {
    "coarse_dirt",
    "cobbled_deepslate",
    "cut_copper",
    "deepslate",
    "deepslate_bricks",
    "deepslate_tiles",
    "dirt",
    "exposed_cut_copper",
    "glass",
    "grass_block",
    "mud",
    "oxidized_cut_copper",
    "packed_mud",
    "polished_deepslate",
    "red_concrete",
    "rooted_dirt",
    "weathered_cut_copper",
}
ROOF_MATERIAL_NAMES = (
    "deepslate_tiles",
    "deepslate_bricks",
    "gray_concrete",
    "stone_bricks",
    "smooth_stone",
    "dark_oak_planks",
    "weathered_cut_copper",
)
TRIM_MATERIAL_NAMES = (
    "stone_bricks",
    "smooth_stone",
    "polished_andesite",
    "light_gray_concrete",
    "white_concrete",
)
SITE_FEATURE_BLOCKS = {
    "road": "minecraft:gray_concrete",
    "path": "minecraft:stone_bricks",
    "parking": "minecraft:light_gray_concrete",
    "water": "minecraft:water",
    "track": "minecraft:red_concrete",
    "tennis": "minecraft:green_concrete",
    "field": "minecraft:grass_block",
    "baseball": "minecraft:coarse_dirt",
    "court": "minecraft:blue_concrete",
}
SITE_FEATURE_PRIORITY = (
    "field",
    "baseball",
    "tennis",
    "court",
    "track",
    "parking",
    "path",
    "road",
    "water",
)
ROAD_NAME_TOKENS = ("alley", "drive", "road", "street")
CHAPEL_LANDMARK_MATERIALS = {
    "wall": "minecraft:bricks",
    "trim": "minecraft:stone_bricks",
    "roof": "minecraft:deepslate_tiles",
    "window": "minecraft:black_stained_glass",
    "floor": "minecraft:smooth_stone",
}
BUILDING_CLEAR_HEADROOM = 12
BUILDING_GROUND_TRANSITION_RADIUS = 12
BUILDING_APRON_SURFACE_BLOCK = "minecraft:grass_block"
CHAPEL_APRON_SURFACE_BLOCK = BUILDING_APRON_SURFACE_BLOCK
CHAPEL_PROCEDURAL_SECTION_RADIUS = 14
CHAPEL_SECTION_SURFACE_BLOCK = "minecraft:grass_block"
CHAPEL_SECTION_SUBSURFACE_BLOCK = "minecraft:dirt"
CHAPEL_SECTION_DEEP_BLOCK = "minecraft:stone"
CHAPEL_SECTION_TOPSOIL_DEPTH = 4
# Building generation comes before landscaping.  Preserve only the terrain
# surface in the Chapel's cleanup ring; trees and photogrammetry fragments can
# be restored later from semantic sources after the architecture is accepted.
CHAPEL_APRON_RUBBLE_HEIGHT = 0


def is_chapel_name(name: str) -> bool:
    return "chapel" in name.lower()


def clamp_channel(value: float | int) -> int:
    return max(0, min(255, int(value)))


def normalize_atlas_block_name(block_name: str | None) -> str | None:
    if block_name is None:
        return None
    key = block_name.lower()
    if not key.startswith("minecraft:"):
        return None
    return key.removeprefix("minecraft:")


def material_block_name_for_atlas_block(block_name: str) -> str | None:
    material_name = normalize_atlas_block_name(block_name)
    if material_name is None:
        return None
    if material_name.endswith("_horizontal"):
        material_name = material_name.removesuffix("_horizontal")
    return f"minecraft:{material_name}"


def has_wood_architecture_suffix(suffix: str) -> bool:
    return suffix in {
        "log",
        "wood",
        "block",
        "planks",
        "mosaic",
        "slab",
        "stairs",
        "fence",
        "fence_gate",
        "door",
        "trapdoor",
    }


def is_wood_candidate_for(material_name: str, wood: str) -> bool:
    stripped_prefix = f"stripped_{wood}_"
    normal_prefix = f"{wood}_"
    if material_name.startswith(stripped_prefix):
        return has_wood_architecture_suffix(material_name.removeprefix(stripped_prefix))
    if material_name.startswith(normal_prefix):
        return has_wood_architecture_suffix(material_name.removeprefix(normal_prefix))
    return False


def is_overworld_wood_material_name(material_name: str) -> bool:
    return any(is_wood_candidate_for(material_name, wood) for wood in OVERWORLD_WOOD_PREFIXES)


def is_campus_safe_material_name(material_name: str) -> bool:
    if "crimson" in material_name or "warped" in material_name:
        return False
    if is_overworld_wood_material_name(material_name):
        return True
    return material_name in SAFE_EXACT_MATERIALS


def load_material_colors_from_atlas(atlas_path: Path) -> dict[str, tuple[int, int, int]]:
    payload = json.loads(atlas_path.read_text(encoding="utf-8"))
    colors: dict[str, tuple[int, int, int]] = {}
    for block_object in payload.get("blocks", []):
        block_name = str(block_object.get("name") or "")
        material_block = material_block_name_for_atlas_block(block_name)
        if material_block is None:
            continue
        material_name = material_block.removeprefix("minecraft:")
        if not is_campus_safe_material_name(material_name):
            continue
        colour = block_object.get("colour") or {}
        if not {"r", "g", "b"}.issubset(colour):
            continue
        colors.setdefault(
            material_block,
            (
                clamp_channel(float(colour["r"]) * 255.0),
                clamp_channel(float(colour["g"]) * 255.0),
                clamp_channel(float(colour["b"]) * 255.0),
            ),
        )
    if not colors:
        raise ValueError(f"atlas has no campus-safe material colors: {atlas_path}")
    return colors


def load_default_material_colors() -> dict[str, tuple[int, int, int]]:
    global MATERIAL_ATLAS_PATH
    checked: list[str] = []
    for atlas_path in VANILLA_ATLAS_CANDIDATES:
        checked.append(str(atlas_path))
        if atlas_path.is_file():
            MATERIAL_ATLAS_PATH = atlas_path
            return load_material_colors_from_atlas(atlas_path)
    raise FileNotFoundError(f"vanilla.atlas not found; checked: {checked}")


def is_facade_palette_candidate(block: str) -> bool:
    name = block.removeprefix("minecraft:")
    if block in NOISY_DARK_BLOCKS or name in FACADE_EXCLUDED_EXACT_MATERIALS:
        return False
    if name in {"sand", "red_sand"} or "glass" in name:
        return False
    if any(part in name for part in ("ore", "powder", "glazed", "slab", "stairs", "fence", "door", "trapdoor")):
        return False
    if name.endswith("_log") or name.endswith("_wood"):
        return False
    return (
        name in SAFE_EXACT_MATERIALS
        or name.endswith("_planks")
        or name.endswith("_mosaic")
        or name == "bamboo_block"
    )


def palette_from_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"minecraft:{name}" for name in names if f"minecraft:{name}" in MATERIAL_COLORS)


MATERIAL_COLORS = load_default_material_colors()
FACADE_PALETTE = tuple(block for block in MATERIAL_COLORS if is_facade_palette_candidate(block))
ROOF_PALETTE = palette_from_names(ROOF_MATERIAL_NAMES)
TRIM_PALETTE = palette_from_names(TRIM_MATERIAL_NAMES)


@dataclass(frozen=True)
class WorldTransform:
    """VoxelEarth local world coordinate transform."""

    origin_ecef: tuple[float, float, float]
    center_latitude: float
    center_longitude: float
    blocks_per_metre: float
    target_minimum_y: int

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "WorldTransform":
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        center = payload.get("center") or [40.24516, -75.63516]
        return cls(
            origin_ecef=tuple(float(v) for v in payload["originEcefMetres"]),
            center_latitude=float(center[0]),
            center_longitude=float(center[1]),
            blocks_per_metre=float(payload.get("blocksPerMetre", 1.0)),
            target_minimum_y=int(payload.get("targetMinimumY", 70)),
        )

    def lonlat_to_block(self, longitude: float, latitude: float) -> tuple[float, float]:
        point = lat_lon_to_ecef(latitude, longitude, 0.0)
        dx = point[0] - self.origin_ecef[0]
        dy = point[1] - self.origin_ecef[1]
        dz = point[2] - self.origin_ecef[2]
        east, _up, south = self._basis()
        x = dot(east, (dx, dy, dz)) * self.blocks_per_metre
        z = dot(south, (dx, dy, dz)) * self.blocks_per_metre
        return x, z

    def metric_to_block(
        self,
        transformer: Transformer,
        easting: float,
        northing: float,
    ) -> tuple[float, float]:
        longitude, latitude = transformer.transform(easting, northing)
        return self.lonlat_to_block(float(longitude), float(latitude))

    def _basis(self) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
        lat = math.radians(self.center_latitude)
        lon = math.radians(self.center_longitude)
        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        sin_lon = math.sin(lon)
        cos_lon = math.cos(lon)
        east = (-sin_lon, cos_lon, 0.0)
        up = (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)
        south = (sin_lat * cos_lon, sin_lat * sin_lon, -cos_lat)
        return east, up, south


@dataclass
class BuildingModel:
    identifier: str
    name: str
    attributes: dict[str, Any]
    footprints: list[Polygon]
    roof_faces: list[list[tuple[float, float, float]]]
    source_base_z: float
    source_max_z: float
    source_eave_z: float
    base_y: int | None = None

    @property
    def height_m(self) -> float:
        return max(1.0, self.source_max_z - self.source_base_z)

    @property
    def eave_height_m(self) -> float:
        return max(3.0, min(self.height_m, self.source_eave_z - self.source_base_z))

    @property
    def footprint_union(self) -> BaseGeometry:
        if len(self.footprints) == 1:
            return self.footprints[0]
        return unary_union(self.footprints)


@dataclass
class VoxelBuildingOverlay:
    blocks: list[tuple[int, int, int, str, str]]
    support_blocks: dict[tuple[int, int, int], str]
    clear_columns: dict[tuple[int, int], tuple[int, int]]
    edit_columns: int
    source_path: Path
    manifest_path: Path
    building_count: int
    building_names: list[str]
    anchors: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    block_states: dict[tuple[int, int, int], dict[str, str]] = field(default_factory=dict)


@dataclass
class ProceduralBuildingResult:
    blocks: list[tuple[int, int, int, str, str]]
    block_states: dict[tuple[int, int, int], dict[str, str]]
    stats: Counter[str]
    window_mode: str


def shift_procedural_building(
    result: ProceduralBuildingResult,
    delta_y: int,
) -> ProceduralBuildingResult:
    if delta_y == 0:
        return result
    return ProceduralBuildingResult(
        blocks=[
            (x, y + delta_y, z, block_name, role)
            for x, y, z, block_name, role in result.blocks
        ],
        block_states={
            (x, y + delta_y, z): properties
            for (x, y, z), properties in result.block_states.items()
        },
        stats=result.stats,
        window_mode=result.window_mode,
    )


@dataclass(frozen=True)
class RegionLocation:
    offset: int
    sectors: int
    timestamp: int


class SectionEditor:
    def __init__(self, section: tag.Compound):
        self.section = section
        parsed = section_block_states(section)
        if parsed is None:
            palette = [block_entry(AIR)]
            self.names = [AIR]
            self.entries = palette
            self.state_keys = [block_state_key(AIR)]
            self.indices = [0] * 4096
            self.dirty = True
        else:
            entries, data = parsed
            self.entries = [entry.copy() for entry in entries]
            self.names = [palette_name(entry) for entry in self.entries]
            self.state_keys = [palette_state_key(entry) for entry in self.entries]
            self.indices = unpack_indices(len(self.names), data)
            self.dirty = False

    def get(self, local_x: int, local_y: int, local_z: int) -> str:
        return self.names[self.indices[section_index(local_x, local_y, local_z)]]

    def get_state(
        self,
        local_x: int,
        local_y: int,
        local_z: int,
    ) -> tuple[str, dict[str, str]]:
        state_key = self.state_keys[self.indices[section_index(local_x, local_y, local_z)]]
        return state_key[0], dict(state_key[1])

    def set(self, local_x: int, local_y: int, local_z: int, block_name: str) -> bool:
        return self.set_state(local_x, local_y, local_z, block_name, {})

    def set_state(
        self,
        local_x: int,
        local_y: int,
        local_z: int,
        block_name: str,
        properties: dict[str, str] | None,
    ) -> bool:
        idx = section_index(local_x, local_y, local_z)
        desired = block_state_key(block_name, properties)
        current = self.state_keys[self.indices[idx]]
        if current == desired:
            return False
        try:
            palette_index = self.state_keys.index(desired)
        except ValueError:
            palette_index = len(self.names)
            self.names.append(block_name)
            self.entries.append(block_entry(block_name, properties))
            self.state_keys.append(desired)
        self.indices[idx] = palette_index
        self.dirty = True
        return True

    def compact(self) -> None:
        if not self.dirty:
            return
        remap: dict[int, int] = {}
        new_entries: list[tag.Compound] = []
        new_names: list[str] = []
        new_state_keys: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        new_indices: list[int] = []
        for old in self.indices:
            new = remap.get(old)
            if new is None:
                new = len(new_entries)
                remap[old] = new
                new_entries.append(self.entries[old])
                new_names.append(self.names[old])
                new_state_keys.append(self.state_keys[old])
            new_indices.append(new)

        self.entries = new_entries
        self.names = new_names
        self.state_keys = new_state_keys
        self.indices = new_indices
        states = tag.Compound()
        states["palette"] = tag.List[tag.Compound](self.entries)
        if len(self.entries) > 1:
            states["data"] = tag.LongArray(pack_indices(self.indices, len(self.entries)))
        self.section["block_states"] = states
        self.dirty = False


class ChunkEditor:
    def __init__(self, root: nbtlib.File):
        self.root = root
        self._sections: dict[int, SectionEditor] = {}
        self.dirty = False

    @property
    def chunk_x(self) -> int:
        return int(self.root["xPos"])

    @property
    def chunk_z(self) -> int:
        return int(self.root["zPos"])

    def section(self, section_y: int) -> SectionEditor | None:
        if section_y in self._sections:
            return self._sections[section_y]
        for section in self.root.get("sections", []):
            if int(section["Y"]) == section_y:
                editor = SectionEditor(section)
                self._sections[section_y] = editor
                return editor
        return None

    def get_block(self, x: int, y: int, z: int) -> str:
        section = self.section(math.floor(y / 16))
        if section is None:
            return AIR
        return section.get(x & 15, y & 15, z & 15)

    def get_block_state(self, x: int, y: int, z: int) -> tuple[str, dict[str, str]]:
        section = self.section(math.floor(y / 16))
        if section is None:
            return AIR, {}
        return section.get_state(x & 15, y & 15, z & 15)

    def set_block(self, x: int, y: int, z: int, block_name: str) -> bool:
        section = self.section(math.floor(y / 16))
        if section is None:
            return False
        changed = section.set(x & 15, y & 15, z & 15, block_name)
        if changed:
            self.dirty = True
        return changed

    def set_block_state(
        self,
        x: int,
        y: int,
        z: int,
        block_name: str,
        properties: dict[str, str],
    ) -> bool:
        section = self.section(math.floor(y / 16))
        if section is None:
            return False
        changed = section.set_state(x & 15, y & 15, z & 15, block_name, properties)
        if changed:
            self.dirty = True
        return changed

    def flush(self) -> None:
        if not self.dirty:
            return
        for section in self._sections.values():
            section.compact()
        self.update_heightmaps()
        self.root["LastUpdate"] = tag.Long(int(time.time() * 20))
        self.dirty = False

    def update_heightmaps(self) -> None:
        heightmaps = self.root.get("Heightmaps")
        if not heightmaps:
            return
        min_section_y = min(int(section["Y"]) for section in self.root.get("sections", []))
        min_world_y = min_section_y * 16
        heights = [0] * 256
        for local_z in range(16):
            for local_x in range(16):
                top_y = self.top_y_at(local_x, local_z)
                if top_y is not None:
                    heights[local_z * 16 + local_x] = max(0, top_y + 1 - min_world_y)
        packed = tag.LongArray(pack_fixed_width(heights, 9))
        for key in list(heightmaps.keys()):
            heightmaps[key] = packed.copy()

    def top_y_at(self, local_x: int, local_z: int) -> int | None:
        top: int | None = None
        for section in self.root.get("sections", []):
            section_y = int(section["Y"])
            editor = self.section(section_y)
            if editor is None:
                continue
            for local_y in range(16):
                name = editor.get(local_x, local_y, local_z)
                if name not in AIR_BLOCKS:
                    world_y = section_y * 16 + local_y
                    if top is None or world_y > top:
                        top = world_y
        return top


class RegionEditor:
    def __init__(self, path: Path):
        self.path = path
        self.locations: dict[int, RegionLocation] = {}
        self.raw_records: dict[int, bytes] = {}
        self.chunks: dict[int, ChunkEditor] = {}
        self.modified: set[int] = set()
        self._read_header()

    def _read_header(self) -> None:
        if not self.path.is_file():
            return
        with self.path.open("rb") as handle:
            header = handle.read(8192)
            if len(header) < 8192:
                raise ValueError(f"truncated region header: {self.path}")
            for index in range(1024):
                location = header[index * 4 : index * 4 + 4]
                offset = int.from_bytes(location[:3], "big")
                sectors = location[3]
                timestamp = int.from_bytes(header[4096 + index * 4 : 4100 + index * 4], "big")
                if offset == 0:
                    continue
                self.locations[index] = RegionLocation(offset, sectors, timestamp)
                handle.seek(offset * 4096)
                length_bytes = handle.read(4)
                if len(length_bytes) != 4:
                    raise ValueError(f"truncated chunk length in {self.path} at {index}")
                length = int.from_bytes(length_bytes, "big")
                if length <= 1:
                    raise ValueError(f"invalid chunk length in {self.path} at {index}: {length}")
                payload = handle.read(length)
                if len(payload) != length:
                    raise ValueError(f"truncated chunk payload in {self.path} at {index}")
                self.raw_records[index] = length_bytes + payload

    def chunk(self, chunk_x: int, chunk_z: int) -> ChunkEditor | None:
        index = region_chunk_index(chunk_x, chunk_z)
        cached = self.chunks.get(index)
        if cached is not None:
            return cached
        record = self.raw_records.get(index)
        if record is None:
            return None
        root = parse_chunk_record(record, self.path, index)
        editor = ChunkEditor(root)
        self.chunks[index] = editor
        return editor

    def mark_modified(self, chunk_x: int, chunk_z: int) -> None:
        self.modified.add(region_chunk_index(chunk_x, chunk_z))

    def save(self) -> int:
        if not self.modified:
            return 0
        for index in self.modified:
            chunk = self.chunks.get(index)
            if chunk is not None:
                chunk.flush()
                self.raw_records[index] = serialize_chunk_record(chunk.root)

        body = bytearray()
        locations = bytearray(4096)
        timestamps = bytearray(4096)
        sector_offset = 2
        now = int(time.time())
        for index in range(1024):
            record = self.raw_records.get(index)
            if record is None:
                continue
            sector_count = math.ceil(len(record) / 4096)
            if sector_count > 255:
                raise ValueError(f"chunk {index} in {self.path} needs {sector_count} sectors")
            locations[index * 4 : index * 4 + 4] = (
                sector_offset.to_bytes(3, "big") + bytes([sector_count])
            )
            location = self.locations.get(index)
            stamp = now if index in self.modified else (location.timestamp if location else now)
            timestamps[index * 4 : index * 4 + 4] = int(stamp).to_bytes(4, "big")
            body.extend(record)
            body.extend(b"\x00" * (sector_count * 4096 - len(record)))
            sector_offset += sector_count

        output = self.path.with_suffix(self.path.suffix + ".tmp")
        with output.open("wb") as handle:
            handle.write(locations)
            handle.write(timestamps)
            handle.write(body)
        output.replace(self.path)
        return len(self.modified)


class AnvilWorld:
    def __init__(self, world_path: Path):
        self.world_path = world_path
        self.region_dir = world_path / "region"
        if not self.region_dir.is_dir():
            raise FileNotFoundError(f"world has no region directory: {self.region_dir}")
        self._regions: dict[tuple[int, int], RegionEditor] = {}
        self.changed_blocks = 0
        self.skipped_missing_chunks = 0

    def region(self, chunk_x: int, chunk_z: int) -> RegionEditor:
        key = (math.floor(chunk_x / 32), math.floor(chunk_z / 32))
        editor = self._regions.get(key)
        if editor is None:
            editor = RegionEditor(self.region_dir / f"r.{key[0]}.{key[1]}.mca")
            self._regions[key] = editor
        return editor

    def chunk(self, x: int, z: int) -> tuple[RegionEditor, ChunkEditor | None, int, int]:
        chunk_x = math.floor(x / 16)
        chunk_z = math.floor(z / 16)
        region = self.region(chunk_x, chunk_z)
        return region, region.chunk(chunk_x, chunk_z), chunk_x, chunk_z

    def get_block(self, x: int, y: int, z: int) -> str:
        _region, chunk, _chunk_x, _chunk_z = self.chunk(x, z)
        if chunk is None:
            return AIR
        return chunk.get_block(x, y, z)

    def get_block_state(self, x: int, y: int, z: int) -> tuple[str, dict[str, str]]:
        _region, chunk, _chunk_x, _chunk_z = self.chunk(x, z)
        if chunk is None:
            return AIR, {}
        return chunk.get_block_state(x, y, z)

    def set_block(self, x: int, y: int, z: int, block_name: str) -> bool:
        region, chunk, chunk_x, chunk_z = self.chunk(x, z)
        if chunk is None:
            self.skipped_missing_chunks += 1
            return False
        if chunk.set_block(x, y, z, block_name):
            region.mark_modified(chunk_x, chunk_z)
            self.changed_blocks += 1
            return True
        return False

    def set_block_state(
        self,
        x: int,
        y: int,
        z: int,
        block_name: str,
        properties: dict[str, str],
    ) -> bool:
        region, chunk, chunk_x, chunk_z = self.chunk(x, z)
        if chunk is None:
            self.skipped_missing_chunks += 1
            return False
        if chunk.set_block_state(x, y, z, block_name, properties):
            region.mark_modified(chunk_x, chunk_z)
            self.changed_blocks += 1
            return True
        return False

    def save(self) -> int:
        touched = 0
        for region in self._regions.values():
            touched += region.save()
        return touched


def lat_lon_to_ecef(latitude: float, longitude: float, altitude: float) -> tuple[float, float, float]:
    axis = 6_378_137.0
    flattening = 1.0 / 298.257223563
    eccentricity_sq = flattening * (2.0 - flattening)
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    prime_vertical = axis / math.sqrt(1.0 - eccentricity_sq * sin_lat * sin_lat)
    return (
        (prime_vertical + altitude) * cos_lat * math.cos(lon),
        (prime_vertical + altitude) * cos_lat * math.sin(lon),
        (prime_vertical * (1.0 - eccentricity_sq) + altitude) * sin_lat,
    )


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def parse_chunk_record(record: bytes, source: Path, index: int) -> nbtlib.File:
    length = int.from_bytes(record[:4], "big")
    compression = record[4]
    payload = record[5 : 4 + length]
    if compression == 1:
        raw = zlib.decompress(payload, wbits=16 + zlib.MAX_WBITS)
    elif compression == 2:
        raw = zlib.decompress(payload)
    elif compression == 3:
        raw = payload
    else:
        raise ValueError(f"unsupported compression {compression} in {source} chunk {index}")
    return nbtlib.File.parse(io.BytesIO(raw))


def serialize_chunk_record(root: nbtlib.File) -> bytes:
    handle = io.BytesIO()
    root.write(handle)
    compressed = zlib.compress(handle.getvalue(), level=6)
    length = len(compressed) + 1
    return length.to_bytes(4, "big") + b"\x02" + compressed


def palette_name(entry: Any) -> str:
    return str(entry.get("Name", AIR))


def palette_properties(entry: Any) -> dict[str, str]:
    properties = entry.get("Properties")
    if not properties:
        return {}
    return {str(key): str(value) for key, value in properties.items()}


def block_state_key(
    block_name: str,
    properties: dict[str, str] | None = None,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    return str(block_name), tuple(
        sorted((str(key), str(value)) for key, value in (properties or {}).items())
    )


def palette_state_key(entry: Any) -> tuple[str, tuple[tuple[str, str], ...]]:
    return block_state_key(palette_name(entry), palette_properties(entry))


def block_entry(
    block_name: str,
    properties: dict[str, str] | None = None,
) -> tag.Compound:
    entry = tag.Compound({"Name": tag.String(block_name)})
    if properties:
        entry["Properties"] = tag.Compound(
            {
                str(key): tag.String(str(value))
                for key, value in sorted(properties.items())
            }
        )
    return entry


def section_block_states(section: Any) -> tuple[list[tag.Compound], Any | None] | None:
    states = section.get("block_states") or section.get("BlockStates")
    if not states:
        return None
    palette = states.get("palette") or states.get("Palette")
    if not palette:
        return None
    data = states.get("data") if "data" in states else states.get("Data")
    return list(palette), data


def bits_for_palette_size(palette_size: int) -> int:
    return max(4, (palette_size - 1).bit_length())


def unpack_indices(palette_size: int, data: Any | None) -> list[int]:
    if data is None or len(data) == 0:
        return [0] * 4096
    bits = bits_for_palette_size(palette_size)
    values_per_long = 64 // bits
    mask = (1 << bits) - 1
    words = [int(value) & ((1 << 64) - 1) for value in data]
    values: list[int] = []
    for index in range(4096):
        word_index = index // values_per_long
        if word_index >= len(words):
            values.append(0)
            continue
        shift = (index % values_per_long) * bits
        values.append((words[word_index] >> shift) & mask)
    return values


def pack_indices(indices: list[int], palette_size: int) -> list[int]:
    return pack_fixed_width(indices, bits_for_palette_size(palette_size))


def pack_fixed_width(indices: list[int], bits: int) -> list[int]:
    values_per_long = 64 // bits
    words = [0] * math.ceil(len(indices) / values_per_long)
    mask = (1 << bits) - 1
    for index, value in enumerate(indices):
        if value < 0 or value > mask:
            raise ValueError(f"value {value} cannot be packed into {bits} bits")
        word_index = index // values_per_long
        shift = (index % values_per_long) * bits
        words[word_index] |= int(value) << shift
    return [to_signed_long(word) for word in words]


def to_signed_long(value: int) -> int:
    value &= (1 << 64) - 1
    if value >= (1 << 63):
        value -= 1 << 64
    return value


def section_index(local_x: int, local_y: int, local_z: int) -> int:
    return (local_y << 8) | (local_z << 4) | local_x


def region_chunk_index(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + ((chunk_z & 31) * 32)


def iter_world_chunks(world_path: Path) -> Iterator[tuple[int, int, nbtlib.File]]:
    region_dir = world_path / "region"
    for region_path in sorted(region_dir.glob("r.*.*.mca")):
        region = RegionEditor(region_path)
        for index in sorted(region.raw_records):
            root = parse_chunk_record(region.raw_records[index], region_path, index)
            yield int(root["xPos"]), int(root["zPos"]), root


def iter_region_records(world_path: Path) -> Iterator[tuple[int, int, bytes]]:
    region_dir = world_path / "region"
    for region_path in sorted(region_dir.glob("r.*.*.mca")):
        match = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", region_path.name)
        if match is None:
            continue
        region_x = int(match.group(1))
        region_z = int(match.group(2))
        region = RegionEditor(region_path)
        for index, record in region.raw_records.items():
            chunk_x = region_x * 32 + (index & 31)
            chunk_z = region_z * 32 + (index >> 5)
            yield chunk_x, chunk_z, record


def iter_chunk_blocks(root: nbtlib.File) -> Iterator[tuple[int, int, int, str]]:
    chunk_x = int(root["xPos"])
    chunk_z = int(root["zPos"])
    for section in root.get("sections", []):
        parsed = section_block_states(section)
        if parsed is None:
            continue
        entries, data = parsed
        names = [palette_name(entry) for entry in entries]
        section_y = int(section["Y"])
        if data is None or len(data) == 0:
            name = names[0]
            if name in AIR_BLOCKS:
                continue
            for local_y in range(16):
                y = section_y * 16 + local_y
                for local_z in range(16):
                    z = chunk_z * 16 + local_z
                    for local_x in range(16):
                        yield chunk_x * 16 + local_x, y, z, name
            continue
        for linear, palette_index in enumerate(unpack_indices(len(names), data)):
            if palette_index >= len(names):
                continue
            name = names[palette_index]
            if name in AIR_BLOCKS:
                continue
            local_y = linear >> 8
            local_z = (linear >> 4) & 15
            local_x = linear & 15
            yield (
                chunk_x * 16 + local_x,
                section_y * 16 + local_y,
                chunk_z * 16 + local_z,
                name,
            )


def section_dense_blocks(section: Any) -> list[str]:
    parsed = section_block_states(section)
    if parsed is None:
        return [AIR] * 4096
    entries, data = parsed
    names = [palette_name(entry) for entry in entries]
    if not names:
        return [AIR] * 4096
    if data is None or len(data) == 0:
        return [names[0]] * 4096
    indices = unpack_indices(len(names), data)
    return [names[index] if 0 <= index < len(names) else AIR for index in indices]


def root_sections_by_y(root: nbtlib.File) -> dict[int, list[str]]:
    sections: dict[int, list[str]] = {}
    for section in root.get("sections", []):
        sections[int(section["Y"])] = section_dense_blocks(section)
    return sections


def load_top_surface(world_path: Path) -> dict[tuple[int, int], tuple[int, str]]:
    top: dict[tuple[int, int], tuple[int, str]] = {}
    for _chunk_x, _chunk_z, root in iter_world_chunks(world_path):
        for x, y, z, name in iter_chunk_blocks(root):
            key = (x, z)
            if key not in top or y > top[key][0]:
                top[key] = (y, name)
    if not top:
        raise ValueError(f"world contains no non-air top surface: {world_path}")
    return top


def denormalize_vertices(cityjson: dict[str, Any]) -> list[tuple[float, float, float]]:
    transform = cityjson.get("transform") or {}
    scale = transform.get("scale") or [1.0, 1.0, 1.0]
    translate = transform.get("translate") or [0.0, 0.0, 0.0]
    vertices = []
    for vertex in cityjson.get("vertices", []):
        vertices.append(
            (
                float(vertex[0]) * float(scale[0]) + float(translate[0]),
                float(vertex[1]) * float(scale[1]) + float(translate[1]),
                float(vertex[2]) * float(scale[2]) + float(translate[2]),
            )
        )
    return vertices


def load_roofer_buildings(cityjson_path: Path, transform: WorldTransform) -> list[BuildingModel]:
    cityjson = json.loads(cityjson_path.read_text(encoding="utf-8"))
    source_vertices = denormalize_vertices(cityjson)
    transformer = Transformer.from_crs("EPSG:6347", "EPSG:4326", always_xy=True)
    world_vertices = [
        (*transform.metric_to_block(transformer, x, y), z)
        for x, y, z in source_vertices
    ]

    objects = cityjson.get("CityObjects", {})
    parents_by_child: dict[str, dict[str, Any]] = {}
    for obj in objects.values():
        for child in obj.get("children", []) or []:
            parents_by_child[str(child)] = obj

    buildings: list[BuildingModel] = []
    for identifier, obj in objects.items():
        for geom in obj.get("geometry", []) or []:
            if str(geom.get("lod")) != "2.2" or geom.get("type") != "Solid":
                continue
            parent = parents_by_child.get(identifier, {})
            attributes = dict(parent.get("attributes", {}) or {})
            attributes.update(obj.get("attributes", {}) or {})
            model = parse_lod22_building(
                str(identifier),
                attributes,
                geom,
                world_vertices,
                source_vertices,
            )
            if model is not None:
                buildings.append(model)
    if not buildings:
        raise ValueError(f"no LoD2.2 buildings found in {cityjson_path}")
    return buildings


def parse_lod22_building(
    identifier: str,
    attributes: dict[str, Any],
    geom: dict[str, Any],
    world_vertices: list[tuple[float, float, float]],
    source_vertices: list[tuple[float, float, float]],
) -> BuildingModel | None:
    semantics = geom.get("semantics") or {}
    surfaces = semantics.get("surfaces") or []
    values = semantics.get("values") or []
    ground_rings: list[list[int]] = []
    wall_z: list[float] = []
    roof_faces: list[list[tuple[float, float, float]]] = []
    all_indices: list[int] = []

    for shell_index, shell in enumerate(geom.get("boundaries") or []):
        semantic_values = values[shell_index] if shell_index < len(values) else []
        for surface_index, surface in enumerate(shell):
            semantic_index = semantic_values[surface_index] if surface_index < len(semantic_values) else None
            surface_type = None
            if isinstance(semantic_index, int) and 0 <= semantic_index < len(surfaces):
                surface_type = surfaces[semantic_index].get("type")
            rings = surface if isinstance(surface, list) else []
            if not rings:
                continue
            outer = [int(value) for value in rings[0]]
            all_indices.extend(outer)
            if surface_type == "GroundSurface":
                ground_rings.append(outer)
            elif surface_type == "RoofSurface":
                roof_faces.append([world_vertices[index] for index in outer])
            elif surface_type == "WallSurface":
                for index in outer:
                    wall_z.append(source_vertices[index][2])

    if not all_indices:
        return None
    source_z_values = [source_vertices[index][2] for index in all_indices]
    source_base_z = min(source_z_values)
    source_max_z = max(source_z_values)
    if not wall_z:
        wall_z = source_z_values
    source_eave_z = percentile(wall_z, 0.88)

    footprints = []
    candidate_rings = ground_rings or [lowest_horizontal_ring(geom, source_vertices)]
    for ring in candidate_rings:
        if not ring:
            continue
        coords = [(world_vertices[index][0], world_vertices[index][1]) for index in ring]
        polygon = clean_polygon(Polygon(coords))
        if polygon is None or polygon.area < 2.0:
            continue
        if isinstance(polygon, Polygon):
            footprints.append(polygon)
        elif isinstance(polygon, MultiPolygon):
            footprints.extend(poly for poly in polygon.geoms if poly.area >= 2.0)

    if not footprints:
        return None
    name = str(
        attributes.get("IMPRNAME")
        or attributes.get("DESCRIPTION")
        or attributes.get("name")
        or identifier
    )
    return BuildingModel(
        identifier=identifier,
        name=name,
        attributes=attributes,
        footprints=footprints,
        roof_faces=roof_faces,
        source_base_z=source_base_z,
        source_max_z=source_max_z,
        source_eave_z=source_eave_z,
    )


def lowest_horizontal_ring(geom: dict[str, Any], source_vertices: list[tuple[float, float, float]]) -> list[int]:
    rings: list[list[int]] = []
    for shell in geom.get("boundaries") or []:
        for surface in shell:
            if surface and isinstance(surface, list):
                rings.append([int(value) for value in surface[0]])
    if not rings:
        return []
    return min(rings, key=lambda ring: sum(source_vertices[index][2] for index in ring) / len(ring))


def clean_polygon(polygon: Polygon) -> BaseGeometry | None:
    if polygon.is_empty:
        return None
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    return polygon


def percentile(values: Iterable[float | int], quantile: float) -> float:
    data = sorted(float(value) for value in values)
    if not data:
        raise ValueError("percentile requires at least one value")
    index = min(len(data) - 1, max(0, int(round((len(data) - 1) * quantile))))
    return data[index]


def sample_building_bases(
    buildings: list[BuildingModel],
    top_surface: dict[tuple[int, int], tuple[int, str]],
) -> None:
    for building in buildings:
        geometry = building.footprint_union
        annulus = geometry.buffer(7.0).difference(geometry.buffer(1.0))
        candidates = sample_top_y(top_surface, annulus, step=1)
        if len(candidates) < 8:
            candidates = sample_top_y(top_surface, geometry.buffer(3.0), step=1)
        if candidates:
            building.base_y = int(round(percentile(candidates, 0.25)))
        else:
            building.base_y = 70


def sample_top_y(
    top_surface: dict[tuple[int, int], tuple[int, str]],
    geometry: BaseGeometry,
    *,
    step: int,
) -> list[int]:
    if geometry.is_empty:
        return []
    prepared = prep(geometry)
    minx, minz, maxx, maxz = geometry.bounds
    values: list[int] = []
    for x in range(math.floor(minx), math.ceil(maxx) + 1, step):
        for z in range(math.floor(minz), math.ceil(maxz) + 1, step):
            if not prepared.contains(Point(x + 0.5, z + 0.5)):
                continue
            entry = top_surface.get((x, z))
            if entry is not None:
                values.append(entry[0])
    return values


def chunk_at(world_path: Path, chunk_x: int, chunk_z: int) -> nbtlib.File | None:
    region_x = math.floor(chunk_x / 32)
    region_z = math.floor(chunk_z / 32)
    region_path = world_path / "region" / f"r.{region_x}.{region_z}.mca"
    if not region_path.is_file():
        return None
    region = RegionEditor(region_path)
    record = region.raw_records.get(region_chunk_index(chunk_x, chunk_z))
    if record is None:
        return None
    return parse_chunk_record(record, region_path, region_chunk_index(chunk_x, chunk_z))


def audit_unmasked_changes(
    source_world: Path,
    target_world: Path,
    edit_mask: set[tuple[int, int, int]],
    *,
    max_samples: int = 50,
    dense_chunk_limit: int = 900,
) -> dict[str, Any]:
    """Assert the VoxelEarth source remains unchanged outside the edit mask.

    Chunks with no allowed edits must be byte-identical. Chunks containing
    allowed edits are compared block-by-block, including air, outside the exact
    (x, y, z) edit mask.
    """

    allowed_chunks = {(math.floor(x / 16), math.floor(z / 16)) for x, _y, z in edit_mask}
    source_records = {(chunk_x, chunk_z): record for chunk_x, chunk_z, record in iter_region_records(source_world)}
    target_records = {(chunk_x, chunk_z): record for chunk_x, chunk_z, record in iter_region_records(target_world)}
    all_chunks = set(source_records) | set(target_records)

    raw_mismatches: list[dict[str, Any]] = []
    checked_raw_chunks = 0
    for chunk_key in sorted(all_chunks):
        if chunk_key in allowed_chunks:
            continue
        checked_raw_chunks += 1
        if source_records.get(chunk_key) != target_records.get(chunk_key):
            if len(raw_mismatches) < max_samples:
                raw_mismatches.append({"chunk": list(chunk_key)})

    if len(allowed_chunks) <= dense_chunk_limit:
        audit_mode = "dense-all-section-blocks"
        block_mismatches, checked_blocks, checked_edit_chunks = audit_dense_edit_chunks(
            source_world,
            target_world,
            allowed_chunks,
            edit_mask,
            max_samples=max_samples,
        )
    else:
        audit_mode = "sparse-non-air-diff"
        block_mismatches, checked_blocks, checked_edit_chunks = audit_sparse_non_air(
            source_world,
            target_world,
            edit_mask,
            max_samples=max_samples,
        )

    payload = {
        "mode": audit_mode,
        "source_world": str(source_world),
        "target_world": str(target_world),
        "edit_mask_blocks": len(edit_mask),
        "edit_mask_chunks": len(allowed_chunks),
        "raw_unchanged_chunks_checked": checked_raw_chunks,
        "edit_chunks_block_checked": checked_edit_chunks,
        "blocks_outside_edit_mask_checked": checked_blocks,
        "raw_mismatches_outside_edit_chunks": len(raw_mismatches),
        "block_mismatches_outside_edit_mask": len(block_mismatches),
        "raw_mismatch_samples": raw_mismatches,
        "block_mismatch_samples": block_mismatches,
    }
    if raw_mismatches or block_mismatches:
        raise AssertionError(json.dumps(payload, indent=2))
    return payload


def audit_dense_edit_chunks(
    source_world: Path,
    target_world: Path,
    allowed_chunks: set[tuple[int, int]],
    edit_mask: set[tuple[int, int, int]],
    *,
    max_samples: int,
) -> tuple[list[dict[str, Any]], int, int]:
    block_mismatches: list[dict[str, Any]] = []
    checked_blocks = 0
    checked_edit_chunks = 0
    for chunk_x, chunk_z in sorted(allowed_chunks):
        source_root = chunk_at(source_world, chunk_x, chunk_z)
        target_root = chunk_at(target_world, chunk_x, chunk_z)
        if source_root is None or target_root is None:
            if source_root is not target_root and len(block_mismatches) < max_samples:
                block_mismatches.append(
                    {
                        "chunk": [chunk_x, chunk_z],
                        "source_present": source_root is not None,
                        "target_present": target_root is not None,
                    }
                )
            continue
        checked_edit_chunks += 1
        source_sections = root_sections_by_y(source_root)
        target_sections = root_sections_by_y(target_root)
        for section_y in sorted(set(source_sections) | set(target_sections)):
            source_blocks = source_sections.get(section_y, [AIR] * 4096)
            target_blocks = target_sections.get(section_y, [AIR] * 4096)
            for linear in range(4096):
                local_x = linear & 15
                local_y = linear >> 8
                local_z = (linear >> 4) & 15
                x = chunk_x * 16 + local_x
                y = section_y * 16 + local_y
                z = chunk_z * 16 + local_z
                if (x, y, z) in edit_mask:
                    continue
                checked_blocks += 1
                source_name = source_blocks[linear]
                target_name = target_blocks[linear]
                if source_name == target_name:
                    continue
                if len(block_mismatches) < max_samples:
                    block_mismatches.append(
                        {
                            "coordinate": [x, y, z],
                            "source": source_name,
                            "target": target_name,
                        }
                    )
    return block_mismatches, checked_blocks, checked_edit_chunks


def audit_sparse_non_air(
    source_world: Path,
    target_world: Path,
    edit_mask: set[tuple[int, int, int]],
    *,
    max_samples: int,
) -> tuple[list[dict[str, Any]], int, int]:
    block_mismatches: list[dict[str, Any]] = []
    checked_blocks = 0
    target_reader = AnvilWorld(target_world)
    for _chunk_x, _chunk_z, root in iter_world_chunks(source_world):
        for x, y, z, source_name in iter_chunk_blocks(root):
            if (x, y, z) in edit_mask:
                continue
            checked_blocks += 1
            target_name = target_reader.get_block(x, y, z)
            if target_name == source_name:
                continue
            if len(block_mismatches) < max_samples:
                block_mismatches.append(
                    {
                        "coordinate": [x, y, z],
                        "source": source_name,
                        "target": target_name,
                    }
                )

    source_reader = AnvilWorld(source_world)
    for _chunk_x, _chunk_z, root in iter_world_chunks(target_world):
        for x, y, z, target_name in iter_chunk_blocks(root):
            if (x, y, z) in edit_mask:
                continue
            source_name = source_reader.get_block(x, y, z)
            if source_name == target_name:
                continue
            checked_blocks += 1
            if len(block_mismatches) < max_samples:
                block_mismatches.append(
                    {
                        "coordinate": [x, y, z],
                        "source": source_name,
                        "target": target_name,
                    }
                )
    checked_chunks = len({(chunk_x, chunk_z) for chunk_x, chunk_z, _root in iter_world_chunks(source_world)})
    return block_mismatches, checked_blocks, checked_chunks


def build_terrain_surface(
    top_surface: dict[tuple[int, int], tuple[int, str]],
    *,
    smooth_radius: int,
    height_percentile: float,
    height_bias: float,
    target_columns: Iterable[tuple[int, int]] | None = None,
) -> dict[tuple[int, int], tuple[int, str]]:
    try:
        from scipy import ndimage
    except ImportError as exc:
        raise RuntimeError("terrain-only fallback requires scipy") from exc

    if not top_surface:
        raise ValueError("terrain surface requires at least one source column")
    targets = set(top_surface) if target_columns is None else set(target_columns)
    if not targets:
        return {}
    extent_columns = set(top_surface) | targets
    xs = [x for x, _z in extent_columns]
    zs = [z for _x, z in extent_columns]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)
    width = max_x - min_x + 1
    height = max_z - min_z + 1

    y_grid = np.zeros((height, width), dtype=np.float32)
    category_grid = np.zeros((height, width), dtype=np.uint8)
    valid = np.zeros((height, width), dtype=bool)
    for (x, z), (y, block) in top_surface.items():
        row = z - min_z
        col = x - min_x
        y_grid[row, col] = float(y)
        category_grid[row, col] = classify_ground_category(block)
        valid[row, col] = True

    missing = ~valid
    if missing.any():
        nearest = ndimage.distance_transform_edt(missing, return_distances=False, return_indices=True)
        y_grid = y_grid[tuple(nearest)]

    category_valid = category_grid > 0
    if category_valid.any() and (~category_valid).any():
        nearest_category = ndimage.distance_transform_edt(
            ~category_valid,
            return_distances=False,
            return_indices=True,
        )
        category_grid = category_grid[tuple(nearest_category)]
    category_grid[category_grid == 0] = 3

    size = smooth_radius * 2 + 1
    terrain_grid = ndimage.percentile_filter(
        y_grid,
        percentile=height_percentile,
        size=size,
        mode="nearest",
    )

    terrain_surface: dict[tuple[int, int], tuple[int, str]] = {}
    for x, z in sorted(targets):
        row = z - min_z
        col = x - min_x
        terrain_y = int(round(float(terrain_grid[row, col]) + height_bias))
        category = int(category_grid[row, col])
        terrain_surface[(x, z)] = (terrain_y, GROUND_CATEGORY_BLOCKS.get(category, "minecraft:smooth_stone"))
    return terrain_surface


def constrain_terrain_to_building_floors(
    terrain_surface: dict[tuple[int, int], tuple[int, str]],
    building_ground_ys: dict[tuple[int, int], int],
) -> dict[tuple[int, int], tuple[int, str]]:
    """Grade terrain into each building floor without stamping a flat apron.

    Every footprint column is fixed to one block below its procedural floor.
    Other terrain columns retain their smoothed height unless it would require a
    step steeper than one block per horizontal block to reach the nearest floor.
    """

    constraints = {
        column: int(ground_y)
        for column, ground_y in building_ground_ys.items()
        if column in terrain_surface
    }
    if not terrain_surface:
        return dict(terrain_surface)
    try:
        from scipy import ndimage
    except ImportError as exc:
        raise RuntimeError("building-constrained terrain requires scipy") from exc

    xs = [x for x, _z in terrain_surface]
    zs = [z for _x, z in terrain_surface]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)
    width = max_x - min_x + 1
    height = max_z - min_z + 1
    target_mask = np.zeros((height, width), dtype=bool)
    base_y = np.zeros((height, width), dtype=np.int16)
    for (x, z), (terrain_y, _surface_block) in terrain_surface.items():
        row = z - min_z
        col = x - min_x
        target_mask[row, col] = True
        base_y[row, col] = terrain_y

    def height_envelopes(
        values: np.ndarray,
        valid_mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        lower = np.full(values.shape, np.iinfo(np.int32).min, dtype=np.int32)
        upper = np.full(values.shape, np.iinfo(np.int32).max, dtype=np.int32)
        for value in np.unique(values[valid_mask]):
            sources = valid_mask & (values == value)
            distance = ndimage.distance_transform_cdt(~sources, metric="taxicab")
            lower = np.maximum(lower, int(value) - distance)
            upper = np.minimum(upper, int(value) + distance)
        return lower, upper

    base_lower, base_upper = height_envelopes(base_y, target_mask)
    walkable_y = np.floor_divide(base_lower + base_upper, 2)

    constraint_mask = np.zeros((height, width), dtype=bool)
    constraint_y = np.zeros((height, width), dtype=np.int16)
    for (x, z), ground_y in constraints.items():
        row = z - min_z
        col = x - min_x
        constraint_mask[row, col] = True
        constraint_y[row, col] = ground_y

    if constraints:
        distances, nearest = ndimage.distance_transform_edt(
            ~constraint_mask,
            return_distances=True,
            return_indices=True,
        )
        nearest_y = constraint_y[tuple(nearest)]
        allowed_delta = np.ceil(distances).astype(np.int32)
        walkable_y = np.minimum(
            np.maximum(walkable_y, nearest_y - allowed_delta),
            nearest_y + allowed_delta,
        )

    graded: dict[tuple[int, int], tuple[int, str]] = {}
    for column, (terrain_y, surface_block) in terrain_surface.items():
        x, z = column
        row = z - min_z
        col = x - min_x
        graded_y = int(walkable_y[row, col])
        if column in constraints:
            graded_y = constraints[column]
            surface_block = "minecraft:smooth_stone"
        graded[column] = (graded_y, surface_block)
    return graded


def classify_ground_category(block: str) -> int:
    name = block.removeprefix("minecraft:")
    if name == "water":
        return 2
    if name in {"grass_block", "moss_block"} or "leaves" in name or "log" in name or "wood" in name:
        return 1
    if name in {"dirt", "coarse_dirt", "rooted_dirt", "mud", "packed_mud"}:
        return 5
    if (
        "concrete" in name
        or "stone" in name
        or "sandstone" in name
        or name in {"andesite", "diorite", "granite", "sand", "red_sand"}
    ):
        return 3
    return 0


def subsurface_block_for(surface_block: str) -> str:
    if surface_block == "minecraft:grass_block":
        return "minecraft:dirt"
    if surface_block == "minecraft:water":
        return "minecraft:dirt"
    return "minecraft:smooth_stone"


def srgb_channel_to_linear(value: int) -> float:
    channel = value / 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def cbrt(value: float) -> float:
    if value >= 0:
        return value ** (1.0 / 3.0)
    return -((-value) ** (1.0 / 3.0))


@lru_cache(maxsize=None)
def rgb_to_oklab(color: tuple[int, int, int]) -> tuple[float, float, float]:
    r = srgb_channel_to_linear(color[0])
    g = srgb_channel_to_linear(color[1])
    b = srgb_channel_to_linear(color[2])
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_ = cbrt(l)
    m_ = cbrt(m)
    s_ = cbrt(s)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def nearest_palette_block(color: tuple[int, int, int], palette: Iterable[str]) -> str:
    candidates = [name for name in palette if name in MATERIAL_COLORS]
    if not candidates:
        raise ValueError("palette has no known material colors")
    source = rgb_to_oklab(color)
    return min(candidates, key=lambda name: oklab_distance(source, rgb_to_oklab(MATERIAL_COLORS[name])))


def is_source_facade_candidate(block: str) -> bool:
    name = block.removeprefix("minecraft:")
    if block in NOISY_DARK_BLOCKS:
        return False
    if name in {"sand", "red_sand"}:
        return False
    if any(part in name for part in GROUND_OR_NOISE_PARTS):
        return False
    return block in MATERIAL_COLORS


def dominant_palette_block(
    samples: Counter[str],
    palette: Iterable[str],
    fallback: str,
) -> tuple[str, int]:
    mapped: Counter[str] = Counter()
    for block, count in samples.items():
        color = MATERIAL_COLORS.get(block)
        if color is None:
            continue
        mapped[nearest_palette_block(color, palette)] += count
    if not mapped:
        return fallback, 0
    block, count = mapped.most_common(1)[0]
    return block, int(count)


def trim_for_wall_material(wall: str) -> str:
    color = MATERIAL_COLORS.get(wall)
    if color is None:
        return "minecraft:stone_bricks"
    return nearest_palette_block(color, TRIM_PALETTE)


def sample_source_block_neighborhood(
    reader: AnvilWorld,
    x: int,
    y: int,
    z: int,
) -> Iterator[str]:
    for dy in (-1, 0, 1):
        for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            yield reader.get_block(x + dx, y + dy, z + dz)


def material_set_from_source(
    source_reader: AnvilWorld,
    raw_blocks: set[tuple[int, int, int]],
    *,
    name: str,
    min_y: int,
    max_y: int,
) -> tuple[dict[str, str], dict[str, Any]]:
    wall_samples: Counter[str] = Counter()
    roof_samples: Counter[str] = Counter()
    window_samples: Counter[str] = Counter()

    for x, y, z in raw_blocks:
        role = overlay_block_role(raw_blocks, x, y, z)
        if role not in {"wall_x", "wall_z", "wall_corner", "roof"}:
            continue
        for sample in sample_source_block_neighborhood(source_reader, x, y, z):
            if "glass" in sample:
                window_samples[sample] += 1
                continue
            if not is_source_facade_candidate(sample):
                continue
            if role == "roof":
                roof_samples[sample] += 1
            else:
                wall_samples[sample] += 1

    is_chapel = is_chapel_name(name)
    fallback = dict(CHAPEL_LANDMARK_MATERIALS) if is_chapel else material_set_for_text("", "")

    wall, wall_votes = dominant_palette_block(wall_samples, FACADE_PALETTE, fallback["wall"])
    roof, roof_votes = dominant_palette_block(roof_samples, ROOF_PALETTE, fallback["roof"])
    window = window_samples.most_common(1)[0][0] if window_samples else fallback["window"]
    material_override = None
    if is_chapel:
        wall = CHAPEL_LANDMARK_MATERIALS["wall"]
        roof = CHAPEL_LANDMARK_MATERIALS["roof"]
        window = CHAPEL_LANDMARK_MATERIALS["window"]
        trim = CHAPEL_LANDMARK_MATERIALS["trim"]
        material_override = "chapel-landmark"
    else:
        trim = trim_for_wall_material(wall)
    materials = {
        "wall": wall,
        "trim": trim,
        "roof": roof,
        "window": window,
        "floor": "minecraft:smooth_stone",
    }
    return materials, {
        "wall_material": wall,
        "trim_material": materials["trim"],
        "roof_material": roof,
        "window_material": window,
        "material_override": material_override,
        "source_wall_samples": int(sum(wall_samples.values())),
        "source_roof_samples": int(sum(roof_samples.values())),
        "source_window_samples": int(sum(window_samples.values())),
        "wall_palette_votes": wall_votes,
        "roof_palette_votes": roof_votes,
        "wall_source_blocks": dict(wall_samples.most_common(6)),
        "roof_source_blocks": dict(roof_samples.most_common(6)),
    }


def aggregate_facade_palette(overlay: VoxelBuildingOverlay) -> dict[str, Any]:
    sampled_buildings = 0
    material_counts: Counter[str] = Counter()
    trim_counts: Counter[str] = Counter()
    roof_counts: Counter[str] = Counter()
    window_counts: Counter[str] = Counter()
    source_wall_blocks: Counter[str] = Counter()
    source_roof_blocks: Counter[str] = Counter()
    placed_wall_blocks: Counter[str] = Counter()
    placed_roof_blocks: Counter[str] = Counter()
    source_wall_samples = 0
    source_roof_samples = 0
    source_window_samples = 0

    for anchor in overlay.anchors:
        sample = anchor.get("material_sample") or {}
        wall_sample_count = int(sample.get("source_wall_samples") or 0)
        roof_sample_count = int(sample.get("source_roof_samples") or 0)
        window_sample_count = int(sample.get("source_window_samples") or 0)
        if wall_sample_count > 0:
            sampled_buildings += 1
        source_wall_samples += wall_sample_count
        source_roof_samples += roof_sample_count
        source_window_samples += window_sample_count

        wall = sample.get("wall_material")
        trim = sample.get("trim_material")
        roof = sample.get("roof_material")
        window = sample.get("window_material")
        if wall:
            material_counts[str(wall)] += 1
        if trim:
            trim_counts[str(trim)] += 1
        if roof:
            roof_counts[str(roof)] += 1
        if window:
            window_counts[str(window)] += 1
        source_wall_blocks.update(sample.get("wall_source_blocks") or {})
        source_roof_blocks.update(sample.get("roof_source_blocks") or {})

    for _x, _y, _z, block, role in overlay.blocks:
        if role in {"wall_x", "wall_z", "wall_corner"}:
            placed_wall_blocks[block] += 1
        elif role == "roof":
            placed_roof_blocks[block] += 1

    return {
        "mode": "voxelearth-dominant-facade-nearest-block",
        "colour_space": "oklab",
        "material_atlas": str(MATERIAL_ATLAS_PATH or DEFAULT_VANILLA_ATLAS),
        "candidate_count": len(FACADE_PALETTE),
        "sampled_buildings": sampled_buildings,
        "source_wall_samples": source_wall_samples,
        "source_roof_samples": source_roof_samples,
        "source_window_samples": source_window_samples,
        "material_counts": dict(material_counts.most_common()),
        "trim_material_counts": dict(trim_counts.most_common()),
        "roof_material_counts": dict(roof_counts.most_common()),
        "window_material_counts": dict(window_counts.most_common()),
        "placed_wall_block_counts": dict(placed_wall_blocks.most_common()),
        "placed_roof_block_counts": dict(placed_roof_blocks.most_common()),
        "source_wall_block_counts": dict(source_wall_blocks.most_common(20)),
        "source_roof_block_counts": dict(source_roof_blocks.most_common(20)),
    }


def apply_terrain_surface_cleanup(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    terrain_surface: dict[tuple[int, int], tuple[int, str]],
    *,
    minimum_y: int,
    fill_depth: int,
    edit_mask: set[tuple[int, int, int]],
) -> Counter[str]:
    stats: Counter[str] = Counter()
    for (x, z), (source_top_y, source_top_block) in source_top_surface.items():
        terrain_y, surface_block = terrain_surface[(x, z)]
        if source_top_y > terrain_y:
            for y in range(terrain_y + 1, source_top_y + 1):
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, AIR):
                    stats["cleared_above_ground"] += 1
        if source_top_block != surface_block or source_top_y != terrain_y:
            edit_mask.add((x, terrain_y, z))
            if world.set_block(x, terrain_y, z, surface_block):
                stats["surface_retyped"] += 1
        if fill_depth > 0:
            fill_block = subsurface_block_for(surface_block)
            for y in range(max(minimum_y, terrain_y - fill_depth), terrain_y):
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, fill_block):
                    stats["subsurface_retyped"] += 1
        stats["columns"] += 1
    return stats


def apply_campus_architecture_cleanup(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    campus_boundary: BaseGeometry,
    *,
    protected_building_columns: set[tuple[int, int]],
    minimum_y: int,
    fill_depth: int,
    smooth_radius: int,
    height_percentile: float,
    height_bias: float,
    sampling_padding: int,
    edit_mask: set[tuple[int, int, int]],
    building_ground_ys: dict[tuple[int, int], int] | None = None,
    ground_surface_out: dict[tuple[int, int], tuple[int, str]] | None = None,
    flat_ground_y: int | None = None,
) -> Counter[str]:
    """Reduce the official campus to clean terrain while retaining buildings.

    Building anchors are sampled before this function runs.  The terrain model
    therefore excludes every known Roofer footprint, uses a small padded window
    to avoid boundary artifacts, and only mutates columns whose centers are
    inside the official Hill campus boundary.
    """

    stats: Counter[str] = Counter()
    if campus_boundary.is_empty:
        return stats
    official_target_columns = set(geometry_integer_cells(campus_boundary))
    target_columns = set(official_target_columns)
    grade_frontier = set((building_ground_ys or {}).keys())
    grade_columns = set(grade_frontier)
    for _distance in range(max(BUILDING_GROUND_TRANSITION_RADIUS, sampling_padding)):
        next_frontier = {
            (x + dx, z + dz)
            for x, z in grade_frontier
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
        } - grade_columns
        grade_columns.update(next_frontier)
        grade_frontier = next_frontier
    target_columns.update(grade_columns)
    stats["official_boundary_columns"] = len(official_target_columns)
    stats["building_grade_extension_columns"] = len(
        target_columns - official_target_columns
    )
    stats["target_columns"] = len(target_columns)

    target_xs = [x for x, _z in target_columns]
    target_zs = [z for _x, z in target_columns]
    sample_min_x = min(target_xs) - max(0, sampling_padding)
    sample_max_x = max(target_xs) + max(0, sampling_padding)
    sample_min_z = min(target_zs) - max(0, sampling_padding)
    sample_max_z = max(target_zs) + max(0, sampling_padding)
    sample_surface = {
        (x, z): surface
        for (x, z), surface in source_top_surface.items()
        if sample_min_x <= x <= sample_max_x
        and sample_min_z <= z <= sample_max_z
        and (x, z) not in protected_building_columns
    }
    stats["sample_columns"] = len(sample_surface)
    if not sample_surface:
        return stats

    terrain_surface = build_terrain_surface(
        sample_surface,
        smooth_radius=smooth_radius,
        height_percentile=height_percentile,
        height_bias=height_bias,
        target_columns=target_columns,
    )
    if flat_ground_y is not None:
        terrain_surface = {
            column: (int(flat_ground_y), surface_block)
            for column, (_terrain_y, surface_block) in terrain_surface.items()
        }
        stats["flat_ground_y"] = int(flat_ground_y)
    building_ground_ys = building_ground_ys or {}
    terrain_surface = constrain_terrain_to_building_floors(
        terrain_surface,
        building_ground_ys,
    )
    ground_ys: list[int] = []
    for (x, z), (terrain_y, surface_block) in sorted(terrain_surface.items()):
        source_top = source_top_surface.get((x, z))
        source_top_y = source_top[0] if source_top is not None else None
        source_top_block = source_top[1] if source_top is not None else AIR
        if source_top is None:
            stats["missing_columns_filled"] += 1
        elif terrain_y > source_top_y:
            stats["columns_raised"] += 1
        elif terrain_y < source_top_y:
            stats["columns_lowered"] += 1
        else:
            stats["columns_level"] += 1
        if (x, z) in building_ground_ys:
            surface_block = "minecraft:smooth_stone"
            stats["building_ground_columns"] += 1
        if source_top_y is not None and source_top_y > terrain_y:
            for y in range(terrain_y + 1, source_top_y + 1):
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, AIR):
                    stats["cleared_above_ground"] += 1
        if source_top is None or source_top_block != surface_block or source_top_y != terrain_y:
            edit_mask.add((x, terrain_y, z))
            if world.set_block(x, terrain_y, z, surface_block):
                stats["surface_retyped"] += 1
        if minimum_y < terrain_y:
            subsurface_block = subsurface_block_for(surface_block)
            topsoil_start = max(minimum_y, terrain_y - max(0, fill_depth))
            for y in range(minimum_y, terrain_y):
                fill_block = (
                    subsurface_block
                    if y >= topsoil_start
                    else "minecraft:stone"
                )
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, fill_block):
                    if y >= topsoil_start:
                        stats["subsurface_retyped"] += 1
                    else:
                        stats["deep_ground_retyped"] += 1
        source_top_surface[(x, z)] = (terrain_y, surface_block)
        if ground_surface_out is not None:
            ground_surface_out[(x, z)] = (terrain_y, surface_block)
        ground_ys.append(terrain_y)
        stats["columns"] += 1
    if ground_ys:
        stats["ground_y_min"] = min(ground_ys)
        stats["ground_y_max"] = max(ground_ys)
    stats["building_sample_exclusion_columns"] = len(protected_building_columns)
    return stats


def load_npz_building_overlay(
    npz_path: Path,
    transform: WorldTransform,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    source_world_path: Path,
    *,
    min_source_column_coverage: float,
    min_support_column_coverage: float,
    min_vertical_offset: float,
    max_vertical_offset: float,
    fill_air_support: bool,
    building_name_filter: str | None = None,
    procedural_ground_y: int | None = None,
) -> VoxelBuildingOverlay:
    manifest_path = npz_path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"NPZ manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    building_map = manifest.get("building_id_map") or {}

    with np.load(npz_path, allow_pickle=False) as payload:
        occupied_neu = payload["occupied_neu"].astype(np.int32, copy=False)
        building_ids = payload["building_ids"].astype(np.uint16, copy=False)
        building_names = [str(value) for value in payload["building_names"].tolist()]
        metric_origin = payload["metric_origin_neu_m"].astype(float, copy=False)
        meshsize = float(payload["meshsize_m"][0])

    if len(occupied_neu) != len(building_ids):
        raise ValueError("occupied_neu and building_ids length mismatch")
    if meshsize <= 0:
        raise ValueError(f"invalid meshsize: {meshsize}")

    ne_to_block = map_ne_cells_to_voxelearth_xz(
        occupied_neu[:, :2],
        metric_origin,
        meshsize,
        transform,
    )
    blocks: list[tuple[int, int, int, str, str]] = []
    block_states: dict[tuple[int, int, int], dict[str, str]] = {}
    support_blocks: dict[tuple[int, int, int], str] = {}
    clear_columns: dict[tuple[int, int], tuple[int, int]] = {}
    anchors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    source_reader = AnvilWorld(source_world_path)
    normalized_filter = building_name_filter.lower() if building_name_filter else None

    for raw_building_id in sorted(int(value) for value in np.unique(building_ids)):
        selector = building_ids == raw_building_id
        coords = occupied_neu[selector]
        if len(coords) == 0:
            continue
        name = building_names[raw_building_id - 1] if 0 < raw_building_id <= len(building_names) else str(raw_building_id)
        metadata = building_map.get(str(raw_building_id), {})
        if normalized_filter is not None:
            searchable = " ".join(
                str(value)
                for value in (
                    raw_building_id,
                    name,
                    metadata.get("name"),
                    metadata.get("IMPRNAME"),
                    metadata.get("STRUCTUREID"),
                    metadata.get("PARID"),
                    metadata.get("roofer_id"),
                )
                if value is not None
            ).lower()
            if normalized_filter not in searchable:
                continue
        description = str(metadata.get("DESCRIPTION") or "")
        qa = metadata.get("roofer_qa") or {}
        rf_h_ground = qa.get("rf_h_ground")
        if rf_h_ground is None:
            rf_h_ground = float(coords[:, 2].min())
        rf_h_ground = float(rf_h_ground)

        ne_columns = {tuple(int(value) for value in pair) for pair in coords[:, :2]}
        mapped_columns = {ne_to_block[(north, east)] for north, east in ne_columns}
        source_column_samples = [
            source_top_surface[column][0]
            for column in mapped_columns
            if column in source_top_surface
        ]
        source_column_coverage = len(source_column_samples) / max(1, len(mapped_columns))
        ring_samples = sample_exterior_ring_ground(
            ne_columns,
            metric_origin,
            meshsize,
            transform,
            source_top_surface,
        )
        if ring_samples:
            anchor_y = int(round(percentile(ring_samples, 0.25)))
        elif source_column_samples:
            anchor_y = int(round(percentile(source_column_samples, 0.25)))
        else:
            skipped.append(
                {
                    "building_id": raw_building_id,
                    "name": name,
                    "reason": "no_voxelearth_source_columns",
                    "columns": len(mapped_columns),
                    "ring_samples": 0,
                    "source_column_coverage": source_column_coverage,
                }
            )
            continue
        y_offset = anchor_y - rf_h_ground
        source_anchor_y = anchor_y
        source_y_offset = y_offset
        if source_column_coverage < min_source_column_coverage:
            skipped.append(
                {
                    "building_id": raw_building_id,
                    "name": name,
                    "reason": "low_voxelearth_source_column_coverage",
                    "columns": len(mapped_columns),
                    "source_columns": len(source_column_samples),
                    "source_column_coverage": source_column_coverage,
                    "ring_samples": len(ring_samples),
                    "vertical_offset": y_offset,
                }
            )
            continue
        if not (min_vertical_offset <= y_offset <= max_vertical_offset):
            skipped.append(
                {
                    "building_id": raw_building_id,
                    "name": name,
                    "reason": "vertical_offset_out_of_band",
                    "roofer_h_ground": rf_h_ground,
                    "voxelearth_ring_ground_y": anchor_y,
                    "vertical_offset": y_offset,
                    "ring_samples": len(ring_samples),
                    "source_column_coverage": source_column_coverage,
                }
            )
            continue

        raw_blocks: set[tuple[int, int, int]] = set()
        for north, east, up in coords:
            x, z = ne_to_block[(int(north), int(east))]
            y = int(round(float(up) + y_offset))
            raw_blocks.add((x, y, z))

        if not raw_blocks:
            continue
        min_y = min(y for _x, y, _z in raw_blocks)
        max_y = max(y for _x, y, _z in raw_blocks)
        materials, material_sample = material_set_from_source(
            source_reader,
            raw_blocks,
            name=name,
            min_y=min_y,
            max_y=max_y,
        )
        column_ranges: dict[tuple[int, int], tuple[int, int]] = {}
        for x, y, z in raw_blocks:
            column = (x, z)
            old_range = column_ranges.get(column)
            if old_range is None:
                column_ranges[column] = (y, y)
            else:
                column_ranges[column] = (min(old_range[0], y), max(old_range[1], y))

        support_hits = 0
        unsupported_columns: set[tuple[int, int]] = set()
        building_support_blocks: dict[tuple[int, int, int], str] = {}
        for column, (column_min_y, _column_max_y) in column_ranges.items():
            support_block = source_reader.get_block(column[0], column_min_y - 1, column[1])
            if support_block not in AIR_BLOCKS:
                support_hits += 1
            else:
                unsupported_columns.add(column)
        support_coverage = support_hits / max(1, len(column_ranges))
        if unsupported_columns and fill_air_support:
            for column in unsupported_columns:
                source_top = source_top_surface.get(column)
                surface_block = source_top[1] if source_top is not None else "minecraft:smooth_stone"
                support_y = column_ranges[column][0] - 1
                building_support_blocks[(column[0], support_y, column[1])] = (
                    subsurface_block_for(surface_block)
                )
        elif support_coverage < min_support_column_coverage:
            skipped.append(
                {
                    "building_id": raw_building_id,
                    "name": name,
                    "reason": "low_support_column_coverage",
                    "columns": len(column_ranges),
                    "support_columns": support_hits,
                    "support_column_coverage": support_coverage,
                    "ring_samples": len(ring_samples),
                    "source_column_coverage": source_column_coverage,
                    "vertical_offset": y_offset,
                }
            )
            continue
        trimmed_columns = 0
        trimmed_voxels = 0
        if unsupported_columns and not fill_air_support:
            before = len(raw_blocks)
            raw_blocks = {
                (x, y, z)
                for x, y, z in raw_blocks
                if (x, z) not in unsupported_columns
            }
            trimmed_columns = len(unsupported_columns)
            trimmed_voxels = before - len(raw_blocks)
            if not raw_blocks:
                skipped.append(
                    {
                        "building_id": raw_building_id,
                        "name": name,
                        "reason": "all_columns_trimmed_for_air_support",
                        "columns": len(column_ranges),
                        "support_columns": support_hits,
                        "support_column_coverage": support_coverage,
                    }
                )
                continue
            min_y = min(y for _x, y, _z in raw_blocks)
            max_y = max(y for _x, y, _z in raw_blocks)
            column_ranges = {}
            for x, y, z in raw_blocks:
                column = (x, z)
                old_range = column_ranges.get(column)
                if old_range is None:
                    column_ranges[column] = (y, y)
                else:
                    column_ranges[column] = (min(old_range[0], y), max(old_range[1], y))

        detected_window_voxels = detect_source_window_voxels(source_reader, raw_blocks)
        procedural = generate_procedural_building_blocks(
            raw_blocks,
            materials,
            name=name,
            detected_window_voxels=detected_window_voxels,
        )
        placement_shift_y = 0
        if procedural_ground_y is not None:
            placement_shift_y = int(procedural_ground_y) + 1 - min_y
        if placement_shift_y:
            raw_blocks = {
                (x, y + placement_shift_y, z)
                for x, y, z in raw_blocks
            }
            column_ranges = {
                column: (
                    column_min_y + placement_shift_y,
                    column_max_y + placement_shift_y,
                )
                for column, (column_min_y, column_max_y) in column_ranges.items()
            }
            procedural = shift_procedural_building(procedural, placement_shift_y)
            building_support_blocks = {
                (x, y + placement_shift_y, z): block_name
                for (x, y, z), block_name in building_support_blocks.items()
            }
        min_y += placement_shift_y
        max_y += placement_shift_y
        if procedural_ground_y is not None:
            anchor_y = int(procedural_ground_y)
            y_offset += placement_shift_y
        support_blocks.update(building_support_blocks)
        blocks.extend(procedural.blocks)
        block_states.update(procedural.block_states)
        placement_block_count = len(procedural.blocks)
        hollowed_interior_voxels = procedural.stats["hollowed_interior_voxels"]

        landmark_blocks: list[tuple[int, int, int, str, str]] = []
        if is_chapel_name(name):
            chapel_shell_blocks = {
                (x, y, z)
                for x, y, z, _block_name, _role in procedural.blocks
            }
            landmark_blocks = generate_chapel_landmark_blocks(chapel_shell_blocks, materials)
            blocks.extend(landmark_blocks)

        for column, (column_min_y, column_max_y) in column_ranges.items():
            old = clear_columns.get(column)
            if old is None:
                clear_columns[column] = (column_min_y, column_max_y + BUILDING_CLEAR_HEADROOM)
            else:
                clear_columns[column] = (
                    min(old[0], column_min_y),
                    max(old[1], column_max_y + BUILDING_CLEAR_HEADROOM),
                )
        for x, y, z, _block_name, _role in landmark_blocks:
            column = (x, z)
            if column not in column_ranges:
                continue
            old = clear_columns.get(column)
            if old is None:
                clear_columns[column] = (y, y + BUILDING_CLEAR_HEADROOM)
            else:
                clear_columns[column] = (
                    min(old[0], y),
                    max(old[1], y + BUILDING_CLEAR_HEADROOM),
                )

        anchors.append(
            {
                "building_id": raw_building_id,
                "name": name,
                "bbox": [
                    min(x for x, _y, _z in raw_blocks),
                    min_y,
                    min(z for _x, _y, z in raw_blocks),
                    max(x for x, _y, _z in raw_blocks),
                    max_y,
                    max(z for _x, _y, z in raw_blocks),
                ],
                "roofer_h_ground": rf_h_ground,
                "voxelearth_ring_ground_y": anchor_y,
                "vertical_offset": y_offset,
                "source_voxelearth_ring_ground_y": source_anchor_y,
                "source_vertical_offset": source_y_offset,
                "placement_shift_y": placement_shift_y,
                "procedural_ground_y": procedural_ground_y,
                "ring_samples": len(ring_samples),
                "source_column_coverage": source_column_coverage,
                "support_column_coverage": support_coverage,
                "trimmed_columns": trimmed_columns,
                "trimmed_voxels": trimmed_voxels,
                "support_fill_columns": len(unsupported_columns) if fill_air_support else 0,
                "voxels": len(raw_blocks),
                "placed_shell_voxels": placement_block_count,
                "hollowed_interior_voxels": hollowed_interior_voxels,
                "hollowed": True,
                "columns": len({(x, z) for x, _y, z in raw_blocks}),
                "landmark_feature_blocks": len(landmark_blocks),
                "window_generation": {
                    "mode": procedural.window_mode,
                    "source": (
                        "voxelearth-3d-tile-raster-exact-glass-cells"
                        if procedural.window_mode == "voxelearth-source-glass-detected"
                        else "deterministic-facade-rhythm"
                    ),
                    "source_evidence_voxels": procedural.stats[
                        "source_window_evidence_voxels"
                    ],
                    "assemblies": procedural.stats["window_assemblies"],
                    "panes": procedural.stats["window_panes"],
                    "sills": procedural.stats["window_sills"],
                    "lintels": procedural.stats["window_lintels"],
                    "pane_material": glass_pane_material(materials["window"]),
                    "stair_material": stair_material_for_trim(materials["trim"]),
                },
                "material_sample": material_sample,
            }
        )

    blocks_by_coordinate: dict[
        tuple[int, int, int], tuple[int, int, int, str, str]
    ] = {}
    for placement in blocks:
        blocks_by_coordinate[placement[:3]] = placement
    blocks = list(blocks_by_coordinate.values())
    stateful_roles = {"window_pane", "window_sill", "window_lintel"}
    block_states = {
        coordinate: properties
        for coordinate, properties in block_states.items()
        if coordinate in blocks_by_coordinate
        and blocks_by_coordinate[coordinate][4] in stateful_roles
    }

    return VoxelBuildingOverlay(
        blocks=blocks,
        support_blocks=support_blocks,
        clear_columns=clear_columns,
        edit_columns=len(clear_columns),
        source_path=npz_path,
        manifest_path=manifest_path,
        building_count=len(anchors),
        building_names=[entry["name"] for entry in anchors],
        anchors=anchors,
        skipped=skipped,
        block_states=block_states,
    )


def load_npz_building_footprint_columns(
    npz_path: Path,
    transform: WorldTransform,
) -> set[tuple[int, int]]:
    with np.load(npz_path, allow_pickle=False) as payload:
        occupied_neu = payload["occupied_neu"].astype(np.int32, copy=False)
        metric_origin = payload["metric_origin_neu_m"].astype(float, copy=False)
        meshsize = float(payload["meshsize_m"][0])
    if len(occupied_neu) == 0:
        return set()
    if meshsize <= 0:
        raise ValueError(f"invalid meshsize: {meshsize}")
    ne_columns = {tuple(int(value) for value in pair) for pair in occupied_neu[:, :2]}
    ne_to_block = map_ne_cells_to_voxelearth_xz(
        occupied_neu[:, :2],
        metric_origin,
        meshsize,
        transform,
    )
    return {ne_to_block[(north, east)] for north, east in ne_columns}


def building_footprint_columns_from_models(buildings: list[BuildingModel]) -> set[tuple[int, int]]:
    columns: set[tuple[int, int]] = set()
    for building in buildings:
        footprint = building.footprint_union
        prepared = prep(footprint)
        minx, minz, maxx, maxz = footprint.bounds
        for x in range(math.floor(minx), math.ceil(maxx) + 1):
            for z in range(math.floor(minz), math.ceil(maxz) + 1):
                if prepared.contains(Point(x + 0.5, z + 0.5)):
                    columns.add((x, z))
    return columns


def map_ne_cells_to_voxelearth_xz(
    ne_cells: np.ndarray,
    metric_origin: np.ndarray,
    meshsize: float,
    transform: WorldTransform,
) -> dict[tuple[int, int], tuple[int, int]]:
    unique = np.unique(ne_cells, axis=0)
    if unique.size == 0:
        return {}
    northing = metric_origin[0] + (unique[:, 0].astype(float) + 0.5) * meshsize
    easting = metric_origin[1] + (unique[:, 1].astype(float) + 0.5) * meshsize
    transformer = Transformer.from_crs("EPSG:6347", "EPSG:4326", always_xy=True)
    longitudes, latitudes = transformer.transform(easting, northing)
    result: dict[tuple[int, int], tuple[int, int]] = {}
    for index, (north, east) in enumerate(unique):
        x_float, z_float = transform.lonlat_to_block(float(longitudes[index]), float(latitudes[index]))
        result[(int(north), int(east))] = (int(round(x_float)), int(round(z_float)))
    return result


def sample_exterior_ring_ground(
    ne_columns: set[tuple[int, int]],
    metric_origin: np.ndarray,
    meshsize: float,
    transform: WorldTransform,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
) -> list[int]:
    ring_ne: set[tuple[int, int]] = set()
    for north, east in ne_columns:
        for dn in (-2, -1, 0, 1, 2):
            for de in (-2, -1, 0, 1, 2):
                if dn == 0 and de == 0:
                    continue
                candidate = (north + dn, east + de)
                if candidate not in ne_columns:
                    ring_ne.add(candidate)

    if not ring_ne:
        return []
    ring_to_block = map_ne_cells_to_voxelearth_xz(
        np.array(sorted(ring_ne), dtype=np.int32),
        metric_origin,
        meshsize,
        transform,
    )
    samples: list[int] = []
    for north, east in ring_ne:
        x, z = ring_to_block[(north, east)]
        value = sample_top_surface_near(source_top_surface, x, z, radius=2)
        if value is not None:
            samples.append(value)
    return samples


def sample_top_surface_near(
    top_surface: dict[tuple[int, int], tuple[int, str]],
    x: int,
    z: int,
    *,
    radius: int,
) -> int | None:
    values: list[int] = []
    for dx in range(-radius, radius + 1):
        for dz in range(-radius, radius + 1):
            entry = top_surface.get((x + dx, z + dz))
            if entry is not None:
                values.append(entry[0])
    if not values:
        return None
    return int(round(percentile(values, 0.25)))


def osm_points_to_block(
    coords: Iterable[dict[str, Any]],
    transform: WorldTransform,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for coord in coords:
        if "lon" not in coord or "lat" not in coord:
            continue
        x, z = transform.lonlat_to_block(float(coord["lon"]), float(coord["lat"]))
        points.append((x, z))
    return points


def is_osm_area(tags: dict[str, Any], points: list[tuple[float, float]]) -> bool:
    return (
        len(points) >= 4
        and points[0] == points[-1]
        and (
            tags.get("area") == "yes"
            or "amenity" in tags
            or "leisure" in tags
            or "landuse" in tags
            or tags.get("natural") in {"water", "wood", "scrub"}
            or "water" in tags
        )
    )


def osm_relation_geometry_to_block(
    element: dict[str, Any],
    transform: WorldTransform,
) -> BaseGeometry | None:
    outers: list[list[tuple[float, float]]] = []
    inners: list[list[tuple[float, float]]] = []
    lines: list[BaseGeometry] = []
    for member in element.get("members", []) or []:
        points = osm_points_to_block(member.get("geometry") or [], transform)
        if len(points) < 2:
            continue
        closed = len(points) >= 4 and points[0] == points[-1]
        if closed and member.get("role") == "inner":
            inners.append(points)
        elif closed:
            outers.append(points)
        else:
            try:
                lines.append(LineString(points))
            except Exception:
                continue

    geometries: list[BaseGeometry] = []
    inner_polygons: list[Polygon] = []
    for ring in inners:
        try:
            polygon = Polygon(ring)
            if polygon.is_valid and not polygon.is_empty:
                inner_polygons.append(polygon)
        except Exception:
            continue
    for ring in outers:
        try:
            outer = Polygon(ring)
            if not outer.is_valid:
                outer = outer.buffer(0)
            if outer.is_empty:
                continue
            holes = [
                list(inner.exterior.coords)
                for inner in inner_polygons
                if outer.contains(inner.representative_point())
            ]
            polygon = Polygon(list(outer.exterior.coords), holes)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if not polygon.is_empty:
                geometries.append(polygon)
        except Exception:
            continue
    geometries.extend(lines)
    if not geometries:
        return None
    geom = unary_union(geometries)
    return None if geom.is_empty else geom


def osm_geometry_to_block(element: dict[str, Any], transform: WorldTransform) -> BaseGeometry | None:
    if element.get("type") == "relation":
        return osm_relation_geometry_to_block(element, transform)
    points = osm_points_to_block(element.get("geometry") or [], transform)
    if len(points) < 2:
        return None
    tags = element.get("tags", {}) or {}
    try:
        geom: BaseGeometry
        if is_osm_area(tags, points):
            geom = Polygon(points)
        else:
            geom = LineString(points)
        if not geom.is_valid:
            geom = geom.buffer(0)
        return None if geom.is_empty else geom
    except Exception:
        return None


def buffered_site_line(geometry: BaseGeometry, width_blocks: float) -> BaseGeometry:
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    return geometry.buffer(max(width_blocks, 0.5) / 2.0, cap_style=2, join_style=2)


def site_feature_group(tags: dict[str, Any]) -> str | None:
    highway = tags.get("highway")
    leisure = tags.get("leisure")
    amenity = tags.get("amenity")
    natural = tags.get("natural")
    sport = str(tags.get("sport", "")).lower()
    if highway:
        if highway in {"footway", "path", "steps", "pedestrian", "cycleway", "bridleway"}:
            return "path"
        return "road"
    if amenity == "parking" or tags.get("parking"):
        return "parking"
    if natural == "water" or tags.get("water") or tags.get("waterway"):
        return "water"
    if leisure == "track":
        return "track"
    if leisure == "pitch":
        if "tennis" in sport or "pickleball" in sport:
            return "tennis"
        if "baseball" in sport or "softball" in sport:
            return "baseball"
        if "basketball" in sport:
            return "court"
        return "field"
    return None


def site_feature_width_blocks(
    group: str,
    transform: WorldTransform,
    tags: dict[str, Any] | None = None,
) -> float:
    """Return the complete rendered width of an OSM linear feature.

    The campus surface resource treats its metre values as buffer radii.  This
    function returns a complete width because ``buffered_site_line`` divides it
    by two.  Keeping those semantics aligned prevents a dark road centre stripe
    surrounded by the old light VoxelEarth road material.
    """

    tags = tags or {}
    if group == "road":
        highway = str(tags.get("highway") or "")
        if highway in {"service", "track", "driveway"}:
            buffer_radius_m = 4.0
        else:
            buffer_radius_m = 6.0
    else:
        buffer_radius_m = {
            "path": 2.0,
            "parking": 5.0,
            "water": 4.0,
            "track": 5.0,
        }.get(group, 0.5)
    return buffer_radius_m * 2.0 * transform.blocks_per_metre


def load_site_feature_geometries(
    osm_path: Path,
    transform: WorldTransform,
) -> tuple[dict[str, list[BaseGeometry]], dict[str, int]]:
    payload = json.loads(osm_path.read_text(encoding="utf-8"))
    groups: dict[str, list[BaseGeometry]] = {name: [] for name in SITE_FEATURE_BLOCKS}
    counts = {name: 0 for name in SITE_FEATURE_BLOCKS}
    for element in payload.get("elements", []):
        if element.get("type") not in {"way", "relation"}:
            continue
        tags = element.get("tags", {}) or {}
        group = site_feature_group(tags)
        if group is None:
            continue
        geom = osm_geometry_to_block(element, transform)
        if geom is None or geom.is_empty:
            continue
        groups[group].append(
            buffered_site_line(
                geom,
                site_feature_width_blocks(group, transform, tags),
            )
        )
        counts[group] += 1
    return groups, counts


def site_feature_material(group: str, geometry: BaseGeometry, x: int, z: int) -> str:
    if group in {"field", "tennis", "court", "baseball", "track"}:
        point = Point(x + 0.5, z + 0.5)
        if geometry.boundary.distance(point) <= 0.8:
            return "minecraft:white_concrete"
        minx, minz, maxx, maxz = geometry.bounds
        width = max(1.0, maxx - minx)
        height = max(1.0, maxz - minz)
        center_x = minx + width * 0.5
        center_z = minz + height * 0.5
        if group in {"field", "tennis", "court"}:
            if abs((x + 0.5) - center_x) <= 0.8 or abs((z + 0.5) - center_z) <= 0.8:
                return "minecraft:white_concrete"
        if group == "tennis":
            service_a = minz + height * 0.25
            service_b = minz + height * 0.75
            if abs((z + 0.5) - service_a) <= 0.8 or abs((z + 0.5) - service_b) <= 0.8:
                return "minecraft:white_concrete"
    return SITE_FEATURE_BLOCKS[group]


def target_top_y_at(
    world: AnvilWorld,
    x: int,
    z: int,
    fallback_y: int,
    *,
    minimum_y: int,
    search_above: int = 32,
) -> int:
    get_block = getattr(world, "get_block", None)
    if get_block is None:
        return fallback_y
    for y in range(fallback_y + search_above, minimum_y - 1, -1):
        if get_block(x, y, z) not in AIR_BLOCKS:
            return y
    return fallback_y


def is_sandlike_top_block(block: str) -> bool:
    return block in SANDLIKE_TOP_BLOCKS or block.removeprefix("minecraft:").startswith("suspicious_sand")


def apply_sandlike_top_cleanup(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    building_footprint_columns: set[tuple[int, int]],
    *,
    minimum_y: int,
    replacement_block: str = SANDLIKE_REPLACEMENT_BLOCK,
    edit_mask: set[tuple[int, int, int]],
) -> dict[str, Any]:
    stats: Counter[str] = Counter()
    source_blocks: Counter[str] = Counter()
    top_y_cache: dict[tuple[int, int], int] = {}
    for (x, z), (source_top_y, source_top_block) in source_top_surface.items():
        if not is_sandlike_top_block(source_top_block):
            continue
        stats["sandlike_source_columns"] += 1
        source_blocks[source_top_block] += 1
        if (x, z) in building_footprint_columns:
            stats["building_columns_exempted"] += 1
            continue
        column = (x, z)
        y = top_y_cache.get(column)
        if y is None:
            y = target_top_y_at(world, x, z, source_top_y, minimum_y=minimum_y)
            top_y_cache[column] = y
        edit_mask.add((x, y, z))
        stats["columns"] += 1
        if world.set_block(x, y, z, replacement_block):
            stats["changed"] += 1
    return {
        "replacement": replacement_block,
        **dict(stats),
        "source_blocks": dict(source_blocks.most_common()),
        "exempt_building_columns": len(building_footprint_columns),
    }


def apply_site_surface_overlay(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    osm_path: Path,
    transform: WorldTransform,
    edit_mask: set[tuple[int, int, int]],
    *,
    minimum_y: int = -64,
) -> dict[str, Any]:
    if not osm_path.is_file():
        raise FileNotFoundError(f"OSM site feature file not found: {osm_path}")
    groups, feature_counts = load_site_feature_geometries(osm_path, transform)
    xs = [x for x, _z in source_top_surface]
    zs = [z for _x, z in source_top_surface]
    surface_bounds = box(min(xs), min(zs), max(xs) + 1, max(zs) + 1)
    cells_by_group: Counter[str] = Counter()
    changed_by_group: Counter[str] = Counter()
    materials: set[str] = set()
    top_y_cache: dict[tuple[int, int], int] = {}

    for group in SITE_FEATURE_PRIORITY:
        for geometry in groups.get(group, []):
            clipped = geometry.intersection(surface_bounds)
            if clipped.is_empty:
                continue
            prepared = prep(clipped)
            minx, minz, maxx, maxz = clipped.bounds
            for x in range(math.floor(minx), math.ceil(maxx) + 1):
                for z in range(math.floor(minz), math.ceil(maxz) + 1):
                    point = Point(x + 0.5, z + 0.5)
                    if not prepared.contains(point):
                        continue
                    top = source_top_surface.get((x, z))
                    if top is None:
                        continue
                    block = site_feature_material(group, clipped, x, z)
                    materials.add(block)
                    column = (x, z)
                    y = top_y_cache.get(column)
                    if y is None:
                        y = target_top_y_at(world, x, z, top[0], minimum_y=minimum_y)
                        top_y_cache[column] = y
                    edit_mask.add((x, y, z))
                    cells_by_group[group] += 1
                    if world.set_block(x, y, z, block):
                        changed_by_group[group] += 1

    return {
        "source": str(osm_path),
        "features": {key: value for key, value in feature_counts.items() if value},
        "cells": dict(cells_by_group),
        "changed": dict(changed_by_group),
        "materials": sorted(materials),
    }


def campus_geojson_geometry_to_block(feature: dict[str, Any], transform: WorldTransform) -> BaseGeometry | None:
    if "geometry" not in feature or feature["geometry"] is None:
        return None

    def to_world(
        longitudes: Iterable[float],
        latitudes: Iterable[float],
        altitudes: Iterable[float] | None = None,
    ) -> tuple[list[float], list[float]]:
        del altitudes
        points = [
            transform.lonlat_to_block(float(longitude), float(latitude))
            for longitude, latitude in zip(longitudes, latitudes)
        ]
        return [point[0] for point in points], [point[1] for point in points]

    try:
        geometry = geometry_transform(to_world, shape(feature["geometry"]))
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        return None if geometry.is_empty else geometry
    except Exception:
        return None


def geometry_integer_cells(geometry: BaseGeometry) -> Iterator[tuple[int, int]]:
    prepared = prep(geometry)
    min_x, min_z, max_x, max_z = geometry.bounds
    for x in range(math.floor(min_x), math.ceil(max_x) + 1):
        for z in range(math.floor(min_z), math.ceil(max_z) + 1):
            if prepared.covers(Point(x + 0.5, z + 0.5)):
                yield x, z


def load_campus_boundary_geometry(
    boundary_path: Path,
    transform: WorldTransform,
) -> BaseGeometry:
    if not boundary_path.is_file():
        raise FileNotFoundError(f"campus boundary GeoJSON not found: {boundary_path}")
    payload = json.loads(boundary_path.read_text(encoding="utf-8"))
    geometries = [
        geometry
        for feature in payload.get("features", [])
        if (geometry := campus_geojson_geometry_to_block(feature, transform)) is not None
    ]
    if not geometries:
        raise ValueError(f"campus boundary contains no usable geometry: {boundary_path}")
    boundary = unary_union(geometries)
    if not boundary.is_valid:
        boundary = boundary.buffer(0)
    if boundary.is_empty:
        raise ValueError(f"campus boundary resolved to an empty geometry: {boundary_path}")
    return boundary


def load_campus_building_geometries(
    buildings_path: Path,
    transform: WorldTransform,
) -> BaseGeometry:
    if not buildings_path.is_file():
        raise FileNotFoundError(f"campus building GeoJSON not found: {buildings_path}")
    payload = json.loads(buildings_path.read_text(encoding="utf-8"))
    geometries = [
        geometry
        for feature in payload.get("features", [])
        if (geometry := campus_geojson_geometry_to_block(feature, transform)) is not None
    ]
    if not geometries:
        raise ValueError(f"campus buildings contain no usable geometry: {buildings_path}")
    union = unary_union(geometries)
    if not union.is_valid:
        union = union.buffer(0)
    if union.is_empty:
        raise ValueError(f"campus buildings resolved to an empty geometry: {buildings_path}")
    return union


def apply_building_seam_fill(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    overlay: VoxelBuildingOverlay,
    campus_boundary: BaseGeometry,
    *,
    all_building_columns: set[tuple[int, int]] | None = None,
    radius: int,
    minimum_y: int,
    edit_mask: set[tuple[int, int, int]],
) -> dict[str, Any]:
    """Fill absent VoxelEarth columns immediately outside campus buildings.

    The Roofer overlay's floor elevation is itself anchored to surrounding
    VoxelEarth terrain.  Reusing ``min_y - 1`` therefore closes source-tile
    holes around accepted buildings.  For footprints Roofer rejected, nearby
    valid VoxelEarth ground supplies the elevation.  Neither path introduces a
    second terrain model or alters existing source columns.  Later road/court
    overlays can still retype the new grass surface at the same elevation.
    """

    accepted_building_columns = set(overlay.clear_columns)
    building_columns = set(all_building_columns or accepted_building_columns)
    building_columns.update(accepted_building_columns)
    if radius <= 0 or not building_columns:
        return {
            "radius": max(0, radius),
            "ring_columns": 0,
            "existing_source_columns": 0,
            "candidate_columns": 0,
            "boundary_rejected_columns": 0,
            "anchored_candidate_columns": 0,
            "anchored_filled_columns": 0,
            "nearby_ground_candidate_columns": 0,
            "nearby_ground_sampled_columns": 0,
            "nearby_ground_filled_columns": 0,
            "filled_columns": 0,
            "filled_blocks": 0,
            "failed_columns": 0,
            "remaining_missing_columns": 0,
            "ground_y_min": None,
            "ground_y_max": None,
        }

    ring_columns: set[tuple[int, int]] = set()
    for building_x, building_z in building_columns:
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                distance = max(abs(dx), abs(dz))
                if distance == 0 or distance > radius:
                    continue
                column = (building_x + dx, building_z + dz)
                if column not in building_columns:
                    ring_columns.add(column)

    # Candidate -> (Chebyshev distance to the closest accepted building
    # column, VoxelEarth-anchored ground Y).  Sorting keeps ties stable.
    anchored_nearest: dict[tuple[int, int], tuple[int, int]] = {}
    for (building_x, building_z), (floor_y, _max_y) in sorted(overlay.clear_columns.items()):
        ground_y = floor_y - 1
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                distance = max(abs(dx), abs(dz))
                if distance == 0 or distance > radius:
                    continue
                column = (building_x + dx, building_z + dz)
                if column in building_columns:
                    continue
                candidate = (distance, ground_y)
                previous = anchored_nearest.get(column)
                if previous is None or candidate < previous:
                    anchored_nearest[column] = candidate

    prepared_boundary = prep(campus_boundary)
    missing_columns = {column for column in ring_columns if column not in source_top_surface}
    targets_in_boundary = {
        column
        for column in missing_columns
        if prepared_boundary.covers(Point(column[0] + 0.5, column[1] + 0.5))
    }

    filled_columns: set[tuple[int, int]] = set()
    filled_blocks = 0
    ground_ys: list[int] = []

    def fill_targets(targets: dict[tuple[int, int], int]) -> set[tuple[int, int]]:
        nonlocal filled_blocks
        completed: set[tuple[int, int]] = set()
        for (x, z), ground_y in sorted(targets.items()):
            if ground_y < minimum_y:
                continue
            changed_in_column = 0
            for y in range(minimum_y, ground_y):
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, "minecraft:dirt"):
                    changed_in_column += 1
            edit_mask.add((x, ground_y, z))
            if world.set_block(x, ground_y, z, "minecraft:grass_block"):
                changed_in_column += 1
                source_top_surface[(x, z)] = (ground_y, "minecraft:grass_block")
                completed.add((x, z))
                ground_ys.append(ground_y)
            filled_blocks += changed_in_column
        filled_columns.update(completed)
        return completed

    anchored_targets = {
        column: anchored_nearest[column][1]
        for column in targets_in_boundary
        if column in anchored_nearest
    }
    anchored_filled = fill_targets(anchored_targets)

    nearby_candidates = {
        column
        for column in targets_in_boundary
        if column not in source_top_surface
    }
    nearby_targets: dict[tuple[int, int], int] = {}
    sample_radius = max(4, radius + 2)
    for x, z in sorted(nearby_candidates):
        values = [
            entry[0]
            for dx in range(-sample_radius, sample_radius + 1)
            for dz in range(-sample_radius, sample_radius + 1)
            if (entry := source_top_surface.get((x + dx, z + dz))) is not None
            and (x + dx, z + dz) not in building_columns
        ]
        if values:
            nearby_targets[(x, z)] = int(round(percentile(values, 0.25)))
    nearby_filled = fill_targets(nearby_targets)

    remaining_missing = sum(column not in source_top_surface for column in targets_in_boundary)

    return {
        "radius": radius,
        "ring_columns": len(ring_columns),
        "existing_source_columns": len(ring_columns) - len(missing_columns),
        "candidate_columns": len(targets_in_boundary),
        "boundary_rejected_columns": len(missing_columns) - len(targets_in_boundary),
        "anchored_candidate_columns": len(anchored_targets),
        "anchored_filled_columns": len(anchored_filled),
        "nearby_ground_candidate_columns": len(nearby_candidates),
        "nearby_ground_sampled_columns": len(nearby_targets),
        "nearby_ground_filled_columns": len(nearby_filled),
        "filled_columns": len(filled_columns),
        "filled_blocks": filled_blocks,
        "failed_columns": remaining_missing,
        "remaining_missing_columns": remaining_missing,
        "ground_y_min": min(ground_ys, default=None),
        "ground_y_max": max(ground_ys, default=None),
    }


def fill_missing_ground_columns(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    columns: Iterable[tuple[int, int]],
    *,
    minimum_y: int,
    edit_mask: set[tuple[int, int, int]],
    sample_radius: int,
    excluded_sample_columns: set[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    sampling_surface = dict(source_top_surface)
    excluded_sample_columns = excluded_sample_columns or set()
    filled_columns = 0
    filled_blocks = 0
    unsampled_columns = 0
    failed_columns = 0
    ground_ys: list[int] = []
    samples: list[list[int]] = []
    targets: dict[tuple[int, int], int] = {}

    for x, z in sorted(set(columns)):
        if (x, z) in source_top_surface:
            continue
        values = [
            entry[0]
            for dx in range(-sample_radius, sample_radius + 1)
            for dz in range(-sample_radius, sample_radius + 1)
            if (x + dx, z + dz) not in excluded_sample_columns
            and (entry := sampling_surface.get((x + dx, z + dz))) is not None
        ]
        if not values:
            unsampled_columns += 1
            if len(samples) < 20:
                samples.append([x, z])
            continue
        targets[(x, z)] = int(round(percentile(values, 0.25)))

    for (x, z), ground_y in sorted(targets.items()):
        changed_in_column = 0
        for y in range(minimum_y, ground_y):
            edit_mask.add((x, y, z))
            if world.set_block(x, y, z, "minecraft:dirt"):
                changed_in_column += 1
        edit_mask.add((x, ground_y, z))
        if world.set_block(x, ground_y, z, "minecraft:grass_block"):
            changed_in_column += 1
            source_top_surface[(x, z)] = (ground_y, "minecraft:grass_block")
            filled_columns += 1
            ground_ys.append(ground_y)
        else:
            failed_columns += 1
        filled_blocks += changed_in_column

    return {
        "filled_columns": filled_columns,
        "filled_blocks": filled_blocks,
        "unsampled_columns": unsampled_columns,
        "unsampled_samples": samples,
        "failed_columns": failed_columns,
        "ground_y_min": min(ground_ys, default=None),
        "ground_y_max": max(ground_ys, default=None),
    }


def apply_official_building_seam_fill(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    campus_buildings: BaseGeometry,
    campus_boundary: BaseGeometry,
    *,
    radius: int,
    minimum_y: int,
    edit_mask: set[tuple[int, int, int]],
    sample_radius: int = 8,
) -> dict[str, Any]:
    if radius <= 0:
        return {
            "radius": max(0, radius),
            "ring_columns": 0,
            "missing_columns": 0,
            "filled_columns": 0,
            "filled_blocks": 0,
            "unsampled_columns": 0,
            "remaining_missing_columns": 0,
        }

    seam_geometry = (
        campus_buildings.buffer(float(radius), join_style=2)
        .difference(campus_buildings)
        .intersection(campus_boundary)
    )
    if seam_geometry.is_empty:
        return {
            "radius": radius,
            "ring_columns": 0,
            "missing_columns": 0,
            "filled_columns": 0,
            "filled_blocks": 0,
            "unsampled_columns": 0,
            "remaining_missing_columns": 0,
        }

    ring_columns = set(geometry_integer_cells(seam_geometry))
    building_columns = set(geometry_integer_cells(campus_buildings))
    missing_columns = {column for column in ring_columns if column not in source_top_surface}
    fill_stats = fill_missing_ground_columns(
        world,
        source_top_surface,
        missing_columns,
        minimum_y=minimum_y,
        edit_mask=edit_mask,
        sample_radius=sample_radius,
        excluded_sample_columns=building_columns,
    )
    remaining_missing = sum(column not in source_top_surface for column in missing_columns)
    return {
        "radius": radius,
        "sample_radius": sample_radius,
        "ring_columns": len(ring_columns),
        "missing_columns": len(missing_columns),
        **fill_stats,
        "remaining_missing_columns": remaining_missing,
    }


def is_named_road_surface(properties: dict[str, Any]) -> bool:
    if properties.get("kind") != "hard":
        return False
    name = str(properties.get("name") or "").lower()
    return any(token in name for token in ROAD_NAME_TOKENS)


def load_named_road_surface_geometries(
    surfaces_path: Path,
    transform: WorldTransform,
) -> tuple[list[BaseGeometry], int]:
    payload = json.loads(surfaces_path.read_text(encoding="utf-8"))
    geometries: list[BaseGeometry] = []
    matched_features = 0
    for feature in payload.get("features", []):
        properties = dict(feature.get("properties") or {})
        if not is_named_road_surface(properties):
            continue
        matched_features += 1
        geometry = campus_geojson_geometry_to_block(feature, transform)
        if geometry is not None:
            geometries.append(geometry)
    return geometries, matched_features


def apply_named_road_surface_overlay(
    world: AnvilWorld,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    surfaces_path: Path,
    transform: WorldTransform,
    edit_mask: set[tuple[int, int, int]],
    *,
    minimum_y: int = -64,
    block_name: str = SITE_FEATURE_BLOCKS["road"],
) -> dict[str, Any]:
    if not surfaces_path.is_file():
        raise FileNotFoundError(f"campus surface GeoJSON not found: {surfaces_path}")
    geometries, matched_features = load_named_road_surface_geometries(surfaces_path, transform)
    if not geometries:
        return {
            "source": str(surfaces_path),
            "features": matched_features,
            "cells": 0,
            "changed": 0,
            "materials": [],
        }
    xs = [x for x, _z in source_top_surface]
    zs = [z for _x, z in source_top_surface]
    surface_bounds = box(min(xs), min(zs), max(xs) + 1, max(zs) + 1)
    top_y_cache: dict[tuple[int, int], int] = {}
    cells = 0
    changed = 0
    for geometry in geometries:
        clipped = geometry.intersection(surface_bounds)
        if clipped.is_empty:
            continue
        minx, minz, maxx, maxz = clipped.bounds
        for x in range(math.floor(minx), math.ceil(maxx) + 1):
            for z in range(math.floor(minz), math.ceil(maxz) + 1):
                if not clipped.covers(Point(x + 0.5, z + 0.5)):
                    continue
                top = source_top_surface.get((x, z))
                if top is None:
                    continue
                y = top_y_cache.get((x, z))
                if y is None:
                    y = target_top_y_at(world, x, z, top[0], minimum_y=minimum_y)
                    top_y_cache[(x, z)] = y
                edit_mask.add((x, y, z))
                cells += 1
                if world.set_block(x, y, z, block_name):
                    changed += 1
    return {
        "source": str(surfaces_path),
        "features": matched_features,
        "cells": cells,
        "changed": changed,
        "materials": [block_name],
    }


def overlay_block_role(raw_blocks: set[tuple[int, int, int]], x: int, y: int, z: int) -> str:
    if (x, y + 1, z) not in raw_blocks:
        return "roof"
    exposed_x = (x + 1, y, z) not in raw_blocks or (x - 1, y, z) not in raw_blocks
    exposed_z = (x, y, z + 1) not in raw_blocks or (x, y, z - 1) not in raw_blocks
    if exposed_x and exposed_z:
        return "wall_corner"
    if exposed_x:
        return "wall_x"
    if exposed_z:
        return "wall_z"
    return "fill"


def hollow_building_blocks(
    raw_blocks: set[tuple[int, int, int]],
) -> tuple[set[tuple[int, int, int]], int]:
    """Reduce a solid Roofer occupancy volume to floor, walls, and roof.

    Roofer's voxel export describes occupied building volume rather than a
    navigable Minecraft shell.  The lowest voxel in each occupied column is
    retained as a one-block floor; laterally exposed voxels form walls and
    voxels exposed above form the roof.  Fully enclosed voxels above the floor
    are deliberately omitted so every generated building has an empty interior.
    """

    if not raw_blocks:
        return set(), 0
    column_mins: dict[tuple[int, int], int] = {}
    for x, y, z in raw_blocks:
        column = (x, z)
        column_mins[column] = min(y, column_mins.get(column, y))

    shell: set[tuple[int, int, int]] = set()
    for x, y, z in raw_blocks:
        is_floor = y == column_mins[(x, z)]
        is_roof = (x, y + 1, z) not in raw_blocks
        is_wall = any(
            neighbor not in raw_blocks
            for neighbor in (
                (x + 1, y, z),
                (x - 1, y, z),
                (x, y, z + 1),
                (x, y, z - 1),
            )
        )
        if is_floor or is_roof or is_wall:
            shell.add((x, y, z))
    return shell, len(raw_blocks) - len(shell)


def hollow_chapel_blocks(
    raw_blocks: set[tuple[int, int, int]],
) -> tuple[set[tuple[int, int, int]], int]:
    """Backward-compatible name for the campus-wide shell extractor."""

    return hollow_building_blocks(raw_blocks)


def building_shell_block_role(
    raw_blocks: set[tuple[int, int, int]],
    column_ranges: dict[tuple[int, int], tuple[int, int]],
    x: int,
    y: int,
    z: int,
) -> str:
    column_min_y, _column_max_y = column_ranges[(x, z)]
    if y == column_min_y:
        return "fill"
    return overlay_block_role(raw_blocks, x, y, z)


def chapel_shell_block_role(
    raw_blocks: set[tuple[int, int, int]],
    column_ranges: dict[tuple[int, int], tuple[int, int]],
    x: int,
    y: int,
    z: int,
) -> str:
    """Backward-compatible name for the generic shell role classifier."""

    return building_shell_block_role(raw_blocks, column_ranges, x, y, z)


def detect_source_window_voxels(
    source_reader: AnvilWorld,
    raw_blocks: set[tuple[int, int, int]],
) -> set[tuple[int, int, int]]:
    """Return exact facade glass cells from the Google/VoxelEarth source world.

    Neighborhood samples remain useful for choosing a building-wide glass
    colour, but they are too imprecise to locate an opening.  This mask only
    accepts an exact glass cell on a non-corner facade voxel.
    """

    detected: set[tuple[int, int, int]] = set()
    for x, y, z in raw_blocks:
        if overlay_block_role(raw_blocks, x, y, z) not in {"wall_x", "wall_z"}:
            continue
        if "glass" in source_reader.get_block(x, y, z):
            detected.add((x, y, z))
    return detected


FACADE_NEIGHBORS: tuple[tuple[int, int, str], ...] = (
    (-1, 0, "west"),
    (1, 0, "east"),
    (0, -1, "north"),
    (0, 1, "south"),
)
OPPOSITE_FACING = {
    "west": "east",
    "east": "west",
    "north": "south",
    "south": "north",
}


def facade_exterior_normal(
    raw_blocks: set[tuple[int, int, int]],
    coordinate: tuple[int, int, int],
    role: str,
) -> str | None:
    x, y, z = coordinate
    allowed = {"west", "east"} if role == "wall_x" else {"north", "south"}
    exposed = [
        facing
        for dx, dz, facing in FACADE_NEIGHBORS
        if facing in allowed and (x + dx, y, z + dz) not in raw_blocks
    ]
    return exposed[0] if len(exposed) == 1 else None


def glass_pane_material(block_name: str) -> str:
    if block_name.endswith("_glass_pane") or block_name == "minecraft:glass_pane":
        return block_name
    if block_name == "minecraft:glass":
        return "minecraft:glass_pane"
    if block_name.endswith("_stained_glass"):
        return f"{block_name}_pane"
    return "minecraft:black_stained_glass_pane"


def stair_material_for_trim(block_name: str) -> str:
    direct = {
        "minecraft:bricks": "minecraft:brick_stairs",
        "minecraft:stone": "minecraft:stone_stairs",
        "minecraft:stone_bricks": "minecraft:stone_brick_stairs",
        "minecraft:mossy_stone_bricks": "minecraft:mossy_stone_brick_stairs",
        "minecraft:cobblestone": "minecraft:cobblestone_stairs",
        "minecraft:mossy_cobblestone": "minecraft:mossy_cobblestone_stairs",
        "minecraft:sandstone": "minecraft:sandstone_stairs",
        "minecraft:smooth_sandstone": "minecraft:smooth_sandstone_stairs",
        "minecraft:red_sandstone": "minecraft:red_sandstone_stairs",
        "minecraft:smooth_red_sandstone": "minecraft:smooth_red_sandstone_stairs",
        "minecraft:quartz_block": "minecraft:quartz_stairs",
        "minecraft:smooth_quartz": "minecraft:smooth_quartz_stairs",
        "minecraft:deepslate_bricks": "minecraft:deepslate_brick_stairs",
        "minecraft:deepslate_tiles": "minecraft:deepslate_tile_stairs",
        "minecraft:polished_deepslate": "minecraft:polished_deepslate_stairs",
        "minecraft:polished_blackstone_bricks": "minecraft:polished_blackstone_brick_stairs",
    }
    if block_name in direct:
        return direct[block_name]
    if block_name.endswith("_planks"):
        return block_name.removesuffix("_planks") + "_stairs"
    if block_name in {"minecraft:white_concrete", "minecraft:white_terracotta"}:
        return "minecraft:quartz_stairs"
    if block_name in {"minecraft:red_concrete", "minecraft:red_terracotta"}:
        return "minecraft:brick_stairs"
    return "minecraft:stone_brick_stairs"


def pane_properties_for_wall(role: str) -> dict[str, str]:
    along_z = role == "wall_x"
    return {
        "east": "false" if along_z else "true",
        "north": "true" if along_z else "false",
        "south": "true" if along_z else "false",
        "waterlogged": "false",
        "west": "false" if along_z else "true",
    }


def stair_properties_for_window(exterior_normal: str, half: str) -> dict[str, str]:
    return {
        # The stair's full-height back faces inward, leaving its tread/lip on
        # the exterior side of the facade.
        "facing": OPPOSITE_FACING[exterior_normal],
        "half": half,
        "shape": "straight",
        "waterlogged": "false",
    }


def procedural_window_candidate(
    materials: dict[str, str],
    role: str,
    name: str,
    x: int,
    y: int,
    z: int,
    min_y: int,
    max_y: int,
) -> bool:
    if role not in {"wall_x", "wall_z"}:
        return False
    local_y = y - min_y
    if local_y <= 1 or max_y - y <= 2:
        return False
    if is_chapel_name(name):
        return (
            chapel_overlay_wall_material(materials, role, x, y, z, min_y, max_y)
            == materials["window"]
        )
    facade_axis = z if role == "wall_x" else x
    return local_y % 6 in (2, 3) and facade_axis % 7 in (2, 3)


def validated_window_assemblies(
    raw_blocks: set[tuple[int, int, int]],
    shell: set[tuple[int, int, int]],
    roles: dict[tuple[int, int, int], str],
    candidates: set[tuple[int, int, int]],
) -> tuple[
    set[tuple[int, int, int]],
    dict[tuple[int, int, int], tuple[str, str]],
    int,
]:
    eligible: dict[tuple[int, int, int], tuple[str, str]] = {}
    for coordinate in candidates & shell:
        role = roles[coordinate]
        if role not in {"wall_x", "wall_z"}:
            continue
        normal = facade_exterior_normal(raw_blocks, coordinate, role)
        if normal is not None:
            eligible[coordinate] = (role, normal)

    by_column: dict[tuple[int, int, str, str], list[int]] = {}
    for (x, y, z), (role, normal) in eligible.items():
        by_column.setdefault((x, z, role, normal), []).append(y)

    panes: set[tuple[int, int, int]] = set()
    frames: dict[tuple[int, int, int], tuple[str, str]] = {}
    assembly_count = 0
    for (x, z, role, normal), ys in sorted(by_column.items()):
        sorted_ys = sorted(set(ys))
        runs: list[list[int]] = []
        for y in sorted_ys:
            if not runs or y != runs[-1][-1] + 1:
                runs.append([y])
            else:
                runs[-1].append(y)
        for run in runs:
            if len(run) < 2:
                continue
            bottom = (x, run[0] - 1, z)
            top = (x, run[-1] + 1, z)
            if roles.get(bottom) != role or roles.get(top) != role:
                continue
            if facade_exterior_normal(raw_blocks, bottom, role) != normal:
                continue
            if facade_exterior_normal(raw_blocks, top, role) != normal:
                continue
            run_coordinates = {(x, y, z) for y in run}
            panes.update(run_coordinates)
            frames[bottom] = ("window_sill", normal)
            frames[top] = ("window_lintel", normal)
            assembly_count += 1
    return panes, frames, assembly_count


def generate_procedural_building_blocks(
    raw_blocks: set[tuple[int, int, int]],
    materials: dict[str, str],
    *,
    name: str,
    detected_window_voxels: set[tuple[int, int, int]] | None = None,
) -> ProceduralBuildingResult:
    if not raw_blocks:
        return ProceduralBuildingResult([], {}, Counter(), "procedural-rhythm-fallback")

    max_y = max(y for _x, y, _z in raw_blocks)
    shell, removed = hollow_building_blocks(raw_blocks)
    column_ranges: dict[tuple[int, int], tuple[int, int]] = {}
    for x, y, z in raw_blocks:
        column = (x, z)
        old_range = column_ranges.get(column)
        if old_range is None:
            column_ranges[column] = (y, y)
        else:
            column_ranges[column] = (min(old_range[0], y), max(old_range[1], y))

    roles = {
        (x, y, z): building_shell_block_role(raw_blocks, column_ranges, x, y, z)
        for x, y, z in shell
    }
    rhythmic_candidates = {
        (x, y, z)
        for x, y, z in shell
        if procedural_window_candidate(
            materials,
            roles[(x, y, z)],
            name,
            x,
            y,
            z,
            column_ranges[(x, z)][0],
            max_y,
        )
    }

    panes: set[tuple[int, int, int]] = set()
    frames: dict[tuple[int, int, int], tuple[str, str]] = {}
    assembly_count = 0
    window_mode = "procedural-rhythm-fallback"
    if detected_window_voxels:
        panes, frames, assembly_count = validated_window_assemblies(
            raw_blocks,
            shell,
            roles,
            set(detected_window_voxels),
        )
        if panes:
            window_mode = "voxelearth-source-glass-detected"
    if not panes:
        panes, frames, assembly_count = validated_window_assemblies(
            raw_blocks,
            shell,
            roles,
            rhythmic_candidates,
        )

    pane_block = glass_pane_material(materials["window"])
    stair_block = stair_material_for_trim(materials["trim"])
    generated: list[tuple[int, int, int, str, str]] = []
    block_states: dict[tuple[int, int, int], dict[str, str]] = {}
    stats: Counter[str] = Counter(
        {
            "raw_voxels": len(raw_blocks),
            "shell_voxels": len(shell),
            "hollowed_interior_voxels": removed,
            "source_window_evidence_voxels": len(detected_window_voxels or ()),
            "window_assemblies": assembly_count,
        }
    )
    for coordinate in sorted(shell):
        x, y, z = coordinate
        raw_role = roles[coordinate]
        role = "floor" if raw_role == "fill" else raw_role
        if coordinate in panes:
            block_name = pane_block
            role = "window_pane"
            block_states[coordinate] = pane_properties_for_wall(raw_role)
            stats["window_panes"] += 1
        elif coordinate in frames:
            role, normal = frames[coordinate]
            block_name = stair_block
            half = "bottom" if role == "window_sill" else "top"
            block_states[coordinate] = stair_properties_for_window(normal, half)
            stats["window_sills" if role == "window_sill" else "window_lintels"] += 1
        else:
            column_min_y, _column_max_y = column_ranges[(x, z)]
            block_name = overlay_material(
                materials,
                raw_role,
                name,
                x,
                y,
                z,
                column_min_y,
                max_y,
            )
            if "glass" in block_name:
                block_name = materials["wall"]
        generated.append((x, y, z, block_name, role))

    return ProceduralBuildingResult(generated, block_states, stats, window_mode)


def generate_chapel_landmark_blocks(
    raw_blocks: set[tuple[int, int, int]],
    materials: dict[str, str],
) -> list[tuple[int, int, int, str, str]]:
    if not raw_blocks:
        return []

    column_tops: dict[tuple[int, int], int] = {}
    for x, y, z in raw_blocks:
        column = (x, z)
        column_tops[column] = max(y, column_tops.get(column, y))

    max_y = max(column_tops.values())
    high_columns = {
        column
        for column, top_y in column_tops.items()
        if top_y >= max_y - 2
    }
    if not high_columns:
        return []

    min_x = min(x for x, _z in high_columns)
    max_x = max(x for x, _z in high_columns)
    min_z = min(z for _x, z in high_columns)
    max_z = max(z for _x, z in high_columns)
    center_x = int(round((min_x + max_x) / 2.0))
    center_z = int(round((min_z + max_z) / 2.0))
    trim = materials["trim"]
    roof = materials["roof"]
    additions: dict[tuple[int, int, int], tuple[str, str]] = {}

    for x, z in sorted(high_columns):
        exposed = any(
            (x + dx, z + dz) not in high_columns
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        if not exposed:
            continue
        additions[(x, max_y + 1, z)] = (trim, "landmark_trim")
        if (x + z) % 2 == 0:
            additions[(x, max_y + 2, z)] = (trim, "landmark_trim")

    for dy in range(2, 7):
        additions[(center_x, max_y + dy, center_z)] = (roof, "landmark_cross")
    if (max_z - min_z) >= (max_x - min_x):
        for dx in (-1, 1):
            additions[(center_x + dx, max_y + 5, center_z)] = (roof, "landmark_cross")
    else:
        for dz in (-1, 1):
            additions[(center_x, max_y + 5, center_z + dz)] = (roof, "landmark_cross")

    return [
        (x, y, z, block, role)
        for (x, y, z), (block, role) in sorted(additions.items())
    ]


def generate_chapel_procedural_blocks(
    raw_blocks: set[tuple[int, int, int]],
    materials: dict[str, str],
) -> list[tuple[int, int, int, str, str]]:
    return generate_procedural_building_blocks(
        raw_blocks,
        materials,
        name="CHAPEL",
    ).blocks


def chapel_overlay_wall_material(
    materials: dict[str, str],
    role: str,
    x: int,
    y: int,
    z: int,
    min_y: int,
    max_y: int,
) -> str:
    if role == "roof":
        return materials["roof"]
    if role == "fill":
        return materials["floor"]
    if role == "wall_corner":
        return materials["trim"]

    local_y = y - min_y
    wall_height = max(1, max_y - min_y)
    if local_y <= 1 or max_y - y <= 1:
        return materials["trim"]

    facade_axis = z if role == "wall_x" else x
    bay = facade_axis % 9
    if bay in (0, 8):
        return materials["trim"]

    arch_top_y = max(4, wall_height - 4)
    if bay in (2, 6) and 2 <= local_y <= arch_top_y + 1:
        return materials["trim"]
    if bay in (3, 4, 5) and local_y in {2, arch_top_y + 1}:
        return materials["trim"]
    if bay in (3, 4, 5) and 3 <= local_y <= arch_top_y:
        return materials["window"]

    return materials["wall"]


def overlay_material(
    materials: dict[str, str],
    role: str,
    name: str,
    x: int,
    y: int,
    z: int,
    min_y: int,
    max_y: int,
) -> str:
    if role == "roof":
        return materials["roof"]
    if role == "fill":
        return materials["floor"]
    if role == "wall_corner":
        return materials["trim"]
    local_y = y - min_y
    is_chapel = is_chapel_name(name)
    if is_chapel:
        return chapel_overlay_wall_material(materials, role, x, y, z, min_y, max_y)
    if local_y <= 1 or max_y - y <= 1:
        return materials["trim"]
    spacing = 7
    window_height = local_y % 6
    facade_axis = z if role == "wall_x" else x
    bay = facade_axis % spacing
    if window_height in (2, 3) and bay in (2, 3):
        return materials["window"]
    return materials["wall"]


def clear_overlay_volumes(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    edit_mask: set[tuple[int, int, int]],
) -> Counter[str]:
    stats: Counter[str] = Counter()
    for (x, z), (min_y, max_y) in overlay.clear_columns.items():
        existing_top = source_top_surface.get((x, z), (max_y, AIR))[0]
        clear_top = max(max_y, existing_top + 2)
        for y in range(min_y, clear_top + 1):
            edit_mask.add((x, y, z))
            if world.set_block(x, y, z, AIR):
                stats["air_blocks"] += 1
        stats["columns"] += 1
    return stats


def place_overlay_support_blocks(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    edit_mask: set[tuple[int, int, int]],
) -> Counter[str]:
    stats: Counter[str] = Counter()
    for (x, y, z), block_name in overlay.support_blocks.items():
        edit_mask.add((x, y, z))
        if world.set_block(x, y, z, block_name):
            stats["support_filled"] += 1
    stats["columns"] = len(overlay.support_blocks)
    return stats


def place_overlay_blocks(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    edit_mask: set[tuple[int, int, int]],
) -> Counter[str]:
    stats: Counter[str] = Counter()
    for x, y, z, block_name, role in overlay.blocks:
        coordinate = (x, y, z)
        edit_mask.add(coordinate)
        properties = overlay.block_states.get(coordinate)
        if properties is None:
            changed = world.set_block(x, y, z, block_name)
        else:
            changed = world.set_block_state(x, y, z, block_name, properties)
            stats["stateful_blocks"] += 1
        if changed:
            stats[role] += 1
            stats["total"] += 1
    return stats


def apply_overlay_apron_cleanup(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    *,
    radius: int,
    edit_mask: set[tuple[int, int, int]],
    protected_building_columns: set[tuple[int, int]] | None = None,
    minimum_y: int = -64,
) -> Counter[str]:
    stats: Counter[str] = Counter()
    if radius <= 0:
        return stats
    building_columns = set(overlay.clear_columns)
    protected_columns = building_columns | set(protected_building_columns or ())
    exempted_columns: set[tuple[int, int]] = set()
    anchors: list[tuple[int, int, int, int, int]] = []
    for anchor in overlay.anchors:
        bbox = anchor.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 6:
            stats["missing_bbox"] += 1
            continue
        try:
            min_x, _min_y, min_z, max_x, _max_y, max_z = [
                int(round(float(value))) for value in bbox
            ]
            ground_y = int(round(float(anchor["voxelearth_ring_ground_y"])))
        except (KeyError, TypeError, ValueError):
            stats["missing_ground_y"] += 1
            continue

        stats["accepted_anchor_count"] += 1
        anchors.append((min_x, min_z, max_x, max_z, ground_y))

    apron_candidates: set[tuple[int, int]] = set()
    for x, z in building_columns:
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if dx == 0 and dz == 0:
                    continue
                column = (x + dx, z + dz)
                if column in protected_columns:
                    exempted_columns.add(column)
                    continue
                apron_candidates.add(column)

    apron_columns: dict[tuple[int, int], tuple[int, int]] = {}
    for column in apron_candidates:
        x, z = column
        nearest_anchor: tuple[int, int] | None = None
        for min_x, min_z, max_x, max_z, ground_y in anchors:
            outside_x = max(min_x - x, 0, x - max_x)
            outside_z = max(min_z - z, 0, z - max_z)
            candidate = (max(outside_x, outside_z), ground_y)
            if nearest_anchor is None or candidate < nearest_anchor:
                nearest_anchor = candidate
        if nearest_anchor is not None:
            apron_columns[column] = nearest_anchor

    stats["candidate_columns"] = len(apron_columns)
    stats["building_columns_exempted"] = len(exempted_columns)
    preserved_surface_ys: list[int] = []
    for (x, z), (_distance, ground_y) in sorted(apron_columns.items()):
        source_top = source_top_surface.get((x, z))
        if source_top is None:
            stats["missing_source_columns"] += 1
            continue
        source_top_y, _source_top_block = source_top
        stats["columns"] += 1
        if source_top_y <= ground_y:
            stats["low_columns_preserved"] += 1
            continue
        for y in range(ground_y + 1, source_top_y + 1):
            edit_mask.add((x, y, z))
            if world.set_block(x, y, z, AIR):
                stats["cleared_above_ground"] += 1
        preserved_surface_y: int | None = None
        preserved_surface = AIR
        for candidate_y in range(ground_y, minimum_y - 1, -1):
            candidate_block = world.get_block(x, candidate_y, z)
            if candidate_block not in AIR_BLOCKS:
                preserved_surface_y = candidate_y
                preserved_surface = candidate_block
                break
        if preserved_surface_y is None:
            source_top_surface.pop((x, z), None)
            stats["missing_preserved_surface"] += 1
        else:
            source_top_surface[(x, z)] = (preserved_surface_y, preserved_surface)
            preserved_surface_ys.append(preserved_surface_y)
            stats["surface_preserved"] += 1
            if preserved_surface_y < ground_y:
                stats["lower_local_surfaces_preserved"] += 1
        stats["cleared_columns"] += 1
    stats["protected_building_columns"] = len(protected_columns)
    if preserved_surface_ys:
        stats["preserved_surface_y_min"] = min(preserved_surface_ys)
        stats["preserved_surface_y_max"] = max(preserved_surface_ys)
    return stats


def apply_chapel_apron_cleanup(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    *,
    radius: int,
    minimum_y: int,
    edit_mask: set[tuple[int, int, int]],
    protected_building_columns: set[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    stats: Counter[str] = Counter()
    if radius <= 0:
        return {
            "enabled": False,
            "radius": max(0, radius),
            "chapel_count": 0,
            "candidate_columns": 0,
            "building_columns_exempted": 0,
            "low_columns_preserved": 0,
            "rubble_columns_cleared": 0,
            "air_blocks": 0,
            "ground_blocks": 0,
        }

    all_building_columns = set(overlay.clear_columns) | set(protected_building_columns or ())
    visited_columns: set[tuple[int, int]] = set()
    ground_ys: list[int] = []
    for anchor in overlay.anchors:
        name = str(anchor.get("name") or "")
        if not is_chapel_name(name):
            continue
        bbox = anchor.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 6:
            stats["missing_bbox"] += 1
            continue
        min_x, min_y, min_z, max_x, _max_y, max_z = [int(round(float(value))) for value in bbox]
        ground_y = int(round(float(anchor.get("voxelearth_ring_ground_y") or min_y)))
        protected_columns = all_building_columns
        ground_ys.append(ground_y)
        stats["chapel_count"] += 1
        for x in range(min_x - radius, max_x + radius + 1):
            for z in range(min_z - radius, max_z + radius + 1):
                column = (x, z)
                if column in visited_columns:
                    continue
                visited_columns.add(column)
                stats["candidate_columns"] += 1
                if column in protected_columns:
                    stats["building_columns_exempted"] += 1
                    continue
                source_top = source_top_surface.get(column)
                fallback_y = source_top[0] if source_top is not None else ground_y
                top_y = target_top_y_at(
                    world,
                    x,
                    z,
                    fallback_y,
                    minimum_y=minimum_y,
                    search_above=max(32, CHAPEL_APRON_RUBBLE_HEIGHT + 16),
                )
                if top_y > ground_y + CHAPEL_APRON_RUBBLE_HEIGHT:
                    for y in range(ground_y + 1, top_y + 1):
                        edit_mask.add((x, y, z))
                        if world.set_block(x, y, z, AIR):
                            stats["air_blocks"] += 1
                    stats["rubble_columns_cleared"] += 1
                elif top_y < ground_y:
                    stats["low_columns_filled"] += 1
                else:
                    stats["level_columns_retyped"] += 1

                if top_y < ground_y:
                    fill_start = max(minimum_y, top_y + 1)
                else:
                    fill_start = max(minimum_y, ground_y - 3)
                for y in range(fill_start, ground_y):
                    edit_mask.add((x, y, z))
                    if world.set_block(x, y, z, "minecraft:dirt"):
                        stats["ground_blocks"] += 1
                edit_mask.add((x, ground_y, z))
                if world.set_block(x, ground_y, z, CHAPEL_APRON_SURFACE_BLOCK):
                    stats["ground_blocks"] += 1
                source_top_surface[column] = (ground_y, CHAPEL_APRON_SURFACE_BLOCK)

    return {
        "enabled": True,
        "radius": radius,
        "chapel_count": stats["chapel_count"],
        "candidate_columns": stats["candidate_columns"],
        "building_columns_exempted": stats["building_columns_exempted"],
        "low_columns_preserved": stats["low_columns_preserved"],
        "low_columns_filled": stats["low_columns_filled"],
        "level_columns_retyped": stats["level_columns_retyped"],
        "rubble_columns_cleared": stats["rubble_columns_cleared"],
        "air_blocks": stats["air_blocks"],
        "ground_blocks": stats["ground_blocks"],
        "missing_bbox": stats["missing_bbox"],
        "ground_y_min": min(ground_ys, default=None),
        "ground_y_max": max(ground_ys, default=None),
    }


def apply_chapel_procedural_section(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    *,
    radius: int,
    minimum_y: int,
    edit_mask: set[tuple[int, int, int]],
    support_overrides: dict[tuple[int, int, int], str] | None = None,
) -> dict[str, Any]:
    """Replace the Chapel test section with deterministic, level terrain.

    This is intentionally applied after generic terrain and site overlays but
    before the Chapel shell is stamped.  Every column in the rectangular test
    section is cleared above the target surface and filled continuously from
    the campus minimum Y, eliminating inherited holes and steep source relief.
    """

    if radius <= 0:
        return {
            "enabled": False,
            "radius": max(0, radius),
            "chapel_count": 0,
            "columns": 0,
        }

    chapel_anchors = [
        anchor
        for anchor in overlay.anchors
        if is_chapel_name(str(anchor.get("name") or ""))
    ]
    if len(chapel_anchors) != 1:
        raise ValueError(
            "procedural Chapel section requires exactly one accepted Chapel "
            f"anchor, found {len(chapel_anchors)}"
        )
    bbox = chapel_anchors[0].get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 6:
        raise ValueError("accepted Chapel anchor has no valid bbox")
    min_x, min_y, min_z, max_x, max_y, max_z = [
        int(round(float(value))) for value in bbox
    ]
    target_ground_y = min_y - 1
    section_min_x = min_x - radius
    section_max_x = max_x + radius
    section_min_z = min_z - radius
    section_max_z = max_z + radius
    chapel_columns = {
        column
        for column in overlay.clear_columns
        if min_x <= column[0] <= max_x and min_z <= column[1] <= max_z
    }
    previous_ground_ys: list[int] = []
    stats: Counter[str] = Counter()

    for x in range(section_min_x, section_max_x + 1):
        for z in range(section_min_z, section_max_z + 1):
            previous_surface = source_top_surface.get((x, z))
            if previous_surface is not None:
                previous_ground_ys.append(previous_surface[0])
                clear_top = max(max_y + BUILDING_CLEAR_HEADROOM, previous_surface[0] + 2)
            else:
                stats["missing_source_columns"] += 1
                clear_top = max_y + BUILDING_CLEAR_HEADROOM

            for y in range(target_ground_y + 1, clear_top + 1):
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, AIR):
                    stats["cleared_above_ground"] += 1

            for y in range(minimum_y, target_ground_y + 1):
                if y == target_ground_y:
                    block_name = CHAPEL_SECTION_SURFACE_BLOCK
                elif y >= target_ground_y - CHAPEL_SECTION_TOPSOIL_DEPTH:
                    block_name = CHAPEL_SECTION_SUBSURFACE_BLOCK
                else:
                    block_name = CHAPEL_SECTION_DEEP_BLOCK
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, block_name):
                    if y == target_ground_y:
                        stats["surface_blocks"] += 1
                    elif block_name == CHAPEL_SECTION_SUBSURFACE_BLOCK:
                        stats["subsurface_blocks"] += 1
                    else:
                        stats["deep_blocks"] += 1

            source_top_surface[(x, z)] = (
                target_ground_y,
                CHAPEL_SECTION_SURFACE_BLOCK,
            )
            support_coord = (x, target_ground_y, z)
            if (
                support_overrides is not None
                and (x, z) in chapel_columns
                and support_coord not in overlay.support_blocks
            ):
                support_overrides[support_coord] = CHAPEL_SECTION_SURFACE_BLOCK
            stats["columns"] += 1

    return {
        "enabled": True,
        "radius": radius,
        "chapel_count": 1,
        "bounds": [
            section_min_x,
            minimum_y,
            section_min_z,
            section_max_x,
            target_ground_y,
            section_max_z,
        ],
        "target_ground_y": target_ground_y,
        "previous_ground_y_min": min(previous_ground_ys, default=None),
        "previous_ground_y_max": max(previous_ground_ys, default=None),
        "columns": stats["columns"],
        "missing_source_columns": stats["missing_source_columns"],
        "cleared_above_ground": stats["cleared_above_ground"],
        "surface_blocks": stats["surface_blocks"],
        "subsurface_blocks": stats["subsurface_blocks"],
        "deep_blocks": stats["deep_blocks"],
        "support_override_columns": len(support_overrides or {}),
        "surface_material": CHAPEL_SECTION_SURFACE_BLOCK,
        "subsurface_material": CHAPEL_SECTION_SUBSURFACE_BLOCK,
        "deep_material": CHAPEL_SECTION_DEEP_BLOCK,
    }


def audit_overlay_support(
    source_world: Path,
    target_world: Path,
    overlay: VoxelBuildingOverlay,
    *,
    max_samples: int = 50,
    allowed_support_overrides: dict[tuple[int, int, int], str] | None = None,
) -> dict[str, Any]:
    source = AnvilWorld(source_world)
    target = AnvilWorld(target_world)
    mismatches: list[dict[str, Any]] = []
    air_supports: list[dict[str, Any]] = []
    floating: list[dict[str, Any]] = []
    checked = 0
    for (x, z), (min_y, _max_y) in sorted(overlay.clear_columns.items()):
        support_y = min_y - 1
        source_block = source.get_block(x, support_y, z)
        target_block = target.get_block(x, support_y, z)
        floor_block = target.get_block(x, min_y, z)
        support_coord = (x, support_y, z)
        checked += 1
        allowed_override = (allowed_support_overrides or {}).get(support_coord)
        if allowed_override is not None:
            if target_block != allowed_override and len(mismatches) < max_samples:
                mismatches.append(
                    {
                        "coordinate": [x, support_y, z],
                        "source": source_block,
                        "target": target_block,
                        "expected_override": allowed_override,
                    }
                )
            if target_block in AIR_BLOCKS and len(air_supports) < max_samples:
                air_supports.append({"coordinate": [x, support_y, z], "source": source_block})
            if floor_block in AIR_BLOCKS and len(floating) < max_samples:
                floating.append({"coordinate": [x, min_y, z]})
            continue
        expected_fill = overlay.support_blocks.get(support_coord)
        if expected_fill is not None:
            if source_block not in AIR_BLOCKS and len(mismatches) < max_samples:
                mismatches.append(
                    {
                        "coordinate": [x, support_y, z],
                        "source": source_block,
                        "target": target_block,
                        "expected_fill": expected_fill,
                    }
                )
            if target_block != expected_fill and len(mismatches) < max_samples:
                mismatches.append(
                    {
                        "coordinate": [x, support_y, z],
                        "source": source_block,
                        "target": target_block,
                        "expected_fill": expected_fill,
                    }
                )
        elif source_block != target_block and len(mismatches) < max_samples:
            mismatches.append(
                {
                    "coordinate": [x, support_y, z],
                    "source": source_block,
                    "target": target_block,
                }
            )
        if target_block in AIR_BLOCKS and len(air_supports) < max_samples:
            air_supports.append({"coordinate": [x, support_y, z], "source": source_block})
        if floor_block in AIR_BLOCKS and len(floating) < max_samples:
            floating.append({"coordinate": [x, min_y, z]})
    payload = {
        "columns_checked": checked,
        "support_block_mismatches": len(mismatches),
        "air_support_columns": len(air_supports),
        "floating_floor_columns": len(floating),
        "expected_support_fill_columns": len(overlay.support_blocks),
        "allowed_support_override_columns": len(allowed_support_overrides or {}),
        "support_mismatch_samples": mismatches,
        "air_support_samples": air_supports,
        "floating_floor_samples": floating,
    }
    if mismatches or air_supports or floating:
        raise AssertionError(json.dumps(payload, indent=2))
    return payload


def audit_overlay_shell_windows(
    target_world: Path,
    overlay: VoxelBuildingOverlay,
    *,
    max_samples: int = 50,
) -> dict[str, Any]:
    """Verify the serialized campus shells, hollow air, panes, and stair states."""

    target = AnvilWorld(target_world)
    expected: dict[tuple[int, int, int], tuple[str, str]] = {}
    for x, y, z, block_name, role in overlay.blocks:
        expected[(x, y, z)] = (block_name, role)

    block_mismatches: list[dict[str, Any]] = []
    state_mismatches: list[dict[str, Any]] = []
    block_mismatch_count = 0
    state_mismatch_count = 0
    actual_roles: Counter[str] = Counter()
    full_glass_blocks = 0
    pane_blocks = 0
    stair_blocks = 0
    for coordinate, (expected_block, role) in sorted(expected.items()):
        x, y, z = coordinate
        actual_block, actual_properties = target.get_block_state(x, y, z)
        actual_roles[role] += 1
        if actual_block != expected_block:
            block_mismatch_count += 1
            if len(block_mismatches) < max_samples:
                block_mismatches.append(
                    {
                        "coordinate": list(coordinate),
                        "expected": expected_block,
                        "actual": actual_block,
                        "role": role,
                    }
                )
        expected_properties = overlay.block_states.get(coordinate)
        if expected_properties is not None and actual_properties != expected_properties:
            state_mismatch_count += 1
            if len(state_mismatches) < max_samples:
                state_mismatches.append(
                    {
                        "coordinate": list(coordinate),
                        "block": actual_block,
                        "expected": expected_properties,
                        "actual": actual_properties,
                        "role": role,
                    }
                )
        if expected_block == "minecraft:glass" or expected_block.endswith("_stained_glass"):
            full_glass_blocks += 1
        if expected_block == "minecraft:glass_pane" or expected_block.endswith("_glass_pane"):
            pane_blocks += 1
        if expected_block.endswith("_stairs"):
            stair_blocks += 1

    shell_column_ys: dict[tuple[int, int], list[int]] = {}
    for (x, y, z), (_block, role) in expected.items():
        if role.startswith("landmark_"):
            continue
        shell_column_ys.setdefault((x, z), []).append(y)
    non_air_interior: list[dict[str, Any]] = []
    non_air_interior_count = 0
    interior_air_checked = 0
    for (x, z), ys in sorted(shell_column_ys.items()):
        for y in range(min(ys) + 1, max(ys)):
            coordinate = (x, y, z)
            if coordinate in expected:
                continue
            interior_air_checked += 1
            actual = target.get_block(x, y, z)
            if actual not in AIR_BLOCKS:
                non_air_interior_count += 1
                if len(non_air_interior) < max_samples:
                    non_air_interior.append(
                        {"coordinate": list(coordinate), "actual": actual}
                    )

    pane_columns: dict[tuple[int, int], list[int]] = {}
    for (x, y, z), (_block, role) in expected.items():
        if role == "window_pane":
            pane_columns.setdefault((x, z), []).append(y)
    unframed_windows: list[dict[str, Any]] = []
    unframed_window_count = 0
    window_assemblies = 0
    for (x, z), ys in sorted(pane_columns.items()):
        runs: list[list[int]] = []
        for y in sorted(set(ys)):
            if not runs or y != runs[-1][-1] + 1:
                runs.append([y])
            else:
                runs[-1].append(y)
        for run in runs:
            window_assemblies += 1
            bottom = (x, run[0] - 1, z)
            top = (x, run[-1] + 1, z)
            bottom_role = expected.get(bottom, (None, None))[1]
            top_role = expected.get(top, (None, None))[1]
            if bottom_role != "window_sill" or top_role != "window_lintel":
                unframed_window_count += 1
                if len(unframed_windows) < max_samples:
                    unframed_windows.append(
                        {
                            "pane_column": [x, z],
                            "pane_y_min": run[0],
                            "pane_y_max": run[-1],
                            "bottom_role": bottom_role,
                            "top_role": top_role,
                        }
                    )

    payload = {
        "expected_blocks_checked": len(expected),
        "stateful_blocks_checked": len(overlay.block_states),
        "block_mismatches": block_mismatch_count,
        "state_mismatches": state_mismatch_count,
        "interior_air_blocks_checked": interior_air_checked,
        "non_air_interior_blocks": non_air_interior_count,
        "window_assemblies": window_assemblies,
        "unframed_window_assemblies": unframed_window_count,
        "pane_blocks": pane_blocks,
        "stair_blocks": stair_blocks,
        "full_glass_blocks": full_glass_blocks,
        "fill_role_blocks": actual_roles["fill"],
        "glowstone_blocks": sum(
            block == "minecraft:glowstone" for block, _role in expected.values()
        ),
        "role_counts": dict(actual_roles.most_common()),
        "block_mismatch_samples": block_mismatches,
        "state_mismatch_samples": state_mismatches,
        "non_air_interior_samples": non_air_interior,
        "unframed_window_samples": unframed_windows,
    }
    failures = (
        block_mismatch_count
        or state_mismatch_count
        or non_air_interior_count
        or unframed_window_count
        or full_glass_blocks
        or actual_roles["fill"]
        or payload["glowstone_blocks"]
        or pane_blocks == 0
        or stair_blocks == 0
    )
    if failures:
        raise AssertionError(json.dumps(payload, indent=2))
    return payload


def material_set_for_text(name: str, description: str = "") -> dict[str, str]:
    text = f"{name} {description}".lower()
    historic = any(token in text for token in ("chapel", "hall", "dorm", "library", "school", "house"))
    if "chapel" in text:
        return {
            "wall": "minecraft:bricks",
            "trim": "minecraft:stone_bricks",
            "roof": "minecraft:deepslate_tiles",
            "window": "minecraft:black_stained_glass",
            "floor": "minecraft:smooth_stone",
        }
    if historic:
        return {
            "wall": "minecraft:bricks",
            "trim": "minecraft:stone_bricks",
            "roof": "minecraft:deepslate_bricks",
            "window": "minecraft:glass",
            "floor": "minecraft:smooth_stone",
        }
    return {
        "wall": "minecraft:smooth_stone",
        "trim": "minecraft:light_gray_concrete",
        "roof": "minecraft:gray_concrete",
        "window": "minecraft:glass",
        "floor": "minecraft:smooth_stone",
    }


def audit_continuous_campus_ground(
    target_world: Path,
    ground_surface: dict[tuple[int, int], tuple[int, str]],
    overlay: VoxelBuildingOverlay,
    *,
    minimum_y: int,
    expected_flat_ground_y: int | None = None,
    max_samples: int = 50,
) -> dict[str, Any]:
    """Verify a single continuous terrain surface and solid building foundations."""

    target = AnvilWorld(target_world)
    top_surface = load_top_surface(target_world)
    building_columns = set(overlay.clear_columns)
    building_columns.update((x, z) for x, _y, z, _block, _role in overlay.blocks)
    missing_surface_samples: list[list[int]] = []
    layered_surface_samples: list[dict[str, Any]] = []
    subsurface_air_samples: list[list[int]] = []
    foundation_air_samples: list[list[int]] = []
    disconnected_edge_samples: list[dict[str, Any]] = []
    missing_surface_columns = 0
    layered_surface_columns = 0
    subsurface_air_blocks = 0
    foundation_air_blocks = 0
    disconnected_building_edges = 0
    building_edges_checked = 0
    adjacent_steps_over_one = 0
    adjacent_steps_over_one_outside_building_grades = 0
    maximum_adjacent_step = 0
    flat_height_mismatches = sum(
        ground_y != expected_flat_ground_y
        for ground_y, _surface_block in ground_surface.values()
    ) if expected_flat_ground_y is not None else 0
    building_transition_columns = set(building_columns)
    transition_frontier = set(building_columns)
    for _distance in range(BUILDING_GROUND_TRANSITION_RADIUS):
        next_frontier = {
            (x + dx, z + dz)
            for x, z in transition_frontier
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
        } - building_transition_columns
        building_transition_columns.update(next_frontier)
        transition_frontier = next_frontier

    for (x, z), (ground_y, _surface_block) in ground_surface.items():
        if target.get_block(x, ground_y, z) in AIR_BLOCKS:
            missing_surface_columns += 1
            if len(missing_surface_samples) < max_samples:
                missing_surface_samples.append([x, ground_y, z])
        foundation_column = (x, z) in overlay.clear_columns
        for y in range(minimum_y, ground_y):
            if target.get_block(x, y, z) not in AIR_BLOCKS:
                continue
            subsurface_air_blocks += 1
            if len(subsurface_air_samples) < max_samples:
                subsurface_air_samples.append([x, y, z])
            if foundation_column:
                foundation_air_blocks += 1
                if len(foundation_air_samples) < max_samples:
                    foundation_air_samples.append([x, y, z])
        if (x, z) in building_columns:
            continue
        actual_top = top_surface.get((x, z))
        if actual_top is None or actual_top[0] != ground_y:
            layered_surface_columns += 1
            if len(layered_surface_samples) < max_samples:
                layered_surface_samples.append(
                    {
                        "column": [x, z],
                        "expected_ground_y": ground_y,
                        "actual_top": list(actual_top) if actual_top is not None else None,
                    }
                )
        for dx, dz in ((1, 0), (0, 1)):
            neighbor = ground_surface.get((x + dx, z + dz))
            if neighbor is None or (x + dx, z + dz) in building_columns:
                continue
            step = abs(ground_y - neighbor[0])
            maximum_adjacent_step = max(maximum_adjacent_step, step)
            if step > 1:
                adjacent_steps_over_one += 1
                if (
                    (x, z) not in building_transition_columns
                    and (x + dx, z + dz) not in building_transition_columns
                ):
                    adjacent_steps_over_one_outside_building_grades += 1

    for (x, z), (floor_y, _max_y) in overlay.clear_columns.items():
        ground = ground_surface.get((x, z))
        if ground is None:
            continue
        support_y = floor_y - 1
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor_column = (x + dx, z + dz)
            neighbor = ground_surface.get(neighbor_column)
            if neighbor is None or neighbor_column in building_columns:
                continue
            building_edges_checked += 1
            step = abs(support_y - neighbor[0])
            if step <= 1:
                continue
            disconnected_building_edges += 1
            if len(disconnected_edge_samples) < max_samples:
                disconnected_edge_samples.append(
                    {
                        "building_column": [x, z],
                        "support_y": support_y,
                        "terrain_column": [neighbor_column[0], neighbor_column[1]],
                        "terrain_y": neighbor[0],
                        "step": step,
                    }
                )

    building_ground_columns = sum(
        column in ground_surface for column in overlay.clear_columns
    )
    payload = {
        "expected_ground_columns": len(ground_surface),
        "expected_flat_ground_y": expected_flat_ground_y,
        "ground_y_min": min(
            (ground_y for ground_y, _block in ground_surface.values()),
            default=None,
        ),
        "ground_y_max": max(
            (ground_y for ground_y, _block in ground_surface.values()),
            default=None,
        ),
        "flat_height_mismatches": flat_height_mismatches,
        "missing_surface_columns": missing_surface_columns,
        "missing_surface_samples": missing_surface_samples,
        "layered_surface_columns": layered_surface_columns,
        "layered_surface_samples": layered_surface_samples,
        "subsurface_air_blocks": subsurface_air_blocks,
        "subsurface_air_samples": subsurface_air_samples,
        "building_ground_columns": building_ground_columns,
        "building_columns_outside_ground": len(overlay.clear_columns) - building_ground_columns,
        "foundation_air_blocks": foundation_air_blocks,
        "foundation_air_samples": foundation_air_samples,
        "building_edges_checked": building_edges_checked,
        "disconnected_building_edges": disconnected_building_edges,
        "disconnected_edge_samples": disconnected_edge_samples,
        "adjacent_steps_over_one": adjacent_steps_over_one,
        "adjacent_steps_over_one_outside_building_grades": (
            adjacent_steps_over_one_outside_building_grades
        ),
        "building_ground_transition_radius": BUILDING_GROUND_TRANSITION_RADIUS,
        "maximum_adjacent_step": maximum_adjacent_step,
    }
    failures = (
        missing_surface_columns
        or layered_surface_columns
        or subsurface_air_blocks
        or payload["building_columns_outside_ground"]
        or foundation_air_blocks
        or disconnected_building_edges
        or adjacent_steps_over_one_outside_building_grades
        or flat_height_mismatches
        or (expected_flat_ground_y is not None and adjacent_steps_over_one)
    )
    if failures:
        raise AssertionError(json.dumps(payload, indent=2))
    return payload


def material_set(building: BuildingModel) -> dict[str, str]:
    return material_set_for_text(building.name, str(building.attributes.get("DESCRIPTION", "")))


def clear_building_volumes(
    world: AnvilWorld,
    buildings: list[BuildingModel],
    top_surface: dict[tuple[int, int], tuple[int, str]],
    clear_buffer: float,
    edit_mask: set[tuple[int, int, int]] | None = None,
) -> Counter[str]:
    stats: Counter[str] = Counter()
    for building in buildings:
        if building.base_y is None:
            continue
        footprint = building.footprint_union
        clear_geom = footprint.buffer(clear_buffer)
        prepared_clear = prep(clear_geom)
        prepared_footprint = prep(footprint)
        minx, minz, maxx, maxz = clear_geom.bounds
        clear_top = building.base_y + int(math.ceil(building.height_m)) + 10
        for x in range(math.floor(minx), math.ceil(maxx) + 1):
            for z in range(math.floor(minz), math.ceil(maxz) + 1):
                point = Point(x + 0.5, z + 0.5)
                if not prepared_clear.contains(point):
                    continue
                inside = prepared_footprint.contains(point)
                existing_top = top_surface.get((x, z), (building.base_y, AIR))[0]
                top_y = max(existing_top + 2, clear_top)
                start_y = building.base_y if inside else building.base_y + 2
                for y in range(start_y, top_y + 1):
                    if edit_mask is not None:
                        edit_mask.add((x, y, z))
                    if world.set_block(x, y, z, AIR):
                        stats["air_blocks"] += 1
                stats["columns"] += 1
    return stats


def generate_building_blocks(
    buildings: list[BuildingModel],
    *,
    wall_thickness: float,
    roof_pitch: float,
) -> Iterator[tuple[int, int, int, str, str]]:
    for building in buildings:
        if building.base_y is None:
            continue
        materials = material_set(building)
        base_y = building.base_y
        eave_y = base_y + int(round(building.eave_height_m))
        max_y = base_y + int(math.ceil(building.height_m))
        for footprint in building.footprints:
            prepared = prep(footprint)
            minx, minz, maxx, maxz = footprint.bounds
            boundary = footprint.boundary
            for x in range(math.floor(minx) - 1, math.ceil(maxx) + 2):
                for z in range(math.floor(minz) - 1, math.ceil(maxz) + 2):
                    point = Point(x + 0.5, z + 0.5)
                    if not prepared.contains(point):
                        continue
                    yield x, base_y, z, materials["floor"], "floor"
                    distance = boundary.distance(point)
                    if distance <= wall_thickness:
                        along = int(round(boundary.project(point)))
                        for y in range(base_y + 1, eave_y + 1):
                            yield x, y, z, wall_material(building, materials, x, y, z, base_y, eave_y, along), "wall"
                    elif (eave_y - base_y) >= 9:
                        for y in range(base_y + 4, eave_y, 4):
                            yield x, y, z, materials["floor"], "floor"
        seen_roof: set[tuple[int, int, int]] = set()
        for face in building.roof_faces:
            for x, y, z in sample_roof_face(face, building.source_base_z, base_y, max_y, roof_pitch):
                key = (x, y, z)
                if key in seen_roof:
                    continue
                seen_roof.add(key)
                yield x, y, z, materials["roof"], "roof"


def wall_material(
    building: BuildingModel,
    materials: dict[str, str],
    x: int,
    y: int,
    z: int,
    base_y: int,
    eave_y: int,
    along: int,
) -> str:
    local_y = y - base_y
    if local_y <= 1 or eave_y - y <= 1:
        return materials["trim"]
    is_chapel = "chapel" in building.name.lower()
    spacing = 8 if is_chapel else 6
    window_width = 2 if is_chapel else 1
    vertical_slot = local_y % 4
    horizontal_slot = along % spacing
    if vertical_slot in (2, 3) and 1 <= horizontal_slot <= window_width:
        return materials["window"]
    if (x + z) % 17 == 0 and local_y % 5 == 0:
        return materials["trim"]
    return materials["wall"]


def sample_roof_face(
    face: list[tuple[float, float, float]],
    source_base_z: float,
    base_y: int,
    max_y: int,
    pitch: float,
) -> Iterator[tuple[int, int, int]]:
    if len(face) < 3:
        return
    anchor = face[0]
    for index in range(1, len(face) - 1):
        yield from sample_triangle(anchor, face[index], face[index + 1], source_base_z, base_y, max_y, pitch)


def sample_triangle(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    source_base_z: float,
    base_y: int,
    max_y: int,
    pitch: float,
) -> Iterator[tuple[int, int, int]]:
    edges = (
        math.dist(a, b),
        math.dist(b, c),
        math.dist(c, a),
    )
    steps = max(1, int(math.ceil(max(edges) / max(0.2, pitch))))
    for i in range(steps + 1):
        for j in range(steps + 1 - i):
            u = i / steps
            v = j / steps
            w = 1.0 - u - v
            x = a[0] * w + b[0] * u + c[0] * v
            z = a[1] * w + b[1] * u + c[1] * v
            source_z = a[2] * w + b[2] * u + c[2] * v
            y = base_y + int(round(source_z - source_base_z))
            if y < base_y:
                y = base_y
            if y > max_y + 3:
                y = max_y + 3
            yield int(round(x)), y, int(round(z))


def copy_world(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"target world already exists: {target}")
    ignore = shutil.ignore_patterns("session.lock", "*.lck")
    shutil.copytree(source, target, ignore=ignore)


def run_self_test(source_world: Path, output_dir: Path) -> Path:
    proof_dir = output_dir / "anvil-write-proof"
    if proof_dir.exists():
        shutil.rmtree(proof_dir)
    copy_world(source_world, proof_dir)
    top_surface = load_top_surface(proof_dir)
    x, z = next(iter(top_surface.keys()))
    y = top_surface[(x, z)][0] + 1
    sample_before = (x, y - 1, z, AnvilWorld(proof_dir).get_block(x, y - 1, z))

    world = AnvilWorld(proof_dir)
    test_block = "minecraft:gold_block"
    changed = world.set_block(x, y, z, test_block)
    touched = world.save()
    if not changed or touched <= 0:
        raise AssertionError("self-test did not modify a chunk")
    reopened = AnvilWorld(proof_dir)
    if reopened.get_block(x, y, z) != test_block:
        raise AssertionError("self-test block did not round-trip")
    if reopened.get_block(sample_before[0], sample_before[1], sample_before[2]) != sample_before[3]:
        raise AssertionError("untouched neighbor block changed")
    invariance = audit_unmasked_changes(source_world, proof_dir, {(x, y, z)})
    marker = proof_dir / "anvil-write-proof.json"
    marker.write_text(
        json.dumps(
            {
                "test_coordinate": [x, y, z],
                "test_block": test_block,
                "touched_chunks": touched,
                "untouched_neighbor": list(sample_before),
                "invariance_audit": invariance,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return marker


def hybridize(args: argparse.Namespace) -> dict[str, Any]:
    source_world = args.source_world.resolve()
    cityjson_path = args.roofer_cityjson.resolve()
    overlay_npz_path = args.roofer_overlay_npz.resolve()
    output_dir = args.output_dir.resolve()
    manifest_path = source_world / "voxelearth-hill-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"VoxelEarth manifest not found: {manifest_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    world_name = args.world_name or f"hill_school_hybrid_voxelearth_ground_roofer_{time.strftime('%Y%m%d_%H%M')}"
    target_world = output_dir / world_name
    copy_world(source_world, target_world)

    transform = WorldTransform.from_manifest(manifest_path)
    source_top_surface = load_top_surface(target_world)
    world = AnvilWorld(target_world)
    edit_mask: set[tuple[int, int, int]] = set()
    cityjson_buildings: list[BuildingModel] | None = None

    terrain_stats: Counter[str] = Counter()
    anchor_surface = source_top_surface
    ground_surface = None
    if args.terrain_only_fallback:
        ground_surface = build_terrain_surface(
            source_top_surface,
            smooth_radius=args.terrain_smooth_radius,
            height_percentile=args.terrain_height_percentile,
            height_bias=args.terrain_height_bias,
        )
        anchor_surface = ground_surface
    if args.terrain_only_fallback:
        if ground_surface is None:
            raise AssertionError("ground surface was not built")
        terrain_stats = apply_terrain_surface_cleanup(
            world,
            source_top_surface,
            ground_surface,
            minimum_y=transform.target_minimum_y,
            fill_depth=args.terrain_fill_depth,
            edit_mask=edit_mask,
        )

    overlay: VoxelBuildingOverlay | None = None
    npz_building_footprint_columns: set[tuple[int, int]] = set()
    building_ground_ys: dict[tuple[int, int], int] = {}
    campus_ground_surface: dict[tuple[int, int], tuple[int, str]] = {}
    campus_boundary_geometry: BaseGeometry | None = None
    if args.building_source == "npz":
        overlay = load_npz_building_overlay(
            overlay_npz_path,
            transform,
            anchor_surface,
            source_world,
            min_source_column_coverage=args.min_source_column_coverage,
            min_support_column_coverage=args.min_support_column_coverage,
            min_vertical_offset=args.min_vertical_offset,
            max_vertical_offset=args.max_vertical_offset,
            fill_air_support=args.fill_air_support,
            building_name_filter=args.building_name_filter,
            procedural_ground_y=(
                args.procedural_campus_ground_y
                if args.campus_architecture_cleanup
                else None
            ),
        )
        npz_building_footprint_columns = load_npz_building_footprint_columns(
            overlay_npz_path,
            transform,
        )
        building_ground_ys = {
            column: min_y - 1
            for column, (min_y, _max_y) in overlay.clear_columns.items()
        }

    apron_stats: Counter[str] = Counter()
    if overlay is not None and args.apron_clear_radius > 0:
        apron_stats = apply_overlay_apron_cleanup(
            world,
            overlay,
            source_top_surface,
            radius=args.apron_clear_radius,
            edit_mask=edit_mask,
            protected_building_columns=npz_building_footprint_columns,
            minimum_y=transform.target_minimum_y,
        )

    campus_architecture_cleanup_stats: Counter[str] = Counter()
    if overlay is not None and args.campus_architecture_cleanup:
        campus_boundary_geometry = load_campus_boundary_geometry(
            args.campus_boundary.resolve(),
            transform,
        )
        campus_core_geometry = campus_boundary_geometry.intersection(
            box(
                -args.campus_core_radius,
                -args.campus_core_radius,
                args.campus_core_radius,
                args.campus_core_radius,
            )
        )
        campus_architecture_cleanup_stats = apply_campus_architecture_cleanup(
            world,
            source_top_surface,
            campus_core_geometry,
            protected_building_columns=npz_building_footprint_columns,
            minimum_y=transform.target_minimum_y,
            fill_depth=args.terrain_fill_depth,
            smooth_radius=args.terrain_smooth_radius,
            height_percentile=args.terrain_height_percentile,
            height_bias=args.terrain_height_bias,
            sampling_padding=args.terrain_smooth_radius + 2,
            edit_mask=edit_mask,
            building_ground_ys=building_ground_ys,
            ground_surface_out=campus_ground_surface,
            flat_ground_y=args.procedural_campus_ground_y,
        )

    chapel_apron_cleanup_stats: dict[str, Any] = {}
    if overlay is not None and args.chapel_apron_cleanup_radius > 0:
        chapel_apron_cleanup_stats = apply_chapel_apron_cleanup(
            world,
            overlay,
            source_top_surface,
            radius=args.chapel_apron_cleanup_radius,
            minimum_y=transform.target_minimum_y,
            edit_mask=edit_mask,
            protected_building_columns=npz_building_footprint_columns,
        )

    building_seam_fill_stats: dict[str, Any] = {}
    if overlay is not None and args.building_seam_fill_radius > 0:
        if campus_boundary_geometry is None:
            campus_boundary_geometry = load_campus_boundary_geometry(
                args.campus_boundary.resolve(),
                transform,
            )
        building_seam_fill_stats = apply_building_seam_fill(
            world,
            source_top_surface,
            overlay,
            campus_boundary_geometry,
            all_building_columns=npz_building_footprint_columns,
            radius=args.building_seam_fill_radius,
            minimum_y=transform.target_minimum_y,
            edit_mask=edit_mask,
        )

    official_building_seam_fill_stats: dict[str, Any] = {}
    if args.official_building_seam_fill_radius > 0:
        if campus_boundary_geometry is None:
            campus_boundary_geometry = load_campus_boundary_geometry(
                args.campus_boundary.resolve(),
                transform,
            )
        campus_buildings = load_campus_building_geometries(
            args.campus_buildings.resolve(),
            transform,
        )
        official_building_seam_fill_stats = apply_official_building_seam_fill(
            world,
            source_top_surface,
            campus_buildings,
            campus_boundary_geometry,
            radius=args.official_building_seam_fill_radius,
            minimum_y=transform.target_minimum_y,
            edit_mask=edit_mask,
        )

    sandlike_cleanup_stats: dict[str, Any] = {}
    if args.sandlike_top_cleanup:
        building_footprint_columns: set[tuple[int, int]] = set()
        if args.building_source == "npz":
            building_footprint_columns = npz_building_footprint_columns
        else:
            cityjson_buildings = load_roofer_buildings(cityjson_path, transform)
            building_footprint_columns = building_footprint_columns_from_models(cityjson_buildings)
        sandlike_cleanup_stats = apply_sandlike_top_cleanup(
            world,
            source_top_surface,
            building_footprint_columns,
            minimum_y=transform.target_minimum_y,
            edit_mask=edit_mask,
        )

    site_feature_stats: dict[str, Any] = {}
    if args.site_feature_overlay:
        site_feature_stats = apply_site_surface_overlay(
            world,
            source_top_surface,
            args.osm_site_features.resolve(),
            transform,
            edit_mask,
            minimum_y=transform.target_minimum_y,
        )

    named_road_surface_stats: dict[str, Any] = {}
    if args.named_road_surface_overlay:
        named_road_surface_stats = apply_named_road_surface_overlay(
            world,
            source_top_surface,
            args.campus_surfaces.resolve(),
            transform,
            edit_mask,
            minimum_y=transform.target_minimum_y,
        )

    chapel_procedural_section_stats: dict[str, Any] = {}
    chapel_procedural_support_overrides: dict[tuple[int, int, int], str] = {}
    if overlay is not None and args.chapel_procedural_section_radius > 0:
        chapel_procedural_section_stats = apply_chapel_procedural_section(
            world,
            overlay,
            source_top_surface,
            radius=args.chapel_procedural_section_radius,
            minimum_y=transform.target_minimum_y,
            edit_mask=edit_mask,
            support_overrides=chapel_procedural_support_overrides,
        )

    overlay_payload: dict[str, Any] | None = None
    support_audit = None
    continuous_ground_audit = None
    material_values: set[str] = set()
    facade_palette_payload: dict[str, Any] | None = None
    if args.building_source == "npz":
        if overlay is None:
            raise AssertionError("NPZ building overlay was not loaded")
        facade_palette_payload = aggregate_facade_palette(overlay)
        support_stats = place_overlay_support_blocks(world, overlay, edit_mask)
        procedural_ground_support_overrides = dict(chapel_procedural_support_overrides)
        if campus_ground_surface:
            for (x, z), (min_y, _max_y) in overlay.clear_columns.items():
                support_coordinate = (x, min_y - 1, z)
                if (x, z) not in campus_ground_surface:
                    continue
                support_block = world.get_block(*support_coordinate)
                if support_block not in AIR_BLOCKS:
                    procedural_ground_support_overrides[support_coordinate] = support_block
        clear_stats = clear_overlay_volumes(world, overlay, source_top_surface, edit_mask)
        place_stats = place_overlay_blocks(world, overlay, edit_mask)
        material_values.update(block_name for _x, _y, _z, block_name, _role in overlay.blocks)
        building_payload = {
            "source": "npz",
            "count": overlay.building_count,
            "skipped_count": len(overlay.skipped),
            "named": sorted(overlay.building_names),
            "edit_columns": overlay.edit_columns,
            "overlay_voxels": len(overlay.blocks),
            "support_fill_columns": len(overlay.support_blocks),
            "source_path": str(overlay.source_path),
            "manifest_path": str(overlay.manifest_path),
        }
        overlay_payload = {
            "anchor_count": len(overlay.anchors),
            "anchor_y_min": min((entry["voxelearth_ring_ground_y"] for entry in overlay.anchors), default=None),
            "anchor_y_max": max((entry["voxelearth_ring_ground_y"] for entry in overlay.anchors), default=None),
            "vertical_offset_min": min((entry["vertical_offset"] for entry in overlay.anchors), default=None),
            "vertical_offset_max": max((entry["vertical_offset"] for entry in overlay.anchors), default=None),
            "anchors": overlay.anchors,
            "skipped": overlay.skipped,
        }
    else:
        support_stats = Counter()
        buildings = cityjson_buildings or load_roofer_buildings(cityjson_path, transform)
        sample_building_bases(buildings, anchor_surface)
        clear_stats = clear_building_volumes(
            world,
            buildings,
            source_top_surface,
            args.clear_buffer,
            edit_mask,
        )
        place_stats = Counter()
        for x, y, z, block_name, role in generate_building_blocks(
            buildings,
            wall_thickness=args.wall_thickness,
            roof_pitch=args.roof_pitch,
        ):
            edit_mask.add((x, y, z))
            if world.set_block(x, y, z, block_name):
                place_stats[role] += 1
                place_stats["total"] += 1
        placed_bases = [building.base_y for building in buildings if building.base_y is not None]
        building_payload = {
            "source": "cityjson",
            "count": len(buildings),
            "named": sorted(building.name for building in buildings),
            "base_y_min": min(placed_bases) if placed_bases else None,
            "base_y_max": max(placed_bases) if placed_bases else None,
        }
        facade_palette_payload = {
            "mode": "cityjson-name-fallback",
            "colour_space": "oklab",
            "sampled_buildings": 0,
            "material_counts": {},
        }
        material_values.update(
            material
            for building in buildings
            for material in material_set(building).values()
        )
    if sandlike_cleanup_stats.get("changed"):
        material_values.add(SANDLIKE_REPLACEMENT_BLOCK)
    if chapel_apron_cleanup_stats.get("rubble_columns_cleared"):
        material_values.update({"minecraft:dirt", CHAPEL_APRON_SURFACE_BLOCK})
    if campus_architecture_cleanup_stats.get("columns"):
        material_values.update(GROUND_CATEGORY_BLOCKS.values())
    if chapel_procedural_section_stats.get("columns"):
        material_values.update(
            {
                CHAPEL_SECTION_SURFACE_BLOCK,
                CHAPEL_SECTION_SUBSURFACE_BLOCK,
                CHAPEL_SECTION_DEEP_BLOCK,
            }
        )
    if building_seam_fill_stats.get("filled_columns") or official_building_seam_fill_stats.get("filled_columns"):
        material_values.update({"minecraft:dirt", "minecraft:grass_block"})
    material_values.update(site_feature_stats.get("materials", []))
    material_values.update(named_road_surface_stats.get("materials", []))
    touched_chunks = world.save()
    shell_window_audit = None
    if args.building_source == "npz":
        shell_window_audit = audit_overlay_shell_windows(target_world, overlay)
        if campus_ground_surface:
            continuous_ground_audit = audit_continuous_campus_ground(
                target_world,
                campus_ground_surface,
                overlay,
                minimum_y=transform.target_minimum_y,
                expected_flat_ground_y=args.procedural_campus_ground_y,
            )
        support_audit = audit_overlay_support(
            source_world,
            target_world,
            overlay,
            allowed_support_overrides=procedural_ground_support_overrides,
        )
    invariance = None
    if not args.skip_invariance_audit:
        invariance = audit_unmasked_changes(
            source_world,
            target_world,
            edit_mask,
            dense_chunk_limit=args.audit_dense_chunk_limit,
        )

    payload: dict[str, Any] = {
        "format": "hill-hybrid-voxelearth-ground-roofer-v1",
        "source_world": str(source_world),
        "target_world": str(target_world),
        "building_source": args.building_source,
        "roofer_cityjson": str(cityjson_path),
        "roofer_overlay_npz": str(overlay_npz_path),
        "voxelearth_manifest": str(manifest_path),
        "world_transform": {
            "axis": "+X east, +Y up, +Z south",
            "blocks_per_metre": transform.blocks_per_metre,
            "target_minimum_y": transform.target_minimum_y,
            "origin_ecef": list(transform.origin_ecef),
            "center": [transform.center_latitude, transform.center_longitude],
        },
        "building_name_filter": args.building_name_filter,
        "terrain_only_fallback": {
            "enabled": bool(args.terrain_only_fallback),
            "smooth_radius": args.terrain_smooth_radius if args.terrain_only_fallback else None,
            "height_percentile": args.terrain_height_percentile if args.terrain_only_fallback else None,
            "height_bias": args.terrain_height_bias if args.terrain_only_fallback else None,
            "fill_depth": args.terrain_fill_depth if args.terrain_only_fallback else None,
            "stats": dict(terrain_stats),
        },
        "campus_architecture_cleanup": {
            "enabled": args.building_source == "npz" and bool(args.campus_architecture_cleanup),
            "source": "dense-voxelearth-ground-constrained-to-procedural-building-floors",
            "mode": "continuous-solid-one-block-building-grade",
            "solid_to_minimum_y": True,
            "procedural_ground_y": args.procedural_campus_ground_y,
            "boundary": str(args.campus_boundary.resolve()) if args.building_source == "npz" else None,
            "core_radius": args.campus_core_radius,
            "smooth_radius": args.terrain_smooth_radius,
            "height_percentile": args.terrain_height_percentile,
            "height_bias": args.terrain_height_bias,
            "fill_depth": args.terrain_fill_depth,
            "stats": dict(campus_architecture_cleanup_stats),
        },
        "sandlike_top_cleanup": {
            "enabled": bool(args.sandlike_top_cleanup),
            "replacement": SANDLIKE_REPLACEMENT_BLOCK if args.sandlike_top_cleanup else None,
            "stats": sandlike_cleanup_stats,
        },
        "building_apron_cleanup": {
            "enabled": args.building_source == "npz" and args.apron_clear_radius > 0,
            "radius": args.apron_clear_radius if args.building_source == "npz" else None,
            "stats": dict(apron_stats),
        },
        "chapel_apron_cleanup": {
            "enabled": args.building_source == "npz" and args.chapel_apron_cleanup_radius > 0,
            "radius": args.chapel_apron_cleanup_radius if args.building_source == "npz" else None,
            "source": "chapel-landmark-ring-ground",
            "stats": chapel_apron_cleanup_stats,
        },
        "chapel_procedural_section": {
            "enabled": args.building_source == "npz"
            and args.chapel_procedural_section_radius > 0,
            "radius": args.chapel_procedural_section_radius
            if args.building_source == "npz"
            else None,
            "source": "deterministic-flat-filled-chapel-test-section",
            "stats": chapel_procedural_section_stats,
        },
        "building_seam_fill": {
            "enabled": args.building_source == "npz" and args.building_seam_fill_radius > 0,
            "radius": args.building_seam_fill_radius if args.building_source == "npz" else None,
            "source": "voxelearth-building-anchor-and-nearby-ground" if args.building_source == "npz" else None,
            "elevation_sources": [
                "accepted-building-voxelearth-anchor",
                "nearby-valid-voxelearth-ground",
            ] if args.building_source == "npz" else [],
            "boundary": str(args.campus_boundary.resolve()) if args.building_source == "npz" else None,
            "stats": building_seam_fill_stats,
        },
        "official_building_seam_fill": {
            "enabled": bool(args.official_building_seam_fill_radius > 0),
            "radius": args.official_building_seam_fill_radius,
            "source": "nearby-voxelearth-top-surface",
            "boundary": str(args.campus_boundary.resolve()) if args.official_building_seam_fill_radius > 0 else None,
            "buildings": str(args.campus_buildings.resolve()) if args.official_building_seam_fill_radius > 0 else None,
            "stats": official_building_seam_fill_stats,
        },
        "site_feature_overlay": {
            "enabled": bool(args.site_feature_overlay),
            "source": str(args.osm_site_features.resolve()) if args.site_feature_overlay else None,
            "stats": site_feature_stats,
        },
        "named_road_surface_overlay": {
            "enabled": bool(args.named_road_surface_overlay),
            "source": str(args.campus_surfaces.resolve()) if args.named_road_surface_overlay else None,
            "stats": named_road_surface_stats,
        },
        "facade_palette": facade_palette_payload,
        "buildings": building_payload,
        "overlay": overlay_payload,
        "shell_window_audit": shell_window_audit,
        "continuous_ground_audit": continuous_ground_audit,
        "support_audit": support_audit,
        "support_stats": dict(support_stats),
        "clear_stats": dict(clear_stats),
        "place_stats": dict(place_stats),
        "anvil": {
            "changed_blocks": world.changed_blocks,
            "touched_chunks": touched_chunks,
            "skipped_missing_chunks": world.skipped_missing_chunks,
        },
        "invariance_audit": invariance,
        "materials": sorted(material_values),
    }
    output_manifest = target_world / "hill-hybrid-manifest.json"
    output_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["manifest_path"] = str(output_manifest)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-world", type=Path, default=DEFAULT_SOURCE_WORLD)
    parser.add_argument("--building-source", choices=("npz", "cityjson"), default="npz")
    parser.add_argument("--roofer-cityjson", type=Path, default=DEFAULT_ROOFER_CITYJSON)
    parser.add_argument("--roofer-overlay-npz", type=Path, default=DEFAULT_ROOFER_OVERLAY_NPZ)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--world-name", default=None)
    parser.add_argument("--building-name-filter", default=None)
    parser.add_argument("--clear-buffer", type=float, default=3.0)
    parser.add_argument("--wall-thickness", type=float, default=1.35)
    parser.add_argument("--roof-pitch", type=float, default=0.55)
    parser.add_argument("--terrain-only-fallback", action="store_true")
    parser.add_argument("--terrain-smooth-radius", type=int, default=10)
    parser.add_argument("--terrain-height-percentile", type=float, default=20.0)
    parser.add_argument("--terrain-height-bias", type=float, default=1.5)
    parser.add_argument("--terrain-fill-depth", type=int, default=4)
    parser.add_argument(
        "--procedural-campus-ground-y",
        type=int,
        default=91,
        help=(
            "level Y for the continuous school ground plane; accepted Roofer "
            "shells are vertically rebased so their floors sit one block above it"
        ),
    )
    parser.add_argument(
        "--campus-architecture-cleanup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="strip elevated non-building clutter inside the official campus boundary",
    )
    parser.add_argument(
        "--campus-core-radius",
        type=int,
        default=512,
        help="half-size in blocks of the main-campus square centered on the world origin",
    )
    parser.add_argument("--sandlike-top-cleanup", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--site-feature-overlay", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--osm-site-features", type=Path, default=DEFAULT_OSM_SITE_FEATURES)
    parser.add_argument("--named-road-surface-overlay", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--campus-surfaces", type=Path, default=DEFAULT_CAMPUS_SURFACES)
    parser.add_argument(
        "--building-seam-fill-radius",
        type=int,
        default=0,
        help="opt-in radius for repairing missing source-ground columns around Roofer footprints",
    )
    parser.add_argument(
        "--official-building-seam-fill-radius",
        type=int,
        default=0,
        help="opt-in radius for repairing missing source-ground columns around official footprints",
    )
    parser.add_argument("--campus-buildings", type=Path, default=DEFAULT_CAMPUS_BUILDINGS)
    parser.add_argument("--campus-boundary", type=Path, default=DEFAULT_CAMPUS_BOUNDARY)
    parser.add_argument("--apron-clear-radius", type=int, default=6)
    parser.add_argument("--chapel-apron-cleanup-radius", type=int, default=0)
    parser.add_argument(
        "--chapel-procedural-section-radius",
        type=int,
        default=0,
        help=(
            "expand the Chapel bbox by this many blocks and replace the entire "
            "section with flat, continuously filled procedural terrain"
        ),
    )
    parser.add_argument("--min-source-column-coverage", type=float, default=0.25)
    parser.add_argument("--min-support-column-coverage", type=float, default=0.90)
    parser.add_argument("--min-vertical-offset", type=float, default=15.0)
    parser.add_argument("--max-vertical-offset", type=float, default=35.0)
    parser.add_argument("--fill-air-support", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--audit-dense-chunk-limit", type=int, default=900)
    parser.add_argument("--skip-invariance-audit", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        marker = run_self_test(args.source_world.resolve(), args.output_dir.resolve())
        print(json.dumps({"self_test": "passed", "path": str(marker)}, indent=2))
        return 0
    payload = hybridize(args)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
