#!/usr/bin/env python3
"""Load precise Roofer roof geometry in VoxelEarth local metre coordinates.

Horizontal coordinates are always ``(x, z)`` where +X is east and +Z is
south.  Bounds are half-open ``(x_min, z_min, x_max, z_max)`` and rasters are
stored ``[z, x]``.  Roofer heights stay in source NAVD88 metres; this module
does not apply the separate terrain-to-Minecraft-Y datum offset.

The public seam is intentionally small: :func:`load_measured_building` turns
one named CityJSON parent and all its LoD2.2 child parts into a
:class:`MeasuredBuilding`, and :func:`rasterize_roof` samples that geometry at
cell centres while preserving concavities and polygon holes.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import hybridize_voxelearth_roofer_world as anvil
import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CITYJSON = (
    REPO_ROOT
    / "runtime/campus-reconstruction/roofer-chapel-trial"
    / "campus-model/hill-campus-roofer.city.json"
)
DEFAULT_MEASURED_TERRAIN_MANIFEST = (
    REPO_ROOT
    / "runtime/campus-reconstruction/measured-terrain"
    / "hill-chapel-measured-terrain.manifest.json"
)
ACADEMIC_CENTER_PARENT_ID = "16001511600613C-92645e8573"
SOURCE_CRS = "EPSG:6347"
WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class RoofFace:
    """One roof face projected to X/Z, with its NAVD88 height plane.

    ``polygon`` includes the source exterior and every source interior ring.
    The height at a horizontal point is ``a * x + b * z + c``.  ``min_h`` and
    ``max_h`` are extrema of the source face vertices rather than raster
    extrema.  ``source_semantics`` is the complete CityJSON semantic surface
    object, including Roofer slope and azimuth metadata when present.
    """

    polygon: Polygon
    a: float
    b: float
    c: float
    min_h: float
    max_h: float
    source_semantics: Mapping[str, Any]
    part_id: str
    shell_index: int
    surface_index: int

    def height_at(self, x: float | np.ndarray, z: float | np.ndarray) -> Any:
        return self.a * x + self.b * z + self.c


@dataclass(frozen=True)
class MeasuredBuilding:
    """Unioned ground footprint and measured roof faces for one parent."""

    footprint: Polygon | MultiPolygon
    roof_faces: tuple[RoofFace, ...]
    source_base: float
    source_max: float
    attrs: Mapping[str, Any]
    parent_id: str
    part_ids: tuple[str, ...]
    source_sha256: str
    ground_surface_count: int
    roof_surface_count: int
    rejected_roof_face_count: int
    rejected_roof_face_reasons: Mapping[str, int]


@dataclass(frozen=True)
class RoofRaster:
    """A cell-centre roof sample; all arrays use ``[z, x]`` ordering."""

    bounds: tuple[float, float, float, float]
    resolution: float
    heights: np.ndarray
    gradient_x: np.ndarray
    gradient_z: np.ndarray
    face_indices: np.ndarray
    footprint_mask: np.ndarray
    missing_mask: np.ndarray
    authored_roof_patches: tuple[Mapping[str, Any], ...] = ()

    @property
    def coverage_report(self) -> dict[str, int]:
        """Counts columns inside the footprint that do or do not have a roof."""

        footprint_columns = int(np.count_nonzero(self.footprint_mask))
        missing_columns = int(np.count_nonzero(self.missing_mask))
        return {
            "footprint_columns": footprint_columns,
            "covered_columns": footprint_columns - missing_columns,
            "missing_covered_columns": missing_columns,
        }


def load_measured_building(
    cityjson_path: Path = DEFAULT_CITYJSON,
    parent_id: str = ACADEMIC_CENTER_PARENT_ID,
    measured_terrain_manifest: Path = DEFAULT_MEASURED_TERRAIN_MANIFEST,
    *,
    minimum_projected_area: float = 1.0e-6,
    minimum_vertical_normal: float = 1.0e-3,
) -> MeasuredBuilding:
    """Load one parent and its direct LoD2.2 child parts from CityJSON.

    The measured-terrain manifest records the exact VoxelEarth manifest used
    to align the terrain.  That recorded path is passed to the existing
    :meth:`anvil.WorldTransform.from_manifest` implementation, keeping roof
    and terrain X/Z coordinates on the same transform.
    """

    cityjson_path = Path(cityjson_path).resolve()
    measured_terrain_manifest = Path(measured_terrain_manifest).resolve()
    if not cityjson_path.is_file():
        raise FileNotFoundError(f"Roofer CityJSON not found: {cityjson_path}")
    if not measured_terrain_manifest.is_file():
        raise FileNotFoundError(
            f"measured terrain manifest not found: {measured_terrain_manifest}"
        )
    if minimum_projected_area <= 0.0:
        raise ValueError("minimum_projected_area must be positive")
    if not 0.0 < minimum_vertical_normal <= 1.0:
        raise ValueError("minimum_vertical_normal must be in (0, 1]")

    cityjson = json.loads(cityjson_path.read_text(encoding="utf-8"))
    reference_system = str(
        (cityjson.get("metadata") or {}).get("referenceSystem") or ""
    )
    if reference_system and not (
        reference_system.upper() == SOURCE_CRS
        or reference_system.rstrip("/").endswith("/6347")
    ):
        raise ValueError(
            f"Roofer CityJSON must use {SOURCE_CRS}, found {reference_system!r}"
        )
    objects = cityjson.get("CityObjects") or {}
    parent = objects.get(parent_id)
    if not isinstance(parent, dict):
        raise KeyError(f"CityJSON parent not found: {parent_id}")
    if parent.get("type") != "Building":
        raise ValueError(f"CityJSON object {parent_id} is not a Building")

    part_ids = tuple(str(value) for value in (parent.get("children") or ()))
    if not part_ids:
        part_ids = (parent_id,)
    missing_parts = [part_id for part_id in part_ids if part_id not in objects]
    if missing_parts:
        raise KeyError(f"CityJSON child parts not found: {missing_parts}")

    world_transform = _world_transform_from_measured_manifest(measured_terrain_manifest)
    if not math.isclose(
        world_transform.blocks_per_metre, 1.0, rel_tol=0.0, abs_tol=1.0e-12
    ):
        raise ValueError(
            "campus roof geometry requires the measured one-block-per-metre transform"
        )
    source_vertices = anvil.denormalize_vertices(cityjson)
    transformer = Transformer.from_crs(SOURCE_CRS, WGS84, always_xy=True)
    world_vertices = [
        (*world_transform.metric_to_block(transformer, easting, northing), height)
        for easting, northing, height in source_vertices
    ]

    ground_polygons: list[Polygon] = []
    roof_faces: list[RoofFace] = []
    source_heights: list[float] = []
    ground_surface_count = 0
    roof_surface_count = 0
    rejected_reasons: dict[str, int] = {}

    for part_id in part_ids:
        part = objects[part_id]
        geometries = [
            geometry
            for geometry in (part.get("geometry") or ())
            if geometry.get("type") == "Solid" and str(geometry.get("lod")) == "2.2"
        ]
        if not geometries:
            continue
        for geometry in geometries:
            semantics = geometry.get("semantics") or {}
            semantic_surfaces = semantics.get("surfaces") or ()
            semantic_values = semantics.get("values") or ()
            for shell_index, shell in enumerate(geometry.get("boundaries") or ()):
                shell_values = (
                    semantic_values[shell_index]
                    if shell_index < len(semantic_values)
                    else ()
                )
                for surface_index, rings in enumerate(shell):
                    semantic_index = (
                        shell_values[surface_index]
                        if surface_index < len(shell_values)
                        else None
                    )
                    if not isinstance(semantic_index, int) or not (
                        0 <= semantic_index < len(semantic_surfaces)
                    ):
                        continue
                    source_semantics = dict(semantic_surfaces[semantic_index])
                    surface_type = source_semantics.get("type")
                    if surface_type not in {"GroundSurface", "RoofSurface"}:
                        continue
                    if surface_type == "GroundSurface":
                        ground_surface_count += 1
                    else:
                        roof_surface_count += 1
                    if not rings:
                        if surface_type == "RoofSurface":
                            _increment(rejected_reasons, "empty_rings")
                        continue

                    indices = [int(index) for ring in rings for index in ring]
                    if any(
                        index < 0 or index >= len(world_vertices) for index in indices
                    ):
                        raise IndexError(
                            f"surface in {part_id} references a missing CityJSON vertex"
                        )
                    source_heights.extend(
                        source_vertices[index][2] for index in indices
                    )
                    polygons = _surface_polygons(rings, world_vertices)

                    if surface_type == "GroundSurface":
                        ground_polygons.extend(polygons)
                        continue

                    if not polygons:
                        _increment(rejected_reasons, "invalid_projected_polygon")
                        continue
                    plane = _fit_height_plane(
                        indices,
                        world_vertices,
                        minimum_vertical_normal=minimum_vertical_normal,
                    )
                    if plane is None:
                        _increment(
                            rejected_reasons, "near_vertical_or_degenerate_plane"
                        )
                        continue
                    a, b, c = plane
                    heights = [source_vertices[index][2] for index in indices]
                    for polygon in polygons:
                        if polygon.area < minimum_projected_area:
                            _increment(rejected_reasons, "projected_area_below_minimum")
                            continue
                        roof_faces.append(
                            RoofFace(
                                polygon=polygon,
                                a=a,
                                b=b,
                                c=c,
                                min_h=min(heights),
                                max_h=max(heights),
                                source_semantics=source_semantics,
                                part_id=part_id,
                                shell_index=shell_index,
                                surface_index=surface_index,
                            )
                        )

    if not ground_polygons:
        raise ValueError(f"parent {parent_id} has no usable LoD2.2 GroundSurface")
    if not roof_faces:
        raise ValueError(f"parent {parent_id} has no usable LoD2.2 RoofSurface")
    if not source_heights:
        raise ValueError(f"parent {parent_id} has no measured surface heights")

    footprint = _polygonal_union(ground_polygons)
    return MeasuredBuilding(
        footprint=footprint,
        roof_faces=tuple(roof_faces),
        source_base=min(source_heights),
        source_max=max(source_heights),
        attrs=dict(parent.get("attributes") or {}),
        parent_id=parent_id,
        part_ids=part_ids,
        source_sha256=_sha256(cityjson_path),
        ground_surface_count=ground_surface_count,
        roof_surface_count=roof_surface_count,
        rejected_roof_face_count=sum(rejected_reasons.values()),
        rejected_roof_face_reasons=dict(sorted(rejected_reasons.items())),
    )


def rasterize_roof(
    building: MeasuredBuilding,
    bounds: Sequence[float],
    resolution: float = 1.0,
) -> RoofRaster:
    """Sample the highest measured roof at each half-open grid cell centre.

    Roof membership uses each Shapely polygon itself, including concave edges
    and interior rings.  Overlapping faces select the greatest NAVD88 height;
    equal-height ties retain the earlier source face for deterministic indices.
    Missing columns are footprint cell centres not covered by any roof face.
    """

    x_min, z_min, x_max, z_max = _validated_grid(bounds, resolution)
    columns = _grid_size(x_max - x_min, resolution)
    rows = _grid_size(z_max - z_min, resolution)
    x = x_min + (np.arange(columns, dtype=np.float64) + 0.5) * resolution
    z = z_min + (np.arange(rows, dtype=np.float64) + 0.5) * resolution
    grid_x, grid_z = np.meshgrid(x, z)

    footprint_mask = contains_xy(building.footprint, grid_x, grid_z)
    heights = np.full((rows, columns), np.nan, dtype=np.float64)
    gradient_x = np.full((rows, columns), np.nan, dtype=np.float64)
    gradient_z = np.full((rows, columns), np.nan, dtype=np.float64)
    face_indices = np.full((rows, columns), -1, dtype=np.int32)

    for face_index, face in enumerate(building.roof_faces):
        inside = contains_xy(face.polygon, grid_x, grid_z)
        if not np.any(inside):
            continue
        candidate = face.height_at(grid_x, grid_z)
        replace = inside & (np.isnan(heights) | (candidate > heights))
        heights[replace] = candidate[replace]
        gradient_x[replace] = face.a
        gradient_z[replace] = face.b
        face_indices[replace] = face_index

    missing_mask = footprint_mask & (face_indices < 0)
    return RoofRaster(
        bounds=(x_min, z_min, x_max, z_max),
        resolution=float(resolution),
        heights=heights,
        gradient_x=gradient_x,
        gradient_z=gradient_z,
        face_indices=face_indices,
        footprint_mask=footprint_mask,
        missing_mask=missing_mask,
    )


def _world_transform_from_measured_manifest(
    measured_terrain_manifest: Path,
) -> anvil.WorldTransform:
    payload = json.loads(measured_terrain_manifest.read_text(encoding="utf-8"))
    if "originEcefMetres" in payload:
        return anvil.WorldTransform.from_manifest(measured_terrain_manifest)

    source = payload.get("voxelearth_manifest") or {}
    source_path_text = source.get("path") if isinstance(source, dict) else None
    if not source_path_text:
        raise ValueError(
            "measured terrain manifest does not record a VoxelEarth manifest path"
        )
    source_path = Path(str(source_path_text))
    if not source_path.is_absolute():
        source_path = measured_terrain_manifest.parent / source_path
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(
            f"recorded VoxelEarth manifest not found: {source_path}"
        )
    expected_sha256 = source.get("sha256")
    if expected_sha256 and _sha256(source_path) != str(expected_sha256).lower():
        raise ValueError("recorded VoxelEarth manifest SHA-256 does not match")
    return anvil.WorldTransform.from_manifest(source_path)


def _surface_polygons(
    rings: Sequence[Sequence[int]],
    world_vertices: Sequence[tuple[float, float, float]],
) -> list[Polygon]:
    projected = [
        [
            (world_vertices[int(index)][0], world_vertices[int(index)][1])
            for index in ring
        ]
        for ring in rings
        if len(ring) >= 3
    ]
    if not projected:
        return []
    polygon: BaseGeometry = Polygon(projected[0], projected[1:])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return []
    if isinstance(polygon, Polygon):
        return [polygon]
    if isinstance(polygon, MultiPolygon):
        return list(polygon.geoms)
    return [item for item in getattr(polygon, "geoms", ()) if isinstance(item, Polygon)]


def _fit_height_plane(
    indices: Sequence[int],
    world_vertices: Sequence[tuple[float, float, float]],
    *,
    minimum_vertical_normal: float,
) -> tuple[float, float, float] | None:
    points = np.asarray([world_vertices[index] for index in indices], dtype=np.float64)
    design = np.column_stack((points[:, 0], points[:, 1], np.ones(len(points))))
    coefficients, _residuals, rank, _singular_values = np.linalg.lstsq(
        design, points[:, 2], rcond=None
    )
    if rank < 3 or not np.all(np.isfinite(coefficients)):
        return None
    a, b, c = (float(value) for value in coefficients)
    vertical_normal = 1.0 / math.sqrt(1.0 + a * a + b * b)
    if vertical_normal < minimum_vertical_normal:
        return None
    return a, b, c


def _polygonal_union(polygons: Sequence[Polygon]) -> Polygon | MultiPolygon:
    merged = unary_union(polygons)
    if isinstance(merged, (Polygon, MultiPolygon)):
        return merged
    parts = [item for item in getattr(merged, "geoms", ()) if isinstance(item, Polygon)]
    result = unary_union(parts)
    if not isinstance(result, (Polygon, MultiPolygon)) or result.is_empty:
        raise ValueError("GroundSurface union did not produce polygonal geometry")
    return result


def _validated_grid(
    bounds: Sequence[float], resolution: float
) -> tuple[float, float, float, float]:
    if len(bounds) != 4:
        raise ValueError("bounds must be (x_min, z_min, x_max, z_max)")
    values = tuple(float(value) for value in bounds)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("bounds must be finite")
    x_min, z_min, x_max, z_max = values
    if x_min >= x_max or z_min >= z_max:
        raise ValueError("bounds must be non-empty and half-open")
    if not math.isfinite(resolution) or resolution <= 0.0:
        raise ValueError("resolution must be a positive finite number")
    _grid_size(x_max - x_min, resolution)
    _grid_size(z_max - z_min, resolution)
    return values


def _grid_size(span: float, resolution: float) -> int:
    cells = span / resolution
    rounded = round(cells)
    if rounded <= 0 or not math.isclose(cells, rounded, rel_tol=0.0, abs_tol=1.0e-9):
        raise ValueError("each bounds span must be an integer multiple of resolution")
    return int(rounded)


def _increment(counts: dict[str, int], reason: str) -> None:
    counts[reason] = counts.get(reason, 0) + 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "ACADEMIC_CENTER_PARENT_ID",
    "DEFAULT_CITYJSON",
    "DEFAULT_MEASURED_TERRAIN_MANIFEST",
    "MeasuredBuilding",
    "RoofFace",
    "RoofRaster",
    "load_measured_building",
    "rasterize_roof",
]
