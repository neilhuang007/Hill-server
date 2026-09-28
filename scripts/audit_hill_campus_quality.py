#!/usr/bin/env python3
"""Fast material and coverage gate for generated Hill campus Anvil worlds.

The audit deliberately checks visible outcomes rather than merely accepting a
successful generator exit code.  It is used while iterating on campus worlds
to prevent four regressions reported during visual QA:

* named roads must use a restrained dark-concrete surface;
* non-building ground must not be mapped to sand/sandstone;
* both mapped tennis-court polygons must be present as court surfaces; and
* facades must record per-building VoxelEarth colour sampling and nearest-block
  palette matching instead of using a metadata-only wall default; and
* exterior building rings must contain terrain instead of elevated source fuzz;
* the Chapel must receive its wider landmark cleanup ring; and
* rebuilt buildings must have complete, non-floating support.
"""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Iterable

from shapely.geometry import Point, shape
from shapely.ops import transform as geometry_transform, unary_union
from shapely.prepared import prep


DEFAULT_RESOURCES = Path(
    "runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831/"
    "src/minecraft-plugin/src/main/resources"
)
DEFAULT_OSM_SITE_FEATURES = Path(
    "runtime/campus-data/gis/osm--75.63850-40.24338--75.61808-40.26086.json"
)
TENNIS_OSM_IDS = {
    1_488_359_323,
    1_488_359_324,
    *range(956_158_564, 956_158_573),
}
DARK_ROAD_BLOCKS = {
    "minecraft:black_concrete",
    "minecraft:gray_concrete",
}
TENNIS_BLOCKS = {
    "minecraft:blue_concrete",
    "minecraft:cyan_concrete",
    "minecraft:green_concrete",
    "minecraft:white_concrete",
}
SANDLIKE_BLOCKS = {
    "minecraft:sand",
    "minecraft:red_sand",
    "minecraft:sandstone",
    "minecraft:smooth_sandstone",
    "minecraft:cut_sandstone",
    "minecraft:red_sandstone",
    "minecraft:smooth_red_sandstone",
    "minecraft:cut_red_sandstone",
}
ROAD_NAME_TOKENS = ("alley", "drive", "road", "street")


def load_hybrid_module(repo: Path) -> Any:
    module_path = repo / "scripts" / "hybridize_voxelearth_roofer_world.py"
    spec = importlib.util.spec_from_file_location("hill_hybrid_quality_audit", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load hybrid module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_world_features(path: Path, transform: Any) -> list[tuple[dict[str, Any], Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    def to_world(
        longitudes: Iterable[float],
        latitudes: Iterable[float],
        altitudes: Iterable[float] | None = None,
    ) -> tuple[list[float], list[float]]:
        del altitudes
        points = [
            transform.lonlat_to_block(float(longitude), float(latitude))
            for longitude, latitude in zip(longitudes, latitudes)
        ]
        return [point[0] for point in points], [point[1] for point in points]

    return [
        (
            dict(feature.get("properties") or {}),
            geometry_transform(to_world, shape(feature["geometry"])),
        )
        for feature in payload["features"]
    ]


def covered_cells(
    geometry: Any,
    top_surface: dict[tuple[int, int], tuple[int, str]],
) -> Iterable[tuple[int, int]]:
    min_x, min_z, max_x, max_z = geometry.bounds
    for x in range(math.floor(min_x), math.ceil(max_x) + 1):
        for z in range(math.floor(min_z), math.ceil(max_z) + 1):
            if (x, z) in top_surface and geometry.covers(Point(x + 0.5, z + 0.5)):
                yield x, z


def geometry_cells(geometry: Any) -> Iterable[tuple[int, int]]:
    prepared = prep(geometry)
    min_x, min_z, max_x, max_z = geometry.bounds
    for x in range(math.floor(min_x), math.ceil(max_x) + 1):
        for z in range(math.floor(min_z), math.ceil(max_z) + 1):
            if prepared.covers(Point(x + 0.5, z + 0.5)):
                yield x, z


def fraction_for(blocks: Counter[str], accepted: set[str]) -> float:
    return sum(blocks[block] for block in accepted) / max(1, sum(blocks.values()))


def load_official_tennis_features(osm_path: Path, transform: Any) -> list[tuple[dict[str, Any], Any]]:
    payload = json.loads(osm_path.read_text(encoding="utf-8"))
    features: list[tuple[dict[str, Any], Any]] = []
    for element in payload.get("elements", []):
        if int(element.get("id", -1)) not in TENNIS_OSM_IDS:
            continue
        points = [
            transform.lonlat_to_block(float(point["lon"]), float(point["lat"]))
            for point in element.get("geometry", [])
            if "lon" in point and "lat" in point
        ]
        if len(points) < 4:
            continue
        geometry = shape({"type": "Polygon", "coordinates": [points]})
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if geometry.is_empty:
            continue
        features.append((dict(element.get("tags") or {}), geometry))
    return features


def run_audit(
    world: Path,
    resources: Path,
    osm_site_features: Path,
    repo: Path,
) -> tuple[dict[str, Any], list[str]]:
    started = time.monotonic()
    hybrid = load_hybrid_module(repo)
    manifest_path = world / "hill-hybrid-manifest.json"
    voxel_manifest_path = world / "voxelearth-hill-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    transform = hybrid.WorldTransform.from_manifest(voxel_manifest_path)
    top_surface = hybrid.load_top_surface(world)

    surfaces = load_world_features(resources / "hill-campus-surfaces.geojson", transform)
    buildings = load_world_features(resources / "hill-campus-buildings.geojson", transform)
    building_union = unary_union([geometry for _props, geometry in buildings])
    building_mask = prep(building_union.buffer(1.0))
    campus_boundary_features = load_world_features(
        resources / "hill-campus-boundary.geojson",
        transform,
    )
    campus_boundary = unary_union(
        [geometry for _props, geometry in campus_boundary_features]
    )

    ground_sandlike_columns = sum(
        1
        for (x, z), (_y, block) in top_surface.items()
        if block in SANDLIKE_BLOCKS
        and not building_mask.covers(Point(x + 0.5, z + 0.5))
    )

    road_geometries = [
        geometry
        for properties, geometry in surfaces
        if properties.get("kind") == "hard"
        and any(
            token in str(properties.get("name") or "").lower()
            for token in ROAD_NAME_TOKENS
        )
    ]
    road_cells = {
        cell
        for geometry in road_geometries
        for cell in covered_cells(geometry, top_surface)
    }
    road_blocks = Counter(top_surface[cell][1] for cell in road_cells)
    road_dark_fraction = fraction_for(road_blocks, DARK_ROAD_BLOCKS)

    tennis_features = load_official_tennis_features(osm_site_features, transform)
    tennis_kinds = ["tennis" for _properties, _geometry in tennis_features]
    tennis_cells = {
        cell
        for _properties, geometry in tennis_features
        for cell in covered_cells(geometry, top_surface)
    }
    tennis_blocks = Counter(top_surface[cell][1] for cell in tennis_cells)
    tennis_surface_fraction = fraction_for(tennis_blocks, TENNIS_BLOCKS)

    facade = manifest.get("facade_palette") or {}
    facade_material_counts = Counter(facade.get("material_counts") or {})
    facade_total = sum(facade_material_counts.values())
    largest_facade_fraction = (
        max(facade_material_counts.values(), default=0) / max(1, facade_total)
    )

    seam_manifest = manifest.get("building_seam_fill") or {}
    seam_manifest_stats = seam_manifest.get("stats") or {}
    official_seam_manifest = manifest.get("official_building_seam_fill") or {}
    official_seam_stats = official_seam_manifest.get("stats") or {}
    cleanup_manifest = manifest.get("building_apron_cleanup") or {}
    cleanup_stats = cleanup_manifest.get("stats") or {}
    architecture_cleanup_manifest = manifest.get("campus_architecture_cleanup") or {}
    architecture_cleanup_stats = architecture_cleanup_manifest.get("stats") or {}
    chapel_cleanup_manifest = manifest.get("chapel_apron_cleanup") or {}
    chapel_cleanup_stats = chapel_cleanup_manifest.get("stats") or {}
    chapel_section_manifest = manifest.get("chapel_procedural_section") or {}
    chapel_section_stats = chapel_section_manifest.get("stats") or {}
    overlay_manifest = manifest.get("overlay") or {}
    support_audit = manifest.get("support_audit") or {}
    shell_window_audit = manifest.get("shell_window_audit") or {}
    continuous_ground_audit = manifest.get("continuous_ground_audit") or {}
    place_stats = manifest.get("place_stats") or {}
    seam_geometry = (
        unary_union([geometry.buffer(3.0, join_style=2) for _props, geometry in buildings])
        .difference(building_union)
        .intersection(campus_boundary)
    )
    seam_cells = set(geometry_cells(seam_geometry)) if not seam_geometry.is_empty else set()
    missing_seam_cells = sorted(cell for cell in seam_cells if cell not in top_surface)

    result = {
        "format": "hill-campus-quality-audit-v1",
        "world": str(world),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "ground": {
            "sandlike_nonbuilding_columns": ground_sandlike_columns,
        },
        "roads": {
            "named_surface_cells": len(road_cells),
            "dark_concrete_fraction": round(road_dark_fraction, 6),
            "top_blocks": road_blocks.most_common(12),
        },
        "tennis": {
            "feature_count": len(tennis_features),
            "feature_kinds": tennis_kinds,
            "surface_cells": len(tennis_cells),
            "court_surface_fraction": round(tennis_surface_fraction, 6),
            "top_blocks": tennis_blocks.most_common(12),
        },
        "facades": {
            "mode": facade.get("mode"),
            "colour_space": facade.get("colour_space"),
            "sampled_buildings": int(facade.get("sampled_buildings") or 0),
            "material_counts": dict(facade_material_counts),
            "unique_materials": len(facade_material_counts),
            "largest_material_fraction": round(largest_facade_fraction, 6),
        },
        "building_ground_seams": {
            "ring_radius_blocks": 3,
            "ring_cells": len(seam_cells),
            "missing_columns": len(missing_seam_cells),
            "missing_samples": [list(cell) for cell in missing_seam_cells[:20]],
            "manifest_enabled": bool(seam_manifest.get("enabled")),
            "manifest_source": seam_manifest.get("source"),
            "manifest_stats": seam_manifest_stats,
            "official_manifest_enabled": bool(official_seam_manifest.get("enabled")),
            "official_manifest_source": official_seam_manifest.get("source"),
            "official_manifest_stats": official_seam_stats,
        },
        "building_cleanup": {
            "enabled": bool(cleanup_manifest.get("enabled")),
            "radius": int(cleanup_manifest.get("radius") or 0),
            "stats": cleanup_stats,
            "accepted_anchor_count": int(overlay_manifest.get("anchor_count") or 0),
            "campus_architecture_enabled": bool(architecture_cleanup_manifest.get("enabled")),
            "campus_architecture_stats": architecture_cleanup_stats,
            "chapel_enabled": bool(chapel_cleanup_manifest.get("enabled")),
            "chapel_radius": int(chapel_cleanup_manifest.get("radius") or 0),
            "chapel_stats": chapel_cleanup_stats,
            "chapel_procedural_section_enabled": bool(chapel_section_manifest.get("enabled")),
            "chapel_procedural_section_radius": int(chapel_section_manifest.get("radius") or 0),
            "chapel_procedural_section_stats": chapel_section_stats,
            "support_audit": support_audit,
            "shell_window_audit": shell_window_audit,
            "continuous_ground_audit": continuous_ground_audit,
        },
    }

    failures: list[str] = []
    if ground_sandlike_columns:
        failures.append(
            f"{ground_sandlike_columns} non-building ground columns are sand-like"
        )
    if len(road_cells) < 1_000:
        failures.append(f"named-road coverage is unexpectedly small: {len(road_cells)} cells")
    if road_dark_fraction < 0.90:
        failures.append(
            f"only {road_dark_fraction:.1%} of named roads use dark concrete"
        )
    if len(tennis_features) != len(TENNIS_OSM_IDS):
        failures.append(
            f"expected {len(TENNIS_OSM_IDS)} official tennis features, got {len(tennis_features)}"
        )
    if len(tennis_cells) < 2_500 or tennis_surface_fraction < 0.90:
        failures.append(
            "tennis courts are missing or not rendered as a distinct court surface "
            f"({len(tennis_cells)} cells, {tennis_surface_fraction:.1%} court material)"
        )
    if facade.get("mode") != "voxelearth-dominant-facade-nearest-block":
        failures.append("facade palette is not sourced from dominant VoxelEarth wall colours")
    if facade.get("colour_space") != "oklab":
        failures.append("facade nearest-block matching is not recorded in Oklab colour space")
    if int(facade.get("sampled_buildings") or 0) < 80:
        failures.append("fewer than 80 accepted buildings have sampled facade evidence")
    if len(facade_material_counts) < 5:
        failures.append("facade palette contains fewer than five distinct building materials")
    if largest_facade_fraction > 0.65:
        failures.append(
            f"one facade material dominates {largest_facade_fraction:.1%} of sampled walls"
        )
    if seam_manifest.get("enabled") or int(seam_manifest_stats.get("filled_columns") or 0):
        failures.append("synthetic Roofer-footprint ground rings are enabled")
    if official_seam_manifest.get("enabled") or int(
        official_seam_stats.get("filled_columns") or 0
    ):
        failures.append("synthetic official-footprint ground rings are enabled")
    accepted_anchor_count = int(overlay_manifest.get("anchor_count") or 0)
    if not cleanup_manifest.get("enabled"):
        failures.append("main-building exterior cleanup is not enabled")
    if int(cleanup_manifest.get("radius") or 0) < 6:
        failures.append("main-building exterior cleanup radius is smaller than six blocks")
    if int(cleanup_stats.get("accepted_anchor_count") or 0) != accepted_anchor_count:
        failures.append("main-building cleanup did not process every accepted building anchor")
    if int(cleanup_stats.get("cleared_columns") or 0) < 1:
        failures.append("main-building cleanup reports no elevated source columns removed")
    if int(cleanup_stats.get("protected_building_columns") or 0) < int(
        manifest.get("buildings", {}).get("edit_columns") or 0
    ):
        failures.append("main-building cleanup did not protect every rebuilt footprint column")
    if int(cleanup_stats.get("surface_retyped") or 0):
        failures.append("main-building cleanup painted a synthetic exterior ground ring")
    if not architecture_cleanup_manifest.get("enabled"):
        failures.append("architecture-only cleanup is not enabled across the campus boundary")
    if int(architecture_cleanup_stats.get("columns") or 0) < 1:
        failures.append("architecture-only campus cleanup processed no ground columns")
    if int(architecture_cleanup_stats.get("cleared_above_ground") or 0) < 1:
        failures.append("architecture-only campus cleanup removed no elevated source clutter")
    if int(architecture_cleanup_stats.get("building_sample_exclusion_columns") or 0) < int(
        manifest.get("buildings", {}).get("edit_columns") or 0
    ):
        failures.append("campus terrain sampling did not exclude every source building footprint")
    if int(architecture_cleanup_stats.get("target_columns") or 0) != int(
        architecture_cleanup_stats.get("columns") or 0
    ):
        failures.append("procedural campus terrain did not write every target column")
    if chapel_cleanup_manifest.get("enabled") or int(chapel_cleanup_manifest.get("radius") or 0):
        failures.append("legacy Chapel exterior pad cleanup is enabled")
    if chapel_section_manifest.get("enabled") or int(chapel_section_manifest.get("radius") or 0):
        failures.append("legacy flat Chapel procedural pad is enabled")
    hollowed_anchors = sum(
        bool(anchor.get("hollowed")) for anchor in overlay_manifest.get("anchors") or []
    )
    if hollowed_anchors != accepted_anchor_count:
        failures.append(
            f"only {hollowed_anchors} of {accepted_anchor_count} accepted buildings are hollow shells"
        )
    for field in (
        "missing_surface_columns",
        "layered_surface_columns",
        "subsurface_air_blocks",
        "building_columns_outside_ground",
        "foundation_air_blocks",
        "disconnected_building_edges",
        "adjacent_steps_over_one_outside_building_grades",
        "flat_height_mismatches",
    ):
        if int(continuous_ground_audit.get(field) or 0):
            failures.append(f"continuous ground audit reports {field}")
    expected_ground_y = architecture_cleanup_manifest.get("procedural_ground_y")
    if expected_ground_y is None:
        failures.append("procedural campus ground level is not recorded")
    elif (
        int(continuous_ground_audit.get("ground_y_min") or -10_000)
        != int(expected_ground_y)
        or int(continuous_ground_audit.get("ground_y_max") or -10_000)
        != int(expected_ground_y)
    ):
        failures.append("campus ground is not one flat procedural level")
    if int(continuous_ground_audit.get("adjacent_steps_over_one") or 0):
        failures.append("flat campus ground still contains multi-block terraces")
    for field in (
        "block_mismatches",
        "state_mismatches",
        "non_air_interior_blocks",
        "unframed_window_assemblies",
        "full_glass_blocks",
        "fill_role_blocks",
        "glowstone_blocks",
    ):
        if int(shell_window_audit.get(field) or 0):
            failures.append(f"shell/window audit reports {field}")
    if int(shell_window_audit.get("pane_blocks") or 0) < 1:
        failures.append("procedural buildings contain no glass panes")
    if int(shell_window_audit.get("stair_blocks") or 0) < 1:
        failures.append("procedural windows contain no stair frames")
    if int(place_stats.get("fill") or 0):
        failures.append("solid interior fill blocks were placed")
    if int(support_audit.get("air_support_columns") or 0):
        failures.append("rebuilt buildings contain unsupported air columns")
    if int(support_audit.get("floating_floor_columns") or 0):
        failures.append("rebuilt buildings contain floating floor columns")
    if int(support_audit.get("support_block_mismatches") or 0):
        failures.append("rebuilt building supports do not match their expected blocks")
    return result, failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--resources", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--osm-site-features", type=Path, default=DEFAULT_OSM_SITE_FEATURES)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo = Path.cwd().resolve()
    result, failures = run_audit(
        args.world.resolve(),
        args.resources.resolve(),
        args.osm_site_features.resolve(),
        repo,
    )
    result["passed"] = not failures
    result["failures"] = failures
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
