"""Independently inspect the frozen CFTA archive, shapes and source controls."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from collections import Counter, deque

import numpy as np
from scipy.ndimage import binary_propagation, distance_transform_cdt, binary_dilation

from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report
from audit_hill_block_artifact import audit
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    args=parser.parse_args();out=args.study.resolve()
    p=json.loads((out/'profile.json').read_text(encoding='utf-8'))
    m=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    d=json.loads((out/'detail-register.json').read_text(encoding='utf-8'))
    bb=m['source_roof']['world_bounds_blocks']
    c=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as a:
        q=a['coords'];ix=q[:,0]-c.x_min;iz=q[:,2]-c.z_min;iy=q[:,1]-c.y_min
        c.data[iy,iz,ix]=a['state_ids'];c.roles[iy,iz,ix]=a['role_ids']
        c.palette=json.loads(str(a['palette_json']))
    b=load_measured_building(parent_id=p['parent_id'])
    fingerprints=[]
    for control,face in zip(d['source_faces'],b.roof_faces,strict=True):
        payload=dict(xz=list(map(list,face.polygon.exterior.coords)),
                     holes=[list(map(list,ring.coords)) for ring in face.polygon.interiors],
                     plane=[face.a,face.b,face.c],surface=face.surface_index)
        sha=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        fingerprints.append(sha==control['sha256'] and payload==control['canonical'])
    r=rasterize_roof(b,[v/2 for v in bb],.5)
    with np.load(out/'source-roof-raster.npz',allow_pickle=False) as a:
        source=np.asarray(a['mask']);body=np.asarray(a['prepared_mask'])
        heights=np.asarray(a['prepared_heights'])
        source_checks=dict(source_sha256=b.source_sha256,
            retained_columns=int(source.sum()),added_enclosure_columns=int((body&~source).sum()),
            original_roof_mask_matches=bool(np.array_equal(source,r.footprint_mask)),
            retained_height_changes=int(np.count_nonzero(a['prepared_heights'][source]!=r.heights[source])),
            frozen_source_height_changes=int(np.count_nonzero(a['heights'][source]!=r.heights[source])),
            source_face_id_changes=int(np.count_nonzero(a['face_indices'][source]!=r.face_indices[source])),
            frozen_gradient_x_changes=int(np.count_nonzero(a['gradient_x'][source]!=r.gradient_x[source])),
            frozen_gradient_z_changes=int(np.count_nonzero(a['gradient_z'][source]!=r.gradient_z[source])),
            source_face_fingerprints_matched=sum(fingerprints),
            source_exceptions=d['roof_exceptions'])
    jar=Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    cache={}
    def state_shape(resources,s,q):
        key=json.dumps(s,sort_keys=True)
        if key not in cache:
            grid=np.zeros((16,16,16),dtype=bool)
            if s['Name']!='minecraft:air':
                bs=BlockState(s['Name'],s.get('Properties',{}))
                for app in applications_for_state(resources.blockstate(bs.name),bs.properties,q):
                    for e in elements_for_state(resources.model(app.model),bs):
                        corners=np.array([rotate_model_point(v,app) for v in itertools.product(*zip(e['from'],e['to']))])
                        lo=np.rint(corners.min(0)).astype(int);hi=np.rint(corners.max(0)).astype(int)
                        x,y,z=np.maximum(lo,0);xx,yy,zz=np.minimum(hi,16)
                        grid[x:xx,y:yy,z:zz]=True
            cache[key]=grid
        return cache[key]
    def occupied(resources,q):
        return state_shape(resources,c.palette[c.get(*q)],q)
    panes=[];partial=[];roof=[];rails=[];supports=[];slices=[];buried=[]
    retint_checks=[];box_contacts=[]
    ids=[i for i,s in enumerate(c.palette) if s['Name'].endswith('_pane')]
    with VanillaResources(jar) as resources:
        recolor=d.get('roof_material_only_changes',{})
        for x,y,z,before,after in recolor.get('roof_field_cells',[])+recolor.get('source_perimeter_cells',[]):
            q=(x,y,z);current=c.palette[c.get(*q)]
            old=dict(Name=before)
            if current.get('Properties'):old['Properties']=current['Properties']
            same=bool(np.array_equal(state_shape(resources,old,q),occupied(resources,q)))
            retint_checks.append(dict(xyz=list(q),before=before,after=current['Name'],same_occupied_model=same))
        for box in d.get('interpreted_rooftop_boxes',[]):
            for x,y,z in box['occupied_cells']:
                contact=int((occupied(resources,(x,y,z))[:,0,:]&occupied(resources,(x,y-1,z))[:,15,:]).sum())
                box_contacts.append(dict(xyz=[x,y,z],full_footprint_contact_patches=contact))
        for iy,iz,ix in np.argwhere(np.isin(c.data,ids)):
            x,y,z=int(ix)+c.x_min,int(iy)+c.y_min,int(iz)+c.z_min
            current=occupied(resources,(x,y,z))
            for dy,face,other in ((-1,0,15),(1,15,0)):
                contact=int((current[:,face,:]&occupied(resources,(x,y+dy,z))[:,other,:]).sum())
                panes.append(dict(xyz=[x,y,z],dy=dy,contact_patches=contact))
        for iz,ix in np.argwhere(body):
            x,z=int(ix)+c.x_min,int(iz)+c.z_min
            half=int(np.floor((heights[iz,ix]-25)*4+.5));y=(half-1)//2
            shape=occupied(resources,(x,y,z))
            # Low source fragments can be buried below measured terrain. They
            # are retained in provenance and are not excavated to expose a cap.
            role=ROLES[c.roles[y+64,iz,ix]]
            if role in ('terrain','pavement'):
                buried.append(dict(xz=[x,z],role=role,expected_y=half/2))
                continue
            actual=y+(np.nonzero(shape)[1].max()+1)/16 if shape.any() else None
            roof.append(dict(xz=[x,z],expected_y=half/2,actual_y=actual))
        architecture=[ROLES.index(v) for v in ('facade','roof','trim','window','door','floor','railing')]
        for iy,iz,ix in np.argwhere(np.isin(c.roles,architecture)):
            state=c.palette[c.data[iy,iz,ix]]
            if not state['Name'].endswith(('_slab','_stairs')):continue
            x,y,z=int(ix)+c.x_min,int(iy)+c.y_min,int(iz)+c.z_min
            shape=occupied(resources,(x,y,z))
            below=occupied(resources,(x,y-1,z))
            contact=int((shape[:,0,:]&below[:,15,:]).sum())
            # Roof/terrace ledges can be side-supported by connected full
            # construction; inspect occupied shapes rather than block names.
            side=0
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                n=occupied(resources,(x+dx,y,z+dz))
                side+=int((shape[15,:,:]&n[0,:,:]).sum()) if dx==1 else 0
                side+=int((shape[0,:,:]&n[15,:,:]).sum()) if dx==-1 else 0
                side+=int((shape[:,:,15]&n[:,:,0]).sum()) if dz==1 else 0
                side+=int((shape[:,:,0]&n[:,:,15]).sum()) if dz==-1 else 0
            partial.append(dict(xyz=[x,y,z],state=state,bottom_contact_patches=contact,side_contact_patches=side))
        for rail in d['rails']:
            for x,y,z in rail['bases']:
                count=int((occupied(resources,(x,y,z))[:,0,:]&occupied(resources,(x,y-1,z))[:,15,:]).sum())
                rails.append(dict(name=rail['name'],xyz=[x,y,z],support_contact_patches=count))
        for x,y,z,high in d['screen']['full_height_support_columns']:
            values=[int((occupied(resources,(x,q,z))[:,15,:]&occupied(resources,(x,q+1,z))[:,0,:]).sum()) for q in range(y,high-1)]
            supports.append(dict(xyz=[x,y,z],high_y=high,all_vertical_contacts=all(values)))
        # Flood actual sixteenth-block cross-sections. Screen openings are
        # deliberately outdoors; only deep enclosed-roof interiors are targets.
        izs,ixs=np.nonzero(body);lx,hx=int(ixs.min())-2,int(ixs.max())+3;lz,hz=int(izs.min())-2,int(izs.max())+3
        for y in (67,72,76,80,84,88,92,100,108):
            interior=distance_transform_cdt(body & (heights>(y+1)/2+25+.5),metric='taxicab')>=4
            for subheight in (4,12):
                layer=np.zeros(((hz-lz)*16,(hx-lx)*16),dtype=bool)
                for iz,ix in np.argwhere(c.data[y+64,lz:hz,lx:hx]!=0):
                    iz,ix=int(iz)+lz,int(ix)+lx
                    shape=occupied(resources,(ix+c.x_min,y,iz+c.z_min))
                    layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=shape[:,subheight,:].T
                seeds=np.zeros_like(layer);seeds[0,:]=seeds[-1,:]=seeds[:,0]=seeds[:,-1]=True
                exterior=binary_propagation(seeds,mask=~layer)
                checked=0;leaked=[]
                for iz,ix in np.argwhere(interior):
                    xx,zz=(ix-lx)*16+8,(iz-lz)*16+8
                    if layer[zz,xx]:continue
                    checked+=1
                    if exterior[zz,xx]:leaked.append([int(ix)+c.x_min,y,int(iz)+c.z_min])
                record=dict(y=y,subheight=subheight,interior_air_points_checked=checked,
                                   exterior_reachable_points=len(leaked),examples=leaked[:8])
                if leaked and y==72 and subheight==4:
                    sx,_,sz=leaked[0];start=((sz-c.z_min-lz)*16+8,(sx-c.x_min-lx)*16+8)
                    queue=deque([start]);parents={start:None};end=None
                    while queue:
                        zz,xx=queue.popleft()
                        if zz in (0,layer.shape[0]-1) or xx in (0,layer.shape[1]-1):end=(zz,xx);break
                        for q in ((zz+1,xx),(zz-1,xx),(zz,xx+1),(zz,xx-1)):
                            if not layer[q] and q not in parents:parents[q]=(zz,xx);queue.append(q)
                    route=[]
                    while end is not None:
                        zz,xx=end;q=[xx//16+lx+c.x_min,y,zz//16+lz+c.z_min]
                        if not route or route[-1]!=q:route.append(q)
                        end=parents[end]
                    record['escape_route_cells']=route[::-1]
                slices.append(record)
    angle=np.deg2rad(9)
    errors=[abs(-(x+.5)/2*np.sin(angle)+(z+.5)/2*np.cos(angle)+171.9) for x,z in d['screen']['columns']]
    # Recreate only the measured ground pipeline, then bound every changed
    # ground column to the retained building or its declared front controls.
    terrain=ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz'
    h,ids,meta=terrain_arrays(terrain,2,[v/2 for v in bb])
    ground=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    build_ground(ground,h,ids,meta['materials'],-25)
    smooth_exposed_measured_pavement(ground,h,ground.ground_heights,vertical_offset=-25)
    canonical={json.dumps(s,sort_keys=True):i for i,s in enumerate(c.palette)}
    lookup=np.array([canonical.get(json.dumps(s,sort_keys=True),65535) for s in ground.palette],dtype=np.uint16)
    ground_roles=[ROLES.index('terrain'),ROLES.index('pavement')]
    changes=((c.data!=lookup[ground.data])|(c.roles!=ground.roles)) & (np.isin(c.roles,ground_roles)|np.isin(ground.roles,ground_roles))
    changed_columns=changes.any(axis=0)
    zz,xx=np.indices(body.shape);x=(xx+c.x_min+.5)/2;z=(zz+c.z_min+.5)/2
    u=x*np.cos(angle)+z*np.sin(angle);v=-x*np.sin(angle)+z*np.cos(angle)
    allowed=binary_dilation(body,iterations=2)
    for u0,v0,u1,v1 in ((126,-172.8,194.5,-171.0),(126.5,-172,158.5,-167.9),
                         (157.3,-173,194.5,-166.3),(132.4,-175.4,182.3,-172.2)):
        allowed|=(u>=u0)&(u<=u1)&(v>=v0)&(v<=v1)
    outside_ground=changed_columns&~allowed
    terrain_checks=dict(measured_terrain_sha256=digest(terrain),
        changed_ground_columns=int(changed_columns.sum()),
        changed_columns_outside_declared_building_and_front_controls=int(outside_ground.sum()),
        outside_examples=[[int(ix)+c.x_min,int(iz)+c.z_min] for iz,ix in np.argwhere(outside_ground)[:12]],
        scope='Original building/apron with one-metre raster margin, separate screen, source stairs/terrace and connected front balcony only')
    del ground,changes
    report=dict(archive_sha256=digest(out/'sample-blocks.npz'),source_controls=source_checks,
        original_jar_sha256=digest(jar),source_roof_physical_tops_checked=len(roof),
        buried_source_roof_columns=buried,
        roof_top_failures=[a for a in roof if a['actual_y']!=a['expected_y']],
        roof_material_only_cells_checked=len(retint_checks),
        roof_material_geometry_changes=[v for v in retint_checks if not v['same_occupied_model']],
        roof_box_columns_checked=len(box_contacts),
        unsupported_roof_box_columns=[v for v in box_contacts if v['full_footprint_contact_patches']!=256],
        screen_straight_plane=dict(maximum_centre_error_m=max(errors),
            note='Main cells are nearest-cell samples; one inward corner return connects every regular diagonal step'),
        pane_support=pane_support_report(c),pane_joints=pane_joint_report(c),pane_perimeter=pane_perimeter_report(c),
        pane_vertical_contacts_checked=len(panes),pane_contact_failures=[a for a in panes if not a['contact_patches']],
        partial_blocks_checked=len(partial),unsupported_partial_blocks=[a for a in partial if not a['bottom_contact_patches'] and not a['side_contact_patches']],
        railing_bases_checked=len(rails),unsupported_railing_bases=[a for a in rails if not a['support_contact_patches']],
        screen_support_columns=len(supports),failed_screen_supports=[a for a in supports if not a['all_vertical_contacts']],
        whole_wall_slices=slices,source_vs_inferred_limits=p['uncertainties'])
    report['terrain_scope']=terrain_checks
    report['passed']=bool(source_checks['original_roof_mask_matches'] and not source_checks['retained_height_changes']
        and not report['roof_top_failures'] and not report['pane_contact_failures']
        and not report['roof_material_geometry_changes'] and not report['unsupported_roof_box_columns']
        and not report['unsupported_partial_blocks'] and not report['unsupported_railing_bases']
        and not report['failed_screen_supports'] and not any(v['exterior_reachable_points'] for v in slices)
        and all(fingerprints) and not outside_ground.any()
        and not report['pane_joints']['unbridged_diagonal_pairs'] and not report['pane_joints']['disconnected_adjacent_pairs'])
    write_json(out/'geometric-validation.json',report)
    native_report=None
    if (out/'native-review.json').exists():
        review=json.loads((out/'native-review.json').read_text(encoding='utf-8'))
        if review.get('native_report'):native_report=ROOT/review['native_report']
    artifact=audit(out,native_report)
    print(json.dumps(dict(passed=report['passed'] and artifact['passed'],roof_failures=len(report['roof_top_failures']),
        pane_failures=len(report['pane_contact_failures']),unsupported_partial_blocks=len(report['unsupported_partial_blocks']),
        rail_failures=len(report['unsupported_railing_bases']),wall_slices=[v for v in slices if v['exterior_reachable_points']],
        export_errors=artifact['errors']),indent=2))
    return 0 if report['passed'] and artifact['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
