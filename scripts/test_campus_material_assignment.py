import numpy as np
import pytest

from campus_material_assignment import transform_states


def test_legacy_rule_requires_the_explicit_source_archive_identity(tmp_path):
    import json
    from build_hill_chapel_sample import Canvas
    from campus_material_assignment import apply_reviewed_palette

    path = tmp_path / "assignments.json"
    path.write_text(json.dumps({"revision": "test", "buildings": {"parent-a": {
        "source_archive_sha256": "legacy-digest", "status": "reviewed",
        "rules": [{"id": "cream", "roles": ["facade"], "from": ["bricks"], "to": "smooth_quartz"}]
    }}}), encoding="utf-8")
    c = Canvas(0, 0, 8, 8, 2)
    c.set(3, 5, 3, "bricks", "facade")
    p = {"parent_id": "parent-a"}
    assert apply_reviewed_palette(c, p, registry_path=path) is None
    assert c.palette[c.get(3, 5, 3)]["Name"] == "minecraft:bricks"
    p["material_assignment_source_sha256"] = "legacy-digest"
    report = apply_reviewed_palette(c, p, registry_path=path)
    assert report["changed_blocks"] == 1
    assert c.palette[c.get(3, 5, 3)]["Name"] == "minecraft:smooth_quartz"


def test_role_and_zone_change_only_matching_original_facade_cells():
    coords = np.array([[0, 80, 0], [0, 85, 0], [0, 80, 1], [0, 80, 2]])
    states = np.array([1, 1, 1, 2], dtype=np.uint16)
    roles = np.array([1, 1, 2, 1], dtype=np.uint8)
    palette = [{"Name": "minecraft:air"}, {"Name": "minecraft:bricks"}, {"Name": "minecraft:white_terracotta"}]
    rules = [
        {"id": "lowerwall", "roles": ["facade"], "from": ["bricks"], "to": "white_terracotta", "where": {"height_navd88_m": [65, 67]}},
        {"id": "existingupperfinish", "roles": ["facade"], "from": ["white_terracotta"], "to": "pale_oak_planks"},
    ]
    result, new_palette, report = transform_states(coords, states, roles, palette, ["air", "facade", "pavement"], rules)
    assert [new_palette[i]["Name"] for i in result] == ["minecraft:white_terracotta", "minecraft:bricks", "minecraft:bricks", "minecraft:pale_oak_planks"]
    assert np.array_equal(states, [1, 1, 1, 2])
    assert [r["matched_blocks"] for r in report] == [1, 1]


def test_roof_family_preserves_stairs_slabs_and_every_property():
    props = {"facing": "east", "half": "top", "shape": "inner_left", "waterlogged": "false"}
    palette = [{"Name": "minecraft:air"}, {"Name": "minecraft:stone_brick_stairs", "Properties": props}, {"Name": "minecraft:stone_brick_slab", "Properties": {"type": "top", "waterlogged": "false"}}, {"Name": "minecraft:stone_bricks"}]
    result, new_palette, _ = transform_states(np.array([[0, 80, 0], [1, 80, 0], [2, 80, 0]]), np.array([1, 2, 3]), np.array([1, 1, 1]), palette, ["air", "roof"], [{"id": "grayroof", "roles": ["roof"], "from": ["stone_bricks", "stone_brick_stairs", "stone_brick_slab"], "to_family": "deepslate_tile"}])
    assert [new_palette[i]["Name"] for i in result] == ["minecraft:deepslate_tile_stairs", "minecraft:deepslate_tile_slab", "minecraft:deepslate_tiles"]
    assert new_palette[result[0]]["Properties"] == props
    assert new_palette[result[1]]["Properties"] == {"type": "top", "waterlogged": "false"}


def test_material_rule_cannot_replace_a_slab_with_a_full_cube_or_ore():
    for source, target, role in [("stone_brick_slab", "quartz_block", "trim"), ("bricks", "iron_ore", "facade")]:
        with pytest.raises(ValueError):
            transform_states(np.array([[0, 80, 0]]), np.array([1]), np.array([1]), [{"Name": "minecraft:air"}, {"Name": "minecraft:" + source}], ["air", role], [{"id": "bad", "roles": [role], "from": [source], "to": target}])
