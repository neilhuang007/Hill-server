from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_PATH = Path(__file__).with_name("campus_paving.py")
SPEC = importlib.util.spec_from_file_location("campus_paving", SCRIPT_PATH)
paving = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = paving
SPEC.loader.exec_module(paving)


class FakeCanvas:
    def __init__(self, width: int, depth: int, scale: int = 2) -> None:
        self.x_min = 0
        self.z_min = 0
        self.y_min = 0
        self.scale = scale
        self.data = np.zeros((32, depth, width), dtype=np.uint16)
        self.roles = np.zeros_like(self.data, dtype=np.uint8)
        self.palette = [{"Name": "minecraft:air"}]

    def state(self, name: str, properties: dict[str, str] | None = None) -> int:
        name = name if name.startswith("minecraft:") else f"minecraft:{name}"
        entry: dict[str, object] = {"Name": name}
        if properties:
            entry["Properties"] = dict(properties)
        key = json.dumps(entry, sort_keys=True)
        for index, existing in enumerate(self.palette):
            if json.dumps(existing, sort_keys=True) == key:
                return index
        self.palette.append(entry)
        return len(self.palette) - 1


def _state(canvas: FakeCanvas, y: int, z: int, x: int) -> dict[str, object]:
    return canvas.palette[int(canvas.data[y, z, x])]


def _sloped_road_canvas() -> tuple[FakeCanvas, np.ndarray, np.ndarray]:
    """Five-wide measured road with one coherent east-facing half-step."""

    canvas = FakeCanvas(width=5, depth=5)
    target_surfaces = np.tile(
        np.asarray([10.0, 10.4, 10.8, 11.1, 11.5], dtype=np.float64),
        (5, 1),
    )
    elevations = target_surfaces / canvas.scale
    heights = np.rint(elevations * canvas.scale).astype(np.int16) - 1
    road_state = canvas.state("gray_concrete")
    substrate_state = canvas.state("stone")
    pavement_role = paving.DEFAULT_ROLE_NAMES.index("pavement")
    terrain_role = paving.DEFAULT_ROLE_NAMES.index("terrain")
    for z, x in np.ndindex(heights.shape):
        height = int(heights[z, x])
        canvas.data[:height, z, x] = substrate_state
        canvas.roles[:height, z, x] = terrain_role
        canvas.data[height, z, x] = road_state
        canvas.roles[height, z, x] = pavement_role
    return canvas, elevations, heights


class CampusPavingTests(unittest.TestCase):
    def test_quantizes_measured_surface_without_flattening_and_uses_coherent_families(
        self,
    ) -> None:
        canvas = FakeCanvas(width=4, depth=1)
        elevations = np.asarray([[5.5, 5.64, 5.81, 5.99]], dtype=np.float64)
        heights = np.rint(elevations * canvas.scale).astype(np.int16) - 1
        path_state = canvas.state("smooth_stone")
        road_state = canvas.state("gray_concrete")
        for x, height in enumerate(heights[0]):
            canvas.data[int(height), 0, x] = path_state if x < 2 else road_state
            canvas.roles[int(height), 0, x] = paving.DEFAULT_ROLE_NAMES.index(
                "pavement"
            )

        stats = paving.smooth_exposed_measured_pavement(
            canvas,
            elevations,
            heights,
            vertical_offset=0.0,
        )

        self.assertEqual(stats["smoothed_cell_count"], 4)
        self.assertEqual(stats["family_cell_counts"], {"footpath": 2, "road": 2})
        self.assertEqual(stats["representation_cell_counts"]["full_block"], 2)
        self.assertEqual(stats["representation_cell_counts"]["bottom_slab"], 2)
        self.assertEqual(stats["representation_cell_counts"]["top_slab"], 0)
        self.assertLessEqual(stats["max_surface_residual_blocks"], 0.25)
        self.assertGreater(stats["distinct_quantized_surface_count"], 1)

        self.assertEqual(_state(canvas, 10, 0, 0)["Name"], "minecraft:smooth_stone")
        self.assertEqual(_state(canvas, 10, 0, 1)["Name"], "minecraft:smooth_stone")
        self.assertEqual(
            _state(canvas, 11, 0, 1),
            {
                "Name": "minecraft:smooth_stone_slab",
                "Properties": {"type": "bottom", "waterlogged": "false"},
            },
        )
        self.assertEqual(
            _state(canvas, 11, 0, 2),
            {
                "Name": "minecraft:polished_deepslate_slab",
                "Properties": {"type": "bottom", "waterlogged": "false"},
            },
        )
        self.assertEqual(
            _state(canvas, 11, 0, 3)["Name"], "minecraft:polished_deepslate"
        )

    def test_skips_non_pavement_and_never_overwrites_protected_cells(self) -> None:
        canvas = FakeCanvas(width=3, depth=1)
        elevations = np.asarray([[5.64, 5.64, 5.64]], dtype=np.float64)
        heights = np.rint(elevations * canvas.scale).astype(np.int16) - 1
        path_state = canvas.state("smooth_stone")
        grass_state = canvas.state("grass_block")
        door_state = canvas.state(
            "dark_oak_door",
            {
                "facing": "south",
                "half": "lower",
                "hinge": "left",
                "open": "false",
                "powered": "false",
            },
        )
        pavement_role = paving.DEFAULT_ROLE_NAMES.index("pavement")
        terrain_role = paving.DEFAULT_ROLE_NAMES.index("terrain")
        door_role = paving.DEFAULT_ROLE_NAMES.index("door")
        canvas.data[10, 0, 0] = path_state
        canvas.roles[10, 0, 0] = pavement_role
        canvas.data[11, 0, 0] = door_state
        canvas.roles[11, 0, 0] = door_role
        canvas.data[10, 0, 1] = grass_state
        canvas.roles[10, 0, 1] = terrain_role
        canvas.data[10, 0, 2] = path_state
        canvas.roles[10, 0, 2] = pavement_role
        before_door = canvas.data[11, 0, 0]

        stats = paving.smooth_exposed_measured_pavement(
            canvas,
            elevations,
            heights,
            vertical_offset=0.0,
        )

        self.assertEqual(stats["smoothed_cell_count"], 1)
        self.assertEqual(stats["skipped_not_exposed"], 1)
        self.assertEqual(stats["skipped_not_pavement"], 1)
        self.assertEqual(canvas.data[11, 0, 0], before_door)
        self.assertEqual(canvas.roles[11, 0, 0], door_role)
        self.assertEqual(_state(canvas, 10, 0, 1)["Name"], "minecraft:grass_block")

    def test_places_supported_stair_run_uphill_without_moving_measured_terraces(
        self,
    ) -> None:
        canvas, elevations, heights = _sloped_road_canvas()

        stats = paving.smooth_exposed_measured_pavement(
            canvas,
            elevations,
            heights,
            vertical_offset=0.0,
        )

        self.assertEqual(stats["stair_count"], 3)
        self.assertEqual(stats["stair_facing_counts"]["east"], 3)
        self.assertEqual(stats["representation_cell_counts"]["bottom_stair"], 3)
        for z in range(1, 4):
            self.assertEqual(
                _state(canvas, 10, z, 2),
                {
                    "Name": "minecraft:polished_deepslate_stairs",
                    "Properties": {
                        "facing": "east",
                        "half": "bottom",
                        "shape": "straight",
                        "waterlogged": "false",
                    },
                },
            )
            # The stair's low tread is 10.5 (matching x=1) and its high tread
            # is 11.0 (matching x=3); both measured terrace states are kept.
            self.assertEqual(
                _state(canvas, 10, z, 1)["Name"],
                "minecraft:polished_deepslate_slab",
            )
            self.assertEqual(
                _state(canvas, 10, z, 3)["Name"],
                "minecraft:polished_deepslate",
            )
        self.assertAlmostEqual(stats["stair_max_tread_residual_blocks"], 0.3)
        self.assertAlmostEqual(stats["stair_mean_tread_residual_blocks"], 0.25)
        self.assertAlmostEqual(stats["stair_max_mean_plane_residual_blocks"], 0.05)
        self.assertAlmostEqual(stats["max_surface_residual_blocks"], 0.3)

    def test_keeps_full_blocks_when_stair_transition_has_no_substrate(self) -> None:
        canvas, elevations, heights = _sloped_road_canvas()
        for z in range(1, 4):
            canvas.data[9, z, 2] = 0
            canvas.roles[9, z, 2] = 0

        stats = paving.smooth_exposed_measured_pavement(
            canvas,
            elevations,
            heights,
            vertical_offset=0.0,
        )

        self.assertEqual(stats["stair_count"], 0)
        self.assertEqual(stats["stair_rejection_counts"]["unsupported_substrate"], 3)
        for z in range(1, 4):
            self.assertEqual(
                _state(canvas, 10, z, 2)["Name"],
                "minecraft:polished_deepslate",
            )


if __name__ == "__main__":
    unittest.main()
