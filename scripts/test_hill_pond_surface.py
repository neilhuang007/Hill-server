import numpy as np
from shapely.geometry import Polygon

from prepare_hill_campus_terrain_v2 import constrain_pond


def test_measured_pond_is_level_without_flattening_shore_or_island():
    elevations = np.arange(64, dtype=float).reshape(8, 8) / 10 + 54
    ids = np.ones((8, 8), dtype=np.uint8)
    polygon = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)],
                      holes=[[(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5)]])
    updated, materials, report = constrain_pond(
        elevations, ids, bounds_m=(0, 0, 4, 4), polygon=polygon, level_m=55, water_id=10,
    )
    assert report["columns"] == 12
    assert np.all(updated[materials == 10] == 55)
    np.testing.assert_array_equal(updated[materials != 10], elevations[materials != 10])
    assert report["outside_polygon_unchanged"]
    assert materials[3, 3] == 1
