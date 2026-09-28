"""Independently prove an environment revision changed only its enumerated site cells."""

import argparse
from collections import Counter
import gc
import json
from pathlib import Path

import numpy as np

from campus_export_parity import read_archive
from campus_study_io import digest, write_json
from refine_hill_campus_environment import load_canvas, SITE_ROLES


def audit(directory):
    read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    manifest = read(directory / "manifest.json")
    environment = manifest["environment_revision"]
    source = Path(environment["base"])
    old = read(source / "manifest.json")
    journal_path = directory / "environment-mutations.json"
    plan_path = directory / "environment-plan.json"
    errors = []
    if digest(source / "manifest.json") != environment["base_manifest_sha256"]:
        errors.append("Base manifest changed")
    if digest(journal_path) != environment["mutations_sha256"] or digest(plan_path) != environment["plan_sha256"]:
        errors.append("Environment plan/journal changed")
    if old["components"] != manifest["components"]:
        errors.append("Component assembly changed")
    journal = read(journal_path)["cells"]
    plan = read(plan_path)
    planned = {(c["x"], c["z"]): c for c in plan["columns"]}
    site_blocks = {tuple(c["xyz"]): c for c in plan.get("site_blocks", [])}
    claimed = {tuple(c["xyz"]): c for c in journal}
    if len(claimed) != len(journal):
        errors.append("Duplicate journal cell")
    old_tiles = {t["path"]: t for t in old["tiles"]}
    totals = Counter()
    found = set()
    xmax, zmax = manifest["bounds_xz_blocks"][2:]
    for spec in manifest["tiles"]:
        relative = spec["path"]
        before_spec = old_tiles[relative]
        if spec["archive_sha256"] == before_spec["archive_sha256"]:
            if digest(directory / relative / "sample-blocks.npz") != before_spec["archive_sha256"]:
                errors.append(f"Unchanged archive hash mismatch: {relative}")
            totals["unchanged_tiles"] += 1
            totals["unchanged_occupied_blocks"] += spec["blocks"]
            continue
        tx, tz = map(int, Path(relative).name[1:].split("_z"))
        bounds = (tx, tz, min(tx + 256, xmax), min(tz + 256, zmax))
        a = read_archive(source / relative / "sample-blocks.npz")
        b = read_archive(directory / relative / "sample-blocks.npz")
        ca, cb = load_canvas(a, bounds), load_canvas(b, bounds)
        del a, b
        lookup = {json.dumps(p, sort_keys=True): i for i, p in enumerate(ca.palette)}
        mapping = np.asarray([lookup.get(json.dumps(p, sort_keys=True), len(ca.palette) + i)
                              for i, p in enumerate(cb.palette)], np.uint32)
        difference = (ca.data != mapping[cb.data]) | (ca.roles != cb.roles)
        architecture = np.any(~np.isin(ca.roles, list(SITE_ROLES)), axis=0)
        if np.any(difference[:, architecture]):
            errors.append(f"Architectural column changed: {relative}")
        totals["compared_cells_including_air"] += ca.data.size
        for iy, iz, ix in np.argwhere(difference):
            xyz = (int(ix + tx), int(iy - 64), int(iz + tz))
            claim = claimed.get(xyz)
            expected = {"before": ca.palette[int(ca.data[iy, iz, ix])],
                        "before_role": __import__('build_hill_chapel_sample').ROLES[int(ca.roles[iy, iz, ix])],
                        "after": cb.palette[int(cb.data[iy, iz, ix])],
                        "after_role": __import__('build_hill_chapel_sample').ROLES[int(cb.roles[iy, iz, ix])]}
            if claim is None or any(claim[k] != v for k, v in expected.items()):
                errors.append(f"Unexplained exact state/role mutation: {xyz}")
            if (xyz[0], xyz[2]) not in planned and xyz not in site_blocks:
                errors.append(f"Mutation outside site plan: {xyz}")
            found.add(xyz)
        totals["changed_tiles"] += 1
        del ca, cb, difference, architecture
        gc.collect()
    if found != set(claimed):
        errors.append("Mutation journal is not the exact complete delta")
    totals["changed_cells"] = len(found)
    totals["architecture_changes"] = 0 if not any("Architectural" in e for e in errors) else -1
    result = {"format": "hill-environment-preservation-audit-v1", "passed": not errors,
              "manifest_sha256": digest(directory / "manifest.json"), "totals": dict(totals),
              "preserved_components": len(old["components"]), "errors": errors,
              "scope": "Exact complete state/role delta including air in changed tiles. Unchanged archives are byte-identical. Every original architecture column is preserved at all heights; no facade, roof, floor, pane, covered passage or fixture is altered. Ground and native/export audits are separate."}
    write_json(directory / "environment-preservation-audit.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    result = audit(p.parse_args().directory)
    raise SystemExit(0 if result["passed"] else 1)
