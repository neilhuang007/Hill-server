import copy
import json
from types import SimpleNamespace

import pytest

from campus_revision_reuse import ReusableAssembly, changed_extents, intersects
from campus_study_io import digest


def meta(x=0, archive="original", margin=2):
    return dict(study="unused", archive_sha256=archive, x_min=x, z_min=0,
                shape=[384, 16, 16], margin_m=margin, site_bounds_uv_m=[])


def test_rebuilds_both_old_and_new_extents_when_component_moves():
    boxes = changed_extents([meta()], [meta(32, "replacement")])
    assert any(intersects((0, 0, 16, 16), b) for b in boxes)
    assert any(intersects((32, 0, 48, 16), b) for b in boxes)
    assert not any(intersects((16, 0, 32, 16), b) for b in boxes)
    assert changed_extents([meta()], [meta(margin=3)])
    other_path = {**meta(), "study": "new-path-same-geometry"}
    assert changed_extents([meta()], [other_path]) == []


def source(tmp_path):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    study = tmp_path / "study"
    study.mkdir()
    (study / "sample-blocks.npz").write_bytes(b"immutable source archive")
    component = {**meta(64), "study": str(study),
                 "archive_sha256": digest(study / "sample-blocks.npz")}
    profile = {"blocks_per_metre": 2, "vertical_offset_m": -25,
               "tile_size_blocks": 16}
    base = tmp_path / "base"
    write(base / "profile.json", profile)
    tile = base / "tiles/x0_z0"
    tile.mkdir(parents=True)
    (tile / "sample-blocks.npz").write_bytes(b"immutable tile archive")
    write(tile / "audit.json", {"block_count": 8, "errors": []})
    manifest = {
        "profile": {"sha256": digest(base / "profile.json")},
        "terrain": {"sha256": "terrain-hash"},
        "bounds_xz_blocks": [0, 0, 96, 16], "terrain_base_y": 18,
        "blocks_per_metre": 2, "vertical_offset_m": -25,
        "components": [component], "tiles": [{
            "path": "tiles/x0_z0", "blocks": 8,
            "archive_sha256": digest(tile / "sample-blocks.npz"),
            "audit_sha256": digest(tile / "audit.json"),
        }],
    }
    write(base / "manifest.json", manifest)
    manifest_hash = digest(base / "manifest.json")
    write(base / "artifact-audit.json", {"passed": True, "manifest_sha256": manifest_hash})
    write(base / "native-review.json", {"status": "accepted_for_bounded_working_campus",
                                        "manifest_sha256": manifest_hash})
    args = [base, profile, [SimpleNamespace(meta=component)], "terrain-hash",
            [0, 0, 96, 16], 18, None]
    return args, tile, write


def test_reuse_binds_tile_hashes_and_rejects_later_mutation(tmp_path):
    args, tile, _ = source(tmp_path)
    plan = ReusableAssembly(*args)
    assert plan.candidate("x0_z0", [0, 0, 16, 16])[0] == tile
    (tile / "sample-blocks.npz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Reuse tile changed"):
        plan.candidate("x0_z0", [0, 0, 16, 16])


@pytest.mark.parametrize("mutation", ["terrain", "landscape", "review", "archive", "frame"])
def test_reuse_rejects_changed_inputs_or_unaccepted_source(tmp_path, mutation):
    args, _, write = source(tmp_path)
    if mutation == "terrain":
        args[3] = "different"
    elif mutation == "landscape":
        args[6] = {"new_path": True}
    elif mutation == "review":
        write(args[0] / "native-review.json", {"status": "rejected"})
    elif mutation == "archive":
        (tmp_path / "study/sample-blocks.npz").write_bytes(b"changed source")
    elif mutation == "frame":
        args[1] = {**args[1], "blocks_per_metre": 4}
    with pytest.raises(ValueError):
        ReusableAssembly(*args)


def test_changed_ownership_or_archive_prevents_tile_reuse(tmp_path):
    args, _, _ = source(tmp_path)
    moved = copy.deepcopy(args[2][0].meta)
    moved.update(x_min=0, archive_sha256="new-archive")
    args[2] = [SimpleNamespace(meta=moved)]
    plan = ReusableAssembly(*args)
    assert plan.candidate("x0_z0", [0, 0, 16, 16]) is None
