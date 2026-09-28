"""Independently check Wendell's exported route, grade and assembly ownership."""

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation, binary_fill_holes, binary_propagation, distance_transform_cdt
from shapely.geometry import box
from shapely.ops import unary_union

from build_hill_chapel_sample import ROLES, Canvas, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json
from refine_hill_library_chapel import load_canvas, occupied_shapes
from assemble_hill_campus_studies import site_local_coordinates

ROOT = Path(__file__).resolve().parents[1]


def audit(study):
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    c = load_canvas(study)
    p, m = read(study/'profile.json'), read(study/'manifest.json')
    d, anchors = read(study/'detail-register.json'), read(study/'connection-anchors.json')
    b = load_measured_building(parent_id=p['parent_id'])
    bounds = m['source_roof']['world_bounds_blocks']
    bounds_m = [v/2 for v in bounds]
    heights, ids, meta = terrain_arrays(Path(m['terrain']['path']), 2, bounds_m)
    old = Canvas(c.x_min, c.z_min, c.data.shape[2], c.data.shape[1], 2)
    build_ground(old, heights, ids, meta['materials'], -25)
    smooth_exposed_measured_pavement(old, heights, old.ground_heights, vertical_offset=-25)
    zz, xx = np.indices(c.data.shape[1:]); x, z = (xx+c.x_min+.5)/2, (zz+c.z_min+.5)/2
    u, v = site_local_coordinates(p, x, z)
    r = rasterize_roof(b, bounds_m, .5)
    high = np.isin(r.face_indices, d['architectural_faces']) & r.footprint_mask
    architecture = np.any(~np.isin(c.roles, [ROLES.index(q) for q in ('air','terrain','pavement')]), axis=0)
    mask = binary_fill_holes(architecture)
    for u0, v0, u1, v1 in p['assembly_site_bounds_uv_m']:
        mask |= (u>=u0)&(u<u1)&(v>=v0)&(v<v1)
    mask = binary_fill_holes(binary_dilation(mask, iterations=1))
    changed = np.any((c.data != old.data) | (c.roles != old.roles), axis=0)
    # Palettes differ after architecture but the common ground palette was built
    # identically; inspect full states independently in exterior columns below.
    exterior_changed = []
    site_keys = set(tuple(q['xz']) for q in d['source_site_surfaces']) | set(map(tuple, d['entry_columns']))
    missing_support = []
    external_exact = 0
    for iz, ix in np.argwhere(~high):
        xc, zc = int(ix)+c.x_min, int(iz)+c.z_min
        column = c.data[:,iz,ix]; prior = old.data[:,iz,ix]
        occupied = np.flatnonzero(column)
        if not len(occupied):
            missing_support.append([xc,zc,'missing_ground']); continue
        terrain_y = np.flatnonzero(np.isin(c.roles[:,iz,ix], [ROLES.index('terrain'),ROLES.index('pavement')]))
        if len(terrain_y) and np.any(column[occupied.min():terrain_y.max()+1] == 0):
            missing_support.append([xc,zc,'subsurface_gap'])
        if np.array_equal(column,prior) and np.array_equal(c.roles[:,iz,ix],old.roles[:,iz,ix]):
            external_exact += 1
        elif (xc,zc) not in site_keys and not architecture[iz,ix]:
            exterior_changed.append([xc,zc])

    @lru_cache(maxsize=None)
    def occupied(xc,yc,zc):
        state = c.palette[c.get(xc,yc,zc)]
        return tuple(tuple(q[i]/16+(xc,yc,zc)[i%3] for i in range(6)) for q in occupied_shapes(state))

    points = anchors['route']['points_xyz']
    failures, samples = [], []
    for start,end in zip(points,points[1:]):
        for t in np.linspace(0,1,11):
            xc,feet,zc = [a+(b-a)*t for a,b in zip(start,end)]
            body=(xc-.3,feet,zc-.3,xc+.3,feet+1.8,zc+.3)
            support,collisions=0,[]
            for bx in range(math.floor(xc-.3),math.floor(xc+.3)+1):
                for bz in range(math.floor(zc-.3),math.floor(zc+.3)+1):
                    for by in range(math.floor(feet)-1,math.ceil(feet+1.8)):
                        for q in occupied(bx,by,bz):
                            overlaps=[min(body[i+3],q[i+3])-max(body[i],q[i]) for i in range(3)]
                            if all(q>1e-7 for q in overlaps):collisions.append([bx,by,bz])
                            if abs(q[4]-feet)<1e-7:support+=max(0,overlaps[0])*max(0,overlaps[2])
            samples.append([xc,feet,zc])
            if support<=1e-7 or collisions:failures.append(dict(xyz=samples[-1],support=support,collisions=collisions))
    authored_keys = site_keys | {(int(ix)+c.x_min,int(iz)+c.z_min) for iz,ix in np.argwhere(architecture)}
    omitted = [list(q) for q in sorted(authored_keys) if not mask[q[1]-c.z_min,q[0]-c.x_min]]
    roof_failures=[]
    with np.load(study/'authored-roof-raster.npz') as current:
        for name, expected in [('heights',r.heights),('gradient_x',r.gradient_x),('gradient_z',r.gradient_z),('face_indices',r.face_indices)]:
            if not np.array_equal(current[name][high],expected[high],equal_nan=True):roof_failures.append(name)
        if not np.array_equal(current['mask'],high):roof_failures.append('architectural_footprint_mask')
    component_shapes=unary_union([box((ix+c.x_min)/2,(iz+c.z_min)/2,(ix+c.x_min+1)/2,(iz+c.z_min+1)/2) for iz,ix in np.argwhere(mask)])
    campus=read(ROOT/'server-assets/hill-campus-context-v18.json')
    components=campus.get('components',campus.get('buildings',[]))
    if not components:
        components=campus['assembly']['components']
    neighbors=[]
    for component in components:
        if not any(word in component['name'].lower() for word in ('ryan','music house','meigs')):continue
        profile=read(ROOT/component['study']/'profile.json')
        other=load_measured_building(parent_id=profile['parent_id'])
        neighbors.append(dict(name=component['name'], source_footprint_distance_m=b.footprint.distance(other.footprint),
                              proposed_ownership_distance_to_source_footprint_m=component_shapes.distance(other.footprint),
                              overlap_m2=component_shapes.intersection(other.footprint).area))
    grade=[]
    for name,selected in [('north',(abs(u)<14)&(v>=-8)&(v<=-7.25)),('south',(abs(u)<12)&(v>=7)&(v<=8))]:
        values=[]
        for iz,ix in np.argwhere(selected & ~high):
            top=np.flatnonzero(np.isin(c.roles[:,iz,ix],[ROLES.index('terrain'),ROLES.index('pavement')]))
            if len(top):
                yy=int(top[-1])-64
                boxes=occupied(int(ix)+c.x_min,yy,int(iz)+c.z_min)
                if boxes:values.append(max(q[4] for q in boxes)/2+25)
        grade.append(dict(side=name,samples=len(values),min_navd88_m=min(values),median_navd88_m=float(np.median(values)),max_navd88_m=max(values)))
    rows,cols=np.nonzero(high)
    lz,hz,lx,hx=int(rows.min())-2,int(rows.max())+3,int(cols.min())-2,int(cols.max())+3
    slices=[]
    for ylevel in range(81,math.ceil((np.nanmax(r.heights[high])-25)*2)+1):
        interior=distance_transform_cdt(high&(r.heights>(ylevel+1)/2+25+.5),metric='taxicab')>=3
        for sub in (4,12):
            layer=np.zeros(((hz-lz)*16,(hx-lx)*16),bool)
            for iz,ix in np.argwhere(c.data[ylevel+64,lz:hz,lx:hx]!=0):
                iz,ix=int(iz)+lz,int(ix)+lx
                state=c.palette[int(c.data[ylevel+64,iz,ix])]
                for q in occupied_shapes(state):
                    if q[1]<=sub<q[4]:
                        layer[(iz-lz)*16+int(q[2]):(iz-lz)*16+int(q[5]),
                              (ix-lx)*16+int(q[0]):(ix-lx)*16+int(q[3])]=True
            for xc,zc in d['entry_columns']:
                iz,ix=zc-c.z_min,xc-c.x_min
                layer[(iz-lz)*16:(iz-lz+1)*16,(ix-lx)*16:(ix-lx+1)*16]=True
            seed=np.zeros_like(layer);seed[0,:]=seed[-1,:]=seed[:,0]=seed[:,-1]=True
            exterior=binary_propagation(seed,mask=~layer)
            leaks=sum(bool(exterior[(iz-lz)*16+8,(ix-lx)*16+8]) for iz,ix in np.argwhere(interior))
            slices.append(dict(y=ylevel,subvoxel_height=sub,tested_interior_columns=int(interior.sum()),leaks=leaks))
    allheight=dict(format='hill-wendell-all-height-enclosure-proof-v1',archive_sha256=digest(study/'sample-blocks.npz'),
                   passed=not any(q['leaks'] for q in slices),slices=slices,
                   scope='Every occupied facade height and each lower/upper half, using physical full/slab/stair/pane/door boxes. Only the registered usable entry is virtually closed for the enclosure test; its actual open route is checked separately.')
    write_json(study/'all-height-enclosure-proof.json',allheight)
    report=dict(format='hill-wendell-outline-site-audit-v1',archive_sha256=digest(study/'sample-blocks.npz'),
                route=dict(passed=not failures,samples=len(samples),failures=failures,points_xyz=points,
                           maximum_step_blocks=0,player_width_blocks=.6,player_height_blocks=1.8,sample_spacing_blocks=.1),
                ground=dict(exterior_columns=int((~high).sum()),exact_unchanged_exterior_columns=external_exact,
                            unauthorized_exterior_changed_columns=exterior_changed,missing_support=missing_support,measured_grade_controls=grade),
                ownership=dict(profile_site_bounds_uv_m=p['assembly_site_bounds_uv_m'],margin_m=.5,
                               owned_columns=int(mask.sum()),authored_columns=len(authored_keys),omitted_authored_columns=omitted,neighbors=neighbors),
                source_roof=dict(exact_high_source_arrays=True,failures=roof_failures,architectural_face_ids=d['architectural_faces'],
                                 site_reclassification_ids=d['reclassified_at_grade_faces']),
                all_height_enclosure=dict(passed=allheight['passed'],slices=len(slices),report='all-height-enclosure-proof.json'),
                passed=not(failures or exterior_changed or missing_support or omitted or roof_failures or any(q['overlap_m2'] for q in neighbors)) and allheight['passed'],
                limitations=['Neighbor comparison uses exact source footprints; the coordinator must check all combined ownership masks.',
                             'The entrance is provisional; only its registered short exterior-to-interior route is certified here.',
                             'No native visual acceptance or completed interiors is claimed.'])
    write_json(study/'site-route-ownership-audit.json',report)
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('study',type=Path)
    result=audit(parser.parse_args().study.resolve())
    raise SystemExit(0 if result['passed'] else 1)
