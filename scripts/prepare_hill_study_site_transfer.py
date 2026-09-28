"""Enumerate exact old-landscape conflicts around newly reviewed entry sitework.

The output is a reviewable proposal, not a permission to overwrite arbitrary
landscape. Each resolution records the current campus state and exact new study
state. Supplemental cells are limited to the vertical neighborhood of authored
site changes in the same column; architectural states cannot be transferred.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from apply_hill_study_deltas import component_delta, read
from assemble_hill_campus_studies import prepare_component
from build_hill_chapel_sample import ROLES
from campus_export_parity import read_archive
from campus_study_io import digest, write_json
from prepare_hill_campus_revision import study_identity
from refine_hill_campus_environment import load_canvas

ROOT = Path(__file__).resolve().parents[1]
SITE = {"air", "terrain", "pavement", "vegetation"}


def prepare(source, studies, output):
    if output.exists():
        raise FileExistsError(output)
    manifest = read(source / "manifest.json")
    xmin, zmin, xmax, zmax = manifest["bounds_xz_blocks"]
    existing = {study_identity(Path(c["study"]))[0]: c for c in manifest["components"]}
    tiles, inputs, resolutions, supplemental, summaries = {}, [], [], [], []
    cache = ROOT / "runtime/campus-reconstruction/component-cache"

    def bind(path):
        record = {"path": path.resolve().relative_to(ROOT).as_posix(), "sha256": digest(path)}
        if record not in inputs:
            inputs.append(record)

    def campus_at(x, y, z):
        tx, tz = xmin+(x-xmin)//256*256, zmin+(z-zmin)//256*256
        name = f"x{tx}_z{tz}"
        if name not in tiles:
            path = source / "tiles" / name / "sample-blocks.npz"
            bind(path)
            tiles[name] = load_canvas(read_archive(path), (tx,tz,min(tx+256,xmax),min(tz+256,zmax)))
        c = tiles[name]
        return c.palette[c.get(x,y,z)], ROLES[int(c.roles[y+64,z-tz,x-tx])]

    for path in studies:
        path = path.resolve()
        meta = existing[study_identity(path)[0]]
        old_path = Path(meta["study"])
        old = prepare_component(old_path, cache, 2, -25, meta["margin_m"])
        new = prepare_component(path, cache, 2, -25, .5)
        for study in (old_path, path):
            for file in ("sample-blocks.npz", "profile.json"):
                bind(study/file)
        if (path/"native-review.json").exists():
            bind(path/"native-review.json")
        changes = component_delta(old, new)
        changed = {tuple(c["xyz"]) for c in changes}
        site_columns = defaultdict(list)
        counts = Counter(source_changes=len(changes))
        for change in changes:
            x,y,z = change["xyz"]
            state, role = campus_at(x,y,z)
            old_matches = state == change["before"] and role == change["before_role"]
            new_matches = state == change["after"] and role == change["after_role"]
            if not old_matches and not new_matches:
                if role not in SITE or change["before_role"] not in SITE:
                    raise ValueError({"architectural_conflict": change, "actual": state, "role":role})
                resolutions.append({"xyz":change["xyz"],"study":new.meta["study"],
                    "campus":state,"campus_role":role,"after":change["after"],
                    "after_role":change["after_role"],
                    "reason":"Exact new supported entry/courtyard construction supersedes this older nonarchitectural landscape cell."})
                counts["conflicts"] += 1
            if change["before_role"] in SITE and change["after_role"] in SITE:
                site_columns[(x,z)].append(y)
        for (x,z), heights in site_columns.items():
            ix, iz = x-new.meta["x_min"], z-new.meta["z_min"]
            if not new.mask[iz,ix]:
                raise ValueError("New site column is not owned")
            for y in range(max(-63,min(heights)-2),min(319,max(heights)+4)+1):
                if (x,y,z) in changed:
                    continue
                state = new.meta["palette"][int(new.data[y+64,iz,ix])]
                role = ROLES[int(new.roles[y+64,iz,ix])]
                actual, actual_role = campus_at(x,y,z)
                if actual == state and actual_role == role:
                    continue
                if role not in SITE or actual_role not in SITE:
                    # Any altered architecture needs a reviewed building delta.
                    continue
                # Do not restore grass/planting from old study baselines. Restore
                # support or clear circulation only in newly authored columns.
                if role == "vegetation" or state["Name"] == "minecraft:grass_block":
                    continue
                supplemental.append({"xyz":[x,y,z],"study":new.meta["study"],
                    "before":actual,"before_role":actual_role,"after":state,"after_role":role,
                    "reason":"Retain exact new entry support/headroom in the same authored site column."})
                counts["supplemental"] += 1
        summaries.append({"study":str(path),**counts})
    result = {"format":"hill-study-site-transfer-v1", "source_manifest_sha256":digest(source/"manifest.json"),
        "inputs":inputs,"resolutions":resolutions,"supplemental_cells":supplemental,"summary":summaries,
        "scope":"Enumerated exact new study site states around authored entries/courtyard; no architectural conflict override."}
    write_json(output,result)
    print(json.dumps({"output":str(output),"summary":summaries},indent=2),flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--study",type=Path,action="append",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    prepare(a.source,a.study,a.output)
