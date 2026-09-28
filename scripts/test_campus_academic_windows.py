"""Window reveals must remain in the rotated masonry envelope."""

import numpy as np
import pytest
from dataclasses import replace
from build_hill_chapel_sample import ROLES, Canvas, connect_window_panes
from campus_academic_building import AcademicExterior
from campus_measured_shell import build_measured_shell
from campus_roof_geometry import rasterize_roof
from campus_window_frames import bridge_frame_edges, pane_support_report, pane_perimeter_report
from shapely.affinity import rotate
from shapely.geometry import Point, box
from test_campus_measured_shell import measured_building, roof_face


@pytest.mark.parametrize("angle", [0, 18.25, 37])
@pytest.mark.parametrize("shape", ["rectangle", "round"])
@pytest.mark.parametrize("scale", [2, 4])
@pytest.mark.parametrize("recess", [0.0, 0.62])
def test_panes_and_trim_stay_inside_rotated_wall(angle, shape, scale, recess):
    footprint = rotate(box(-4, -2, 4, 2), angle, origin=(0, 0))
    building = measured_building(footprint, [roof_face(footprint, c=10)])
    r = rasterize_roof(building, (-8, -8, 8, 8), resolution=1 / scale)
    c = Canvas(-8 * scale, -8 * scale, 16 * scale, 16 * scale, scale)
    c.ground_heights = np.zeros((16 * scale, 16 * scale), dtype=int)
    build_measured_shell(c, building, r, vertical_offset=0)
    p = {
        "geometry": {
            "origin_xz_m": [0, 0],
            "axis_degrees": angle,
            "main_roof_threshold_navd88_m": 9,
        },
        "window_reveal": {"glass_recess_m": recess, "trim_width_m": 0.26},
    }
    facade = AcademicExterior(c, p, r, 0)
    facade.opening(0, "north", 3, 3.0, 2.4, shape)
    panes = np.argwhere(c.roles == ROLES.index("window"))
    assert len(panes) > 0
    for iy, iz, ix in panes:
        # Frame mode reaches the outer masonry row; the legacy explicit
        # recess remains available for archived studies.
        assert c.palette[c.data[iy, iz, ix]]["Name"].endswith("_glass_pane")
        point = Point((ix + c.x_min + 0.5) / c.scale, (iz + c.z_min + 0.5) / c.scale)
        assert footprint.contains(point)
        if recess:
            assert point.distance(footprint.boundary) > 0.3
        else:
            assert point.distance(footprint.boundary) < 1.0
    if not recess:
        assert any(
            Point((ix + c.x_min + 0.5) / scale, (iz + c.z_min + 0.5) / scale).distance(
                footprint.boundary
            )
            < 0.3
            for _, iz, ix in panes
        )
        connect_window_panes(c)
        assert pane_support_report(c)["unsupported_components"] == 0
        assert pane_perimeter_report(c)["vertical_air_or_reversed_slab_contacts"] == 0
    trim = np.argwhere(c.roles == ROLES.index("trim"))
    assert len(trim) > 0
    assert all(r.footprint_mask[iz, ix] for _, iz, ix in trim)
    if shape == "round":
        assert any(
            c.palette[c.data[iy, iz, ix]]["Name"] == "minecraft:quartz_stairs"
            for iy, iz, ix in trim
        )


def test_perimeter_pane_bridges_to_frame_only_inside_authorised_reveal():
    c = Canvas(0, 0, 8, 8, 2)
    c.set(2, 5, 3, "gray_stained_glass_pane", "window")
    c.set(4, 5, 3, "terracotta", "trim")
    c.set(2, 5, 5, "bricks", "facade")
    # East is an opening edge. South is outside the frame and must stay air.
    assert bridge_frame_edges(c, {(2, 5, 3), (3, 5, 3)}) == 1
    connect_window_panes(c)
    edge = c.palette[c.get(3, 5, 3)]
    assert edge["Name"] == "minecraft:gray_stained_glass_pane"
    assert edge["Properties"]["east"] == "true"
    assert edge["Properties"]["west"] == "true"
    assert c.get(2, 5, 4) == 0
    assert pane_support_report(c)["unsupported_components"] == 0


def test_authored_sash_posts_keep_connections_and_role_beside_glass():
    from campus_reference_details import connect_wood_fences

    c = Canvas(0, 0, 8, 8, 2)
    props = {d: "false" for d in ("north", "south", "east", "west")}
    props["waterlogged"] = "false"
    c.set(3, 5, 3, "pale_oak_fence", "trim", props)
    c.set(4, 5, 3, "glass_pane", "window")
    c.set(3, 5, 4, "glass_pane", "window")
    connect_wood_fences(c)
    assert c.palette[c.get(3, 5, 3)]["Properties"] == props
    assert c.roles[5 - c.y_min, 3, 3] == ROLES.index("trim")


def test_window_contour_does_not_float_above_adjacent_low_roof():
    footprint = rotate(box(-4, -2, 4, 2), 18.25, origin=(0, 0))
    building = measured_building(footprint, [roof_face(footprint, c=10)])
    r = rasterize_roof(building, (-8, -8, 8, 8), resolution=0.5)
    x_centres = -8 + (np.arange(32) + 0.5) / 2
    low_columns = np.broadcast_to(x_centres < -0.5, r.heights.shape)
    r = replace(r, heights=np.where(low_columns & r.footprint_mask, 2, r.heights))
    c = Canvas(-16, -16, 32, 32, 2)
    c.ground_heights = np.zeros((32, 32), dtype=int)
    build_measured_shell(c, building, r, vertical_offset=0)
    before = c.data[:, low_columns].copy()
    p = {
        "geometry": {"origin_xz_m": [0, 0], "axis_degrees": 18.25,
                     "main_roof_threshold_navd88_m": 9},
        "window_reveal": {"glass_recess_m": 0, "trim_width_m": 0.26},
    }
    AcademicExterior(c, p, r, 0).opening(0, "north", 3, 6, 2.4, at=-2)
    connect_window_panes(c)
    panes = np.argwhere(c.roles == ROLES.index("window"))
    assert len(panes) > 0
    assert all((iy + c.y_min + 0.5) / c.scale <= r.heights[iz, ix]
               for iy, iz, ix in panes)
    np.testing.assert_array_equal(c.data[:, low_columns], before)


@pytest.mark.parametrize("roof_block, properties", [
    ("stone_brick_slab", {"type": "bottom", "waterlogged": "false"}),
    ("stone_brick_stairs", {"facing": "east", "half": "bottom",
                           "shape": "straight", "waterlogged": "false"}),
])
def test_thin_gable_coping_has_solid_backing_without_lifting_roof(roof_block, properties):
    from campus_reference_details import ReferenceExterior

    footprint = box(-2, -2, 2, 2)
    building = measured_building(footprint, [roof_face(footprint, c=10)])
    r = rasterize_roof(building, (-4, -4, 4, 4), resolution=0.5)
    c = Canvas(-8, -8, 16, 16, 2)
    c.ground_heights = np.zeros((16, 16), dtype=int)
    c.set(0, 19, -4, "bricks", "facade")
    c.set(0, 20, -4, roof_block, "roof", properties)
    p = {"geometry": {"origin_xz_m": [0, 0], "axis_degrees": 0,
                      "main_roof_threshold_navd88_m": 9},
         "materials": {"facade": "bricks"}}
    ReferenceExterior(c, p, r, 0).roof_edge_trim((-2, -2, 2, 2))
    backing = c.palette[c.get(0, 19, -4)]
    coping = c.palette[c.get(0, 20, -4)]
    assert backing == {"Name": "minecraft:bricks"}
    assert coping["Properties"] == properties
    assert c.get(0, 21, -4) == 0


@pytest.mark.parametrize("angle", [0, 18.25, 37])
def test_thin_metal_mullions_remain_attached_trim_in_rotated_wall(angle):
    from campus_athey_details import connect_iron_rails
    from campus_materials import TRIM_BLOCKS

    footprint = rotate(box(-5, -2, 5, 2), angle, origin=(0, 0))
    building = measured_building(footprint, [roof_face(footprint, c=10)])
    r = rasterize_roof(building, (-8, -8, 8, 8), resolution=0.5)
    c = Canvas(-16, -16, 32, 32, 2)
    c.ground_heights = np.zeros((32, 32), dtype=int)
    build_measured_shell(c, building, r, vertical_offset=0)
    p = {
        "geometry": {
            "origin_xz_m": [0, 0],
            "axis_degrees": angle,
            "main_roof_threshold_navd88_m": 9,
        },
        "window_reveal": {
            "trim_width_m": 0.26,
            "mullion_block": "iron_bars",
        },
    }
    AcademicExterior(c, p, r, 0).opening(0, "north", 3, 5, 3, lights=3)
    connect_iron_rails(c)
    connect_window_panes(c)
    bars = [
        (iy, iz, ix)
        for iy, iz, ix in np.argwhere(c.data != 0)
        if c.palette[c.data[iy, iz, ix]]["Name"] == "minecraft:iron_bars"
    ]
    assert bars
    assert "minecraft:iron_bars" in TRIM_BLOCKS
    for iy, iz, ix in bars:
        assert c.roles[iy, iz, ix] == ROLES.index("trim")
        assert r.footprint_mask[iz, ix]
        props = c.palette[c.data[iy, iz, ix]]["Properties"]
        assert any(props[direction] == "true" for direction in ("north", "south", "east", "west"))
    assert pane_support_report(c)["unsupported_components"] == 0
