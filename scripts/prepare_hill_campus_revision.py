"""Join refreshed terrain studies and individually reviewed building revisions.

This prepares an assembly configuration only. A native review verdict belongs
to the particular exported study; no envelope is relabelled a finished facade.
"""

import argparse
import copy
import json
from pathlib import Path

from campus_material_assignment import assignment_key
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def merge_camera_views(updated, previous):
    """Keep the latest pose once per screenshot name across campus revisions."""
    result, names = [], set()
    for view in updated + previous:
        if view["name"] not in names:
            result.append(view)
            names.add(view["name"])
    return result


def study_identity(study):
    p = read(ROOT / study / "profile.json")
    key = assignment_key(p)
    if key is None:
        raise ValueError(f"Study has no unambiguous campus identity: {study}")
    return key, p


def native_review(path):
    """Carry a verdict only with the exact building archive it inspected."""
    review_path = path / "native-review.json"
    if not review_path.exists():
        raise ValueError(f"Individual study has no native review: {path}")
    review = read(review_path)
    archive_hash = digest(path / "sample-blocks.npz")
    recorded_hash = review.get("archive_sha256", review.get("sample_blocks_sha256"))
    if recorded_hash != archive_hash:
        raise ValueError(f"Native review belongs to a different building archive: {path}")
    status = review.get("status", "")
    if not status.startswith("accepted_for_"):
        raise ValueError(f"Individual study has no accepted native verdict: {path}: {status}")
    return {
        "status": status,
        "path": review_path.resolve().relative_to(ROOT).as_posix(),
        "sha256": digest(review_path),
        "archive_sha256": archive_hash,
        "verdict": review,
    }


def reviewed_replacement(path, scale, offset):
    relative = path.resolve().relative_to(ROOT).as_posix()
    key, profile = study_identity(relative)
    manifest = read(path / "manifest.json")
    if (manifest.get("blocks_per_metre") != scale or
            manifest.get("vertical_offset_m", profile.get("vertical_offset_m")) != offset):
        raise ValueError(f"Individual study frame differs from campus: {path}")
    if manifest.get("material_violations") or manifest.get("clipped_writes"):
        raise ValueError(f"Invalid building export: {path}")
    review = native_review(path)
    spec = {
        "name": profile["name"], "study": relative, "margin_m": 0.5,
        "detail_status": "individual_photo_study", "native_review": review,
        "source_archive_sha256": review["archive_sha256"],
    }
    views = []
    for v in read(path / "camera-views.json")["views"][:2]:
        def point(q):
            return [q[0] / scale, q[2] / scale, q[1] / scale - offset]
        views.append({"name": v["name"], "eye_xz_navd88_m": point(v["eye"]),
                      "target_xz_navd88_m": point(v["target"]), "fov": v["fov"]})
    return key, spec, views


def replace_individual_studies(base, studies, revision):
    """Replace only named studies, retaining every other frozen campus input."""
    p = copy.deepcopy(base)
    scale, offset = p["blocks_per_metre"], p["vertical_offset_m"]
    if scale != 2 or offset != -25:
        raise ValueError("Campus must retain the established 2 blocks/metre NAVD88 frame")
    indices = {}
    for i, spec in enumerate(p["components"]):
        key, _ = study_identity(spec["study"])
        if key in indices:
            raise ValueError(f"Duplicate campus identity: {key}")
        indices[key] = i
    changed, views = set(), []
    for path in studies:
        key, spec, cameras = reviewed_replacement(path, scale, offset)
        if key not in indices or key in changed:
            raise ValueError(f"Study absent from campus or supplied twice: {key}")
        p["components"][indices[key]] = spec
        changed.add(key)
        views.extend(cameras)
    p["revision"] = revision
    p["camera_views"] = merge_camera_views(views, p["camera_views"])
    remaining = sum(c.get("detail_status") == "measured_envelope" for c in p["components"])
    # Retain specific architectural/terrain limits, replacing only the old count.
    p["uncertainties"] = [
        f"Working reconstruction: {remaining} measured envelopes still require individual facade development; their presence is not a photographic completion claim.",
        *[u for u in p.get("uncertainties", []) if not u.startswith("Working reconstruction:")],
    ]
    p["reconstruction_status"] = {
        "components": len(p["components"]),
        "individual_photo_studies": sum(c.get("detail_status") == "individual_photo_study" for c in p["components"]),
        "individual_studies_replaced_this_revision": len(changed),
        "major_building_frame_refinements": sum(c.get("detail_status") == "major_building_frame_refinement" for c in p["components"]),
        "remaining_measured_envelopes": remaining, "visual_review": "pending",
    }
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--terrain", type=Path)
    ap.add_argument("--envelopes", type=Path)
    ap.add_argument("--developed", type=Path)
    ap.add_argument("--preserve-existing", action="store_true",
                    help="replace only --study buildings; retain the frozen base terrain and other components")
    ap.add_argument("--study", type=Path, action="append", default=[])
    ap.add_argument("--revision", required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    p = read(a.base)
    if a.preserve_existing:
        if any((a.terrain, a.envelopes, a.developed)) or not a.study:
            ap.error("--preserve-existing requires --study and cannot refresh terrain/envelopes/developed")
        result = replace_individual_studies(p, a.study, a.revision)
        write_json(a.output, result)
        print(json.dumps(result["reconstruction_status"]), flush=True)
        return
    if not all((a.terrain, a.envelopes, a.developed)):
        ap.error("terrain refresh requires --terrain, --envelopes and --developed")
    scale, offset = p["blocks_per_metre"], p["vertical_offset_m"]
    if scale != 2 or offset != -25:
        raise ValueError("Campus must retain the established 2 blocks/metre NAVD88 frame")
    replacements = {}
    for spec in read(a.envelopes / "components.json") + read(a.developed / "components.json"):
        key, _ = study_identity(spec["study"])
        if key in replacements:
            raise ValueError(f"Duplicate refreshed study: {key}")
        replacements[key] = spec
    # If a resumed ground batch completed Chapel/pavilions separately, include
    # their finished manifests rather than treating a partial batch as missing.
    chapel = a.developed / "chapel"
    if (chapel / "manifest.json").exists():
        replacements["chapel"] = {"name": "Alumni Chapel", "study": chapel.resolve().relative_to(ROOT).as_posix(), "margin_m": 2}
    pavilion_index = a.developed / "pavilions/components.json"
    if pavilion_index.exists():
        for spec in read(pavilion_index):
            key, _ = study_identity(spec["study"])
            replacements[key] = spec
    new_views = []
    for path in a.study:
        key, spec, views = reviewed_replacement(path, scale, offset)
        replacements[key] = spec
        new_views.extend(views)
    result, used = [], set()
    for old in p["components"]:
        key, _ = study_identity(old["study"])
        if key not in replacements:
            raise ValueError(f"No terrain-refreshed study for {old['name']}")
        replacement = replacements[key]
        # Preserve the review status of rough envelopes instead of carrying
        # an obsolete label onto their individually authored replacement.
        result.append(replacement)
        used.add(key)
    if used != set(replacements):
        raise ValueError(f"Replacement studies absent from campus scope: {set(replacements)-used}")
    p.update(revision=a.revision, terrain=a.terrain.resolve().relative_to(ROOT).as_posix(), components=result)
    p.pop("resource_pack", None)
    p["camera_views"] = merge_camera_views(new_views, p["camera_views"])
    remaining = sum(c.get("detail_status") == "measured_envelope" for c in result)
    p["uncertainties"] = [
        f"Working reconstruction: {remaining} measured envelopes still require individual facade development; their presence is not a photographic completion claim.",
        "Individually authored study cameras and observed material zones are retained. Concealed elevations remain unresolved where their profiles say so.",
        "Original Minecraft textures and ordinary construction blocks only; thin glazing, stair/slab trim and measured physical coordinates share one 2 blocks/metre scale.",
        "Ground uses a native 0.5m DEM grid with block tops at NAVD88. Dell pond is levelled to measured 55.0m; surrounding slopes are retained.",
        "Field paths, planting and sports structures retain the uncertainty documented in their source profiles. Campus-wide visual acceptance is pending.",
    ]
    p["reconstruction_status"] = {"components": len(result), "individual_photo_studies_added": len(a.study),
                                   "remaining_measured_envelopes": remaining, "visual_review": "pending"}
    write_json(a.output, p)
    print(json.dumps(p["reconstruction_status"]), flush=True)


if __name__ == "__main__":
    main()
