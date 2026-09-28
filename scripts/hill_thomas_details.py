"""Thomas House: photographed brick, shuttered sashes and separate entries.

All authored surfaces and hidden-elevation proposals are recorded in the
profile. The exact source footprint and the shared 2 blocks/m datum remain.
"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion

from build_hill_chapel_sample import ROLES
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building
from campus_window_frames import close_diagonal_pane_corners

ROOT = Path(__file__).resolve().parents[1]
BOTTOM = {"type": "bottom", "waterlogged": "false"}
TOP = {"type": "top", "waterlogged": "false"}


def _source(p):
    b = load_measured_building(parent_id=p["parent_id"])
    research = json.loads((ROOT / p["roof_evidence"]["ledger"]).read_text(encoding="utf-8"))
    r = next(x for x in research["building_records"] if x["parent_id"] == p["parent_id"])
    if b.source_sha256 != p["roof_evidence"]["source_sha256"]:
        raise ValueError("Thomas source hash changed; roof masks require another audit")
    fr = r["measured"]["local_frame"]
    origin = np.array(fr["origin_xz_m"])
    axes = np.array([fr["U_xz"], fr["V_xz"]])
    for i, (face, m) in enumerate(zip(b.roof_faces, r["measured"]["roof_planes"], strict=True)):
        fp = hashlib.sha256(json.dumps({"xy": m["uv_polygon_m"], "plane": m["height_plane_xz"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        if fp != r["roof_face_audit"]["faces"][i]["fingerprint"]:
            raise ValueError(f"Thomas research fingerprint changed: face {i}")
        if not np.allclose(origin + np.array(m["uv_polygon_m"]) @ axes,
                           np.array(face.polygon.exterior.coords), atol=.00002):
            raise ValueError(f"Thomas source polygon identity changed: face {i}")
        if not np.allclose([face.a, face.b, face.c], m["height_plane_xz"], atol=1e-8):
            raise ValueError(f"Thomas source plane identity changed: face {i}")
    return b


def _patch(r, mask, heights, gx, gz, record):
    mask = mask & r.footprint_mask
    h, dx, dz, ids = r.heights.copy(), r.gradient_x.copy(), r.gradient_z.copy(), r.face_indices.copy()
    for target, value in ((h, heights), (dx, gx), (dz, gz)):
        target[mask] = np.broadcast_to(value, h.shape)[mask]
    face_id = 1_000_000 + len(r.authored_roof_patches)
    ids[mask] = face_id
    evidence = {"face_index": face_id, "source": "explicit photo-interpreted Thomas roof correction; not a surveyed surface", "affected_columns": int(mask.sum()), "footprint_change_columns": 0, **record}
    return replace(r, heights=h, gradient_x=dx, gradient_z=dz, face_indices=ids,
                   missing_mask=r.missing_mask & ~mask,
                   authored_roof_patches=(*r.authored_roof_patches, evidence))


def prepare_roof(r, f, p):
    b = _source(p)
    original = r.face_indices.copy()
    north = np.isin(original, [2, 9, 10, 11, 12, 13])
    # The photograph shows a complete two-storey northern end, not the
    # 55m ground fragments or 71–75m canopy fragments in this same plan.
    flat = north & (f.v < 5.234)
    face = b.roof_faces[5]
    r = _patch(r, flat, face.height_at(f.x, f.z), face.a, face.b,
               {"reason": "Restore the photographed full-height north end using adjacent accepted flat roof 5; explicit high and low masks only.",
                "replaced_source_face_ids": [2, 9, 10, 11, 12, 13], "extended_source_plane": 5})
    face = b.roof_faces[1]
    r = _patch(r, north & ~flat, face.height_at(f.x, f.z), face.a, face.b,
               {"reason": "North-hip edge of high fragment 2 follows its accepted adjacent hip plane.", "replaced_source_face_ids": [2], "extended_source_plane": 1})
    face = b.roof_faces[4]
    r = _patch(r, original == 8, face.height_at(f.x, f.z), face.a, face.b,
               {"reason": "A photographed upper sash above the right entry requires the full two-storey south end; low patch 8 is not an occupied-storey limit.", "replaced_source_face_ids": [8], "extended_source_plane": 4})
    face = b.roof_faces[7]
    r = _patch(r, original == 0, face.height_at(f.x, f.z), face.a, face.b,
               {"reason": "Unmatched tiny west-edge fragment 0 is excluded from this interpreted silhouette; it cannot be identified as a chimney or second dormer. Its identity remains unresolved.", "replaced_source_face_ids": [0], "extended_source_plane": 7})
    # The single visible bow-top dormer. It remains inside the footprint,
    # with an explicit barrel-profile roof instead of a generic gable.
    d = p["dormer"]
    dv = f.v-d["centre_v_m"]
    radius = d["width_m"]/2
    arch = np.sqrt(np.maximum(0, 1-(dv/radius)**2))
    levels = d["spring_navd88_m"] + d["rise_m"]*arch
    dz, dx = np.gradient(levels, r.resolution)
    mask = f.local_mask(d["bounds_uv_m"])
    r = _patch(r, mask, levels, dx, dz,
               {"reason": "One curved white dormer directly visible in the west Street View; dimensions and exact position are interpreted.",
                "bounds_uv_m": d["bounds_uv_m"], "spring_navd88_m": d["spring_navd88_m"], "rise_m": d["rise_m"], "profile": "semicircular barrel segment across V"})
    return r


def _flush_aperture(f, side, at, centre, sill, width, height, *, door=False,
                    wall_mask=None, surround="bricks"):
    """Use actual wall-edge columns as the oblique opening contour.

    A narrow half-metre contour bin can otherwise select an interior roof
    sample when its wall sample falls just outside that bin. Thomas has a
    straight envelope, so only its true perimeter may contain facade glass.
    """
    raster = f.r
    if wall_mask is None:
        wall_mask = raster.footprint_mask & ~binary_erosion(raster.footprint_mask)
    depth = f.u if side in {"west", "east"} else f.v
    wall_mask &= abs(depth-at) < .85
    f.r = replace(raster, footprint_mask=wall_mask)
    try:
        if door:
            f.door(side, at, centre, sill, width, height)
        else:
            f.window_row(side, at, [centre], sill, width, height, lights=1)
    finally:
        f.r = raster
    along = f.v if side in {"west", "east"} else f.u
    mask = (abs(along-centre) <= width/2+.30) & wall_mask
    # Every actual wall-edge cell inside the intended aperture receives
    # glazing. Interpolated contour bins must not leave a narrow air strip
    # alongside the pane on a diagonal raster step.
    opening_mask=(abs(along-centre)<=width/2) & wall_mask
    for x,z,iz,ix in f.each_column(opening_mask):
        for y in range(f.height_y(sill),f.height_y(sill+height)+1):
            h=(y+.5)/f.c.scale-f.offset
            if sill<=h<=sill+height and y>f.c.ground_at(x,z):
                f.c.set(x,y,z,f.p["window_reveal"]["glass_block"],"window",PANE_PROPS)
    # Seat pane ends in full existing-envelope masonry. No half-slab sill
    # replaces the wall, and no projecting glass or masonry cage is added.
    for x, z, iz, ix in f.each_column(mask):
        ys = [y for y in range(f.height_y(sill), f.height_y(sill+height)+1)
              if f.c.palette[f.c.get(x,y,z)]["Name"].endswith("_pane")]
        if not ys:
            continue
        for y in (min(ys)-1, max(ys)+1):
            if (y+.5)/f.c.scale-f.offset < f.r.heights[iz,ix] and y > f.c.ground_at(x,z):
                if not f.c.palette[f.c.get(x,y,z)]["Name"].endswith("_door"):
                    f.c.set(x,y,z,surround,"facade")
    # Authorise one inward L-return only within this window's reveal. This
    # closes diagonal pane joints without enlarging the outside footprint.
    reveal=raster.footprint_mask & (abs(along-centre)<=width/2+.30) & (abs(depth-at)<1.10)
    allowed={(x,y,z) for x,z,_,_ in f.each_column(reveal)
             for y in range(f.height_y(sill),f.height_y(sill+height)+1)}
    inward=f.t*(1 if side=="west" else -1) if side in {"west","east"} else f.n*(1 if side=="north" else -1)
    f.features["authorised_inward_pane_corner_returns"]+=close_diagonal_pane_corners(f.c,allowed,inward=inward)


def _window(f, side, at, centre, sill, width, height, shutters=False):
    _flush_aperture(f, side, at, centre, sill, width, height)
    if not shutters:
        return
    # Actual photographed shutters are separate thin panels on the brick.
    # The open trapdoor model is only 3/16 block deep, rather than a cube.
    along = f.v if side in {"west", "east"} else f.u
    depth = f.u if side in {"west", "east"} else f.v
    perimeter = f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    outward = f.t*(-1 if side=="west" else 1) if side in {"west","east"} else f.n*(-1 if side=="north" else 1)
    delta = (int(np.sign(outward[0])),0) if abs(outward[0])>=abs(outward[1]) else (0,int(np.sign(outward[1])))
    facing = ("east" if outward[0]>0 else "west") if abs(outward[0])>=abs(outward[1]) else ("south" if outward[1]>0 else "north")
    ys=range(f.height_y(sill),f.height_y(sill+height))
    for direction in (-1,1):
        position=centre+direction*(width/2+.26)
        candidates=perimeter & (abs(depth-at)<.85) & (direction*(along-centre)>width/2) & (abs(along-position)<1.0)
        choices=[]
        for x,z,iz,ix in f.each_column(candidates):
            if all(f.c.palette[f.c.get(x,y,z)]["Name"]=="minecraft:bricks" for y in ys):
                choices.append((abs(along[iz,ix]-position),x,z))
        if not choices:
            raise ValueError("Thomas shutter has no adjacent brick attachment")
        _,x,z=min(choices)
        x+=delta[0];z+=delta[1]
        for y in ys:
            f.c.set(x,y,z,"pale_oak_trapdoor","window",
                    {"facing":facing,"half":"bottom","open":"true","powered":"false","waterlogged":"false"})
    f.features["photographed_pale_shutter_pairs"] += 1


def _pedimented_entry(f, centre, floor):
    _flush_aperture(f, "west", .02, centre, floor, 1.10, 2.15)
    edge=f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    entry=edge & (f.u<.85) & (abs(f.v-centre)<.65)
    columns=list(f.each_column(entry))
    # Thin painted panels lie in the cut wall cells. The lower centre keeps
    # a real two-block door; no plank cubes project beyond the facade.
    for x,z,iz,ix in columns:
        for y in range(f.height_y(floor),f.height_y(floor+2.15)):
            f.c.set(x,y,z,"pale_oak_trapdoor","window",
                    {"facing":"east","half":"bottom","open":"true","powered":"false","waterlogged":"false"})
    x,z,_,_=min(columns,key=lambda a:abs(f.v[a[2],a[3]]-centre))
    for half,dy in (("lower",0),("upper",1)):
        f.c.set(x,f.height_y(floor)+dy,z,"birch_door","door",
                {"half":half,"facing":"west","hinge":"left","open":"false","powered":"false"})
    f.features["operable_reference_doors"]+=1
    # A quarter-metre cornice and shallow stair/slab triangle. It is only
    # one raster cell deep outside the wall and has continuous backing.
    mask=f.local_mask((-.34,centre-1.10,.32,centre+1.10))
    fronts={}
    for x,z,iz,ix in f.each_column(mask):
        fronts[z]=min(fronts.get(z,x),x)
    base=f.height_y(floor+2.25)
    for z,x in fronts.items():
        iz,ix=z-f.c.z_min,x-f.c.x_min
        distance=abs(f.v[iz,ix]-centre)
        peak=(floor+2.50+.50*max(0,1-distance/1.10)+f.offset)*f.c.scale
        surface=round(peak*2)/2
        top=int(np.floor(surface-.01))
        for y in range(base,top):
            f.c.set(x,y,z,"smooth_quartz","trim")
        if surface%1:
            f.c.set(x,top,z,"smooth_quartz_slab","trim",BOTTOM)
        elif distance>.28:
            f.c.set(x,top,z,"smooth_quartz_stairs","trim",
                    {"half":"bottom","shape":"straight","waterlogged":"false","facing":"south" if f.v[iz,ix]<centre else "north"})
        else:
            f.c.set(x,top,z,"smooth_quartz_slab","trim",TOP)
        # Only the wall-side backing is full: the outer hood retains its
        # low triangle, while the original masonry cannot show a sky slit.
        for y in range(base,top+1):
            if f.r.footprint_mask[iz,ix+1]:
                f.c.set(x+1,y,z,"smooth_quartz","trim")
    # Paved landings meet the door floor and descend to the measured lawn.
    f.box((-1.05,centre-.93,.10,centre+.93),floor-.50,floor-.25,"smooth_stone","pavement")
    f.box((-1.05,centre-.93,.10,centre+.93),floor-.25,floor,"smooth_stone_slab","pavement",TOP)
    for i,h in enumerate((floor-.50,floor-.25)):
        f.box((-2.05+.50*i,centre-.88,-1.50+.50*i,centre+.88),floor-1.0,h-.25,"smooth_stone","pavement")
        f.box((-2.05+.50*i,centre-.88,-1.50+.50*i,centre+.88),h-.25,h,"smooth_stone_slab","pavement",BOTTOM)
    f.features["photographed_separate_pedimented_entries"] += 1


def _dormer(f,p):
    d=p["dormer"];u0,v0,u1,v1=d["bounds_uv_m"]
    mask=f.local_mask((u0,v0,u0+.80,v1)) & f.r.footprint_mask
    fronts={}
    for x,z,iz,ix in f.each_column(mask):
        fronts[z]=min(fronts.get(z,x),x)
        for y in range(f.height_y(61.70),int(np.floor((f.r.heights[iz,ix]+f.offset)*f.c.scale))):
            f.c.set(x,y,z,"smooth_quartz","facade")
    # Quarter-block roof surfaces approximate the photographed curved brow.
    for z,x in fronts.items():
        iz,ix=z-f.c.z_min,x-f.c.x_min
        ys=np.flatnonzero(f.c.roles[:,iz,ix]==ROLES.index("roof"))
        if ys.size:
            y=int(ys[-1])-64
            st=f.c.palette[f.c.get(x,y,z)]
            name="smooth_quartz_stairs" if st["Name"].endswith("_stairs") else "smooth_quartz_slab" if st["Name"].endswith("_slab") else "smooth_quartz"
            f.c.set(x,y,z,name,"trim",st.get("Properties"))
            f.c.set(x,y-1,z,"smooth_quartz","facade")
    # Three clear block columns by two high give the photographed broad
    # sash a 1.5m x 1.0m aperture. Select the real front raster, not roof
    # samples behind it. The remaining border is a compact bevel at 2x.
    chosen=sorted(fronts,key=lambda z:abs(f.v[z-f.c.z_min,fronts[z]-f.c.x_min]-d["centre_v_m"]))[:3]
    bottom=f.height_y(61.95)
    for z in chosen:
        x=fronts[z]
        for y in range(bottom,bottom+2):
            for inner_x in range(x+1,x+5):
                iz,ix=z-f.c.z_min,inner_x-f.c.x_min
                if f.u[iz,ix]<u1+.2:
                    f.c.set(inner_x,y,z,"air","air")
            f.c.set(x,y,z,"white_stained_glass_pane","window",PANE_PROPS)
        f.c.set(x,bottom-1,z,"smooth_quartz_slab","trim",TOP)
        f.c.set(x+1,bottom-1,z,"smooth_quartz","facade")
        f.c.set(x,bottom+2,z,"smooth_quartz_slab","trim",BOTTOM)
    for za,zb in zip(sorted(chosen),sorted(chosen)[1:]):
        xa,xb=fronts[za],fronts[zb]
        if abs(xa-xb)==1 and zb-za==1:
            x=max(xa,xb);z=za if xa<xb else zb
            for y in range(bottom,bottom+2):
                f.c.set(x,y,z,"white_stained_glass_pane","window",PANE_PROPS)
    f.features["dormer_clear_glazing_width_blocks"]=3
    f.features["dormer_clear_glazing_height_blocks"]=2
    f.features["photographed_curved_white_dormer"] = 1


def _flat_end_coping(f):
    # A roof substrate is necessary, but its exposed edge is brick below
    # a single slab of coping. Keep every roof column's physical top.
    mask=np.isin(f.r.face_indices,[4,5,1_000_000,1_000_002]) & f.r.footprint_mask
    edge=f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    caps=[]
    backing=set()
    for x,z,iz,ix in f.each_column(mask & edge):
        ys=np.flatnonzero(f.c.roles[:,iz,ix]==ROLES.index("roof"))
        if not len(ys):continue
        y=int(ys[-1])+f.c.y_min
        state=f.c.palette[f.c.get(x,y,z)]
        for iy in ys[:-1]:
            f.c.set(x,int(iy)+f.c.y_min,z,"bricks","facade")
        if state["Name"].endswith("_slab") and state.get("Properties",{}).get("type")=="bottom":
            # Existing lower-half coping already rests on the wall below.
            caps.append((x,y,z,BOTTOM))
            continue
        outside=[(dx,dz) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))
                 if not f.r.footprint_mask[iz+dz,ix+dx]]
        supports=[]
        for dx,dz in outside:
            nx,nz=x-dx,z-dz
            support=f.c.palette[f.c.get(nx,y,nz)]["Name"]
            if support in {"minecraft:stone_bricks","minecraft:bricks"}:
                supports.append((nx,y,nz))
        if len(outside)==1 and supports:
            # The solid inward roof cell closes the cap's lower half and
            # provides physical support. It keeps its exact original top.
            backing.add(supports[0])
            caps.append((x,y,z,TOP))
        else:
            # A diagonal outer corner cannot hold two different slab
            # materials in one voxel. Keep a solid brick closure there.
            f.c.set(x,y,z,"bricks","facade")
            f.features["solid_brick_coping_corner_closures"]+=1
    for x,y,z,props in caps:
        if (x,y,z) not in backing:
            f.c.set(x,y,z,"stone_brick_slab","roof",props)
        f.features["flat_end_coping_columns_top_preserved"]+=1
    for x,y,z in backing:
        f.c.set(x,y,z,"bricks","facade")
    f.features["solid_coping_backer_cells"]=len(backing)
    # The interior floor does not create an invented gray exterior belt.
    y=f.height_y(f.p["geometry"]["entrance_floor_navd88_m"])-1
    for x,z,iz,ix in f.each_column(edge):
        if f.c.roles[y+64,iz,ix]==ROLES.index("floor"):
            f.c.set(x,y,z,"bricks","facade")


def _site(f,p):
    # The hedge is directly observed, but its measured line/species are not
    # available. Context height/location are explicitly approximate.
    for lo,hi in [(-.8,21.9)]:
        mask=f.local_mask((-5.25,lo,-4.35,hi))
        for x,z,iz,ix in f.each_column(mask):
            ground=f.c.ground_at(x,z)
            for y in range(ground+1,ground+5):
                f.c.set(x,y,z,"oak_leaves","vegetation",{"persistent":"true","distance":"1","waterlogged":"false"})
    f.features["photographed_hedge_interpreted_line"] = 1


def _accepted_frame_revision(f, p):
    """Repair only enumerated contacts in the hash-bound native baseline.

    The original facade generator remains available above. A reviewed study
    must not import unrelated changes from shared window/roof helpers while
    its remaining frame contacts are being repaired.
    """
    base = p["accepted_baseline"]
    archive_path = ROOT / base["archive"]
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != base["sha256"]:
        raise ValueError("Accepted Thomas baseline changed")
    manifest = json.loads((ROOT / base["manifest"]).read_text(encoding="utf-8"))
    bounds = [f.c.x_min, f.c.z_min, f.c.x_min + f.c.data.shape[2],
              f.c.z_min + f.c.data.shape[1]]
    if manifest["source_roof"]["world_bounds_blocks"] != bounds:
        raise ValueError("Thomas baseline grid differs from this study")
    with np.load(archive_path, allow_pickle=False) as archive:
        if tuple(str(v) for v in archive["role_names"]) != ROLES:
            raise ValueError("Thomas baseline role schema changed")
        xyz = archive["coords"]
        indexes = (xyz[:, 1] - f.c.y_min, xyz[:, 2] - f.c.z_min,
                   xyz[:, 0] - f.c.x_min)
        f.c.data.fill(0)
        f.c.roles.fill(0)
        f.c.data[indexes] = archive["state_ids"]
        f.c.roles[indexes] = archive["role_ids"]
        f.c.palette = json.loads(str(archive["palette_json"]))
        f.c.palette_lookup = {json.dumps(state, sort_keys=True): i
                              for i, state in enumerate(f.c.palette)}
    f.features.update(manifest["features"])
    f.features["hash_checked_accepted_baseline_preserved"] = 1

    def inside(position):
        x, y, z = position
        iz, ix = z - f.c.z_min, x - f.c.x_min
        return (f.r.footprint_mask[iz, ix]
                and (y + 1) / f.c.scale - f.offset <= f.r.heights[iz, ix] + .125)

    for joint in p["frame_contact_repair"]["jamb_returns"]:
        x, z = joint["return_xz"]
        px, pz = joint["pane_xz"]
        jx, jz = joint["jamb_xz"]
        for y in joint["ys"]:
            position = (x, y, z)
            if not inside(position) or f.c.get(*position):
                raise ValueError(f"Thomas return is not an empty inward cell: {position}")
            pane = f.c.palette[f.c.get(px, y, pz)]
            jamb = f.c.palette[f.c.get(jx, y, jz)]
            if not pane["Name"].endswith("_pane") or jamb["Name"] != "minecraft:bricks":
                raise ValueError(f"Thomas source pane/jamb changed: {joint}")
            if abs(x-px) + abs(z-pz) != 1 or abs(x-jx) + abs(z-jz) != 1:
                raise ValueError("Thomas return must contact both existing pane and jamb")
            f.c.set(*position, pane["Name"], "window", PANE_PROPS)
            f.features["final_inward_pane_to_jamb_returns"] += 1
    for cap in p["frame_contact_repair"]["caps"]:
        position = tuple(cap["xyz"])
        state = f.c.palette[f.c.get(*position)]
        x, y, z = position
        role = f.c.roles[y-f.c.y_min, z-f.c.z_min, x-f.c.x_min]
        if not inside(position) or state != cap["expected"] or role == ROLES.index("roof"):
            raise ValueError(f"Thomas cap repair is outside its exact bound: {position}")
        f.c.set(*position, cap["block"], cap["role"])
        f.features["final_full_frame_cap_cells"] += 1


def build_details(f,p):
    b=_source(p)
    if p.get("accepted_baseline"):
        _accepted_frame_revision(f, p)
        return
    _flat_end_coping(f)
    for row in p["window_rows"]:
        for centre in row["centres_m"]:
            _window(f,row["side"],row["at_m"],centre,row["sill_navd88_m"],row["width_m"],row["height_m"],row.get("shutters",False))
    for centre in p["west_entries_v_m"]:
        _pedimented_entry(f,centre,p["geometry"]["entrance_floor_navd88_m"])
    _dormer(f,p)
    # A single short red masonry chimney is visible above the main ridge.
    u,v=p["chimney"]["centre_uv_m"]
    f.box((u-.35,v-.35,u+.35,v+.35),64.1,65.05,"bricks","facade")
    f.box((u-.42,v-.42,u+.42,v+.42),65.0,65.25,"stone_brick_slab","trim",BOTTOM)
    for level in (55.75,58.65):
        f.floor_plate(level)
    _site(f,p)
    f.features.update(source_face_fingerprints_verified=len(b.roof_faces),
                      independently_photographed_facades=1,
                      interpreted_other_facades=3,
                      photographed_short_brick_chimney_interpreted_position=1,
                      exposed_stone_plinths=0)
