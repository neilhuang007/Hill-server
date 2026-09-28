"""Protect architecture and real terrain support during exterior repairs."""

import numpy as np
import pytest

from build_hill_chapel_sample import Canvas
from refine_hill_campus_environment import apply_surface, apply_site_block
from campus_materials import audit_role_materials


def ground():
    c = Canvas(0, 0, 3, 3, 2)
    c.ground_heights = np.full((3, 3), 10, np.int16)
    for z in range(3):
        for x in range(3):
            for y in range(5, 11):
                c.set(x, y, z, "grass_block" if y == 10 else "dirt", "terrain")
    return c


def action(y):
    return {"x": 1, "z": 1, "y": y, "state": {"Name": "minecraft:smooth_stone_slab",
            "Properties": {"type": "bottom", "waterlogged": "false"}}}


def test_raised_slab_has_solid_support_and_neighbors_unchanged():
    c = ground()
    neighbor = c.data[:, 0, 0].copy()
    apply_surface(c, action(12))
    assert all(c.get(1, y, 1) for y in range(5, 13))
    assert c.palette[c.get(1, 12, 1)]["Properties"]["type"] == "bottom"
    assert np.array_equal(neighbor, c.data[:, 0, 0])


def test_lowered_surface_removes_grass_above_but_keeps_substrate():
    c = ground()
    apply_surface(c, action(9))
    assert c.get(1, 10, 1) == 0
    assert c.get(1, 8, 1) != 0
    assert c.ground_heights[1, 1] == 9


def test_covered_passage_and_vegetation_cannot_be_overwritten():
    c = ground()
    c.set(1, 18, 1, "stone_bricks", "roof")
    before = c.data.copy()
    with pytest.raises(ValueError, match="architectural"):
        apply_surface(c, action(10))
    assert np.array_equal(c.data, before)
    c = ground()
    c.set(1, 11, 1, "oak_log", "vegetation")
    with pytest.raises(ValueError, match="vegetation"):
        apply_surface(c, action(10))


def test_large_unreviewed_grade_change_rejected():
    with pytest.raises(ValueError, match="grade"):
        apply_surface(ground(), action(16))


def test_ordinary_paver_partial_blocks_keep_the_construction_palette():
    assert audit_role_materials({"pavement": {"minecraft:stone_brick_slab": 1,
                                             "minecraft:stone_brick_stairs": 1}}) == []
    assert audit_role_materials({"pavement": {"minecraft:sculk": 1}})


def test_planting_exact_precondition_and_architecture_protection():
    c = ground()
    item = {"xyz": [1, 11, 1], "before": {"Name": "minecraft:air"},
            "before_role": "air", "state": {"Name": "minecraft:oak_log", "Properties": {"axis": "y"}},
            "role": "vegetation"}
    protected = np.zeros((3, 3), bool)
    protected[1, 1] = True
    with pytest.raises(ValueError, match="architectural"):
        apply_site_block(c, item, protected)
    protected[1, 1] = False
    apply_site_block(c, item, protected)
    assert c.palette[c.get(1, 11, 1)]["Name"] == "minecraft:oak_log"
    with pytest.raises(ValueError, match="site_block_conflict"):
        apply_site_block(c, item, protected)
