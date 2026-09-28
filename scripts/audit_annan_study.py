"""Audit Annan's exact roof repair, wall closure, contacts, site and export."""

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_propagation, distance_transform_cdt
from shapely import contains_xy
from shapely.ops import unary_union

from audit_hill_block_artifact import audit
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

ROOT=Path(__file__).resolve().parents[1]


def run(out):
    p=json.loads((out/'profile.json').read_text(encoding='utf-8'))
    m=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    d=json.loads((out/'detail-register.json').read_text(encoding='utf-8'))
    bb=m['source_roof']['world_bounds_blocks']
    c=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as data:
        coords=data['coords'];ix=coords[:,0]-c.x_min;iz=coords[:,2]-c.z_min;iy=coords[:,1]+64
        c.data[iy,iz,ix]=data['state_ids'];c.roles[iy,iz,ix]=data['role_ids']
        c.palette=json.loads(str(data['palette_json']))
    refinement=None
    if p.get('refinement_baseline'):
        baseline=ROOT/p['refinement_baseline']['path']
        assert digest(baseline)==p['refinement_baseline']['sha256']
        with np.load(baseline,allow_pickle=False) as previous:
            q=previous['coords'];old_palette=json.loads(str(previous['palette_json']))
            lookup={json.dumps(s,sort_keys=True):i for i,s in enumerate(c.palette)}
            mapping=np.array([lookup.get(json.dumps(s,sort_keys=True),65535) for s in old_palette])
            old_roles=previous['role_ids'];old_states=mapping[previous['state_ids']]
            ox,oy,oz=q[:,0]-c.x_min,q[:,1]+64,q[:,2]-c.z_min
            changed=np.flatnonzero((c.data[oy,oz,ox]!=old_states)|(c.roles[oy,oz,ox]!=old_roles))
            registered={tuple(k['xyz']):k for k in d['backing_retints']}
            failures=[]
            for i in changed:
                xyz=tuple(map(int,q[i]));before=old_palette[int(previous['state_ids'][i])]
                after=c.palette[c.get(*xyz)]
                record=registered.get(xyz)
                if (record is None or before!=record['before'] or after!=record['after']
                    or old_roles[i]!=ROLES.index('roof') or c.roles[oy[i],oz[i],ox[i]]!=ROLES.index('facade')):
                    failures.append(dict(xyz=list(xyz),before=before,after=after))
            occupied=np.zeros(c.data.shape,bool);occupied[oy,oz,ox]=True
            added=np.argwhere((c.data!=0)&~occupied)
            actual_added={(int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min) for iy,iz,ix in added}
            declared_added={tuple(k['xyz']) for k in d['south_wall_completion']}
            brick_additions=all(c.palette[c.get(*q)]['Name']=='minecraft:bricks' for q in actual_added)
            refinement=dict(baseline=p['refinement_baseline'],original_cells=len(q),
                missing_original_cells=int((c.data[oy,oz,ox]==0).sum()),changed_original_cells=len(changed),
                declared_backing_retints=len(registered),unexpected_changes=failures,
                added_cells=len(actual_added),additions_match_register=actual_added==declared_added,
                additions_all_bricks=brick_additions,
                passed=bool(not failures and len(changed)==len(registered) and actual_added==declared_added and brick_additions))
    b=load_measured_building(parent_id=p['parent_id'])
    r=rasterize_roof(b,[v/2 for v in bb],.5)
    source=[]
    for face,record in zip(b.roof_faces,d['source_faces'],strict=True):
        value=dict(xz=list(map(list,face.polygon.exterior.coords)),
            holes=[list(map(list,q.coords)) for q in face.polygon.interiors],
            plane=[face.a,face.b,face.c],surface=face.surface_index)
        sha=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        source.append(value==record['canonical'] and sha==record['sha256'])
    with np.load(out/'source-roof-raster.npz',allow_pickle=False) as frozen:
        source_arrays={name:bool(np.array_equal(frozen[name],value,equal_nan=True)) for name,value in
            [('mask',r.footprint_mask),('heights',r.heights),('face_indices',r.face_indices),('gradient_x',r.gradient_x),('gradient_z',r.gradient_z)]}
    zz,xx=np.indices(r.heights.shape);x=(xx+c.x_min+.5)/2;z=(zz+c.z_min+.5)/2
    angle=np.deg2rad(9);u=x*np.cos(angle)+z*np.sin(angle);v=-x*np.sin(angle)+z*np.cos(angle)
    omitted=[2,7,8,9,10,12,13,14,15,16,18,19]
    union=unary_union([b.roof_faces[i].polygon for i in omitted])
    patch=contains_xy(union,x,z) & r.footprint_mask
    plane=b.roof_faces[20];expected=r.heights.copy();expected[patch]=(plane.a*x+plane.b*z+plane.c)[patch]
    with np.load(out/'authored-roof-raster.npz',allow_pickle=False) as frozen:
        roof_values=frozen['heights'].copy()
        retained=~patch
        patch_report=dict(authority=p['reference_addenda'][0],columns=int(patch.sum()),area_m2=union.area,
            nonexcluded_face_ids=[i for i in range(21) if i not in omitted],
            exact_plane_every_patch_column=bool(np.array_equal(frozen['heights'][patch],expected[patch])),
            unchanged_other_heights=bool(np.array_equal(frozen['heights'][retained],r.heights[retained],equal_nan=True)),
            unchanged_footprint=bool(np.array_equal(frozen['mask'],r.footprint_mask)),
            patch_face_ids=bool((frozen['face_indices'][patch]==1_000_000).all()),
            original_other_face_ids=bool(np.array_equal(frozen['face_indices'][retained],r.face_indices[retained])),
            exact_patch_gradients=bool((frozen['gradient_x'][patch]==plane.a).all() and (frozen['gradient_z'][patch]==plane.b).all()),
            unchanged_other_gradients=bool(np.array_equal(frozen['gradient_x'][retained],r.gradient_x[retained],equal_nan=True)
                and np.array_equal(frozen['gradient_z'][retained],r.gradient_z[retained],equal_nan=True)))
    jar=Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    cache={}
    def state_shape(resources,state,q):
        key=json.dumps(state,sort_keys=True)
        if key not in cache:
            grid=np.zeros((16,16,16),bool)
            if state['Name']!='minecraft:air':
                bs=BlockState(state['Name'],state.get('Properties',{}))
                for app in applications_for_state(resources.blockstate(bs.name),bs.properties,q):
                    for e in elements_for_state(resources.model(app.model),bs):
                        corners=np.array([rotate_model_point(q,app) for q in itertools.product(*zip(e['from'],e['to']))])
                        lo=np.maximum(0,np.rint(corners.min(0)).astype(int));hi=np.minimum(16,np.rint(corners.max(0)).astype(int))
                        grid[lo[0]:hi[0],lo[1]:hi[1],lo[2]:hi[2]]=True
            cache[key]=grid
        return cache[key]
    def shape(resources,q):return state_shape(resources,c.palette[c.get(*q)],q)
    def side_contact(a,n,dx,dz):
        if dx==1:return int((a[15,:,:]&n[0,:,:]).sum())
        if dx==-1:return int((a[0,:,:]&n[15,:,:]).sum())
        if dz==1:return int((a[:,:,15]&n[:,:,0]).sum())
        return int((a[:,:,0]&n[:,:,15]).sum())
    roofs=[];buried=[];retints=[];panes=[];partial=[];slices=[];trim_components=[]
    with VanillaResources(jar) as resources:
        for record in d['roof_retints']:
            q=tuple(record['xyz'])
            if not np.array_equal(state_shape(resources,record['before'],q),shape(resources,q)):
                retints.append(record)
        for iz,ix in np.argwhere(r.footprint_mask):
            x,z=int(ix)+c.x_min,int(iz)+c.z_min
            half=math.floor((roof_values[iz,ix]-25)*4+.5);y=(half-1)//2
            role=ROLES[c.roles[y+64,iz,ix]]
            if role in ('terrain','pavement'):
                buried.append([x,z,int(r.face_indices[iz,ix])]);continue
            a=shape(resources,(x,y,z));actual=y+(np.nonzero(a)[1].max()+1)/16 if a.any() else None
            if actual!=half/2:roofs.append(dict(xz=[x,z],expected=half/2,actual=actual,role=role))
        paneids=[i for i,s in enumerate(c.palette) if s['Name'].endswith('_pane')]
        for iy,iz,ix in np.argwhere(np.isin(c.data,paneids)):
            x,y,z=int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min;a=shape(resources,(x,y,z))
            for dy,face,opposite in ((-1,0,15),(1,15,0)):
                panes.append(dict(xyz=[x,y,z],dy=dy,contact=int((a[:,face,:]&shape(resources,(x,y+dy,z))[:,opposite,:]).sum())))
        architecture=[ROLES.index(q) for q in ('roof','facade','trim','window','floor')]
        for iy,iz,ix in np.argwhere(np.isin(c.roles,architecture)):
            state=c.palette[c.data[iy,iz,ix]]
            if not state['Name'].endswith(('_slab','_stairs')):continue
            x,y,z=int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min;a=shape(resources,(x,y,z))
            bottom=int((a[:,0,:]&shape(resources,(x,y-1,z))[:,15,:]).sum())
            side=sum(side_contact(a,shape(resources,(x+dx,y,z+dz)),dx,dz) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)))
            if not bottom and not side:partial.append([x,y,z])
        for name in ('division','canopy'):
            allcells={tuple(q) for q in d[name]};remaining=set(allcells)
            while remaining:
                stack=[remaining.pop()];component=[];anchored=False
                while stack:
                    q=stack.pop();component.append(q);x,y,z=q;a=shape(resources,q)
                    for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                        n=(x+dx,y,z+dz)
                        if n in remaining:remaining.remove(n);stack.append(n)
                        elif n not in allcells and side_contact(a,shape(resources,n),dx,dz):anchored=True
                    if (a[:,0,:]&shape(resources,(x,y-1,z))[:,15,:]).any():anchored=True
                trim_components.append(dict(name=name,cells=len(component),anchored=anchored))
        izs,ixs=np.nonzero(r.footprint_mask)
        lx,hx=int(ixs.min())-3,int(ixs.max())+4;lz,hz=int(izs.min())-3,int(izs.max())+4
        for y in range(61,83):
            interior=distance_transform_cdt(r.footprint_mask & (roof_values>(y+1)/2+25+.5),metric='taxicab')>=3
            for sub in (4,12):
                layer=np.zeros(((hz-lz)*16,(hx-lx)*16),bool)
                for iz,ix in np.argwhere(c.data[y+64,lz:hz,lx:hx]!=0):
                    iz,ix=int(iz)+lz,int(ix)+lx;a=shape(resources,(ix+c.x_min,y,iz+c.z_min))
                    layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=a[:,sub,:].T
                seed=np.zeros_like(layer);seed[0,:]=seed[-1,:]=seed[:,0]=seed[:,-1]=True
                outside=binary_propagation(seed,mask=~layer);leaks=[];checked=0
                for iz,ix in np.argwhere(interior):
                    xi,zi=(ix-lx)*16+8,(iz-lz)*16+8
                    if layer[zi,xi]:continue
                    checked+=1
                    if outside[zi,xi]:leaks.append([int(ix)+c.x_min,y,int(iz)+c.z_min])
                slices.append(dict(y=y,subheight=sub,checked=checked,leaks=len(leaks),examples=leaks[:5]))
    h,ids,meta=terrain_arrays(ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz',2,[q/2 for q in bb])
    ground=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    build_ground(ground,h,ids,meta['materials'],-25)
    smooth_exposed_measured_pavement(ground,h,ground.ground_heights,vertical_offset=-25)
    palette={json.dumps(s,sort_keys=True):i for i,s in enumerate(c.palette)}
    lookup=np.array([palette.get(json.dumps(s,sort_keys=True),65535) for s in ground.palette])
    terrainroles=[ROLES.index('terrain'),ROLES.index('pavement')]
    groundchange=(((c.data!=lookup[ground.data])|(c.roles!=ground.roles)) & (np.isin(c.roles,terrainroles)|np.isin(ground.roles,terrainroles))).any(0)
    archcolumns=np.isin(c.roles,[ROLES.index(q) for q in ('facade','roof','window','trim','door','floor')]).any(0)
    cores={'tuck':(u>54)&(u<60.6)&(v>-167)&(v<-134.5),
        'sweeney':(u>61.8)&(u<91.8)&(v>-133)&(v<-131),
        'davy':(u>93)&(u<102)&(v>-144)&(v<-134.4)}
    gaps={name:dict(architecture_columns=int((mask&archcolumns).sum()),changed_ground_columns=int((mask&groundchange).sum())) for name,mask in cores.items()}
    from assemble_hill_campus_studies import prepare_component
    component=prepare_component(out,ROOT/'runtime/campus-reconstruction/component-cache',2,-25,.5)
    owned=component.mask
    bridges=[]
    for cell in d['wall_corner_bridges']:
        q=cell['xyz'];x,y,z=q
        bridges.append(bool(r.footprint_mask[z-c.z_min,x-c.x_min] and c.get(x,y,z) and
            all(sum(abs(a-b) for a,b in zip(q,n))==1 and c.get(*n) for n in cell['attached_wall_cells'])))
    excessive_patch=[]
    for iz,ix in np.argwhere(patch):
        top=math.ceil((roof_values[iz,ix]-25)*2)
        occupied=np.flatnonzero(np.isin(c.roles[top+64:,iz,ix],[ROLES.index(q) for q in ('roof','facade','trim','window')]))
        if occupied.size:excessive_patch.append([int(ix)+c.x_min,int(iz)+c.z_min,int(occupied.size)])
    joints=pane_joint_report(c);perimeter=pane_perimeter_report(c);support=pane_support_report(c)
    report=dict(archive_sha256=digest(out/'sample-blocks.npz'),source_faces_matched=sum(source),source_arrays=source_arrays,
        roof_repair=patch_report,roof_top_failures=roofs,buried_source_columns=buried,retint_shape_failures=retints,
        architecture_above_replacement_plane=excessive_patch,
        pane_vertical_contacts_checked=len(panes),pane_contact_failures=[q for q in panes if not q['contact']],
        pane_joints=joints,pane_perimeter=perimeter,pane_support=support,unsupported_partial_blocks=partial,
        attached_trim_components=trim_components,whole_wall_slices=slices,bridges_checked=len(bridges),bridges_valid=all(bridges),
        protected_gap_cores=gaps,changed_ground_columns=int(groundchange.sum()),
        changed_ground_columns_outside_footprint=int((groundchange&~r.footprint_mask).sum()),
        changed_ground_columns_outside_ownership=int((groundchange&~owned).sum()),
        glazing=d['glazing'],source_disposition=p['reference_addenda'][0],refinement=refinement)
    report['passed']=bool(all(source) and all(source_arrays.values()) and all(q for q in patch_report.values() if isinstance(q,bool))
        and not roofs and not retints and not excessive_patch and not report['pane_contact_failures'] and not partial
        and not joints['unbridged_diagonal_pairs'] and not joints['disconnected_adjacent_pairs']
        and not support['unsupported_components'] and all(q['anchored'] for q in trim_components)
        and not any(q['leaks'] for q in slices) and all(bridges)
        and all(not q['architecture_columns'] and not q['changed_ground_columns'] for q in gaps.values())
        and not report['changed_ground_columns_outside_footprint'] and not report['changed_ground_columns_outside_ownership']
        and (refinement is None or refinement['passed']))
    write_json(out/'geometric-validation.json',report)
    artifact=audit(out);write_json(out/'artifact-audit.json',artifact)
    print(json.dumps(dict(geometry_passed=report['passed'],artifact_passed=artifact['passed'],
        roof_failures=len(roofs),retint_shape_failures=len(retints),pane_contact_failures=len(report['pane_contact_failures']),
        unsupported_partial_blocks=len(partial),leaking_wall_slices=[q for q in slices if q['leaks']],
        unanchored_trim=[q for q in trim_components if not q['anchored']],gaps=gaps),indent=2))
    return report['passed'] and artifact['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True)
    raise SystemExit(0 if run(parser.parse_args().study.resolve()) else 1)
