"""Build Athey and its measured Dining Hall envelope as a standalone study.

Positions stay in the campus metre frame. Facade interpretation lives in the
reference profile; roofs and grade retain their measured sources. This command
creates a fresh vanilla world, semantic block archive and native camera file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import hybridize_voxelearth_roofer_world as anvil
import numpy as np
from build_hill_chapel_sample import (
    ROLES,
    Canvas,
    build_ground,
    connect_window_panes,
    terrain_arrays,
    write_world,
)
from campus_academic_building import AcademicExterior
from campus_athey_details import AtheyExterior, connect_iron_rails
from campus_materials import audit_role_materials
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_window_frames import pane_joint_report, pane_support_report
from scipy.ndimage import binary_erosion

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERRAIN = (
    ROOT
    / "runtime/campus-reconstruction/measured-terrain-academic-quad-v1/hill-academic-quad-measured-terrain.npz"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "server-assets/hill-athey-reference.json"
    )
    parser.add_argument("--terrain", type=Path, default=DEFAULT_TERRAIN)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(
            "Use a fresh revision directory; existing worlds are preserved"
        )
    p = json.loads(args.profile.read_text(encoding="utf-8"))
    s, offset = p["blocks_per_metre"], p["vertical_offset_m"]
    print("Preparing measured terrain", flush=True)
    heights, ids, meta = terrain_arrays(args.terrain, s, p.get("terrain_bounds_m"))
    c = Canvas(
        meta["x_min"] * s, meta["z_min"] * s, heights.shape[1], heights.shape[0], s
    )
    build_ground(c, heights, ids, meta["materials"], offset)
    paving = smooth_exposed_measured_pavement(
        c, heights, c.ground_heights, vertical_offset=offset
    )
    b = load_measured_building(
        ROOT / p["source_cityjson"],
        p["parent_id"],
        ROOT / p["measured_terrain_manifest"],
    )
    bounds = (
        c.x_min / s,
        c.z_min / s,
        (c.x_min + c.data.shape[2]) / s,
        (c.z_min + c.data.shape[1]) / s,
    )
    bx0, bz0, bx1, bz1 = b.footprint.bounds
    if not (bounds[0] < bx0 < bx1 < bounds[2] and bounds[1] < bz0 < bz1 < bounds[3]):
        raise ValueError("The complete measured complex must fit in the terrain bounds")
    raster = rasterize_roof(b, bounds, resolution=1 / s)
    if raster.missing_mask.any():
        raise ValueError(
            f"Uncovered measured footprint columns: {raster.coverage_report}"
        )
    print("Constructing measured roof, masonry, openings and court", flush=True)
    shell = build_measured_shell(
        c,
        b,
        raster,
        vertical_offset=offset,
        facade=p["materials"]["facade"],
        foundation=p["materials"]["foundation"],
        roof_family=p["materials"]["roof_family"],
        roof_backing_metres=0.4,
    )
    facade_class = AtheyExterior if p.get("east_return") else AcademicExterior
    facade = facade_class(c, p, raster, offset)
    features = facade.build()
    # Unfurnished floor plates avoid looking through an entire four-storey
    # void. They are construction proxies, not reconstructed interior plans.
    for level in p.get("floor_plates_navd88_m", []):
        y = round((level + offset) * s) - 1
        mask = shell.active_mask & (
            raster.heights >= p["geometry"]["main_roof_threshold_navd88_m"]
        )
        mask = binary_erosion(mask, iterations=max(2, math.ceil(0.6 * s)))
        mask &= (shell.roof_block_y > y + 2) & (c.ground_heights < y)
        c.data[y + 64, mask] = c.state("birch_planks")
        c.roles[y + 64, mask] = ROLES.index("floor")
    connect_window_panes(c)
    connect_iron_rails(c)
    joints = pane_joint_report(c)
    if joints["unbridged_diagonal_pairs"] or joints["disconnected_adjacent_pairs"]:
        raise ValueError({"open_window_joints": joints})
    from campus_material_assignment import apply_reviewed_palette

    if not p.get("material_review"):
        review = apply_reviewed_palette(c, p)
        if review:
            p["material_review"] = review
    roles = {}
    for i, role in enumerate(ROLES[1:], 1):
        unique, counts = np.unique(c.data[c.roles == i], return_counts=True)
        total = Counter()
        for state, n in zip(unique, counts):
            if state:
                total[c.palette[state]["Name"]] += int(n)
        if total:
            roles[role] = dict(total)
    violations = audit_role_materials(roles)
    if violations or c.clipped:
        raise ValueError({"materials": violations, "clipped_writes": c.clipped})
    args.output.mkdir(parents=True)
    print("Exporting exact block archive", flush=True)
    materials = c.export(args.output / "sample-blocks.npz")

    def point(u, v, h):
        x, z = facade.world(u, v)
        return [float(x * s), float((h + offset) * s), float(z * s)]

    cameras = []
    for spec in p["camera_views"]:
        cameras.append(
            {
                "name": spec["name"],
                "eye": point(*spec["eye_uv_navd88_m"]),
                "target": point(*spec["target_uv_navd88_m"]),
                "fov": spec["fov"],
            }
        )
    (args.output / "camera-views.json").write_text(
        json.dumps(
            {"format": "hill-native-camera-views-v1", "views": cameras}, indent=2
        )
        + "\n"
    )
    start_view = next(view for view in cameras if view["name"] == "quad-straight")
    (args.output / "play-start.json").write_text(
        json.dumps(
            {"format": "hill-native-camera-views-v1", "views": [start_view]}, indent=2
        )
        + "\n"
    )
    print("Writing vanilla Anvil world", flush=True)
    spawn = tuple(round(v) for v in cameras[0]["eye"])
    world = write_world(
        c,
        args.output / "world",
        "Hill — Athey Academic Center",
        spawn,
        anvil.DEFAULT_SOURCE_WORLD / "level.dat",
    )
    (args.output / "profile.json").write_text(
        json.dumps(p, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "format": "hill-athey-study-v1",
        "created_unix": int(time.time()),
        "revision": p["revision"],
        "world": world,
        "blocks_per_metre": s,
        "vertical_offset_m": offset,
        "axis": f"X east, Y up, Z south; Y = (NAVD88 metres + {offset}) * {s}",
        "block_count": int(np.count_nonzero(c.data)),
        "window_joints": joints,
        "sources": {
            "roof": {"path": p["source_cityjson"], "sha256": b.source_sha256},
            "terrain": {"path": str(args.terrain), "sha256": digest(args.terrain)},
            "profile": {
                "path": str(args.profile),
                "sha256": digest(args.output / "profile.json"),
            },
        },
        "source_roof": shell.to_manifest(),
        "roof_coverage": raster.coverage_report,
        "paving": paving,
        "features": features,
        "window_support": pane_support_report(c),
        "materials": materials,
        "material_roles": roles,
        "material_violations": violations,
        "clipped_writes": c.clipped,
        "visual_review": "pending — successful export is not a likeness approval",
        "uncertainties": p["uncertainties"],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "blocks": manifest["block_count"],
                "features": features,
                "clipped_writes": c.clipped,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
