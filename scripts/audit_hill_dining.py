"""Occupied-shape contacts and source-face preservation for Dining amendments."""

import argparse
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np
from audit_hill_quadrivium_contacts import AXES, shapes
from audit_hill_window_joints import ArchiveStates
from build_hill_chapel_sample import ROLES
from build_hill_dining import load_accepted_canvas
from campus_roof_geometry import load_measured_building,rasterize_roof
from campus_study_io import digest,write_json

ROOT=Path(__file__).resolve().parents[1]


def audit(study,routes_profile=None):
    profile=json.loads((study/"profile.json").read_text(encoding="utf-8"))
    manifest=json.loads((study/"manifest.json").read_text(encoding="utf-8"))
    routes_input=json.loads(routes_profile.read_text(encoding="utf-8")) if routes_profile else profile
    lookup=ArchiveStates(study/"sample-blocks.npz")
    keys=[json.dumps(s,sort_keys=True) for s in lookup.palette]

    @lru_cache(maxsize=None)
    def area_states(a,b,d):
        axis=next(i for i,v in enumerate(d) if v)
        tangent=[i for i in range(3) if i!=axis]
        score=0
        for left in shapes(keys[a]):
            for right in shapes(keys[b]):
                translated=[right[i]+16*d[i%3] for i in range(6)]
                if left[axis+3 if d[axis]>0 else axis]!=translated[axis if d[axis]>0 else axis+3]:
                    continue
                overlap=[min(left[i+3],translated[i+3])-max(left[i],translated[i]) for i in tangent]
                if all(v>0 for v in overlap):
                    score+=overlap[0]*overlap[1]
        return score

    def area(q,d):
        end=tuple(q[i]+d[i] for i in range(3))
        return area_states(lookup.get(*q),lookup.get(*end),d)

    pane_failures=[]
    panes={tuple(q) for aperture in manifest["dining_openings"] for q in aperture["pane_cells"]}
    for q in sorted(panes):
        horizontal=[d for d in AXES if d[1]==0 and area(q,d)>0]
        vertical=[d for d in AXES if d[1]!=0 and area(q,d)>0]
        if len(horizontal)<2 or len(vertical)<2:
            pane_failures.append({"xyz":q,"horizontal_contacts":horizontal,"vertical_contacts":vertical})
    partials=[]
    for q,b in manifest["dining_partial_backing"]["pairs"]:
        d=tuple(b[i]-q[i] for i in range(3))
        partials.append({"xyz":q,"backing":b,"positive_area":area(q,d)>0})
    base_path=ROOT/profile["baseline_study"]
    base_manifest=json.loads((base_path/"manifest.json").read_text(encoding="utf-8"))
    base=load_accepted_canvas(base_path/"sample-blocks.npz",base_manifest,2)
    current=load_accepted_canvas(study/"sample-blocks.npz",base_manifest,2)
    building=load_measured_building(ROOT/profile["source_cityjson"],profile["parent_id"],ROOT/profile["measured_terrain_manifest"])
    bounds=[v/2 for v in base_manifest["source_roof"]["world_bounds_blocks"]]
    raster=rasterize_roof(building,bounds,.5)
    shape_keys=sorted({shapes(json.dumps(state,sort_keys=True)) for canvas in (base,current) for state in canvas.palette})
    shape_ids={key:i for i,key in enumerate(shape_keys)}
    old=np.array([shape_ids[shapes(json.dumps(s,sort_keys=True))] for s in base.palette])
    new=np.array([shape_ids[shapes(json.dumps(s,sort_keys=True))] for s in current.palette])
    original_roof=base.roles==ROLES.index("roof")
    yy,zz,xx=np.nonzero(original_roof)
    changed=old[base.data[yy,zz,xx]]!=new[current.data[yy,zz,xx]]
    counts=Counter(map(int,raster.face_indices[zz[changed],xx[changed]]))
    change_examples=[]
    for index in np.flatnonzero(changed)[:350]:
        iy,iz,ix=int(yy[index]),int(zz[index]),int(xx[index])
        change_examples.append({"face_id":int(raster.face_indices[iz,ix]),"xyz":[ix+base.x_min,iy+base.y_min,iz+base.z_min],"before":base.palette[base.data[iy,iz,ix]],"after":current.palette[current.data[iy,iz,ix]]})
    source_changes=[]
    for face,count in sorted(counts.items()):
        source_changes.append({"face_id":face,"changed_original_roof_shapes":count})
    unexpected=[r for r in source_changes if r["face_id"] not in (10,26,31,60)]
    routes=[]
    angle=math.radians(profile["geometry"]["axis_degrees"])
    def world(uv):
        u,v=uv
        ox,oz=profile["geometry"]["origin_xz_m"]
        return ((ox+u*math.cos(angle)-v*math.sin(angle))*2,(oz+u*math.sin(angle)+v*math.cos(angle))*2)
    upper=profile["upper_front"]
    points=[]
    for u in np.linspace(*upper["ends_u_m"],math.ceil((upper["ends_u_m"][1]-upper["ends_u_m"][0])*50)):
        q=tuple(math.floor(v) for v in world((u,upper["wall_v_m"])))
        if points and q==points[-1]:continue
        if points and abs(q[0]-points[-1][0])+abs(q[1]-points[-1][1])==2:
            points.append((q[0],points[-1][1]))
        points.append(q)
    expected={(x,z+depth) for x,z in points for depth in (0,1)}
    yi,zi,xi=np.nonzero(current.roles==ROLES.index("facade"))
    x,z=(xi+current.x_min+.5)/2,(zi+current.z_min+.5)/2
    ox,oz=profile["geometry"]["origin_xz_m"]
    u=(x-ox)*math.cos(angle)+(z-oz)*math.sin(angle)
    v=-(x-ox)*math.sin(angle)+(z-oz)*math.cos(angle)
    selected=(u>upper["ends_u_m"][0]+.5)&(u<upper["ends_u_m"][1]-.5)&(v>upper["wall_v_m"]-.8)&(v<upper["wall_v_m"]+1)&(yi+current.y_min>=97)&(yi+current.y_min<102)
    surplus=[[int(xi[i])+current.x_min,int(yi[i])+current.y_min,int(zi[i])+current.z_min] for i in np.flatnonzero(selected) if (int(xi[i])+current.x_min,int(zi[i])+current.z_min) not in expected]
    steps=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:])]
    straight_wall={"controls_uv_m":[[upper["ends_u_m"][0],upper["wall_v_m"]],[upper["ends_u_m"][1],upper["wall_v_m"]]],"path_columns":len(points),"cardinal_step_counts":dict(Counter(map(str,steps))),"reverse_steps":sum(dx<0 or dz<0 for dx,dz in steps),"extra_facade_voxels_outside_two_column_analytic_wall":surplus,"scope":"Upper front levels NAVD88 73.5 to76.0; monotonic cardinal raster of the one measured-orientation plane. Main-roof/rooftop silhouettes are inspected separately."}
    def occupied(q):
        x,y,z=q
        return [(x+b[0]/16,y+b[1]/16,z+b[2]/16,x+b[3]/16,y+b[4]/16,z+b[5]/16) for b in shapes(keys[lookup.get(*q)])]
    for spec in routes_input.get("walking_routes",[]):
        points=[world(p) for p in spec["waypoints_uv_m"]]
        samples=[]
        for start,end in zip(points,points[1:]):
            samples.extend(((1-w)*np.asarray(start)+w*np.asarray(end)).tolist() for w in np.linspace(0,1,max(2,math.ceil(math.dist(start,end)/.1))))
        failures=[]
        feet=(spec["floor_navd88_m"]-25)*2
        width=spec.get("clearance_width_blocks",.6)
        height=spec.get("clearance_height_blocks",1.8)
        radius=width/2
        for x,z in samples:
            body=(x-radius,feet,z-radius,x+radius,feet+height,z+radius)
            collision=[]
            support=0
            for xx in range(math.floor(x-radius),math.floor(x+radius)+1):
                for zz in range(math.floor(z-radius),math.floor(z+radius)+1):
                    for yy in range(math.floor(feet)-1,math.floor(feet+height)+1):
                        for box in occupied((xx,yy,zz)):
                            overlap=[min(body[i+3],box[i+3])-max(body[i],box[i]) for i in range(3)]
                            if all(v>1e-7 for v in overlap):
                                collision.append([xx,yy,zz])
                            if abs(box[4]-feet)<1e-7:
                                support+=max(0,overlap[0])*max(0,overlap[2])
            if collision or support<.09:
                failures.append({"center_xz_blocks":[round(x,3),round(z,3)],"collisions":collision,"foot_support_area":round(support,4)})
        routes.append({**spec,"samples":len(samples),"sample_spacing_max_blocks":.1,"player_width_blocks":width,"player_height_blocks":height,"feet_y":feet,"failures":failures,"passed":not failures})
    # The largest occupied source roof-cell top remains independently checked.
    roof_columns=[]
    for face in range(len(building.roof_faces)):
        mask=(raster.face_indices==face)&raster.footprint_mask
        failed=0
        tested=0
        for iz,ix in np.argwhere(mask):
            roofs=np.flatnonzero(original_roof[:,iz,ix])
            if not len(roofs):continue
            top=int(roofs[-1])
            tested+=1
            failed+=int(old[base.data[top,iz,ix]]!=new[current.data[top,iz,ix]])
        if tested:
            roof_columns.append({"face_id":face,"tested_top_columns":tested,"shape_changes_at_original_top":failed})
    report={"format":"hill-dining-physical-source-audit-v1","archive_sha256":digest(study/"sample-blocks.npz"),
            "new_dining_panes":len(panes),"pane_positive_area_failures":pane_failures,
            "partial_backing_checks":partials,"missing_partial_backing":[r for r in partials if not r["positive_area"]],
            "source_roof_shape_changes":source_changes,"unexpected_source_roof_shape_changes":unexpected,
            "source_shape_change_examples":change_examples,
            "walking_routes":routes,
            "upper_front_straightness":straight_wall,
            "walking_routes_profile":{"path":str(routes_profile or study/"profile.json"),"sha256":digest(routes_profile or study/"profile.json"),"external_probe_only":bool(routes_profile)},
            "source_roof_top_shapes":roof_columns,
            "passed":not pane_failures and not unexpected and all(r["positive_area"] for r in partials) and all(r["passed"] for r in routes),
            "limits":["Pane contacts and declared partial backing are checked with positive occupied-shape area; native views remain required for complete opening enclosure.","Measured source roof cells are compared by occupied shape, allowing declared palette substitutions. Face10 screen and faces26/31 connector exceptions are recorded in the profile. Face60 underside closure is bounded to the north wall.","Pre-existing Athey physical limitations are not reclassified by this patch audit."]}
    if profile.get("court_spur_exception"):
        previous_path=ROOT/"runtime/campus-reconstruction/athey-dining-v4-2x/sample-blocks.npz"
        previous=load_accepted_canvas(previous_path,base_manifest,2)
        current_lookup={json.dumps(s,sort_keys=True):i for i,s in enumerate(current.palette)}
        translation=np.array([current_lookup.get(json.dumps(s,sort_keys=True),-1) for s in previous.palette])
        changed=(current.data!=translation[previous.data])|(current.roles!=previous.roles)
        zgrid,xgrid=np.indices(raster.heights.shape)
        x,z=(xgrid+current.x_min+.5)/2,(zgrid+current.z_min+.5)/2
        local_u=(x-ox)*math.cos(angle)+(z-oz)*math.sin(angle)
        local_v=-(x-ox)*math.sin(angle)+(z-oz)*math.cos(angle)
        spec=profile["court_spur_exception"]
        u0,v0,u1,v1=spec["bounds_uv_m"]
        spur=(local_u>=u0)&(local_u<u1)&(local_v>=v0)&(local_v<v1)&(raster.face_indices==10)
        seal=next(r for r in profile["mutation_regions"] if r["name"]=="court_seal")
        u0,v0,u1,v1=seal["bounds_uv_m"]
        paving=(local_u>=u0)&(local_u<u1)&(local_v>=v0)&(local_v<v1)&~raster.footprint_mask
        allowed=np.zeros_like(changed)
        low,high=[round((h-25)*2)-current.y_min for h in spec["height_navd88_m"]]
        allowed[low:high,spur]=True
        low,high=[round((h-25)*2)-current.y_min for h in seal["height_navd88_m"]]
        allowed[low:high,paving]=True
        invalid=int((changed&~allowed).sum())
        baseline_lookup=np.array([current_lookup.get(json.dumps(s,sort_keys=True),-1) for s in base.palette])
        face52=raster.face_indices==52
        protected_changes=int(((current.data[:,face52]!=baseline_lookup[base.data[:,face52]])|(current.roles[:,face52]!=base.roles[:,face52])).sum())
        report["v4_to_current_site_delta"]={"previous_archive_sha256":digest(previous_path),"changed_cells":int(changed.sum()),"outside_spur_and_surface_seal_changes":invalid,"source_face52_state_or_role_changes_from_accepted_athey":protected_changes,"surface_only_medallion":True,"source_face10_outside_spur_unchanged_from_v4":not (changed&~allowed)[:,raster.face_indices==10].any()}
        report["passed"] &= invalid==0 and protected_changes==0
        if profile.get("seal_placement_addendum"):
            previous_path=ROOT/"runtime/campus-reconstruction/athey-dining-v5-2x/sample-blocks.npz"
            previous=load_accepted_canvas(previous_path,base_manifest,2)
            translation=np.array([current_lookup.get(json.dumps(s,sort_keys=True),-1) for s in previous.palette])
            delta=(current.data!=translation[previous.data])|(current.roles!=previous.roles)
            old_profile=json.loads(previous_path.with_name("profile.json").read_text(encoding="utf-8"))
            old_seal=next(r for r in old_profile["mutation_regions"] if r["name"]=="court_seal")
            u0,v0,u1,v1=old_seal["bounds_uv_m"]
            old_paving=(local_u>=u0)&(local_u<u1)&(local_v>=v0)&(local_v<v1)&~raster.footprint_mask
            seal_allowed=np.zeros_like(delta)
            seal_allowed[low:high,old_paving|paving]=True
            outside=int((delta&~seal_allowed).sum())
            court=profile["court"]["bounds_uv_m"]
            court_mask=(local_u>=court[0])&(local_u<court[2])&(local_v>=court[1])&(local_v<court[3])
            crossing=court_mask&((abs(local_u-37)<.55)|(abs(local_v-27.5)<.55))
            crossing_changes=int(delta[:,crossing].sum())
            retained_source_changes=int(delta[:,raster.footprint_mask].sum())
            seal_cells=set(map(tuple,np.argwhere(changed[low:high].any(axis=0)&paving)))
            remaining=set(seal_cells)
            components=0
            while remaining:
                components+=1
                pending=[remaining.pop()]
                while pending:
                    zz,xx=pending.pop()
                    for q in ((zz-1,xx),(zz+1,xx),(zz,xx-1),(zz,xx+1)):
                        if q in remaining:
                            remaining.remove(q)
                            pending.append(q)
            report["v5_to_v6_seal_delta"]={"previous_archive_sha256":digest(previous_path),"changed_cells":int(delta.sum()),"outside_old_and_new_surface_seal_changes":outside,"crossing_state_or_role_changes":crossing_changes,"retained_source_state_or_role_changes":retained_source_changes,"new_seal_surface_cells":len(seal_cells),"new_seal_cardinal_components":components,"only_new_seal_and_restored_old_paving":outside==0}
            report["passed"] &= outside==0 and crossing_changes==0 and retained_source_changes==0 and components==1
    write_json(study/("physical-source-audit-route-probe.json" if routes_profile else "physical-source-audit.json"),report)
    print(json.dumps({"passed":report["passed"],"panes":len(panes),"pane_failures":len(pane_failures),"missing_backing":len(report["missing_partial_backing"]),"source_shape_changes":source_changes,"unexpected":unexpected,"route_failures":[[r['name'],len(r['failures'])] for r in routes if not r['passed']]}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study",type=Path)
    parser.add_argument("--routes-profile",type=Path)
    args=parser.parse_args()
    audit(args.study,args.routes_profile)
