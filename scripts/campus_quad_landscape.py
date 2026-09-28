"""Build the 2026 drone's Quad paths and planting in the fixed campus frame.

Positions are photo interpretations recorded separately from surveyed roofs
and the DEM. Ground edits stop at actual generated architecture, including
the Chapel's newer addition, and tree crowns never overwrite structures.
"""

import hashlib
import math
from collections import Counter

import numpy as np
from build_hill_chapel_sample import ROLES
from scipy.ndimage import binary_dilation
from shapely import contains_xy
from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union

LEAVES = {"persistent": "true", "distance": "1", "waterlogged": "false"}


def set_surface(c, iz, ix, surface_y, full, slab=None, role="pavement"):
    """Place a supported physical surface, clearing only previous site blocks."""
    surface = (
        round(float(surface_y) * 2) / 2 if slab else float(round(float(surface_y)))
    )
    top = math.ceil(surface) - 1
    old = int(c.ground_heights[iz, ix])
    site_roles = {ROLES.index(r) for r in ("air", "terrain", "pavement", "vegetation")}
    for y in range(min(old, top) - 2, max(old, top) + 5):
        if not -64 <= y < 320:
            raise ValueError("Landscape exceeds world height")
        if int(c.roles[y + 64, iz, ix]) not in site_roles:
            raise ValueError("Landscape tried to alter architecture")
        if y < top:
            block, target_role, props = "dirt", "terrain", None
        elif y == top:
            block = full if surface.is_integer() else slab
            target_role = role
            props = (
                None
                if surface.is_integer()
                else {"type": "bottom", "waterlogged": "false"}
            )
        else:
            block, target_role, props = "air", "air", None
        c.set(ix + c.x_min, y, iz + c.z_min, block, target_role, props)
    c.ground_heights[iz, ix] = top


def build_quad_landscape(c, elevations, profile, offset):
    """Apply one deterministic tile of the shared landscape; return evidence."""
    zz, xx = np.indices(elevations.shape)
    x, z = (xx + c.x_min + 0.5) / c.scale, (zz + c.z_min + 0.5) / c.scale
    architecture = np.any(
        np.isin(
            c.roles,
            [
                ROLES.index(r)
                for r in (
                    "facade",
                    "roof",
                    "trim",
                    "window",
                    "door",
                    "floor",
                    "railing",
                    "lighting",
                    "fixture",
                    "furniture",
                )
            ],
        ),
        axis=0,
    )
    protected = binary_dilation(architecture, iterations=1)
    paths = [(p, shape(p["polygon_xz"])) for p in profile["paths"]]
    all_paths = unary_union([geom for _, geom in paths])
    path_mask = contains_xy(all_paths, x, z)
    lawn = shape(profile["lawn"]["outer_polygon_xz"])
    bed_geometries = [shape(p["polygon_xz"]) for p in profile["planting_beds"]]
    # Current footage supersedes the old road surface inside this bounded
    # landscape only. Keep the main field open and unmarked.
    reset = contains_xy(unary_union([lawn, *bed_geometries]), x, z) & ~protected
    counts = Counter()
    for iz, ix in np.argwhere(reset):
        set_surface(
            c,
            iz,
            ix,
            (elevations[iz, ix] + offset) * c.scale,
            "grass_block",
            role="terrain",
        )
    counts["lawn_and_bed_surface_columns"] = int(reset.sum())
    step_shapes = [
        shape(p["polygon_xz"])
        for p in profile["steps_and_terraces"]
        if p["id"] == "ryan_main_stairs"
    ]
    step_mask = contains_xy(unary_union(step_shapes), x, z)
    for p, geom in paths:
        mask = contains_xy(geom, x, z) & ~architecture & ~step_mask
        red = p["id"] == "quad_central_red_crosswalk"
        for iz, ix in np.argwhere(mask):
            surface = (elevations[iz, ix] + offset) * c.scale
            # The engineered Ryan approach connects to the existing flight.
            # Its observed plane is in the building's independent profile.
            if p["id"].startswith("ryan_"):
                angle = math.radians(23.95049970400529)
                v = -(x[iz, ix] - 115.249079686) * math.sin(angle) + (
                    z[iz, ix] - 42.994671715
                ) * math.cos(angle)
                design = (67.7 + 0.025 * (v + 21.5) + offset) * c.scale
                # Blend north/south connections into the measured lawn grade.
                blend = min(1, max(0, (-v - 1) / 6), max(0, (v + 44) / 6))
                surface = surface * (1 - blend) + design * blend
            set_surface(
                c,
                iz,
                ix,
                surface,
                "bricks" if red else "smooth_stone",
                "brick_slab" if red else "smooth_stone_slab",
            )
        counts[p["id"] + "_columns"] = int(mask.sum())

    for terrace in profile.get("engineered_terraces", []):
        geom = shape(terrace["polygon_xz"])
        mask = contains_xy(geom, x, z) & ~architecture
        start = np.array(terrace["approach_start_xz_m"])
        end = np.array(terrace["threshold_xz_m"])
        direction = end - start
        fraction = np.clip(
            ((x - start[0]) * direction[0] + (z - start[1]) * direction[1])
            / float(direction @ direction),
            0,
            1,
        )
        surface = (
            terrace["start_navd88_m"] * (1 - fraction)
            + terrace["threshold_navd88_m"] * fraction
            + offset
        ) * c.scale
        for iz, ix in np.argwhere(mask):
            set_surface(c, iz, ix, surface[iz, ix], "smooth_stone", "smooth_stone_slab")
        # The central brick strip continues to the actual door, with a pale
        # terrace on either side; its grade comes from the generated threshold.
        if terrace.get("central_brick_width_m"):
            red = (
                contains_xy(
                    LineString([start, end]).buffer(
                        terrace["central_brick_width_m"] / 2
                    ),
                    x,
                    z,
                )
                & mask
            )
            for iz, ix in np.argwhere(red):
                set_surface(c, iz, ix, surface[iz, ix], "bricks", "brick_slab")
        counts[terrace["id"] + "_columns"] = int(mask.sum())

    # Small varied shrubs, not a solid green extrusion over an entire bed.
    for bed, geom in zip(profile["planting_beds"], bed_geometries):
        mask = contains_xy(geom, x, z) & ~path_mask & ~protected & ~step_mask
        seed = int(hashlib.sha256(bed["id"].encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        bx0, bz0, bx1, bz1 = geom.bounds
        clumps = []
        for cx in np.arange(bx0 + 0.8, bx1, 2.0):
            for cz in np.arange(bz0 + 0.8, bz1, 2.2):
                cx1, cz1 = cx + rng.uniform(-0.6, 0.6), cz + rng.uniform(-0.6, 0.6)
                if geom.contains(Point(cx1, cz1)):
                    clumps.append(
                        (cx1, cz1, rng.uniform(0.5, 1.0), rng.uniform(0.45, 1.25))
                    )
        for iz, ix in np.argwhere(mask):
            ground = int(c.ground_heights[iz, ix])
            c.set(ix + c.x_min, ground, iz + c.z_min, "coarse_dirt", "terrain")
            height = max(
                (
                    h
                    * math.sqrt(
                        max(
                            0,
                            1
                            - ((x[iz, ix] - cx) ** 2 + (z[iz, ix] - cz) ** 2)
                            / radius**2,
                        )
                    )
                    for cx, cz, radius, h in clumps
                ),
                default=0,
            )
            for y in range(ground + 1, ground + 1 + round(height * c.scale)):
                if not c.get(ix + c.x_min, y, iz + c.z_min):
                    c.set(
                        ix + c.x_min,
                        y,
                        iz + c.z_min,
                        "oak_leaves",
                        "vegetation",
                        LEAVES,
                    )
                    counts["shrub_leaf_blocks"] += 1
        counts[bed["id"] + "_columns"] = int(mask.sum())
    tree_counts = {}
    for tree in profile["trees"]:
        result = build_tree(c, tree, protected, offset)
        if result:
            tree_counts[tree["id"]] = result
    return {
        "surface_columns": dict(counts),
        "trees": tree_counts,
        "architectural_columns_protected": int(protected.sum()),
        "position_evidence": "2026 drone interpretation; estimated 1.5–4 m path uncertainty; tree dimensions estimated",
    }


def build_tree(c, tree, protected, offset):
    """A branching ordinary oak approximation with an irregular lobed crown."""
    cx, cz = tree["center_xz_m"]
    radius, height = tree["crown_radius_m"], tree["height_above_ground_m"]
    tile = (
        c.x_min / c.scale,
        c.z_min / c.scale,
        (c.x_min + c.data.shape[2]) / c.scale,
        (c.z_min + c.data.shape[1]) / c.scale,
    )
    if (
        cx + radius + 1 < tile[0]
        or cx - radius - 1 >= tile[2]
        or cz + radius + 1 < tile[1]
        or cz - radius - 1 >= tile[3]
    ):
        return None
    seed = int(hashlib.sha256(tree["id"].encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    base = (tree["ground_navd88_m"] + offset) * c.scale
    top = base + height * c.scale
    crown_y = top - min(radius * 0.9, height * 0.3) * c.scale
    lobes = [(cx, crown_y, cz, radius * 0.77, min(radius, height * 0.3), radius * 0.73)]
    branches = []
    for angle in np.linspace(0, 2 * math.pi, 7, endpoint=False):
        angle += rng.uniform(-0.22, 0.22)
        reach = radius * rng.uniform(0.45, 0.64)
        bx, bz = cx + math.cos(angle) * reach, cz + math.sin(angle) * reach
        by = crown_y + rng.uniform(-0.22, 0.27) * radius * c.scale
        lobes.append(
            (
                bx,
                by,
                bz,
                radius * 0.48,
                min(radius * 0.65, height * 0.25),
                radius * 0.48,
            )
        )
        branches.append((bx, by, bz))
    count = Counter()

    def put(x, y, z, block, props):
        ix, iz = x - c.x_min, z - c.z_min
        if (
            not (0 <= ix < c.data.shape[2] and 0 <= iz < c.data.shape[1])
            or protected[iz, ix]
        ):
            return
        current = c.palette[c.get(x, y, z)]["Name"]
        if current != "minecraft:air" and not current.endswith("_leaves"):
            return
        c.set(x, y, z, block, "vegetation", props)
        count[block] += 1

    for x in range(
        max(c.x_min, math.floor((cx - radius - 1) * c.scale)),
        min(c.x_min + c.data.shape[2], math.ceil((cx + radius + 1) * c.scale)),
    ):
        for z in range(
            max(c.z_min, math.floor((cz - radius - 1) * c.scale)),
            min(c.z_min + c.data.shape[1], math.ceil((cz + radius + 1) * c.scale)),
        ):
            px, pz = (x + 0.5) / c.scale, (z + 0.5) / c.scale
            crown_bottom = max(
                base + min(2.0, height * 0.28) * c.scale,
                min(ly - ry * c.scale for _, ly, _, _, ry, _ in lobes),
            )
            for y in range(math.floor(crown_bottom), math.ceil(top) + 1):
                distance = min(
                    ((px - lx) / rx) ** 2
                    + ((y + 0.5 - ly) / (ry * c.scale)) ** 2
                    + ((pz - lz) / rz) ** 2
                    for lx, ly, lz, rx, ry, rz in lobes
                )
                noise = 0.06 * math.sin(x * 1.7 + z * 0.6 + y * 0.9) + 0.045 * math.sin(
                    z * 2.1 - x * 0.9 + y * 1.3
                )
                if distance < 1 + noise:
                    put(x, y, z, "oak_leaves", LEAVES)
    trunk_x, trunk_z = math.floor(cx * c.scale), math.floor(cz * c.scale)
    for y in range(round(base), round(crown_y + radius * c.scale * 0.1)):
        put(trunk_x, y, trunk_z, "oak_log", {"axis": "y"})
        if radius > 6:
            put(trunk_x - 1, y, trunk_z, "oak_log", {"axis": "y"})
    for bx, by, bz in branches:
        start = np.array([trunk_x, crown_y - radius * 0.65 * c.scale, trunk_z])
        end = np.array([bx * c.scale, by, bz * c.scale])
        for t in np.linspace(0, 1, max(2, math.ceil(np.linalg.norm(end - start) * 3))):
            x, y, z = np.rint(start * (1 - t) + end * t).astype(int)
            put(int(x), int(y), int(z), "oak_log", {"axis": "y"})
    return dict(count)
