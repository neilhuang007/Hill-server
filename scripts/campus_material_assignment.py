"""Apply reviewed, building-specific material rules without changing geometry.

Rules select original states and semantic roles, optionally within a measured
zone. They never cascade through each other's output. Stair/slab/wall geometry
and block properties are preserved. The registry records actual source material,
photographic observations, alternatives and uncertainty separately.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from campus_materials import is_allowed_for_role

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "server-assets/hill-campus-material-assignments.json"


def canonical(name):
    return name if ":" in name else "minecraft:" + name


def full_block(family):
    return {
        "brick": "bricks", "mud_brick": "mud_bricks", "stone_brick": "stone_bricks",
        "tuff_brick": "tuff_bricks", "deepslate_tile": "deepslate_tiles",
        "deepslate_brick": "deepslate_bricks", "quartz": "quartz_block",
        "birch": "birch_planks", "oak": "oak_planks", "pale_oak": "pale_oak_planks",
        "spruce": "spruce_planks", "dark_oak": "dark_oak_planks",
    }.get(family, family)


def shape_replacement(original, rule):
    name = original["Name"].removeprefix("minecraft:")
    if "to_family" in rule:
        family = rule["to_family"]
        suffix = next((s for s in ("_stairs", "_slab", "_wall") if name.endswith(s)), "")
        name = family + suffix if suffix else full_block(family)
    else:
        name = rule["to"]
        if any(original["Name"].endswith(s) for s in ("_stairs", "_slab", "_wall")):
            suffix = next(s for s in ("_stairs", "_slab", "_wall") if original["Name"].endswith(s))
            if not name.endswith(suffix):
                raise ValueError(f"Rule changes occupied shape: {original['Name']} -> {name}")
    return {"Name": canonical(name), **({"Properties": original["Properties"].copy()} if original.get("Properties") else {})}


def assignment_key(profile):
    if profile.get("material_assignment_key"):
        return profile["material_assignment_key"]
    if profile.get("parent_id"):
        return profile["parent_id"]
    name = profile.get("name", "").lower()
    if "chapel" in name:
        return "chapel"
    if "kipp" in name:
        return "kipp_46_pavilion"
    if "press" in name or "puccio" in name:
        return "madden_puccio_66_press_box"
    return None


def transform_states(coords, state_ids, role_ids, palette, role_names, rules, *, scale=2, offset=-25):
    original = state_ids.copy()
    result = state_ids.copy()
    output_palette = [dict(p) for p in palette]
    lookup = {json.dumps(p, sort_keys=True): i for i, p in enumerate(output_palette)}
    reports = []
    written = np.zeros(len(original), dtype=bool)
    for rule in rules:
        allowed_roles = rule["roles"]
        source_names = {canonical(n) for n in rule["from"]}
        source_states = [i for i, p in enumerate(palette) if p["Name"] in source_names]
        mask = np.isin(original, source_states) & np.isin(role_ids, [role_names.index(r) for r in allowed_roles])
        where = rule.get("where", {})
        height = (coords[:, 1] + 0.5) / scale - offset
        if "height_navd88_m" in where:
            low, high = where["height_navd88_m"]
            mask &= (height >= low) & (height < high)
        if "bounds_xz_m" in where:
            a, b, c, d = where["bounds_xz_m"]
            x, z = (coords[:, 0] + 0.5) / scale, (coords[:, 2] + 0.5) / scale
            mask &= (x >= a) & (x < c) & (z >= b) & (z < d)
        if "bounds_uv_m" in where:
            frame = where["frame"]
            theta = math.radians(frame["axis_degrees"])
            dx = (coords[:, 0] + 0.5) / scale - frame["origin_xz_m"][0]
            dz = (coords[:, 2] + 0.5) / scale - frame["origin_xz_m"][1]
            u, v = dx * math.cos(theta) + dz * math.sin(theta), -dx * math.sin(theta) + dz * math.cos(theta)
            a, b, c, d = where["bounds_uv_m"]
            mask &= (u >= a) & (u < c) & (v >= b) & (v < d)
        overlap = mask & written
        if overlap.any() and not rule.get("overrides_previous_zone", False):
            raise ValueError(f"Unintentional overlapping material rules at {rule['id']}: {overlap.sum()}")
        changes = Counter()
        for state in np.unique(original[mask]):
            target = shape_replacement(palette[state], rule)
            selected = mask & (original == state)
            for role in set(role_names[int(r)] for r in np.unique(role_ids[selected])):
                if not is_allowed_for_role(target["Name"], role):
                    raise ValueError(f"{target['Name']} disallowed for {role} in {rule['id']}")
            key = json.dumps(target, sort_keys=True)
            if key not in lookup:
                lookup[key] = len(output_palette)
                output_palette.append(target)
            target_id = lookup[key]
            changed = selected & (original != target_id)
            result[selected] = target_id
            changes[palette[state]["Name"] + " -> " + target["Name"]] += int(changed.sum())
        written |= mask
        reports.append({"rule": rule["id"], "matched_blocks": int(mask.sum()), "changes": {k: v for k, v in changes.items() if v}})
    if len(output_palette) >= 65535:
        raise ValueError("Palette exceeds uint16 capacity")
    return result.astype(np.uint16), output_palette, reports


def apply_reviewed_palette(canvas, profile, *, registry_path=REGISTRY):
    if not Path(registry_path).exists():
        return None
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    key = assignment_key(profile)
    assignment = registry["buildings"].get(key)
    if not assignment:
        return None
    source_hash = assignment.get("source_archive_sha256")
    if source_hash and profile.get("material_assignment_source_sha256") != source_hash:
        # A legacy material migration must never recolour a newly authored
        # facade that happens to have the same county building identifier.
        return None
    from build_hill_chapel_sample import ROLES

    roles = {ROLES.index(r) for rule in assignment["rules"] for r in rule["roles"]}
    yy, zz, xx = np.nonzero(np.isin(canvas.roles, list(roles)))
    coords = np.column_stack((xx + canvas.x_min, yy + canvas.y_min, zz + canvas.z_min))
    original = canvas.data[yy, zz, xx]
    states, palette, report = transform_states(coords, original, canvas.roles[yy, zz, xx], canvas.palette, list(ROLES), assignment["rules"], scale=canvas.scale, offset=profile.get("vertical_offset_m", -25))
    mapping = np.array([canvas.state(p["Name"], p.get("Properties")) for p in palette], dtype=np.uint16)
    canvas.data[yy, zz, xx] = mapping[states]
    return {"registry": str(Path(registry_path).resolve()), "revision": registry["revision"], "building_key": key,
            "status": assignment["status"], "changed_blocks": int(np.count_nonzero(original != mapping[states])), "rules": report}
