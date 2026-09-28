#!/usr/bin/env python3
"""Extract measured Chapel-area vegetation evidence from local USGS LiDAR.

Only LAS vegetation classes 3, 4, and 5 are retained.  The LAZ streams are
cropped in their native EPSG:6347 coordinates before conversion to VoxelEarth
coordinates, and points inside official building footprints are removed.
Tree positions are crown-apex proxies derived from local maxima, not surveyed
trunks; that uncertainty is explicit in the output.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import laspy
import numpy as np
from pyproj import CRS, Transformer
from scipy.ndimage import distance_transform_edt, label, map_coordinates, maximum_filter
from shapely import contains_xy
from shapely.geometry import MultiPoint, Polygon, shape
from shapely.ops import unary_union

import build_hill_measured_terrain as terrain


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERRAIN = (
    REPO_ROOT
    / "runtime/campus-reconstruction/measured-terrain/hill-chapel-measured-terrain.npz"
)
DEFAULT_LIDAR = (
    REPO_ROOT / "runtime/campus-data/lidar/USGS_LPC_PA_17County_D24_18TVK445455.laz",
    REPO_ROOT / "runtime/campus-data/lidar/USGS_LPC_PA_17County_D24_18TVK446455.laz",
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "runtime/campus-reconstruction/measured-terrain/hill-chapel-canopy.npz"
)
DEFAULT_PROFILE = REPO_ROOT / "server-assets/hill-chapel-reference.json"
DEFAULT_INFERRED_OUTPUT = (
    REPO_ROOT
    / "runtime/campus-reconstruction/measured-terrain/hill-chapel-inferred-canopy.npz"
)
DEFAULT_INFERRED_TREES_OUTPUT = (
    REPO_ROOT
    / "runtime/campus-reconstruction/measured-terrain/hill-chapel-inferred-trees.json"
)
VEGETATION_CLASSES = (3, 4, 5)
VEGETATION_CLASS_NAMES = {3: "low_vegetation", 4: "medium_vegetation", 5: "high_vegetation"}


def load_terrain(path: Path) -> dict[str, Any]:
    terrain.require_file(path, "measured terrain NPZ")
    with np.load(path, allow_pickle=False) as archive:
        required = {
            "ground_elevation_navd88_m",
            "ground_y",
            "x_min",
            "z_min",
            "metadata_json",
        }
        missing = required.difference(archive.files)
        if missing:
            raise ValueError(f"terrain archive is missing {sorted(missing)}")
        metadata = json.loads(archive["metadata_json"].item())
        result = {
            "ground_elevation_navd88_m": archive[
                "ground_elevation_navd88_m"
            ].astype(np.float32),
            "ground_y": archive["ground_y"].astype(np.int16),
            "x_min": int(archive["x_min"].item()),
            "z_min": int(archive["z_min"].item()),
            "metadata": metadata,
        }
    expected_shape = tuple(metadata["shape_zx"])
    if result["ground_elevation_navd88_m"].shape != expected_shape:
        raise ValueError("terrain metadata shape does not match its elevation grid")
    return result


def bounds_from_terrain(terrain_data: Mapping[str, Any]) -> terrain.WorldBounds:
    rows, cols = terrain_data["ground_elevation_navd88_m"].shape
    x_min = int(terrain_data["x_min"])
    z_min = int(terrain_data["z_min"])
    return terrain.WorldBounds(x_min, z_min, x_min + cols, z_min + rows)


def world_bounds_projected_bbox(
    transform: terrain.WorldTransform,
    bounds: terrain.WorldBounds,
    target_crs: CRS,
) -> tuple[float, float, float, float]:
    # The expanded block-centre envelope safely contains the exact block-edge
    # quadrilateral while still cropping each million-point LAZ chunk early.
    sample_x, sample_y = terrain.block_centres_to_crs(transform, bounds, target_crs)
    margin = 1.0 / transform.blocks_per_metre
    return (
        float(sample_x.min()) - margin,
        float(sample_y.min()) - margin,
        float(sample_x.max()) + margin,
        float(sample_y.max()) + margin,
    )


def projected_to_world_xz(
    easting: np.ndarray,
    northing: np.ndarray,
    *,
    source_crs: CRS,
    transform: terrain.WorldTransform,
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized equivalent of WorldTransform.lonlat_to_block."""

    to_lonlat = Transformer.from_crs(
        terrain.horizontal_crs(source_crs), "EPSG:4326", always_xy=True
    )
    longitude, latitude = to_lonlat.transform(easting, northing)
    lat = np.radians(np.asarray(latitude, dtype=np.float64))
    lon = np.radians(np.asarray(longitude, dtype=np.float64))
    axis = 6378137.0
    flattening = 1.0 / 298.257223563
    eccentricity_sq = flattening * (2.0 - flattening)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    prime_vertical = axis / np.sqrt(1.0 - eccentricity_sq * sin_lat * sin_lat)
    ecef_x = prime_vertical * cos_lat * np.cos(lon)
    ecef_y = prime_vertical * cos_lat * np.sin(lon)
    ecef_z = prime_vertical * (1.0 - eccentricity_sq) * sin_lat
    dx = ecef_x - transform.origin_ecef[0]
    dy = ecef_y - transform.origin_ecef[1]
    dz = ecef_z - transform.origin_ecef[2]
    east, _up, south = transform._basis()
    scale = transform.blocks_per_metre
    world_x = (east[0] * dx + east[1] * dy + east[2] * dz) * scale
    world_z = (south[0] * dx + south[1] * dy + south[2] * dz) * scale
    return world_x, world_z


def sample_ground(
    ground_navd88_m: np.ndarray,
    world_x: np.ndarray,
    world_z: np.ndarray,
    *,
    x_min: int,
    z_min: int,
) -> np.ndarray:
    """Bilinearly sample the 1 m centre-based terrain grid."""

    column = world_x - x_min - 0.5
    row = world_z - z_min - 0.5
    return map_coordinates(
        ground_navd88_m,
        [row, column],
        order=1,
        mode="nearest",
        prefilter=False,
    )


def load_building_union_world(
    buildings_path: Path,
    transform: terrain.WorldTransform,
    bounds: terrain.WorldBounds,
) -> tuple[Any, int]:
    crop = Polygon(
        [
            (bounds.x_min, bounds.z_min),
            (bounds.x_max, bounds.z_min),
            (bounds.x_max, bounds.z_max),
            (bounds.x_min, bounds.z_max),
        ]
    )
    geometries = []
    for feature in terrain.load_geojson(buildings_path).get("features", []):
        geometry_payload = feature.get("geometry")
        if not geometry_payload:
            continue
        geometry = terrain.lonlat_geometry_to_world(shape(geometry_payload), transform)
        if not geometry.is_empty and geometry.intersects(crop):
            geometries.append(geometry)
    return (unary_union(geometries) if geometries else Polygon(), len(geometries))


def load_addition_guard(profile_path: Path) -> tuple[Polygon, dict[str, Any]]:
    profile = json.loads(terrain.require_file(profile_path, "Chapel profile").read_text(encoding="utf-8"))
    geometry = profile["geometry"]
    u_min, u_max = (float(value) for value in geometry["addition_outer_bounds_u_m"])
    v_min = float(geometry["addition_start_m"])
    v_max = float(geometry["south_m"])
    rotation = float(geometry["rotation_degrees"])
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle), math.sin(angle)

    def to_world(u: float, v: float) -> tuple[float, float]:
        return cosine * u + sine * v, -sine * u + cosine * v

    polygon = Polygon(
        [
            to_world(u_min, v_min),
            to_world(u_max, v_min),
            to_world(u_max, v_max),
            to_world(u_min, v_max),
        ]
    )
    return polygon, {
        "profile": terrain.file_record(profile_path),
        "local_uv_bounds_m": [u_min, v_min, u_max, v_max],
        "rotation_degrees": rotation,
        "world_xz_outline": [[float(x), float(z)] for x, z in polygon.exterior.coords],
    }


def _raw_coordinate_limits(
    minimum: float, maximum: float, scale: float, offset: float
) -> tuple[int, int]:
    return (
        math.floor((minimum - offset) / scale),
        math.ceil((maximum - offset) / scale),
    )


def extract_vegetation_points(
    lidar_paths: Sequence[Path],
    *,
    transform: terrain.WorldTransform,
    bounds: terrain.WorldBounds,
    ground_navd88_m: np.ndarray,
    buildings_world: Any,
    chunk_size: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    all_x: list[np.ndarray] = []
    all_z: list[np.ndarray] = []
    all_height: list[np.ndarray] = []
    all_class: list[np.ndarray] = []
    tile_records: list[dict[str, Any]] = []
    source_class_counts: Counter[int] = Counter()
    class_counts_before_buildings: Counter[int] = Counter()
    class_counts_after_buildings: Counter[int] = Counter()
    below_ground_count = 0
    source_crs: CRS | None = None

    for lidar_path in lidar_paths:
        terrain.require_file(lidar_path, "LiDAR LAZ")
        tile_source_counts: Counter[int] = Counter()
        tile_counts: Counter[int] = Counter()
        tile_exact_crop = 0
        tile_building_removed = 0
        with laspy.open(lidar_path) as reader:
            parsed_crs = reader.header.parse_crs()
            if parsed_crs is None:
                raise ValueError(f"LiDAR has no CRS: {lidar_path}")
            this_crs = CRS.from_user_input(parsed_crs)
            if source_crs is None:
                source_crs = this_crs
            elif terrain.horizontal_crs(source_crs) != terrain.horizontal_crs(this_crs):
                raise ValueError("LiDAR tiles do not share a horizontal CRS")
            projected_bbox = world_bounds_projected_bbox(transform, bounds, this_crs)
            x_raw_min, x_raw_max = _raw_coordinate_limits(
                projected_bbox[0],
                projected_bbox[2],
                float(reader.header.scales[0]),
                float(reader.header.offsets[0]),
            )
            y_raw_min, y_raw_max = _raw_coordinate_limits(
                projected_bbox[1],
                projected_bbox[3],
                float(reader.header.scales[1]),
                float(reader.header.offsets[1]),
            )
            for points in reader.chunk_iterator(chunk_size):
                classifications = np.asarray(points.classification, dtype=np.uint8)
                for value, count in zip(*np.unique(classifications, return_counts=True)):
                    tile_source_counts[int(value)] += int(count)
                    source_class_counts[int(value)] += int(count)
                keep = np.isin(classifications, VEGETATION_CLASSES)
                if not np.any(keep):
                    continue
                raw_x = np.asarray(points.X)
                raw_y = np.asarray(points.Y)
                keep &= (
                    (raw_x >= x_raw_min)
                    & (raw_x <= x_raw_max)
                    & (raw_y >= y_raw_min)
                    & (raw_y <= y_raw_max)
                )
                selected = np.nonzero(keep)[0]
                if selected.size == 0:
                    continue
                easting = (
                    raw_x[selected] * reader.header.scales[0] + reader.header.offsets[0]
                )
                northing = (
                    raw_y[selected] * reader.header.scales[1] + reader.header.offsets[1]
                )
                world_x, world_z = projected_to_world_xz(
                    easting, northing, source_crs=this_crs, transform=transform
                )
                exact = (
                    (world_x >= bounds.x_min)
                    & (world_x < bounds.x_max)
                    & (world_z >= bounds.z_min)
                    & (world_z < bounds.z_max)
                )
                if not np.any(exact):
                    continue
                selected = selected[exact]
                world_x = world_x[exact]
                world_z = world_z[exact]
                selected_classes = classifications[selected]
                tile_exact_crop += len(selected)
                for value, count in zip(*np.unique(selected_classes, return_counts=True)):
                    tile_counts[int(value)] += int(count)
                    class_counts_before_buildings[int(value)] += int(count)

                inside_building = contains_xy(buildings_world, world_x, world_z)
                tile_building_removed += int(np.count_nonzero(inside_building))
                outside = ~inside_building
                if not np.any(outside):
                    continue
                selected = selected[outside]
                world_x = world_x[outside]
                world_z = world_z[outside]
                selected_classes = selected_classes[outside]
                elevation = (
                    np.asarray(points.Z)[selected] * reader.header.scales[2]
                    + reader.header.offsets[2]
                )
                ground = sample_ground(
                    ground_navd88_m,
                    world_x,
                    world_z,
                    x_min=bounds.x_min,
                    z_min=bounds.z_min,
                )
                height = np.asarray(elevation - ground, dtype=np.float32)
                below_ground_count += int(np.count_nonzero(height < 0.0))
                height = np.maximum(height, 0.0)
                for value, count in zip(*np.unique(selected_classes, return_counts=True)):
                    class_counts_after_buildings[int(value)] += int(count)
                all_x.append(np.asarray(world_x, dtype=np.float32))
                all_z.append(np.asarray(world_z, dtype=np.float32))
                all_height.append(height)
                all_class.append(selected_classes)

            tile_records.append(
                {
                    **terrain.file_record(lidar_path),
                    "header_point_count": int(reader.header.point_count),
                    "source_class_counts": {
                        str(key): value for key, value in sorted(tile_source_counts.items())
                    },
                    "source_has_requested_vegetation_classes": any(
                        tile_source_counts.get(key, 0) for key in VEGETATION_CLASSES
                    ),
                    "projected_bounds": list(projected_bbox),
                    "vegetation_points_in_exact_crop": tile_exact_crop,
                    "building_footprint_points_removed": tile_building_removed,
                    "crop_class_counts": {
                        VEGETATION_CLASS_NAMES[key]: value
                        for key, value in sorted(tile_counts.items())
                    },
                }
            )

    if all_x:
        points_xzh = np.column_stack(
            [np.concatenate(all_x), np.concatenate(all_z), np.concatenate(all_height)]
        ).astype(np.float32)
        point_classes = np.concatenate(all_class).astype(np.uint8)
    else:
        points_xzh = np.empty((0, 3), dtype=np.float32)
        point_classes = np.empty((0,), dtype=np.uint8)
    return points_xzh, point_classes, {
        "tiles": tile_records,
        "class_counts_before_building_removal": {
            VEGETATION_CLASS_NAMES[key]: value
            for key, value in sorted(class_counts_before_buildings.items())
        },
        "source_class_counts": {
            str(key): value for key, value in sorted(source_class_counts.items())
        },
        "source_has_requested_vegetation_classes": any(
            source_class_counts.get(key, 0) for key in VEGETATION_CLASSES
        ),
        "class_counts_after_building_removal": {
            VEGETATION_CLASS_NAMES[key]: value
            for key, value in sorted(class_counts_after_buildings.items())
        },
        "below_ground_heights_clamped_to_zero": below_ground_count,
        "retained_point_count": int(len(points_xzh)),
        "chunk_size": int(chunk_size),
        "native_crs": source_crs.to_string() if source_crs else None,
    }


def extract_unclassified_high_points(
    lidar_paths: Sequence[Path],
    *,
    transform: terrain.WorldTransform,
    bounds: terrain.WorldBounds,
    ground_navd88_m: np.ndarray,
    exclusion_world: Any,
    minimum_height_m: float,
    chunk_size: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Extract class-1 returns that can support, but cannot verify, crowns."""

    all_points: list[np.ndarray] = []
    tile_records: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for lidar_path in lidar_paths:
        tile: Counter[str] = Counter()
        with laspy.open(lidar_path) as reader:
            parsed_crs = reader.header.parse_crs()
            if parsed_crs is None:
                raise ValueError(f"LiDAR has no CRS: {lidar_path}")
            source_crs = CRS.from_user_input(parsed_crs)
            projected_bbox = world_bounds_projected_bbox(transform, bounds, source_crs)
            x_raw_min, x_raw_max = _raw_coordinate_limits(
                projected_bbox[0],
                projected_bbox[2],
                float(reader.header.scales[0]),
                float(reader.header.offsets[0]),
            )
            y_raw_min, y_raw_max = _raw_coordinate_limits(
                projected_bbox[1],
                projected_bbox[3],
                float(reader.header.scales[1]),
                float(reader.header.offsets[1]),
            )
            for points in reader.chunk_iterator(chunk_size):
                classifications = np.asarray(points.classification, dtype=np.uint8)
                keep = classifications == 1
                if not np.any(keep):
                    continue
                raw_x = np.asarray(points.X)
                raw_y = np.asarray(points.Y)
                keep &= (
                    (raw_x >= x_raw_min)
                    & (raw_x <= x_raw_max)
                    & (raw_y >= y_raw_min)
                    & (raw_y <= y_raw_max)
                )
                selected = np.nonzero(keep)[0]
                tile["class1_projected_bbox"] += len(selected)
                if selected.size == 0:
                    continue
                easting = raw_x[selected] * reader.header.scales[0] + reader.header.offsets[0]
                northing = raw_y[selected] * reader.header.scales[1] + reader.header.offsets[1]
                world_x, world_z = projected_to_world_xz(
                    easting, northing, source_crs=source_crs, transform=transform
                )
                exact = (
                    (world_x >= bounds.x_min)
                    & (world_x < bounds.x_max)
                    & (world_z >= bounds.z_min)
                    & (world_z < bounds.z_max)
                )
                selected = selected[exact]
                world_x = world_x[exact]
                world_z = world_z[exact]
                tile["class1_exact_world_crop"] += len(selected)
                if selected.size == 0:
                    continue
                excluded = contains_xy(exclusion_world, world_x, world_z)
                tile["class1_exclusion_removed"] += int(np.count_nonzero(excluded))
                outside = ~excluded
                selected = selected[outside]
                world_x = world_x[outside]
                world_z = world_z[outside]
                if selected.size == 0:
                    continue
                elevation = (
                    np.asarray(points.Z)[selected] * reader.header.scales[2]
                    + reader.header.offsets[2]
                )
                ground = sample_ground(
                    ground_navd88_m,
                    world_x,
                    world_z,
                    x_min=bounds.x_min,
                    z_min=bounds.z_min,
                )
                heights = np.asarray(elevation - ground, dtype=np.float32)
                tall = heights >= minimum_height_m
                tile["class1_below_height_rejected"] += int(np.count_nonzero(~tall))
                tile["class1_high_retained"] += int(np.count_nonzero(tall))
                if np.any(tall):
                    all_points.append(
                        np.column_stack([world_x[tall], world_z[tall], heights[tall]]).astype(
                            np.float32
                        )
                    )
        totals.update(tile)
        tile_records.append(
            {
                "path": str(lidar_path),
                **{key: int(value) for key, value in sorted(tile.items())},
            }
        )
    points_xzh = (
        np.concatenate(all_points, axis=0)
        if all_points
        else np.empty((0, 3), dtype=np.float32)
    )
    return points_xzh, {
        "source_class": 1,
        "minimum_height_above_ground_m": float(minimum_height_m),
        "totals": {key: int(value) for key, value in sorted(totals.items())},
        "tiles": tile_records,
    }


def minimum_rotated_component_width(points_xz: np.ndarray) -> float:
    rectangle = MultiPoint(points_xz).minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon":
        return 0.0
    coordinates = np.asarray(rectangle.exterior.coords, dtype=np.float64)
    lengths = np.hypot(np.diff(coordinates[:, 0]), np.diff(coordinates[:, 1]))
    positive = lengths[lengths > 1e-6]
    return float(np.min(positive)) if len(positive) else 0.0


def infer_tree_candidates(
    points_xzh: np.ndarray,
    *,
    bounds: terrain.WorldBounds,
    resolution_m: float,
    minimum_height_m: float,
    suppression_radius_m: float,
    minimum_component_area_m2: float,
    minimum_component_width_m: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], tuple[np.ndarray, np.ndarray, np.ndarray]]:
    canopy_max, canopy_p95, point_count = aggregate_canopy_grid(
        points_xzh, bounds, resolution_m
    )
    occupied = point_count > 0
    component_labels, component_count = label(
        occupied, structure=np.ones((3, 3), dtype=np.uint8)
    )
    accepted_labels: list[int] = []
    rejected: Counter[str] = Counter()
    component_records: dict[int, dict[str, Any]] = {}
    for component_id in range(1, component_count + 1):
        rows, columns = np.nonzero(component_labels == component_id)
        area = len(rows) * resolution_m * resolution_m
        centres = np.column_stack(
            [
                bounds.x_min + (columns + 0.5) * resolution_m,
                bounds.z_min + (rows + 0.5) * resolution_m,
            ]
        )
        centre_width = minimum_rotated_component_width(centres)
        width = centre_width + resolution_m if centre_width > 0 else resolution_m
        inscribed_width = float(
            2.0
            * resolution_m
            * np.max(distance_transform_edt(component_labels == component_id))
        )
        record = {
            "occupied_area_m2": float(area),
            "minimum_rotated_width_m": float(width),
            "maximum_inscribed_width_m": inscribed_width,
            "occupied_cell_count": int(len(rows)),
        }
        component_records[component_id] = record
        if area < minimum_component_area_m2:
            rejected["area_below_minimum"] += 1
        elif inscribed_width < minimum_component_width_m:
            rejected["width_below_minimum"] += 1
        else:
            accepted_labels.append(component_id)

    inferred: list[dict[str, Any]] = []
    radius_cells = max(1, int(math.ceil(suppression_radius_m / resolution_m)))
    local_max = maximum_filter(
        canopy_p95,
        size=2 * radius_cells + 1,
        mode="constant",
        cval=0.0,
    )
    for component_id in accepted_labels:
        component_mask = component_labels == component_id
        rows, columns = np.nonzero(
            component_mask & (canopy_p95 >= minimum_height_m) & (canopy_p95 == local_max)
        )
        candidates = sorted(
            zip(rows, columns),
            key=lambda rc: (-float(canopy_p95[rc]), int(rc[0]), int(rc[1])),
        )
        seeds: list[tuple[float, float, int, int]] = []
        for row, column in candidates:
            x = bounds.x_min + (column + 0.5) * resolution_m
            z = bounds.z_min + (row + 0.5) * resolution_m
            if any(
                math.hypot(x - old_x, z - old_z) < suppression_radius_m
                for old_x, old_z, _, _ in seeds
            ):
                continue
            seeds.append((x, z, int(row), int(column)))
        if not seeds:
            rejected["accepted_component_without_local_maximum"] += 1
            continue

        point_columns = np.floor(
            (points_xzh[:, 0] - bounds.x_min) / resolution_m
        ).astype(int)
        point_rows = np.floor(
            (points_xzh[:, 1] - bounds.z_min) / resolution_m
        ).astype(int)
        within_grid = (
            (point_rows >= 0)
            & (point_rows < component_labels.shape[0])
            & (point_columns >= 0)
            & (point_columns < component_labels.shape[1])
        )
        component_points_mask = np.zeros(len(points_xzh), dtype=bool)
        component_points_mask[within_grid] = (
            component_labels[point_rows[within_grid], point_columns[within_grid]]
            == component_id
        )
        component_points = points_xzh[component_points_mask]
        seed_xz = np.asarray([(seed[0], seed[1]) for seed in seeds])
        squared = (
            (component_points[:, None, 0] - seed_xz[None, :, 0]) ** 2
            + (component_points[:, None, 1] - seed_xz[None, :, 1]) ** 2
        )
        assignment = np.argmin(squared, axis=1)
        for seed_index, (x, z, row, column) in enumerate(seeds):
            assigned_evidence = component_points[assignment == seed_index]
            if not len(assigned_evidence):
                continue
            assigned_distance = np.hypot(
                assigned_evidence[:, 0] - x, assigned_evidence[:, 1] - z
            )
            evidence = assigned_evidence[assigned_distance <= 8.0]
            if not len(evidence):
                continue
            outline = MultiPoint(evidence[:, :2]).convex_hull
            if outline.geom_type == "Polygon":
                outline_xz = [
                    [round(float(px), 3), round(float(pz), 3)]
                    for px, pz in outline.exterior.coords
                ]
            else:
                outline_xz = []
            distances = np.hypot(evidence[:, 0] - x, evidence[:, 1] - z)
            radius = float(np.quantile(distances, 0.90)) if len(distances) else resolution_m
            height = float(np.quantile(evidence[:, 2], 0.95))
            component = component_records[component_id]
            confidence = (
                "moderate"
                if component["occupied_area_m2"] >= 12.0
                and component["maximum_inscribed_width_m"] >= 3.0
                and len(evidence) >= 20
                else "low"
            )
            inferred.append(
                {
                    "x": float(x),
                    "z": float(z),
                    "height_m": height,
                    "crown_radius_m": radius,
                    "crown_outline_xz": outline_xz,
                    "source_class": 1,
                    "evidence_point_count": int(len(evidence)),
                    "component_id": int(component_id),
                    "component_occupied_area_m2": component["occupied_area_m2"],
                    "component_minimum_rotated_width_m": component[
                        "minimum_rotated_width_m"
                    ],
                    "component_maximum_inscribed_width_m": component[
                        "maximum_inscribed_width_m"
                    ],
                    "inference_method": (
                        "class-1 returns >=3m above measured ground; connected-component "
                        "filter; local crown maximum with 3m suppression"
                    ),
                    "confidence": confidence,
                    "position_role": "inferred crown apex; trunk location unverified",
                    "species": None,
                }
            )
    inferred.sort(key=lambda item: (-item["height_m"], item["z"], item["x"]))
    stats = {
        "connected_component_count": int(component_count),
        "accepted_component_count": len(accepted_labels),
        "rejected_component_counts": dict(sorted(rejected.items())),
        "minimum_component_area_m2": float(minimum_component_area_m2),
        "minimum_component_width_m": float(minimum_component_width_m),
        "inferred_tree_count": len(inferred),
        "confidence_counts": dict(
            sorted(Counter(item["confidence"] for item in inferred).items())
        ),
    }
    return inferred, stats, (canopy_max, canopy_p95, point_count)


def aggregate_canopy_grid(
    points_xzh: np.ndarray,
    bounds: terrain.WorldBounds,
    resolution_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if resolution_m <= 0:
        raise ValueError("grid resolution must be positive")
    rows = int(round((bounds.z_max - bounds.z_min) / resolution_m))
    cols = int(round((bounds.x_max - bounds.x_min) / resolution_m))
    if not math.isclose(rows * resolution_m, bounds.z_max - bounds.z_min) or not math.isclose(
        cols * resolution_m, bounds.x_max - bounds.x_min
    ):
        raise ValueError("grid resolution must divide both world-bound dimensions")
    counts = np.zeros((rows, cols), dtype=np.uint16)
    maxima = np.zeros((rows, cols), dtype=np.float32)
    p95 = np.zeros((rows, cols), dtype=np.float32)
    if not len(points_xzh):
        return maxima, p95, counts

    columns = np.floor((points_xzh[:, 0] - bounds.x_min) / resolution_m).astype(int)
    rows_index = np.floor((points_xzh[:, 1] - bounds.z_min) / resolution_m).astype(int)
    valid = (columns >= 0) & (columns < cols) & (rows_index >= 0) & (rows_index < rows)
    columns = columns[valid]
    rows_index = rows_index[valid]
    heights = points_xzh[valid, 2]
    flat_ids = rows_index * cols + columns
    unique_ids, cell_counts = np.unique(flat_ids, return_counts=True)
    counts.reshape(-1)[unique_ids] = np.minimum(cell_counts, np.iinfo(np.uint16).max)
    np.maximum.at(maxima.reshape(-1), flat_ids, heights)
    order = np.argsort(flat_ids, kind="stable")
    sorted_ids = flat_ids[order]
    sorted_heights = heights[order]
    starts = np.searchsorted(sorted_ids, unique_ids, side="left")
    ends = np.searchsorted(sorted_ids, unique_ids, side="right")
    for cell_id, start, end in zip(unique_ids, starts, ends):
        p95.reshape(-1)[cell_id] = np.quantile(sorted_heights[start:end], 0.95)
    return maxima, p95, counts


def derive_crown_seeds(
    canopy_p95_m: np.ndarray,
    points_xzh: np.ndarray,
    point_classes: np.ndarray,
    *,
    bounds: terrain.WorldBounds,
    resolution_m: float,
    minimum_height_m: float,
    suppression_radius_m: float,
) -> list[dict[str, Any]]:
    if not len(points_xzh):
        return []
    radius_cells = max(1, int(math.ceil(suppression_radius_m / resolution_m)))
    local_max = maximum_filter(
        canopy_p95_m,
        size=2 * radius_cells + 1,
        mode="constant",
        cval=0.0,
    )
    candidate_rows, candidate_cols = np.nonzero(
        (canopy_p95_m >= minimum_height_m) & (canopy_p95_m == local_max)
    )
    candidates = sorted(
        zip(candidate_rows, candidate_cols),
        key=lambda rc: (-float(canopy_p95_m[rc]), int(rc[0]), int(rc[1])),
    )
    selected: list[tuple[float, float, int, int]] = []
    for row, column in candidates:
        x = bounds.x_min + (column + 0.5) * resolution_m
        z = bounds.z_min + (row + 0.5) * resolution_m
        if any(math.hypot(x - old_x, z - old_z) < suppression_radius_m for old_x, old_z, _, _ in selected):
            continue
        selected.append((x, z, row, column))

    trees: list[dict[str, Any]] = []
    for x, z, row, column in selected:
        height = float(canopy_p95_m[row, column])
        distances = np.hypot(points_xzh[:, 0] - x, points_xzh[:, 1] - z)
        crown_evidence = (distances <= 8.0) & (
            points_xzh[:, 2] >= max(2.0, height * 0.2)
        )
        evidence_distances = distances[crown_evidence]
        crown_radius = (
            float(np.clip(np.quantile(evidence_distances, 0.90), resolution_m, 8.0))
            if len(evidence_distances)
            else float(resolution_m)
        )
        class_counts = Counter(int(value) for value in point_classes[crown_evidence])
        trees.append(
            {
                "x": float(x),
                "z": float(z),
                "height_m": height,
                "crown_radius_m": crown_radius,
                "evidence_point_count": int(np.count_nonzero(crown_evidence)),
                "evidence_class_counts": {
                    VEGETATION_CLASS_NAMES[key]: value
                    for key, value in sorted(class_counts.items())
                },
                "position_role": "LiDAR crown-apex proxy; trunk location uncertain",
                "trunk_location_uncertainty_m": float(suppression_radius_m),
            }
        )
    return trees


def build_canopy(args: argparse.Namespace) -> dict[str, Any]:
    terrain_path = args.terrain.resolve()
    terrain_data = load_terrain(terrain_path)
    bounds = bounds_from_terrain(terrain_data)
    if args.bounds is not None and list(args.bounds) != bounds.as_list():
        raise ValueError(
            f"requested bounds {list(args.bounds)} do not match terrain {bounds.as_list()}"
        )
    transform = terrain.WorldTransform.from_manifest(args.world_manifest.resolve())
    buildings_path = terrain.require_file(args.buildings.resolve(), "building footprints")
    buildings_world, building_count = load_building_union_world(
        buildings_path, transform, bounds
    )
    lidar_paths = [path.resolve() for path in args.lidar]
    points_xzh, point_classes, extraction = extract_vegetation_points(
        lidar_paths,
        transform=transform,
        bounds=bounds,
        ground_navd88_m=terrain_data["ground_elevation_navd88_m"],
        buildings_world=buildings_world,
        chunk_size=args.chunk_size,
    )
    canopy_max, canopy_p95, point_count = aggregate_canopy_grid(
        points_xzh, bounds, args.resolution
    )
    trees = derive_crown_seeds(
        canopy_p95,
        points_xzh,
        point_classes,
        bounds=bounds,
        resolution_m=args.resolution,
        minimum_height_m=args.minimum_tree_height,
        suppression_radius_m=args.suppression_radius,
    )

    output_path = args.output.resolve()
    trees_path = (
        args.trees_output.resolve()
        if args.trees_output is not None
        else output_path.with_name(output_path.stem.replace("canopy", "trees") + ".json")
    )
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else output_path.with_suffix(".manifest.json")
    )
    metadata = {
        "format": "hill-chapel-lidar-canopy-v1",
        "axis": "+X east, +Y up, +Z south (north is -Z)",
        "world_bounds": bounds.as_list(),
        "array_order": "[z, x] with row 0 at z_min",
        "resolution_m": float(args.resolution),
        "vegetation_las_classes": list(VEGETATION_CLASSES),
        "height_datum": "metres above measured NAVD88 bare-earth terrain",
    }
    terrain.write_deterministic_npz(
        output_path,
        {
            "canopy_max_height_m": canopy_max,
            "canopy_p95_height_m": canopy_p95,
            "vegetation_point_count": point_count,
            "vegetation_points_xzh": points_xzh,
            "vegetation_point_class": point_classes,
            "x_min": np.asarray(bounds.x_min, dtype=np.int32),
            "z_min": np.asarray(bounds.z_min, dtype=np.int32),
            "resolution_m": np.asarray(args.resolution, dtype=np.float32),
            "metadata_json": np.asarray(
                json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            ),
        },
    )
    tree_payload = {
        **metadata,
        "position_semantics": (
            "Each x/z is a local LiDAR crown maximum. It is a deterministic "
            "placement seed, not an observed trunk coordinate."
        ),
        "crown_radius_method": (
            "p90 radial extent of classified vegetation points at >=max(2m, "
            "20% apex height) within 8m; cap prevents linked crowns from expanding indefinitely"
        ),
        "local_maximum_minimum_height_m": float(args.minimum_tree_height),
        "local_maximum_suppression_radius_m": float(args.suppression_radius),
        "trees": trees,
    }
    terrain.write_json(trees_path, tree_payload)

    inference_manifest: dict[str, Any] = {"enabled": False}
    if args.infer_unclassified:
        addition_guard, addition_guard_record = load_addition_guard(args.profile.resolve())
        inference_exclusion = unary_union([buildings_world, addition_guard]).buffer(
            args.building_exclusion_buffer
        )
        inferred_points, inferred_extraction = extract_unclassified_high_points(
            lidar_paths,
            transform=transform,
            bounds=bounds,
            ground_navd88_m=terrain_data["ground_elevation_navd88_m"],
            exclusion_world=inference_exclusion,
            minimum_height_m=args.minimum_tree_height,
            chunk_size=args.chunk_size,
        )
        inferred_trees, inferred_stats, inferred_grids = infer_tree_candidates(
            inferred_points,
            bounds=bounds,
            resolution_m=args.resolution,
            minimum_height_m=args.minimum_tree_height,
            suppression_radius_m=args.suppression_radius,
            minimum_component_area_m2=args.minimum_component_area,
            minimum_component_width_m=args.minimum_component_width,
        )
        inferred_output_path = args.inferred_output.resolve()
        inferred_trees_path = args.inferred_trees_output.resolve()
        inferred_metadata = {
            **metadata,
            "format": "hill-chapel-inferred-class1-canopy-v1",
            "verified_vegetation": False,
            "source_class": 1,
            "inference_method": (
                "unclassified class-1 returns >=3m above measured ground, outside "
                "official/current building exclusion, filtered by measured connected footprint"
            ),
        }
        inferred_max, inferred_p95, inferred_count = inferred_grids
        terrain.write_deterministic_npz(
            inferred_output_path,
            {
                "canopy_max_height_m": inferred_max,
                "canopy_p95_height_m": inferred_p95,
                "candidate_point_count": inferred_count,
                "candidate_points_xzh": inferred_points,
                "x_min": np.asarray(bounds.x_min, dtype=np.int32),
                "z_min": np.asarray(bounds.z_min, dtype=np.int32),
                "resolution_m": np.asarray(args.resolution, dtype=np.float32),
                "metadata_json": np.asarray(
                    json.dumps(inferred_metadata, sort_keys=True, separators=(",", ":"))
                ),
            },
        )
        inferred_payload = {
            **inferred_metadata,
            "confidence_semantics": {
                "moderate": "broad component and >=20 actual returns; still not LAS-classified vegetation",
                "low": "passes minimum geometry only; visually verify before placement",
            },
            "building_exclusion_buffer_m": float(args.building_exclusion_buffer),
            "addition_guard": addition_guard_record,
            "extraction": inferred_extraction,
            "component_filter": inferred_stats,
            "site_plan_comparison": {
                "reference": str(
                    REPO_ROOT
                    / "runtime/research/hill-reference-20260904/chapel-gko-2.jpg"
                ),
                "status": "qualitative only; the rendered site plan is not georeferenced",
                "observations": [
                    "The dominant north/northeast and south/southeast return clusters agree with broad tree masses drawn on GKO SP-1.",
                    "Small low-height components beside the Chapel and tennis boundary remain ambiguous and may include pavilion, fence, or fixture returns.",
                ],
                "placement_rule": "All class-1 candidates require visual review; none are verified trees.",
            },
            "trees": inferred_trees,
        }
        terrain.write_json(inferred_trees_path, inferred_payload)
        inference_manifest = {
            "enabled": True,
            "verified_vegetation": False,
            "source_class": 1,
            "canopy_output": terrain.file_record(inferred_output_path),
            "trees_output": terrain.file_record(inferred_trees_path),
            "extraction": inferred_extraction,
            "component_filter": inferred_stats,
            "building_exclusion_buffer_m": float(args.building_exclusion_buffer),
            "addition_guard": addition_guard_record,
        }

    nonzero = point_count > 0
    manifest = {
        **metadata,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "output": terrain.file_record(output_path),
        "trees_output": terrain.file_record(trees_path),
        "terrain_source": terrain.file_record(terrain_path),
        "building_footprints": {
            "source": terrain.file_record(buildings_path),
            "features_intersecting_crop": building_count,
            "removal": "exact official footprint union; no arbitrary buffer",
        },
        "extraction": extraction,
        "grid": {
            "shape_zx": list(canopy_max.shape),
            "cells_with_vegetation_evidence": int(np.count_nonzero(nonzero)),
            "canopy_max_height_min_max_m": [
                float(canopy_max[nonzero].min()) if np.any(nonzero) else None,
                float(canopy_max.max()) if np.any(nonzero) else None,
            ],
            "canopy_p95_height_min_max_m": [
                float(canopy_p95[nonzero].min()) if np.any(nonzero) else None,
                float(canopy_p95.max()) if np.any(nonzero) else None,
            ],
        },
        "tree_seed_count": len(trees),
        "tree_location_warning": "crown maxima are uncertain trunk proxies",
        "unclassified_inference": inference_manifest,
    }
    terrain.write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain", type=Path, default=DEFAULT_TERRAIN)
    parser.add_argument("--world-manifest", type=Path, default=terrain.DEFAULT_WORLD_MANIFEST)
    parser.add_argument("--buildings", type=Path, default=terrain.DEFAULT_BUILDINGS)
    parser.add_argument("--lidar", type=Path, nargs="+", default=list(DEFAULT_LIDAR))
    parser.add_argument(
        "--bounds",
        type=int,
        nargs=4,
        metavar=("X_MIN", "Z_MIN", "X_MAX", "Z_MAX"),
        default=(-40, -40, 40, 45),
        help="Required terrain bounds guard; extraction never expands beyond them",
    )
    parser.add_argument("--resolution", type=float, default=0.5)
    parser.add_argument("--minimum-tree-height", type=float, default=3.0)
    parser.add_argument("--suppression-radius", type=float, default=3.0)
    parser.add_argument(
        "--infer-unclassified",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Infer unverified crown candidates from above-ground LAS class-1 returns",
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--building-exclusion-buffer", type=float, default=2.0)
    parser.add_argument("--minimum-component-area", type=float, default=6.0)
    parser.add_argument("--minimum-component-width", type=float, default=2.0)
    parser.add_argument("--chunk-size", type=int, default=2_000_000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trees-output", type=Path, default=None)
    parser.add_argument("--inferred-output", type=Path, default=DEFAULT_INFERRED_OUTPUT)
    parser.add_argument(
        "--inferred-trees-output", type=Path, default=DEFAULT_INFERRED_TREES_OUTPUT
    )
    parser.add_argument("--manifest", type=Path, default=None)
    return parser


def main(argv: list[str]) -> int:
    manifest = build_canopy(build_parser().parse_args(argv))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
