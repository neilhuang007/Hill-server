"""Build a hollow, measured building shell on a Canvas-like voxel grid.

The input :class:`campus_roof_geometry.RoofRaster` is sampled at one raster
cell per Minecraft column.  Its NAVD88 roof planes are converted to physical
Minecraft Y with the same fixed campus datum used by measured terrain.  A full
block at Y has physical top Y+1; a bottom slab has physical top Y+0.5.

Only roof-covered footprint columns are changed.  A column is left untouched
when its exact measured roof surface is at or below the current measured
ground block's physical top.  This keeps buried low facets from excavating
grade and never changes terrain outside the footprint or in courtyard holes.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from campus_roof_geometry import MeasuredBuilding, RoofRaster

AIR = "minecraft:air"
FLOOR = "minecraft:smooth_stone"
BOTTOM_SLAB_PROPERTIES = {"type": "bottom", "waterlogged": "false"}
BOTTOM_STAIR_PROPERTIES = {
    "half": "bottom",
    "shape": "straight",
    "waterlogged": "false",
}


@dataclass(frozen=True)
class ShellEvidence:
    """Construction evidence plus grids needed by a later facade builder."""

    world_bounds_blocks: tuple[int, int, int, int]
    built_bounds_blocks: tuple[int, int, int, int] | None
    floor_y: int
    floor_navd88: float
    vertical_offset: float
    scale: int
    roof_surface_y: np.ndarray
    quantized_roof_surface_y: np.ndarray
    roof_block_y: np.ndarray
    active_mask: np.ndarray
    exterior_wall_mask: np.ndarray
    internal_wall_mask: np.ndarray
    material_counts: Mapping[str, int]
    state_counts: Mapping[str, int]
    role_counts: Mapping[str, int]
    roof_representation_counts: Mapping[str, int]
    stair_facing_counts: Mapping[str, int]
    skipped_counts: Mapping[str, int]
    cleared_air_blocks: int
    foundation_column_count: int
    clipped_writes: int
    internal_wall_drop_metres: float
    neighbor_radius_metres: float
    parent_id: str
    roof_backing_metres: float = 0.0
    roof_backing_blocks: int = 0

    def to_manifest(self) -> dict[str, Any]:
        """Return the JSON-safe evidence; large per-column grids stay in memory."""

        return {
            "format": "hill-measured-shell-v1",
            "axis": "+X east, +Y up, +Z south",
            "array_order": "[z, x]",
            "bounds_semantics": "half-open [x_min, x_max) x [z_min, z_max)",
            "world_bounds_blocks": list(self.world_bounds_blocks),
            "built_bounds_blocks": (
                list(self.built_bounds_blocks)
                if self.built_bounds_blocks is not None
                else None
            ),
            "floor_y": self.floor_y,
            "floor_navd88_m": self.floor_navd88,
            "navd88_to_world_y_offset_m": self.vertical_offset,
            "scale_blocks_per_metre": self.scale,
            "active_roof_columns": int(np.count_nonzero(self.active_mask)),
            "exterior_wall_columns": int(np.count_nonzero(self.exterior_wall_mask)),
            "internal_wall_columns": int(np.count_nonzero(self.internal_wall_mask)),
            "material_counts": dict(self.material_counts),
            "state_counts": dict(self.state_counts),
            "role_counts": dict(self.role_counts),
            "roof_representation_counts": dict(self.roof_representation_counts),
            "stair_facing_counts": dict(self.stair_facing_counts),
            "skipped_counts": dict(self.skipped_counts),
            "cleared_air_blocks": self.cleared_air_blocks,
            "foundation_column_count": self.foundation_column_count,
            "clipped_writes": self.clipped_writes,
            "internal_wall_drop_metres": self.internal_wall_drop_metres,
            "neighbor_radius_metres": self.neighbor_radius_metres,
            "buried_column_rule": (
                "skip when exact roof physical Y <= measured ground block top Y+1"
            ),
            "parent_id": self.parent_id,
            "roof_backing_metres": self.roof_backing_metres,
            "roof_backing_blocks": self.roof_backing_blocks,
        }


def build_measured_shell(
    canvas: Any,
    building: MeasuredBuilding,
    roof_raster: RoofRaster,
    *,
    vertical_offset: float = 24.25,
    floor_navd88: float | None = None,
    facade: str = "bricks",
    foundation: str = "bricks",
    roof_family: str = "deepslate_tile",
    roof_backing_metres: float = 0.0,
) -> ShellEvidence:
    """Place one hollow measured shell and one ground-level floor.

    The raster resolution must equal one voxel column (``1 / canvas.scale``).
    Exterior walls occupy the high column at every four-neighbor footprint
    edge.  Internal walls occupy the high side of a roof discontinuity of at
    least one metre, measured against neighbors within roughly 0.5 metre;
    smooth roof slopes therefore remain hollow while low porches support the
    taller mass beside them.
    """

    scale = _positive_integer_scale(canvas)
    if not math.isfinite(vertical_offset):
        raise ValueError("vertical_offset must be finite")
    if not math.isfinite(roof_backing_metres) or roof_backing_metres < 0:
        raise ValueError("roof_backing_metres must be finite and nonnegative")
    backing_depth = math.ceil(roof_backing_metres * scale)
    backing_blocks = 0
    expected_resolution = 1.0 / scale
    if not math.isclose(
        roof_raster.resolution,
        expected_resolution,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise ValueError(
            "roof raster must contain exactly one cell per Minecraft column; "
            f"expected resolution {expected_resolution}, got {roof_raster.resolution}"
        )
    if roof_raster.resolution > 0.5 + 1.0e-9:
        raise ValueError(
            "measured shells require roof resolution of 0.5 metre or finer"
        )
    _validate_raster_arrays(roof_raster)
    used_face_indices = roof_raster.face_indices[roof_raster.face_indices >= 0]
    authored_ids = {int(p["face_index"]) for p in roof_raster.authored_roof_patches}
    unknown_ids = {
        int(i)
        for i in np.unique(used_face_indices)
        if int(i) >= len(building.roof_faces)
    } - authored_ids
    if unknown_ids:
        raise ValueError(
            "roof raster references a face absent from the measured building"
        )

    base_navd88 = building.source_base if floor_navd88 is None else float(floor_navd88)
    if not math.isfinite(base_navd88):
        raise ValueError("floor_navd88 must be finite")
    floor_y = round((base_navd88 + vertical_offset) * scale) - 1
    floor_surface_y = float(floor_y + 1)
    x0, z0, x1, z1 = _block_bounds(roof_raster, scale)
    rows, columns = roof_raster.heights.shape

    facade_name = _canonical_name(facade)
    foundation_name = _canonical_name(foundation)
    roof_blocks = _roof_family_blocks(roof_family)
    if facade_name == AIR or foundation_name == AIR:
        raise ValueError("facade and foundation must be solid construction blocks")
    roof_surface_y = (roof_raster.heights.astype(np.float64) + vertical_offset) * scale
    quantized_surface_y = np.full((rows, columns), np.nan, dtype=np.float64)
    roof_block_y = np.full((rows, columns), np.iinfo(np.int32).min, dtype=np.int32)
    ground_y = np.full_like(roof_block_y, np.iinfo(np.int32).min)

    source_covered = (
        roof_raster.footprint_mask
        & (roof_raster.face_indices >= 0)
        & np.isfinite(roof_surface_y)
    )
    active = np.zeros_like(source_covered, dtype=bool)
    skipped = Counter(
        {
            "roof_outside_footprint": int(
                np.count_nonzero(
                    (roof_raster.face_indices >= 0) & ~roof_raster.footprint_mask
                )
            ),
            "footprint_without_roof": int(np.count_nonzero(roof_raster.missing_mask)),
            "buried_at_measured_grade": 0,
            "roof_at_or_below_floor": 0,
            "quantized_roof_at_or_below_floor": 0,
        }
    )

    for row, column in zip(*np.nonzero(source_covered), strict=True):
        x, z = x0 + int(column), z0 + int(row)
        measured_ground_y = int(canvas.ground_at(x, z))
        ground_y[row, column] = measured_ground_y
        target_surface = float(roof_surface_y[row, column])
        if target_surface <= measured_ground_y + 1.0 + 1.0e-9:
            skipped["buried_at_measured_grade"] += 1
            continue
        if target_surface <= floor_surface_y + 1.0e-9:
            skipped["roof_at_or_below_floor"] += 1
            continue

        half_units = math.floor(target_surface * 2.0 + 0.5)
        quantized = half_units / 2.0
        block_y = half_units // 2 - 1 if half_units % 2 == 0 else half_units // 2
        if block_y <= floor_y:
            skipped["quantized_roof_at_or_below_floor"] += 1
            continue
        quantized_surface_y[row, column] = quantized
        roof_block_y[row, column] = block_y
        active[row, column] = True

    neighbor_radius = max(0.5, roof_raster.resolution)
    neighbor_offsets = _neighbor_offsets(roof_raster.resolution, neighbor_radius)
    exterior_wall_mask, internal_wall_mask = _wall_masks(
        active,
        quantized_surface_y,
        floor_surface_y=floor_surface_y,
        resolution=roof_raster.resolution,
        scale=scale,
        neighbor_offsets=neighbor_offsets,
    )
    representation, stair_facing = _roof_representations(
        active,
        quantized_surface_y,
        roof_raster,
    )

    material_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    cleared_air_blocks = 0
    clipped_before = int(getattr(canvas, "clipped", 0))
    foundation_columns: list[tuple[int, int, int]] = []

    def place(
        x: int,
        y: int,
        z: int,
        name: str,
        role: str,
        properties: Mapping[str, str] | None = None,
    ) -> None:
        canonical = _canonical_name(name)
        props = dict(properties) if properties else None
        canvas.set(x, y, z, canonical, role, props)
        if canonical != AIR:
            material_counts[canonical] += 1
            role_counts[role] += 1
            state_counts[_state_key(canonical, props)] += 1

    for row, column in zip(*np.nonzero(active), strict=True):
        row_i, column_i = int(row), int(column)
        x, z = x0 + column_i, z0 + row_i
        current_ground = int(ground_y[row_i, column_i])
        foundation_start = min(current_ground, floor_y - 2)
        for y in range(foundation_start, floor_y):
            place(x, y, z, foundation_name, "facade")
        foundation_columns.append((x, z, foundation_start))
        place(x, floor_y, z, FLOOR, "floor")

        top_block_y = int(roof_block_y[row_i, column_i])
        for y in range(floor_y + 1, top_block_y + 1):
            canvas.set(x, y, z, AIR, "air")
            cleared_air_blocks += 1
        if exterior_wall_mask[row_i, column_i] or internal_wall_mask[row_i, column_i]:
            for y in range(floor_y + 1, top_block_y):
                place(x, y, z, facade_name, "facade")

        # A sampled stair/slab surface alone has no roof substrate. Oblique
        # native views can see sky between adjacent risers, even when every
        # raster column is covered. Add thickness below the measured surface;
        # never lift its silhouette or fill a courtyard/outside column.
        for y in range(max(floor_y + 1, top_block_y - backing_depth), top_block_y):
            place(x, y, z, roof_blocks["full"], "roof")
            backing_blocks += 1

        kind = str(representation[row_i, column_i])
        if kind == "bottom_slab":
            place(
                x,
                top_block_y,
                z,
                roof_blocks["slab"],
                "roof",
                BOTTOM_SLAB_PROPERTIES,
            )
        elif kind == "bottom_stair":
            props = dict(BOTTOM_STAIR_PROPERTIES)
            props["facing"] = str(stair_facing[row_i, column_i])
            place(x, top_block_y, z, roof_blocks["stairs"], "roof", props)
        else:
            place(x, top_block_y, z, roof_blocks["full"], "roof")

    clipped_writes = int(getattr(canvas, "clipped", clipped_before)) - clipped_before
    if clipped_writes:
        raise ValueError(
            f"measured shell produced {clipped_writes} clipped Canvas writes"
        )
    _verify_foundations(canvas, foundation_columns, floor_y)

    active_rows, active_columns = np.nonzero(active)
    built_bounds = (
        (
            x0 + int(active_columns.min()),
            z0 + int(active_rows.min()),
            x0 + int(active_columns.max()) + 1,
            z0 + int(active_rows.max()) + 1,
        )
        if active_rows.size
        else None
    )
    representation_counts = Counter(
        str(representation[row, column])
        for row, column in zip(active_rows, active_columns, strict=True)
    )
    facing_counts = Counter(
        str(stair_facing[row, column])
        for row, column in zip(active_rows, active_columns, strict=True)
        if representation[row, column] == "bottom_stair"
    )
    return ShellEvidence(
        world_bounds_blocks=(x0, z0, x1, z1),
        built_bounds_blocks=built_bounds,
        floor_y=floor_y,
        floor_navd88=base_navd88,
        vertical_offset=float(vertical_offset),
        scale=scale,
        roof_surface_y=roof_surface_y,
        quantized_roof_surface_y=quantized_surface_y,
        roof_block_y=roof_block_y,
        active_mask=active,
        exterior_wall_mask=exterior_wall_mask,
        internal_wall_mask=internal_wall_mask,
        material_counts=dict(sorted(material_counts.items())),
        state_counts=dict(sorted(state_counts.items())),
        role_counts=dict(sorted(role_counts.items())),
        roof_representation_counts=dict(sorted(representation_counts.items())),
        stair_facing_counts=dict(sorted(facing_counts.items())),
        skipped_counts=dict(sorted(skipped.items())),
        cleared_air_blocks=cleared_air_blocks,
        foundation_column_count=len(foundation_columns),
        clipped_writes=clipped_writes,
        internal_wall_drop_metres=max(1.0, 2.0 * roof_raster.resolution),
        neighbor_radius_metres=neighbor_radius,
        parent_id=building.parent_id,
        roof_backing_metres=float(roof_backing_metres),
        roof_backing_blocks=backing_blocks,
    )


def _wall_masks(
    active: np.ndarray,
    quantized_surface_y: np.ndarray,
    *,
    floor_surface_y: float,
    resolution: float,
    scale: int,
    neighbor_offsets: tuple[tuple[int, int], ...],
) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = active.shape
    exterior = np.zeros_like(active)
    internal = np.zeros_like(active)
    immediate = ((-1, 0), (1, 0), (0, -1), (0, 1))
    drop_threshold_blocks = max(1.0, 2.0 * resolution) * scale

    for row, column in zip(*np.nonzero(active), strict=True):
        current = float(quantized_surface_y[row, column])
        for dr, dc in immediate:
            nr, nc = int(row + dr), int(column + dc)
            if not (0 <= nr < rows and 0 <= nc < columns and active[nr, nc]):
                exterior[row, column] = True
                # Outside the roof mask has floor height by definition.
                if current < floor_surface_y:
                    raise AssertionError(
                        "active roof surface is below outside floor height"
                    )
        for dr, dc in neighbor_offsets:
            nr, nc = int(row + dr), int(column + dc)
            if not (0 <= nr < rows and 0 <= nc < columns) or not active[nr, nc]:
                neighbor = floor_surface_y
            else:
                neighbor = float(quantized_surface_y[nr, nc])
            if (
                0 <= nr < rows
                and 0 <= nc < columns
                and active[nr, nc]
                and current - neighbor >= drop_threshold_blocks - 1.0e-9
            ):
                internal[row, column] = True
    return exterior, internal


def _roof_representations(
    active: np.ndarray,
    quantized_surface_y: np.ndarray,
    roof_raster: RoofRaster,
) -> tuple[np.ndarray, np.ndarray]:
    representation = np.full(active.shape, "none", dtype="<U16")
    stair_facing = np.full(active.shape, "", dtype="<U5")
    preliminary: dict[tuple[int, int], str] = {}
    directions = {
        "east": (0, 1),
        "west": (0, -1),
        "south": (1, 0),
        "north": (-1, 0),
    }
    opposite = {"east": "west", "west": "east", "south": "north", "north": "south"}

    for row, column in zip(*np.nonzero(active), strict=True):
        surface = float(quantized_surface_y[row, column])
        if not math.isclose(surface, round(surface), abs_tol=1.0e-9):
            representation[row, column] = "bottom_slab"
            continue
        representation[row, column] = "full_block"
        gx = float(roof_raster.gradient_x[row, column])
        gz = float(roof_raster.gradient_z[row, column])
        if not math.isfinite(gx) or not math.isfinite(gz):
            continue
        major, minor = max(abs(gx), abs(gz)), min(abs(gx), abs(gz))
        if major < 0.05 or major < 1.25 * minor:
            continue
        uphill = (
            ("east" if gx > 0.0 else "west")
            if abs(gx) >= abs(gz)
            else ("south" if gz > 0.0 else "north")
        )
        downhill = opposite[uphill]
        ur, uc = directions[uphill]
        dr, dc = directions[downhill]
        uphill_cell = (int(row + ur), int(column + uc))
        downhill_cell = (int(row + dr), int(column + dc))
        if not (
            _inside_active(active, *uphill_cell)
            and _inside_active(active, *downhill_cell)
        ):
            continue
        uphill_surface = float(quantized_surface_y[uphill_cell])
        downhill_surface = float(quantized_surface_y[downhill_cell])
        drop = surface - downhill_surface
        if (
            0.5 - 1.0e-9 <= drop <= 1.0 + 1.0e-9
            and uphill_surface >= surface - 1.0e-9
            and float(roof_raster.heights[downhill_cell])
            < float(roof_raster.heights[row, column])
        ):
            preliminary[(int(row), int(column))] = uphill

    # Require a lateral partner so a noisy single cell cannot become a notch.
    for (row, column), facing in preliminary.items():
        lateral = ((-1, 0), (1, 0)) if facing in {"east", "west"} else ((0, -1), (0, 1))
        if any(
            preliminary.get((row + dr, column + dc)) == facing for dr, dc in lateral
        ):
            representation[row, column] = "bottom_stair"
            stair_facing[row, column] = facing
    return representation, stair_facing


def _neighbor_offsets(resolution: float, radius: float) -> tuple[tuple[int, int], ...]:
    cells = max(1, math.ceil(radius / resolution))
    offsets = []
    for dr in range(-cells, cells + 1):
        for dc in range(-cells, cells + 1):
            if (dr or dc) and math.hypot(
                dr * resolution, dc * resolution
            ) <= radius + 1e-9:
                offsets.append((dr, dc))
    return tuple(offsets)


def _inside_active(active: np.ndarray, row: int, column: int) -> bool:
    return (
        0 <= row < active.shape[0]
        and 0 <= column < active.shape[1]
        and bool(active[row, column])
    )


def _positive_integer_scale(canvas: Any) -> int:
    value = getattr(canvas, "scale", None)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, np.integer))
        or value <= 0
    ):
        raise ValueError("canvas.scale must be a positive integer blocks-per-metre")
    return int(value)


def _validate_raster_arrays(raster: RoofRaster) -> None:
    shape = raster.heights.shape
    if len(shape) != 2 or any(
        array.shape != shape
        for array in (
            raster.gradient_x,
            raster.gradient_z,
            raster.face_indices,
            raster.footprint_mask,
            raster.missing_mask,
        )
    ):
        raise ValueError(
            "roof raster arrays must share one two-dimensional [z, x] shape"
        )
    expected_missing = raster.footprint_mask & (raster.face_indices < 0)
    if not np.array_equal(raster.missing_mask, expected_missing):
        raise ValueError(
            "roof raster missing mask is inconsistent with footprint coverage"
        )


def _block_bounds(raster: RoofRaster, scale: int) -> tuple[int, int, int, int]:
    scaled = tuple(value * scale for value in raster.bounds)
    rounded = tuple(round(value) for value in scaled)
    if any(
        not math.isclose(value, integer, rel_tol=0.0, abs_tol=1.0e-8)
        for value, integer in zip(scaled, rounded, strict=True)
    ):
        raise ValueError("roof raster bounds must align to Minecraft column edges")
    x0, z0, x1, z1 = (int(value) for value in rounded)
    rows, columns = raster.heights.shape
    if x1 - x0 != columns or z1 - z0 != rows:
        raise ValueError("roof raster bounds, resolution, and array shape disagree")
    return x0, z0, x1, z1


def _roof_family_blocks(family: str) -> dict[str, str]:
    base = _canonical_name(family)
    namespace, path = base.split(":", 1)
    if path == "brick" or path.endswith(("_tile", "_brick")):
        full_path = path + "s"
    elif path == "spruce":
        full_path = path + "_planks"
    elif path in {
        "waxed_cut_copper",
        "waxed_exposed_cut_copper",
        "waxed_weathered_cut_copper",
        "waxed_oxidized_cut_copper",
    }:
        full_path = path
    else:
        raise ValueError(
            "roof_family must be a supported Minecraft tile/brick, spruce, "
            "or waxed cut-copper family"
        )
    return {
        "full": f"{namespace}:{full_path}",
        "slab": f"{namespace}:{path}_slab",
        "stairs": f"{namespace}:{path}_stairs",
    }


def _canonical_name(name: str) -> str:
    value = str(name).strip()
    if not value:
        raise ValueError("Minecraft block name cannot be empty")
    return value if ":" in value else f"minecraft:{value}"


def _state_key(name: str, properties: Mapping[str, str] | None) -> str:
    state: dict[str, Any] = {"Name": name}
    if properties:
        state["Properties"] = dict(properties)
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def _verify_foundations(
    canvas: Any, columns: list[tuple[int, int, int]], floor_y: int
) -> None:
    get_block = getattr(canvas, "get", None)
    if not callable(get_block):
        return
    for x, z, start in columns:
        for y in range(start, floor_y):
            if int(get_block(x, y, z)) == 0:
                raise AssertionError(f"foundation gap at {(x, y, z)}")


__all__ = ["ShellEvidence", "build_measured_shell"]
