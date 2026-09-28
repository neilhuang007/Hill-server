"""Reproducible final-archive Davy geometry, original models and exact delta."""
import importlib.util
import itertools
import json
import math
from collections import Counter, deque
from pathlib import Path
import sys
import zipfile
import argparse

import numpy as np
from scipy.ndimage import binary_propagation, distance_transform_cdt

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--study', type=Path, required=True)
parser.add_argument('--preceding', type=Path)
args = parser.parse_args()
OUT = args.study.resolve()
ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent/'scripts/campus_roof_geometry.py').exists())
sys.path.insert(0, str(ROOT/'scripts'))
from build_hill_chapel_sample import Canvas, ROLES
from campus_reference_details import ReferenceExterior
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from campus_export_parity import read_archive, compare_world
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

p = json.loads((OUT/'profile.json').read_text(encoding='utf-8'))
m = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
d = json.loads((OUT/'detail-register.json').read_text(encoding='utf-8'))
bb = m['source_roof']['world_bounds_blocks']
archive_sha = digest(OUT/'sample-blocks.npz')


def load(path):
    c = Canvas(bb[0], bb[1], bb[2]-bb[0], bb[3]-bb[1], 2)
    with np.load(path, allow_pickle=False) as a:
        q = a['coords']; index = (q[:,1]+64, q[:,2]-c.z_min, q[:,0]-c.x_min)
        c.data[index], c.roles[index] = a['state_ids'], a['role_ids']
        c.palette = json.loads(str(a['palette_json']))
    return c


c = load(OUT/'sample-blocks.npz')
base_path = (args.preceding.resolve()/'sample-blocks.npz' if args.preceding else
             ROOT/'runtime/campus-reconstruction/davy-v8-2x/sample-blocks.npz')
old = load(base_path)
spec = importlib.util.spec_from_file_location('frozen_davy', OUT/'detail-generator.py')
detail = importlib.util.module_from_spec(spec); spec.loader.exec_module(detail); detail.ROOT = ROOT
assert digest(OUT/'detail-generator.py') == m['detail_generator']['sha256']
b = load_measured_building(parent_id=p['parent_id'])
original = rasterize_roof(b, [v/2 for v in bb], .5)
f = ReferenceExterior(c, p, original, -25)
f.r = detail.prepare_roof(original, f, p)
body = detail.SOURCE['body']

# Canonical state dictionaries allow comparison across independent palettes.
canonical = sorted({json.dumps(s, sort_keys=True) for a in (old,c) for s in a.palette})
indices = {v:i for i,v in enumerate(canonical)}
normalized = [np.array([indices[json.dumps(s, sort_keys=True)] for s in a.palette])[a.data] for a in (old,c)]
different = (normalized[0] != normalized[1]) | (old.roles != c.roles)
changes = []
for iy,iz,ix in np.argwhere(different):
    before, after = old.palette[old.data[iy,iz,ix]], c.palette[c.data[iy,iz,ix]]
    changes.append({'xyz':[int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min],
                    'before':before,'after':after,'roles':[ROLES[old.roles[iy,iz,ix]],ROLES[c.roles[iy,iz,ix]]]})
write_json(OUT/'preceding-to-revision-delta.json', {
    'baseline_archive':str(base_path), 'baseline_sha256':digest(base_path), 'archive_sha256':archive_sha,
    'baseline_occupied':int(np.count_nonzero(old.data)), 'revision_occupied':int(np.count_nonzero(c.data)),
    'state_or_role_changes':len(changes),
    'state_name_counts':dict(Counter(v['before']['Name']+' -> '+v['after']['Name'] for v in changes)),
    'role_counts':dict(Counter(' -> '.join(v['roles']) for v in changes)), 'changes':changes,
    'scope':'Source roof restoration, removal of unsupported mirrored west apertures, bounded east/north frames, existing open porch/terrace rails; exact unchanged terrain outside these operations.'})

baseline_path = ROOT/'runtime/campus-reconstruction/davy-v6-2x/sample-blocks.npz'
baseline = load(baseline_path)
baseline_states = {json.dumps(s,sort_keys=True):i for i,s in enumerate(baseline.palette)}
new_to_baseline = np.array([baseline_states.get(json.dumps(s,sort_keys=True),-1) for s in c.palette])
baseline_different = (baseline.data != new_to_baseline[c.data]) | (baseline.roles != c.roles)
baseline_changes = []
for iy,iz,ix in np.argwhere(baseline_different):
    baseline_changes.append({'xyz':[int(ix)+c.x_min,int(iy)-64,int(iz)+c.z_min],
        'before':baseline.palette[baseline.data[iy,iz,ix]],'after':c.palette[c.data[iy,iz,ix]],
        'roles':[ROLES[baseline.roles[iy,iz,ix]],ROLES[c.roles[iy,iz,ix]]]})
write_json(OUT/'baseline-to-revision-delta.json',{
    'baseline_archive':str(baseline_path),'baseline_sha256':digest(baseline_path),
    'archive_sha256':archive_sha,'baseline_occupied':int(np.count_nonzero(baseline.data)),
    'revision_occupied':int(np.count_nonzero(c.data)),'state_or_role_changes':len(baseline_changes),
    'changes':baseline_changes})
del baseline,baseline_different,baseline_changes

retained = original.footprint_mask & np.isin(original.face_indices, detail.KEEP)
unchanged = retained & (f.r.face_indices < 1_000_000)
face_records = []
for control in detail.SOURCE['packet']['source_face_controls']+detail.SOURCE['packet']['nonbuilding_low_face_controls']:
    selected = original.footprint_mask & (original.face_indices == control['id'])
    same = selected & unchanged
    face_records.append({**control, 'source_raster_columns':int(selected.sum()),
                         'unchanged_source_columns':int(same.sum()),
                         'overlaid_columns':int((selected & (f.r.face_indices >= 1_000_000)).sum()),
                         'unchanged_max_height_delta_m':float(np.max(abs(f.r.heights[same]-original.heights[same]))) if same.any() else None,
                         'source_raster_height_range_m':[float(original.heights[selected].min()),float(original.heights[selected].max())]})
source_checks = {'source_sha256':b.source_sha256, 'original_columns':int(original.footprint_mask.sum()),
                 'retained_elevated_columns':int(retained.sum()), 'excluded_low_columns':1499,
                 'prepared_shell_columns':int(f.r.footprint_mask.sum()),
                 'outside_original_footprint_columns':int((f.r.footprint_mask & ~original.footprint_mask).sum()),
                 'unchanged_elevated_columns':int(unchanged.sum()),
                 'unchanged_height_max_delta_m':float(abs(f.r.heights[unchanged]-original.heights[unchanged]).max()),
                 'unchanged_gradient_x_max_delta':float(abs(f.r.gradient_x[unchanged]-original.gradient_x[unchanged]).max()),
                 'unchanged_gradient_z_max_delta':float(abs(f.r.gradient_z[unchanged]-original.gradient_z[unchanged]).max()),
                 'source_face_records':face_records, 'bounded_overlays':list(f.r.authored_roof_patches)}

# Reconstruct v8's stored overlay operation on the now independently verified
# source geometry. Its historical packet hash is known stale; no source bytes
# or source checks from that revision are reused as an authority.
prior_dir = ROOT/'runtime/campus-reconstruction/davy-v8-2x'
prior_manifest = json.loads((prior_dir/'manifest.json').read_text(encoding='utf-8'))
assert digest(prior_dir/'detail-generator.py') == prior_manifest['detail_generator']['sha256']
spec = importlib.util.spec_from_file_location('prior_davy_overlay', prior_dir/'detail-generator.py')
prior_detail = importlib.util.module_from_spec(spec); spec.loader.exec_module(prior_detail)
prior_detail._source = lambda profile: (b,detail.SOURCE['packet'])
prior_f = ReferenceExterior(c,p,original,-25)
prior = prior_detail.prepare_roof(original,prior_f,p)
east_patches = np.zeros_like(original.footprint_mask)
for center in detail.CENTRES:
    east_patches |= f.local_mask((114.25,center-1.05,116.75,center+1.05))
outside = original.footprint_mask & ~east_patches
source_checks['preceding_v8_comparison'] = {
    'method':'Verified original source geometry and byte-bound frozen v8 overlay code; prior stale provenance assertion bypassed only for reconstruction after current source verification.',
    'prior_generator_sha256':digest(prior_dir/'detail-generator.py'),
    'outside_east_patches_height_changes':int(np.count_nonzero(f.r.heights[outside]!=prior.heights[outside])),
    'outside_east_patches_gradient_x_changes':int(np.count_nonzero(f.r.gradient_x[outside]!=prior.gradient_x[outside])),
    'outside_east_patches_gradient_z_changes':int(np.count_nonzero(f.r.gradient_z[outside]!=prior.gradient_z[outside])),
    'roof_mask_changes':int(np.count_nonzero(f.r.footprint_mask!=prior.footprint_mask)),
    'height_changed_columns':int(np.count_nonzero(f.r.heights[original.footprint_mask]!=prior.heights[original.footprint_mask])),
}
assert all(source_checks['preceding_v8_comparison'][k]==0 for k in (
    'outside_east_patches_height_changes','outside_east_patches_gradient_x_changes',
    'outside_east_patches_gradient_z_changes','roof_mask_changes'))
fronts = d['straight_wall_rows']
plane_errors = [abs(float(f.u[z-c.z_min,x-c.x_min])-116.60) for x,z in fronts]
steps = [b[0]-a[0] for a,b in zip(fronts,fronts[1:])]
straight_check = {'constant_u_m':116.60,'axis_degrees':9,'row_count':len(fronts),
                  'maximum_cell_center_plane_error_m':max(plane_errors),
                  'row_x_steps':dict(Counter(map(str,steps))),
                  'all_steps_monotonic_and_at_most_one_cell':all(v in (0,-1) for v in steps),
                  'all_front_cells_within_original_footprint':all(original.footprint_mask[z-c.z_min,x-c.x_min] for x,z in fronts),
                  'wall_only_added_columns':int(np.count_nonzero(body & ~detail.SOURCE['measured_body'])),
                  'wall_only_removed_columns':int(np.count_nonzero(detail.SOURCE['measured_body'] & ~body)),
                  'minimum_corner_rule':'Exactly one inward masonry turn per diagonal step; source roof caps retain their measured outline.'}
assert max(plane_errors)<=.30 and straight_check['all_steps_monotonic_and_at_most_one_cell']
if d.get('west_wall_rows'):
    from shapely.geometry import Point, shape
    county_path = ROOT/'runtime/campus-reconstruction/campus-plan-v1/footprints-local-metres.json'
    county_feature = next(v for v in json.loads(county_path.read_text(encoding='utf-8'))['features']
                          if v['properties']['id']==p['parent_id'])
    county = shape(county_feature['geometry'])
    west = d['west_wall_rows']
    points = [Point((x+.5)/2,(z+.5)/2) for x,z in west]
    distances = [q.distance(b.footprint) for q in points]
    west_steps = [bb[0]-aa[0] for aa,bb in zip(west,west[1:])]
    straight_check['west'] = {
        'constant_u_m':103.35,'basis':'Median U103.3416 of measured west contour rows; below-eave wall regularization authorized after native v9.',
        'row_count':len(west),'maximum_cell_center_plane_error_m':max(abs(float(f.u[z-c.z_min,x-c.x_min])-103.35) for x,z in west),
        'row_x_steps':dict(Counter(map(str,west_steps))),
        'all_steps_monotonic_and_at_most_one_cell':all(v in (0,-1) for v in west_steps),
        'county_footprint_path':str(county_path),'county_file_sha256':digest(county_path),
        'county_parent_id':p['parent_id'],'outside_original_county_footprint_cell_centers':sum(not county.covers(q) for q in points),
        'outside_noisy_roofer_ground_union_cell_centers':sum(v>0 for v in distances),
        'maximum_distance_outside_noisy_roofer_ground_union_m':max(distances),
        'roof_exception':'No change to retained roof heights, gradients, cap physical tops, or roof mask; wall-only contour regularization inside original county footprint.',
    }
    assert straight_check['west']['outside_original_county_footprint_cell_centers']==0
    assert straight_check['west']['all_steps_monotonic_and_at_most_one_cell']

jar = Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
assert digest(jar) == 'b1b3158572666445eff01e82fad8c7de2e4953db6d354f311730d77a8359d0b0'
shape_cache = {}
occupied_cache = {}


def boxes(resources, state, q):
    if state['Name'] == 'minecraft:air':
        return []
    key = json.dumps(state, sort_keys=True)
    if key not in shape_cache:
        block = BlockState(state['Name'], state.get('Properties',{})); result = []
        for app in applications_for_state(resources.blockstate(block.name), block.properties, q):
            for e in elements_for_state(resources.model(app.model), block):
                corners = np.array([rotate_model_point(v,app) for v in itertools.product(*zip(e['from'],e['to']))])
                result.append((np.rint(corners.min(0)).astype(int), np.rint(corners.max(0)).astype(int)))
        shape_cache[key] = result
    return shape_cache[key]


def occupied(resources, q):
    state_id = c.get(*q)
    if state_id in occupied_cache:
        return occupied_cache[state_id]
    result = np.zeros((16,16,16), dtype=bool)
    for low, high in boxes(resources,c.palette[c.get(*q)],q):
        x,y,z=low;xx,yy,zz=high
        result[max(0,x):min(16,xx),max(0,y):min(16,yy),max(0,z):min(16,zz)] = True
    occupied_cache[state_id] = result
    return result


roof_points, roof_tops, roof_failures, pane_contacts, cap_backings, post_contacts = set(),[],[],[],[],[]
roof_classifications, door_contacts = [], []
with VanillaResources(jar) as resources:
    for x,z,iz,ix in f.each_column(f.r.footprint_mask):
        expected_half = math.floor((f.r.heights[iz,ix]-25)*4+.5)
        top = (expected_half-1)//2
        cap = occupied(resources,(x,top,z))
        actual_top = top+(np.nonzero(cap)[1].max()+1)/16 if cap.any() else None
        roof_tops.append({'xz':[x,z], 'expected_y':expected_half/2, 'actual_y':actual_top})
        for y in range(top-5,top+1):
            if ROLES[c.roles[y+64,iz,ix]] not in ('roof','trim'):continue
            for low,high in boxes(resources,c.palette[c.get(x,y,z)],(x,y,z)):
                for dx,dy,dz in itertools.product((0,1),repeat=3):
                    center=np.array((dx,dy,dz))*8+4
                    if np.all(center >= low) and np.all(center < high):
                        roof_points.add((2*x+dx,2*y+dy,2*z+dz))
    positions={(x,z) for x,z,_,_ in f.each_column(f.r.footprint_mask)}
    pair_count=0
    for x,z in sorted(positions):
        for dx,dz in ((1,0),(0,1)):
            if (x+dx,z+dz) not in positions:continue
            pair_count+=1
            if dx:
                contact=sum((2*x+1,y,zz) in roof_points and (2*x+2,y,zz) in roof_points for y in range(120,160) for zz in (2*z,2*z+1))
            else:
                contact=sum((xx,y,2*z+1) in roof_points and (xx,y,2*z+2) in roof_points for y in range(120,160) for xx in (2*x,2*x+1))
            if not contact:
                first_top = detail._roof_y(f,z-c.z_min,x-c.x_min)
                second_top = detail._roof_y(f,z+dz-c.z_min,x+dx-c.x_min)
                physical = 0
                for yy in range(min(first_top,second_top)-1,max(first_top,second_top)+1):
                    first = occupied(resources,(x,yy,z))
                    second = occupied(resources,(x+dx,yy,z+dz))
                    physical += int((first[15,:,:]&second[0,:,:]).sum() if dx else (first[:,:,15]&second[:,:,0]).sum())
                record = {'columns':[[x,z],[x+dx,z+dz]],'original_model_contact_patches':physical,
                          'classification':'roof_to_masonry_junction' if physical else 'unclosed_roof_junction'}
                roof_classifications.append(record)
                if not physical: roof_failures.append(record)
    for opening in d['openings']:
        low,high=opening['low_y'],opening['high_y_exclusive']
        inward=opening['inward']
        if opening['door']:
            for x,z in opening['pane_columns']:
                for y in (low-1,low,low+1,low+2):
                    first=occupied(resources,(x,y,z)); second=occupied(resources,(x,y+1,z))
                    door_contacts.append({'lower':[x,y,z],'upper':[x,y+1,z],
                                          'contact_patches':int((first[:,15,:]&second[:,0,:]).sum())})
        for x,z in opening['pane_columns']:
            for y in range(low,high):
                if not c.palette[c.get(x,y,z)]['Name'].endswith('_pane'):continue
                shape=occupied(resources,(x,y,z))
                for dy,face,otherface in ((-1,0,15),(1,15,0)):
                    neighbor=occupied(resources,(x,y+dy,z))
                    contact=int((shape[:,face,:]&neighbor[:,otherface,:]).sum())
                    pane_contacts.append({'pane':[x,y,z],'neighbor':[x,y+dy,z],'contact_patches':contact})
        for x,z in opening['front_columns']:
            for y in (low-1,high):
                state=c.palette[c.get(x,y,z)]
                if not state['Name'].endswith('_slab'):continue
                back=(x+inward[0],y,z+inward[1])
                if opening['door']:
                    choices=[q for q in opening['pane_columns'] if (q[1]==z if inward[0] else q[0]==x)]
                    q=min(choices,key=lambda q:abs(q[0]-x)+abs(q[1]-z));back=(q[0],y,q[1])
                full=bool(occupied(resources,back).all())
                cap_backings.append({'front_cap':[x,y,z],'full_inward_backing':list(back),'is_full':full})
    for post in d['posts']:
        x,low,z=post['xyz_bottom'];high=post['contact_y']
        contacts=[int((occupied(resources,(x,y,z))[:,15,:]&occupied(resources,(x,y+1,z))[:,0,:]).sum()) for y in range(low-1,high)]
        post_contacts.append({**post,'all_positive_vertical_contacts':all(contacts),'contact_patches':contacts})

    # Whole wall cross sections inspect original occupied shapes, not names
    # or pane graph closure. Exterior cannot reach the deep main-body air.
    izs,ixs=np.nonzero(body);lx,hx=int(ixs.min())-3,int(ixs.max())+4;lz,hz=int(izs.min())-3,int(izs.max())+4
    wall_slices=[]
    architecture=[ROLES.index(v) for v in ('facade','roof','trim','window','door','floor')]
    for y in range(62,72):
        interior=distance_transform_cdt(body & ((y+1)/2+25 < f.r.heights-.4),metric='taxicab')>=4
        for half in (0,1):
            layer=np.zeros(((hz-lz)*16,(hx-lx)*16),dtype=bool)
            for iz,ix in np.argwhere(np.isin(c.roles[y+64,lz:hz,lx:hx],architecture)):
                iz,ix=int(iz)+lz,int(ix)+lx;q=(ix+c.x_min,y,iz+c.z_min)
                for low,high in boxes(resources,c.palette[c.get(*q)],q):
                    if not low[1] <= half*8+4 < high[1]:continue
                    x0,z0=max(0,low[0]),max(0,low[2]);x1,z1=min(16,high[0]),min(16,high[2])
                    layer[(iz-lz)*16+z0:(iz-lz)*16+z1,(ix-lx)*16+x0:(ix-lx)*16+x1]=True
            seeds=np.zeros_like(layer);seeds[0,:]=seeds[-1,:]=seeds[:,0]=seeds[:,-1]=True
            exterior=binary_propagation(seeds,mask=~layer)
            checked,leaked=0,[]
            for iz,ix in np.argwhere(interior):
                xx,zz=(ix-lx)*16+8,(iz-lz)*16+8
                if layer[zz,xx]:continue
                checked+=1
                if exterior[zz,xx]:leaked.append([int(ix)+c.x_min,y,int(iz)+c.z_min])
            record={'y':y,'half':half,'interior_air_points_checked':checked,'exterior_reachable_points':len(leaked),'examples':leaked[:4]}
            if leaked and y in (62,64,67,71):
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
            wall_slices.append(record)

rail_positions={(x,y,z) for run in d['rails'] for x,z in run['columns'] for y in range(run['low_y'],run['high_y_exclusive'])}
rail_failures=[]
for q in sorted(rail_positions):
    state=c.palette[c.get(*q)]
    if state['Name']!='minecraft:pale_oak_fence':rail_failures.append({'xyz':q,'reason':'wrong material'})
    x,y,z=q
    for direction,opposite,dx,dz in (('east','west',1,0),('west','east',-1,0),('north','south',0,-1),('south','north',0,1)):
        neighbor=(x+dx,y,z+dz)
        if neighbor in rail_positions and (state.get('Properties',{}).get(direction)!='true' or c.palette[c.get(*neighbor)].get('Properties',{}).get(opposite)!='true'):
            rail_failures.append({'xyz':q,'neighbor':neighbor,'reason':'nonreciprocal'})
roof_top_failures=[v for v in roof_tops if v['expected_y']!=v['actual_y']]
report={'archive_sha256':archive_sha,'source_controls':source_checks,
        'straight_wall_control':straight_check,
        'original_26_1_2_jar_sha256':digest(jar),'block_count':int(np.count_nonzero(c.data)),
        'source_roof_physical_tops_checked':len(roof_tops),'physical_top_failures':roof_top_failures,
        'roof_adjacent_pairs_checked':pair_count,'roof_pairs_without_occupied_contact':roof_failures,
        'roof_to_masonry_junction_classifications':roof_classifications,
        'door_transom_contacts':door_contacts,
        'pane_vertical_contacts_checked':len(pane_contacts),'pane_contact_failures':[v for v in pane_contacts if not v['contact_patches']],
        'cap_backings':cap_backings,'post_contacts':post_contacts,
        'whole_wall_slices':wall_slices,'rails_checked':len(rail_positions),'rail_failures':rail_failures,
        'materials_original_textures_only':not m.get('resource_pack') and not (OUT/'world/resources.zip').exists(),
        'material_violations':m['material_violations'],'clipped_writes':m['clipped_writes'],
        'provisional_faces':p['uncertainties']}
write_json(OUT/'geometric-validation.json',report)
parity,errors,_,_=compare_world(read_archive(OUT/'sample-blocks.npz'),OUT/'world')
write_json(OUT/'export-parity.json',{'archive_sha256':archive_sha,**parity,'errors':errors})
with zipfile.ZipFile(OUT/'davy-house-vanilla-2x.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((OUT/'world').rglob('*')):
        if path.is_file():archive.write(path,Path('Davy House')/path.relative_to(OUT/'world'))
print(json.dumps({'delta_cells':len(changes),'unchanged_source':source_checks['unchanged_elevated_columns'],
                  'roof_top_failures':roof_top_failures,'roof_contact_failures':roof_failures,
                  'pane_contact_failures':report['pane_contact_failures'],
                  'failed_wall_slices':[v for v in wall_slices if v['exterior_reachable_points']],
                  'rail_failures':rail_failures,'export_errors':errors},indent=2))
assert not roof_top_failures and not roof_failures and not rail_failures and not errors
assert all(v['is_full'] for v in cap_backings) and all(v['all_positive_vertical_contacts'] for v in post_contacts)
assert not any(v['exterior_reachable_points'] for v in wall_slices)
assert not report['pane_contact_failures']
assert all(v['contact_patches'] for v in door_contacts)
