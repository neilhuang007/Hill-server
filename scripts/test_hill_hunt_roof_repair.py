import numpy as np
from build_hill_hunt_hall import repair_north_roof
from campus_roof_geometry import rasterize_roof
from shapely.geometry import box
from test_campus_roof_geometry import building, face


def test_north_correction_preserves_real_south_arcade_and_raw_source():
    source = building(
        box(0, 0, 8, 20),
        [
            face(box(0, 0, 8, 3), c=63),
            face(box(0, 3, 8, 16), b=0.1, c=81, surface_index=1),
            face(box(0, 16, 8, 20), c=70.1, surface_index=2),
        ],
    )
    raw = rasterize_roof(source, (-1, -1, 9, 21), resolution=0.5)
    original = [a.copy() for a in (raw.heights, raw.face_indices, raw.gradient_z)]
    profile = {
        "geometry": {
            "origin_xz_m": [0, 0],
            "axis_degrees": 0,
            "north_roof_repair": {
                "maximum_v_m": 5,
                "reject_below_navd88_m": 75,
                "method": "explicit photo interpretation",
            },
        }
    }
    repaired, evidence = repair_north_roof(raw, source, profile)
    north = raw.footprint_mask & (raw.heights == 63)
    south = raw.footprint_mask & (raw.heights == 70.1)
    assert evidence["area_m2"] == 24
    assert np.all(repaired.heights[north] >= 81)
    np.testing.assert_array_equal(repaired.heights[south], raw.heights[south])
    for actual, expected in zip(
        (raw.heights, raw.face_indices, raw.gradient_z), original
    ):
        np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(repaired.footprint_mask, raw.footprint_mask)
    np.testing.assert_array_equal(repaired.missing_mask, raw.missing_mask)
