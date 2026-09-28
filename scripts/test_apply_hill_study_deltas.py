"""Three-way amendments must not erase independent campus landscape changes."""

import numpy as np
import pytest

from apply_hill_study_deltas import apply_delta
from build_hill_chapel_sample import Canvas


def change():
    return {"xyz": [1, 10, 1], "before": {"Name": "minecraft:bricks"},
            "before_role": "facade", "after": {"Name": "minecraft:glass"},
            "after_role": "window", "study": "test"}


def test_amendment_preserves_surrounding_site_and_other_height():
    c = Canvas(0, 0, 3, 3, 2)
    c.set(1, 10, 1, "bricks", "facade")
    c.set(1, 9, 1, "smooth_stone", "pavement")
    c.set(0, 10, 1, "oak_leaves", "vegetation")
    before = c.data.copy()
    assert apply_delta(c, change())
    different = np.argwhere(before != c.data).tolist()
    assert different == [[74, 1, 1]]


def test_conflict_does_not_modify_campus():
    c = Canvas(0, 0, 3, 3, 2)
    c.set(1, 10, 1, "smooth_stone", "pavement")
    before, roles = c.data.copy(), c.roles.copy()
    with pytest.raises(ValueError, match="three_way_conflict"):
        apply_delta(c, change())
    assert np.array_equal(c.data, before)
    assert np.array_equal(c.roles, roles)


def test_existing_identical_change_needs_no_mutation():
    c = Canvas(0, 0, 3, 3, 2)
    c.set(1, 10, 1, "glass", "window")
    assert apply_delta(c, change()) is None


def test_site_override_is_exact_and_cannot_override_architecture():
    c = Canvas(0, 0, 3, 3, 2)
    c.set(1, 10, 1, "coarse_dirt", "terrain")
    patch = {**change(), "before": {"Name":"minecraft:grass_block"}, "before_role":"terrain",
             "after":{"Name":"minecraft:smooth_stone"}, "after_role":"pavement"}
    resolution = {"xyz":[1,10,1],"study":"test","campus":{"Name":"minecraft:coarse_dirt"},
                  "campus_role":"terrain","after":patch["after"],"after_role":"pavement"}
    record = apply_delta(c, patch, {(1,10,1):resolution})
    assert record["before"] == resolution["campus"]
    c.set(1,10,1,"bricks","facade")
    resolution.update(campus={"Name":"minecraft:bricks"},campus_role="facade")
    with pytest.raises(ValueError, match="three_way_conflict"):
        apply_delta(c, patch, {(1,10,1):resolution})


def test_reviewed_new_cheek_can_replace_an_exact_old_landscape_cell():
    c = Canvas(0,0,3,3,2)
    c.set(1,10,1,"dirt","terrain")
    patch = {**change(),"before":{"Name":"minecraft:stone"},"before_role":"terrain",
             "after":{"Name":"minecraft:stone_bricks"},"after_role":"trim"}
    resolution={"xyz":[1,10,1],"study":"test","campus":{"Name":"minecraft:dirt"},
                "campus_role":"terrain","after":patch["after"],"after_role":"trim"}
    assert apply_delta(c,patch,{(1,10,1):resolution})
