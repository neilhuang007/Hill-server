"""Current 1925 Meigs Admission House, individually interpreted from school photos.

Coordinates are local metres and NAVD88 metres. Original roof faces are retained
except explicit porch corrections and a separately documented small dormer.
Unknown elevations do not receive mirrored or procedurally repeated windows.
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
from scipy.ndimage import binary_erosion
from shapely import distance, points

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building
from campus_window_frames import bridge_frame_edges, close_diagonal_pane_corners


BOTTOM = {"type": "bottom", "waterlogged": "false"}
TOP = {"type": "top", "waterlogged": "false"}
ISOLATED_POST = {d: "false" for d in ("east", "west", "north", "south")}
ISOLATED_POST["waterlogged"] = "false"


def _surface(r, f, mask, levels, record):
    heights, faces = r.heights.copy(), r.face_indices.copy()
    gx, gz = r.gradient_x.copy(), r.gradient_z.copy()
    dz, dx = np.gradient(levels, r.resolution)
    face_id = 1_000_000 + len(r.authored_roof_patches)
    heights[mask], faces[mask] = levels[mask], face_id
    gx[mask], gz[mask] = dx[mask], dz[mask]
    return replace(
        r, heights=heights, face_indices=faces, gradient_x=gx, gradient_z=gz,
        missing_mask=r.missing_mask & ~mask,
        authored_roof_patches=(*r.authored_roof_patches, {
            **record, "face_index": face_id, "affected_columns": int(mask.sum()),
            "origin_xz_m": f.origin.tolist(), "axis_degrees": f.g["axis_degrees"],
            "plan_rule": "clipped to the original measured footprint",
        }),
    )


def prepare_roof(r, f, p):
    """Use reliable measured planes; normalise only the evidenced porch strip."""
    measured = load_measured_building(parent_id=p["parent_id"])
    sources = []
    for i, face in enumerate(measured.roof_faces):
        saved = p["roof_evidence"]["all_original_faces"][i]
        sources.append({
            **saved, "part_id": face.part_id, "surface_index": face.surface_index,
            "disposition": (
                "replaced by shallow continuous photographed north/west porch"
                if i in p["porch"]["source_ids"] else
                "north stripV<=4.3m replaced for photographed porch continuity; eastern remainder unchanged/unresolved"
                if i == 2 else
                "original main plane retained except the explicitly authored smaller-dormer overlay"
                if i == 16 else
                "unchanged unresolved low eastern fragment; not a photographed roof claim"
                if i in (2, 3) else "retained original measured plane"
            ),
        })
    mask = r.footprint_mask & (
        np.isin(r.face_indices, p["porch"]["source_ids"])
        | ((r.face_indices == 2) & (f.v <= 4.3))
    )
    # The measured north perimeter steps from V0 to V2.5m. One global V0
    # slope flattened the narrower eastern porch and raised its fascia.
    # Normalise against the actual exterior outline and interpreted inner
    # wall instead, keeping the photographed outer fascia level throughout.
    world_x = f.origin[0] + f.u*f.t[0] + f.v*f.n[0]
    world_z = f.origin[1] + f.u*f.t[1] + f.v*f.n[1]
    outside_distance = distance(points(world_x,world_z),measured.footprint.boundary)
    north_distance = np.hypot(np.maximum(2.6-f.u,np.maximum(f.u-18.05,0)),f.v-3.8)
    west_distance = np.hypot(f.u-2.6,np.maximum(3.8-f.v,np.maximum(f.v-7.7,0)))
    inside_distance = np.minimum(north_distance,west_distance)
    amount = outside_distance/np.maximum(outside_distance+inside_distance,.001)
    amount = np.where((f.u>=2.6)&(f.v>=3.8),1,amount)
    outside_edge = mask & ~binary_erosion(r.footprint_mask)
    amount[outside_edge] = 0
    g = p["geometry"]
    levels = g["porch_eave_navd88_m"] + amount * (
        g["porch_inner_navd88_m"] - g["porch_eave_navd88_m"]
    )
    r = _surface(r, f, mask, levels, {
        "source": "School campaign photograph and measured lower north/west roof masks",
        "source_ref": "meigs_campaign_2024", "source_roof_sha256": p["roof_evidence"]["source_sha256"],
        "replaced_source_face_ids": p["porch"]["source_ids"], "all_original_source_faces": sources,
        "partially_replaced_source_faces": [{"face_id":2,"section":"V<=4.3m north strip"}],
        "measured_footprint_area_m2": measured.footprint.area,
        "reason": "The photographed continuous shallow porch contradicts source6/19 near-ground sloping fragments;20 supplies an approximately71m porch-height control.7 and the north part of2 continue that strip. Schooldrone238 shows the cover continuing across the north frontage, contradicting the near-ground north end of2; its eastern remainder remains unresolved.",
        "uncertainty": "Height and slope are photo interpretations, not replacement survey measurements.",
        "v2_native_correction": "Same193-column mask; level exterior fascia and shallow rise normalised from the exact stepped outer perimeter toward the interpreted north/west wall. V1 incorrectly usedV0 for the entire north eave.",
    })
    d = p["small_dormer"]
    u0, v0, u1, v1 = d["bounds_uv_m"]
    levels = d["eave_navd88_m"] + (
        d["ridge_navd88_m"] - d["eave_navd88_m"]
    ) * (1 - abs(f.u - (u0 + u1) / 2) / ((u1 - u0) / 2))
    mask = r.footprint_mask & f.local_mask(d["bounds_uv_m"]) & (levels > r.heights)
    r = _surface(r, f, mask, levels, {
        "source": "Smaller western north-facing dormer visible in official school drone238 and partly in campaign photo",
        "source_ref": "school_drone238", "underlying_source_face_ids": [16],
        "bounds_uv_m": d["bounds_uv_m"], "ridge_navd88_m": d["ridge_navd88_m"],
        "eave_navd88_m": d["eave_navd88_m"],
        "geometry_status": "photo-interpreted authored gable; existing large measured dormer1/5 unchanged",
    })
    return r


def _body(f):
    return f.r.footprint_mask & (f.r.heights > f.g["main_roof_threshold_navd88_m"])


def _opening(f, row, center, body):
    """One outer pane sheet with bounded cut and explicitly authorised turns."""
    side, at = row["side"], row["at_m"]
    along, normal = (f.v, f.u) if side in ("east", "west") else (f.u, f.v)
    sign = 1 if side in ("east", "south") else -1
    depth = (normal - at) * sign
    span = abs(along - center) <= row["width_m"] / 2
    mid = math.floor((row["sill_navd88_m"] + row["height_m"]/2 + f.offset) * f.c.scale)
    actual_wall = np.isin(f.c.roles[mid+64], [ROLES.index("facade"), ROLES.index("trim")])
    mask = body & actual_wall & span & (depth >= -.65) & (depth <= .2)
    # Only clear through the existing exterior wall skin. A deeper generic
    # reveal can cut the perpendicular wall at a rasterised corner.
    columns = {}
    for x, z, iz, ix in f.each_column(mask):
        key = z if side in ("east", "west") else x
        candidate = columns.get(key)
        normal_coordinate = x if side in ("east", "west") else z
        previous_coordinate = (candidate[0] if side in ("east", "west") else candidate[1]) if candidate else 0
        if candidate is None or sign * normal_coordinate > sign * previous_coordinate:
            columns[key] = (x, z)
    columns = [columns[k] for k in sorted(columns)]
    if not columns:
        raise ValueError(f"No measured wall cells for {row['id']} at {center}")
    sill, height = row["sill_navd88_m"], row["height_m"]
    low = math.ceil((sill + f.offset) * f.c.scale - .5)
    high = math.ceil((sill + height + f.offset) * f.c.scale - .5)
    inward = {"north": (0, 1), "south": (0, -1), "west": (1, 0), "east": (-1, 0)}[side]
    allowed = set()
    for x, z in columns:
        for y in range(low, high):
            f.c.set(x, y, z, f.p["materials"]["glass"], "window", PANE_PROPS)
            allowed.add((x, y, z))
            xx, zz = x + inward[0], z + inward[1]
            if body[zz - f.c.z_min, xx - f.c.x_min]:
                # Clear one backing cell only if the shell made that cell a
                # facade. The outer cell remains the sole main pane plane.
                if f.c.roles[y + 64, zz - f.c.z_min, xx - f.c.x_min] == ROLES.index("facade"):
                    f.c.set(xx, y, zz, "air", "air")
                allowed.add((xx, y, zz))
        f.c.set(x, low - 1, z, "quartz_slab", "trim", TOP)
        f.c.set(x, high, z, "quartz_slab", "trim", BOTTOM)
    for aa, bb in zip(columns, columns[1:]):
        if abs(aa[0] - bb[0]) == 1 and abs(aa[1] - bb[1]) == 1:
            for x, z in ((aa[0], bb[1]), (bb[0], aa[1])):
                if body[z - f.c.z_min, x - f.c.x_min]:
                    allowed.update((x, y, z) for y in range(low, high))
    f.meigs_apertures.append((row["id"], allowed, inward))
    f.features["individually_observed_window_groups"] += 1


def _finish_glazing(f):
    """Close both pane graph and physical aperture perimeter, not just support."""
    for _, allowed, inward in f.meigs_apertures:
        # A frame return can itself finish on a raster turn. Resolve those
        # newly created endpoints within the same bounded aperture only.
        for _ in range(3):
            corner = close_diagonal_pane_corners(f.c, allowed, inward=inward)
            returned = bridge_frame_edges(f.c, allowed, inward=inward)
            f.features["authorised_diagonal_corner_panes"] += corner
            f.features["authorised_frame_return_panes"] += returned
            if not corner and not returned:
                break
    pane_ids = [i for i, s in enumerate(f.c.palette) if s["Name"].endswith("_pane")]
    for iy, iz, ix in np.argwhere(np.isin(f.c.data, pane_ids)):
        x, y, z = int(ix) + f.c.x_min, int(iy) + f.c.y_min, int(iz) + f.c.z_min
        for dy, props in ((-1, TOP), (1, BOTTOM)):
            state = f.c.palette[f.c.get(x, y + dy, z)]
            wrong_slab = state["Name"].endswith("_slab") and state.get("Properties", {}).get("type") not in {props["type"], "double"}
            if state["Name"] == "minecraft:air" or wrong_slab:
                f.c.set(x, y + dy, z, "quartz_slab", "trim", props)
                f.features["contacting_window_head_sill_repairs"] += 1
    # A contacting half-slab alone is not a closed wall: its unused half
    # would leave a daylight slit against the next full masonry course.
    # Close that void from inside, keeping the outer sill/head visibly thin.
    body = _body(f)
    for name,allowed,inward in f.meigs_apertures:
        backing = "quartz_block" if "dormer" in name else f.p["materials"]["facade"]
        for x,y,z in allowed:
            if not f.c.palette[f.c.get(x,y,z)]["Name"].endswith("_pane"):
                continue
            for dy in (-1,1):
                cap = f.c.palette[f.c.get(x,y+dy,z)]
                if not cap["Name"].endswith("_slab"):
                    continue
                xx,zz=x+inward[0],z+inward[1]
                if not body[zz-f.c.z_min,xx-f.c.x_min]:
                    raise ValueError(f"Head/sill backing outside Meigs body at {(xx,y+dy,zz)}")
                state = f.c.palette[f.c.get(xx,y+dy,zz)]
                if state["Name"] == "minecraft:air" or state["Name"].endswith("_slab"):
                    f.c.set(xx,y+dy,zz,backing,"facade")
                    f.features["closed_head_sill_backing_cells"] += 1
    connect_window_panes(f.c)
    pane_ids = [i for i, s in enumerate(f.c.palette) if s["Name"].endswith("_pane")]
    checked = 0
    for iy, iz, ix in np.argwhere(np.isin(f.c.data, pane_ids)):
        x, y, z = int(ix) + f.c.x_min, int(iy) + f.c.y_min, int(iz) + f.c.z_min
        state = f.c.palette[f.c.get(x, y, z)]
        if sum(state.get("Properties", {}).get(d) == "true" for d in ("east", "west", "north", "south")) < 2:
            raise ValueError(f"Meigs unclosed horizontal pane endpoint at {(x, y, z)}")
        for dy, need in ((-1, "top"), (1, "bottom")):
            state = f.c.palette[f.c.get(x, y + dy, z)]
            if state["Name"] == "minecraft:air" or (state["Name"].endswith("_slab") and state.get("Properties", {}).get("type") not in {need, "double"}):
                raise ValueError(f"Meigs unclosed physical pane edge at {(x, y, z)}")
        checked += 1
    f.features["pane_perimeters_checked_without_gaps"] = checked


def _porch_mask(f):
    return f.r.face_indices == 1_000_000


def _porch(f, p):
    floor = f.g["entrance_floor_navd88_m"]
    mask = _porch_mask(f)
    # Fascia belongs at the outside eave, not the boundary against the wall.
    # Colouring both edges made narrow north roof strips entirely white.
    edge = mask & ~binary_erosion(f.r.footprint_mask)
    # The source roof overhang is ahead of the photo-interpreted wall plane.
    # A narrow cover return closes that interval below the untouched main
    # roof; it does not change the857 retained highest roof controls.
    inner_return = f.local_mask((3.3,2.9,18.05,f.g["north_wall_v_m"])) & f.r.footprint_mask & ~mask
    cover = mask | inner_return
    levels = np.where(mask,f.r.heights,f.g["porch_inner_navd88_m"])
    # The shell establishes foundations and floor; remove its enclosing walls
    # and backing throughout the open porch, then place one thin roof skin.
    for x, z, iz, ix in f.each_column(cover):
        half = round((levels[iz, ix] + f.offset) * f.c.scale * 2)
        y = (half - 1) // 2
        props = TOP if half % 2 == 0 else BOTTOM
        for yy in range(f.height_y(floor), y + 1):
            f.c.set(x, yy, z, "air", "air")
        f.c.set(x, y, z, "quartz_slab" if edge[iz, ix] else p["materials"]["roof_family"] + "_slab",
                "trim" if edge[iz, ix] else "roof", props)
        f.features["open_porch_single_slab_roof_columns"] += 1
    f.features["porch_inner_cover_return_below_retained_main_roof"] = int(inner_return.sum())
    f.meigs_porch_cover = cover
    f.meigs_porch_levels = levels
    _join_porch_skin_steps(f,p,cover,levels)
    for u, v in p["porch"]["posts_uv_m"]:
        candidates = [(x, z, iz, ix) for x, z, iz, ix in f.each_column(mask & f.local_mask((u-.5, v-.5, u+.5, v+.5)))]
        if not candidates:
            continue
        x, z, iz, ix = min(candidates, key=lambda q: (f.u[q[2], q[3]]-u)**2+(f.v[q[2], q[3]]-v)**2)
        roof_y = (round((f.r.heights[iz, ix] + f.offset) * f.c.scale * 2)-1)//2
        for y in range(f.height_y(floor), roof_y):
            f.c.set(x, y, z, p["materials"]["porch_post"], "trim", ISOLATED_POST)
        # The roof slab itself is the shallow capital. Where it is upper-half,
        # a stair's lower body makes physical contact with the shaft below,
        # retaining the same roof top instead of leaving a quarter-metre slit.
        roof_state = f.c.palette[f.c.get(x,roof_y,z)]
        if roof_state.get("Properties",{}).get("type") == "top":
            f.c.set(x,roof_y,z,"quartz_stairs","trim",{
                "half":"bottom","facing":"south","shape":"inner_left","waterlogged":"false"
            })
        else:
            f.c.set(x,roof_y,z,"quartz_slab","trim",BOTTOM)
        f.features["pale_narrow_porch_posts"] += 1
    for rail in p["porch"]["rails"]:
        a, b = rail["ends_m"]
        for along in np.arange(a, b+.01, .24):
            point = f.world(rail["at_m"], along) if rail["side"] == "west" else f.world(along, rail["at_m"])
            x, z = np.floor(point*f.c.scale).astype(int)
            iz, ix = z-f.c.z_min, x-f.c.x_min
            if not mask[iz, ix]:
                continue
            for y in range(f.height_y(floor), f.height_y(floor+1)):
                if f.c.roles[y+64, iz, ix] != ROLES.index("trim"):
                    role = "trim" if y == f.height_y(floor) else "railing"
                    f.c.set(int(x), y, int(z), p["materials"]["railing"], role, ISOLATED_POST)
        f.features["photo_pale_balustrade_runs"] += 1


def _join_porch_skin_steps(f,p,cover,levels):
    """Give adjacent quarter-grid roof courses actual overlapping contact."""
    halves=np.rint((levels+f.offset)*f.c.scale*2).astype(int)
    for x,z,iz,ix in f.each_column(cover):
        current=int(halves[iz,ix])
        lower=[(int(halves[iz+dz,ix+dx]),dx,dz) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))
               if cover[iz+dz,ix+dx] and halves[iz+dz,ix+dx]<current]
        if not lower:
            continue
        lowest,dx,dz=min(lower)
        y=(current-1)//2
        state=f.c.palette[f.c.get(x,y,z)]
        family="quartz" if state["Name"].startswith("minecraft:quartz") else p["materials"]["roof_family"]
        role="trim" if family=="quartz" else "roof"
        if current%2==0 and current-lowest==1:
            # A stair's lower body laps onto the lower neighbour. Its upper
            # half remains uphill at exactly the previous roof surface.
            facing={(1,0):"west",(-1,0):"east",(0,1):"north",(0,-1):"south"}[(dx,dz)]
            f.c.set(x,y,z,family+"_stairs",role,{"facing":facing,"half":"bottom","shape":"straight","waterlogged":"false"})
            f.features["porch_quarter_step_stair_laps"]+=1
        else:
            # A lower slab above an integer boundary needs an upper slab
            # immediately below; complete only the missing quarter courses.
            for half in range(lowest-1,current-1):
                yy=half//2;old=f.c.palette[f.c.get(x,yy,z)]
                if old["Name"]=="minecraft:air":
                    f.c.set(x,yy,z,family+"_slab",role,TOP if half%2 else BOTTOM)
                    f.features["porch_concealed_quarter_course_laps"]+=1
                elif old["Name"].endswith("_slab") and old.get("Properties",{}).get("type") != ("top" if half%2 else "bottom"):
                    full="quartz_block" if family=="quartz" else family+"_planks"
                    f.c.set(x,yy,z,full,role)
                    f.features["porch_concealed_quarter_course_laps"]+=1


def _physical_top(f, mask, navd):
    half = round((navd + f.offset) * f.c.scale * 2)
    solid, fractional = divmod(half, 2)
    for x, z, _, _ in f.each_column(mask):
        for y in range(min(f.c.ground_at(x, z), solid)-1, solid):
            f.c.set(x, y, z, "smooth_stone", "pavement")
        if fractional:
            f.c.set(x, solid, z, "smooth_stone_slab", "pavement", BOTTOM)


def _entrance(f, p, body):
    porch = p["porch"]
    floor = f.g["entrance_floor_navd88_m"]
    u, v = porch["entry_door_uv_m"]
    # A partial photo edge suggests this covered access. Its precise door
    # position is an explicit functional interpretation, not a measured door.
    selected = body & f.local_mask((u-.6, v-porch["entry_width_m"]/2, u+.55, v+porch["entry_width_m"]/2))
    columns = {}
    for x, z, iz, ix in f.each_column(selected):
        if z not in columns or x < columns[z][0]:
            columns[z] = (x, z)
    low, high = f.height_y(floor), f.height_y(floor+2.25)
    props = {"facing":"east", "half":"bottom", "open":"true", "powered":"false", "waterlogged":"false"}
    for x, z in columns.values():
        for y in range(low, high):
            f.c.set(x, y, z, "pale_oak_trapdoor", "trim", props)
        f.c.set(x, high, z, "quartz_slab", "trim", BOTTOM)
    if columns:
        x, z = min(columns.values(), key=lambda q: abs(f.v[q[1]-f.c.z_min, q[0]-f.c.x_min]-v))
        for half, dy in (("lower",0),("upper",1)):
            f.c.set(x, low+dy, z, "pale_oak_door", "door", {"facing":"east", "half":half, "hinge":"left", "open":"false", "powered":"false"})
        f.features["partly_observed_interpreted_operable_entry"] = 1
    u0, v0, u1, v1 = porch["stair_bounds_uv_m"]
    n = porch["stair_risers"]
    for step in range(n):
        a, b = u0+(u1-u0)*step/n, u0+(u1-u0)*(step+1)/n
        level = floor - (n-step)*porch["stair_rise_m"]
        _physical_top(f, f.local_mask((a,v0,b,v1)), level)
        f.features["graded_quarter_metre_entry_treads"] += 1
    for v in (v0+.1, v1-.1):
        for u in np.arange(u0+.1, u1-.05, .3):
            level = floor - max(1, math.ceil((u1-u)/(u1-u0)*n))*porch["stair_rise_m"]
            x, z = np.floor(f.world(u,v)*f.c.scale).astype(int)
            for y in range(f.height_y(level),f.height_y(level+1)):
                role = "trim" if y == f.height_y(level) else "railing"
                f.c.set(int(x), y, int(z), "pale_oak_fence", role, ISOLATED_POST)


def _dormer_faces(f, p):
    # The large gable remains the source1/5 roof; only visible light infill
    # receives pale paint above the main roof eave. No opaque window cage.
    front = f.g["north_wall_v_m"]
    old_skin = f.local_mask((8.1,3.05,12.1,front+.55))
    a,b = f.height_y(74.0)+64,f.height_y(78.7)+64
    changed = (f.c.roles[a:b] == ROLES.index("facade")) & old_skin[None]
    f.c.data[a:b][changed] = 0
    f.c.roles[a:b][changed] = 0
    # A0.7m raster envelope includes the single backing cell at the rotated
    # right-hand jamb; a0.5m band omitted that turn beside the roof footprint.
    face = f.local_mask((8.35,front,11.85,front+.7)) & f.r.footprint_mask
    for x,z,iz,ix in f.each_column(face):
        top = math.floor((f.r.heights[iz,ix]+f.offset)*f.c.scale-.5)
        for y in range(f.height_y(74.0),top):
            if f.c.roles[y+64,iz,ix] != ROLES.index("roof"):
                f.c.set(x,y,z,"quartz_block","facade")
    d = p["small_dormer"]
    u0,v0,u1,v1 = d["bounds_uv_m"]
    mask = f.local_mask((u0,v0,u1,v0+.6)) & (f.r.face_indices==1_000_001)
    for x,z,iz,ix in f.each_column(mask):
        top = math.floor((f.r.heights[iz,ix]+f.offset)*f.c.scale-.5)
        for y in range(f.height_y(d["front_base_navd88_m"]),top):
            f.c.set(x,y,z,"quartz_block","facade")
    for bounds in ((8.1,3.05,12.1,4.05),(u0,v0-.1,u1,v0+.5)):
        _main_roof_edge_trim(f,bounds)
    f.features["retained_measured_large_dormer"] = 1
    f.features["photo_interpreted_small_dormer"] = 1


def _main_roof_edge_trim(f,bounds):
    """Trim the measured main roof once, excluding the lower porch cover."""
    mask=f.local_mask(bounds) & _body(f)
    for x,z,iz,ix in f.each_column(mask):
        if (x,z) in f.meigs_trimmed_main_roof_columns:
            continue
        u,v=f.u[iz,ix],f.v[iz,ix]
        f.roof_edge_trim((u-.12,v-.12,u+.12,v+.12))
        f.meigs_trimmed_main_roof_columns.add((x,z))


def _observed_north_wall(f):
    """Use the photographed planar stucco wall behind the measured roof eave.

    Roofer polygons describe irregular roof overhangs, not individual window
    reveals. The north wall is photo-estimated0.3–0.6m behind those roof edges.
    This preserves the measured roof while avoiding metre-deep jagged sash.
    """
    at = f.g["north_wall_v_m"]
    region = f.local_mask((3.3,2.9,18.05,at+.55))
    a,b = f.height_y(68.0)+64,f.height_y(79.0)+64
    old = (f.c.roles[a:b] == ROLES.index("facade")) & region[None]
    f.c.data[a:b][old] = 0
    f.c.roles[a:b][old] = 0
    wall = f.local_mask((3.3,at,18.05,at+.7)) & f.r.footprint_mask
    for x,z,iz,ix in f.each_column(wall):
        top = math.floor((f.r.heights[iz,ix]+f.offset)*f.c.scale)
        for y in range(f.height_y(68.0),top):
            if f.c.roles[y+64,iz,ix] != ROLES.index("roof"):
                f.c.set(x,y,z,f.p["materials"]["facade"],"facade")
        f.features["photo_planar_north_wall_columns"] += 1


def _observed_north_soffit(f):
    """Thin the exterior overhang only where the inset wall seals behind it."""
    front=f.g["north_wall_v_m"]
    outside=f.local_mask((3.3,2.9,18.05,front)) & f.r.footprint_mask
    for x,z,iz,ix in f.each_column(outside):
        trim=np.flatnonzero((f.c.roles[:,iz,ix]==ROLES.index("trim")) &
                            (np.arange(f.c.data.shape[0])+f.c.y_min>=f.height_y(73.6)))
        if not len(trim):
            continue
        y=int(trim[-1])+f.c.y_min-1
        if f.c.palette[f.c.get(x,y,z)]["Name"] != "minecraft:white_terracotta":
            continue
        for depth in (1,2,3):
            zz=z+depth
            if f.v[zz-f.c.z_min,ix]<front:
                continue
            backing=f.c.palette[f.c.get(x,y,zz)]["Name"]
            if backing in ("minecraft:white_terracotta","minecraft:quartz_block"):
                f.c.set(x,y,z,"quartz_slab","trim",TOP)
                f.features["thin_exterior_soffit_with_full_inset_wall_backing"]+=1
            break


def _chimneys(f, p):
    for stack in p["chimneys"]:
        bounds, top = stack["bounds_uv_m"],stack["top_navd88_m"]
        mask = f.local_mask(bounds) & f.r.footprint_mask
        for x,z,iz,ix in f.each_column(mask):
            low = f.height_y(f.r.heights[iz,ix]) - 1
            high = f.height_y(top)
            for y in range(low,high):
                f.c.set(x,y,z,"mud_bricks","facade")
            f.c.set(x,high,z,"mud_brick_slab","trim",BOTTOM)
        f.features["photo_interpreted_warm_masonry_chimneys"] += 1


def build_details(f, p):
    body = _body(f)
    f.meigs_apertures = []
    f.meigs_trimmed_main_roof_columns = set()
    # Paint follows measured walls; floor plates remain inside the closed body
    # and cannot expose a contrasting timber floor rim on the stucco facade.
    f.floor_plate(f.g["upper_floor_navd88_m"])
    f.floor_plate(f.g["attic_floor_navd88_m"])
    _porch(f,p)
    _observed_north_wall(f)
    _dormer_faces(f,p)
    _chimneys(f,p)
    edge = body & ~binary_erosion(body)
    for x,z,iz,ix in f.each_column(edge):
        # The trim helper retains a solid backing block below the roof cap.
        u,v = f.u[iz,ix],f.v[iz,ix]
        if v<4.2 or u<3.4:
            _main_roof_edge_trim(f,(u-.12,v-.12,u+.12,v+.12))
    for row in p["openings"]:
        for center in row["centres_m"]:
            _opening(f,row,center,body)
    _entrance(f,p,body)
    # Judge backing after the openings exist: a future dormer pane must not
    # be mistaken for solid backing when thinning the exterior soffit.
    _observed_north_soffit(f)
    _finish_glazing(f)
    f.features["unphotographed_mirrored_window_rows"] = 0
    f.features["original_roof_faces_retained"] = len(p["roof_evidence"]["unchanged_source_ids"])
    f.features["native_material_and_geometry_review_pending"] = 1
