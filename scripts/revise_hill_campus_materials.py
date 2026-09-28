"""Export every current component with its reviewed material-only revision.

Every source archive is retained. Occupied coordinates, semantic roles, panes
and shape properties are unchanged. A material audit is not facade acceptance.
"""

import argparse
import gc
import json
from pathlib import Path

import numpy as np
from build_hill_chapel_sample import Canvas, ROLES
from campus_material_assignment import REGISTRY, apply_reviewed_palette, assignment_key
from campus_study_io import digest, finish_study, write_json

ROOT = Path(__file__).resolve().parents[1]


def revise(study, output, registry_path):
    p = json.loads((study / "profile.json").read_text(encoding="utf-8"))
    old = json.loads((study / "manifest.json").read_text(encoding="utf-8"))
    p["revision"] = p["revision"] + "-materials-20260907"
    p["material_assignment_key"] = assignment_key(p)
    p["material_assignment_source_sha256"] = digest(study / "sample-blocks.npz")
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    p.setdefault("name", registry["buildings"][p["material_assignment_key"]]["name"])
    p["vertical_offset_m"] = -25
    p.pop("vanilla_state_replacements", None)  # These have already been applied in source NPZ.
    p.pop("resource_pack", None)
    p.get("materials", {}).pop("resource_pack", None)
    with np.load(study / "sample-blocks.npz", allow_pickle=False) as a:
        xyz, states, roles = a["coords"], a["state_ids"], a["role_ids"]
        palette = json.loads(str(a["palette_json"]))
        names = [str(v) for v in a["role_names"]]
    low, high = xyz.min(axis=0), xyz.max(axis=0) + 1
    c = Canvas(int(low[0]), int(low[2]), int(high[0] - low[0]), int(high[2] - low[2]), 2)
    state_map = np.array([c.state(v["Name"], v.get("Properties")) for v in palette], dtype=np.uint16)
    role_map = np.array([ROLES.index(n) for n in names], dtype=np.uint8)
    x, y, z = (xyz - [low[0], -64, low[2]]).T
    c.data[y, z, x] = state_map[states]
    c.roles[y, z, x] = role_map[roles]
    report = apply_reviewed_palette(c, p, registry_path=registry_path)
    if report is None:
        raise ValueError(f"Missing explicit review entry: {study}")
    cameras = json.loads((study / "camera-views.json").read_text(encoding="utf-8"))["views"]
    p["material_review"] = report
    evidence = {k: old[k] for k in ("source_roof", "terrain", "features", "paving", "roof_patches") if k in old}
    evidence.update({"material_review": report, "source_geometry": {"study": str(study.resolve()), "archive_sha256": digest(study / "sample-blocks.npz"), "occupied_coordinates_unchanged": True, "block_properties_unchanged": True}, "detail_status": old.get("detail_status", p.get("detail_status", "Individual facade review remains required"))})
    m = finish_study(c, p, output, cameras, evidence)
    if m["block_count"] != len(xyz):
        raise ValueError("Material revision changed block occupancy")
    with np.load(output / "sample-blocks.npz", allow_pickle=False) as revised:
        if not np.array_equal(revised["coords"], xyz):
            raise ValueError("Material revision moved occupied coordinates")
        revised_roles = [str(v) for v in revised["role_names"]]
        if not np.array_equal(
            revised["role_ids"],
            np.array([revised_roles.index(name) for name in names])[roles],
        ):
            raise ValueError("Material revision changed semantic roles")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    reports = []
    for i, component in enumerate(config["components"]):
        source = ROOT / component["study"]
        output = args.output / f"{i:02d}-{source.name}"
        print(f"Materials {i + 1}/{len(config['components'])}: {component['name']}", flush=True)
        if (output / "manifest.json").exists():
            existing = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            if existing["material_review"]["revision"] != registry["revision"]:
                raise ValueError(f"Different registry revision in {output}; choose a fresh output")
            report = existing["material_review"]
        else:
            report = revise(source, output, args.registry)
        reports.append({"name": component["name"], "source": str(source), "output": str(output), **report})
        component["study"] = output.resolve().relative_to(ROOT).as_posix()
        component["material_status"] = report["status"]
        gc.collect()
    config["revision"] += "-reviewed-materials-20260907"
    config["material_assignment_registry"] = str(args.registry)
    write_json(args.output / "campus-config.json", config)
    write_json(args.output / "material-change-report.json", {"registry": str(args.registry), "registry_sha256": digest(args.registry), "buildings_reviewed": len(reports), "changed_blocks": sum(r["changed_blocks"] for r in reports), "components": reports, "visual_review": "Native combined-campus review required; material changes do not complete rough geometry."})


if __name__ == "__main__":
    main()
