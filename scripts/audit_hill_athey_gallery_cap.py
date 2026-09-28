"""Read actual combined side-pocket route and exact retained north supports."""
import argparse
import json
import math
from pathlib import Path

from audit_hill_athey_dining_connections import CombinedStates
from campus_study_io import digest, write_json
from refine_hill_library_chapel import occupied_shapes

ROOT = Path(__file__).resolve().parents[1]


def audit(campus, retained, extended_path):
    read = lambda p: json.loads(p.read_text(encoding="utf-8"))
    study = ROOT / "runtime/campus-reconstruction/athey-dining-v20-2x"
    current = CombinedStates(campus, study, read(campus / "manifest.json"))
    old = CombinedStates(retained, study, read(retained / "manifest.json"))
    probes = set()
    samples = []
    for n in range(21):
        x, feet, z = 73.5 + n * .05, 89., 119.5
        body = (x - .3, feet, z - .3, x + .3, feet + 1.8, z + .3)
        support, collisions = 0., []
        for xx in range(math.floor(x - .3), math.floor(x + .3) + 1):
            for zz in range(math.floor(z - .3), math.floor(z + .3) + 1):
                for yy in range(88, 91):
                    q = (xx, yy, zz)
                    probes.add(q)
                    for shape in occupied_shapes(current.palette[current.get(q)]):
                        box = [shape[i] / 16 + q[i % 3] for i in range(6)]
                        spans = [min(body[i + 3], box[i + 3]) - max(body[i], box[i]) for i in range(3)]
                        if min(spans) > 1e-7:
                            collisions.append(list(q))
                        if abs(box[4] - feet) < 1e-7:
                            support += max(0, spans[0]) * max(0, spans[2])
        samples.append({"xyz_feet": [x, feet, z], "support_area": support, "collisions": collisions})
    differences = [d for q in sorted(probes) if (d := current.mismatch(q))]
    extended = read(extended_path)
    source_sha = digest(study / "sample-blocks.npz")
    manifest_sha = digest(campus / "manifest.json")
    assert extended["archive_sha256"] == source_sha and extended["campus_manifest_sha256"] == manifest_sha
    expected_north = {(117, 84, 78), (118, 84, 78)}
    journal_path = campus / "study-mutations.json"
    if not journal_path.exists():
        journal_path = campus / "environment-mutations.json"
    journal = read(journal_path)
    changed = {tuple(c["xyz"]) for c in journal["cells"]}
    north = []
    for difference in extended["source_state_differences"]:
        q = tuple(difference["xyz"])
        retained_state = old.palette[old.get(q)]
        current_state = current.palette[current.get(q)]
        valid = (q in expected_north and q not in changed and current_state == retained_state == difference["actual"]
                 and difference["expected"] == {"Name": "minecraft:air"}
                 and current_state == {"Name": "minecraft:bricks"})
        north.append({**difference, "equals_explicit_retained_campus": current_state == retained_state,
                      "outside_current_study_delta": q not in changed, "passed": valid})
    site = read(campus / "retained-site-proof.json")
    if not site.get("passed") or site.get("manifest_sha256") != manifest_sha:
        raise ValueError("Coordinator site proof must pass and bind this exact campus")
    listed_north = {tuple(c["xyz"]) for c in site["site_cells"]
                    if c["study"] == study.name and tuple(c["xyz"]) in expected_north}
    # Retain the coordinator's complete proof by hash; the direct cell proof
    # above independently compares actual source-sized windows from both worlds.
    valid_north = ({tuple(d["xyz"]) for d in north} == expected_north
                   and listed_north == expected_north and all(d["passed"] for d in north))
    passed = all(s["support_area"] >= .3599999 and not s["collisions"] for s in samples) and not differences and extended["passed"] and valid_north
    return {"format": "hill-athey-combined-gallery-cap-v1", "passed": passed,
            "campus_manifest_sha256": manifest_sha, "source_archive_sha256": source_sha,
            "verified_combined_tiles": current.tiles, "auditor_sha256": digest(Path(__file__)),
            "route": {"name": "west-gallery-side-pocket-floor", "samples": 21, "maximum_step_blocks": 0,
                      "minimum_support_area": min(s["support_area"] for s in samples), "checks": samples,
                      "exact_source_probe_differences": differences},
            "retained_north_support_proof": {"campus": str(retained), "manifest_sha256": digest(retained / "manifest.json"),
                                             "verified_tiles": old.tiles, "cells": north, "passed": valid_north,
                                             "current_journal": str(journal_path),
                                             "current_journal_sha256": digest(journal_path),
                                             "coordinator_site_proof_sha256": digest(campus / "retained-site-proof.json")},
            "extended_route_report": {"path": str(extended_path), "sha256": digest(extended_path), "physical_passed": extended["passed"],
                                      "raw_source_parity_passed": extended["source_state_parity_passed"]},
            "scope": "Actual 0.6x1.8-block player at 0.05-block intervals; exact source probe states. The sole two raw extended-route differences remain explicit and equal the named retained campus outside the exact current mutation journal, with both cells included in the passed full-source site proof."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campus", type=Path)
    parser.add_argument("--retained-campus", type=Path, required=True)
    parser.add_argument("--extended-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit(args.campus, args.retained_campus, args.extended_report)
    write_json(args.output, result)
    print(json.dumps({"passed": result["passed"], "samples": result["route"]["samples"],
                      "minimum_support_area": result["route"]["minimum_support_area"],
                      "retained_north_supports": result["retained_north_support_proof"]["cells"]}))
    raise SystemExit(0 if result["passed"] else 1)
