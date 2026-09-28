"""Write the small study's original JSON surface models; no image processing."""

import json
from pathlib import Path


PACK = (
    Path(__file__).resolve().parents[1] / "server-assets/resourcepacks/hill-brownstone"
)


def write(relative: str, payload: dict):
    target = PACK / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    # The reference's dimensional brownstone is warm, not pale limestone.
    # The original cut-stone bitmap avoids the overly red terracotta proxy.
    for suffix, parent in (
        ("", "cube_all"),
        ("_slab", "slab"),
        ("_slab_top", "slab_top"),
        ("_stairs", "stairs"),
        ("_inner_stairs", "inner_stairs"),
        ("_outer_stairs", "outer_stairs"),
    ):
        texture_keys = ("all",) if not suffix else ("bottom", "top", "side")
        write(
            f"assets/minecraft/models/block/smooth_sandstone{suffix}.json",
            {
                "parent": f"minecraft:block/{parent}",
                "textures": {
                    key: "hill-brownstone:block/cut_brownstone" for key in texture_keys
                },
            },
        )
    for suffix, parent in (
        ("post", "template_wall_post"),
        ("side", "template_wall_side"),
        ("side_tall", "template_wall_side_tall"),
        ("inventory", "wall_inventory"),
    ):
        write(
            f"assets/minecraft/models/block/sandstone_wall_{suffix}.json",
            {
                "parent": f"minecraft:block/{parent}",
                "textures": {"wall": "hill-brownstone:block/cut_brownstone"},
            },
        )
    for suffix, parent in (
        ("stairs", "stairs"),
        ("inner_stairs", "inner_stairs"),
        ("outer_stairs", "outer_stairs"),
    ):
        write(
            f"assets/minecraft/models/block/polished_deepslate_{suffix}.json",
            {
                "parent": f"minecraft:block/{parent}",
                "textures": {
                    key: "minecraft:block/gray_concrete"
                    for key in ("bottom", "top", "side")
                },
            },
        )
    # A deterministic vanilla model variant changes course phase across blocks
    # while retaining horizontal masonry and the same original bitmap.
    write(
        "assets/hill-brownstone/models/block/brownstone_reversed.json",
        {
            "textures": {"all": "minecraft:block/stone_bricks", "particle": "#all"},
            "elements": [
                {
                    "from": [0, 0, 0],
                    "to": [16, 16, 16],
                    "faces": {
                        face: {
                            "texture": "#all",
                            "uv": [0, 0, 16, 16],
                            "rotation": 180,
                            "cullface": face,
                        }
                        for face in ("north", "south", "east", "west", "up", "down")
                    },
                }
            ],
        },
    )
    write(
        "assets/minecraft/blockstates/stone_bricks.json",
        {
            "variants": {
                "": [
                    {"model": "minecraft:block/stone_bricks"},
                    {"model": "hill-brownstone:block/brownstone_reversed"},
                ]
            }
        },
    )


if __name__ == "__main__":
    main()
