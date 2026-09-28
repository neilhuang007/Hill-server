import pytest

from build_hill_chapel_sample import Canvas, connect_window_panes
from campus_window_frames import bridge_frame_edges, close_diagonal_pane_corners, close_diagonal_pane_jambs, pane_joint_report, pane_perimeter_report


@pytest.mark.parametrize("dz", [-1, 1])
def test_diagonal_sheet_gets_exactly_one_inward_return_and_reciprocal_joins(dz):
    c = Canvas(0, 0, 8, 8, 2)
    a, b = (3, 5, 3), (4, 5, 3 + dz)
    corners = {(4, 5, 3), (3, 5, 3 + dz)}
    for p in (a, b):
        c.set(*p, "white_stained_glass_pane", "window")
    assert pane_joint_report(c)["unbridged_diagonal_pairs"] == 1
    assert close_diagonal_pane_corners(c, {a, b, *corners}, inward=(-1, 0)) == 1
    connect_window_panes(c)
    assert sum(c.get(*p) != 0 for p in corners) == 1
    assert c.get(3, 5, 3 + dz)
    assert pane_joint_report(c)["unbridged_diagonal_pairs"] == 0
    assert pane_joint_report(c)["disconnected_adjacent_pairs"] == 0
    assert close_diagonal_pane_corners(c, {a, b, *corners}, inward=(-1, 0)) == 0


def test_diagonal_repair_cannot_grow_beyond_its_authorised_opening():
    c = Canvas(0, 0, 8, 8, 2)
    a, b = (3, 5, 3), (4, 5, 4)
    for p in (a, b):
        c.set(*p, "glass_pane", "window")
    assert close_diagonal_pane_corners(c, {a, b}) == 0
    c.set(3, 5, 4, "bricks", "facade")
    assert close_diagonal_pane_corners(c, {a, b, (3, 5, 4), (4, 5, 3)}) == 0
    assert c.palette[c.get(3, 5, 4)]["Name"] == "minecraft:bricks"
    assert c.get(4, 5, 3) == 0


def test_final_connection_pass_restores_a_corner_removed_by_later_facade_work():
    c = Canvas(0, 0, 8, 8, 2)
    a, b, corner = (3,5,3), (4,5,4), (3,5,4)
    for p in (a,b):
        c.set(*p,"glass_pane","window")
    assert bridge_frame_edges(c,{a,b,corner},inward=(-1,0)) == 1
    c.set(*corner,"air","air")
    connect_window_panes(c)
    assert c.get(*corner)
    assert pane_joint_report(c)["unbridged_diagonal_pairs"] == 0


def test_frame_report_catches_free_end_and_wrong_slab_half_missed_by_pair_report():
    c = Canvas(0, 0, 8, 8, 2)
    c.set(3, 5, 3, "white_stained_glass_pane", "window")
    c.set(2, 5, 3, "bricks", "facade")
    c.set(3, 4, 3, "quartz_slab", "trim", {"type": "bottom"})
    c.set(3, 6, 3, "quartz_slab", "trim", {"type": "top"})
    connect_window_panes(c)
    assert pane_joint_report(c)["unbridged_diagonal_pairs"] == 0
    report = pane_perimeter_report(c)
    assert report["fewer_than_two_horizontal_joins"] == 1
    assert report["vertical_air_or_reversed_slab_contacts"] == 2
    c.set(4, 5, 3, "bricks", "facade")
    c.set(3, 4, 3, "quartz_slab", "trim", {"type": "top"})
    c.set(3, 6, 3, "quartz_slab", "trim", {"type": "bottom"})
    connect_window_panes(c)
    report = pane_perimeter_report(c)
    assert report["fewer_than_two_horizontal_joins"] == 0
    assert report["vertical_air_or_reversed_slab_contacts"] == 0


def test_free_pane_end_gets_one_inward_return_to_untouched_diagonal_jamb():
    c = Canvas(0, 0, 8, 8, 2)
    c.set(2, 5, 3, "bricks", "facade")
    c.set(3, 5, 3, "white_stained_glass_pane", "window")
    c.set(4, 5, 4, "bricks", "facade")
    allowed = {(3,5,3), (4,5,3), (3,5,4)}
    assert close_diagonal_pane_jambs(c, allowed, inward=(-1,0)) == 1
    connect_window_panes(c)
    assert c.get(3,5,4) and not c.get(4,5,3)
    assert c.palette[c.get(4,5,4)] == {"Name": "minecraft:bricks"}
    assert pane_perimeter_report(c)["fewer_than_two_horizontal_joins"] == 0
    assert close_diagonal_pane_jambs(c, allowed, inward=(-1,0)) == 0


def test_diagonal_jamb_repair_never_crosses_frame_bounds():
    c = Canvas(0, 0, 8, 8, 2)
    c.set(3,5,3,"glass_pane","window")
    c.set(4,5,4,"bricks","facade")
    assert close_diagonal_pane_jambs(c, {(3,5,3)}, inward=(-1,0)) == 0
    assert not c.get(3,5,4) and not c.get(4,5,3)
