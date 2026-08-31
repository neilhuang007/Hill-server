#!/usr/bin/env python3
"""Generate a rights-cleared Minecraft structure NBT for The Hill School campus.

The generator builds a 1 block = 1 metre base map from authoritative parcels,
county building outlines, OpenStreetMap site features, USGS D24 DEM tiles, and
optional USGS D24 lidar surface points. It writes a Minecraft structure file in
the streamed format consumed by StructureNbtLoader.java.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import random
import struct
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import laspy
import numpy as np
import requests
import rasterio
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio import features
from rasterio.crs import CRS as RioCRS
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject
from scipy import ndimage
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union


WGS84 = "EPSG:4326"
WORK_CRS_EPSG = 6347
WORK_CRS = RioCRS.from_epsg(WORK_CRS_EPSG)

PHASE1_BBOX_WGS84 = (-75.63850, 40.24338, -75.62273, 40.25369)
FULL_BBOX_WGS84 = (-75.63849771145249, 40.24338459442697, -75.61807609652666, 40.26085826379907)
PHASE1_PARCELS = ("160015116006", "160016044005", "160016052006")

ASSESSMENT_URL = "https://gis.montcopa.org/arcgis/rest/services/Parcels/GIS_BOA_LAND/FeatureServer/0/query"
PARCELS_URL = "https://gis.montcopa.org/arcgis/rest/services/Parcels/Montgomery_County_Parcels/FeatureServer/10/query"
BUILDINGS_URL = "https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6/query"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OFFICIAL_CAMPUS_MAP_URL = "https://www.thehill.org/fs/resource-manager/view/60ebc57e-cb17-4e98-a0fc-84653974f28a"
OFFICIAL_CAMPUS_MAP_PATH = Path("runtime/campus-data/reference/hill-official-campus-map.pdf")

OFFICIAL_LANDMARKS = (
    "Meigs House",
    "John P. Ryan Library",
    "Athey Academic Center",
    "Dining Hall",
    "Alumni Chapel",
    "Davy Hall",
    "Center for the Arts",
    "Mercer Field House / Day Squash Center",
    "Sweeney Gymnasium",
    "Tuck Hall Arena / Eccleston Rink",
    "The Dell Pond",
    "Hunt Dormitory",
    "Wendell Dormitory",
    "Ferenbach Dormitory",
    "Senter Dormitory",
    "Lowndes Dormitory",
    "Scheerer Dormitory",
    "Foster Dormitory",
    "Rolfe Dormitory",
    "Dutch Village",
    "Shirley Quadrivium Center",
    "Gatehouse",
    "Dell Field",
    "Beech Street Tennis Courts",
    "Nam Family Field",
    "Jim Long Field",
    "Far Fields",
    "Price Field",
    "Cunningham Field",
    "Madden Stadium",
    "Hauser Track",
)

TILE_IDS = (
    "18TVK445454",
    "18TVK445455",
    "18TVK445456",
    "18TVK446454",
    "18TVK446455",
    "18TVK446456",
    "18TVK447454",
    "18TVK447455",
    "18TVK447456",
)

EXPECTED_LAZ_SIZES = {
    "18TVK445454": 186_318_463,
    "18TVK445455": 199_582_586,
    "18TVK445456": 241_158_377,
    "18TVK446454": 177_196_504,
    "18TVK446455": 244_753_552,
    "18TVK446456": 157_575_747,
    "18TVK447454": 239_034_364,
    "18TVK447455": 193_314_723,
    "18TVK447456": 182_862_880,
}

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

BLOCK_RECORD = struct.Struct("<HHHH")

MATERIAL_COLORS = {
    "minecraft:air": (0, 0, 0),
    "minecraft:stone": (86, 86, 82),
    "minecraft:dirt": (114, 80, 54),
    "minecraft:coarse_dirt": (126, 91, 60),
    "minecraft:grass_block": (86, 146, 71),
    "minecraft:moss_block": (74, 130, 62),
    "minecraft:sand": (208, 193, 132),
    "minecraft:water": (65, 113, 190),
    "minecraft:blue_concrete": (45, 75, 165),
    "minecraft:green_concrete": (73, 98, 39),
    "minecraft:lime_concrete": (95, 168, 52),
    "minecraft:white_concrete": (218, 221, 218),
    "minecraft:light_gray_concrete": (126, 131, 131),
    "minecraft:gray_concrete": (73, 76, 78),
    "minecraft:black_concrete": (22, 24, 27),
    "minecraft:red_concrete": (142, 33, 33),
    "minecraft:brown_concrete": (96, 59, 36),
    "minecraft:bricks": (151, 82, 65),
    "minecraft:mud_bricks": (136, 92, 68),
    "minecraft:stone_bricks": (112, 116, 111),
    "minecraft:smooth_stone": (154, 154, 148),
    "minecraft:polished_andesite": (133, 136, 134),
    "minecraft:deepslate_tiles": (53, 54, 58),
    "minecraft:dark_oak_planks": (65, 43, 25),
    "minecraft:glass": (164, 190, 198),
    "minecraft:light_blue_stained_glass": (113, 163, 184),
    "minecraft:oak_log": (96, 73, 42),
    "minecraft:oak_leaves": (47, 103, 45),
}


@dataclass(frozen=True)
class GridSpec:
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    resolution: float
    width: int
    depth: int
    transform: Affine

    def col_for_x(self, x: float) -> int:
        return int(math.floor((x - self.min_x) / self.resolution))

    def row_for_y(self, y: float) -> int:
        return int(math.floor((self.max_y - y) / self.resolution))

    def minecraft_for_point(self, point: Point) -> tuple[int, int]:
        return self.col_for_x(point.x), self.row_for_y(point.y)


@dataclass
class GeoFeature:
    geometry: BaseGeometry
    properties: dict[str, Any]


@dataclass
class SourceStatus:
    name: str
    path: str
    status: str
    bytes: int = 0
    expected_bytes: int = 0
    sha256: str | None = None
    note: str | None = None


class Timer:
    def __init__(self) -> None:
        self.started = time.monotonic()

    def elapsed(self) -> str:
        seconds = time.monotonic() - self.started
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {seconds:.0f}s"


class Palette:
    def __init__(self) -> None:
        self.entries: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        self.indices: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}

    def add(self, name: str, properties: dict[str, str] | None = None) -> int:
        if not name.startswith("minecraft:"):
            name = "minecraft:" + name
        props = tuple(sorted((properties or {}).items()))
        key = (name, props)
        existing = self.indices.get(key)
        if existing is not None:
            return existing
        index = len(self.entries)
        if index > 65_535:
            raise ValueError("Palette grew beyond the 16-bit spool format")
        self.entries.append(key)
        self.indices[key] = index
        return index

    def block_name(self, index: int) -> str:
        return self.entries[index][0]


class BlockSpool:
    def __init__(self, path: Path, palette: Palette, size_x: int, size_y: int, size_z: int) -> None:
        self.path = path
        self.palette = palette
        self.size_x = size_x
        self.size_y = size_y
        self.size_z = size_z
        self.count = 0
        self._file = path.open("wb")

    def close(self) -> None:
        self._file.close()

    def add_state(self, state: int, x: int, y: int, z: int) -> None:
        if x < 0 or x >= self.size_x or z < 0 or z >= self.size_z or y < 0 or y >= self.size_y:
            return
        self._file.write(BLOCK_RECORD.pack(state, x, y, z))
        self.count += 1

    def add(self, name: str, x: int, y: int, z: int, properties: dict[str, str] | None = None) -> None:
        self.add_state(self.palette.add(name, properties), x, y, z)


def log(message: str) -> None:
    print(message, flush=True)


def cache_json(path: Path, fetch: callable, refresh: bool) -> Any:
    if path.is_file() and not refresh:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = fetch()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return payload


def request_json_post(url: str, data: dict[str, Any], timeout: int = 180) -> Any:
    headers = {"User-Agent": "HillSchoolVoxelMap/1.0"}
    response = requests.post(url, data=data, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"ArcGIS error from {url}: {payload['error']}")
    return payload


def fetch_assessment_rows(gis_dir: Path, refresh: bool) -> tuple[list[dict[str, Any]], list[SourceStatus]]:
    path = gis_dir / "montco-hill-assessment.json"

    def fetch() -> Any:
        return request_json_post(
            ASSESSMENT_URL,
            {
                "where": "OWN1 LIKE 'HILL SCHOOL THE%'",
                "outFields": "PARCEL,LOCATION1,LAND_ACRES,LAND_SF,OWN1",
                "returnGeometry": "false",
                "resultRecordCount": "2000",
                "f": "json",
            },
        )

    payload = cache_json(path, fetch, refresh)
    rows = [feature.get("attributes", {}) for feature in payload.get("features", [])]
    status = SourceStatus("Montgomery County assessment owner rows", str(path), "cached" if path.is_file() else "fetched")
    return rows, [status]


def parcel_ids_for_scope(scope: str, assessment_rows: list[dict[str, Any]]) -> list[str]:
    if scope == "phase1":
        return list(PHASE1_PARCELS)
    ids = sorted(
        {
            str(row.get("PARCEL", "")).strip()
            for row in assessment_rows
            if str(row.get("PARCEL", "")).strip()
        }
    )
    if not ids:
        raise RuntimeError("No Hill-owned parcel IDs were available from the assessment cache/query.")
    return ids


def fetch_geojson_chunks(
    cache_path: Path,
    url: str,
    where_field: str,
    values: list[str],
    out_fields: str,
    refresh: bool,
) -> dict[str, Any]:
    if cache_path.is_file() and not refresh:
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    all_features: list[dict[str, Any]] = []
    for start in range(0, len(values), 25):
        chunk = values[start : start + 25]
        quoted = ",".join("'" + value.replace("'", "''") + "'" for value in chunk)
        request = {
            "where": f"{where_field} IN ({quoted})",
            "outFields": out_fields,
            "outSR": "4326",
            "returnGeometry": "true",
            "f": "geojson",
        }
        try:
            payload = request_json_post(url, request)
        except RuntimeError:
            request["f"] = "json"
            payload = arcgis_json_to_geojson(request_json_post(url, request))
        all_features.extend(payload.get("features", []))
    merged = {"type": "FeatureCollection", "features": all_features}
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, separators=(",", ":"))
    return merged


def arcgis_json_to_geojson(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") == "FeatureCollection":
        return payload
    converted: list[dict[str, Any]] = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        geojson_geometry: dict[str, Any] | None = None
        if "rings" in geometry:
            polygons = []
            for ring in geometry.get("rings") or []:
                if len(ring) >= 4:
                    try:
                        polygon = Polygon(ring)
                        if not polygon.is_valid:
                            polygon = polygon.buffer(0)
                        if not polygon.is_empty:
                            polygons.append(polygon)
                    except Exception:
                        continue
            if polygons:
                merged = unary_union(polygons)
                geojson_geometry = merged.__geo_interface__
        elif "paths" in geometry:
            paths = geometry.get("paths") or []
            if len(paths) == 1:
                geojson_geometry = {"type": "LineString", "coordinates": paths[0]}
            elif paths:
                geojson_geometry = {"type": "MultiLineString", "coordinates": paths}
        elif "x" in geometry and "y" in geometry:
            geojson_geometry = {"type": "Point", "coordinates": [geometry["x"], geometry["y"]]}
        if geojson_geometry is None:
            continue
        converted.append(
            {
                "type": "Feature",
                "geometry": geojson_geometry,
                "properties": feature.get("attributes", {}) or {},
            }
        )
    return {"type": "FeatureCollection", "features": converted}


def fetch_osm(gis_dir: Path, bbox_wgs84: tuple[float, float, float, float], refresh: bool) -> tuple[dict[str, Any], list[SourceStatus]]:
    west, south, east, north = bbox_wgs84
    path = gis_dir / f"osm-v3-{west:.5f}-{south:.5f}-{east:.5f}-{north:.5f}.json"

    def fetch() -> Any:
        query = f"""
[out:json][timeout:180];
(
  way["highway"]({south},{west},{north},{east});
  way["amenity"="parking"]({south},{west},{north},{east});
  way["leisure"]({south},{west},{north},{east});
  way["natural"="water"]({south},{west},{north},{east});
  way["water"]({south},{west},{north},{east});
  way["waterway"]({south},{west},{north},{east});
  way["landuse"]({south},{west},{north},{east});
  way["barrier"]({south},{west},{north},{east});
  way["man_made"]({south},{west},{north},{east});
  relation["amenity"="parking"]({south},{west},{north},{east});
  relation["leisure"]({south},{west},{north},{east});
  relation["natural"="water"]({south},{west},{north},{east});
  relation["water"]({south},{west},{north},{east});
  relation["landuse"]({south},{west},{north},{east});
);
out body geom qt;
"""
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "HillSchoolVoxelMap/1.0"},
            timeout=220,
        )
        response.raise_for_status()
        return response.json()

    try:
        payload = cache_json(path, fetch, refresh)
        status = SourceStatus("OpenStreetMap Overpass extract", str(path), "cached")
        return payload, [status]
    except Exception as exc:
        if path.is_file():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle), [SourceStatus("OpenStreetMap Overpass extract", str(path), "cached-after-error", note=str(exc))]
        log(f"Warning: OSM fetch failed and no cache exists: {exc}")
        return {"elements": []}, [SourceStatus("OpenStreetMap Overpass extract", str(path), "missing", note=str(exc))]


def load_geojson_features(payload: dict[str, Any]) -> list[GeoFeature]:
    loaded: list[GeoFeature] = []
    for item in payload.get("features", []):
        geometry = item.get("geometry")
        if not geometry:
            continue
        try:
            geom = shape(geometry)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            if not geom.is_empty:
                loaded.append(GeoFeature(geom, item.get("properties", {}) or {}))
        except Exception as exc:
            log(f"Warning: skipped invalid GeoJSON feature: {exc}")
    return loaded


def to_work_geometry(geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    return shapely_transform(transformer.transform, geometry)


def create_grid(terrain_geometry: BaseGeometry, resolution: float, max_dimension: int) -> GridSpec:
    min_x, min_y, max_x, max_y = terrain_geometry.bounds
    min_x = math.floor(min_x / resolution) * resolution
    min_y = math.floor(min_y / resolution) * resolution
    max_x = math.ceil(max_x / resolution) * resolution
    max_y = math.ceil(max_y / resolution) * resolution
    width = int(math.ceil((max_x - min_x) / resolution))
    depth = int(math.ceil((max_y - min_y) / resolution))
    if width > max_dimension or depth > max_dimension:
        raise RuntimeError(
            f"Grid {width}x{depth} exceeds --max-dimension {max_dimension}. "
            "Use --scope phase1, lower --buffer-metres, or raise server border settings."
        )
    transform = Affine(resolution, 0.0, min_x, 0.0, -resolution, max_y)
    return GridSpec(min_x, min_y, max_x, max_y, resolution, width, depth, transform)


def rasterize_mask(geometries: Iterable[BaseGeometry], grid: GridSpec, all_touched: bool = True) -> np.ndarray:
    pairs = [(geom, 1) for geom in geometries if geom and not geom.is_empty]
    if not pairs:
        return np.zeros((grid.depth, grid.width), dtype=bool)
    return features.rasterize(
        pairs,
        out_shape=(grid.depth, grid.width),
        transform=grid.transform,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    ).astype(bool)


def transform_bbox_to_work(bbox_wgs84: tuple[float, float, float, float], transformer: Transformer) -> BaseGeometry:
    west, south, east, north = bbox_wgs84
    return to_work_geometry(box(west, south, east, north), transformer)


def load_dem_grid(dem_dirs: list[Path], grid: GridSpec, smooth_sigma: float) -> tuple[np.ndarray, list[SourceStatus]]:
    dem = np.full((grid.depth, grid.width), np.nan, dtype=np.float32)
    statuses: list[SourceStatus] = []
    tif_paths: list[Path] = []
    for directory in dem_dirs:
        if directory.is_dir():
            tif_paths.extend(sorted(directory.glob("*.tif")))
    if not tif_paths:
        raise RuntimeError(f"No DEM GeoTIFFs found in: {', '.join(str(path) for path in dem_dirs)}")

    for path in tif_paths:
        tmp = np.full_like(dem, np.nan)
        try:
            with rasterio.open(path) as src:
                reproject(
                    source=rasterio.band(src, 1),
                    destination=tmp,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    src_nodata=src.nodata,
                    dst_transform=grid.transform,
                    dst_crs=WORK_CRS,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
        except Exception as exc:
            statuses.append(SourceStatus("DEM", str(path), "error", bytes=path.stat().st_size, note=str(exc)))
            continue
        valid = np.isfinite(tmp) & (tmp > -500.0) & (tmp < 1_000.0)
        write_mask = valid & ~np.isfinite(dem)
        dem[write_mask] = tmp[write_mask]
        statuses.append(SourceStatus("DEM", str(path), "used", bytes=path.stat().st_size, note=f"filled {int(write_mask.sum())} cells"))

    missing = ~np.isfinite(dem)
    if missing.all():
        raise RuntimeError("DEM reprojection produced no valid elevations for the campus grid.")
    if missing.any():
        nearest = ndimage.distance_transform_edt(missing, return_distances=False, return_indices=True)
        dem[missing] = dem[tuple(index[missing] for index in nearest)]
    if smooth_sigma > 0:
        dem = ndimage.gaussian_filter(dem, sigma=smooth_sigma).astype(np.float32)
    return dem, statuses


def build_lidar_dsm(lidar_dir: Path, grid: GridSpec, chunk_size: int) -> tuple[np.ndarray | None, list[SourceStatus]]:
    if not lidar_dir.is_dir():
        return None, [SourceStatus("USGS D24 lidar", str(lidar_dir), "missing")]

    dsm = np.full((grid.depth, grid.width), -np.inf, dtype=np.float32)
    statuses: list[SourceStatus] = []
    used_any = False
    for tile_id in TILE_IDS:
        path = lidar_dir / f"USGS_LPC_PA_17County_D24_{tile_id}.laz"
        expected = EXPECTED_LAZ_SIZES[tile_id]
        if not path.is_file():
            statuses.append(SourceStatus(tile_id, str(path), "missing", expected_bytes=expected))
            continue
        size = path.stat().st_size
        if size + 1_024 < expected:
            statuses.append(SourceStatus(tile_id, str(path), "partial", bytes=size, expected_bytes=expected))
            continue
        if size > expected + 4_096:
            statuses.append(SourceStatus(tile_id, str(path), "unexpected-size", bytes=size, expected_bytes=expected))
            continue
        point_count = 0
        accepted = 0
        try:
            with laspy.open(path) as reader:
                min_x, min_y, _ = reader.header.mins
                max_x, max_y, _ = reader.header.maxs
                if max_x < grid.min_x or min_x > grid.max_x or max_y < grid.min_y or min_y > grid.max_y:
                    statuses.append(SourceStatus(tile_id, str(path), "outside-grid", bytes=size, expected_bytes=expected))
                    continue
                for points in reader.chunk_iterator(chunk_size):
                    point_count += len(points)
                    classifications = np.asarray(points.classification)
                    keep = (classifications != 7) & (classifications != 18)
                    if not keep.any():
                        continue
                    xs = np.asarray(points.x)[keep]
                    ys = np.asarray(points.y)[keep]
                    zs = np.asarray(points.z, dtype=np.float32)[keep]
                    inside = (
                        (xs >= grid.min_x)
                        & (xs < grid.max_x)
                        & (ys >= grid.min_y)
                        & (ys < grid.max_y)
                        & np.isfinite(zs)
                    )
                    if not inside.any():
                        continue
                    cols = ((xs[inside] - grid.min_x) / grid.resolution).astype(np.int32)
                    rows = ((grid.max_y - ys[inside]) / grid.resolution).astype(np.int32)
                    zvals = zs[inside]
                    valid = (rows >= 0) & (rows < grid.depth) & (cols >= 0) & (cols < grid.width)
                    if valid.any():
                        np.maximum.at(dsm, (rows[valid], cols[valid]), zvals[valid])
                        accepted += int(valid.sum())
            statuses.append(SourceStatus(tile_id, str(path), "used", bytes=size, expected_bytes=expected, note=f"{accepted}/{point_count} points in grid"))
            used_any = used_any or accepted > 0
            log(f"  lidar {tile_id}: accepted {accepted:,} of {point_count:,} points")
        except Exception as exc:
            statuses.append(SourceStatus(tile_id, str(path), "error", bytes=size, expected_bytes=expected, note=str(exc)))
    if not used_any:
        return None, statuses
    dsm[~np.isfinite(dsm)] = np.nan
    return dsm, statuses


def osm_geometry(element: dict[str, Any], transformer: Transformer) -> BaseGeometry | None:
    if element.get("type") == "relation":
        return osm_relation_geometry(element, transformer)
    coords = element.get("geometry") or []
    if len(coords) < 2:
        return None
    points = [(node["lon"], node["lat"]) for node in coords if "lon" in node and "lat" in node]
    if len(points) < 2:
        return None
    tags = element.get("tags", {})
    is_area = (
        points[0] == points[-1]
        and (
            tags.get("area") == "yes"
            or "amenity" in tags
            or "leisure" in tags
            or "landuse" in tags
            or tags.get("natural") in {"water", "wood", "scrub"}
            or "water" in tags
        )
    )
    try:
        geom: BaseGeometry
        if is_area and len(points) >= 4:
            geom = Polygon(points)
        else:
            geom = LineString(points)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            return None
        return to_work_geometry(geom, transformer)
    except Exception:
        return None


def osm_relation_geometry(element: dict[str, Any], transformer: Transformer) -> BaseGeometry | None:
    outers: list[list[tuple[float, float]]] = []
    inners: list[list[tuple[float, float]]] = []
    lines: list[BaseGeometry] = []
    for member in element.get("members", []) or []:
        coords = member.get("geometry") or []
        points = [(node["lon"], node["lat"]) for node in coords if "lon" in node and "lat" in node]
        if len(points) < 2:
            continue
        closed = len(points) >= 4 and points[0] == points[-1]
        role = member.get("role", "")
        if closed and role == "inner":
            inners.append(points)
        elif closed:
            outers.append(points)
        else:
            try:
                lines.append(LineString(points))
            except Exception:
                continue

    geometries: list[BaseGeometry] = []
    inner_polygons = []
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
            holes = [list(inner.exterior.coords) for inner in inner_polygons if outer.contains(inner.representative_point())]
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
    try:
        geom = unary_union(geometries)
        if geom.is_empty:
            return None
        return to_work_geometry(geom, transformer)
    except Exception:
        return None


def buffered_line(geometry: BaseGeometry, width: float) -> BaseGeometry:
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    return geometry.buffer(max(width, 0.5) / 2.0, cap_style=2, join_style=2)


def surface_layers_from_osm(
    osm_payload: dict[str, Any],
    transformer: Transformer,
    terrain_geometry: BaseGeometry,
    grid: GridSpec,
) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    groups: dict[str, list[BaseGeometry]] = {
        "road": [],
        "path": [],
        "parking": [],
        "water": [],
        "grass": [],
        "track": [],
        "tennis": [],
        "field": [],
        "baseball": [],
        "court": [],
    }
    counts = {name: 0 for name in groups}
    terrain_clip = terrain_geometry.buffer(1.0)
    for element in osm_payload.get("elements", []):
        if element.get("type") not in {"way", "relation"}:
            continue
        tags = element.get("tags", {}) or {}
        geom = osm_geometry(element, transformer)
        if geom is None or geom.is_empty:
            continue
        geom = geom.intersection(terrain_clip)
        if geom.is_empty:
            continue

        highway = tags.get("highway")
        leisure = tags.get("leisure")
        amenity = tags.get("amenity")
        natural = tags.get("natural")
        landuse = tags.get("landuse")
        sport = tags.get("sport", "")
        surface = tags.get("surface", "")

        if highway:
            if highway in {"footway", "path", "steps", "pedestrian", "cycleway", "bridleway"}:
                groups["path"].append(buffered_line(geom, 2.0))
                counts["path"] += 1
            elif highway in {"service", "track", "driveway"}:
                groups["road"].append(buffered_line(geom, 4.0))
                counts["road"] += 1
            else:
                groups["road"].append(buffered_line(geom, 6.0))
                counts["road"] += 1
            continue
        if amenity == "parking" or tags.get("parking"):
            groups["parking"].append(buffered_line(geom, 5.0))
            counts["parking"] += 1
            continue
        if natural == "water" or tags.get("water") or tags.get("waterway"):
            groups["water"].append(buffered_line(geom, 4.0))
            counts["water"] += 1
            continue
        if leisure == "track":
            groups["track"].append(buffered_line(geom, 5.0))
            counts["track"] += 1
            continue
        if leisure == "pitch":
            if "tennis" in sport or "pickleball" in sport:
                groups["tennis"].append(geom)
                counts["tennis"] += 1
            elif "baseball" in sport or "softball" in sport:
                groups["baseball"].append(geom)
                counts["baseball"] += 1
            elif "basketball" in sport:
                groups["court"].append(geom)
                counts["court"] += 1
            else:
                groups["field"].append(geom)
                counts["field"] += 1
            continue
        if leisure in {"park", "garden", "sports_centre"} or landuse in {"grass", "recreation_ground", "meadow"} or surface in {"grass", "turf"}:
            groups["grass"].append(geom)
            counts["grass"] += 1

    masks = {name: rasterize_mask(geoms, grid, all_touched=True) for name, geoms in groups.items()}
    return masks, counts


def outline_mask(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    if not mask.any():
        return mask
    eroded = ndimage.binary_erosion(mask, iterations=iterations, border_value=0)
    return mask & ~eroded


def add_sports_markings(surface: np.ndarray, masks: dict[str, np.ndarray], states: dict[str, int]) -> None:
    for name in ("field", "tennis", "court", "baseball", "track"):
        mask = masks.get(name)
        if mask is None or not mask.any():
            continue
        surface[outline_mask(mask)] = states["white_concrete"]
        rows, cols = np.nonzero(mask)
        if len(rows) == 0:
            continue
        min_r, max_r = int(rows.min()), int(rows.max())
        min_c, max_c = int(cols.min()), int(cols.max())
        height = max(1, max_r - min_r + 1)
        width = max(1, max_c - min_c + 1)
        rr = rows - min_r
        cc = cols - min_c
        line = np.zeros_like(rows, dtype=bool)
        if name in {"field", "tennis", "court"}:
            line |= np.abs(rr - height / 2.0) <= 1.0
            line |= np.abs(cc - width / 2.0) <= 1.0
        if name == "tennis":
            line |= np.abs(rr - height * 0.25) <= 0.75
            line |= np.abs(rr - height * 0.75) <= 0.75
        if line.any():
            surface[rows[line], cols[line]] = states["white_concrete"]


def create_surface_grid(
    terrain_mask: np.ndarray,
    masks: dict[str, np.ndarray],
    palette: Palette,
) -> tuple[np.ndarray, dict[str, int]]:
    states = {
        "stone": palette.add("stone"),
        "dirt": palette.add("dirt"),
        "coarse_dirt": palette.add("coarse_dirt"),
        "grass_block": palette.add("grass_block"),
        "moss_block": palette.add("moss_block"),
        "sand": palette.add("sand"),
        "water": palette.add("water"),
        "gray_concrete": palette.add("gray_concrete"),
        "black_concrete": palette.add("black_concrete"),
        "light_gray_concrete": palette.add("light_gray_concrete"),
        "stone_bricks": palette.add("stone_bricks"),
        "white_concrete": palette.add("white_concrete"),
        "green_concrete": palette.add("green_concrete"),
        "lime_concrete": palette.add("lime_concrete"),
        "blue_concrete": palette.add("blue_concrete"),
        "red_concrete": palette.add("red_concrete"),
        "brown_concrete": palette.add("brown_concrete"),
        "bricks": palette.add("bricks"),
        "mud_bricks": palette.add("mud_bricks"),
        "smooth_stone": palette.add("smooth_stone"),
        "polished_andesite": palette.add("polished_andesite"),
        "deepslate_tiles": palette.add("deepslate_tiles"),
        "dark_oak_planks": palette.add("dark_oak_planks"),
        "glass": palette.add("glass"),
        "light_blue_stained_glass": palette.add("light_blue_stained_glass"),
        "air": palette.add("air"),
        "oak_log": palette.add("oak_log", {"axis": "y"}),
        "oak_leaves": palette.add("oak_leaves", {"persistent": "true"}),
    }
    surface = np.full(terrain_mask.shape, states["grass_block"], dtype=np.uint16)
    if masks.get("grass") is not None:
        surface[masks["grass"] & terrain_mask] = states["moss_block"]
    if masks.get("path") is not None:
        surface[masks["path"] & terrain_mask] = states["stone_bricks"]
    if masks.get("road") is not None:
        surface[masks["road"] & terrain_mask] = states["gray_concrete"]
    if masks.get("parking") is not None:
        surface[masks["parking"] & terrain_mask] = states["light_gray_concrete"]
    if masks.get("track") is not None:
        surface[masks["track"] & terrain_mask] = states["red_concrete"]
    if masks.get("field") is not None:
        field = masks["field"] & terrain_mask
        surface[field] = states["grass_block"]
        rows, cols = np.nonzero(field)
        stripes = ((cols // 8) % 2) == 0
        surface[rows[stripes], cols[stripes]] = states["moss_block"]
    if masks.get("tennis") is not None:
        surface[masks["tennis"] & terrain_mask] = states["green_concrete"]
    if masks.get("court") is not None:
        surface[masks["court"] & terrain_mask] = states["blue_concrete"]
    if masks.get("baseball") is not None:
        surface[masks["baseball"] & terrain_mask] = states["coarse_dirt"]
    if masks.get("water") is not None:
        surface[masks["water"] & terrain_mask] = states["water"]
    add_sports_markings(surface, masks, states)
    return surface, states


def local_raster_mask(geometry: BaseGeometry, grid: GridSpec, padding: int = 1) -> tuple[np.ndarray, int, int]:
    min_x, min_y, max_x, max_y = geometry.bounds
    c0 = max(0, grid.col_for_x(min_x) - padding)
    c1 = min(grid.width - 1, grid.col_for_x(max_x) + padding)
    r0 = max(0, grid.row_for_y(max_y) - padding)
    r1 = min(grid.depth - 1, grid.row_for_y(min_y) + padding)
    if c1 < c0 or r1 < r0:
        return np.zeros((0, 0), dtype=bool), 0, 0
    local_transform = grid.transform * Affine.translation(c0, r0)
    mask = features.rasterize(
        [(geometry, 1)],
        out_shape=(r1 - r0 + 1, c1 - c0 + 1),
        transform=local_transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)
    return mask, r0, c0


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def building_height_metres(properties: dict[str, Any], normalized_heights: np.ndarray) -> tuple[float, str]:
    lidar_values = normalized_heights[np.isfinite(normalized_heights)]
    lidar_values = lidar_values[(lidar_values > 2.0) & (lidar_values < 70.0)]
    lidar_height = float(np.percentile(lidar_values, 82)) if lidar_values.size >= 12 else None
    attr = numeric(properties.get("Height"))
    attr_metres = attr * 0.3048 if attr and 6.0 <= attr <= 220.0 else None
    stories = numeric(properties.get("STORIES"))
    story_metres = stories * 3.4 + 1.0 if stories and 1 <= stories <= 8 else None

    candidates = [value for value in (lidar_height, attr_metres, story_metres) if value is not None]
    if not candidates:
        return 7.0, "default"
    if lidar_height is not None and attr_metres is not None:
        if lidar_height > attr_metres * 1.55:
            return max(4.0, attr_metres), "county-height-feet-tree-clamped"
        if lidar_height < attr_metres * 0.55:
            return max(4.0, attr_metres), "county-height-feet"
        return max(4.0, lidar_height), "lidar"
    source = "lidar" if lidar_height is not None else "county-height-feet" if attr_metres is not None else "stories"
    return max(4.0, candidates[0]), source


def building_materials(properties: dict[str, Any], states: dict[str, int]) -> tuple[int, int, int, int]:
    text = " ".join(str(properties.get(key, "")).lower() for key in ("IMPRNAME", "DESCRIPTION", "Category"))
    if any(word in text for word in ("garage", "shed", "utility", "commercial", "industrial", "pool")):
        return states["polished_andesite"], states["smooth_stone"], states["deepslate_tiles"], states["light_blue_stained_glass"]
    if any(word in text for word in ("field house", "gym", "athletic", "rink")):
        return states["mud_bricks"], states["smooth_stone"], states["deepslate_tiles"], states["light_blue_stained_glass"]
    return states["bricks"], states["stone_bricks"], states["deepslate_tiles"], states["glass"]


def place_buildings(
    store: BlockSpool,
    building_features: list[GeoFeature],
    transformer: Transformer,
    terrain_geometry: BaseGeometry,
    grid: GridSpec,
    terrain_y: np.ndarray,
    ndsm: np.ndarray | None,
    states: dict[str, int],
    road_distance: np.ndarray,
    top_state: np.ndarray,
    top_y: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    building_mask = np.zeros((grid.depth, grid.width), dtype=bool)
    manifest: list[dict[str, Any]] = []
    for index, feature in enumerate(building_features, start=1):
        source_geom = to_work_geometry(feature.geometry, transformer)
        geom = source_geom.intersection(terrain_geometry.buffer(4.0))
        if geom.is_empty:
            centroid = source_geom.representative_point()
            mc_x, mc_z = grid.minecraft_for_point(centroid)
            manifest.append(
                {
                    "index": index,
                    "name": feature.properties.get("IMPRNAME") or feature.properties.get("DESCRIPTION") or f"building-{index}",
                    "parid": feature.properties.get("PARID"),
                    "category": feature.properties.get("Category"),
                    "description": feature.properties.get("DESCRIPTION"),
                    "placed": False,
                    "skip_reason": "outside terrain geometry",
                    "footprint_cells": 0,
                    "minecraft": {"x": mc_x, "y": None, "z": mc_z},
                }
            )
            continue
        mask, r0, c0 = local_raster_mask(geom, grid, padding=2)
        if mask.size == 0 or not mask.any():
            centroid = geom.representative_point()
            mc_x, mc_z = grid.minecraft_for_point(centroid)
            manifest.append(
                {
                    "index": index,
                    "name": feature.properties.get("IMPRNAME") or feature.properties.get("DESCRIPTION") or f"building-{index}",
                    "parid": feature.properties.get("PARID"),
                    "category": feature.properties.get("Category"),
                    "description": feature.properties.get("DESCRIPTION"),
                    "placed": False,
                    "skip_reason": "rasterized to zero cells",
                    "footprint_cells": 0,
                    "minecraft": {"x": mc_x, "y": None, "z": mc_z},
                }
            )
            continue
        local_rows, local_cols = np.nonzero(mask)
        rows = local_rows + r0
        cols = local_cols + c0
        building_mask[rows, cols] = True
        terrain_values = terrain_y[rows, cols]
        # Buildings need a single level datum.  Following the DEM independently
        # at every footprint cell produces visibly warped walls and rooflines on
        # large/sloped footprints.  A slightly uphill-biased pad minimizes the
        # worst cut while leaving enough foundation on the downhill edge.
        floor_y = int(np.rint(np.percentile(terrain_values, 60)))
        terrain_y_min = int(terrain_values.min())
        terrain_y_max = int(terrain_values.max())
        local_ndsm = ndsm[rows, cols] if ndsm is not None else np.array([], dtype=np.float32)
        height_m, height_source = building_height_metres(feature.properties, local_ndsm)
        height_blocks = int(np.clip(round(height_m), 4, 48))
        roof_blocks = int(np.clip(round(height_blocks * 0.22), 1, 7))
        wall_blocks = max(3, height_blocks - roof_blocks)
        wall_state, floor_state, roof_state, window_state = building_materials(feature.properties, states)
        boundary = outline_mask(mask)
        distance = ndimage.distance_transform_edt(mask)
        local_boundary_rows, local_boundary_cols = np.nonzero(boundary)
        door_local: tuple[int, int] | None = None
        if len(local_boundary_rows) > 0:
            global_rows = local_boundary_rows + r0
            global_cols = local_boundary_cols + c0
            choice = int(np.argmin(road_distance[global_rows, global_cols]))
            door_local = (int(local_boundary_rows[choice]), int(local_boundary_cols[choice]))

        for lr, lc in zip(local_rows, local_cols, strict=False):
            row = int(lr + r0)
            col = int(lc + c0)
            cell_terrain = int(terrain_y[row, col])
            for y in range(cell_terrain + 1, floor_y):
                store.add_state(floor_state, col, y, row)
            for y in range(floor_y + 1, cell_terrain + 1):
                store.add_state(states["air"], col, y, row)
            store.add_state(floor_state, col, floor_y, row)
            if boundary[lr, lc]:
                for dy in range(1, wall_blocks + 1):
                    y = floor_y + dy
                    window_band = dy >= 2 and dy <= wall_blocks - 1 and dy % 4 in {2, 3}
                    regular_window = window_band and ((row + col) % 5 in {0, 1})
                    store.add_state(window_state if regular_window else wall_state, col, y, row)
            roof_extra = int(min(roof_blocks, max(1.0, distance[lr, lc] * 0.5)))
            roof_start = floor_y + wall_blocks + 1
            for y in range(roof_start, roof_start + roof_extra + 1):
                store.add_state(roof_state, col, y, row)
            top_state[row, col] = roof_state
            top_y[row, col] = max(top_y[row, col], roof_start + roof_extra)

        if door_local is not None:
            dr, dc = door_local
            for rr in range(max(0, dr - 1), min(mask.shape[0], dr + 2)):
                for cc in range(max(0, dc - 1), min(mask.shape[1], dc + 2)):
                    if not boundary[rr, cc]:
                        continue
                    row = rr + r0
                    col = cc + c0
                    for y in (floor_y + 1, floor_y + 2):
                        store.add_state(states["air"], col, y, row)

        centroid = geom.representative_point()
        mc_x, mc_z = grid.minecraft_for_point(centroid)
        manifest.append(
            {
                "index": index,
                "name": feature.properties.get("IMPRNAME") or feature.properties.get("DESCRIPTION") or f"building-{index}",
                "parid": feature.properties.get("PARID"),
                "category": feature.properties.get("Category"),
                "description": feature.properties.get("DESCRIPTION"),
                "placed": True,
                "county_height_raw": feature.properties.get("Height"),
                "height_metres": round(height_m, 2),
                "height_source": height_source,
                "footprint_cells": int(mask.sum()),
                "floor_y": floor_y,
                "terrain_y_range": [terrain_y_min, terrain_y_max],
                "pad_cut_fill_blocks": {
                    "cut": max(0, terrain_y_max - floor_y),
                    "fill": max(0, floor_y - terrain_y_min),
                },
                "minecraft": {"x": mc_x, "y": floor_y + 1, "z": mc_z},
            }
        )
    return building_mask, manifest


def place_tree(
    store: BlockSpool,
    row: int,
    col: int,
    terrain_y: np.ndarray,
    canopy_height: float,
    states: dict[str, int],
    top_state: np.ndarray,
    top_y: np.ndarray,
    blocked_mask: np.ndarray,
) -> None:
    base_y = int(terrain_y[row, col])
    trunk_height = int(np.clip(round(canopy_height * 0.42), 3, 9))
    radius = int(np.clip(round(canopy_height / 5.5), 2, 5))
    leaf_center_y = base_y + trunk_height + 1
    for y in range(base_y + 1, base_y + trunk_height + 1):
        store.add_state(states["oak_log"], col, y, row)
    for dz in range(-radius, radius + 1):
        rr = row + dz
        if rr < 0 or rr >= terrain_y.shape[0]:
            continue
        for dx in range(-radius, radius + 1):
            cc = col + dx
            if cc < 0 or cc >= terrain_y.shape[1]:
                continue
            if blocked_mask[rr, cc]:
                continue
            horizontal = (dx * dx + dz * dz) ** 0.5
            if horizontal > radius + 0.15:
                continue
            for dy in range(-radius + 1, radius + 2):
                if (horizontal / max(1, radius)) ** 2 + (dy / max(1, radius + 0.5)) ** 2 > 1.15:
                    continue
                y = leaf_center_y + dy
                store.add_state(states["oak_leaves"], cc, y, rr)
                if y >= top_y[rr, cc]:
                    top_y[rr, cc] = y
                    top_state[rr, cc] = states["oak_leaves"]


def place_trees(
    store: BlockSpool,
    terrain_mask: np.ndarray,
    terrain_y: np.ndarray,
    ndsm: np.ndarray | None,
    excluded: np.ndarray,
    states: dict[str, int],
    top_state: np.ndarray,
    top_y: np.ndarray,
    seed: int,
    max_trees: int,
) -> int:
    rng = random.Random(seed)
    candidate = terrain_mask & ~excluded
    candidate &= ~ndimage.binary_dilation(excluded, iterations=2)
    if not candidate.any() or max_trees <= 0:
        return 0

    placed = 0
    occupied = np.zeros_like(candidate)
    centers: list[tuple[int, int, float]] = []
    if ndsm is not None:
        heights = np.where(candidate & np.isfinite(ndsm), ndsm, np.nan)
        heights[(heights < 5.0) | (heights > 36.0)] = np.nan
        maxima = np.isfinite(heights) & (heights == ndimage.maximum_filter(np.nan_to_num(heights, nan=-1.0), size=9))
        rows, cols = np.nonzero(maxima)
        if len(rows) > 0:
            values = heights[rows, cols]
            order = np.argsort(-values)
            centers = [(int(rows[i]), int(cols[i]), float(values[i])) for i in order]
    if not centers:
        rows, cols = np.nonzero(candidate)
        sample_size = min(len(rows), max_trees * 20)
        sample_indices = rng.sample(range(len(rows)), sample_size) if len(rows) > sample_size else list(range(len(rows)))
        centers = [(int(rows[i]), int(cols[i]), rng.uniform(7.0, 16.0)) for i in sample_indices]
        rng.shuffle(centers)

    for row, col, height in centers:
        radius = int(np.clip(round(height / 5.5), 3, 7))
        r0, r1 = max(0, row - radius), min(candidate.shape[0], row + radius + 1)
        c0, c1 = max(0, col - radius), min(candidate.shape[1], col + radius + 1)
        if occupied[r0:r1, c0:c1].any():
            continue
        place_tree(store, row, col, terrain_y, height, states, top_state, top_y, excluded)
        occupied[r0:r1, c0:c1] = True
        placed += 1
        if placed >= max_trees:
            break
    return placed


def write_string(handle: Any, value: str) -> None:
    data = value.encode("utf-8")
    if len(data) > 65_535:
        raise ValueError(f"NBT string too long: {value[:40]}")
    handle.write(struct.pack(">H", len(data)))
    handle.write(data)


def write_named_header(handle: Any, tag_type: int, name: str) -> None:
    handle.write(bytes([tag_type]))
    write_string(handle, name)


def write_int(handle: Any, value: int) -> None:
    handle.write(struct.pack(">i", value))


def write_int_list_tag(handle: Any, name: str, values: list[int]) -> None:
    write_named_header(handle, TAG_LIST, name)
    handle.write(bytes([TAG_INT]))
    write_int(handle, len(values))
    for value in values:
        write_int(handle, value)


def write_palette(handle: Any, palette: Palette) -> None:
    write_named_header(handle, TAG_LIST, "palette")
    handle.write(bytes([TAG_COMPOUND]))
    write_int(handle, len(palette.entries))
    for block_name, props in palette.entries:
        write_named_header(handle, TAG_STRING, "Name")
        write_string(handle, block_name)
        if props:
            write_named_header(handle, TAG_COMPOUND, "Properties")
            for key, value in props:
                write_named_header(handle, TAG_STRING, key)
                write_string(handle, value)
            handle.write(bytes([TAG_END]))
        handle.write(bytes([TAG_END]))


def write_block(handle: Any, state: int, x: int, y: int, z: int) -> None:
    write_named_header(handle, TAG_INT, "state")
    write_int(handle, state)
    write_named_header(handle, TAG_LIST, "pos")
    handle.write(bytes([TAG_INT]))
    write_int(handle, 3)
    write_int(handle, x)
    write_int(handle, y)
    write_int(handle, z)
    handle.write(bytes([TAG_END]))


def write_structure_nbt(path: Path, palette: Palette, spool_path: Path, block_count: int, size: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=6) as handle:
        write_named_header(handle, TAG_COMPOUND, "")
        write_named_header(handle, TAG_INT, "DataVersion")
        write_int(handle, 4903)
        write_int_list_tag(handle, "size", list(size))
        write_palette(handle, palette)
        write_named_header(handle, TAG_LIST, "blocks")
        handle.write(bytes([TAG_COMPOUND]))
        write_int(handle, block_count)
        with spool_path.open("rb") as spool:
            while True:
                record = spool.read(BLOCK_RECORD.size)
                if not record:
                    break
                state, x, y, z = BLOCK_RECORD.unpack(record)
                write_block(handle, state, x, y, z)
        write_named_header(handle, TAG_LIST, "entities")
        handle.write(bytes([TAG_COMPOUND]))
        write_int(handle, 0)
        handle.write(bytes([TAG_END]))


def validate_nbt_metadata(path: Path) -> dict[str, int]:
    def read_string(handle: Any) -> str:
        length_bytes = handle.read(2)
        if len(length_bytes) != 2:
            raise EOFError("Unexpected EOF reading string length")
        length = struct.unpack(">H", length_bytes)[0]
        data = handle.read(length)
        if len(data) != length:
            raise EOFError("Unexpected EOF reading string")
        return data.decode("utf-8")

    def skip_payload(handle: Any, tag_type: int) -> None:
        if tag_type == TAG_BYTE:
            handle.read(1)
        elif tag_type == TAG_SHORT:
            handle.read(2)
        elif tag_type == TAG_INT:
            handle.read(4)
        elif tag_type == TAG_LONG:
            handle.read(8)
        elif tag_type == TAG_FLOAT:
            handle.read(4)
        elif tag_type == TAG_DOUBLE:
            handle.read(8)
        elif tag_type == TAG_BYTE_ARRAY:
            length = struct.unpack(">i", handle.read(4))[0]
            handle.read(length)
        elif tag_type == TAG_STRING:
            read_string(handle)
        elif tag_type == TAG_LIST:
            element = handle.read(1)[0]
            length = struct.unpack(">i", handle.read(4))[0]
            for _ in range(length):
                skip_payload(handle, element)
        elif tag_type == TAG_COMPOUND:
            while True:
                nested = handle.read(1)[0]
                if nested == TAG_END:
                    break
                read_string(handle)
                skip_payload(handle, nested)
        elif tag_type == TAG_INT_ARRAY:
            length = struct.unpack(">i", handle.read(4))[0]
            handle.read(length * 4)
        elif tag_type == TAG_LONG_ARRAY:
            length = struct.unpack(">i", handle.read(4))[0]
            handle.read(length * 8)
        elif tag_type == TAG_END:
            return
        else:
            raise RuntimeError(f"Unknown NBT tag type {tag_type}")

    opener = gzip.open if path.suffix == ".nbt" else open
    with opener(path, "rb") as handle:
        root = handle.read(1)[0]
        if root != TAG_COMPOUND:
            raise RuntimeError("NBT root is not a compound")
        read_string(handle)
        metadata: dict[str, int] = {}
        while True:
            tag = handle.read(1)[0]
            if tag == TAG_END:
                break
            name = read_string(handle)
            if name == "size":
                element = handle.read(1)[0]
                length = struct.unpack(">i", handle.read(4))[0]
                if tag != TAG_LIST or element != TAG_INT or length != 3:
                    raise RuntimeError("Invalid size tag")
                metadata["size_x"] = struct.unpack(">i", handle.read(4))[0]
                metadata["size_y"] = struct.unpack(">i", handle.read(4))[0]
                metadata["size_z"] = struct.unpack(">i", handle.read(4))[0]
            elif name == "palette":
                element = handle.read(1)[0]
                length = struct.unpack(">i", handle.read(4))[0]
                metadata["palette"] = length
                for _ in range(length):
                    skip_payload(handle, element)
            elif name == "blocks":
                element = handle.read(1)[0]
                length = struct.unpack(">i", handle.read(4))[0]
                if tag != TAG_LIST or element != TAG_COMPOUND:
                    raise RuntimeError("Invalid blocks tag")
                metadata["blocks"] = length
                return metadata
            else:
                skip_payload(handle, tag)
    raise RuntimeError("NBT did not contain a blocks list")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def color_for_state(palette: Palette, state: int) -> tuple[int, int, int]:
    return MATERIAL_COLORS.get(palette.block_name(int(state)), (180, 180, 170))


def render_preview(
    path: Path,
    palette: Palette,
    top_state: np.ndarray,
    top_y: np.ndarray,
    terrain_mask: np.ndarray,
    dem: np.ndarray,
    buildings: list[dict[str, Any]],
    grid: GridSpec,
    reference_image: Path | None,
    reference_bounds: tuple[float, float, float, float] | None,
) -> None:
    rgb = np.zeros((grid.depth, grid.width, 3), dtype=np.uint8)
    for state in np.unique(top_state[terrain_mask]):
        rgb[top_state == state] = color_for_state(palette, int(state))
    rgb[~terrain_mask] = (10, 14, 18)

    gy, gx = np.gradient(dem.astype(np.float32))
    shade = 1.0 - np.clip((gx * -0.4 + gy * 0.7), -0.35, 0.35)
    shade = np.clip(shade, 0.72, 1.18)
    rgb = np.clip(rgb.astype(np.float32) * shade[:, :, None], 0, 255).astype(np.uint8)

    if reference_image and reference_bounds and reference_image.is_file():
        try:
            image = Image.open(reference_image).convert("RGB")
            img_min_x, img_min_y, img_max_x, img_max_y = reference_bounds
            left = (grid.min_x - img_min_x) / (img_max_x - img_min_x) * image.width
            right = (grid.max_x - img_min_x) / (img_max_x - img_min_x) * image.width
            top = (img_max_y - grid.max_y) / (img_max_y - img_min_y) * image.height
            bottom = (img_max_y - grid.min_y) / (img_max_y - img_min_y) * image.height
            if right > 0 and bottom > 0 and left < image.width and top < image.height:
                crop = image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))
                crop = crop.resize((grid.width, grid.depth), Image.Resampling.BILINEAR)
                ref = np.asarray(crop, dtype=np.uint8)
                rgb[terrain_mask] = (rgb[terrain_mask].astype(np.float32) * 0.72 + ref[terrain_mask].astype(np.float32) * 0.28).astype(np.uint8)
        except Exception as exc:
            log(f"Warning: could not blend reference imagery into preview: {exc}")

    image = Image.fromarray(rgb, "RGB")
    draw = ImageDraw.Draw(image)
    largest = sorted(buildings, key=lambda item: item.get("footprint_cells", 0), reverse=True)[:20]
    for building in largest:
        name = str(building.get("name", "")).strip()
        if not name or name.startswith("building-"):
            continue
        mc = building.get("minecraft", {})
        x = int(mc.get("x", 0))
        z = int(mc.get("z", 0))
        if 0 <= x < grid.width and 0 <= z < grid.depth:
            draw.rectangle((x - 2, z - 2, x + 2, z + 2), fill=(255, 245, 160))
            draw.text((x + 4, z - 4), name[:28], fill=(255, 245, 160))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def generate_terrain_blocks(
    store: BlockSpool,
    terrain_mask: np.ndarray,
    terrain_y: np.ndarray,
    surface: np.ndarray,
    states: dict[str, int],
    top_state: np.ndarray,
    top_y: np.ndarray,
) -> None:
    rows, cols = np.nonzero(terrain_mask)
    water = surface == states["water"]
    for row, col in zip(rows, cols, strict=False):
        h = int(terrain_y[row, col])
        base = max(0, h - 4)
        for y in range(base, h - 2):
            store.add_state(states["stone"], int(col), y, int(row))
        for y in range(max(base, h - 2), h):
            store.add_state(states["dirt"], int(col), y, int(row))
        if water[row, col]:
            store.add_state(states["sand"], int(col), h - 1, int(row))
            store.add_state(states["water"], int(col), h, int(row))
        else:
            store.add_state(int(surface[row, col]), int(col), h, int(row))
        top_state[row, col] = surface[row, col]
        top_y[row, col] = h


def parse_bounds(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("Bounds must be minx,miny,maxx,maxy")
    return tuple(parts)  # type: ignore[return-value]


def default_output_paths(scope: str, root: Path) -> tuple[Path, Path, Path]:
    out_dir = root / "runtime" / "campus-output"
    return (
        out_dir / f"hill-campus-{scope}.nbt",
        out_dir / f"hill-campus-{scope}-preview.png",
        out_dir / f"hill-campus-{scope}-manifest.json",
    )


def run_self_test(root: Path) -> None:
    out_dir = root / "runtime" / "campus-output"
    out_dir.mkdir(parents=True, exist_ok=True)
    palette = Palette()
    grass = palette.add("grass_block")
    stone = palette.add("stone")
    bricks = palette.add("bricks")
    glass = palette.add("glass")
    accumulator = np.full((2, 2), -np.inf, dtype=np.float32)
    np.maximum.at(accumulator, ([0], [1]), np.array([123.5], dtype=np.float32))
    accumulator[~np.isfinite(accumulator)] = np.nan
    if not np.isfinite(accumulator[0, 1]):
        raise RuntimeError("DSM accumulator self-test failed")
    fd, temp_name = tempfile.mkstemp(prefix="hill-campus-selftest-", suffix=".spool", dir=out_dir)
    os.close(fd)
    spool_path = Path(temp_name)
    store = BlockSpool(spool_path, palette, 16, 16, 16)
    try:
        for x in range(16):
            for z in range(16):
                store.add_state(stone, x, 0, z)
                store.add_state(grass, x, 1, z)
        for x in range(4, 12):
            for z in range(4, 12):
                store.add_state(bricks if x in {4, 11} or z in {4, 11} else glass, x, 2, z)
        store.close()
        output = out_dir / "hill-campus-self-test.nbt"
        write_structure_nbt(output, palette, spool_path, store.count, (16, 16, 16))
        metadata = validate_nbt_metadata(output)
        if metadata != {"size_x": 16, "size_y": 16, "size_z": 16, "palette": 4, "blocks": store.count}:
            raise RuntimeError(f"Unexpected self-test metadata: {metadata}")
        log(f"Self-test wrote {output} with {store.count} blocks.")
    finally:
        try:
            store.close()
        except Exception:
            pass
        spool_path.unlink(missing_ok=True)


def build_manifest(
    args: argparse.Namespace,
    grid: GridSpec,
    terrain_mask: np.ndarray,
    terrain_y: np.ndarray,
    palette: Palette,
    store: BlockSpool,
    buildings: list[dict[str, Any]],
    sources: list[SourceStatus],
    osm_counts: dict[str, int],
    tree_count: int,
    nbt_path: Path,
    preview_path: Path,
) -> dict[str, Any]:
    nbt_metadata = validate_nbt_metadata(nbt_path)
    return {
        "generated_at_unix": int(time.time()),
        "scope": args.scope,
        "address": "The Hill School, 860 Beech Street, Pottstown, PA 19464",
        "minecraft": {
            "structure_file": str(nbt_path),
            "preview_file": str(preview_path),
            "data_version": 4903,
            "size": {"x": grid.width, "y": int(args.size_y), "z": grid.depth},
            "blocks": store.count,
            "palette_size": len(palette.entries),
            "centered_world_origin": {"x": -(grid.width // 2), "y": 64, "z": -(grid.depth // 2)},
            "metadata_readback": nbt_metadata,
        },
        "grid": {
            "crs": f"EPSG:{WORK_CRS_EPSG}",
            "resolution_metres_per_block": grid.resolution,
            "utm_bounds": [grid.min_x, grid.min_y, grid.max_x, grid.max_y],
            "cells_inside_terrain_mask": int(terrain_mask.sum()),
            "terrain_y_range": [int(terrain_y[terrain_mask].min()), int(terrain_y[terrain_mask].max())],
        },
        "source_notes": {
            "voxelearth": "Chrome/VoxelEarth was used for interactive inspection, but not as an exported source. This file is generated from GIS, DEM, lidar, and OSM data.",
            "building_height": "County Height values are treated as feet and cross-checked/clamped with USGS lidar when complete tiles are available.",
            "building_pads": "Each footprint is cut/filled to one 60th-percentile terrain datum so walls and rooflines remain level across sloped DEM cells.",
            "interiors": "Buildings are hollow massing models with floors, walls, roofs, window rhythm, and door openings; private interior layouts are not inferred.",
            "neutral_intermediate": "Use --keep-spool to preserve the fixed-record block stream used to write NBT. Each little-endian record is state:uint16,x:uint16,y:uint16,z:uint16.",
            "phase1_scope": "Phase 1 is a gameplay crop around the main academic/athletic campus and all queried county building footprints, not a parcel survey boundary.",
        },
        "official_campus_map": {
            "url": OFFICIAL_CAMPUS_MAP_URL,
            "local_path": str((Path.cwd() / OFFICIAL_CAMPUS_MAP_PATH).resolve()),
            "landmark_checklist": list(OFFICIAL_LANDMARKS),
            "note": "The checklist comes from the official Hill campus map and is for manual QA against the generated massing.",
        },
        "osm_feature_counts": osm_counts,
        "tree_count": tree_count,
        "buildings": buildings,
        "sources": [status.__dict__ for status in sources],
        "sha256": {"nbt": sha256_file(nbt_path), "preview": sha256_file(preview_path) if preview_path.is_file() else None},
    }


def generate(args: argparse.Namespace) -> None:
    timer = Timer()
    root = Path.cwd()
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    gis_dir = data_dir / "gis"
    dem_dirs = [data_dir / "dem-d24", data_dir / "dem"]
    lidar_dir = data_dir / "lidar"

    default_nbt, default_preview, default_manifest = default_output_paths(args.scope, root)
    output_path = Path(args.output) if args.output else default_nbt
    preview_path = Path(args.preview) if args.preview else default_preview
    manifest_path = Path(args.manifest) if args.manifest else default_manifest
    if not output_path.is_absolute():
        output_path = root / output_path
    if not preview_path.is_absolute():
        preview_path = root / preview_path
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path

    lonlat_to_work = Transformer.from_crs(WGS84, f"EPSG:{WORK_CRS_EPSG}", always_xy=True)

    log(f"Fetching/caching GIS inputs for {args.scope} scope...")
    assessment_rows, statuses = fetch_assessment_rows(gis_dir, args.refresh)
    parcel_ids = parcel_ids_for_scope(args.scope, assessment_rows)
    bbox_wgs84 = PHASE1_BBOX_WGS84 if args.scope == "phase1" else FULL_BBOX_WGS84

    parcel_payload = fetch_geojson_chunks(
        gis_dir / f"montco-hill-parcels-{args.scope}.geojson",
        PARCELS_URL,
        "TAXPIN",
        parcel_ids,
        "TAXPIN,ALTERNATEID,PARCELTYPE,CALCACREAGE,TrueCalculatedAcres",
        args.refresh,
    )
    building_payload = fetch_geojson_chunks(
        gis_dir / f"montco-hill-buildings-{args.scope}.geojson",
        BUILDINGS_URL,
        "PARID",
        parcel_ids,
        "PARID,STRUCTUREID,Height,STORIES,SFLA,IMPRNAME,DESCRIPTION,Category,YRBLT",
        args.refresh,
    )
    osm_payload, osm_statuses = fetch_osm(gis_dir, bbox_wgs84, args.refresh)
    statuses.extend(osm_statuses)
    statuses.append(SourceStatus("Montgomery County parcels", str(gis_dir / f"montco-hill-parcels-{args.scope}.geojson"), "cached"))
    statuses.append(SourceStatus("Montgomery County building outlines", str(gis_dir / f"montco-hill-buildings-{args.scope}.geojson"), "cached"))

    parcel_features = load_geojson_features(parcel_payload)
    building_features = load_geojson_features(building_payload)
    if not parcel_features:
        raise RuntimeError("No parcel geometries were returned for the requested scope.")
    parcel_union = unary_union([to_work_geometry(feature.geometry, lonlat_to_work) for feature in parcel_features])
    building_seed_geometries = [to_work_geometry(feature.geometry, lonlat_to_work) for feature in building_features]
    terrain_seed = unary_union([parcel_union, *building_seed_geometries]) if building_seed_geometries else parcel_union
    bbox_work = transform_bbox_to_work(bbox_wgs84, lonlat_to_work)
    terrain_geometry = terrain_seed.buffer(args.buffer_metres).intersection(bbox_work)
    if terrain_geometry.is_empty:
        raise RuntimeError("Terrain geometry is empty after parcel/bbox clipping.")
    grid = create_grid(terrain_geometry, args.metres_per_block, args.max_dimension)
    log(f"Grid: {grid.width} x {grid.depth} at {grid.resolution:g} m/block")

    terrain_mask = rasterize_mask([terrain_geometry], grid, all_touched=True)
    log("Loading DEM...")
    dem, dem_statuses = load_dem_grid(dem_dirs, grid, args.smooth_dem)
    statuses.extend(dem_statuses)
    min_elev = float(np.percentile(dem[terrain_mask], 1.0))
    terrain_y = np.rint((dem - min_elev) * args.vertical_scale + args.base_depth).astype(np.int16)
    terrain_y = np.maximum(terrain_y, 2)
    if args.size_y is None:
        args.size_y = int(max(96, min(224, terrain_y[terrain_mask].max() + 76)))
    if int(terrain_y[terrain_mask].max()) + 60 >= int(args.size_y):
        args.size_y = int(terrain_y[terrain_mask].max()) + 72
    log(f"Terrain Y range: {int(terrain_y[terrain_mask].min())}..{int(terrain_y[terrain_mask].max())}, structure Y size {args.size_y}")

    ndsm: np.ndarray | None = None
    if not args.skip_lidar:
        log("Loading lidar surface model from complete LAZ tiles...")
        dsm, lidar_statuses = build_lidar_dsm(lidar_dir, grid, args.lidar_chunk_size)
        statuses.extend(lidar_statuses)
        if dsm is not None:
            ndsm = dsm - dem
            ndsm[(ndsm < -3.0) | (ndsm > 80.0)] = np.nan
            log(f"LiDAR coverage cells: {int(np.isfinite(ndsm).sum()):,}")
        else:
            log("No usable lidar points were available; using county heights and procedural trees.")

    log("Rasterizing OSM roads, paths, sports surfaces, parking, and water...")
    masks, osm_counts = surface_layers_from_osm(osm_payload, lonlat_to_work, terrain_geometry, grid)
    palette = Palette()
    surface, states = create_surface_grid(terrain_mask, masks, palette)
    top_state = np.zeros((grid.depth, grid.width), dtype=np.uint16)
    top_y = np.zeros((grid.depth, grid.width), dtype=np.int16)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, spool_name = tempfile.mkstemp(prefix=f"hill-campus-{args.scope}-", suffix=".spool", dir=output_path.parent)
    os.close(fd)
    spool_path = Path(spool_name)
    store = BlockSpool(spool_path, palette, grid.width, int(args.size_y), grid.depth)
    try:
        log("Writing terrain block spool...")
        generate_terrain_blocks(store, terrain_mask, terrain_y, surface, states, top_state, top_y)
        log(f"  terrain spool records: {store.count:,}")

        traversable = masks.get("road", np.zeros_like(terrain_mask)) | masks.get("path", np.zeros_like(terrain_mask))
        road_distance = ndimage.distance_transform_edt(~traversable)
        log(f"Placing {len(building_features)} county building footprints...")
        building_mask, building_manifest = place_buildings(
            store,
            building_features,
            lonlat_to_work,
            terrain_geometry,
            grid,
            terrain_y,
            ndsm,
            states,
            road_distance,
            top_state,
            top_y,
        )
        placed_buildings = sum(1 for building in building_manifest if building.get("placed"))
        log(f"  building footprints placed: {placed_buildings}/{len(building_manifest)}")

        excluded = building_mask.copy()
        for name in ("road", "path", "parking", "water", "track", "tennis", "field", "baseball", "court"):
            if name in masks:
                excluded |= masks[name]
        log("Placing canopy-derived trees...")
        tree_count = place_trees(
            store,
            terrain_mask,
            terrain_y,
            ndsm,
            excluded,
            states,
            top_state,
            top_y,
            args.seed,
            args.max_trees,
        )
        log(f"  trees placed: {tree_count}")
        store.close()

        log(f"Writing NBT: {output_path}")
        write_structure_nbt(output_path, palette, spool_path, store.count, (grid.width, int(args.size_y), grid.depth))
        metadata = validate_nbt_metadata(output_path)
        log(f"NBT metadata: {metadata}")

        reference_image = None
        reference_bounds = None
        if args.preview_imagery_overlay:
            reference_image = Path(args.reference_imagery) if args.reference_imagery else data_dir / "imagery" / "hill-campus-pema-2021-1m.png"
            reference_bounds = parse_bounds(args.reference_imagery_bounds) or (
                445691.8327,
                4454966.46235,
                447442.3480,
                4456893.92865,
            )
            if not reference_image.is_absolute():
                reference_image = root / reference_image
        log(f"Writing preview: {preview_path}")
        render_preview(
            preview_path,
            palette,
            top_state,
            top_y,
            terrain_mask,
            dem,
            building_manifest,
            grid,
            reference_image,
            reference_bounds,
        )

        manifest = build_manifest(
            args,
            grid,
            terrain_mask,
            terrain_y,
            palette,
            store,
            building_manifest,
            statuses,
            osm_counts,
            tree_count,
            output_path,
            preview_path,
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        log(f"Manifest: {manifest_path}")
        log(f"Completed in {timer.elapsed()}.")
    finally:
        try:
            store.close()
        except Exception:
            pass
        if args.keep_spool:
            log(f"Kept block spool for debugging: {spool_path}")
        else:
            spool_path.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_nbt, default_preview, default_manifest = default_output_paths("phase1", Path.cwd())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("phase1", "full"), default="phase1", help="Campus extent. phase1 is the default main academic/athletic map.")
    parser.add_argument("--data-dir", default="runtime/campus-data", help="Cached GIS, DEM, lidar, and imagery directory.")
    parser.add_argument("--output", default=None, help=f"Output structure NBT. Default: {default_nbt}")
    parser.add_argument("--preview", default=None, help=f"Output preview PNG. Default: {default_preview}")
    parser.add_argument("--manifest", default=None, help=f"Output provenance manifest JSON. Default: {default_manifest}")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch ArcGIS/OSM JSON instead of using cached files.")
    parser.add_argument("--metres-per-block", type=float, default=1.0, help="Horizontal resolution. Keep at 1.0 for the current server config.")
    parser.add_argument("--vertical-scale", type=float, default=1.0, help="Vertical exaggeration multiplier.")
    parser.add_argument("--base-depth", type=int, default=4, help="Y offset for the lowest local terrain.")
    parser.add_argument("--size-y", type=int, default=None, help="Explicit structure Y size. Defaults from terrain relief.")
    parser.add_argument("--buffer-metres", type=float, default=None, help="Parcel/building-union buffer before clipping to the scope bbox. Defaults: phase1=90, full=22.")
    parser.add_argument("--max-dimension", type=int, default=2048, help="Refuse to generate wider/deeper structures than this.")
    parser.add_argument("--smooth-dem", type=float, default=0.35, help="Gaussian smoothing sigma for bare-earth DEM.")
    parser.add_argument("--skip-lidar", action="store_true", help="Skip LAZ processing and rely on county/procedural heights.")
    parser.add_argument("--lidar-chunk-size", type=int, default=1_500_000, help="Point chunk size for LAZ streaming.")
    parser.add_argument("--seed", type=int, default=175, help="Deterministic tree/procedural seed.")
    parser.add_argument("--max-trees", type=int, default=900, help="Maximum procedural trees.")
    parser.add_argument("--reference-imagery", default=None, help="Optional PEMA PNG used only for preview blending.")
    parser.add_argument("--reference-imagery-bounds", default=None, help="UTM bounds for preview imagery: minx,miny,maxx,maxy.")
    parser.add_argument("--preview-imagery-overlay", action="store_true", help="Blend the PEMA reference image into the preview. Default preview is block-only.")
    parser.add_argument("--keep-spool", action="store_true", help="Keep the temporary fixed-record block spool.")
    parser.add_argument("--self-test", action="store_true", help="Write and validate a tiny synthetic structure NBT, then exit.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.buffer_metres is None:
        args.buffer_metres = 90.0 if args.scope == "phase1" else 22.0
    if args.self_test:
        run_self_test(Path.cwd())
        return 0
    generate(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
