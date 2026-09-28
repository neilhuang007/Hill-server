"""Photo-controlled Quadrivium facade paths on its measured campus envelope.

The long walls are analytic planes, voxelized as cardinal paths. Roof samples
never choose a window's depth. Only the two photographed bays curve; the west
wing's measured bend is retained pending closer source registration.
"""

from dataclasses import replace
import math

import numpy as np
from build_hill_chapel_sample import ROLES
from campus_reference_details import roof_patch

PANE = dict(north="false", south="false", east="false", west="false", waterlogged="false")
WEST = [(-42.0, -9.3), (-33.5, -6.45), (-15.9, -7.25)]
EAST = [(4.3, -5.32), (44.0, -8.25)]
WEST_REAR = [(-46.0, 0.0), (-35.5, 5.23), (-15.1, 4.70)]
EAST_REAR = [(4.7, 6.7), (40.3, 5.06)]


def front(u, side="west"):
    points = WEST if side == "west" else EAST
    return float(np.interp(u, [p[0] for p in points], [p[1] for p in points]))


def prepare_roof(r, f, p):
    mask = r.footprint_mask & (r.heights > 71)
    r = replace(r, footprint_mask=mask, missing_mask=r.missing_mask & mask,
                face_indices=np.where(mask, r.face_indices, -1))
    for center in [-38, -28, -18, 14.5, 31.3]:
        r = roof_patch(r, f, (center-1.9, -7.8, center+1.9, -1),
                       eave=77.3, ridge=80.9, ridge_axis="v", combine="max")
    # The original link is already measured as faces 1/21. The earlier U=-9.4
    # interpretation duplicated it; retain the actual U≈-5.8 source ridge.
    return r


class Quadrivium:
    def __init__(self, f, p):
        self.f, self.c, self.p = f, f.c, p
        self.openings = []
        self.partial_backing = []
        self.wall_records = []
        self.eave_closures = []
        self.bay_cap_cells=set()

    def set(self, q, block, role="facade", props=None):
        self.c.set(*map(int, q), block, role, props)

    def name(self, q):
        return self.c.palette[self.c.get(*q)]["Name"]

    def uv(self, q):
        x, z = q
        return (float(self.f.u[z-self.c.z_min, x-self.c.x_min]),
                float(self.f.v[z-self.c.z_min, x-self.c.x_min]))

    def path(self, points):
        """Supercover a measured polyline; use one deliberate inside corner."""
        result = []
        for a, b in zip(points, points[1:]):
            count = max(2, math.ceil(math.dist(a, b) * 50))
            for t in np.linspace(0, 1, count):
                u, v = (1-t)*np.asarray(a) + t*np.asarray(b)
                x, z = np.floor(self.f.world(u, v)*self.c.scale).astype(int)
                q = (int(x), int(z))
                if result and q == result[-1]:
                    continue
                if result and abs(q[0]-result[-1][0])+abs(q[1]-result[-1][1]) == 2:
                    result.append((q[0], result[-1][1]))
                result.append(q)
        return list(dict.fromkeys(result))

    def window_path(self, center, width, face, *, end=False):
        points = [(face(s), s) if end else (s, face(s))
                  for s in np.linspace(center-width/2-.25, center+width/2+.25,
                                       max(4, math.ceil((width+.5)*30)))]
        return self.path(points)

    def backing(self, q, inward, material="mud_bricks"):
        x, y, z = q
        b = (x+inward[0], y, z+inward[1])
        if self.name(b).endswith(("_pane", "iron_bars", "_door")):
            return
        self.set(b, material)
        self.partial_backing.append((q, b))

    def wall(self, name, points, *, eave=75.75, inward=(0, 1)):
        path = self.path(points)
        lower = self.f.height_y(63.0)
        for x, z in path:
            iz, ix = z-self.c.z_min, x-self.c.x_min
            roofs = np.flatnonzero(self.c.roles[:, iz, ix] == ROLES.index("roof"))
            top = int(roofs[0])+self.c.y_min if len(roofs) else self.f.height_y(eave)
            top = max(top, self.f.height_y(eave))
            for y in range(lower, top):
                if self.name((x,y,z)) == "minecraft:air" or y < self.f.height_y(eave):
                    self.set((x,y,z), "mud_bricks")
            # A second inside column closes thin-wall corner and frame returns.
            for y in range(lower, min(top, self.f.height_y(eave))):
                q = (x+inward[0], y, z+inward[1])
                if self.name(q) == "minecraft:air":
                    self.set(q, "mud_bricks")
        self.wall_records.append(dict(name=name, controls_uv_m=points,
                                      column_count=len(path), inward=list(inward)))
        return path

    def clear_raw_lower_walls(self):
        # The shell drops a wall at every roof discontinuity. Below the eave
        # those are unsupported buttresses, not measured facade breaks.
        mask = self.f.local_mask((-47,-11,45,16))
        a,b = self.f.height_y(63)+64,self.f.height_y(75.75)+64
        region, roles = self.c.data[a:b], self.c.roles[a:b]
        selected = (roles == ROLES.index("facade")) & mask[None]
        self.f.features["raw_lower_shell_wall_cells_replaced"] = int(selected.sum())
        region[selected], roles[selected] = 0,0

    def aperture(self, label, center, face, sill, width, height, lights=1,
                 *, inward=(0,1), end=False, shape="rectangle", door=False,
                 material="smooth_quartz", sparse=False, slim_frame=False):
        path = self.window_path(center, width, face, end=end)
        if len(path) < 4:
            # A narrow 0.85m lancet still needs an actual pane between jambs.
            path = self.window_path(center, max(1.0,width), face, end=end)
        y0, y1 = self.f.height_y(sill), self.f.height_y(sill+height)
        edge = len(path)-1
        mullions = {round(i*edge/lights) for i in range(1,lights)}
        panes, partials, door_cells = [],[],[]
        sheet_columns=set(path)
        for j,(x,z) in enumerate(path):
            # The first and final raster columns are the slender jambs.
            jamb = j in (0,edge)
            d = abs(2*j/edge-1)
            top = y1
            if shape in {"pointed", "triangle", "gable"}:
                rise = (7 if shape=="gable" else
                        min(y1-y0-2, round(width*1.5)) if shape == "pointed" else y1-y0)
                top = y1-round(rise*d)
            for y in range(y0-1,y1+1):
                q=(x,y,z)
                if shape in {"triangle","gable"} and y>top:
                    # The glazed crown has a pitched roof silhouette, not a
                    # rectangular bounding wall above its sloping head.
                    self.set(q,"air","air")
                elif shape=="pointed" and y>top:
                    self.set(q,"mud_bricks")
                elif jamb:
                    if slim_frame and y>=y0 and y<top:
                        self.set(q,"black_stained_glass_pane","window",PANE)
                        panes.append(q)
                    else:
                        role="trim" if material!="quartz_bricks" else "facade"
                        self.set(q, "mud_bricks" if slim_frame else material, role)
                elif y == y0-1 or y == top:
                    props=dict(type="top" if y == y0-1 else "bottom", waterlogged="false")
                    if slim_frame and y==y0-1:
                        self.set(q,"mud_bricks")
                    else:
                        self.set(q, "smooth_quartz_slab", "trim", props)
                    self.backing(q,inward)
                    # Every top sill touches a full masonry course below;
                    # each bottom head is held by the full course above.
                    if y==y0-1 or shape not in {"triangle","gable"}:
                        self.set((x,y-1 if y==y0-1 else y+1,z),"mud_bricks")
                    partials.append(q)
                else:
                    # Clear exactly two reveal columns, not a sampled contour.
                    if (x+inward[0],z+inward[1]) not in sheet_columns:
                        self.set((x+inward[0],y,z+inward[1]),"air","air")
                    if door:
                        self.set(q,"air","air")
                        b=(x+inward[0],y,z+inward[1])
                        self.set(b,"dark_oak_planks")
                        door_cells.append(b)
                    else:
                        name="black_stained_glass_pane" if j in mullions else "gray_stained_glass_pane"
                        self.set(q,name,"window",PANE)
                        panes.append(q)
            if shape=="pointed" and not jamb and top<y1:
                # Inverted arch shoulders remain backed and keep their full
                # top surface against the brick above; the aperture cap stays
                # a bottom slab so the glass does not meet an empty half-cell.
                facing=("east" if j<edge/2 else "west") if not end else ("south" if j<edge/2 else "north")
                q=(x,top+1,z)
                self.set(q,"smooth_quartz_stairs","trim",
                         dict(facing=facing,half="top",shape="straight",waterlogged="false"))
                self.backing(q,inward)
                partials.append(q)
            elif shape in {"triangle","gable"}:
                # Smooth pale stair coping along the exact peaked boundary.
                side=("east" if j<edge/2 else "west") if not end else ("south" if j<edge/2 else "north")
                self.set((x,top,z),"smooth_quartz_stairs","trim",
                         dict(facing=side,half="bottom",shape="straight",waterlogged="false"))
                self.backing((x,top,z),inward)
        if door:
            candidates=path[max(1,len(path)//2-1):max(1,len(path)//2-1)+2]
            for j,(x,z) in enumerate(candidates):
                for dy,half in [(0,"lower"),(1,"upper")]:
                    q=(x+inward[0],y0+dy,z+inward[1])
                    self.set(q,"dark_oak_door","door",dict(facing="north",half=half,
                             hinge="left" if j==0 else "right",open="false",powered="false"))
                self.set((x+inward[0],y0-1,z+inward[1]),"smooth_stone","floor")
                self.set((x,y0-1,z),"smooth_stone","floor")
                # A short, physically supported entrance apron meets the
                # measured grade. Only the two door-width approach columns
                # are touched; the falling campus terrain stays as measured.
                dx,dz=inward
                for distance in (1,2):
                    ax,az=x-dx*distance,z-dz*distance
                    grade=self.c.ground_at(ax,az)
                    if grade>=y0:
                        self.set((ax,y0,az),"smooth_quartz_stairs","trim",
                                 dict(facing="north",half="bottom",shape="straight",waterlogged="false"))
                    # Shell excavation does not update ground metadata. Find
                    # occupied support in the actual canvas, not the old DTM.
                    actual=next((yy for yy in range(y0-1,self.f.height_y(62)-1,-1)
                                 if self.c.get(ax,yy,az)),self.f.height_y(62))
                    for yy in range(actual+1,y0):
                        self.set((ax,yy,az),"smooth_stone","floor")
            self.f.features["operable_double_portals"]+=1
        self.openings.append(dict(label=label,center=center,sill=sill,width=width,
                                  height=height,lights=lights,shape=shape,door=door,
                                  pane_cells=[list(q) for q in panes],
                                  path_xz=[list(q) for q in path],inward=list(inward),
                                  partial_cells=[list(q) for q in partials]))
        return path

    def pointed_portal(self, center, face_v, width, height):
        """A connected limestone arch around an actual peaked dark aperture.

        The eight-neighbour frame ring keeps the outer stone continuous at
        each raster rise. No disconnected slab motifs stand in for an arch.
        """
        label=f"pointed-portal-{center}"
        path=self.aperture(label,center,lambda _:face_v,67.75,width,height,door=True)
        y0=self.f.height_y(67.75)
        edge=len(path)-1
        peak=round(edge/2)
        apex=round(height*2)
        spring=max(3,apex-3)
        radius=max(1,peak-1,edge-1-peak)
        opening=set()
        for j in range(1,edge):
            top=apex-math.ceil((apex-spring)*abs(j-peak)/radius)
            opening.update((j,h) for h in range(top))
        ring={(j+dj,h+dh) for j,h in opening
              for dj in (-1,0,1) for dh in (-1,0,1)}-opening
        for j,(x,z) in enumerate(path):
            for h in range(apex+2):
                q,b=(x,y0+h,z),(x,y0+h,z+1)
                if (j,h) in opening:
                    self.set(q,"air","air")
                    self.set(b,"dark_oak_planks")
                elif (j,h) in ring:
                    self.set(q,"smooth_quartz","trim")
                    self.set(b,"smooth_quartz","trim")
                else:
                    self.set(q,"mud_bricks")
                    self.set(b,"mud_bricks")
            # A half-height outer coping keeps the crest narrow, backed by
            # its full stone return and the connected ring directly below.
            caps=[h for jj,h in ring if jj==j and h>=0]
            if caps:
                h=max(caps)
                q=(x,y0+h,z)
                self.set(q,"smooth_quartz_slab","trim",dict(type="bottom",waterlogged="false"))
                self.backing(q,(0,1),"smooth_quartz")
        for j,(x,z) in enumerate(path[max(1,len(path)//2-1):max(1,len(path)//2-1)+2]):
            for dy,half in [(0,"lower"),(1,"upper")]:
                self.set((x,y0+dy,z+1),"dark_oak_door","door",
                         dict(facing="north",half=half,hinge="left" if j==0 else "right",open="false",powered="false"))
        self.openings[-1]["shape"]="pointed_connected_arch"
        self.openings[-1]["arch_opening_cells"]=[list(q) for q in sorted(opening)]

    def bay(self, center, width):
        radius=width/2
        def curve(u):
            t=min(1,abs((u-center)/radius))
            return front(u)-1.25*math.sqrt(max(0,1-t*t))
        path=self.path([(u,curve(u)) for u in np.linspace(center-radius,center+radius,150)])
        # Back to the original wall plane at each side; no square detached box.
        points=[(center-radius,front(center-radius))]
        points += [(u,curve(u)) for u in np.linspace(center-radius,center+radius,150)]
        points += [(center+radius,front(center+radius))]
        self.wall(f"curved-bay-{center}",points,eave=76.2)
        for sill in (68.35,72.4):
            sheet=set(path)
            # Remove the old straight host wall behind the bay's own glass,
            # bounded by this opening and the original inward wall return.
            selected=self.f.local_mask((center-radius+.25,front(center)-2,
                                        center+radius-.25,front(center)+1.2))
            for x,z,iz,ix in self.f.each_column(selected):
                u,v=self.uv((x,z))
                if (x,z) in sheet or v<curve(u)+.2:continue
                for y in range(self.f.height_y(sill),self.f.height_y(sill+2.5)):
                    self.set((x,y,z),"air","air")
            self.aperture(f"curved-bay-{center}-{sill}",center,curve,sill,width-.2,2.5,lights=4)
        # The photographed curved brick crown has a thin, fully backed cap.
        for x,z in path:
            y=self.f.height_y(76.2)
            self.set((x,y,z),"smooth_quartz_slab","trim",dict(type="bottom",waterlogged="false"))
            self.set((x,y-1,z),"mud_bricks")
            self.backing((x,y,z),(0,1))
            self.bay_cap_cells.add((x,y,z))

    def gable(self, center):
        face=lambda _: -7.8
        path=self.window_path(center,3.8,face)
        y0=self.f.height_y(75.4)
        for x,z in path:
            u,_=self.uv((x,z))
            top=self.f.height_y(77.3+3.6*max(0,1-abs(u-center)/1.9))
            for y in range(y0,top):
                self.set((x,y,z),"mud_bricks")
            # Continuous stair/slab coping; never isolated full quartz teeth.
            side="east" if u<center else "west"
            self.set((x,top,z),"smooth_quartz_stairs","trim",
                     dict(facing=side,half="bottom",shape="straight",waterlogged="false"))
            self.set((x,top-1,z),"mud_bricks")
            self.backing((x,top,z),(0,1))
        self.aperture(f"gable-{center}",center,face,76.0,1.6 if center>0 else 1.9,1.9,2)

    def link(self):
        f,c=self.f,self.c
        # Recolor the two source roof faces without moving a single vertex.
        bounds=np.isin(f.r.face_indices,[1,21])
        for sid,state in enumerate(list(c.palette)):
            if not state["Name"].startswith("minecraft:stone_brick"):continue
            target=state["Name"].replace("stone_bricks","smooth_quartz").replace("stone_brick_","smooth_quartz_")
            selected=(c.data==sid)&(c.roles==ROLES.index("roof"))&bounds[None]
            c.data[selected]=c.state(target,state.get("Properties"))
        # Fill only the modern flank envelope, removing its obsolete low
        # slate return (face7) from the photographed three-storey panels.
        flank=f.local_mask((-15.6,-8.5,4.3,-5.5)) & ~f.local_mask((-9.6,-8.5,-2.7,-5.5))
        a,b=f.height_y(67.75)+64,f.height_y(79.95)+64
        old_roof=(c.roles[a:b]==ROLES.index("roof"))&flank[None]
        c.data[a:b][old_roof]=0;c.roles[a:b][old_roof]=0
        self.wall("link-west-front-panel",[(-15.6,-6.7),(-9.6,-6.7)],eave=79.95)
        self.wall("link-east-front-panel",[(-2.7,-6.7),(4.3,-6.7)],eave=79.95)
        self.wall("link-front",[(-9.55,-8.3),(-2.95,-8.3)],eave=80.0)
        path=self.aperture("link-continuous-gable",-6.25,lambda _: -8.3,
                           67.95,6.1,15.6,4,shape="gable",sparse=True,slim_frame=True)
        # Exactly three thin floor rails, not an iron lattice at every block.
        for level in (70.8,74.7,78.8):
            y=f.height_y(level)
            for x,z in path[1:-1]:
                self.set((x,y,z),"black_stained_glass_pane","window",PANE)
        for u,inward in [(-9.55,(1,0)),(-2.95,(-1,0))]:
            self.wall(f"link-glazed-return-{u}",[(u,-8.3),(u,-6.5)],eave=80.0,inward=inward)
            side=self.aperture(f"link-return-{u}",-7.4,lambda _,u=u:u,
                              67.95,1.3,11.55,1,end=True,inward=inward,sparse=True,slim_frame=True)
            for level in (70.8,74.7,78.8):
                for x,z in side[1:-1]:
                    self.set((x,f.height_y(level),z),"black_stained_glass_pane","window",PANE)
        for center,width in [(-12.7,5.4),(.7,5.0)]:
            # The re-registered fields now fit on both sides of the source
            # gable, with brick piers and no overlap onto the historic bay.
            f.box((center-width/2,-6.8,center+width/2,-6.1),67.75,79.95,"quartz_bricks","facade")
            for sill in (68.4,72.35,76.3):
                self.aperture(f"link-panel-{center}-{sill}",center,lambda _: -6.7,
                              sill,max(.9,width-.7),2.75,1 if width<2 else 3,material="quartz_bricks")
            # The pane schedule cuts a continuous pale small-unit panel;
            # neither cap backing nor raster phase may turn its spandrels
            # into unrelated brown belts.
            panel=self.path([(center-width/2,-6.7),(center+width/2,-6.7)])
            for x,z in panel:
                for y in range(f.height_y(67.75),f.height_y(79.95)):
                    for zz in (z,z+1):
                        if self.name((x,y,zz))=="minecraft:mud_bricks":
                            self.set((x,y,zz),"quartz_bricks")
        self.aperture("link-door",-6.25,lambda _: -8.3,67.75,1.8,2.4,door=True)

    def seal_authored_pane_ends(self):
        """Complete caps after overlapping portal/link passes, within paths."""
        for opening in self.openings:
            for q in opening["pane_cells"]:
                x,y,z=q
                if not self.name(q).endswith("_pane"):continue
                for dy in (-1,1):
                    cap=(x,y+dy,z)
                    if self.name(cap)=="minecraft:air":
                        self.set(cap,"smooth_quartz_slab","trim",
                                 dict(type="top" if dy<0 else "bottom",waterlogged="false"))
                        self.backing(cap,opening["inward"])
                def full_join(at):
                    name=self.name(at)
                    return name!="minecraft:air" and not name.endswith(("_slab","_stairs","_door"))
                joins=sum(full_join((x+dx,y,z+dz)) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)))
                if joins<2:
                    # A narrowed crown meets the occupied full side of its
                    # bounded masonry frame; a neighbouring slab alone cannot
                    # receive the arm of a pane.
                    for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                        at=(x+dx,y,z+dz)
                        if self.name(at).endswith(("_slab","_stairs")):
                            self.set(at,"smooth_quartz","trim")
                            joins+=1
                            if joins>=2:break
        # Multiple nearby groups can overwrite the shared cardinal bridge.
        # Repeat only inside the union of their authored one-cell reveals.
        from campus_window_frames import close_diagonal_pane_corners
        allowed=set()
        for opening in self.openings:
            dx,dz=opening["inward"]
            for x,y,z in opening["pane_cells"]:
                allowed.add((x,y,z));allowed.add((x+dx,y,z+dz))
        close_diagonal_pane_corners(self.c,allowed,inward=(0,1))
        for x,y,z in allowed:
            if not self.name((x,y,z)).endswith("_pane"):continue
            for dy in (-1,1):
                cap=(x,y+dy,z)
                if self.name(cap)=="minecraft:air":
                    self.set(cap,"smooth_quartz","trim")
                    self.backing(cap,(0,1))
        # Side-glass reveals are authored after the front crown; restore only
        # their two accidentally cleared inward caps, without touching glass.
        for q,b in self.partial_backing:
            if self.name(q).endswith(("_stairs","_slab")) and self.name(b)=="minecraft:air":
                self.set(b,"mud_bricks")
            elif q in self.bay_cap_cells and self.name(b).endswith("_pane"):
                # The source bay crown overlaps the bottom of the dormer
                # behind it. Seat that lower sill on the crown's return;
                # never leave a half-cell of air between cap and glazing.
                self.set(b,"smooth_quartz","trim")


def build_details(f,p):
    q=Quadrivium(f,p)
    q.clear_raw_lower_walls()
    q.wall("west-historic-front",WEST)
    q.wall("west-end",[(-42,-9.3),(-46,0)],inward=(1,0))
    q.wall("west-rear",WEST_REAR,inward=(0,-1))
    q.wall("east-historic-front",EAST)
    q.wall("east-end",[(44,-8.25),(44.4,2.2)],inward=(-1,0))
    q.wall("east-rear",EAST_REAR,inward=(0,-1))
    q.wall("east-rear-measured-return",[(40.3,5.06),(40.0,2.7),(44.4,2.2)],inward=(0,-1))
    q.wall("link-west",[(-15.9,-7.25),(-15.1,14.2)],eave=79.95,inward=(1,0))
    q.wall("link-rear",[(-15.1,14.2),(1.7,14.2)],eave=79.95,inward=(0,-1))
    q.wall("link-east",[(1.7,14.2),(1.4,6.9),(4.7,6.7),(4.3,-5.32)],eave=79.95,inward=(-1,0))
    for level in (67.75,71.85,76.05): f.floor_plate(level)
    for sill in (68.35,72.4):
        # The leftmost photo registration falls beyond the bent front's roof;
        # its opening is placed on the measured west return, not in open air.
        q.aperture(f"west-return-{sill}",-5.9,lambda v: -42-(v+9.3)*4/9.3,
                   sill,1.15,2.5,end=True,inward=(1,0))
        for center in (-32.9,-23.2):
            q.aperture(f"west-flat-{center}-{sill}",center,front,sill,4.5,2.5,4)
        for center in (-35.6,-20.4):
            q.aperture(f"west-lancet-{center}-{sill}",center,front,sill+.1,1.05,2.7,shape="pointed")
        for center,width,lights in [(7.8,5.2,4),(23.1,8.6,6),(38.9,5.7,4)]:
            q.aperture(f"east-flat-{center}-{sill}",center,lambda u: front(u,"east"),sill,width,2.5,lights)
    for center,width in [(-38.8,4.0),(-17.6,3.5)]:q.bay(center,width)
    for center in (-28,14.5,31.3):
        face_v=-7.15 if center<0 else -7.8
        q.wall(f"portal-pier-{center}",[(center-1.7,face_v),(center+1.7,face_v)],eave=77.3)
        q.pointed_portal(center,face_v,2.5 if center<0 else 2.05,3.6 if center<0 else 3.3)
        if center>0:
            q.aperture(f"portal-upper-{center}",center,lambda _: -7.8,72.1,1.1,2.8)
        else:
            x,z=q.path([(center,-7.18),(center+.05,-7.18)])[0]
            q.set((x,f.height_y(73.45),z),"smooth_quartz","trim")
    for center in (-38,-28,-18,14.5,31.3):q.gable(center)
    for sill,width,lights in [(68.35,6.7,6),(72.4,6.7,6),(77.2,2.0,2)]:
        q.aperture(f"east-end-{sill}",-3.1,lambda v:44+(v+8.25)*.5/13.1,sill,
                   width,2.1 if sill>77 else 2.5,lights,end=True,inward=(-1,0))
    q.link()
    for sill in (64.2,68.5,72.5):
        for center in (-40,-33,-26,-19,8,16,24,32,38.5):
            points=WEST_REAR if center<0 else EAST_REAR
            face=lambda u,points=points:float(np.interp(u,[p[0] for p in points],[p[1] for p in points]))
            q.aperture(f"inferred-rear-{center}-{sill}",center,face,sill,2.5,2.2,2,inward=(0,-1))
    q.seal_authored_pane_ends()
    p["facade_path_evidence"]={"walls":q.wall_records,"openings":q.openings,
                               "partial_backing":[[list(a),list(b)] for a,b in q.partial_backing],
                               "source_exceptions":[
        "Photographed west-front doors/bays stand above Roofer face 36 at 68.1m; wall paths continue through that falsely low frontage sample.",
        "Measured west wing turns at U=-33.5; preserve the two source straight runs pending improved photographic registration.",
        "Photo U=-44 single is on the measured angled west return; it must not float beyond the roof-covered wall."]}
    f.features.update(historic_pointed_portals=3,historic_curved_bays=2,
                      individual_gable_dormers=5,modern_three_storey_glazed_link=1,
                      analytic_facade_runs=len(q.wall_records),sparse_link_horizontal_rails=3)
