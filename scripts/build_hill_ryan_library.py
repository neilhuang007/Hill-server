"""Measured Ryan Library with photograph-supported west arcade and facade groups."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from build_hill_chapel_sample import (
    ROLES,
    Canvas,
    build_ground,
    connect_window_panes,
    terrain_arrays,
)
from campus_academic_building import PANE_PROPS
from campus_athey_details import AtheyExterior, connect_iron_rails
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study
from scipy.ndimage import binary_erosion

ROOT = Path(__file__).resolve().parents[1]


class RyanExterior(AtheyExterior):
    def west_site(self):
        # OSM way 263155560 is tagged service/asphalt. Current school footage
        # shows a concrete pedestrian apron and beds here; this local override
        # deliberately takes the newer photographic evidence over that tag.
        corridor = self.local_mask((-18, -43, -3.2, 1))
        for x, z, _, _ in self.each_column(corridor):
            y = self.c.ground_at(x, z)
            for yy in range(y - 2, y + 3):
                self.c.set(
                    x,
                    yy,
                    z,
                    "grass_block" if yy == y else "dirt" if yy < y else "air",
                    "terrain" if yy <= y else "air",
                )
        level = 67.7 + 0.025 * (self.v + 21.5)
        self.pave(self.local_mask((-12, -43, -8, 1)), level)
        self.features["photo_verified_pedestrian_approach"] = 1

    def west_planting(self):
        # Broad beds and shrub masses are visible in the 18 s school aerial.
        for v in np.arange(-39, -2, 3.4):
            mask = ((self.u + 13.5) / 0.8) ** 2 + ((self.v - v) / 1.0) ** 2 <= 1
            for x, z, iz, ix in self.each_column(mask):
                ground = self.c.ground_at(x, z)
                self.c.set(x, ground, z, "coarse_dirt", "terrain")
                radius = ((self.u[iz, ix] + 13.5) / 0.8) ** 2 + (
                    (self.v[iz, ix] - v) / 1.0
                ) ** 2
                height = 2 if radius < 0.55 else 1
                for y in range(ground + 1, ground + 1 + height):
                    self.c.set(
                        x,
                        y,
                        z,
                        "oak_leaves",
                        "vegetation",
                        {"persistent": "true", "distance": "1", "waterlogged": "false"},
                    )
        self.features["interpreted_west_shrub_groups"] = 11

    def pave(self, mask, level):
        """Supported half-block paving at an interpreted engineered surface."""
        levels = np.broadcast_to(level, self.u.shape)
        for x, z, iz, ix in self.each_column(mask):
            surface = (
                round((float(levels[iz, ix]) + self.offset) * self.c.scale * 2) / 2
            )
            top = math.ceil(surface) - 1
            old = self.c.ground_at(x, z)
            for y in range(min(old, top) - 1, max(old, top) + 1):
                if y < top:
                    self.c.set(x, y, z, "stone", "terrain")
                elif y > top:
                    self.c.set(x, y, z, "air", "air")
            self.c.set(
                x,
                top,
                z,
                "smooth_stone" if surface.is_integer() else "smooth_stone_slab",
                "pavement",
                None
                if surface.is_integer()
                else {"type": "bottom", "waterlogged": "false"},
            )
            self.c.ground_heights[iz, ix] = top

    def west_windows(self):
        for v in self.g["arcade_centres_v_m"]:
            self.opening(
                v, "west", 75.5, 3.3, 3.65, "pointed", lights=3, at=1.35, transom=2.6
            )
            # Glazed entry wall stands behind the open passage, not at its front.
            self.opening(v, "west", 69.75, 2.9, 3.5, lights=2, at=1.35, transom=2.3)
        for level in (67.8, 71.8, 75.8):
            self.opening(-37.4, "west", level, 3.8, 2.25, lights=3, at=-0.4)
        self.opening(-4.1, "west", 69.75, 3.7, 4.4, "pointed", lights=3, at=-0.4)
        self.opening(-4.1, "west", 76.2, 4.0, 2.7, lights=4, at=-0.4)
        for v in (-9.1, -33.6):
            for level in (70.2, 75.6):
                self.opening(v, "west", level, 1.25, 1.95, lights=2, at=1.35)

    def end_windows(self):
        # The two end elevations are deliberately described independently.
        self.opening(
            8.0, "south", 70.0, 7.0, 4.35, "pointed", lights=5, at=0.0, transom=2.8
        )
        self.opening(8.0, "south", 76.3, 7.0, 2.65, lights=5, at=0.0)
        self.opening(8.0, "south", 82.0, 1.8, 1.5, lights=2, at=0.0)
        for u in (1.6, 15.8):
            self.opening(u, "south", 70.5, 1.8, 3.2, lights=2, at=0.0)
            self.opening(u, "south", 76.3, 1.8, 2.3, lights=2, at=0.0)
        self.opening(10.0, "north", 75.4, 6.3, 3.1, lights=5, at=-42.15)
        for u in (3.0, 16.4):
            self.opening(u, "north", 75.6, 2.0, 2.6, lights=2, at=-42.15)
        self.opening(9.0, "north", 82.0, 2.0, 1.25, lights=2, at=-42.15)

    def arcade(self):
        u0, v0, u1, v1 = self.g["arcade_bounds_uv_m"]
        floor = self.g["landing_navd88_m"]
        roof = self.g["canopy_navd88_m"]
        bounds = (u0, v0, u1, v1)
        self.pave(self.local_mask(bounds), floor)
        self.box(bounds, floor, roof, "air", "air")
        self.box(bounds, roof - 0.45, roof, "smooth_stone", "roof")
        self.box((u0, v0, u0 + 0.5, v1), floor, roof + 0.45, "mud_bricks", "facade")
        self.box(
            (u0, v0, u1, v0 + 0.4), roof, roof + 0.45, "smooth_red_sandstone", "trim"
        )
        self.box(
            (u0, v1 - 0.4, u1, v1), roof, roof + 0.45, "smooth_red_sandstone", "trim"
        )
        front = self.local_mask((u0, v0, u0 + 0.5, v1))
        for x, z, iz, ix in self.each_column(front):
            d = min(
                (
                    float(self.v[iz, ix]) - center
                    for center in self.g["arcade_centres_v_m"]
                ),
                key=abs,
            )
            for y in range(self.height_y(floor), self.height_y(roof + 0.45)):
                h = (y + 0.5) / self.c.scale - self.offset - floor
                inner = self.in_opening(d, h, 3.65, 4.25, "pointed")
                outer = self.in_opening(d, h + 0.3, 4.2, 4.85, "pointed")
                if inner:
                    self.c.set(x, y, z, "air", "air")
                elif outer or h > 4.05:
                    if h > 3.0 and abs(d) > 0.7 and outer:
                        facing = "north" if d < 0 else "south"
                        self.c.set(
                            x,
                            y,
                            z,
                            "smooth_red_sandstone_stairs",
                            "trim",
                            {
                                "facing": facing,
                                "half": "top",
                                "shape": "straight",
                                "waterlogged": "false",
                            },
                        )
                    else:
                        self.c.set(x, y, z, "smooth_red_sandstone", "trim")
        # Squared caps and piers remain inside the observed portico envelope.
        for v in np.linspace(v0, v1, 6):
            self.box(
                (u0, v - 0.3, u0 + 0.65, v + 0.3),
                floor,
                floor + 0.7,
                "smooth_red_sandstone",
                "trim",
            )
            self.box(
                (u0, v - 0.35, u0 + 0.65, v + 0.35),
                floor + 3.7,
                floor + 4.1,
                "smooth_red_sandstone",
                "trim",
            )
        stairs = self.local_mask((-8.0, v0, u0, v1))
        rise = np.floor(np.clip((self.u + 8.0) / 5.0, 0, 1) * 8) / 8
        self.pave(stairs, floor - 2.0 + 2.0 * rise)
        # The broad approach is constrained to the photographed west apron.
        approach = self.local_mask((-10.0, v0 - 1.0, -8.0, v1 + 1.0))
        self.pave(approach, floor - 2.0)
        for v in np.linspace(v0 + 0.3, v1 - 0.3, 6):
            mask = self.local_mask((-8.0, v - 0.16, u0, v + 0.16))
            for x, z, _, _ in self.each_column(mask):
                y = self.c.ground_at(x, z)
                for yy in (y + 1, y + 2):
                    self.c.set(x, yy, z, "iron_bars", "railing", PANE_PROPS)
        self.features["open_pointed_arcade_bays"] = 5
        self.features["separate_flat_arcade_roof"] = 1
        self.features["broad_staircase_with_six_rails"] = 1

    def east_addition(self):
        mask = self.r.footprint_mask & (self.r.heights < 77) & (self.u > 18)
        # Photo shows dressed panels on the low wing, above a masonry plinth.
        # Recolour existing masonry only: do not extend a panel above its
        # measured low roof or fill the hollow addition with new wall columns.
        for y in range(self.height_y(69.6), self.height_y(76.0)):
            selected = mask & (self.c.roles[y + 64] == ROLES.index("facade"))
            self.c.data[y + 64, selected] = self.c.state("smooth_red_sandstone")
        for v in (-13.5, -20, -27.5, -32.0):
            self.opening(v, "east", 70.0, 3.8, 3.2, lights=2, at=32.5, transom=1.5)
        for u in (21.5, 27.0):
            self.opening(u, "south", 70.0, 3.5, 3.0, lights=2, at=-8.5, transom=1.45)
        self.features["east_addition_dressed_panels"] = 1

    def parapets_and_gables(self):
        # The main west eave is a low slotted parapet; the two end towers retain
        # their measured pitched/gabled roofs behind the coping.
        for v in np.arange(-32.7, -8.7, 0.25):
            high = 80.35 if abs(((v + 32.7) % 3.0) - 1.5) > 0.35 else 79.95
            self.box(
                (1.30, v, 1.80, v + 0.3),
                79.5,
                high,
                "mud_bricks",
                "facade",
                mask=self.r.footprint_mask,
            )
        family = "minecraft:stone_brick"
        edge = self.r.footprint_mask & ~binary_erosion(self.r.footprint_mask)
        selected = edge & ((self.v < -34) | (self.v > -8.8)) & (self.u < 18.4)
        for x, z, iz, ix in self.each_column(selected):
            y = self.height_y(float(self.r.heights[iz, ix]))
            for yy in range(y - 2, y + 2):
                entry = self.c.palette[self.c.get(x, yy, z)]
                if entry["Name"].startswith(family):
                    part = (
                        "_stairs"
                        if entry["Name"].endswith("_stairs")
                        else "_slab"
                        if entry["Name"].endswith("_slab")
                        else ""
                    )
                    self.c.set(
                        x,
                        yy,
                        z,
                        "smooth_red_sandstone" + part,
                        "trim",
                        entry.get("Properties"),
                    )

    def build(self):
        self.west_site()
        self.west_windows()
        self.end_windows()
        self.east_addition()
        self.parapets_and_gables()
        self.arcade()
        self.west_planting()
        return dict(self.features)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "server-assets/hill-ryan-library-reference.json",
    )
    parser.add_argument(
        "--terrain",
        type=Path,
        default=ROOT
        / "runtime/campus-reconstruction/ryan-library-preparation/terrain.npz",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    p = json.loads(args.profile.read_text(encoding="utf-8"))
    s, offset = p["blocks_per_metre"], p["vertical_offset_m"]
    h, ids, meta = terrain_arrays(args.terrain, s, p.get("terrain_bounds_m"))
    c = Canvas(meta["x_min"] * s, meta["z_min"] * s, h.shape[1], h.shape[0], s)
    build_ground(c, h, ids, meta["materials"], offset)
    smooth_exposed_measured_pavement(c, h, c.ground_heights, vertical_offset=offset)
    b = load_measured_building(parent_id=p["parent_id"])
    bounds = (
        c.x_min / s,
        c.z_min / s,
        (c.x_min + c.data.shape[2]) / s,
        (c.z_min + c.data.shape[1]) / s,
    )
    r = rasterize_roof(b, bounds, resolution=1 / s)
    shell = build_measured_shell(
        c,
        b,
        r,
        vertical_offset=offset,
        facade=p["materials"]["facade"],
        foundation=p["materials"]["foundation"],
        roof_family=p["materials"]["roof_family"],
        roof_backing_metres=0.4,
    )
    facade = RyanExterior(c, p, r, offset)
    for level in (69.7, 75.05):
        mask = binary_erosion(shell.active_mask & (r.heights > 78), iterations=2)
        y = round((level + offset) * s) - 1
        mask &= c.ground_heights < y
        mask &= c.roles[y + 64] == ROLES.index("air")
        c.data[y + 64, mask] = c.state("birch_planks")
        c.roles[y + 64, mask] = ROLES.index("floor")
    features = facade.build()
    connect_window_panes(c)
    connect_iron_rails(c)

    def point(uvh):
        x, z = facade.world(*uvh[:2])
        return [x * s, (uvh[2] + offset) * s, z * s]

    cameras = [
        {
            "name": v["name"],
            "eye": point(v["eye_uv_navd88_m"]),
            "target": point(v["target_uv_navd88_m"]),
            "fov": v["fov"],
        }
        for v in p["camera_views"]
    ]
    finish_study(
        c,
        p,
        args.output,
        cameras,
        {
            "features": features,
            "source_roof": shell.to_manifest(),
            "roof_coverage": r.coverage_report,
            "terrain": {"path": str(args.terrain), "sha256": digest(args.terrain)},
            "uncertainties": p["uncertainties"],
        },
        resource_pack=ROOT / p["materials"]["resource_pack"]
        if p["materials"].get("resource_pack")
        else None,
    )


if __name__ == "__main__":
    main()
