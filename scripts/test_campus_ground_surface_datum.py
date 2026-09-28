"""The visible ground surface, not its block's lower corner, represents the DEM."""

import json

import numpy as np
import pytest
from assemble_hill_campus_studies import ground_tile
from build_hill_chapel_sample import Canvas, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement


@pytest.mark.parametrize("assembler", [False, True])
def test_ground_surface_matches_exact_half_metre_dem(assembler):
    c = Canvas(0, 0, 16, 16, 2)
    heights = np.full((16, 16), 67.0)
    ids = np.ones((16, 16), dtype=np.uint8)
    palette = {"grass": {"id": 1, "minecraft_block": "minecraft:grass_block"}}
    if assembler:
        ground_tile(c, heights, ids, palette, -25, 60)
    else:
        build_ground(c, heights, ids, palette, -25)
    occupied_y = np.flatnonzero(c.data[:, 8, 8]) + c.y_min
    visible_navd88 = (occupied_y[-1] + 1) / c.scale + 25
    assert visible_navd88 == 67.0, (
        f"DEM 67.0 m became visible ground at {visible_navd88} m"
    )


def test_paved_surface_stays_at_dem_datum():
    c = Canvas(0, 0, 16, 16, 2)
    h = np.full((16, 16), 67.25)
    ids = np.ones((16, 16), dtype=np.uint8)
    build_ground(
        c, h, ids, {"path": {"id": 1, "minecraft_block": "minecraft:smooth_stone"}}, -25
    )
    smooth_exposed_measured_pavement(c, h, c.ground_heights, vertical_offset=-25)
    y = int(np.flatnonzero(c.data[:, 8, 8])[-1])
    state = c.palette[c.data[y, 8, 8]]
    thickness = 0.5 if state.get("Properties", {}).get("type") == "bottom" else 1
    assert (y + c.y_min + thickness) / c.scale + 25 == 67.25


def test_native_half_metre_grid_preserves_retaining_edge_and_crop(tmp_path):
    h = np.full((8, 8), 67.0)
    h[:, 3:] = 65.5
    source = tmp_path / "terrain.npz"
    np.savez(
        source,
        ground_elevation_navd88_m=h,
        material_id=np.ones_like(h, dtype=np.uint8),
        x_min=-2,
        z_min=-4,
        metadata_json=json.dumps({"resolution_m": 0.5}),
    )
    sampled, _, metadata = terrain_arrays(source, 2, (-1, -3, 1, -1))
    np.testing.assert_array_equal(sampled, h[2:6, 2:6])
    assert [metadata["x_min"], metadata["z_min"]] == [-1, -3]
