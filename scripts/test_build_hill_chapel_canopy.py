from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer


SCRIPT_PATH = Path(__file__).with_name("build_hill_chapel_canopy.py")
SPEC = importlib.util.spec_from_file_location("build_hill_chapel_canopy", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class CoordinateTests(unittest.TestCase):
    def test_projected_chapel_centroid_matches_world_landmark(self) -> None:
        if not module.terrain.DEFAULT_WORLD_MANIFEST.is_file():
            self.skipTest("Hill world manifest is absent")
        transform = module.terrain.WorldTransform.from_manifest(
            module.terrain.DEFAULT_WORLD_MANIFEST
        )
        to_metric = Transformer.from_crs("EPSG:4326", "EPSG:6347", always_xy=True)
        east, north = to_metric.transform(-75.6351593685645, 40.245103367709575)

        world_x, world_z = module.projected_to_world_xz(
            np.asarray([east]),
            np.asarray([north]),
            source_crs=CRS.from_epsg(6347),
            transform=transform,
        )

        np.testing.assert_allclose(
            [world_x[0], world_z[0]],
            module.terrain.CHAPEL_EXPECTED_WORLD_XZ,
            atol=0.00002,
        )


class GridTests(unittest.TestCase):
    def test_inference_rejects_small_and_thin_components(self) -> None:
        bounds = module.terrain.WorldBounds(0, 0, 20, 20)
        broad = []
        for z in np.arange(1.25, 4.25, 0.5):
            for x in np.arange(1.25, 4.25, 0.5):
                broad.append([x, z, 7.0 + 0.1 * x])
        thin = [[8.25, z, 10.0] for z in np.arange(1.25, 16.25, 0.5)]
        points = np.asarray(broad + thin, dtype=np.float32)

        trees, stats, _grids = module.infer_tree_candidates(
            points,
            bounds=bounds,
            resolution_m=0.5,
            minimum_height_m=3.0,
            suppression_radius_m=3.0,
            minimum_component_area_m2=6.0,
            minimum_component_width_m=2.0,
        )

        self.assertEqual(stats["accepted_component_count"], 1)
        self.assertEqual(stats["rejected_component_counts"]["width_below_minimum"], 1)
        self.assertGreaterEqual(len(trees), 1)
        self.assertTrue(all(tree["source_class"] == 1 for tree in trees))
        self.assertTrue(all(tree["species"] is None for tree in trees))

    def test_current_addition_guard_uses_profile_rotation(self) -> None:
        if not module.DEFAULT_PROFILE.is_file():
            self.skipTest("Chapel profile is absent")
        guard, record = module.load_addition_guard(module.DEFAULT_PROFILE)

        self.assertAlmostEqual(guard.area, 19.6 * 7.7, places=4)
        self.assertEqual(record["local_uv_bounds_m"], [-9.0, 20.8, 10.6, 28.5])
        self.assertEqual(record["rotation_degrees"], -8.5)

    def test_canopy_grid_uses_positive_z_rows_and_computes_p95(self) -> None:
        bounds = module.terrain.WorldBounds(0, 0, 2, 2)
        points = np.asarray(
            [
                [0.1, 0.1, 2.0],
                [0.2, 0.2, 4.0],
                [0.3, 0.3, 6.0],
                [1.6, 1.6, 8.0],
            ],
            dtype=np.float32,
        )

        maximum, p95, count = module.aggregate_canopy_grid(points, bounds, 1.0)

        self.assertEqual(count[0, 0], 3)
        self.assertEqual(count[1, 1], 1)
        self.assertEqual(maximum[0, 0], 6.0)
        self.assertAlmostEqual(float(p95[0, 0]), 5.8, places=5)
        self.assertEqual(p95[1, 1], 8.0)

    def test_empty_class_evidence_stays_empty(self) -> None:
        bounds = module.terrain.WorldBounds(-1, -1, 1, 1)
        maximum, p95, count = module.aggregate_canopy_grid(
            np.empty((0, 3), dtype=np.float32), bounds, 0.5
        )
        trees = module.derive_crown_seeds(
            p95,
            np.empty((0, 3), dtype=np.float32),
            np.empty((0,), dtype=np.uint8),
            bounds=bounds,
            resolution_m=0.5,
            minimum_height_m=3.0,
            suppression_radius_m=3.0,
        )

        self.assertFalse(np.any(maximum))
        self.assertFalse(np.any(count))
        self.assertEqual(trees, [])

    def test_crown_seeds_are_deterministic_and_suppressed_within_three_metres(self) -> None:
        bounds = module.terrain.WorldBounds(0, 0, 10, 10)
        canopy = np.zeros((20, 20), dtype=np.float32)
        canopy[4, 4] = 10.0
        canopy[4, 8] = 9.0  # 2 m away; suppressed by the taller maximum.
        canopy[14, 14] = 8.0
        points = np.asarray(
            [[2.25, 2.25, 10.0], [4.25, 2.25, 9.0], [7.25, 7.25, 8.0]],
            dtype=np.float32,
        )
        classes = np.asarray([5, 5, 4], dtype=np.uint8)

        trees = module.derive_crown_seeds(
            canopy,
            points,
            classes,
            bounds=bounds,
            resolution_m=0.5,
            minimum_height_m=3.0,
            suppression_radius_m=3.0,
        )

        self.assertEqual(len(trees), 2)
        self.assertEqual(trees[0]["height_m"], 10.0)
        self.assertEqual((trees[0]["x"], trees[0]["z"]), (2.25, 2.25))
        self.assertIn("uncertain", trees[0]["position_role"])


if __name__ == "__main__":
    unittest.main()
