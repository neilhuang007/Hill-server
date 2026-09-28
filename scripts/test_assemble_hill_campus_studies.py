import json
import numpy as np
import pytest

from build_hill_chapel_sample import Canvas, ROLES
from assemble_hill_campus_studies import (
    prepare_component,
    merge_tile_world,
    verify_merged_world,
    audit_component_ownership,
    site_local_coordinates,
)
from test_audit_hill_chapel_sample import _SyntheticStudy
import hybridize_voxelearth_roofer_world as anvil


def test_chapel_site_bounds_follow_its_original_rotation_convention():
    angle = np.radians(-8.5)
    u, v = 7.5, 11.0
    x, z = np.cos(angle)*u+np.sin(angle)*v, -np.sin(angle)*u+np.cos(angle)*v
    profile = {"geometry": {"rotation_degrees": -8.5, "nave_half_width_m": 4.75}}
    assert site_local_coordinates(profile, x, z) == pytest.approx((u,v))


def test_component_preserves_air_panes_and_ground_below_foundation(tmp_path):
    study = tmp_path / "building"
    study.mkdir()
    c = Canvas(-16, 0, 32, 16, 2)
    c.data[64] = c.state("stone")
    c.roles[64] = ROLES.index("terrain")
    # Closed roof projection owns the room's empty columns as well as walls.
    c.data[70, 4:12, 8:24] = c.state("bricks")
    c.roles[70, 4:12, 8:24] = ROLES.index("roof")
    c.set(
        -7,
        2,
        6,
        "glass_pane",
        "window",
        {
            "north": "true",
            "south": "true",
            "east": "false",
            "west": "false",
            "waterlogged": "false",
        },
    )
    c.export(study / "sample-blocks.npz")
    (study / "manifest.json").write_text(
        json.dumps({"blocks_per_metre": 2, "vertical_offset_m": -25})
    )
    (study / "profile.json").write_text("{}")
    component = prepare_component(study, tmp_path / "cache", 2, -25, margin_m=0.5)
    target = Canvas(-16, 0, 32, 16, 2)
    target.data[60:75] = target.state("stone")
    target.roles[60:75] = ROLES.index("terrain")
    owners = np.zeros((16, 32), dtype=np.uint8)
    assert component.paste(target, owners, 1) > 0
    assert target.get(0, 2, 7) == 0  # interior remains hollow
    assert target.get(0, 8, 7) == 0  # air above roof is retained
    assert target.palette[target.get(-7, 2, 6)]["Properties"]["north"] == "true"
    assert target.get(0, -2, 7) != 0  # deeper continuous campus foundation
    assert target.get(-15, 2, 0) != 0  # surroundings stay outside ownership
    ownership = audit_component_ownership([component], -16, 0, (16, 32))
    assert ownership["owned_columns"] == component.meta["owned_columns"]
    assert ownership["components"][0]["translation_blocks"] == [0, 0, 0]
    with pytest.raises(ValueError, match="Overlapping"):
        audit_component_ownership([component, component], -16, 0, (16, 32))
    with pytest.raises(ValueError, match="clipped"):
        audit_component_ownership([component], -16, 0, (16, 16))
    with pytest.raises(ValueError, match="Overlapping"):
        component.paste(target, owners, 2)
    with pytest.raises(ValueError, match="frame mismatch"):
        prepare_component(study, tmp_path / "bad-cache", 4, -25)


def test_merge_rejects_overlap_and_detects_changed_chunk_bytes(tmp_path):
    study = _SyntheticStudy(tmp_path)
    source = study.study_dir / "world"
    (source / "level.dat").write_bytes(b"metadata copied unchanged")
    target = tmp_path / "assembled"
    expected = {}
    count = merge_tile_world(source, target, expected)
    assert count > 0 and verify_merged_world(target, expected) == count
    with pytest.raises(ValueError, match="Duplicate assembly chunk"):
        merge_tile_world(source, target, expected)
    path = next((target / "region").glob("*.mca"))
    region = anvil.RegionEditor(path)
    index = next(iter(region.raw_records))
    record = bytearray(region.raw_records[index])
    record[-1] ^= 1
    region.raw_records[index] = bytes(record)
    region.modified.add(index)
    region.save()
    with pytest.raises(ValueError, match="differ"):
        verify_merged_world(target, expected)
