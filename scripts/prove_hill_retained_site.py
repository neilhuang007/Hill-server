"""Explain only exact inherited site overrides after a reviewed study amendment."""

import argparse
import json
from pathlib import Path

from assemble_hill_campus_studies import prepare_component
from audit_hill_window_joints import ArchiveStates
from build_hill_chapel_sample import ROLES
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def key(state):
    if isinstance(state, (list, tuple)):
        return state[0], tuple(tuple(p) for p in state[1])
    return state["Name"], tuple(sorted(state.get("Properties", {}).items()))


def prove(directory, report_path, output):
    manifest, report = read(directory / "manifest.json"), read(report_path)
    revision = manifest["study_revision"]
    source = Path(revision["base"])
    old_manifest = read(source / "manifest.json")
    if report["manifest_sha256"] != digest(directory / "manifest.json"):
        raise ValueError("Raw comparison does not match current manifest")
    cells = report["examples"]
    if len(cells) != sum(report["different_cells"].values()):
        raise ValueError("Raw comparison examples are truncated")
    changed = {tuple(c["xyz"]) for c in read(directory / "study-mutations.json")["cells"]}
    replacements = {Path(r["after"]["study"]).name: r for r in revision["replacements"]}
    # A later amendment can replace one study while retaining other previously
    # reviewed studies and their exact campus-site differences.
    old_components = {Path(c["study"]).name: c for c in old_manifest["components"]}
    for component in manifest["components"]:
        name = Path(component["study"]).name
        if name not in replacements and old_components.get(name) == component:
            replacements[name] = {"before": component, "after": component}
    cache = ROOT / "runtime/campus-reconstruction/component-cache"
    loaded, tiles, inputs = {}, {}, []

    def bind(path):
        record = {"path": str(path.resolve()), "sha256": digest(path)}
        if record not in inputs:
            inputs.append(record)

    for path in (directory / "manifest.json", source / "manifest.json", report_path,
                 directory / "study-mutations.json"):
        bind(path)
    for cell in cells:
        name, xyz = cell["study"], tuple(cell["xyz"])
        if xyz in changed:
            raise ValueError(f"Changed cell cannot be an inherited override: {cell}")
        if name not in loaded:
            replacement = replacements[name]
            pair = []
            for side in ("before", "after"):
                meta = replacement[side]
                study = Path(meta["study"])
                bind(study / "sample-blocks.npz")
                pair.append(prepare_component(study, cache, 2, -25, meta["margin_m"]))
            loaded[name] = pair
        x, y, z = xyz
        states = []
        for component in loaded[name]:
            ix, iz = x-component.meta["x_min"], z-component.meta["z_min"]
            state = component.meta["palette"][int(component.data[y+64, iz, ix])]
            role = ROLES[int(component.roles[y+64, iz, ix])]
            if role not in {"air", "terrain", "pavement", "vegetation"}:
                raise ValueError(f"Architectural cell cannot be retained-site proof: {cell}")
            states.append(key(state))
        if states[0] != states[1] or states[1] != key(cell["expected"]):
            raise ValueError(f"Source cell is not unchanged: {cell}")
        xmin, zmin = old_manifest["bounds_xz_blocks"][:2]
        tile_name = f"x{xmin+(x-xmin)//256*256}_z{zmin+(z-zmin)//256*256}"
        if tile_name not in tiles:
            path = source / "tiles" / tile_name / "sample-blocks.npz"
            bind(path)
            tiles[tile_name] = ArchiveStates(path)
        lookup = tiles[tile_name]
        if key(lookup.palette[lookup.get(x,y,z)]) != key(cell["actual"]):
            raise ValueError(f"Campus mismatch is not inherited: {cell}")
    proof = {"format": "hill-retained-site-proof-v1", "passed": True,
             "manifest_sha256": digest(directory / "manifest.json"), "count": len(cells),
             "inputs": inputs, "site_cells": cells,
             "scope": "Every listed site state equals the accepted prior campus, the source study cell is unchanged, and no mutation touches it. No architectural or newly changed state is exempted."}
    write_json(output, proof)
    print(json.dumps({"passed": True, "count": len(cells), "output": str(output)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prove(args.directory, args.report, args.output)
