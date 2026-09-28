from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box

SCRIPTS = Path(__file__).parent
ROOF_SPEC = importlib.util.spec_from_file_location(
    "campus_roof_geometry", SCRIPTS / "campus_roof_geometry.py"
)
roof = importlib.util.module_from_spec(ROOF_SPEC)
assert ROOF_SPEC.loader is not None
sys.modules[ROOF_SPEC.name] = roof
ROOF_SPEC.loader.exec_module(roof)

SHELL_SPEC = importlib.util.spec_from_file_location(
    "campus_measured_shell", SCRIPTS / "campus_measured_shell.py"
)
shell = importlib.util.module_from_spec(SHELL_SPEC)
assert SHELL_SPEC.loader is not None
sys.modules[SHELL_SPEC.name] = shell
SHELL_SPEC.loader.exec_module(shell)


class FakeCanvas:
    def __init__(
        self,
        *,
        scale: int = 2,
        x_min: int = -20,
        z_min: int = -20,
        width: int = 80,
        depth: int = 80,
        ground_y: int = -1,
    ) -> None:
        self.scale = scale
        self.x_min = x_min
        self.z_min = z_min
        self.width = width
        self.depth = depth
        self.y_min = -64
        self.y_max = 320
        self.clipped = 0
        self.default_ground_y = ground_y
        self.blocks: dict[
            tuple[int, int, int], tuple[str, str, tuple[tuple[str, str], ...]]
        ] = {}
        for z in range(z_min, z_min + depth):
            for x in range(x_min, x_min + width):
                self.blocks[(x, ground_y, z)] = (
                    "minecraft:grass_block",
                    "terrain",
                    (),
                )

    def set(
        self,
        x: int,
        y: int,
        z: int,
        name: str,
        role: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        if not (
            self.x_min <= x < self.x_min + self.width
            and self.z_min <= z < self.z_min + self.depth
            and self.y_min <= y < self.y_max
        ):
            self.clipped += 1
            return
        if name == "minecraft:air":
            self.blocks.pop((x, y, z), None)
            return
        self.blocks[(x, y, z)] = (
            name,
            role,
            tuple(sorted((properties or {}).items())),
        )

    def get(self, x: int, y: int, z: int) -> int:
        return int((x, y, z) in self.blocks)

    def ground_at(self, _x: int, _z: int) -> int:
        return self.default_ground_y


def roof_face(
    polygon: Polygon,
    *,
    a: float = 0.0,
    b: float = 0.0,
    c: float = 2.0,
    index: int = 0,
) -> roof.RoofFace:
    vertex_heights = [a * x + b * z + c for x, z in polygon.exterior.coords]
    return roof.RoofFace(
        polygon=polygon,
        a=a,
        b=b,
        c=c,
        min_h=min(vertex_heights),
        max_h=max(vertex_heights),
        source_semantics={"type": "RoofSurface"},
        part_id="fixture-part",
        shell_index=0,
        surface_index=index,
    )


def measured_building(
    footprint: Polygon, faces: list[roof.RoofFace], *, source_base: float = 0.0
) -> roof.MeasuredBuilding:
    return roof.MeasuredBuilding(
        footprint=footprint,
        roof_faces=tuple(faces),
        source_base=source_base,
        source_max=max(face.max_h for face in faces),
        attrs={},
        parent_id="fixture-parent",
        part_ids=("fixture-part",),
        source_sha256="0" * 64,
        ground_surface_count=1,
        roof_surface_count=len(faces),
        rejected_roof_face_count=0,
        rejected_roof_face_reasons={},
    )


class MeasuredShellTests(unittest.TestCase):
    def test_copper_roof_preserves_stairs_and_slab_representation(self):
        footprint = box(0, 0, 4, 3)
        building = measured_building(footprint, [roof_face(footprint, a=0.7, c=2.2)])
        raster = roof.rasterize_roof(building, (0, 0, 4, 3), resolution=0.5)
        copper = FakeCanvas()
        stone = FakeCanvas()
        shell.build_measured_shell(
            copper, building, raster, vertical_offset=0, roof_family="waxed_cut_copper"
        )
        shell.build_measured_shell(
            stone, building, raster, vertical_offset=0, roof_family="stone_brick"
        )
        first = {
            p: (n, r, props)
            for p, (n, r, props) in copper.blocks.items()
            if r == "roof"
        }
        second = {
            p: (n, r, props) for p, (n, r, props) in stone.blocks.items() if r == "roof"
        }
        self.assertEqual(set(first), set(second))
        self.assertTrue(any(n.endswith("_stairs") for n, _, _ in first.values()))
        for position, (name, role, properties) in first.items():
            self.assertIn(
                name,
                {
                    "minecraft:waxed_cut_copper",
                    "minecraft:waxed_cut_copper_slab",
                    "minecraft:waxed_cut_copper_stairs",
                },
            )
            self.assertEqual(properties, second[position][2])

    def test_roof_substrate_seals_risers_without_lifting_roof_or_covering_court(self):
        footprint = Polygon(
            [(0, 0), (6, 0), (6, 6), (0, 6)], [[(2, 2), (4, 2), (4, 4), (2, 4)]]
        )
        building = measured_building(footprint, [roof_face(footprint, a=0.8, c=6)])
        raster = roof.rasterize_roof(building, (0, 0, 6, 6), resolution=0.25)
        plain, backed = FakeCanvas(scale=4), FakeCanvas(scale=4)
        reference = shell.build_measured_shell(
            plain, building, raster, vertical_offset=0
        )
        result = shell.build_measured_shell(
            backed, building, raster, vertical_offset=0, roof_backing_metres=0.4
        )
        np.testing.assert_array_equal(result.roof_block_y, reference.roof_block_y)
        for row, column in np.argwhere(result.active_mask):
            top = int(result.roof_block_y[row, column])
            self.assertEqual(
                backed.blocks[(int(column), top, int(row))],
                plain.blocks[(int(column), top, int(row))],
            )
            self.assertEqual(
                backed.blocks[(int(column), top - 1, int(row))][0],
                "minecraft:deepslate_tiles",
            )
        self.assertNotIn((12, 5, 12), backed.blocks)  # courtyard remains open
        self.assertNotIn((4, 5, 4), backed.blocks)  # occupied volume stays hollow
        self.assertEqual(result.clipped_writes, 0)

    def test_pitched_shell_is_hollow_with_one_floor_and_full_foundation(self) -> None:
        footprint = box(0, 0, 3, 3)
        building = measured_building(footprint, [roof_face(footprint, a=0.5, c=2.0)])
        raster = roof.rasterize_roof(building, (0, 0, 3, 3), resolution=0.5)
        canvas = FakeCanvas()

        result = shell.build_measured_shell(
            canvas, building, raster, vertical_offset=0.0
        )

        self.assertEqual(result.floor_y, -1)
        self.assertEqual((result.floor_y + 1) / canvas.scale, building.source_base)
        self.assertEqual(result.world_bounds_blocks, (0, 0, 6, 6))
        self.assertEqual(result.foundation_column_count, 36)
        self.assertEqual(result.skipped_counts["buried_at_measured_grade"], 0)
        self.assertEqual(result.clipped_writes, 0)
        for row, column in zip(*np.nonzero(result.active_mask), strict=True):
            x, z = int(column), int(row)
            self.assertEqual(canvas.blocks[(x, -3, z)][0], "minecraft:bricks")
            self.assertEqual(canvas.blocks[(x, -2, z)][0], "minecraft:bricks")
            self.assertEqual(canvas.blocks[(x, -1, z)][0], "minecraft:smooth_stone")

        # This is an interior slab column: air remains between its single floor
        # and roof, rather than an inferred upper floor or solid mass.
        self.assertFalse(result.exterior_wall_mask[2, 2])
        self.assertFalse(result.internal_wall_mask[2, 2])
        self.assertNotIn((2, 1, 2), canvas.blocks)
        top_y = int(result.roof_block_y[2, 2])
        self.assertEqual(
            canvas.blocks[(2, top_y, 2)][0], "minecraft:deepslate_tile_slab"
        )

        self.assertGreater(result.roof_representation_counts["bottom_stair"], 0)
        self.assertGreater(result.roof_representation_counts["bottom_slab"], 0)
        self.assertGreater(result.roof_representation_counts["full_block"], 0)
        self.assertEqual(set(result.stair_facing_counts), {"east"})
        stair_states = [
            json.loads(state)
            for state in result.state_counts
            if "deepslate_tile_stairs" in state
        ]
        self.assertEqual(len(stair_states), 1)
        self.assertEqual(stair_states[0]["Properties"]["facing"], "east")
        self.assertEqual(stair_states[0]["Properties"]["half"], "bottom")

    def test_high_side_of_internal_roof_step_gets_full_height_wall(self) -> None:
        footprint = box(0, 0, 4, 3)
        high = roof_face(box(0, 0, 2, 3), c=5.0, index=0)
        low = roof_face(box(2, 0, 4, 3), c=2.0, index=1)
        building = measured_building(footprint, [high, low])
        raster = roof.rasterize_roof(building, (0, 0, 4, 3), resolution=0.5)
        canvas = FakeCanvas()

        result = shell.build_measured_shell(
            canvas, building, raster, vertical_offset=0.0
        )

        # Column 3 is the high cell immediately west of the height step; row 2
        # is away from the exterior wall.
        self.assertTrue(result.internal_wall_mask[2, 3])
        self.assertFalse(result.exterior_wall_mask[2, 3])
        high_roof_y = int(result.roof_block_y[2, 3])
        for y in range(result.floor_y + 1, high_roof_y):
            self.assertEqual(canvas.blocks[(3, y, 2)][0], "minecraft:bricks")
        self.assertFalse(result.internal_wall_mask[2, 4])
        self.assertEqual(result.internal_wall_drop_metres, 1.0)

    def test_courtyard_and_exterior_grade_are_untouched(self) -> None:
        outer = [(0, 0), (4, 0), (4, 4), (0, 4)]
        hole = [(1, 1), (3, 1), (3, 3), (1, 3)]
        footprint = Polygon(outer, [hole])
        building = measured_building(footprint, [roof_face(footprint, c=2.0)])
        raster = roof.rasterize_roof(building, (0, 0, 4, 4), resolution=0.5)
        canvas = FakeCanvas()
        courtyard_before = canvas.blocks[(3, -1, 3)]
        exterior_before = canvas.blocks[(-1, -1, 0)]

        result = shell.build_measured_shell(
            canvas, building, raster, vertical_offset=0.0
        )

        self.assertFalse(result.active_mask[3, 3])
        self.assertEqual(canvas.blocks[(3, -1, 3)], courtyard_before)
        self.assertNotIn((3, 0, 3), canvas.blocks)
        self.assertEqual(canvas.blocks[(-1, -1, 0)], exterior_before)
        self.assertNotIn((-1, 0, 0), canvas.blocks)

    def test_buried_roof_column_is_skipped_without_excavation(self) -> None:
        footprint = box(0, 0, 1, 1)
        building = measured_building(
            footprint, [roof_face(footprint, c=0.0)], source_base=-2.0
        )
        raster = roof.rasterize_roof(building, (0, 0, 1, 1), resolution=0.5)
        canvas = FakeCanvas(ground_y=-1)
        before = dict(canvas.blocks)

        result = shell.build_measured_shell(
            canvas,
            building,
            raster,
            vertical_offset=0.0,
            floor_navd88=-2.0,
        )

        self.assertFalse(np.any(result.active_mask))
        self.assertEqual(result.skipped_counts["buried_at_measured_grade"], 4)
        self.assertEqual(canvas.blocks, before)
        self.assertEqual(result.material_counts, {})


if __name__ == "__main__":
    unittest.main()
