"""Frozen, bounded entry amendments to the integrated Ryan and Chapel studies.

The baseline is loaded exactly. Measured roofs and every cell outside the
declared amendment regions are retained; campus integration applies only the
recorded delta so previously accepted landscape remains authoritative.
"""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil

import numpy as np

from build_hill_chapel_sample import Canvas, ROLES, connect_window_panes
from campus_athey_details import connect_iron_rails
from campus_export_parity import compare_world, read_archive
from campus_study_io import digest, finish_study, write_json
from audit_hill_quadrivium_contacts import shapes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runtime/campus-reconstruction/campus-developed-ground-v6-2x"
SLAB = {"type": "bottom", "waterlogged": "false"}
PANE = {"north": "false", "south": "false", "east": "false", "west": "false", "waterlogged": "false"}


def load_canvas(study):
    with np.load(study / "sample-blocks.npz", allow_pickle=False) as archive:
        xyz = archive["coords"]
        low, high = xyz.min(axis=0), xyz.max(axis=0)
        c = Canvas(int(low[0]), int(low[2]), int(high[0]-low[0]+1), int(high[2]-low[2]+1), 2)
        c.palette = json.loads(str(archive["palette_json"]))
        c.palette_lookup = {json.dumps(s, sort_keys=True): i for i, s in enumerate(c.palette)}
        where = (xyz[:, 1]+64, xyz[:, 2]-c.z_min, xyz[:, 0]-c.x_min)
        c.data[where] = archive["state_ids"]
        c.roles[where] = archive["role_ids"]
    ground = np.isin(c.roles, [ROLES.index("terrain"), ROLES.index("pavement")])
    c.ground_heights = np.max(np.where(ground, np.arange(384)[:, None, None]-64, -64), axis=0)
    return c


class EntryAmendment:
    def __init__(self, c, p, kind):
        self.c, self.p, self.kind = c, p, kind
        g = p["geometry"]
        angle = math.radians(g["axis_degrees"] if kind == "ryan-library" else -g["rotation_degrees"])
        self.cos, self.sin = math.cos(angle), math.sin(angle)
        self.origin = np.asarray(g.get("origin_xz_m", [0, 0]), float)
        iz, ix = np.indices(c.ground_heights.shape)
        x, z = (ix+c.x_min+.5)/2-self.origin[0], (iz+c.z_min+.5)/2-self.origin[1]
        self.u, self.v = x*self.cos+z*self.sin, -x*self.sin+z*self.cos
        self.regions = []
        self.routes = []
        self.door_cells = []
        self.new_panes = set()

    def world(self, uv):
        u, v = uv
        return 2*(self.origin + [u*self.cos-v*self.sin, u*self.sin+v*self.cos])

    def local(self, x, z):
        x,z=x/2-self.origin[0],z/2-self.origin[1]
        return [x*self.cos+z*self.sin,-x*self.sin+z*self.cos]

    def mask(self, bounds):
        u0, v0, u1, v1 = bounds
        return (self.u >= u0) & (self.u < u1) & (self.v >= v0) & (self.v < v1)

    def columns(self, bounds):
        for iz, ix in np.argwhere(self.mask(bounds)):
            yield int(ix+self.c.x_min), int(iz+self.c.z_min), int(iz), int(ix)

    def region(self, name, bounds, y0, y1):
        self.regions.append({"name": name, "bounds_uv_m": list(bounds), "y_blocks": [y0, y1]})

    def box(self, bounds, y0, y1, block, role, properties=None):
        for x, z, _, _ in self.columns(bounds):
            for y in range(y0, y1):
                self.c.set(x, y, z, block, role, properties)

    def pave(self, bounds, surfaces, clear=0):
        values = np.broadcast_to(surfaces, self.u.shape)
        for x, z, iz, ix in self.columns(bounds):
            surface = round(float(values[iz, ix])*2)/2
            top = math.ceil(surface)-1
            old = int(self.c.ground_heights[iz, ix])
            # Fill to an occupied base, not only the single new top cell.
            for y in range(min(old, top)-2, top):
                self.c.set(x, y, z, "stone", "terrain")
            for y in range(top+1, max(old+1, top+1+clear)):
                self.c.set(x, y, z, "air", "air")
            self.c.set(x, top, z, "smooth_stone" if surface.is_integer() else "smooth_stone_slab", "pavement", None if surface.is_integer() else SLAB)
            self.c.ground_heights[iz, ix] = top

    def connect_local_panes(self):
        # Connection recomputation is allowed only where a new reveal meets an
        # existing pane. Keep all unchanged distant pane states exact.
        before_states, before_roles = self.c.data.copy(), self.c.roles.copy()
        connect_window_panes(self.c)
        allowed = self.allowed_mask()
        self.c.data[~allowed] = before_states[~allowed]
        self.c.roles[~allowed] = before_roles[~allowed]

    def allowed_mask(self):
        result = np.zeros(self.c.data.shape, bool)
        for region in self.regions:
            low, high = region["y_blocks"]
            result[low+64:high+64, self.mask(region["bounds_uv_m"])] = True
        return result

    def ryan_portal(self, centre_v, wall_u, central):
        """Open only the photographed rear/side entrance reveal.

        The small operating pair is recessed within the full-size portal; it
        does not define the measured wall plane or move the exterior jambs.
        """
        bounds = (wall_u-.8, centre_v-1.8, wall_u+2, centre_v+1.8)
        self.region("central-recessed-entry" if central else "south-west-pointed-entry", bounds, 78, 100)
        floor = 90
        self.pave((wall_u-.8, centre_v-1.0, wall_u+1.8, centre_v+1.0), floor, clear=4)
        self.box((wall_u-.8, centre_v-1.0, wall_u+1.8, centre_v+1.0), floor, floor+4, "air", "air")
        # The operating doors use a cardinal recess inside the unchanged
        # rotated exterior. Each closes one normal one-block door aperture.
        xw, zw = self.world((wall_u+.65, centre_v))
        dx, dz = math.floor(xw), math.floor(zw)
        for x in range(dx-1, dx+3):
            for z in (dz-1,dz):
                self.c.set(x, floor-1, z, "smooth_stone", "floor")
                for y in range(floor,floor+4):
                    self.c.set(x,y,z,"air","air")
        for z,hinge in ((dz-1,"right"),(dz,"left")):
            for y,half in ((floor,"lower"),(floor+1,"upper")):
                q=(dx,y,z)
                self.c.set(*q,"dark_oak_door","door",{"facing":"west","half":half,"hinge":hinge,"open":"true","powered":"false"})
                self.door_cells.append(list(q))
        if central:
            # Keep the original analytic opening contour and add the current
            # drone's two rows of three panels above the clear door opening.
            for x,z,iz,ix in self.columns((wall_u-.1,centre_v-1.65,wall_u+1.2,centre_v+1.65)):
                states=[self.c.palette[self.c.get(x,y,z)]["Name"] for y in (94,96)]
                if not any(n.endswith("_pane") or n.endswith("terracotta") for n in states):
                    continue
                d=float(self.v[iz,ix]-centre_v)
                divider=min(abs(d-.5),abs(d+.5))<.16 or abs(d)>1.4
                for y in range(94,99):
                    if y in (95,98) or divider:
                        self.c.set(x,y,z,"dark_oak_planks","facade")
                    else:
                        self.c.set(x,y,z,"gray_stained_glass_pane","window",PANE)
                        self.new_panes.add((x,y,z))
                        if y==94 and not self.c.get(x,y-1,z):
                            self.c.set(x,y-1,z,"dark_oak_slab","furniture",{"type":"top","waterlogged":"false"})
        # Explicit cardinal waypoints cross the open pair without clipping
        # its swung leaves at the adjacent rotated masonry corner.
        def local(x,z):
            x,z=x/2-self.origin[0],z/2-self.origin[1]
            return [x*self.cos+z*self.sin,-x*self.sin+z*self.cos]
        self.routes.append({"name":"ryan-central-entry" if central else "ryan-south-west-entry",
            "waypoints_uv_m":[[-10,centre_v],[-8,centre_v],[-3.3 if central else -2.1,centre_v],local(dx-.75,dz),local(dx+1.5,dz)],
            "feet_hints_blocks":[85.5,85.5,89.5,90,90]})

    def ryan(self):
        self.region("west-arcade-dressed-stone-palette",(-3.5,-33.8,2.2,-9.3),89,101)
        for x,z,_,_ in self.columns((-3.5,-33.8,2.2,-9.3)):
            for y in range(89,101):
                state=self.c.palette[self.c.get(x,y,z)]
                name=state["Name"].removeprefix("minecraft:")
                if name.startswith("smooth_red_sandstone"):
                    self.c.set(x,y,z,name.replace("smooth_red_sandstone","smooth_sandstone"),ROLES[int(self.c.roles[y+64,z-self.c.z_min,x-self.c.x_min])],state.get("Properties"))
        # The old arcade carving began at round(89.4), deleting the half slab
        # it had just laid. Restore the declared 89.5 walking top in its clear
        # bays; never cut a pier to make the floor continuous.
        for x,z,_,_ in self.columns((-3,-33,1.35,-10)):
            if not self.c.get(x,89,z) and self.c.get(x,88,z):
                self.c.set(x,89,z,"smooth_stone_slab","floor",SLAB)
        # The separate broad south staircase is visible beside the main flight
        # at 18 s. Match the inherited 69.75 m rounded landing and 67.75 m apron.
        self.region("south-west-stairs-and-landing",(-10.2,-10.0,-.35,-1.4),78,94)
        self.pave((-10,-9.8,-8,-1.6),85.5,clear=3)
        rise=np.floor(np.clip((self.u+8)/5,0,1)*8)/2
        self.pave((-8,-9.8,-3,-1.6),85.5+rise,clear=3)
        self.pave((-3,-9.8,-.4,-1.6),89.5,clear=3)
        # Two additional rails appear on the south flight, independent of the
        # six retained central-flight rails. Their lower posts touch each tread.
        for v in (-6.6,-2.3):
            path=[]
            for u in np.linspace(-7.9,-3.1,120):
                q=tuple(map(math.floor,self.world((u,v))))
                if path and q==path[-1]:continue
                if path and abs(q[0]-path[-1][0])+abs(q[1]-path[-1][1])==2:
                    choices=[(q[0],path[-1][1]),(path[-1][0],q[1])]
                    path.append(min(choices,key=lambda q:abs(self.local(q[0]+.5,q[1]+.5)[1]-v)))
                path.append(q)
            for x,z in path:
                iz,ix=z-self.c.z_min,x-self.c.x_min
                surface=85.5+float(rise[iz,ix])
                # A bar begins at an integer Y. Embed its foot in the tread's
                # rail column instead of hovering above a bottom half slab.
                base=math.floor(surface)
                self.c.set(x,base-1,z,"smooth_stone","pavement")
                for y in (base,base+1):
                    self.c.set(x,y,z,"iron_bars","railing",PANE)
        self.ryan_portal(-21.5,1.35,True)
        self.ryan_portal(-4.1,-.4,False)
        # Two source-photographed simple benches are recessed beside the
        # central door. Components are physically supported by the landing.
        self.region("recessed-entry-benches",(-.4,-25,1.4,-18),88,93)
        for v in (-24,-19):
            for x,z,_,_ in self.columns((.1,v-.7,.65,v+.7)):
                self.c.set(x,89,z,"smooth_stone","floor")
                self.c.set(x,90,z,"dark_oak_slab","furniture",SLAB)
        self.connect_local_panes()
        # Complete the newly cut timber jambs. Retained flanking glass that
        # terminated at the old infill cannot end freely at an open doorway.
        for centre_v,wall_u in ((-21.5,1.35),(-4.1,-.4)):
            for x,z,_,_ in self.columns((wall_u-.1,centre_v-1.8,wall_u+1.2,centre_v+1.8)):
                for y in range(90,94):
                    state=self.c.palette[self.c.get(x,y,z)]
                    if not state["Name"].endswith("_pane"):continue
                    if sum(state.get("Properties",{}).get(d)=="true" for d in ("north","south","east","west"))<2:
                        self.c.set(x,y,z,"dark_oak_planks","facade")
        self.connect_local_panes()
        self.ryan_stair_cheeks()
        # The source control selects one coherent pale dressed-stone family.
        # Keep the existing gable coping geometry, including stair/slab state
        # properties, while removing the isolated orange remnant palette.
        self.region("existing-gable-coping-palette",(-2,-44,36,3),98,125)
        coping=self.mask((-2,-44,36,3))
        for y in range(98,125):
            for iz,ix in np.argwhere(coping & (self.c.roles[y+64]==ROLES.index("trim"))):
                state=self.c.palette[int(self.c.data[y+64,iz,ix])]
                if state["Name"].startswith("minecraft:smooth_red_sandstone"):
                    self.c.set(int(ix+self.c.x_min),y,int(iz+self.c.z_min),state["Name"].replace("smooth_red_sandstone","smooth_sandstone"),"trim",state.get("Properties"))
        before=self.c.data.copy()
        connect_iron_rails(self.c)
        mask=self.allowed_mask()
        self.c.data[~mask]=before[~mask]

    def ryan_stair_cheeks(self):
        """Connected source-visible main-flight cheek and south separator.

        The narrow V=-10 gap between old/new paving retained tall DEM columns
        in v2. This is a masonry stair boundary in the 18-second aerial, not
        an exposed turf strip. Caps follow the retained stair rise and join
        the existing arcade pier, leaving both entry centerlines unchanged.
        """
        for name,v,strip in (
            ("main-north-stair-cheek",-33.12,(-8.2,-33.45,-2.55,-32.82)),
            ("main-south-stair-separator",-9.96,(-8.2,-10.25,-.4,-9.65)),
        ):
            # The dense analytical path adds only minimal orthogonal corner
            # cells where a 0.5 m raster would otherwise touch diagonally.
            columns={(x,z) for x,z,_,_ in self.columns(strip)}
            path=[]
            for u in np.linspace(strip[0]+.15,strip[2]-.1,180):
                q=tuple(map(math.floor,self.world((u,v))))
                if path and q==path[-1]:continue
                if path and abs(q[0]-path[-1][0])+abs(q[1]-path[-1][1])==2:
                    corners=[(q[0],path[-1][1]),(path[-1][0],q[1])]
                    path.append(min(corners,key=lambda q:abs(self.local(q[0]+.5,q[1]+.5)[1]-v)))
                path.append(q)
            columns.update(path)
            local=[self.local(x+.5,z+.5) for x,z in columns]
            self.region(name,(min(q[0] for q in local)-.01,min(q[1] for q in local)-.01,max(q[0] for q in local)+.01,max(q[1] for q in local)+.01),72,95)
            for x,z in sorted(columns):
                iz,ix=z-self.c.z_min,x-self.c.x_min
                u=float(self.u[iz,ix])
                walking=85.5+math.floor(float(np.clip((u+8)/5,0,1))*8)/2
                top_surface=walking+1.5
                top=math.ceil(top_surface)-1
                ground=int(self.c.ground_heights[iz,ix])
                bottom=min(ground,82)-1
                # Trim denotes this exterior site retaining structure; it
                # must not be counted as a widened building body/footprint.
                for y in range(bottom,top):
                    self.c.set(x,y,z,"stone_bricks","trim")
                self.c.set(x,top,z,"smooth_sandstone" if top_surface.is_integer() else "smooth_sandstone_slab","trim",None if top_surface.is_integer() else SLAB)
                for y in range(top+1,max(ground+1,93)):
                    role=ROLES[int(self.c.roles[y+64,iz,ix])]
                    if role in {"terrain","pavement","vegetation","railing"}:
                        self.c.set(x,y,z,"air","air")

    def chapel(self):
        # Correct the existing paired hinges. The former pair swung both
        # leaves into the centre, leaving two isolated narrow apertures.
        for x,y,z in ((-9,83,56),(-8,83,56)):
            for yy in (y,y+1):
                state=self.c.palette[self.c.get(x,yy,z)]
                props=dict(state["Properties"])
                props["hinge"]="right" if props["hinge"]=="left" else "left"
                self.c.set(x,yy,z,state["Name"],"door",props)
                self.door_cells.append([x,yy,z])
        self.region("south-paired-hinges",(-1.5,27.4,1.5,29.7),82,86)
        self.region("east-arcade-quad-threshold",(7.5,9.8,13.6,11.5),77,86)
        surface=np.where(self.u<10.7,83.,82.5)
        self.pave((7.5,9.8,13.6,11.5),surface,clear=2)
        self.routes=[
            {"name":"chapel-south-entrance","waypoints_uv_m":[[0,34],[0,31],self.local(-8,59),self.local(-8,53.5)],"feet_hints_blocks":[82.5,83,83,83]},
            {"name":"chapel-quad-east-entrance","waypoints_uv_m":[[13,10.6],[7.5,10.6],self.local(9,22),self.local(3,22)],"feet_hints_blocks":[82.5,83,83,83]},
            {"name":"chapel-east-arcade-longitudinal","waypoints_uv_m":[[6.5,5.8],[6.5,18.5]],"feet_hints_blocks":[83,83]},
        ]


def occupied_shapes(state, open_doors=False):
    """Use the established study shapes plus explicit doors and trapdoors."""
    n, p = state["Name"], state.get("Properties", {})
    if n.endswith("_door"):
        facing = p["facing"]
        if open_doors or p.get("open") == "true":
            right = p.get("hinge") == "right"
            facing = {"east": "north" if right else "south", "south": "east" if right else "west", "west": "south" if right else "north", "north": "west" if right else "east"}[facing]
        return ({"north": (0,0,13,16,16,16), "south": (0,0,0,16,16,3), "east": (0,0,0,3,16,16), "west": (13,0,0,16,16,16)}[facing],)
    if n.endswith("_trapdoor"):
        if p.get("open") == "true":
            return ({"north": (0,0,13,16,16,16), "south": (0,0,0,16,16,3), "west": (13,0,0,16,16,16), "east": (0,0,0,3,16,16)}[p["facing"]],)
        return ((0,13,0,16,16,16),) if p.get("half") == "top" else ((0,0,0,16,3,16),)
    if n.endswith("_slab") and p.get("type") == "double":
        return ((0,0,0,16,16,16),)
    return shapes(json.dumps(state, sort_keys=True))


def route_audit(c, amendment, routes, open_doors=False):
    @lru_cache(maxsize=None)
    def occupied(x, y, z):
        state = c.palette[c.get(x, y, z)]
        return tuple((x+a/16,y+b/16,z+d/16,x+e/16,y+f/16,z+g/16) for a,b,d,e,f,g in occupied_shapes(state,open_doors))
    reports = []
    for spec in routes:
        points = [amendment.world(uv) for uv in spec["waypoints_uv_m"]]
        hints = spec["feet_hints_blocks"]
        samples = []
        for i,(start,end) in enumerate(zip(points,points[1:])):
            for t in np.linspace(0,1,max(2,math.ceil(np.linalg.norm(end-start)/.1)+1)):
                samples.append(((1-t)*start+t*end,(1-t)*hints[i]+t*hints[i+1]))
        heights, failures = [], []
        for (x,z),hint in samples:
            boxes = []
            for xx in range(math.floor(x-.3),math.floor(x+.3)+1):
                for zz in range(math.floor(z-.3),math.floor(z+.3)+1):
                    for yy in range(math.floor(hint)-3,math.ceil(hint)+4):
                        boxes.extend(occupied(xx,yy,zz))
            candidates = sorted({b[4] for b in boxes if abs(b[4]-hint)<=1.5},key=lambda y:abs(y-hint))
            accepted = None
            for feet in candidates:
                body=(x-.3,feet,z-.3,x+.3,feet+1.8,z+.3)
                support, collision=0,False
                for b in boxes:
                    overlap=[min(body[i+3],b[i+3])-max(body[i],b[i]) for i in range(3)]
                    collision |= all(o>1e-7 for o in overlap)
                    if abs(b[4]-feet)<1e-7:
                        support += max(0,overlap[0])*max(0,overlap[2])
                if not collision and support>1e-7:
                    accepted=feet
                    break
            heights.append(accepted)
            if accepted is None:
                failures.append({"xz_blocks":[round(x,4),round(z,4)],"hint":round(hint,4)})
        steps=[abs(a-b) for a,b in zip(heights,heights[1:]) if a is not None and b is not None]
        large_steps=[{"xz_blocks":list(map(float,samples[i][0])),"before":a,"after":b} for i,(a,b) in enumerate(zip(heights,heights[1:])) if a is not None and b is not None and abs(a-b)>.50001]
        reports.append({**spec,"samples":len(samples),"passed":not failures and not large_steps,"maximum_step_blocks":max(steps,default=0),"large_steps":large_steps,"failures":failures})
    return {"passed":all(r["passed"] for r in reports),"player_width_blocks":.6,"player_height_blocks":1.8,"sample_spacing_max_blocks":.1,"doors_opened_for_access":open_doors,"routes":reports}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind",choices=("ryan-library","chapel"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--audit-only",action="store_true")
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Completed revisions are immutable; use a new directory")
    baseline=BASE/args.kind
    p=json.loads((baseline/"profile.json").read_text(encoding="utf-8"))
    manifest=json.loads((baseline/"manifest.json").read_text(encoding="utf-8"))
    c=load_canvas(baseline)
    before,roles=c.data.copy(),c.roles.copy()
    amendment=EntryAmendment(c,p,args.kind)
    getattr(amendment,"ryan" if args.kind=="ryan-library" else "chapel")()
    allowed=amendment.allowed_mask()
    changed=(before!=c.data)|(roles!=c.roles)
    outside=changed&~allowed
    if outside.any():
        yy,zz,xx=np.nonzero(outside)
        raise ValueError({"outside_declared_regions":int(outside.sum()),"examples":np.column_stack((xx+c.x_min,yy-64,zz+c.z_min))[:20].tolist()})
    roof=roles==ROLES.index("roof")
    if np.any(changed&roof):
        raise ValueError("An entry amendment changed an existing roof cell")
    physical=route_audit(c,amendment,amendment.routes,True)
    summary={"passed":physical["passed"],"routes":[{"name":r["name"],"passed":r["passed"],"maximum_step_blocks":r["maximum_step_blocks"],"failures":len(r["failures"]),"examples":r["failures"][:3],"large_steps":r["large_steps"][:3]} for r in physical["routes"]]}
    print(json.dumps(summary),flush=True)
    if args.audit_only:
        return
    if not physical["passed"]:
        raise ValueError("Entry routes require repair before exporting a review candidate")
    p.update(revision=f"20260927-{args.kind}-entry-amendment",baseline_study=baseline.relative_to(ROOT).as_posix(),baseline_archive_sha256=digest(baseline/"sample-blocks.npz"),scope="Exact integrated source amended only at observed exterior entries and declared adjoining paving. Main footprints, bodies and roof dimensions retained.",mutation_regions=amendment.regions,walking_routes=amendment.routes)
    p["material_review"]={"status":"preserve_exact_baseline_except_declared_entry_materials","basis":"Reference agent current drone/contractor comparison 2026-09-27; coherent smooth_sandstone for Ryan dressed arcade, existing Chapel palette retained."}
    p.setdefault("assembly_site_bounds_uv_m",[]).extend([r["bounds_uv_m"] for r in amendment.regions])
    p["uncertainties"].extend(["New entrance surfaces retain the existing interpreted landing datum; photographs constrain plan and stairs but do not provide a surveyed stair tread count.","Operating door panels retain vanilla one-block width within the interpreted facade aperture; fine historic door and sash profiles are below the 0.5 m construction grid.","This amendment completes the declared entry approaches; concealed elevations, fine tracery and library interiors are not a photographic completion claim."])
    if args.kind=="ryan-library":
        views=[("ryan-west-front",(-25,-21.5,72),(1,-21.5,75),72), ("ryan-central-entry",(-5.5,-21.5,71), (2,-21.5,72),80), ("ryan-south-west-steps",(-13,-1,70),(-1,-5,72),78), ("ryan-arcade-oblique",(-9,-37,73),(-.5,-20,72),80), ("ryan-roof-preservation",(-22,-52,99),(10,-20,76),74)]
    else:
        views=[("chapel-south-threshold",(-8,36,69),(0,28,68),76), ("chapel-east-walk-join",(17,10.6,68),(5,10.6,67),76), ("chapel-east-arcade",(6.5,18.4,67.6),(6.5,7,67.4),80), ("chapel-east-whole",(32,17,73),(3,8,73),72)]
    cameras=[]
    for name,eye,target,fov in views:
        def point(t):
            x,z=amendment.world(t[:2]); return [float(x),2*(t[2]-25),float(z)]
        cameras.append({"name":name,"eye":point(eye),"target":point(target),"fov":fov})
    yy,zz,xx=np.nonzero(changed)
    delta={"baseline_archive_sha256":p["baseline_archive_sha256"],"changed_state_or_role_cells":int(changed.sum()),"outside_declared_regions":0,"preserved_cells":int((~changed).sum()),"unchanged_existing_roof_cells":int(roof.sum()),"changed_bounds_xyz_blocks":[[int(xx.min()+c.x_min),int(yy.min()-64),int(zz.min()+c.z_min)],[int(xx.max()+c.x_min),int(yy.max()-64),int(zz.max()+c.z_min)]],"regions":amendment.regions}
    evidence={"baseline":{"study":p["baseline_study"],"archive_sha256":p["baseline_archive_sha256"]},"bounded_mutation_parity":delta,"generator_sha256":digest(Path(__file__)),"uncertainties":p["uncertainties"],"new_door_cells":amendment.door_cells}
    if "source_roof" in manifest:evidence["source_roof"]=manifest["source_roof"]
    finish_study(c,p,args.output,cameras,evidence)
    digest_new=digest(args.output/"sample-blocks.npz")
    physical["archive_sha256"]=digest_new
    write_json(args.output/"entry-route-audit.json",physical)
    write_json(args.output/"bounded-mutation-parity.json",delta)
    coords=np.column_stack((xx+c.x_min,yy-64,zz+c.z_min)).astype(np.int32)
    np.savez_compressed(args.output/"entry-delta.npz",coords=coords,before_state_ids=before[changed],after_state_ids=c.data[changed],before_role_ids=roles[changed],after_role_ids=c.roles[changed],palette_json=np.array(json.dumps(c.palette)))
    shutil.copy2(Path(__file__),args.output/"entry-generator.py")
    parity,errors,_,chunks=compare_world(read_archive(args.output/"sample-blocks.npz"),args.output/"world")
    write_json(args.output/"export-parity.json",{"archive_sha256":digest_new,"chunks":chunks,"errors":errors,**parity})
    if errors:raise ValueError(errors)
    print(json.dumps({"output":str(args.output),"archive_sha256":digest_new,"changes":delta,"export_errors":errors}),flush=True)


if __name__=="__main__":
    main()
