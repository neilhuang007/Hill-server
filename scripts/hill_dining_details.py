"""Bounded Dining Hall amendment on an immutable accepted Athey canvas.

All new walls follow metric lines, then use a connected cardinal raster path.
Source roof sampling is never used to vary a photographed straight facade.
"""

import math
import json
from collections import Counter
from pathlib import Path

import numpy as np
from build_hill_chapel_sample import ROLES
from campus_reference_details import ReferenceExterior

PANE = dict(north="false",south="false",east="false",west="false",waterlogged="false")
SLAB = dict(type="bottom",waterlogged="false")


class DiningAmendment(ReferenceExterior):
    def __init__(self,canvas,profile,raster,offset):
        super().__init__(canvas,profile,raster,offset)
        self.mutation_mask = np.zeros_like(canvas.roles,dtype=bool)
        self.openings=[]
        self.partial_backing=[]
        self.wall_paths=[]
        self.pane_cells=set()
        self.region_masks={}
        for region in profile["mutation_regions"]:
            mask=self.local_mask(region["bounds_uv_m"])
            if region.get("source_faces") is not None:
                mask &= np.isin(raster.face_indices,region["source_faces"])
            if region.get("exclude_source_faces"):
                mask &= ~np.isin(raster.face_indices,region["exclude_source_faces"])
            if region.get("clip_source_footprint"):
                mask &= raster.footprint_mask
            if region.get("exclude_source_ground"):
                mask &= ~raster.footprint_mask
            if region.get("protect_high_athey"):
                mask &= ~(raster.footprint_mask & (raster.heights >= 80.5))
            a,b=(self.height_y(v)-canvas.y_min for v in region["height_navd88_m"])
            self.mutation_mask[a:b,mask]=True
            self.region_masks[region["name"]]=mask
        # Every measured occupied fringe column of the court is protected.
        protected=self.local_mask(profile["court"]["bounds_uv_m"]) & raster.footprint_mask
        self.mutation_mask[:,protected]=False
        self.protected_fringe_count=int(protected.sum())
        self.original_fringe_count=self.protected_fringe_count
        exception=profile.get("court_spur_exception")
        if exception:
            selected=self.local_mask(exception["bounds_uv_m"]) & (raster.face_indices==10)
            a,b=(self.height_y(v)-canvas.y_min for v in exception["height_navd88_m"])
            self.mutation_mask[a:b,selected]=True
            self.region_masks["court_spur_exception"]=selected
            self.protected_fringe_count-=int((selected&protected).sum())
        for x,y,z in profile.get("foundation_repair_cells",[]):
            self.mutation_mask[y-canvas.y_min,z-canvas.z_min,x-canvas.x_min]=True

    def set_cell(self,q,block,role="facade",props=None):
        x,y,z=map(int,q)
        if not self.mutation_mask[y-self.c.y_min,z-self.c.z_min,x-self.c.x_min]:
            raise ValueError(f"Dining operation outside declared mutation mask: {q} {block}")
        self.c.set(x,y,z,block,role,props)

    def name(self,q):
        return self.c.palette[self.c.get(*q)]["Name"]

    def fill(self,mask,low,high,block,role="facade",props=None,preserve_roof=False):
        a,b=self.height_y(low)-self.c.y_min,self.height_y(high)-self.c.y_min
        authorized=self.mutation_mask[a:b] & mask[None]
        if preserve_roof:
            authorized &= self.c.roles[a:b]!=ROLES.index("roof")
        state=self.c.state(block,props)
        self.c.data[a:b][authorized]=state
        self.c.roles[a:b][authorized]=ROLES.index(role) if state else 0

    def path(self,points):
        """Connected raster of declared straight control segments."""
        result=[]
        for start,end in zip(points,points[1:]):
            for weight in np.linspace(0,1,max(2,math.ceil(math.dist(start,end)*50))):
                p=(1-weight)*np.asarray(start)+weight*np.asarray(end)
                x,z=np.floor(self.world(*p)*self.c.scale).astype(int)
                q=int(x),int(z)
                if result and q==result[-1]:
                    continue
                if result and abs(q[0]-result[-1][0])+abs(q[1]-result[-1][1])==2:
                    result.append((q[0],result[-1][1]))
                result.append(q)
        return list(dict.fromkeys(result))

    def wall(self,name,points,low,high,*,inward=(0,1),thickness=2):
        path=self.path(points)
        for x,z in path:
            for depth in range(thickness):
                for y in range(self.height_y(low),self.height_y(high)):
                    self.set_cell((x+inward[0]*depth,y,z+inward[1]*depth),self.p["materials"]["facade"])
        self.wall_paths.append({"name":name,"controls_uv_m":points,"column_count":len(path),"inward":inward,"thickness_blocks":thickness})
        return path

    def aperture(self,spec,at,*,trim=True,shape="rectangle",glazed=True):
        center,width=spec["center_u_m"],spec["width_m"]
        path=self.path([(center-width/2,at),(center+width/2,at)])
        floor=self.height_y(spec["sill_navd88_m"])
        top=self.height_y(spec["head_navd88_m"])
        panes=[]
        sheet=set(path)
        # One connected path is the glazing plane. Full masonry immediately
        # behind each head/jamb backs all partial front blocks.
        for index,(x,z) in enumerate(path):
            edge=index in (0,len(path)-1)
            shoulder=0
            if shape=="chamfered":
                shoulder=max(0,2-min(index,len(path)-1-index))
            head=top-shoulder
            for y in range(floor-1,top+1):
                q=(x,y,z)
                back=(x,y,z+1)
                if edge or y>head:
                    self.set_cell(q,self.p["materials"]["trim"] if trim else self.p["materials"]["facade"],"trim" if trim else "facade")
                    if (x,z+1) not in sheet:
                        self.set_cell(back,self.p["materials"]["facade"])
                elif y==floor-1 or y==head:
                    if trim and shape=="chamfered" and shoulder:
                        # The shoulder meets a pane sideways. A full connected
                        # trim cube closes that occupied contact; a slab does not.
                        self.set_cell(q,self.p["materials"]["trim"],"trim")
                        if (x,z+1) not in sheet:
                            self.set_cell(back,self.p["materials"]["facade"])
                    elif trim:
                        props=dict(type="top" if y==floor-1 else "bottom",waterlogged="false")
                        self.set_cell(q,self.p["materials"]["trim_slab"],"trim",props)
                        if (x,z+1) not in sheet:
                            self.set_cell(back,self.p["materials"]["facade"])
                            self.partial_backing.append([list(q),list(back)])
                        self.set_cell((x,y-1 if y==floor-1 else y+1,z),self.p["materials"]["facade"])
                    else:
                        self.set_cell(q,self.p["materials"]["facade"])
                else:
                    if (x,z+1) not in sheet:
                        self.set_cell(back,"air","air")
                    if glazed:
                        self.set_cell(q,self.p["materials"]["glazing"],"window",PANE)
                        panes.append(q)
                        self.pane_cells.add(q)
                    else:
                        self.set_cell(q,"air","air")
        self.openings.append({**spec,"wall_v_m":at,"shape":shape,"glazed":glazed,"pane_cells":[list(q) for q in panes],"path_xz":[list(q) for q in path],"observation_status":spec["observation_status"]})

    def connect_new_panes(self):
        for x,y,z in sorted(self.pane_cells):
            if not self.name((x,y,z)).endswith("_pane"):
                continue
            properties={"waterlogged":"false"}
            for side,dx,dz in (("east",1,0),("west",-1,0),("south",0,1),("north",0,-1)):
                state=self.name((x+dx,y,z+dz))
                connects=state!="minecraft:air" and not state.endswith(("_slab","_stairs","_door","_trapdoor"))
                properties[side]="true" if connects else "false"
            self.set_cell((x,y,z),self.p["materials"]["glazing"],"window",properties)

    def court(self):
        # Accepted engineered court grade and its crossing strips are retained.
        # No new building or roof may occupy its 1,763 non-source columns.
        mask=self.local_mask(self.p["court"]["bounds_uv_m"]) & ~self.r.footprint_mask
        y0=self.height_y(70.0)-self.c.y_min
        obstruction=np.isin(self.c.roles[y0:],[ROLES.index(v) for v in ("roof","facade","window","trim")]) & mask[None]
        if obstruction.any():
            raise ValueError("Existing roof/building obstructs protected open court")
        self.features["preserved_open_court_columns"]=int(mask.sum())

    def dining_front(self):
        config=self.p["dining_front"]
        bounds=config["clear_bounds_uv_m"]
        mask=self.local_mask(bounds) & ~np.isin(self.r.face_indices,[5,12,32])
        self.fill(mask,config["base_navd88_m"],config["clear_top_navd88_m"],"air","air")
        u0,u1=config["ends_u_m"]
        at=config["wall_v_m"]
        front=config["front_controls_uv_m"]
        self.wall("low Dining court front and measured east return",front,config["base_navd88_m"],config["coping_navd88_m"])
        for edge,inward in ((u0,(1,0)),(config["east_end_u_m"],(-1,0))):
            end_v=at if edge==u0 else front[-1][1]
            back_v=config["back_v_m"] if edge==u0 else min(config["back_v_m"],38.1)
            self.wall("front-strip end return",[(edge,end_v),(edge,back_v)],config["base_navd88_m"],config["roof_navd88_m"],inward=inward)
        # Broad rear membrane of the low frontage; visible brick parapet stays
        # at the front, with no invented gable or tower.
        roof=self.local_mask([u0,at+.55,config["east_end_u_m"],config["back_v_m"]])
        self.fill(roof,config["roof_navd88_m"]-.5,config["roof_navd88_m"],"smooth_stone","roof")
        self.fill(mask,69.0,69.5,"smooth_stone","floor")
        for opening in config["openings"]:
            self.aperture(opening,at,shape="chamfered",glazed=False)
        for x,z in self.path(front):
            u=self.u[z-self.c.z_min,x-self.c.x_min]
            lowered=any(a<=u<b for a,b in config["notches_u_m"])
            y=self.height_y(config["coping_navd88_m"])-(1 if lowered else 0)
            for depth in (0,1):
                self.set_cell((x,y,z+depth),self.p["materials"]["trim_slab"],"trim",dict(type="top" if lowered else "bottom",waterlogged="false"))
                if not lowered:
                    self.set_cell((x,y-1,z+depth),self.p["materials"]["facade"])
                if lowered:
                    self.set_cell((x,y+1,z+depth),"air","air")
                    backing=(x,y,z+2)
                    self.set_cell(backing,self.p["materials"]["facade"])
                    if depth==1:
                        self.partial_backing.append([[x,y,z+depth],list(backing)])
        rear=self.p["upper_front"]
        self.fill(self.local_mask(rear["clear_bounds_uv_m"]),rear["base_navd88_m"],rear["top_navd88_m"],"air","air",preserve_roof=True)
        self.wall("recessed Dining upper wall",[(rear["ends_u_m"][0],rear["wall_v_m"]),(rear["ends_u_m"][1],rear["wall_v_m"])],rear["base_navd88_m"],rear["top_navd88_m"])
        for opening in rear["openings"]:
            self.aperture(opening,rear["wall_v_m"],trim=False)
        for opening in config["openings"]:
            self.aperture({**opening,"observation_status":"Recessed glazing behind photographed broad screen bay; exact entry configuration inferred"},rear["wall_v_m"],trim=False)
        self.features["dining_lower_bays"]=len(config["openings"])
        self.features["dining_upper_windows"]=len(rear["openings"])

    def east_link(self):
        config=self.p["east_link"]
        mask=self.region_masks["east_link"]
        # Preserve source roof tops. Replace only the old five-pier lower
        # implementation with the bounded photographed colonnade rhythm.
        low=self.height_y(config["floor_navd88_m"])
        extension=self.local_mask(config["roof_extension_bounds_uv_m"])
        roof_mask=mask & ((self.r.footprint_mask & (self.r.heights < 76)) | extension)
        pier_mask=self.pier_mask(roof_mask,config)
        built=0
        for x,z,iz,ix in self.each_column(roof_mask):
            if self.r.footprint_mask[iz,ix]:
                level=float(self.r.heights[iz,ix])
            else:
                peak=74.3-abs(self.u[iz,ix]-55.15)*.62
                end=min(1,max(0,(36.5-self.v[iz,ix])/1.9))
                level=72.95+(peak-72.95)*end
            roof=self.height_y(level)
            for y in range(low-1,roof+2):
                if not self.mutation_mask[y-self.c.y_min,iz,ix]:
                    continue
                self.set_cell((x,y,z),"air","air")
            self.set_cell((x,low-1,z),"smooth_stone","floor")
            for y in range(max(self.height_y(66),min(self.c.ground_at(x,z)+1,low-1)),low-1):
                self.set_cell((x,y,z),"stone_bricks")
            for y in (roof-1,):
                self.set_cell((x,y,z),"smooth_stone","roof")
            self.set_cell((x,roof,z),"smooth_stone_slab","roof",SLAB)
            self.partial_backing.append([[x,roof,z],[x,roof-1,z]])
            # Pier rows follow the two measured canopy sides. Each cap sits
            # directly on a brick pier and directly under the canopy backing.
            pier=bool(pier_mask[iz,ix])
            if pier:
                for y in range(low,roof-1):
                    self.set_cell((x,y,z),self.p["materials"]["trim"] if y in (low,roof-2) else self.p["materials"]["facade"],"trim" if y in (low,roof-2) else "facade")
                built+=1
        self.features["east_link_pier_columns"]=built
        self.features["east_link_measured_canopy_columns"]=int(roof_mask.sum())

    def roof_palette(self):
        mask=self.region_masks["dining_roof_palette"]
        replacements={"stone_bricks":"deepslate_tiles","stone_brick_slab":"deepslate_tile_slab","stone_brick_stairs":"deepslate_tile_stairs"}
        for state_id,state in enumerate(list(self.c.palette)):
            replacement=replacements.get(state["Name"].removeprefix("minecraft:"))
            if replacement:
                selected=(self.c.data==state_id) & (self.c.roles==ROLES.index("roof")) & mask[None] & self.mutation_mask
                self.features["dining_roof_palette_cells"]+=int(selected.sum())
                self.c.data[selected]=self.c.state(replacement,state.get("Properties"))

    def west_link(self):
        """User-authorized west passage: preserve measured canopy, open below."""
        config=self.p["west_link"]
        mask=self.region_masks["west_link"] & np.isin(self.r.face_indices,[5,32])
        pier_mask=self.pier_mask(mask,config)
        low=self.height_y(config["floor_navd88_m"])
        piers=0
        for x,z,iz,ix in self.each_column(mask):
            roofs=np.flatnonzero(self.c.roles[:,iz,ix]==ROLES.index("roof"))
            if not len(roofs):
                continue
            underside=int(roofs[0])+self.c.y_min
            for y in range(low-1,underside):
                self.set_cell((x,y,z),"air","air")
            self.set_cell((x,low-1,z),"smooth_stone","floor")
            for y in range(max(self.height_y(66),min(self.c.ground_at(x,z)+1,low-1)),low-1):
                self.set_cell((x,y,z),"stone_bricks")
            pier=bool(pier_mask[iz,ix])
            if pier:
                for y in range(low,underside):
                    cap=y in (low,underside-1)
                    self.set_cell((x,y,z),self.p["materials"]["trim"] if cap else self.p["materials"]["facade"],"trim" if cap else "facade")
                piers+=1
        replacements={"stone_bricks":"smooth_quartz","stone_brick_slab":"smooth_quartz_slab","stone_brick_stairs":"smooth_quartz_stairs"}
        for state_id,state in enumerate(list(self.c.palette)):
            replacement=replacements.get(state["Name"].removeprefix("minecraft:"))
            if replacement:
                selected=(self.c.data==state_id)&(self.c.roles==ROLES.index("roof"))&mask[None]&self.mutation_mask
                self.c.data[selected]=self.c.state(replacement,state.get("Properties"))
                self.features["west_canopy_source_shape_palette_cells"]+=int(selected.sum())
        self.features["west_link_open_canopy_columns"]=int(mask.sum())
        self.features["west_link_pier_columns"]=piers

    def pier_mask(self,mask,config):
        """One 0.5m square shaft at each registered interpreted pier center."""
        result=np.zeros_like(mask)
        for u in config["pier_rows_u_m"]:
            for v in config["pier_centres_v_m"]:
                distance=(self.u-u)**2+(self.v-v)**2
                candidates=np.where(mask,distance,np.inf)
                flat=int(np.argmin(candidates))
                if candidates.flat[flat] <= .45**2:
                    result.flat[flat]=True
        return result

    def court_details(self):
        if self.p.get("court_spur_exception"):
            mask=self.region_masks["court_spur_exception"]
            self.fill(mask,69.5,74,"air","air")
            self.fill(mask,69,69.5,"bricks","pavement")
            self.features["photo_corrected_face10_spur_columns"]=int(mask.sum())
        seal=self.p.get("court_seal")
        if not seal:
            return
        radius=np.hypot(self.u-seal["center_uv_m"][0],self.v-seal["center_uv_m"][1])
        mask=self.region_masks["court_seal"] & (radius<seal["radius_m"]) & ~self.r.footprint_mask
        crossings=(abs(self.u-37)<.55)|(abs(self.v-27.5)<.55)
        if (mask&crossings).any():
            raise ValueError("Complete court seal must clear both crossing strips")
        for x,z,iz,ix in self.each_column(mask):
            y=self.c.ground_at(x,z)
            name=self.name((x,y,z))
            if name in ("minecraft:smooth_stone","minecraft:smooth_stone_slab"):
                raise ValueError("Court seal overlaps retained pale paving")
            r=float(radius[iz,ix])
            material="smooth_stone" if r>seal["radius_m"]-.5 else "gray_concrete"
            self.set_cell((x,y,z),material,"pavement")
            self.features["court_medallion_surface_cells"]+=1

    def build(self):
        self.court()
        self.dining_front()
        self.east_link()
        self.west_link()
        self.roof_palette()
        self.court_details()
        self.connect_new_panes()
        missing=[(a,b) for a,b in self.partial_backing if not self.c.get(*b)]
        if missing:
            raise ValueError({"missing_partial_backing":missing})
        return {"features":dict(self.features),"dining_wall_paths":self.wall_paths,"dining_openings":self.openings,
                "dining_partial_backing":{"checked":len(self.partial_backing),"missing":len(missing),"pairs":self.partial_backing},
                "protected_source_court_fringe_columns":self.protected_fringe_count,
                "original_source_court_fringe_columns":self.original_fringe_count,
                "scope":"Source-bounded Dining north frontage plus both user-required walk-through courtyard connectors. Accepted Athey and rear Dining source roof remain preserved outside the declared amendment."}

    def refine_existing(self):
        from campus_athey_details import refine_existing_athey
        from campus_study_io import digest
        config = self.p["exterior_refinement"]
        root = Path(__file__).resolve().parents[1]
        source = root/config["athey_profile"]
        if digest(source) != config["athey_profile_sha256"]:
            raise ValueError("Frozen Athey source profile changed")
        athey_profile = json.loads(source.read_text(encoding="utf-8"))
        repair = refine_existing_athey(self.c,athey_profile,self.r,self.offset,
                                      {**config,"measured_footprint":self.measured_building.footprint})
        rear = self.refine_dining_rear(athey_profile) if config.get("dining_rear") else {}
        site = (self.refine_recessed_court(athey_profile) if config.get("recessed_court") else
                self.refine_court_site(athey_profile) if config.get("court_site") else {})
        upper = self.refine_south_upper_flanks() if config.get("upper_flank_regularization") else {}
        north = self.refine_north_entry() if config.get("north_entry") else {}
        east_roof = self.refine_east_gallery_roof() if config.get("east_gallery_roof_palette") else {}
        return {"athey_exterior_refinement":repair,
                "east_gallery_roof_palette_refinement":east_roof,
                "north_entry_refinement":north,
                "upper_flank_regularization":upper,
                "dining_rear_refinement":rear,
                "court_site_refinement":site,
                "features":{"athey_return_panes":len(repair["pane_returns"]),
                            "athey_return_caps":len(repair["frame_caps"]),
                            "athey_court_ground_arches":len(config.get("recessed_court",{}).get("arch_centers_u_m",repair["court_ground_arches"]))},
                "scope":"Accepted v6 shared Athey/Dining component amended at facade glazing returns, source-supported raised Athey court arches, and user-required clear courtyard/landing surfaces. Gallery and Dining roof/body/source placement remain exact."}

    def refine_east_gallery_roof(self):
        """Source-correct pale metal proxy; preserve every occupied roof shape."""
        config=self.p["exterior_refinement"]["east_gallery_roof_palette"]
        mask=self.local_mask(config["bounds_uv_m"]) | np.isin(self.r.face_indices,config["source_faces"])
        heights=np.arange(self.c.data.shape[0])+self.c.y_min
        vertical=(heights>=config["height_y_blocks"][0])&(heights<=config["height_y_blocks"][1])
        replacements={"smooth_stone":"smooth_quartz","smooth_stone_slab":"smooth_quartz_slab",
                      "stone_bricks":"smooth_quartz","stone_brick_slab":"smooth_quartz_slab",
                      "stone_brick_stairs":"smooth_quartz_stairs"}
        records=[]
        for iy,iz,ix in np.argwhere((self.c.roles==ROLES.index("roof"))&mask[None]&vertical[:,None,None]):
            q=(int(ix+self.c.x_min),int(iy+self.c.y_min),int(iz+self.c.z_min))
            before=self.c.palette[self.c.get(*q)]
            replacement=replacements.get(before["Name"].removeprefix("minecraft:"))
            if replacement:
                self.set_cell(q,replacement,"roof",before.get("Properties"))
                records.append({"xyz":q,"source_face_index":int(self.r.face_indices[iz,ix]),
                                "before":before,"after":self.c.palette[self.c.get(*q)]})
        return {"controls":config,"changed_roof_cells":records,
                "rule":"Palette only; unchanged positions, full/slab/stair properties, roles, ridge, slopes, soffit and roof attachments."}

    def refine_south_upper_flanks(self):
        """Regularize the two photographed straight runs below retained roofs."""
        settings=self.p["exterior_refinement"]["upper_flank_regularization"]
        records=[];floor_edges=[]
        for u0,u1 in settings["u_runs_m"]:
            mask=self.local_mask([u0,12.9,u1,16.2])
            for x,z,iz,ix in self.each_column(mask):
                u,v=float(self.u[iz,ix]),float(self.v[iz,ix])
                front=settings["wall_front_v_m"]
                nearest=min([25,30,44,49],key=lambda center:abs(u-center));d=abs(u-nearest)
                for y in range(99,114):
                    old=self.c.palette[self.c.get(x,y,z)];old_role=ROLES[self.c.roles[y-self.c.y_min,iz,ix]]
                    if old_role=="roof":continue
                    if v>front:
                        block,role="air","air"
                    elif v<front-.7:
                        continue
                    else:
                        h=(y+.5)/2+25
                        window=next((sill for sill in (75.5,79.5) if sill-.26<=h<=sill+1.9+.26 and d<=1.4+.26),None)
                        if window is not None:
                            clear=d<1.4 and window<=h<window+1.9
                            if clear:block,role=("gray_stained_glass","window") if v<front-.30 else ("air","air")
                            else:block,role="smooth_quartz","trim"
                        else:block,role=("smooth_quartz","trim") if y==107 else ("bricks","facade")
                    if old_role=="floor" and block=="air":
                        floor_edges.append({"xyz":[x,y,z],"before":old,"after":{"Name":"minecraft:air"},"reason":"Clip only the exposed outer edge of the old accordion wall floor to the source-corrected straight envelope; storey height and inboard plate remain"})
                    if old_role=="floor" and block!="air":
                        role="floor"
                        if block=="smooth_quartz":block="smooth_stone"
                    target={"Name":"minecraft:"+block}
                    if old!=target:
                        self.set_cell((x,y,z),block,role);records.append([x,y,z])
        # The old reveal-closure pass added short return panes behind the
        # adjoining central jamb. Once the flank opening is planar these
        # are obsolete blind return tails, not separate central windows.
        for lo,hi in ((31.8,32.5),(41.5,42.2)):
            for x,z,iz,ix in self.each_column(self.local_mask([lo,14.2,hi,16.2])):
                for y in range(99,114):
                    if "glass" in self.c.palette[self.c.get(x,y,z)]["Name"]:
                        self.set_cell((x,y,z),"bricks","facade");records.append([x,y,z])
        returns=[]
        for u0,u1 in settings["u_runs_m"]:
            for boundary,outside in ((u0,u0-.55),(u1,u1+.55)):
                source=(abs(self.u-outside)<.3)&self.r.footprint_mask&(self.r.heights>=80.5)
                if not source.any():raise ValueError("No measured adjacent wall for the flank return")
                neighbor=float(self.v[source].max());front=settings["wall_front_v_m"]
                v0,v1=min(front,neighbor)-.25,max(front,neighbor)+.35
                join=self.local_mask([boundary-.35,v0,boundary+.35,v1]);joincells=[]
                for x,z,iz,ix in self.each_column(join):
                    for y in range(99,114):
                        old_role=ROLES[self.c.roles[y-self.c.y_min,iz,ix]]
                        if old_role in ("roof","floor"):continue
                        block,role=("smooth_quartz","trim") if y==107 else ("bricks","facade")
                        self.set_cell((x,y,z),block,role);joincells.append([x,y,z]);records.append([x,y,z])
                returns.append({"boundary_u_m":boundary,"neighbor_sample_u_m":outside,"neighbor_v_m":neighbor,"bounds_uv_m":[boundary-.35,v0,boundary+.35,v1],"height_y_blocks":[99,114],"authored_cells":joincells,"reason":"Close the side face between the regularized flanking plane and the retained neighboring wall/central crossgable"})
        return {"controls":settings,"changed_cells":records,"old_floor_edge_corrections":floor_edges,"junction_return_planes":returns,"source_rule":"Court correction packet: one central cross-gable, straight flanking runs with level continuous pale belts; no per-window projections. Every original roof cell retained."}

    def refine_north_entry(self):
        """Join the measured central door sill to its existing Quad approach.

        The accepted north entry was a glazed opening with timber panels
        behind it. Remove only the central two-block threshold obstruction
        and replace those panels with an ordinary working pair of doors.
        """
        settings=self.p["exterior_refinement"]["north_entry"]
        x0,z0,x1,z1=settings["landing_bounds_xz_blocks"]
        feet=settings["threshold_feet_y"]
        repairs=[];changes=[]
        for x in range(x0,x1+1):
            for z in range(z0,z1+1):
                # The landing narrows to the source doorway as it enters
                # the wall, preserving the two masonry/glazed jambs.
                if z>=87 and x not in (117,118):
                    continue
                for y in range(82,feet):
                    old_id=self.c.get(x,y,z);old_state=self.c.palette[old_id]
                    role=ROLES[self.c.roles[y-self.c.y_min,z-self.c.z_min,x-self.c.x_min]]
                    if role in ("roof","floor") and old_id:
                        if old_state.get("Properties",{}).get("type")=="bottom":
                            repairs.append({"xyz":[x,y,z],"before":old_state,"reason":"Support the source north entrance sill at the height of its retained exterior approach"})
                            self.set_cell((x,y,z),old_state["Name"].replace("minecraft:",""),role,{**old_state["Properties"],"type":"double"})
                        continue
                    self.set_cell((x,y,z),"smooth_stone" if y==feet-1 else "stone_bricks","pavement")
                    changes.append([x,y,z])
                self.c.ground_heights[z-self.c.z_min,x-self.c.x_min]=feet-1
        doors=[]
        for x,hinge in ((117,"left"),(118,"right")):
            for z in (87,88):
                for y in (85,86):
                    self.set_cell((x,y,z),"air","air");changes.append([x,y,z])
            for y,half in ((85,"lower"),(86,"upper")):
                props={"facing":"north","half":half,"hinge":hinge,"open":"false","powered":"false"}
                self.set_cell((x,y,87),"dark_oak_door","door",props)
                doors.append([x,y,87])
            # A solid tinted transom caps the working door; it gives the
            # retained panes above a full-width physical bottom contact.
            self.set_cell((x,87,87),"gray_stained_glass","window");changes.append([x,87,87])
        for y in (85,86):
            self.set_cell((119,y,87),"gray_stained_glass","window");changes.append([119,y,87])
        return {"source_sill_navd88_m":67.35,"quantized_threshold_feet_y":feet,
                "landscape_join_xyz":[118,85,79],"landing_bounds_xz_blocks":settings["landing_bounds_xz_blocks"],
                "working_door_cells":doors,"low_grade_slab_support_repairs":repairs,"authored_cells":changes,
                "explanation":"Existing source-profile north door center and masonry frame retained. Flat Y85 landing joins upstream Y85 path and replaces the inherited dip to Y82.5; no invented down/up stairs."}

    def refine_dining_rear(self, athey_profile):
        """Conservative, explicitly inferred completion of measured rear walls."""
        from dataclasses import replace
        from campus_academic_building import AcademicExterior
        from campus_athey_details import refine_existing_athey
        from build_hill_chapel_sample import connect_window_panes
        settings=self.p["exterior_refinement"]["dining_rear"]
        facade_profile={"geometry":{**self.p["geometry"],"main_roof_threshold_navd88_m":60},
                        "materials":self.p["materials"],
                        "window_reveal":{"trim_width_m":.26,"glass_recess_m":0,
                                         "trim_family":"smooth_sandstone",
                                         "glass_block":"gray_stained_glass_pane"}}
        facade=AcademicExterior(self.c,facade_profile,self.r,self.offset)
        schedule=[]
        for side,start,end in (("south",10,57),("west",42,71),("east",42,71)):
            for center in np.arange(start,end,settings["spacing_m"]):
                transverse=self.u if side=="south" else self.v
                depth=self.v if side=="south" else self.u
                source=self.r.footprint_mask&(self.v>=40)&(abs(transverse-center)<.28)
                if not source.any():
                    continue
                at=float(depth[source].min() if side=="west" else depth[source].max())
                if side=="south" and at<63:
                    continue
                # Omit corners and interrupted/strongly stepped returns.
                samples=[]
                for along in (center-1.25,center+1.25):
                    near=self.r.footprint_mask&(self.v>=40)&(abs(transverse-along)<.28)
                    if near.any():
                        samples.append(float(depth[near].min() if side=="west" else depth[near].max()))
                if len(samples)!=2 or max(abs(v-at) for v in samples)>.85:
                    continue
                for sill in settings["sills_navd88_m"]:
                    head=sill+settings["height_m"]
                    original=facade.r
                    facade.r=replace(self.r,footprint_mask=self.r.footprint_mask&(self.r.heights>=head+.3))
                    before=sum(facade.features.values())
                    facade.opening(float(center),side,sill,settings["width_m"],settings["height_m"],at=at,lights=1)
                    facade.r=original
                    if sum(facade.features.values())>before:
                        schedule.append({"side":side,"center_along_m":float(center),"wall_at_m":at,
                            "sill_navd88_m":sill,"head_navd88_m":head,"width_m":settings["width_m"],
                            "observation_status":"Inferred completion of concealed/rear measured wall; no exact photographic opening count claimed"})
        connect_window_panes(self.c)
        closures=refine_existing_athey(self.c,athey_profile,self.r,self.offset,
            {"measured_footprint":self.measured_building.footprint,
             "repair_pane_bounds_uv_m":[5,40.5,59,73]})
        return {"opening_schedule":schedule,"closure":closures,
                "source_control":"2026-09-27 Sol packet: measured body/roof retained, simple small rectangular openings only, 3.6–4.2m rhythm, modest pale frames and dark glazing. Unseen schedules remain explicitly inferred."}

    def refine_recessed_court(self, athey_profile):
        """Deep open lower arcade, real vaulted covers, and one central stair.

        Roof-raster ground fragments previously made five projecting landings.
        The official 88/89s frames and direct user correction instead control
        this bounded lower shell independently of the retained upper body.
        """
        settings=self.p["exterior_refinement"]["recessed_court"]
        centers=settings["arch_centers_u_m"];width=settings["arch_width_m"]
        front=settings["shell_front_v_m"];rear=settings["recess_back_v_m"]
        low_roof_changes=[];floor_finishes=[];cells=[];surfaces=[];vault=[]
        def put(x,y,z,block,role,props=None):
            old=self.c.palette[self.c.get(x,y,z)]
            old_role=ROLES[self.c.roles[y-self.c.y_min,z-self.c.z_min,x-self.c.x_min]]
            target={"Name":"minecraft:"+block}
            if props:target["Properties"]=props
            if old_role=="roof" and old!=target:
                if y>92:
                    raise ValueError(f"Court correction would touch a weather roof at {(x,y,z)}")
                low_roof_changes.append({"xyz":[x,y,z],"source_face_index":int(self.r.face_indices[z-self.c.z_min,x-self.c.x_min]),"before":old,"after":target,"reason":"Remove a low source ground/landing fragment contradicted by the photographed continuous arcade and single central stair"})
            self.set_cell((x,y,z),block,role,props);cells.append([x,y,z])
        mask=self.local_mask([21.8,13.0,52.2,21.0])
        for x,z,iz,ix in self.each_column(mask):
            u,v=float(self.u[iz,ix]),float(self.v[iz,ix])
            # Nothing north of the new rear wall is reconstructed. The
            # existing classroom volume and first-floor plate stay intact.
            if v<rear-.5:
                continue
            access=settings["stair_u_bounds_m"][0]<=u<=settings["stair_u_bounds_m"][1]
            if v<=18.3:
                top=92.0;material="smooth_stone"
            elif access:
                step=min(6,math.floor((v-18.3)/(21-18.3)*6+1e-8))
                top=92-.5*step;material="smooth_stone"
            else:
                # A single low edge, with dark non-grass finish behind it.
                # No separate planter pockets or extra flights are invented.
                top=90.0;material="smooth_stone" if v>=20.5 or u>=51.8 or u<22.2 else "coarse_dirt"
            slab=not float(top).is_integer();floor=math.floor(top) if slab else int(top)-1
            for y in range(88,92):
                old_role=ROLES[self.c.roles[y-self.c.y_min,iz,ix]]
                if old_role=="floor":
                    # The first floor is a measured occupied deck. Its
                    # exterior continuation may meet it, never erase it.
                    if y>floor:raise ValueError(f"Court would remove first floor {(x,y,z)}")
                    if y==floor:
                        old=self.c.palette[self.c.get(x,y,z)]
                        if old["Name"]!="minecraft:smooth_stone":
                            floor_finishes.append({"xyz":[x,y,z],"before":old,"after":{"Name":"minecraft:smooth_stone"},"reason":"Exterior recessed-walk paving replaces exposed interior plank finish at identical occupied height"})
                            put(x,y,z,"smooth_stone","floor")
                    continue
                if old_role=="roof" and y<=floor:
                    old=self.c.palette[self.c.get(x,y,z)]
                    bottom=old.get("Properties",{}).get("type")=="bottom"
                    if bottom and (y<floor or not slab):
                        put(x,y,z,old["Name"].replace("minecraft:",""),"roof",{**old["Properties"],"type":"double"})
                    continue
                if y<floor:block,role,props="stone","terrain",None
                elif y==floor:block,role,props=(material+"_slab" if slab else material),("terrain" if material=="coarse_dirt" else "pavement"),(SLAB if slab else None)
                else:block,role,props="air","air",None
                put(x,y,z,block,role,props)
            self.c.ground_heights[iz,ix]=floor
            surfaces.append({"xz":[x,z],"top_y":top,"material":material,"central_stair":access and v>18.3})
            # Remove the inherited lower accordion wall and panes. The
            # upper facade starts at the original Y99 floor and is retained.
            for y in range(92,99):
                put(x,y,z,"air","air")
            if v>front+.5:
                continue
            nearest=min(centers,key=lambda center:abs(u-center));d=u-nearest
            width=settings.get("arch_widths_m",{}).get(str(nearest),settings["arch_width_m"])
            half=width/2;spring=1.25
            # The approved curve is a pointed shell, not the older shallow
            # circular segment whose voxel center became a square lintel.
            h=2.6-(2.6-spring)*(min(1,abs(d)/half)**.8)
            underside=round((92+2*h)*2)/2
            if v>=rear and v<=front+.15:
                # Each pointed arch is extruded inward as an actual vault,
                # not just a trim ring pasted onto flat glazing. A clear
                # connecting lane behind the front piers links every bay.
                bottom=math.floor(underside)
                for y in range(bottom,99):
                    partial=y==bottom and underside!=bottom
                    put(x,y,z,"smooth_quartz_slab" if partial else "smooth_quartz" if y==bottom else "bricks","trim" if y==bottom else "facade",{"type":"top","waterlogged":"false"} if partial else None)
                    if y==bottom:vault.append([x,y,z])
            if rear-.5<=v<rear:
                for y in range(92,99):
                    glazing=abs(d)<width/2-.25 and 92<=y<=96
                    put(x,y,z,"gray_stained_glass" if glazing else "bricks","window" if glazing else "facade")
            if front-.35<=v<=front+.35:
                for y in range(92,98):
                    bottom_h=(y-92)/2;middle_h=bottom_h+.25
                    in_arch=abs(d)<=half and middle_h<h
                    outer_head=2.6+.26-(2.6-spring)*(min(1,abs(d)/(half+.26))**.8)
                    in_outer=abs(d)<=half+.26 and bottom_h<outer_head
                    if in_arch:
                        put(x,y,z,"air","air")
                    elif in_outer:
                        # Inverted steps remove the cubical shoulder. The
                        # stair's high half remains positively backed above.
                        shoulder=abs(d)>.15 and bottom_h>=spring-.25
                        facing="east" if d>0 else "west"
                        if shoulder:put(x,y,z,"smooth_quartz_stairs","trim",{"facing":facing,"half":"top","shape":"straight","waterlogged":"false"})
                        else:put(x,y,z,"smooth_quartz","trim")
                    else:put(x,y,z,"bricks","facade")
                put(x,98,z,"smooth_quartz","trim")
        # One stair only, with the observed side and central slender rails.
        rails=[]
        for u in [settings["stair_u_bounds_m"][0],37,settings["stair_u_bounds_m"][1]]:
            columns=[]
            for v in np.arange(18.3,21.05,.20):
                xx,zz=self.world(u,float(v))*2;q=(int(math.floor(xx)),int(math.floor(zz)))
                if columns and q!=columns[-1] and q[0]!=columns[-1][0] and q[1]!=columns[-1][1]:
                    columns.append((q[0],columns[-1][1]))
                if not columns or q!=columns[-1]:columns.append(q)
            for x,z in columns:
                v=float(self.v[z-self.c.z_min,x-self.c.x_min])
                step=min(6,max(0,math.floor((v-18.3)/(21-18.3)*6+1e-8)));top=92-.5*step
                floor=math.floor(top)
                for yy in range(89,math.ceil(top)):
                    state=self.c.palette[self.c.get(x,yy,z)]
                    if state["Name"]=="minecraft:air":put(x,yy,z,"smooth_stone","pavement")
                if top!=floor:
                    # The narrow rail post has its own full-height footing;
                    # the parallel walking tracks retain half-block treads.
                    put(x,floor,z,"smooth_stone","pavement")
                for y in range(math.ceil(top),math.ceil(top)+2):
                    put(x,y,z,"iron_bars","railing",PANE);rails.append([x,y,z])
        railset=set(map(tuple,rails))
        for x,y,z in railset:
            props={**PANE}
            for key,dx,dz in (("north",0,-1),("south",0,1),("east",1,0),("west",-1,0)):
                props[key]="true" if (x+dx,y,z+dz) in railset else "false"
            self.set_cell((x,y,z),"iron_bars","railing",props)
        plants=[]
        planting=settings.get("planting",{})
        safe=self.local_mask([22.3,18.75,51.7,20.45])&((self.u<33.6)|(self.u>40.4))
        for uc,vc,ru,rv in planting.get("shrubs",[]):
            shrub=safe&(((self.u-uc)/ru)**2+((self.v-vc)/rv)**2<=1)
            for x,z,iz,ix in self.each_column(shrub):
                for y in range(90,93):
                    if ((self.u[iz,ix]-uc)/ru)**2+((self.v[iz,ix]-vc)/rv)**2+((y+.5-91)/1.6)**2>1:continue
                    put(x,y,z,"oak_leaves","vegetation",{"distance":"1","persistent":"true","waterlogged":"false"});plants.append([x,y,z])
        if planting.get("ornamental_tree_uv_m"):
            uc,vc=planting["ornamental_tree_uv_m"];xx,zz=self.world(uc,vc)*2;x,z=int(math.floor(xx)),int(math.floor(zz))
            for y in range(90,95):put(x,y,z,"oak_log","vegetation",{"axis":"y"});plants.append([x,y,z])
            crown=safe&(((self.u-uc)/1.05)**2+((self.v-vc)/.78)**2<=1)
            for xx,zz,iz,ix in self.each_column(crown):
                for y in range(94,97):
                    if ((self.u[iz,ix]-uc)/1.05)**2+((self.v[iz,ix]-vc)/.78)**2+((y+.5-95)/2.0)**2<=1:
                        put(xx,y,zz,"oak_leaves","vegetation",{"distance":"1","persistent":"true","waterlogged":"false"});plants.append([xx,y,zz])
        # Clear every inherited grass cube in the entire interbuilding area,
        # including galleries; support the known buried six-cell court void.
        whole=self.local_mask([16.1,13.0,57,36.5]);grass_ids=[i for i,state in enumerate(self.c.palette) if state["Name"]=="minecraft:grass_block"]
        grass=[]
        for iy,iz,ix in np.argwhere(np.isin(self.c.data,grass_ids)&whole[None]):
            if not self.mutation_mask[iy,iz,ix]:continue
            x,y,z=int(ix+self.c.x_min),int(iy+self.c.y_min),int(iz+self.c.z_min)
            exposed=not self.c.get(x,y+1,z)
            put(x,y,z,"smooth_stone" if exposed else "stone","pavement" if exposed else "terrain");grass.append([x,y,z])
        support=[]
        for y in (88,89):
            walk=np.isin(self.c.roles[y-self.c.y_min],[ROLES.index("pavement"),ROLES.index("floor")])&whole
            for x,z,iz,ix in self.each_column(walk):
                if self.v[iz,ix]<21 and 21.8<self.u[iz,ix]<52.2:continue
                yy=y-1
                while yy>=y-6 and not self.c.get(x,yy,z):
                    put(x,yy,z,"stone","terrain");support.append([x,yy,z]);yy-=1
        return {"interpretation":"Source88/89 and user-confirmed curved covering over an inward-recessed walkway; five candidate arch centers retain interpreted rhythm, not five doors.",
                "shell_controls":settings,"surface_schedule":surfaces,"actual_vault_underside_cells":vault,
                "low_source_grade_exceptions":low_roof_changes,"exterior_floor_finish_changes":floor_finishes,"central_stair_rail_cells":sorted(set(map(tuple,rails))),
                "grass_cells_replaced":grass,"source_visible_bed_plant_cells":plants,"court_gallery_foundation_void_repairs":support,
                "authored_cell_bounds_xyz":[np.min(cells,axis=0).tolist(),np.max(cells,axis=0).tolist()]}

    def refine_court_site(self, athey_profile):
        """Contained north planting plus supported landing/stair circulation.

        The user specifically rejects stray grass blocks between the two
        buildings. Real planting is retained only within the source strip;
        all circulation surfaces are paving, with no unsupported air below.
        """
        from campus_athey_details import AtheyExterior
        facade = AtheyExterior(self.c,athey_profile,self.r,self.offset)
        settings = self.p["exterior_refinement"]["court_site"]
        # Face52 is the measured low paving/grade fragment, not a building
        # volume. Its existing pavement must participate in the stair grade;
        # otherwise a preserved flat strip creates a sudden 1.5-block rise.
        architecture=np.isin(self.c.roles[90-self.c.y_min:],
            [ROLES.index(role) for role in ("roof","facade","window","trim","railing","floor")]).any(axis=0)
        mask = self.local_mask(settings["north_bounds_uv_m"]) & (
            ~self.r.footprint_mask | ((self.r.face_indices==52)&~architecture))
        cells=[]; surfaces=[]; low_grade_slab_repairs=[]
        centers=[o["center_u_m"] for o in self.p["exterior_refinement"]["court_ground_arches"]["openings"]]
        landing_starts={}
        for center in centers:
            front=facade.edge_v(center,"south")
            ledge=(abs(self.u-center)<settings["stair_width_m"]/2)&(self.v>front)&(self.v<21)&self.r.footprint_mask&(self.r.heights<72)&(self.r.face_indices!=52)
            landing_starts[center]=max(front+1.2,float(self.v[ledge].max()) if ledge.any() else front+1.2)
        for x,z,iz,ix in self.each_column(mask):
            u,v=float(self.u[iz,ix]),float(self.v[iz,ix])
            front=facade.edge_v(u,"south")
            if front is None or v<front:
                continue
            access=min(abs(u-center) for center in centers)<settings["stair_width_m"]/2
            if access:
                nearest=min(centers,key=lambda center:abs(u-center))
                start=landing_starts[nearest]
                fraction=min(1,max(0,(v-start)/(21.0-start)))
                top=92-.5*math.floor(fraction*6+1e-8)
                material="smooth_stone"
            elif v<18.3:
                top=92.0;material="smooth_stone"
            else:
                top=90.0
                # One continuous containing stone curb surrounds each low
                # mulch bed; stair channels interrupt it at the five bays.
                curb=v>=20.5 or v<18.8 or u>=51.8 or u<22.2 or min(abs(u-center) for center in centers)<settings["stair_width_m"]/2+.5
                material="smooth_stone" if curb else "coarse_dirt"
            bottom_slab=not float(top).is_integer()
            floor=math.floor(top) if bottom_slab else int(top)-1
            old_ground=self.c.ground_at(x,z)
            for y in range(min(old_ground,floor)-1,max(old_ground+2,93)):
                if not self.mutation_mask[y-self.c.y_min,iz,ix]:
                    continue
                if y<floor:
                    block,role,props="stone","terrain",None
                elif y==floor:
                    block=material+"_slab" if bottom_slab else material
                    role="terrain" if material=="coarse_dirt" else "pavement"
                    props=SLAB if bottom_slab else None
                else:
                    block,role,props="air","air",None
                old_id=self.c.get(x,y,z)
                old_role=ROLES[self.c.roles[y-self.c.y_min,iz,ix]]
                if old_role in ("roof","floor"):
                    # Source face52 is a low court-grade surface. Keep its
                    # full blocks buried under the approach, and join the
                    # half-height ones into full supports where necessary.
                    old_state=self.c.palette[old_id]
                    old_props=old_state.get("Properties",{})
                    if y<floor and old_props.get("type")=="bottom":
                        low_grade_slab_repairs.append({"xyz":[x,y,z],"face_index":int(self.r.face_indices[iz,ix]),"before":old_state,"reason":"Half-slab court-grade source fragment needs full backing beneath the raised arcade stair"})
                        self.set_cell((x,y,z),old_state["Name"].replace("minecraft:",""),old_role,{**old_props,"type":"double"})
                    elif y>=floor:
                        if y==floor and old_props.get("type")=="bottom" and not bottom_slab:
                            low_grade_slab_repairs.append({"xyz":[x,y,z],"face_index":int(self.r.face_indices[iz,ix]),"before":old_state,"reason":"Join source low court-grade slab to the supported stair surface"})
                            self.set_cell((x,y,z),old_state["Name"].replace("minecraft:",""),old_role,{**old_props,"type":"double"})
                        elif y>floor:
                            raise ValueError(f"Stair would cut retained architecture at {(x,y,z)}")
                    cells.append([x,y,z])
                    continue
                self.set_cell((x,y,z),block,role,props)
                cells.append([x,y,z])
            self.c.ground_heights[iz,ix]=floor
            surfaces.append({"xz":[x,z],"top_y":top,"surface":material,"stair":access})
        # This includes the two connector envelopes at all heights. Replace
        # inherited buried grass with stone and exposed ground with paving;
        # roofs, floors, piers and supported open bays remain untouched.
        whole=self.local_mask(settings["interbuilding_bounds_uv_m"])
        grass_ids=[i for i,state in enumerate(self.c.palette) if state["Name"]=="minecraft:grass_block"]
        grass=[]
        for iy,iz,ix in np.argwhere(np.isin(self.c.data,grass_ids)&whole[None]):
            x,y,z=int(ix+self.c.x_min),int(iy+self.c.y_min),int(iz+self.c.z_min)
            if not self.mutation_mask[iy,iz,ix]:
                continue
            exposed=not self.c.get(x,y+1,z)
            self.set_cell((x,y,z),"smooth_stone" if exposed else "stone","pavement" if exposed else "terrain")
            grass.append([x,y,z]);cells.append([x,y,z])
        remaining=np.argwhere(np.isin(self.c.data,grass_ids)&whole[None])
        support_repairs=[]
        for y in (88,89):
            walk=np.isin(self.c.roles[y-self.c.y_min], [ROLES.index("pavement"),ROLES.index("floor")])&whole
            for x,z,iz,ix in self.each_column(walk):
                # Only foundation voids below actual court/gallery surfacing;
                # never fill the room beneath a higher Athey floor plate.
                if self.v[iz,ix]<21 and 21.8<self.u[iz,ix]<52:
                    continue
                yy=y-1
                while yy>=y-6 and not self.c.get(x,yy,z):
                    if not self.mutation_mask[yy-self.c.y_min,iz,ix]:
                        raise ValueError(f"Court support repair requires an explicit ownership cell: {(x,yy,z)}")
                    self.set_cell((x,yy,z),"stone","terrain")
                    support_repairs.append([x,yy,z]);cells.append([x,yy,z]);yy-=1
        return {"north_surface_columns":len(surfaces),"surface_schedule":surfaces,
                "grass_cells_replaced":grass,"remaining_grass_cells_all_heights":remaining.tolist(),
                "authored_cell_bounds_xyz":[np.min(cells,axis=0).tolist(),np.max(cells,axis=0).tolist()],
                "circulation_bounds_uv_m":settings["interbuilding_bounds_uv_m"],
                "mulch_only_bounds_uv_m":[21.8,18.3,52.2,21.0],
                "landing_feet_y":92,"court_feet_y":89,"maximum_stair_riser_blocks":.5,
                "stair_landing_starts_v_m":landing_starts,
                "low_source_grade_slab_support_repairs":low_grade_slab_repairs,
                "court_gallery_foundation_void_repairs":support_repairs,
                "authorization":"User requires no exposed grass blocks between Athey and Dining. Source 88–89 permits only the bounded north planting strip; five stair channels retain unobstructed raised-arcade access."}
