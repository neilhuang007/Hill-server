"""Prove the demo destinations share actual connected, walkable paving.

Routes are derived from occupied paving/floor surfaces, never lawn shortcuts.
Every graph edge receives player-shape clearance and half-block step checks;
the resulting complete destination routes are resampled at 0.1 block.
"""

import argparse
from functools import lru_cache
import heapq
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

from audit_hill_quadrivium_contacts import shapes
from build_hill_chapel_sample import ROLES
from campus_study_io import digest, write_json
from prepare_hill_core_environment import load_region
from refine_hill_campus_environment import apply_surface, apply_site_block, SITE_ROLES

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def audit(source, plan_path, output):
    if output.exists(): raise FileExistsError("Choose a fresh network report")
    manifest=read(source/"manifest.json")
    controls=read(ROOT/"runtime/research/core-demo-20260927/core-site-controls-v1.json")
    bounds=[-80,-110,360,250]
    c=load_region(source,manifest,bounds)
    if plan_path:
        plan=read(plan_path)
        if plan["source_manifest_sha256"]!=digest(source/"manifest.json"):
            raise ValueError("Network plan targets a different campus")
        for record in plan["inputs"]:
            if digest(ROOT/record["path"])!=record["sha256"]: raise ValueError("Network plan input changed")
        arch=np.any(~np.isin(c.roles,list(SITE_ROLES)),axis=0)
        for a in plan["columns"]: apply_surface(c,a)
        for a in plan.get("site_blocks",[]): apply_site_block(c,a,arch)
    x0,z0,x1,z1=bounds
    keys=[json.dumps(p,sort_keys=True) for p in c.palette]

    @lru_cache(maxsize=None)
    def occupied(x,y,z):
        if not (x0<=x<x1 and z0<=z<z1 and -64<=y<320): return ()
        state=c.palette[c.get(x,y,z)]
        if state["Name"] in {"minecraft:fern","minecraft:oxeye_daisy","minecraft:azure_bluet","minecraft:dandelion","minecraft:short_grass","minecraft:short_dry_grass","minecraft:tall_dry_grass"}: return ()
        return tuple((x+b[0]/16,y+b[1]/16,z+b[2]/16,x+b[3]/16,y+b[4]/16,z+b[5]/16)
                     for b in shapes(json.dumps(state,sort_keys=True)))

    def standing(x,z,feet):
        body=(x-.3,feet,z-.3,x+.3,feet+1.8,z+.3); support=0
        for xx in range(math.floor(x-.3),math.floor(x+.3)+1):
            for zz in range(math.floor(z-.3),math.floor(z+.3)+1):
                for yy in range(math.floor(feet)-1,math.ceil(feet+1.8)):
                    for b in occupied(xx,yy,zz):
                        overlap=[min(body[i+3],b[i+3])-max(body[i],b[i]) for i in range(3)]
                        if all(v>1e-7 for v in overlap): return False
                        if abs(b[4]-feet)<1e-7: support+=max(0,overlap[0])*max(0,overlap[2])
        return support>1e-7

    paved_roles={ROLES.index("pavement"),ROLES.index("floor")}
    paved=np.any(np.isin(c.roles,list(paved_roles)),axis=0)
    heights=np.full(paved.shape,np.nan)
    # Surface candidates include raised arcade floors but never roof/wall tops.
    for iz,ix in np.argwhere(paved):
        x,z=int(ix+x0),int(iz+z0); ground=int(c.ground_heights[iz,ix])
        candidates=set()
        for y in range(max(-63,ground-2),min(319,ground+13)):
            if int(c.roles[y+64,iz,ix]) in paved_roles:
                candidates.update(b[4] for b in occupied(x,y,z))
        for feet in sorted(candidates,key=lambda h:abs(h-(ground+1))):
            if standing(x+.5,z+.5,feet): heights[iz,ix]=feet; break
    walkable=np.isfinite(heights)
    clearance=distance_transform_edt(walkable)

    def world(study,uv,kind=None):
        p=read(study/"profile.json"); g=p["geometry"]
        angle=math.radians(-g["rotation_degrees"] if kind=="chapel" else g["axis_degrees"])
        ox,oz=g.get("origin_xz_m",[0,0]); u,v=uv
        return [2*(ox+u*math.cos(angle)-v*math.sin(angle)),2*(oz+u*math.sin(angle)+v*math.cos(angle))]
    # Fixed source locations identify the actual exterior approaches. Snapping
    # only selects their containing/adjacent block centre within one metre.
    ryan=ROOT/"runtime/campus-reconstruction/ryan-library-entry-v3-2x"
    chapel=ROOT/"runtime/campus-reconstruction/chapel-entry-v1-2x"
    athey=next(Path(s["study"]) for s in manifest["components"] if "athey" in Path(s["study"]).name)
    anchors={
        "quadrivium_link_approach":[222,187],
        "ryan_main_stair_foot":world(ryan,[-10,-21.5]),
        "ryan_south_stair_foot":world(ryan,[-10,-4.1]),
        "quad_central_red_walk":[138,20],
        "chapel_east_approach":world(chapel,[13,10.6],"chapel"),
        "chapel_south_approach":world(chapel,[0,34],"chapel"),
        # Explicit boundary shared with the Athey builder's accepted door
        # approach: their supported landing continues X116..120/Z79..88 at85.
        "athey_north_approach":[118,79],
        "dining_west_gallery":world(athey,[19.4,28]),
        "dining_east_gallery":world(athey,[54.65,28]),
        "dining_court_center":world(athey,[37,28]),
        "athey_east_gallery_outer_endpoint":world(athey,[56.4,20.5]),
        "east_garden_main_junction":[196,118],
    }
    required_feet={"dining_west_gallery":89,"dining_east_gallery":89,"dining_court_center":89,
                   "athey_east_gallery_outer_endpoint":89,"athey_north_approach":85}
    nodes={}; node_report=[]
    for name,p in anchors.items():
        required=required_feet.get(name)
        candidate_cells=np.argwhere(walkable if required is None else walkable&np.isclose(heights,required))
        if not len(candidate_cells):
            node_report.append({"name":name,"source_xz":p,"required_feet_y":required,"valid":False,"reason":"No paving/floor at the exact registered walking datum"}); continue
        distances=(candidate_cells[:,1]+x0+.5-p[0])**2+(candidate_cells[:,0]+z0+.5-p[1])**2
        q=tuple(map(int,candidate_cells[int(np.argmin(distances))])); error=float(np.sqrt(distances.min()))
        center=[q[1]+x0+.5,q[0]+z0+.5]
        anchor_clear=all(standing(p[0]*(1-t)+center[0]*t,p[1]*(1-t)+center[1]*t,float(heights[q])) for t in np.linspace(0,1,max(2,math.ceil(error/.1)+1)))
        record={"name":name,"source_xz":p,"selected_center_xz":center,"source_snap_blocks":error,"required_feet_y":required,"feet_y":float(heights[q]),"anchor_connector_clear":anchor_clear,"valid":error<=2 and anchor_clear}
        node_report.append(record)
        if record["valid"]: nodes[name]=q

    @lru_cache(maxsize=None)
    def edge(a,b):
        if abs(heights[a]-heights[b])>.50001: return False
        x=(a[1]+b[1])/2+x0+.5; z=(a[0]+b[0])/2+z0+.5
        return standing(x,z,float(max(heights[a],heights[b])))
    def search(a,b):
        queue=[(0,a)]; costs={a:0}; previous={a:None}
        while queue:
            cost,q=heapq.heappop(queue)
            if q==b:
                route=[]
                while q is not None: route.append(q); q=previous[q]
                return route[::-1],set(previous)
            if cost!=costs[q]: continue
            for dz,dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                r=q[0]+dz,q[1]+dx
                if not (0<=r[0]<walkable.shape[0] and 0<=r[1]<walkable.shape[1] and walkable[r] and edge(q,r)): continue
                new=cost+1+1/(clearance[r]+.5)
                if new<costs.get(r,1e30): costs[r]=new; previous[r]=q; heapq.heappush(queue,(new,r))
        return None,set(previous)
    pairs=[
        ("quadrivium_link_approach","ryan_south_stair_foot"),
        ("ryan_south_stair_foot","ryan_main_stair_foot"),
        ("ryan_main_stair_foot","quad_central_red_walk"),
        ("quad_central_red_walk","chapel_east_approach"),
        ("chapel_east_approach","chapel_south_approach"),
        ("quad_central_red_walk","athey_north_approach"),
        ("chapel_south_approach","dining_west_gallery"),
        ("dining_west_gallery","dining_court_center"),
        ("dining_court_center","dining_east_gallery"),
        ("dining_east_gallery","ryan_south_stair_foot"),
        ("dining_east_gallery","athey_east_gallery_outer_endpoint"),
        ("athey_east_gallery_outer_endpoint","east_garden_main_junction"),
    ]
    routes=[]
    for start,end in pairs:
        name=start+"__to__"+end
        path,visited=search(nodes[start],nodes[end]) if start in nodes and end in nodes else (None,set())
        if not path:
            diagnostic={}
            if visited and end in nodes:
                _,other=search(nodes[end],(-1,-1))
                mask=np.ones(walkable.shape,bool)
                for q in visited: mask[q]=False
                distance,indices=distance_transform_edt(mask,return_indices=True)
                b=min(other,key=lambda q:distance[q]); a=tuple(int(indices[i][b]) for i in range(2))
                diagnostic={"closest_reachable_banks":[[a[1]+x0+.5,float(heights[a]),a[0]+z0+.5],[b[1]+x0+.5,float(heights[b]),b[0]+z0+.5]],"horizontal_gap_blocks":float(distance[b]),"start_component_columns":len(visited),"end_component_columns":len(other)}
            routes.append({"name":name,"start":start,"end":end,"passed":False,"reason":"No connected half-block-step paved player route between registered destination approaches","diagnostic":diagnostic}); continue
        samples=[]; failures=[]; feet_values=[]
        for a,b in zip(path,path[1:]):
            for t in np.linspace(0,1,11):
                x=a[1]+x0+.5+(b[1]-a[1])*t; z=a[0]+z0+.5+(b[0]-a[0])*t
                candidate=sorted({float(heights[a]),float(heights[b])},key=lambda h:abs(h-(heights[a]*(1-t)+heights[b]*t)))
                accepted=next((h for h in candidate if standing(x,z,h)),None)
                samples.append([round(x,3),round(z,3)]); feet_values.append(accepted)
                if accepted is None: failures.append({"xz":samples[-1],"reason":"No supported player-body clearance"})
        steps=[abs(a-b) for a,b in zip(feet_values,feet_values[1:]) if a is not None and b is not None]
        if max(steps,default=0)>.50001: failures.append({"reason":"More than half-block traversal step"})
        routes.append({"name":name,"start":start,"end":end,"passed":not failures,"samples":len(samples),"maximum_step_blocks":max(steps,default=0),"length_blocks":len(path)-1,"waypoints_xz_blocks":[[q[1]+x0+.5,q[0]+z0+.5] for q in path],"failures":failures})
    report={"format":"hill-core-destination-route-network-v1","passed":all(n["valid"] for n in node_report) and all(r["passed"] for r in routes),
            "source_manifest_sha256":digest(source/"manifest.json"),"plan_sha256":digest(plan_path) if plan_path else None,
            "auditor_sha256":digest(Path(__file__)),"source_frames":[{"path":str(study/"profile.json"),"sha256":digest(study/"profile.json")} for study in (ryan,chapel,athey)],
            "anchors":node_report,"routes":routes,"connected_destination_pairs":sum(r["passed"] for r in routes),
            "player":{"width_blocks":.6,"height_blocks":1.8,"maximum_step_blocks":.5,"sample_spacing_max_blocks":.1},
            "scope":"Actual continuous paved routes between source-registered building approaches and through both court galleries. Every graph edge checks occupied-shape support/body clearance. No grass shortcut or new service-road loop. Building entrance audits continue from these exterior anchors through their threshold routes separately."}
    write_json(output,report)
    np.savez_compressed(output.with_suffix(".walking-field.npz"),heights=heights,paved=paved,bounds=np.array(bounds),ground=c.ground_heights)
    print(json.dumps({"passed":report["passed"],"anchors":node_report,"routes":[{k:v for k,v in r.items() if k!="waypoints_xz_blocks"} for r in routes]},indent=2),flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path)
    p.add_argument("--plan",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); r=audit(a.source.resolve(),a.plan.resolve() if a.plan else None,a.output.resolve())
    raise SystemExit(0 if r["passed"] else 1)
