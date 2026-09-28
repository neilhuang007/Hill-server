"""Common export and provenance for bounded architectural studies."""

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import hybridize_voxelearth_roofer_world as anvil
import numpy as np
from build_hill_chapel_sample import ROLES, write_world
from campus_materials import audit_role_materials


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def material_roles(canvas):
    n = len(canvas.palette)
    hist = np.zeros(n * len(ROLES), dtype=np.int64)
    states, roles = canvas.data.ravel(), canvas.roles.ravel()
    for start in range(0, states.size, 1_000_000):
        sl = slice(start, start + 1_000_000)
        hist += np.bincount(
            roles[sl].astype(np.int32) * n + states[sl], minlength=hist.size
        )
    result = {}
    for role, row in zip(ROLES, hist.reshape(len(ROLES), n)):
        counts = Counter()
        for state in np.flatnonzero(row):
            if state:
                counts[canvas.palette[state]["Name"]] += int(row[state])
        if counts:
            result[role] = dict(counts)
    return result


def finish_study(canvas, profile, output, cameras, evidence, *, resource_pack=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    replacements = profile.get("vanilla_state_replacements", {})
    for i, state in enumerate(list(canvas.palette)):
        short = state["Name"].removeprefix("minecraft:")
        if short in replacements:
            canvas.data[canvas.data == i] = canvas.state(
                replacements[short], state.get("Properties")
            )
    if not profile.get("material_review"):
        from campus_material_assignment import apply_reviewed_palette

        material_review = apply_reviewed_palette(canvas, profile)
        if material_review:
            profile["material_review"] = material_review
            evidence["material_review"] = material_review
    from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report

    evidence["window_support"] = pane_support_report(canvas)
    evidence["window_joints"] = pane_joint_report(canvas)
    evidence["window_perimeter"] = pane_perimeter_report(canvas)
    evidence["completed_frame_cap_cells"] = getattr(canvas, "window_cap_repair_count", 0)
    if evidence["window_support"]["unsupported_components"]:
        raise ValueError({"unsupported_window_panes": evidence["window_support"]})
    if evidence["window_joints"]["unbridged_diagonal_pairs"] or evidence["window_joints"]["disconnected_adjacent_pairs"]:
        raise ValueError({"open_window_joints": evidence["window_joints"]})
    roles = material_roles(canvas)
    violations = audit_role_materials(roles)
    if violations or canvas.clipped:
        raise ValueError({"materials": violations, "clipped_writes": canvas.clipped})
    output.mkdir(parents=True, exist_ok=False)
    print("Exporting block archive", flush=True)
    materials = canvas.export(output / "sample-blocks.npz")
    write_json(output / "profile.json", profile)
    write_json(
        output / "camera-views.json",
        {"format": "hill-native-camera-views-v1", "views": cameras},
    )
    write_json(
        output / "play-start.json",
        {"format": "hill-native-camera-views-v1", "views": cameras[:1]},
    )
    print("Writing Anvil world", flush=True)
    world = write_world(
        canvas,
        output / "world",
        profile["name"],
        tuple(round(v) for v in cameras[0]["eye"]),
        anvil.DEFAULT_SOURCE_WORLD / "level.dat",
    )
    manifest = {
        "format": "hill-building-study-v1",
        "created_unix": int(time.time()),
        "revision": profile["revision"],
        "blocks_per_metre": canvas.scale,
        "vertical_offset_m": profile["vertical_offset_m"],
        "profile": {
            "path": str((output / "profile.json").resolve()),
            "sha256": digest(output / "profile.json"),
        },
        "world": world,
        "block_count": int(np.count_nonzero(canvas.data)),
        "material_roles": roles,
        "materials": materials,
        "material_violations": violations,
        "clipped_writes": canvas.clipped,
        "visual_review": "pending",
        **evidence,
    }
    if resource_pack:
        pack = Path(resource_pack)
        manifest["resource_pack"] = {
            "path": str(pack.resolve()),
            "files": {
                str(p.relative_to(pack)).replace("\\", "/"): digest(p)
                for p in sorted(pack.rglob("*"))
                if p.is_file()
            },
        }
    write_json(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "output": str(output),
                "blocks": manifest["block_count"],
                "clipped": canvas.clipped,
            }
        ),
        flush=True,
    )
    return manifest
