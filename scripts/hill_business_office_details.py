"""Photo-interpreted west elevation of Hillhouse & Moore Business Office.

The original measured outline and twenty roof faces remain in provenance.
Only the photo-proven two-storey bay overlays a bounded ground-height subset
of source face4. Unseen elevations receive no mirrored aperture pattern.
"""
from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
from scipy.ndimage import binary_erosion
from shapely import contains_xy
from shapely.geometry import Polygon

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building
from campus_window_frames import (
    bridge_frame_edges, close_diagonal_pane_corners, close_diagonal_pane_jambs,
)

TOP = {"type": "top", "waterlogged": "false"}
BOTTOM = {"type": "bottom", "waterlogged": "false"}
POST = {**{d: "false" for d in ("north", "south", "east", "west")}, "waterlogged": "false"}


def _bay_mask(f, p):
    return contains_xy(Polygon(p["bay"]["polygon_uv_m"]), f.u, f.v) & f.r.footprint_mask


def prepare_roof(r, f, p):
    """Overlay the observed bay, retaining every original ordered source face."""
    original = load_measured_building(parent_id=p["parent_id"])
    records = []
    for i, face in enumerate(original.roof_faces):
        records.append({**p["roof_evidence"]["all_original_faces"][i],
                        "part_id": face.part_id, "surface_index": face.surface_index,
                        "disposition": "bounded bay subset overlaid; remaining original ground-level sample retained"
                        if i == 4 else "original measured plane retained without height change"})
    bay = p["bay"]
    mask = _bay_mask(f, p) & (r.face_indices == bay["source_face_id"])
    amount = np.clip((f.u-.12)/(1.8-.12), 0, 1)
    levels = bay["cap_eave_navd88_m"] + amount*(bay["cap_inner_navd88_m"]-bay["cap_eave_navd88_m"])
    heights, indices = r.heights.copy(), r.face_indices.copy()
    gx, gz = r.gradient_x.copy(), r.gradient_z.copy()
    dz, dx = np.gradient(levels, r.resolution)
    heights[mask], indices[mask] = levels[mask], 1000000
    gx[mask], gz[mask] = dx[mask], dz[mask]
    provenance = {
        "face_index": 1000000, "source_ref": "office_streetview_2019",
        "source": "Directly photographed two-storey polygonal bay versus ground-height sourceface4",
        "source_roof_sha256": p["roof_evidence"]["source_sha256"],
        "all_original_source_faces": records, "overlaid_source_face_id": 4,
        "affected_columns": int(mask.sum()), "polygon_uv_m": bay["polygon_uv_m"],
        "eave_navd88_m": bay["cap_eave_navd88_m"], "inner_navd88_m": bay["cap_inner_navd88_m"],
        "plan_rule": "Bay polygon intersected with the exact original source footprint and only sourceface4",
        "geometry_status": "Photo-authored bay cap estimate; affected old ground heights are superseded, not claimed exposed or unchanged.",
        "unchanged_roof_rule": "All other source cells, including faces16/7 and every higher main roof, retain their original heights.",
    }
    return replace(r, heights=heights, face_indices=indices, gradient_x=gx, gradient_z=gz,
                   authored_roof_patches=(*r.authored_roof_patches, provenance))


def _body(f):
    return f.r.footprint_mask & (f.r.heights > f.g["entrance_floor_navd88_m"]+.5)


def _west_wall(f, p):
    """The photograph shows a planar rendered wall behind the roof eave."""
    at = f.g["main_west_wall_u_m"]
    v0, v1 = f.g["main_west_wall_v_limits_m"]
    old = f.local_mask((.75, v0, at+.7, v1))
    low, high = f.height_y(f.g["entrance_floor_navd88_m"])+64, f.height_y(59.0)+64
    facade = (f.c.roles[low:high] == ROLES.index("facade")) & old[None]
    f.c.data[low:high][facade] = 0
    f.c.roles[low:high][facade] = 0
    wall = f.local_mask((at, v0, at+.7, v1)) & _body(f)
    for x, z, iz, ix in f.each_column(wall):
        top = math.floor((f.r.heights[iz, ix]+f.offset)*f.c.scale)
        for y in range(f.height_y(f.g["entrance_floor_navd88_m"]), top):
            if f.c.roles[y+64, iz, ix] != ROLES.index("roof"):
                f.c.set(x, y, z, p["materials"]["facade"], "facade")
    f.features["photo_planar_main_west_wall_columns"] = int(wall.sum())


def _bay_walls(f, p):
    mask = _bay_mask(f, p)
    edge = mask & ~binary_erosion(mask)
    floor = f.height_y(f.g["entrance_floor_navd88_m"])
    for x, z, iz, ix in f.each_column(mask):
        top = math.floor((f.r.heights[iz, ix]+f.offset)*f.c.scale-.5)
        for y in range(floor, top):
            if edge[iz, ix] and f.u[iz, ix] < 1.65:
                f.c.set(x, y, z, p["materials"]["facade"], "facade")
            elif f.c.roles[y+64, iz, ix] == ROLES.index("facade"):
                f.c.set(x, y, z, "air", "air")
    f.features["photo_two_storey_polygonal_bay"] = 1


def _west_eaves(f):
    # One pass, only along the photographed west return. No duplicate pass
    # may descend into roof backing, and no low appendage is deleted.
    body = _body(f)
    edge = body & ~binary_erosion(body)
    chosen = edge & f.local_mask((.1, 3.6, 2.7, 20.5))
    for x, z, iz, ix in f.each_column(chosen):
        cells = np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("roof"))
        if not len(cells):
            continue
        y = int(cells[-1])+f.c.y_min
        old = f.c.palette[f.c.get(x, y, z)]
        block = "quartz_stairs" if old["Name"].endswith("_stairs") else "quartz_slab" if old["Name"].endswith("_slab") else "quartz_block"
        f.c.set(x, y, z, block, "trim", old.get("Properties") if block != "quartz_block" else None)
        f.c.set(x, y-1, z, f.p["materials"]["facade"], "facade")
        f.features["observed_west_eave_columns_with_solid_backing"] += 1


def _exterior_floor_rims(f, p):
    """Continue the rendered field over exposed structural floor ends."""
    body = _body(f)
    edge = body & ~binary_erosion(body)
    for x, z, iz, ix in f.each_column(edge):
        for iy in np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("floor")):
            f.c.set(x, int(iy)+f.c.y_min, z, p["materials"]["facade"], "facade")
            f.features["exposed_floor_ends_finished_as_render"] += 1


def _opening(f, name, center_uv, outward_uv, sill, width, height, green=False):
    """Cut one actual wall skin and record this aperture's allowed returns."""
    out = np.array(outward_uv, dtype=float)
    out /= np.linalg.norm(out)
    tangent = np.array([-out[1], out[0]])
    du, dv = f.u-center_uv[0], f.v-center_uv[1]
    along = du*tangent[0]+dv*tangent[1]
    depth = du*out[0]+dv*out[1]
    mid = math.floor((sill+height/2+f.offset)*f.c.scale)
    skin = np.isin(f.c.roles[mid+64], [ROLES.index("facade"), ROLES.index("trim")])
    wall = _body(f) & skin & (abs(along) <= width/2) & (depth >= -.7) & (depth <= .25)
    normal_world = out[0]*f.t+out[1]*f.n
    axis = int(abs(normal_world[1]) > abs(normal_world[0]))
    sign = 1 if normal_world[axis] >= 0 else -1
    inward = (-sign, 0) if axis == 0 else (0, -sign)
    columns = {}
    for x, z, iz, ix in f.each_column(wall):
        key = z if axis == 0 else x
        coord = x if axis == 0 else z
        old = columns.get(key)
        if old is None or sign*coord > sign*(old[0] if axis == 0 else old[1]):
            columns[key] = (x, z)
    columns = [columns[k] for k in sorted(columns)]
    if not columns:
        raise ValueError(f"No actual wall skin for Office opening {name} at {center_uv}")
    low = math.ceil((sill+f.offset)*f.c.scale-.5)
    high = math.ceil((sill+height+f.offset)*f.c.scale-.5)
    allowed = set()
    body = _body(f)
    cap = f.p["materials"]["green_driphood"] if green else "quartz_slab"
    for x, z in columns:
        for y in range(low, high):
            f.c.set(x, y, z, f.p["materials"]["glass"], "window", PANE_PROPS)
            allowed.add((x, y, z))
            xx, zz = x+inward[0], z+inward[1]
            if body[zz-f.c.z_min, xx-f.c.x_min]:
                if f.c.roles[y+64, zz-f.c.z_min, xx-f.c.x_min] == ROLES.index("facade"):
                    f.c.set(xx, y, zz, "air", "air")
                allowed.add((xx, y, zz))
        f.c.set(x, low-1, z, "quartz_slab", "trim", TOP)
        old = f.c.palette[f.c.get(x, high, z)]
        role = ROLES[int(f.c.roles[high+64, z-f.c.z_min, x-f.c.x_min])]
        if name.startswith("bay-") and role in ("roof", "trim") and old["Name"] != "minecraft:air":
            # The upper bay caps are clipped by the supplied photograph.
            # Keep an intersecting authored cornice whole rather than cutting
            # its upper half away to force a separate green hood below it.
            f.features["upper_bay_heads_integrated_with_backed_cornice"] += 1
        else:
            f.c.set(x, high, z, cap, "roof" if green else "trim", BOTTOM)
    for a, b in zip(columns, columns[1:]):
        if abs(a[0]-b[0]) == 1 and abs(a[1]-b[1]) == 1:
            for x, z in ((a[0], b[1]), (b[0], a[1])):
                if body[z-f.c.z_min, x-f.c.x_min]:
                    allowed.update((x, y, z) for y in range(low, high))
    f.office_apertures.append((name, allowed, inward, cap))
    f.features["individually_observed_window_groups"] += 1
    f.features["small_green_driphood_groups"] += int(green)


def _finish_openings(f):
    for name, allowed, inward, cap in f.office_apertures:
        for _ in range(3):
            a = close_diagonal_pane_corners(f.c, allowed, inward=inward)
            b = bridge_frame_edges(f.c, allowed, inward=inward)
            b += close_diagonal_pane_jambs(f.c, allowed, inward=inward)
            f.features["authorised_corner_return_panes"] += a
            f.features["authorised_frame_return_panes"] += b
            if not a and not b:
                break
    body = _body(f)
    backed = set()
    for name, allowed, inward, cap in f.office_apertures:
        for x, y, z in sorted(allowed):
            if not f.c.palette[f.c.get(x, y, z)]["Name"].endswith("_pane"):
                continue
            for dy, props in ((-1, TOP), (1, BOTTOM)):
                at = (x, y+dy, z)
                state = f.c.palette[f.c.get(*at)]
                wrong = state["Name"].endswith("_slab") and state.get("Properties", {}).get("type") not in (props["type"], "double")
                if state["Name"] == "minecraft:air" or wrong:
                    block = "quartz_slab" if dy < 0 else cap
                    f.c.set(*at, block, "trim" if block == "quartz_slab" else "roof", props)
                    f.features["contacting_window_cap_repairs"] += 1
                if not f.c.palette[f.c.get(*at)]["Name"].endswith("_slab") or (at, inward) in backed:
                    continue
                backed.add((at, inward))
                for depth in (1, 2, 3):
                    xx, zz = x+inward[0]*depth, z+inward[1]*depth
                    if not body[zz-f.c.z_min, xx-f.c.x_min]:
                        raise ValueError(f"Office window cap backing outside body: {name}, {at}")
                    state = f.c.palette[f.c.get(xx, y+dy, zz)]
                    if state["Name"] == "minecraft:air":
                        f.c.set(xx, y+dy, zz, f.p["materials"]["facade"], "facade")
                        f.features["concealed_full_window_cap_backing_cells"] += 1
                        break
                    if state["Name"].endswith(("_slab", "_stairs", "_pane", "_fence", "_door", "_trapdoor")):
                        continue
                    break
                else:
                    raise ValueError(f"Office cap has no full backing: {name}, {at}")
    connect_window_panes(f.c)
    checked = 0
    ids = [i for i, s in enumerate(f.c.palette) if s["Name"].endswith("_pane")]
    for iy, iz, ix in np.argwhere(np.isin(f.c.data, ids)):
        x, y, z = int(ix)+f.c.x_min, int(iy)+f.c.y_min, int(iz)+f.c.z_min
        state = f.c.palette[f.c.get(x, y, z)]
        if sum(state.get("Properties", {}).get(d) == "true" for d in ("east", "west", "north", "south")) < 2:
            raise ValueError(f"Office free horizontal sash endpoint at {(x, y, z)}")
        for dy, need in ((-1, "top"), (1, "bottom")):
            state = f.c.palette[f.c.get(x, y+dy, z)]
            if state["Name"] == "minecraft:air" or (state["Name"].endswith("_slab") and state.get("Properties", {}).get("type") not in (need, "double")):
                raise ValueError(f"Office open vertical sash contact at {(x, y, z)}")
        checked += 1
    f.features["pane_perimeters_checked_without_gaps"] = checked
    f.features["half_slab_cap_backings_checked"] = len(backed)


def _bay_corner_jambs(f, p):
    """Retain the photographed stucco corner between separate bay sashes.

    On this narrow measured bay, the front and south cheek raster openings
    remove the same inboard corner cell. Restore that shared wall pier, not
    a projecting white surround or glass across the photographed stucco.
    """
    bay = _bay_mask(f, p)
    columns = set()
    for level in ("lower", "upper"):
        groups = []
        for name, allowed, inward, cap in f.office_apertures:
            if name.startswith("bay-facet") and name.endswith(level):
                groups.append({q for q in allowed if f.c.palette[f.c.get(*q)]["Name"].endswith("_pane")})
        for left, right in zip(groups, groups[1:]):
            for x, y, z in left:
                for dx in (-1, 1):
                    for dz in (-1, 1):
                        if (x+dx, y, z+dz) not in right:
                            continue
                        corners = ((x+dx, z), (x, z+dz))
                        if any(f.c.get(xx, y, zz) for xx, zz in corners):
                            continue
                        inside = [(xx, zz) for xx, zz in corners
                                  if bay[zz-f.c.z_min, xx-f.c.x_min]]
                        if inside:
                            columns.add(max(inside, key=lambda q: f.u[q[1]-f.c.z_min, q[0]-f.c.x_min]))
    floor = f.height_y(f.g["entrance_floor_navd88_m"])
    for x, z in columns:
        iz, ix = z-f.c.z_min, x-f.c.x_min
        top = math.floor((f.r.heights[iz, ix]+f.offset)*f.c.scale)
        for y in range(floor, top):
            role = ROLES[int(f.c.roles[y+64, iz, ix])]
            if role not in ("roof", "window"):
                f.c.set(x, y, z, p["materials"]["facade"], "facade")
    f.features["photographed_bay_stucco_corner_columns_retained"] = len(columns)


def _terrace(f, p):
    top = f.height_y(p["terrace"]["rail_top_navd88_m"])
    roof_mask = f.r.footprint_mask & (f.r.face_indices == 16)
    supports = list(f.each_column(roof_mask))
    done, ordered = set(), []
    max_snap = 0.0
    for a, b in p["terrace"]["rail_segments_uv_m"]:
        a, b = np.array(a), np.array(b)
        path = []
        for t in np.linspace(0, 1, math.ceil(np.linalg.norm(b-a)/.22)+1):
            uv = a+(b-a)*t
            x, z = np.floor(f.world(*uv)*f.c.scale).astype(int)
            iz, ix = z-f.c.z_min, x-f.c.x_min
            if not roof_mask[iz, ix]:
                # The low roof begins diagonally across the voxel grid.
                # Snap the intended rail to its nearest actual support rather
                # than dropping the corner and leaving two disconnected runs.
                x, z, iz, ix = min(supports, key=lambda q:
                    (f.u[q[2], q[3]]-uv[0])**2 + (f.v[q[2], q[3]]-uv[1])**2)
                distance = float(np.hypot(f.u[iz, ix]-uv[0], f.v[iz, ix]-uv[1]))
                if distance > .65:
                    raise ValueError(f"Office terrace path exceeds bounded roof snap: {uv}")
                max_snap = max(max_snap, distance)
            q = (int(x), int(z))
            if not path or path[-1] != q:
                path.append(q)
        for a, b in zip(path, path[1:]):
            if abs(a[0]-b[0]) == 1 and abs(a[1]-b[1]) == 1:
                corners = [(a[0], b[1]), (b[0], a[1])]
                corners = [q for q in corners if roof_mask[q[1]-f.c.z_min, q[0]-f.c.x_min]]
                if not corners:
                    raise ValueError(f"Office terrace corner has no retained roof support: {a}, {b}")
                ordered.append(max(corners, key=lambda q: f.u[q[1]-f.c.z_min, q[0]-f.c.x_min]))
            elif abs(a[0]-b[0])+abs(a[1]-b[1]) > 1:
                raise ValueError(f"Office terrace path jumps over a roof cell: {a}, {b}")
        ordered.extend(path)
    for x, z in ordered:
        if (x, z) in done:
            continue
        done.add((x, z))
        iz, ix = z-f.c.z_min, x-f.c.x_min
        roof = np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("roof"))
        if not len(roof):
            raise ValueError(f"Office terrace post has no measured roof support at {(x, z)}")
        base_y = int(roof[-1])+f.c.y_min
        base = f.c.palette[f.c.get(x, base_y, z)]
        if base["Name"].endswith("_slab") and base.get("Properties", {}).get("type") == "bottom":
            # Use the retained dark roof family for the small local support;
            # a full white foot read as an invented heavy balcony pedestal.
            f.c.set(x, base_y, z, p["materials"]["terrace_foot"], "roof",
                    {"type": "double", "waterlogged": "false"})
            f.features["terrace_quarter_metre_post_foot_overlays"] += 1
        low = base_y+1
        for y in range(low, top):
            f.c.set(x, y, z, p["materials"]["terrace_rail"], "railing" if y == top-1 else "trim", POST)
    f.features["observed_north_terrace_railing_columns"] = len(done)
    f.features["terrace_maximum_support_snap_m"] = max_snap
    f.features["north_low_source_face16_preserved"] = 1


def build_details(f, p):
    f.office_apertures = []
    f.floor_plate(f.g["upper_floor_navd88_m"])
    f.floor_plate(f.g["attic_floor_navd88_m"])
    _west_wall(f, p)
    _bay_walls(f, p)
    _west_eaves(f)
    _exterior_floor_rims(f, p)
    _terrace(f, p)
    for row in p["openings"]:
        for center in row["centres_m"]:
            _opening(f, row["id"], (row["at_m"], center), (-1, 0),
                     row["sill_navd88_m"], row["width_m"], row["height_m"], row["green_cap"])
    polygon = np.array(p["bay"]["polygon_uv_m"])
    for facet, (a, b) in enumerate(zip(polygon[1:4], polygon[2:5])):
        tangent = b-a
        out = np.array([-tangent[1], tangent[0]])
        for row in p["bay"]["sash_levels"]:
            _opening(f, f"bay-facet{facet}-{row['id']}", (a+b)/2, out,
                     row["sill_navd88_m"], 1.05 if facet == 1 else .65,
                     row["height_m"], True)
    _bay_corner_jambs(f, p)
    _finish_openings(f)
    f.features["unphotographed_mirrored_window_rows"] = 0
    f.features["unphotographed_door_positions_invented"] = 0
    f.features["original_ordered_roof_faces_in_provenance"] = 20
    f.features["native_geometry_and_material_review_pending"] = 1
