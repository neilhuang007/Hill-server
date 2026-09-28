"""Metric construction primitives for individually referenced campus exteriors.

Every coordinate is a physical local UV/NAVD88 coordinate. These operations
do not choose window counts or apply a campus-wide facade pattern.
"""

from dataclasses import replace

import numpy as np
from build_hill_chapel_sample import ROLES
from campus_athey_details import AtheyExterior
from campus_quad_landscape import set_surface
from scipy.ndimage import binary_erosion
from shapely import contains_xy
from shapely.geometry import Polygon


def roof_patch(
    r,
    frame,
    bounds,
    *,
    eave,
    ridge=None,
    ridge_axis="v",
    material=None,
    combine="replace",
):
    """Correct a photographed roof plane in place, including its wall outline."""
    mask = frame.local_mask(bounds)
    u0, v0, u1, v1 = bounds
    if ridge is None:
        levels = np.full(r.heights.shape, eave)
    else:
        across, midpoint, radius = (
            (frame.u, (u0 + u1) / 2, (u1 - u0) / 2)
            if ridge_axis == "v"
            else (frame.v, (v0 + v1) / 2, (v1 - v0) / 2)
        )
        levels = eave + (ridge - eave) * (1 - np.abs(across - midpoint) / radius)
    if combine == "max":
        mask &= ~r.footprint_mask | (levels > r.heights)
    heights = r.heights.copy()
    heights[mask] = levels[mask]
    gz, gx = np.gradient(levels, r.resolution)
    rx, rz = r.gradient_x.copy(), r.gradient_z.copy()
    rx[mask], rz[mask] = gx[mask], gz[mask]
    face_index = 1_000_000 + len(r.authored_roof_patches)
    faces = r.face_indices.copy()
    faces[mask] = face_index
    record = {
        "face_index": face_index,
        "source": "individually photo-interpreted roof correction",
        "bounds_uv_m": list(bounds),
        "origin_xz_m": frame.origin.tolist(),
        "axis_degrees": frame.g["axis_degrees"],
        "eave_navd88_m": eave,
        "ridge_navd88_m": ridge,
        "ridge_axis": ridge_axis,
        "material": material,
        "affected_columns": int(mask.sum()),
    }
    return replace(
        r,
        heights=heights,
        gradient_x=rx,
        gradient_z=rz,
        face_indices=faces,
        footprint_mask=r.footprint_mask | mask,
        missing_mask=r.missing_mask & ~mask,
        authored_roof_patches=(*r.authored_roof_patches, record),
    )


class ReferenceExterior(AtheyExterior):
    def box(self, bounds, low, high, block, role, props=None, mask=None):
        selected = self.local_mask(bounds)
        if mask is not None:
            selected &= mask
        a, b = self.height_y(low) + 64, self.height_y(high) + 64
        if high > low and b == a and block not in {"air", "minecraft:air"}:
            b = a + 1
        if not 0 <= a <= b <= self.c.data.shape[0]:
            raise ValueError("Detail exceeds build height")
        state = self.c.state(block, props)
        self.c.data[a:b, selected] = state
        self.c.roles[a:b, selected] = ROLES.index(role) if state else 0

    def recolor(self, bounds, low, high, block, source_role="facade", role="facade"):
        selected = self.local_mask(bounds)
        a, b = self.height_y(low) + 64, self.height_y(high) + 64
        region = self.c.data[a:b]
        roles = self.c.roles[a:b]
        mask = (roles == ROLES.index(source_role)) & selected[None]
        region[mask] = self.c.state(block)
        roles[mask] = ROLES.index(role)

    def window_row(
        self,
        side,
        at,
        centres,
        sill,
        width,
        height,
        *,
        lights=1,
        shape="rectangle",
        transom=None,
    ):
        for centre in centres:
            self.opening(
                float(centre),
                side,
                float(sill),
                float(width),
                float(height),
                shape,
                lights=lights,
                at=float(at) if at is not None else None,
                transom=transom,
            )

    def wall_band(
        self, side, at, ends, low, height=0.25, block="quartz_block", depth=0.3
    ):
        bounds = (
            (at - depth, ends[0], at + depth, ends[1])
            if side in {"east", "west"}
            else (ends[0], at - depth, ends[1], at + depth)
        )
        # Follow existing masonry only, so a belt cannot bridge an open court.
        self.recolor(bounds, low, low + height, block, role="trim")

    def door(self, side, at, centre, floor, width=1.2, height=2.3, shape="rectangle"):
        self.window_row(side, at, [centre], floor, width, height, lights=1, shape=shape)
        bounds = (
            (at - 0.35, centre - width / 2, at + 0.35, centre + width / 2)
            if side in {"east", "west"}
            else (centre - width / 2, at - 0.35, centre + width / 2, at + 0.35)
        )
        self.box(
            bounds, floor, floor + min(1.6, height - 0.5), "dark_oak_planks", "facade"
        )
        # A real operable two-block door is set into the scaled panel.
        point = (
            self.world(at, centre)
            if side in {"east", "west"}
            else self.world(centre, at)
        )
        x, z = np.floor(point * self.c.scale).astype(int)
        y = self.height_y(floor)
        normal = (
            self.t * (1 if side == "east" else -1)
            if side in {"east", "west"}
            else self.n * (1 if side == "south" else -1)
        )
        facing = (
            ("east" if normal[0] > 0 else "west")
            if abs(normal[0]) > abs(normal[1])
            else ("south" if normal[1] > 0 else "north")
        )
        for half, dy in [("lower", 0), ("upper", 1)]:
            self.c.set(
                int(x),
                y + dy,
                int(z),
                "dark_oak_door",
                "door",
                {
                    "half": half,
                    "facing": facing,
                    "hinge": "left",
                    "open": "false",
                    "powered": "false",
                },
            )
        self.features["operable_reference_doors"] += 1

    def floor_plate(self, level, bounds=None, block="birch_planks"):
        mask = binary_erosion(
            self.r.footprint_mask & (self.r.heights > level + 1), iterations=2
        )
        if bounds:
            mask &= self.local_mask(bounds)
        y = self.height_y(level) - 1
        mask &= self.c.ground_heights < y
        mask &= self.c.roles[y + 64] == ROLES.index("air")
        self.c.data[y + 64, mask] = self.c.state(block)
        self.c.roles[y + 64, mask] = ROLES.index("floor")

    def deck(self, bounds, level, block="smooth_stone", thickness=0.5, role="floor"):
        self.box(bounds, level - thickness, level, block, role)

    def site_surface(
        self,
        polygon_uv,
        level,
        full="smooth_stone",
        slab="smooth_stone_slab",
        slope=(0, 0),
    ):
        mask = contains_xy(Polygon(polygon_uv), self.u, self.v)
        protected = np.any(
            np.isin(
                self.c.roles,
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
                    )
                ],
            ),
            axis=0,
        )
        for _, _, iz, ix in self.each_column(mask & ~protected):
            h = level + slope[0] * self.u[iz, ix] + slope[1] * self.v[iz, ix]
            set_surface(self.c, iz, ix, (h + self.offset) * self.c.scale, full, slab)

    def railing(self, side, at, ends, floor, height=1.0, post_spacing=2.2, white=False):
        bounds = (
            (at - 0.2, ends[0], at + 0.2, ends[1])
            if side in {"east", "west"}
            else (ends[0], at - 0.2, ends[1], at + 0.2)
        )
        self.box(
            bounds,
            floor,
            floor + height,
            "birch_fence" if white else "iron_bars",
            "railing",
            {
                "north": "false",
                "south": "false",
                "east": "false",
                "west": "false",
                "waterlogged": "false",
            },
        )
        if white:
            self.features["fine_pale_wood_balustrade_runs"] += 1
            return
        for at_along in np.arange(ends[0], ends[1] + 0.01, post_spacing):
            post = (
                (at - 0.25, at_along - 0.25, at + 0.25, at_along + 0.25)
                if side in {"east", "west"}
                else (at_along - 0.25, at - 0.25, at_along + 0.25, at + 0.25)
            )
            self.box(
                post,
                floor,
                floor + height,
                "quartz_block" if white else "stone_bricks",
                "trim" if white else "facade",
            )
        if white:
            self.box(
                bounds,
                floor + height - 0.15,
                floor + height,
                "quartz_slab",
                "trim",
                {"type": "bottom", "waterlogged": "false"},
            )

    def roof_edge_trim(self, bounds, block="quartz_block"):
        mask = self.local_mask(bounds) & self.r.footprint_mask
        for x, z, iz, ix in self.each_column(mask):
            roof_cells = np.flatnonzero(self.c.roles[:, iz, ix] == ROLES.index("roof"))
            if not roof_cells.size:
                continue
            y = int(roof_cells[-1]) + self.c.y_min
            state = self.c.palette[self.c.get(x, y, z)]
            props = state.get("Properties")
            target = (
                "quartz_stairs"
                if "stairs" in state["Name"]
                else "quartz_slab"
                if "slab" in state["Name"]
                else block
            )
            self.c.set(x, y, z, target, "trim", props if target != block else None)
            # A top slab in this substrate cell left a quarter-metre daylight
            # slit between the gable wall and its coping. Retain solid backing
            # below the thin roof-edge piece without lifting the roof top.
            self.c.set(x, y - 1, z, self.p["materials"]["facade"], "facade")


def connect_wood_fences(c):
    for state_id, state in enumerate(list(c.palette)):
        if not state["Name"].endswith("_fence"):
            continue
        for iy, iz, ix in np.argwhere(c.data == state_id):
            x, y, z = int(ix + c.x_min), int(iy + c.y_min), int(iz + c.z_min)
            role = ROLES[int(c.roles[iy, iz, ix])]
            if role == "trim" and all(
                direction in state.get("Properties", {})
                for direction in ("north", "south", "east", "west")
            ):
                # Authored sash shafts carry an intentional connection state.
                # They must not be reclassified as exterior railing or joined
                # indiscriminately to glass by the site-fence convenience pass.
                continue
            props = {"waterlogged": "false"}
            for name, dx, dz in [
                ("east", 1, 0),
                ("west", -1, 0),
                ("south", 0, 1),
                ("north", 0, -1),
            ]:
                props[name] = "true" if c.get(x + dx, y, z + dz) else "false"
            c.set(x, y, z, state["Name"], role, props)
