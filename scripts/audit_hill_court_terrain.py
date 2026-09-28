"""Inspect exposed grass and unsupported paving in the Athey-Dining court."""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from campus_export_parity import read_archive
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
CAP_XYZ = (74, 88, 119)
HORIZONTAL = ((-1, 0, 0), (1, 0, 0), (0, 0, -1), (0, 0, 1))


def validate_structural_cap(record, actual, source, predecessor):
    """Only the documented one-cell gallery floor may use four-sided backing."""
    from refine_hill_library_chapel import occupied_shapes
    errors = []
    q = tuple(record["xyz"])
    expected = {"state": {"Name": "minecraft:smooth_stone"}, "role": "pavement"}
    if q != CAP_XYZ or {"state": record["state"], "role": record["role"]} != expected:
        errors.append("Proof is not the exact documented west-gallery cap")
    if source.get(q) != expected or actual.get(q) != expected:
        errors.append("Actual/source cap state or role differs")
    if predecessor.get(q) != {"state": {"Name": "minecraft:air"}, "role": "air"}:
        errors.append("Predecessor cap cell was not air")
    contacts = record["contacts"]
    wanted = {tuple(q[i] + d[i] for i in range(3)) for d in HORIZONTAL}
    if len(contacts) != 4 or {tuple(c["xyz"]) for c in contacts} != wanted:
        errors.append("Proof must enumerate the four distinct horizontal neighbors")
    for contact in contacts:
        cq = tuple(contact["xyz"])
        specified = {"state": contact["state"], "role": contact["role"]}
        if source.get(cq) != specified or actual.get(cq) != specified:
            errors.append(f"Source/actual contact state or role differs at {cq}")
        if occupied_shapes(contact["state"]) != ((0, 0, 0, 16, 16, 16),):
            errors.append(f"Contact is not a full cube at {cq}")
    return errors


def load_structural_cap_proof(path):
    proof = json.loads(path.read_text(encoding="utf-8"))
    if proof.get("format") != "hill-structural-floor-cap-proof-v1":
        raise ValueError("Unrecognized structural cap proof")
    record = proof["cell"]
    wanted = {tuple(record["xyz"]), *(tuple(c["xyz"]) for c in record["contacts"])}
    values = []
    for label in ("source", "predecessor"):
        archive = ROOT / proof[label]["archive"]
        if digest(archive) != proof[label]["archive_sha256"]:
            raise ValueError(f"Structural cap {label} archive hash differs")
        a = read_archive(archive)
        found = {q: {"state": {"Name": "minecraft:air"}, "role": "air"} for q in wanted}
        xyz = a["coords"]
        selection = ((xyz[:, 0] >= 73) & (xyz[:, 0] <= 75)
                     & (xyz[:, 1] == 88) & (xyz[:, 2] >= 118) & (xyz[:, 2] <= 120))
        for row in np.flatnonzero(selection):
            q = tuple(map(int, xyz[row]))
            if q not in wanted:
                continue
            name, props = a["palette_keys"][a["state_ids"][row]]
            found[q] = {"state": {"Name": name, **({"Properties": dict(props)} if props else {})},
                        "role": a["role_names"][a["role_ids"][row]]}
        values.append(found)
    if validate_structural_cap(record, values[0], values[0], values[1]):
        raise ValueError("Structural cap proof does not match frozen source/predecessor")
    return proof, wanted, values


def audit(directory, output, structural_cap_proof=None):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "tiles" in manifest:
        paths = [directory / t["path"] / "sample-blocks.npz" for t in manifest["tiles"]
                 if -64 <= int(Path(t["path"]).name[1:].split("_z")[0]) <= 192
                 and -64 <= int(Path(t["path"]).name[1:].split("_z")[1]) <= 192]
    else:
        paths = [directory / "sample-blocks.npz"]
    regions = {
        "paved_court": [21.8,21.0,52.2,35.7],
        "west_gallery": [16.1,16.7,21.8,35.8],
        "east_gallery": [52.0,16.7,57.0,36.5],
        "north_raised_bed_and_stairs": [21.8,18.3,52.2,21.0],
        "athey_recessed_arcade": [21.8,14.5,52.2,18.3],
    }
    findings = {n: {"exposed_grass": [], "exposed_terrain_above_court": [],
                    "unsupported_pavement": []} for n in regions}
    proof, wanted, proof_values = load_structural_cap_proof(structural_cap_proof) if structural_cap_proof else (None, set(), None)
    observed = {q: {"state": {"Name": "minecraft:air"}, "role": "air"} for q in wanted}
    angle = math.radians(18.25)
    ca, sa = math.cos(angle), math.sin(angle)
    for path in paths:
        a = read_archive(path)
        if "tiles" in manifest:
            expected = next(t["archive_sha256"] for t in manifest["tiles"]
                            if directory / t["path"] / "sample-blocks.npz" == path)
            if digest(path) != expected:
                raise ValueError(f"Campus tile differs from manifest: {path}")
        q, states, role_ids = a["coords"], a["state_ids"], a["role_ids"]
        if wanted:
            selection = ((q[:, 0] >= 73) & (q[:, 0] <= 75) & (q[:, 1] == 88)
                         & (q[:, 2] >= 118) & (q[:, 2] <= 120))
            for row in np.flatnonzero(selection):
                pos = tuple(map(int, q[row]))
                if pos not in wanted:
                    continue
                name, props = a["palette_keys"][states[row]]
                observed[pos] = {"state": {"Name": name, **({"Properties": dict(props)} if props else {})},
                                 "role": a["role_names"][role_ids[row]]}
        # A compact dense window permits exact vertical neighbor lookup.
        low, high = q.min(axis=0), q.max(axis=0)+1
        w, d = int(high[0]-low[0]), int(high[2]-low[2])
        grid = np.zeros((384,d,w), np.uint16)
        grid[q[:,1]+64,q[:,2]-low[2],q[:,0]-low[0]] = states
        x, z = (q[:,0]+.5)/2-22, (q[:,2]+.5)/2-37
        u, v = x*ca+z*sa, -x*sa+z*ca
        names = np.asarray([k[0] for k in a["palette_keys"]])
        grass = names[states] == "minecraft:grass_block"
        terrain = role_ids == a["role_names"].index("terrain")
        pavement = role_ids == a["role_names"].index("pavement")
        above_air = grid[np.minimum(q[:,1]+65,383),q[:,2]-low[2],q[:,0]-low[0]] == 0
        below_air = grid[np.maximum(q[:,1]+63,0),q[:,2]-low[2],q[:,0]-low[0]] == 0
        for name,(u0,v0,u1,v1) in regions.items():
            inside = (u>=u0)&(u<u1)&(v>=v0)&(v<v1)
            for label,mask in (("exposed_grass",grass&above_air),
                               ("exposed_terrain_above_court",terrain&above_air&(q[:,1]>=89)),
                               ("unsupported_pavement",pavement&below_air&(q[:,1]>=88))):
                findings[name][label].extend(q[inside&mask].astype(int).tolist())
        del a,q,grid
    cap_report = None
    if proof:
        errors = validate_structural_cap(proof["cell"], observed, *proof_values)
        waived = []
        if not errors:
            for name, finding in findings.items():
                if list(CAP_XYZ) in finding["unsupported_pavement"]:
                    finding["unsupported_pavement"].remove(list(CAP_XYZ))
                    waived.append({"region": name, "xyz": list(CAP_XYZ)})
        cap_report = {"path": str(structural_cap_proof), "sha256": digest(structural_cap_proof),
                      "source": proof["source"], "predecessor": proof["predecessor"],
                      "passed": not errors, "errors": errors, "four_full_cube_side_contacts": not errors,
                      "exact_structurally_supported_cap": waived,
                      "scope": "Only [74,88,119], with exact source/target state and role and all four full-cube neighbor contacts. No other pavement exception."}
    passed = all(not r["exposed_grass"] and not r["unsupported_pavement"] for r in findings.values()) and (cap_report is None or cap_report["passed"])
    result = {"format":"hill-court-terrain-audit-v1","passed":passed,
              "manifest_sha256":digest(manifest_path),"regions_uv_m":regions,"findings":findings,
              "scope":"Exposed grass checked at every height; pavement backing checked at/above the court paving level. No exposed grass or floating pavement across the court, galleries or north bed/stairs. Terrain above court is reported separately because the authentic raised north terrace has substrate; architectural clearance has separate occupied-shape route checks."}
    if cap_report:
        result["structural_cap_proof"] = cap_report
    write_json(output,result)
    print(json.dumps({"passed":passed,"regions":{k:{n:len(c) for n,c in v.items()} for k,v in findings.items()}}),flush=True)
    return result


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--structural-cap-proof", type=Path)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a fresh report path")
    result=audit(args.directory,args.output,args.structural_cap_proof)
    raise SystemExit(0 if result["passed"] else 1)
