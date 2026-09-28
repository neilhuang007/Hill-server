"""Rebuild the existing reviewed Chapel rules in the campus's shared frame.

This is regeneration in physical metres, not duplication of partial Minecraft
blocks. The isolated v11 study and its resource pack remain untouched.
"""

import argparse
import json
import shutil
from pathlib import Path

from build_hill_chapel_sample import (
    Canvas,
    Chapel,
    add_landscape,
    add_pews,
    add_reference_paths,
    build_ground,
    connect_window_panes,
    connect_window_stonework,
    terrain_arrays,
)
from campus_athey_details import connect_iron_rails
from campus_paving import smooth_exposed_measured_pavement
from campus_study_io import digest, finish_study

ROOT = Path(__file__).resolve().parents[1]


def make_campus_pack(target):
    """Reserve mud brick masonry, leaving vanilla gray stone bricks unchanged."""
    source = ROOT / "server-assets/resourcepacks/hill-brownstone"
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue

        def remap(text):
            return (
                text.replace("stone_bricks", "mud_bricks")
                .replace("smooth_sandstone", "smooth_red_sandstone")
                .replace("sandstone_wall", "red_sandstone_wall")
                .replace("birch_trapdoor", "acacia_trapdoor")
            )

        rel = remap(str(p.relative_to(source)).replace("\\", "/"))
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix in {".json", ".mcmeta"}:
            out.write_text(
                remap(p.read_text(encoding="utf-8")).replace(
                    "Hill Chapel:", "Hill campus:"
                ),
                encoding="utf-8",
            )
        else:
            shutil.copyfile(p, out)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=2, choices=(2, 4))
    parser.add_argument("--terrain", type=Path)
    parser.add_argument("--terrain-bounds", type=float, nargs=4)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    original = ROOT / "runtime/campus-reconstruction/chapel-study-v11/profile.json"
    p = json.loads(original.read_text(encoding="utf-8"))
    p.update(
        name="Hill — Alumni Chapel at campus scale",
        revision=f"2026-09-05-context-{args.scale}x-v5-vanilla",
        blocks_per_metre=args.scale,
        vertical_offset_m=-25,
    )
    p["scope"] = (
        "Existing accepted Chapel regenerated at the common campus scale; native context review required."
    )
    pack = None
    p["materials"].pop("resource_pack", None)
    p.pop("resource_pack", None)
    p["window_reveal"] = {
        "glass_recess_m": 0.0,
        "construction": "Glass panes at the masonry frame with connecting perimeter panes.",
    }
    p["materials"]["masonry"] = "mud_bricks"
    p["uncertainties"].append(
        f"The original rules are regenerated at {args.scale} blocks/metre. Large inferred tree crowns are omitted from this rescaling pass; reference planting beds remain. Clock, railing and tracery fine detail remains simplified."
    )
    terrain = args.terrain or (
        ROOT
        / "runtime/campus-reconstruction/measured-terrain/hill-chapel-measured-terrain.npz"
    )
    elevations, ids, meta = terrain_arrays(terrain, args.scale, args.terrain_bounds)
    c = Canvas(
        round(meta["x_min"] * args.scale),
        round(meta["z_min"] * args.scale),
        elevations.shape[1],
        elevations.shape[0],
        args.scale,
    )
    heights = build_ground(c, elevations, ids, meta["materials"], -25)
    chapel = Chapel(c, p, -25)
    add_reference_paths(chapel, heights)
    paving = smooth_exposed_measured_pavement(
        c, elevations, heights, vertical_offset=-25
    )
    chapel.build()
    add_landscape(chapel, heights)
    add_pews(chapel)
    chapel.place_entry()
    connect_window_stonework(c)
    connect_window_panes(c)
    connect_iron_rails(c)
    # The existing rules also name stone brick components for coping and steps.
    # Reassign just these Chapel states, keeping every stair/slab property.
    replacements = {
        "stone_bricks": "mud_bricks",
        "stone_brick_stairs": "mud_brick_stairs",
        "stone_brick_slab": "mud_brick_slab",
        "smooth_sandstone": "terracotta",
        "smooth_sandstone_stairs": "mud_brick_stairs",
        "smooth_sandstone_slab": "mud_brick_slab",
        "sandstone_wall": "mud_brick_wall",
        "birch_trapdoor": "acacia_trapdoor",
    }
    for i, state in enumerate(list(c.palette)):
        short = state["Name"].removeprefix("minecraft:")
        if short in replacements:
            c.data[c.data == i] = c.state(replacements[short], state.get("Properties"))
    p["vanilla_materials"] = replacements

    def point(u, v, navd):
        x, _, z = chapel.xyz(u, 0, v)
        return [x, (navd - 25) * args.scale, z]

    cameras = [
        {
            "name": "chapel-south",
            "eye": point(-14, 44, 71),
            "target": point(0, 21, 72),
            "fov": 72,
        },
        {
            "name": "chapel-east",
            "eye": point(32, 17, 73),
            "target": point(3, 8, 73),
            "fov": 72,
        },
        {
            "name": "chapel-overview",
            "eye": point(36, 42, 94),
            "target": point(0, 11, 70),
            "fov": 76,
        },
    ]
    finish_study(
        c,
        p,
        args.output,
        cameras,
        {
            "features": dict(chapel.features),
            "paving": paving,
            "source_profile": {"path": str(original), "sha256": digest(original)},
            "terrain": {"path": str(terrain), "sha256": digest(terrain)},
        },
        resource_pack=pack,
    )


if __name__ == "__main__":
    main()
