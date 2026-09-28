"""Two post-survey structures, separated from the immutable county geometry.

Kipp uses published design dimensions and approximate plan registration.
Madden's compact elevated press box uses a documented photo interpretation.
Neither output claims a surveyed footprint or a finished facade replica.
"""

import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from build_hill_chapel_sample import Canvas, build_ground, connect_window_panes
from campus_academic_building import AcademicExterior
from campus_measured_shell import _roof_representations
from campus_study_io import digest, finish_study, write_json
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
PROPOSALS = (
    ROOT / "runtime/research/quad-landscape-20260905/current-pavilion-proposals.json"
)


class SiteFrame:
    def __init__(self, canvas, origin, tangent, normal, offset=-25):
        self.c, self.origin, self.t, self.n = canvas, np.array(origin), tangent, normal
        self.offset = offset
        zz, xx = np.indices(canvas.data.shape[1:])
        self.x = (xx + canvas.x_min + 0.5) / canvas.scale
        self.z = (zz + canvas.z_min + 0.5) / canvas.scale
        dx, dz = self.x - origin[0], self.z - origin[1]
        self.u = dx * tangent[0] + dz * tangent[1]
        self.v = dx * normal[0] + dz * normal[1]

    def y(self, height):
        return round((height + self.offset) * self.c.scale)

    def mask(self, bounds):
        a, b, c, d = bounds
        return (self.u >= a) & (self.u < c) & (self.v >= b) & (self.v < d)

    def fill(self, bounds, bottom, top, block, role, properties=None):
        mask = self.mask(bounds)
        for iz, ix in np.argwhere(mask):
            upper = (
                max(self.y(bottom) + 1, self.y(top)) if block != "air" else self.y(top)
            )
            for y in range(self.y(bottom), upper):
                self.c.set(
                    int(ix) + self.c.x_min,
                    y,
                    int(iz) + self.c.z_min,
                    block,
                    role,
                    properties,
                )

    def rail(self, bounds, bottom, top):
        self.fill(
            bounds,
            bottom,
            top,
            "iron_bars",
            "railing",
            {
                "north": "false",
                "east": "false",
                "south": "false",
                "west": "false",
                "waterlogged": "false",
            },
        )

    def glazing(self, length, depth, top, sill, width, height, centres):
        inside = self.mask([0, 0, length, depth])
        r = SimpleNamespace(
            heights=np.where(inside, top, np.nan), footprint_mask=inside
        )
        origin, tangent = self.origin, np.asarray(self.t)
        if self.t[0] * self.n[1] - self.t[1] * self.n[0] < 0:
            origin = origin + length * tangent
            tangent = -tangent
            centres = [length - u for u in centres]
        p = {
            "geometry": {
                "origin_xz_m": origin.tolist(),
                "axis_degrees": math.degrees(math.atan2(tangent[1], tangent[0])),
                "main_roof_threshold_navd88_m": 0,
            },
            "materials": {"facade": "white_concrete"},
            "window_reveal": {"glass_recess_m": 0, "trim_width_m": 0.35},
        }
        ex = AcademicExterior(self.c, p, r, self.offset)
        for u in centres:
            ex.opening(u, "south", sill, width, height, lights=1, at=depth)
        connect_window_panes(self.c)
        return dict(ex.features)


def connect_rails(c):
    ids = [i for i, p in enumerate(c.palette) if p["Name"] == "minecraft:iron_bars"]
    for iy, iz, ix in np.argwhere(np.isin(c.data, ids)):
        x, y, z = int(ix) + c.x_min, int(iy) - 64, int(iz) + c.z_min
        props = {"waterlogged": "false"}
        for side, (dx, dz) in {
            "north": (0, -1),
            "south": (0, 1),
            "east": (1, 0),
            "west": (-1, 0),
        }.items():
            props[side] = "true" if c.get(x + dx, y, z + dz) else "false"
        c.set(x, y, z, "iron_bars", "railing", props)


def build_kipp(f, source):
    length, depth = source["main_rectangle_dimensions_m"]
    levels = source["proposed_blocking_levels_m"]
    lower, upper, eave, ridge = (
        levels[k] for k in ("lower_floor", "upper_floor", "eave", "ridge")
    )
    # Excavate only the building's design rectangle; the veranda remains open.
    f.fill([0, 0, length, depth], lower, ridge + 1, "air", "air")
    f.fill([0, 0, length, depth], lower - 0.5, lower, "smooth_stone", "floor")
    for rect in (
        [0, 0, length, 0.65],
        [0, 0, 0.65, depth],
        [length - 0.65, 0, length, depth],
        [0, 6.5, length, 7.2],
    ):
        f.fill(rect, lower, upper, "terracotta", "facade")
    f.fill([0, 0, length, depth], upper - 0.5, upper, "smooth_stone", "floor")
    for rect in (
        [0, 0, length, 0.65],
        [0, 0, 0.65, 7.8],
        [length - 0.65, 0, length, 7.8],
        [0, 7.1, length, 7.8],
    ):
        f.fill(rect, upper, eave, "white_concrete", "facade")
    # Count and offsets of veranda piers are photo proportion estimates.
    for u in np.linspace(0.5, length - 0.5, 9):
        rect = [u - 0.4, depth - 0.7, u + 0.4, depth]
        f.fill(rect, lower, upper + 0.9, "bricks", "facade")
        f.fill(rect, upper + 0.9, eave, "white_concrete", "trim")
    f.rail([0.8, depth - 0.65, length - 0.8, depth - 0.15], upper, upper + 1.0)
    f.fill([0, 0, length, depth], eave - 0.25, eave, "birch_planks", "floor")
    # The north stair projection is explicitly present in the design plan.
    for rect in (
        [12.2, -2.33, 18.51, -1.73],
        [12.2, -2.33, 12.8, 0],
        [17.91, -2.33, 18.51, 0],
    ):
        f.fill(rect, lower, eave, "terracotta", "facade")
    f.fill(
        [12.2, -2.33, 18.51, 0],
        eave,
        eave + 0.25,
        "smooth_stone_slab",
        "roof",
        {"type": "bottom", "waterlogged": "false"},
    )
    f.glazing(
        length, 7.8, eave, upper + 0.35, 3.2, 2.1, [6.2, length / 2, length - 6.2]
    )

    active = f.mask([-0.65, -0.65, length + 0.65, depth + 0.65])
    rise = ridge - eave
    fractions = np.minimum.reduce(
        [
            (f.v + 0.65) / (depth / 2 + 0.65),
            (depth + 0.65 - f.v) / (depth / 2 + 0.65),
            (f.u + 0.65) / (depth / 2 + 0.65),
            (length + 0.65 - f.u) / (depth / 2 + 0.65),
        ]
    )
    heights = eave + rise * np.clip(fractions, 0, 1)
    for centre, width, peak in (
        (6.2, 6.3, ridge - 0.5),
        (length / 2, 9.0, ridge + 0.4),
        (length - 6.2, 6.3, ridge - 0.5),
    ):
        branch = active & (abs(f.u - centre) < width / 2) & (f.v > depth / 2)
        branch_height = eave + (peak - eave) * (1 - abs(f.u - centre) / (width / 2))
        heights[branch] = np.maximum(heights[branch], branch_height[branch])
        front = branch & (f.v >= depth - 0.6) & (f.v < depth)
        for iz, ix in np.argwhere(front):
            for y in range(f.y(eave), f.y(float(branch_height[iz, ix]))):
                f.c.set(
                    int(ix) + f.c.x_min,
                    y,
                    int(iz) + f.c.z_min,
                    "white_concrete",
                    "facade",
                )
    quantized = np.rint((heights + f.offset) * f.c.scale * 2) / 2
    gz, gx = np.gradient(heights, 1 / f.c.scale)
    reps, directions = _roof_representations(
        active,
        quantized,
        SimpleNamespace(heights=heights, gradient_x=gx, gradient_z=gz),
    )
    for iz, ix in np.argwhere(active):
        top = float(quantized[iz, ix])
        x, z = int(ix) + f.c.x_min, int(iz) + f.c.z_min
        y = math.ceil(top) - 1
        for by in range(y - 1, y):
            f.c.set(x, by, z, "stone_bricks", "roof")
        block, props = "stone_bricks", None
        if reps[iz, ix] == "bottom_slab":
            block, props = (
                "stone_brick_slab",
                {"type": "bottom", "waterlogged": "false"},
            )
        elif reps[iz, ix] == "bottom_stair":
            block, props = (
                "stone_brick_stairs",
                {
                    "half": "bottom",
                    "shape": "straight",
                    "waterlogged": "false",
                    "facing": str(directions[iz, ix]),
                },
            )
        f.c.set(x, y, z, block, "roof", props)
        if (
            min(
                float(f.u[iz, ix]) + 0.65,
                length + 0.65 - float(f.u[iz, ix]),
                float(f.v[iz, ix]) + 0.65,
                depth + 0.65 - float(f.v[iz, ix]),
            )
            < 0.5
        ):
            f.c.set(x, y - 1, z, "white_concrete", "trim")
    return {
        "court_facing_gables": 3,
        "veranda_piers_estimated": 9,
        "design_dimensions_m": [length, depth],
    }


def build_madden(f, source):
    length, depth = source["enclosed_box_dimensions_m"]
    levels = source["proposed_levels_navd88_m"]
    ground, floor, roof, guard = (
        levels[k]
        for k in (
            "support_ground",
            "box_floor",
            "box_eave_or_flat_roof",
            "filming_guard_top",
        )
    )
    f.fill([0, 0, length, depth], floor, guard + 0.5, "air", "air")
    # Four thin columns and cross beams keep the stand visibly open underneath.
    for u in (0.5, length - 0.5):
        for v in (0.4, depth - 0.4):
            f.fill(
                [u - 0.25, v - 0.25, u + 0.25, v + 0.25],
                ground - 0.5,
                floor,
                "light_gray_concrete",
                "trim",
            )
    for v in (0.25, depth - 0.25):
        f.fill(
            [0, v - 0.25, length, v + 0.25],
            floor - 0.75,
            floor - 0.25,
            "light_gray_concrete",
            "trim",
        )
    f.fill(
        [0, 0, length, depth],
        floor - 0.25,
        floor,
        "smooth_stone_slab",
        "floor",
        {"type": "bottom", "waterlogged": "false"},
    )
    walls = (
        [0, 0, length, 0.65],
        [0, 0, 0.65, depth],
        [length - 0.65, 0, length, depth],
        [0, depth - 0.65, length, depth],
    )
    for wall in walls:
        f.fill(wall, floor, roof, "white_concrete", "facade")
        f.fill(wall, floor, floor + 0.5, "blue_concrete", "facade")
    windows = f.glazing(length, depth, roof, floor + 0.8, 3.0, 1.35, [2.2, 6.0, 9.8])
    f.fill(
        [0, 0, length, depth],
        roof - 0.25,
        roof,
        "smooth_stone_slab",
        "roof",
        {"type": "bottom", "waterlogged": "false"},
    )
    for wall in walls:
        f.rail(wall, roof, guard)
    # A narrow external stair is separate from the enclosed box and bleachers.
    steps = max(1, round((floor - ground) * 4))
    for i in range(steps):
        height = ground + (floor - ground) * (i + 1) / steps
        v0, v1 = -6 + i * 6 / steps, -6 + (i + 1) * 6 / steps
        f.fill([0, v0, 1.5, v1], height - 0.5, height, "smooth_stone", "trim")
        for u in (-0.4, 1.5):
            f.rail([u, v0, u + 0.5, v1], height, height + 1)
    return {
        "elevated_box_dimensions_m": [length, depth],
        "support_columns": 4,
        "bleachers_enclosed": False,
        "window_features": windows,
    }


def make_canvas(terrain, bounds):
    from build_hill_chapel_sample import terrain_arrays

    x0, z0, x1, z1 = bounds
    h, materials, meta = terrain_arrays(terrain, 2, bounds)
    c = Canvas(x0 * 2, z0 * 2, (x1 - x0) * 2, (z1 - z0) * 2, 2)
    build_ground(c, h, materials, meta["materials"], -25)
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--terrain",
        type=Path,
        default=ROOT
        / "runtime/campus-reconstruction/campus-all-named-preparation/terrain.npz",
    )
    args = ap.parse_args()
    proposal = json.loads(PROPOSALS.read_text(encoding="utf-8"))
    components = []
    for source in proposal["structures"]:
        kipp = source["id"] == "kipp_46_pavilion"
        origin = (
            source["main_rect_origin_northwest_xz_m"]
            if kipp
            else source["polygon_xz"]["coordinates"][0][0]
        )
        tangent = (
            source["axis_long_u_east_southeast"]
            if kipp
            else source["axis_long_southwest"]
        )
        normal = (
            source["axis_depth_v_south_southwest"]
            if kipp
            else source["axis_depth_southeast"]
        )
        b = source["bounds_xz_m"]
        bounds = [math.floor((v - 10) / 8) * 8 for v in b[:2]] + [
            math.ceil((v + 10) / 8) * 8 for v in b[2:]
        ]
        c = make_canvas(args.terrain, bounds)
        f = SiteFrame(c, origin, tangent, normal)
        features = build_kipp(f, source) if kipp else build_madden(f, source)
        connect_rails(c)
        p = {
            "name": "Hill - " + source["name"],
            "revision": "2026-09-05-current-pavilion-1-2x",
            "parent_id": None,
            "interpreted_id": source["id"],
            "school_map_numbers": [source["school_map_number"]],
            "blocks_per_metre": 2,
            "vertical_offset_m": -25,
            "geometry": {
                "origin_xz_m": origin,
                "axis_degrees": math.degrees(math.atan2(tangent[1], tangent[0])),
            },
            "interpreted_source": source,
            "source_references": proposal["sources"],
            "detail_status": "Interpreted structure; position and architectural dimensions remain provisional. Facade openings are photo-proportion studies, not an as-built window census.",
            "uncertainties": [
                source.get("vertical_datum_caution", source["height_evidence"]),
                "Veranda piers, opening divisions and stair layout are approximate. No interiors or full sports stands are claimed.",
            ],
        }
        eye = (
            f.origin
            + (18 if kipp else 6) * np.array(tangent)
            + (48 if kipp else 26) * np.array(normal)
        )
        target = source["centre_xz_m"]
        target_h = (
            source["proposed_blocking_levels_m"]["upper_floor"] + 2
            if kipp
            else source["proposed_levels_navd88_m"]["box_floor"] + 1
        )
        cameras = [
            {
                "name": "pavilion-front" if kipp else "press-box-front",
                "eye": [eye[0] * 2, (target_h + 9 - 25) * 2, eye[1] * 2],
                "target": [target[0] * 2, (target_h - 25) * 2, target[1] * 2],
                "fov": 68,
            }
        ]
        output = args.output / source["id"]
        finish_study(
            c,
            p,
            output,
            cameras,
            {
                "features": features,
                "proposal_sha256": digest(PROPOSALS),
                "terrain_sha256": digest(args.terrain),
            },
        )
        components.append(
            {
                "name": source["name"],
                "study": output.resolve().relative_to(ROOT).as_posix(),
                "margin_m": 0.5,
                "detail_status": "interpreted_structure",
            }
        )
    write_json(args.output / "components.json", components)


if __name__ == "__main__":
    main()
