"""Check assembled terrain block tops at the saved LiDAR controls and pond."""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import shape
from shapely import contains_xy

from campus_export_parity import read_archive
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ROOT / "runtime/research/campus-full-detail-20260905/terrain-control-checkpoints.json"
POND = ROOT / "runtime/research/campus-full-detail-20260905/terrain-dell-pond-controls.json"


def block_top(key):
    name, properties = key
    props = dict(properties)
    return 0.5 if name.endswith("_slab") and props.get("type") == "bottom" else 1.0


def audit(directory):
    profile = json.loads((directory / "profile.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    controls = json.loads(CONTROLS.read_text(encoding="utf-8"))["checkpoints"]
    pond = shape(json.loads(POND.read_text(encoding="utf-8"))["outline_geometry_xz_m"])
    scale, offset = profile["blocks_per_metre"], profile["vertical_offset_m"]
    xmin, zmin = manifest["bounds_xz_blocks"][:2]
    size = profile.get("tile_size_blocks", 256)
    with np.load(ROOT / profile["terrain"], allow_pickle=False) as source:
        elevations = source["ground_elevation_navd88_m"]

    grouped = defaultdict(list)
    for control in controls:
        x, z = [math.floor(q * scale) for q in control["xz_m"]]
        tx, tz = xmin + (x - xmin) // size * size, zmin + (z - zmin) // size * size
        grouped[f"x{tx}_z{tz}"].append((control, x, z))
    p0, q0, p1, q1 = [math.floor(v * scale) for v in pond.bounds]
    for tz in range(zmin + (q0 - zmin) // size * size, q1 + 1, size):
        for tx in range(xmin + (p0 - xmin) // size * size, p1 + 1, size):
            grouped.setdefault(f"x{tx}_z{tz}", [])

    rows, water_tops, checked_tiles = [], [], []
    for tile_name, entries in grouped.items():
        archive_path = directory / "tiles" / tile_name / "sample-blocks.npz"
        a = read_archive(archive_path)
        checked_tiles.append({"tile": tile_name, "sha256": digest(archive_path)})
        coords, roles = a["coords"], a["role_ids"]
        ground_ids = [a["role_names"].index(n) for n in ("terrain", "pavement")]
        for control, x, z in entries:
            column = (coords[:, 0] == x) & (coords[:, 2] == z)
            selected = np.flatnonzero(column & np.isin(roles, ground_ids))
            if not len(selected):
                rows.append({"id": control["id"], "status": "no_ground_role_at_control"})
                continue
            index = max(selected, key=lambda i: coords[i, 1] + block_top(a["palette_keys"][a["state_ids"][i]]))
            key = a["palette_keys"][a["state_ids"][index]]
            top_y = float(coords[index, 1]) + block_top(key)
            actual = top_y / scale - offset
            expected = float(elevations[z - zmin, x - xmin])
            above = column & (coords[:, 1] >= top_y) & ~np.isin(roles, ground_ids + [a["role_names"].index("vegetation")])
            covered = bool(above.any()) or control["within_county_building"]
            error = actual - expected
            rows.append({
                "id": control["id"], "source_control_xz_m": control["xz_m"],
                "sampled_block_centre_xz_m": [(x + 0.5) / scale, (z + 0.5) / scale],
                "source_dem_at_control_m": control["direct_native_d24_m"],
                "measured_grid_at_block_centre_m": expected, "built_block_top_navd88_m": actual,
                "error_from_grid_m": error, "state": {"Name": key[0], "Properties": dict(key[1])},
                "role": a["role_names"][roles[index]], "architecture_at_control": covered,
                "status": "covered_or_finished_building_level_requires_separate_review" if covered else
                          "within_half_metre_quantization" if abs(error) <= 0.25001 else "surface_deviation_requires_review",
            })
        water_ids = [i for i, key in enumerate(a["palette_keys"]) if key[0] == "minecraft:water"]
        wet = coords[np.isin(a["state_ids"], water_ids)]
        if len(wet):
            wet = wet[contains_xy(pond, (wet[:, 0] + 0.5) / scale, (wet[:, 2] + 0.5) / scale)]
        if len(wet):
            columns, inverse = np.unique(wet[:, (0, 2)], axis=0, return_inverse=True)
            tops = np.full(len(columns), -64, dtype=np.int16)
            np.maximum.at(tops, inverse, wet[:, 1])
            water_tops.extend(((tops + 1) / scale - offset).tolist())
        del a, coords, roles
    open_rows = [r for r in rows if r.get("architecture_at_control") is False]
    result = {
        "format": "hill-assembled-ground-controls-v1",
        "assembly_manifest_sha256": digest(directory / "manifest.json"),
        "control_source_sha256": digest(CONTROLS), "pond_control_sha256": digest(POND),
        "terrain_source_sha256": digest(ROOT / profile["terrain"]), "checked_tiles": checked_tiles,
        "checkpoints": rows,
        "open_control_count": len(open_rows),
        "open_surface_deviations": [r["id"] for r in open_rows if r["status"] == "surface_deviation_requires_review"],
        "pond": {"water_columns": len(water_tops), "nominal_block_top_navd88_range_m": [min(water_tops), max(water_tops)] if water_tops else [],
                 "all_nominal_tops_at_55m": bool(water_tops) and all(abs(h - 55.0) < 1e-6 for h in water_tops)},
        "scope": "Assembled archive state/role columns, following independent archive-to-Anvil parity. Full cubes and slab physical tops are measured; stair tops use maximum occupied height, and water uses nominal block tops rather than its fluid mesh. Covered and finished building levels are classified separately from open bare-earth controls. Source point and grid-centre coordinates differ by up to half a cell.",
    }
    write_json(directory / "ground-control-audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    report = audit(parser.parse_args().directory)
    print(json.dumps({k: report[k] for k in ("open_control_count", "open_surface_deviations", "pond")}, indent=2))
