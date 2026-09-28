"""Independently verify every campus mutation against its reviewed source study."""

import argparse
from collections import Counter
import gc
import json
from pathlib import Path

import numpy as np

from build_hill_chapel_sample import ROLES
from campus_export_parity import read_archive
from campus_study_io import digest, write_json
from refine_hill_campus_environment import load_canvas


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def audit(directory):
    manifest = read(directory / "manifest.json")
    revision = manifest["study_revision"]
    source = Path(revision["base"])
    before = read(source / "manifest.json")
    journal_path = directory / "study-mutations.json"
    errors, totals = [], Counter()
    if digest(source / "manifest.json") != revision["base_manifest_sha256"]:
        errors.append("Accepted base manifest changed")
    if digest(journal_path) != revision["journal_sha256"]:
        errors.append("Mutation journal changed")
    journal = read(journal_path)["cells"]
    claims = {tuple(c["xyz"]): c for c in journal}
    if len(claims) != len(journal):
        errors.append("Duplicate mutation claim")
    # Check the target value directly in each frozen new study archive.
    for replacement in revision["replacements"]:
        meta = replacement["after"]
        study = Path(meta["study"])
        if digest(study / "sample-blocks.npz") != meta["archive_sha256"]:
            errors.append(f"Reviewed source changed: {study}")
        lookup = load_canvas(read_archive(study / "sample-blocks.npz"),
                             (meta["x_min"],meta["z_min"],meta["x_min"]+meta["shape"][2],
                              meta["z_min"]+meta["shape"][1]))
        for claim in journal:
            if claim["study"] != str(study):
                continue
            x,y,z = claim["xyz"]
            state = lookup.palette[lookup.get(x,y,z)]
            role = ROLES[int(lookup.roles[y+64,z-meta["z_min"],x-meta["x_min"]])]
            if state != claim["after"] or role != claim["after_role"]:
                errors.append(f"Mutation differs from reviewed source: {claim['xyz']}")
        del lookup
    old_tiles = {t["path"]: t for t in before["tiles"]}
    found = set()
    xmax, zmax = manifest["bounds_xz_blocks"][2:]
    for spec in manifest["tiles"]:
        relative = spec["path"]
        old_spec = old_tiles[relative]
        if spec["archive_sha256"] == old_spec["archive_sha256"]:
            if digest(directory / relative / "sample-blocks.npz") != old_spec["archive_sha256"]:
                errors.append(f"Unchanged tile hash mismatch: {relative}")
            totals["unchanged_tiles"] += 1
            totals["unchanged_occupied_blocks"] += spec["blocks"]
            continue
        tx, tz = map(int, Path(relative).name[1:].split("_z"))
        bounds = (tx, tz, min(tx+256, xmax), min(tz+256, zmax))
        a = load_canvas(read_archive(source / relative / "sample-blocks.npz"), bounds)
        b = load_canvas(read_archive(directory / relative / "sample-blocks.npz"), bounds)
        lookup = {json.dumps(p, sort_keys=True): i for i, p in enumerate(a.palette)}
        mapping = np.asarray([lookup.get(json.dumps(p, sort_keys=True), len(lookup)+i)
                              for i, p in enumerate(b.palette)], np.uint32)
        different = (a.data != mapping[b.data]) | (a.roles != b.roles)
        totals["compared_cells_including_air"] += a.data.size
        for iy, iz, ix in np.argwhere(different):
            xyz = (int(ix+tx), int(iy-64), int(iz+tz))
            claim = claims.get(xyz)
            expected = {"before": a.palette[int(a.data[iy,iz,ix])],
                        "after": b.palette[int(b.data[iy,iz,ix])],
                        "before_role": ROLES[int(a.roles[iy,iz,ix])],
                        "after_role": ROLES[int(b.roles[iy,iz,ix])]}
            if claim is None or any(claim[k] != v for k, v in expected.items()):
                errors.append(f"Unexplained exact state/role mutation: {xyz}")
            found.add(xyz)
        totals["changed_tiles"] += 1
        del a, b, different
        gc.collect()
    if found != set(claims):
        errors.append("Mutation journal does not match the complete exact delta")
    totals["changed_cells"] = len(found)
    result = {"format": "hill-study-revision-audit-v1", "passed": not errors,
              "manifest_sha256": digest(directory / "manifest.json"), "totals": dict(totals),
              "errors": errors, "scope": "Every changed state and role including air, exact new study source values, all other accepted campus cells preserved."}
    write_json(directory / "study-preservation-audit.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    report = audit(parser.parse_args().directory)
    raise SystemExit(0 if report["passed"] else 1)
