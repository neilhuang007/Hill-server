"""Sample the full campus at 0.5 m and constrain the documented Dell pond level.

The source DEM, coordinate frame and surface geometries are retained as separate
provenance. Only the pond polygon receives a constant level; surrounding ground
and retaining slopes are not flattened to fit a building.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import shape

import build_hill_measured_terrain as source
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
POND = ROOT / "runtime/research/campus-full-detail-20260905/terrain-dell-pond-controls.json"
BOUNDS_M = (-288, -800, 704, 208)


def constrain_pond(heights, material_ids, *, bounds_m, polygon, level_m, water_id):
    """Apply a measured water plane at cell centres, retaining polygon holes."""
    rows, cols = np.indices(heights.shape)
    resolution_x = (bounds_m[2] - bounds_m[0]) / heights.shape[1]
    resolution_z = (bounds_m[3] - bounds_m[1]) / heights.shape[0]
    x = bounds_m[0] + (cols + 0.5) * resolution_x
    z = bounds_m[1] + (rows + 0.5) * resolution_z
    mask = contains_xy(polygon, x, z)
    before = heights[mask].copy()
    corrected, ids = heights.copy(), material_ids.copy()
    corrected[mask], ids[mask] = level_m, water_id
    return corrected, ids, {
        "columns": int(mask.sum()),
        "nominal_water_level_navd88_m": level_m,
        "source_height_range_m": [float(before.min()), float(before.max())] if len(before) else [],
        "outside_polygon_unchanged": bool(np.array_equal(corrected[~mask], heights[~mask])),
    }


def build(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    transform = replace(source.WorldTransform.from_manifest(source.DEFAULT_WORLD_MANIFEST), blocks_per_metre=2)
    bounds = source.WorldBounds(*(v * 2 for v in BOUNDS_M))
    heights, dem = source.sample_dem_at_block_centres(
        transform, bounds, requested_dem=None, default_dem=source.DEFAULT_DEM,
        tile_dir=source.DEFAULT_DEM_TILE_DIR,
    )
    features, load_stats = source.load_surface_features(source.DEFAULT_SURFACES, source.DEFAULT_OSM, transform)
    ids, surface_stats = source.rasterize_materials(features, bounds)
    control = json.loads(POND.read_text(encoding="utf-8"))
    # The inner 8 m ground-return median is 55.000 m, IQR 54.99–55.02 m.
    level = float(control["ground_cloud"][0]["elevation_percentiles_m"]["50"])
    heights, ids, pond = constrain_pond(
        heights, ids, bounds_m=BOUNDS_M, polygon=shape(control["outline_geometry_xz_m"]),
        level_m=level, water_id=source.MATERIALS["water"]["id"],
    )
    metadata = {
        "format": "hill-measured-terrain-v2", "resolution_m": 0.5,
        "axis": "+X east, +Z south", "array_order": "[z,x]",
        "physical_bounds_m": list(BOUNDS_M), "materials": source.MATERIALS,
        "physical_surface_formula": "(NAVD88_m - 25) * blocks_per_metre",
        "dem": dem, "surface_load": load_stats, "surface_raster": surface_stats,
        "pond": {"control_file": str(POND), "sha256": digest(POND), **pond},
    }
    output.mkdir(parents=True)
    destination = output / "terrain.npz"
    source.write_deterministic_npz(destination, {
        "ground_elevation_navd88_m": heights, "material_id": ids,
        "x_min": np.asarray(BOUNDS_M[0]), "z_min": np.asarray(BOUNDS_M[1]),
        "metadata_json": np.asarray(json.dumps(metadata)),
    })
    write_json(output / "manifest.json", {**metadata, "terrain": str(destination.resolve()), "sha256": digest(destination)})
    print(json.dumps({"output": str(destination), "shape": list(heights.shape), "pond": pond}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
