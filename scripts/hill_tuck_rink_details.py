"""Tuck/Rink's photographed north skin on the retained measured arena."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion

from build_hill_chapel_sample import ROLES
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {}


def path_columns(f, points, inward):
    """One regular cardinally connected trace of an analytic wall plane."""
    chain = []
    for a, b in zip(points, points[1:]):
        start, end = f.world(*a)*2-.5, f.world(*b)*2-.5
        for point in np.linspace(start, end, max(2, math.ceil(max(abs(end-start))*8))):
            q = tuple(int(round(v)) for v in point)
            if chain and q == chain[-1]:
                continue
            if chain and abs(q[0]-chain[-1][0])+abs(q[1]-chain[-1][1]) == 2:
                prev = chain[-1]
                chain.append(max(((prev[0], q[1]), (q[0], prev[1])),
                                 key=lambda r:r[0]*inward[0]+r[1]*inward[1]))
            chain.append(q)
    return list(dict.fromkeys(chain))


def uv(f, x, z):
    return float(f.u[z-f.c.z_min, x-f.c.x_min]), float(f.v[z-f.c.z_min, x-f.c.x_min])


def prepare_roof(r, f, p):
    for info in [p['reference_packet'], *p.get('reference_addenda', [])]:
        assert hashlib.sha256((ROOT/info['path']).read_bytes()).hexdigest() == info['sha256']
    b = load_measured_building(parent_id=p['parent_id'])
    assert b.source_sha256 == p['source_roof_sha256']
    faces = []
    for i, face in enumerate(b.roof_faces):
        canonical = dict(xz=list(map(list, face.polygon.exterior.coords)),
                         holes=[list(map(list, ring.coords)) for ring in face.polygon.interiors],
                         plane=[face.a, face.b, face.c], surface=face.surface_index)
        faces.append(dict(id=i, canonical=canonical,
                          sha256=hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()))
    SOURCE.clear()
    SOURCE.update(raster=r, building=b, details=dict(source_faces=faces, glazing=[],
        roof_material_cells=[], east_gable_backing_retints=[], wall_corner_bridges=[], north_plane={}, sidewalk=[], entry={}, louver={},
        roof_exceptions=p.get('source_surface_exceptions', [])))
    return r


def surface(f, mask, levels, role='pavement'):
    levels = np.broadcast_to(levels, mask.shape)
    records = []
    for x, z, iz, ix in f.each_column(mask):
        half = math.floor((float(levels[iz, ix])-25)*4+.5)
        cap = (half-1)//2
        for y in range(min(cap, f.c.ground_at(x,z)), cap):
            f.c.set(x,y,z,'smooth_stone',role)
        f.c.set(x,cap,z,'smooth_stone_slab' if half%2 else 'smooth_stone',role,
                {'type':'bottom','waterlogged':'false'} if half%2 else None)
        for y in range(cap+1, max(cap+2, f.c.ground_at(x,z)+2)):
            if ROLES[f.c.roles[y+64,iz,ix]] in ('terrain','pavement','vegetation'):
                f.c.set(x,y,z,'air','air')
        records.append([x,cap,z,half/2])
    return records


def clear_skin(f, bounds, low, high):
    mask = f.local_mask(bounds)
    a,b = f.height_y(low)+64, f.height_y(high)+64
    roles = f.c.roles[a:b]
    chosen = mask[None] & np.isin(roles,[ROLES.index('facade'),ROLES.index('trim')])
    f.c.data[a:b][chosen] = 0
    roles[chosen] = 0


def sheet(f, name, columns, low, high, *, glass='gray_stained_glass_pane', ends=True):
    a,b = f.height_y(low),f.height_y(high)
    panes = []
    for i,(x,z) in enumerate(columns):
        for y in range(a-1,b+1):
            cap = y in (a-1,b) or (ends and i in (0,len(columns)-1))
            f.c.set(x,y,z,'smooth_quartz' if cap else glass,'trim' if cap else 'window',
                    None if cap else PANE_PROPS)
            if not cap:panes.append([x,y,z])
    SOURCE['details']['glazing'].append(dict(name=name,columns=columns,low_y=a,
        high_y_exclusive=b,pane_cells=panes))
    return panes


def connect_service_wall_corners(f):
    """Fill only the inward cell at a diagonal sample turn, below the roof."""
    body=f.r.footprint_mask
    boundary=body & ~binary_erosion(body,structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
    vertices=np.array(SOURCE['building'].footprint.exterior.coords)
    local=np.column_stack((vertices@f.t,vertices@f.n))
    segments=[]
    for a,b in zip(local,local[1:]):
        if abs(b[0]-a[0])>50 and -133<a[1]<-132 and -133<b[1]<-132:
            segments.append(('south_main',a,b,0,1))
        elif a[0]<-11 and b[0]<-11 and abs(b[1]-a[1])>10:
            segments.append(('west_main',a,b,1,-1))
    for name,a,b,dominant,sign in segments:
        unit=(b-a)/np.linalg.norm(b-a)
        along=(f.u-a[0])*unit[0]+(f.v-a[1])*unit[1]
        normal=(f.u-a[0])*(-unit[1])+(f.v-a[1])*unit[0]
        strip=(along>=0)&(along<=np.linalg.norm(b-a))&(abs(normal)<.75)
        trace={}
        for x,z,_,_ in f.each_column(boundary&strip):
            point=(x,z);key=point[dominant];value=point[1-dominant]
            if key not in trace or sign*value>sign*trace[key][1-dominant]:
                trace[key]=point
        points=[trace[k] for k in sorted(trace)]
        for first,second in zip(points,points[1:]):
            if abs(first[0]-second[0])!=1 or abs(first[1]-second[1])!=1:
                continue
            x,z=(second[0],first[1]) if dominant==0 else (first[0],second[1])
            iz,ix=z-f.c.z_min,x-f.c.x_min
            assert body[iz,ix] and strip[iz,ix]
            for y in range(59,82):
                if f.c.get(x,y,z):
                    continue
                contacts=[f.c.palette[f.c.get(q[0],y,q[1])]['Name'] for q in (first,second)]
                if ('minecraft:red_terracotta' not in contacts or not all(name in {
                    'minecraft:red_terracotta','minecraft:smooth_quartz','minecraft:white_concrete','minecraft:mud_bricks'} for name in contacts)):
                    continue
                f.c.set(x,y,z,'red_terracotta','facade')
                SOURCE['details']['wall_corner_bridges'].append(dict(xyz=[x,y,z],segment=name,
                    attached_wall_cells=[[first[0],y,first[1]],[second[0],y,second[1]]]))


def build_details(f,p):
    d=SOURCE['details']
    # The material replacement never changes the measured cap shape or height.
    replacements={'minecraft:stone_bricks':'smooth_stone',
                  'minecraft:stone_brick_slab':'smooth_stone_slab',
                  'minecraft:stone_brick_stairs':'smooth_quartz_stairs'}
    for iy,iz,ix in np.argwhere(f.c.roles==ROLES.index('roof')):
        s=f.c.palette[f.c.data[iy,iz,ix]]
        if s['Name'] in replacements:
            x,y,z=int(ix)+f.c.x_min,int(iy)-64,int(iz)+f.c.z_min
            after=replacements[s['Name']]
            f.c.set(x,y,z,after,'roof',s.get('Properties'))
            d['roof_material_cells'].append([x,y,z,s['Name'],'minecraft:'+after])
    # Only the exposed east-gable substrate takes the red wall finish. Keep
    # each measured top cell pale and leave hidden roof backing untouched.
    mask=f.r.footprint_mask
    for x,z,iz,ix in f.each_column(mask & (f.u>=52.75) & (f.v>=-167.6) & (f.v<=-132.4)):
        exposed=not mask[iz,ix+1] or not mask[iz+1,ix]
        if not exposed:
            continue
        half=math.floor((float(f.r.heights[iz,ix])-25)*4+.5)
        cap=(half-1)//2
        for y in range(cap-2,cap):
            if ROLES[f.c.roles[y+64,iz,ix]]!='roof':
                continue
            before=f.c.palette[f.c.get(x,y,z)]
            if before['Name']!='minecraft:smooth_stone':
                continue
            f.c.set(x,y,z,'red_terracotta','facade')
            d['east_gable_backing_retints'].append(dict(xyz=[x,y,z],cap_y=cap,
                before_state=before,after_state={'Name':'minecraft:red_terracotta'}))
    # A gently graded north path, with a level landing at the eastern doors.
    slope=57.8+np.clip((f.u+13)/68,0,1)*.8
    slope=np.where(f.u>=40.7,58.5,slope)
    d['sidewalk']=surface(f,f.local_mask([-13,-170.8,55,-168.65]),slope)
    d['entry']['landing']=surface(f,f.local_mask([40.7,-169.0,50.3,-165.8]),58.5,'floor')
    # Retain the arena floor at the low service level. Only a narrow gallery
    # strip is supported behind the raised street windows and entrance.
    d['gallery']=surface(f,f.local_mask([-11.5,-167.3,40.8,-165.5]) & f.r.footprint_mask,
                         58.5,'floor')
    north=path_columns(f,[[-12,-167.6],[37.83,-167.6]],f.n)
    clear_skin(f,[-12,-168.25,37.83,-167.2],57.4,61.8)
    for x,z in north:
        for y in range(f.height_y(57.4),f.height_y(61.8)):
            f.c.set(x,y,z,'mud_bricks' if y<f.height_y(59.05) else 'white_concrete','facade')
    slots=[]
    for centre in p['north_slot_centres_u_m']:
        # Exactly one principal pane column; a corner return can require a
        # second connected column at the minimal rotation step.
        idx=min(range(len(north)),key=lambda i:abs(uv(f,*north[i])[0]-centre))
        columns=north[max(0,idx-1):min(len(north),idx+2)]
        panes=sheet(f,f'north-slot-{len(slots)+1}',columns,59.05,61.5)
        slots.append(dict(source_centre_u_m=centre,columns=columns,pane_cells=panes))
    # Thin fascia retints an existing cap/backing cell where possible; it
    # never raises a source roof slab to a full block.
    for x,z in north:
        y=f.height_y(61.5);s=f.c.palette[f.c.get(x,y,z)]
        if s['Name']=='minecraft:smooth_stone_slab':
            f.c.set(x,y,z,'smooth_quartz_slab','trim',s.get('Properties'))
        else:f.c.set(x,y,z,'smooth_quartz','trim')
    d['north_plane']=dict(columns=north,nominal_v_m=-167.6,slots=slots,
        max_centre_error_m=max(abs(uv(f,x,z)[1]+167.6) for x,z in north))
    # The photographed entrance is an attached lower canopy and brick bay.
    # Its low measured source face remains underneath the raised landing.
    front=path_columns(f,[[41.5,-168.65],[49.5,-168.65]],f.n)
    left=path_columns(f,[[41.5,-168.65],[41.5,-166.8]],f.t)
    right=path_columns(f,[[49.5,-168.65],[49.5,-166.8]],-f.t)
    for x,z in set(front+left+right):
        for y in range(f.height_y(58.5),f.height_y(61.5)):
            f.c.set(x,y,z,'bricks','facade')
    clear_skin(f,[43.0,-168.4,48.0,-166.7],58.5,61.0)
    doorcols=path_columns(f,[[43.15,-168.65],[47.85,-168.65]],f.n)
    panes=sheet(f,'four-leaf-entry',doorcols,58.5,61.0)
    dividers=[]
    for centre in (44.45,45.5,46.55):
        x,z=min(doorcols[1:-1],key=lambda q:abs(uv(f,*q)[0]-centre))
        for y in range(f.height_y(58.5),f.height_y(61.0)):
            f.c.set(x,y,z,'light_gray_stained_glass_pane','window',PANE_PROPS)
        dividers.append([x,z])
    canopy=[]
    for x,z,iz,ix in f.each_column(f.local_mask([40.7,-170,50.3,-167.2])):
        y=f.height_y(61.5)
        if ROLES[f.c.roles[y+64,iz,ix]]=='roof':
            continue
        f.c.set(x,y,z,'smooth_quartz_slab','trim',{'type':'bottom','waterlogged':'false'})
        canopy.append([x,y,z])
    d['entry'].update(front_columns=front,side_columns=[left,right],door_columns=doorcols,
        divider_columns=dividers,door_bottom_y=f.height_y(58.5),canopy_cells=canopy,
        canopy_physical_top_navd88_m=61.75,leaf_count=4,
        limitation='Four scaled fixed glazed leaves; operable doors and interior fit-out unresolved')
    # A small source-visible louver, attached to the existing red gable skin.
    gable=path_columns(f,[[53.52,-165.4],[53.52,-164.0]],-f.t)
    louver=[]
    for i,(x,z) in enumerate(gable):
        for y in range(f.height_y(59.5),f.height_y(60.5)):
            f.c.set(x,y,z,'polished_andesite' if i in (0,len(gable)-1) else 'gray_terracotta','facade')
            louver.append([x,y,z])
    d['louver']=dict(columns=gable,cells=louver,count=1,source_centre_v_m=-164.7,
        limitation='Compact supported dark/red proxy; fine louver blades are sub-block')
    if p.get('connect_service_wall_corners'):
        connect_service_wall_corners(f)
    f.features.update(north_glazed_slots=9,entrance_glass_leaves=4,entry_canopies=1,east_louvers=1)
