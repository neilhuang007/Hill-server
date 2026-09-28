"""The photo-interpreted press box must not turn its entire stand into a wall."""

import json

import numpy as np
from build_hill_chapel_sample import ROLES, Canvas
from build_hill_current_pavilions import (
    PROPOSALS,
    SiteFrame,
    build_madden,
    connect_rails,
)
from campus_materials import audit_role_materials
from campus_study_io import material_roles
from campus_window_frames import pane_support_report


def test_elevated_press_box_keeps_open_support_and_connected_glazing():
    p = json.loads(PROPOSALS.read_text(encoding="utf-8"))["structures"][1]
    c = Canvas(912, -1024, 96, 80, 2)
    c.ground_heights = np.full((80, 96), 100, dtype=np.int16)
    f = SiteFrame(
        c,
        p["polygon_xz"]["coordinates"][0][0],
        p["axis_long_southwest"],
        p["axis_depth_southeast"],
    )
    build_madden(f, p)
    connect_rails(c)
    inside = f.mask([1, 0.75, 11, 2.75])
    assert inside.any()
    # Halfway between ground and the press box there is a usable open void.
    assert np.all(c.data[f.y(77) + 64][inside] == 0)
    panes = pane_support_report(c)
    assert panes["panes"] > 0
    assert panes["unsupported_components"] == 0
    assert (c.roles == ROLES.index("railing")).any()
    assert c.clipped == 0
    assert not audit_role_materials(material_roles(c))
