"""Rasterize reviewed demo site controls without moving a campus building."""

from collections import Counter
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter, binary_dilation
from shapely.geometry import LineString, Point

from build_hill_chapel_sample import terrain_arrays
from campus_study_io import digest, write_json
from campus_export_parity import read_archive
from refine_hill_campus_environment import apply_surface, load_canvas

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "runtime/campus-reconstruction/demo-prep-20260923"
SOURCE = ROOT / "runtime/campus-reconstruction/campus-context-v13-2x"
CONTROLS = ROOT / "runtime/research/hill-demo-site-reference-20260923/site-controls.json"


def prepare():
    read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    manifest, profile = read(SOURCE / "manifest.json"), read(SOURCE / "profile.json")
    controls = read(CONTROLS)
    inventory = read(SESSION / "study-inventory.json")["chapel_authored_site_transfer"]
    with np.load(SESSION / "ground-baseline/surface-survey.npz") as a:
        arrays = {k: a[k] for k in a.files}
    ground, architecture, surface = (arrays[k] for k in ("ground", "architecture", "surface"))
    palette = arrays["palette"].tolist()
    xmin, zmin, xmax, zmax = arrays["bounds"].tolist()
    elevation, source_materials, meta = terrain_arrays(ROOT / profile["terrain"], 2)
    target = (elevation - 25) * 2
    actual_top = ground + 1 - arrays["ground_half"] / 2
    asphalt = np.isin(surface, [i for i, n in enumerate(palette) if "polished_deepslate" in n])
    plans = {}
    feature_notes = []

    def put(x, z, height, full, slab, feature, role="pavement"):
        x, z = int(x), int(z)
        ix, iz = x - xmin, z - zmin
        if architecture[iz, ix]:
            return
        height = round(float(height) * 2) / 2 if slab else round(float(height))
        top = math.ceil(height) - 1
        state = {"Name": "minecraft:" + (full if height == int(height) else slab)}
        if height != int(height):
            state["Properties"] = {"type": "bottom", "waterlogged": "false"}
        plans[x, z] = {"x": x, "z": z, "y": top, "state": state, "role": role,
                       "feature": feature, "max_delta_blocks": 4}

    restore_mask = arrays["grass_paving"] & (abs(ground - arrays["expected"]) <= 1)
    for iz, ix in np.argwhere(restore_mask):
        path = source_materials[iz, ix] == meta["materials"]["path"]["id"]
        put(ix + xmin, iz + zmin, target[iz, ix],
            "smooth_stone" if path else "polished_deepslate",
            "smooth_stone_slab" if path else "polished_deepslate_slab", "restore_measured_paving")
    feature_notes.append({"id": "restore_measured_paving", "evidence": profile["terrain"],
                          "scope": "Restore 63 Ryan road/path columns at measured grade. Retain 362 elevated Hunt columns belonging to its engineered terrace; old road masks do not override that retaining section.",
                          "preserved_engineered_terrace_columns": int((arrays["grass_paving"] & ~restore_mask).sum())})

    # Keep the later drone-supported open lawn and beds. Only outer Chapel
    # walks and the south entry are eligible, never the proposed cross-lawn path.
    route_cells = set()
    for route in inventory["routes"]:
        if route["number"] in (1, 4, 5):
            route_cells.update(map(tuple, route["columns_xz"]))
    chapel_cells = inventory["unique_columns"] + inventory["south_entry_landing"]["unowned_columns"]
    for cell in chapel_cells:
        x, z = cell["xz"]
        if ((x, z) not in route_cells and (x, z) != (-10, 65)) or cell["chapel_owned"]:
            continue
        if (cell["current_architecture_in_column"] or cell["current_quad_lawn"]
                or cell["current_planting_beds"] or cell["current_engineered_terraces"]
                or cell["current_landscape_paths"]):
            continue
        top_cell = max(cell["source_pavement_cells"], key=lambda c: c["xyz"][1])
        state = top_cell["source_state"]
        height = top_cell["xyz"][1] + (0.5 if state["Name"].endswith("_slab") and state.get("Properties", {}).get("type") == "bottom" else 1)
        put(x, z, height, "smooth_stone", "smooth_stone_slab", "chapel_outer_walk_restoration")
    feature_notes.append({"id": "chapel_outer_walk_restoration", "evidence": "study-inventory.json",
                          "scope": "Only off-mask outer path/entry cells outside current lawn, beds, paths and architecture; no old proposed diagonal Quad route restored."})

    # Remove isolated one-cell contour spikes/pits beside circulation, bounded
    # to one half-metre block and without flattening any broader lawn slope.
    zz, xx = np.indices(ground.shape)
    core = ((xx + xmin >= -260) & (xx + xmin <= 460) & (zz + zmin >= -280) & (zz + zmin <= 360))
    grass = surface == palette.index("minecraft:grass_block")
    median = median_filter(ground, 3)
    same = np.zeros(ground.shape, np.uint8)
    for dz, dx in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
        same += np.roll(np.roll(ground, dz, 0), dx, 1) == median
    paving = np.isin(surface, [i for i, n in enumerate(palette) if n.startswith("minecraft:smooth_stone") or "polished_deepslate" in n or n == "minecraft:bricks" or n == "minecraft:brick_slab"])
    cleanup = (core & grass & (same >= 7) & (abs(ground - median) == 1)
               & (abs(median - arrays["expected"]) <= 1) & binary_dilation(paving, iterations=3)
               & ~binary_dilation(architecture, iterations=2) & ~arrays["quad"])
    for iz, ix in np.argwhere(cleanup):
        if (ix + xmin, iz + zmin) not in plans:
            put(ix + xmin, iz + zmin, median[iz, ix] + 1, "grass_block", None, "isolated_grass_contour_cleanup", "terrain")

    # Archive-verified physical tops take precedence over reference-profile
    # floor datums that were rounded differently by the historical generators.
    entrance_tops = {"quadrivium_west_historic_portal_walk": 87.0,
                     "quadrivium_link_brick_apron": 86.0,
                     "quadrivium_east_portal_14_5_walk": 86.0,
                     "quadrivium_east_portal_31_3_walk": 86.0,
                     "dining_west_passage_to_drive": 89.0}
    for control in controls["controls"]:
        name = control["id"]
        points = control["centerline_world_blocks_2x"]
        if name == "quadrivium_link_drive_crossing":
            # The current road is wider than the nominal photo registration.
            # Continue only within existing asphalt to its actual opposite edge.
            points = [points[0], [221, 163]]
        line = LineString(points)
        distances = np.linspace(0, line.length, max(2, math.ceil(line.length * 2) + 1))
        samples = np.array([[line.interpolate(d).x, line.interpolate(d).y] for d in distances])
        sx = np.floor(samples[:, 0]).astype(int) - xmin
        sz = np.floor(samples[:, 1]).astype(int) - zmin
        heights = gaussian_filter1d(target[sz, sx], 1.25)
        start_top = entrance_tops.get(name, actual_top[sz[0], sx[0]])
        end_top = actual_top[sz[-1], sx[-1]]
        if name in ("dining_west_passage_to_drive", "hunt_west_gap_to_west_drive", "hunt_west_gap_to_north_drive"):
            road = np.flatnonzero(asphalt[sz, sx] & (distances > 1))
            if not len(road):
                feature_notes.append({"id": name, "omitted": "No existing road contacted inside bounded source control"})
                continue
            stop = road[0]
            endpoint = samples[stop]
            line = LineString([*points[:1], *[p for p in points[1:] if LineString(points).project(Point(p)) < distances[stop]], endpoint.tolist()])
            distances, samples, sx, sz, heights = distances[:stop+1], samples[:stop+1], sx[:stop+1], sz[:stop+1], heights[:stop+1]
            end_top = actual_top[sz[-1], sx[-1]]
        if name in entrance_tops or name.startswith("hunt_west"):
            heights = np.interp(distances, [0, distances[-1]], [start_top, end_top])
        if name == "quadrivium_north_continuous_sidewalk":
            # Gentle measured cross-section; separate entry joins meet the
            # exact thresholds instead of globally levelling the facade.
            pass
        polygon = line.buffer(control["width_blocks_2x"] / 2, cap_style=2, join_style=2)
        x0, z0, x1, z1 = polygon.bounds
        count_before = len(plans)
        for z in range(math.floor(z0), math.ceil(z1)):
            for x in range(math.floor(x0), math.ceil(x1)):
                if not polygon.covers(Point(x + 0.5, z + 0.5)):
                    continue
                iz, ix = z - zmin, x - xmin
                if name == "quadrivium_link_drive_crossing" and not asphalt[iz, ix]:
                    continue
                distance = line.project(Point(x + 0.5, z + 0.5))
                height = np.interp(distance, distances, heights)
                brick = name == "quadrivium_link_brick_apron"
                full, slab = ("bricks", "brick_slab") if brick else ("smooth_stone", "smooth_stone_slab")
                if name == "quadrivium_link_drive_crossing":
                    # Restrained two-colour paver field, surface-only.
                    height = actual_top[iz, ix]
                    if (x + z) % 2:
                        full, slab = "stone_bricks", "stone_brick_slab"
                put(x, z, height, full, slab, name)
        feature_notes.append({"id": name, "evidence": control["evidence"], "new_plan_columns": len(plans) - count_before,
                              "centerline_blocks": list(map(list, line.coords)), "width_blocks": control["width_blocks_2x"],
                              "endpoint_tops_blocks": [float(start_top), float(end_top)],
                              "interpretation": control.get("confidence", {})})

    # Dry-run against the actual source volume. Invalid columns are recorded,
    # never silently paved through an architectural object or tree.
    grouped = {}
    for action in plans.values():
        tx = xmin + (action["x"] - xmin) // 256 * 256
        tz = zmin + (action["z"] - zmin) // 256 * 256
        grouped.setdefault((tx, tz), []).append(action)
    blocked = []
    for (tx, tz), actions in grouped.items():
        a = read_archive(SOURCE / "tiles" / f"x{tx}_z{tz}" / "sample-blocks.npz")
        c = load_canvas(a, (tx, tz, min(tx + 256, xmax), min(tz + 256, zmax)))
        del a
        for action in actions:
            try:
                apply_surface(c, action)
            except ValueError as error:
                blocked.append({"action": action, "reason": str(error)})
                del plans[action["x"], action["z"]]
        del c
    inputs = [CONTROLS, SESSION / "study-inventory.json", SOURCE / "profile.json",
              ROOT / profile["terrain"], SESSION / "ground-baseline/surface-survey.npz"]
    inputs.extend(ROOT / e["path"] for e in controls["evidence_ids"].values() if e.get("path"))
    plan = {"format": "hill-enumerated-environment-plan-v1", "source_manifest_sha256": digest(SOURCE / "manifest.json"),
            "inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in inputs],
            "features": feature_notes, "blocked_columns": blocked,
            "columns": sorted(plans.values(), key=lambda a: (a["z"], a["x"])),
            "scope": "Exterior paths, entry joins and bounded isolated contour repairs only. Preserve current Quad lawn/planting, architecture, measured broad grades, all studied covered passages and historical source revisions."}
    write_json(SESSION / "environment-plan.json", plan)
    print(json.dumps({"columns": len(plans), "features": dict(Counter(p["feature"] for p in plans.values())),
                      "blocked_columns": len(blocked), "blocked_examples": blocked[:8]}, indent=2), flush=True)


if __name__ == "__main__":
    prepare()
