"""Integrate reviewed study amendments without rebuilding accepted campus sitework.

Only exact changed study cells are transferred. Unchanged source cells retain the
accepted campus value, including earlier landscape overrides. A three-way conflict
stops the operation instead of silently overwriting an environment repair.
"""

import argparse
from collections import Counter
from copy import deepcopy
import gc
import json
from pathlib import Path
import shutil

import numpy as np

from assemble_hill_campus_studies import (
    audit_component_ownership, merge_tile_world, prepare_component,
    verify_merged_world,
)
from build_hill_chapel_sample import ROLES, write_world
from campus_export_parity import compare_world, read_archive
from campus_materials import audit_role_materials
from campus_study_io import digest, material_roles, write_json
from prepare_hill_campus_revision import replace_individual_studies
from refine_hill_campus_environment import load_canvas

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def component_delta(before, after):
    """Enumerate complete state/role changes and reject omitted authored sitework."""
    for field in ("x_min", "z_min", "shape", "scale", "offset"):
        if before.meta[field] != after.meta[field]:
            raise ValueError(f"Amendment must retain source canvas/frame: {field}")
    lookup = {json.dumps(p, sort_keys=True): i for i, p in enumerate(before.meta["palette"])}
    mapping = np.asarray([lookup.get(json.dumps(p, sort_keys=True), len(lookup) + i)
                          for i, p in enumerate(after.meta["palette"])], np.uint32)
    owned = before.mask | after.mask
    changes = []
    for iy in range(384):
        difference = ((before.data[iy] != mapping[after.data[iy]])
                      | (before.roles[iy] != after.roles[iy]))
        if np.any(difference & ~owned):
            z, x = np.argwhere(difference & ~owned)[0]
            raise ValueError(f"Authored change omitted by ownership: "
                             f"{after.meta['study']} {x + after.meta['x_min']},"
                             f"{iy - 64},{z + after.meta['z_min']}")
        for iz, ix in np.argwhere(difference):
            changes.append({
                "xyz": [int(ix + after.meta["x_min"]), iy - 64,
                        int(iz + after.meta["z_min"])],
                "study": after.meta["study"],
                "before": before.meta["palette"][int(before.data[iy, iz, ix])],
                "before_role": ROLES[int(before.roles[iy, iz, ix])],
                "after": after.meta["palette"][int(after.data[iy, iz, ix])],
                "after_role": ROLES[int(after.roles[iy, iz, ix])],
            })
    return changes


def apply_delta(canvas, change, site_resolutions=None):
    x, y, z = change["xyz"]
    iz, ix = z - canvas.z_min, x - canvas.x_min
    actual = canvas.palette[canvas.get(x, y, z)]
    role = ROLES[int(canvas.roles[y + 64, iz, ix])]
    old = actual == change["before"] and role == change["before_role"]
    new = actual == change["after"] and role == change["after_role"]
    if not old and not new:
        resolution = (site_resolutions or {}).get(tuple(change["xyz"]))
        site_roles = {"air", "terrain", "pavement", "vegetation"}
        if (resolution is None or resolution["campus"] != actual or resolution["campus_role"] != role
                or resolution["study"] != change["study"] or resolution["after"] != change["after"]
                or resolution["after_role"] != change["after_role"]
                or role not in site_roles or change["before_role"] not in site_roles):
            raise ValueError({"three_way_conflict": change, "campus": actual, "campus_role": role})
    if new:
        return None
    state = change["after"]
    canvas.set(x, y, z, state["Name"], change["after_role"], state.get("Properties"))
    return {**change, "before": actual, "before_role": role}


def amend(source, studies, output, config, site_transfer=None):
    source, output, config = source.resolve(), output.resolve(), config.resolve()
    if output.exists() or config.exists():
        raise FileExistsError("Choose fresh campus and configuration paths")
    base = read(source / "manifest.json")
    source_hash = digest(source / "manifest.json")
    audit, review = read(source / "artifact-audit.json"), read(source / "native-review.json")
    if (not audit.get("passed") or audit.get("manifest_sha256") != source_hash
            or not review.get("status", "").startswith("accepted")
            or review.get("manifest_sha256") != source_hash):
        raise ValueError("Source must be the accepted and exactly audited campus")
    profile = replace_individual_studies(read(source / "profile.json"), studies, output.name)
    components, deltas, replacements = [], [], []
    cache = ROOT / "runtime/campus-reconstruction/component-cache"
    for previous, spec in zip(base["components"], profile["components"]):
        old_study, new_study = Path(previous["study"]), ROOT / spec["study"]
        if digest(old_study / "sample-blocks.npz") != previous["archive_sha256"]:
            raise ValueError(f"Source study changed: {old_study}")
        after = prepare_component(new_study, cache, 2, -25, spec.get("margin_m", 2))
        components.append(after)
        if after.meta["archive_sha256"] == previous["archive_sha256"]:
            continue
        before = prepare_component(old_study, cache, 2, -25, previous["margin_m"])
        changes = component_delta(before, after)
        deltas.extend(changes)
        replacements.append({"before": previous, "after": after.meta, "changed_study_cells": len(changes)})
    resolutions = {}
    if site_transfer:
        transfer = read(site_transfer)
        if transfer["source_manifest_sha256"] != source_hash:
            raise ValueError("Site transfer targets a different accepted campus")
        for record in transfer["inputs"]:
            if digest(ROOT / record["path"]) != record["sha256"]:
                raise ValueError(f"Site transfer input changed: {record['path']}")
        resolutions = {tuple(r["xyz"]): r for r in transfer["resolutions"]}
        if len(resolutions) != len(transfer["resolutions"]):
            raise ValueError("Duplicate site-transfer resolution")
        sources = {c.meta["study"]: c for c in components}
        for change in transfer["supplemental_cells"]:
            c = sources[change["study"]]
            x,y,z = change["xyz"]
            ix,iz = x-c.meta["x_min"],z-c.meta["z_min"]
            state = c.meta["palette"][int(c.data[y+64,iz,ix])]
            role = ROLES[int(c.roles[y+64,iz,ix])]
            if (state != change["after"] or role != change["after_role"]
                    or change["before_role"] not in {"air","terrain","pavement","vegetation"}
                    or role not in {"air","terrain","pavement","vegetation"}
                    or not c.mask[iz,ix]):
                raise ValueError(f"Supplemental transfer is not exact reviewed sitework: {change}")
            deltas.append(change)
    xmin, zmin, xmax, zmax = base["bounds_xz_blocks"]
    ownership = audit_component_ownership(components, xmin, zmin, (zmax-zmin, xmax-xmin))
    by_tile, coordinates = {}, set()
    for change in deltas:
        x, y, z = change["xyz"]
        if tuple(change["xyz"]) in coordinates:
            raise ValueError("Multiple amendments change the same world cell")
        coordinates.add(tuple(change["xyz"]))
        tx, tz = xmin + (x-xmin)//256*256, zmin + (z-zmin)//256*256
        by_tile.setdefault(f"x{tx}_z{tz}", []).append(change)
    # Conflict preflight happens before writing any new campus output.
    for name, changes in by_tile.items():
        tx, tz = map(int, name[1:].split("_z"))
        c = load_canvas(read_archive(source / "tiles" / name / "sample-blocks.npz"),
                        (tx, tz, min(tx+256, xmax), min(tz+256, zmax)))
        for change in changes:
            apply_delta(c, change, resolutions)
        del c
        gc.collect()
    output.mkdir(parents=True)
    profile["building_amendment"] = {"source": str(source), "manifest_sha256": source_hash,
                                     "method": "exact_reviewed_study_delta"}
    write_json(config, profile)
    write_json(output / "profile.json", profile)
    write_json(output / "ownership-audit.json", ownership)
    if site_transfer:
        shutil.copy2(site_transfer, output / "site-transfer-plan.json")
    for name in ("landscape-profile.json", "quad-start.json", "play-start.json", "camera-views.json"):
        if (source / name).exists():
            shutil.copy2(source / name, output / name)
    totals, registered, tiles, journal = Counter(), {}, [], []
    for spec in base["tiles"]:
        old_tile, tile = source / spec["path"], output / spec["path"]
        for filename, field in (("sample-blocks.npz", "archive_sha256"), ("audit.json", "audit_sha256")):
            if digest(old_tile / filename) != spec[field]:
                raise ValueError(f"Source tile changed: {old_tile / filename}")
        changes = by_tile.get(tile.name, [])
        if not changes:
            shutil.copytree(old_tile, tile)
            report = read(tile / "audit.json")
        else:
            print(f"Applying {len(changes)} reviewed study cells in {tile.name}", flush=True)
            tx, tz = map(int, tile.name[1:].split("_z"))
            c = load_canvas(read_archive(old_tile / "sample-blocks.npz"),
                            (tx, tz, min(tx+256, xmax), min(tz+256, zmax)))
            applied = [record for change in changes if (record := apply_delta(c, change, resolutions))]
            journal.extend(applied)
            roles = material_roles(c)
            if c.clipped or audit_role_materials(roles):
                raise ValueError("Invalid construction palette or clipped amendment")
            tile.mkdir(parents=True)
            c.export(tile / "sample-blocks.npz")
            write_world(c, tile / "world", profile["name"], (137,85,24), old_tile / "world/level.dat")
            del c
            gc.collect()
            archive = read_archive(tile / "sample-blocks.npz")
            parity, errors, _, _ = compare_world(archive, tile / "world")
            if errors:
                raise ValueError(errors)
            report = read(old_tile / "audit.json")
            report.update(block_count=len(archive["coords"]), parity=parity, material_roles=roles,
                          study_amendment={"changed_cells": len(applied), "source_archive_sha256": spec["archive_sha256"]})
            write_json(tile / "audit.json", report)
            del archive
            gc.collect()
        chunks = merge_tile_world(tile / "world", output / "world", registered)
        totals.update(blocks=report["block_count"], chunks=chunks, tiles=1)
        tiles.append({"path": spec["path"], "blocks": report["block_count"], "chunks": chunks,
                      "archive_sha256": digest(tile / "sample-blocks.npz"), "audit_sha256": digest(tile / "audit.json")})
    verify_merged_world(output / "world", registered)
    write_json(output / "study-mutations.json", {"format": "hill-study-mutations-v1", "cells": journal,
                                                "source_manifest_sha256": source_hash})
    result = deepcopy(base)
    result.update(tiles=tiles, components=[c.meta for c in components], totals=dict(totals), visual_review="pending",
                  profile={"path": str(output / "profile.json"), "sha256": digest(output / "profile.json")},
                  ownership_audit={"path": "ownership-audit.json", "sha256": digest(output / "ownership-audit.json")})
    if result.get("landscape"):
        result["landscape"]["path"] = str(output / "landscape-profile.json")
    if result.get("environment_revision"):
        result["inherited_environment_revision"] = result.pop("environment_revision")
    result.pop("tile_reuse", None)
    result["study_revision"] = {"base": str(source), "base_manifest_sha256": source_hash,
                                "replacements": replacements, "changed_cells": len(journal),
                                "changed_tiles": sorted(by_tile), "journal_sha256": digest(output / "study-mutations.json"),
                                "scope": "Only exact reviewed study state/role amendments; every other accepted campus cell retained."}
    if site_transfer:
        result["study_revision"]["site_transfer_plan"] = {"path":"site-transfer-plan.json", "sha256":digest(output / "site-transfer-plan.json")}
    write_json(output / "manifest.json", result)
    print(json.dumps({"output": str(output), "replacements": len(replacements), "changed_cells": len(journal), **totals}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--study", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--site-transfer-plan", type=Path)
    args = parser.parse_args()
    amend(args.source, args.study, args.output, args.config, args.site_transfer_plan)
