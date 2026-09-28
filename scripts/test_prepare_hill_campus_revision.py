import json

import pytest

import prepare_hill_campus_revision as revision


def test_native_verdict_cannot_be_reused_for_changed_or_rejected_build(tmp_path, monkeypatch):
    monkeypatch.setattr(revision, "ROOT", tmp_path)
    study = tmp_path / "house"
    study.mkdir()
    archive = study / "sample-blocks.npz"
    archive.write_bytes(b"reviewed building export")
    review = {
        "status": "accepted_for_bounded_integration",
        "archive_sha256": revision.digest(archive),
        "remaining_limits": ["Unseen rear openings remain provisional"],
    }
    review_path = study / "native-review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    result = revision.native_review(study)
    assert result["verdict"]["remaining_limits"] == review["remaining_limits"]
    assert result["path"] == "house/native-review.json"

    archive.write_bytes(b"changed glazing after the review")
    with pytest.raises(ValueError, match="different building archive"):
        revision.native_review(study)
    review["archive_sha256"] = revision.digest(archive)
    review["status"] = "rejected_white_trim_obstructs_glass"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="no accepted native verdict"):
        revision.native_review(study)


def test_missing_native_review_cannot_promote_individual_house(tmp_path):
    with pytest.raises(ValueError, match="no native review"):
        revision.native_review(tmp_path)


def test_updated_camera_replaces_old_pose_without_overwriting_its_capture():
    updated = {"name": "house-front", "eye_xz_navd88_m": [1, 2, 63]}
    old = {"name": "house-front", "eye_xz_navd88_m": [4, 5, 60]}
    context = {"name": "quad", "eye_xz_navd88_m": [10, 20, 70]}
    assert revision.merge_camera_views([updated], [old, context, old]) == [updated, context]


def reviewed_study(tmp_path, name, parent, scale=2):
    path = tmp_path / name
    path.mkdir()
    revision.write_json(path / "profile.json", {"name": name, "parent_id": parent, "vertical_offset_m": -25})
    revision.write_json(path / "manifest.json", {"blocks_per_metre": scale, "vertical_offset_m": -25})
    (path / "sample-blocks.npz").write_bytes(name.encode())
    revision.write_json(path / "native-review.json", {
        "status": "accepted_for_bounded_integration",
        "archive_sha256": revision.digest(path / "sample-blocks.npz"),
    })
    revision.write_json(path / "camera-views.json", {"views": [
        {"name": "front", "eye": [2, 90, 4], "target": [6, 94, 8], "fov": 65}
    ]})
    return path


def test_building_only_revision_preserves_prior_refinements_and_ground(tmp_path, monkeypatch):
    monkeypatch.setattr(revision, "ROOT", tmp_path)
    reviewed_study(tmp_path, "old-house", "house")
    new = reviewed_study(tmp_path, "new-house", "house")
    reviewed_study(tmp_path, "athey", "athey")
    kept = {"name": "Athey", "study": "athey", "margin_m": 2,
            "detail_status": "major_building_frame_refinement", "native_review": {"bounded": True}}
    base = {"blocks_per_metre": 2, "vertical_offset_m": -25, "terrain": "frozen-terrain.npz",
            "landscape": "frozen-landscape.json", "revision": "old", "camera_views": [],
            "components": [kept, {"study": "old-house", "detail_status": "measured_envelope"}],
            "uncertainties": ["Working reconstruction: old count", "Athey limits remain."]}
    result = revision.replace_individual_studies(base, [new], "new")
    assert result["components"][0] == kept
    assert result["components"][1]["study"] == "new-house"
    assert result["terrain"] == base["terrain"] and result["landscape"] == base["landscape"]
    assert result["camera_views"][0]["eye_xz_navd88_m"] == [1, 2, 70]
    assert result["reconstruction_status"]["remaining_measured_envelopes"] == 0
    assert result["uncertainties"][1] == "Athey limits remain."
    assert base["revision"] == "old" and base["components"][1]["study"] == "old-house"


def test_building_only_revision_rejects_wrong_scale_and_out_of_scope_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(revision, "ROOT", tmp_path)
    bad = reviewed_study(tmp_path, "wrong-scale", "house", scale=1)
    absent = reviewed_study(tmp_path, "absent", "other")
    reviewed_study(tmp_path, "old-house", "house")
    base = {"blocks_per_metre": 2, "vertical_offset_m": -25, "camera_views": [],
            "components": [{"study": "old-house"}]}
    with pytest.raises(ValueError, match="frame differs"):
        revision.replace_individual_studies(base, [bad], "new")
    with pytest.raises(ValueError, match="absent from campus"):
        revision.replace_individual_studies(base, [absent], "new")
