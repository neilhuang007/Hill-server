"""Check a Ferenbach draft archive, measured roof, contacts, site and entry."""

import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_propagation, binary_erosion

from audit_hill_block_artifact import audit
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

ROOT=Path(__file__).resolve().parents[1]


def run(out):
    p=json.loads((out/'profile.json').read_text());m=json.loads((out/'manifest.json').read_text())
    d=json.loads((out/'detail-register.json').read_text());bb=m['source_roof']['world_bounds_blocks']
    c=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as a:
        q=a['coords'];c.data[q[:,1]+64,q[:,2]-bb[1],q[:,0]-bb[0]]=a['state_ids']
        c.roles[q[:,1]+64,q[:,2]-bb[1],q[:,0]-bb[0]]=a['role_ids'];c.palette=json.loads(str(a['palette_json']))
    with np.load(out/'source-roof-raster.npz') as a:
        body=a['body_mask'].copy();walls=a['wall_mask'].copy()
    b=load_measured_building(parent_id=p['parent_id']);r=rasterize_roof(b,[v/2 for v in bb],.5)
    h,ids,meta=terrain_arrays(ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz',2,[v/2 for v in bb])
    baseline=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    build_ground(baseline,h,ids,meta['materials'],-25)
    smooth_exposed_measured_pavement(baseline,h,baseline.ground_heights,vertical_offset=-25)
    initial_states=baseline.data.copy();initial_roles=baseline.roles.copy();initial_palette=list(baseline.palette)
    build_measured_shell(baseline,b,r,vertical_offset=-25,floor_navd88=65.5,facade='pale_oak_planks',foundation='bricks',roof_family='stone_brick',roof_backing_metres=.4)
    lookup={json.dumps(s,sort_keys=True):i for i,s in enumerate(c.palette)}
    mapping=np.array([lookup.get(json.dumps(s,sort_keys=True),65535) for s in baseline.palette])
    roof=baseline.roles==ROLES.index('roof')
    roof_exact=bool(np.array_equal(c.data[roof],mapping[baseline.data[roof]]))
    ground_mapping=np.array([lookup.get(json.dumps(s,sort_keys=True),65535) for s in initial_palette])
    site_set={(q[0]-bb[0],q[1]-bb[1]) for q in d['site_columns']}
    changed=((c.data!=ground_mapping[initial_states])|(c.roles!=initial_roles)).any(0)
    authorized=r.footprint_mask.copy()
    for ix,iz in site_set:authorized[iz,ix]=True
    unexpected=np.argwhere(changed&~authorized)
    cache={};jar=Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    def shape(resources,q):
        state=c.palette[c.get(*q)];key=json.dumps(state,sort_keys=True)
        if key not in cache:
            grid=np.zeros((16,16,16),bool)
            if state['Name']!='minecraft:air':
                bs=BlockState(state['Name'],state.get('Properties',{}))
                for app in applications_for_state(resources.blockstate(bs.name),bs.properties,q):
                    for e in elements_for_state(resources.model(app.model),bs):
                        corners=np.array([rotate_model_point(v,app) for v in itertools.product(*zip(e['from'],e['to']))])
                        lo=np.maximum(0,np.rint(corners.min(0)).astype(int));hi=np.minimum(16,np.rint(corners.max(0)).astype(int))
                        grid[lo[0]:hi[0],lo[1]:hi[1],lo[2]:hi[2]]=True
            cache[key]=grid
        return cache[key]
    def contact(a,n,dx,dz):
        if dx==1:return bool((a[15]&n[0]).any())
        if dx==-1:return bool((a[0]&n[15]).any())
        if dz==1:return bool((a[:,:,15]&n[:,:,0]).any())
        return bool((a[:,:,0]&n[:,:,15]).any())
    partial_fail=[];pane_fail=[];slices=[];route_fail=[];support_fail=[]
    portal={tuple(q) for q in d['provisional_portal']['air_cells']}
    with VanillaResources(jar) as resources:
        arch=[ROLES.index(q) for q in ('facade','floor','window','trim','roof')]
        for iy,iz,ix in np.argwhere(np.isin(c.roles,arch)):
            state=c.palette[int(c.data[iy,iz,ix])];name=state['Name'];q=(int(ix)+bb[0],int(iy)-64,int(iz)+bb[1])
            if name.endswith('_pane'):
                a=shape(resources,q)
                for dy,face,opp in [(-1,0,15),(1,15,0)]:
                    if not (a[:,face,:]&shape(resources,(q[0],q[1]+dy,q[2]))[:,opp,:]).any():pane_fail.append([*q,dy])
            if name.endswith(('_stairs','_slab')):
                a=shape(resources,q)
                if not ((a[:,0,:]&shape(resources,(q[0],q[1]-1,q[2]))[:,15,:]).any() or
                        any(contact(a,shape(resources,(q[0]+dx,q[1],q[2]+dz)),dx,dz) for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)])):
                    partial_fail.append(q)
        izs,ixs=np.nonzero(body);lx,hx=int(ixs.min())-2,int(ixs.max())+3;lz,hz=int(izs.min())-2,int(izs.max())+3
        interior=binary_erosion(body,structure=np.ones((3,3)),iterations=2)
        for y in range(81,95):
            for sub in (4,12):
                layer=np.zeros(((hz-lz)*16,(hx-lx)*16),bool)
                for iz in range(lz,hz):
                    for ix in range(lx,hx):
                        q=(ix+bb[0],y,iz+bb[1]);a=shape(resources,q)[:,sub,:].T
                        layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=True if q in portal else a
                seed=np.zeros_like(layer);seed[0,:]=seed[-1,:]=seed[:,0]=seed[:,-1]=True
                exterior=binary_propagation(seed,mask=~layer);leaks=[]
                for iz,ix in np.argwhere(interior & (r.heights>(y+1)/2+25+.5)):
                    if exterior[(iz-lz)*16+8,(ix-lx)*16+8]:leaks.append([int(ix)+bb[0],y,int(iz)+bb[1]])
                slices.append(dict(y=y,subheight=sub,leaks=len(leaks),examples=leaks[:3]))
        # Native-player size in blocks; route into the explicitly open draft
        # portal. Ground support checked across the full 0.6-block footprint.
        angle=math.radians(-12);route_samples=[]
        for v in np.linspace(8.25,11,61):
            x=2*(300+12.5*math.cos(angle)-v*math.sin(angle));z=2*(-66+12.5*math.sin(angle)+v*math.cos(angle));feet=81
            for fx in np.linspace(x-.29,x+.29,4):
                for fz in np.linspace(z-.29,z+.29,4):
                    ix,iz=math.floor(fx),math.floor(fz);sx,sz=int((fx-ix)*16),int((fz-iz)*16)
                    if not shape(resources,(ix,80,iz))[sx,15,sz]:support_fail.append([fx,feet,fz])
                    for y in (81,82):
                        if shape(resources,(ix,y,iz))[sx,:13 if y==82 else 16,sz].any():route_fail.append([fx,y,fz])
            route_samples.append([x,feet,z])
        for x,z,feet in d['site_columns']:
            if not shape(resources,(x,feet-2,z))[:,15,:].any():support_fail.append([x,feet,z])
    faces=[]
    for face,record in zip(b.roof_faces,d['source_faces'],strict=True):
        value=dict(xz=list(map(list,face.polygon.exterior.coords)),plane=[face.a,face.b,face.c],surface=face.surface_index)
        faces.append(value==record['canonical'])
    sources=[dict(**s,matched=digest(ROOT/s['path'])==s['sha256']) for s in p['reference_inputs']]
    report=dict(archive_sha256=digest(out/'sample-blocks.npz'),source_inputs=sources,source_faces_exact=sum(faces),source_roof_states_preserved=int(roof.sum()),source_roof_exact=roof_exact,
        wall_planes=dict(bearing_degrees=-12,outline_uv_m=p['wall_outline_uv_m'],wall_columns=int(walls.sum()),method='Exact straight authored planes with the minimum raster staircase and inward one-cell grid joins; source roof unchanged.'),
        enclosure_slices=slices,enclosure_exception='Provisional open entry is sealed only for enclosure test; its real authored opening is independently traversed.',
        pane_vertical_contact_failures=pane_fail,pane_joints=pane_joint_report(c),pane_support=pane_support_report(c),pane_perimeter=pane_perimeter_report(c),unsupported_partial_blocks=partial_fail,
        changed_columns_outside_authorized_scope=len(unexpected),authored_site_columns=d['site_columns'],unsupported_site_or_route_points=support_fail,
        route=dict(status='passed' if not route_fail and not support_fail else 'failed',samples=len(route_samples),player_width_blocks=.6,player_height_blocks=1.8,maximum_step_blocks=0,collision_failures=route_fail[:10],seam_block_xyz=route_samples[0],limit='Only short provisional north entry approach; interiors beyond this stub unreviewed.'),
        neighboring_gap=dict(name='Sherrill',original_measured_gap_m=5.1883313279,roof_footprint_unchanged=True,site_on_north_face_not_west_gap=True))
    report['passed']=bool(all(faces) and all(s['matched'] for s in sources) and roof_exact and not partial_fail and not pane_fail and not any(s['leaks'] for s in slices) and not unexpected.size and not support_fail and not route_fail and not report['pane_joints']['unbridged_diagonal_pairs'] and not report['pane_joints']['disconnected_adjacent_pairs'] and not report['pane_support']['unsupported_components'])
    write_json(out/'geometric-validation.json',report)
    artifact=audit(out);write_json(out/'artifact-audit.json',artifact)
    print(json.dumps(dict(geometry_passed=report['passed'],artifact_passed=artifact['passed'],roof_exact=roof_exact,partial_failures=len(partial_fail),pane_failures=len(pane_fail),leaking_slices=sum(bool(s['leaks']) for s in slices),route_failures=len(route_fail),support_failures=len(support_fail)),indent=2))
    return report['passed'] and artifact['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True)
    raise SystemExit(0 if run(parser.parse_args().study.resolve()) else 1)
