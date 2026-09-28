from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from shapely.geometry import box


SCRIPT_PATH = Path(__file__).with_name("assemble_hill_voxcity_full_campus.py")
SPEC = importlib.util.spec_from_file_location("assemble_hill_voxcity_full_campus", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class RectangleAndMaskTests(unittest.TestCase):
    def test_parser_defaults_unmapped_hill_space_to_rangeland(self) -> None:
        args = module.build_parser().parse_args([])

        self.assertEqual(args.default_land_cover_class, "Rangeland")
        self.assertFalse(args.detect_ocean)
        self.assertFalse(args.dem_interpolation)

    def test_metric_rectangle_snaps_bounds_to_mesh_with_padding(self) -> None:
        geometry = box(100.2, 200.4, 104.1, 203.8)

        rect = module.metric_rectangle_from_geometry(
            geometry,
            metric_crs="EPSG:32618",
            meshsize=1.0,
            padding_m=0.5,
        )

        self.assertEqual(rect.bounds, (99.0, 199.0, 105.0, 205.0))
        self.assertEqual(rect.width_m, 6.0)
        self.assertEqual(rect.height_m, 6.0)

    def test_property_mask_uses_voxcity_south_up_row_order(self) -> None:
        rect = module.MetricRectangle(
            crs="EPSG:32618",
            minx=0.0,
            miny=0.0,
            maxx=4.0,
            maxy=3.0,
            meshsize=1.0,
        )
        southern_strip = box(1.0, 0.0, 3.0, 1.0)

        mask = module.rasterize_property_keep_mask(
            southern_strip,
            rect,
            (3, 4),
            boundary_m=0.0,
            all_touched=False,
        )

        expected = np.array(
            [
                [False, True, True, False],
                [False, False, False, False],
                [False, False, False, False],
            ],
            dtype=bool,
        )
        np.testing.assert_array_equal(mask, expected)

    def test_property_mask_boundary_preserves_nearby_cells(self) -> None:
        rect = module.MetricRectangle(
            crs="EPSG:32618",
            minx=0.0,
            miny=0.0,
            maxx=4.0,
            maxy=3.0,
            meshsize=1.0,
        )
        one_cell = box(1.0, 0.0, 2.0, 1.0)

        mask = module.rasterize_property_keep_mask(
            one_cell,
            rect,
            (3, 4),
            boundary_m=0.6,
            all_touched=False,
        )

        self.assertTrue(mask[0, 0])
        self.assertTrue(mask[0, 1])
        self.assertTrue(mask[0, 2])
        self.assertFalse(mask[2, 3])


class ClearExteriorCellsTests(unittest.TestCase):
    def test_clear_exterior_cells_only_zeros_geometry_bearing_layers(self) -> None:
        classes = np.ones((2, 3, 4), dtype=np.int8)
        heights = np.arange(6, dtype=float).reshape(2, 3) + 1.0
        ids = np.arange(6, dtype=np.int32).reshape(2, 3) + 10
        min_heights = np.empty((2, 3), dtype=object)
        for idx in np.ndindex(min_heights.shape):
            min_heights[idx] = [[0.0, 3.0]]
        land_cover = np.arange(6, dtype=np.int32).reshape(2, 3)
        dem = np.arange(6, dtype=float).reshape(2, 3) + 100.0
        canopy_top = np.ones((2, 3), dtype=float) * 12.0
        canopy_bottom = np.ones((2, 3), dtype=float) * 6.0
        city = SimpleNamespace(
            voxels=SimpleNamespace(classes=classes),
            buildings=SimpleNamespace(heights=heights, ids=ids, min_heights=min_heights),
            land_cover=SimpleNamespace(classes=land_cover.copy()),
            dem=SimpleNamespace(elevation=dem.copy()),
            tree_canopy=SimpleNamespace(top=canopy_top, bottom=canopy_bottom),
            extras={},
        )
        keep_mask = np.array(
            [
                [True, False, True],
                [False, True, False],
            ],
            dtype=bool,
        )

        stats = module.clear_exterior_cells(city, keep_mask)

        exterior = ~keep_mask
        self.assertEqual(stats["masked_cells"], 3)
        self.assertTrue(np.all(city.voxels.classes[exterior, :] == 0))
        self.assertTrue(np.all(city.voxels.classes[keep_mask, :] == 1))
        self.assertTrue(np.all(city.buildings.heights[exterior] == 0))
        self.assertTrue(np.all(city.buildings.ids[exterior] == 0))
        self.assertTrue(np.all(city.tree_canopy.top[exterior] == 0))
        self.assertTrue(np.all(city.tree_canopy.bottom[exterior] == 0))
        for cell in city.buildings.min_heights[exterior]:
            self.assertEqual(cell, [])
        np.testing.assert_array_equal(city.land_cover.classes, land_cover)
        np.testing.assert_array_equal(city.dem.elevation, dem)


if __name__ == "__main__":
    unittest.main()
