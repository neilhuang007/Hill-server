"""Prepare a bounded campus road/parking draft without exporting a world.

Exact source polygons, DEM grades and accepted tile preconditions are retained.
The resulting enumerated plan is consumed by refine_hill_campus_environment.py.
Broad visible paving is reliable; stall spacing and flush curb representation
are explicitly rough interpretations, never an as-built parking inventory.
"""

import argparse
from collections import Counter
from dataclasses import replace
import csv
import gc
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, gaussian_filter
from shapely import contains_xy
from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import unary_union

import build_hill_measured_terrain as measured
from assemble_hill_campus_studies import prepare_component
from build_hill_chapel_sample import ROLES
from campus_export_parity import read_archive
from campus_materials import audit_role_materials
from campus_study_io import digest, write_json
from refine_hill_campus_environment import load_canvas, apply_surface, apply_site_block, SITE_ROLES

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runtime/research/campus-exterior-draft-20260927"
TERRAIN = ROOT / "runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz"
AERIAL = ROOT / "runtime/research/campus-priority-20260905/campus-2026-aerial-original.jpg"
MAP = ROOT / "runtime/research/quad-landscape-20260905/campus-map-2026-artwork.png"
DRONE = ROOT / "runtime/research/campus-full-detail-20260905/drone-238s.png"
CORE = (-80, -110, 360, 250)  # Inclusive protected bounds, in blocks.
PUBLIC = {"way/719695390", "way/468226002", "way/12324417", "way/12375508",
          "way/12374585", "way/1012209641", "way/1163861987"}
SKIP = {"way/724643559", "way/724643560", "way/263155597", "way/263155592",
        "way/263155591", "way/263135558", "way/263155560", "way/263155562"}
LEAVES = {"persistent": "true", "distance": "1", "waterlogged": "false"}
CAMERAS=[("cfta-lot-north",[280,-545],[315,-425],36), ("cfta-lot-west",[164,-360],[265,-422],25),
         ("cfta-island-eye",[317,-479],[334,-448],3.4),("dell-shared-lots",[447,-177],[485,-110],26),
         ("wendell-music-lots",[431,-46],[380,-88],21),("east-faculty-loop",[954,-50],[901,-126],28),
         ("west-dutch-access",[-296,-72],[-162,-70],35),("athletic-front-drive",[-51,-112],[90,-124],22),
         ("gate-arrival-island",[799,-429],[747,-327],31),("tennis-north-link",[730,-655],[789,-714],30),
         ("stadium-approach",[830,-873],[943,-1025],37),("west-arrival-street",[-405,62],[-330,-27],33)]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def local_polygon(origin, angle, bounds):
    a = math.radians(angle)
    u0, v0, u1, v1 = bounds
    return Polygon([(origin[0]+u*math.cos(a)-v*math.sin(a),
                     origin[1]+u*math.sin(a)+v*math.cos(a))
                    for u,v in [(u0,v0),(u1,v0),(u1,v1),(u0,v1)]])


def top_state(height, style):
    # The half-height state keeps the measured continuous slope walkable.
    height = round(float(height)*2)/2
    full, slab = {"asphalt": ("polished_deepslate", "polished_deepslate_slab"),
                  "edge": ("smooth_stone", "smooth_stone_slab"),
                  "stripe": ("white_concrete", "smooth_stone_slab")}[style]
    state = {"Name": "minecraft:"+(full if height == int(height) else slab)}
    if height != int(height):
        state["Properties"] = {"type": "bottom", "waterlogged": "false"}
    return math.ceil(height)-1, state


def footprint_mask(geometry, bounds):
    x0,z0,x1,z1 = bounds
    zz,xx = np.indices((z1-z0,x1-x0))
    return contains_xy(geometry, xx+x0+.5, zz+z0+.5)


def source_features():
    transform = replace(measured.WorldTransform.from_manifest(measured.DEFAULT_WORLD_MANIFEST), blocks_per_metre=2)
    all_features, _ = measured.load_surface_features(measured.DEFAULT_SURFACES, measured.DEFAULT_OSM, transform)
    rows = {r["source_id"]: r for r in csv.DictReader((PACKET/"surface-source-index.tsv").open(), delimiter="\t")}
    # The packet lists 536533149 in N1 prose. 864524592 is the exact cached
    # connecting road visible between tennis and the baseball/stadium path.
    for sid in ("way/536533149", "way/864524592"):
        rows[sid] = {"sector": "N1,N2", "status": "map_aerial_broad_circulation"}
    clip = box(-450,-1300,1155,248)
    features = []
    for p in all_features:
        if p.source_id not in rows or p.source_id in SKIP:
            continue
        g = p.geometry.intersection(clip)
        if g.is_empty:
            continue
        features.append({"id": p.source_id, "kind": p.material, "sector": rows[p.source_id]["sector"],
                         "source": p.source, "geometry": g, "original_geometry": p.geometry,
                         "evidence": [rel(AERIAL), rel(MAP)],
                         "status": "rough_visible_pavement_using_cached_boundary",
                         "limitations": "Cached OSM edge and width retained as a rough trace; obscured curbs, exact stalls and traffic controls are not surveyed."})
    # The exported surface layer deliberately punched out some road junctions.
    # Its CFTA north/south fields, for example, leave a six-metre grass stripe
    # across the original continuous drive. Restore only those source-line gaps,
    # bounded by the exported feature's neighbourhood and the campus clip.
    raw=read(measured.DEFAULT_OSM)
    raw_by_id={f"{e['type']}/{e['id']}":e for e in raw["elements"]}
    hard=unary_union([f["geometry"] for f in features])
    fills=[]
    for f in features:
        if f["kind"]!="road" or f["source"]!="exported-campus-surfaces":continue
        e=raw_by_id.get(f["id"])
        if not e:continue
        line=measured.osm_geometry_to_block(e,transform)
        if line is None or line.geom_type!="LineString":continue
        width=measured.site_feature_width_blocks("road",transform,e.get("tags",{}))
        g=measured.buffered_site_line(line,width).intersection(f["geometry"].envelope.buffer(18)).intersection(clip).difference(hard)
        if g.area<.5:continue
        fills.append({"id":f["id"]+"_registered_junction_restoration","kind":"road","sector":f["sector"],"source":"raw-cached-osm-centerline",
                      "geometry":g,"original_geometry":line,"evidence":[rel(AERIAL),rel(MAP)],
                      "status":"continuous_source_line_restores_export_cutouts","source_width_blocks":width,
                      "limitations":"Junction fill within 9m of the exported source extent; default road width is an interpreted rough trace, not a curb survey."})
    features.extend(fills)
    return features, transform


def detail_controls(features):
    by_id = {f["id"]:f for f in features}
    details = []
    # Four visibly parallel parking rows on the 2026 CFTA aerial, represented
    # at 0.5m resolution. Spacing/count are drawing decisions, not measurements.
    cfta = by_id["way/263135537"]["geometry"]
    origin, angle = (212.6423571994082,-499.5525415223004), 8.584
    for row,(v0,v1) in enumerate([(3,13),(25,34),(34,43),(53,61)],1):
        stripes = [local_polygon(origin,angle,(u-.42,v0,u+.42,v1)) for u in np.arange(15,216,5.5)]
        details.append({"id":f"cfta_north_stall_row_{row}","kind":"stripe",
                        "geometry":unary_union(stripes).intersection(cfta.buffer(-2)),
                        "evidence":[rel(AERIAL)],"confidence":"observed parallel white markings; inferred spacing/count"})
    # West CFTA field has two visible paired rows, partly hidden by trees.
    origin2=(201.4893153715756,-430.14130067041276)
    for row,(v0,v1) in enumerate([(4,14),(34,44),(44,54),(69,78)],1):
        stripes=[local_polygon(origin2,angle,(u-.42,v0,u+.42,v1)) for u in np.arange(8,77,5.5)]
        details.append({"id":f"cfta_west_stall_row_{row}","kind":"stripe",
                        "geometry":unary_union(stripes).intersection(cfta.buffer(-2)),
                        "evidence":[rel(AERIAL)],"confidence":"partly observed white rows; rough spacing/count"})
    # Small rounded, planted median heads are visible in CFTA's lot; exact
    # extents/trunk locations cannot be resolved from the oblique aerial.
    for number,(u0,u1) in enumerate([(4,10),(104,110),(212,218)],1):
        g=local_polygon(origin,angle,(u0,27,u1,41)).buffer(1.8,join_style=1).intersection(cfta.buffer(-2))
        details.append({"id":f"cfta_planted_median_head_{number}","kind":"island", "geometry":g,
                        "evidence":[rel(AERIAL)],"confidence":"visible island form; approximate placement within source lot"})
    # Dell drone shows two facing rows in the long shared pocket. Do not stripe
    # small hidden residential pockets where even row orientation is unclear.
    f=by_id["way/263155599"]; origin=(427.39176846165617,-129.54456112364454); angle=-14.14
    for row,(v0,v1) in enumerate([(2,10),(22,29)],1):
        stripes=[local_polygon(origin,angle,(u-.42,v0,u+.42,v1)) for u in np.arange(8,112,5.5)]
        details.append({"id":f"dell_shared_pocket_stall_row_{row}","kind":"stripe",
                        "geometry":unary_union(stripes).intersection(f["geometry"].buffer(-1.5)),
                        "evidence":[rel(DRONE),rel(MAP)],"confidence":"two visible rows; approximate grid spacing/count"})
    lanes=unary_union([f["geometry"] for f in features if f["kind"]=="road"]).buffer(.8)
    for detail in details:
        detail["geometry"]=detail["geometry"].difference(lanes)
    return [d for d in details if not d["geometry"].is_empty]


def raster_sources(features, details, bounds):
    x0,z0,x1,z1=bounds
    shape=(z1-z0,x1-x0)
    ids=np.zeros(shape,np.uint16); internal=np.zeros(shape,bool); style=np.zeros(shape,np.uint8)
    def stamp(g):
        a,b,c,d=g.bounds; xa=max(x0,math.floor(a)); za=max(z0,math.floor(b)); xb=min(x1,math.ceil(c)); zb=min(z1,math.ceil(d))
        if xa>=xb or za>=zb:return None,None
        slices=(slice(za-z0,zb-z0),slice(xa-x0,xb-x0))
        return slices,footprint_mask(g,(xa,za,xb,zb))
    ledger=[]
    for i,f in enumerate(features,1):
        sl,mask=stamp(f["geometry"])
        if sl is None:continue
        ids[sl][mask]=i; internal[sl][mask]|=f["id"] not in PUBLIC; style[sl][mask]=1 if f["kind"]=="path" else 0
        ledger.append({k:(mapping(v) if k in {"geometry","original_geometry"} else v) for k,v in f.items()})
    # Flush pale edging, inside the source footprint only. Joined source polygons
    # are unioned before outlining, so no transverse curb cuts a drive junction.
    hard=ids>0
    edge=hard&~binary_erosion(hard,np.ones((3,3)))&internal
    style[edge]=1
    for j,d in enumerate(details,len(features)+1):
        sl,mask=stamp(d["geometry"])
        if sl is None:continue
        mask &= hard[sl]
        ids[sl][mask]=j; style[sl][mask]=2 if d["kind"]=="stripe" else 3
        if d["kind"]=="island":
            inner=footprint_mask(d["geometry"].buffer(-1.0),(sl[1].start+x0,sl[0].start+z0,sl[1].stop+x0,sl[0].stop+z0))
            style[sl][mask&~inner]=1
        ledger.append({k:(mapping(v) if k=="geometry" else v) for k,v in d.items()})
    return ids,style,ledger


def reserve_studies(manifest, bounds, extra_studies, cache):
    x0,z0,x1,z1=bounds; owned=np.zeros((z1-z0,x1-x0),bool); records=[]
    pairs=[(Path(p["study"]),p["margin_m"]) for p in manifest["components"]]+[(p,.5) for p in extra_studies]
    for study,margin in pairs:
        part=prepare_component(study,cache,2,-25,margin)
        sx,sz=part.meta["x_min"],part.meta["z_min"]; sd,sw=part.mask.shape
        l,t,r,b=max(x0,sx),max(z0,sz),min(x1,sx+sw),min(z1,sz+sd)
        if l<r and t<b:owned[t-z0:b-z0,l-x0:r-x0]|=part.mask[t-sz:b-sz,l-sx:r-sx]
        records.append({"study":rel(study),"archive_sha256":digest(study/"sample-blocks.npz"),"margin_m":margin,"owned_columns":int(part.mask.sum())})
        del part
    return owned,records


def routes_from_osm(features, transform):
    raw=read(measured.DEFAULT_OSM)
    nodes={e["id"]:(e["lon"],e["lat"]) for e in raw["elements"] if e["type"]=="node"}
    ids={f["id"] for f in features if f["kind"] in {"road","path"} and f["id"] not in PUBLIC}
    routes=[]
    for e in raw["elements"]:
        sid=f"{e['type']}/{e['id']}"
        if sid not in ids:continue
        points=e.get("geometry")
        if points:points=[(p["lon"],p["lat"]) for p in points]
        else:points=[nodes[n] for n in e.get("nodes",[]) if n in nodes]
        if len(points)>1:
            coords=[list(transform.lonlat_to_block(*p)) for p in points]
            routes.append({"id":sid,"centerline_blocks":coords})
    return routes


def route_probes(routes, tops, obstruction, touched, bounds):
    x0,z0,x1,z1=bounds; rows=[]
    for route in routes:
        line=LineString(route["centerline_blocks"]); observations=[]; gaps=0
        for dist in np.linspace(0,line.length,max(2,math.ceil(line.length/.1)+1)):
            p=line.interpolate(float(dist)); x,z=p.x,p.y; ix,iz=math.floor(x)-x0,math.floor(z)-z0
            if not (1<=ix<tops.shape[1]-1 and 1<=iz<tops.shape[0]-1) or not touched[max(0,iz-1):iz+2,max(0,ix-1):ix+2].any():
                observations.append(None);gaps+=1;continue
            cells=[(zz,xx) for zz in range(math.floor(z-.3)-z0,math.floor(z+.3)+1-z0) for xx in range(math.floor(x-.3)-x0,math.floor(x+.3)+1-x0)]
            clear=all(not obstruction[a,b] and tops[a,b]>-300 for a,b in cells)
            h=max(tops[a,b] for a,b in cells) if clear else None
            observations.append((round(x,3),round(z,3),float(h)) if h is not None else (round(x,3),round(z,3),None))
        spans=[];current=[]
        for o in observations+[None]:
            if o is not None:current.append(o)
            elif current:
                if len(current)>=20:spans.append(current)
                current=[]
        for n,span in enumerate(spans):
            errors=[{"xz":o[:2],"reason":"occupied or unsupported source column"} for o in span if o[2] is None]
            steps=[]
            for a,b in zip(span,span[1:]):
                if a[2] is None or b[2] is None:continue
                step=abs(a[2]-b[2]);steps.append(step)
                if step>.50001:errors.append({"from":a,"to":b,"reason":"greater than half-block step"})
            rows.append({"id":route["id"]+f"_span_{n+1}","samples":len(span),"from":span[0],"to":span[-1],
                         "maximum_step_blocks":max(steps,default=0),"passed":not errors,"errors":errors[:30],"error_count":len(errors)})
    return {"passed":all(r["passed"] for r in rows),"routes":rows,
            "scope":"0.1-block source-centerline samples using 0.6-wide body footprint, exact slab standing tops, and all-height non-ground obstruction exclusion. Spans outside planned work are not certified. Architecture-owned approaches remain building tasks.",
            "player_width_blocks":.6,"player_height_blocks":1.8,"sample_spacing_max_blocks":.1}


def prepare(source, output, extra_studies, component_cache=None):
    if output.exists():raise FileExistsError("Use a fresh immutable plan directory")
    output.mkdir(parents=True)
    m=read(source/"manifest.json");bounds=tuple(m["bounds_xz_blocks"]);x0,z0,x1,z1=bounds
    features,transform=source_features();details=detail_controls(features)
    ids,style,ledger=raster_sources(features,details,bounds)
    owned,reserved=reserve_studies(m,bounds,extra_studies,component_cache or output/"component-cache")
    zz,xx=np.indices(ids.shape)
    core=(xx+x0>=CORE[0])&(xx+x0<=CORE[2])&(zz+z0>=CORE[1])&(zz+z0<=CORE[3])
    candidate=(ids>0)&~owned&~core
    with np.load(TERRAIN) as a:
        measured_top=(a["ground_elevation_navd88_m"].astype(np.float64)-25)*2
        if measured_top.shape!=ids.shape or int(a["x_min"])*2!=x0 or int(a["z_min"])*2!=z0:
            raise ValueError("Measured terrain frame mismatch")
    # A 0.5m smoothing radius removes sub-cell DEM jitter. No constant sector
    # plane, height relocation or global leveling is used.
    target=np.rint(gaussian_filter(measured_top,.8)*2)/2
    tops=np.full(ids.shape,-320.,np.float32);obstruction=np.ones(ids.shape,bool)
    touched=np.zeros(ids.shape,bool);all_arch=np.zeros(ids.shape,bool)
    plans=[];blocks=[];preconditions=[];mutations=[];tile_audits=[];camera_air=[];blocked=Counter();changed_materials=Counter()
    actual_by_feature=Counter();route_rows=routes_from_osm(features,transform)
    for spec in m["tiles"]:
        tx,tz=map(int,Path(spec["path"]).name[1:].split("_z")); bx,bz=min(tx+256,x1),min(tz+256,z1)
        sl=(slice(tz-z0,bz-z0),slice(tx-x0,bx-x0))
        if not (ids[sl]>0).any():continue
        path=source/spec["path"]/"sample-blocks.npz"
        if digest(path)!=spec["archive_sha256"]:raise ValueError("Source tile hash changed")
        a=read_archive(path);c=load_canvas(a,(tx,tz,bx,bz));del a
        before=c.data.copy();before_roles=c.roles.copy()
        arch=np.any(~np.isin(c.roles,list(SITE_ROLES)),axis=0);all_arch[sl]=arch
        gz=c.ground_heights;rz,rx=np.indices(gz.shape)
        states=c.data[gz+64,rz,rx]
        half=np.array([s["Name"].endswith("_slab") and s.get("Properties",{}).get("type")=="bottom" for s in c.palette])
        current=gz+1-half[states]*.5
        tops[sl]=current
        upper=np.arange(384)[:,None,None]>gz[None,:,:]+64
        ob=np.any(upper&(c.data!=0),axis=0)
        obstruction[sl]=ob|arch
        names=np.array([s["Name"] for s in c.palette]);water=names[states]=="minecraft:water"
        safe=candidate[sl]&~arch&~ob&~water
        blocked.update({"architecture":int((candidate[sl]&arch).sum()),"vegetation_or_above_ground":int((candidate[sl]&~arch&ob).sum()),"water":int((candidate[sl]&water).sum())})
        tile_plans=[];tile_blocks=[]
        for iz,ix in np.argwhere(safe):
            gx,gz_=int(tx+ix),int(tz+iz);j,i=iz+tz-z0,ix+tx-x0
            feature=ledger[int(ids[j,i])-1]["id"]
            height=float(target[j,i])
            # Existing authored terrain gets priority if it differs from bare
            # DEM by >0.75m, even outside explicit building ownership.
            if abs(height-current[iz,ix])>1.5:
                height=float(current[iz,ix]);blocked["retained_engineered_grade"]+=1
            st=int(style[j,i]);role="pavement"
            if st==3:
                # Island planting on full supported cells only, flush with the
                # current lot's grade. A planted head is not a high traffic curb.
                height=round(height); y=math.ceil(height)-1;state={"Name":"minecraft:coarse_dirt"};role="terrain"
            else:y,state=top_state(height,("asphalt","edge","stripe")[st])
            action={"x":gx,"z":gz_,"y":y,"state":state,"role":role,"feature":feature,"max_delta_blocks":2}
            old_y=int(c.ground_heights[iz,ix]);oldstate=c.palette[c.get(gx,old_y,gz_)]
            if y==old_y and state==oldstate and ROLES[int(c.roles[old_y+64,iz,ix])]==role:continue
            pre={"xz":[gx,gz_],"top_y":old_y,"top_state":oldstate,"top_role":ROLES[int(c.roles[old_y+64,iz,ix])],
                 "column_sha256":hashlib.sha256(before[:,iz,ix].tobytes()+before_roles[:,iz,ix].tobytes()).hexdigest(),"tile":spec["path"],"tile_sha256":spec["archive_sha256"]}
            try:apply_surface(c,action)
            except ValueError as e:raise ValueError({"action":action,"error":str(e)}) from e
            plans.append(action);tile_plans.append(action);preconditions.append(pre);touched[j,i]=True;actual_by_feature[feature]+=1
            tops[j,i]=y+(.5 if state.get("Properties",{}).get("type")=="bottom" else 1)
            if st==3 and (gx+gz_)%3==0:
                by=y+1
                if c.get(gx,by,gz_)==0:
                    ba={"xyz":[gx,by,gz_],"before":{"Name":"minecraft:air"},"before_role":"air",
                        "state":{"Name":"minecraft:oak_leaves","Properties":LEAVES},"role":"vegetation","feature":feature+"_low_planting"}
                    apply_site_block(c,ba,arch);blocks.append(ba);tile_blocks.append(ba);obstruction[j,i]=True
        diff=(before!=c.data)|(before_roles!=c.roles)
        if np.any(diff[:,arch]) or np.any(diff[:,owned[sl]]) or np.any(diff[:,core[sl]]):raise ValueError("Protected column changed")
        for iy,iz,ix in np.argwhere(diff):
            after=c.palette[int(c.data[iy,iz,ix])];role=ROLES[int(c.roles[iy,iz,ix])]
            mutations.append({"xyz":[int(tx+ix),int(iy-64),int(tz+iz)],"before":c.palette[int(before[iy,iz,ix])],"before_role":ROLES[int(before_roles[iy,iz,ix])],"after":after,"after_role":role})
            changed_materials[(role,after["Name"])]+=1
        # Replay from the unchanged source arrays using production functions.
        final_data=c.data;final_roles=c.roles;c.data=before.copy();c.roles=before_roles.copy()
        c.ground_heights=gz.copy()
        # gz is the initial array object, modified by apply_surface; reconstruct
        # original ground using exact original top preconditions for changed cells.
        for pre in preconditions[-len(tile_plans):] if tile_plans else []:
            c.ground_heights[pre["xz"][1]-tz,pre["xz"][0]-tx]=pre["top_y"]
        for action in tile_plans:apply_surface(c,action)
        for action in tile_blocks:apply_site_block(c,action,arch)
        replay=np.array_equal(c.data,final_data) and np.array_equal(c.roles,final_roles)
        if not replay:raise ValueError("Exact production replay failed")
        for name,eye,_,lift in CAMERAS:
            if not (tx<=eye[0]<bx and tz<=eye[1]<bz):continue
            ey=float(tops[int(eye[1]-z0),int(eye[0]-x0)]+lift)
            state=c.palette[c.get(int(eye[0]),math.floor(ey),int(eye[1]))]
            camera_air.append({"name":name,"eye":[eye[0]+.5,ey,eye[1]+.5],"air":state["Name"]=="minecraft:air","state":state,"tile":spec["path"]})
        tile_audits.append({"tile":spec["path"],"source_sha256":spec["archive_sha256"],"columns":len(tile_plans),"site_blocks":len(tile_blocks),"mutations":int(diff.sum()),"replay_passed":replay,"protected_architecture_cells":int(arch.sum()*384)})
        print(json.dumps(tile_audits[-1]),flush=True)
        del c,before,before_roles,final_data,final_roles,diff,upper
        gc.collect()
    materials={}
    for (role,name),count in changed_materials.items():
        if role!="air":materials.setdefault(role,{})[name]=count
    material_report=audit_role_materials(materials)
    if material_report:raise ValueError(material_report)
    # Candidate roads, frozen core and component masks are separately counted;
    # omission under a building never becomes silent architectural alteration.
    routes=route_probes(route_rows,tops,obstruction,candidate,bounds)
    for f in ledger:f["changed_columns"]=actual_by_feature[f["id"]]
    snapshot=output/"prepare_hill_campus_road_draft.py";shutil.copy2(__file__,snapshot)
    input_paths=[measured.DEFAULT_SURFACES,measured.DEFAULT_OSM,measured.DEFAULT_WORLD_MANIFEST,TERRAIN,AERIAL,MAP,DRONE,snapshot,
                 ROOT/"scripts/refine_hill_campus_environment.py",ROOT/"scripts/assemble_hill_campus_studies.py",source/"profile.json"]+list(PACKET.glob("*"))
    for p in extra_studies:input_paths.extend([p/"sample-blocks.npz",p/"profile.json"])
    source_hash=digest(source/"manifest.json")
    plan={"format":"hill-site-plan-v1","revision":"campus-exterior-road-parking-draft-20260927","source_manifest_sha256":source_hash,
          "inputs":[{"path":rel(p),"sha256":digest(p)} for p in input_paths if p.is_file()],"columns":plans,"site_blocks":blocks,
          "features":ledger,"protected_core_blocks_inclusive":list(CORE),"registered_core_joins":[],
          "scope":"Terrain-following broad roads and lots in seven outer sectors, flush edge returns, bounded CFTA/Dell white stall rows and CFTA planted median heads. Current and pending building masks plus all-height architecture are preserved. Exact curb/stall inventories, traffic controls and concealed doors are not claimed."}
    write_json(output/"environment-plan.json",plan)
    write_json(output/"feature-ledger.json",{"features":ledger,"source_boundaries":"Exact unrounded source geometry, clipped to stated campus review bounds; all styling occurs within it.","limitations":plan["scope"]})
    write_json(output/"column-preconditions.json",{"source_manifest_sha256":source_hash,"columns":preconditions})
    write_json(output/"expected-mutations.json",{"source_manifest_sha256":source_hash,"cells":mutations})
    write_json(output/"route-seam-probes.json",routes)
    write_json(output/"component-reservations.json",{"components":reserved,"protected_core":list(CORE)})
    np.savez_compressed(output/"surface-draft.npz",tops=tops,obstruction=obstruction,changed=touched,feature_id=ids,style=style,bounds=bounds,architecture=all_arch,owned=owned)
    review=read(source/"native-review.json") if (source/"native-review.json").exists() else {}
    camera_pass=len(camera_air)==len(CAMERAS) and all(a["air"] for a in camera_air)
    audit={"format":"hill-road-draft-preflight-v1","passed":routes["passed"] and camera_pass,"source_manifest_sha256":source_hash,
           "base_native_accepted":review.get("status","").startswith("accepted"),"plan_sha256":digest(output/"environment-plan.json"),
           "planned_columns":len(plans),"site_blocks":len(blocks),"exact_mutations":len(mutations),"tiles":tile_audits,
           "all_height_architecture_changes":0,"core_changes":0,"component_owned_changes":0,"materials_passed":True,
           "source_feature_count":len(features),"detail_feature_count":len(details),"route_probes_passed":routes["passed"],"camera_eyes_passed":camera_pass,"excluded":dict(blocked),
           "pending":"Whole-campus export, integrated native camera review and exact global audits belong to root. No launcher selection changed."}
    write_json(output/"preflight-audit.json",audit)
    views=[]
    for name,eye,target_xz,lift in CAMERAS:
        def height_at(p):
            ix,iz=math.floor(p[0])-x0,math.floor(p[1])-z0
            h=tops[iz,ix]
            return float(h if h>-300 else measured_top[iz,ix])
        views.append({"name":name,"eye":[eye[0]+.5,height_at(eye)+lift,eye[1]+.5],"target":[target_xz[0]+.5,height_at(target_xz)+1,target_xz[1]+.5],"fov":72})
    write_json(output/"camera-views.json",{"format":"hill-native-camera-views-v1","views":views})
    write_json(output/"camera-air-audit.json",{"passed":camera_pass,"source_manifest_sha256":source_hash,"plan_sha256":audit["plan_sha256"],"views":camera_air})
    print(json.dumps(audit,indent=2),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reserve-study",type=Path,action="append",default=[])
    parser.add_argument("--component-cache",type=Path)
    args=parser.parse_args()
    prepare(args.source.resolve(),args.output.resolve(),[p.resolve() for p in args.reserve_study],args.component_cache.resolve() if args.component_cache else None)
