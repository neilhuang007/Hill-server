"""Audit accepted Athey/Dining connections in combined-campus tile archives.

Reads immutable source and campus artifacts; writes only the requested report.
All twenty accepted routes retain their original UV coordinates and floor level.
Exact architectural-column comparisons preserve accepted roof/building contacts
and air without claiming that unreviewed interior or facade details are complete.
"""

import argparse
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np

from audit_hill_quadrivium_contacts import AXES, shapes
from campus_export_parity import read_archive
from campus_study_io import digest, write_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "runtime/campus-reconstruction/athey-dining-v6-2x"
ARCHITECTURE_ROLES = {
    "facade", "roof", "trim", "window", "railing", "lighting", "door",
    "floor", "fixture", "furniture",
}
EPSILON = 1e-7


def read_json(path):
    return Path(path).read_text(encoding="utf-8")


def state_key(state):
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


class CombinedStates:
    """Dense source-sized window, populated from verified combined tile archives."""

    def __init__(self, campus, study, manifest):
        archive = read_archive(study / "sample-blocks.npz")
        coords = archive["coords"]
        low, high = coords.min(axis=0), coords.max(axis=0) + 1
        self.x0, self.z0 = int(low[0]), int(low[2])
        self.width, self.depth = int(high[0] - low[0]), int(high[2] - low[2])
        self.palette = [
            {"Name": name, **({"Properties": dict(props)} if props else {})}
            for name, props in archive["palette_keys"]
        ]
        if self.palette[0] != {"Name": "minecraft:air"}:
            raise ValueError("Source palette zero must be air")
        self.palette_ids = {state_key(p): i for i, p in enumerate(self.palette)}
        shape = (384, self.depth, self.width)
        self.expected = np.zeros(shape, dtype=np.uint16)
        self.actual = np.zeros(shape, dtype=np.uint16)
        self.architecture = np.zeros(shape[1:], dtype=bool)
        self.minimum = np.full(shape[1:], 320, dtype=np.int16)
        self.roof_cells = np.empty((0, 3), dtype=np.int32)
        roles = archive["role_names"]
        architectural_ids = [i for i, role in enumerate(roles) if role in ARCHITECTURE_ROLES]
        x, y, z = (coords - [self.x0, -64, self.z0]).T
        self.expected[y, z, x] = archive["state_ids"]
        architectural = np.isin(archive["role_ids"], architectural_ids)
        self.architecture[z[architectural], x[architectural]] = True
        np.minimum.at(self.minimum, (z, x), coords[:, 1])
        self.roof_cells = coords[archive["role_ids"] == roles.index("roof")].copy()
        del archive, coords, x, y, z
        self.tiles = []
        covered = np.zeros(shape[1:], dtype=bool)
        campus_x0, campus_z0, campus_x1, campus_z1 = manifest["bounds_xz_blocks"]
        if not (campus_x0 <= self.x0 and campus_z0 <= self.z0
                and self.x0 + self.width <= campus_x1
                and self.z0 + self.depth <= campus_z1):
            raise ValueError("Campus does not contain the complete source study window")
        for spec in manifest["tiles"]:
            tile = campus / spec["path"]
            tx, tz = map(int, tile.name[1:].split("_z"))
            right, bottom = min(tx + 256, campus_x1), min(tz + 256, campus_z1)
            left, top = max(tx, self.x0), max(tz, self.z0)
            r, b = min(right, self.x0 + self.width), min(bottom, self.z0 + self.depth)
            if left >= r or top >= b:
                continue
            path = tile / "sample-blocks.npz"
            actual_hash = digest(path)
            if actual_hash != spec["archive_sha256"]:
                raise ValueError(f"Campus tile archive differs from its manifest: {path}")
            selection = (slice(top-self.z0, b-self.z0), slice(left-self.x0, r-self.x0))
            if covered[selection].any():
                raise ValueError(f"Overlapping campus tiles: {path}")
            covered[selection] = True
            archive = read_archive(path)
            mapping = []
            for name, props in archive["palette_keys"]:
                state = {"Name": name, **({"Properties": dict(props)} if props else {})}
                key = state_key(state)
                if key not in self.palette_ids:
                    self.palette_ids[key] = len(self.palette)
                    self.palette.append(state)
                mapping.append(self.palette_ids[key])
            if len(self.palette) >= 65535:
                raise ValueError("Audit palette exceeds uint16 capacity")
            q = archive["coords"]
            selected = ((q[:, 0] >= left) & (q[:, 0] < r)
                        & (q[:, 2] >= top) & (q[:, 2] < b))
            x, y, z = (q[selected] - [self.x0, -64, self.z0]).T
            self.actual[y, z, x] = np.asarray(mapping, dtype=np.uint16)[archive["state_ids"][selected]]
            self.tiles.append({"path": str(path), "sha256": actual_hash})
            del archive, q, x, y, z
        if not covered.all():
            raise ValueError("Missing campus tile coverage in the source study window")
        self.keys = [state_key(p) for p in self.palette]

    def get(self, xyz, source=False):
        x, y, z = map(int, xyz)
        if not (self.x0 <= x < self.x0+self.width and self.z0 <= z < self.z0+self.depth
                and -64 <= y < 320):
            raise ValueError(f"Audit probe outside the verified study window: {xyz}")
        grid = self.expected if source else self.actual
        return int(grid[y+64, z-self.z0, x-self.x0])

    def mismatch(self, xyz):
        before, after = self.get(xyz, source=True), self.get(xyz)
        return ({"xyz": list(map(int, xyz)), "expected": self.palette[before],
                 "actual": self.palette[after]} if before != after else None)

    @lru_cache(maxsize=None)
    def boxes(self, state_id):
        state = self.palette[state_id]
        if state["Name"].endswith("_slab") and state.get("Properties", {}).get("type") == "double":
            return ((0, 0, 0, 16, 16, 16),)
        # Retain the accepted source audit's occupied-shape model. Refuse shapes
        # for which that helper would silently ignore an important state value.
        props = state.get("Properties", {})
        if state["Name"].endswith("_stairs") and props.get("shape", "straight") != "straight":
            raise ValueError(f"Non-straight stair requires a fuller collision model: {state}")
        if state["Name"].endswith("_door") and props.get("open", "false") != "false":
            raise ValueError(f"Open door requires a fuller collision model: {state}")
        return shapes(self.keys[state_id])

    @lru_cache(maxsize=None)
    def occupied(self, xyz):
        x, y, z = xyz
        return tuple((x+b[0]/16, y+b[1]/16, z+b[2]/16,
                      x+b[3]/16, y+b[4]/16, z+b[5]/16)
                     for b in self.boxes(self.get(xyz)))

    @lru_cache(maxsize=None)
    def contact_area(self, xyz, direction):
        other = tuple(xyz[i]+direction[i] for i in range(3))
        axis = next(i for i, value in enumerate(direction) if value)
        tangents = [i for i in range(3) if i != axis]
        score = 0
        for left in self.boxes(self.get(xyz)):
            for right in self.boxes(self.get(other)):
                translated = [right[i]+16*direction[i % 3] for i in range(6)]
                if left[axis+3 if direction[axis] > 0 else axis] != translated[axis if direction[axis] > 0 else axis+3]:
                    continue
                overlap = [min(left[i+3], translated[i+3])-max(left[i], translated[i]) for i in tangents]
                if all(value > 0 for value in overlap):
                    score += overlap[0]*overlap[1]
        return score


def route_audit(states, profile):
    angle = math.radians(profile["geometry"]["axis_degrees"])
    ox, oz = profile["geometry"]["origin_xz_m"]

    def world(uv):
        u, v = uv
        return ((ox+u*math.cos(angle)-v*math.sin(angle))*2,
                (oz+u*math.sin(angle)+v*math.cos(angle))*2)

    reports, all_probes = [], set()
    specs = profile["walking_routes"]
    names = [spec["name"] for spec in specs]
    expected_names = {f"{side}-longitudinal-covered-passage" for side in ("east", "west")}
    expected_names |= {f"{side}-broadside-bay-{number}" for side in ("east", "west") for number in range(1, 10)}
    if len(names) != 20 or set(names) != expected_names:
        raise ValueError("Expected the two accepted longitudinal routes and eighteen named broadside bays")
    for spec in specs:
        width, height = spec.get("clearance_width_blocks", .6), spec.get("clearance_height_blocks", 1.8)
        if width != .6 or height != 1.8:
            raise ValueError("This audit requires the accepted 0.6 x 1.8 block player")
        points = [world(point) for point in spec["waypoints_uv_m"]]
        samples = []
        spacing = 0
        for start, end in zip(points, points[1:]):
            intervals = max(1, math.ceil(math.dist(start, end)/.1))
            spacing = max(spacing, math.dist(start, end)/intervals)
            samples.extend((1-f)*np.asarray(start)+f*np.asarray(end) for f in np.linspace(0, 1, intervals+1))
        feet, radius = (spec["floor_navd88_m"]-25)*2, width/2
        failures, probes, minimum_support = [], set(), math.inf
        for x, z in samples:
            body = (x-radius, feet, z-radius, x+radius, feet+height, z+radius)
            collision, support = set(), 0
            for xx in range(math.floor(x-radius), math.floor(x+radius)+1):
                for zz in range(math.floor(z-radius), math.floor(z+radius)+1):
                    for yy in range(math.floor(feet)-1, math.floor(feet+height)+1):
                        q = (xx, yy, zz)
                        probes.add(q)
                        for box in states.occupied(q):
                            overlap = [min(body[i+3], box[i+3])-max(body[i], box[i]) for i in range(3)]
                            if all(value > EPSILON for value in overlap):
                                collision.add(q)
                            if abs(box[4]-feet) < EPSILON:
                                support += max(0, overlap[0])*max(0, overlap[2])
            minimum_support = min(minimum_support, support)
            if collision or support < .09-EPSILON:
                failures.append({"center_xz_blocks": [round(x, 6), round(z, 6)],
                                 "collisions": sorted(collision), "foot_support_area": round(support, 8)})
        differences = [row for q in sorted(probes) if (row := states.mismatch(q))]
        all_probes.update(probes)
        reports.append({**spec, "world_waypoints_xz_blocks": points, "samples": len(samples),
                        "sample_spacing_max_blocks": spacing, "feet_y": feet,
                        "player_width_blocks": width, "player_height_blocks": height,
                        "minimum_required_support_area_blocks2": .09,
                        "minimum_observed_support_area_blocks2": minimum_support,
                        "failures": failures, "compared_route_volume_cells_including_air": len(probes),
                        "source_state_differences": differences,
                        "passed": not failures and not differences})
    return reports, len(all_probes)


def verified_physical_resolution(study, source_hash, path):
    """Accept only the separately recorded, hash-bound one-cell cap resolution."""
    from audit_hill_court_terrain import load_structural_cap_proof
    report = json.loads(read_json(path))
    if (report.get("format") != "hill-athey-physical-source-cap-resolution-v1"
            or report.get("archive_sha256") != source_hash or not report.get("passed")
            or len(report.get("checks", {})) != 12 or not all(report["checks"].values())):
        raise ValueError("Invalid source physical cap resolution")
    for key, name in (("raw_physical_source_audit", "physical-source-audit.json"),
                      ("raw_court_audit", "court-terrain-audit.json"),
                      ("resolved_court_audit", "court-terrain-structural-cap-audit.json")):
        if report[key]["sha256"] != digest(study / name):
            raise ValueError(f"Physical resolution input changed: {name}")
    for name, expected in report["verification_reports"].items():
        if Path(name).name != name or digest(study / name) != expected:
            raise ValueError(f"Physical resolution verification changed: {name}")
    court = json.loads(read_json(study / "court-terrain-structural-cap-audit.json"))
    cap_path = study / "structural-floor-cap-proof.json"
    proof, _, _ = load_structural_cap_proof(cap_path)
    if (not court["passed"] or not court["structural_cap_proof"]["passed"]
            or court["structural_cap_proof"]["sha256"] != digest(cap_path)
            or proof["source"]["archive_sha256"] != source_hash
            or court["structural_cap_proof"]["exact_structurally_supported_cap"] != [
                {"region": "west_gallery", "xyz": [74, 88, 119]}]):
        raise ValueError("Physical resolution does not bind the exact supported cap")
    return {"path": str(path), "sha256": digest(path), "passed": True,
            "scope": "Raw source failure retained; only the exact four-sided structural cap is resolved."}


def audit(campus, study, source_physical_resolution=None):
    manifest_path = campus / "manifest.json"
    manifest_hash = digest(manifest_path)
    manifest = json.loads(read_json(manifest_path))
    if manifest["blocks_per_metre"] != 2 or manifest["vertical_offset_m"] != -25:
        raise ValueError("The combined campus must retain the accepted 2x coordinate frame")
    source_hash = digest(study / "sample-blocks.npz")
    profile_hash = digest(study / "profile.json")
    profile = json.loads(read_json(study / "profile.json"))
    source_manifest = json.loads(read_json(study / "manifest.json"))
    review = json.loads(read_json(study / "native-review.json"))
    physical = json.loads(read_json(study / "physical-source-audit.json"))
    components = [c for c in manifest["components"] if Path(c["study"]).resolve() == study.resolve()]
    if len(components) != 1 or components[0]["archive_sha256"] != source_hash:
        raise ValueError("Campus does not integrate this exact accepted Athey/Dining archive once")
    if source_manifest["profile"]["sha256"] != profile_hash:
        raise ValueError("Source profile has changed since artifact generation")
    if review.get("status") != "accepted_for_bounded_integration" or review.get("archive_sha256") != source_hash:
        raise ValueError("Source review does not accept this exact archive")
    if physical.get("archive_sha256") != source_hash:
        raise ValueError("Source physical audit is not passed and bound to the accepted archive")
    physical_resolution = None
    if not physical.get("passed"):
        if source_physical_resolution is None:
            raise ValueError("Source physical audit is not passed; provide its exact separately resolved structural-cap proof when applicable")
        physical_resolution = verified_physical_resolution(study, source_hash, source_physical_resolution)
    states = CombinedStates(campus, study, manifest)
    routes, route_cells = route_audit(states, profile)
    compared, differences, examples = 0, 0, []
    for iy in range(384):
        selected = states.architecture & (iy-64 >= states.minimum)
        changed = selected & (states.actual[iy] != states.expected[iy])
        compared += int(selected.sum())
        differences += int(changed.sum())
        for iz, ix in np.argwhere(changed)[:max(0, 100-len(examples))]:
            examples.append(states.mismatch((int(ix)+states.x0, iy-64, int(iz)+states.z0)))
    roof_differences = [row for q in states.roof_cells if (row := states.mismatch(tuple(map(int, q))))]
    panes = sorted({tuple(q) for opening in source_manifest["dining_openings"] for q in opening["pane_cells"]})
    pane_failures = []
    for q in panes:
        horizontal = [d for d in AXES if d[1] == 0 and states.contact_area(q, d) > 0]
        vertical = [d for d in AXES if d[1] != 0 and states.contact_area(q, d) > 0]
        if len(horizontal) < 2 or len(vertical) < 2:
            pane_failures.append({"xyz": q, "horizontal_contacts": horizontal, "vertical_contacts": vertical})
    backing_failures = []
    backing_pairs = source_manifest["dining_partial_backing"]["pairs"]
    for q, b in backing_pairs:
        direction = tuple(b[i]-q[i] for i in range(3))
        if states.contact_area(tuple(q), direction) <= 0:
            backing_failures.append({"xyz": q, "backing": b})
    if digest(manifest_path) != manifest_hash:
        raise ValueError("Campus manifest changed while this audit was running")
    passed = (all(route["passed"] for route in routes) and not differences
              and not roof_differences and not pane_failures and not backing_failures)
    return {
        "format": "hill-athey-dining-combined-connection-audit-v1", "passed": passed,
        "campus": str(campus.resolve()), "manifest_sha256": manifest_hash,
        "source": {"study": str(study.resolve()), "archive_sha256": source_hash,
                   "profile_sha256": profile_hash, "manifest_sha256": digest(study / "manifest.json"),
                   "native_review_sha256": digest(study / "native-review.json"),
                   "physical_source_audit_sha256": digest(study / "physical-source-audit.json"),
                   "physical_source_resolution": physical_resolution},
        "auditor_sha256": digest(Path(__file__)),
        "occupied_shape_helper_sha256": digest(ROOT / "scripts/audit_hill_quadrivium_contacts.py"),
        "verified_combined_tiles": states.tiles,
        "walking_routes": routes, "unique_route_volume_cells_including_air": route_cells,
        "architectural_columns": {"columns": int(states.architecture.sum()),
                                  "compared_full_states_including_air": compared,
                                  "different_cells": differences, "examples": examples,
                                  "scope": "Every column containing source architecture (including floors, roofs, piers, glazing, stairs and trim), from its actual foundation through Y319. Includes surrounding air in those columns; excludes source-only exterior pavement/terrain columns."},
        "accepted_roof_states": {"cells": len(states.roof_cells), "different_cells": len(roof_differences),
                                 "examples": roof_differences[:100]},
        "declared_connection_controls": {
            "east_link": profile["east_link"], "west_link": profile["west_link"],
            "source_regions": [region for region in profile["mutation_regions"] if region["name"] in {"east_link", "west_link", "dining_front"}],
            "verification": "Exact architectural columns and roof states retain the already accepted Athey-to-link and link-to-Dining junction geometry, including declared east roof closure. No new junction acceptance inferred from labels."},
        "dining_pane_contacts": {"panes": len(panes), "failures": pane_failures},
        "dining_partial_backing": {"checks": len(backing_pairs), "failures": backing_failures},
        "source_review_limits": review.get("limits", []),
        "limits": [
            "This audit reads combined tile archives; archive-to-Anvil/native parity and new native visual review remain separate required checks.",
            "The accepted actual player is 0.6 x 1.8 blocks. The conservative 2 x 4 block envelope does not pass all routes and is not certified here.",
            "Samples include both endpoints with maximum 0.1-block spacing; twenty additional samples versus the old 2084-sample source audit correct its slightly wider interval rounding.",
            "Occupied shapes reuse the accepted straight-stair/slab/pane/bar/closed-door model; unsupported stair and open-door variants fail explicitly. Generic other blocks retain that helper's full-cube approximation.",
            "Exact source preservation does not accept unresolved Athey facade enclosure, concealed openings, interior rooms, or photographic opening counts.",
            "Exterior campus approaches beyond the twenty source route endpoints require their own grade, support and player-clearance audit.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campus", type=Path)
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--source-physical-resolution", type=Path,
                        help="Exact separately resolved one-cell structural cap proof; raw failures remain preserved")
    parser.add_argument("--output", type=Path, required=True,
                        help="New report path; existing files are never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report = audit(args.campus.resolve(), args.study.resolve(), args.source_physical_resolution)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps({"passed": report["passed"], "report": str(args.output),
                      "routes": len(report["walking_routes"]),
                      "route_failures": [route["name"] for route in report["walking_routes"] if not route["passed"]],
                      "samples": sum(route["samples"] for route in report["walking_routes"]),
                      "architectural_state_differences": report["architectural_columns"]["different_cells"],
                      "roof_state_differences": report["accepted_roof_states"]["different_cells"],
                      "pane_failures": len(report["dining_pane_contacts"]["failures"]),
                      "backing_failures": len(report["dining_partial_backing"]["failures"])}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
