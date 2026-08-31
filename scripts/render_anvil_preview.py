#!/usr/bin/env python3
"""Render lightweight PNG previews of a Java Anvil world.

The renderer is intentionally simple. It is a smoke-test and inspection aid for
generated terrain/building worlds, not a replacement for BlueMap or an in-game
review.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
HYBRID_SCRIPT = REPO_ROOT / "scripts/hybridize_voxelearth_roofer_world.py"


def load_hybrid_module() -> Any:
    spec = importlib.util.spec_from_file_location("hill_hybrid_world", HYBRID_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {HYBRID_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def block_color(block: str) -> tuple[int, int, int]:
    name = block.removeprefix("minecraft:")
    if name in {"grass_block", "moss_block"}:
        return (82, 142, 57)
    if name in {"water"}:
        return (42, 111, 206)
    if "brick" in name and "deepslate" not in name and "mud" not in name:
        return (159, 70, 52)
    if "deepslate" in name:
        return (59, 62, 66)
    if "stone" in name or "cobblestone" in name:
        return (135, 137, 132)
    if "concrete" in name:
        if "light_gray" in name:
            return (163, 166, 162)
        if "gray" in name:
            return (102, 106, 101)
        if "white" in name:
            return (218, 221, 216)
        return (146, 147, 140)
    if "glass" in name:
        return (98, 122, 132)
    if "sandstone" in name:
        return (211, 198, 141)
    if "planks" in name or "wood" in name or "log" in name:
        return (133, 89, 52)
    if "dirt" in name or "mud" in name:
        return (112, 82, 54)
    return (166, 157, 137)


def shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def in_bounds(
    x: int,
    y: int,
    z: int,
    args: argparse.Namespace,
) -> bool:
    return (
        (args.x_min is None or x >= args.x_min)
        and (args.x_max is None or x <= args.x_max)
        and (args.y_min is None or y >= args.y_min)
        and (args.y_max is None or y <= args.y_max)
        and (args.z_min is None or z >= args.z_min)
        and (args.z_max is None or z <= args.z_max)
    )


def iter_blocks(world: Path, args: argparse.Namespace) -> Iterable[tuple[int, int, int, str]]:
    hybrid = load_hybrid_module()
    for _chunk_x, _chunk_z, root in hybrid.iter_world_chunks(world):
        for x, y, z, block in hybrid.iter_chunk_blocks(root):
            if in_bounds(x, y, z, args):
                yield x, y, z, block


def render_topdown(world: Path, args: argparse.Namespace) -> None:
    top: dict[tuple[int, int], tuple[int, str]] = {}
    for x, y, z, block in iter_blocks(world, args):
        key = (x, z)
        if key not in top or y > top[key][0]:
            top[key] = (y, block)
    if not top:
        raise ValueError("no blocks in requested bounds")

    xs = [x for x, _z in top]
    zs = [z for _x, z in top]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)
    width_blocks = max_x - min_x + 1
    height_blocks = max_z - min_z + 1
    scale = max(1, math.floor(args.size / max(width_blocks, height_blocks)))
    image = Image.new("RGB", (width_blocks * scale, height_blocks * scale), args.background)
    draw = ImageDraw.Draw(image)
    min_y = min(y for y, _block in top.values())
    max_y = max(y for y, _block in top.values())
    relief = max(1, max_y - min_y)
    for (x, z), (y, block) in top.items():
        color = block_color(block)
        color = shade(color, 0.82 + 0.24 * ((y - min_y) / relief))
        left = (x - min_x) * scale
        top_px = (z - min_z) * scale
        draw.rectangle((left, top_px, left + scale - 1, top_px + scale - 1), fill=color)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, optimize=True)
    print(args.output)


def render_iso(world: Path, args: argparse.Namespace) -> None:
    blocks = {(x, y, z): block for x, y, z, block in iter_blocks(world, args)}
    if not blocks:
        raise ValueError("no blocks in requested bounds")

    tile_w = args.tile_width
    tile_h = args.tile_height
    voxel_h = args.voxel_height

    def project(x: float, y: float, z: float) -> tuple[float, float]:
        return ((x - z) * tile_w / 2.0, (x + z) * tile_h / 2.0 - y * voxel_h)

    faces: list[tuple[int, list[tuple[float, float]], tuple[int, int, int]]] = []
    for x, y, z in blocks:
        color = block_color(blocks[(x, y, z)])
        order = x + z + y
        if (x, y + 1, z) not in blocks:
            faces.append(
                (
                    order + 3,
                    [project(x, y + 1, z), project(x + 1, y + 1, z), project(x + 1, y + 1, z + 1), project(x, y + 1, z + 1)],
                    shade(color, 1.10),
                )
            )
        if (x + 1, y, z) not in blocks:
            faces.append(
                (
                    order + 2,
                    [project(x + 1, y, z), project(x + 1, y + 1, z), project(x + 1, y + 1, z + 1), project(x + 1, y, z + 1)],
                    shade(color, 0.78),
                )
            )
        if (x, y, z + 1) not in blocks:
            faces.append(
                (
                    order + 1,
                    [project(x, y, z + 1), project(x + 1, y, z + 1), project(x + 1, y + 1, z + 1), project(x, y + 1, z + 1)],
                    shade(color, 0.65),
                )
            )

    min_px = min(point[0] for _order, points, _color in faces for point in points)
    max_px = max(point[0] for _order, points, _color in faces for point in points)
    min_py = min(point[1] for _order, points, _color in faces for point in points)
    max_py = max(point[1] for _order, points, _color in faces for point in points)
    width = max_px - min_px + 20
    height = max_py - min_py + 20
    scale = min(1.0, args.size / max(width, height))
    image = Image.new(
        "RGB",
        (max(1, int(math.ceil(width * scale))), max(1, int(math.ceil(height * scale)))),
        args.background,
    )
    draw = ImageDraw.Draw(image)
    faces.sort(key=lambda item: item[0])
    for _order, points, color in faces:
        projected = [
            (int(round((x - min_px + 10) * scale)), int(round((y - min_py + 10) * scale)))
            for x, y in points
        ]
        draw.polygon(projected, fill=color)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, optimize=True)
    print(args.output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("world", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("topdown", "iso"), default="topdown")
    parser.add_argument("--size", type=int, default=1200)
    parser.add_argument("--x-min", type=int)
    parser.add_argument("--x-max", type=int)
    parser.add_argument("--y-min", type=int)
    parser.add_argument("--y-max", type=int)
    parser.add_argument("--z-min", type=int)
    parser.add_argument("--z-max", type=int)
    parser.add_argument("--tile-width", type=float, default=5.0)
    parser.add_argument("--tile-height", type=float, default=2.5)
    parser.add_argument("--voxel-height", type=float, default=4.0)
    parser.add_argument("--background", default="#7eaae7")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "topdown":
        render_topdown(args.world.resolve(), args)
    else:
        render_iso(args.world.resolve(), args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
