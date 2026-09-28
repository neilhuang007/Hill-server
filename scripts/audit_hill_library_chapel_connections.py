"""Verify accepted Ryan/Chapel entries in merged campus tile archives.

Read-only on studies and campus. The requested output files must be new.
This checks the accepted source routes, partial contacts and exact entry delta;
shared routes between buildings belong to the separate environment audit.
"""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np

from audit_hill_athey_dining_connections import CombinedStates
from audit_hill_quadrivium_contacts import AXES
from campus_study_io import digest, write_json
from refine_hill_library_chapel import EntryAmendment, load_canvas, occupied_shapes, route_audit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDIES = [
    ROOT / "runtime/campus-reconstruction/ryan-library-entry-v3-2x",
    ROOT / "runtime/campus-reconstruction/chapel-entry-v1-2x",
]
CRITICAL_VIEWS = {
    "ryan-west-front", "ryan-central-entry", "ryan-south-west-steps",
    "ryan-arcade-oblique", "chapel-south-threshold",
    "chapel-east-walk-join", "chapel-east-whole",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RouteWindow:
    """Use the exact standalone route helper against a verified merged window."""

    def __init__(self, states, source=False):
        self.states, self.source = states, source
        self.x_min, self.z_min, self.scale = states.x0, states.z0, 2
        self.palette = states.palette
        self.ground_heights = np.zeros((states.depth, states.width), dtype=np.int16)
        self.probes = set()

    def get(self, x, y, z):
        q = (int(x), int(y), int(z))
        self.probes.add(q)
        return self.states.get(q, source=self.source)


def physical_contacts(states, source_report):
    @lru_cache(maxsize=None)
    def boxes(q):
        return occupied_shapes(states.palette[states.get(q)])

    def area(q, direction):
        neighbor = tuple(q[i]+direction[i] for i in range(3))
        axis = next(i for i, value in enumerate(direction) if value)
        tangents = [i for i in range(3) if i != axis]
        score = 0
        for left in boxes(q):
            for right in boxes(neighbor):
                right = [right[i]+16*direction[i % 3] for i in range(6)]
                if left[axis+3 if direction[axis] > 0 else axis] != right[axis if direction[axis] > 0 else axis+3]:
                    continue
                overlap = [min(left[i+3], right[i+3])-max(left[i], right[i]) for i in tangents]
                if min(overlap) > 0:
                    score += math.prod(overlap)
        return score

    failures, state_changes, checks = [], [], []
    for source in source_report["contacts"]:
        q = tuple(source["xyz"])
        state = states.palette[states.get(q)]
        if state != source["state"]:
            state_changes.append({"xyz": list(q), "expected": source["state"], "actual": state})
        directions = [list(d) for d in AXES if area(q, d) > 0]
        name = state["Name"]
        failed = (not directions
                  or name == "minecraft:iron_bars" and [0, -1, 0] not in directions
                  or name.endswith("_pane") and
                  (sum(d[1] == 0 for d in directions) < 2 or sum(d[1] != 0 for d in directions) < 2))
        check = {"xyz": list(q), "positive_area_contacts": directions}
        checks.append(check)
        if failed:
            failures.append({**check, "state": state})
    return {"passed": not failures and not state_changes, "checks": len(checks),
            "failed_contacts": failures, "source_state_changes": state_changes,
            "occupied_contact_checks": checks}


def camera_check(states, camera):
    eye = np.asarray(camera["eye"], float)
    target = np.asarray(camera["target"], float)
    blocked = []
    # Eye plus a small clearance cube prevents placing the native camera
    # exactly on a neighbor wall/leaf edge. Keep original accepted camera poses.
    for dx in (-.2, 0, .2):
        for dy in (-.2, 0, .2):
            for dz in (-.2, 0, .2):
                point = eye + [dx, dy, dz]
                q = tuple(map(math.floor, point))
                state = states.palette[states.get(q)]
                if state["Name"] != "minecraft:air":
                    blocked.append({"xyz": list(q), "state": state})
    direction = target-eye
    distance = float(np.linalg.norm(direction))
    near_ray = []
    for length in np.arange(.25, min(6., distance*.2), .25):
        q = tuple(map(math.floor, eye + direction * length / distance))
        state = states.palette[states.get(q)]
        if state["Name"] != "minecraft:air":
            near_ray.append({"xyz": list(q), "state": state})
    return {"name": camera["name"], "eye": camera["eye"],
            "clear_eye_and_near_ray": not blocked and not near_ray,
            "blocked_eye_samples": blocked, "near_ray_obstructions": near_ray}


def audit(campus, studies, camera_only=False, retained_campus=None):
    manifest_path = campus / "manifest.json"
    manifest_hash = digest(manifest_path)
    manifest = read(manifest_path)
    if (manifest["blocks_per_metre"], manifest["vertical_offset_m"]) != (2, -25):
        raise ValueError("Combined campus changed the accepted coordinate frame")
    reports, cameras, camera_reports = [], [], []
    retained_manifest = read(retained_campus / "manifest.json") if retained_campus else None
    retained_manifest_hash = digest(retained_campus / "manifest.json") if retained_campus else None
    for study in studies:
        archive_hash = digest(study / "sample-blocks.npz")
        profile = read(study / "profile.json")
        review = read(study / "native-review.json")
        artifact = read(study / "artifact-audit.json")
        physical = read(study / "entry-physical-audit.json")
        standalone_routes = read(study / "entry-route-audit.json")
        if review.get("status") != "accepted_for_bounded_integration" or review["archive_sha256"] != archive_hash:
            raise ValueError(f"Study is not accepted at this exact archive: {study}")
        for label, report in (("artifact", artifact), ("physical", physical), ("routes", standalone_routes)):
            if not report.get("passed", label == "artifact") or report["archive_sha256"] != archive_hash:
                raise ValueError(f"The accepted {label} check is not bound to this archive: {study}")
        component = [c for c in manifest["components"] if Path(c["study"]).resolve() == study.resolve()]
        integrated = len(component) == 1 and component[0]["archive_sha256"] == archive_hash
        if not integrated and not camera_only:
            raise ValueError(f"Study is not integrated exactly once: {study}")
        states = CombinedStates(campus, study, manifest)
        current_cameras = [view for view in read(study / "camera-views.json")["views"] if view["name"] in CRITICAL_VIEWS]
        kind = "ryan-library" if profile.get("parent_id") == "160015116006-567a5eddd9" else "chapel"
        expected_views = {name for name in CRITICAL_VIEWS if name.startswith("ryan-" if kind == "ryan-library" else "chapel-")}
        if {view["name"] for view in current_cameras} != expected_views or len(current_cameras) != len(expected_views):
            raise ValueError(f"Critical accepted camera set is incomplete: {study}")
        geometry = EntryAmendment(RouteWindow(states, True), profile, kind)
        # The isolated southern stair observer sits behind a retained campus
        # tree. Move only the combined review camera onto the adjacent apron;
        # the original accepted source camera and every source block remain.
        for index, camera in enumerate(current_cameras):
            if camera["name"] == "ryan-south-west-steps":
                x, z = geometry.world((-9, -7))
                current_cameras[index] = {
                    **camera, "eye": [float(x), 91., float(z)],
                    "source_eye": camera["eye"],
                    "campus_camera_adjustment": "Move to local U-9,V-7,H70.5 on the west apron to avoid the retained tree near X209,Z76; target and FOV retained.",
                }
        cameras.extend(current_cameras)
        camera_reports.extend(camera_check(states, view) for view in current_cameras)
        if camera_only:
            reports.append({"study": str(study.resolve()), "integrated": integrated, "verified_tiles": states.tiles})
            continue
        source_window, combined_window = RouteWindow(states, True), RouteWindow(states)
        geometry = EntryAmendment(source_window, profile, kind)
        source_routes = route_audit(source_window, geometry, profile["walking_routes"], True)
        actual_routes = route_audit(combined_window, geometry, profile["walking_routes"], True)
        expected_summary = [(r["name"], r["samples"], r["passed"], r["maximum_step_blocks"]) for r in standalone_routes["routes"]]
        actual_summary = [(r["name"], r["samples"], r["passed"], r["maximum_step_blocks"]) for r in source_routes["routes"]]
        if not source_routes["passed"] or expected_summary != actual_summary:
            raise ValueError(f"The route helper does not reproduce accepted source checks: {study}")
        probes = source_window.probes | combined_window.probes
        route_differences = [different for q in sorted(probes) if (different := states.mismatch(q))]
        with np.load(study / "entry-delta.npz", allow_pickle=False) as delta:
            delta_cells = [tuple(map(int, q)) for q in delta["coords"]]
        delta_differences = [different for q in delta_cells if (different := states.mismatch(q))]
        retained_proof, unexplained_routes = [], list(route_differences)
        retained_tiles = []
        if route_differences and retained_campus:
            # Preserve an explicitly named accepted campus's solid support
            # material only. No air, missing floor, moved slab, vegetation or
            # authored entry change can pass through this bounded proof.
            retained = CombinedStates(retained_campus, study, retained_manifest)
            baseline = ROOT / profile["baseline_study"]
            if digest(baseline / "sample-blocks.npz") != profile["baseline_archive_sha256"]:
                raise ValueError(f"Original entry baseline changed: {baseline}")
            before = load_canvas(baseline)
            delta_set, unexplained_routes = set(delta_cells), []
            full_cube = ((0, 0, 0, 16, 16, 16),)
            for difference in route_differences:
                q = tuple(difference["xyz"])
                source_state, actual_state = difference["expected"], difference["actual"]
                original_state = before.palette[before.get(*q)]
                retained_state = retained.palette[retained.get(q)]
                proven = (q not in delta_set and source_state == original_state
                          and actual_state == retained_state
                          and occupied_shapes(source_state) == full_cube
                          and occupied_shapes(actual_state) == full_cube)
                if proven:
                    retained_proof.append({**difference, "unchanged_source_baseline": True,
                                           "equals_retained_campus": True,
                                           "same_full_cube_support_shape": True})
                else:
                    unexplained_routes.append(difference)
            retained_tiles = retained.tiles
        contacts = physical_contacts(states, physical)
        passed = actual_routes["passed"] and not unexplained_routes and not delta_differences and contacts["passed"]
        reports.append({"study": str(study.resolve()), "archive_sha256": archive_hash,
            "profile_sha256": digest(study / "profile.json"), "native_review_sha256": digest(study / "native-review.json"),
            "integrated": integrated, "verified_tiles": states.tiles, "passed": passed,
            "accepted_source_routes_reproduced": True, "combined_routes": actual_routes,
            "exact_entry_delta": {"checked_cells": len(delta_cells), "different_cells": len(delta_differences), "differences": delta_differences},
            "exact_route_probe_volume": {"checked_cells_including_air": len(probes), "different_cells": len(route_differences), "differences": route_differences,
                                         "unexplained_different_cells": len(unexplained_routes), "unexplained_differences": unexplained_routes},
            "retained_solid_support_proof": {"campus": str(retained_campus) if retained_campus else None,
                                             "manifest_sha256": retained_manifest_hash,
                                             "verified_tiles": retained_tiles, "count": len(retained_proof), "cells": retained_proof},
            "entry_partial_contacts": contacts})
    if digest(manifest_path) != manifest_hash:
        raise ValueError("Campus manifest changed during verification")
    if retained_campus and digest(retained_campus / "manifest.json") != retained_manifest_hash:
        raise ValueError("Retained campus manifest changed during verification")
    cameras_pass = bool(cameras) and len(camera_reports) == len(cameras) and all(r["clear_eye_and_near_ray"] for r in camera_reports)
    return {"format": "hill-library-chapel-combined-entries-v1", "campus": str(campus.resolve()),
            "manifest_sha256": manifest_hash, "auditor_sha256": digest(Path(__file__)),
            "shape_and_route_helper_sha256": digest(ROOT / "scripts/refine_hill_library_chapel.py"),
            "camera_check_only": camera_only, "passed": cameras_pass and (camera_only or all(r["passed"] for r in reports)),
            "studies": reports, "camera_checks": camera_reports,
            "limits": ["Exact accepted source route waypoints and door-open semantics are reused. A supported 0.6 by 1.8 block player and at most half-block steps are required.",
                       "Entry deltas, including removed terrain and air, must remain exact. Raw route probe differences are retained. An explicitly named earlier campus can prove only unchanged, equal full-cube support materials outside the authored delta; air/vegetation/partial geometry cannot be waived.",
                       "New stair cheeks, rail feet, amended glazing and thresholds have physical contact checks. Whole-building architectural preservation is independently audited by the coordinator.",
                       "This does not certify unfinished interiors, hidden source details or paths between buildings. It creates no new architectural link between separately positioned buildings.",
                       "Camera eyes and initial viewing rays are checked for obstruction. Full native rendering, image inspection and archive-to-Anvil parity remain separate requirements."]}, {"format": "hill-native-camera-views-v1", "views": cameras}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campus", type=Path)
    parser.add_argument("--study", type=Path, action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--camera-output", type=Path)
    parser.add_argument("--camera-check-only", action="store_true")
    parser.add_argument("--retained-campus", type=Path,
                        help="Explicit accepted campus for an enumerated unchanged full-cube support proof")
    args = parser.parse_args()
    for path in (args.output, args.camera_output):
        if path and path.exists():
            raise FileExistsError(f"Use a fresh report path: {path}")
    report, cameras = audit(args.campus.resolve(), args.study or DEFAULT_STUDIES, args.camera_check_only,
                            args.retained_campus.resolve() if args.retained_campus else None)
    write_json(args.output, report)
    if args.camera_output:
        write_json(args.camera_output, cameras)
    print(json.dumps({"passed": report["passed"], "report": str(args.output),
                      "camera_failures": [c for c in report["camera_checks"] if not c["clear_eye_and_near_ray"]],
                      "studies": [{"study": r["study"], "passed": r.get("passed"),
                                   "route_differences": r.get("exact_route_probe_volume", {}).get("different_cells"),
                                   "unexplained_route_differences": r.get("exact_route_probe_volume", {}).get("unexplained_different_cells"),
                                   "delta_differences": r.get("exact_entry_delta", {}).get("different_cells"),
                                   "contact_failures": len(r.get("entry_partial_contacts", {}).get("failed_contacts", []))} for r in report["studies"]]}), flush=True)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
