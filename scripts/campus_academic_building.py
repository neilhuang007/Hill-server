"""Photo-informed academic exteriors on a measured, hollow Roofer envelope.

This is an explicitly interpreted exterior study. The profile distinguishes
measured roof geometry from estimated opening dimensions and facade rhythms.
Local U follows Athey's long axis eastward; local V points toward Dining Hall.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from campus_measured_shell import build_measured_shell
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_window_frames import bridge_frame_edges

ROOT = Path(__file__).resolve().parents[1]
PANE_PROPS = {
    "north": "false",
    "south": "false",
    "east": "false",
    "west": "false",
    "waterlogged": "false",
}


class AcademicExterior:
    def __init__(self, canvas: Any, profile: dict, raster: Any, offset: float):
        self.c, self.p, self.r, self.offset = canvas, profile, raster, offset
        self.g = profile["geometry"]
        self.origin = np.array(self.g["origin_xz_m"], dtype=float)
        angle = math.radians(self.g["axis_degrees"])
        self.t = np.array([math.cos(angle), math.sin(angle)])
        self.n = np.array([-math.sin(angle), math.cos(angle)])
        zi, xi = np.indices(raster.heights.shape)
        self.x = (xi + canvas.x_min + 0.5) / canvas.scale
        self.z = (zi + canvas.z_min + 0.5) / canvas.scale
        dx, dz = self.x - self.origin[0], self.z - self.origin[1]
        self.u = dx * self.t[0] + dz * self.t[1]
        self.v = dx * self.n[0] + dz * self.n[1]
        self.features: Counter[str] = Counter()

    def world(self, u: float, v: float) -> np.ndarray:
        return self.origin + u * self.t + v * self.n

    def height_y(self, navd: float) -> int:
        return round((navd + self.offset) * self.c.scale)

    def each_column(self, mask: np.ndarray):
        for iz, ix in np.argwhere(mask):
            yield int(ix + self.c.x_min), int(iz + self.c.z_min), int(iz), int(ix)

    def local_mask(self, bounds: list[float]) -> np.ndarray:
        u0, v0, u1, v1 = bounds
        return (self.u >= u0) & (self.u < u1) & (self.v >= v0) & (self.v < v1)

    def edge_v(self, u: float, side: str) -> float | None:
        candidates = (
            (np.abs(self.u - u) <= 0.3)
            & (self.v > -12)
            & (self.v < 24)
            & (self.r.heights >= self.g["main_roof_threshold_navd88_m"])
        )
        values = self.v[candidates]
        if not len(values):
            return None
        return float(values.min() if side == "north" else values.max())

    @staticmethod
    def in_opening(d: float, h: float, width: float, height: float, shape: str) -> bool:
        if abs(d) > width / 2 or h < 0 or h > height:
            return False
        if shape == "circle":
            return (d / (width / 2)) ** 2 + ((h - height / 2) / (height / 2)) ** 2 <= 1
        if shape == "triangle":
            return h / height <= 1 - abs(d) / (width / 2)
        if shape == "round":
            radius = min(width / 2, height / 2)
            spring = height - radius
            return (
                h <= spring
                or (d / (width / 2)) ** 2 + ((h - spring) / radius) ** 2 <= 1
            )
        if shape == "pointed":
            half = width / 2
            rise = min(height * 0.42, width * 0.65)
            spring = height - rise
            center = (rise * rise - half * half) / (2 * half)
            radius = half + center
            return (
                h <= spring
                or (abs(d) + center) ** 2 + (h - spring) ** 2 <= radius * radius
            )
        return True

    def opening(
        self,
        u: float,
        side: str,
        sill: float,
        width: float,
        height: float,
        shape: str = "rectangle",
        lights: int = 2,
        at: float | None = None,
        transom: float | None = None,
    ) -> None:
        if side in {"east", "west"}:
            candidates = (np.abs(self.v - u) <= 0.3) & (
                self.r.heights >= self.g["main_roof_threshold_navd88_m"]
            )
            values = self.u[candidates]
            v = (
                at
                if at is not None
                else (
                    float(values.max() if side == "east" else values.min())
                    if len(values)
                    else None
                )
            )
            along = self.n
        else:
            v = self.edge_v(u, side) if at is None else at
            along = self.t
        if v is None:
            self.features["opening_without_measured_wall"] += 1
            return
        end = side in {"east", "west"}
        center = self.world(v, u) if end else self.world(u, v)
        outward = (
            self.t * (1 if side == "east" else -1)
            if end
            else self.n * (-1 if side == "north" else 1)
        )
        d = (self.x - center[0]) * along[0] + (self.z - center[1]) * along[1]
        depth = (self.x - center[0]) * outward[0] + (self.z - center[1]) * outward[1]
        reveal = self.p.get("window_reveal", {})
        border = reveal.get("trim_width_m", reveal.get("border_m", 0.26))
        recess = self.p.get("window_reveal", {}).get("glass_recess_m", 0.0)
        trim_family = self.p.get("window_reveal", {}).get("trim_family", "quartz")
        trim_block = {
            "quartz": "quartz_block",
            "mud_brick": "mud_bricks",
            "stone_brick": "stone_bricks",
        }.get(trim_family, trim_family)
        trim_block = self.p.get("window_reveal", {}).get("trim_block", trim_block)
        extent = width / 2 + border
        mask = (np.abs(d) <= extent) & (depth >= -2.5) & (depth <= 1.5)
        # The LiDAR wall can have small setbacks inside one opening group.
        # Follow that actual masonry contour along the opening: a single
        # constant plane either floats in front or loses half its surround.
        bins = np.clip(
            np.floor((d + extent) * self.c.scale).astype(int),
            0,
            math.ceil(2 * extent * self.c.scale),
        )
        contour = np.full(math.ceil(2 * extent * self.c.scale) + 1, -np.inf)
        source = mask & self.r.footprint_mask & (self.r.heights >= sill + height / 2)
        np.maximum.at(contour, bins[source], depth[source])
        known = np.flatnonzero(np.isfinite(contour))
        if not known.size:
            self.features["opening_without_measured_wall"] += 1
            return
        contour = np.interp(np.arange(len(contour)), known, contour[known])
        local_depth = depth - contour[bins]
        mask &= local_depth >= -1.35
        half_sheet = (abs(outward[0]) + abs(outward[1])) / (2 * self.c.scale) + 1e-6
        posts = np.linspace(-width / 2, width / 2, lights + 1)[1:-1]
        # At two blocks/metre a sub-voxel mullion can miss every sample on a
        # diagonal pane sheet. Give it at least one raster cell of support.
        post_half_width = max(
            0.16, (abs(along[0]) + abs(along[1])) / (2 * self.c.scale)
        )
        transom_half_height = max(0.115, 0.5 / self.c.scale)
        pane_count = 0
        reveal_cells = set()
        corner_cells = set()
        for x, z, iz, ix in self.each_column(mask):
            distance = float(d[iz, ix])
            dep = float(local_depth[iz, ix])
            outside = (
                np.array([(x + 0.5) / self.c.scale, (z + 0.5) / self.c.scale])
                + outward * 1.3
            )
            ox, oz = np.floor(outside * self.c.scale).astype(int)
            exterior_grade = self.c.ground_at(int(ox), int(oz))
            for y in range(
                self.height_y(sill - border), self.height_y(sill + height + border) + 1
            ):
                h = (y + 0.5) / self.c.scale - self.offset - sill
                inside = self.in_opening(distance, h, width, height, shape)
                outer = self.in_opening(
                    distance, h + border, width + 2 * border, height + 2 * border, shape
                )
                if not outer or y <= exterior_grade:
                    continue
                in_envelope = bool(self.r.footprint_mask[iz, ix]) and (
                    (y + 0.5) / self.c.scale - self.offset <= self.r.heights[iz, ix]
                )
                # A contour bin can span both a tall wall and its low porch.
                # Do not copy the tall wall's glazing into air above that roof,
                # or cut an unrelated detail outside this wall's envelope.
                if not in_envelope:
                    continue
                if (
                    -1.35 <= dep + recess <= half_sheet + 1 / self.c.scale
                ):
                    # An L-return can fall just outside the glass silhouette
                    # while still being inside the authorised frame/reveal.
                    # Include the depth already cut from this reveal: a
                    # stepped measured wall may need its inward corner there.
                    corner_cells.add((x, y, z))
                if inside:
                    if (
                        self.r.footprint_mask[iz, ix]
                        and abs(dep + recess) <= half_sheet + 1 / self.c.scale
                    ):
                        reveal_cells.add((x, y, z))
                    if (
                        abs(dep + recess) <= half_sheet
                        and self.r.footprint_mask[iz, ix]
                    ):
                        if shape != "circle" and (
                            any(
                                abs(distance - post) <= post_half_width
                                for post in posts
                            )
                            or (
                                transom is not None
                                and abs(h - transom) < transom_half_height
                            )
                        ):
                            mullion = reveal.get("mullion_block", trim_block)
                            self.c.set(
                                x, y, z, mullion, "trim",
                                PANE_PROPS if mullion == "iron_bars" else None,
                            )
                        else:
                            self.c.set(
                                x,
                                y,
                                z,
                                self.p.get("window_reveal", {}).get(
                                    "glass_block", "gray_stained_glass_pane"
                                ),
                                "window",
                                PANE_PROPS,
                            )
                            pane_count += 1
                    else:
                        self.c.set(x, y, z, "air", "air")
                elif -recess - half_sheet <= dep <= half_sheet:
                    # The trim belongs in the masonry, not on an added box.
                    # A roof footprint alone is insufficient at a low bay:
                    # also require that the roof lies above this window cell.
                    existing = self.c.palette[self.c.get(x, y, z)]["Name"]
                    in_wall = existing in {
                        "minecraft:bricks",
                        "minecraft:quartz_block",
                        "minecraft:stone_bricks",
                        "minecraft:"
                        + self.p.get("materials", {}).get("facade", "bricks"),
                        "minecraft:" + trim_block,
                    }
                    if not in_envelope or (dep > -half_sheet and not in_wall):
                        continue
                    # Inverted stairs remove the square inner corner of an
                    # arch. They stay in the original wall's raster envelope.
                    round_corner = (
                        shape in {"round", "circle", "pointed"}
                        and h > height - width / 2
                        and abs(distance) > width * 0.18
                    )
                    if round_corner:
                        direction = along * (1 if distance > 0 else -1)
                        facing = (
                            ("east" if direction[0] > 0 else "west")
                            if abs(direction[0]) >= abs(direction[1])
                            else ("south" if direction[1] > 0 else "north")
                        )
                        self.c.set(
                            x,
                            y,
                            z,
                            trim_family + "_stairs",
                            "trim",
                            {
                                "facing": facing,
                                "half": "top",
                                "shape": "straight",
                                "waterlogged": "false",
                            },
                        )
                    elif h < 0:
                        self.c.set(
                            x,
                            y,
                            z,
                            trim_family + "_slab",
                            "trim",
                            {"type": "top", "waterlogged": "false"},
                        )
                    else:
                        self.c.set(x, y, z, trim_block, "trim")
        if recess < 0.25:
            self.features["pane_frame_edge_connectors"] += bridge_frame_edges(
                self.c, reveal_cells, inward=-outward, corner_allowed=corner_cells
            )
            # The inserted return is inside the wall but can sit behind the
            # original thin head/sill. Complete only its concealed frame cap.
            caps = set()
            for x, y, z in corner_cells:
                iz, ix = z - self.c.z_min, x - self.c.x_min
                for dy in (-1, 1):
                    yy = y + dy
                    if (yy > self.c.ground_at(x, z) and
                        (yy + 0.5) / self.c.scale - self.offset <= self.r.heights[iz, ix]):
                        caps.add((x, yy, z))
            if not hasattr(self.c, "window_cap_regions"):
                self.c.window_cap_regions = []
            # Defer completion until all facade passes finish. An early cap
            # must not become a false jamb for a later overlapping opening.
            self.c.window_cap_regions.append((corner_cells, caps, trim_block))
        self.features[f"{side}_{shape}_window_groups"] += int(pane_count > 0)

    def bands(self) -> None:
        mask = (
            (self.u > 2)
            & (self.u < 73)
            & (self.v > -12)
            & (self.v < 24)
            & (self.r.heights >= self.g["main_roof_threshold_navd88_m"])
        )
        for height in self.g["continuous_bands_navd88_m"]:
            y = self.height_y(height)
            for x, z, _, _ in self.each_column(mask):
                state = self.c.palette[self.c.get(x, y, z)]["Name"]
                if state != "minecraft:bricks":
                    continue
                if any(
                    self.c.get(x + dx, y, z + dz) == 0
                    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                ):
                    self.c.set(x, y, z, "quartz_block", "trim")
                    self.features["pale_stringcourse_blocks"] += 1

    def gable_coping(self) -> None:
        center = self.g["central_bay_u_m"]
        for side in ("north", "south"):
            for u in np.arange(center - 5.0, center + 5.01, 0.25):
                v = self.edge_v(float(u), side)
                if v is None:
                    continue
                p = self.world(float(u), v)
                x, z = np.floor(p * self.c.scale).astype(int)
                iz, ix = z - self.c.z_min, x - self.c.x_min
                if not math.isfinite(self.r.heights[iz, ix]):
                    continue
                y0 = self.height_y(float(self.r.heights[iz, ix]))
                for y in range(y0 - 1, y0 + 3):
                    entry = self.c.palette[self.c.get(int(x), y, int(z))]
                    name = entry["Name"]
                    if name.startswith(
                        "minecraft:" + self.p["materials"]["roof_family"]
                    ):
                        target = (
                            "quartz_stairs"
                            if name.endswith("_stairs")
                            else "quartz_slab"
                            if name.endswith("_slab")
                            else "quartz_block"
                        )
                        self.c.set(
                            int(x), y, int(z), target, "trim", entry.get("Properties")
                        )
                        self.features["central_gable_coping_blocks"] += 1

    def court_and_links(self) -> None:
        # Pavers follow the measured surface; no planar court excavation.
        court = self.local_mask(self.g["court_bounds_uv_m"]) & ~self.r.footprint_mask
        for x, z, _, _ in self.each_column(court):
            self.c.set(x, self.c.ground_at(x, z), z, "bricks", "pavement")
            self.features["court_brick_paver_columns"] += 1
        for link in self.g["covered_links"]:
            if not link["open_passage"]:
                continue
            u0, v0, u1, v1 = link["bounds_uv_m"]
            mask = (
                self.local_mask(link["bounds_uv_m"])
                & self.r.footprint_mask
                & (self.r.heights < 76)
            )
            centres = np.linspace(v0 + 1.0, v1 - 1.0, 5)
            for x, z, iz, ix in self.each_column(mask):
                ground = self.c.ground_at(x, z)
                roof = self.height_y(float(self.r.heights[iz, ix]))
                pier = (
                    min(self.u[iz, ix] - u0, u1 - self.u[iz, ix]) < 0.65
                    and np.min(np.abs(centres - self.v[iz, ix])) < 0.6
                )
                for y in range(self.height_y(65.8), ground + 1):
                    self.c.set(
                        x,
                        y,
                        z,
                        "stone_bricks" if y < ground else "smooth_stone",
                        "facade" if y < ground else "floor",
                    )
                for y in range(ground + 1, roof):
                    self.c.set(
                        x,
                        y,
                        z,
                        "bricks" if pier else "air",
                        "facade" if pier else "air",
                    )
                if pier:
                    self.c.set(x, roof - 1, z, "quartz_block", "trim")
                # The reference link has a pale metal roof. Smooth stone is a
                # geometric proxy; its exact standing seams are not yet modeled.
                for y in range(roof - 1, roof + 3):
                    entry = self.c.palette[self.c.get(x, y, z)]
                    if entry["Name"].startswith(
                        "minecraft:" + self.p["materials"]["roof_family"]
                    ):
                        self.c.set(
                            x,
                            y,
                            z,
                            "smooth_stone_slab",
                            "roof",
                            {"type": "bottom", "waterlogged": "false"},
                        )
                self.features["open_east_link_columns"] += 1

    def build(self) -> dict[str, int]:
        self.court_and_links()
        self.bands()
        for side in ("north", "south"):
            elevation = self.p.get("elevations", {}).get(side, {})
            sills = elevation.get(
                "window_sills_navd88_m", self.g["window_sills_navd88_m"]
            )
            for row, sill in enumerate(sills):
                shape = (
                    "round"
                    if side == "north" and abs(sill - 71.5) < 0.1
                    else "rectangle"
                )
                height = (
                    self.g["round_arch_height_m"]
                    if shape == "round"
                    else self.g["window_height_m"]
                )
                for u in elevation.get(
                    "flank_window_centres_u_m", self.g["flank_window_centres_u_m"]
                ):
                    self.opening(
                        u,
                        side,
                        sill,
                        self.g["flank_window_width_m"],
                        height,
                        shape,
                        lights=elevation.get("lights", 2),
                        transom=elevation.get("transom_height_m"),
                    )
                if not (side == "north" and row == 0 and self.p.get("east_return")):
                    self.opening(
                        self.g["central_bay_u_m"],
                        side,
                        sill,
                        self.g["central_window_width_m"],
                        self.g["window_height_m"],
                        lights=3,
                    )
            self.opening(
                self.g["central_bay_u_m"],
                side,
                self.g["oculus_sill_navd88_m"],
                self.g["oculus_diameter_m"],
                self.g["oculus_diameter_m"],
                "circle",
                1,
            )
        self.gable_coping()
        return dict(self.features)


def build_academic_complex(
    canvas: Any, profile_path: Path, vertical_offset: float
) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    source = (ROOT / profile["source_cityjson"]).resolve()
    terrain_manifest = (ROOT / profile["measured_terrain_manifest"]).resolve()
    building = load_measured_building(source, profile["parent_id"], terrain_manifest)
    bounds = (
        canvas.x_min / canvas.scale,
        canvas.z_min / canvas.scale,
        (canvas.x_min + canvas.data.shape[2]) / canvas.scale,
        (canvas.z_min + canvas.data.shape[1]) / canvas.scale,
    )
    bx0, bz0, bx1, bz1 = building.footprint.bounds
    if not (bounds[0] < bx0 < bx1 < bounds[2] and bounds[1] < bz0 < bz1 < bounds[3]):
        raise ValueError("Academic complex must fit wholly inside the bounded study")
    raster = rasterize_roof(building, bounds, 1 / canvas.scale)
    if np.any(raster.missing_mask):
        raise ValueError(
            f"Measured academic roof has uncovered columns: {raster.coverage_report}"
        )
    materials = profile["materials"]
    shell = build_measured_shell(
        canvas,
        building,
        raster,
        vertical_offset=vertical_offset,
        facade=materials["facade"],
        foundation=materials["foundation"],
        roof_family=materials["roof_family"],
    )
    features = AcademicExterior(canvas, profile, raster, vertical_offset).build()
    return {
        "source_cityjson": {"path": str(source), "sha256": building.source_sha256},
        "measured_terrain_manifest": {
            "path": str(terrain_manifest),
            "sha256": hashlib.sha256(terrain_manifest.read_bytes()).hexdigest(),
        },
        "parent_id": building.parent_id,
        "part_ids": list(building.part_ids),
        "footprint_area_m2": building.footprint.area,
        "footprint_bounds_m": list(building.footprint.bounds),
        "source_height_navd88_m": [building.source_base, building.source_max],
        "roof_coverage": raster.coverage_report,
        "shell": shell,
        "features": features,
        "uncertainties": profile["uncertainties"],
    }
