from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS
from shapely.geometry import box


SCRIPT_PATH = Path(__file__).with_name("build_hill_measured_terrain.py")
SPEC = importlib.util.spec_from_file_location("build_hill_measured_terrain", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class WorldGridTests(unittest.TestCase):
    def test_raster_rows_follow_positive_world_z(self) -> None:
        bounds = module.WorldBounds(-2, -3, 2, 1)
        southern_world_strip = box(-1.0, -3.0, 1.0, -2.0)

        mask = module.rasterize_geometry_mask(southern_world_strip, bounds)

        expected = np.array(
            [
                [False, True, True, False],
                [False, False, False, False],
                [False, False, False, False],
                [False, False, False, False],
            ]
        )
        np.testing.assert_array_equal(mask, expected)

    def test_chapel_landmark_matches_voxelearth_transform(self) -> None:
        if not (
            module.DEFAULT_WORLD_MANIFEST.is_file()
            and module.DEFAULT_BUILDINGS.is_file()
        ):
            self.skipTest("Hill transform sources are not present")
        transform = module.WorldTransform.from_manifest(module.DEFAULT_WORLD_MANIFEST)

        result = module.validate_chapel_landmark(module.DEFAULT_BUILDINGS, transform)

        self.assertLess(result["horizontal_error_blocks"], 0.00001)
        np.testing.assert_allclose(
            result["actual_world_xz"], module.CHAPEL_EXPECTED_WORLD_XZ, atol=0.00001
        )


class MaterialTests(unittest.TestCase):
    def test_unknown_space_defaults_to_grass_and_paths_stay_distinct_from_roads(self) -> None:
        bounds = module.WorldBounds(0, 0, 5, 4)
        surface_features = [
            module.SurfaceFeature("path", box(1, 0, 2, 4), "test", "path", ""),
            module.SurfaceFeature("road", box(3, 0, 4, 4), "test", "road", ""),
        ]

        materials, stats = module.rasterize_materials(surface_features, bounds)

        self.assertTrue(np.all(materials[:, 0] == module.MATERIALS["grass"]["id"]))
        self.assertTrue(np.all(materials[:, 1] == module.MATERIALS["path"]["id"]))
        self.assertTrue(np.all(materials[:, 3] == module.MATERIALS["road"]["id"]))
        self.assertEqual(stats["cell_counts"]["grass"], 12)
        self.assertNotEqual(
            module.MATERIALS["path"]["id"], module.MATERIALS["road"]["id"]
        )

    def test_osm_surface_classification_preserves_sports_and_hardscape_semantics(self) -> None:
        self.assertEqual(
            module.classify_surface({"highway": "footway"}, "hard"), "path"
        )
        self.assertEqual(
            module.classify_surface({"highway": "service"}, "hard"), "road"
        )
        self.assertEqual(
            module.classify_surface({"amenity": "parking"}, "hard"), "parking"
        )
        self.assertEqual(
            module.classify_surface({"leisure": "pitch", "sport": "tennis"}, "grass"),
            "tennis",
        )
        self.assertEqual(module.classify_surface({}, "grass"), "grass")


class DemAndDatumTests(unittest.TestCase):
    def test_npz_preserves_scalar_origins_and_is_deterministic(self) -> None:
        arrays = {
            "ground_y": np.asarray([[90, 91]], dtype=np.int16),
            "x_min": np.asarray(-40, dtype=np.int32),
        }
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.npz"
            second = Path(directory) / "second.npz"
            module.write_deterministic_npz(first, arrays)
            module.write_deterministic_npz(second, arrays)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with np.load(first, allow_pickle=False) as archive:
                self.assertEqual(archive["x_min"].shape, ())
                self.assertEqual(archive["x_min"].item(), -40)

    def test_dem_is_bilinearly_sampled_at_block_centres(self) -> None:
        if not module.DEFAULT_WORLD_MANIFEST.is_file():
            self.skipTest("Hill transform manifest is not present")
        transform = module.WorldTransform.from_manifest(module.DEFAULT_WORLD_MANIFEST)
        bounds = module.WorldBounds(-2, -2, 2, 2)
        target_crs = CRS.from_epsg(6347)
        sample_x, sample_y = module.block_centres_to_crs(transform, bounds, target_crs)
        min_x = float(np.floor(sample_x.min()) - 3)
        max_y = float(np.ceil(sample_y.max()) + 3)
        raster_transform = Affine(1.0, 0.0, min_x, 0.0, -1.0, max_y)
        values = np.full((12, 12), 61.75, dtype=np.float32)

        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            dem_path = directory_path / "constant-dem.tif"
            with rasterio.open(
                dem_path,
                "w",
                driver="GTiff",
                height=values.shape[0],
                width=values.shape[1],
                count=1,
                dtype="float32",
                crs=target_crs,
                transform=raster_transform,
                nodata=-999999.0,
            ) as destination:
                destination.write(values, 1)

            elevation, manifest = module.sample_dem_at_block_centres(
                transform,
                bounds,
                requested_dem=dem_path,
                default_dem=dem_path,
                tile_dir=directory_path,
            )

        np.testing.assert_allclose(elevation, 61.75, atol=1e-5)
        self.assertEqual(manifest["nodata_sample_count"], 0)
        self.assertIn("x+0.5", manifest["sampling"])

    def test_datum_evidence_uses_one_robust_global_median(self) -> None:
        payload = {
            "overlay": {
                "anchors": [
                    {"source_column_coverage": 1.0, "vertical_offset": 24.0},
                    {"source_column_coverage": 0.95, "vertical_offset": 24.5},
                    {"source_column_coverage": 0.2, "vertical_offset": 31.0},
                    {"source_column_coverage": 1.0, "vertical_offset": -8.0},
                ]
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = module.datum_evidence(path, 24.25)

        self.assertEqual(result["accepted_anchor_count"], 2)
        self.assertEqual(result["accepted_anchor_median_blocks"], 24.25)
        self.assertEqual(result["chosen_minus_evidence_median_blocks"], 0.0)
        self.assertIn("no per-building shifts", result["scope"])


if __name__ == "__main__":
    unittest.main()
