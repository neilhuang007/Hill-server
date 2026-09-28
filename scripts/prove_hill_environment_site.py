"""Explain final study differences with exact inherited and environment evidence.

This does not waive component masks. Each reported cell must either match an
untouched prior retained-site signature, or an exact authorized environment
journal mutation. Architectural columns are never eligible.
"""

import argparse
from collections import Counter, defaultdict
import gc
import json
from pathlib import Path
import shutil

import numpy as np
from shapely.geometry import Point, Polygon

from assemble_hill_campus_studies import prepare_component
from build_hill_chapel_sample import ROLES
from campus_export_parity import read_archive
from campus_study_io import digest, write_json
from refine_hill_campus_environment import load_canvas, SITE_ROLES

ROOT = Path(__file__).resolve().parents[1]
SITE_NAMES = {"air", "terrain", "pavement", "vegetation"}
DETAIL_NAMES = {"furniture", "lighting", "fixture"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def state_key(state):
    if isinstance(state, (list, tuple)):
        return state[0], tuple(sorted(tuple(p) for p in state[1]))
    return state["Name"], tuple(sorted(state.get("Properties", {}).items()))


def signature(cell):
    # Keep the exact raw-report representation consumed by the existing audit.
    return json.dumps(cell, sort_keys=True)


def require_complete_report(report, manifest_hash, label):
    if (report.get("format") != "hill-integrated-study-audit-v1"
            or report.get("manifest_sha256") != manifest_hash):
        raise ValueError(f"{label} is not bound to the exact manifest")
    cells = report.get("examples", [])
    if len(cells) != sum(report.get("different_cells", {}).values()):
        raise ValueError(f"{label} has truncated differences")
    if len({(c["study"], tuple(c["xyz"])) for c in cells}) != len(cells):
        raise ValueError(f"{label} has duplicate difference cells")
    if any(not camera.get("air") for camera in report.get("camera_eyes", [])):
        raise ValueError(f"{label} contains an obstructed camera; a site proof cannot excuse it")
    return cells


def classify_cell(cell, before_state, before_role, after_state, after_role,
                  source_state, source_role, original_column_roles,
                  final_column_roles, journal, authorized_xz, inherited,
                  registered_fixture_xyz=frozenset(), final_fixture_xyz=frozenset()):
    """Reject every difference not proved by exact cell-specific evidence."""
    xyz = tuple(cell["xyz"])
    if (source_role not in SITE_NAMES or before_role not in SITE_NAMES
            or after_role not in SITE_NAMES | DETAIL_NAMES
            or not set(original_column_roles) <= SITE_NAMES
            or not set(final_column_roles) <= SITE_NAMES | DETAIL_NAMES):
        raise ValueError(f"Architectural cell or column cannot receive site proof: {cell}")
    if ((set(final_column_roles) & DETAIL_NAMES and not final_fixture_xyz)
            or not set(final_fixture_xyz) <= set(registered_fixture_xyz)):
        raise ValueError(f"Unexplained final fixture in site column: {cell}")
    if state_key(source_state) != state_key(cell["expected"]):
        raise ValueError(f"Reported expected state differs from unchanged study source: {cell}")
    if state_key(after_state) != state_key(cell["actual"]):
        raise ValueError(f"Reported actual state differs from final campus: {cell}")
    mutation = journal.get(xyz)
    if mutation is not None:
        if (xyz[0], xyz[2]) not in authorized_xz:
            raise ValueError(f"Journal cell lacks an explicit authorized site column: {cell}")
        if (mutation["before_role"] not in SITE_NAMES or mutation["after_role"] not in SITE_NAMES | DETAIL_NAMES
                or mutation["before_role"] != before_role or mutation["after_role"] != after_role
                or state_key(mutation["before"]) != state_key(before_state)
                or state_key(mutation["after"]) != state_key(after_state)):
            raise ValueError(f"Exact environment journal state/role mismatch: {cell}")
        if after_role in DETAIL_NAMES and xyz not in registered_fixture_xyz:
            raise ValueError(f"New fixture lacks a registered source footprint: {cell}")
        return "environment_journal"
    if signature(cell) not in inherited:
        raise ValueError(f"Untouched difference lacks an exact prior proof signature: {cell}")
    if state_key(before_state) != state_key(after_state) or before_role != after_role:
        raise ValueError(f"Inherited difference changed without a journal mutation: {cell}")
    return "inherited_untouched"


def prove(directory, report_path, base_proof_path, output):
    directory, report_path, base_proof_path, output = [p.resolve() for p in
                                                      (directory, report_path, base_proof_path, output)]
    raw_copy = output.with_name(output.stem + "-raw-report.json")
    if output.exists() or raw_copy.exists():
        raise FileExistsError("Choose a fresh proof path; previous proof/raw reports are immutable")
    manifest_path = directory / "manifest.json"
    manifest, raw = read(manifest_path), read(report_path)
    final_hash = digest(manifest_path)
    cells = require_complete_report(raw, final_hash, "Final raw study comparison")
    environment = manifest["environment_revision"]
    base = Path(environment["base"]).resolve()
    base_manifest_path = base / "manifest.json"
    base_manifest, base_hash = read(base_manifest_path), digest(base_manifest_path)
    if base_hash != environment["base_manifest_sha256"]:
        raise ValueError("Environment base manifest changed")
    if manifest["components"] != base_manifest["components"]:
        raise ValueError("Environment revision changed component specifications")
    if manifest["bounds_xz_blocks"] != base_manifest["bounds_xz_blocks"]:
        raise ValueError("Environment revision changed campus bounds")

    preservation_path = directory / "environment-preservation-audit.json"
    preservation = read(preservation_path)
    if (preservation.get("format") != "hill-environment-preservation-audit-v1"
            or not preservation.get("passed") or preservation.get("manifest_sha256") != final_hash
            or preservation.get("totals", {}).get("architecture_changes") != 0
            or preservation.get("errors")):
        raise ValueError("Final environment preservation audit is absent, failed or stale")
    plan_path, journal_path = directory / "environment-plan.json", directory / "environment-mutations.json"
    if digest(plan_path) != environment["plan_sha256"] or digest(journal_path) != environment["mutations_sha256"]:
        raise ValueError("Environment plan or journal changed")
    plan, journal_record = read(plan_path), read(journal_path)
    if (plan["source_manifest_sha256"] != base_hash
            or journal_record["source_manifest_sha256"] != base_hash
            or journal_record["plan_sha256"] != digest(plan_path)):
        raise ValueError("Environment plan/journal provenance differs from the base")
    mutations = journal_record["cells"]
    journal = {tuple(c["xyz"]): c for c in mutations}
    if len(journal) != len(mutations):
        raise ValueError("Environment journal has duplicate cells")
    if len(journal) != preservation["totals"]["changed_cells"]:
        raise ValueError("Environment journal count differs from preservation audit")
    authorized_records = plan.get("authorized_component_site_overrides", [])
    authorized = {tuple(c["xz"]) for c in authorized_records}
    if len(authorized) != len(authorized_records):
        raise ValueError("Plan has duplicate authorized component-site columns")

    base_proof = read(base_proof_path)
    if (base_proof.get("format") != "hill-retained-site-proof-v1" or not base_proof.get("passed")
            or base_proof.get("manifest_sha256") != base_hash):
        raise ValueError("Prior retained-site proof is not bound to the environment base")
    inherited = {signature(c) for c in base_proof["site_cells"]}
    if len(inherited) != base_proof["count"] or len(base_proof["site_cells"]) != base_proof["count"]:
        raise ValueError("Prior retained-site proof count/uniqueness is invalid")
    base_audit_path = base / "integrated-study-audit.json"
    base_audit = read(base_audit_path)
    base_cells = require_complete_report(base_audit, base_hash, "Prior full study comparison")
    if not base_audit.get("passed") or any(base_audit.get("unexplained_different_cells", {}).values()):
        raise ValueError("Prior full study comparison did not pass")
    prior_binding = base_audit.get("retained_site_proof")
    if (not prior_binding or digest(base_proof_path) != prior_binding["sha256"]
            or Path(prior_binding["path"]).resolve() != base_proof_path
            or prior_binding["applied_cells"] != len(inherited)):
        raise ValueError("Prior full comparison did not use the provided retained-site proof")
    if inherited != {signature(c) for c in base_cells}:
        raise ValueError("Prior retained-site signatures do not exactly explain the prior comparison")
    for study, count in raw["compared_cells_including_air"].items():
        if base_audit["compared_cells_including_air"].get(study) != count:
            raise ValueError(f"Prior full study comparison did not cover the same complete study: {study}")

    inputs = {}
    def bind(path, expected=None):
        path = Path(path)
        path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
        actual = digest(path)
        if expected is not None and actual != expected:
            raise ValueError(f"Proof input hash changed: {path}")
        inputs[str(path)] = {"path": str(path), "sha256": actual}
        return path

    for record in [*base_proof["inputs"], *plan["inputs"]]:
        bind(record["path"], record["sha256"])
    for path in (manifest_path, base_manifest_path, preservation_path, plan_path,
                 journal_path, base_proof_path, base_audit_path, Path(__file__)):
        bind(path)
    # Preserve the failed raw evidence under an immutable fresh filename. Do
    # not bind the audit's conventional output path, which the passing rerun
    # intentionally replaces.
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, raw_copy)
    bind(raw_copy, digest(report_path))
    for campus, specs in ((base, base_manifest["tiles"]), (directory, manifest["tiles"])):
        for spec in specs:
            bind(campus / spec["path"] / "sample-blocks.npz", spec["archive_sha256"])
            bind(campus / spec["path"] / "audit.json", spec["audit_sha256"])

    # Source detail registrations are hash-bound controls, not polygons added
    # ad hoc to the proof. Every actual fixture cell must occur in the exact
    # journal, in its registered footprint and in an explicit override column.
    registered_fixtures = set()
    plan_inputs = {(ROOT / r["path"]).resolve():r["sha256"] for r in plan["inputs"]}
    for detail in plan.get("registered_source_details", []):
        source_path = (ROOT / detail["source_path"]).resolve()
        if source_path not in plan_inputs:
            raise ValueError("Registered source detail is not a bound plan input")
        bind(source_path,plan_inputs[source_path])
        records = read(source_path)[detail["source_collection"]]
        matches = [r for r in records if r["id"] == detail["source_record_id"]]
        if len(matches) != 1:
            raise ValueError("Registered detail source identity is missing or ambiguous")
        record=matches[0]
        polygon = Polygon(record.get("world_block_polygon") or record["build_footprint_world_block_polygon"])
        if record.get("source_world_block_polygon") and not Polygon(record["source_world_block_polygon"]).covers(polygon):
            raise ValueError("Fixture construction footprint exceeds its registered source envelope")
        if not polygon.is_valid or polygon.is_empty:
            raise ValueError("Registered fixture footprint is invalid")
        for position in detail["authored_cells_xyz"]:
            xyz = tuple(position); mutation = journal.get(xyz)
            if (xyz in registered_fixtures or mutation is None
                    or mutation["feature"] != detail["id"]
                    or mutation["after_role"] not in DETAIL_NAMES
                    or not polygon.covers(Point(xyz[0]+.5,xyz[2]+.5))):
                raise ValueError(f"Fixture is outside its exact registered source/journal: {position}")
            registered_fixtures.add(xyz)

    component_specs = {Path(c["study"]).name: c for c in manifest["components"]}
    if len(component_specs) != len(manifest["components"]):
        raise ValueError("Ambiguous component labels cannot support exact study proof")
    loaded = {}
    for name in raw["compared_cells_including_air"]:
        spec = component_specs[name]
        study = Path(spec["study"])
        bind(study / "sample-blocks.npz", spec["archive_sha256"])
        component = prepare_component(study, ROOT / "runtime/campus-reconstruction/component-cache", 2, -25, spec["margin_m"])
        if component.meta != spec:
            raise ValueError(f"Source component identity changed: {name}")
        loaded[name] = component

    xmin,zmin,xmax,zmax = manifest["bounds_xz_blocks"]
    grouped = defaultdict(list)
    for cell in cells:
        x,y,z = cell["xyz"]
        if not (xmin<=x<xmax and zmin<=z<zmax and -64<=y<320):
            raise ValueError(f"Difference lies outside the campus: {cell}")
        grouped[xmin+(x-xmin)//256*256,zmin+(z-zmin)//256*256].append(cell)
    counts, by_study, explanation = Counter(), defaultdict(Counter), []
    for (tx,tz), tile_cells in grouped.items():
        relative = Path("tiles") / f"x{tx}_z{tz}" / "sample-blocks.npz"
        bounds = tx,tz,min(tx+256,xmax),min(tz+256,zmax)
        before = load_canvas(read_archive(base / relative), bounds)
        after = load_canvas(read_archive(directory / relative), bounds)
        for cell in tile_cells:
            name = cell["study"]; x,y,z = cell["xyz"]
            source = loaded[name]
            sx,sz = x-source.meta["x_min"],z-source.meta["z_min"]
            if not (0<=sx<source.mask.shape[1] and 0<=sz<source.mask.shape[0]
                    and source.mask[sz,sx] and y>=source.minimum[sz,sx]):
                raise ValueError(f"Raw difference is outside the complete source ownership: {cell}")
            iz,ix = z-tz,x-tx
            original_roles = {ROLES[int(r)] for r in np.unique(before.roles[:,iz,ix])}
            final_roles = {ROLES[int(r)] for r in np.unique(after.roles[:,iz,ix])}
            final_fixture_xyz = set()
            for iy in np.flatnonzero(np.isin(after.roles[:,iz,ix],[ROLES.index(r) for r in DETAIL_NAMES])):
                xyz = (x,int(iy)-64,z); mutation = journal.get(xyz)
                if (xyz not in registered_fixtures or (x,z) not in authorized or mutation is None
                        or state_key(before.palette[before.get(*xyz)]) != state_key(mutation["before"])
                        or ROLES[int(before.roles[iy,iz,ix])] != mutation["before_role"]
                        or state_key(after.palette[after.get(*xyz)]) != state_key(mutation["after"])
                        or ROLES[int(after.roles[iy,iz,ix])] != mutation["after_role"]):
                    raise ValueError(f"Unexplained final fixture in source-owned column: {xyz}")
                final_fixture_xyz.add(xyz)
            source_roles = {ROLES[int(r)] for r in np.unique(source.roles[:,sz,sx])}
            if not source_roles <= SITE_NAMES:
                raise ValueError(f"Source architectural column cannot receive site proof: {cell}")
            classification = classify_cell(
                cell, before.palette[before.get(x,y,z)], ROLES[int(before.roles[y+64,iz,ix])],
                after.palette[after.get(x,y,z)], ROLES[int(after.roles[y+64,iz,ix])],
                source.meta["palette"][int(source.data[y+64,sz,sx])], ROLES[int(source.roles[y+64,sz,sx])],
                original_roles, final_roles, journal, authorized, inherited,registered_fixtures,final_fixture_xyz)
            counts[classification] += 1; by_study[name][classification] += 1
            explanation.append({"study":name,"xyz":[x,y,z],"classification":classification,
                                **({"feature":journal[x,y,z]["feature"]} if classification=="environment_journal" else {})})
        del before, after
        gc.collect()
    proof = {"format":"hill-retained-site-proof-v1","passed":True,
             "manifest_sha256":final_hash,"count":len(cells),"inputs":list(inputs.values()),"site_cells":cells,
             "environment_classification":dict(counts),"classification_by_study":{k:dict(v) for k,v in by_study.items()},
             "cell_explanations":explanation,"preserved_raw_report":{"path":str(raw_copy),"sha256":digest(raw_copy)},
             "registered_new_fixture_cells":len(registered_fixtures),
             "scope":"Every complete final source-study difference is either an exact untouched prior retained-site signature, or an exact before/after state-and-role environment journal cell in an explicitly authorized component-site column. Source and original-campus columns contain site roles only. Final furniture/lighting is permitted only for exact journal cells within hash-bound registered source-detail footprints; every fixture cell in each affected column is checked. All component identities, both assemblies' tile archives/audits, prior proof inputs and environment inputs are hash-validated. No whole-mask exemptions, truncated reports or original architectural exceptions."}
    write_json(output, proof)
    print(json.dumps({"passed":True,"count":len(cells),"classification":dict(counts),"output":str(output),"preserved_raw_report":str(raw_copy)}),flush=True)
    return proof


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--base-proof",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a = p.parse_args(); prove(a.directory,a.report,a.base_proof,a.output)
