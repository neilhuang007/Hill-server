"""Inspect the frozen Tuck/Rink export against source and vanilla shapes."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation, binary_propagation, distance_transform_cdt

from audit_hill_block_artifact import audit
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    out=parser.parse_args().study.resolve()
    p=json.loads((out/'profile.json').read_text(encoding='utf-8'))
    m=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    d=json.loads((out/'detail-register.json').read_text(encoding='utf-8'))
    bb=m['source_roof']['world_bounds_blocks']
    c=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as archive:
        q=archive['coords'];ix=q[:,0]-c.x_min;iz=q[:,2]-c.z_min;iy=q[:,1]-c.y_min
        state_ids=archive['state_ids'];role_ids=archive['role_ids']
        c.data[iy,iz,ix]=state_ids;c.roles[iy,iz,ix]=role_ids
        c.palette=json.loads(str(archive['palette_json']))
    refinement=None
    if p.get('refinement_baseline') and not p.get('corner_bridge_baseline'):
        baseline=p['refinement_baseline'];baseline_path=ROOT/baseline['path']
        assert digest(baseline_path)==baseline['sha256']
        with np.load(baseline_path,allow_pickle=False) as previous:
            same_coordinates=bool(np.array_equal(previous['coords'],q))
            assert same_coordinates, 'Texture refinement changed occupied coordinates'
            old_palette=json.loads(str(previous['palette_json']))
            keys={json.dumps(state,sort_keys=True):i for i,state in enumerate(c.palette)}
            lookup=np.array([keys.get(json.dumps(state,sort_keys=True),65535) for state in old_palette])
            old_ids=previous['state_ids'];old_roles=previous['role_ids']
            changed=np.flatnonzero((lookup[old_ids]!=state_ids)|(old_roles!=role_ids))
            backing={tuple(cell['xyz']):cell for cell in d['east_gable_backing_retints']}
            stair_count=0;backing_count=0;failures=[]
            for i in changed:
                xyz=tuple(map(int,q[i]));before=old_palette[old_ids[i]];after=c.palette[state_ids[i]]
                if (before['Name']=='minecraft:stone_brick_stairs'
                    and after['Name']=='minecraft:smooth_quartz_stairs'
                    and before.get('Properties')==after.get('Properties')
                    and old_roles[i]==role_ids[i]==ROLES.index('roof')):
                    stair_count+=1
                elif (xyz in backing and before==backing[xyz]['before_state']
                    and after==backing[xyz]['after_state'] and xyz[1]<backing[xyz]['cap_y']
                    and old_roles[i]==ROLES.index('roof') and role_ids[i]==ROLES.index('facade')):
                    backing_count+=1
                else:
                    failures.append(dict(xyz=xyz,before=before,after=after))
            refinement=dict(baseline=baseline,same_occupied_coordinates=same_coordinates,
                changed_cells=len(changed),same_shape_stair_retints=stair_count,
                exposed_east_backing_retints=backing_count,unexpected_changes=failures,
                passed=bool(not failures and stair_count==1456 and backing_count==len(backing)))
    if p.get('corner_bridge_baseline'):
        baseline=p['corner_bridge_baseline'];baseline_path=ROOT/baseline['path']
        assert digest(baseline_path)==baseline['sha256']
        with np.load(baseline_path,allow_pickle=False) as previous:
            old=previous['coords'];ox=old[:,0]-c.x_min;oz=old[:,2]-c.z_min;oy=old[:,1]-c.y_min
            palette=json.loads(str(previous['palette_json']))
            keys={json.dumps(state,sort_keys=True):i for i,state in enumerate(c.palette)}
            lookup=np.array([keys.get(json.dumps(state,sort_keys=True),65535) for state in palette])
            changed=(lookup[previous['state_ids']]!=c.data[oy,oz,ox])|(previous['role_ids']!=c.roles[oy,oz,ox])
            occupied=np.zeros(c.data.shape,dtype=bool);occupied[oy,oz,ox]=True
            added=q[~occupied[iy,iz,ix]]
            registered={tuple(cell['xyz']) for cell in d['wall_corner_bridges']}
            actual={tuple(map(int,cell)) for cell in added}
            bridge_checks=[]
            for cell in d['wall_corner_bridges']:
                position=tuple(cell['xyz']);neighbors=cell['attached_wall_cells']
                bridge_checks.append(c.palette[c.get(*position)]['Name']=='minecraft:red_terracotta'
                    and len(neighbors)==2 and all(sum(abs(a-b) for a,b in zip(position,n))==1
                    and n[1]==position[1] and c.palette[c.get(*n)]['Name'] in {
                        'minecraft:red_terracotta','minecraft:smooth_quartz','minecraft:white_concrete','minecraft:mud_bricks'} for n in neighbors))
            refinement=dict(kind='inward_cardinal_wall_bridges',baseline=baseline,
                original_occupied_cells=len(old),original_cells_removed_or_changed=int(changed.sum()),
                added_cells=len(added),registered_bridge_cells=len(registered),
                additions_match_registered_bridges=actual==registered,
                two_positive_area_cardinal_contacts_checked=len(bridge_checks),
                passed=bool(not changed.any() and actual==registered and bridge_checks and all(bridge_checks)))
    b=load_measured_building(parent_id=p['parent_id'])
    r=rasterize_roof(b,[v/2 for v in bb],.5)
    if refinement is not None:
        backing_checks=[]
        for cell in d['east_gable_backing_retints']:
            x,y,z=cell['xyz'];iz=z-c.z_min;ix=x-c.x_min
            angle=np.deg2rad(9);u=(x+.5)/2*np.cos(angle)+(z+.5)/2*np.sin(angle)
            v=-(x+.5)/2*np.sin(angle)+(z+.5)/2*np.cos(angle)
            cap=(math_floor((r.heights[iz,ix]-25)*4+.5)-1)//2
            exposed=not r.footprint_mask[iz,ix+1] or not r.footprint_mask[iz+1,ix]
            backing_checks.append(bool(u>=52.75 and -167.6<=v<=-132.4 and exposed
                and y<cap and cell['cap_y']==cap and c.palette[c.get(x,y,z)]['Name']=='minecraft:red_terracotta'))
        refinement['east_backing_bounds_and_cap_checks']=len(backing_checks)
        refinement['passed']=bool(refinement['passed'] and backing_checks and all(backing_checks))
    exceptions={tuple(q):entry for entry in p.get('source_surface_exceptions',[]) for q in entry['world_xyz_cells']}
    for entry in p.get('source_surface_exceptions',[]):
        authority=entry['authority'];assert digest(ROOT/authority['path'])==authority['sha256']
        authorized=json.loads((ROOT/authority['path']).read_text(encoding='utf-8'))['source_face3_disposition']['supported_threshold_exception']
        assert entry['world_xyz_cells']==authorized['world_xyz_cells']
    source=[]
    for control,face in zip(d['source_faces'],b.roof_faces,strict=True):
        canonical=dict(xz=list(map(list,face.polygon.exterior.coords)),
            holes=[list(map(list,ring.coords)) for ring in face.polygon.interiors],
            plane=[face.a,face.b,face.c],surface=face.surface_index)
        sha=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        source.append(control['canonical']==canonical and control['sha256']==sha)
    with np.load(out/'source-roof-raster.npz',allow_pickle=False) as frozen:
        raster_checks={name:bool(np.array_equal(frozen[name],value,equal_nan=True)) for name,value in
            [('mask',r.footprint_mask),('heights',r.heights),('face_indices',r.face_indices),
             ('gradient_x',r.gradient_x),('gradient_z',r.gradient_z)]}
    jar=Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    cache={}
    def state_shape(resources,state,q):
        key=json.dumps(state,sort_keys=True)
        if key not in cache:
            grid=np.zeros((16,16,16),dtype=bool)
            if state['Name']!='minecraft:air':
                bs=BlockState(state['Name'],state.get('Properties',{}))
                for app in applications_for_state(resources.blockstate(bs.name),bs.properties,q):
                    for e in elements_for_state(resources.model(app.model),bs):
                        corners=np.array([rotate_model_point(v,app) for v in itertools.product(*zip(e['from'],e['to']))])
                        lo=np.maximum(0,np.rint(corners.min(0)).astype(int));hi=np.minimum(16,np.rint(corners.max(0)).astype(int))
                        grid[lo[0]:hi[0],lo[1]:hi[1],lo[2]:hi[2]]=True
            cache[key]=grid
        return cache[key]
    def shape(resources,q):return state_shape(resources,c.palette[c.get(*q)],q)
    panes=[];partial=[];roof=[];buried=[];retints=[];slices=[];canopy=[];threshold=[];louver=[];exception_checks=[]
    with VanillaResources(jar) as resources:
        for x,y,z,before,after in d['roof_material_cells']:
            current=c.palette[c.get(x,y,z)];old=dict(Name=before)
            if current.get('Properties'):old['Properties']=current['Properties']
            if (x,y,z) in exceptions:
                old['Properties']={'type':'bottom','waterlogged':'false'}
                previous=state_shape(resources,old,(x,y,z));now=shape(resources,(x,y,z))
                exception_checks.append(dict(xyz=[x,y,z],source_face=int(r.face_indices[z-c.z_min,x-c.x_min]),
                    original_slab_volume_retained=bool(np.all(now[previous])),
                    source_top_delta_m=.25,after_state=current,
                    passed=bool(current['Name']=='minecraft:bricks' and now.all() and np.all(now[previous]))))
                continue
            if not np.array_equal(state_shape(resources,old,(x,y,z)),shape(resources,(x,y,z))):
                retints.append(dict(xyz=[x,y,z],before=before,after=current))
        ids=[i for i,s in enumerate(c.palette) if s['Name'].endswith('_pane')]
        for iy,iz,ix in np.argwhere(np.isin(c.data,ids)):
            x,y,z=int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min
            a=shape(resources,(x,y,z))
            for dy,side,other in ((-1,0,15),(1,15,0)):
                contact=int((a[:,side,:]&shape(resources,(x,y+dy,z))[:,other,:]).sum())
                panes.append(dict(xyz=[x,y,z],direction=dy,contact=contact))
        for iz,ix in np.argwhere(r.footprint_mask):
            x,z=int(ix)+c.x_min,int(iz)+c.z_min
            half=math_floor((r.heights[iz,ix]-25)*4+.5);y=(half-1)//2
            role=ROLES[c.roles[y+64,iz,ix]]
            if role in ('terrain','pavement'):
                buried.append(dict(xz=[x,z],source_face=int(r.face_indices[iz,ix]),role=role))
                continue
            a=shape(resources,(x,y,z));actual=y+(np.nonzero(a)[1].max()+1)/16 if a.any() else None
            if (x,y,z) in exceptions:
                if int(r.face_indices[iz,ix])==3 and half/2==67.5 and actual==68.0:continue
            if actual!=half/2:roof.append(dict(xz=[x,z],face=int(r.face_indices[iz,ix]),expected=half/2,actual=actual,role=role))
        architecture=[ROLES.index(v) for v in ('facade','roof','trim','window','door','floor','railing')]
        for iy,iz,ix in np.argwhere(np.isin(c.roles,architecture)):
            state=c.palette[c.data[iy,iz,ix]]
            if not state['Name'].endswith(('_slab','_stairs')):continue
            x,y,z=int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min
            a=shape(resources,(x,y,z));bottom=int((a[:,0,:]&shape(resources,(x,y-1,z))[:,15,:]).sum());side=0
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                n=shape(resources,(x+dx,y,z+dz))
                side+=int((a[15,:,:]&n[0,:,:]).sum()) if dx==1 else 0
                side+=int((a[0,:,:]&n[15,:,:]).sum()) if dx==-1 else 0
                side+=int((a[:,:,15]&n[:,:,0]).sum()) if dz==1 else 0
                side+=int((a[:,:,0]&n[:,:,15]).sum()) if dz==-1 else 0
            partial.append(dict(xyz=[x,y,z],bottom=bottom,side=side))
        # Prove the slab canopy reaches occupied masonry/roof through a
        # cardinal graph, not merely that each floating slab touches a slab.
        candidates={tuple(q) for q in d['entry']['canopy_cells']};pending=set(candidates)
        while pending:
            stack=[pending.pop()];component=[];anchored=False
            while stack:
                q=stack.pop();component.append(q);x,y,z=q;a=shape(resources,q)
                if (a[:,0,:]&shape(resources,(x,y-1,z))[:,15,:]).any():anchored=True
                for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                    n=(x+dx,y,z+dz)
                    if n in pending:pending.remove(n);stack.append(n)
                    elif n not in candidates and shape(resources,n).any():anchored=True
            canopy.append(dict(cells=len(component),anchored=anchored))
        # The photographed louver must remain attached to the gable wall.
        louver_set={tuple(q) for q in d['louver']['cells']}
        for x,y,z in louver_set:
            neighbors=[(x+dx,y+dy,z+dz) for dx,dy,dz in
                ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))]
            louver.append(dict(xyz=[x,y,z],attached=any(c.get(*q) for q in neighbors if q not in louver_set)))
        # Check actual occupied headroom on the outside approach. Fixed scaled
        # glass leaves are explicitly not claimed as a traversable doorway.
        for x,cap,z,top in d['sidewalk']:
            a=np.deg2rad(9);u=(x+.5)/2*np.cos(a)+(z+.5)/2*np.sin(a)
            v=-(x+.5)/2*np.sin(a)+(z+.5)/2*np.cos(a)
            if not (43.2<=u<=47.8 and -170<=v<=-169):continue
            occupied_above=[]
            for y in range(int(np.floor(top)),int(np.ceil(top))+4):
                voxel=shape(resources,(x,y,z))
                first=max(0,int(round((top-y)*16)))
                if first<16 and voxel[:,first:,:].any():occupied_above.append(y)
            threshold.append(dict(xz=[x,z],surface_y=top,headroom_blockers=occupied_above))
        izs,ixs=np.nonzero(r.footprint_mask);lx,hx=int(ixs.min())-3,int(ixs.max())+4;lz,hz=int(izs.min())-3,int(izs.max())+4
        for y in (62,66,67,68,70,72,74,76,78):
            interior=distance_transform_cdt(r.footprint_mask & (r.heights>(y+1)/2+25+.5),metric='taxicab')>=4
            for sub in (4,12):
                layer=np.zeros(((hz-lz)*16,(hx-lx)*16),dtype=bool)
                for iz,ix in np.argwhere(c.data[y+64,lz:hz,lx:hx]!=0):
                    iz,ix=int(iz)+lz,int(ix)+lx;a=shape(resources,(ix+c.x_min,y,iz+c.z_min))
                    layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=a[:,sub,:].T
                seed=np.zeros_like(layer);seed[0,:]=seed[-1,:]=seed[:,0]=seed[:,-1]=True
                exterior=binary_propagation(seed,mask=~layer);leaks=[];checked=0
                for iz,ix in np.argwhere(interior):
                    xx,zz=(ix-lx)*16+8,(iz-lz)*16+8
                    if layer[zz,xx]:continue
                    checked+=1
                    if exterior[zz,xx]:leaks.append([int(ix)+c.x_min,y,int(iz)+c.z_min])
                slices.append(dict(y=y,subheight=sub,checked=checked,leaks=len(leaks),examples=leaks[:8]))
    terrain=ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz'
    h,ids,meta=terrain_arrays(terrain,2,[v/2 for v in bb]);ground=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    build_ground(ground,h,ids,meta['materials'],-25);smooth_exposed_measured_pavement(ground,h,ground.ground_heights,vertical_offset=-25)
    canonical={json.dumps(s,sort_keys=True):i for i,s in enumerate(c.palette)}
    lookup=np.array([canonical.get(json.dumps(s,sort_keys=True),65535) for s in ground.palette],dtype=np.uint16)
    roles=[ROLES.index('terrain'),ROLES.index('pavement')]
    changed=(((c.data!=lookup[ground.data])|(c.roles!=ground.roles)) & (np.isin(c.roles,roles)|np.isin(ground.roles,roles))).any(0)
    zz,xx=np.indices(r.heights.shape);angle=np.deg2rad(9);x=(xx+c.x_min+.5)/2;z=(zz+c.z_min+.5)/2
    u=x*np.cos(angle)+z*np.sin(angle);v=-x*np.sin(angle)+z*np.cos(angle)
    allowed=binary_dilation(r.footprint_mask,iterations=2)|((u>=-13.5)&(u<=55.5)&(v>=-171.3)&(v<=-164))
    outside=changed&~allowed
    architecture_columns=np.isin(c.roles,[ROLES.index(q) for q in ('facade','roof','trim','window','door','railing')]).any(0)
    gap_controls={
        'annan_corridor_core':(u>=54.25)&(u<=60.75)&(v>=-166.0)&(v<=-134.5),
        'mercer_passage_core':(u>=-11.5)&(u<=53.0)&(v>=-129.75)&(v<=-122.5)}
    gaps={name:dict(architecture_columns=int((mask&architecture_columns).sum()),
                   changed_ground_columns=int((mask&changed).sum())) for name,mask in gap_controls.items()}
    joints=pane_joint_report(c);perimeter=pane_perimeter_report(c)
    result=dict(archive_sha256=digest(out/'sample-blocks.npz'),source_face_fingerprints_matched=sum(source),source_raster_checks=raster_checks,
        material_refinement=refinement,
        roof_top_failures=roof,buried_source_roof_columns=buried,roof_material_shape_changes=retints,
        authorized_source_surface_exceptions=exception_checks,
        pane_vertical_contacts_checked=len(panes),pane_contact_failures=[q for q in panes if not q['contact']],
        pane_support=pane_support_report(c),pane_joints=joints,pane_perimeter=perimeter,
        partial_blocks_checked=len(partial),unsupported_partial_blocks=[q for q in partial if not q['bottom'] and not q['side']],
        canopy_components=canopy,louver_attachment=louver,threshold_approach=threshold,
        protected_neighbor_gaps=gaps,whole_wall_slices=slices,north_plane=d['north_plane'],
        changed_ground_columns=int(changed.sum()),ground_changes_outside_scope=int(outside.sum()),
        source_vs_inferred_limits=p['uncertainties'])
    result['passed']=bool(all(source) and all(raster_checks.values()) and not roof and not retints
        and len(exception_checks)==len(exceptions) and all(q['passed'] and q['source_face']==3 for q in exception_checks)
        and not result['pane_contact_failures'] and not result['unsupported_partial_blocks']
        and all(q['anchored'] for q in canopy) and not any(q['leaks'] for q in slices)
        and all(q['attached'] for q in louver) and threshold and not any(q['headroom_blockers'] for q in threshold)
        and not any(q['architecture_columns'] or q['changed_ground_columns'] for q in gaps.values())
        and not outside.any() and not joints['unbridged_diagonal_pairs'] and not joints['disconnected_adjacent_pairs']
        and not perimeter['fewer_than_two_horizontal_joins'] and not perimeter['vertical_air_or_reversed_slab_contacts']
        and (refinement is None or refinement['passed']))
    write_json(out/'geometric-validation.json',result)
    native=None
    if (out/'native-review.json').exists():
        review=json.loads((out/'native-review.json').read_text(encoding='utf-8'))
        if review.get('native_report'):native=ROOT/review['native_report']
    artifact=audit(out,native)
    print(json.dumps(dict(passed=result['passed'] and artifact['passed'],roof_failures=roof[:15],retint_changes=retints[:5],
        pane_failures=result['pane_contact_failures'][:10],partial_failures=result['unsupported_partial_blocks'][:10],
        leaks=[q for q in slices if q['leaks']],ground_outside=int(outside.sum()),export_errors=artifact['errors']),indent=2))
    return 0 if result['passed'] and artifact['passed'] else 1


def math_floor(value):return int(np.floor(value))


if __name__=='__main__':raise SystemExit(main())
