from __future__ import annotations

import importlib.util
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import geopandas as gpd
import trimesh
from pyproj import Transformer
from shapely.geometry import box


SCRIPT_PATH = Path(__file__).with_name("generate_hill_roofer_building_overlay.py")
SPEC = importlib.util.spec_from_file_location(
    "generate_hill_roofer_building_overlay", SCRIPT_PATH
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
module.ensure_voxcity_on_path(module.VOXCITY_SRC)


class AxisAndScaleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.domain = module.MetricDomain(
            crs="EPSG:6347",
            min_east_m=445900.0,
            min_north_m=4455100.0,
            max_east_m=445920.0,
            max_north_m=4455120.0,
            meshsize_m=1.0,
        )

    def test_official_voxcity_transform_is_north_east_up_at_one_metre(self) -> None:
        transform, shape, _vertices = module.make_voxcity_transform(self.domain)
        self.assertEqual(shape, (20, 20))

        anchor = np.array([445910.0, 4455110.0, 25.0, 1.0])
        base = transform @ anchor
        east = transform @ (anchor + np.array([1.0, 0.0, 0.0, 0.0]))
        north = transform @ (anchor + np.array([0.0, 1.0, 0.0, 0.0]))
        up = transform @ (anchor + np.array([0.0, 0.0, 1.0, 0.0]))

        np.testing.assert_allclose(east - base, [0.0, 1.0, 0.0, 0.0], atol=2e-3)
        np.testing.assert_allclose(north - base, [1.0, 0.0, 0.0, 0.0], atol=2e-3)
        np.testing.assert_allclose(up - base, [0.0, 0.0, 1.0, 0.0], atol=1e-9)

    def test_building_only_voxelization_has_expected_scale_and_no_network(self) -> None:
        # x=east width 2 m, y=north width 3 m, z=up height 4 m.
        mesh = trimesh.creation.box(extents=(2.0, 3.0, 4.0))
        mesh.apply_translation((445906.0, 4455107.5, 12.0))
        metadata = {
            "test-building": {
                "roofer_id": "test-building",
                "name": "Test Building",
            }
        }

        with mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("building-only overlay attempted network access"),
        ):
            result = module.voxelize_groups(
                [("test-building-0", mesh)],
                group_to_parent={"test-building-0": "test-building"},
                metadata=metadata,
                domain=self.domain,
                property_geometry=box(*self.domain.bounds),
                property_boundary_m=0.0,
                mask_all_touched=False,
            )

        cells = result.occupied_neu
        spans = cells.max(axis=0) - cells.min(axis=0) + 1
        np.testing.assert_array_equal(spans, [3, 2, 4])
        self.assertEqual(result.stats["input_parent_buildings"], 1)
        self.assertEqual(result.stats["buildings_with_voxels"], 1)
        self.assertTrue(np.all(result.building_ids == 1))


class FullCampusIdentityTests(unittest.TestCase):
    def test_full_roofer_obj_parts_map_to_108_stable_parent_buildings(self) -> None:
        if not (
            module.DEFAULT_OBJ.is_file()
            and module.DEFAULT_CITYJSON.is_file()
            and module.DEFAULT_FOOTPRINTS.is_file()
        ):
            self.skipTest("full Hill Roofer trial assets are not present")

        metadata, child_to_parent = module.load_roofer_metadata(
            module.DEFAULT_FOOTPRINTS,
            module.DEFAULT_CITYJSON,
            metric_crs=module.DEFAULT_METRIC_CRS,
        )
        group_names = module.read_obj_object_names(module.DEFAULT_OBJ)
        mapping = module.map_group_parents(group_names, metadata, child_to_parent)

        self.assertEqual(len(group_names), 110)
        self.assertEqual(len(metadata), 108)
        self.assertEqual(len(set(mapping.values())), 108)
        self.assertGreaterEqual(len(set(mapping.values())), 79)

    def test_npz_writer_is_byte_deterministic_and_mask_is_explicit(self) -> None:
        arrays = {
            "occupied_neu": np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.int32),
            "building_edit_neu": np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.int32),
            "building_ids": np.asarray([1, 2], dtype=np.uint16),
        }
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.npz"
            second = Path(directory) / "second.npz"
            module.write_deterministic_npz(first, arrays)
            module.write_deterministic_npz(second, arrays)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with np.load(first, allow_pickle=False) as archive:
                np.testing.assert_array_equal(
                    archive["occupied_neu"], archive["building_edit_neu"]
                )


class VoxelEarthDomainTests(unittest.TestCase):
    def test_manifest_inclusive_bounds_preserve_full_world_dimensions(self) -> None:
        to_lonlat = Transformer.from_crs("EPSG:6347", "EPSG:4326", always_xy=True)
        lon, lat = to_lonlat.transform(445900.0, 4455100.0)
        payload = {
            "axis": "+X east, +Y up, +Z south (north is -Z)",
            "center": [lat, lon],
            "metresPerBlock": 1,
            "originEcefMetres": module.wgs84_latlon_to_ecef(lat, lon, 0.0).tolist(),
            "result": {
                "minimumBlock": [-2, 70, -3],
                "maximumBlock": [4, 90, 5],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            domain, alignment = module.domain_from_voxelearth_manifest(
                path,
                metric_crs="EPSG:6347",
                meshsize_m=1.0,
            )

        self.assertEqual(domain.width_m, 7.0)
        self.assertEqual(domain.height_m, 9.0)
        self.assertEqual(alignment["world_axis"], payload["axis"])

    def test_named_footprint_centroids_match_java_ecef_world_positions(self) -> None:
        if not (
            module.DEFAULT_FOOTPRINTS.is_file()
            and module.DEFAULT_VOXELEARTH_MANIFEST.is_file()
        ):
            self.skipTest("Hill footprints or VoxelEarth v11 manifest are absent")

        with module.DEFAULT_VOXELEARTH_MANIFEST.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        footprints = gpd.read_file(module.DEFAULT_FOOTPRINTS).to_crs(
            module.DEFAULT_METRIC_CRS
        )
        footprints = footprints.set_index("ROOFER_ID")

        # Fixed reference values were produced by the compiled Java
        # GeoReference.latLonToMinecraftMetres implementation used by v11.
        expected_xz = {
            "16001511600623C-ba74e78741": (-172.270556419467, 31.138783878190978),
            "16001511600610C-e7f1a01cbc": (-174.3154984091707, -24.933044218463145),
            "1600151160068C-6108d587dc": (0.053723935398621525, 6.2884190576462995),
        }
        for roofer_id, expected in expected_xz.items():
            centroid = footprints.loc[roofer_id].geometry.centroid
            world = module.metric_east_north_to_voxelearth_world_xyz(
                centroid.x,
                centroid.y,
                metric_crs=module.DEFAULT_METRIC_CRS,
                origin_ecef_m=manifest["originEcefMetres"],
                blocks_per_metre=float(manifest["blocksPerMetre"]),
            )
            np.testing.assert_allclose(world[[0, 2]], expected, atol=1e-6, rtol=0.0)

        feroe = footprints.loc["16001511600623C-ba74e78741"].geometry.centroid
        to_metric = Transformer.from_crs(
            "EPSG:4326", module.DEFAULT_METRIC_CRS, always_xy=True
        )
        center_e, center_n = to_metric.transform(
            manifest["center"][1], manifest["center"][0]
        )
        naive_xz = np.asarray([feroe.x - center_e, center_n - feroe.y])
        exact_xz = np.asarray(expected_xz["16001511600623C-ba74e78741"])
        self.assertGreater(float(np.linalg.norm(naive_xz - exact_xz)), 1.0)


if __name__ == "__main__":
    unittest.main()
