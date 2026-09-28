#!/usr/bin/env python3
"""Build a measured, world-aligned Hill School terrain layer.

The output is terrain only: one bare-earth height and one intentional semantic
surface material per Minecraft column.  Coordinates use the existing
VoxelEarth convention (+X east, +Z south, one block per metre).  DEM samples
are taken at block centres and converted from NAVD88 metres with one fixed
campus-wide vertical offset; no building-specific elevation fitting occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS, Transformer
from rasterio import features
from rasterio.merge import merge
from scipy.ndimage import map_coordinates
from shapely.geometry import LineString, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as geometry_transform

from hybridize_voxelearth_roofer_world import (
    WorldTransform,
    buffered_site_line,
    osm_geometry_to_block,
    site_feature_group,
    site_feature_width_blocks,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_WORLD = (
    REPO_ROOT
    / "runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831"
    / "paper-runtime-wallclean-v7-1226"
    / "hill_school_voxelearth_full_groundfallback_v11_1xg64_20260831_1346"
)
DEFAULT_WORLD_MANIFEST = DEFAULT_SOURCE_WORLD / "voxelearth-hill-manifest.json"
DEFAULT_DEM = (
    REPO_ROOT
    / "runtime/campus-reconstruction/roofer-chapel-trial/inputs/hill-campus-dem-0p5m.tif"
)
DEFAULT_DEM_TILE_DIR = REPO_ROOT / "runtime/campus-data/dem-d24"
DEFAULT_PARCELS = REPO_ROOT / "runtime/campus-data/gis/montco-hill-parcels-full.geojson"
DEFAULT_BUILDINGS = REPO_ROOT / "runtime/campus-data/gis/montco-hill-buildings-full.geojson"
DEFAULT_OSM = (
    REPO_ROOT / "runtime/campus-data/gis/osm--75.63850-40.24338--75.61808-40.26086.json"
)
DEFAULT_SURFACES = (
    REPO_ROOT
    / "runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831"
    / "src/minecraft-plugin/src/main/resources/hill-campus-surfaces.geojson"
)
DEFAULT_DATUM_EVIDENCE = (
    REPO_ROOT
    / "runtime/campus-reconstruction/hybrid-voxelearth-ground-roofer-buildings"
    / "hill_school_hybrid_v15_strict_voxelearth_v11_roofer_npz_support_1x_20260831"
    / "hill-hybrid-manifest.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "runtime/campus-reconstruction/measured-terrain"
    / "hill-chapel-measured-terrain.npz"
)

# Median of 91 v15 Roofer NAVD88 base-to-VoxelEarth terrain anchors after
# requiring >=90% source coverage and rejecting offsets outside 15..35 blocks.
# The unrounded median is exactly 24.25; MAD is 0.98 block.
DEFAULT_NAVD88_TO_WORLD_Y_OFFSET = 24.25

CHAPEL_STRUCTURE_ID = "1600151160068C"
CHAPEL_EXPECTED_WORLD_XZ = (0.053723935398621525, 6.2884190576462995)


MATERIALS: dict[str, dict[str, Any]] = {
    "grass": {"id": 1, "minecraft_block": "minecraft:grass_block"},
    "field": {"id": 2, "minecraft_block": "minecraft:grass_block"},
    "baseball": {"id": 3, "minecraft_block": "minecraft:coarse_dirt"},
    "tennis": {"id": 4, "minecraft_block": "minecraft:green_concrete"},
    "court": {"id": 5, "minecraft_block": "minecraft:blue_concrete"},
    "track": {"id": 6, "minecraft_block": "minecraft:red_concrete"},
    "parking": {"id": 7, "minecraft_block": "minecraft:light_gray_concrete"},
    "path": {"id": 8, "minecraft_block": "minecraft:smooth_stone"},
    "road": {"id": 9, "minecraft_block": "minecraft:gray_concrete"},
    "water": {"id": 10, "minecraft_block": "minecraft:water"},
}
# Later entries overwrite earlier ones at intersections.
MATERIAL_PRIORITY = tuple(MATERIALS)


@dataclass(frozen=True)
class WorldBounds:
    """Half-open integer bounds for a [Z, X] output raster."""

    x_min: int
    z_min: int
    x_max: int
    z_max: int

    def __post_init__(self) -> None:
        if self.x_min >= self.x_max or self.z_min >= self.z_max:
            raise ValueError(f"invalid half-open world bounds: {self}")

    @property
    def shape_zx(self) -> tuple[int, int]:
        return (self.z_max - self.z_min, self.x_max - self.x_min)

    @property
    def affine(self) -> Affine:
        return Affine(1.0, 0.0, self.x_min, 0.0, 1.0, self.z_min)

    def as_list(self) -> list[int]:
        return [self.x_min, self.z_min, self.x_max, self.z_max]


@dataclass(frozen=True)
class SurfaceFeature:
    material: str
    geometry: BaseGeometry
    source: str
    source_id: str
    name: str


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, *, include_sha256: bool = True) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path.resolve()), "bytes": path.stat().st_size}
    if include_sha256:
        record["sha256"] = sha256_file(path)
    return record


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_deterministic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    """Write a compressed, pickle-free NPZ with stable ordering and timestamps."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for name in sorted(arrays):
            array = np.asarray(arrays[name])
            if array.ndim:
                array = np.ascontiguousarray(array)
            buffer = io.BytesIO()
            np.lib.format.write_array(
                buffer, array, allow_pickle=False
            )
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, buffer.getvalue(), compresslevel=9)


def load_geojson(path: Path) -> dict[str, Any]:
    payload = json.loads(require_file(path, "GeoJSON").read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"expected GeoJSON FeatureCollection: {path}")
    return payload


def lonlat_geometry_to_world(
    geometry: BaseGeometry, transform: WorldTransform
) -> BaseGeometry:
    def project(
        longitude: float | Sequence[float],
        latitude: float | Sequence[float],
        altitude: float | Sequence[float] | None = None,
    ) -> tuple[Any, Any]:
        if np.isscalar(longitude):
            x, z = transform.lonlat_to_block(float(longitude), float(latitude))
            return x, z
        pairs = [
            transform.lonlat_to_block(float(lon), float(lat))
            for lon, lat in zip(longitude, latitude)
        ]
        return tuple(pair[0] for pair in pairs), tuple(pair[1] for pair in pairs)

    result = geometry_transform(project, geometry)
    if not result.is_valid:
        result = result.buffer(0)
    return result


def load_property_geometry(path: Path, transform: WorldTransform) -> tuple[BaseGeometry, int]:
    geometries: list[BaseGeometry] = []
    for feature in load_geojson(path).get("features", []):
        geometry_payload = feature.get("geometry")
        if not geometry_payload:
            continue
        geometry = lonlat_geometry_to_world(shape(geometry_payload), transform)
        if not geometry.is_empty:
            geometries.append(geometry)
    if not geometries:
        raise ValueError(f"parcel GeoJSON has no usable geometry: {path}")
    from shapely.ops import unary_union

    combined = unary_union(geometries)
    if not combined.is_valid:
        combined = combined.buffer(0)
    return combined, len(geometries)


def bounds_from_geometry(geometry: BaseGeometry) -> WorldBounds:
    min_x, min_z, max_x, max_z = geometry.bounds
    return WorldBounds(
        math.floor(min_x), math.floor(min_z), math.ceil(max_x), math.ceil(max_z)
    )


def rasterize_geometry_mask(
    geometry: BaseGeometry,
    bounds: WorldBounds,
    *,
    all_touched: bool = False,
) -> np.ndarray:
    return features.rasterize(
        [(geometry, 1)],
        out_shape=bounds.shape_zx,
        transform=bounds.affine,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    ).astype(bool)


def classify_surface(tags: Mapping[str, Any], fallback_kind: str | None = None) -> str | None:
    leisure = str(tags.get("leisure") or "").lower()
    sport = str(tags.get("sport") or "").lower()
    if leisure == "swimming_pool":
        return "water"
    group = site_feature_group(dict(tags))
    if group is not None:
        return group
    if fallback_kind == "grass":
        return "grass"
    if fallback_kind == "hard":
        return "road"
    return None


def load_osm_payload(path: Path) -> tuple[dict[str, Any], dict[tuple[str, int], dict[str, Any]]]:
    payload = json.loads(require_file(path, "OSM JSON").read_text(encoding="utf-8"))
    index = {
        (str(element.get("type")), int(element["id"])): element
        for element in payload.get("elements", [])
        if element.get("id") is not None
    }
    return payload, index


def load_surface_features(
    surface_path: Path,
    osm_path: Path,
    transform: WorldTransform,
) -> tuple[list[SurfaceFeature], dict[str, Any]]:
    osm_payload, osm_index = load_osm_payload(osm_path)
    output: list[SurfaceFeature] = []
    exported_keys: set[tuple[str, int]] = set()
    source_counts: Counter[str] = Counter()
    material_counts: Counter[str] = Counter()

    for feature in load_geojson(surface_path).get("features", []):
        properties = feature.get("properties") or {}
        geometry_payload = feature.get("geometry")
        if not geometry_payload:
            continue
        osm_type = str(properties.get("osm_type") or "way")
        try:
            osm_id = int(properties["osm_id"])
        except (KeyError, TypeError, ValueError):
            osm_id = -1
        key = (osm_type, osm_id)
        tags = (osm_index.get(key) or {}).get("tags") or {}
        material = classify_surface(tags, str(properties.get("kind") or ""))
        if material is None:
            continue
        geometry = lonlat_geometry_to_world(shape(geometry_payload), transform)
        if geometry.is_empty:
            continue
        output.append(
            SurfaceFeature(
                material=material,
                geometry=geometry,
                source="exported-campus-surfaces",
                source_id=f"{osm_type}/{osm_id}",
                name=str(properties.get("name") or tags.get("name") or ""),
            )
        )
        exported_keys.add(key)
        source_counts["exported-campus-surfaces"] += 1
        material_counts[material] += 1

    for element in osm_payload.get("elements", []):
        if element.get("type") not in {"way", "relation"} or element.get("id") is None:
            continue
        key = (str(element["type"]), int(element["id"]))
        if key in exported_keys:
            continue
        tags = element.get("tags") or {}
        material = classify_surface(tags)
        if material is None:
            continue
        geometry = osm_geometry_to_block(element, transform)
        if geometry is None or geometry.is_empty:
            continue
        geometry = buffered_site_line(
            geometry, site_feature_width_blocks(material, transform, tags)
        )
        output.append(
            SurfaceFeature(
                material=material,
                geometry=geometry,
                source="osm-json",
                source_id=f"{key[0]}/{key[1]}",
                name=str(tags.get("name") or ""),
            )
        )
        source_counts["osm-json"] += 1
        material_counts[material] += 1

    return output, {
        "feature_count": len(output),
        "source_feature_counts": dict(sorted(source_counts.items())),
        "material_feature_counts": dict(sorted(material_counts.items())),
    }


def rasterize_materials(
    surface_features: Iterable[SurfaceFeature], bounds: WorldBounds
) -> tuple[np.ndarray, dict[str, Any]]:
    """Rasterize intentional classes; all unclassified cells stay grass."""

    material = np.full(
        bounds.shape_zx, MATERIALS["grass"]["id"], dtype=np.uint8
    )
    grouped: dict[str, list[BaseGeometry]] = defaultdict(list)
    used_features: Counter[str] = Counter()
    for feature in surface_features:
        if feature.geometry.intersects(
            Polygon(
                [
                    (bounds.x_min, bounds.z_min),
                    (bounds.x_max, bounds.z_min),
                    (bounds.x_max, bounds.z_max),
                    (bounds.x_min, bounds.z_max),
                ]
            )
        ):
            grouped[feature.material].append(feature.geometry)
            used_features[feature.material] += 1

    for name in MATERIAL_PRIORITY:
        geometries = grouped.get(name)
        if not geometries or name == "grass":
            continue
        class_mask = features.rasterize(
            [(geometry, 1) for geometry in geometries],
            out_shape=bounds.shape_zx,
            transform=bounds.affine,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
        material[class_mask] = MATERIALS[name]["id"]

    id_to_name = {entry["id"]: name for name, entry in MATERIALS.items()}
    ids, counts = np.unique(material, return_counts=True)
    return material, {
        "features_intersecting_bounds": dict(sorted(used_features.items())),
        "cell_counts": {
            id_to_name[int(material_id)]: int(count)
            for material_id, count in zip(ids, counts)
        },
    }


def horizontal_crs(crs: CRS) -> CRS:
    return crs.sub_crs_list[0] if crs.is_compound else crs


def block_centres_to_ecef(
    transform: WorldTransform, bounds: WorldBounds
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.arange(bounds.x_min, bounds.x_max, dtype=np.float64) + 0.5
    z = np.arange(bounds.z_min, bounds.z_max, dtype=np.float64) + 0.5
    world_x, world_z = np.meshgrid(x, z)
    east, _up, south = transform._basis()
    scale = transform.blocks_per_metre
    ecef = []
    for axis in range(3):
        ecef.append(
            transform.origin_ecef[axis]
            + east[axis] * world_x / scale
            + south[axis] * world_z / scale
        )
    return ecef[0], ecef[1], ecef[2]


def block_centres_to_crs(
    transform: WorldTransform, bounds: WorldBounds, target_crs: CRS
) -> tuple[np.ndarray, np.ndarray]:
    ecef_x, ecef_y, ecef_z = block_centres_to_ecef(transform, bounds)
    transformer = Transformer.from_crs("EPSG:4978", horizontal_crs(target_crs), always_xy=True)
    projected = transformer.transform(ecef_x, ecef_y, ecef_z)
    return np.asarray(projected[0]), np.asarray(projected[1])


def dem_intersects(bounds: Sequence[float], sample_bounds: Sequence[float]) -> bool:
    return not (
        bounds[2] <= sample_bounds[0]
        or bounds[0] >= sample_bounds[2]
        or bounds[3] <= sample_bounds[1]
        or bounds[1] >= sample_bounds[3]
    )


def resolve_dem_paths(
    requested_dem: Path | None,
    default_dem: Path,
    tile_dir: Path,
    sample_bounds: Sequence[float],
) -> tuple[list[Path], str]:
    if requested_dem is not None:
        return [require_file(requested_dem, "DEM")], "explicit"
    if default_dem.is_file():
        with rasterio.open(default_dem) as source:
            if dem_intersects(source.bounds, sample_bounds) and (
                source.bounds.left <= sample_bounds[0]
                and source.bounds.bottom <= sample_bounds[1]
                and source.bounds.right >= sample_bounds[2]
                and source.bounds.top >= sample_bounds[3]
            ):
                return [default_dem], "default-campus-crop"
    paths: list[Path] = []
    for path in sorted(tile_dir.glob("*.tif")):
        with rasterio.open(path) as source:
            if dem_intersects(source.bounds, sample_bounds):
                paths.append(path)
    if not paths:
        raise ValueError(f"no DEM covers projected sample bounds {tuple(sample_bounds)}")
    return paths, "dem-d24-tiles"


def sample_dem_at_block_centres(
    transform: WorldTransform,
    bounds: WorldBounds,
    *,
    requested_dem: Path | None,
    default_dem: Path,
    tile_dir: Path,
) -> tuple[np.ndarray, dict[str, Any]]:
    probe_path = requested_dem or default_dem
    if not probe_path.is_file():
        probe_path = next(iter(sorted(tile_dir.glob("*.tif"))), probe_path)
    with rasterio.open(require_file(probe_path, "DEM or DEM tile")) as probe:
        if probe.crs is None:
            raise ValueError(f"DEM has no CRS: {probe_path}")
        dem_crs = CRS.from_user_input(probe.crs)
    sample_x, sample_y = block_centres_to_crs(transform, bounds, dem_crs)
    sample_bounds = (
        float(np.min(sample_x)) - 1.0,
        float(np.min(sample_y)) - 1.0,
        float(np.max(sample_x)) + 1.0,
        float(np.max(sample_y)) + 1.0,
    )
    paths, mode = resolve_dem_paths(
        requested_dem, default_dem, tile_dir, sample_bounds
    )
    sources = [rasterio.open(path) for path in paths]
    try:
        source_crs = CRS.from_user_input(sources[0].crs)
        for source in sources[1:]:
            if horizontal_crs(CRS.from_user_input(source.crs)) != horizontal_crs(source_crs):
                raise ValueError("DEM sources do not share a horizontal CRS")
        resolution = min(abs(float(source.res[0])) for source in sources)
        mosaic, mosaic_transform = merge(
            sources,
            bounds=sample_bounds,
            res=resolution,
            nodata=np.nan,
            dtype="float32",
            masked=True,
        )
        values = np.asarray(mosaic[0].filled(np.nan), dtype=np.float32)
    finally:
        for source in sources:
            source.close()

    inverse = ~mosaic_transform
    pixel_col, pixel_row = inverse * (sample_x, sample_y)
    elevations = map_coordinates(
        values,
        [pixel_row - 0.5, pixel_col - 0.5],
        order=1,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    ).astype(np.float32)
    missing = int(np.count_nonzero(~np.isfinite(elevations)))
    if missing:
        raise ValueError(
            f"DEM has {missing} nodata block-centre samples within bounds {bounds.as_list()}"
        )
    return elevations, {
        "mode": mode,
        "vertical_datum": "NAVD88 height - Geoid18 (metres)",
        "horizontal_crs": horizontal_crs(source_crs).to_string(),
        "native_resolution_m": resolution,
        "sampling": "bilinear at world block centres (x+0.5, z+0.5)",
        "nodata_sample_count": missing,
        "sources": [file_record(path) for path in paths],
    }


def datum_evidence(path: Path, chosen_offset: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "chosen_navd88_to_world_y_offset_blocks": float(chosen_offset),
        "application": "ground_y = round(NAVD88_metres + fixed_offset_blocks)",
        "scope": "single campus-wide datum; no per-building shifts",
    }
    if not path.is_file():
        result["evidence"] = "built-in robust v15 anchor statistic; evidence file unavailable"
        return result
    payload = json.loads(path.read_text(encoding="utf-8"))
    anchors = ((payload.get("overlay") or {}).get("anchors") or [])
    accepted = [
        float(anchor["vertical_offset"])
        for anchor in anchors
        if float(anchor.get("source_column_coverage", 0.0)) >= 0.9
        and 15.0 <= float(anchor.get("vertical_offset", math.nan)) <= 35.0
    ]
    if accepted:
        values = np.asarray(accepted, dtype=np.float64)
        median = float(np.median(values))
        result.update(
            {
                "evidence_manifest": file_record(path),
                "filter": "source_column_coverage >= 0.90 and 15 <= vertical_offset <= 35",
                "accepted_anchor_count": len(accepted),
                "accepted_anchor_median_blocks": median,
                "accepted_anchor_mad_blocks": float(np.median(np.abs(values - median))),
                "chosen_minus_evidence_median_blocks": float(chosen_offset - median),
            }
        )
    return result


def validate_chapel_landmark(
    buildings_path: Path, transform: WorldTransform
) -> dict[str, Any]:
    matches = []
    for feature in load_geojson(buildings_path).get("features", []):
        properties = feature.get("properties") or {}
        if str(properties.get("STRUCTUREID")) == CHAPEL_STRUCTURE_ID:
            matches.append(feature)
    if len(matches) != 1:
        raise ValueError(
            f"expected one {CHAPEL_STRUCTURE_ID} landmark, found {len(matches)}"
        )
    centroid = shape(matches[0]["geometry"]).centroid
    actual = transform.lonlat_to_block(float(centroid.x), float(centroid.y))
    error = math.hypot(
        actual[0] - CHAPEL_EXPECTED_WORLD_XZ[0],
        actual[1] - CHAPEL_EXPECTED_WORLD_XZ[1],
    )
    if error > 0.05:
        raise ValueError(f"Chapel world-transform landmark error is {error:.6f} blocks")
    return {
        "structure_id": CHAPEL_STRUCTURE_ID,
        "centroid_lonlat": [float(centroid.x), float(centroid.y)],
        "expected_world_xz": list(CHAPEL_EXPECTED_WORLD_XZ),
        "actual_world_xz": [float(actual[0]), float(actual[1])],
        "horizontal_error_blocks": error,
    }


def terrain_stats(
    elevation_m: np.ndarray,
    ground_y: np.ndarray,
    property_mask: np.ndarray,
) -> dict[str, Any]:
    float_differences = np.concatenate(
        [
            np.abs(np.diff(elevation_m, axis=0)).ravel(),
            np.abs(np.diff(elevation_m, axis=1)).ravel(),
        ]
    )
    block_differences = np.concatenate(
        [
            np.abs(np.diff(ground_y.astype(np.int32), axis=0)).ravel(),
            np.abs(np.diff(ground_y.astype(np.int32), axis=1)).ravel(),
        ]
    )
    return {
        "shape_zx": list(elevation_m.shape),
        "navd88_elevation_min_max_m": [
            float(np.min(elevation_m)),
            float(np.max(elevation_m)),
        ],
        "ground_y_min_max": [int(np.min(ground_y)), int(np.max(ground_y))],
        "property_cells": int(np.count_nonzero(property_mask)),
        "property_fraction": float(np.mean(property_mask)),
        "adjacent_dem_delta_m": {
            "p50": float(np.percentile(float_differences, 50)),
            "p95": float(np.percentile(float_differences, 95)),
            "p99": float(np.percentile(float_differences, 99)),
            "max": float(np.max(float_differences)),
        },
        "adjacent_ground_y_delta_blocks": {
            "p95": float(np.percentile(block_differences, 95)),
            "p99": float(np.percentile(block_differences, 99)),
            "max": int(np.max(block_differences)),
        },
    }


def build_terrain(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = require_file(args.world_manifest.resolve(), "VoxelEarth manifest")
    transform = WorldTransform.from_manifest(manifest_path)
    if not math.isclose(transform.blocks_per_metre, 1.0):
        raise ValueError("measured terrain currently requires one VoxelEarth block per metre")

    parcels_path = require_file(args.parcels.resolve(), "Hill parcel GeoJSON")
    property_geometry, parcel_count = load_property_geometry(parcels_path, transform)
    bounds = (
        WorldBounds(*args.bounds)
        if args.bounds is not None
        else bounds_from_geometry(property_geometry)
    )
    property_mask = rasterize_geometry_mask(property_geometry, bounds)

    elevation_m, dem_manifest = sample_dem_at_block_centres(
        transform,
        bounds,
        requested_dem=args.dem.resolve() if args.dem is not None else None,
        default_dem=args.default_dem.resolve(),
        tile_dir=args.dem_tile_dir.resolve(),
    )
    ground_y = np.rint(elevation_m + args.vertical_offset).astype(np.int16)

    surface_features, surface_load_stats = load_surface_features(
        args.surfaces.resolve(), args.osm.resolve(), transform
    )
    material_id, material_stats = rasterize_materials(surface_features, bounds)
    landmark = validate_chapel_landmark(args.buildings.resolve(), transform)
    stats = terrain_stats(elevation_m, ground_y, property_mask)

    output_path = args.output.resolve()
    manifest_out = (
        args.manifest.resolve()
        if args.manifest is not None
        else output_path.with_suffix(".manifest.json")
    )
    metadata = {
        "format": "hill-measured-terrain-v1",
        "axis": "+X east, +Y up, +Z south (north is -Z)",
        "array_order": "[z, x] with row 0 at z_min",
        "bounds_semantics": "half-open [x_min, x_max) x [z_min, z_max)",
        "world_bounds": bounds.as_list(),
        "shape_zx": list(bounds.shape_zx),
        "block_sample_point": "column centre (x+0.5, z+0.5)",
        "materials": MATERIALS,
        "default_surface": "grass",
    }
    arrays = {
        "ground_y": ground_y,
        "ground_elevation_navd88_m": elevation_m.astype(np.float32, copy=False),
        "material_id": material_id,
        "property_mask": property_mask.astype(np.uint8),
        "x_min": np.asarray(bounds.x_min, dtype=np.int32),
        "z_min": np.asarray(bounds.z_min, dtype=np.int32),
        "metadata_json": np.asarray(
            json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        ),
    }
    write_deterministic_npz(output_path, arrays)

    output_manifest: dict[str, Any] = {
        **metadata,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "output": file_record(output_path),
        "voxelearth_manifest": file_record(manifest_path),
        "world_transform": {
            "origin_ecef_metres": list(transform.origin_ecef),
            "center_latitude_longitude": [
                transform.center_latitude,
                transform.center_longitude,
            ],
            "blocks_per_metre": transform.blocks_per_metre,
            "target_minimum_y": transform.target_minimum_y,
        },
        "datum": datum_evidence(args.datum_evidence.resolve(), args.vertical_offset),
        "dem": dem_manifest,
        "property": {
            "source": file_record(parcels_path),
            "parcel_feature_count": parcel_count,
            "mask_definition": "cell centre is inside the exact parcel union",
        },
        "surfaces": {
            "osm": file_record(args.osm.resolve()),
            "exported": file_record(args.surfaces.resolve()),
            "load_stats": surface_load_stats,
            "raster_stats": material_stats,
        },
        "landmark_validation": landmark,
        "terrain_stats": stats,
        "terrain_only": True,
        "contains_buildings": False,
        "contains_trees": False,
    }
    write_json(manifest_out, output_manifest)
    output_manifest["manifest_path"] = str(manifest_out)
    return output_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world-manifest", type=Path, default=DEFAULT_WORLD_MANIFEST)
    parser.add_argument("--dem", type=Path, default=None, help="Explicit covering DEM GeoTIFF")
    parser.add_argument("--default-dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--dem-tile-dir", type=Path, default=DEFAULT_DEM_TILE_DIR)
    parser.add_argument("--parcels", type=Path, default=DEFAULT_PARCELS)
    parser.add_argument("--buildings", type=Path, default=DEFAULT_BUILDINGS)
    parser.add_argument("--osm", type=Path, default=DEFAULT_OSM)
    parser.add_argument("--surfaces", type=Path, default=DEFAULT_SURFACES)
    parser.add_argument("--datum-evidence", type=Path, default=DEFAULT_DATUM_EVIDENCE)
    parser.add_argument(
        "--vertical-offset",
        type=float,
        default=DEFAULT_NAVD88_TO_WORLD_Y_OFFSET,
        help="Single campus-wide NAVD88 metres to VoxelEarth world-Y offset",
    )
    parser.add_argument(
        "--bounds",
        type=int,
        nargs=4,
        metavar=("X_MIN", "Z_MIN", "X_MAX", "Z_MAX"),
        help="Optional half-open VoxelEarth bounds; default is the full parcel-union bbox",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    result = build_terrain(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
