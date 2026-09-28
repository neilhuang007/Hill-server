import numpy as np

from audit_hill_demo_walks import surface_hint, standing_height


def test_actual_road_crown_controls_layer_not_distant_endpoints():
    coords = np.array([[0, 80, 0], [1, 87, 0], [2, 80, 0], [1, 95, 0]])
    ground = surface_hint(coords, np.array([0, 1, 0, 2]),
                          ["terrain", "pavement", "vegetation"], 0, 0)
    assert ground[0].tolist()[:3] == [80, 87, 80]
    boxes = [(1, 87, 0, 2, 88, 1)]
    assert standing_height(boxes, 1.5, .5, float(ground[0, 1]+1)) == 88
    assert standing_height(boxes, 1.5, .5, 81) is None


def test_actual_hole_and_low_ceiling_still_fail():
    assert standing_height([], .5, .5, 81) is None
    boxes = [(0, 80, 0, 1, 81, 1), (0, 82, 0, 1, 84, 1)]
    assert standing_height(boxes, .5, .5, 81) is None


def test_half_slab_still_requires_real_support():
    assert standing_height([(0, 80, 0, 1, 80.5, 1)], .5, .5, 81) == 80.5
