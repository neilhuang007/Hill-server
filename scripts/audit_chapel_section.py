#!/usr/bin/env python3
"""Block-level QA for the procedurally rebuilt Chapel section."""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any


DEFAULT_WORLD = Path(
    "runtime/campus-reconstruction/hybrid-voxelearth-ground-roofer-buildings/"
    "hill_school_hybrid_v30_main_buildings_final_1x_20260901"
)
DEFAULT_CHAPEL_BBOX = (-9, 92, -12, 11, 109, 20)
DEFAULT_APRON_RADIUS = 14
INTERIOR_FILL_BLOCKS = {"minecraft:glowstone", "minecraft:smooth_stone"}


def load_hybrid_module(repo: Path) -> Any:
    module_path = repo / "scripts" / "hybridize_voxelearth_roofer_world.py"
    spec = importlib.util.spec_from_file_location("hill_hybrid_chapel_audit", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load hybrid module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_manifest(world: Path) -> dict[str, Any]:
    manifest_path = world / "hill-hybrid-manifest.json"
    if not manifest_path.is_file():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def chapel_anchor_from_manifest(manifest: dict[str, Any]) -> dict[str, Any] | None:
    anchors = (manifest.get("overlay") or {}).get("anchors") or []
    chapel_anchors = [
        anchor
        for anchor in anchors
        if "chapel" in str(anchor.get("name") or "").lower()
    ]
    if len(chapel_anchors) != 1:
        return None
    return chapel_anchors[0]


def bbox_from_anchor(anchor: dict[str, Any] | None) -> tuple[int, int, int, int, int, int]:
    if anchor is None:
        return DEFAULT_CHAPEL_BBOX
    bbox = anchor.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 6:
        return DEFAULT_CHAPEL_BBOX
    return tuple(int(round(float(value))) for value in bbox)  # type: ignore[return-value]


def raw_chapel_blocks(
    manifest: dict[str, Any],
    anchor: dict[str, Any],
    hybrid: Any,
) -> set[tuple[int, int, int]]:
    npz_path = Path(str(manifest["roofer_overlay_npz"]))
    building_id = int(anchor["building_id"])
    with hybrid.np.load(npz_path, allow_pickle=False) as payload:
        occupied_neu = payload["occupied_neu"].astype(hybrid.np.int32, copy=False)
        building_ids = payload["building_ids"].astype(hybrid.np.uint16, copy=False)
        metric_origin = payload["metric_origin_neu_m"].astype(float, copy=False)
        meshsize = float(payload["meshsize_m"][0])
    coords = occupied_neu[building_ids == building_id]
    world_transform = manifest["world_transform"]
    transform = hybrid.WorldTransform(
        origin_ecef=tuple(float(value) for value in world_transform["origin_ecef"]),
        center_latitude=float(world_transform["center"][0]),
        center_longitude=float(world_transform["center"][1]),
        blocks_per_metre=float(world_transform["blocks_per_metre"]),
        target_minimum_y=int(world_transform["target_minimum_y"]),
    )
    mapped_columns = hybrid.map_ne_cells_to_voxelearth_xz(
        coords[:, :2],
        metric_origin,
        meshsize,
        transform,
    )
    vertical_offset = float(anchor["vertical_offset"])
    return {
        (
            mapped_columns[(int(north), int(east))][0],
            int(round(float(up) + vertical_offset)),
            mapped_columns[(int(north), int(east))][1],
        )
        for north, east, up in coords
    }


def top_y_at(
    world: Any,
    air_blocks: set[str],
    x: int,
    z: int,
    *,
    high_y: int,
    low_y: int,
) -> tuple[int, str] | None:
    for y in range(high_y, low_y - 1, -1):
        block = world.get_block(x, y, z)
        if block not in air_blocks:
            return y, block
    return None


def audit_chapel_section(
    world_path: Path,
    *,
    repo: Path,
    apron_radius: int,
    max_interior_solid_fraction: float,
    max_terrain_delta: int,
) -> tuple[dict[str, Any], list[str]]:
    started = time.monotonic()
    hybrid = load_hybrid_module(repo)
    manifest = load_manifest(world_path)
    anchor = chapel_anchor_from_manifest(manifest)
    min_x, min_y, min_z, max_x, max_y, max_z = bbox_from_anchor(anchor)
    anchor_ground_y = int(round(float((anchor or {}).get("voxelearth_ring_ground_y") or min_y)))
    expected_ground_y = min_y - 1
    minimum_y = int(
        ((manifest.get("world_transform") or {}).get("target_minimum_y"))
        or expected_ground_y - 32
    )
    world = hybrid.AnvilWorld(world_path)

    interior_blocks: Counter[str] = Counter()
    raw_blocks: set[tuple[int, int, int]] = set()
    shell_blocks: set[tuple[int, int, int]] = set()
    interior_coordinates: set[tuple[int, int, int]] = set()
    if anchor is not None:
        raw_blocks = raw_chapel_blocks(manifest, anchor, hybrid)
        shell_blocks, _removed = hybrid.hollow_chapel_blocks(raw_blocks)
        interior_coordinates = raw_blocks - shell_blocks
    for x, y, z in interior_coordinates:
        block = world.get_block(x, y, z)
        if block not in hybrid.AIR_BLOCKS:
            interior_blocks[block] += 1
    interior_positions = len(interior_coordinates)
    interior_non_air = sum(interior_blocks.values())

    terrain_tops: list[tuple[int, int, int, str]] = []
    terrain_missing: list[tuple[int, int]] = []
    terrain_blocks: Counter[str] = Counter()
    scan_high_y = max_y + 32
    for x in range(min_x - apron_radius, max_x + apron_radius + 1):
        for z in range(min_z - apron_radius, max_z + apron_radius + 1):
            if min_x <= x <= max_x and min_z <= z <= max_z:
                continue
            top = top_y_at(
                world,
                hybrid.AIR_BLOCKS,
                x,
                z,
                high_y=scan_high_y,
                low_y=minimum_y,
            )
            if top is None:
                terrain_missing.append((x, z))
                continue
            y, block = top
            terrain_tops.append((x, z, y, block))
            terrain_blocks[block] += 1

    terrain_ys = [y for _x, _z, y, _block in terrain_tops]
    terrain_low = min(terrain_ys, default=None)
    terrain_high = max(terrain_ys, default=None)
    low_columns = [
        [x, z, y, block]
        for x, z, y, block in terrain_tops
            if y < expected_ground_y - max_terrain_delta
    ]
    high_columns = [
        [x, z, y, block]
        for x, z, y, block in terrain_tops
        if y > expected_ground_y + max_terrain_delta
    ]
    subsurface_air: list[tuple[int, int, int]] = []
    for x, z, y, _block in terrain_tops:
        for subsurface_y in range(minimum_y, y):
            if world.get_block(x, subsurface_y, z) in hybrid.AIR_BLOCKS:
                subsurface_air.append((x, subsurface_y, z))
                break

    interior_solid_fraction = interior_non_air / max(1, interior_positions)
    interior_fill_counts = {
        block: interior_blocks[block]
        for block in sorted(INTERIOR_FILL_BLOCKS)
        if interior_blocks[block]
    }
    interior_fill_count = sum(interior_fill_counts.values())
    glowstone_count = interior_blocks["minecraft:glowstone"]
    result = {
        "format": "hill-chapel-section-audit-v1",
        "world": str(world_path),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "chapel": {
            "anchor_found": anchor is not None,
            "bbox": [min_x, min_y, min_z, max_x, max_y, max_z],
            "anchor_ground_y": anchor_ground_y,
            "expected_ground_y": expected_ground_y,
        },
        "interior": {
            "source_occupied_blocks": len(raw_blocks),
            "generated_shell_blocks": len(shell_blocks),
            "checked_blocks": interior_positions,
            "non_air_blocks": interior_non_air,
            "solid_fraction": round(interior_solid_fraction, 6),
            "max_solid_fraction": max_interior_solid_fraction,
            "glowstone_blocks": glowstone_count,
            "fill_blocks": interior_fill_count,
            "fill_block_counts": interior_fill_counts,
            "top_blocks": interior_blocks.most_common(12),
        },
        "terrain": {
            "radius": apron_radius,
            "checked_columns": len(terrain_tops),
            "missing_columns": len(terrain_missing),
            "ground_y_min": terrain_low,
            "ground_y_max": terrain_high,
            "max_delta": max_terrain_delta,
            "low_columns": len(low_columns),
            "high_columns": len(high_columns),
            "subsurface_air_columns": len(subsurface_air),
            "low_samples": low_columns[:20],
            "high_samples": high_columns[:20],
            "subsurface_air_samples": [list(sample) for sample in subsurface_air[:20]],
            "top_blocks": terrain_blocks.most_common(12),
        },
    }

    failures: list[str] = []
    if anchor is None:
        failures.append("expected exactly one Chapel anchor in the hybrid manifest")
    if glowstone_count:
        failures.append(f"Chapel interior contains {glowstone_count} glowstone blocks")
    if interior_fill_count:
        failures.append(
            f"Chapel interior contains {interior_fill_count} solid floor/fill blocks"
        )
    if interior_solid_fraction > max_interior_solid_fraction:
        failures.append(
            "Chapel interior is not hollow: "
            f"{interior_non_air}/{interior_positions} contracted interior blocks are non-air"
        )
    if terrain_missing:
        failures.append(f"{len(terrain_missing)} Chapel apron columns have no terrain")
    if low_columns:
        failures.append(
            f"{len(low_columns)} Chapel apron columns are more than {max_terrain_delta} block(s) below expected_ground_y={expected_ground_y}"
        )
    if high_columns:
        failures.append(
            f"{len(high_columns)} Chapel apron columns are more than {max_terrain_delta} block(s) above expected_ground_y={expected_ground_y}"
        )
    if subsurface_air:
        failures.append(
            f"{len(subsurface_air)} Chapel apron columns contain air below their surface"
        )
    result["passed"] = not failures
    result["failures"] = failures
    return result, failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apron-radius", type=int, default=DEFAULT_APRON_RADIUS)
    parser.add_argument("--max-interior-solid-fraction", type=float, default=0.0)
    parser.add_argument("--max-terrain-delta", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result, failures = audit_chapel_section(
        args.world.resolve(),
        repo=args.repo.resolve(),
        apron_radius=args.apron_radius,
        max_interior_solid_fraction=args.max_interior_solid_fraction,
        max_terrain_delta=args.max_terrain_delta,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
