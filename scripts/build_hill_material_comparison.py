"""Native Minecraft material coupons with real panes, sills, stairs and roofs."""

import argparse
from pathlib import Path

import numpy as np
from build_hill_chapel_sample import Canvas, ROLES, connect_window_panes
from campus_study_io import finish_study

ROOT = Path(__file__).resolve().parents[1]
ROWS = [
    ("brick-and-ashlar", ["bricks", "mud_bricks", "stone_bricks", "tuff_bricks", "polished_granite", "ashlar_mix"]),
    ("pale-surrounds", ["quartz_block", "smooth_quartz", "polished_diorite", "calcite", "white_concrete", "white_terracotta"]),
    ("gray-taupe-masonry", ["tuff", "polished_tuff", "stone_bricks", "light_gray_concrete", "light_gray_terracotta", "white_terracotta"]),
    ("siding", ["birch_planks", "pale_oak_planks", "oak_planks", "white_concrete", "white_terracotta", "gray_concrete"]),
    ("roofing", ["stone_brick", "deepslate_tile", "deepslate_brick", "brick", "waxed_cut_copper", "waxed_weathered_cut_copper"]),
]


def build(output):
    c = Canvas(-16, -48, 96, 384, 2)
    c.data[123, :, :] = c.state("grass_block")  # physical top Y60
    c.roles[123, :, :] = ROLES.index("terrain")
    c.data[121:123, :, :] = c.state("dirt")
    c.roles[121:123, :, :] = ROLES.index("terrain")
    c.ground_heights = np.full(c.data.shape[1:], 59, dtype=np.int16)
    cameras, specs = [], []
    for row, (label, candidates) in enumerate(ROWS):
        z = row * 72  # Keep earlier rows behind each camera, not in its sightline.
        for col, candidate in enumerate(candidates):
            x = col * 10
            wall = "bricks" if label == "roofing" else candidate
            for dx in range(8):
                for dy in range(8):
                    block = wall
                    if block == "ashlar_mix":
                        # Explicit coupon, not a building assignment. Coherent
                        # two-block ashlar stones, offset on alternate courses.
                        index = ((dx + (dy % 2)) // 2 + dy * 3) % 10
                        block = ["mud_bricks"] * 5 + ["stone_bricks"] * 3 + ["polished_granite"] * 2
                        block = block[index]
                    c.set(x + dx, 60 + dy, z, block, "facade")
            # Actual opening replaces the wall cells. Its panes touch the jambs.
            for dx in (3, 4):
                for dy in range(2, 6):
                    c.set(x + dx, 60 + dy, z, "glass_pane", "window", {"waterlogged": "false"})
            trim = candidate if label == "pale-surrounds" else "smooth_quartz"
            for dy in range(1, 7):
                for dx in (2, 5):
                    c.set(x + dx, 60 + dy, z, trim, "trim")
            slab = "polished_diorite_slab" if trim == "polished_diorite" else "smooth_quartz_slab"
            stair = "polished_diorite_stairs" if trim == "polished_diorite" else "smooth_quartz_stairs"
            for dx in range(2, 6):
                c.set(x + dx, 61, z, slab, "trim", {"type": "top", "waterlogged": "false"})
                c.set(x + dx, 66, z, slab, "trim", {"type": "bottom", "waterlogged": "false"})
            for dx, facing in ((2, "west"), (5, "east")):
                c.set(x + dx, 66, z, stair, "trim", {"facing": facing, "half": "top", "shape": "straight", "waterlogged": "false"})
            family = candidate if label == "roofing" else "stone_brick"
            full = family if "copper" in family else family + "s"
            for dx in range(-1, 9):
                for dz in range(7):
                    yy = 68 + min(dz, 6 - dz)
                    if dz == 3:
                        c.set(x + dx, yy, z + dz, family + "_slab", "roof", {"type": "bottom", "waterlogged": "false"})
                    else:
                        c.set(x + dx, yy, z + dz, family + "_stairs", "roof", {"facing": "south" if dz < 3 else "north", "half": "bottom", "shape": "straight", "waterlogged": "false"})
                    c.set(x + dx, yy - 1, z + dz, full, "roof")
            specs.append({"row": label, "screen_column_left_to_right": 6 - col, "candidate": candidate, "origin_blocks": [x, 60, z]})
        cameras.append({"name": label, "eye": [29, 68.5 if label != "roofing" else 79, z - 35], "target": [29, 64.5 if label != "roofing" else 68, z + 1], "fov": 65})
    connect_window_panes(c)
    finish_study(c, {"name": "Hill material comparison with vanilla textures", "revision": "2026-09-05-material-coupons-1", "blocks_per_metre": 2, "vertical_offset_m": -25, "coupons": specs}, output, cameras, {"purpose": "Compare construction families and partial blocks in the actual game. This is not a campus structure."})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
