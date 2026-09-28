"""Measured LiDAR roof + photo-interpreted construction components, in vanilla blocks.

Produces a new bounded Anvil world, exact semantic block archive and repeatable
native camera views. No Chapel geometry is built or modified by this study.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import hybridize_voxelearth_roofer_world as anvil
import numpy as np
from build_hill_chapel_sample import (
    ROLES,
    Canvas,
    build_ground,
    connect_window_panes,
    terrain_arrays,
    write_world,
)
from campus_materials import audit_role_materials
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_window_frames import bridge_frame_edges, pane_joint_report, pane_support_report
from prepare_hill_alumni_house import ORIGIN, U, V

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "runtime/campus-reconstruction/alumni-house-preparation"
PANE = {
    "north": "false",
    "south": "false",
    "east": "false",
    "west": "false",
    "waterlogged": "false",
}
SLAB = {"type": "bottom", "waterlogged": "false"}


class House:
    def __init__(self, canvas, profile, raster):
        self.c, self.p, self.r = canvas, profile, raster
        self.s, self.offset = canvas.scale, profile["vertical_offset_m"]
        z, x = np.indices(canvas.ground_heights.shape)
        dx = (x + canvas.x_min + 0.5) / self.s - ORIGIN[0]
        dz = (z + canvas.z_min + 0.5) / self.s - ORIGIN[1]
        self.u, self.v = dx * U[0] + dz * U[1], dx * V[0] + dz * V[1]
        self.features = Counter()

    def y(self, navd):
        return round((navd + self.offset) * self.s)

    def world(self, u, v, h):
        xz = ORIGIN + u * U + v * V
        return [
            float(xz[0] * self.s),
            float((h + self.offset) * self.s),
            float(xz[1] * self.s),
        ]

    def mask(self, bounds):
        u0, v0, u1, v1 = bounds
        return (self.u >= u0) & (self.u < u1) & (self.v >= v0) & (self.v < v1)

    def box(self, bounds, low, high, block, role, props=None, only=None):
        mask = self.mask(bounds)
        y0, y1 = self.y(low) + 64, self.y(high) + 64
        y0, y1 = max(y0, 0), min(y1, 384)
        state = self.c.state(block, props)
        view, roles = self.c.data[y0:y1], self.c.roles[y0:y1]
        if only is None:
            view[:, mask] = state
            roles[:, mask] = ROLES.index(role) if state else 0
        else:
            selected = mask[None, :, :] & np.isin(roles, [ROLES.index(r) for r in only])
            view[selected] = state
            roles[selected] = ROLES.index(role) if state else 0

    def opening(
        self,
        center,
        sill,
        width,
        height,
        *,
        side="front",
        at=None,
        arch=False,
        paired=False,
    ):
        # Openings have a full-depth cut, frame-plane glazing, a narrow surround,
        # and a sill. A photograph's dark region never becomes a solid black cube.
        depth = self.p["front_wall_v_m"] if at is None else at
        along = self.u if side == "front" else self.v
        normal = self.v if side == "front" else self.u
        band = abs(normal - depth) < 1.10
        trim_band = abs(normal - depth) < 0.48
        # A rotated plane needs a supercover raster, not a centre-distance
        # threshold narrower than a cell. This keeps diagonal panes connected.
        plane_half_width = (abs(U[0]) + abs(U[1])) / (2 * self.s) + 0.015
        center_band = abs(normal - depth) <= plane_half_width
        trim = max(0.26, 1.15 / self.s)
        allowed = set()
        for yi in range(self.y(sill - trim), self.y(sill + height + trim) + 1):
            h = (yi + 0.5) / self.s - self.offset - sill
            d = abs(along - center)
            cap = height - (0.45 * (d / max(width / 2, 0.1)) ** 2 if arch else 0)
            inside = band & (d < width / 2) & (h >= 0) & (h < cap)
            silhouette = (d < width / 2) & (h >= 0) & (h < cap)
            surround = (
                trim_band
                & (d < width / 2 + trim)
                & (h >= -trim)
                & (h < cap + trim)
                & ~silhouette
            )
            self.c.data[yi + 64, inside] = 0
            self.c.roles[yi + 64, inside] = 0
            self.c.data[yi + 64, surround] = self.c.state("birch_planks")
            self.c.roles[yi + 64, surround] = ROLES.index("trim")
            glazed = inside & center_band
            for iz, ix in np.argwhere(inside & trim_band):
                allowed.add((int(ix) + self.c.x_min, yi, int(iz) + self.c.z_min))
            self.c.data[yi + 64, glazed] = self.c.state(
                self.p["materials"]["window"], PANE
            )
            self.c.roles[yi + 64, glazed] = ROLES.index("window")
            if paired:
                mullion = inside & trim_band & (d < 0.14)
                self.c.data[yi + 64, mullion] = self.c.state("birch_planks")
                self.c.roles[yi + 64, mullion] = ROLES.index("trim")
            # A continuous pale meeting rail gives the tall sash its real
            # two-part rhythm without replacing the glazing with black blocks.
            if abs(h - height * 0.48) < 0.12:
                rail = inside & center_band
                self.c.data[yi + 64, rail] = self.c.state("birch_slab", SLAB)
                self.c.roles[yi + 64, rail] = ROLES.index("trim")
        self.features["pane_frame_edge_connectors"] += bridge_frame_edges(
            self.c, allowed
        )
        self.features[
            f"{side}_{'paired_' if paired else ''}{'arched_' if arch else ''}windows"
        ] += 1

    def roof_backing(self, shell):
        """Give the sampled roof real thickness so stair risers cannot leak sky."""
        thickness = max(2, math.ceil(0.40 * self.s))
        for iz, ix in np.argwhere(shell.active_mask):
            top = int(shell.roof_block_y[iz, ix])
            for y in range(max(shell.floor_y + 1, top - thickness), top):
                self.c.set(
                    ix + self.c.x_min,
                    y,
                    iz + self.c.z_min,
                    self.p["materials"]["roof_family"] + "s",
                    "roof",
                )
        self.features["roof_backing_columns"] = int(shell.active_mask.sum())

    def frontage(self):
        """Photo-confirmed site elements; dimensions remain interpreted, not surveyed."""
        # Keep measured grade, except for the actual engineered vertical face
        # of the retaining wall and the narrow paved approaches.
        wall_v = -10.0
        for iz, ix in np.argwhere(self.mask((-9, wall_v - 0.35, 22, wall_v + 0.4))):
            u = self.u[iz, ix]
            if 8.0 < u < 10.25:
                continue
            base = 49.4 + 0.045 * u
            top = base + 1.15
            for y in range(self.y(base - 0.25), self.y(top)):
                self.c.set(
                    ix + self.c.x_min, y, iz + self.c.z_min, "stone_bricks", "facade"
                )
        for iz, ix in np.argwhere(self.mask((-9, -13.2, 22, -11.0))):
            h = 49.3 + 0.045 * self.u[iz, ix]
            y = self.y(h)
            self.c.data[y + 64 :, iz, ix] = 0
            self.c.roles[y + 64 :, iz, ix] = 0
            for yi in range(y - 2, y):
                self.c.set(
                    ix + self.c.x_min, yi, iz + self.c.z_min, "smooth_stone", "pavement"
                )
        # Upper gravel walk from the porch steps to the frontage stair.
        for iz, ix in np.argwhere(self.mask((8.0, -8.6, 10.25, -3.4))):
            y = int(self.c.ground_heights[iz, ix])
            self.c.set(
                ix + self.c.x_min, y, iz + self.c.z_min, "coarse_dirt", "pavement"
            )
        for i in range(8):
            v = -11.5 + i * 0.40
            top = 49.75 + i * 0.20
            self.box((8.0, v, 10.25, v + 0.42), 49.2, top, "smooth_stone", "pavement")
        # Groundcover follows the measured bank instead of an artificial cube.
        for iz, ix in np.argwhere(self.mask((-0.5, -9.4, 7.8, -2.7))):
            y = int(self.c.ground_heights[iz, ix])
            self.c.set(
                ix + self.c.x_min, y, iz + self.c.z_min, "moss_block", "vegetation"
            )
        self.features.update({"retaining_wall": 1, "sidewalk": 1, "frontage_stair": 1})

    def build(self):
        p = self.p
        front = p["front_wall_v_m"]
        deck = p["porch_deck_navd88_m"]
        # LiDAR's low front roof is an open porch, not a room. Clear the
        # automatic envelope below it and continue the porch around the east.
        self.box((-0.45, -0.45, 11.0, front - 0.2), deck, 57.1, "air", "air")
        self.box((8.6, -0.45, 11.0, 8.65), deck, 57.1, "air", "air")
        # The front's measured eave is slightly outside the masonry plane.
        for iz, ix in np.argwhere(self.mask((0.05, front - 0.25, 8.45, front + 0.35))):
            roof = float(self.r.heights[iz, ix])
            if not math.isfinite(roof) or roof < 58:
                continue
            self.c.data[self.y(deck) + 64 : self.y(roof) - 1 + 64, iz, ix] = (
                self.c.state("bricks")
            )
            self.c.roles[self.y(deck) + 64 : self.y(roof) - 1 + 64, iz, ix] = (
                ROLES.index("facade")
            )
        self.box(
            (-3, 1.0, 9.0, 4.1),
            p["brick_to_shingle_navd88_m"],
            64,
            p["materials"]["gable"],
            "facade",
            only=("facade",),
        )
        self.box(
            (-0.1, front - 0.4, 8.5, front + 0.1),
            58.85,
            59.1,
            "birch_slab",
            "trim",
            SLAB,
        )
        # Photograph-specific asymmetrical first and second floor composition.
        self.opening(2.0, 56.55, 1.0, 1.85)
        self.opening(5.65, 56.5, 2.25, 2.0, arch=True, paired=True)
        self.opening(4.35, 53.6, 1.15, 2.0)
        self.opening(6.9, 53.6, 1.15, 2.0)
        self.opening(4.1, 60.2, 2.2, 1.1, paired=True)
        # Timber entrance is built at the model scale. A tiny two-block door
        # under a seven-block window would distort a four-block/metre facade.
        self.box((1.0, front - 0.65, 2.65, front + 0.8), deck, deck + 2.7, "air", "air")
        self.box(
            (0.75, front - 0.45, 1.02, front + 0.15),
            deck,
            deck + 2.8,
            "smooth_sandstone",
            "trim",
        )
        self.box(
            (2.65, front - 0.45, 2.92, front + 0.15),
            deck,
            deck + 2.8,
            "smooth_sandstone",
            "trim",
        )
        self.box(
            (0.75, front - 0.45, 2.92, front + 0.15),
            deck + 2.65,
            deck + 2.95,
            "smooth_sandstone_slab",
            "trim",
            SLAB,
        )
        self.box(
            (1.0, front - 0.05, 2.65, front + 0.3),
            deck,
            deck + 2.5,
            "dark_oak_planks",
            "facade",
        )
        self.box(
            (1.18, front - 0.1, 1.72, front + 0.35),
            deck + 0.9,
            deck + 2.22,
            "glass_pane",
            "window",
            PANE,
        )
        self.box(
            (1.92, front - 0.1, 2.46, front + 0.35),
            deck + 0.9,
            deck + 2.22,
            "glass_pane",
            "window",
            PANE,
        )
        # Functional vanilla door is inset within the timber entrance for
        # access; its physical dimensions are recorded separately from scale.
        pos = self.world(1.4, front + 0.2, deck)
        door_y = self.y(deck)
        for dx, hinge in ((0, "left"), (1, "right")):
            for dy, half in ((0, "lower"), (1, "upper")):
                self.c.set(
                    round(pos[0]) + dx,
                    door_y + dy,
                    round(pos[2]),
                    "dark_oak_door",
                    "door",
                    {
                        "facing": "south",
                        "half": half,
                        "hinge": hinge,
                        "open": "false",
                        "powered": "false",
                    },
                )
        self.box(
            (1.0, front - 0.1, 2.65, front + 0.4),
            deck + 2.5,
            deck + 2.65,
            "glass_pane",
            "window",
            PANE,
        )
        # Small gable balcony is a defining feature, distinct from a window sill.
        self.box(
            (2.85, front - 0.65, 5.35, front + 0.1),
            60.1,
            60.225,
            "birch_slab",
            "trim",
            SLAB,
        )
        self.box(
            (2.95, front - 0.6, 5.25, front - 0.35),
            60.225,
            60.75,
            "birch_fence",
            "railing",
            PANE,
        )
        # Continuous deck, shallow porch roof, painted posts, lattice and rail.
        self.box(
            (-0.25, -0.35, 10.7, front + 0.25),
            deck - 1 / self.s,
            deck,
            "birch_planks",
            "floor",
        )
        self.box(
            (8.2, -0.35, 10.7, 8.3), deck - 1 / self.s, deck, "birch_planks", "floor"
        )
        for iz, ix in np.argwhere(
            self.mask((8.2, -0.35, 10.9, 8.6))
            | self.mask((-0.4, -0.35, 10.9, front + 0.15))
        ):
            h = min(
                56.15 + 0.22 * max(0, self.v[iz, ix]),
                56.15 + 0.20 * (10.9 - self.u[iz, ix]),
            )
            y = self.y(h)
            for yi in range(y - 2, y):
                self.c.set(
                    ix + self.c.x_min,
                    yi,
                    iz + self.c.z_min,
                    p["materials"]["roof_family"] + "s",
                    "roof",
                )
            self.c.set(
                ix + self.c.x_min,
                y,
                iz + self.c.z_min,
                p["materials"]["roof_family"] + "_slab",
                "roof",
                SLAB,
            )
        for u in p["porch_post_u_m"]:
            self.box(
                (u - 0.12, -0.02, u + 0.14, 0.26), deck, 56.05, "birch_planks", "trim"
            )
            self.box(
                (u - 0.26, -0.18, u + 0.3, 0.42),
                deck - 0.25,
                deck + 0.25,
                "smooth_sandstone",
                "trim",
            )
        for v in (3.0, 5.6, 8.0):
            self.box(
                (10.08, v - 0.12, 10.34, v + 0.14), deck, 56.05, "birch_planks", "trim"
            )
        self.box(
            (0.35, -0.12, 7.45, 0.4),
            55.5,
            56.05,
            "birch_trapdoor",
            "trim",
            {
                "facing": "south",
                "half": "top",
                "open": "true",
                "powered": "false",
                "waterlogged": "false",
            },
        )
        self.box(
            (10.1, 0.3, 10.65, 8.1),
            55.5,
            56.05,
            "birch_trapdoor",
            "trim",
            {
                "facing": "east",
                "half": "top",
                "open": "true",
                "powered": "false",
                "waterlogged": "false",
            },
        )
        self.box(
            (0.3, -0.12, 7.3, 0.4),
            deck + 0.15,
            deck + 0.8,
            "birch_fence",
            "railing",
            PANE,
        )
        self.box(
            (10.0, 0.3, 10.5, 8.1),
            deck + 0.15,
            deck + 0.8,
            "birch_fence",
            "railing",
            PANE,
        )
        # Photo shows the east corner stair approaching the wraparound porch.
        for i in range(7):
            low_v = -3.4 + i * 0.50
            top = deck - (6 - i) * 0.25
            self.box((7.4, low_v, 10.5, 0.15), 51.6, top, "smooth_stone", "pavement")
        # Foundation piers provide physical support under the open veranda.
        for u in p["porch_post_u_m"]:
            self.box(
                (u - 0.25, -0.2, u + 0.35, 0.45), 51.5, deck - 0.25, "bricks", "facade"
            )
        for v in (3, 5.6, 8):
            self.box(
                (10.0, v - 0.25, 10.6, v + 0.35), 51.5, deck - 0.25, "bricks", "facade"
            )
        # Tall narrow chimney on the east roofline, with a dark open cap.
        self.box((7.55, 5.0, 8.15, 5.85), 57.5, 63.9, "bricks", "facade")
        self.box((7.45, 4.9, 8.25, 5.95), 63.8, 64.0, "brick_slab", "trim", SLAB)
        self.box((7.7, 5.2, 8.0, 5.65), 63.6, 64.4, "air", "air")
        # Only the east near-porch openings have photographic confirmation.
        self.opening(4.0, 53.6, 1.1, 1.9, side="east", at=8.35)
        self.opening(4.0, 56.5, 1.1, 1.8, side="east", at=8.35)
        # South-facing wall of the west projection is visible in the historic
        # oblique photograph. Its sill heights follow the main storeys.
        self.opening(-1.05, 53.65, 0.95, 1.9, at=4.4)
        self.opening(-1.05, 56.65, 0.95, 1.85, at=4.4)
        # Unfurnished floor plates stop a front window looking through the
        # entire multi-storey roof void. Interior layout is not reconstructed.
        for level in (56.15, 59.35):
            self.box(
                (0.65, front + 0.65, 7.95, 12.6),
                level - 0.25,
                level,
                "birch_planks",
                "floor",
            )
        # Pale roof verge follows the measured front gable, never the image sky.
        for iz, ix in np.argwhere(
            self.mask((-0.3, 1.3, 8.7, 2.0)) & (self.r.heights > 58.5)
        ):
            y = self.y(float(self.r.heights[iz, ix]))
            self.c.set(
                ix + self.c.x_min, y, iz + self.c.z_min, "birch_slab", "trim", SLAB
            )
        # Low planting is visibly present; exact species and shapes are inferred.
        for u, v, r, h in (
            (1.2, -1.8, 1.8, 1.1),
            (4.2, -1.7, 1.6, 0.8),
            (6.3, -1.5, 0.8, 0.65),
        ):
            mask = (self.u - u) ** 2 + (self.v - v) ** 2 < r * r
            for iz, ix in np.argwhere(mask):
                ground = self.c.ground_heights[iz, ix]
                for y in range(int(ground) + 1, int(ground) + 1 + round(h * self.s)):
                    if self.c.get(ix + self.c.x_min, y, iz + self.c.z_min) == 0:
                        self.c.set(
                            ix + self.c.x_min,
                            y,
                            iz + self.c.z_min,
                            "oak_leaves",
                            "vegetation",
                            {
                                "persistent": "true",
                                "distance": "1",
                                "waterlogged": "false",
                            },
                        )
        self.features.update(
            {
                "wraparound_porch": 1,
                "front_gable_balcony": 1,
                "chimney": 1,
                "entrance": 1,
            }
        )
        self.frontage()


def connect_fences(canvas):
    ids = [i for i, p in enumerate(canvas.palette) if p["Name"].endswith("_fence")]
    for iy, iz, ix in np.argwhere(np.isin(canvas.data, ids)):
        state = canvas.palette[int(canvas.data[iy, iz, ix])]
        props = dict(PANE)
        x, y, z = ix + canvas.x_min, iy - 64, iz + canvas.z_min
        for direction, dx, dz in (
            ("north", 0, -1),
            ("south", 0, 1),
            ("east", 1, 0),
            ("west", -1, 0),
        ):
            name = canvas.palette[canvas.get(x + dx, y, z + dz)]["Name"]
            props[direction] = (
                "true"
                if name.endswith("_fence")
                or name
                in {
                    "minecraft:bricks",
                    "minecraft:smooth_sandstone",
                    "minecraft:birch_planks",
                }
                else "false"
            )
        role = ROLES[int(canvas.roles[iy, iz, ix])]
        canvas.set(x, y, z, state["Name"], role, props)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "server-assets/hill-alumni-house-reference.json",
    )
    parser.add_argument("--terrain", type=Path, default=PREP / "terrain.npz")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(
            "Use a fresh revision directory; existing worlds are never overwritten"
        )
    p = json.loads(args.profile.read_text(encoding="utf-8"))
    s = p["blocks_per_metre"]
    h, ids, meta = terrain_arrays(args.terrain, s, p.get("terrain_bounds_m"))
    c = Canvas(meta["x_min"] * s, meta["z_min"] * s, h.shape[1], h.shape[0], s)
    build_ground(c, h, ids, meta["materials"], p["vertical_offset_m"])
    paving = smooth_exposed_measured_pavement(
        c, h, c.ground_heights, vertical_offset=p["vertical_offset_m"]
    )
    b = load_measured_building(parent_id=p["parent_id"])
    bounds = (
        c.x_min / s,
        c.z_min / s,
        (c.x_min + c.data.shape[2]) / s,
        (c.z_min + c.data.shape[1]) / s,
    )
    raster = rasterize_roof(b, bounds, resolution=1 / s)
    shell = build_measured_shell(
        c,
        b,
        raster,
        vertical_offset=p["vertical_offset_m"],
        floor_navd88=p["floor_navd88_m"],
        roof_family=p["materials"]["roof_family"],
    )
    house = House(c, p, raster)
    house.roof_backing(shell)
    house.build()
    connect_window_panes(c)
    connect_fences(c)
    joints = pane_joint_report(c)
    if joints["unbridged_diagonal_pairs"] or joints["disconnected_adjacent_pairs"]:
        raise ValueError({"open_window_joints": joints})
    from campus_material_assignment import apply_reviewed_palette

    if not p.get("material_review"):
        review = apply_reviewed_palette(c, p)
        if review:
            p["material_review"] = review
    roles = {}
    for i, role in enumerate(ROLES[1:], 1):
        unique, counts = np.unique(c.data[c.roles == i], return_counts=True)
        count = Counter()
        for state, n in zip(unique, counts):
            if state:
                count[c.palette[state]["Name"]] += int(n)
        if count:
            roles[role] = dict(count)
    violations = audit_role_materials(roles)
    if violations:
        raise ValueError(violations)
    args.output.mkdir(parents=True)
    materials = c.export(args.output / "sample-blocks.npz")
    spawn = tuple(round(x) for x in house.world(8.8, -8, 54))
    world = write_world(
        c,
        args.output / "world",
        "Hill — Class of 1960 Alumni House",
        spawn,
        anvil.DEFAULT_SOURCE_WORLD / "level.dat",
    )
    (args.output / "profile.json").write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")
    views = []
    for name, eye, target, fov in (
        ("front-reference", (15, -15, 54), (4.3, 2.0, 57.7), 62),
        ("front-straight", (4.3, -19, 54), (4.3, 2.0, 57.7), 55),
        ("east-porch", (24, -3, 54.0), (7.0, 6.0, 56.4), 65),
        ("roof-overview", (29, -19, 76), (3, 11, 56), 58),
    ):
        views.append(
            {
                "name": name,
                "eye": house.world(*eye),
                "target": house.world(*target),
                "fov": fov,
            }
        )
    (args.output / "camera-views.json").write_text(
        json.dumps({"format": "hill-native-camera-views-v1", "views": views}, indent=2)
        + "\n"
    )
    manifest = {
        "format": "hill-alumni-house-study-v1",
        "created_unix": int(time.time()),
        "revision": p["revision"],
        "world": world,
        "blocks_per_metre": s,
        "block_count": int(np.count_nonzero(c.data)),
        "source_roof_sha256": b.source_sha256,
        "terrain_sha256": hashlib.sha256(args.terrain.read_bytes()).hexdigest(),
        "profile_sha256": hashlib.sha256(
            (args.output / "profile.json").read_bytes()
        ).hexdigest(),
        "source_roof": shell.to_manifest(),
        "paving": paving,
        "materials": materials,
        "material_roles": roles,
        "material_violations": violations,
        "clipped_writes": c.clipped,
        "features": dict(house.features),
        "window_support": pane_support_report(c),
        "window_joints": joints,
        "visual_review": "pending — no acceptance implied by generation",
        "uncertainties": p["uncertainties"],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "blocks": manifest["block_count"],
                "features": manifest["features"],
                "clipped_writes": c.clipped,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
