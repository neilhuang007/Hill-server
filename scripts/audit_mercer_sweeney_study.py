"""Check a frozen Mercer/Day/Sweeney export against geometry and vanilla shapes."""

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation, binary_propagation, distance_transform_cdt, label

from audit_hill_block_artifact import audit
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

ROOT = Path(__file__).resolve().parents[1]


def audit_material_only_revision(out, profile, details):
    """Bind the narrow roof correction to the already reviewed v5 geometry."""
    controls = profile.get('material_only_revision')
    if not controls:
        return None
    previous = ROOT/controls['geometry_study']
    original = ROOT/controls['restoration_study']
    assert digest(previous/'sample-blocks.npz') == controls['geometry_archive_sha256']
    assert digest(original/'sample-blocks.npz') == controls['restoration_archive_sha256']
    archives = []
    for directory in (original, previous, out):
        with np.load(directory/'sample-blocks.npz', allow_pickle=False) as a:
            archives.append({key:a[key] for key in ('coords', 'state_ids', 'role_ids', 'palette_json')})
    old, before, after = archives
    coordinates_equal = bool(np.array_equal(before['coords'], after['coords']))
    roles_equal = bool(np.array_equal(before['role_ids'], after['role_ids']))
    palettes = [json.loads(str(a['palette_json'])) for a in archives]
    keys = sorted({json.dumps(s, sort_keys=True) for palette in palettes for s in palette})
    ids = {key:index for index, key in enumerate(keys)}
    canonical = [np.array([ids[json.dumps(s, sort_keys=True)] for s in palette])[a['state_ids']]
                 for palette, a in zip(palettes, archives)]
    differences = np.flatnonzero(canonical[1] != canonical[2]) if coordinates_equal else []
    lower = np.minimum(old['coords'].min(0), after['coords'].min(0))
    widths = np.maximum(old['coords'].max(0), after['coords'].max(0))-lower+1
    def coordinate_keys(coords):
        q = (coords-lower).astype(np.int64)
        return (q[:,1]*widths[2]+q[:,2])*widths[0]+q[:,0]
    old_keys = coordinate_keys(old['coords'])
    order = np.argsort(old_keys)
    selected_keys = coordinate_keys(after['coords'][differences])
    indices = np.searchsorted(old_keys[order], selected_keys)
    old_lookup = {tuple(map(int, q)):int(canonical[0][order[index]])
                  for q,index,key in zip(after['coords'][differences], indices, selected_keys)
                  if index < len(order) and old_keys[order[index]] == key}
    changes, failures = [], []
    mapping = {'minecraft:polished_andesite':'minecraft:deepslate_tiles',
               'minecraft:polished_andesite_slab':'minecraft:deepslate_tile_slab',
               'minecraft:polished_andesite_stairs':'minecraft:deepslate_tile_stairs'}
    for index in differences:
        xyz = tuple(map(int, after['coords'][index]))
        a = palettes[1][before['state_ids'][index]]
        b = palettes[2][after['state_ids'][index]]
        restored = old_lookup.get(xyz) == canonical[2][index]
        item = dict(xyz=xyz, before=a, after=b, matches_v4=bool(restored))
        changes.append(item)
        if (mapping.get(a['Name']) != b['Name'] or a.get('Properties') != b.get('Properties')
                or not restored or ROLES[int(after['role_ids'][index])] != 'roof'):
            failures.append(item)
    previous_details = json.loads((previous/'detail-register.json').read_text(encoding='utf-8'))
    geometry_keys = ('openings', 'wall_planes', 'inward_wall_bridges', 'floors',
                     'arch_contact_repairs', 'roof_spur_wall_removals', 'roof_seam_backing', 'roof_spur_bridge')
    geometry_unchanged = {key:details[key] == previous_details[key] for key in geometry_keys}
    result = dict(archive_sha256=digest(out/'sample-blocks.npz'),
        previous_archive_sha256=controls['geometry_archive_sha256'],
        restoration_archive_sha256=controls['restoration_archive_sha256'],
        occupied_coordinates_identical=coordinates_equal, roles_identical=roles_equal,
        registered_geometry_unchanged=geometry_unchanged, restored_roof_cells=len(changes),
        changes=changes, failures=failures,
        passed=coordinates_equal and roles_equal and all(geometry_unchanged.values()) and not failures)
    result['passed'] &= len(changes) == profile['roof_retint_scope']['expected_restored_v5_cells']
    write_json(out/'material-only-revision-audit.json', result)
    return {key:value for key,value in result.items() if key not in ('changes', 'failures')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    out = parser.parse_args().study.resolve()
    p = json.loads((out/'profile.json').read_text())
    m = json.loads((out/'manifest.json').read_text())
    d = json.loads((out/'detail-register.json').read_text())
    revision_delta = audit_material_only_revision(out, p, d)
    bb = m['source_roof']['world_bounds_blocks']
    c = Canvas(bb[0], bb[1], bb[2]-bb[0], bb[3]-bb[1], 2)
    with np.load(out/'sample-blocks.npz', allow_pickle=False) as a:
        q = a['coords']; ix=q[:, 0]-c.x_min; iy=q[:, 1]-c.y_min; iz=q[:, 2]-c.z_min
        c.data[iy, iz, ix]=a['state_ids']; c.roles[iy, iz, ix]=a['role_ids']
        c.palette=json.loads(str(a['palette_json']))
    b = load_measured_building(parent_id=p['parent_id'])
    r = rasterize_roof(b, [value/2 for value in bb], resolution=.5)
    roof_scope_failures = []
    roof_scope_counts = {}
    roof_scope = p.get('roof_retint_scope')
    if roof_scope:
        allowed_faces = set(roof_scope['sweeney_pitched_face_indices'])
        exceptions = {(201,80,-132)}
        original_roof_states = {tuple(q['xyz']):q['before']['Name'] for q in d['roof_material_cells']}
        source_family = {'minecraft:deepslate_tiles','minecraft:deepslate_tile_slab','minecraft:deepslate_tile_stairs'}
        gray_ids = [i for i,s in enumerate(c.palette) if s['Name'] in
                    ('minecraft:polished_andesite', 'minecraft:polished_andesite_slab', 'minecraft:polished_andesite_stairs')]
        for iy,iz,ix in np.argwhere(np.isin(c.data, gray_ids)):
            xyz = (int(ix)+c.x_min, int(iy)+c.y_min, int(iz)+c.z_min)
            face = int(r.face_indices[iz,ix])
            cap = (math.floor((r.heights[iz,ix]-25)*4+.5)-1)//2 if np.isfinite(r.heights[iz,ix]) else None
            permitted = xyz in exceptions or (face in allowed_faces and cap is not None
                and xyz[1] in (cap,cap-1) and original_roof_states.get(xyz) in source_family)
            roof_scope_counts[str(face)] = roof_scope_counts.get(str(face),0)+1
            if not permitted or ROLES[c.roles[iy,iz,ix]] != 'roof':
                roof_scope_failures.append(dict(xyz=xyz, source_face=face, cap_y=cap))
        expected_gray = roof_scope['expected_gray_loop_cells_after_coping']+1
        actual_gray = sum(roof_scope_counts.values())
        operations = sum('polished_andesite' in q['after']['Name'] for q in d['roof_material_cells'])
        if actual_gray != expected_gray or operations != roof_scope['expected_retint_operations']:
            roof_scope_failures.append(dict(expected_final_gray_cells=expected_gray, actual_final_gray_cells=actual_gray,
                expected_retint_operations=roof_scope['expected_retint_operations'], actual_retint_operations=operations))
    source = []
    for record, face in zip(d['source_faces'], b.roof_faces):
        value = dict(xz=list(map(list, face.polygon.exterior.coords)),
                     holes=[list(map(list, ring.coords)) for ring in face.polygon.interiors],
                     plane=[face.a, face.b, face.c], surface=face.surface_index, part=face.part_id)
        source.append(hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == record['sha256'])
    excluded = {(q[0], q[1]) for q in d['excluded_child_columns']}
    with np.load(out/'raster.npz', allow_pickle=False) as saved:
        keep = np.ones(r.heights.shape, dtype=bool)
        for x, z in excluded: keep[z-c.z_min, x-c.x_min] = False
        raster_checks = {name:bool(np.array_equal(saved[name][keep], expected[keep], equal_nan=True))
                         for name, expected in [('heights', r.heights), ('mask', r.footprint_mask),
                         ('face_indices', r.face_indices), ('gradient_x', r.gradient_x), ('gradient_z', r.gradient_z)]}
        raster_checks['only_authorized_child_removed'] = bool(not saved['mask'][~keep].any() and (saved['face_indices'][~keep] == -1).all())
    cache = {}
    jar = Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    def state_shape(resources, state, xyz):
        key = json.dumps(state, sort_keys=True)
        if key not in cache:
            grid = np.zeros((16, 16, 16), dtype=bool)
            if state['Name'] != 'minecraft:air':
                bs = BlockState(state['Name'], state.get('Properties', {}))
                for app in applications_for_state(resources.blockstate(bs.name), bs.properties, xyz):
                    for element in elements_for_state(resources.model(app.model), bs):
                        corners = np.array([rotate_model_point(v, app) for v in itertools.product(*zip(element['from'], element['to']))])
                        lo = np.maximum(0, np.rint(corners.min(0)).astype(int)); hi = np.minimum(16, np.rint(corners.max(0)).astype(int))
                        grid[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = True
            cache[key] = grid
        return cache[key]
    def shape(resources, xyz): return state_shape(resources, c.palette[c.get(*xyz)], xyz)
    roof_failures, retint_failures, buried, pane_failures, partial_failures, slices, spur_contacts = [], [], [], [], [], [], []
    panes_checked = partial_checked = 0
    with VanillaResources(jar) as resources:
        for item in d['roof_material_cells']+d['trim_cells']:
            xyz = tuple(item['xyz'])
            if not np.array_equal(state_shape(resources, item['before'], xyz), shape(resources, xyz)):
                retint_failures.append(item)
        for item in d.get('roof_spur_bridge', []):
            xyz=tuple(item['xyz']);a=shape(resources,xyz)
            for neighbor in item['contacts']:
                n=shape(resources,tuple(neighbor));delta=np.array(neighbor)-np.array(xyz)
                contact=int((a[15,:,:]&n[0,:,:]).sum()) if delta[0]==1 else int((a[:,:,0]&n[:,:,15]).sum())
                spur_contacts.append(dict(bridge=xyz,neighbor=neighbor,occupied_contact_area=contact))
        for z, x in np.argwhere(r.footprint_mask):
            xyz = (int(x)+c.x_min, int(z)+c.z_min)
            if xyz in excluded: continue
            half = math.floor((r.heights[z, x]-25)*4+.5); y=(half-1)//2
            role = ROLES[c.roles[y+64, z, x]]
            if role in ('terrain', 'pavement'):
                buried.append([*xyz, int(r.face_indices[z, x])]); continue
            occupied = shape(resources, (xyz[0], y, xyz[1]))
            actual = y+(np.nonzero(occupied)[1].max()+1)/16 if occupied.any() else None
            if actual != half/2:
                roof_failures.append(dict(xz=xyz, face=int(r.face_indices[z, x]), expected=half/2, actual=actual, role=role))
        pane_ids = [i for i, state in enumerate(c.palette) if state['Name'].endswith('_pane')]
        for iy, iz, ix in np.argwhere(np.isin(c.data, pane_ids)):
            xyz = (int(ix)+c.x_min, int(iy)+c.y_min, int(iz)+c.z_min)
            occupied = shape(resources, xyz)
            for dy, side, other in ((-1, 0, 15), (1, 15, 0)):
                contact = int((occupied[:, side, :] & shape(resources, (xyz[0], xyz[1]+dy, xyz[2]))[:, other, :]).sum())
                panes_checked += 1
                if not contact: pane_failures.append(dict(xyz=xyz, direction=dy))
        architectural_roles = [ROLES.index(q) for q in ('facade', 'roof', 'trim', 'window', 'floor', 'door')]
        for iy, iz, ix in np.argwhere(np.isin(c.roles, architectural_roles)):
            state = c.palette[c.data[iy, iz, ix]]
            if not state['Name'].endswith(('_slab', '_stairs')): continue
            xyz=(int(ix)+c.x_min, int(iy)+c.y_min, int(iz)+c.z_min)
            a=shape(resources, xyz); x,y,z=xyz
            contacts=int((a[:, 0, :] & shape(resources, (x, y-1, z))[:, 15, :]).sum())
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                n=shape(resources,(x+dx,y,z+dz))
                contacts+=int((a[15,:,:]&n[0,:,:]).sum()) if dx==1 else int((a[0,:,:]&n[15,:,:]).sum()) if dx==-1 else int((a[:,:,15]&n[:,:,0]).sum()) if dz==1 else int((a[:,:,0]&n[:,:,15]).sum())
            partial_checked += 1
            if not contacts: partial_failures.append(dict(xyz=xyz,state=state))
        # Flood real occupied vanilla shapes, including connected pane arms,
        # at both quarter-cell heights. This catches a diagonal full-wall
        # corner or a partial arch-head slit that component checks miss.
        active = r.footprint_mask.copy()
        for x, z in excluded: active[z-c.z_min, x-c.x_min] = False
        zs, xs = np.nonzero(active)
        lx, hx = int(xs.min())-3, int(xs.max())+4
        lz, hz = int(zs.min())-3, int(zs.max())+4
        for y in (70, 74, 78, 82):
            interior = distance_transform_cdt(active & (r.heights > (y+3)/2+25), metric='taxicab') >= 5
            for subheight in (4, 12):
                layer = np.zeros(((hz-lz)*16, (hx-lx)*16), dtype=bool)
                for iz, ix in np.argwhere(c.data[y+64, lz:hz, lx:hx] != 0):
                    iz, ix = int(iz)+lz, int(ix)+lx
                    occupied = shape(resources, (ix+c.x_min, y, iz+c.z_min))
                    layer[(iz-lz)*16:(iz-lz+1)*16, (ix-lx)*16:(ix-lx+1)*16] = occupied[:, subheight, :].T
                seed = np.zeros_like(layer); seed[0,:]=seed[-1,:]=seed[:,0]=seed[:,-1]=True
                exterior = binary_propagation(seed, mask=~layer)
                leaks, checked = [], 0
                for iz, ix in np.argwhere(interior):
                    xx, zz = (ix-lx)*16+8, (iz-lz)*16+8
                    if layer[zz, xx]: continue
                    checked += 1
                    if exterior[zz, xx]: leaks.append([int(ix)+c.x_min, y, int(iz)+c.z_min])
                slices.append(dict(y=y, subheight=subheight, checked=checked, leaks=len(leaks), examples=leaks[:12]))
    # Rebuild only the terrain to establish that no external grade was moved.
    terrain = ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz'
    h, ids, meta = terrain_arrays(terrain, 2, [value/2 for value in bb])
    ground = Canvas(bb[0], bb[1], bb[2]-bb[0], bb[3]-bb[1], 2)
    build_ground(ground, h, ids, meta['materials'], -25)
    smooth_exposed_measured_pavement(ground, h, ground.ground_heights, vertical_offset=-25)
    canonical = {json.dumps(s, sort_keys=True):i for i,s in enumerate(c.palette)}
    lookup = np.array([canonical.get(json.dumps(s,sort_keys=True),65535) for s in ground.palette],dtype=np.uint16)
    ground_roles=[ROLES.index(q) for q in ('terrain','pavement')]
    changed=(((c.data!=lookup[ground.data])|(c.roles!=ground.roles)) & (np.isin(c.roles,ground_roles)|np.isin(ground.roles,ground_roles))).any(0)
    mask=r.footprint_mask.copy()
    for x,z in excluded:mask[z-c.z_min,x-c.x_min]=False
    allowed=binary_dilation(mask,iterations=2)
    zz,xx=np.indices(mask.shape);x=(xx+c.x_min+.5)/2;z=(zz+c.z_min+.5)/2
    angle=np.deg2rad(9);u=x*np.cos(angle)+z*np.sin(angle);v=-x*np.sin(angle)+z*np.cos(angle)
    architecture=np.isin(c.roles,[ROLES.index(q) for q in ('facade','roof','trim','window','door')]).any(0)
    gap_masks={'tuck_mercer_core':(u>=-11.5)&(u<=53)&(v>=-131.8)&(v<=-122.8),
               'annan_sweeney_core':(u>=65)&(u<=87)&(v>=-133.5)&(v<=-131.0),
               'davy_approach_core':(u>=90.5)&(u<=94)&(v>=-119)&(v<=-79)}
    gaps={name:dict(architecture_columns=int((region&architecture).sum()),changed_ground_columns=int((region&changed).sum())) for name,region in gap_masks.items()}
    joints=pane_joint_report(c);support=pane_support_report(c);perimeter=pane_perimeter_report(c)
    # Include full blocks as well as partials: a two-cell full-block roof
    # fragment can pass the partial-block audit while hanging in free air.
    architectural=np.isin(c.roles,[ROLES.index(q) for q in ('facade','roof','trim','window','floor','door')])
    labels,count=label(architectural);sizes=np.bincount(labels.ravel());main=int(sizes[1:].argmax()+1)
    components=[]
    for index in range(1,count+1):
        if index==main:continue
        cells=np.argwhere(labels==index);ground_contacts=0
        for iy,iz,ix in cells:
            for dy,dz,dx in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
                if c.roles[iy+dy,iz+dz,ix+dx] in [ROLES.index('terrain'),ROLES.index('pavement')]:ground_contacts+=1
        components.append(dict(cells=len(cells),ground_contacts=ground_contacts,
            examples=[[int(ix)+c.x_min,int(iy)+c.y_min,int(iz)+c.z_min] for iy,iz,ix in cells[:12]]))
    del labels
    arches=[]
    for opening in d['openings']:
        if not opening['arched']:continue
        tops=[q[2] for q in opening['actual_pane_tops']]
        arches.append(dict(name=opening['name'],pane_head_y_min=min(tops),pane_head_y_max=max(tops),
            visible_crown_rise_blocks=max(tops)-min(tops),distinct_head_levels=len(set(tops))))
    cadence=[]
    for wall in d['wall_planes']:
        trace=wall['columns'];delta=np.diff(np.asarray(trace),axis=0)
        cadence.append(dict(name=wall['name'],columns=len(trace),noncardinal_steps=int((abs(delta).sum(1)!=1).sum()),
            reverse_steps=int(sum(np.any(delta[:,axis]>0) and np.any(delta[:,axis]<0) for axis in (0,1))),
            max_normal_centre_error_m=wall['normal_max_cell_centre_error_m']))
    result=dict(archive_sha256=digest(out/'sample-blocks.npz'),source_faces_matched=sum(source),source_raster_checks=raster_checks,
        excluded_child_columns=len(excluded),roof_top_failures=roof_failures,source_roofs_buried_at_grade=buried,
        roof_material_shape_failures=retint_failures,pane_vertical_contacts_checked=panes_checked,pane_contact_failures=pane_failures,
        pane_joints=joints,pane_support=support,pane_perimeter=perimeter,partial_blocks_checked=partial_checked,
        unsupported_partial_blocks=partial_failures,whole_wall_slices=slices,straight_wall_cadence=cadence,protected_gaps=gaps,
        other_architectural_components=components,spur_bridge_contacts=spur_contacts,arch_silhouettes=arches,
        roof_material_scope_counts=roof_scope_counts,roof_material_scope_failures=roof_scope_failures,
        ground_changes_outside_facade_strip=int((changed&~allowed).sum()),
        east_arches=[o['name'] for o in d['openings'] if o['name'].startswith('sweeney-east-tall-')],
        interpreted_centres=p['sweeney_east_centre_interpretation'],opening_limits=d['limitations'],uncertainties=p['uncertainties'])
    result['passed']=bool(all(source) and all(raster_checks.values()) and not roof_failures and not retint_failures and not roof_scope_failures
        and not pane_failures and not partial_failures and not support['unsupported_components']
        and not joints['unbridged_diagonal_pairs'] and not joints['disconnected_adjacent_pairs']
        and not perimeter['fewer_than_two_horizontal_joins'] and not perimeter['vertical_air_or_reversed_slab_contacts']
        and not any(q['noncardinal_steps'] or q['reverse_steps'] for q in cadence)
        and not any(q['architecture_columns'] or q['changed_ground_columns'] for q in gaps.values())
        and not (changed&~allowed).any() and not any(q['leaks'] for q in slices) and len(result['east_arches'])==10)
    result['passed'] &= bool(all(q['ground_contacts'] for q in components) and all(q['occupied_contact_area'] for q in spur_contacts)
        and all(q['visible_crown_rise_blocks']>=1 for q in arches))
    result['material_only_revision'] = revision_delta
    if revision_delta is not None:
        result['passed'] &= revision_delta['passed']
    write_json(out/'geometric-validation.json',result)
    artifact=audit(out)
    print(json.dumps(dict(passed=result['passed'] and artifact['passed'],roof_failures=roof_failures[:8],
        retint_failures=len(retint_failures),pane_failures=pane_failures[:8],partial_failures=partial_failures[:8],
        horizontal_candidates=perimeter['horizontal_candidates'][:12],gaps=gaps,ground_outside=result['ground_changes_outside_facade_strip'],
        wall_leaks=[q for q in slices if q['leaks']],opening_limits=d['limitations'],export_errors=artifact['errors']),indent=2))
    return 0 if result['passed'] and artifact['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
