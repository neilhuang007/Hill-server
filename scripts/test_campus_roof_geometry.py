from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, Polygon, box

SCRIPT_PATH = Path(__file__).with_name("campus_roof_geometry.py")
SPEC = importlib.util.spec_from_file_location("campus_roof_geometry", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def face(
    polygon: Polygon,
    *,
    a: float = 0.0,
    b: float = 0.0,
    c: float = 10.0,
    surface_index: int = 0,
) -> module.RoofFace:
    heights = [a * float(x) + b * float(z) + c for x, z in polygon.exterior.coords]
    return module.RoofFace(
        polygon=polygon,
        a=a,
        b=b,
        c=c,
        min_h=min(heights),
        max_h=max(heights),
        source_semantics={"type": "RoofSurface"},
        part_id="test-part",
        shell_index=0,
        surface_index=surface_index,
    )


def building(
    footprint: Polygon, faces: list[module.RoofFace]
) -> module.MeasuredBuilding:
    return module.MeasuredBuilding(
        footprint=footprint,
        roof_faces=tuple(faces),
        source_base=0.0,
        source_max=max(item.max_h for item in faces),
        attrs={},
        parent_id="test",
        part_ids=("test-part",),
        source_sha256="0" * 64,
        ground_surface_count=1,
        roof_surface_count=len(faces),
        rejected_roof_face_count=0,
        rejected_roof_face_reasons={},
    )


class RoofRasterTests(unittest.TestCase):
    def test_pitched_roof_retains_height_gradient_and_face_indices(self) -> None:
        west = face(box(0, 0, 2, 2), a=1.0, c=10.0, surface_index=0)
        east = face(box(2, 0, 4, 2), a=-1.0, c=14.0, surface_index=1)

        result = module.rasterize_roof(
            building(box(0, 0, 4, 2), [west, east]), (0, 0, 4, 2)
        )

        np.testing.assert_allclose(
            result.heights,
            [[10.5, 11.5, 11.5, 10.5], [10.5, 11.5, 11.5, 10.5]],
        )
        np.testing.assert_array_equal(
            result.gradient_x,
            [[1.0, 1.0, -1.0, -1.0], [1.0, 1.0, -1.0, -1.0]],
        )
        np.testing.assert_array_equal(result.face_indices, [[0, 0, 1, 1], [0, 0, 1, 1]])
        self.assertEqual(result.coverage_report["missing_covered_columns"], 0)

    def test_overlaps_choose_highest_face_and_polygon_holes_stay_empty(self) -> None:
        outer = [(0, 0), (3, 0), (3, 3), (0, 3)]
        hole = [(1, 1), (2, 1), (2, 2), (1, 2)]
        low_with_hole = face(Polygon(outer, [hole]), c=10.0, surface_index=0)
        high_overlap = face(box(0, 0, 1, 3), c=12.0, surface_index=1)

        result = module.rasterize_roof(
            building(box(0, 0, 3, 3), [low_with_hole, high_overlap]),
            (0, 0, 3, 3),
        )

        np.testing.assert_allclose(result.heights[:, 0], 12.0)
        self.assertTrue(math.isnan(float(result.heights[1, 1])))
        self.assertEqual(result.face_indices[0, 0], 1)
        self.assertEqual(result.face_indices[1, 1], -1)
        self.assertTrue(result.missing_mask[1, 1])
        self.assertEqual(
            result.coverage_report,
            {
                "footprint_columns": 9,
                "covered_columns": 8,
                "missing_covered_columns": 1,
            },
        )


class CityJsonLoaderTests(unittest.TestCase):
    def test_coordinate_transform_preserves_ground_and_roof_holes(self) -> None:
        easting = 445_960.0
        northing = 4_455_150.0
        outer_xy = [(0, 0), (4, 0), (4, 4), (0, 4)]
        hole_xy = [(1, 1), (1, 3), (3, 3), (3, 1)]
        vertices = [
            [easting + x, northing + y, height]
            for height in (65.0, 70.0)
            for ring in (outer_xy, hole_xy)
            for x, y in ring
        ]
        # A vertical semantic roof is deliberate malformed input for the
        # reject counter. It must never become an extrapolated height plane.
        vertical_start = len(vertices)
        vertices.extend(
            [
                [easting + 4.0, northing + 0.0, 65.0],
                [easting + 4.0, northing + 4.0, 65.0],
                [easting + 4.0, northing + 4.0, 71.0],
                [easting + 4.0, northing + 0.0, 71.0],
            ]
        )
        cityjson = {
            "type": "CityJSON",
            "version": "2.0",
            "metadata": {
                "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/6347"
            },
            "vertices": vertices,
            "CityObjects": {
                "parent": {
                    "type": "Building",
                    "children": ["part-b", "part-a"],
                    "attributes": {"IMPRNAME": "Transform fixture"},
                },
                "part-b": {"type": "BuildingPart", "parents": ["parent"]},
                "part-a": {
                    "type": "BuildingPart",
                    "parents": ["parent"],
                    "geometry": [
                        {
                            "type": "Solid",
                            "lod": "2.2",
                            "boundaries": [
                                [
                                    [list(range(4)), list(range(4, 8))],
                                    [list(range(8, 12)), list(range(12, 16))],
                                    [list(range(vertical_start, vertical_start + 4))],
                                ]
                            ],
                            "semantics": {
                                "surfaces": [
                                    {"type": "GroundSurface", "fixture": "ground"},
                                    {"type": "RoofSurface", "fixture": "roof"},
                                ],
                                "values": [[0, 1, 1]],
                            },
                        }
                    ],
                },
            },
        }
        world_manifest = {
            "originEcefMetres": [
                1209506.3580558784,
                -4722746.0186042255,
                4098801.2033486697,
            ],
            "center": [40.24516, -75.63516],
            "blocksPerMetre": 1,
            "targetMinimumY": 70,
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cityjson_path = root / "fixture.city.json"
            cityjson_path.write_text(json.dumps(cityjson), encoding="utf-8")
            world_manifest_path = root / "world.json"
            world_manifest_path.write_text(json.dumps(world_manifest), encoding="utf-8")
            measured_manifest_path = root / "terrain.manifest.json"
            measured_manifest_path.write_text(
                json.dumps(
                    {
                        "voxelearth_manifest": {
                            "path": str(world_manifest_path),
                            "sha256": hashlib.sha256(
                                world_manifest_path.read_bytes()
                            ).hexdigest(),
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = module.load_measured_building(
                cityjson_path, "parent", measured_manifest_path
            )
            transform = module.anvil.WorldTransform.from_manifest(world_manifest_path)
            expected_first = transform.metric_to_block(
                Transformer.from_crs("EPSG:6347", "EPSG:4326", always_xy=True),
                easting,
                northing,
            )
            source_sha256 = hashlib.sha256(cityjson_path.read_bytes()).hexdigest()

        self.assertTrue(
            result.footprint.boundary.distance(Point(expected_first)) < 1e-8
        )
        self.assertEqual(len(result.footprint.interiors), 1)
        self.assertEqual(len(result.roof_faces), 1)
        self.assertEqual(len(result.roof_faces[0].polygon.interiors), 1)
        self.assertEqual(result.roof_faces[0].source_semantics["fixture"], "roof")
        self.assertEqual(result.part_ids, ("part-b", "part-a"))
        self.assertEqual(result.source_base, 65.0)
        self.assertEqual(result.source_max, 71.0)
        self.assertEqual(result.roof_surface_count, 2)
        self.assertEqual(result.rejected_roof_face_count, 1)
        self.assertEqual(
            result.rejected_roof_face_reasons, {"invalid_projected_polygon": 1}
        )
        self.assertEqual(result.source_sha256, source_sha256)

    @unittest.skipUnless(
        module.DEFAULT_CITYJSON.is_file()
        and module.DEFAULT_MEASURED_TERRAIN_MANIFEST.is_file(),
        "Academic Center Roofer inputs are absent",
    )
    def test_actual_academic_center_has_complete_roof_coverage(self) -> None:
        result = module.load_measured_building()

        self.assertEqual(result.attrs["IMPRNAME"], "ACADEMIC CENTER #25")
        self.assertEqual(len(result.part_ids), 2)
        self.assertEqual(result.ground_surface_count, 2)
        self.assertEqual(result.roof_surface_count, 72)
        self.assertEqual(len(result.roof_faces), 72)
        self.assertEqual(result.rejected_roof_face_count, 0)
        self.assertAlmostEqual(result.footprint.area, 3117.549983895695, places=6)
        self.assertAlmostEqual(result.source_base, 65.8799, places=4)
        self.assertAlmostEqual(result.source_max, 89.1534, places=4)
        self.assertEqual(
            result.source_sha256,
            "b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8",
        )
        self.assertEqual(
            sum(len(item.polygon.interiors) for item in result.roof_faces), 2
        )

        bounds = (9, 33, 95, 117)
        raster = module.rasterize_roof(result, bounds)
        self.assertGreater(raster.coverage_report["covered_columns"], 2_900)
        self.assertEqual(raster.coverage_report["missing_covered_columns"], 0)


if __name__ == "__main__":
    unittest.main()
