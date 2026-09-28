"""Build a bounded, auditable Chapel study and explicitly gated adjacent geometry.

The terrain remains measured. Architecture is a deliberately documented
interpretation of the Roofer envelope and current ground photographs. The
result is a new vanilla Anvil world plus the exact states for offline previews.
An offline preview does not satisfy the separate native in-game review gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

import hybridize_voxelearth_roofer_world as anvil
import nbtlib
import numpy as np
from campus_materials import audit_role_materials
from campus_paving import smooth_exposed_measured_pavement
from nbtlib import tag
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "server-assets/hill-chapel-reference.json"
AIR = "minecraft:air"
ROLES = (
    "air",
    "terrain",
    "pavement",
    "facade",
    "roof",
    "trim",
    "window",
    "vegetation",
    "railing",
    "lighting",
    "door",
    "floor",
    "fixture",
    "furniture",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Canvas:
    """Small bounded voxel volume with material intent stored per occupied cell."""

    def __init__(self, x_min: int, z_min: int, width: int, depth: int, scale: int):
        self.x_min, self.z_min, self.scale = x_min, z_min, scale
        self.y_min, self.y_max = -64, 320
        self.data = np.zeros((384, depth, width), dtype=np.uint16)
        self.roles = np.zeros_like(self.data, dtype=np.uint8)
        self.palette: list[dict[str, Any]] = [{"Name": AIR}]
        self.palette_lookup: dict[str, int] = {AIR: 0}
        self.clipped = 0
        self.ground_heights: np.ndarray | None = None

    def state(self, name: str, properties: dict[str, str] | None = None) -> int:
        if not name.startswith("minecraft:"):
            name = "minecraft:" + name
        entry: dict[str, Any] = {"Name": name}
        if properties:
            entry["Properties"] = properties
        key = json.dumps(entry, sort_keys=True)
        if name == AIR:
            return 0
        if key not in self.palette_lookup:
            self.palette_lookup[key] = len(self.palette)
            self.palette.append(entry)
        return self.palette_lookup[key]

    def set(
        self,
        x: int,
        y: int,
        z: int,
        name: str,
        role: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        ix, iz, iy = x - self.x_min, z - self.z_min, y - self.y_min
        if not (
            0 <= iy < 384
            and 0 <= iz < self.data.shape[1]
            and 0 <= ix < self.data.shape[2]
        ):
            self.clipped += 1
            return
        self.data[iy, iz, ix] = self.state(name, properties)
        self.roles[iy, iz, ix] = ROLES.index(role) if name not in {AIR, "air"} else 0

    def get(self, x: int, y: int, z: int) -> int:
        ix, iz, iy = x - self.x_min, z - self.z_min, y - self.y_min
        if (
            0 <= iy < 384
            and 0 <= iz < self.data.shape[1]
            and 0 <= ix < self.data.shape[2]
        ):
            return int(self.data[iy, iz, ix])
        return 0

    def ground_at(self, x: int, z: int) -> int:
        if self.ground_heights is None:
            raise RuntimeError("Generate measured terrain before placing architecture")
        return int(self.ground_heights[z - self.z_min, x - self.x_min])

    def export(self, path: Path) -> dict[str, int]:
        yy, zz, xx = np.nonzero(self.data)
        np.savez_compressed(
            path,
            coords=np.column_stack(
                (xx + self.x_min, yy + self.y_min, zz + self.z_min)
            ).astype(np.int32),
            state_ids=self.data[yy, zz, xx],
            role_ids=self.roles[yy, zz, xx],
            role_names=np.asarray(ROLES),
            palette_json=np.asarray(json.dumps(self.palette, sort_keys=True)),
        )
        counts: Counter[str] = Counter()
        for i, n in zip(*np.unique(self.data[self.data != 0], return_counts=True)):
            counts[self.palette[int(i)]["Name"]] += int(n)
        return dict(counts)


def terrain_arrays(
    path: Path, scale: int, bounds: tuple[float, float, float, float] | None = None
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path, allow_pickle=False) as p:
        meta = json.loads(str(p["metadata_json"]))
        h = p["ground_elevation_navd88_m"].astype(float)
        ids = p["material_id"]
        meta["x_min"], meta["z_min"] = int(p["x_min"]), int(p["z_min"])
    resolution = float(meta.get("resolution_m", 1.0))
    source_x, source_z = meta["x_min"], meta["z_min"]
    full_bounds = (
        source_x,
        source_z,
        source_x + h.shape[1] * resolution,
        source_z + h.shape[0] * resolution,
    )
    x0, z0, x1, z1 = full_bounds if bounds is None else bounds
    if not (
        full_bounds[0] <= x0 < x1 <= full_bounds[2]
        and full_bounds[1] <= z0 < z1 <= full_bounds[3]
    ):
        raise ValueError(f"Terrain crop {bounds} exceeds source {full_bounds}")
    rows, cols = np.indices(
        (round((z1 - z0) * scale), round((x1 - x0) * scale)), dtype=float
    )
    sample_rows = ((rows + 0.5) / scale + z0 - source_z) / resolution - 0.5
    sample_cols = ((cols + 0.5) / scale + x0 - source_x) / resolution - 0.5
    elevations = map_coordinates(h, [sample_rows, sample_cols], order=1, mode="nearest")
    material_ids = map_coordinates(
        ids, [sample_rows, sample_cols], order=0, mode="nearest"
    )
    meta["x_min"], meta["z_min"] = x0, z0
    return elevations, material_ids, meta


def build_ground(
    canvas: Canvas,
    elevations: np.ndarray,
    material_ids: np.ndarray,
    materials: Any,
    offset: float,
) -> np.ndarray:
    # The DEM denotes the physical top, whereas a block's Y denotes its bottom.
    heights = np.rint((elevations + offset) * canvas.scale).astype(np.int16) - 1
    material_map = {int(v["id"]): v["minecraft_block"] for v in materials.values()}
    stone, dirt = canvas.state("stone"), canvas.state("dirt")
    base = int(heights.min()) - 12 * canvas.scale
    for iz, ix in np.ndindex(heights.shape):
        top = int(heights[iz, ix])
        b = material_map[int(material_ids[iz, ix])]
        if not str(b).startswith("minecraft:"):
            raise ValueError(f"Terrain material lacks a Minecraft identifier: {b!r}")
        canvas.data[base + 64 : top - 3 + 64, iz, ix] = stone
        canvas.data[top - 3 + 64 : top + 64, iz, ix] = dirt
        canvas.roles[base + 64 : top + 65, iz, ix] = ROLES.index("terrain")
        canvas.data[top + 64, iz, ix] = canvas.state(b)
        if b not in {
            "minecraft:grass_block",
            "minecraft:dirt",
            "minecraft:water",
            "minecraft:coarse_dirt",
            "minecraft:clay",
            "minecraft:gravel",
        }:
            canvas.roles[top + 64, iz, ix] = ROLES.index("pavement")
        if b == "minecraft:water":
            canvas.data[top + 62 : top + 65, iz, ix] = canvas.state(b, {"level": "0"})
    canvas.ground_heights = heights
    return heights


class Chapel:
    def __init__(self, canvas: Canvas, profile: dict[str, Any], offset: float):
        self.c, self.g = canvas, profile["geometry"]
        self.p = profile
        self.masonry = profile.get("materials", {}).get("masonry", "stone_bricks")
        a = math.radians(self.g["rotation_degrees"])
        self.cos, self.sin = math.cos(a), math.sin(a)
        self.floor = round((self.g["floor_navd88_m"] + offset) * canvas.scale)
        self.features: Counter[str] = Counter()

    def xyz(self, u: float, h: float, v: float) -> tuple[int, int, int]:
        s = self.c.scale
        return (
            round((self.cos * u + self.sin * v) * s),
            self.floor + round(h * s),
            round((-self.sin * u + self.cos * v) * s),
        )

    def columns(self, bounds: tuple[float, float, float, float]):
        u0, v0, u1, v1 = bounds
        corners = [self.xyz(u, 0, v) for u in (u0, u1) for v in (v0, v1)]
        for x in range(min(p[0] for p in corners) - 1, max(p[0] for p in corners) + 2):
            for z in range(
                min(p[2] for p in corners) - 1, max(p[2] for p in corners) + 2
            ):
                east, south = (x + 0.5) / self.c.scale, (z + 0.5) / self.c.scale
                u, v = (
                    self.cos * east - self.sin * south,
                    self.sin * east + self.cos * south,
                )
                if u0 <= u < u1 and v0 <= v < v1:
                    yield x, z, u, v

    def box(
        self,
        bounds: tuple[float, float, float, float],
        bottom: float,
        top: float,
        block: str,
        role: str,
        props: dict[str, str] | None = None,
    ):
        for x, z, _u, _v in self.columns(bounds):
            for y in range(
                self.floor + math.floor(bottom * self.c.scale),
                self.floor + math.ceil(top * self.c.scale),
            ):
                self.c.set(x, y, z, block, role, props)

    def shell(
        self,
        bounds: tuple[float, float, float, float],
        eave: float,
        ridge: float,
        *,
        front: bool = True,
    ):
        u0, v0, u1, v1 = bounds
        half, mid = (u1 - u0) / 2, (u1 + u0) / 2
        for x, z, u, v in self.columns(bounds):
            roof = eave + (ridge - eave) * (1 - abs(u - mid) / half)
            top = self.floor + math.floor(roof * self.c.scale)
            edge = min(u - u0, u1 - u, v - v0, v1 - v) < 0.6
            # Only the building footprint is excavated/seated; no flattened apron.
            for y in range(min(self.c.ground_at(x, z), self.floor - 3), top + 1):
                if y < self.floor:
                    block, role = "stone_bricks", "facade"
                elif y == self.floor:
                    block, role = "smooth_stone", "floor"
                elif y == top and not (front and (v1 - v < 0.6 or v - v0 < 0.6)):
                    block, role = "deepslate_tiles", "roof"
                elif edge:
                    block, role = self.masonry, "facade"
                else:
                    block, role = AIR, "air"
                self.c.set(x, y, z, block, role)
            is_coping = front and (v1 - v < 0.6 or v - v0 < 0.6)
            if ridge > eave:
                self.roof_surface(
                    x,
                    z,
                    roof,
                    (ridge - eave) / half,
                    "stone_brick" if is_coping else "deepslate_tile",
                    "trim" if is_coping else "roof",
                    "west" if u > mid else "east",
                )
        self.features["modeled_mass_shells"] += 1

    def roof_surface(
        self,
        x: int,
        z: int,
        height: float,
        gradient: float,
        family: str,
        role: str,
        facing: str,
    ):
        """A continuous half-block roof profile; stairs only on rising treads."""
        surface = round((self.floor + height * self.c.scale + 1) * 2) / 2
        downhill = (
            round(
                (self.floor + height * self.c.scale + 1 - gradient * abs(self.cos)) * 2
            )
            / 2
        )
        y = math.ceil(surface) - 1
        if surface % 1:
            name, props = family + "_slab", {"type": "bottom", "waterlogged": "false"}
        elif downhill < surface:
            name, props = (
                family + "_stairs",
                {
                    "facing": facing,
                    "half": "bottom",
                    "shape": "straight",
                    "waterlogged": "false",
                },
            )
        else:
            name, props = family + "s", None
        self.c.set(x, y, z, name, role, props)

    def lean_shell(self, bounds: tuple[float, float, float, float]):
        u0, v0, u1, v1 = bounds
        inner = u0 if u0 > 0 else u1
        for x, z, u, v in self.columns(bounds):
            roof = 4.0 + 1.0 * (1 - abs(u - inner) / (u1 - u0))
            top = self.floor + math.floor(roof * self.c.scale)
            side_wall = min(u - u0, u1 - u, v - v0, v1 - v) < 0.55
            for y in range(min(self.c.ground_at(x, z), self.floor - 3), top + 1):
                block, role = (
                    ("stone_bricks", "facade")
                    if y < self.floor
                    else ("smooth_stone", "floor")
                    if y == self.floor
                    else (self.masonry, "facade")
                    if side_wall
                    else ("deepslate_tiles", "roof")
                    if y == top
                    else (AIR, "air")
                )
                self.c.set(x, y, z, block, role)
            if side_wall and (v1 - v < 0.55 or v - v0 < 0.55):
                self.roof_surface(
                    x,
                    z,
                    roof,
                    1.0 / (u1 - u0),
                    "stone_brick",
                    "trim",
                    "west" if u0 > 0 else "east",
                )
            elif not side_wall:
                self.roof_surface(
                    x,
                    z,
                    roof,
                    1.0 / (u1 - u0),
                    "deepslate_tile",
                    "roof",
                    "west" if u0 > 0 else "east",
                )
        self.features["modeled_lean_to_wings"] += 1

    @staticmethod
    def in_arch(
        horizontal: float, vertical: float, half_width: float, height: float
    ) -> bool:
        if abs(horizontal) > half_width or vertical < 0:
            return False
        # Two intersecting circular arcs produce the observed pointed head.
        # A straight triangular cap made every opening read as a chevron.
        rise = half_width * 1.35
        centre = (rise * rise - half_width * half_width) / (2 * half_width)
        radius = half_width + centre
        arc = math.sqrt(max(0, radius * radius - (abs(horizontal) + centre) ** 2))
        return vertical <= height - rise + arc

    def arch(
        self,
        side: str,
        plane: float,
        centre: float,
        bottom: float,
        width: float,
        height: float,
        *,
        opening: bool = False,
        door: bool = False,
        tracery: bool = False,
    ):
        half, border = width / 2, 0.45
        # The pane belongs at the frame. An optional historical recess keeps
        # archived studies reproducible without imposing it on the campus.
        recess = self.p.get("window_reveal", {}).get("glass_recess_m", 0.3)
        pane_plane = plane - (recess if side in {"east", "south"} else -recess)
        # Include every cell intersected by the rotated pane plane. This
        # supercover adds the orthogonal bridge at diagonal wall steps; a
        # fixed narrow centre-distance test left disconnected glass lights.
        pane_depth = (abs(self.cos) + abs(self.sin)) / (2 * self.c.scale) + 1e-6
        bounds = (
            (plane - 0.85, centre - half - border, plane + 0.85, centre + half + border)
            if side in {"east", "west"}
            else (
                centre - half - border,
                plane - 0.85,
                centre + half + border,
                plane + 0.85,
            )
        )
        reveal_cells = set()
        for x, z, u, v in self.columns(bounds):
            d = (v if side in {"east", "west"} else u) - centre
            axis = u if side in {"east", "west"} else v
            depth = abs(axis - pane_plane)
            outward = (axis - plane) * (1 if side in {"east", "south"} else -1)
            for y in range(
                self.floor + math.floor((bottom - border) * self.c.scale),
                self.floor + math.ceil((bottom + height + border) * self.c.scale),
            ):
                h = (y - self.floor + 0.5) / self.c.scale - bottom
                inside = self.in_arch(d, h, half, height)
                outer = self.in_arch(d, h + border, half + border, height + 2 * border)
                if inside:
                    if not opening and not door and -0.65 <= outward <= pane_depth:
                        reveal_cells.add((x, y, z))
                    if opening:
                        block, role = AIR, "air"
                    elif door:
                        if h >= height * 0.67:
                            block, role = (
                                ("gray_stained_glass_pane", "window")
                                if depth <= pane_depth
                                else (AIR, "air")
                            )
                        else:
                            block, role = "dark_oak_planks", "facade"
                    elif (
                        depth <= pane_depth
                        and tracery
                        and self.on_tracery(d, h, width, height)
                    ):
                        block, role = "sandstone_wall", "trim"
                    else:
                        block, role = (
                            ("gray_stained_glass_pane", "window")
                            if depth <= pane_depth
                            else (AIR, "air")
                        )
                    properties = None
                    if role == "window":
                        properties = {
                            "north": "true" if side in {"east", "west"} else "false",
                            "south": "true" if side in {"east", "west"} else "false",
                            "east": "true" if side in {"north", "south"} else "false",
                            "west": "true" if side in {"north", "south"} else "false",
                            "waterlogged": "false",
                        }
                    elif block == "sandstone_wall":
                        properties = {
                            "up": "true",
                            "north": "none",
                            "south": "none",
                            "east": "none",
                            "west": "none",
                            "waterlogged": "false",
                        }
                    self.c.set(x, y, z, block, role, properties)
                elif outer and -0.65 <= outward <= pane_depth:
                    spring = height - half * 1.35
                    if h >= spring and abs(d) > 0.3 and h < height - 0.25:
                        toward = (
                            ("north" if d > 0 else "south")
                            if side in {"east", "west"}
                            else ("west" if d > 0 else "east")
                        )
                        self.c.set(
                            x,
                            y,
                            z,
                            "smooth_sandstone_stairs",
                            "trim",
                            {
                                "facing": toward,
                                "half": "top",
                                "shape": "straight",
                                "waterlogged": "false",
                            },
                        )
                    elif h < 0 and not opening and not door:
                        self.c.set(
                            x,
                            y,
                            z,
                            "smooth_sandstone_slab",
                            "trim",
                            {"type": "top", "waterlogged": "false"},
                        )
                    else:
                        self.c.set(x, y, z, "smooth_sandstone", "facade")
        from campus_window_frames import bridge_frame_edges

        self.features["pane_frame_edge_connectors"] += bridge_frame_edges(
            self.c, reveal_cells
        )
        self.features[
            "open_arcades" if opening else "arched_doors" if door else "pointed_windows"
        ] += 1

    @staticmethod
    def on_tracery(d: float, h: float, width: float, height: float) -> bool:
        """Three lower lights and branching upper stonework from the front photo."""
        split, spring, apex = width / 6, height * 0.56, height * 0.67
        segments = [
            ((-split, 0), (-split, spring)),
            ((split, 0), (split, spring)),
            ((-split, spring), (0, apex)),
            ((split, spring), (0, apex)),
            # The tall central upper lancet is glass. Its two sides branch
            # upward from the lower mullions, leaving the centreline clear.
            ((-split, spring), (-split * 0.9, height * 0.86)),
            ((split, spring), (split * 0.9, height * 0.86)),
            ((-split * 0.9, height * 0.86), (-split * 0.5, height * 0.96)),
            ((split * 0.9, height * 0.86), (split * 0.5, height * 0.96)),
            ((-split, spring), (-width / 3, apex)),
            ((split, spring), (width / 3, apex)),
            ((-width / 3, apex), (-width / 2, spring)),
            ((width / 3, apex), (width / 2, spring)),
        ]
        for (x0, y0), (x1, y1) in segments:
            length2 = (x1 - x0) ** 2 + (y1 - y0) ** 2
            t = min(1, max(0, ((d - x0) * (x1 - x0) + (h - y0) * (y1 - y0)) / length2))
            if math.hypot(d - x0 - t * (x1 - x0), h - y0 - t * (y1 - y0)) <= 0.18:
                return True
        return False

    def build(self):
        g, s = self.g, self.c.scale
        half, south = g["nave_half_width_m"], g["south_m"]
        old_south = g["addition_start_m"]
        self.shell((-half, g["nave_north_m"], half, south), g["eave_m"], g["ridge_m"])
        self.shell((-2.6, -11.0, 2.6, -1.0), 6.8, 8.0)
        outer = g["aisle_outer_m"]
        # Side aisles have lean-to roofs, not a second gable.
        for sign in (-1, 1):
            bounds = (
                (half, 4.6, outer, old_south)
                if sign > 0
                else (-outer, 4.6, -half, old_south)
            )
            for x, z, u, v in self.columns(bounds):
                roof = 4.0 + (outer - abs(u)) / (outer - half)
                top = self.floor + int(roof * s)
                outside = outer - abs(u) < 0.6 or old_south - v < 0.6 or v - 4.6 < 0.6
                for y in range(min(self.c.ground_at(x, z), self.floor - 3), top + 1):
                    block, role = (
                        ("stone_bricks", "facade")
                        if y < self.floor
                        else ("smooth_stone", "floor")
                        if y == self.floor
                        else ("deepslate_tiles", "roof")
                        if y == top
                        else (self.masonry, "facade")
                        if outside
                        else (AIR, "air")
                    )
                    self.c.set(x, y, z, block, role)
                if not outside:
                    self.roof_surface(
                        x,
                        z,
                        roof,
                        1 / (outer - half),
                        "deepslate_tile",
                        "roof",
                        "west" if sign > 0 else "east",
                    )
            # Low aisle band and buttresses retain the visible masonry rhythm.
            side = "east" if sign > 0 else "west"
            for v in np.arange(6.6, old_south - 1.0, 4.0):
                self.arch(
                    side,
                    sign * outer,
                    float(v),
                    0.5 if sign > 0 else 1.25,
                    2.5,
                    3.3 if sign > 0 else 2.55,
                    opening=sign > 0,
                )
                if sign > 0:
                    self.arch(side, half, float(v), 1.2, 1.45, 2.6)
            for v in np.arange(3.0, south - 1.0, 4.0):
                if (sign > 0 and v < 4.6) or v >= old_south:
                    # The tower and the taller new transverse wing cover these
                    # former exterior locations; they are not exterior windows.
                    continue
                self.arch(side, sign * half, float(v), 5.4, 1.3, 1.7)
            for v in np.arange(4.6, old_south, 4.0):
                u0, u1 = (
                    (outer - 0.4, outer + 0.65)
                    if sign > 0
                    else (-outer - 0.65, -outer + 0.4)
                )
                self.box(
                    (u0, float(v) - 0.35, u1, float(v) + 0.35),
                    0,
                    4.5,
                    self.masonry,
                    "facade",
                )
                self.box(
                    (u0, float(v) - 0.35, u1, float(v) + 0.35),
                    4.5,
                    4.75,
                    "smooth_sandstone_slab",
                    "trim",
                    {"type": "bottom", "waterlogged": "false"},
                )
        # The new addition is a wide transverse block. Its side rooms enclose
        # the southern end of the old open ambulatory, as shown on GKO SP-1.
        for u0, u1 in (
            (g["addition_outer_bounds_u_m"][0], -half),
            (half, g["addition_outer_bounds_u_m"][1]),
        ):
            self.lean_shell((u0, old_south, u1, south))
            side = "west" if u1 < 0 else "east"
            plane = u0 if side == "west" else u1
            for v in (old_south + 2.0, old_south + 5.5):
                self.arch(side, plane, v, 1.3, 1.45, 2.5)
        self.features["documented_south_addition"] += 1
        # The completed 2025 west elevation has three upper windows across
        # the addition. The proposed drawing differs here; use the built photo.
        for v in (22.0, 24.5, 27.0):
            self.arch("west", -half, v, 5.6, 1.25, 1.35)
        self.features["west_addition_clerestory_windows"] = 3
        # Brownstone fascia and coping hide the lower aisle roof edge in the
        # contractor's close eastern elevation. Roofing remains behind it.
        for side in (-1, 1):
            bounds = (
                (outer - 0.65, 4.6, outer + 0.25, old_south)
                if side > 0
                else (-outer - 0.25, 4.6, -outer + 0.65, old_south)
            )
            self.box(bounds, 4.0, 4.5, self.masonry, "facade")
            self.box(
                bounds,
                4.5,
                4.75,
                "smooth_sandstone_slab",
                "trim",
                {"type": "bottom", "waterlogged": "false"},
            )
        # Recessed east doorway inside the ambulatory, visible in the current
        # school's drone walkthrough. Outer arch reaches the aisle paving.
        self.arch("east", half, 10.6, 0.5, 1.8, 2.8, door=True)
        # Current southern front: traceried lancet above the timber doorway.
        self.arch("south", south, 0, 4.3, 2.8, 4.55, tracery=True)
        self.arch("south", south, 0, 0.5, 2.0, 3.0, door=True)
        for u in (-6.3, 6.3):
            self.arch("south", south, u, 1.2, 1.45, 2.6)
        for u in (-half, half):
            self.box(
                (u - 0.35, south - 0.3, u + 0.35, south + 0.65),
                0,
                7.2,
                self.masonry,
                "facade",
            )
        self.box(
            (-0.25, south - 0.2, 0.25, south + 0.3),
            g["ridge_m"] + 0.3,
            g["ridge_m"] + 1.65,
            self.masonry,
            "facade",
        )
        # Align the arm to one exact row. Fractional box bounds previously
        # rounded into the top stem row, changing the Latin cross into a T.
        arm_y = self.floor + round((g["ridge_m"] + 1.05) * s)
        for x, z, _u, _v in self.columns((-0.75, south - 0.2, 0.75, south + 0.3)):
            self.c.set(x, arm_y, z, self.masonry, "facade")
        self.tower()

    def place_entry(self):
        """Finalize complete door pairs after all ground/landing writes."""
        south = self.g["south_m"]
        # Tall paired timber panels give the entrance its photographed scale.
        # The real two-block operating doors remain at the base of this portal.
        for x, z, u, v in self.columns((-0.95, south - 0.2, 0.95, south + 0.3)):
            for y in range(self.floor + 1, self.floor + round(2.5 * self.c.scale)):
                self.c.set(
                    x,
                    y,
                    z,
                    "dark_oak_trapdoor",
                    "furniture",
                    {
                        "facing": "north",
                        "half": "bottom",
                        "open": "true",
                        "powered": "false",
                        "waterlogged": "false",
                    },
                )
        dx, dy, dz = self.xyz(0, 0.5, south)
        for x in range(dx - 1, dx + 1):
            for z in range(dz - 2, dz + 2):
                self.c.set(x, dy - 1, z, "smooth_stone", "floor")
                for y in range(dy, dy + 2):
                    self.c.set(x, y, z, AIR, "air")
        for side, x in (("left", dx - 1), ("right", dx)):
            for y, half_door in ((dy, "lower"), (dy + 1, "upper")):
                self.c.set(
                    x,
                    y,
                    dz,
                    "dark_oak_door",
                    "door",
                    {
                        "half": half_door,
                        "hinge": side,
                        "facing": "south",
                        "open": "false",
                        "powered": "false",
                    },
                )
        self.features["entrance_passage"] += 1
        ex, ey, ez = self.xyz(self.g["nave_half_width_m"], 0.5, 10.6)
        # A cross aisle connects this entrance to the central aisle. The former
        # two-cell pocket stopped at pew backs despite valid door-half states.
        for x, z, _u, _v in self.columns(
            (0.0, 10.0, self.g["nave_half_width_m"] + 0.6, 11.2)
        ):
            self.c.set(x, ey - 1, z, "smooth_stone", "floor")
            for y in range(ey, ey + 4):
                self.c.set(x, y, z, AIR, "air")
        for x in range(ex - 2, ex + 3):
            for z in range(ez - 1, ez + 1):
                self.c.set(x, ey - 1, z, "smooth_stone", "floor")
                for y in range(ey, ey + 2):
                    self.c.set(x, y, z, AIR, "air")
        for hinge, z in (("left", ez - 1), ("right", ez)):
            for y, half_door in ((ey, "lower"), (ey + 1, "upper")):
                self.c.set(
                    ex,
                    y,
                    z,
                    "dark_oak_door",
                    "door",
                    {
                        "half": half_door,
                        "hinge": hinge,
                        "facing": "east",
                        "open": "false",
                        "powered": "false",
                    },
                )
        self.features["east_entrance_passage"] += 1

    def tower(self):
        u0, v0, u1, v1 = self.g["tower_bounds_uv_m"]
        height = self.g["tower_height_m"]
        self.shell((u0, v0, u1, v1), height - 1.2, height - 1.2, front=False)
        for h in (4.8, 10.7, 14.8):
            for b in (
                (u0, v0, u1, v0 + 0.5),
                (u0, v1 - 0.5, u1, v1),
                (u0, v0, u0 + 0.5, v1),
                (u1 - 0.5, v0, u1, v1),
            ):
                self.box(
                    b,
                    h,
                    h + 0.25,
                    "smooth_sandstone_slab",
                    "trim",
                    {"type": "bottom", "waterlogged": "false"},
                )
        mid = (v0 + v1) / 2
        self.arch("east", u1, mid, 1.0, 2.0, 3.4)
        # The intermediate stage is a small rectangular pair, not a lancet.
        self.box(
            (u1 - 0.65, mid - 0.65, u1 + 0.1, mid + 0.65),
            7.5,
            9.4,
            "smooth_sandstone",
            "facade",
        )
        for centre in (mid - 0.25, mid + 0.25):
            self.box(
                (u1 - 0.85, centre - 0.2, u1 + 0.25, centre + 0.2), 7.8, 9.1, AIR, "air"
            )
            self.box(
                (u1 - 0.4, centre - 0.2, u1, centre + 0.2),
                7.8,
                9.1,
                "gray_stained_glass_pane",
                "window",
            )
        for centre in (mid - 0.75, mid + 0.75):
            self.arch("east", u1, centre, 11.15, 1.2, 2.8)
            for x, z, _u, v in self.columns(
                (u1 - 0.3, centre - 0.6, u1 + 0.25, centre + 0.6)
            ):
                for y in range(
                    self.floor + round(11.2 * self.c.scale),
                    self.floor + round(13.8 * self.c.scale),
                ):
                    if self.in_arch(
                        v - centre, (y - self.floor) / self.c.scale - 11.15, 0.6, 2.8
                    ):
                        self.c.set(
                            x,
                            y,
                            z,
                            "birch_trapdoor",
                            "window",
                            {
                                "facing": "east",
                                "half": "bottom",
                                "open": "true",
                                "powered": "true",
                                "waterlogged": "false",
                            },
                        )
        self.features["paired_belfry_louvers"] += 1
        # The live pack gives this deliberate iron fixture an open metal clock
        # model, 1 m across. It does not occlude the paired louver panels.
        x, y, z = self.xyz(u1 + 0.25, 12.4, mid)
        self.c.set(
            x,
            y,
            z,
            "iron_trapdoor",
            "fixture",
            {
                "facing": "east",
                "half": "bottom",
                "open": "true",
                "powered": "true",
                "waterlogged": "false",
            },
        )
        self.features["open_metal_clock"] += 1
        # The square tower has a continuous slotted parapet. Only the separate
        # circular stair turret has the conspicuous raised merlons.
        for bounds in (
            (u0, v0, u1, v0 + 0.6),
            (u0, v1 - 0.6, u1, v1),
            (u0, v0, u0 + 0.6, v1),
            (u1 - 0.6, v0, u1, v1),
        ):
            self.box(bounds, height - 1.2, height - 0.5, self.masonry, "facade")
            self.box(bounds, height - 0.5, height, "smooth_sandstone", "facade")
        for centre in (mid - 0.9, mid, mid + 0.9):
            self.box(
                (u1 - 0.85, centre - 0.25, u1 + 0.25, centre + 0.25),
                height - 1.2,
                height - 0.5,
                AIR,
                "air",
            )
        # Polygonal stair turret beside the tower, visible in the contractor photo.
        cu, cv, radius = u1, v0 + 0.4, 1.35
        for x, z, u, v in self.columns(
            (cu - radius, cv - radius, cu + radius, cv + radius)
        ):
            r = math.hypot(u - cu, v - cv)
            if r > radius:
                continue
            for y in range(
                self.floor, self.floor + round(self.g["turret_height_m"] * self.c.scale)
            ):
                if r > radius - 0.6 or y == self.floor:
                    self.c.set(x, y, z, self.masonry, "facade")
            cap = self.floor + round(self.g["turret_height_m"] * self.c.scale)
            self.c.set(x, cap - 1, z, "stone_bricks", "facade")
            sector = int((math.atan2(v - cv, u - cu) + math.pi) * 6 / math.pi)
            if r > radius - 0.6 and sector % 2 == 0:
                self.c.set(x, cap, z, self.masonry, "facade")
        for h in (5.5, 11.5):
            self.arch("east", cu + radius - 0.2, cv, h, 0.55, 1.65)
        self.arch("south", v1, (u0 + u1) / 2, 6.0, 0.65, 2.0)
        self.features["slotted_parapet_clock_tower"] += 1
        self.features["polygonal_turret"] += 1


def add_landscape(chapel: Chapel, heights: np.ndarray):
    c, south = chapel.c, chapel.g["south_m"]
    # Photograph-backed entrance landing and staircase. Each riser is one half-metre
    # voxel with a vanilla stair providing a quarter-metre intermediate tread.
    for x, z, _u, v in chapel.columns((-2.2, south, 2.2, south + 5.0)):
        iz, ix = z - c.z_min, x - c.x_min
        if not (0 <= iz < heights.shape[0] and 0 <= ix < heights.shape[1]):
            continue
        ground = int(heights[iz, ix])
        blend = min(1, max(0, (v - south - 1) / 4))
        top = round(chapel.floor * (1 - blend) + ground * blend)
        for y in range(min(ground, top), max(ground, top) + 1):
            c.set(
                x,
                y,
                z,
                "smooth_stone" if y <= top else AIR,
                "pavement" if y <= top else "air",
            )
        for y in range(min(ground, top), top + 1):
            c.set(x, y, z, "smooth_stone", "pavement")
        if v > south + 1 and top > ground:
            c.set(
                x,
                top,
                z,
                "stone_brick_stairs",
                "trim",
                {
                    "facing": "north",
                    "half": "bottom",
                    "shape": "straight",
                    "waterlogged": "false",
                },
            )
    for side in (-1, 1):
        for v in np.arange(south + 0.5, south + 4.5, 0.5):
            x, _y, z = chapel.xyz(side * 2.25, 0, float(v))
            iz, ix = z - c.z_min, x - c.x_min
            if 0 <= iz < heights.shape[0] and 0 <= ix < heights.shape[1]:
                blend = min(1, max(0, (v - south - 1) / 4))
                top = round(chapel.floor * (1 - blend) + int(heights[iz, ix]) * blend)
                c.set(
                    x,
                    top + 2,
                    z,
                    "iron_bars",
                    "railing",
                    {
                        "north": "true",
                        "south": "true",
                        "east": "false",
                        "west": "false",
                        "waterlogged": "false",
                    },
                )
                c.set(
                    x,
                    top + 1,
                    z,
                    "iron_bars",
                    "railing",
                    {
                        "north": "true",
                        "south": "true",
                        "east": "false",
                        "west": "false",
                        "waterlogged": "false",
                    },
                )
    # Compact lanterns stand on masonry piers at the landing. The previous
    # green bars projecting from the facade were not present in the photograph.
    for u in (-2.25, 2.25):
        x, y, z = chapel.xyz(u, 1.5, south + 1.4)
        for px in (x - 1, x):
            for pz in (z - 1, z):
                for py in range(min(c.ground_at(px, pz), chapel.floor), y):
                    c.set(px, py, pz, chapel.masonry, "facade")
        c.set(
            x, y, z, "lantern", "lighting", {"hanging": "false", "waterlogged": "false"}
        )
        c.set(
            x,
            y + 1,
            z,
            "waxed_oxidized_cut_copper_slab",
            "trim",
            {"type": "bottom", "waterlogged": "false"},
        )
    x, y, z = chapel.xyz(0, 3.65, south + 0.25)
    c.set(x, y, z, "lantern", "lighting", {"hanging": "true", "waterlogged": "false"})
    c.set(
        x,
        y + 1,
        z,
        "waxed_oxidized_cut_copper_slab",
        "trim",
        {"type": "bottom", "waterlogged": "false"},
    )
    add_reference_planting(chapel)
    chapel.features["entrance_steps_and_railings"] += 1


def add_reference_planting(chapel: Chapel):
    """Photo-backed planting beds; individual plants remain interpretations."""
    c, south = chapel.c, chapel.g["south_m"]
    beds = unary_union(
        [
            Polygon(
                [(-9.4, south), (-2.9, south), (-2.9, south + 1.5), (-9.4, south + 1.5)]
            ),
            Polygon(
                [(2.9, south), (10.6, south), (10.6, south + 1.5), (2.9, south + 1.5)]
            ),
            LineString([(9.1, 5.4), (9.1, 9), (9.1, 12.3), (9.1, 20)]).buffer(0.55),
            LineString([(-9.5, 22), (-9.5, south + 0.7)]).buffer(0.45),
        ]
    )
    bed_columns = set()
    for x, z, u, v in chapel.columns(tuple(beds.bounds)):
        if not beds.covers(Point(u, v)) or (8.5 < u < 10 and 9.8 < v < 11.5):
            continue
        y = c.ground_at(x, z)
        if any(
            c.roles[h + 64, z - c.z_min, x - c.x_min]
            in {ROLES.index(r) for r in ("facade", "floor", "door", "trim")}
            for h in range(y, y + 3)
        ):
            continue
        c.set(x, y, z, "coarse_dirt", "terrain")
        bed_columns.add((x, z))
        if (x * 17 + z * 31) % 7 == 0 and c.get(x, y + 1, z) == 0:
            c.set(x, y + 1, z, "fern", "vegetation")
    # Low irregular shrubs frame the opening without blocking either entrance.
    shrubs = [
        (-8.5, south + 0.6, 0.6),
        (-6.8, south + 0.7, 0.7),
        (-4.3, south + 0.6, 0.55),
        (3.6, south + 0.6, 0.6),
        (6.8, south + 0.7, 0.7),
        (9.5, south + 0.6, 0.65),
        (9.1, 6.1, 0.5),
        (9.1, 13.8, 0.6),
        (9.1, 17.2, 0.55),
        (9.1, 19.5, 0.5),
    ]
    for u0, v0, radius in shrubs:
        for x, z, u, v in chapel.columns(
            (u0 - radius, v0 - radius, u0 + radius, v0 + radius)
        ):
            if (x, z) not in bed_columns:
                continue
            d2 = ((u - u0) / radius) ** 2 + ((v - v0) / radius) ** 2
            if d2 > 1:
                continue
            ground = c.ground_at(x, z)
            for y in range(
                ground + 1,
                ground + 1 + max(1, round(0.8 * c.scale * math.sqrt(1 - d2))),
            ):
                if c.get(x, y, z) == 0:
                    c.set(
                        x,
                        y,
                        z,
                        "oak_leaves",
                        "vegetation",
                        {"persistent": "true", "distance": "1", "waterlogged": "false"},
                    )
    chapel.features["reference_planting_bed_columns"] = len(bed_columns)
    chapel.features["interpreted_low_shrubs"] = len(shrubs)


def add_reference_paths(chapel: Chapel, heights: np.ndarray):
    """Interpret GKO SP-1 path centre lines; preserve measured elevation."""
    paths = (
        ([(13, -8), (14, -1), (13, 8), (11.5, 17), (12.5, 26), (10, 33)], 2.0),
        ([(13, 8), (21, 16), (29, 22), (38, 23)], 1.6),
        ([(13, -8), (21, -12), (34, -15)], 1.5),
        ([(0, 33), (8, 33), (12.5, 28)], 2.0),
        ([(-9.5, -7), (-9.5, 18), (-10.5, 25)], 1.25),
    )
    for points, width in paths:
        geometry = LineString(points).buffer(width / 2)
        for x, z, u, v in chapel.columns(tuple(geometry.bounds)):
            if geometry.covers(Point(u, v)):
                y = chapel.c.ground_at(x, z)
                chapel.c.set(x, y, z, "smooth_stone", "pavement")
    chapel.features["reference_path_routes"] = len(paths)


def add_pews(chapel: Chapel):
    """Two timber pew banks and centre aisle from the school's 2026 footage.

    Cushions are not inferred merely because they are common in other churches.
    Slabs form seats; upright trapdoors form thin backs and end panels.
    """
    for v in np.arange(3.0, 19.0, 1.8):
        for u0, u1 in ((-3.9, -1.0), (1.0, 3.9)):
            chapel.box(
                (u0, float(v), u1, float(v) + 0.6),
                0.5,
                1.0,
                "oak_slab",
                "furniture",
                {"type": "top", "waterlogged": "false"},
            )
            chapel.box(
                (u0, float(v) + 0.55, u1, float(v) + 1.0),
                1.0,
                1.5,
                "oak_trapdoor",
                "furniture",
                {
                    "half": "bottom",
                    "facing": "south",
                    "open": "true",
                    "powered": "false",
                    "waterlogged": "false",
                },
            )
            for u in (u0, u1 - 0.4):
                chapel.box(
                    (u, float(v), u + 0.4, float(v) + 0.6),
                    0.5,
                    1.5,
                    "oak_planks",
                    "furniture",
                )
            chapel.features["timber_pew_rows"] += 1
    # Plain timber communion table on the north platform, seen in frame 28.
    for u in (-0.8, 0.8):
        for v in (-4.0, -3.2):
            chapel.box(
                (u - 0.2, v - 0.2, u + 0.2, v + 0.2),
                0.5,
                1.5,
                "dark_oak_fence",
                "furniture",
                {
                    "north": "false",
                    "south": "false",
                    "east": "false",
                    "west": "false",
                    "waterlogged": "false",
                },
            )
    chapel.box(
        (-1.3, -4.5, 1.3, -2.8),
        1.5,
        2.0,
        "dark_oak_slab",
        "furniture",
        {"type": "bottom", "waterlogged": "false"},
    )
    chapel.features["timber_communion_table"] += 1


def connect_window_stonework(canvas: Canvas) -> int:
    """Join narrow tracery posts into their horizontal/stepped stone branches."""
    walls = [
        i
        for i, state in enumerate(canvas.palette)
        if state["Name"] == "minecraft:sandstone_wall"
    ]
    positions = np.argwhere(np.isin(canvas.data, walls))
    directions = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
    for iy, iz, ix in positions:
        x, y, z = int(ix) + canvas.x_min, int(iy) - 64, int(iz) + canvas.z_min
        props = {"up": "true", "waterlogged": "false"}
        for side, (dx, dz) in directions.items():
            connected = [
                dy
                for dy in (0, 1, -1)
                if canvas.palette[canvas.get(x + dx, y + dy, z + dz)]["Name"]
                == "minecraft:sandstone_wall"
            ]
            props[side] = "tall" if 1 in connected else "low" if connected else "none"
        canvas.set(x, y, z, "sandstone_wall", "trim", props)
    return len(positions)


def connect_window_panes(canvas: Canvas) -> int:
    """Connect the final rasterized panes, including diagonal-wall stair steps."""
    from campus_window_frames import repair_registered_pane_corners

    repair_registered_pane_corners(canvas)
    pane_ids = [
        i for i, state in enumerate(canvas.palette) if state["Name"].endswith("_pane")
    ]
    rows = np.argwhere(np.isin(canvas.data, pane_ids))
    directions = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
    changed = 0
    for iy, iz, ix in rows:
        x, y, z = int(ix) + canvas.x_min, int(iy) - 64, int(iz) + canvas.z_min
        state = canvas.palette[canvas.get(x, y, z)]
        properties = dict(state.get("Properties", {}))
        for side, (dx, dz) in directions.items():
            neighbour = canvas.palette[canvas.get(x + dx, y, z + dz)]["Name"]
            full_face = (
                neighbour != AIR
                and not neighbour.endswith(
                    (
                        "_stairs",
                        "_slab",
                        "_door",
                        "_trapdoor",
                        "_fence",
                        "_wall",
                        "_leaves",
                    )
                )
                and neighbour not in {"minecraft:lantern", "minecraft:iron_bars"}
            )
            properties[side] = (
                "true"
                if neighbour.endswith(("_pane", "_wall"))
                or neighbour == "minecraft:iron_bars"
                or full_face
                else "false"
            )
        if properties != state.get("Properties", {}):
            canvas.set(x, y, z, state["Name"], "window", properties)
            changed += 1
    return changed


def add_inferred_trees(
    canvas: Canvas, source: Path | None, canopy: Path | None
) -> dict[str, Any]:
    if source is None:
        return {"placed": 0, "evidence": "none supplied"}
    payload = json.loads(source.read_text(encoding="utf-8"))
    if canopy is None:
        raise ValueError("Inferred trees require the matching measured canopy grid")
    candidates = [
        t
        for t in payload["trees"]
        if t["confidence"] == "moderate"
        and t["height_m"] >= 14
        and t["component_occupied_area_m2"] >= 30
    ]
    # A cropped point-cloud edge cannot establish a complete crown. Avoid
    # presenting such a slice as an unusually narrow, truncated tree.
    selected = [
        t
        for t in candidates
        if canvas.x_min / canvas.scale <= t["x"] - t["crown_radius_m"]
        and t["x"] + t["crown_radius_m"]
        < (canvas.x_min + canvas.data.shape[2]) / canvas.scale
        and canvas.z_min / canvas.scale <= t["z"] - t["crown_radius_m"]
        and t["z"] + t["crown_radius_m"]
        < (canvas.z_min + canvas.data.shape[1]) / canvas.scale
    ]
    protected = np.any(
        np.isin(
            canvas.roles, [ROLES.index(r) for r in ("facade", "roof", "floor", "door")]
        ),
        axis=0,
    )
    with np.load(canopy, allow_pickle=False) as archive:
        measured = archive["canopy_p95_height_m"]
        if (
            measured.shape != protected.shape
            or float(archive["resolution_m"]) != 1 / canvas.scale
            or int(archive["x_min"]) * canvas.scale != canvas.x_min
            or int(archive["z_min"]) * canvas.scale != canvas.z_min
        ):
            raise ValueError("Canopy and sample grids do not align")
        valid = archive["candidate_point_count"] > 0
    nearest = distance_transform_edt(
        ~valid, return_distances=False, return_indices=True
    )
    top_heights = gaussian_filter(measured[tuple(nearest)], sigma=2.0)
    outlines = unary_union([Polygon(tree["crown_outline_xz"]) for tree in selected])
    zz, xx = np.indices(protected.shape)
    east = (xx + canvas.x_min + 0.5) / canvas.scale
    south = (zz + canvas.z_min + 0.5) / canvas.scale
    crown_mask = contains_xy(outlines, east, south)
    minimum_crown_height = np.zeros(protected.shape)
    for tree in selected:
        mask = contains_xy(Polygon(tree["crown_outline_xz"]), east, south)
        minimum_crown_height[mask] = np.maximum(
            minimum_crown_height[mask], tree["height_m"] * 0.6
        )
    # Low branch/trunk returns are not foliage columns. Round the lower canopy
    # at its perimeter instead of extruding a vertical curtain from every hit.
    crown_mask &= top_heights >= minimum_crown_height
    edge_distance = distance_transform_edt(crown_mask) / canvas.scale
    # Each crown follows its measured horizontal outline and height surface.
    # Only the lower foliage envelope, branching and species are interpreted.
    for iz, ix in np.ndindex(protected.shape):
        x, z = canvas.x_min + ix, canvas.z_min + iz
        if protected[iz, ix] or not crown_mask[iz, ix]:
            continue
        h = float(top_heights[iz, ix])
        top = int(canvas.ground_heights[iz, ix]) + round(h * canvas.scale)
        thickness = (
            min(6.5, max(2.5, h * 0.3))
            * min(1.0, math.sqrt(edge_distance[iz, ix] / 2))
            * canvas.scale
        )
        for y in range(round(top - thickness), top + 1):
            if canvas.get(x, y, z) == 0:
                canvas.set(
                    x,
                    y,
                    z,
                    "oak_leaves",
                    "vegetation",
                    {"persistent": "true", "distance": "1", "waterlogged": "false"},
                )
    for tree in selected:
        cx, cz = tree["x"] * canvas.scale, tree["z"] * canvas.scale
        ix, iz = round(cx) - canvas.x_min, round(cz) - canvas.z_min
        if (
            not (0 <= ix < protected.shape[1] and 0 <= iz < protected.shape[0])
            or protected[iz, ix]
        ):
            continue
        ground = int(canvas.ground_heights[iz, ix])
        height = tree["height_m"] * canvas.scale
        radius = tree["crown_radius_m"] * canvas.scale
        top = ground + height
        crown_y = top - radius * 0.85
        for y in range(ground + 1, round(crown_y + radius * 0.25)):
            for dx in (0, 1):
                for dz in (0, 1):
                    canvas.set(
                        round(cx) + dx,
                        y,
                        round(cz) + dz,
                        "oak_log",
                        "vegetation",
                        {"axis": "y"},
                    )
        for angle in (0.2, 1.7, 3.4, 5.0):
            for t in np.linspace(0, 1, max(2, round(radius * 2))):
                x = round(cx + math.cos(angle) * radius * 0.6 * t)
                z = round(cz + math.sin(angle) * radius * 0.6 * t)
                y = round(top - radius * 0.9 + t * radius * 0.55)
                if (
                    canvas.x_min <= x < canvas.x_min + protected.shape[1]
                    and canvas.z_min <= z < canvas.z_min + protected.shape[0]
                    and not protected[z - canvas.z_min, x - canvas.x_min]
                ):
                    # Keep secondary branches within the interpreted crown,
                    # rather than projecting bare horizontal stubs into air.
                    nearby_leaves = any(
                        canvas.palette[canvas.get(x + dx, y + dy, z + dz)][
                            "Name"
                        ].endswith("_leaves")
                        for dx, dy, dz in (
                            (0, 1, 0),
                            (0, 0, 1),
                            (0, 0, -1),
                            (1, 0, 0),
                            (-1, 0, 0),
                        )
                    )
                    if t > 0.2 and not nearby_leaves:
                        continue
                    canvas.set(
                        x,
                        y,
                        z,
                        "oak_log",
                        "vegetation",
                        {
                            "axis": "x"
                            if abs(math.cos(angle)) > abs(math.sin(angle))
                            else "z"
                        },
                    )
    return {
        "placed": len(selected),
        "source": str(source),
        "sha256": digest(source),
        "canopy": {"path": str(canopy), "sha256": digest(canopy)},
        "placement": "inferred broadleaf crowns using LiDAR outline and height surface smoothed at 1 metre; lower crown envelope, species and trunk positions interpreted",
        "rejected_small_or_ambiguous": len(payload["trees"]) - len(candidates),
        "rejected_crop_edge_crowns": len(candidates) - len(selected),
    }


def write_world(
    canvas: Canvas,
    target: Path,
    name: str,
    spawn: tuple[int, int, int],
    level_template: Path,
):
    (target / "region").mkdir(parents=True)
    # Copy only level metadata; copied audits/old chunks must never enter this world.
    level = nbtlib.load(level_template)
    d = level["Data"]
    for key in ("Player", "DragonFight", "CustomBossEvents", "Bukkit", "BukkitValues"):
        d.pop(key, None)
    d.update(
        {
            "LevelName": tag.String(name),
            "DataVersion": tag.Int(3700),
            "GameType": tag.Int(1),
            "allowCommands": tag.Byte(1),
            "Difficulty": tag.Byte(0),
            "raining": tag.Byte(0),
            "thundering": tag.Byte(0),
            "Time": tag.Long(6000),
            "DayTime": tag.Long(6000),
            "SpawnX": tag.Int(spawn[0]),
            "SpawnY": tag.Int(spawn[1]),
            "SpawnZ": tag.Int(spawn[2]),
        }
    )
    d["Version"] = tag.Compound(
        {
            "Id": tag.Int(3700),
            "Name": tag.String("1.20.4"),
            "Series": tag.String("main"),
            "Snapshot": tag.Byte(0),
        }
    )
    d["DataPacks"] = tag.Compound(
        {
            "Enabled": tag.List[tag.String]([tag.String("vanilla")]),
            "Disabled": tag.List[tag.String]([]),
        }
    )
    d["GameRules"] = tag.Compound(
        {
            key: tag.String(value)
            for key, value in {
                "doDaylightCycle": "false",
                "doWeatherCycle": "false",
                "doMobSpawning": "false",
                "randomTickSpeed": "0",
                "doFireTick": "false",
                "spawnRadius": "0",
            }.items()
        }
    )
    d["WorldGenSettings"]["dimensions"]["minecraft:overworld"]["generator"] = (
        tag.Compound(
            {
                "type": tag.String("minecraft:flat"),
                "settings": tag.Compound(
                    {
                        "biome": tag.String("minecraft:plains"),
                        "lakes": tag.Byte(0),
                        "features": tag.Byte(0),
                        "layers": tag.List[tag.Compound]([]),
                        "structure_overrides": tag.List[tag.String]([]),
                    }
                ),
            }
        )
    )
    level.save(target / "level.dat")
    regions: dict[tuple[int, int], anvil.RegionEditor] = {}
    count = 0
    bell_states = {i for i, state in enumerate(canvas.palette)
                   if state["Name"] == "minecraft:bell"}
    x_max = canvas.x_min + canvas.data.shape[2]
    z_max = canvas.z_min + canvas.data.shape[1]
    for cz in range(canvas.z_min // 16, math.ceil(z_max / 16)):
        for cx in range(canvas.x_min // 16, math.ceil(x_max / 16)):
            sections = []
            block_entities = []
            for sy in range(-4, 20):
                data = np.zeros((16, 16, 16), dtype=np.uint16)
                x0, x1 = max(cx * 16, canvas.x_min), min(cx * 16 + 16, x_max)
                z0, z1 = max(cz * 16, canvas.z_min), min(cz * 16 + 16, z_max)
                data[:, z0 - cz * 16 : z1 - cz * 16, x0 - cx * 16 : x1 - cx * 16] = (
                    canvas.data[
                        (sy + 4) * 16 : (sy + 5) * 16,
                        z0 - canvas.z_min : z1 - canvas.z_min,
                        x0 - canvas.x_min : x1 - canvas.x_min,
                    ]
                )
                used, inverse = np.unique(data, return_inverse=True)
                # Bells render through their block entity. A palette state
                # alone exports an invisible fixture in native Minecraft.
                for state_id in bell_states.intersection(used):
                    for by, bz, bx in np.argwhere(data == state_id):
                        block_entities.append(tag.Compound({
                            "id": tag.String("minecraft:bell"),
                            "x": tag.Int(cx * 16 + int(bx)),
                            "y": tag.Int(sy * 16 + int(by)),
                            "z": tag.Int(cz * 16 + int(bz)),
                        }))
                entries = [
                    anvil.block_entry(
                        canvas.palette[int(i)]["Name"],
                        canvas.palette[int(i)].get("Properties"),
                    )
                    for i in used
                ]
                states = tag.Compound({"palette": tag.List[tag.Compound](entries)})
                if len(entries) > 1:
                    states["data"] = tag.LongArray(
                        anvil.pack_indices(inverse.ravel().tolist(), len(entries))
                    )
                sections.append(
                    tag.Compound(
                        {
                            "Y": tag.Byte(sy),
                            "block_states": states,
                            "biomes": tag.Compound(
                                {
                                    "palette": tag.List[tag.String](
                                        [tag.String("minecraft:plains")]
                                    )
                                }
                            ),
                        }
                    )
                )
            root = nbtlib.File(
                {
                    "DataVersion": tag.Int(3700),
                    "xPos": tag.Int(cx),
                    "zPos": tag.Int(cz),
                    "yPos": tag.Int(-4),
                    "Status": tag.String("minecraft:full"),
                    "LastUpdate": tag.Long(0),
                    "InhabitedTime": tag.Long(0),
                    "isLightOn": tag.Byte(0),
                    "sections": tag.List[tag.Compound](sections),
                    "block_entities": tag.List[tag.Compound](block_entities),
                    "block_ticks": tag.List[tag.Compound]([]),
                    "fluid_ticks": tag.List[tag.Compound]([]),
                    "structures": tag.Compound(
                        {"starts": tag.Compound({}), "References": tag.Compound({})}
                    ),
                }
            )
            key = (cx // 32, cz // 32)
            region = regions.setdefault(
                key, anvil.RegionEditor(target / "region" / f"r.{key[0]}.{key[1]}.mca")
            )
            index = anvil.region_chunk_index(cx, cz)
            region.raw_records[index] = anvil.serialize_chunk_record(root)
            region.modified.add(index)
            count += 1
    for region in regions.values():
        region.save()
    return {"chunks": count, "regions": len(regions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--level-template", type=Path, default=anvil.DEFAULT_SOURCE_WORLD / "level.dat"
    )
    parser.add_argument("--vertical-offset", type=float, default=24.25)
    parser.add_argument("--inferred-trees", type=Path)
    parser.add_argument("--inferred-canopy", type=Path)
    parser.add_argument("--academic-profile", type=Path)
    parser.add_argument("--accepted-sample", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Choose a fresh study output directory: {args.output}")
    accepted_evidence = None
    if args.academic_profile:
        if args.accepted_sample is None:
            parser.error("--academic-profile requires --accepted-sample")
        from audit_hill_chapel_sample import audit_study

        previous = audit_study(args.accepted_sample)
        if previous["status"] != "pass" or not previous["visual_gate"].get(
            "larger_area_authorized"
        ):
            raise ValueError(
                "The previous small sample has no verified visual acceptance"
            )
        accepted_evidence = {
            "study": str(args.accepted_sample.resolve()),
            "manifest_sha256": digest(args.accepted_sample / "manifest.json"),
            "visual_review_sha256": digest(args.accepted_sample / "visual-review.json"),
            "sample_blocks_sha256": digest(args.accepted_sample / "sample-blocks.npz"),
        }
    elif args.accepted_sample:
        parser.error("--accepted-sample is only used with --academic-profile")
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    scale = int(profile["blocks_per_metre"])
    elevations, ids, metadata = terrain_arrays(args.terrain, scale)
    if elevations.size > 100_000:
        raise ValueError(
            "This study is deliberately limited to 100,000 ground columns; pass the small visual gate before expanding."
        )
    canvas = Canvas(
        metadata["x_min"] * scale,
        metadata["z_min"] * scale,
        elevations.shape[1],
        elevations.shape[0],
        scale,
    )
    heights = build_ground(
        canvas, elevations, ids, metadata["materials"], args.vertical_offset
    )
    chapel = Chapel(canvas, profile, args.vertical_offset)
    add_reference_paths(chapel, heights)
    paving_qa = smooth_exposed_measured_pavement(
        canvas, elevations, heights, vertical_offset=args.vertical_offset
    )
    chapel.build()
    add_landscape(chapel, heights)
    add_pews(chapel)
    chapel.place_entry()
    academic_evidence = None
    if args.academic_profile:
        from campus_academic_building import build_academic_complex

        academic_evidence = build_academic_complex(
            canvas, args.academic_profile, args.vertical_offset
        )
    chapel.features["connected_tracery_posts"] = connect_window_stonework(canvas)
    chapel.features["pane_states_connected_after_rasterization"] = connect_window_panes(
        canvas
    )
    tree_evidence = add_inferred_trees(
        canvas, args.inferred_trees, args.inferred_canopy
    )
    args.output.mkdir(parents=True)
    npz_path = args.output / "sample-blocks.npz"
    palette_counts = canvas.export(npz_path)
    material_roles = {}
    for role_index, role in enumerate(ROLES[1:], 1):
        values, counts = np.unique(
            canvas.data[canvas.roles == role_index], return_counts=True
        )
        role_counts: Counter[str] = Counter()
        for value, count in zip(values, counts):
            if value:
                role_counts[canvas.palette[int(value)]["Name"]] += int(count)
        if role_counts:
            material_roles[role] = dict(role_counts)
    material_violations = audit_role_materials(material_roles)
    if material_violations:
        raise ValueError(
            f"Material policy failed; world export withheld: {material_violations}"
        )
    spawn = chapel.xyz(0, 3.0, profile["geometry"]["south_m"] + 9)
    world_stats = write_world(
        canvas,
        args.output / "world",
        (
            "Hill Chapel and academic courts — measured study"
            if academic_evidence
            else "Hill Chapel — measured terrain study"
        ),
        spawn,
        args.level_template,
    )
    manifest = {
        "format": "hill-chapel-study-v1",
        "created_unix": int(time.time()),
        "profile": {"path": str(args.profile), "sha256": digest(args.profile)},
        "terrain": {"path": str(args.terrain), "sha256": digest(args.terrain)},
        "blocks_per_metre": scale,
        "bounds": [
            canvas.x_min,
            int(heights.min()) - 12 * scale,
            canvas.z_min,
            canvas.x_min + canvas.data.shape[2],
            int(np.nonzero(canvas.data)[0].max()) - 64,
            canvas.z_min + canvas.data.shape[1],
        ],
        "terrain_y_range": [int(heights.min()), int(heights.max())],
        "world": world_stats,
        "features": dict(chapel.features),
        "material_roles": material_roles,
        "materials": palette_counts,
        "clipped_writes": canvas.clipped,
        "uncertainties": profile["uncertainties"],
        "visual_gate": {
            "native_minecraft_review": "pending",
            "matched_current_photo": "pending",
            "larger_area_authorized_by_quality_gate": False,
        },
    }
    manifest["material_audit"] = material_violations
    manifest["trees"] = tree_evidence
    manifest["paving"] = paving_qa
    if academic_evidence:
        manifest["academic_complex"] = academic_evidence
        manifest["accepted_previous_sample"] = accepted_evidence
        academic_snapshot = args.output / "academic-profile.json"
        shutil.copyfile(args.academic_profile, academic_snapshot)
        manifest["academic_complex"]["profile"] = {
            "path": str(academic_snapshot.resolve()),
            "source_path": str(args.academic_profile),
            "sha256": digest(academic_snapshot),
        }
    # Store the exact profile beside the world: future edits to the working
    # profile must not make historical study provenance stale or irreproducible.
    pack_source = profile.get("materials", {}).get("resource_pack")
    if pack_source:
        pack_source = ROOT / pack_source
        pack_snapshot = args.output / "resourcepacks" / pack_source.name
        shutil.copytree(pack_source, pack_snapshot)
        profile["materials"]["resource_pack"] = str(pack_snapshot.resolve())
        manifest["resource_pack"] = {
            "path": str(pack_snapshot.resolve()),
            "files": {
                str(p.relative_to(pack_snapshot)).replace("\\", "/"): digest(p)
                for p in sorted(pack_snapshot.rglob("*"))
                if p.is_file()
            },
        }
    profile_snapshot = args.output / "profile.json"
    profile_snapshot.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    manifest["profile"] = {
        "path": str(profile_snapshot.resolve()),
        "source_path": str(args.profile),
        "sha256": digest(profile_snapshot),
    }
    manifest["block_count"] = int(np.count_nonzero(canvas.data))
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "features": manifest["features"],
                "world": world_stats,
                "clipped_writes": canvas.clipped,
                "visual_gate": manifest["visual_gate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
