"""Bounded Robins outline: preserve the measured shell, annotate sparse evidence.

No shared helper, terrain, selection manifest or old study is modified. Native
capture belongs to the coordinator and remains pending while the demo is open.
"""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil

import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes, binary_propagation, distance_transform_cdt
from shapely.geometry import box
from shapely.ops import unary_union

from audit_hill_block_artifact import audit as audit_export
from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study, write_json
from campus_quad_landscape import set_surface
from refine_hill_library_chapel import load_canvas, occupied_shapes

ROOT = Path(__file__).resolve().parents[1]
PARENT = '160015116006-451a0df37b'
BASE = ROOT / 'runtime/campus-reconstruction/campus-envelopes-v2-ground' / PARENT
BASE_SHA = 'd21dc932bd1e7b7d45fd3bd340a2441acf005d07732a3c8b20c3432e58e28b0a'
RESEARCH = ROOT / 'runtime/research/campus-full-detail-20260905'
ORIGIN = np.array([-64.67617711516898, -5.102045760333293])
U = np.array([.9875096568701928, .157558489419372])
V = np.array([-.157558489419372, .9875096568701928])
PANE = dict(north='false', south='false', east='false', west='false', waterlogged='false')
CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))


def local_grid(c):
    zz, xx = np.indices(c.data.shape[1:])
    dx, dz = (xx+c.x_min+.5)/2-ORIGIN[0], (zz+c.z_min+.5)/2-ORIGIN[1]
    return dx*U[0]+dz*U[1], dx*V[0]+dz*V[1]


def building_record(value):
    if isinstance(value, dict):
        if value.get('parent_id') == PARENT and 'measured' in value:
            return value
        for v in value.values():
            found = building_record(v)
            if found:
                return found
    elif isinstance(value, list):
        for v in value:
            found = building_record(v)
            if found:
                return found


def geometry_audit(c, old, r, register, profile):
    @lru_cache(maxsize=None)
    def voxels(state_id):
        result = np.zeros((16, 16, 16), bool)
        for q in occupied_shapes(c.palette[state_id]):
            a,b,d,e,f,g = map(int, q)
            result[a:e,b:f,d:g] = True
        return result

    def at(x,y,z):
        return voxels(c.get(x,y,z))

    cap_failures, partial_failures, roof_backing, pane_caps = [], [], [], []
    for iy,iz,ix in np.argwhere(np.isin(c.roles, [ROLES.index(q) for q in ('roof','trim','window','pavement')])):
        x,y,z = int(ix)+c.x_min, int(iy)-64, int(iz)+c.z_min
        state = c.palette[c.get(x,y,z)]; name = state['Name']
        if not name.endswith(('_slab','_stairs','_pane')):
            continue
        a=at(x,y,z)
        if name.endswith('_pane'):
            for dy, face, other in ((-1,0,15),(1,15,0)):
                if not (a[:,face,:]&at(x,y+dy,z)[:,other,:]).any():
                    pane_caps.append([x,y,z,dy])
        else:
            contact=(a[:,0,:]&at(x,y-1,z)[:,15,:]).any()
            contact|=(a[0,:,:]&at(x-1,y,z)[15,:,:]).any()
            contact|=(a[15,:,:]&at(x+1,y,z)[0,:,:]).any()
            contact|=(a[:,:,0]&at(x,y,z-1)[:,:,15]).any()
            contact|=(a[:,:,15]&at(x,y,z+1)[:,:,0]).any()
            if not contact:
                partial_failures.append([x,y,z])
    # Exact roof-role preservation includes cap shape, facing, backing and low
    # source fragments. No source face is reclassified by this rough outline.
    old_roof=old.roles==ROLES.index('roof')
    roof_exact=np.array_equal(c.data[old_roof],old.data[old_roof]) and np.array_equal(c.roles[old_roof],old.roles[old_roof])
    for iz,ix in np.argwhere(r.footprint_mask):
        x,z=int(ix)+c.x_min,int(iz)+c.z_min
        roof_y=np.flatnonzero(old_roof[:,iz,ix])
        if not len(roof_y):
            continue
        y=int(roof_y.max())-64
        if not at(x,y-1,z).all():
            roof_backing.append([x,y-1,z])
        if not np.array_equal(at(x,y,z),voxels(int(old.data[y+64,iz,ix]))):
            cap_failures.append([x,y,z])

    rows,cols=np.nonzero(r.footprint_mask)
    lz,hz,lx,hx=int(rows.min())-2,int(rows.max())+3,int(cols.min())-2,int(cols.max())+3
    slices=[]
    for y in range(73,97):
        interior=distance_transform_cdt(r.footprint_mask&(r.heights>(y+1)/2+25+.5),metric='taxicab')>=3
        for sub in (4,12):
            layer=np.zeros(((hz-lz)*16,(hx-lx)*16),bool)
            for iz,ix in np.argwhere(c.data[y+64,lz:hz,lx:hx]!=0):
                iz,ix=int(iz)+lz,int(ix)+lx
                layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=voxels(int(c.data[y+64,iz,ix]))[:,sub,:].T
            # The open door corridor is the sole declared enclosure exception.
            if 78<=y<82:
                for x in (-128,-127):
                    iz,ix=29-c.z_min,x-c.x_min
                    layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=True
            seed=np.zeros_like(layer);seed[0,:]=seed[-1,:]=seed[:,0]=seed[:,-1]=True
            outside=binary_propagation(seed,mask=~layer)
            failures=[[int(ix)+c.x_min,y,int(iz)+c.z_min] for iz,ix in np.argwhere(interior) if outside[(iz-lz)*16+8,(ix-lx)*16+8]]
            slices.append(dict(y=y,subvoxel_height=sub,interior_columns=int(interior.sum()),leaks=len(failures),examples=failures[:5]))

    # Actual-player surface following samples evaluate each tread, including
    # the precise riser transition. The maximum allowed step is half a block.
    route_failures=[];samples=[];last=None;steps=[]
    for z in np.linspace(36.5,27.5,181):
        x=-127.0
        footprint=(x-.3,z-.3,x+.3,z+.3)
        supports=[]
        for bx in range(math.floor(x-.3),math.floor(x+.3)+1):
            for bz in range(math.floor(z-.3),math.floor(z+.3)+1):
                for by in range(72,79):
                    for q in occupied_shapes(c.palette[c.get(bx,by,bz)]):
                        ax,ay,az,ex,ey,ez=(q[i]/16+(bx,by,bz)[i%3] for i in range(6))
                        if min(footprint[2],ex)>max(footprint[0],ax)+1e-7 and min(footprint[3],ez)>max(footprint[1],az)+1e-7:
                            supports.append(ey)
        feet=max(supports) if supports else None
        collisions=[]
        if feet is not None:
            body=(x-.3,feet,z-.3,x+.3,feet+1.8,z+.3)
            for bx in range(math.floor(x-.3),math.floor(x+.3)+1):
                for bz in range(math.floor(z-.3),math.floor(z+.3)+1):
                    for by in range(math.floor(feet),math.ceil(feet+1.8)):
                        for q in occupied_shapes(c.palette[c.get(bx,by,bz)]):
                            bounds=tuple(q[i]/16+(bx,by,bz)[i%3] for i in range(6))
                            if all(min(body[i+3],bounds[i+3])-max(body[i],bounds[i])>1e-7 for i in range(3)):
                                collisions.append([bx,by,bz])
            if last is not None:
                steps.append(abs(feet-last))
            last=feet
        samples.append([x,feet,float(z)])
        if feet is None or collisions:
            route_failures.append(dict(xyz=samples[-1],collisions=collisions))

    changed=np.any((c.data!=old.data)|(c.roles!=old.roles),axis=0)
    outside=np.argwhere(changed&~r.footprint_mask)
    allowed=set(map(tuple,register['site_columns_xz']))
    unregistered=[[int(ix)+c.x_min,int(iz)+c.z_min] for iz,ix in outside if (int(ix)+c.x_min,int(iz)+c.z_min) not in allowed]
    support_failures=[]
    for iz,ix in np.argwhere(~r.footprint_mask):
        nonzero=np.flatnonzero(c.data[:,iz,ix])
        if not len(nonzero) or np.any(c.data[nonzero[0]:nonzero[-1]+1,iz,ix]==0):
            support_failures.append([int(ix)+c.x_min,int(iz)+c.z_min])
    u,v=local_grid(c)
    architecture=np.any(~np.isin(c.roles,[ROLES.index(q) for q in ('air','terrain','pavement')]),axis=0)
    mask=binary_fill_holes(architecture)
    for u0,v0,u1,v1 in profile['assembly_site_bounds_uv_m']:
        mask|=(u>=u0)&(u<u1)&(v>=v0)&(v<v1)
    mask=binary_fill_holes(binary_dilation(mask,iterations=1))
    missing=np.argwhere(changed&~mask)
    ownership_shape=unary_union([box((ix+c.x_min)/2,(iz+c.z_min)/2,(ix+c.x_min+1)/2,(iz+c.z_min+1)/2) for iz,ix in np.argwhere(mask)])
    neighbors=[]
    for name,pid in [('Sherrerd','160015116006-07f1d5b7e0'),('Johnson','160015116006-36b81aa17d'),('Markle','160015116006-53c8a9efca')]:
        other=load_measured_building(parent_id=pid)
        neighbors.append(dict(name=name,source_footprint_gap_m=float(r.building.footprint.distance(other.footprint)) if hasattr(r,'building') else None,ownership_gap_m=float(ownership_shape.distance(other.footprint)),ownership_overlap_m2=float(ownership_shape.intersection(other.footprint).area)))
    result=dict(format='hill-robins-outline-physical-audit-v1',
        roof=dict(exact_source_roof_states=roof_exact,roof_cells=int(old_roof.sum()),cap_failures=cap_failures,backing_failures=roof_backing),
        construction=dict(unsupported_partial_blocks=partial_failures,pane_cap_failures=pane_caps),
        enclosure=dict(slices=slices,passed=not any(q['leaks'] for q in slices),exception='Only the declared south door corridor; no other virtual closure.'),
        route=dict(passed=not route_failures and max(steps,default=0)<=.5,samples=len(samples),sample_spacing_blocks=.05,player_width_blocks=.6,player_height_blocks=1.8,maximum_step_blocks=max(steps,default=0),failures=route_failures,points_xyz=samples[::20]),
        ground=dict(exterior_columns=int((~r.footprint_mask).sum()),changed_exterior_columns=len(outside),unregistered_changed_columns=unregistered,missing_support_columns=support_failures),
        ownership=dict(margin_m=.5,owned_columns=int(mask.sum()),bounds_xz_m=list(ownership_shape.bounds),site_bounds_uv_m=profile['assembly_site_bounds_uv_m'],omitted_authored_columns=missing.tolist(),neighbors=neighbors),
        passed=roof_exact and not(cap_failures or roof_backing or partial_failures or pane_caps or route_failures or unregistered or support_failures or len(missing) or any(q['leaks'] for q in slices) or any(q['ownership_overlap_m2'] for q in neighbors)) and max(steps,default=0)<=.5)
    return result


def build(output):
    if output.exists():
        raise FileExistsError(output)
    assert digest(BASE/'sample-blocks.npz')==BASE_SHA
    old=load_canvas(BASE); c=load_canvas(BASE)
    old_manifest=json.loads((BASE/'manifest.json').read_text())
    source=building_record(json.loads((RESEARCH/'housing-facades.json').read_text(encoding='utf-8')))
    b=load_measured_building(parent_id=PARENT)
    r=rasterize_roof(b,[-72,-16,-48,24],.5)
    u,v=local_grid(c)
    source_files=[BASE/'sample-blocks.npz',BASE/'profile.json',BASE/'manifest.json',RESEARCH/'housing-facades.json',RESEARCH/'housing-material-evidence.json',RESEARCH/'housing-major-roof-face-masks.json',RESEARCH/'terrain-all-components-perimeter-controls.json',RESEARCH/'dutch-east-aerial-crop.png',ROOT/'runtime/research/campus-priority-20260905/campus-2026-aerial-original.jpg',ROOT/'docs/research/hill-housing-facades-20260905.md',ROOT/'runtime/research/campus-exterior-draft-20260927/next-builder-packets.md']
    sources=[dict(path=str(q.relative_to(ROOT)).replace('\\','/'),sha256=digest(q)) for q in source_files]
    # Keep the source shell and all measured roof states. Change only wall
    # materials, with the exposed south gable distinctly stone-patterned.
    for iy,iz,ix in np.argwhere(c.roles==ROLES.index('facade')):
        c.set(int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min,'cobblestone' if v[iz,ix]>18.8 else 'white_concrete','facade')
    # Minimal inward corner bridges close the diagonal raster's pinholes.
    # Work inside each horizontal source roof section and never overwrite roof.
    bridges=[]
    for y in range(73,97):
        body=r.footprint_mask&(r.heights>(y+1)/2+25)
        edge=body&~binary_erosion(body)
        # Full inward backing at roof-section corners also closes the exposed
        # half of an eave stair without altering its measured exterior cap.
        joins=set(map(tuple,np.argwhere(body&~binary_erosion(body,structure=np.ones((3,3),bool)))))
        for iz,ix in np.argwhere(edge):
            for dz in (-1,1):
                if not edge[iz+dz,ix+1]:
                    continue
                options=[q for q in ((iz,ix+1),(iz+dz,ix)) if body[q]]
                if len(options)==1:
                    joins.add(options[0])
        for iz,ix in joins:
            x,z=int(ix)+c.x_min,int(iz)+c.z_min
            if c.get(x,y,z)==0:
                c.set(x,y,z,'cobblestone' if v[iz,ix]>18.8 else 'white_concrete','facade');bridges.append([x,y,z])
    openings=[]
    for name,xs,z,lo,hi in [('south-upper-sash',[-128,-127],29,83,86),('south-attic-vent',[-123],30,91,92)]:
        cells=[]
        for x in xs:
            for y in range(lo,hi):
                assert c.get(x,y,z) and c.roles[y+64,z-c.z_min,x-c.x_min]!=ROLES.index('roof')
                c.set(x,y,z,'gray_stained_glass_pane' if 'sash' in name else 'white_stained_glass_pane','window',PANE);cells.append([x,y,z])
            for y in (lo-1,hi):
                c.set(x,y,z,'smooth_quartz','trim')
        for x in (min(xs)-1,max(xs)+1):
            for y in range(lo,hi):
                c.set(x,y,z,'dark_oak_planks' if 'sash' in name else 'smooth_quartz','facade' if 'sash' in name else 'trim')
        openings.append(dict(name=name,cells=cells,status='Observed subset; exact position and dimensions inferred from aerial, not surveyed.'))
    site=[]
    for z in range(27,37):
        surface={31:77.5,32:77,33:76.5}.get(z,78 if z<=30 else 76)
        for x in (-128,-127):
            iz,ix=z-c.z_min,x-c.x_min
            if not r.footprint_mask[iz,ix]:
                set_surface(c,iz,ix,surface,'smooth_stone','smooth_stone_slab');site.append([x,z])
            else:
                for y in range(73,78):
                    c.set(x,y,z,'smooth_stone','floor')
            for y in range(math.ceil(surface),82):
                c.set(x,y,z,'air','air')
    for x,hinge in [(-128,'right'),(-127,'left')]:
        for half,y in [('lower',78),('upper',79)]:
            c.set(x,y,29,'birch_door','door',dict(half=half,facing='south',hinge=hinge,open='true',powered='false'))
    # White door head and jambs remain flush; opening is a rough four-block
    # recess containing usable standard vanilla doors, not a bespoke asset.
    for x in (-129,-126):
        for y in range(78,82):
            c.set(x,y,29,'smooth_quartz','trim')
    for x in (-128,-127):
        c.set(x,82,29,'smooth_quartz','trim')
    connect_window_panes(c)
    site_uv=np.array([((np.array([(x+.5)/2,(z+.5)/2])-ORIGIN)@U,(np.array([(x+.5)/2,(z+.5)/2])-ORIGIN)@V) for x,z in site])
    site_bounds=[float(math.floor(site_uv[:,0].min()*2)/2),float(math.floor(site_uv[:,1].min()*2)/2),float(math.ceil(site_uv[:,0].max()*2)/2),float(math.ceil(site_uv[:,1].max()*2)/2)]
    profile=dict(name='Hill — Robins Dormitory bounded exterior outline',revision='2026-09-27-robins-outline-v1-2x',parent_id=PARENT,school_names=['Robins Dormitory - Dutch Village'],school_map_numbers=[44],blocks_per_metre=2,vertical_offset_m=-25,
        geometry=dict(origin_xz_m=ORIGIN.tolist(),axis_degrees=math.degrees(math.atan2(U[1],U[0])),entrance_floor_navd88_m=64.0),
        materials=dict(south_gable='cobblestone',west_return='white_concrete',hidden_generic_walls='white_concrete',roof_family='stone_brick',trim='smooth_quartz',shutters='dark_oak_planks',glazing='gray_stained_glass_pane'),
        material_review=dict(status='Bounded semantic vanilla proxies from retained individual evidence; native appearance pending.',rationale='Cobblestone irregular texture for the stone-pattern gable; white concrete for the painted return; retained gray roof. Mineralogy, roof product and hidden wall finish are not inferred.'),
        assembly_site_bounds_uv_m=[site_bounds],detail_status='Rough exterior outline with only the three visible south features and short inferred entry registration.',
        uncertainties=['North/east openings and wall finishes remain unresolved; white closure is explicitly generic.','West sash count and glazed projecting bay dimensions remain unresolved; no new bay was added.','All seven measured roof faces and original footprint retained. Low face 3 may be a ground/deck reconstruction; this outline does not repair or reinterpret it.','The south door, upper sash and vent are observed; precise dimensions, registration and threshold at NAVD88 64m are inferred.','Brick chimney shafts are visible but exact positions/count are unregistered, so no new chimney geometry is invented.','No interior completion; the usable route ends 1m inside the door.','No native acceptance, integrated campus replacement or shared path construction is claimed.'])
    register=dict(source_parent=PARENT,source_archive_sha256=BASE_SHA,source_roof_faces_preserved=list(range(7)),source_footprint_bounds_xz_m=list(b.footprint.bounds),roof_face_3_retained_unresolved=True,
        inward_corner_bridge_cells=bridges,visible_openings=openings,entry_corridor_columns_xz=[[x,z] for x in (-128,-127) for z in range(27,30)],site_columns_xz=site,
        source_facades=source['facades'],source_roof_audit=source['roof_face_audit'])
    report=geometry_audit(c,old,r,register,profile)
    if not report['passed']:
        diagnostic=ROOT/'runtime/campus-reconstruction/robins-outline-v1-construction-diagnostic.json'
        write_json(diagnostic,report)
        raise ValueError(f'Construction checks failed; preserved diagnostic {diagnostic}')
    cameras=[dict(name=name,eye=eye,target=target,fov=fov) for name,eye,target,fov in [
        ('south-gable-ground',[-127,80,46],[-124,85,29],62),
        ('southwest-material-junction',[-150,85,42],[-130,85,24],65),
        ('west-return-outline',[-158,88,9],[-131,86,11],64),
        ('north-unresolved-outline',[-123,87,-25],[-119,85,-3],64),
        ('east-unresolved-outline',[-84,88,10],[-109,85,12],64),
        ('south-entry-steps',[-127,80,38],[-127,79,28],62)]]
    for q in cameras:
        assert c.get(*[math.floor(n) for n in q['eye']])==0,q['name']
    anchors=dict(format='hill-exterior-connection-anchors-v1',status='Observed entry/steps; exact registration and threshold are inferred.',
        source='2026 official aerial; housing-facades Robins south record',
        door=dict(xyz=[-127,78,29.5],navd88_m=64.0,source_uv_m=[4.7,19.7],registration_tolerance_m=1.0,clear_width_blocks=1.625),
        walk_seam=dict(xyz=[-127,76,36.5],metres_east_navd88_south=[-63.5,63,18.25],clear_width_blocks=2,owner='Robins ends at south edge of Z=36; campus roads owns onward link.'),
        site_bounds_xz_blocks_half_open=[-128,30,-126,37],site_bounds_xz_m_half_open=[-64,15,-63,18.5],route=report['route'])
    evidence=dict(source_roof=old_manifest['source_roof'],roof_coverage=old_manifest['roof_coverage'],terrain=old_manifest['terrain'],source_shell=dict(path=str(BASE.relative_to(ROOT)),sha256=BASE_SHA),source_packet=dict(path='source-packet.json'),roof_changes='None: exact source roof states retained.',physical_audit='physical-audit.json')
    finish_study(c,profile,output,cameras,evidence)
    archive_sha=digest(output/'sample-blocks.npz')
    for value in (report,register,anchors):
        value['archive_sha256']=archive_sha
    write_json(output/'source-packet.json',dict(format='hill-robins-bounded-source-packet-v1',sources=sources,source_record=source,visible_vs_inferred=profile['uncertainties']))
    write_json(output/'detail-register.json',register)
    write_json(output/'physical-audit.json',report)
    write_json(output/'connection-anchors.json',anchors)
    np.savez_compressed(output/'source-roof-raster.npz',heights=r.heights,mask=r.footprint_mask,face_indices=r.face_indices,gradient_x=r.gradient_x,gradient_z=r.gradient_z)
    shutil.copyfile(__file__,output/Path(__file__).name)
    exported=audit_export(output)
    assert exported['passed'],exported['errors']
    assert digest(BASE/'sample-blocks.npz')==BASE_SHA
    write_json(output/'native-review.json',dict(status='pending_native_review',archive_sha256=archive_sha,inspected_images=[],findings=['Exact export/palette/closure/route checks passed. No native client launched.'],limitations=profile['uncertainties']))
    print(json.dumps(dict(status='native_review_pending',study=str(output),archive_sha256=archive_sha,source_packet_sha256=digest(output/'source-packet.json'),ownership=report['ownership'],walk_seam=anchors['walk_seam']),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/campus-reconstruction/robins-outline-v1-2x')
    build(parser.parse_args().output.resolve())
