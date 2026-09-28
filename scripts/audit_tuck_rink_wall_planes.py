"""Classify the inherited south/west steps against the exact county perimeter."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion
from shapely import contains_xy

from build_hill_chapel_sample import ROLES
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    out=parser.parse_args().study.resolve()
    manifest=json.loads((out/'manifest.json').read_text())
    bb=manifest['source_roof']['world_bounds_blocks']
    building=load_measured_building(parent_id='16003036400434C-c86ee564a0')
    r=rasterize_roof(building,[v/2 for v in bb],.5)
    zz,xx=np.indices(r.footprint_mask.shape)
    x=(xx+bb[0]+.5)/2;z=(zz+bb[1]+.5)/2
    angle=np.deg2rad(9);co=np.cos(angle);si=np.sin(angle)
    u=x*co+z*si;v=-x*si+z*co
    exact=contains_xy(building.footprint,x,z)
    boundary=exact & ~binary_erosion(exact,structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
    caps=np.zeros_like(xx)
    caps[exact]=(np.floor((r.heights[exact]-25)*4+.5).astype(int)-1)//2
    vertices=np.array(building.footprint.exterior.coords)
    uv=np.column_stack((vertices[:,0]*co+vertices[:,1]*si,-vertices[:,0]*si+vertices[:,1]*co))
    segments=[]
    for a,b in zip(uv,uv[1:]):
        if abs(b[0]-a[0])>50 and -133<a[1]<-132 and -133<b[1]<-132:
            segments.append(('south_main',a,b,'x',1))
        elif a[0]<-11 and b[0]<-11 and abs(b[1]-a[1])>10:
            segments.append((f'west_main_{len(segments)}',a,b,'z',-1))
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as archive:
        coords=archive['coords'];roles=archive['role_ids']
        names=np.array([state['Name'] for state in json.loads(str(archive['palette_json']))])
        states=names[archive['state_ids']]
    architecture=np.isin(roles,[ROLES.index(q) for q in ('facade','trim','window','door')])
    architectural_occupancy={tuple(map(int,q)):s for q,s,role in zip(coords,states,roles)
        if role in (ROLES.index('facade'),ROLES.index('trim'),ROLES.index('roof'),ROLES.index('floor'))}
    reports=[]
    for name,a,b,axis,step_sign in segments:
        direction=b-a;length=float(np.linalg.norm(direction));unit=direction/length
        along=(u-a[0])*unit[0]+(v-a[1])*unit[1]
        distance=(u-a[0])*(-unit[1])+(v-a[1])*unit[0]
        strip=(along>=0)&(along<=length)&(abs(distance)<.8)
        expected=boundary & strip
        indices=np.flatnonzero(architecture & (coords[:,1]>=59))
        cells=coords[indices];iz=cells[:,2]-bb[1];ix=cells[:,0]-bb[0]
        selected=strip[iz,ix] & (cells[:,1]<caps[iz,ix]-1)
        cells=cells[selected];cell_states=states[indices][selected]
        actual={(int(q[0]),int(q[1]),int(q[2])) for q in cells}
        expected_cells={(int(ix)+bb[0],y,int(iz)+bb[1])
            for iz,ix in np.argwhere(expected) for y in range(59,int(caps[iz,ix])-1)}
        missing=sorted(expected_cells-actual)
        required_bridges=set();slices=[];all_offsets=[]
        outward=np.array([0.,1.]) if axis=='x' else np.array([-1.,0.])
        normal=np.array([-unit[1],unit[0]])
        if normal@outward<0:normal=-normal
        world_normal=np.array([normal[0]*co-normal[1]*si,normal[0]*si+normal[1]*co])
        cube_support=.25*abs(world_normal).sum()
        for y in sorted({q[1] for q in expected_cells}):
            points=np.array([(q[0],q[2]) for q in actual if q[1]==y])
            if not len(points):
                continue
            dominant=0 if axis=='x' else 1;other=1-dominant
            trace={}
            for position in points:
                key=int(position[dominant]);value=int(position[other])
                trace[key]=max(trace.get(key,value),value) if step_sign==1 else min(trace.get(key,value),value)
            ordered=sorted(trace.items())
            changes=[(b[0]-a[0],step_sign*(b[1]-a[1])) for a,b in zip(ordered,ordered[1:])]
            reverse=[q for q in changes if q[1]<0]
            oversized=[q for q in changes if q[0]==1 and q[1]>1]
            bridges=[]
            for first,second in zip(ordered,ordered[1:]):
                if second[0]-first[0]!=1 or step_sign*(second[1]-first[1])!=1:continue
                bridge=(second[0],y,first[1]) if axis=='x' else (first[1],y,second[0])
                required_bridges.add(bridge);bridges.append(bridge)
            trace_xz=[(key,value) if axis=='x' else (value,key) for key,value in ordered]
            offsets=[]
            for px,pz in trace_xz:
                pu=(px+.5)/2*co+(pz+.5)/2*si;pv=-(px+.5)/2*si+(pz+.5)/2*co
                offsets.append(float((np.array([pu,pv])-a)@normal))
            all_offsets.extend(offsets)
            runs=[];run=1
            for dx,dy in changes:
                if dx==1 and dy==0:run+=1
                else:runs.append(run);run=1
            runs.append(run)
            slices.append(dict(y=y,wall_cells=len(points),trace_columns=len(trace),reverse_steps=len(reverse),
                steps_larger_than_one_cell=len(oversized),max_adjacent_step=max([q[1] for q in changes if q[0]==1],default=0),
                trace_xz=trace_xz,run_lengths_including_clipped_end_runs=runs,cardinal_turns=len(bridges),
                inward_bridge_cells=bridges,signed_centre_offset_range_m=[min(offsets),max(offsets)],
                exposed_cube_envelope_offset_range_m=[min(offsets)+cube_support,max(offsets)+cube_support]))
        extra=sorted(actual-expected_cells-required_bridges)
        def endpoint_return(q):
            iz=q[2]-bb[1];ix=q[0]-bb[0]
            return bool(exact[iz,ix] and (along[iz,ix]<.75 or along[iz,ix]>length-.75))
        protected_returns=[q for q in extra if endpoint_return(q)]
        extra=[q for q in extra if not endpoint_return(q)]
        material_returns=[list(map(int,q)) for q,s in zip(cells,cell_states) if s!='minecraft:red_terracotta' and endpoint_return(q)]
        bad_materials=[list(map(int,q)) for q,s in zip(cells,cell_states) if s!='minecraft:red_terracotta' and not endpoint_return(q)]
        missing_bridges=sorted(q for q in required_bridges if q not in architectural_occupancy)
        partial_bridges=sorted(q for q in required_bridges if architectural_occupancy.get(q,'').endswith(('_slab','_stairs')))
        reports.append(dict(id=name,exact_source_endpoints_uv_m=[a.tolist(),b.tolist()],
            expected_wall_cells=len(expected_cells),checked_wall_cells=len(actual),height_slices=slices,
            missing_expected_cells=missing,extra_projecting_or_thickened_cells=extra,unexpected_material_cells=bad_materials,
            preserved_endpoint_return_cells=protected_returns,preserved_endpoint_trim_cells=material_returns,
            required_inward_bridges=len(required_bridges),missing_cardinal_bridge_cells=missing_bridges,
            partial_bridge_cells_requiring_shape_review=partial_bridges,half_cube_normal_support_m=float(cube_support),
            all_height_centre_offset_range_m=[min(all_offsets),max(all_offsets)],
            all_height_exposed_envelope_offset_range_m=[min(all_offsets)+cube_support,max(all_offsets)+cube_support],
            passed=not missing and not extra and not bad_materials and not missing_bridges and not partial_bridges
                and all(not s['reverse_steps'] and not s['steps_larger_than_one_cell'] for s in slices)))
    report=dict(archive_sha256=digest(out/'sample-blocks.npz'),source_sha256=building.source_sha256,
        source_center_sample_mask_exact=bool(np.array_equal(exact,r.footprint_mask)),
        method='Compare every red wall cell from floor Y59 to the retained roof substrate against the one-cell cardinal boundary of the exact county polygon sampled at 0.5m. Endpoint cells are included. Check each height trace for reverse or larger-than-one-cell steps.',
        segments=reports,
        preserved_corners_and_projection='Exact v2-to-v3 coordinate/state delta audit preserves every south/west corner, southwest projection and roof cap; its only facade edits are 69 exposed EAST gable substrate retints.',
        limitation='This classifies the regular half-metre voxel steps. Native shadows remain visible; this does not assert a smooth sub-block surface or observed hidden elevation detail.',
        passed=bool(len(reports)==3 and np.array_equal(exact,r.footprint_mask) and all(q['passed'] for q in reports)))
    write_json(out/'wall-plane-classification.json',report)
    print(json.dumps(dict(passed=report['passed'],segments=[dict(id=q['id'],checked=q['checked_wall_cells'],
        slices=len(q['height_slices']),missing=len(q['missing_expected_cells']),extra=len(q['extra_projecting_or_thickened_cells'])) for q in reports]),indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
