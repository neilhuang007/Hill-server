"""Assemble the full Hill campus VoxCity model from Roofer LoD2 solids.

This is an orchestration wrapper around the existing VoxCity and Roofer outputs:

* VoxCity builds the 1 m terrain, OSM semantic land-cover, and static canopy.
* VoxCity's official OBJ importer stamps the Roofer LoD2.2 building solids.
* A Hill parcel mask clears geometry-bearing cells outside the property buffer.

The script is intentionally import-safe: no downloads, voxelization, or file
writes happen until ``main()`` runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS, Transformer
from rasterio import features
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import transform_bounds
from shapely.geometry.base import BaseGeometry


REPO_ROOT = Path(__file__).resolve().parents[1]
VOXCITY_SRC = REPO_ROOT / "runtime/vendor/VoxCity/src"

DEFAULT_TRIAL_DIR = REPO_ROOT / "runtime/campus-reconstruction/roofer-chapel-trial"
DEFAULT_OBJ = DEFAULT_TRIAL_DIR / "campus-model/hill-campus-roofer-lod22.obj"
DEFAULT_CROPPED_DEM = DEFAULT_TRIAL_DIR / "inputs/hill-campus-dem-0p5m.tif"
DEFAULT_DEM_TILE_DIR = REPO_ROOT / "runtime/campus-data/dem-d24"
DEFAULT_PARCELS = REPO_ROOT / "runtime/campus-data/gis/montco-hill-parcels-full.geojson"
DEFAULT_OUTPUT_DIR = DEFAULT_TRIAL_DIR / "voxcity-full-campus-1m"

DEFAULT_METRIC_CRS = "EPSG:6347"
DEFAULT_ANCHOR_LONLAT = (-75.63898598373832, 40.24300717067909)
DEFAULT_ANCHOR_MODEL_POINT = (445650.0, 4454925.0, 0.0)

EMPTY_VOXEL = 0


@dataclass(frozen=True)
class MetricRectangle:
    """Metric, axis-aligned rectangle used to derive VoxCity's lon/lat ROI."""

    crs: str
    minx: float
    miny: float
    maxx: float
    maxy: float
    meshsize: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.minx, self.miny, self.maxx, self.maxy)

    @property
    def width_m(self) -> float:
        return self.maxx - self.minx

    @property
    def height_m(self) -> float:
        return self.maxy - self.miny


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, CRS):
        return value.to_string()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=_json_default)
        handle.write("\n")


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def file_manifest(path: Path, *, sha256: bool = True) -> dict[str, Any]:
    stat = path.stat()
    payload: dict[str, Any] = {
        "path": str(path),
        "bytes": stat.st_size,
    }
    if sha256:
        payload["sha256"] = sha256_file(path)
    return payload


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"{label} is empty: {path}")
    return path


def require_dir(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def parse_pair(text: str) -> tuple[float, float]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected two comma-separated numbers")
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected numeric lon,lat values") from exc


def parse_triple(text: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three comma-separated numbers")
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected numeric x,y,z values") from exc


def union_geometries(geometries: Any) -> BaseGeometry:
    if hasattr(geometries, "union_all"):
        return geometries.union_all()
    return geometries.unary_union


def clean_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.is_empty:
        return geometry
    if geometry.is_valid:
        return geometry
    try:
        from shapely import make_valid

        fixed = make_valid(geometry)
    except Exception:
        fixed = geometry.buffer(0)
    return fixed


def load_property_geometry(
    parcel_path: Path,
    metric_crs: str,
) -> tuple[gpd.GeoDataFrame, BaseGeometry]:
    require_file(parcel_path, "Hill parcel GeoJSON")
    parcels = gpd.read_file(parcel_path)
    if parcels.empty:
        raise ValueError(f"Hill parcel GeoJSON has no features: {parcel_path}")
    if parcels.crs is None:
        raise ValueError(f"Hill parcel GeoJSON has no CRS: {parcel_path}")

    parcels_metric = parcels.to_crs(metric_crs)
    valid = parcels_metric.geometry.notna() & ~parcels_metric.geometry.is_empty
    parcels_metric = parcels_metric.loc[valid].copy()
    if parcels_metric.empty:
        raise ValueError(f"Hill parcel GeoJSON has no usable geometries: {parcel_path}")
    parcels_metric.geometry = parcels_metric.geometry.map(clean_geometry)

    property_geometry = clean_geometry(union_geometries(parcels_metric.geometry))
    if property_geometry.is_empty:
        raise ValueError(f"Hill parcel union is empty: {parcel_path}")
    return parcels_metric, property_geometry


def metric_rectangle_from_geometry(
    geometry: BaseGeometry,
    *,
    metric_crs: str,
    meshsize: float,
    padding_m: float,
) -> MetricRectangle:
    if meshsize <= 0:
        raise ValueError("meshsize must be positive")
    if padding_m < 0:
        raise ValueError("padding_m cannot be negative")
    minx, miny, maxx, maxy = geometry.bounds
    minx = math.floor((minx - padding_m) / meshsize) * meshsize
    miny = math.floor((miny - padding_m) / meshsize) * meshsize
    maxx = math.ceil((maxx + padding_m) / meshsize) * meshsize
    maxy = math.ceil((maxy + padding_m) / meshsize) * meshsize
    if minx >= maxx or miny >= maxy:
        raise ValueError("property geometry produced a degenerate bounding rectangle")
    return MetricRectangle(
        crs=metric_crs,
        minx=float(minx),
        miny=float(miny),
        maxx=float(maxx),
        maxy=float(maxy),
        meshsize=float(meshsize),
    )


def metric_rectangle_to_lonlat(rect: MetricRectangle) -> list[tuple[float, float]]:
    transformer = Transformer.from_crs(rect.crs, "EPSG:4326", always_xy=True)
    return [
        transformer.transform(rect.minx, rect.miny),
        transformer.transform(rect.minx, rect.maxy),
        transformer.transform(rect.maxx, rect.maxy),
        transformer.transform(rect.maxx, rect.miny),
    ]


def bounds_intersect(a: Sequence[float], b: Sequence[float]) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def bounds_cover(outer: Sequence[float], inner: Sequence[float], tolerance_m: float = 0.0) -> bool:
    return (
        outer[0] <= inner[0] + tolerance_m
        and outer[1] <= inner[1] + tolerance_m
        and outer[2] >= inner[2] - tolerance_m
        and outer[3] >= inner[3] - tolerance_m
    )


def raster_bounds_in_metric(path: Path, metric_crs: str) -> tuple[float, float, float, float]:
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"DEM has no CRS: {path}")
        return tuple(float(v) for v in transform_bounds(src.crs, metric_crs, *src.bounds))


def validate_dem_coverage(path: Path, rect: MetricRectangle, tolerance_m: float) -> dict[str, Any]:
    require_file(path, "DEM GeoTIFF")
    raster_bounds = raster_bounds_in_metric(path, rect.crs)
    covers = bounds_cover(raster_bounds, rect.bounds, tolerance_m)
    payload = {
        "path": str(path),
        "bounds_in_metric_crs": raster_bounds,
        "covers_rectangle": covers,
        "coverage_tolerance_m": float(tolerance_m),
    }
    if not covers:
        raise ValueError(
            "DEM does not cover the requested full-campus rectangle. "
            f"DEM bounds in {rect.crs}: {raster_bounds}; rectangle: {rect.bounds}. "
            "Pass --dem with a covering mosaic or allow --dem-tile-dir to build one."
        )
    return payload


def collect_intersecting_dem_tiles(
    tile_dir: Path,
    rect: MetricRectangle,
) -> list[Path]:
    require_dir(tile_dir, "DEM tile directory")
    paths = sorted(tile_dir.glob("*.tif"))
    if not paths:
        raise FileNotFoundError(f"No DEM GeoTIFF tiles found in: {tile_dir}")

    selected: list[Path] = []
    for path in paths:
        try:
            tile_bounds = raster_bounds_in_metric(path, rect.crs)
        except Exception:
            continue
        if bounds_intersect(tile_bounds, rect.bounds):
            selected.append(path)
    if not selected:
        raise ValueError(f"No DEM tiles in {tile_dir} intersect rectangle {rect.bounds}")
    return selected


def build_dem_mosaic(
    tile_paths: Sequence[Path],
    output_path: Path,
    rect: MetricRectangle,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sources = [rasterio.open(path) for path in tile_paths]
    try:
        first = sources[0]
        if first.crs is None:
            raise ValueError(f"DEM tile has no CRS: {tile_paths[0]}")
        merge_bounds = transform_bounds(rect.crs, first.crs, *rect.bounds)
        mosaic, transform = merge(
            sources,
            bounds=merge_bounds,
            res=(rect.meshsize, rect.meshsize),
            nodata=first.nodata,
            resampling=Resampling.bilinear,
            target_aligned_pixels=True,
        )
        meta = first.meta.copy()
        meta.update(
            {
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": transform,
                "count": mosaic.shape[0],
                "compress": "deflate",
                "predictor": 3,
            }
        )
        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(mosaic)
    finally:
        for src in sources:
            src.close()

    return {
        "path": str(output_path),
        "source_tiles": [str(path) for path in tile_paths],
        "source_tile_count": len(tile_paths),
        "output_resolution_m": float(rect.meshsize),
    }


def resolve_dem_path(
    *,
    requested_dem: Path | None,
    default_dem: Path,
    dem_tile_dir: Path | None,
    output_dir: Path,
    rect: MetricRectangle,
    coverage_tolerance_m: float,
    build_mosaic: bool,
) -> tuple[Path, dict[str, Any]]:
    if requested_dem is not None:
        validate_dem_coverage(requested_dem, rect, coverage_tolerance_m)
        return requested_dem, {"mode": "explicit", **file_manifest(requested_dem)}

    if default_dem.is_file():
        try:
            validate_dem_coverage(default_dem, rect, coverage_tolerance_m)
            return default_dem, {"mode": "default", **file_manifest(default_dem)}
        except ValueError as exc:
            default_note = str(exc)
    else:
        default_note = f"default DEM missing: {default_dem}"

    if build_mosaic and dem_tile_dir is not None and dem_tile_dir.is_dir():
        mosaic_path = output_dir / "source-data/hill-full-campus-dem-0p5m-mosaic.tif"
        tile_paths = collect_intersecting_dem_tiles(dem_tile_dir, rect)
        mosaic_manifest = build_dem_mosaic(tile_paths, mosaic_path, rect)
        validate_dem_coverage(mosaic_path, rect, coverage_tolerance_m)
        return mosaic_path, {
            "mode": "mosaic_from_tiles",
            "default_dem_rejected": default_note,
            **file_manifest(mosaic_path),
            **mosaic_manifest,
        }

    if default_dem.is_file():
        validate_dem_coverage(default_dem, rect, coverage_tolerance_m)
    raise ValueError(default_note)


def rasterize_property_keep_mask(
    property_geometry_metric: BaseGeometry,
    rect: MetricRectangle,
    shape: tuple[int, int],
    *,
    boundary_m: float,
    all_touched: bool,
) -> np.ndarray:
    """Return a VoxCity-oriented keep mask with row 0 at the south edge."""

    if boundary_m < 0:
        raise ValueError("boundary_m cannot be negative")
    rows, cols = shape
    if rows <= 0 or cols <= 0:
        raise ValueError(f"invalid mask shape: {shape}")

    keep_geometry = property_geometry_metric.buffer(boundary_m) if boundary_m else property_geometry_metric
    keep_geometry = clean_geometry(keep_geometry)
    if keep_geometry.is_empty:
        raise ValueError("buffered property geometry is empty")

    transform = Affine(
        rect.width_m / cols,
        0.0,
        rect.minx,
        0.0,
        -(rect.height_m / rows),
        rect.maxy,
    )
    north_up = features.rasterize(
        [(keep_geometry, 1)],
        out_shape=(rows, cols),
        transform=transform,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    ).astype(bool)
    return np.flipud(north_up)


def write_mask_geotiff(mask_uv: np.ndarray, rect: MetricRectangle, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, cols = mask_uv.shape
    transform = Affine(
        rect.width_m / cols,
        0.0,
        rect.minx,
        0.0,
        -(rect.height_m / rows),
        rect.maxy,
    )
    meta = {
        "driver": "GTiff",
        "height": rows,
        "width": cols,
        "count": 1,
        "dtype": "uint8",
        "crs": CRS.from_user_input(rect.crs),
        "transform": transform,
        "nodata": 0,
    }
    with rasterio.open(path, "w", **meta) as dst:
        dst.write(np.flipud(mask_uv).astype("uint8"), 1)


def _clear_object_cells(array: np.ndarray, exterior: np.ndarray) -> None:
    for idx in zip(*np.nonzero(exterior)):
        array[idx] = []


def clear_exterior_cells(city: Any, keep_mask: np.ndarray) -> dict[str, Any]:
    """Clear geometry-bearing grids outside the Hill property keep mask."""

    keep = np.asarray(keep_mask, dtype=bool)
    shape = tuple(keep.shape)
    expected = tuple(city.land_cover.classes.shape)
    if shape != expected:
        raise ValueError(f"keep mask shape {shape} does not match VoxCity 2D shape {expected}")
    if tuple(city.voxels.classes.shape[:2]) != expected:
        raise ValueError("VoxCity voxel grid shape does not match 2D source grids")

    exterior = ~keep
    canopy_top = None
    if city.tree_canopy is not None and city.tree_canopy.top is not None:
        canopy_top = city.tree_canopy.top

    stats = {
        "shape": shape,
        "kept_cells": int(np.count_nonzero(keep)),
        "masked_cells": int(np.count_nonzero(exterior)),
        "voxels_cleared": int(np.count_nonzero(city.voxels.classes[exterior, :])),
        "building_cells_cleared": int(np.count_nonzero(city.buildings.ids[exterior])),
        "canopy_cells_cleared": int(np.count_nonzero(canopy_top[exterior] > 0)) if canopy_top is not None else 0,
    }

    city.voxels.classes[exterior, :] = EMPTY_VOXEL
    city.buildings.heights[exterior] = 0
    city.buildings.ids[exterior] = 0
    if city.buildings.min_heights is not None:
        _clear_object_cells(city.buildings.min_heights, exterior)
    if city.tree_canopy is not None and city.tree_canopy.top is not None:
        city.tree_canopy.top[exterior] = 0
    if city.tree_canopy is not None and city.tree_canopy.bottom is not None:
        city.tree_canopy.bottom[exterior] = 0

    city.extras.setdefault("hill_property_mask", {})
    city.extras["hill_property_mask"].update(
        {
            "masked_exterior_cells": True,
            "kept_cells": stats["kept_cells"],
            "masked_cells": stats["masked_cells"],
        }
    )
    return stats


def unique_counts(array: np.ndarray) -> dict[str, int]:
    classes, counts = np.unique(array, return_counts=True)
    return {str(int(cls)): int(count) for cls, count in zip(classes, counts)}


def voxcity_stats(city: Any) -> dict[str, Any]:
    dem = np.asarray(city.dem.elevation)
    canopy = np.asarray(city.tree_canopy.top)
    return {
        "voxel_shape": [int(v) for v in city.voxels.classes.shape],
        "grid_shape": [int(v) for v in city.land_cover.classes.shape],
        "voxel_class_counts": unique_counts(city.voxels.classes),
        "land_cover_counts": unique_counts(city.land_cover.classes),
        "dem_min_m": float(np.nanmin(dem)),
        "dem_max_m": float(np.nanmax(dem)),
        "canopy_cells": int(np.count_nonzero(canopy > 0)),
        "building_cells": int(np.count_nonzero(city.buildings.ids > 0)),
        "building_id_max": int(np.max(city.buildings.ids)) if city.buildings.ids.size else 0,
    }


def ensure_voxcity_on_path(voxcity_src: Path = VOXCITY_SRC) -> None:
    require_dir(voxcity_src, "VoxCity source directory")
    path = str(voxcity_src)
    if path not in sys.path:
        sys.path.insert(0, path)


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


def build_empty_building_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"height": np.array([], dtype=float)},
        geometry=gpd.GeoSeries([], crs="EPSG:4326"),
        crs="EPSG:4326",
    )


def run_assembly(args: argparse.Namespace) -> dict[str, Any]:
    obj_path = require_file(args.obj, "Roofer LoD2 OBJ")
    parcel_path = require_file(args.parcels, "Hill parcel GeoJSON")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("VOXCITY_CACHE_DIR", str((output_dir / "cache").resolve()))
    ensure_voxcity_on_path(args.voxcity_src)

    parcels_metric, property_geometry = load_property_geometry(parcel_path, args.metric_crs)
    rectangle_padding_m = args.rectangle_padding_m
    if rectangle_padding_m is None:
        rectangle_padding_m = args.mask_boundary_m
    rect = metric_rectangle_from_geometry(
        property_geometry,
        metric_crs=args.metric_crs,
        meshsize=args.meshsize,
        padding_m=rectangle_padding_m,
    )
    rectangle_vertices = metric_rectangle_to_lonlat(rect)

    dem_path, dem_manifest = resolve_dem_path(
        requested_dem=args.dem,
        default_dem=args.default_dem,
        dem_tile_dir=args.dem_tile_dir,
        output_dir=output_dir,
        rect=rect,
        coverage_tolerance_m=args.dem_coverage_tolerance_m,
        build_mosaic=not args.no_dem_mosaic,
    )

    from voxcity.exporter.obj import export_obj
    from voxcity.generator import get_voxcity
    from voxcity.importer import add_buildings_from_obj
    from voxcity.io import save_voxcity

    city = get_voxcity(
        rectangle_vertices,
        meshsize=args.meshsize,
        building_source="GeoDataFrame",
        building_complementary_source="None",
        building_gdf=build_empty_building_gdf(),
        land_cover_source="OpenStreetMap",
        default_land_cover_class=args.default_land_cover_class,
        detect_ocean=args.detect_ocean,
        canopy_height_source="Static",
        dem_source="Local file",
        dem_path=str(dem_path),
        output_dir=str(output_dir / "source-data"),
        save_voxcity_data=False,
        gridvis=False,
        mapvis=False,
        parallel_download=True,
        use_download_cache=True,
        dem_interpolation=args.dem_interpolation,
        static_tree_height=args.static_tree_height,
        trunk_height_ratio=args.trunk_height_ratio,
        max_voxel_ram_mb=args.max_voxel_ram_mb,
        voxel_dtype=np.int8,
    )

    pre_import_stats = voxcity_stats(city)
    city = add_buildings_from_obj(
        city,
        str(obj_path),
        anchor_lonlat=args.anchor_lonlat,
        anchor_elevation=args.anchor_elevation,
        anchor_model_point=args.anchor_model_point,
        rotation=args.rotation,
        move=args.move,
        units=args.units,
        backend=args.import_backend,
        overwrite=True,
        auto_window=args.auto_window,
        gridvis=False,
    )
    pre_mask_stats = voxcity_stats(city)

    keep_mask = rasterize_property_keep_mask(
        property_geometry,
        rect,
        tuple(city.land_cover.classes.shape),
        boundary_m=args.mask_boundary_m,
        all_touched=args.mask_all_touched,
    )
    mask_stats = clear_exterior_cells(city, keep_mask)
    city.extras["hill_property_mask"].update(
        {
            "parcel_path": str(parcel_path),
            "metric_crs": rect.crs,
            "metric_bounds": list(rect.bounds),
            "rectangle_padding_m": float(rectangle_padding_m),
            "boundary_m": float(args.mask_boundary_m),
            "all_touched": bool(args.mask_all_touched),
        }
    )
    post_mask_stats = voxcity_stats(city)

    output_stem = args.output_stem
    h5_path = output_dir / f"{output_stem}.h5"
    mask_path = output_dir / f"{output_stem}-property-keep-mask.tif"
    manifest_path = output_dir / f"{output_stem}.manifest.json"
    stats_path = output_dir / f"{output_stem}.stats.json"

    save_voxcity(h5_path, city)
    write_mask_geotiff(keep_mask, rect, mask_path)

    exported_obj: dict[str, Any] | None = None
    if args.export_obj:
        export_obj(city, str(output_dir), output_stem)
        exported_obj = {
            "obj": file_manifest(output_dir / f"{output_stem}.obj", sha256=False),
            "mtl": file_manifest(output_dir / f"{output_stem}.mtl", sha256=False),
        }

    stats = {
        "pre_import": pre_import_stats,
        "pre_mask": pre_mask_stats,
        "mask": mask_stats,
        "post_mask": post_mask_stats,
    }
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": str(Path(__file__).resolve()),
        "voxcity_revision": git_revision(args.voxcity_src.parent),
        "inputs": {
            "roofer_obj": file_manifest(obj_path),
            "parcels": file_manifest(parcel_path),
            "dem": dem_manifest,
        },
        "configuration": {
            "meshsize": float(args.meshsize),
            "metric_rectangle": asdict(rect),
            "rectangle_vertices_lonlat": rectangle_vertices,
            "land_cover_source": "OpenStreetMap",
            "default_land_cover_class": args.default_land_cover_class,
            "detect_ocean": bool(args.detect_ocean),
            "canopy_height_source": "Static",
            "static_tree_height": float(args.static_tree_height),
            "trunk_height_ratio": float(args.trunk_height_ratio),
            "dem_source": "Local file",
            "mask_boundary_m": float(args.mask_boundary_m),
            "mask_all_touched": bool(args.mask_all_touched),
            "anchor_lonlat": list(args.anchor_lonlat),
            "anchor_elevation": float(args.anchor_elevation),
            "anchor_model_point": list(args.anchor_model_point),
            "rotation": float(args.rotation),
            "move": list(args.move),
            "units": args.units,
            "import_backend": args.import_backend,
        },
        "parcel_summary": {
            "feature_count": int(len(parcels_metric)),
            "union_area_m2": float(property_geometry.area),
            "union_bounds_m": list(property_geometry.bounds),
        },
        "outputs": {
            "h5": file_manifest(h5_path, sha256=False),
            "property_keep_mask": file_manifest(mask_path, sha256=False),
            "manifest": str(manifest_path),
            "stats": str(stats_path),
            "exported_obj": exported_obj,
        },
        "stats": stats,
    }

    write_json(stats_path, stats)
    write_json(manifest_path, manifest)
    print(f"Saved VoxCity H5: {h5_path}")
    print(f"Saved property keep mask: {mask_path}")
    print(f"Saved manifest: {manifest_path}")
    print(f"Saved stats: {stats_path}")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble full-campus Hill VoxCity H5 using VoxCity and Roofer outputs.",
    )
    parser.add_argument("--obj", type=Path, default=DEFAULT_OBJ, help="Full-campus Roofer LoD2.2 OBJ.")
    parser.add_argument("--parcels", type=Path, default=DEFAULT_PARCELS, help="Hill parcel mask GeoJSON.")
    parser.add_argument("--dem", type=Path, default=None, help="Covering local DEM GeoTIFF. Overrides default discovery.")
    parser.add_argument("--default-dem", type=Path, default=DEFAULT_CROPPED_DEM, help="Default local DEM crop to try before mosaicking tiles.")
    parser.add_argument("--dem-tile-dir", type=Path, default=DEFAULT_DEM_TILE_DIR, help="Directory of DEM GeoTIFF tiles used to build a covering mosaic.")
    parser.add_argument("--no-dem-mosaic", action="store_true", help="Do not build a DEM mosaic from --dem-tile-dir.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory for H5, manifest, stats, cache, and source data.")
    parser.add_argument("--output-stem", default="hill-full-campus-roofer-voxcity-1m", help="Base filename for generated outputs.")
    parser.add_argument("--voxcity-src", type=Path, default=VOXCITY_SRC, help="Path to the VoxCity src directory.")
    parser.add_argument("--metric-crs", default=DEFAULT_METRIC_CRS, help="Metric CRS for parcel bounds and mask rasterization.")
    parser.add_argument("--meshsize", type=float, default=1.0, help="VoxCity grid size in metres.")
    parser.add_argument("--rectangle-padding-m", type=float, default=None, help="Padding added to the property bbox before snapping to meshsize. Defaults to --mask-boundary-m.")
    parser.add_argument("--mask-boundary-m", type=float, default=2.0, help="Exterior property buffer to preserve before masking cells.")
    parser.add_argument("--mask-all-touched", action=argparse.BooleanOptionalAction, default=True, help="Rasterize the parcel mask with all_touched semantics.")
    parser.add_argument("--dem-coverage-tolerance-m", type=float, default=1.0, help="Tolerance for DEM-vs-rectangle bounds validation.")
    parser.add_argument("--dem-interpolation", action="store_true", help="Use VoxCity's interpolated DEM sampling instead of nearest.")
    parser.add_argument("--static-tree-height", type=float, default=14.0, help="Height for VoxCity static canopy over OSM tree landcover.")
    parser.add_argument("--default-land-cover-class", default="Rangeland", help="Semantic class for OSM-unmapped cells; Hill open space defaults to lawn/grass.")
    parser.add_argument("--detect-ocean", action=argparse.BooleanOptionalAction, default=False, help="Run VoxCity coastline detection for the inland Hill campus.")
    parser.add_argument("--trunk-height-ratio", type=float, default=11.76 / 19.98, help="VoxCity canopy bottom ratio.")
    parser.add_argument("--max-voxel-ram-mb", type=float, default=10000.0, help="VoxCity voxel allocation guard.")
    parser.add_argument("--anchor-lonlat", type=parse_pair, default=DEFAULT_ANCHOR_LONLAT, help="Roofer anchor lon,lat.")
    parser.add_argument("--anchor-elevation", type=float, default=0.0, help="Roofer anchor elevation in metres.")
    parser.add_argument("--anchor-model-point", type=parse_triple, default=DEFAULT_ANCHOR_MODEL_POINT, help="Roofer model anchor x,y,z in model units.")
    parser.add_argument("--rotation", type=float, default=0.0, help="Roofer horizontal rotation in degrees.")
    parser.add_argument("--move", type=parse_triple, default=(0.0, 0.0, 0.0), help="Post-anchor east,north,up move in metres.")
    parser.add_argument("--units", default="m", choices=("m", "cm", "mm", "ft", "in"), help="Roofer OBJ length unit.")
    parser.add_argument("--import-backend", default="trimesh", choices=("trimesh", "meshlib"), help="VoxCity OBJ voxelization backend.")
    parser.add_argument("--auto-window", action=argparse.BooleanOptionalAction, default=False, help="Let VoxCity auto-classify window/glass OBJ groups.")
    parser.add_argument("--export-obj", action="store_true", help="Also export a VoxCity OBJ using the official exporter.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_assembly(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
