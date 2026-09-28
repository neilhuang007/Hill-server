"""Prepare source-bound core grounds with exact registered site overrides.

The plan is applied in memory through the production environment applicator.
Fresh source archives supply every block precondition; a survey supplies only
measured terrain references. Native review and whole-campus export are separate.
"""

import argparse
from collections import Counter
from functools import lru_cache
import gc
import hashlib
import heapq
import json
import math
from pathlib import Path
import shutil

import numpy as np
from scipy.ndimage import binary_dilation, binary_fill_holes, gaussian_filter, gaussian_filter1d, median_filter, label, distance_transform_edt
from shapely import contains_xy
from shapely.geometry import LineString, Polygon, Point

from assemble_hill_campus_studies import prepare_component
from audit_hill_quadrivium_contacts import shapes
from build_hill_chapel_sample import Canvas, ROLES
from campus_export_parity import read_archive
from campus_materials import audit_role_materials
from campus_study_io import digest, write_json
from refine_hill_campus_environment import apply_surface, apply_site_block, SITE_ROLES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "runtime/campus-reconstruction/core-demo-20260927/environment"
LEAVES = {"persistent": "true", "distance": "1", "waterlogged": "false"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_region(source, manifest, bounds):
    x0, z0, x1, z1 = bounds
    c = Canvas(x0, z0, x1-x0, z1-z0, 2)
    c.ground_heights = np.full((z1-z0, x1-x0), -320, np.int16)
    for spec in manifest["tiles"]:
        path = source / spec["path"] / "sample-blocks.npz"
        tx, tz = map(int, path.parent.name[1:].split("_z"))
        if tx >= x1 or tx+256 <= x0 or tz >= z1 or tz+256 <= z0:
            continue
        if digest(path) != spec["archive_sha256"]:
            raise ValueError(f"Changed source archive: {path}")
        a = read_archive(path)
        q = a["coords"]
        selected = (q[:,0]>=x0)&(q[:,0]<x1)&(q[:,2]>=z0)&(q[:,2]<z1)
        q = q[selected]
        x, y, z = (q-[x0,-64,z0]).T
        states = np.array([c.state(n, dict(p) if p else None) for n,p in a["palette_keys"]],np.uint16)
        roles = np.array([ROLES.index(n) for n in a["role_names"]],np.uint8)
        c.data[y,z,x] = states[a["state_ids"][selected]]
        r = roles[a["role_ids"][selected]]
        c.roles[y,z,x] = r
        site = np.isin(r, [ROLES.index("terrain"),ROLES.index("pavement")])
        np.maximum.at(c.ground_heights,(z[site],x[site]),q[site,1])
        del a, q, states, roles
        gc.collect()
    return c


def route_audit(c, features, planned):
    @lru_cache(maxsize=None)
    def occupied(x,y,z):
        if not (c.x_min <= x < c.x_min+c.data.shape[2] and c.z_min <= z < c.z_min+c.data.shape[1]):
            return ()
        state=c.palette[c.get(x,y,z)]
        if state["Name"] in {"minecraft:fern","minecraft:oxeye_daisy","minecraft:azure_bluet","minecraft:dandelion","minecraft:short_dry_grass","minecraft:tall_dry_grass"}:
            return ()
        return tuple((x+b[0]/16,y+b[1]/16,z+b[2]/16,x+b[3]/16,y+b[4]/16,z+b[5]/16)
                     for b in shapes(json.dumps(state,sort_keys=True)))
    rows=[]
    for feature in features:
        if "centerline_blocks" not in feature:
            continue
        line=LineString(feature["centerline_blocks"])
        heights=[]; errors=[]; locations=[]
        count=max(2,math.ceil(line.length/.1)+1)
        for d in np.linspace(0,line.length,count):
            p=line.interpolate(d); x,z=p.x,p.y
            ix,iz=math.floor(x)-c.x_min,math.floor(z)-c.z_min
            hint=float(c.ground_heights[iz,ix]+1)
            if feature.get("preserved_gallery_endpoint"):
                floor_ys=np.flatnonzero(c.roles[:,iz,ix]==ROLES.index("floor"))-64
                floors=[y+1 for y in floor_ys if hint<=y+1<=hint+12]
                if floors: hint=float(min(floors,key=lambda y:abs(y-feature["preserved_gallery_endpoint"]["feet_y_block"])))
            boxes=[]
            for xx in range(math.floor(x-.3),math.floor(x+.3)+1):
                for zz in range(math.floor(z-.3),math.floor(z+.3)+1):
                    for yy in range(math.floor(hint)-3,math.ceil(hint)+4):
                        boxes.extend(occupied(xx,yy,zz))
            accepted=None
            for feet in sorted({b[4] for b in boxes if abs(b[4]-hint)<=2},key=lambda y:abs(y-hint)):
                body=(x-.3,feet,z-.3,x+.3,feet+1.8,z+.3)
                support=0; collisions=0
                for b in boxes:
                    ov=[min(body[i+3],b[i+3])-max(body[i],b[i]) for i in range(3)]
                    collisions+=all(v>1e-7 for v in ov)
                    if abs(b[4]-feet)<1e-7:
                        support+=max(0,ov[0])*max(0,ov[2])
                if support>1e-7 and not collisions:
                    accepted=feet; break
            heights.append(accepted)
            locations.append([round(x,3),round(z,3)])
            if accepted is None:
                errors.append({"xz":[round(x,3),round(z,3)],"reason":"No supported player-sized standing position"})
        steps=[abs(a-b) for a,b in zip(heights,heights[1:]) if a is not None and b is not None]
        too_large=sum(v>.50001 for v in steps)
        if too_large: errors.append({"reason":"More than half-block step","count":too_large})
        rows.append({"name":feature["id"],"samples":count,"passed":not errors,
                     "maximum_sampled_step_blocks":max(steps,default=0),
                     "steps_above_half_block":sum(v>.50001 for v in steps),
                     "large_step_locations":[{"from":locations[i],"to":locations[i+1],"height_from":a,"height_to":b} for i,(a,b) in enumerate(zip(heights,heights[1:])) if a is not None and b is not None and abs(a-b)>.50001],"errors":errors})
    return {"passed":all(r["passed"] for r in rows),"routes":rows,
            "player":{"width_blocks":.6,"height_blocks":1.8,"sample_spacing_max_blocks":.1}}


def prepare(source, survey, controls_path, output, detail_controls_path=None, paths_only=False, fixture_addendum_path=None, route_addendum_path=None, native_touchup_path=None):
    if output.exists():
        raise FileExistsError("Choose a fresh plan output directory")
    output.mkdir(parents=True)
    m=read(source/"manifest.json"); controls=read(controls_path)
    touchups=read(native_touchup_path) if native_touchup_path else {}
    for evidence in touchups.get("inputs",[]):
        if digest(ROOT/evidence["path"])!=evidence["sha256"]: raise ValueError(f"Changed native touchup evidence: {evidence['path']}")
    detail_controls=read(detail_controls_path) if detail_controls_path else {}
    garden=detail_controls.get("south_ryan_class_1971_garden",detail_controls)
    if paths_only: garden={"path_corridors":garden.get("path_corridors",[])}
    for item in garden.get("fixtures",[]): item["_source_path"]=detail_controls_path
    if fixture_addendum_path:
        patch=read(fixture_addendum_path)
        if digest(ROOT/patch["base"]["path"])!=patch["base"]["sha256"]: raise ValueError("Fixture addendum base changed")
        replacements={p["id"]:{**p,"world_blocks":p["preferred_world_blocks"],"world_block_polygon":p["build_footprint_world_block_polygon"],"_source_path":fixture_addendum_path} for p in patch["fixtures"]}
        garden["fixtures"]=[replacements.get(p["id"],p) for p in garden.get("fixtures",[])]
        bed=patch["planting_bed_patch"]
        garden["planting_beds"]=[bed if p["id"]==bed["id"] else p for p in garden.get("planting_beds",[])]
    added_paths=garden.get("path_corridors",[])
    for correction in touchups.get("path_endpoint_corrections",[]):
        control=next(p for p in added_paths if p["id"]==correction["feature"])
        if control["world_blocks"][-1]!=correction["registered_endpoint_xz"]: raise ValueError("Unexpected source path endpoint")
        control["world_blocks"].append(correction["actual_north_curb_xz"])
    if route_addendum_path:
        route_patch=read(route_addendum_path)
        endpoint=route_patch["accepted_gallery_endpoint"]
        endpoint_profile=ROOT/Path(endpoint["source"]).parent/"profile.json"
        frame=read(endpoint_profile)["geometry"]
        angle=math.radians(frame["axis_degrees"]); ox,oz=frame["origin_xz_m"]; u,v=endpoint["local_uv_outer_endpoint_m"]
        exact_endpoint=[2*(ox+u*math.cos(angle)-v*math.sin(angle)),2*(oz+u*math.sin(angle)+v*math.cos(angle))]
        for p in route_patch["path_corridors"]:
            points=[list(q) for q in p["world_blocks"]]
            points[0]=exact_endpoint
            added_paths.append({**p,"world_blocks":points,"preserved_gallery_endpoint":route_patch["accepted_gallery_endpoint"]})
    added_path_ids={a["id"] for a in added_paths}
    cross_path=DEFAULT/"cross-feature-controls-v1.json"
    cross=read(cross_path)
    scope=Polygon(controls["bounded_scope"]["world_block_polygon"])
    x0,z0,x1,z1=map(int,scope.bounds)
    c=load_region(source,m,(x0,z0,x1,z1))
    zz,xx=np.indices(c.ground_heights.shape); x=xx+x0; z=zz+z0
    inside=contains_xy(scope,x+.5,z+.5)
    arch=np.any(~np.isin(c.roles,list(SITE_ROLES)),axis=0)
    owned=np.zeros(arch.shape,bool); ownership=[]
    for spec in m["components"]:
        sx,sz=spec["x_min"],spec["z_min"]
        sy,sd,sw=spec["shape"]
        left,top,right,bottom=max(x0,sx),max(z0,sz),min(x1,sx+sw),min(z1,sz+sd)
        if left>=right or top>=bottom: continue
        part=prepare_component(Path(spec["study"]),ROOT/"runtime/campus-reconstruction/component-cache",2,-25,spec["margin_m"])
        mask=part.mask[top-sz:bottom-sz,left-sx:right-sx]
        owned[top-z0:bottom-z0,left-x0:right-x0]|=mask
        ownership.append({"study":spec["study"],"archive_sha256":spec["archive_sha256"],"protected_columns_in_scope":int(mask.sum())})
        del part
    excluded=np.zeros(arch.shape,bool)
    for zone in controls["hard_exclusion_zones"]:
        excluded|=contains_xy(Polygon(zone["world_block_polygon"]).buffer(1),x+.5,z+.5)
    # The building specialist owns the complete north terrace as well as court.
    terrace=next(p for p in controls["planting_beds"] if p["id"]=="athey_court_raised_north_bed")
    excluded|=contains_xy(Polygon(terrace["world_block_polygon"]).buffer(1),x+.5,z+.5)
    safe=inside&~arch&~owned&~excluded
    ground=c.ground_heights.copy()
    surface=c.data[ground+64,zz,xx]
    names=np.array([p["Name"] for p in c.palette])
    ns=names[surface]
    half=np.array([p["Name"].endswith("_slab") and p.get("Properties",{}).get("type")=="bottom" for p in c.palette])
    tops=ground+1-half[surface]*.5
    road=np.char.startswith(ns,"minecraft:polished_deepslate")
    paving=(c.roles[ground+64,zz,xx]==ROLES.index("pavement"))
    grass=np.isin(ns,["minecraft:grass_block","minecraft:dirt"])
    with np.load(survey) as a:
        bx,bz,_,_=map(int,a["bounds"])
        expected=a["expected"][z0-bz:z1-bz,x0-bx:x1-bx].copy()+1
    plans={}; blocks={}; features=[]; blocked=[]; notes=[]; override_columns={}

    def put_surface(ix,iz,height,full,slab,feature,role="pavement",max_delta=2,allow_owned=False):
        if not (safe[iz,ix] or (allow_owned and inside[iz,ix] and not arch[iz,ix] and not excluded[iz,ix])): return False
        height=round(float(height)*2)/2 if slab else round(float(height))
        y=math.ceil(height)-1
        state={"Name":"minecraft:"+(full if height==int(height) else slab)}
        if height!=int(height): state["Properties"]={"type":"bottom","waterlogged":"false"}
        action={"x":int(ix+x0),"z":int(iz+z0),"y":y,"state":state,"role":role,"feature":feature,"max_delta_blocks":max_delta}
        if state==c.palette[c.get(action["x"],y,action["z"])] and y==c.ground_heights[iz,ix] and ROLES[int(c.roles[y+64,iz,ix])]==role:
            return False
        try: apply_surface(c,action)
        except ValueError as error:
            blocked.append({"action":action,"reason":str(error)}); return False
        plans[action["x"],action["z"]]=action
        if owned[iz,ix]: override_columns[action["x"],action["z"]]=feature
        return True

    def put_block(px,py,pz,name,role,feature,props=None,allow_owned=False):
        ix,iz=px-x0,pz-z0
        if not (0<=ix<c.data.shape[2] and 0<=iz<c.data.shape[1]): return False
        if not (safe[iz,ix] or (allow_owned and inside[iz,ix] and not arch[iz,ix] and not excluded[iz,ix])): return False
        old=c.palette[c.get(px,py,pz)]
        state={"Name":"minecraft:"+name,**({"Properties":props} if props else {})}
        if old==state: return False
        # Never grow a plant or post through existing plants or another fixture.
        if old["Name"]!="minecraft:air": return False
        action={"xyz":[px,py,pz],"before":old,"before_role":ROLES[int(c.roles[py+64,iz,ix])],"state":state,"role":role,"feature":feature}
        apply_site_block(c,action,arch)
        blocks[px,py,pz]=action
        if owned[iz,ix]: override_columns[px,pz]=feature
        return True

    # These exact columns were inspected in native captures and compared with
    # their surrounding terrain. They are not a general smoothing operation.
    for fix in touchups.get("terrain_columns",[]):
        px,pz=fix["xz"]; ix,iz=px-x0,pz-z0
        gy=int(c.ground_heights[iz,ix]); state=c.palette[c.get(px,gy,pz)]
        if gy!=fix["source_y"] or state!=fix["source_state"]:
            raise ValueError(f"Native terrain precondition changed at {px},{pz}: {gy}, {state}")
        if not put_surface(ix,iz,fix["target_y"]+1,"grass_block",None,fix["feature"],"terrain",1,allow_owned=True):
            raise ValueError(f"Protected native terrain correction: {px},{pz}")

    # Preserve the original asphalt footprint, and close only enclosed <=4-cell
    # pockets. No bed or source path is classified as a road hole.
    road_holes=binary_fill_holes(road)&~road&grass
    labels,n=label(road_holes)
    sizes=np.bincount(labels.ravel())
    road_holes&=sizes[labels]<=4
    road_work=(road|road_holes)&safe
    weight=gaussian_filter(road.astype(float),1.4)
    smooth=gaussian_filter(tops*road,1.4)/np.maximum(weight,1e-6)
    # Preserve engineered heights: only gentle corrections to already surfaced
    # roads; adjacent protected road levels constrain the same interpolation.
    smooth=np.clip(smooth,tops-1,tops+1)
    for iz,ix in np.argwhere(road_work):
        put_surface(ix,iz,smooth[iz,ix],"polished_deepslate","polished_deepslate_slab","existing_measured_road_grade_and_pockets",max_delta=1)
    features.append({"id":"existing_measured_road_grade_and_pockets","existing_road_columns":int((road&safe).sum()),"enclosed_small_pockets":int((road_holes&safe).sum()),"maximum_correction_blocks":1,"evidence":"Existing exact v14 pavement footprint within source full-core bounds; normalized local grade smoothing, no footprint expansion except enclosed <=4-cell pockets."})

    path_union=np.zeros(safe.shape,bool)
    for control in [*controls["path_corridors"],*added_paths]:
        if control["id"] in {"athey_main_approach","athey_terrace_front","dining_west_drive_join"}:
            notes.append({"id":control["id"],"status":"Building-owned approach preserved; builder handles north terrace/court"}); continue
        line=LineString(control["world_blocks"])
        corridor=contains_xy(line.buffer(control["width_blocks"]/2,cap_style=2,join_style=2),x+.5,z+.5)
        path_union|=corridor
        ds=np.linspace(0,line.length,max(2,math.ceil(line.length*2)+1))
        points=np.array([(line.interpolate(d).x,line.interpolate(d).y) for d in ds])
        sx=np.floor(points[:,0]).astype(int)-x0; sz=np.floor(points[:,1]).astype(int)-z0
        source_heights=tops[sz,sx].copy()
        if control.get("preserved_gallery_endpoint"):
            endpoint_height=control["preserved_gallery_endpoint"]["feet_y_block"]
            source_heights[arch[sz,sx]]=endpoint_height
            n=min(len(ds)-1,int(np.searchsorted(ds,8)))
            source_heights[:n+1]=np.linspace(endpoint_height,source_heights[n],n+1)
        hs=gaussian_filter1d(source_heights,2)
        hs[0]=source_heights[0]; hs[-1]=source_heights[-1]
        # Median removes one-cell contour defects, while retaining measured
        # longitudinal slopes and immutable component thresholds.
        eligible=safe if control["id"] not in added_path_ids else inside&~arch&~excluded
        for iz,ix in np.argwhere(corridor&eligible):
            d=line.project(Point(ix+x0+.5,iz+z0+.5))
            height=float(np.interp(d,ds,hs))
            if abs(height-tops[iz,ix])>2:
                blocked.append({"feature":control["id"],"xz":[int(ix+x0),int(iz+z0)],"reason":"Source corridor grade differs over two blocks; preserve terrain"}); continue
            brick="red" in control["surface"]
            put_surface(ix,iz,height,"bricks" if brick else "smooth_stone","brick_slab" if brick else "smooth_stone_slab",control["id"],allow_owned=control["id"] in added_path_ids)
        features.append({"id":control["id"],"centerline_blocks":control["world_blocks"],"width_blocks":control["width_blocks"],"endpoint_tops_blocks":[float(hs[0]),float(hs[-1])],"confidence":control["confidence"],"component_owned_columns_in_corridor":int((corridor&owned).sum()),"source_registered_site_override_allowed":control["id"] in added_path_ids})
        if control.get("preserved_gallery_endpoint"): features[-1]["preserved_gallery_endpoint"]=control["preserved_gallery_endpoint"]

    # Outer roads are routes on their observed surface, not new authored lines.
    # The controls explicitly allow existing-surface seam repairs in these zones.
    for zone in controls["surface_cleanup_zones"]:
        mask=contains_xy(Polygon(zone["world_block_polygon"]),x+.5,z+.5)
        notes.append({"id":zone["id"],"existing_pavement_columns":int((mask&paving).sum()),"road_columns_regraded":sum(bool(mask[a["z"]-z0,a["x"]-x0]) and a["feature"]=="existing_measured_road_grade_and_pockets" for a in plans.values())})

    # Correct the low member of an isolated one-block pavement seam. This is
    # permitted inside inherited component site only when the exact source
    # corridor contains it and its all-height column is nonarchitectural.
    before_routes=route_audit(c,features,plans)
    for row in before_routes["routes"]:
        for step in row["large_step_locations"]:
            low_point=step["to"] if step["height_from"]>step["height_to"] else step["from"]
            low=step["height_to"] if step["height_from"]>step["height_to"] else step["height_from"]
            ix,iz=math.floor(low_point[0])-x0,math.floor(low_point[1])-z0
            if not path_union[iz,ix] or not paving[iz,ix] or arch[iz,ix] or excluded[iz,ix]: continue
            sy=int(c.ground_heights[iz,ix]); state=c.palette[c.get(ix+x0,sy,iz+z0)]
            top=sy+(0.5 if state["Name"].endswith("_slab") else 1)
            if abs(top-low)<1e-6:
                brick="brick" in state["Name"]
                put_surface(ix,iz,low+.5,"bricks" if brick else "smooth_stone","brick_slab" if brick else "smooth_stone_slab","core_route_half_block_seam",allow_owned=True)

    # Add independent outer-road traversal probes by following the center of
    # current pavement. Their derived lines are read-only audit routes.
    traversable=(road|(paving&binary_dilation(road,iterations=10)))&~arch&~excluded
    clearance=distance_transform_edt(road)
    def road_route(name,start,end):
        candidates=np.argwhere(traversable)
        def nearest(p):
            q=candidates[np.argmin((candidates[:,1]+x0-p[0])**2+(candidates[:,0]+z0-p[1])**2)]
            return tuple(map(int,q))
        a,b=nearest(start),nearest(end); queue=[(0,a)]; previous={a:None}; costs={a:0}
        while queue:
            cost,q=heapq.heappop(queue)
            if q==b: break
            if cost!=costs[q]: continue
            for dz,dx in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                r=(q[0]+dz,q[1]+dx)
                if not (0<=r[0]<traversable.shape[0] and 0<=r[1]<traversable.shape[1] and traversable[r]): continue
                new=cost+math.hypot(dx,dz)*(1+3/(clearance[r]+.5))
                if new<costs.get(r,1e30): costs[r]=new; previous[r]=q; heapq.heappush(queue,(new,r))
        if b not in previous:
            notes.append({"id":name,"status":"No continuous existing-pavement road connection"}); return
        path=[]; q=b
        while q is not None:
            path.append([q[1]+x0+.5,q[0]+z0+.5]); q=previous[q]
        path.reverse()
        points=list(map(list,LineString(path).simplify(.3).coords))
        features.append({"id":name,"centerline_blocks":points,"endpoint_tops_blocks":[float(tops[a]),float(tops[b])],"interpretation":"Read-only route derived from current connected road mask, favoring maximum road clearance; not a new authored path."})
    road_route("chapel_north_west_existing_drive",[-69,-31],[-34,-88])
    road_route("chapel_south_to_dining_west_existing_drive",[-64,64],[49,139])
    road_route("dining_south_existing_drive",[-64,206],[147,237])
    road_route("quadrivium_north_to_ryan_east_existing_drive",[180,170],[337,40])
    road_route("ryan_east_to_north_existing_drive",[337,40],[262,-11])

    # Source-supported cross-feature seam: the old campus leaves one grass
    # column between two otherwise adjoining Chapel paving branches.
    for seam in cross["paving_seams"]:
        for px,pz in seam["retained_neighbor_columns_xz"]:
            gy=int(c.ground_heights[pz-z0,px-x0]); state=c.palette[c.get(px,gy,pz)]
            top=gy+(.5 if state["Name"].endswith("_slab") else 1)
            if state["Name"]!=seam["expected_neighbor_surface"] or top!=seam["physical_top_blocks"]:
                raise ValueError(f"Source-bound Chapel seam neighbors changed: {px},{pz}")
        for px,pz in seam["columns_xz"]:
            put_surface(px-x0,pz-z0,seam["physical_top_blocks"],"smooth_stone","smooth_stone_slab",seam["id"],allow_owned=True)
        for n,(_,pz) in enumerate(seam["columns_xz"]):
            features.append({"id":seam["id"]+f"_{n+1}","centerline_blocks":[[17.5,pz+.5],[19.5,pz+.5]],"endpoint_tops_blocks":[83.5,83.5],"width_blocks":1,"evidence":cross_path.relative_to(ROOT).as_posix()})

    # The source seating envelope contains both the brick bay and its planted
    # island. Keep the registered pale routes continuous through the bay.
    detail_beds=[]
    for item in garden.get("planting_layers",garden.get("planting_beds",[])):
        polygon=item.get("world_block_polygon",item.get("world_block_envelope"))
        if polygon:
            detail_beds.append({**item,"world_block_polygon":polygon,
                                "height_m":item.get("height_m",[v/2 for v in item.get("height_blocks",[1,2])])})
        else:
            notes.append({"id":item["id"],"status":"Source audit envelope only; no invented bed footprint"})
    detail_bed_mask=np.zeros(safe.shape,bool)
    for item in detail_beds:
        detail_bed_mask|=contains_xy(Polygon(item["world_block_polygon"]),x+.5,z+.5)
    detail_bays=garden.get("paved_bays",[garden.get("seating_bay"),garden.get("pavilion_approach")])
    for item in detail_bays:
        if not item: continue
        polygon=item.get("world_block_polygon",item.get("world_block_envelope"))
        raw=contains_xy(Polygon(polygon),x+.5,z+.5)
        mask=raw&inside&~arch&~excluded&~path_union&~detail_bed_mask
        # A one-block-wide pale perimeter keeps the source curve visible.
        edge=raw&binary_dilation(~raw,iterations=1)
        bay_height=round(float(np.median(tops[mask]))*2)/2 if mask.any() else 0
        for iz,ix in np.argwhere(mask):
            height=bay_height if "seating" in item["id"] else tops[iz,ix]
            if abs(height-tops[iz,ix])>2: continue
            brick="seating" in item["id"] and not edge[iz,ix]
            put_surface(ix,iz,height,"mud_bricks" if brick else "smooth_stone","mud_brick_slab" if brick else "smooth_stone_slab",item["id"],allow_owned=True)
        notes.append({"id":item["id"],"source_polygon_columns":int(raw.sum()),"eligible_paving_columns":int(mask.sum()),"clipped_architecture":int((raw&arch).sum()),"clipped_registered_walks":int((raw&path_union).sum())})

    # Resolve ordinary furniture against the registered source footprints before
    # planting. Every final fixture cell is separately registered for the study
    # difference proof; a tolerance never expands the source polygon.
    fixture_jobs=[]; fixture_rows=[]; registered_details=[]
    fixture_reserve=np.zeros(safe.shape,bool)
    fixture_route_clear=np.zeros(safe.shape,bool)
    for control in [*controls["path_corridors"],*added_paths]:
        if control["id"] in {"athey_main_approach","athey_terrace_front","dining_west_drive_join"}: continue
        fixture_route_clear|=contains_xy(LineString(control["world_blocks"]).buffer(control["width_blocks"]/2+.4,cap_style=2,join_style=2),x+.5,z+.5)
    # The memorial sits flush with the adjacent bay rather than on isolated
    # high dirt footings. Grade only the registered bed, at most half a metre.
    flush_beds={}
    for bed in detail_beds:
        if "memorial" not in bed["id"] and "seating_island" not in bed["id"]: continue
        flush_beds[bed["id"]]=87
        mask=contains_xy(Polygon(bed["world_block_polygon"]),x+.5,z+.5)&inside&~arch&~excluded&~binary_dilation(path_union|paving,iterations=1)
        for iz,ix in np.argwhere(mask):
            put_surface(ix,iz,87,"coarse_dirt",None,bed["id"]+"_flush_mulch","terrain",1,allow_owned=True)
    fence_props={"east":"false","west":"false","north":"false","south":"false","waterlogged":"false"}
    for item in garden.get("fixtures",[]):
        kind=item["type"]; ident=item["id"]; poly=Polygon(item["world_block_polygon"])
        cells=[]
        if "bench" in kind:
            start,end=item["endpoint_world_blocks"]; length=item["furniture_length_blocks"]
            tx,tz=math.floor(min(start[0],end[0])),math.floor(start[1])
            facing="north" if item["facing"]=="+Z" else "south"
            back_facing="south" if facing=="north" else "north"
            for dx in range(length):
                cells.extend([(dx,0,0,"oak_stairs","furniture",{"facing":facing,"half":"top","shape":"straight","waterlogged":"false"}),
                              (dx,1,0,"oak_trapdoor","furniture",{"facing":back_facing,"half":"bottom","open":"true","powered":"false","waterlogged":"false"})])
        elif "lantern" in kind:
            tx,tz=item["world_blocks"]
            cells=[(0,h,0,"dark_oak_fence","furniture",fence_props) for h in range(4)]
            cells.append((0,4,0,"lantern","lighting",{"hanging":"false","waterlogged":"false"}))
        elif "flagpole" in kind:
            tx,tz=item["world_blocks"]
            cells=[(0,h,0,"iron_bars","fixture",fence_props) for h in range(12)]
        elif "bell" in kind:
            tx,tz=item["world_blocks"]
            frame=set()
            for dz in (-1,1):
                frame.update((dx,h,dz) for dx in (-2,2) for h in range(3))
                frame.update((dx,2,dz) for dx in (-1,1))
                frame.update((dx,3,dz) for dx in (-1,0,1))
            for dx,h,dz in sorted(frame):
                props={direction:str((dx+sx,h,dz+sz) in frame).lower() for direction,sx,sz in [("east",1,0),("west",-1,0),("north",0,-1),("south",0,1)]}
                props["waterlogged"]="false"
                cells.append((dx,h,dz,"iron_bars","fixture",props))
            cells.extend([(0,3,0,"black_concrete","fixture",None),(0,2,0,"bell","fixture",{"attachment":"ceiling","facing":"north","powered":"false"})])
        else:
            fixture_rows.append({"id":ident,"status":"unsupported source fixture type"}); continue
        columns={(dx,dz) for dx,_,dz,*_ in cells}
        tolerance=int(item.get("placement_tolerance_blocks",0))
        offsets=sorted(((dx,dz) for dx in range(-tolerance,tolerance+1) for dz in range(-tolerance,tolerance+1) if dx*dx+dz*dz<=tolerance*tolerance),key=lambda q:(q[0]**2+q[1]**2,q))
        selected=None
        for ox,oz in offsets:
            positions=[(tx+ox+dx,tz+oz+dz) for dx,dz in columns]
            if any(not poly.covers(Point(px+.5,pz+.5)) or not (x0<=px<x1 and z0<=pz<z1) for px,pz in positions): continue
            if any(arch[pz-z0,px-x0] or excluded[pz-z0,px-x0] or fixture_route_clear[pz-z0,px-x0] or fixture_reserve[pz-z0,px-x0] for px,pz in positions): continue
            heights=[]
            for px,pz in positions:
                gy=int(c.ground_heights[pz-z0,px-x0]); st=c.palette[c.get(px,gy,pz)]
                heights.append(gy+(.5 if st["Name"].endswith("_slab") and st.get("Properties",{}).get("type")=="bottom" else 1))
            base=math.ceil(float(max(heights)))
            if max(abs(base-h) for h in heights)>1: continue
            if any(c.get(tx+ox+dx,base+dy,tz+oz+dz) for dx,dy,dz,*_ in cells): continue
            selected=(ox,oz,base,positions); break
        if selected is None:
            fixture_rows.append({"id":ident,"status":"omitted: no source-footprint placement clear of routes, architecture and existing objects"}); continue
        ox,oz,base,positions=selected
        for px,pz in positions:
            ix,iz=px-x0,pz-z0
            gy=int(c.ground_heights[iz,ix]); st=c.palette[c.get(px,gy,pz)]
            full="mud_bricks" if "bench" in kind or "brick" in st["Name"] else ("smooth_stone" if ROLES[int(c.roles[gy+64,iz,ix])]=="pavement" else "coarse_dirt")
            role="terrain" if full=="coarse_dirt" else "pavement"
            put_surface(ix,iz,base,full,None,ident+"_supported_base",role,max_delta=1,allow_owned=True)
            fixture_reserve[iz,ix]=True
        fixture_jobs.append((item,[(tx+ox+dx,base+dy,tz+oz+dz,name,role,props) for dx,dy,dz,name,role,props in cells]))
        fixture_rows.append({"id":ident,"status":"placed","registered_center_or_start_xz":[tx,tz],"placement_offset_blocks":[ox,oz],"supported_base_y":base,"planned_cells":len(cells)})

    # Beds keep every existing paved cell and one block of route clearance.
    path_clear=binary_dilation(path_union|paving,iterations=1)
    path_clear|=binary_dilation(fixture_reserve,iterations=1)
    chapel_clear=cross["chapel_entry_clearance"]
    u0,v0,u1,v1=chapel_clear["planting_exclusion_local_uv_m"]
    angle=math.radians(8.5)
    corners=[(2*(u*math.cos(angle)-v*math.sin(angle)),2*(u*math.sin(angle)+v*math.cos(angle))) for u,v in [(u0,v0),(u1,v0),(u1,v1),(u0,v1)]]
    path_clear|=contains_xy(Polygon(corners).buffer(chapel_clear["player_buffer_blocks"]),x+.5,z+.5)
    bed_masks=[]
    for bed in [*controls["planting_beds"],*detail_beds]:
        if bed["id"]=="athey_court_raised_north_bed": continue
        geom=Polygon(bed["world_block_polygon"])
        raw=contains_xy(geom,x+.5,z+.5)
        mask=raw&inside&~arch&~excluded&~path_clear
        bed_masks.append((bed,mask))
        for iz,ix in np.argwhere(mask):
            put_surface(ix,iz,flush_beds.get(bed["id"],ground[iz,ix]+1),"coarse_dirt",None,bed["id"]+"_mulch","terrain",1 if bed["id"] in flush_beds else 0,allow_owned=True)
        seed=int(hashlib.sha256(bed["id"].encode()).hexdigest()[:8],16)
        rng=np.random.default_rng(seed)
        eligible=list(np.argwhere(mask))
        rng.shuffle(eligible)
        centers=[]
        for iz,ix in eligible:
            if all((ix-a)**2+(iz-b)**2>=16 for a,b in centers): centers.append((int(ix),int(iz)))
        max_height=max(1,min(3,round(bed["height_m"][1]*2)))
        if "memorial" in bed["id"]: centers=[]
        if "seating_island" in bed["id"]:
            candidates=[(int(ix),int(iz)) for iz,ix in eligible]
            best=[]; score=-1
            for first in candidates:
                trial=[first]
                while len(trial)<6:
                    q=max(candidates,key=lambda p:min((p[0]-a)**2+(p[1]-b)**2 for a,b in trial))
                    if q in trial: break
                    trial.append(q)
                spacing=min((a[0]-b[0])**2+(a[1]-b[1])**2 for i,a in enumerate(trial) for b in trial[i+1:])
                if spacing>score: best=trial; score=spacing
            if len(best)!=6 or score<16: raise ValueError("Seating island cannot fit six separated source shrubs")
            centers=best
        for ix,iz in centers:
            radius=1.25 if "seating_island" in bed["id"] else float(rng.uniform(1.3,2.5))
            h=int(rng.integers(1,max_height+1))
            for j in range(max(0,iz-3),min(mask.shape[0],iz+4)):
                for i in range(max(0,ix-3),min(mask.shape[1],ix+4)):
                    r=((i-ix)**2+(j-iz)**2)/radius**2
                    if not mask[j,i] or r>=1: continue
                    height=max(1,round(h*math.sqrt(1-r)))
                    base=int(c.ground_heights[j,i])+1
                    for yb in range(base,base+height):
                        put_block(int(i+x0),yb,int(j+z0),"oak_leaves","vegetation",bed["id"]+"_shrubs",LEAVES,allow_owned=True)
        if "seating_island" in bed["id"]:
            grass_centers=[]
            for iz,ix in eligible:
                if len(grass_centers)>=3: break
                if c.get(int(ix+x0),int(c.ground_heights[iz,ix])+1,int(iz+z0)): continue
                if any((ix-a)**2+(iz-b)**2<16 for a,b in grass_centers): continue
                grass_centers.append((int(ix),int(iz)))
            for gx,gz in grass_centers:
                for iz,ix in eligible:
                    if (ix-gx)**2+(iz-gz)**2<=3:
                        put_block(int(ix+x0),int(c.ground_heights[iz,ix])+1,int(iz+z0),"short_dry_grass","vegetation",bed["id"]+"_pale_grass_clumps",allow_owned=True)
        for iz,ix in eligible:
            density=11 if "seating_island" in bed["id"] else 23
            if (int(ix)*37+int(iz)*61+seed)%density==0:
                plant=("fern","oxeye_daisy","azure_bluet","fern","dandelion")[(int(ix)+int(iz)+seed)%5]
                put_block(int(ix+x0),int(c.ground_heights[iz,ix])+1,int(iz+z0),plant,"vegetation",bed["id"]+"_perennials",allow_owned=True)
        notes.append({"id":bed["id"],"source_polygon_columns":int(raw.sum()),"eligible_mulch_columns":int(mask.sum()),"source_bed_owned_columns_authorized":int((mask&owned).sum()),"clipped_architecture":int((raw&arch).sum()),"clipped_paving_clearance":int((raw&path_clear).sum()),"shrub_clumps":len(centers)})

    for item,cells in fixture_jobs:
        authored=[]
        for px,py,pz,name,role,props in cells:
            if not put_block(px,py,pz,name,role,item["id"],props,allow_owned=True):
                raise ValueError(f"Registered fixture placement changed after planning: {item['id']} {px},{py},{pz}")
            authored.append([px,py,pz])
        registered_details.append({"id":item["id"],"source_path":item["_source_path"].relative_to(ROOT).as_posix(),"source_collection":"fixtures","source_record_id":item["id"],"authored_cells_xyz":authored})

    # These existing leaves mask air in the accepted Chapel entry study. Their
    # removal is exact and source-bound, not a general vegetation clearing mask.
    chapel_source=read_archive(ROOT/chapel_clear["source_study"]/"sample-blocks.npz")
    for px,py,pz in chapel_clear["clear_cells_xyz"]:
        selected=np.all(chapel_source["coords"]==[px,py,pz],axis=1)
        if selected.any():
            sid=int(chapel_source["state_ids"][selected][0])
            if chapel_source["palette_keys"][sid][0]!=chapel_clear["expected_study_state"]:
                raise ValueError("Chapel clearance source is not accepted air")
        iz,ix=pz-z0,px-x0
        current=c.palette[c.get(px,py,pz)]
        if current["Name"]=="minecraft:air": continue
        if current["Name"]!=chapel_clear["eligible_campus_before"] or arch[iz,ix]:
            raise ValueError(f"Unreviewed Chapel entry clearance conflict: {px},{py},{pz}")
        action={"xyz":[px,py,pz],"before":current,"before_role":ROLES[int(c.roles[py+64,iz,ix])],"state":{"Name":"minecraft:air"},"role":"air","feature":chapel_clear["id"]}
        apply_site_block(c,action,arch); blocks[px,py,pz]=action
        if owned[iz,ix]: override_columns[px,pz]=action["feature"]
    del chapel_source

    tree_rows=[]
    for tree in controls["trees"]:
        tx,tz=tree["world_blocks"]; ix,iz=tx-x0,tz-z0
        trunk=[y for y in range(int(ground[iz,ix]),min(319,int(ground[iz,ix]+tree["height_m"]*2+3))) if c.palette[c.get(tx,y,tz)]["Name"].endswith("_log")]
        if tree["mode"].startswith("enhance_existing"):
            # New low planting improves the setting; do not duplicate crowns.
            gy=int(c.ground_heights[iz,ix]); gs=c.palette[c.get(tx,gy,tz)]
            actual_top=gy+(.5 if gs["Name"].endswith("_slab") and gs.get("Properties",{}).get("type")=="bottom" else 1)
            if trunk and min(trunk)-actual_top==.5 and not arch[iz,ix] and not excluded[iz,ix]:
                # One inherited ornamental tree begins above a bottom paving
                # slab. Close its exact half-block root gap without relocating
                # the registered tree or changing adjacent walkway columns.
                replacements={"minecraft:smooth_stone_slab":"minecraft:smooth_stone","minecraft:stone_brick_slab":"minecraft:stone_bricks","minecraft:brick_slab":"minecraft:bricks"}
                if gs["Name"] in replacements:
                    action={"xyz":[tx,gy,tz],"before":gs,"before_role":ROLES[int(c.roles[gy+64,iz,ix])],"state":{"Name":replacements[gs["Name"]]},"role":ROLES[int(c.roles[gy+64,iz,ix])],"feature":tree["id"]+"_root_contact"}
                    apply_site_block(c,action,arch); blocks[tx,gy,tz]=action
                    if owned[iz,ix]: override_columns[tx,tz]=action["feature"]
                    actual_top=gy+1
            tree_rows.append({"id":tree["id"],"mode":"retained_existing","trunk_blocks_at_registered_column":len(trunk),"trunk_bottom":min(trunk) if trunk else None,"ground_top":float(actual_top),"new_tree_blocks":0,"trunk_supported":bool(trunk and min(trunk)<=actual_top)})
            continue
        radius=tree["crown_radius_m"]*2
        trunk_clear=Point(tx+.5,tz+.5).buffer(2)
        trunk_mask=contains_xy(trunk_clear,x+.5,z+.5)
        reason=None
        if not safe[iz,ix] or np.any(trunk_mask&(~safe|path_clear)): reason="Registered trunk is in protected ownership, paving, or path clearance"
        if any((tx-t["world_blocks"][0])**2+(tz-t["world_blocks"][1])**2<(radius+t["crown_radius_m"]*2)**2 for t in controls["trees"] if t["mode"].startswith("enhance_existing")):
            reason="Candidate crown overlaps an already-registered tree; no duplicate crown"
        if reason:
            tree_rows.append({"id":tree["id"],"mode":"omitted_candidate","reason":reason}); continue
        base=int(c.ground_heights[iz,ix])+1; height=round(tree["height_m"]*2)
        before=len(blocks)
        for yb in range(base,base+height-2): put_block(tx,yb,tz,"oak_log","vegetation",tree["id"],{"axis":"y"})
        cy=base+height-radius*.65
        for pz in range(math.floor(tz-radius),math.ceil(tz+radius)+1):
            for px in range(math.floor(tx-radius),math.ceil(tx+radius)+1):
                if not (x0<=px<x1 and z0<=pz<z1): continue
                for py in range(max(base+5,math.floor(cy-radius*.7)),base+height+1):
                    norm=((px-tx)/radius)**2+((pz-tz)/(radius*.87))**2+((py-cy)/(radius*.72))**2
                    if norm<1+.07*math.sin(px*1.7+pz*.4+py*.8):
                        put_block(px,py,pz,"oak_leaves","vegetation",tree["id"],LEAVES)
        tree_rows.append({"id":tree["id"],"mode":"new_source_candidate","new_tree_blocks":len(blocks)-before,"trunk_base_y":base,"height_blocks":height,"crown_radius_blocks":radius})

    lamp_rows=[]
    for n,lamp in enumerate(controls["quadrivium_frontage_lamps"]):
        tx,tz=lamp["world_blocks"]; ix,iz=tx-x0,tz-z0
        if not safe[iz,ix] or path_union[iz,ix] or road[iz,ix]:
            lamp_rows.append({"xz":[tx,tz],"status":"omitted: protected column or route"}); continue
        base=int(c.ground_heights[iz,ix])+1
        if any(c.get(tx,y,tz) for y in range(base,base+6)):
            lamp_rows.append({"xz":[tx,tz],"status":"omitted: existing vegetation or fixture"}); continue
        for yb in range(base,base+4):
            put_block(tx,yb,tz,"dark_oak_fence","furniture",f"quadrivium_lamp_{n+1}",{"east":"false","west":"false","north":"false","south":"false","waterlogged":"false"})
        put_block(tx,base+4,tz,"lantern","lighting",f"quadrivium_lamp_{n+1}",{"hanging":"false","waterlogged":"false"})
        lamp_rows.append({"xz":[tx,tz],"status":"placed","base_y":base,"height_blocks":5})

    # The registered east-gallery corridor skirts retained stair rails. Derive
    # its actual walking probe within that same paved corridor, never through
    # a protected rail or by extending paving across an unregistered lawn.
    for feature in features:
        if not feature.get("preserved_gallery_endpoint"): continue
        source_line=LineString(feature["centerline_blocks"])
        probe_mask=contains_xy(source_line.buffer(feature["width_blocks"]/2,cap_style=1),x+.5,z+.5)
        @lru_cache(maxsize=None)
        def boxes_at(px,py,pz):
            if not (x0<=px<x1 and z0<=pz<z1): return ()
            st=c.palette[c.get(px,py,pz)]
            if st["Name"] in {"minecraft:fern","minecraft:oxeye_daisy","minecraft:azure_bluet","minecraft:dandelion","minecraft:short_grass","minecraft:short_dry_grass","minecraft:tall_dry_grass"}: return ()
            return tuple((px+b[0]/16,py+b[1]/16,pz+b[2]/16,px+b[3]/16,py+b[4]/16,pz+b[5]/16) for b in shapes(json.dumps(st,sort_keys=True)))
        def can_stand(px,pz,feet):
            body=(px-.3,feet,pz-.3,px+.3,feet+1.8,pz+.3); support=0
            for bx in range(math.floor(px-.3),math.floor(px+.3)+1):
                for bz in range(math.floor(pz-.3),math.floor(pz+.3)+1):
                    for by in range(math.floor(feet)-1,math.ceil(feet+1.8)):
                        for box in boxes_at(bx,by,bz):
                            overlap=[min(body[k+3],box[k+3])-max(body[k],box[k]) for k in range(3)]
                            if all(v>1e-7 for v in overlap): return False
                            if abs(box[4]-feet)<1e-7: support+=max(0,overlap[0])*max(0,overlap[2])
            return support>1e-7
        heights={}
        for iz,ix in np.argwhere(probe_mask):
            px,pz=int(ix+x0),int(iz+z0); gy=int(c.ground_heights[iz,ix])
            for py in range(gy-1,gy+13):
                if int(c.roles[py+64,iz,ix]) not in {ROLES.index("pavement"),ROLES.index("floor")}: continue
                for box in boxes_at(px,py,pz):
                    if can_stand(px+.5,pz+.5,box[4]): heights[px,pz]=box[4]
        endpoints=[]
        for point in (source_line.coords[0],source_line.coords[-1]):
            q=min(heights,key=lambda q:(q[0]+.5-point[0])**2+(q[1]+.5-point[1])**2)
            if math.hypot(q[0]+.5-point[0],q[1]+.5-point[1])>1: raise ValueError("No retained-gallery probe anchor within one block of source endpoint")
            endpoints.append(q)
        start,end=endpoints; queue=[(0,start)]; cost={start:0}; previous={start:None}
        while queue:
            distance,q=heapq.heappop(queue)
            if distance!=cost[q]: continue
            if q==end: break
            for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)]:
                r=(q[0]+dx,q[1]+dz)
                if r not in heights or abs(heights[q]-heights[r])>.5: continue
                if not can_stand((q[0]+r[0])/2+.5,(q[1]+r[1])/2+.5,max(heights[q],heights[r])): continue
                value=distance+1+.2*source_line.distance(Point(r[0]+.5,r[1]+.5))
                if value<cost.get(r,math.inf): cost[r]=value; previous[r]=q; heapq.heappush(queue,(value,r))
        if end not in previous: raise ValueError("Registered east-gallery paved corridor has no collision-free half-block route")
        route=[]; q=end
        while q is not None: route.append([q[0]+.5,q[1]+.5]); q=previous[q]
        route.reverse()
        if all(can_stand(source_line.coords[0][0]+t*(route[0][0]-source_line.coords[0][0]),source_line.coords[0][1]+t*(route[0][1]-source_line.coords[0][1]),heights[start]) for t in np.linspace(0,1,12)):
            route.insert(0,list(source_line.coords[0]))
        feature["source_centerline_blocks"]=feature["centerline_blocks"]
        feature["centerline_blocks"]=route
        feature["probe_rule"]="Actual paved/floor probe inside the registered five-block corridor; preserves original stair rails. Endpoint centres lie within one block of source registration; full destination graph verifies continuous gallery access."
        feature["probe_endpoint_offsets_blocks"]=[math.dist(route[0],source_line.coords[0]),math.dist(route[-1],source_line.coords[-1])]

    # Each surface column occurs once in the plan. In-memory earlier surfaces
    # are superseded by the final column; block preconditions refer to the final
    # surface because all planting is authored after paving and mulch.
    generator_snapshot=output/"prepare_hill_core_environment.py"
    shutil.copyfile(Path(__file__).resolve(),generator_snapshot)
    inputs=[controls_path,cross_path,source/"profile.json",survey,generator_snapshot,
            ROOT/chapel_clear["source_study"]/"sample-blocks.npz",ROOT/chapel_clear["source_study"]/"entry-route-audit.json"]
    inputs.extend(ROOT/p for p in controls["evidence_basis"])
    if detail_controls_path: inputs.append(detail_controls_path)
    if fixture_addendum_path: inputs.append(fixture_addendum_path)
    if native_touchup_path:
        inputs.append(native_touchup_path)
        inputs.extend(ROOT/e["path"] for e in touchups.get("inputs",[]))
    if route_addendum_path:
        inputs.append(route_addendum_path)
        inputs.extend([ROOT/endpoint["source"],endpoint_profile])
        for p in route_patch["path_corridors"]: inputs.extend(ROOT/s for s in p.get("sources",[]))
        inputs.extend([ROOT/"runtime/research/core-demo-20260927/court-correction/evidence-addendum-v2.json",ROOT/"docs/research/hill-athey-court-correction-addendum-20260927.md"])
    for evidence in detail_controls.get("source_list",[]):
        paths=evidence.get("paths",[evidence["path"]] if "path" in evidence else [])
        hashes=evidence["sha256"] if isinstance(evidence["sha256"],list) else [evidence["sha256"]]
        for path,expected_hash in zip(paths,hashes,strict=True):
            if digest(ROOT/path)!=expected_hash: raise ValueError(f"Changed detail reference: {path}")
            inputs.append(ROOT/path)
    for name in ("artifact-audit.json","native-review.json"):
        if (source/name).is_file(): inputs.append(source/name)
    plan={"format":"hill-enumerated-environment-plan-v1","revision":"core-demo-20260927-environment","source_manifest_sha256":digest(source/"manifest.json"),
          "inputs":[{"path":p.relative_to(ROOT).as_posix(),"sha256":digest(p)} for p in dict.fromkeys(inputs)],
          "features":features,"columns":sorted(plans.values(),key=lambda a:(a["z"],a["x"])),
          "site_blocks":list(blocks.values()),"blocked_columns":blocked,
          "registered_source_details":registered_details,
          "authorized_component_site_overrides":[{"xz":list(q),"source_feature":v} for q,v in sorted(override_columns.items())],
          "scope":"Full source-bounded core; all original architectural columns preserved. Component-owned site changes only within source-registered gardens, paths and detail footprints, or isolated controlled pavement seam/root-support cells under coordinator authorization. Ordinary fixture cells individually registered against hash-bound source polygons. Measured existing road grades, controlled paths, paving bays, mulch, low shrubs, perennials and collision-gated source trees/lamps. Athey court/north terrace owned by building specialist."}
    # Independently replay from source: preconditions must survive deduplication.
    replay=load_region(source,m,(x0,z0,x1,z1))
    for action in plan["columns"]: apply_surface(replay,action)
    for action in plan["site_blocks"]: apply_site_block(replay,action,arch)
    palette_ids={json.dumps(p,sort_keys=True):i for i,p in enumerate(c.palette)}
    mapping=np.array([palette_ids[json.dumps(p,sort_keys=True)] for p in replay.palette],np.uint16)
    if not np.array_equal(c.data,mapping[replay.data]) or not np.array_equal(c.roles,replay.roles):
        raise ValueError("Final enumerated plan does not exactly reproduce the in-memory construction")
    del replay
    material_roles={}
    for action in [*plan["columns"],*plan["site_blocks"]]:
        if action["role"]=="air": continue
        material_roles.setdefault(action["role"],set()).add(action["state"]["Name"])
    violations=audit_role_materials(material_roles)
    if violations: raise ValueError(violations)
    route_report=route_audit(c,features,plans)
    write_json(output/"environment-plan.json",plan)
    write_json(output/"route-audit.json",route_report)
    report={"source_manifest_sha256":plan["source_manifest_sha256"],"plan_sha256":digest(output/"environment-plan.json"),"bounds_xz_blocks":[x0,z0,x1,z1],"blocks_per_metre":2,
            "surface_columns":len(plans),"site_blocks":len(blocks),"features":dict(Counter(a["feature"] for a in plans.values())),"site_features":dict(Counter(a["feature"] for a in blocks.values())),
            "excluded_component_columns":int(owned.sum()),"excluded_architectural_columns":int(arch.sum()),"component_ownership":ownership,"blocked_actions":len(blocked),"notes":notes,"trees":tree_rows,"lamps":lamp_rows,
            "authorized_component_site_override_columns":len(override_columns),
            "registered_source_fixtures":fixture_rows,
            "source_rail_observations":garden.get("rails",[]),
            "exact_replay_passed":True,"material_violations":violations,"routes_passed":route_report["passed"],"material_roles":{k:sorted(v) for k,v in material_roles.items()},
            "limitations":["Source plant species unresolved; coherent ordinary oak approximation.","No new mature trees; three young-tree interpretations accepted only if collision/duplicate checks allow.","Native visual review required before integration acceptance.","Component-owned terrain outside source-registered garden beds remains preserved; building agent handles Athey court and north terrace."]}
    write_json(output/"preparation-report.json",report)
    views=[
        ("core-ground-overview",[175,218,-160],[130,84,42],83),
        ("quad-ryan-gardens",[166,91,14],[216,88,50],76),
        ("chapel-east-garden",[49,90,47],[15,87,27],75),
        ("chapel-west-south-drive",[-66,99,84],[-20,83,16],82),
        ("chapel-south-approach",[-23,91,93],[-9,87,54],74),
        ("ryan-east-road",[345,96,126],[331,85,45],78),
        ("quadrivium-planted-frontage",[233,111,144],[233,87,187],87),
        ("quadrivium-west-garden",[165,90,173],[190,88,191],73),
        ("dining-outer-west-drive",[27,101,196],[45,88,143],78),
        ("dining-south-drive",[80,101,242],[80,89,202],85),
        ("hunt-quad-bed-edge",[143,87,-4],[139,87,-38],78),
        ("quad-athey-west-garden",[70,92,37],[40,87,65],77),
        ("south-ryan-garden-network",[221,124,174],[231,87,129],82),
        ("garden-opposing-timber-benches",[235,92,145],[241,88,130],72),
        ("garden-bell-support-detail",[213,92,137],[225,90,128],67),
        ("garden-main-walk-to-ryan",[201,92,147],[211,88,98],73),
    ]
    write_json(output/"camera-views.json",{"format":"hill-native-camera-views-v1","views":[{"name":n,"eye":e,"target":t,"fov":f} for n,e,t,f in views]})
    # Plan drawing includes clipping and preserves the physical axis/scale.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rgb=np.ones((*safe.shape,3))*.83
    rgb[grass]=[.50,.62,.42]; rgb[road]=[.25,.27,.29]; rgb[paving&~road]=[.70,.68,.63]; rgb[owned]=[.58,.49,.43]
    for a in plans.values():
        rgb[a["z"]-z0,a["x"]-x0]=[.37,.23,.12] if a["role"]=="terrain" else ([.24,.26,.28] if "deepslate" in a["state"]["Name"] else [.94,.83,.64])
    fig,ax=plt.subplots(figsize=(13,11)); ax.imshow(rgb,extent=(x0/2,x1/2,z1/2,z0/2),interpolation="nearest")
    for tree in tree_rows:
        t=next(t for t in controls["trees"] if t["id"]==tree["id"])
        ax.plot(t["world_m"][0],t["world_m"][1],"o",color="#183c27",ms=5 if tree["mode"]!="omitted_candidate" else 2)
    ax.set(xlabel="East (metres)",ylabel="South (metres)",title="Core demo source-bound environment plan — 2 blocks / metre")
    ax.set_aspect("equal"); ax.grid(alpha=.2); fig.tight_layout(); fig.savefig(output/"plan-overview.png",dpi=150); plt.close(fig)
    print(json.dumps({"output":str(output),"surface_columns":len(plans),"site_blocks":len(blocks),"blocked":len(blocked),"routes_passed":route_report["passed"],"route_results":[{"id":r["name"],"passed":r["passed"],"step":r["maximum_sampled_step_blocks"],"errors":len(r["errors"])} for r in route_report["routes"]],"trees":tree_rows,"lamps":lamp_rows},indent=2),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,default=ROOT/"runtime/campus-reconstruction/campus-context-v14-2x")
    p.add_argument("--survey",type=Path,default=ROOT/"runtime/campus-reconstruction/campus-context-v14-2x/ground-review/surface-survey.npz")
    p.add_argument("--controls",type=Path,default=ROOT/"runtime/research/core-demo-20260927/core-site-controls-v1.json")
    p.add_argument("--output",type=Path,default=DEFAULT/"plan-v1")
    p.add_argument("--detail-controls",type=Path)
    p.add_argument("--paths-only",action="store_true",help="Use only independently registered path corridors from a detail packet")
    p.add_argument("--fixture-addendum",type=Path)
    p.add_argument("--route-addendum",type=Path)
    p.add_argument("--native-touchups",type=Path)
    a=p.parse_args(); prepare(a.source.resolve(),a.survey.resolve(),a.controls.resolve(),a.output.resolve(),a.detail_controls.resolve() if a.detail_controls else None,a.paths_only,a.fixture_addendum.resolve() if a.fixture_addendum else None,a.route_addendum.resolve() if a.route_addendum else None,a.native_touchups.resolve() if a.native_touchups else None)
