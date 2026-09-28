"""Check the new exterior joins with actual partial-block collision shapes."""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import LineString

from audit_hill_window_joints import ArchiveStates
from audit_hill_quadrivium_contacts import shapes
from campus_study_io import digest, write_json

NONCOLLIDING_PLANTS = {"minecraft:" + name for name in (
    "fern", "oxeye_daisy", "azure_bluet", "dandelion", "short_grass",
    "short_dry_grass", "tall_dry_grass")}


def surface_hint(coords, role_ids, role_names, tx, tz):
    """Read the actual undulating ground, independent of endpoint interpolation."""
    ground = np.full((256, 256), -320, np.int16)
    selected = np.isin(role_ids, [i for i, n in enumerate(role_names)
                                 if n in {"terrain", "pavement"}])
    q = coords[selected]
    np.maximum.at(ground, (q[:, 2] - tz, q[:, 0] - tx), q[:, 1])
    return ground


def standing_height(boxes, x, z, hint):
    for feet in sorted({b[4] for b in boxes if abs(b[4]-hint) <= 2.0},
                       key=lambda y: abs(y-hint)):
        body = (x-.3, feet, z-.3, x+.3, feet+1.8, z+.3)
        support, collisions = 0, 0
        for b in boxes:
            overlap = [min(body[i+3], b[i+3])-max(body[i], b[i]) for i in range(3)]
            collisions += all(o > 1e-7 for o in overlap)
            if abs(b[4]-feet) < 1e-7:
                support += max(0, overlap[0])*max(0, overlap[2])
        if support > 1e-7 and not collisions:
            return feet
    return None


def audit(directory):
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    manifest = read(directory / "manifest.json")
    plan = read(directory / "environment-plan.json")
    xmin, zmin, xmax, zmax = manifest["bounds_xz_blocks"]
    cache = {}
    ground_cache = {}
    verified_tiles = {}
    specs = {str(Path(s["path"]) / "sample-blocks.npz"): s for s in manifest["tiles"]}

    def lookup_tile(x, z):
        tx = xmin + (x - xmin) // 256 * 256
        tz = zmin + (z - zmin) // 256 * 256
        if (tx, tz) not in cache:
            path = directory / "tiles" / f"x{tx}_z{tz}" / "sample-blocks.npz"
            expected = specs[str(path.relative_to(directory))]["archive_sha256"]
            if digest(path) != expected:
                raise ValueError(f"Changed archive: {path}")
            cache[tx, tz] = ArchiveStates(path)
            with np.load(path, allow_pickle=False) as a:
                ground_cache[tx, tz] = surface_hint(a["coords"], a["role_ids"],
                                                    a["role_names"].tolist(), tx, tz)
            verified_tiles[str(path)] = expected
        return cache[tx, tz], ground_cache[tx, tz], tx, tz

    @lru_cache(maxsize=None)
    def occupied(x, y, z):
        lookup, _, _, _ = lookup_tile(x, z)
        state = lookup.palette[lookup.get(x, y, z)]
        if state["Name"] in NONCOLLIDING_PLANTS:
            return ()
        return tuple((x+b[0]/16, y+b[1]/16, z+b[2]/16,
                      x+b[3]/16, y+b[4]/16, z+b[5]/16)
                     for b in shapes(json.dumps(state, sort_keys=True)))

    routes = []
    for feature in plan["features"]:
        if "centerline_blocks" not in feature:
            continue
        points = feature["centerline_blocks"]
        line = LineString(points)
        errors, heights = [], []
        count = max(2, math.ceil(line.length / 0.1) + 1)
        # Actual site height selects the walking layer. Linear endpoint heights
        # are wrong on existing drives that rise and descend between endpoints.
        for distance in np.linspace(0, line.length, count):
            point = line.interpolate(distance)
            x, z = point.x, point.y
            _, ground, tx, tz = lookup_tile(math.floor(x), math.floor(z))
            hint = float(ground[math.floor(z)-tz, math.floor(x)-tx] + 1)
            if feature.get("preserved_gallery_endpoint"):
                datum = feature["preserved_gallery_endpoint"]["feet_y_block"]
                if hint <= datum <= hint + 12:
                    hint = float(datum)
            boxes = []
            for xx in range(math.floor(x-.3), math.floor(x+.3)+1):
                for zz in range(math.floor(z-.3), math.floor(z+.3)+1):
                    for yy in range(math.floor(hint)-3, math.ceil(hint)+4):
                        boxes.extend(occupied(xx, yy, zz))
            accepted = standing_height(boxes, x, z, hint)
            heights.append(accepted)
            if accepted is None:
                errors.append({"xz": [round(x, 3), round(z, 3)], "reason": "No supported player-sized clear standing position"})
        steps = [abs(a-b) for a, b in zip(heights, heights[1:]) if a is not None and b is not None]
        too_large = sum(v > .50001 for v in steps)
        if too_large:
            errors.append({"reason": "More than a half-block traversal step", "count": too_large})
        routes.append({"name": feature["id"], "samples": count, "passed": not errors,
                       "maximum_sampled_step_blocks": max(steps, default=0),
                       "steps_above_half_block": sum(v > .50001 for v in steps),
                       "errors": errors})
    result = {"format": "hill-demo-walking-joins-v1", "passed": all(r["passed"] for r in routes),
              "manifest_sha256": digest(directory / "manifest.json"), "routes": routes,
              "auditor_sha256": digest(Path(__file__)), "verified_tiles": verified_tiles,
              "player": {"width_blocks": .6, "height_blocks": 1.8, "sample_spacing_max_blocks": .1},
              "limits": "Exterior centerline traversal checks with support and occupied shapes, allowing at most a half-block step. Actual verified archive ground selects the walking layer; noncolliding plants do not block a player. Closed doors are not opened. Athey/Dining covered passages have a separate fixed-floor audit; image-based horizontal placement remains approximate."}
    write_json(directory / "environment-walk-audit.json", result)
    print(json.dumps({"passed": result["passed"], "routes": [
        {**{k: r[k] for k in ("name", "samples", "passed", "maximum_sampled_step_blocks", "steps_above_half_block")},
         "failure_count": len(r["errors"]), "examples": r["errors"][:3]} for r in routes]}, indent=2), flush=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    report = audit(p.parse_args().directory)
    raise SystemExit(0 if report["passed"] else 1)
