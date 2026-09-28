"""Apply an enumerated, source-bound site plan to a fresh combined-campus revision.

All accepted component archives and architectural states stay untouched. Every
changed cell is recorded; unaffected tile archives and worlds are copied exactly.
"""

import argparse
from collections import Counter
from copy import deepcopy
import gc
import json
import math
from pathlib import Path
import shutil

import numpy as np

import hybridize_voxelearth_roofer_world as anvil
from assemble_hill_campus_studies import merge_tile_world, verify_merged_world
from build_hill_chapel_sample import Canvas, ROLES, write_world
from campus_export_parity import read_archive, compare_world
from campus_materials import audit_role_materials
from campus_study_io import digest, material_roles, write_json

ROOT = Path(__file__).resolve().parents[1]
SITE_ROLES = {ROLES.index(n) for n in ("air", "terrain", "pavement", "vegetation")}


def load_canvas(archive, bounds):
    x0, z0, x1, z1 = bounds
    c = Canvas(x0, z0, x1 - x0, z1 - z0, 2)
    c.palette = [{"Name": name, **({"Properties": dict(props)} if props else {})}
                 for name, props in archive["palette_keys"]]
    c.palette_lookup = {json.dumps(p, sort_keys=True): i for i, p in enumerate(c.palette)}
    q = archive["coords"]
    ix, iy, iz = q[:, 0] - x0, q[:, 1] + 64, q[:, 2] - z0
    c.data[iy, iz, ix] = archive["state_ids"]
    mapping = np.array([ROLES.index(n) for n in archive["role_names"]], np.uint8)
    c.roles[iy, iz, ix] = mapping[archive["role_ids"]]
    c.ground_heights = np.full((z1 - z0, x1 - x0), -320, np.int16)
    site = np.isin(archive["role_ids"], [archive["role_names"].index(n) for n in ("terrain", "pavement")])
    np.maximum.at(c.ground_heights, (iz[site], ix[site]), q[site, 1])
    return c


def apply_surface(c, action):
    x, z, top = action["x"], action["z"], action["y"]
    ix, iz = x - c.x_min, z - c.z_min
    if not (0 <= ix < c.data.shape[2] and 0 <= iz < c.data.shape[1]):
        raise ValueError("Site action is outside its assigned tile")
    roles = c.roles[:, iz, ix]
    if any(int(r) not in SITE_ROLES for r in np.unique(roles)):
        raise ValueError(f"Site action intersects an architectural column: {x},{z}")
    old = int(c.ground_heights[iz, ix])
    if abs(top - old) > action.get("max_delta_blocks", 4):
        raise ValueError(f"Unreviewed grade change: {x},{z}: {old} -> {top}")
    if old == -320 or not -63 <= top < 315:
        raise ValueError("Site action lacks safe existing substrate")
    # Trees and shrubs are kept. A sourced path must route around their authored
    # position or explicitly relocate them in a separately reviewed revision.
    if np.any(roles[min(top, old)+65:max(top, old)+69] == ROLES.index("vegetation")):
        raise ValueError(f"Site action would intersect vegetation: {x},{z}")
    for y in range(min(old, top), max(old, top) + 1):
        if y < top:
            c.set(x, y, z, "dirt", "terrain")
        elif y > top:
            c.set(x, y, z, "air", "air")
    # This also makes raised slab surfaces physically supported.
    if c.get(x, top - 1, z) == 0:
        c.set(x, top - 1, z, "dirt", "terrain")
    state = action["state"]
    c.set(x, top, z, state["Name"], action.get("role", "pavement"), state.get("Properties"))
    c.ground_heights[iz, ix] = top


def apply_site_block(c, action, original_architecture):
    """Apply a source-planned planting/fixture cell with an exact precondition."""
    x, y, z = action["xyz"]
    ix, iz = x - c.x_min, z - c.z_min
    if not (0 <= ix < c.data.shape[2] and 0 <= iz < c.data.shape[1] and -64 <= y < 320):
        raise ValueError("Site block is outside its assigned tile")
    if original_architecture[iz, ix]:
        raise ValueError(f"Site block intersects an architectural column: {x},{z}")
    actual = c.palette[c.get(x, y, z)]
    role = ROLES[int(c.roles[y + 64, iz, ix])]
    if actual != action["before"] or role != action["before_role"]:
        raise ValueError({"site_block_conflict": action, "actual": actual, "role": role})
    if role not in {"air", "terrain", "pavement", "vegetation"}:
        raise ValueError("Site plan cannot alter an existing fixture or building")
    if action["role"] not in {"air", "terrain", "pavement", "vegetation", "lighting", "furniture", "fixture"}:
        raise ValueError("Unsupported site-block role")
    state = action["state"]
    c.set(x, y, z, state["Name"], action["role"], state.get("Properties"))


def refine(source, plan_path, output, config_path):
    source = source.resolve()
    if output.exists():
        raise FileExistsError("Choose a fresh campus revision; previous work is immutable")
    m = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    p = json.loads((source / "profile.json").read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    audit = json.loads((source / "artifact-audit.json").read_text(encoding="utf-8"))
    review = json.loads((source / "native-review.json").read_text(encoding="utf-8"))
    source_hash = digest(source / "manifest.json")
    if (not audit.get("passed") or audit.get("manifest_sha256") != source_hash
            or review.get("manifest_sha256") != source_hash
            or not review.get("status", "").startswith("accepted")):
        raise ValueError("Environment base must be an accepted, exactly audited assembly")
    if plan["source_manifest_sha256"] != source_hash:
        raise ValueError("Site plan targets a different source assembly")
    for record in plan["inputs"]:
        if digest(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"Site evidence changed: {record['path']}")
    for component in m["components"]:
        if digest(Path(component["study"]) / "sample-blocks.npz") != component["archive_sha256"]:
            raise ValueError(f"Building source changed: {component['study']}")
    xmin, zmin, xmax, zmax = m["bounds_xz_blocks"]
    tile_size = p.get("tile_size_blocks", 256)
    by_tile, block_tiles, seen = {}, {}, set()
    for action in plan["columns"]:
        x, z = action["x"], action["z"]
        if (x, z) in seen or not (xmin <= x < xmax and zmin <= z < zmax):
            raise ValueError("Duplicate or out-of-bounds site plan column")
        seen.add((x, z))
        tx = xmin + (x - xmin) // tile_size * tile_size
        tz = zmin + (z - zmin) // tile_size * tile_size
        by_tile.setdefault(f"x{tx}_z{tz}", []).append(action)
    block_positions = set()
    for action in plan.get("site_blocks", []):
        x, y, z = action["xyz"]
        if tuple(action["xyz"]) in block_positions or not (xmin <= x < xmax and zmin <= z < zmax):
            raise ValueError("Duplicate or out-of-bounds planned site block")
        block_positions.add(tuple(action["xyz"]))
        seen.add((x, z))
        tx = xmin + (x - xmin) // tile_size * tile_size
        tz = zmin + (z - zmin) // tile_size * tile_size
        block_tiles.setdefault(f"x{tx}_z{tz}", []).append(action)
    output.mkdir(parents=True)
    shutil.copy2(plan_path, output / "environment-plan.json")
    p["revision"] = plan.get("revision", output.name + "-demonstration-environment")
    p["environment"] = {"plan": str(plan_path.relative_to(ROOT)), "sha256": digest(plan_path),
                        "base_manifest_sha256": source_hash}
    write_json(config_path, p)
    write_json(output / "profile.json", p)
    for name in ("landscape-profile.json", "ownership-audit.json", "quad-start.json", "play-start.json", "camera-views.json"):
        shutil.copy2(source / name, output / name)
    journal, tiles, totals, registered, changed_tiles = [], [], Counter(), {}, []
    for spec in m["tiles"]:
        old_tile = source / spec["path"]
        tile = output / spec["path"]
        actions = by_tile.get(tile.name, [])
        block_actions = block_tiles.get(tile.name, [])
        for name, field in (("sample-blocks.npz", "archive_sha256"), ("audit.json", "audit_sha256")):
            if digest(old_tile / name) != spec[field]:
                raise ValueError(f"Source tile changed: {old_tile}/{name}")
        if not actions and not block_actions:
            shutil.copytree(old_tile, tile)
            report = json.loads((tile / "audit.json").read_text(encoding="utf-8"))
        else:
            print(f"Applying {len(actions)} site columns and {len(block_actions)} site blocks in {tile.name}", flush=True)
            tx, tz = map(int, tile.name[1:].split("_z"))
            a = read_archive(old_tile / "sample-blocks.npz")
            c = load_canvas(a, (tx, tz, min(tx + tile_size, xmax), min(tz + tile_size, zmax)))
            del a
            before, before_roles = c.data.copy(), c.roles.copy()
            old_palette = deepcopy(c.palette)
            protected = ~np.isin(before_roles, list(SITE_ROLES))
            architecture = np.any(protected, axis=0)
            for action in actions:
                apply_surface(c, action)
            for action in block_actions:
                apply_site_block(c, action, architecture)
            if np.any(c.data[protected] != before[protected]) or np.any(c.roles[protected] != before_roles[protected]):
                raise ValueError("Site repair altered architecture")
            difference = (c.data != before) | (c.roles != before_roles)
            tile_journal = []
            reasons = {(a["x"], a["z"]): a["feature"] for a in actions}
            block_reasons = {tuple(a["xyz"]): a["feature"] for a in block_actions}
            for iy, iz, ix in np.argwhere(difference):
                x, y, z = int(ix + tx), int(iy - 64), int(iz + tz)
                if (x, z) not in reasons and (x, y, z) not in block_reasons:
                    raise ValueError("Mutation outside planned columns")
                tile_journal.append({"xyz": [x, y, z], "feature": block_reasons.get((x, y, z), reasons.get((x, z))),
                                     "before": old_palette[int(before[iy, iz, ix])],
                                     "before_role": ROLES[int(before_roles[iy, iz, ix])],
                                     "after": c.palette[int(c.data[iy, iz, ix])],
                                     "after_role": ROLES[int(c.roles[iy, iz, ix])]})
            journal.extend(tile_journal)
            del before, before_roles, protected, architecture, difference
            roles = material_roles(c)
            violations = audit_role_materials(roles)
            if violations or c.clipped:
                raise ValueError({"materials": violations, "clipped": c.clipped})
            tile.mkdir(parents=True)
            c.export(tile / "sample-blocks.npz")
            write_world(c, tile / "world", p["name"], (137, 85, 24), old_tile / "world/level.dat")
            del c
            gc.collect()
            a = read_archive(tile / "sample-blocks.npz")
            parity, errors, _, _ = compare_world(a, tile / "world")
            if errors:
                raise ValueError(errors)
            report = json.loads((old_tile / "audit.json").read_text(encoding="utf-8"))
            report.update(block_count=len(a["coords"]), parity=parity, material_roles=roles,
                          environment={"planned_columns": len(actions), "planned_site_blocks": len(block_actions), "changed_cells": len(tile_journal),
                                       "architecture_changes": 0, "source_archive_sha256": spec["archive_sha256"]})
            write_json(tile / "audit.json", report)
            del a
            gc.collect()
            changed_tiles.append(tile.name)
        chunks = merge_tile_world(tile / "world", output / "world", registered)
        totals.update(blocks=report["block_count"], chunks=chunks, tiles=1)
        tiles.append({"path": str(tile.relative_to(output)), "blocks": report["block_count"],
                      "chunks": chunks, "audit_sha256": digest(tile / "audit.json"),
                      "archive_sha256": digest(tile / "sample-blocks.npz")})
    verify_merged_world(output / "world", registered)
    write_json(output / "environment-mutations.json", {"format": "hill-site-mutations-v1", "cells": journal,
               "source_manifest_sha256": source_hash, "plan_sha256": digest(plan_path)})
    result = deepcopy(m)
    result.update(tiles=tiles, totals=dict(totals), visual_review="pending",
                  profile={"path": str((output / "profile.json").resolve()), "sha256": digest(output / "profile.json")})
    if result.get("landscape"):
        result["landscape"]["path"] = str((output / "landscape-profile.json").resolve())
    result.pop("tile_reuse", None)
    result["environment_revision"] = {
        "base": str(source), "base_manifest_sha256": source_hash,
        "plan_sha256": digest(output / "environment-plan.json"),
        "mutations_sha256": digest(output / "environment-mutations.json"),
        "changed_tiles": changed_tiles, "changed_cells": len(journal),
        "planned_columns": len(seen), "unchanged_architecture": True,
        "planned_site_blocks": len(block_positions),
        "scope": "Enumerated exterior ground, paving, planting and site fixtures; all source components and original architectural columns unchanged. Unaffected tiles are byte-identical. Native and full artifact reviews pending.",
    }
    write_json(output / "manifest.json", result)
    print(json.dumps({"output": str(output), "changed_tiles": changed_tiles, "changed_cells": len(journal), **totals}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    refine(args.source, args.plan.resolve(), args.output, args.config)
