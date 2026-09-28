"""Building-specific Athey details supported by the school's 2026 footage.

The east bay/parapet and engineered paving deliberately refine the raw LiDAR
envelope. Estimated dimensions and every correction are kept in the profile.
"""

from __future__ import annotations

import math
from dataclasses import replace
import numpy as np

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import AcademicExterior, PANE_PROPS

SLAB = {"type": "bottom", "waterlogged": "false"}


class AtheyExterior(AcademicExterior):
    def opening(
        self, u, side, sill, width, height, shape="rectangle", lights=2,
        at=None, transom=None,
    ):
        """Keep sub-voxel sash bars from becoming half-metre masonry posts.

        The photographed narrow groups have fine internal sash divisions;
        their pale surround is structural. At the retained two-block scale,
        expanding each sash to the shared raster's minimum post width loses
        most of a three-light group's glazing. The existing pane texture is
        the bounded proxy for those small divisions. Large central masonry
        groups keep their authored posts and all opening controls stay put.
        """
        config = self.p.get("frame_refinement", {})
        narrow = config.get("pane_sash_max_width_m", 0) >= width
        before = len(getattr(self.c, "window_opening_regions", []))
        original_raster = self.r
        if config.get("fit_complete_frame_below_roof"):
            # The east bay was already corrected to its photographed flat
            # roof. Its obsolete Roofer ramp must not receive upper windows.
            # A low link/eave column also needs room for a complete head before
            # any glass is cut there; checking pane centres alone leaves open
            # tops and floating partial windows over the lower roof.
            if not hasattr(self, "opening_roof_heights"):
                self.opening_roof_heights = self.r.heights.copy()
                bay = self.p["east_return"]
                mask = (self.local_mask(bay["bay_bounds_uv_m"]) & self.r.footprint_mask
                        & (self.r.heights < self.g["main_roof_threshold_navd88_m"]))
                self.opening_roof_heights[mask] = np.minimum(
                    self.opening_roof_heights[mask], bay["roof_navd88_m"],
                )
            border = self.p["window_reveal"]["trim_width_m"]
            self.r = replace(
                self.r, heights=self.opening_roof_heights,
                footprint_mask=self.r.footprint_mask &
                (self.opening_roof_heights >= sill + height + border),
            )
        try:
            super().opening(
                u, side, sill, width, height, shape,
                lights=1 if narrow else lights, at=at,
                transom=None if narrow else transom,
            )
        finally:
            self.r = original_raster
        if len(getattr(self.c, "window_opening_regions", [])) == before:
            return
        allowed, inward = self.c.window_opening_regions[-1]
        if config:
            if not hasattr(self, "frame_regions"):
                self.frame_regions = []
            self.frame_regions.append({
                "allowed": allowed, "inward": inward, "side": side, "u": u,
                "sill": sill, "width": width, "height": height, "shape": shape,
            })
        if narrow and (lights > 1 or transom is not None):
            self.features["narrow_groups_with_pane_texture_sash"] += 1
            self.features["sub_voxel_sash_divisions_retained_in_profile"] += lights - 1
            # At one measured setback the raster footprints touch diagonally
            # and neither shared corner belongs to the wall. Keep the nearest
            # original masonry divider there instead of projecting new glass
            # across an exterior cell. This is a footprint constraint, not a
            # licence to widen every post.
            along_values = self.v if side in {"east", "west"} else self.u
            posts = u + np.linspace(-width / 2, width / 2, lights + 1)[1:-1]
            if len(posts):
                for x, y, z in sorted(allowed):
                    if not self.c.palette[self.c.get(x, y, z)]["Name"].endswith("_pane"):
                        continue
                    for dz in (-1, 1):
                        end = (x + 1, y, z + dz)
                        corners = ((x + 1, y, z), (x, y, z + dz))
                        if (end not in allowed or
                            not self.c.palette[self.c.get(*end)]["Name"].endswith("_pane") or
                            any(q in allowed or self.c.get(*q) for q in corners)):
                            continue
                        def distance(q):
                            iz, ix = q[2] - self.c.z_min, q[0] - self.c.x_min
                            return float(np.min(abs(along_values[iz, ix] - posts)))
                        retained = min(((x, y, z), end), key=distance)
                        if distance(retained) <= 0.33:
                            self.c.set(*retained, "quartz_block", "trim")
                            self.features["masonry_at_unjoinable_measured_setback"] += 1

    def support_window_frames(self):
        """Back the authored frame ring without filling the glass silhouette.

        Ground metadata survives the hollow shell's excavation. Therefore it
        cannot stand in for an occupied sill cell. Missing frame caps use the
        actual archive state, and sill haunches retain the original top level.
        A single inward brick course is bounded to the same cut reveal and to
        the outside of the opening silhouette; it never grows through glass.
        """
        if not self.p.get("frame_refinement", {}).get("back_frame_ring"):
            return
        connect_window_panes(self.c)
        self.frame_repairs = {"caps": [], "sill_haunches": [], "brick_backing": []}
        for region in self.frame_regions:
            allowed, inward = region["allowed"], region["inward"]
            columns = {(x, z) for x, _, z in allowed}
            along = self.v if region["side"] in {"east", "west"} else self.u
            border = self.p["window_reveal"]["trim_width_m"]

            def frame_cell(q):
                x, y, z = q
                iz, ix = z - self.c.z_min, x - self.c.x_min
                if ((x, z) not in columns or not self.r.footprint_mask[iz, ix] or
                    (y + 0.5) / self.c.scale - self.offset > self.r.heights[iz, ix]):
                    return False
                d = float(along[iz, ix] - region["u"])
                h = (y + 0.5) / self.c.scale - self.offset - region["sill"]
                return (self.in_opening(d, h + border, region["width"] + 2 * border,
                                       region["height"] + 2 * border, region["shape"])
                        and not self.in_opening(d, h, region["width"],
                                                region["height"], region["shape"]))

            ring = {q for q in allowed if frame_cell(q)}
            grade_caps = set()
            for x, y, z in sorted(allowed):
                if not self.c.palette[self.c.get(x, y, z)]["Name"].endswith("_pane"):
                    continue
                for dy in (-1, 1):
                    q = (x, y + dy, z)
                    # A pane may start above its nominal sill where external
                    # grade hides the lower part. That metadata is not a real
                    # block: complete precisely the air cell below live glass.
                    below_live_glass = (dy < 0 and (x, z) in columns and
                                        q[1] >= self.height_y(region["sill"] - border))
                    if (frame_cell(q) or below_live_glass) and not self.c.get(*q):
                        self.c.set(*q, "quartz_slab", "trim", {
                            "type": "top" if dy < 0 else "bottom", "waterlogged": "false",
                        })
                        ring.add(q)
                        if below_live_glass:
                            grade_caps.add(q)
                        self.frame_repairs["caps"].append(list(q))
            dx, dz = ((1 if inward[0] > 0 else -1, 0) if abs(inward[0]) >= abs(inward[1])
                      else (0, 1 if inward[1] > 0 else -1))
            facing = "east" if dx == 1 else "west" if dx == -1 else "south" if dz == 1 else "north"
            for q in sorted(ring):
                state = self.c.palette[self.c.get(*q)]
                if (state["Name"] == "minecraft:quartz_slab" and
                    state.get("Properties", {}).get("type") == "top"):
                    self.c.set(*q, "quartz_stairs", "trim", {
                        "facing": facing, "half": "top", "shape": "straight",
                        "waterlogged": "false",
                    })
                    self.frame_repairs["sill_haunches"].append(list(q))
                if not state["Name"].startswith("minecraft:quartz"):
                    continue
                backing = (q[0] + dx, q[1], q[2] + dz)
                grade_backing = (q in grade_caps and (backing[0], backing[2]) in columns)
                if (frame_cell(backing) or grade_backing) and not self.c.get(*backing):
                    self.c.set(*backing, "bricks", "facade")
                    self.frame_repairs["brick_backing"].append(list(backing))
        for kind, positions in self.frame_repairs.items():
            self.features["frame_" + kind + "_cells"] = len(positions)

    def remove_unbacked_bay_band_islands(self):
        """Remove only detached full-block band pieces outside the source wall.

        The authored band previously lacked the footprint mask used by the
        bay wall below it. Its disconnected exterior pieces therefore floated
        in air. Full cubes need no guessed partial shape: a component without
        any occupied face neighbour has no physical backing at all.
        """
        if not self.p.get("frame_refinement", {}).get("remove_unbacked_bay_band"):
            return
        bay = self.p["east_return"]
        _, v0, u1, v1 = bay["bay_bounds_uv_m"]
        roof = bay["roof_navd88_m"]
        mask = self.local_mask((u1 - 0.4, v0, u1 + 0.05, v1))
        candidates = {
            (x, y, z)
            for x, z, _, _ in self.each_column(mask)
            for y in range(self.height_y(roof - 0.1), self.height_y(roof + 0.05))
            if self.c.palette[self.c.get(x, y, z)]["Name"] == "minecraft:quartz_block"
        }
        removed = []
        while candidates:
            start = candidates.pop()
            pending, component, backed = [start], {start}, False
            while pending:
                x, y, z = pending.pop()
                for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                   (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                    q = (x + dx, y + dy, z + dz)
                    if q in candidates:
                        candidates.remove(q); component.add(q); pending.append(q)
                    elif q not in component and self.c.get(*q):
                        backed = True
            outside = all(not self.r.footprint_mask[z - self.c.z_min, x - self.c.x_min]
                          for x, _, z in component)
            if outside and not backed:
                for q in sorted(component):
                    self.c.set(*q, "air", "air")
                    removed.append(list(q))
        self.features["unbacked_exterior_bay_band_cells_removed"] = len(removed)
        self.frame_repairs["unbacked_exterior_bay_band_removed"] = removed

    def box(self, bounds, low, high, block, role, props=None, mask=None):
        selected = self.local_mask(bounds)
        if mask is not None:
            selected &= mask
        a, b = self.height_y(low) + 64, self.height_y(high) + 64
        if not 0 <= a <= b <= self.c.data.shape[0]:
            raise ValueError("Athey detail exceeds vanilla build height")
        state = self.c.state(block, props)
        self.c.data[a:b, selected] = state
        self.c.roles[a:b, selected] = ROLES.index(role) if state else 0

    def engineered_court(self):
        config = self.p["site_details"]
        mask = self.local_mask(self.g["court_bounds_uv_m"]) & ~self.r.footprint_mask
        # Reconstructed DTM beside walls undulates. The current video shows an
        # engineered paved court. Only that observed paving gets a smooth grade.
        base, du, dv = config["court_plane_navd88_m"]
        level = base + du * (self.u - 37) + dv * (self.v - 28)
        y = np.rint((level + self.offset) * self.c.scale).astype(int) - 1
        for x, z, iz, ix in self.each_column(mask):
            target = int(y[iz, ix])
            old = self.c.ground_at(x, z)
            for yy in range(min(old, target) - 1, max(old, target) + 1):
                self.c.set(
                    x,
                    yy,
                    z,
                    "stone" if yy < target else "air",
                    "terrain" if yy < target else "air",
                )
            pale = abs(self.u[iz, ix] - 37) < 0.55 or abs(self.v[iz, ix] - 27.5) < 0.55
            self.c.set(x, target, z, "smooth_stone" if pale else "bricks", "pavement")
            self.c.ground_heights[iz, ix] = target
        self.features["engineered_court_columns"] = int(mask.sum())

    def coping(self):
        family = "minecraft:" + self.p["materials"]["roof_family"]
        # Coping follows actual sampled gable slopes. Limit it to the three
        # observed cross-gables, rather than drawing a pale line on every eave.
        for center, half_width in self.p["gable_coping_uv_m"]:
            for side in ("north", "south"):
                for u in np.arange(
                    center - half_width, center + half_width + 0.1, 0.13
                ):
                    v = self.edge_v(float(u), side)
                    if v is None:
                        continue
                    mask = (abs(self.u - u) < 0.20) & (abs(self.v - v) < 0.34)
                    for x, z, iz, ix in self.each_column(mask):
                        h = self.r.heights[iz, ix]
                        if not math.isfinite(h):
                            continue
                        y = self.height_y(float(h))
                        for yy in range(y - 2, y + 2):
                            block = self.c.palette[self.c.get(x, yy, z)]
                            if not block["Name"].startswith(family):
                                continue
                            suffix = block["Name"].removeprefix(family)
                            target = (
                                "quartz_stairs"
                                if suffix == "_stairs"
                                else "quartz_slab"
                                if suffix == "_slab"
                                else "quartz_block"
                            )
                            self.c.set(
                                x, yy, z, target, "trim", block.get("Properties")
                            )
                            self.features["photo_gable_coping_blocks"] += 1

    def central_north(self):
        u = self.g["central_bay_u_m"]
        v = self.edge_v(u, "north")
        if v is None:
            return
        for post in (u - 3.15, u + 3.15):
            self.box(
                (post - 0.16, v + 0.05, post + 0.16, v + 0.45),
                69.9,
                81.75,
                "quartz_block",
                "trim",
            )
        # Central entrance is narrower than the upper three-light groups.
        self.opening(u, "north", 67.35, 2.65, 2.7, lights=2, transom=2.05)
        self.box(
            (u - 1.05, v + 0.05, u + 1.05, v + 0.42),
            67.4,
            69.15,
            "dark_oak_planks",
            "facade",
        )
        for delta in (-0.8, 0.8):
            self.box(
                (u + delta - 0.11, v - 0.12, u + delta + 0.11, v + 0.18),
                68.05,
                68.55,
                "iron_bars",
                "railing",
                PANE_PROPS,
            )
        self.features["central_north_entrance"] = 1

    def east_return(self):
        g = self.p["east_return"]
        u0, v0, u1, v1 = g["bay_bounds_uv_m"]
        deck, roof, parapet = (
            g["deck_navd88_m"],
            g["roof_navd88_m"],
            g["parapet_navd88_m"],
        )
        mask = self.r.footprint_mask & (self.r.heights < 80.5)
        # Current footage has a low flat bay with notched brick parapet. Roofer
        # fits this end as a ramp: retain its plan, correct just the verified bay.
        self.box((u0, v0, u1, v1), roof - 0.2, 78, "air", "air", mask=mask)
        self.box((u0, v0, u1, v1), roof - 0.45, roof, "smooth_stone", "roof", mask=mask)
        self.box((u1 - 0.4, v0, u1, v1), deck, roof, "bricks", "facade", mask=mask)
        self.box(
            (u1 - 0.45, v0, u1 + 0.05, v1),
            68.0,
            deck,
            "polished_granite",
            "facade",
            mask=mask,
        )
        for bounds in (
            (u1 - 0.35, v0, u1, v1),
            (u0, v0, u1, v0 + 0.35),
            (u0, v1 - 0.35, u1, v1),
        ):
            self.box(bounds, roof, parapet, "bricks", "facade", mask=mask)
            self.box(
                bounds, parapet - 0.125, parapet, "quartz_slab", "trim", SLAB, mask=mask
            )
        for center in g["parapet_notches_v_m"]:
            self.box(
                (u1 - 0.5, center - 0.45, u1 + 0.2, center + 0.45),
                parapet - 0.35,
                parapet + 0.2,
                "air",
                "air",
            )
            self.box(
                (u1 - 0.4, center - 0.45, u1 + 0.1, center + 0.45),
                parapet - 0.5,
                parapet - 0.375,
                "quartz_slab",
                "trim",
                SLAB,
            )
        self.box(
            (u1 - 0.4, v0, u1 + 0.05, v1),
            roof - 0.1,
            roof + 0.05,
            "quartz_block",
            "trim",
        )
        for center in g["bay_window_centres_v_m"]:
            self.opening(
                center,
                "east",
                deck + 0.5,
                2.75,
                2.0,
                lights=3,
                at=u1 - 0.15,
                transom=1.5,
            )
        for height in (75.8, 79.6):
            for center in (3.1, 8.5):
                self.opening(center, "east", height, 2.7, 1.85, lights=3)
        door_v = g["door_v_m"]
        self.opening(
            door_v, "east", deck, 1.25, 2.4, lights=1, at=u1 - 0.15, transom=1.85
        )
        self.box(
            (u1 - 0.2, door_v - 0.52, u1 + 0.12, door_v + 0.52),
            deck,
            deck + 1.85,
            "dark_oak_planks",
            "facade",
        )
        # Stone landing and descending run, entirely inside the bounded site.
        landing = (u1 - 0.1, door_v - 1.1, u1 + 1.6, door_v + 1.1)
        self.box(landing, 68.2, deck, "smooth_stone", "pavement")
        for i in range(7):
            h = deck - (i + 1) * 0.2
            self.box(
                (u1 + 1.4 + i * 0.4, door_v - 1, u1 + 1.8 + i * 0.4, door_v + 1),
                68.0,
                h,
                "smooth_stone",
                "pavement",
            )
            for edge in (-1.15, 1.15):
                self.box(
                    (
                        u1 + 1.4 + i * 0.4,
                        door_v + edge - 0.1,
                        u1 + 1.8 + i * 0.4,
                        door_v + edge + 0.1,
                    ),
                    h,
                    h + 0.9,
                    "iron_bars",
                    "railing",
                    PANE_PROPS,
                )
        for edge in (-1.15, 1.15):
            self.box(
                (u1, door_v + edge - 0.1, u1 + 1.6, door_v + edge + 0.1),
                deck,
                deck + 0.9,
                "iron_bars",
                "railing",
                PANE_PROPS,
            )
        self.features.update(
            {
                "east_bay_parapet": 1,
                "east_door_and_steps": 1,
                "east_upper_window_groups": 4,
            }
        )

    def link_roof(self):
        for link in self.g["covered_links"]:
            if not link["open_passage"]:
                continue
            mask = (
                self.local_mask(link["bounds_uv_m"])
                & self.r.footprint_mask
                & (self.r.heights < 76)
            )
            for x, z, iz, ix in self.each_column(mask):
                roof = self.height_y(float(self.r.heights[iz, ix]))
                # A continuous thin backing prevents sky slits between rotated
                # metal-roof proxy slabs after opening the passage underneath.
                self.c.set(x, roof - 1, z, "smooth_stone", "roof")
                self.c.set(x, roof, z, "smooth_stone_slab", "roof", SLAB)

    def build(self):
        super().build()
        self.engineered_court()
        self.coping()
        self.central_north()
        self.east_return()
        self.link_roof()
        self.support_window_frames()
        self.remove_unbacked_bay_band_islands()
        result = dict(self.features)
        if hasattr(self, "frame_repairs"):
            result["frame_repair_coordinates"] = self.frame_repairs
        return result


def connect_iron_rails(canvas):
    ids = [
        i for i, p in enumerate(canvas.palette) if p["Name"] == "minecraft:iron_bars"
    ]
    if not ids:
        return
    for iy, iz, ix in np.argwhere(np.isin(canvas.data, ids)):
        x, y, z = int(ix) + canvas.x_min, int(iy) - 64, int(iz) + canvas.z_min
        props = dict(PANE_PROPS)
        for name, dx, dz in (
            ("north", 0, -1),
            ("south", 0, 1),
            ("east", 1, 0),
            ("west", -1, 0),
        ):
            neighbor = canvas.palette[canvas.get(x + dx, y, z + dz)]["Name"]
            props[name] = "true" if neighbor != "minecraft:air" else "false"
        role = ROLES[int(canvas.roles[iy, iz, ix])]
        canvas.set(x, y, z, "iron_bars", role, props)


def refine_existing_athey(canvas, profile, raster, offset, config):
    """Repair an accepted archive without regenerating its measured shell.

    Returns close only gaps between already-authored glazing and its masonry
    or another piece of the same glazing. The measured footprint admits the
    inward shared corner of a diagonal voxel boundary (at most 0.36 m from
    its polygon); this does not move a wall plane or invent an exterior bay.
    """
    from collections import deque
    from shapely import contains_xy

    exterior = AtheyExterior(canvas, profile, raster, offset)
    pane_region=exterior.local_mask(config.get("repair_pane_bounds_uv_m",[-1,-10,79,24]))
    report = {"court_ground_arches": [], "pane_returns": [], "frame_caps": [],
              "frame_cap_backing": [], "boundary_corner_cells": []}
    arches = config.get("court_ground_arches", {})
    for spec in arches.get("openings", []):
        u, width = spec["center_u_m"], spec["width_m"]
        edge = exterior.edge_v(u, "south")
        if edge is None:
            raise ValueError("Court opening has no measured south wall")
        # Remove only the previous lower glazed/trim opening. Its surrounding
        # brick planes, floor, roof and upper-storey openings remain exact.
        old_width = profile["geometry"]["central_window_width_m"] if u == 37 else profile["geometry"]["flank_window_width_m"]
        selected = (abs(exterior.u-u) <= old_width/2+.55) & (abs(exterior.v-edge) <= 2.8)
        for x,z,_,_ in exterior.each_column(selected):
            for y in range(exterior.height_y(69.5), exterior.height_y(74.0)):
                state = canvas.palette[canvas.get(x,y,z)]
                if state["Name"].endswith("_pane") or "quartz" in state["Name"]:
                    canvas.set(x,y,z,"bricks","facade")
        exterior.opening(u,"south",arches["sill_navd88_m"],width,
                         arches["height_m"],"pointed",lights=1)
        report["court_ground_arches"].append({**spec,"wall_v_m":edge,
            "sill_navd88_m":arches["sill_navd88_m"],"height_m":arches["height_m"]})
    west_end=config.get("west_end_inferred",{})
    for sill in west_end.get("sills_navd88_m",[]):
        for center in west_end["centers_v_m"]:
            exterior.opening(center,"west",sill,west_end["width_m"],
                             west_end["height_m"],"rectangle",lights=1)
            report.setdefault("west_end_inferred_openings",[]).append({
                "center_v_m":center,"sill_navd88_m":sill,
                "width_m":west_end["width_m"],"height_m":west_end["height_m"],
                "status":"Conservative inferred end elevation, aligned to retained storey levels; no exact west photographic schedule claimed"})
    if arches or west_end:
        exterior.support_window_frames()
    if "south_stringcourse_navd88_m" in config:
        old = exterior.height_y(70.4)
        new = exterior.height_y(config["south_stringcourse_navd88_m"])
        for u in np.arange(21.8,52.2,.20):
            edge = exterior.edge_v(float(u),"south")
            if edge is None:
                continue
            mask = (abs(exterior.u-u)<.21)&(abs(exterior.v-edge)<.8)
            for x,z,_,_ in exterior.each_column(mask):
                if canvas.palette[canvas.get(x,old,z)]["Name"] in {
                    "minecraft:quartz_block","minecraft:smooth_quartz"}:
                    canvas.set(x,old,z,"bricks","facade")
                if canvas.palette[canvas.get(x,new,z)]["Name"] == "minecraft:bricks":
                    canvas.set(x,new,z,"smooth_quartz","trim")

    pane_ids = [i for i,state in enumerate(canvas.palette) if state["Name"].endswith("_pane")]
    panes = {(int(x+canvas.x_min),int(y+canvas.y_min),int(z+canvas.z_min))
             for y,z,x in np.argwhere(np.isin(canvas.data,pane_ids)) if pane_region[z,x]}
    original_panes = panes.copy()
    allowed = contains_xy(config["measured_footprint"].buffer(.36),exterior.x,exterior.z)
    directions = ((1,0,0),(-1,0,0),(0,0,1),(0,0,-1))

    def add(q,d):
        return tuple(q[i]+d[i] for i in range(3))

    def solid(q):
        name = canvas.palette[canvas.get(*q)]["Name"]
        return name != "minecraft:air" and not name.endswith(
            ("_pane","_stairs","_slab","_door","_trapdoor","_bars"))

    def valid(q):
        x,y,z=q; iz,ix=z-canvas.z_min,x-canvas.x_min
        return allowed[iz,ix] and pane_region[iz,ix] and 66<y/2+25<88

    def degree(q):
        return sum(solid(add(q,d)) or add(q,d) in panes for d in directions)

    def component(q):
        seen={q};pending=[q]
        while pending:
            p=pending.pop()
            for d in directions:
                nxt=add(p,d)
                if nxt in panes and nxt not in seen:
                    seen.add(nxt);pending.append(nxt)
        return seen

    report["original_horizontal_endpoints"] = sum(degree(q)<2 for q in panes)
    # A pane whose rasterised reveal lost its jamb may need three cells to
    # follow the already-authored diagonal indentation back to that jamb.
    # A longer final pass is allowed only for the two residual source breaks.
    for max_air_cells in (3,3,4):
        for q in sorted(panes.copy()):
            if degree(q)>=2:
                continue
            own=component(q);choices=[];pending=deque([(q,[])])
            while pending:
                at,path=pending.popleft()
                if len(path)>max_air_cells:
                    continue
                for d in directions:
                    nxt=add(at,d)
                    if nxt==q or nxt in path or not valid(nxt):
                        continue
                    if solid(nxt) or (nxt in panes and nxt not in own):
                        if path and math.dist(q,nxt)>1:
                            choices.append(path)
                    elif not canvas.get(*nxt):
                        pending.append((nxt,path+[nxt]))
            if not choices:
                continue
            iz,ix=q[2]-canvas.z_min,q[0]-canvas.x_min
            u,v=exterior.u[iz,ix],exterior.v[iz,ix]
            inward=(-exterior.t if u>71 else exterior.t if u<3 else
                    -exterior.n if v>7.5 else exterior.n)
            path=min(choices,key=lambda p:(len(p),-sum(
                (k[0]-q[0])*inward[0]+(k[2]-q[2])*inward[1] for k in p),p))
            for nxt in path:
                canvas.set(*nxt,"gray_stained_glass_pane","window",PANE_PROPS)
                panes.add(nxt)
                report["pane_returns"].append(list(nxt))
    # Complete vertical gaps within one storey's new return, then cap its
    # actual occupied ends. No floor plate or original glass is overwritten.
    for x,y,z in list(panes-original_panes):
        for dy in (-1,1):
            q=(x,y+dy,z)
            if not canvas.get(*q) and (x,y+2*dy,z) in panes:
                canvas.set(*q,"gray_stained_glass_pane","window",PANE_PROPS)
                panes.add(q);report["pane_returns"].append(list(q))
    for x,y,z in sorted(panes):
        for dy in (-1,1):
            q=(x,y+dy,z)
            if not canvas.get(*q):
                # This is a concealed glazing-return corner, not a new
                # photographed pale arch surround. Full tinted glass closes
                # its occupied height without pale islands inside the window.
                canvas.set(*q,"gray_stained_glass","window")
                report["frame_caps"].append(list(q))
    # The newly cap-filled return can sit inward of the old head/sill. Tie
    # each cap to real masonry using a same-height concealed shortest path.
    cap_set={tuple(q) for q in report["frame_caps"] if "quartz" in
             canvas.palette[canvas.get(*q)]["Name"]}
    for q in sorted(cap_set):
        pending=deque([(q,[])]);choices=[];seen={q}
        while pending:
            at,path=pending.popleft()
            if len(path)>3:
                continue
            for d in directions:
                nxt=add(at,d)
                if nxt in seen or not valid(nxt):
                    continue
                seen.add(nxt)
                if solid(nxt) and nxt not in cap_set:
                    choices.append(path)
                elif not canvas.get(*nxt) or nxt in cap_set:
                    pending.append((nxt,path+[nxt]))
        if choices:
            for nxt in min(choices,key=lambda p:(len(p),p)):
                if not canvas.get(*nxt):
                    canvas.set(*nxt,"bricks","facade")
                    report["frame_cap_backing"].append(list(nxt))
    # Retain the accepted Athey material family after the opening helper.
    for state_id,state in enumerate(list(canvas.palette)):
        replacement={"minecraft:quartz_block":"smooth_quartz",
                     "minecraft:quartz_stairs":"smooth_quartz_stairs",
                     "minecraft:quartz_slab":"smooth_quartz_slab"}.get(state["Name"])
        if replacement:
            canvas.data[canvas.data==state_id]=canvas.state(replacement,state.get("Properties"))
    # Resolve the residual short shoulder ends using a full glazing return.
    # A full glass cell, still inside the reveal, has occupied contact with a
    # neighbouring stair even where vanilla pane auto-connection refuses it.
    for q in sorted(panes):
        if degree(q)<2:
            touching_partial = [add(q,d) for d in directions if canvas.palette[
                canvas.get(*add(q,d))]["Name"].endswith(("_stairs","_slab"))]
            if touching_partial:
                canvas.set(*q,"gray_stained_glass","window")
                report.setdefault("solid_glazing_shoulder_returns",[]).append(list(q))
    # Ensure detached trim tips introduced by a stepped opening have a real
    # masonry return. Search from each small trim island, never through glass.
    from audit_hill_quadrivium_contacts import shapes, AXES
    def occupies_face(q,d):
        axis=next(i for i,value in enumerate(d) if value)
        tangent=[i for i in range(3) if i!=axis]
        lefts=shapes(__import__("json").dumps(canvas.palette[canvas.get(*q)],sort_keys=True))
        rights=shapes(__import__("json").dumps(canvas.palette[canvas.get(*add(q,d))],sort_keys=True))
        for left in lefts:
            for right in rights:
                shifted=[right[i]+16*d[i%3] for i in range(6)]
                if left[axis+3 if d[axis]>0 else axis] != shifted[axis if d[axis]>0 else axis+3]:
                    continue
                if all(min(left[i+3],shifted[i+3])>max(left[i],shifted[i]) for i in tangent):
                    return True
        return False
    trim_ids=[i for i,state in enumerate(canvas.palette) if "quartz" in state["Name"]]
    trim={(int(x+canvas.x_min),int(y+canvas.y_min),int(z+canvas.z_min))
          for y,z,x in np.argwhere(np.isin(canvas.data,trim_ids)) if pane_region[z,x]}
    remaining=trim.copy()
    while remaining:
        first=remaining.pop();group={first};pending=[first];rooted=False
        while pending:
            q=pending.pop()
            for d in AXES:
                nxt=add(q,d)
                if not occupies_face(q,d):
                    continue
                if nxt in remaining:
                    remaining.remove(nxt);group.add(nxt);pending.append(nxt)
                elif nxt not in trim:
                    name=canvas.palette[canvas.get(*nxt)]["Name"]
                    if name!="minecraft:air" and not any(part in name for part in ("glass","bars","leaves")):
                        rooted=True
        if rooted:
            continue
        pending=deque((q,[]) for q in sorted(group));seen=set(group);choices=[]
        while pending:
            q,path=pending.popleft()
            if len(path)>4:
                continue
            for d in AXES:
                nxt=add(q,d)
                if nxt in seen or not valid(nxt):
                    continue
                seen.add(nxt)
                name=canvas.palette[canvas.get(*nxt)]["Name"]
                if name!="minecraft:air" and not any(part in name for part in ("glass","bars","leaves")):
                    # Other members of this floating trim island cannot root it.
                    if nxt not in group:
                        choices.append(path)
                elif name=="minecraft:air":
                    pending.append((nxt,path+[nxt]))
        if choices:
            for nxt in min(choices,key=lambda p:(len(p),p)):
                canvas.set(*nxt,"bricks","facade")
                report["frame_cap_backing"].append(list(nxt))
    connect_window_panes(canvas)
    report["remaining_horizontal_endpoints"]=sorted(q for q in panes
        if canvas.palette[canvas.get(*q)]["Name"].endswith("_pane") and degree(q)<2)
    report["boundary_corner_cells"]=[q for q in report["pane_returns"]+report["frame_caps"]+
        report["frame_cap_backing"] if not raster.footprint_mask[q[2]-canvas.z_min,q[0]-canvas.x_min]]
    report["method"]="Shortest connected glazing returns within existing cut reveals; original roof and existing nonwindow masonry planes retained. Concealed full-glass caps close return heights without introducing pale trim islands. Corner cells intersect the measured footprint."
    return report
