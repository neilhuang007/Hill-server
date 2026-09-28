"""Landscape cannot erase architecture or leave clipped crowns at tile seams."""

import numpy as np
from build_hill_chapel_sample import ROLES, Canvas
from campus_quad_landscape import build_quad_landscape, build_tree
from shapely.geometry import box, mapping


def canvas(x0=0, width=24):
    c = Canvas(x0, 0, width, 24, 2)
    c.ground_heights = np.full((24, width), 80, dtype=int)
    c.data[64:145] = c.state("dirt")
    c.roles[64:145] = ROLES.index("terrain")
    c.data[144] = c.state("grass_block")
    return c


def test_paths_protect_building_and_leave_lawn_open():
    c = canvas()
    for y in range(81, 96):
        c.set(12, y, 12, "bricks", "facade")
    before = c.data[:, 12, 12].copy()
    elevations = np.full((24, 24), 65.0)
    p = {
        "paths": [
            {
                "id": "quad_central_red_crosswalk",
                "polygon_xz": mapping(box(2, 5, 10, 7)),
            }
        ],
        "lawn": {"outer_polygon_xz": mapping(box(1, 1, 11, 11))},
        "planting_beds": [],
        "trees": [],
        "steps_and_terraces": [],
    }
    report = build_quad_landscape(c, elevations, p, -25)
    assert np.array_equal(before, c.data[:, 12, 12])
    assert np.all(elevations == 65)
    assert report["surface_columns"]["quad_central_red_crosswalk_columns"] > 0
    assert c.palette[c.get(5, 79, 5)]["Name"] == "minecraft:grass_block"
    assert c.palette[c.get(5, 79, 12)]["Name"] == "minecraft:bricks"
    assert c.clipped == 0


def test_crown_is_identical_when_built_across_two_tiles():
    tree = {
        "id": "seam",
        "center_xz_m": [6, 6],
        "crown_radius_m": 2,
        "height_above_ground_m": 5,
        "ground_navd88_m": 65,
    }
    whole, left, right = canvas(), canvas(0, 12), canvas(12, 12)
    for c in (whole, left, right):
        build_tree(c, tree, np.zeros(c.data.shape[1:], bool), -25)
        assert c.clipped == 0

    # Compare actual named states, not palette registration order.
    def names(c):
        return np.array([str(s) for s in c.palette], dtype=object)[c.data]

    assert np.array_equal(
        names(whole), np.concatenate([names(left), names(right)], axis=2)
    )


def test_terrace_reaches_the_actual_door_without_a_grass_gap():
    c = canvas()
    for y in range(82, 92):
        c.set(16, y, 12, "dark_oak_planks", "facade")
    p = {
        "paths": [],
        "lawn": {"outer_polygon_xz": mapping(box(1, 1, 11, 11))},
        "planting_beds": [],
        "trees": [],
        "steps_and_terraces": [],
        "engineered_terraces": [
            {
                "id": "entrance",
                "polygon_xz": mapping(box(3, 5, 8.5, 7)),
                "approach_start_xz_m": [3, 6],
                "threshold_xz_m": [8, 6],
                "start_navd88_m": 65.5,
                "threshold_navd88_m": 66.0,
                "central_brick_width_m": 2,
            }
        ],
    }
    build_quad_landscape(c, np.full((24, 24), 65.0), p, -25)
    assert c.palette[c.get(15, 81, 12)]["Name"] in {
        "minecraft:bricks",
        "minecraft:brick_slab",
    }
    assert c.palette[c.get(16, 82, 12)]["Name"] == "minecraft:dark_oak_planks"
    assert c.get(15, 80, 12) != 0
