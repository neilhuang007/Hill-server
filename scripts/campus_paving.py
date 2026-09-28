"""Half-block paving over the measured Hill campus DEM.

Minecraft has no literal asphalt block.  This module uses polished deepslate as
the documented vanilla approximation for roads and parking, while footpaths
use smooth stone.  It changes only exposed, measured pavement surface cells;
terrain, courts, structures, doors, railings, and other semantic roles are not
touched.

A full block at block Y has physical top Y + 1 and a bottom slab has physical
top Y + 0.5.  Those two supported states represent every half-block surface.
On broad road contours, a bottom stair can join those two levels without
changing either measured terrace: its downhill tread is Y + 0.5 and its uphill
tread is Y + 1.  Stairs are emitted only in supported, coherent runs whose
orientation follows the local DEM gradient.  Top-slab state definitions are
retained in each construction family, but are not emitted for terrain: a top
slab has the same integer top as a full block and would leave an unsupported
half-block void beneath the paving surface.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

DEFAULT_ROLE_NAMES = (
    "air",
    "terrain",
    "pavement",
    "facade",
    "roof",
    "trim",
    "window",
    "vegetation",
    "railing",
    "lighting",
    "door",
    "floor",
    "fixture",
    "furniture",
)

BOTTOM_SLAB_PROPERTIES = {"type": "bottom", "waterlogged": "false"}
TOP_SLAB_PROPERTIES = {"type": "top", "waterlogged": "false"}


@dataclass(frozen=True)
class PavingFamily:
    name: str
    source_blocks: frozenset[str]
    full_block: str
    slab_block: str
    interpretation: str
    stair_block: str | None = None

    def full_state(self) -> dict[str, Any]:
        return {"Name": self.full_block}

    def bottom_slab_state(self) -> dict[str, Any]:
        return {"Name": self.slab_block, "Properties": dict(BOTTOM_SLAB_PROPERTIES)}

    def top_slab_state(self) -> dict[str, Any]:
        return {"Name": self.slab_block, "Properties": dict(TOP_SLAB_PROPERTIES)}

    def bottom_stair_state(self, facing: str) -> dict[str, Any]:
        if self.stair_block is None:
            raise ValueError(f"paving family {self.name!r} has no stair block")
        return {
            "Name": self.stair_block,
            "Properties": {
                "facing": facing,
                "half": "bottom",
                "shape": "straight",
                "waterlogged": "false",
            },
        }


FOOTPATH = PavingFamily(
    name="footpath",
    source_blocks=frozenset({"minecraft:smooth_stone", "minecraft:smooth_stone_slab"}),
    full_block="minecraft:smooth_stone",
    slab_block="minecraft:smooth_stone_slab",
    interpretation="smooth stone pedestrian paving",
)

ROAD = PavingFamily(
    name="road",
    source_blocks=frozenset(
        {
            "minecraft:gray_concrete",
            "minecraft:light_gray_concrete",
            "minecraft:polished_deepslate",
            "minecraft:polished_deepslate_slab",
            "minecraft:polished_deepslate_stairs",
        }
    ),
    full_block="minecraft:polished_deepslate",
    slab_block="minecraft:polished_deepslate_slab",
    interpretation="vanilla polished-deepslate approximation; not literal asphalt",
    stair_block="minecraft:polished_deepslate_stairs",
)

DEFAULT_FAMILIES = (FOOTPATH, ROAD)


def _canonical_name(name: str) -> str:
    return name if name.startswith("minecraft:") else f"minecraft:{name}"


def _state_id(canvas: Any, state: Mapping[str, Any]) -> int:
    """Register an exact block state on a Canvas-like object."""

    name = _canonical_name(str(state["Name"]))
    properties = {
        str(key): str(value) for key, value in (state.get("Properties") or {}).items()
    }
    state_method = getattr(canvas, "state", None)
    if callable(state_method):
        return int(state_method(name, properties or None))

    entry: dict[str, Any] = {"Name": name}
    if properties:
        entry["Properties"] = properties
    key = json.dumps(entry, sort_keys=True)
    for index, existing in enumerate(canvas.palette):
        if json.dumps(existing, sort_keys=True) == key:
            return index
    canvas.palette.append(entry)
    return len(canvas.palette) - 1


def _role_names(canvas: Any, supplied: Sequence[str] | None) -> tuple[str, ...]:
    if supplied is not None:
        result = tuple(str(value) for value in supplied)
    elif getattr(canvas, "role_names", None) is not None:
        result = tuple(str(value) for value in canvas.role_names)
    else:
        result = DEFAULT_ROLE_NAMES
    if "pavement" not in result:
        raise ValueError("role names do not define a pavement role")
    return result


def _validate_canvas(
    canvas: Any,
    continuous_elevations: np.ndarray,
    original_ground_heights: np.ndarray,
    scale: int,
) -> tuple[np.ndarray, np.ndarray]:
    if scale <= 0:
        raise ValueError("scale must be positive")
    data = np.asarray(canvas.data)
    roles = np.asarray(canvas.roles)
    if data.ndim != 3 or roles.shape != data.shape:
        raise ValueError("canvas data and roles must be matching [y,z,x] arrays")
    elevations = np.asarray(continuous_elevations, dtype=np.float64)
    heights = np.asarray(original_ground_heights)
    expected_shape = data.shape[1:]
    if elevations.shape != expected_shape or heights.shape != expected_shape:
        raise ValueError(
            f"elevations and ground heights must have canvas [z,x] shape {expected_shape}"
        )
    if not np.all(np.isfinite(elevations)):
        raise ValueError("continuous elevations contain non-finite values")
    if not np.issubdtype(heights.dtype, np.integer):
        rounded = np.rint(heights)
        if not np.array_equal(heights, rounded):
            raise ValueError(
                "original ground heights must be integer block coordinates"
            )
        heights = rounded.astype(np.int64)
    else:
        heights = heights.astype(np.int64, copy=False)
    return elevations, heights


def smooth_exposed_measured_pavement(
    canvas: Any,
    continuous_elevations: np.ndarray,
    original_ground_heights: np.ndarray,
    *,
    vertical_offset: float,
    scale: int | None = None,
    role_names: Sequence[str] | None = None,
    families: Sequence[PavingFamily] = DEFAULT_FAMILIES,
) -> dict[str, Any]:
    """Quantize exposed measured path/road surfaces at half-block intervals.

    Args:
        canvas: Canvas-like object with ``data``, ``roles``, ``palette``,
            ``x_min``, ``z_min``, ``y_min``, and optionally ``state``.
        continuous_elevations: Measured DEM elevation in metres, sampled to the
            canvas [z,x] grid before integer rounding.
        original_ground_heights: Integer surface-block Y values returned by
            ``build_ground`` (``round((elevation + offset) * scale) - 1``).
        vertical_offset: The same fixed elevation-to-world offset used by
            ``build_ground``.  It is never fitted per cell or per feature.
        scale: Blocks per metre.  Defaults to ``canvas.scale``.
        role_names: Role-index ordering.  Defaults to ``canvas.role_names`` or
            the Chapel canvas role ordering.
        families: Explicit source-to-construction mappings.

    Returns:
        JSON-serializable QA statistics.  The physical target is
        ``(elevation + vertical_offset) * scale``. A full block's lower
        coordinate is one block below its physical top.
    """

    if scale is None:
        scale = int(canvas.scale)
    else:
        scale = int(scale)
    if getattr(canvas, "scale", scale) != scale:
        raise ValueError("scale does not match canvas.scale")
    elevations, ground_heights = _validate_canvas(
        canvas, continuous_elevations, original_ground_heights, scale
    )
    names = _role_names(canvas, role_names)
    pavement_role = names.index("pavement")
    supported_substrate_roles = {pavement_role}
    if "terrain" in names:
        supported_substrate_roles.add(names.index("terrain"))
    y_min = int(canvas.y_min)

    family_by_source: dict[str, PavingFamily] = {}
    for family in families:
        for source_block in family.source_blocks:
            canonical = _canonical_name(source_block)
            if canonical in family_by_source:
                raise ValueError(
                    f"paving source block belongs to multiple families: {canonical}"
                )
            family_by_source[canonical] = family

    candidate_cells = 0
    smoothed_cells = 0
    skipped_not_pavement = 0
    skipped_not_exposed = 0
    skipped_unrecognized_material = 0
    skipped_out_of_bounds = 0
    family_counts: dict[str, int] = {family.name: 0 for family in families}
    representation_counts = {"full_block": 0, "bottom_slab": 0, "top_slab": 0}
    quantized_surfaces: dict[tuple[int, int], float] = {}
    processed: dict[tuple[int, int], dict[str, Any]] = {}

    for iz, ix in np.ndindex(elevations.shape):
        ground_y = int(ground_heights[iz, ix])
        ground_iy = ground_y - y_min
        if not (0 <= ground_iy < canvas.data.shape[0]):
            skipped_out_of_bounds += 1
            continue
        state_id = int(canvas.data[ground_iy, iz, ix])
        role_id = int(canvas.roles[ground_iy, iz, ix])
        if state_id == 0 or role_id != pavement_role:
            skipped_not_pavement += 1
            continue
        candidate_cells += 1
        source_name = _canonical_name(str(canvas.palette[state_id]["Name"]))
        family = family_by_source.get(source_name)
        if family is None:
            skipped_unrecognized_material += 1
            continue

        # The original measured surface must remain exposed.  This prevents a
        # late call from writing slabs into architecture, doors, or railings.
        above_iy = ground_iy + 1
        if above_iy >= canvas.data.shape[0] or int(canvas.data[above_iy, iz, ix]) != 0:
            skipped_not_exposed += 1
            continue

        target_surface = (
            float(elevations[iz, ix]) + float(vertical_offset)
        ) * scale
        half_units = math.floor(target_surface * 2.0 + 0.5)
        quantized_surface = half_units / 2.0
        residual = abs(quantized_surface - target_surface)
        if residual > 0.250000001:
            raise AssertionError(
                f"half-block quantization residual exceeds 0.25: {residual}"
            )

        if half_units % 2 == 0:
            surface_block_y = half_units // 2 - 1
            surface_state = family.full_state()
            representation = "full_block"
        else:
            surface_block_y = half_units // 2
            surface_state = family.bottom_slab_state()
            representation = "bottom_slab"
        surface_iy = surface_block_y - y_min
        if not (0 <= surface_iy < canvas.data.shape[0]):
            skipped_out_of_bounds += 1
            continue

        # Rounding build_ground to an integer means the half-step surface block
        # is either the original top or the empty cell directly above it.
        if surface_block_y not in {ground_y, ground_y + 1}:
            raise ValueError(
                "original ground heights do not correspond to the supplied elevations/offset/scale"
            )
        destination_state = int(canvas.data[surface_iy, iz, ix])
        destination_role = int(canvas.roles[surface_iy, iz, ix])
        if destination_state != 0 and destination_role != pavement_role:
            skipped_not_exposed += 1
            continue

        full_state_id = _state_id(canvas, family.full_state())
        surface_state_id = _state_id(canvas, surface_state)
        # Keep a coherent full-block substrate when the measured surface rises
        # into a bottom slab in the cell above the original ground block.
        if surface_block_y == ground_y + 1:
            canvas.data[ground_iy, iz, ix] = full_state_id
            canvas.roles[ground_iy, iz, ix] = pavement_role
        canvas.data[surface_iy, iz, ix] = surface_state_id
        canvas.roles[surface_iy, iz, ix] = pavement_role

        quantized_surfaces[(iz, ix)] = quantized_surface
        processed[(iz, ix)] = {
            "family": family,
            "representation": representation,
            "surface_block_y": surface_block_y,
            "target_surface": target_surface,
            "quantized_surface": quantized_surface,
            "surface_residuals": (residual,),
        }
        smoothed_cells += 1
        family_counts[family.name] += 1
        representation_counts[representation] += 1

    # Replace selected full road blocks at a half-step transition with bottom
    # stairs.  The quantized terrace elevations are unchanged: the stair's low
    # tread matches the downhill slab and its high tread matches the full-block
    # terrace.  Requiring a same-facing lateral neighbor avoids isolated stair
    # notches caused by DEM noise.
    directions = {
        "east": (0, 1),
        "west": (0, -1),
        "south": (1, 0),
        "north": (-1, 0),
    }
    stair_rejections = {
        "not_interior_road_neighborhood": 0,
        "unsupported_substrate": 0,
        "non_gentle_or_ambiguous_gradient": 0,
        "neighbor_surface_mismatch": 0,
        "target_outside_stair_band": 0,
        "isolated_transition": 0,
    }
    eligible_full_road_cells = 0
    preliminary_stairs: dict[tuple[int, int], str] = {}
    for (iz, ix), record in processed.items():
        family = record["family"]
        if (
            family.stair_block is None
            or family.name != ROAD.name
            or record["representation"] != "full_block"
        ):
            continue
        eligible_full_road_cells += 1
        neighbors = {
            facing: processed.get((iz + dz, ix + dx))
            for facing, (dz, dx) in directions.items()
        }
        if any(
            neighbor is None or neighbor["family"].name != ROAD.name
            for neighbor in neighbors.values()
        ):
            stair_rejections["not_interior_road_neighborhood"] += 1
            continue

        surface_iy = int(record["surface_block_y"]) - y_min
        below_iy = surface_iy - 1
        if (
            below_iy < 0
            or int(canvas.data[below_iy, iz, ix]) == 0
            or int(canvas.roles[below_iy, iz, ix]) not in supported_substrate_roles
        ):
            stair_rejections["unsupported_substrate"] += 1
            continue

        target = float(record["target_surface"])
        gx = (
            float(neighbors["east"]["target_surface"])
            - float(neighbors["west"]["target_surface"])
        ) / 2.0
        gz = (
            float(neighbors["south"]["target_surface"])
            - float(neighbors["north"]["target_surface"])
        ) / 2.0
        abs_gx, abs_gz = abs(gx), abs(gz)
        major, minor = max(abs_gx, abs_gz), min(abs_gx, abs_gz)
        if major < 0.125 or major > 0.75 or major < 1.25 * minor:
            stair_rejections["non_gentle_or_ambiguous_gradient"] += 1
            continue
        if abs_gx >= abs_gz:
            facing = "east" if gx > 0 else "west"
            cross_facings = ("north", "south")
        else:
            facing = "south" if gz > 0 else "north"
            cross_facings = ("west", "east")
        downhill_facing = {
            "east": "west",
            "west": "east",
            "south": "north",
            "north": "south",
        }[facing]
        uphill = neighbors[facing]
        downhill = neighbors[downhill_facing]
        surface = float(record["quantized_surface"])
        downhill_surface = float(downhill["quantized_surface"])
        uphill_surface = float(uphill["quantized_surface"])
        cross_surfaces = [
            float(neighbors[cross]["quantized_surface"]) for cross in cross_facings
        ]
        if not (
            surface - 1.0 <= downhill_surface <= surface - 0.5
            and surface <= uphill_surface <= surface + 0.5
            and float(downhill["target_surface"])
            < target
            < float(uphill["target_surface"])
            and all(abs(value - surface) <= 0.5 for value in cross_surfaces)
        ):
            stair_rejections["neighbor_surface_mismatch"] += 1
            continue

        # A stair has two equal-area tread elevations.  Keep its area-weighted
        # mean plane within one eighth block of the measured target; individual
        # tread residuals are reported below rather than represented by a false
        # single-height residual.
        stair_mean_plane = surface - 0.25
        if abs(stair_mean_plane - target) > 0.125000001:
            stair_rejections["target_outside_stair_band"] += 1
            continue
        preliminary_stairs[(iz, ix)] = facing

    final_stairs: dict[tuple[int, int], str] = {}
    for (iz, ix), facing in preliminary_stairs.items():
        lateral_offsets = (
            ((-1, 0), (1, 0)) if facing in {"east", "west"} else ((0, -1), (0, 1))
        )
        if any(
            preliminary_stairs.get((iz + dz, ix + dx)) == facing
            for dz, dx in lateral_offsets
        ):
            final_stairs[(iz, ix)] = facing
        else:
            stair_rejections["isolated_transition"] += 1

    stair_facing_counts = {facing: 0 for facing in directions}
    stair_tread_residuals: list[float] = []
    stair_mean_plane_residuals: list[float] = []
    for (iz, ix), facing in final_stairs.items():
        record = processed[(iz, ix)]
        family = record["family"]
        surface_iy = int(record["surface_block_y"]) - y_min
        canvas.data[surface_iy, iz, ix] = _state_id(
            canvas, family.bottom_stair_state(facing)
        )
        canvas.roles[surface_iy, iz, ix] = pavement_role
        target = float(record["target_surface"])
        high_tread = float(record["quantized_surface"])
        tread_residuals = (abs(high_tread - 0.5 - target), abs(high_tread - target))
        record["representation"] = "bottom_stair"
        record["surface_residuals"] = tread_residuals
        representation_counts["full_block"] -= 1
        representation_counts.setdefault("bottom_stair", 0)
        representation_counts["bottom_stair"] += 1
        stair_facing_counts[facing] += 1
        stair_tread_residuals.extend(tread_residuals)
        stair_mean_plane_residuals.append(abs(high_tread - 0.25 - target))

    representation_counts.setdefault("bottom_stair", 0)

    adjacent_steps: list[float] = []
    for (iz, ix), surface in quantized_surfaces.items():
        for neighbor in ((iz + 1, ix), (iz, ix + 1)):
            neighbor_surface = quantized_surfaces.get(neighbor)
            if neighbor_surface is not None:
                adjacent_steps.append(abs(neighbor_surface - surface))

    cell_mean_residuals = np.asarray(
        [np.mean(record["surface_residuals"]) for record in processed.values()],
        dtype=np.float64,
    )
    cell_mean_squared_residuals = np.asarray(
        [
            np.mean(np.square(record["surface_residuals"]))
            for record in processed.values()
        ],
        dtype=np.float64,
    )
    all_surface_residuals = np.asarray(
        [
            residual
            for record in processed.values()
            for residual in record["surface_residuals"]
        ],
        dtype=np.float64,
    )
    stair_tread_array = np.asarray(stair_tread_residuals, dtype=np.float64)
    stair_mean_plane_array = np.asarray(stair_mean_plane_residuals, dtype=np.float64)
    return {
        "format": "hill-campus-paving-qa-v1",
        "scale_blocks_per_metre": scale,
        "half_block_metres": 0.5 / scale,
        "target_surface_formula": "(elevation_m + vertical_offset) * scale",
        "candidate_measured_pavement_cells": candidate_cells,
        "smoothed_cell_count": smoothed_cells,
        "skipped_not_pavement": skipped_not_pavement,
        "skipped_not_exposed": skipped_not_exposed,
        "skipped_unrecognized_material": skipped_unrecognized_material,
        "skipped_out_of_bounds": skipped_out_of_bounds,
        "family_cell_counts": family_counts,
        "representation_cell_counts": representation_counts,
        "stair_count": len(final_stairs),
        "stair_facing_counts": stair_facing_counts,
        "stair_eligible_full_road_cells": eligible_full_road_cells,
        "stair_rejection_counts": stair_rejections,
        "max_surface_residual_blocks": (
            float(all_surface_residuals.max()) if all_surface_residuals.size else None
        ),
        "mean_surface_residual_blocks": (
            float(cell_mean_residuals.mean()) if cell_mean_residuals.size else None
        ),
        "rms_surface_residual_blocks": (
            float(math.sqrt(cell_mean_squared_residuals.mean()))
            if cell_mean_squared_residuals.size
            else None
        ),
        "max_surface_residual_metres": (
            float(all_surface_residuals.max() / scale)
            if all_surface_residuals.size
            else None
        ),
        "stair_max_tread_residual_blocks": (
            float(stair_tread_array.max()) if stair_tread_array.size else None
        ),
        "stair_mean_tread_residual_blocks": (
            float(stair_tread_array.mean()) if stair_tread_array.size else None
        ),
        "stair_max_mean_plane_residual_blocks": (
            float(stair_mean_plane_array.max()) if stair_mean_plane_array.size else None
        ),
        "stair_residual_note": (
            "Each bottom stair has equal-area low/high treads at quantized_surface "
            "- 0.5 and quantized_surface blocks; residual extrema include both."
        ),
        "distinct_quantized_surface_count": len(set(quantized_surfaces.values())),
        "quantized_surface_range_blocks": (
            [
                float(min(quantized_surfaces.values())),
                float(max(quantized_surfaces.values())),
            ]
            if quantized_surfaces
            else None
        ),
        "max_adjacent_surface_step_blocks": (
            float(max(adjacent_steps)) if adjacent_steps else None
        ),
        "asphalt_material_note": ROAD.interpretation,
    }


__all__ = [
    "BOTTOM_SLAB_PROPERTIES",
    "DEFAULT_FAMILIES",
    "FOOTPATH",
    "PavingFamily",
    "ROAD",
    "TOP_SLAB_PROPERTIES",
    "smooth_exposed_measured_pavement",
]
