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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import nbtlib
import numpy as np
from nbtlib import tag
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
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

AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
AIR = "minecraft:air"
GROUND_CATEGORY_BLOCKS = {
    1: "minecraft:grass_block",
    2: "minecraft:water",
    3: "minecraft:smooth_stone",
    4: "minecraft:sandstone",
    5: "minecraft:dirt",
}


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
            self.indices = [0] * 4096
            self.dirty = True
        else:
            entries, data = parsed
            self.entries = [entry.copy() for entry in entries]
            self.names = [palette_name(entry) for entry in self.entries]
            self.indices = unpack_indices(len(self.names), data)
            self.dirty = False

    def get(self, local_x: int, local_y: int, local_z: int) -> str:
        return self.names[self.indices[section_index(local_x, local_y, local_z)]]

    def set(self, local_x: int, local_y: int, local_z: int, block_name: str) -> bool:
        idx = section_index(local_x, local_y, local_z)
        current = self.names[self.indices[idx]]
        if current == block_name:
            return False
        try:
            palette_index = self.names.index(block_name)
        except ValueError:
            palette_index = len(self.names)
            self.names.append(block_name)
            self.entries.append(block_entry(block_name))
        self.indices[idx] = palette_index
        self.dirty = True
        return True

    def compact(self) -> None:
        if not self.dirty:
            return
        remap: dict[int, int] = {}
        new_entries: list[tag.Compound] = []
        new_names: list[str] = []
        new_indices: list[int] = []
        for old in self.indices:
            new = remap.get(old)
            if new is None:
                new = len(new_entries)
                remap[old] = new
                new_entries.append(self.entries[old])
                new_names.append(self.names[old])
            new_indices.append(new)

        self.entries = new_entries
        self.names = new_names
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

    def set_block(self, x: int, y: int, z: int, block_name: str) -> bool:
        section = self.section(math.floor(y / 16))
        if section is None:
            return False
        changed = section.set(x & 15, y & 15, z & 15, block_name)
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


def block_entry(block_name: str) -> tag.Compound:
    return tag.Compound({"Name": tag.String(block_name)})


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
) -> dict[tuple[int, int], tuple[int, str]]:
    try:
        from scipy import ndimage
    except ImportError as exc:
        raise RuntimeError("terrain-only fallback requires scipy") from exc

    xs = [x for x, _z in top_surface]
    zs = [z for _x, z in top_surface]
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
    for (x, z), (source_y, _source_block) in top_surface.items():
        row = z - min_z
        col = x - min_x
        terrain_y = int(round(float(terrain_grid[row, col]) + height_bias))
        if terrain_y > source_y:
            terrain_y = source_y
        category = int(category_grid[row, col])
        terrain_surface[(x, z)] = (terrain_y, GROUND_CATEGORY_BLOCKS.get(category, "minecraft:smooth_stone"))
    return terrain_surface


def classify_ground_category(block: str) -> int:
    name = block.removeprefix("minecraft:")
    if name == "water":
        return 2
    if name in {"grass_block", "moss_block"} or "leaves" in name or "log" in name or "wood" in name:
        return 1
    if "sandstone" in name or name in {"sand", "red_sand"}:
        return 4
    if name in {"dirt", "coarse_dirt", "rooted_dirt", "mud", "packed_mud"}:
        return 5
    if "concrete" in name or "stone" in name or name in {"andesite", "diorite", "granite"}:
        return 3
    return 0


def subsurface_block_for(surface_block: str) -> str:
    if surface_block == "minecraft:grass_block":
        return "minecraft:dirt"
    if surface_block == "minecraft:water":
        return "minecraft:dirt"
    if "sandstone" in surface_block:
        return "minecraft:sandstone"
    return "minecraft:smooth_stone"


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
    support_blocks: dict[tuple[int, int, int], str] = {}
    clear_columns: dict[tuple[int, int], tuple[int, int]] = {}
    anchors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    source_reader = AnvilWorld(source_world_path)

    for raw_building_id in sorted(int(value) for value in np.unique(building_ids)):
        selector = building_ids == raw_building_id
        coords = occupied_neu[selector]
        if len(coords) == 0:
            continue
        name = building_names[raw_building_id - 1] if 0 < raw_building_id <= len(building_names) else str(raw_building_id)
        metadata = building_map.get(str(raw_building_id), {})
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

        materials = material_set_for_text(name, description)
        if not raw_blocks:
            continue
        min_y = min(y for _x, y, _z in raw_blocks)
        max_y = max(y for _x, y, _z in raw_blocks)
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
                support_blocks[(column[0], support_y, column[1])] = subsurface_block_for(surface_block)
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

        for x, y, z in raw_blocks:
            role = overlay_block_role(raw_blocks, x, y, z)
            block_name = overlay_material(materials, role, name, x, y, z, min_y, max_y)
            blocks.append((x, y, z, block_name, role))

        for column, (column_min_y, column_max_y) in column_ranges.items():
            old = clear_columns.get(column)
            if old is None:
                clear_columns[column] = (column_min_y, column_max_y + 2)
            else:
                clear_columns[column] = (min(old[0], column_min_y), max(old[1], column_max_y + 2))

        anchors.append(
            {
                "building_id": raw_building_id,
                "name": name,
                "roofer_h_ground": rf_h_ground,
                "voxelearth_ring_ground_y": anchor_y,
                "vertical_offset": y_offset,
                "ring_samples": len(ring_samples),
                "source_column_coverage": source_column_coverage,
                "support_column_coverage": support_coverage,
                "trimmed_columns": trimmed_columns,
                "trimmed_voxels": trimmed_voxels,
                "support_fill_columns": len(unsupported_columns) if fill_air_support else 0,
                "voxels": len(raw_blocks),
                "columns": len({(x, z) for x, _y, z in raw_blocks}),
            }
        )

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
    )


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
    is_chapel = "chapel" in name.lower()
    if local_y <= 1 or max_y - y <= 1:
        return materials["trim"]
    spacing = 9 if is_chapel else 7
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
        edit_mask.add((x, y, z))
        if world.set_block(x, y, z, block_name):
            stats[role] += 1
            stats["total"] += 1
    return stats


def apply_overlay_apron_cleanup(
    world: AnvilWorld,
    overlay: VoxelBuildingOverlay,
    source_top_surface: dict[tuple[int, int], tuple[int, str]],
    ground_surface: dict[tuple[int, int], tuple[int, str]],
    *,
    radius: int,
    edit_mask: set[tuple[int, int, int]],
) -> Counter[str]:
    stats: Counter[str] = Counter()
    if radius <= 0:
        return stats
    building_columns = set(overlay.clear_columns)
    apron_columns: set[tuple[int, int]] = set()
    for x, z in building_columns:
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if dx == 0 and dz == 0:
                    continue
                if max(abs(dx), abs(dz)) > radius:
                    continue
                column = (x + dx, z + dz)
                if column not in building_columns:
                    apron_columns.add(column)

    for x, z in sorted(apron_columns):
        source_top = source_top_surface.get((x, z))
        ground = ground_surface.get((x, z))
        if source_top is None or ground is None:
            continue
        source_top_y, source_top_block = source_top
        ground_y, ground_block = ground
        if source_top_y > ground_y:
            for y in range(ground_y + 1, source_top_y + 1):
                edit_mask.add((x, y, z))
                if world.set_block(x, y, z, AIR):
                    stats["cleared_above_ground"] += 1
        if source_top_y != ground_y or source_top_block != ground_block:
            edit_mask.add((x, ground_y, z))
            if world.set_block(x, ground_y, z, ground_block):
                stats["surface_retyped"] += 1
        stats["columns"] += 1
    return stats


def audit_overlay_support(
    source_world: Path,
    target_world: Path,
    overlay: VoxelBuildingOverlay,
    *,
    max_samples: int = 50,
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
        "support_mismatch_samples": mismatches,
        "air_support_samples": air_supports,
        "floating_floor_samples": floating,
    }
    if mismatches or air_supports or floating:
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

    terrain_stats: Counter[str] = Counter()
    anchor_surface = source_top_surface
    ground_surface = None
    needs_ground_surface = args.terrain_only_fallback or (
        args.building_source == "npz" and args.apron_clear_radius > 0
    )
    if needs_ground_surface:
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

    overlay_payload: dict[str, Any] | None = None
    apron_stats: Counter[str] = Counter()
    support_audit = None
    material_values: set[str] = set()
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
        )
        support_stats = place_overlay_support_blocks(world, overlay, edit_mask)
        if args.apron_clear_radius > 0:
            if ground_surface is None:
                ground_surface = source_top_surface
            apron_stats = apply_overlay_apron_cleanup(
                world,
                overlay,
                source_top_surface,
                ground_surface,
                radius=args.apron_clear_radius,
                edit_mask=edit_mask,
            )
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
        buildings = load_roofer_buildings(cityjson_path, transform)
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
        material_values.update(
            material
            for building in buildings
            for material in material_set(building).values()
        )
    touched_chunks = world.save()
    if args.building_source == "npz":
        support_audit = audit_overlay_support(source_world, target_world, overlay)
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
        "terrain_only_fallback": {
            "enabled": bool(args.terrain_only_fallback),
            "smooth_radius": args.terrain_smooth_radius if args.terrain_only_fallback else None,
            "height_percentile": args.terrain_height_percentile if args.terrain_only_fallback else None,
            "height_bias": args.terrain_height_bias if args.terrain_only_fallback else None,
            "fill_depth": args.terrain_fill_depth if args.terrain_only_fallback else None,
            "stats": dict(terrain_stats),
        },
        "building_apron_cleanup": {
            "enabled": args.building_source == "npz" and args.apron_clear_radius > 0,
            "radius": args.apron_clear_radius if args.building_source == "npz" else None,
            "stats": dict(apron_stats),
        },
        "buildings": building_payload,
        "overlay": overlay_payload,
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
    parser.add_argument("--clear-buffer", type=float, default=3.0)
    parser.add_argument("--wall-thickness", type=float, default=1.35)
    parser.add_argument("--roof-pitch", type=float, default=0.55)
    parser.add_argument("--terrain-only-fallback", action="store_true")
    parser.add_argument("--terrain-smooth-radius", type=int, default=10)
    parser.add_argument("--terrain-height-percentile", type=float, default=20.0)
    parser.add_argument("--terrain-height-bias", type=float, default=1.5)
    parser.add_argument("--terrain-fill-depth", type=int, default=4)
    parser.add_argument("--apron-clear-radius", type=int, default=0)
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
