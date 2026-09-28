"""Hunt Upper School at the shared scale, with explicit source-roof corrections."""

import argparse
import json
import math
from dataclasses import replace
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
from campus_window_frames import bridge_frame_edges
from scipy.ndimage import binary_erosion, distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]


def repair_north_roof(raw, building, profile):
    zz, xx = np.indices(raw.heights.shape)
    x = raw.bounds[0] + (xx + 0.5) * raw.resolution
    z = raw.bounds[1] + (zz + 0.5) * raw.resolution
    g = profile["geometry"]
    angle = math.radians(g["axis_degrees"])
    v = -(x - g["origin_xz_m"][0]) * math.sin(angle) + (
        z - g["origin_xz_m"][1]
    ) * math.cos(angle)
    spec = g["north_roof_repair"]
    bad = (
        raw.footprint_mask
        & (v < spec["maximum_v_m"])
        & (raw.heights < spec["reject_below_navd88_m"])
    )
    valid = raw.footprint_mask & (raw.heights >= spec["reject_below_navd88_m"])
    if not valid.any():
        raise ValueError("No credible source roof for Hunt correction")
    _, near = distance_transform_edt(~valid, return_indices=True)
    ids = raw.face_indices[near[0], near[1]]
    h, gx, gz, faces = (
        a.copy()
        for a in (raw.heights, raw.gradient_x, raw.gradient_z, raw.face_indices)
    )
    before = h[bad].copy()
    for index in np.unique(ids[bad]):
        f = building.roof_faces[int(index)]
        selected = bad & (ids == index)
        h[selected] = np.clip(
            f.height_at(x[selected], z[selected]), 78, building.source_max
        )
        gx[selected], gz[selected], faces[selected] = f.a, f.b, index
    # The source's low north end strips also erase the photographed attic
    # gables. Continue the two measured long wing slopes to the north gables.
    gable_count = 0
    u = (x - g["origin_xz_m"][0]) * math.cos(angle) + (
        z - g["origin_xz_m"][1]
    ) * math.sin(angle)
    for band in g.get("north_gable_roof_planes", []):
        selected = (
            raw.footprint_mask & (v < 5) & (u >= band["u_min"]) & (u < band["u_max"])
        )
        f = building.roof_faces[band["face_index"]]
        h[selected] = np.minimum(
            f.height_at(x[selected], z[selected]), building.source_max
        )
        gx[selected], gz[selected], faces[selected] = f.a, f.b, band["face_index"]
        gable_count += int(selected.sum())
    evidence = {
        "method": spec["method"],
        "corrected_columns": int(bad.sum()),
        "area_m2": float(bad.sum() * raw.resolution**2),
        "photo_interpreted_north_gable_columns": gable_count,
        "source_height_range_m": [float(before.min()), float(before.max())]
        if before.size
        else None,
        "corrected_height_range_m": [float(h[bad].min()), float(h[bad].max())]
        if bad.any()
        else None,
    }
    return replace(
        raw, heights=h, gradient_x=gx, gradient_z=gz, face_indices=faces
    ), evidence


class HuntExterior(AtheyExterior):
    def framed_panes(self, u, v, sill, width, height, *, inside=-1, lights=1):
        """Glazing at the authored frame, with short pane returns at its edges."""
        front, back = sorted((v, v + inside * 1.1))
        self.box(
            (u - width / 2 - 0.25, front, u + width / 2 + 0.25, back),
            sill - 0.25,
            sill + height + 0.25,
            "smooth_red_sandstone",
            "trim",
        )
        # Clear the complete reveal first, then insert glass at the front frame.
        self.box(
            (u - width / 2, front - 0.3, u + width / 2, back + 0.3),
            sill,
            sill + height,
            "air",
            "air",
        )
        plane = v + inside * 0.15
        half = (abs(self.n[0]) + abs(self.n[1])) / (2 * self.c.scale) + 1e-6
        bounds = (u - width / 2, plane - half, u + width / 2, plane + half)
        self.box(
            bounds, sill, sill + height, "gray_stained_glass_pane", "window", PANE_PROPS
        )
        for post in np.linspace(u - width / 2, u + width / 2, lights + 1)[1:-1]:
            self.box(
                (post - 0.27, plane - half, post + 0.27, plane + half),
                sill,
                sill + height,
                "smooth_red_sandstone",
                "trim",
            )
        self.box(
            bounds,
            sill + height / 2 - 0.25,
            sill + height / 2 + 0.25,
            "smooth_red_sandstone",
            "trim",
        )
        allowed = set()
        mask = self.local_mask((u - width / 2, front, u + width / 2, back))
        for x, z, _, _ in self.each_column(mask):
            for y in range(self.height_y(sill), self.height_y(sill + height)):
                allowed.add((x, y, z))
        self.features["pane_frame_edge_connectors"] += bridge_frame_edges(
            self.c, allowed
        )

    def measured_facade(self, level, block):
        for y in range(self.height_y(60), self.height_y(level)):
            mask = self.c.roles[y + 64] == ROLES.index("facade")
            self.c.data[y + 64, mask] = self.c.state(block)

    def long_windows(self):
        for u in self.g["long_front_window_centres_u_m"]:
            for h in self.g["window_sills_navd88_m"]:
                self.opening(u, "south", h, 1.55, 2.25, lights=1, at=15.5, transom=1.1)
        # Five levels are exposed on the north side, where the terrain drops.
        for u in np.arange(16, 61, 4.6):
            for h in (63.5, 67.2, 70.9, 74.6):
                self.opening(
                    float(u), "north", h, 1.7, 2.0, lights=1, at=2.1, transom=1.05
                )
        for end in (6.5, 68):
            for u in (end - 3.8, end, end + 3.8):
                for h in (67.5, 71.0, 74.5, 78.0):
                    self.opening(
                        u, "south", h, 1.9, 2.2, lights=1, at=25.8, transom=1.1
                    )
                    self.opening(
                        u, "north", h - 3.5, 1.8, 2.1, lights=1, at=0.2, transom=1.05
                    )
            self.opening(end, "south", 82, 3.8, 2.3, lights=3, at=25.8)
            self.opening(end, "north", 82, 3.8, 2.3, lights=3, at=0.2)
        for side, at in (("west", 0.9), ("east", 73.1)):
            for v in (5.5, 11.0, 17.0, 22.5):
                for h in (67.2, 70.9, 74.6, 78.3):
                    self.opening(v, side, h, 1.7, 2.1, lights=1, at=at, transom=1.05)
        for side, at in (("east", 13.8), ("west", 61.5)):
            for v in (19.8, 23.5):
                for h in (67.5, 71.0, 74.5, 78.0):
                    self.opening(v, side, h, 1.65, 2.1, lights=1, at=at, transom=1.05)

    def arcade(self):
        u0, v0, u1, v1 = self.g["arcade_bounds_uv_m"]
        floor = self.g["quad_floor_navd88_m"]
        self.box((u0, v0, u1, v1 + 0.7), floor, 70.1, "air", "air")
        self.box((u0, v0, u1, v1), floor - 0.5, floor, "smooth_stone", "floor")
        self.box((u0, v0, u1, v1), 69.9, 70.25, "smooth_stone", "floor")
        self.box((u0, v1 - 0.5, u1, v1), floor, 70.25, "mud_bricks", "facade")
        mask = self.local_mask((u0, v1 - 0.5, u1, v1))
        for x, z, iz, ix in self.each_column(mask):
            d = min(
                (
                    float(self.u[iz, ix]) - center
                    for center in self.g["arcade_centres_u_m"]
                ),
                key=abs,
            )
            for y in range(self.height_y(floor), self.height_y(70.25)):
                h = (y + 0.5) / self.c.scale - self.offset - floor
                if self.in_opening(d, h, 4.05, 3.45, "round"):
                    self.c.set(x, y, z, "air", "air")
                elif self.in_opening(d, h + 0.3, 4.65, 4.05, "round"):
                    if h > 2.1 and abs(d) > 0.8:
                        self.c.set(
                            x,
                            y,
                            z,
                            "smooth_red_sandstone_stairs",
                            "trim",
                            {
                                "facing": "east" if d > 0 else "west",
                                "half": "top",
                                "shape": "straight",
                                "waterlogged": "false",
                            },
                        )
                    else:
                        self.c.set(x, y, z, "smooth_red_sandstone", "trim")
        for u in self.g["arcade_centres_u_m"]:
            self.opening(
                u, "south", floor + 0.15, 2.2, 2.9, lights=2, at=v0 - 0.2, transom=2.1
            )
        self.features["open_round_arcade_bays"] = len(self.g["arcade_centres_u_m"])

    def dormers_and_copper(self):
        # Gray flat strip between the main red slopes is visible in the drone.
        family = self.p["materials"]["roof_family"]
        roof_states = {
            "minecraft:" + family: "deepslate_tiles",
            "minecraft:" + family + "_slab": "deepslate_tile_slab",
            "minecraft:" + family + "_stairs": "deepslate_tile_stairs",
        }
        mask = self.local_mask((12, 9.0, 63, 12.8)) & self.r.footprint_mask
        for x, z, iz, ix in self.each_column(mask):
            y = self.height_y(float(self.r.heights[iz, ix]))
            for yy in range(y - 2, y + 2):
                state = self.c.palette[self.c.get(x, yy, z)]
                if state["Name"] in roof_states and self.c.roles[
                    yy + 64, iz, ix
                ] == ROLES.index("roof"):
                    self.c.set(
                        x,
                        yy,
                        z,
                        roof_states[state["Name"]],
                        "roof",
                        state.get("Properties"),
                    )
        specifications = (
            ("south_single_dormer_centres_u_m", 15.9, -1, 2.1, 2.2, 81.4, 1),
            ("north_box_dormer_centres_u_m", 3.1, 1, 3.6, 3.2, 82.3, 2),
        )
        for key, v, inside, width, depth, top, lights in specifications:
            for u in self.g[key]:
                a, b = sorted((v, v + inside * depth))
                self.box(
                    (u - width / 2, a, u + width / 2, b), 78, top, "bricks", "facade"
                )
                self.box(
                    (u - width / 2 + 0.5, a + 0.5, u + width / 2 - 0.5, b - 0.5),
                    78.3,
                    top - 0.5,
                    "air",
                    "air",
                )
                self.framed_panes(
                    u, v, 78.8, width - 0.65, top - 79.35, inside=inside, lights=lights
                )
                self.box(
                    (u - width / 2 - 0.15, a - 0.15, u + width / 2 + 0.15, b + 0.15),
                    top - 0.15,
                    top + 0.2,
                    "waxed_oxidized_cut_copper_slab"
                    if inside < 0
                    else "smooth_stone_slab",
                    "trim",
                    {"type": "top", "waterlogged": "false"},
                )
                self.features[key.removesuffix("_centres_u_m")] += 1
        for v in (2.7, 15.7):
            self.box(
                (12, v, 63, v + 0.35),
                78.0,
                78.35,
                "waxed_oxidized_cut_copper_slab",
                "trim",
                {"type": "top", "waterlogged": "false"},
            )

    def central_bay(self):
        u = self.g["central_bay_u_m"]
        # The projecting central masonry bay is an observed part of the wall.
        self.box((u - 2.2, 15.0, u + 2.2, 16.4), 70.25, 81.2, "bricks", "facade")
        for h in (70.7, 74.6, 78.8):
            self.framed_panes(u, 16.4, h, 3.4, 2.0, lights=2)
        self.box(
            (u - 2.5, 14.8, u + 2.5, 16.8),
            81.1,
            81.45,
            "waxed_oxidized_cut_copper_slab",
            "trim",
            {"type": "top", "waterlogged": "false"},
        )
        # Photo-interpreted oval copper crest with a real opening and finial.
        mask = self.local_mask((u - 2.7, 15.5, u + 2.7, 16.1))
        for x, z, iz, ix in self.each_column(mask):
            d = float(self.u[iz, ix]) - u
            for y in range(self.height_y(81.4), self.height_y(85.7)):
                h = (y + 0.5) / self.c.scale - self.offset
                oval = (d / 1.25) ** 2 + ((h - 83.5) / 2.0) ** 2 <= 1
                hollow = (d / 0.65) ** 2 + ((h - 83.5) / 1.4) ** 2 < 1
                shoulder = abs(d) <= 2.5 and h < 81.6 + 1.4 * (1 - abs(d) / 2.5) ** 2
                if (oval and not hollow) or shoulder:
                    self.c.set(x, y, z, "waxed_oxidized_cut_copper", "trim")
        self.box(
            (u - 0.28, 15.5, u + 0.28, 16.1),
            85.2,
            86.8,
            "waxed_oxidized_cut_copper",
            "trim",
        )
        self.features["central_masonry_bay_and_copper_crest"] = 1

    def site_and_retaining_wall(self):
        # Photograph-supported two-level north wall. Heights follow the DEM's
        # lower road and source base; exact terrace edges remain interpreted.
        for bounds, base, slope, block in (
            ((0, -3.8, 75, 0), 62.15, 0.006, "smooth_stone"),
            ((0, -5.3, 75, -3.8), 60.4, 0.006, "grass_block"),
            ((14, 17.7, 61.5, 22), 66.1, 0, "bricks"),
        ):
            mask = self.local_mask(bounds) & ~self.r.footprint_mask
            for x, z, iz, ix in self.each_column(mask):
                top = self.height_y(base + slope * float(self.u[iz, ix])) - 1
                old = self.c.ground_at(x, z)
                for y in range(min(old, top) - 1, max(old, top) + 1):
                    self.c.set(
                        x,
                        y,
                        z,
                        "stone" if y < top else "air",
                        "terrain" if y < top else "air",
                    )
                self.c.set(
                    x,
                    top,
                    z,
                    block,
                    "terrain" if block == "grass_block" else "pavement",
                )
                self.c.ground_heights[iz, ix] = top
        for v, top in ((-5.8, 60.4), (-3.8, 62.15)):
            self.box((0, v, 75, v + 0.6), 58.1, top, "mud_bricks", "facade")
            self.box(
                (0, v - 0.1, 75, v + 0.7),
                top,
                top + 0.3,
                "smooth_stone_slab",
                "trim",
                {"type": "bottom", "waterlogged": "false"},
            )
        self.box((0, -3.7, 75, -3.1), 62.4, 63.4, "iron_bars", "railing", PANE_PROPS)
        # One clear stepped route on each end of the north terrace.
        for u0 in (1.5, 70):
            for i in range(16):
                v0 = -10.5 + i * 0.5
                h = 58.4 + i * 0.25
                self.box((u0, v0, u0 + 2.2, v0 + 0.5), 57.9, h, "mud_bricks", "facade")
                self.box(
                    (u0, v0, u0 + 2.2, v0 + 0.5),
                    h,
                    h + 0.3,
                    "smooth_stone_slab",
                    "trim",
                    {"type": "bottom", "waterlogged": "false"},
                )
            self.box((u0, -3.9, u0 + 2.2, -3), 62.4, 63.5, "air", "air")
        self.features["interpreted_north_terrace_and_steps"] = 1

    def build(self):
        self.measured_facade(70.1, "mud_bricks")
        # North lower masonry is only one storey, not the Quad's whole plinth.
        north = self.v < 8
        for y in range(self.height_y(66.3), self.height_y(70.1)):
            mask = north & (self.c.roles[y + 64] == ROLES.index("facade"))
            self.c.data[y + 64, mask] = self.c.state("bricks")
        self.site_and_retaining_wall()
        self.long_windows()
        self.arcade()
        self.dormers_and_copper()
        self.central_bay()
        return dict(self.features)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "server-assets/hill-hunt-hall-reference.json",
    )
    parser.add_argument(
        "--terrain",
        type=Path,
        default=ROOT
        / "runtime/campus-reconstruction/hunt-hall-preparation/terrain.npz",
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
    raw = rasterize_roof(b, bounds, resolution=1 / s)
    r, correction = repair_north_roof(raw, b, p)
    shell = build_measured_shell(
        c,
        b,
        r,
        vertical_offset=offset,
        facade="bricks",
        foundation="mud_bricks",
        roof_family=p["materials"]["roof_family"],
        roof_backing_metres=0.4,
    )
    for level in p["geometry"]["floor_plates_navd88_m"]:
        y = round((level + offset) * s) - 1
        mask = (
            binary_erosion(shell.active_mask & (r.heights > level + 1), iterations=2)
            & (c.ground_heights < y)
            & (c.roles[y + 64] == ROLES.index("air"))
        )
        c.data[y + 64, mask] = c.state("birch_planks")
        c.roles[y + 64, mask] = ROLES.index("floor")
    facade = HuntExterior(c, p, r, offset)
    features = facade.build()
    connect_window_panes(c)
    connect_iron_rails(c)

    def point(v):
        x, z = facade.world(*v[:2])
        return [x * s, (v[2] + offset) * s, z * s]

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
            "roof_corrections": correction,
            "terrain": {"path": str(args.terrain), "sha256": digest(args.terrain)},
            "uncertainties": p["uncertainties"],
        },
        resource_pack=ROOT / p["materials"]["resource_pack"]
        if p["materials"].get("resource_pack")
        else None,
    )


if __name__ == "__main__":
    main()
