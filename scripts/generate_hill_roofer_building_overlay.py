"""Generate a sparse, building-only Hill campus voxel overlay.

The script deliberately does not generate terrain, land cover, vegetation, or
water.  VoxelEarth remains the source of every ground cell.  This wrapper only
loads Roofer's georeferenced LoD2.2 OBJ, runs the vendored VoxCity importer
functions unchanged, clips the occupied cells to Hill property and the full
VoxelEarth capture bounds, and writes a compact deterministic NPZ.

Axis contract
-------------
``occupied_neu`` stores integer cells as ``(north, east, up)``.  North/east
are zero-based offsets from ``metric_origin_neu_m``.  Up is the one-metre
NAVD88 elevation cell; VoxCity's internal ``+1`` terrain seating offset is
removed because this artifact intentionally contains no terrain.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

import geopandas as gpd
import numpy as np
from affine import Affine
from pyproj import Transformer
from rasterio import features
from shapely.geometry.base import BaseGeometry


REPO_ROOT = Path(__file__).resolve().parents[1]
VOXCITY_SRC = REPO_ROOT / "runtime/vendor/VoxCity/src"
TRIAL_DIR = REPO_ROOT / "runtime/campus-reconstruction/roofer-chapel-trial"

DEFAULT_OBJ = TRIAL_DIR / "campus-model/hill-campus-roofer-lod22.obj"
DEFAULT_CITYJSON = TRIAL_DIR / "campus-model/hill-campus-roofer.city.json"
DEFAULT_FOOTPRINTS = TRIAL_DIR / "inputs/hill-buildings-full-unique-epsg6347.geojson"
DEFAULT_PARCELS = REPO_ROOT / "runtime/campus-data/gis/montco-hill-parcels-full.geojson"
DEFAULT_VOXELEARTH_MANIFEST = (
    REPO_ROOT
    / "runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831"
    / "paper-runtime-wallclean-v7-1226"
    / "hill_school_voxelearth_full_groundfallback_v11_1xg64_20260831_1346"
    / "voxelearth-hill-manifest.json"
)
DEFAULT_OUTPUT_DIR = TRIAL_DIR / "roofer-building-overlay-1m"
DEFAULT_OUTPUT_STEM = "hill-campus-roofer-lod22-buildings-only-1m"
DEFAULT_METRIC_CRS = "EPSG:6347"

VOXCITY_TERRAIN_SEATING_OFFSET_CELLS = 1
WGS84_A_M = 6_378_137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


@dataclass(frozen=True)
class MetricDomain:
    """Axis-aligned metric domain, ordered east then north in its bounds."""

    crs: str
    min_east_m: float
    min_north_m: float
    max_east_m: float
    max_north_m: float
    meshsize_m: float

    @property
    def width_m(self) -> float:
        return self.max_east_m - self.min_east_m

    @property
    def height_m(self) -> float:
        return self.max_north_m - self.min_north_m

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (
            self.min_east_m,
            self.min_north_m,
            self.max_east_m,
            self.max_north_m,
        )


@dataclass
class OverlayResult:
    occupied_neu: np.ndarray
    building_ids: np.ndarray
    building_table: list[dict[str, Any]]
    stats: dict[str, Any]
    transform_model_to_voxcity_ijk: np.ndarray
    grid_shape_ne: tuple[int, int]
    rectangle_vertices_lonlat: list[tuple[float, float]]


def ensure_voxcity_on_path(path: Path) -> None:
    resolved = str(path.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"{label} is empty: {path}")
    return path


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def file_manifest(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": repo_path(path),
        "bytes": int(stat.st_size),
        "sha256": sha256_file(path),
    }


def git_revision(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
        return None if math.isnan(value) else value
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def write_deterministic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    """Write a compressed NPZ with stable member order and ZIP timestamps."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for name in sorted(arrays):
            array = np.ascontiguousarray(arrays[name])
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, array, allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, buffer.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _union_geometries(geometries: Any) -> BaseGeometry:
    if hasattr(geometries, "union_all"):
        return geometries.union_all()
    return geometries.unary_union


def load_property_geometry(parcel_path: Path, metric_crs: str) -> tuple[int, BaseGeometry]:
    parcels = gpd.read_file(require_file(parcel_path, "Hill parcel GeoJSON"))
    if parcels.empty:
        raise ValueError(f"Hill parcel GeoJSON has no features: {parcel_path}")
    if parcels.crs is None:
        raise ValueError(f"Hill parcel GeoJSON has no CRS: {parcel_path}")
    parcels = parcels.to_crs(metric_crs)
    valid = parcels.geometry.notna() & ~parcels.geometry.is_empty
    parcels = parcels.loc[valid].copy()
    if parcels.empty:
        raise ValueError(f"Hill parcel GeoJSON has no usable geometry: {parcel_path}")
    geometry = _union_geometries(parcels.geometry)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise ValueError(f"Hill parcel union is empty: {parcel_path}")
    return int(len(parcels)), geometry


def _snap_domain(
    bounds: Sequence[float],
    *,
    metric_crs: str,
    meshsize_m: float,
) -> MetricDomain:
    if meshsize_m <= 0:
        raise ValueError("meshsize must be positive")
    min_e, min_n, max_e, max_n = (float(v) for v in bounds)
    min_e = math.floor(min_e / meshsize_m) * meshsize_m
    min_n = math.floor(min_n / meshsize_m) * meshsize_m
    max_e = math.ceil(max_e / meshsize_m) * meshsize_m
    max_n = math.ceil(max_n / meshsize_m) * meshsize_m
    if min_e >= max_e or min_n >= max_n:
        raise ValueError(f"degenerate metric domain: {bounds}")
    return MetricDomain(metric_crs, min_e, min_n, max_e, max_n, meshsize_m)


def wgs84_latlon_to_ecef(
    latitude: Any,
    longitude: Any,
    altitude_m: Any = 0.0,
) -> np.ndarray:
    """Python parity with VoxelEarth ``GeoReference.latLonToEcef``."""

    latitude = np.asarray(latitude, dtype=np.float64)
    longitude = np.asarray(longitude, dtype=np.float64)
    altitude_m = np.asarray(altitude_m, dtype=np.float64)
    lat = np.radians(latitude)
    lon = np.radians(longitude)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    radius = WGS84_A_M / np.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    return np.stack(
        [
            (radius + altitude_m) * cos_lat * np.cos(lon),
            (radius + altitude_m) * cos_lat * np.sin(lon),
            (radius * (1.0 - WGS84_E2) + altitude_m) * sin_lat,
        ],
        axis=-1,
    )


def wgs84_ecef_to_latlon(ecef_xyz: Sequence[float]) -> tuple[float, float, float]:
    """Python parity with VoxelEarth ``GeoReference.ecefToLatLon``."""

    x, y, z = (float(value) for value in ecef_xyz)
    longitude = math.atan2(y, x)
    horizontal = math.hypot(x, y)
    latitude = math.atan2(z, horizontal * (1.0 - WGS84_E2))
    altitude = 0.0
    for _ in range(12):
        sin_lat = math.sin(latitude)
        radius = WGS84_A_M / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        altitude = horizontal / math.cos(latitude) - radius
        next_latitude = math.atan2(
            z,
            horizontal * (1.0 - WGS84_E2 * radius / (radius + altitude)),
        )
        if abs(next_latitude - latitude) < 1.0e-13:
            latitude = next_latitude
            break
        latitude = next_latitude
    return math.degrees(latitude), math.degrees(longitude), altitude


def voxelearth_ecef_basis(origin_ecef_m: Sequence[float]) -> np.ndarray:
    """Rows are VoxelEarth east, geodetic-up, and south unit vectors."""

    latitude, longitude, _altitude = wgs84_ecef_to_latlon(origin_ecef_m)
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    return np.asarray(
        [
            [-sin_lon, cos_lon, 0.0],
            [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat],
            [sin_lat * cos_lon, sin_lat * sin_lon, -cos_lat],
        ],
        dtype=np.float64,
    )


def metric_east_north_to_voxelearth_world_xyz(
    east_m: Any,
    north_m: Any,
    *,
    metric_crs: str,
    origin_ecef_m: Sequence[float],
    blocks_per_metre: float,
    ellipsoid_altitude_m: float = 0.0,
) -> np.ndarray:
    """Map projected E/N through WGS84 ECEF into exact VoxelEarth X/Y/Z.

    This intentionally mirrors ``GeoReference.latLonToMinecraftMetres``.
    Horizontal footprint alignment uses ellipsoid altitude zero, exactly as
    VoxelEarth's parcel/building mask projection does.
    """

    if blocks_per_metre <= 0:
        raise ValueError("blocks_per_metre must be positive")
    east = np.asarray(east_m, dtype=np.float64)
    north = np.asarray(north_m, dtype=np.float64)
    east, north = np.broadcast_arrays(east, north)
    to_lonlat = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)
    longitude, latitude = to_lonlat.transform(east, north)
    ecef = wgs84_latlon_to_ecef(latitude, longitude, ellipsoid_altitude_m)
    origin = np.asarray(origin_ecef_m, dtype=np.float64)
    basis = voxelearth_ecef_basis(origin)
    local_xyz_m = (ecef - origin) @ basis.T
    return local_xyz_m * float(blocks_per_metre)


def domain_from_voxelearth_manifest(
    manifest_path: Path,
    *,
    metric_crs: str,
    meshsize_m: float,
) -> tuple[MetricDomain, dict[str, Any]]:
    """Recover the inclusive VoxelEarth world footprint in the metric CRS."""

    with require_file(manifest_path, "VoxelEarth Hill manifest").open(
        "r", encoding="utf-8"
    ) as handle:
        manifest = json.load(handle)

    if manifest.get("axis") != "+X east, +Y up, +Z south (north is -Z)":
        raise ValueError(f"unsupported VoxelEarth axis contract: {manifest.get('axis')!r}")
    center = manifest.get("center")
    result = manifest.get("result") or {}
    minimum = result.get("minimumBlock")
    maximum = result.get("maximumBlock")
    if not (isinstance(center, list) and len(center) == 2):
        raise ValueError("VoxelEarth manifest is missing center [lat, lon]")
    if not (isinstance(minimum, list) and len(minimum) == 3):
        raise ValueError("VoxelEarth manifest is missing result.minimumBlock")
    if not (isinstance(maximum, list) and len(maximum) == 3):
        raise ValueError("VoxelEarth manifest is missing result.maximumBlock")

    metres_per_block = float(manifest.get("metresPerBlock", 1.0))
    if metres_per_block <= 0:
        raise ValueError("VoxelEarth metresPerBlock must be positive")
    lat, lon = float(center[0]), float(center[1])
    to_metric = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
    center_e, center_n = to_metric.transform(lon, lat)

    # Block bounds are inclusive.  +X is east and +Z is south.
    min_e = center_e + float(minimum[0]) * metres_per_block
    max_e = center_e + (float(maximum[0]) + 1.0) * metres_per_block
    min_n = center_n - (float(maximum[2]) + 1.0) * metres_per_block
    max_n = center_n - float(minimum[2]) * metres_per_block
    domain = _snap_domain(
        (min_e, min_n, max_e, max_n),
        metric_crs=metric_crs,
        meshsize_m=meshsize_m,
    )
    alignment = {
        "center_latlon": [lat, lon],
        "center_metric_east_north_m": [float(center_e), float(center_n)],
        "source_minimum_block_xyz": [int(v) for v in minimum],
        "source_maximum_block_xyz": [int(v) for v in maximum],
        "metres_per_block": metres_per_block,
        "blocks_per_metre": 1.0 / metres_per_block,
        "world_axis": manifest["axis"],
        "origin_ecef_m": [float(value) for value in manifest["originEcefMetres"]],
        "ecef_to_world_xyz_basis_rows": voxelearth_ecef_basis(
            manifest["originEcefMetres"]
        ).tolist(),
        "metric_to_world_block": {
            "method": "exact WGS84 ECEF tangent frame; never subtract projected origins",
            "source_crs": metric_crs,
            "steps": [
                "transform projected east,north to WGS84 longitude,latitude",
                "ECEF = WGS84(latitude, longitude, ellipsoid_altitude=0)",
                "delta = ECEF - origin_ecef_m",
                "world_xyz = ecef_to_world_xyz_basis_rows @ delta * blocks_per_metre",
            ],
            "world_x": "dot(east_basis, ECEF - origin_ecef_m) * blocks_per_metre",
            "world_z": "dot(south_basis, ECEF - origin_ecef_m) * blocks_per_metre",
            "forbidden_approximation": "x=east-center_east; z=center_north-north",
        },
    }
    return domain, alignment


def domain_from_property(
    property_geometry: BaseGeometry,
    *,
    metric_crs: str,
    meshsize_m: float,
) -> MetricDomain:
    return _snap_domain(
        property_geometry.bounds,
        metric_crs=metric_crs,
        meshsize_m=meshsize_m,
    )


def rectangle_vertices_lonlat(domain: MetricDomain) -> list[tuple[float, float]]:
    to_lonlat = Transformer.from_crs(domain.crs, "EPSG:4326", always_xy=True)
    return [
        to_lonlat.transform(domain.min_east_m, domain.min_north_m),
        to_lonlat.transform(domain.min_east_m, domain.max_north_m),
        to_lonlat.transform(domain.max_east_m, domain.max_north_m),
        to_lonlat.transform(domain.max_east_m, domain.min_north_m),
    ]


def make_voxcity_transform(
    domain: MetricDomain,
) -> tuple[np.ndarray, tuple[int, int], list[tuple[float, float]]]:
    """Build the official VoxCity model->(north,east,up) index transform."""

    from voxcity.geoprocessor.raster.core import compute_grid_geometry
    from voxcity.importer.transform import build_placement_transform

    vertices = rectangle_vertices_lonlat(domain)
    geom = compute_grid_geometry(vertices, domain.meshsize_m)
    if geom is None:
        raise ValueError("VoxCity could not compute grid geometry")
    grid_shape_ne = tuple(int(v) for v in geom["grid_size"])

    # A minimal, terrain-free carrier gives the unchanged VoxCity transform
    # exactly the metadata it requires.  The zero DEM only defines a vertical
    # datum; no DEM cells are generated or exported.
    carrier = SimpleNamespace(
        extras={"rectangle_vertices": vertices},
        voxels=SimpleNamespace(meta=SimpleNamespace(meshsize=domain.meshsize_m)),
        dem=SimpleNamespace(elevation=np.zeros((1, 1), dtype=np.float32)),
    )
    anchor_e = (domain.min_east_m + domain.max_east_m) * 0.5
    anchor_n = (domain.min_north_m + domain.max_north_m) * 0.5
    to_lonlat = Transformer.from_crs(domain.crs, "EPSG:4326", always_xy=True)
    anchor_lonlat = to_lonlat.transform(anchor_e, anchor_n)
    # Roofer coordinates are axes of the projected metric CRS, whereas the
    # public VoxCity transform describes model X/Y as true east/north.  Cancel
    # the transform's own domain-bearing term so projected +X/+Y land exactly
    # on the domain's east/north grid axes (no campus-scale convergence drift).
    u_vec = np.asarray(geom["u_vec"], dtype=np.float64)
    domain_rotation_deg = math.degrees(math.atan2(u_vec[0], u_vec[1]))
    transform = build_placement_transform(
        carrier,
        anchor_lonlat=anchor_lonlat,
        anchor_elevation=0.0,
        anchor_model_point=(anchor_e, anchor_n, 0.0),
        rotation=-domain_rotation_deg,
        move=(0.0, 0.0, 0.0),
        units="m",
    )
    return np.asarray(transform, dtype=np.float64), grid_shape_ne, vertices


def rasterize_property_mask(
    property_geometry: BaseGeometry,
    domain: MetricDomain,
    shape_ne: tuple[int, int],
    *,
    boundary_m: float,
    all_touched: bool,
) -> np.ndarray:
    """Return a south-up mask whose axes match VoxCity (north, east)."""

    if boundary_m < 0:
        raise ValueError("property boundary cannot be negative")
    north_cells, east_cells = shape_ne
    geometry = property_geometry.buffer(boundary_m) if boundary_m else property_geometry
    if geometry.is_empty:
        raise ValueError("buffered Hill property geometry is empty")
    transform = Affine(
        domain.width_m / east_cells,
        0.0,
        domain.min_east_m,
        0.0,
        -(domain.height_m / north_cells),
        domain.max_north_m,
    )
    north_up = features.rasterize(
        [(geometry, 1)],
        out_shape=(north_cells, east_cells),
        transform=transform,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    ).astype(bool)
    return np.flipud(north_up)


def transformed_top_k(mesh: Any, transform: np.ndarray) -> int:
    bounds = np.asarray(mesh.bounds, dtype=np.float64)
    corners = np.array(
        [
            [bounds[x, 0], bounds[y, 1], bounds[z, 2], 1.0]
            for x in (0, 1)
            for y in (0, 1)
            for z in (0, 1)
        ],
        dtype=np.float64,
    )
    transformed = corners @ transform.T
    return int(math.ceil(float(np.max(transformed[:, 2])))) + 1


def read_obj_object_names(obj_path: Path) -> list[str]:
    names: list[str] = []
    with require_file(obj_path, "Roofer LoD2 OBJ").open(
        "r", encoding="utf-8", errors="replace"
    ) as handle:
        for line in handle:
            if line.startswith("o "):
                name = line[2:].strip()
                if name:
                    names.append(name)
    return names


def load_roofer_metadata(
    footprints_path: Path,
    cityjson_path: Path,
    *,
    metric_crs: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return parent metadata and Roofer BuildingPart->Building mapping."""

    footprints = gpd.read_file(require_file(footprints_path, "Roofer footprints"))
    if footprints.crs is None:
        raise ValueError(f"Roofer footprints have no CRS: {footprints_path}")
    footprints = footprints.to_crs(metric_crs)
    if "ROOFER_ID" not in footprints.columns:
        raise ValueError("Roofer footprints are missing ROOFER_ID")
    if footprints["ROOFER_ID"].duplicated().any():
        raise ValueError("Roofer footprints contain duplicate ROOFER_ID values")

    metadata: dict[str, dict[str, Any]] = {}
    for _, row in footprints.iterrows():
        roofer_id = str(row["ROOFER_ID"])
        raw = {
            key: _json_value(row.get(key))
            for key in (
                "PARID",
                "STRUCTUREID",
                "Height",
                "STORIES",
                "SFLA",
                "IMPRNAME",
                "DESCRIPTION",
                "Category",
                "YRBLT",
            )
        }
        label = raw.get("IMPRNAME") or raw.get("DESCRIPTION") or raw.get("Category")
        raw.update(
            {
                "roofer_id": roofer_id,
                "name": str(label or raw.get("STRUCTUREID") or roofer_id),
                "footprint_area_m2": float(row.geometry.area),
            }
        )
        metadata[roofer_id] = raw

    with require_file(cityjson_path, "Roofer CityJSON").open("r", encoding="utf-8") as handle:
        cityjson = json.load(handle)
    child_to_parent: dict[str, str] = {}
    city_objects = cityjson.get("CityObjects") or {}
    for object_id, obj in city_objects.items():
        if obj.get("type") != "Building":
            continue
        parent_id = str(object_id)
        for child_id in obj.get("children") or []:
            child_to_parent[str(child_id)] = parent_id
        # Merge Roofer's reconstruction QA attributes without replacing the
        # authoritative county attributes already loaded above.
        if parent_id in metadata:
            attributes = obj.get("attributes") or {}
            metadata[parent_id]["roofer_qa"] = {
                key: _json_value(value)
                for key, value in attributes.items()
                if key.startswith("rf_")
            }
    return metadata, child_to_parent


def resolve_group_parent(
    group_name: str,
    metadata: Mapping[str, Mapping[str, Any]],
    child_to_parent: Mapping[str, str],
) -> str:
    if group_name in child_to_parent:
        return child_to_parent[group_name]
    if group_name in metadata:
        return group_name
    # Roofer normally names LoD2 parts ``<ROOFER_ID>-0`` (or -1, ...).
    candidate, separator, suffix = group_name.rpartition("-")
    if separator and suffix.isdigit() and candidate in metadata:
        return candidate
    raise KeyError(f"OBJ group {group_name!r} has no Roofer parent building")


def map_group_parents(
    group_names: Iterable[str],
    metadata: Mapping[str, Mapping[str, Any]],
    child_to_parent: Mapping[str, str],
) -> dict[str, str]:
    return {
        name: resolve_group_parent(name, metadata, child_to_parent)
        for name in group_names
    }


def _string_array(values: Sequence[str]) -> np.ndarray:
    width = max(1, *(len(value) for value in values))
    return np.asarray(values, dtype=f"<U{width}")


def voxelize_groups(
    groups: Sequence[tuple[str, Any]],
    *,
    group_to_parent: Mapping[str, str],
    metadata: Mapping[str, Mapping[str, Any]],
    domain: MetricDomain,
    property_geometry: BaseGeometry,
    property_boundary_m: float,
    mask_all_touched: bool,
) -> OverlayResult:
    """Voxelize already loaded OBJ groups using VoxCity's unchanged engine."""

    from voxcity.importer.voxelize import voxelize_mesh

    transform, grid_shape_ne, vertices = make_voxcity_transform(domain)
    keep_mask = rasterize_property_mask(
        property_geometry,
        domain,
        grid_shape_ne,
        boundary_m=property_boundary_m,
        all_touched=mask_all_touched,
    )

    ordered_parents = sorted(set(group_to_parent.values()))
    unknown = [parent for parent in ordered_parents if parent not in metadata]
    if unknown:
        raise KeyError(f"missing metadata for Roofer parents: {unknown[:5]}")
    stable_ids = {parent: index for index, parent in enumerate(ordered_parents, start=1)}

    max_k = max((transformed_top_k(mesh, transform) for _, mesh in groups), default=1)
    voxelize_shape = (grid_shape_ne[0], grid_shape_ne[1], max(1, max_k))

    cells_parts: list[np.ndarray] = []
    id_parts: list[np.ndarray] = []
    raw_counts = {parent: 0 for parent in ordered_parents}
    clipped_counts = {parent: 0 for parent in ordered_parents}
    group_counts = {parent: 0 for parent in ordered_parents}
    voxelized_groups = 0
    empty_groups = 0

    for group_name, mesh in sorted(groups, key=lambda item: item[0]):
        parent = group_to_parent[group_name]
        group_counts[parent] += 1
        occupied = voxelize_mesh(mesh, transform, voxelize_shape)
        raw_counts[parent] += int(len(occupied))
        if not len(occupied):
            empty_groups += 1
            continue
        voxelized_groups += 1
        inside = keep_mask[occupied[:, 0], occupied[:, 1]]
        occupied = occupied[inside]
        clipped_counts[parent] += int(len(occupied))
        if not len(occupied):
            continue
        occupied = occupied.astype(np.int32, copy=False)
        occupied[:, 2] -= VOXCITY_TERRAIN_SEATING_OFFSET_CELLS
        cells_parts.append(occupied)
        id_parts.append(
            np.full(len(occupied), stable_ids[parent], dtype=np.uint16)
        )

    if not cells_parts:
        raise ValueError("Roofer geometry produced no occupied cells inside Hill property")

    cells = np.concatenate(cells_parts, axis=0)
    ids = np.concatenate(id_parts, axis=0)
    before_overlap_resolution = int(len(cells))

    # Deterministic overlap rule: sort by (north, east, up, stable id) and keep
    # the lowest stable parent id for any shared cell.
    order = np.lexsort((ids, cells[:, 2], cells[:, 1], cells[:, 0]))
    cells = cells[order]
    ids = ids[order]
    unique = np.ones(len(cells), dtype=bool)
    unique[1:] = np.any(cells[1:] != cells[:-1], axis=1)
    cells = cells[unique]
    ids = ids[unique]

    final_counts_array = np.bincount(ids.astype(np.int64), minlength=len(ordered_parents) + 1)
    building_table: list[dict[str, Any]] = []
    for parent in ordered_parents:
        stable_id = stable_ids[parent]
        entry = dict(metadata[parent])
        entry.update(
            {
                "id": stable_id,
                "obj_group_count": int(group_counts[parent]),
                "raw_voxel_count": int(raw_counts[parent]),
                "parcel_clipped_voxel_count": int(clipped_counts[parent]),
                "final_voxel_count": int(final_counts_array[stable_id]),
            }
        )
        building_table.append(entry)

    stats = {
        "input_obj_groups": int(len(groups)),
        "input_parent_buildings": int(len(ordered_parents)),
        "voxelized_obj_groups": int(voxelized_groups),
        "empty_obj_groups": int(empty_groups),
        "buildings_with_voxels": int(np.count_nonzero(final_counts_array[1:])),
        "raw_voxels": int(sum(raw_counts.values())),
        "parcel_clipped_voxels_before_overlap_resolution": before_overlap_resolution,
        "occupied_voxels": int(len(cells)),
        "overlap_voxels_resolved": before_overlap_resolution - int(len(cells)),
        "north_index_min_max": [int(cells[:, 0].min()), int(cells[:, 0].max())],
        "east_index_min_max": [int(cells[:, 1].min()), int(cells[:, 1].max())],
        "up_elevation_cell_min_max": [int(cells[:, 2].min()), int(cells[:, 2].max())],
    }
    return OverlayResult(
        occupied_neu=cells,
        building_ids=ids,
        building_table=building_table,
        stats=stats,
        transform_model_to_voxcity_ijk=transform,
        grid_shape_ne=grid_shape_ne,
        rectangle_vertices_lonlat=vertices,
    )


def overlay_arrays(
    result: OverlayResult,
    domain: MetricDomain,
    voxelearth_alignment: Mapping[str, Any] | None = None,
) -> dict[str, np.ndarray]:
    table = result.building_table
    edit_mask_ne = np.zeros(result.grid_shape_ne, dtype=np.uint8)
    edit_mask_ne[result.occupied_neu[:, 0], result.occupied_neu[:, 1]] = 1
    model_to_output_neu = result.transform_model_to_voxcity_ijk.copy()
    model_to_output_neu[2, 3] -= VOXCITY_TERRAIN_SEATING_OFFSET_CELLS
    output_neu_to_model = np.linalg.inv(model_to_output_neu)
    model_origin = output_neu_to_model @ np.asarray([0.0, 0.0, 0.0, 1.0])
    arrays = {
        "occupied_neu": result.occupied_neu.astype(np.int32, copy=False),
        # This is intentionally an exact alias of occupied_neu.  Downstream
        # merging may write only these 3D cells; everything else in the base
        # VoxelEarth world is outside the edit mask and must remain unchanged.
        "building_edit_neu": result.occupied_neu.astype(np.int32, copy=False),
        "building_ids": result.building_ids.astype(np.uint16, copy=False),
        "edit_mask_ne_packed_bits": np.packbits(
            edit_mask_ne.reshape(-1), bitorder="little"
        ),
        "edit_mask_shape_ne": np.asarray(result.grid_shape_ne, dtype=np.int32),
        "building_table_ids": np.asarray([row["id"] for row in table], dtype=np.uint16),
        "building_roofer_ids": _string_array([str(row["roofer_id"]) for row in table]),
        "building_names": _string_array([str(row["name"]) for row in table]),
        "grid_shape_ne": np.asarray(result.grid_shape_ne, dtype=np.int32),
        "metric_origin_neu_m": np.asarray(
            [model_origin[1], model_origin[0], model_origin[2]], dtype=np.float64
        ),
        "model_east_north_up_to_output_neu": model_to_output_neu.astype(np.float64),
        "output_neu_to_model_east_north_up": output_neu_to_model.astype(np.float64),
        "meshsize_m": np.asarray([domain.meshsize_m], dtype=np.float64),
    }
    if voxelearth_alignment is not None:
        arrays.update(
            {
                "voxelearth_origin_ecef_m": np.asarray(
                    voxelearth_alignment["origin_ecef_m"], dtype=np.float64
                ),
                "voxelearth_ecef_to_world_xyz_basis_rows": np.asarray(
                    voxelearth_alignment["ecef_to_world_xyz_basis_rows"],
                    dtype=np.float64,
                ),
                "voxelearth_blocks_per_metre": np.asarray(
                    [voxelearth_alignment["blocks_per_metre"]], dtype=np.float64
                ),
            }
        )
    return arrays


def run_generation(args: argparse.Namespace) -> dict[str, Any]:
    ensure_voxcity_on_path(args.voxcity_src)
    obj_path = require_file(args.obj, "Roofer LoD2 OBJ")
    cityjson_path = require_file(args.cityjson, "Roofer CityJSON")
    footprints_path = require_file(args.footprints, "Roofer footprints")
    parcel_path = require_file(args.parcels, "Hill parcels")

    parcel_count, property_geometry = load_property_geometry(parcel_path, args.metric_crs)
    if args.voxelearth_manifest is not None:
        domain, voxelearth_alignment = domain_from_voxelearth_manifest(
            args.voxelearth_manifest,
            metric_crs=args.metric_crs,
            meshsize_m=args.meshsize,
        )
    else:
        domain = domain_from_property(
            property_geometry,
            metric_crs=args.metric_crs,
            meshsize_m=args.meshsize,
        )
        voxelearth_alignment = None

    metadata, child_to_parent = load_roofer_metadata(
        footprints_path,
        cityjson_path,
        metric_crs=args.metric_crs,
    )
    keep_geometry = property_geometry
    if args.preserve_roofer_footprints:
        _footprint_count, roofer_footprint_geometry = load_property_geometry(
            footprints_path, args.metric_crs
        )
        # County parcel polygons have narrow gaps and, around the academic
        # core, can miss parts of named school buildings by tens of metres.
        # The Roofer inputs are already the selected Hill building set, so
        # unioning only those footprints prevents the parcel crop from cutting
        # Feroe, Thomas House, Pine Court, etc. without admitting unrelated
        # neighborhood geometry.
        keep_geometry = property_geometry.union(roofer_footprint_geometry)

    from voxcity.importer.loader import load_obj_groups

    groups = load_obj_groups(obj_path, swap_yz=False)
    group_names = [name for name, _ in groups]
    if len(group_names) != len(set(group_names)):
        raise ValueError("Roofer OBJ contains duplicate group names")
    group_to_parent = map_group_parents(group_names, metadata, child_to_parent)

    result = voxelize_groups(
        groups,
        group_to_parent=group_to_parent,
        metadata=metadata,
        domain=domain,
        property_geometry=keep_geometry,
        property_boundary_m=args.property_boundary_m,
        mask_all_touched=args.mask_all_touched,
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / f"{args.output_stem}.npz"
    manifest_path = output_dir / f"{args.output_stem}.manifest.json"
    arrays = overlay_arrays(result, domain, voxelearth_alignment)
    write_deterministic_npz(npz_path, arrays)

    building_map = {
        str(row["id"]): {
            key: value
            for key, value in row.items()
            if key not in {"id"}
        }
        for row in result.building_table
    }
    manifest: dict[str, Any] = {
        "format": "hill-roofer-voxcity-buildings-only-v1",
        "determinism": {
            "stable_parent_id_order": "lexicographic Roofer parent id",
            "overlap_rule": "lowest stable parent id wins",
            "npz_zip_timestamp": "1980-01-01T00:00:00",
        },
        "engine": {
            "name": "VoxCity",
            "revision": git_revision(args.voxcity_src.parent),
            "functions": [
                "voxcity.importer.loader.load_obj_groups",
                "voxcity.importer.transform.build_placement_transform",
                "voxcity.importer.voxelize.voxelize_mesh",
            ],
            "vendored_engine_modified_by_this_script": False,
        },
        "layers": {
            "buildings": "Roofer LoD2.2 solid occupancy",
            "terrain": None,
            "land_cover": None,
            "vegetation": None,
            "water": None,
            "ground_provider": "VoxelEarth (merged downstream, absent from this NPZ)",
        },
        "axis_contract": {
            "occupied_neu_columns": ["north", "east", "up"],
            "north_east_cells": "zero-based offsets from metric_origin_neu_m",
            "up_cells": "one-metre NAVD88 elevation cells",
            "voxcity_internal_terrain_seating_offset_removed_cells": (
                VOXCITY_TERRAIN_SEATING_OFFSET_CELLS
            ),
            "meshsize_m": domain.meshsize_m,
            "exact_affine_arrays": {
                "forward": "model_east_north_up_to_output_neu",
                "inverse": "output_neu_to_model_east_north_up",
            },
        },
        "edit_contract": {
            "exact_3d_edit_cells_array": "building_edit_neu",
            "occupied_cells_array": "occupied_neu",
            "column_mask_arrays": ["edit_mask_ne_packed_bits", "edit_mask_shape_ne"],
            "column_mask_bit_order": "little; unpack then reshape C-order",
            "outside_edit_cells": "must remain bit-identical to the VoxelEarth base world",
            "terrain_cells_in_overlay": 0,
            "land_cover_cells_in_overlay": 0,
        },
        "domain": {
            **asdict(domain),
            "grid_shape_ne": list(result.grid_shape_ne),
            "rectangle_vertices_lonlat": [list(vertex) for vertex in result.rectangle_vertices_lonlat],
            "property_feature_count": parcel_count,
            "property_union_area_m2": float(property_geometry.area),
            "property_boundary_m": float(args.property_boundary_m),
            "mask_all_touched": bool(args.mask_all_touched),
            "preserve_roofer_footprints": bool(args.preserve_roofer_footprints),
            "edit_mask_geometry": (
                "Hill parcels union selected Roofer building footprints"
                if args.preserve_roofer_footprints
                else "Hill parcels only"
            ),
            "voxelearth_alignment": voxelearth_alignment,
        },
        "inputs": {
            "roofer_obj": file_manifest(obj_path),
            "roofer_cityjson": file_manifest(cityjson_path),
            "roofer_footprints": file_manifest(footprints_path),
            "hill_parcels": file_manifest(parcel_path),
            "voxelearth_manifest": (
                file_manifest(args.voxelearth_manifest)
                if args.voxelearth_manifest is not None
                else None
            ),
        },
        "output": {
            "npz": file_manifest(npz_path),
            "arrays": {
                name: {"shape": list(value.shape), "dtype": str(value.dtype)}
                for name, value in arrays.items()
            },
        },
        "stats": result.stats,
        "building_id_map": building_map,
    }
    write_json(manifest_path, manifest)
    print(f"Saved building-only overlay: {npz_path}")
    print(f"Saved manifest: {manifest_path}")
    print(json.dumps(result.stats, indent=2, sort_keys=True))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Voxelize Roofer LoD2 buildings only; VoxelEarth supplies all ground geometry."
        )
    )
    parser.add_argument("--obj", type=Path, default=DEFAULT_OBJ)
    parser.add_argument("--cityjson", type=Path, default=DEFAULT_CITYJSON)
    parser.add_argument("--footprints", type=Path, default=DEFAULT_FOOTPRINTS)
    parser.add_argument("--parcels", type=Path, default=DEFAULT_PARCELS)
    parser.add_argument(
        "--voxelearth-manifest",
        type=Path,
        default=DEFAULT_VOXELEARTH_MANIFEST,
        help="Full-campus VoxelEarth manifest used to set the exact ground-world bounds.",
    )
    parser.add_argument(
        "--property-bounds-only",
        action="store_true",
        help="Ignore the VoxelEarth manifest and use the snapped Hill parcel bbox.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-stem", default=DEFAULT_OUTPUT_STEM)
    parser.add_argument("--voxcity-src", type=Path, default=VOXCITY_SRC)
    parser.add_argument("--metric-crs", default=DEFAULT_METRIC_CRS)
    parser.add_argument("--meshsize", type=float, default=1.0)
    parser.add_argument("--property-boundary-m", type=float, default=2.0)
    parser.add_argument(
        "--preserve-roofer-footprints",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Union selected Roofer footprints into the parcel edit mask so named "
            "campus buildings are not cut by gaps in county parcel geometry."
        ),
    )
    parser.add_argument(
        "--mask-all-touched",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.property_bounds_only:
        args.voxelearth_manifest = None
    if abs(args.meshsize - 1.0) > 1e-9:
        parser.error("this Hill overlay is intentionally fixed to 1.0 m voxels")
    run_generation(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
