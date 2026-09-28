"""Individually photo-interpreted exterior of the numbered East Faculty Unit 3.

All design values are local metres / NAVD88 metres. Source roof masks are kept
in provenance, and the measured footprint clips authored occupied volumes.
Unphotographed elevations are deliberately not assigned fabricated window rows.
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
from scipy.ndimage import binary_erosion

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building
from campus_window_frames import bridge_frame_edges, close_diagonal_pane_corners


SLAB_BOTTOM = {"type": "bottom", "waterlogged": "false"}
SLAB_TOP = {"type": "top", "waterlogged": "false"}


def _body_mask(f, p):
    g = p["geometry"]
    return f.local_mask(g["main_body_bounds_uv_m"]) | f.local_mask(
        g["front_projection_bounds_uv_m"]
    )


def _roof_surface(r, f, mask, levels, record, *, maximum=False):
    """Apply a source-labelled surface without growing the measured plan."""
    mask = mask.copy()
    if maximum:
        mask &= ~r.footprint_mask | ~np.isfinite(r.heights) | (levels > r.heights)
    heights, faces = r.heights.copy(), r.face_indices.copy()
    gx, gz = r.gradient_x.copy(), r.gradient_z.copy()
    dz, dx = np.gradient(levels, r.resolution)
    face_id = 1_000_000 + len(r.authored_roof_patches)
    heights[mask], faces[mask] = levels[mask], face_id
    gx[mask], gz[mask] = dx[mask], dz[mask]
    record = {
        **record,
        "face_index": face_id,
        "affected_columns": int(mask.sum()),
        "origin_xz_m": f.origin.tolist(),
        "axis_degrees": f.g["axis_degrees"],
        "plan_rule": "intersected with exact original measured footprint raster",
    }
    return replace(
        r,
        heights=heights,
        face_indices=faces,
        gradient_x=gx,
        gradient_z=gz,
        footprint_mask=r.footprint_mask | mask,
        missing_mask=r.missing_mask & ~mask,
        authored_roof_patches=(*r.authored_roof_patches, record),
    )


def prepare_roof(r, f, p):
    """Repair low false facets; reconstruct the photographed gable overlap."""
    original = r.footprint_mask.copy()
    measured = load_measured_building(parent_id=p["parent_id"])
    source_faces = []
    for i, face in enumerate(measured.roof_faces):
        xy = np.asarray(face.polygon.exterior.coords)
        delta = xy - f.origin
        uv = np.column_stack((delta @ f.t, delta @ f.n))
        source_faces.append(
            {
                "face_id_0based": i,
                "fingerprint": p["roof_evidence"]["face_fingerprints"][str(i)],
                "part_id": face.part_id,
                "surface_index": face.surface_index,
                "polygon_uv_m": np.round(uv, 6).tolist(),
                "height_plane_xz": [face.a, face.b, face.c],
                "height_min_max_navd88_m": [face.min_h, face.max_h],
                "disposition": (
                    "southern/front porch orientation evidence; surface rebuilt at the photographed continuous porch level"
                    if i in (0, 3)
                    else "ground-level reconstruction contradicted by photographed porch/body"
                    if i in (2, 4)
                    else "ridge/slope control; single ridge topology corrected against numbered photo"
                ),
            }
        )
    retained = original & np.isin(r.face_indices, [0, 3])
    record = {
        "face_index": 999_999,
        "source": "Unit 3 primary contractor photo versus six original Roofer faces",
        "source_ref": "east_photo_2",
        "affected_columns": int((original & ~retained).sum()),
        "source_roof_sha256": p["roof_evidence"]["source_sha256"],
        "source_faces": source_faces,
        "measured_footprint_columns": int(original.sum()),
        "measured_footprint_area_m2": measured.footprint.area,
        "uncertainty": "Photo counts are observed; gable placement and porch metric bounds are interpreted.",
    }
    r = replace(
        r,
        footprint_mask=retained,
        missing_mask=np.zeros_like(retained),
        heights=np.where(retained, r.heights, np.nan),
        face_indices=np.where(retained, r.face_indices, -1),
        authored_roof_patches=(*r.authored_roof_patches, record),
    )
    g = p["geometry"]
    a, b, c, d = g["main_body_bounds_uv_m"]
    ridge = g["source_roof_ridge_navd88_m"]
    eave = g["main_roof_eave_navd88_m"]
    main = eave + (ridge - eave) * (
        1 - abs(f.u - (a + c) / 2) / ((c - a) / 2)
    )
    r = _roof_surface(
        r, f, original & f.local_mask((a, b, c, d)), main,
        {
            "source": "photographed taller setback gable using measured ridge and approximately 30-degree pitch",
            "source_ref": "east_photo_2",
            "control_source_face_ids": [1, 5],
            "bounds_uv_m": [a, b, c, d],
            "ridge_navd88_m": ridge,
            "eave_navd88_m": eave,
            "ridge_u_m": (a + c) / 2,
            "slope_degrees": math.degrees(math.atan((ridge - eave) / ((c-a)/2))),
        },
    )
    a, b, c, d = g["front_projection_bounds_uv_m"]
    ridge, eave = g["front_roof_ridge_navd88_m"], g["front_roof_eave_navd88_m"]
    front = eave + (ridge - eave) * (
        1 - abs(f.u - (a+c)/2) / ((c-a)/2)
    )
    r = _roof_surface(
        r, f, original & f.local_mask((a,b,c,d)), front,
        {
            "source": "photographed lower projecting gable, photo-proportioned intersecting roof",
            "source_ref": "east_photo_2",
            "reinterpreted_source_face_ids": [1,5],
            "bounds_uv_m": [a,b,c,d],
            "ridge_navd88_m": ridge,
            "eave_navd88_m": eave,
            "ridge_u_m": (a+c)/2,
            "geometry_status": "photo-interpreted, not a measured independent source plane",
        }, maximum=True,
    )
    porch = p["porch"]
    eave, inner = g["porch_eave_navd88_m"], g["porch_inner_roof_navd88_m"]
    for name, bounds, along in (
        ("front", porch["front_bounds_uv_m"], f.v),
        ("west", porch["west_bounds_uv_m"], f.u),
    ):
        lo, hi = (bounds[1], bounds[3]) if name == "front" else (bounds[0], bounds[2])
        amount = (along-lo)/(hi-lo)
        if name == "front":
            amount = 1-amount
        levels = eave + (inner-eave) * amount
        r = _roof_surface(
            r, f, original & f.local_mask(bounds) & ~_body_mask(f,p), levels,
            {
                "source": "observed open wraparound porch; explicit repair of ground-height roof artefacts",
                "source_ref": "east_photo_2",
                "replaced_source_face_ids": [0,2,3,4],
                "bounds_uv_m": bounds,
                "outer_eave_navd88_m": eave,
                "inner_roof_navd88_m": inner,
                "porch_side": name,
            },
        )
    return r


def _post(f, u, v, floor, top):
    """One minimum-grid square post, with a half-block capital and base."""
    x, z = np.floor(f.world(u,v) * f.c.scale).astype(int)
    for y in range(f.height_y(floor), f.height_y(top)):
        f.c.set(int(x),y,int(z),"quartz_block","trim")
    f.c.set(int(x),f.height_y(floor)-1,int(z),"quartz_block","trim")
    f.features["photo_interpreted_square_porch_posts"] += 1


def _physical_top(f, mask, navd, role="pavement", full="smooth_stone", slab="smooth_stone_slab"):
    """Solid stair/landing top on a physical quarter-metre grid."""
    top_half = round((navd+f.offset)*f.c.scale*2)
    solid_top, half = divmod(top_half,2)
    for x,z,iz,ix in f.each_column(mask):
        ground = f.c.ground_at(x,z)
        for y in range(min(ground,solid_top)-1,solid_top):
            f.c.set(x,y,z,full,role)
        if half:
            f.c.set(x,solid_top,z,slab,role,SLAB_BOTTOM)
        f.features["graded_entry_tread_columns"] += 1


def _flush_openings(f,p,body):
    """A single pale pane sheet occupies the outer wall aperture."""
    old = f.r
    f.r = replace(old,footprint_mask=body & old.footprint_mask)
    for row in p["openings"]:
        for center in row["centres_m"]:
            _residential_opening(f,center,row["side"],row["sill_navd88_m"],row["width_m"],
                                 row["height_m"],at=row["at_m"],sashes=row["sashes"])
            f.features["photo_sash_count_with_pale_pane_proxy"] += row["sashes"]
    floor=p["geometry"]["entrance_floor_navd88_m"]
    u,v=p["porch"]["entry_door_uv_m"]
    columns,low,high=_residential_opening(
        f,u,"south",floor,1.1,2.2,at=v,panel="dark_oak_trapdoor",glazed=False
    )
    # One real operable lower door remains in the thin, scaled door panel.
    # Its upper panel is a vertical trapdoor skin rather than a projecting cube.
    if columns:
        x,z=min(columns,key=lambda q:abs(f.u[q[1]-f.c.z_min,q[0]-f.c.x_min]-u))
        for half,dy in (("lower",0),("upper",1)):
            f.c.set(x,low+dy,z,"dark_oak_door","door",
                    {"facing":"north","half":half,"hinge":"left","open":"false","powered":"false"})
        f.features["operable_reference_doors"]+=1
    f.features["flush_thin_door_panels"]+=len(columns)
    # Narrow glass at the latch side and a glazed head are visible on this door.
    _residential_opening(f,u-0.78,"south",floor+0.2,0.4,2.0,at=v)
    _residential_opening(f,u,"south",floor+2.0,1.15,0.4,at=v)
    f.r=old
    f.features["photo_recessed_entry_with_sidelight_transom"]=1
    f.features["unsupported_unseen_east_north_window_rows"]=0


def _residential_opening(f,center,side,sill,width,height,*,at,panel=None,glazed=True,sashes=1):
    """Cut only this wall skin and seat a single outer white pane sheet.

    The generic 1.35m reveal cut crossed the adjacent wall near the door.
    This bounded residential cut follows the authored 0.5m wall instead.
    """
    glass=f.p["materials"]["glass"]
    along,normal=(f.u,f.v) if side=="south" else (f.v,f.u)
    sign=1 if side=="south" else -1
    depth=(normal-at)*sign
    span=abs(along-center)<=width/2
    wall=f.r.footprint_mask & span & (depth>=-.65) & (depth<=.3)
    low=math.ceil((sill+f.offset)*f.c.scale-.5)
    high=math.ceil((sill+height+f.offset)*f.c.scale-.5)
    columns={}
    for x,z,iz,ix in f.each_column(wall):
        key=x if side=="south" else z
        old=columns.get(key)
        if old is None or (z>old[1] if side=="south" else x<old[0]):
            columns[key]=(x,z)
        for y in range(low,high):
            f.c.set(x,y,z,"air","air")
    columns=[columns[k] for k in sorted(columns)]
    if not columns:
        raise ValueError(f"No residential aperture at {side} {center}, {at}")
    inward=(0,-1) if side=="south" else (1,0)
    props={"facing":"north" if side=="south" else "east","half":"bottom",
           "open":"true","powered":"false","waterlogged":"false"}
    allowed=set()
    for x,z in columns:
        for y in range(low,high):
            f.c.set(x,y,z,glass if glazed else panel,"window" if glazed else "trim",
                    PANE_PROPS if glazed else props)
            if glazed:
                allowed.add((x,y,z))
                xx,zz=x+inward[0],z+inward[1]
                if f.r.footprint_mask[zz-f.c.z_min,xx-f.c.x_min]:
                    allowed.add((xx,y,zz))
        f.c.set(x,low-1,z,"quartz_slab","trim",SLAB_TOP)
        f.c.set(x,high,z,"quartz_slab","trim",SLAB_BOTTOM)
    if glazed:
        # Both alternative raster corners are authorised only inside this
        # window's wall; the shared helper chooses exactly one inward return.
        for aa,bb in zip(columns,columns[1:]):
            if abs(aa[0]-bb[0])==1 and abs(aa[1]-bb[1])==1:
                for x,z in ((aa[0],bb[1]),(bb[0],aa[1])):
                    if f.r.footprint_mask[z-f.c.z_min,x-f.c.x_min]:
                        allowed.update((x,y,z) for y in range(low,high))
        if not hasattr(f,"unit3_window_authorisations"):
            f.unit3_window_authorisations=[]
        f.unit3_window_authorisations.append((allowed,inward))
        f.features["outer_wall_pane_sheet_blocks"]+=len(columns)*(high-low)
    f.features["thin_residential_sill_and_head_windows"]+=1
    return columns,low,high


def _close_window_perimeters(f):
    """Finish authorised turns and physical head/sill contact after the brow."""
    for allowed,inward in f.unit3_window_authorisations:
        f.features["authorised_diagonal_return_panes"]+=close_diagonal_pane_corners(
            f.c,allowed,inward=inward)
        f.features["authorised_frame_return_panes"]+=bridge_frame_edges(
            f.c,allowed,inward=inward)
    pane_ids=[i for i,s in enumerate(f.c.palette) if s["Name"].endswith("_pane")]
    for iy,iz,ix in np.argwhere(np.isin(f.c.data,pane_ids)):
        x,y,z=int(ix)+f.c.x_min,int(iy)+f.c.y_min,int(iz)+f.c.z_min
        for dy,props in ((-1,SLAB_TOP),(1,SLAB_BOTTOM)):
            target=(x,y+dy,z)
            state=f.c.palette[f.c.get(*target)]
            name=state["Name"]
            if name.endswith("_pane"):
                continue
            wrong_slab=name.endswith("_slab") and state.get("Properties",{}).get("type") not in {props["type"],"double"}
            if name=="minecraft:air" or wrong_slab:
                # A lower-half pale fascia also closes the four bay-head
                # contacts formerly overwritten by upper-half brow slabs.
                f.c.set(*target,"quartz_slab","trim",props)
                f.features["physical_window_perimeter_caps"]+=1
    connect_window_panes(f.c)
    # A transom can terminate beside the partial slab cap of its sidelight.
    # Complete only that authorised, embedded head corner; there is no new
    # projecting jamb column or opaque skin over the glass.
    for allowed,inward in f.unit3_window_authorisations:
        for position in sorted(allowed):
            state=f.c.palette[f.c.get(*position)]
            if not state["Name"].endswith("_pane"):
                continue
            props=state.get("Properties",{})
            if sum(props.get(d)=="true" for d in ("east","west","north","south"))>=2:
                continue
            x,y,z=position
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                adjacent=(x+dx,y,z+dz)
                if adjacent in allowed and f.c.palette[f.c.get(*adjacent)]["Name"]=="minecraft:quartz_slab":
                    f.c.set(*adjacent,"quartz_block","trim")
                    f.features["embedded_transom_head_corner_closures"]+=1
                    break
                if adjacent not in allowed or f.c.get(*adjacent):
                    continue
                # At a diagonal transom/sidelight junction the existing cap
                # is beside the single authorised return cell, not beside
                # the main pane. Complete that cap before adding the return.
                closed=False
                for ex,ez in ((1,0),(-1,0),(0,1),(0,-1)):
                    cap=(adjacent[0]+ex,y,adjacent[2]+ez)
                    if f.c.palette[f.c.get(*cap)]["Name"]=="minecraft:quartz_slab":
                        f.c.set(*cap,"quartz_block","trim")
                        f.features["embedded_transom_head_corner_closures"]+=1
                        closed=True
                        break
                if closed:
                    break
        f.features["authorised_frame_return_panes"]+=bridge_frame_edges(
            f.c,allowed,inward=inward)
    # Any last transom return receives its own contacting caps.
    pane_ids=[i for i,s in enumerate(f.c.palette) if s["Name"].endswith("_pane")]
    for iy,iz,ix in np.argwhere(np.isin(f.c.data,pane_ids)):
        x,y,z=int(ix)+f.c.x_min,int(iy)+f.c.y_min,int(iz)+f.c.z_min
        for dy,props in ((-1,SLAB_TOP),(1,SLAB_BOTTOM)):
            state=f.c.palette[f.c.get(x,y+dy,z)]
            wrong_slab=state["Name"].endswith("_slab") and state.get("Properties",{}).get("type") not in {props["type"],"double"}
            if state["Name"]=="minecraft:air" or wrong_slab:
                f.c.set(x,y+dy,z,"quartz_slab","trim",props)
                f.features["physical_window_perimeter_caps"]+=1
    # A half-slab touching glass still leaves its other half open against the
    # next masonry course unless there is solid wall backing. Fill only the
    # concealed interior cap backing; preserve the outer sheet and roof cells.
    body=_body_mask(f,f.p) & f.r.footprint_mask
    checked_caps=set()
    for allowed,inward in f.unit3_window_authorisations:
        for x,y,z in sorted(allowed):
            if not f.c.palette[f.c.get(x,y,z)]["Name"].endswith("_pane"):
                continue
            for dy in (-1,1):
                cap=(x,y+dy,z)
                state=f.c.palette[f.c.get(*cap)]
                if not state["Name"].endswith("_slab") or (cap,inward) in checked_caps:
                    continue
                checked_caps.add((cap,inward))
                for depth in (1,2,3):
                    xx,zz=x+inward[0]*depth,z+inward[1]*depth
                    if not body[zz-f.c.z_min,xx-f.c.x_min]:
                        raise ValueError(f"Window cap backing leaves occupied body at {(xx,y+dy,zz)}")
                    back=(xx,y+dy,zz)
                    state=f.c.palette[f.c.get(*back)]
                    name=state["Name"]
                    role=f.c.roles[y+dy+64,zz-f.c.z_min,xx-f.c.x_min]
                    if name=="minecraft:air":
                        f.c.set(*back,f.p["materials"]["facade"],"facade")
                        f.features["concealed_head_sill_backing_cells"]+=1
                        break
                    if name=="minecraft:quartz_slab" and role==ROLES.index("trim"):
                        f.c.set(*back,"quartz_block","trim")
                        f.features["embedded_partial_cap_backing_closures"]+=1
                        break
                    if name.endswith(("_slab","_stairs","_pane","_door","_trapdoor","_fence")):
                        continue
                    break
                else:
                    raise ValueError(f"No solid backing behind window cap {cap}")
    f.features["head_sill_caps_checked_for_solid_backing"]=len(checked_caps)
    connect_window_panes(f.c)
    checked=0
    for iy,iz,ix in np.argwhere(np.isin(f.c.data,[i for i,s in enumerate(f.c.palette) if s["Name"].endswith("_pane")])):
        x,y,z=int(ix)+f.c.x_min,int(iy)+f.c.y_min,int(iz)+f.c.z_min
        state=f.c.palette[f.c.get(x,y,z)]
        joins=sum(state.get("Properties",{}).get(d)=="true" for d in ("east","west","north","south"))
        if joins<2:
            raise ValueError(f"Unclosed horizontal sash endpoint at {(x,y,z)}")
        for dy,need in ((-1,"top"),(1,"bottom")):
            adjacent=f.c.palette[f.c.get(x,y+dy,z)]
            if adjacent["Name"]=="minecraft:air" or (adjacent["Name"].endswith("_slab") and adjacent.get("Properties",{}).get("type") not in {need,"double"}):
                raise ValueError(f"Unclosed vertical sash edge at {(x,y,z)}")
        checked+=1
    f.features["pane_perimeters_checked_without_gaps"]=checked


def _facade_finish(f,p,body):
    g=p["geometry"]
    # Facing only: do not fill the hollow interior with the plinth material.
    f.recolor((0,-0.4,10.1,15),65.0,g["plinth_top_navd88_m"],"tuff")
    for side,at,ends in (
        ("west",2.55,(0.01,12.25)),
        ("south",12.25,(2.55,5.75)),
        ("south",13.88,(5.75,9.7972)),
        ("east",9.7972,(0.01,13.88)),
        ("north",0.01,(2.55,9.7972)),
    ):
        f.wall_band(side,at,ends,g["plinth_top_navd88_m"],0.2,"quartz_block",depth=0.3)
    # Only the two observed gable-tip panels receive the lighter shingle proxy.
    f.recolor((2.55,11.8,9.8,12.5),73.12,75.4,p["materials"]["gable_infill"])
    f.recolor((5.75,13.4,9.8,14.1),72.9,74.75,p["materials"]["gable_infill"])
    # Inset corner boards: no 1m projecting tower around a residential corner.
    for u,v,low,high in (
        (2.55,12.25,67.6,73.1),(5.75,13.88,67.6,72.8),
        (9.7972,13.88,67.6,72.8),(9.7972,0.01,67.6,73.1),
        (2.55,0.01,67.6,73.1),
    ):
        f.recolor((u-.3,v-.3,u+.3,v+.3),low,high,"quartz_block",role="trim")
    f.features["observed_gable_tip_infill_panels"]=2
    f.features["photo_profile_material_roles"]=5


def _thin_roof_fascia(f,p,body):
    # Thin trim follows the original top shape. Its wall substrate stays
    # solid: a top slab substituted below the roof creates a daylight slit.
    g=p["geometry"]
    exposed=(f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask))
    fronts=(f.local_mask((2.25,11.8,5.75,12.5)) |
            f.local_mask((5.45,13.35,10.05,14.1)))
    ends=(exposed|fronts)&body
    for x,z,iz,ix in f.each_column(ends):
        cells=np.flatnonzero(f.c.roles[:,iz,ix]==ROLES.index("roof"))
        if not len(cells):
            continue
        y=int(cells[-1])+f.c.y_min
        state=f.c.palette[f.c.get(x,y,z)]
        target="quartz_stairs" if state["Name"].endswith("_stairs") else "quartz_slab" if state["Name"].endswith("_slab") else "quartz_block"
        props=state.get("Properties")
        if target=="quartz_block" and fronts[iz,ix]:
            # Native v7 made the photographed narrow rake read as white
            # square teeth. Bevel its full-cell caps uphill, retaining the
            # same maximum height and the solid wall immediately below.
            # This changes trim shape only, not either authored roof plane.
            gx,gz=float(f.r.gradient_x[iz,ix]),float(f.r.gradient_z[iz,ix])
            if abs(gx)>=abs(gz):
                facing="east" if gx>=0 else "west"
            else:
                facing="south" if gz>=0 else "north"
            target="quartz_stairs"
            props={"facing":facing,"half":"bottom","shape":"straight","waterlogged":"false"}
            f.features["photo_gable_full_caps_bevelled_without_height_change"]+=1
        f.c.set(x,y,z,target,"trim",props if target!="quartz_block" else None)
        f.c.set(x,y-1,z,p["materials"]["facade"],"facade")
        f.features["roof_edge_fascia_states"]=f.features.get("roof_edge_fascia_states",0)+1
        f.features["roof_edge_solid_backing_columns"]+=1


def _roof_slab(f,x,z,navd,block,role):
    """One and only one half-height slab ending at the physical surface."""
    halves=round((navd+f.offset)*f.c.scale*2)
    whole,half=divmod(halves,2)
    y,props=(whole,SLAB_BOTTOM) if half else (whole-1,SLAB_TOP)
    f.c.set(x,y,z,block,role,props)


def _porch_roof(f,p,porch_mask):
    """Remove shell backing and give the photographed porch a thin cap."""
    g=p["geometry"]
    outer=porch_mask & ~binary_erosion(f.r.footprint_mask)
    for x,z,iz,ix in f.each_column(porch_mask):
        # No tall backed dark band is retained from the general shell builder.
        old=np.flatnonzero(np.isin(f.c.roles[:,iz,ix],[ROLES.index("roof"),ROLES.index("trim")]))
        for iy in old:
            if int(iy)+f.c.y_min>=f.height_y(g["entrance_floor_navd88_m"]+1.0):
                f.c.set(x,int(iy)+f.c.y_min,z,"air","air")
        level=g["porch_eave_navd88_m"] if outer[iz,ix] else float(f.r.heights[iz,ix])
        _roof_slab(f,x,z,level,"quartz_slab" if outer[iz,ix] else p["materials"]["roof_family"]+"_slab",
                   "trim" if outer[iz,ix] else "roof")
        f.features["single_slab_porch_roof_columns"]+=1
    f.features["continuous_cream_porch_fascia_columns"]=int(outer.sum())
    # The shallow brow across the projecting front bay follows the same cap.
    body=_body_mask(f,p) & f.r.footprint_mask
    for x,z,iz,ix in f.each_column(f.local_mask((5.75,13.5,9.8,14.22))):
        if body[iz,ix]:
            # The brow is an exterior overhang, not a cut through the wall.
            # V7 replaced two complete jamb/floor-edge cells with top slabs,
            # opening their lower halves at the ends of the bay. Preserve
            # the existing wall and contacting pane heads inside the body.
            f.features["bay_brow_preserved_occupied_wall_columns"]+=1
            continue
        edge=f.v[iz,ix]>=13.9
        _roof_slab(f,x,z,g["porch_eave_navd88_m"],"quartz_slab" if edge else p["materials"]["roof_family"]+"_slab",
                   "trim" if edge else "roof")


def build_details(f,p):
    g,porch=p["geometry"],p["porch"]
    floor=g["entrance_floor_navd88_m"]
    body=_body_mask(f,p) & f.r.footprint_mask
    open_porch=(f.local_mask(porch["front_bounds_uv_m"]) |
                f.local_mask(porch["west_bounds_uv_m"])) & ~body & f.r.footprint_mask
    # A roof footprint must not become an enclosed siding room under the porch.
    for x,z,iz,ix in f.each_column(open_porch):
        roof_cells=np.flatnonzero(f.c.roles[:,iz,ix]==ROLES.index("roof"))
        if not len(roof_cells):
            continue
        roof_y=int(roof_cells.min())+f.c.y_min
        for y in range(f.height_y(floor),roof_y):
            f.c.set(x,y,z,"air","air")
    _physical_top(f,open_porch,floor,"floor")
    # Re-establish the actual recessed wall at the roof change rather than
    # allowing the inherited contour to select the outer porch posts.
    for bounds in ((2.55,0.01,3.05,12.25),(2.55,11.75,5.75,12.25),
                   (5.75,12.25,6.25,13.88)):
        f.box(bounds,floor,g["porch_inner_roof_navd88_m"],p["materials"]["facade"],"facade")
    _facade_finish(f,p,body)
    _flush_openings(f,p,body)
    _thin_roof_fascia(f,p,body)
    _porch_roof(f,p,open_porch)
    for u,v in porch["posts_uv_m"]:
        _post(f,u,v,floor,g["porch_eave_navd88_m"])
    # The photographed entry has a shallow, broad concrete-looking stair.
    a,b,c,d=porch["entry_step_bounds_uv_m"]
    for i in range(3):
        v0=b+i*.55
        _physical_top(f,f.local_mask((a,v0,c,v0+.55)),floor-(i+1)*.25)
    # A small smooth landing meets the measured grade, without levelling lawn.
    f.site_surface([(a,d),(c,d),(c,d+.8),(a,d+.8)],floor-.85)
    chimney=p["chimney"]
    a,b,c,d=chimney["bounds_uv_m"]
    top=chimney["top_navd88_m"]
    f.box((a,b,c,d),65.5,top,p["materials"]["facade"],"facade")
    f.recolor((a,b,c,d),65.5,g["plinth_top_navd88_m"],"tuff")
    # Do not let sub-grid overhang rounding turn this into a broad flying cap.
    for x,z,_,_ in f.each_column(f.local_mask((a,b,c,d))):
        _roof_slab(f,x,z,top,"smooth_stone_slab","trim")
    # A tiny pale flue termination is visible; its exact type is not asserted.
    x,z=np.floor(f.world((a+c)/2,(b+d)/2)*f.c.scale).astype(int)
    f.c.set(int(x),f.height_y(top),int(z),"iron_trapdoor","fixture",
            {"facing":"north","half":"bottom","open":"false","powered":"false","waterlogged":"false"})
    f.floor_plate(floor,block="birch_planks")
    f.floor_plate(g["upper_floor_navd88_m"],block="birch_planks")
    # Native v4 exposed two yellow strips below the front sashes. These came
    # from the floor-role interior plate, not gable infill or a second siding
    # color. Give only the visible front rim the same exterior-facing finish.
    rim=(f.local_mask((2.55,10.7,5.75,12.25)) |
         f.local_mask((5.75,12.4,9.8,13.88)))
    floor_y=f.height_y(g["upper_floor_navd88_m"])-1
    floor_index=floor_y-f.c.y_min
    rim &= ((f.c.roles[floor_index]==ROLES.index("floor")) &
            (f.c.data[floor_index]==f.c.state("birch_planks")))
    for x,z,_,_ in f.each_column(rim):
        f.c.set(x,floor_y,z,p["materials"]["facade"],"facade")
    f.features["photo_front_floor_rim_clad_to_match_siding"]=int(rim.sum())
    _close_window_perimeters(f)
    f.features.update({
        "photo_numbered_unit3":1,
        "open_wrap_porch_columns":int(open_porch.sum()),
        "individually_interpreted_photo_elevations":2,
        "unphotographed_elevations_flagged_unresolved":2,
        "separate_front_gables":2,
        "photo_external_clad_chimney":1,
        "invented_dormers":0,
    })
