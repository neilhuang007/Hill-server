"""Annan's source-bounded west windows and connected measured enclosure."""

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion
from shapely import contains_xy
from shapely.ops import unary_union

from build_hill_chapel_sample import ROLES
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {}
CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))


def prepare_roof(r, f, p):
    for info in [p['reference_packet'], *p.get('reference_addenda', [])]:
        assert hashlib.sha256((ROOT / info['path']).read_bytes()).hexdigest() == info['sha256']
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
    SOURCE.update(source_raster=r, building=b, details=dict(source_faces=faces, roof_retints=[],
        wall_corner_bridges=[], glazing=[], floors=[], division=[], canopy=[], backing_retints=[],
        south_wall_completion=[]))
    omitted=[2,7,8,9,10,12,13,14,15,16,18,19]
    union=unary_union([b.roof_faces[i].polygon for i in omitted])
    mask=contains_xy(union,f.x,f.z) & r.footprint_mask
    assert np.array_equal(mask,np.isin(r.face_indices,omitted))
    plane=b.roof_faces[20]
    levels=plane.a*f.x+plane.b*f.z+plane.c
    heights=r.heights.copy();heights[mask]=levels[mask]
    gx=r.gradient_x.copy();gz=r.gradient_z.copy()
    gx[mask]=plane.a;gz[mask]=plane.b
    indices=r.face_indices.copy();indices[mask]=1_000_000
    patch=dict(face_index=1_000_000,source='Sol frozen vegetation-contamination disposition',
        excluded_faces=omitted,source_union_area_m2=union.area,source_union_bounds_xz_m=list(union.bounds),
        plane_source_face=20,plane=[plane.a,plane.b,plane.c],affected_columns=int(mask.sum()),
        authority=p['reference_addenda'][0])
    revised=replace(r,heights=heights,gradient_x=gx,gradient_z=gz,face_indices=indices,
        authored_roof_patches=(*r.authored_roof_patches,patch))
    SOURCE['raster']=revised
    SOURCE['details']['roof_patch']=patch
    return revised


def connect_wall_corners(f):
    """Add only inward missing cells at a three-inside/one-outside grid turn."""
    body = f.r.footprint_mask
    boundary = body & ~binary_erosion(body, structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
    candidates = {}
    for iz, ix in np.argwhere(boundary):
        for dz in (-1, 1):
            jz, jx = iz + dz, ix + 1
            if not boundary[jz, jx]:
                continue
            corners = [(iz, jx), (jz, ix)]
            inside = [q for q in corners if body[q]]
            if len(inside) != 1:
                continue
            q = inside[0]
            candidates[q] = ((int(ix)+f.c.x_min, int(iz)+f.c.z_min),
                             (int(jx)+f.c.x_min, int(jz)+f.c.z_min))
    for (iz, ix), ends in candidates.items():
        x, z = int(ix)+f.c.x_min, int(iz)+f.c.z_min
        for y in range(60, 110):
            if f.c.get(x, y, z):
                continue
            if all(ROLES[f.c.roles[y+64, qz-f.c.z_min, qx-f.c.x_min]] == 'facade' for qx, qz in ends):
                f.c.set(x, y, z, 'bricks', 'facade')
                SOURCE['details']['wall_corner_bridges'].append(dict(xyz=[x,y,z],
                    attached_wall_cells=[[qx,y,qz] for qx,qz in ends]))


def floor_plate(f, name, mask, height):
    """A local program floor, leaving low measured faces entirely untouched."""
    half = math.floor((height - 25) * 4 + .5)
    cap = (half-1)//2
    cells = []
    for x,z,iz,ix in f.each_column(mask & f.r.footprint_mask & (f.r.heights > height+.75)):
        if ROLES[f.c.roles[cap+64,iz,ix]] not in ('air', 'floor'):
            continue
        if name != 'upper_program':
            for y in range(61, cap):
                if not f.c.get(x,y,z):
                    f.c.set(x,y,z,'smooth_stone','floor')
        f.c.set(x,cap,z,'smooth_stone_slab' if half%2 else 'smooth_stone','floor',
            {'type':'bottom','waterlogged':'false'} if half%2 else None)
        cells.append([x,cap,z])
    SOURCE['details']['floors'].append(dict(name=name,navd88_m=height,
        quantized_surface_y=half/2,cells=cells))


def wall_trace(f, side, at, lo, hi, y):
    """Recover the existing single nearest-inside wall and its inward joins."""
    along, normal = (f.v, f.u) if side == 'west' else (f.u, f.v)
    mask = (abs(normal-at)<.8) & (along>=lo) & (along<=hi)
    points = []
    for x,z,iz,ix in f.each_column(mask):
        if ROLES[f.c.roles[y+64,iz,ix]] == 'facade':
            points.append((x,z))
    return sorted(points, key=lambda q:(along[q[1]-f.c.z_min,q[0]-f.c.x_min],q))


def opening(f, side, centre, width, bottom, height, name, confidence):
    at = 61.3 if side == 'west' else -133.99
    a,b = f.height_y(bottom),f.height_y(bottom+height)
    trace = wall_trace(f,side,at,centre-width/2-.55,centre+width/2+.55,a)
    along = f.v if side == 'west' else f.u
    selected = [(x,z) for x,z in trace if abs(along[z-f.c.z_min,x-f.c.x_min]-centre)<=width/2]
    assert selected, (name,centre)
    cells=[]
    for x,z in selected:
        for y in range(a,b):
            assert ROLES[f.c.roles[y+64,z-f.c.z_min,x-f.c.x_min]] == 'facade', (name,x,y,z)
            f.c.set(x,y,z,'gray_stained_glass_pane','window',PANE_PROPS)
            cells.append([x,y,z])
        # Existing full masonry heads and sills preserve the narrow opening.
        assert f.c.get(x,a-1,z) and f.c.get(x,b,z), (name,x,z,'open cap')
    SOURCE['details']['glazing'].append(dict(name=name,side=side,plane_m=at,
        centre_m=centre,width_m=width,bottom_navd88_m=bottom,height_m=height,
        confidence=confidence,pane_cells=cells,columns=[list(q) for q in selected],
        low_y=a,high_y_exclusive=b))


def attached_trim(f):
    """Quarter-metre slab proxies attached to the existing wall, never belts."""
    d=SOURCE['details']
    # A one-cell shallow ledge is the minimum voxel proxy for the pale course.
    y=f.height_y(60.5)
    selected=f.local_mask([60.75,-163.0,61.5,-134.6]) & ~f.r.footprint_mask
    for x,z,iz,ix in f.each_column(selected):
        if f.c.get(x,y,z):continue
        if any(f.c.palette[f.c.get(x+dx,y,z+dz)]['Name']=='minecraft:bricks' for dx,dz in CARDINAL):
            f.c.set(x,y,z,'smooth_stone_slab','trim',{'type':'bottom','waterlogged':'false'})
            d['division'].append([x,y,z])
    # Canopy projects only into the immediate south entry threshold, <1m.
    y=f.height_y(59.5)
    for x,z,iz,ix in f.each_column(f.local_mask([64.4,-134.4,67.2,-133.25])):
        if f.c.get(x,y,z):continue
        f.c.set(x,y,z,'smooth_stone_slab','trim',{'type':'bottom','waterlogged':'false'})
        d['canopy'].append([x,y,z])


def retint_exposed_backing(f):
    """Only the already occupied full substrate under a retained cap."""
    for x,z,iz,ix in f.each_column(f.r.footprint_mask & (f.r.face_indices!=4)):
        half=math.floor((float(f.r.heights[iz,ix])-25)*4+.5)
        cap=(half-1)//2;y=cap-1
        before=f.c.palette[f.c.get(x,y,z)]
        if before['Name']!='minecraft:polished_andesite' or ROLES[f.c.roles[y+64,iz,ix]]!='roof':
            continue
        exposed=[]
        for dx,dz in CARDINAL:
            jz,jx=iz+dz,ix+dx
            outer=not f.r.footprint_mask[jz,jx]
            tall_junction=f.r.footprint_mask[jz,jx] and f.r.heights[iz,ix]-f.r.heights[jz,jx]>=1.0
            if (outer or tall_junction) and f.c.get(x+dx,y,z+dz)==0:
                exposed.append([dx,dz])
        if exposed:
            f.c.set(x,y,z,'bricks','facade')
            SOURCE['details']['backing_retints'].append(dict(xyz=[x,y,z],cap_xyz=[x,cap,z],
                before=before,after={'Name':'minecraft:bricks'},exterior_directions=exposed,
                face_index=int(f.r.face_indices[iz,ix])))


def complete_south_plane(f):
    """Continue the proven lower outer trace above localized low caps."""
    body=f.r.footprint_mask
    boundary=body & ~binary_erosion(body,structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
    strip=f.local_mask([61.75,-135.25,77.1,-133.3])
    trace={}
    for x,z,iz,ix in f.each_column(boundary&strip):
        trace[x]=max(trace.get(x,z),z)
    ordered=sorted(trace.items());columns=set(ordered)
    for (x0,z0),(x1,z1) in zip(ordered,ordered[1:]):
        if x1-x0==1 and z1-z0==1:
            columns.add((x1,z0))
    west,east=SOURCE['building'].roof_faces[11],SOURCE['building'].roof_faces[20]
    for x,z in sorted(columns):
        iz,ix=z-f.c.z_min,x-f.c.x_min
        assert body[iz,ix]
        xm,zm=(x+.5)/2,(z+.5)/2
        # The planes constrain only wall closure below the retained roof.
        ceiling=min(west.a*xm+west.b*zm+west.c,east.a*xm+east.b*zm+east.c)
        stop=math.floor((ceiling-25)*2)-1
        for y in range(69,stop):
            if f.c.get(x,y,z):continue
            f.c.set(x,y,z,'bricks','facade')
            SOURCE['details']['south_wall_completion'].append(dict(xyz=[x,y,z],
                roof_underside_limit_y=stop,outer_trace_z=trace.get(x),
                inward_cardinal_bridge=z!=trace.get(x)))
    SOURCE['details']['south_outer_trace_xz']=[list(q) for q in ordered]


def build_details(f,p):
    d=SOURCE['details']
    replacements={'minecraft:stone_bricks':'polished_andesite',
        'minecraft:stone_brick_slab':'polished_andesite_slab',
        'minecraft:stone_brick_stairs':'polished_andesite_stairs'}
    for iy,iz,ix in np.argwhere(f.c.roles==ROLES.index('roof')):
        before=f.c.palette[f.c.data[iy,iz,ix]]
        after=replacements[before['Name']]
        if int(f.r.face_indices[iz,ix])==4:
            after={'polished_andesite':'smooth_stone','polished_andesite_slab':'smooth_stone_slab'}.get(after,after)
        x,y,z=int(ix)+f.c.x_min,int(iy)-64,int(iz)+f.c.z_min
        f.c.set(x,y,z,after,'roof',before.get('Properties'))
        d['roof_retints'].append(dict(xyz=[x,y,z],before=before,after=f.c.palette[f.c.get(x,y,z)]))
    connect_wall_corners(f)
    floor_plate(f,'lower_program',f.v>=-163.3,57.0)
    floor_plate(f,'north_approach',f.v<-163.3,59.0)
    floor_plate(f,'upper_program',f.local_mask([61.3,-163.3,77.18,-133.99]),60.3)
    for i,centre in enumerate(p['west_upper_centres_v_m']):
        opening(f,'west',centre,.9,62.15,1.3,f'west-upper-{i+1}','four directly observed; centres interpreted')
    for i,centre in enumerate(p['west_lower_centres_v_m']):
        opening(f,'west',centre,1.2,57.85,1.8,f'west-lower-{i+1}','five interpreted from at least four partly visible patches')
    opening(f,'south',65.8,1.3,57.0,2.25,'south-entry','single conservative interpreted fixed glazed entry')
    attached_trim(f)
    if p.get('complete_south_plane'):
        complete_south_plane(f)
    if p.get('retint_exposed_backing'):
        retint_exposed_backing(f)
    f.features['west_observed_upper_windows']=4
    f.features['west_interpreted_lower_windows']=5
    f.features['south_interpreted_fixed_entry']=1
    f.features['inward_wall_corner_bridges']=len(d['wall_corner_bridges'])
