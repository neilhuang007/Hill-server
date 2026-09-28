"""Independently classify Annan's completed exact south perimeter trace."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion

from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json


def run(out):
    m=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    d=json.loads((out/'detail-register.json').read_text(encoding='utf-8'))
    bb=m['source_roof']['world_bounds_blocks']
    b=load_measured_building(parent_id='1600303920031C-4b7d18d798')
    r=rasterize_roof(b,[q/2 for q in bb],.5)
    zz,xx=np.indices(r.heights.shape);xm=(xx+bb[0]+.5)/2;zm=(zz+bb[1]+.5)/2
    co,si=np.cos(np.deg2rad(9)),np.sin(np.deg2rad(9))
    u=xm*co+zm*si;v=-xm*si+zm*co
    boundary=r.footprint_mask & ~binary_erosion(r.footprint_mask,structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
    strip=(u>=61.75)&(u<77.1)&(v>=-135.25)&(v<-133.3)
    trace={}
    for iz,ix in np.argwhere(boundary&strip):trace[int(ix)]=max(trace.get(int(ix),int(iz)),int(iz))
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as archive:
        q=archive['coords'];grid=np.zeros((384,*r.heights.shape),np.uint16)
        grid[q[:,1]+64,q[:,2]-bb[1],q[:,0]-bb[0]]=archive['state_ids']
        palette=json.loads(str(archive['palette_json']))
    west,east=b.roof_faces[11],b.roof_faces[20]
    upper=np.minimum(west.a*xm+west.b*zm+west.c,east.a*xm+east.b*zm+east.c)
    ordered=sorted(trace.items());allowed=set(ordered)
    for (ix0,iz0),(ix1,iz1) in zip(ordered,ordered[1:]):
        if ix1-ix0==1 and iz1-iz0==1:allowed.add((ix1,iz0))
    additions=[]
    for record in d['south_wall_completion']:
        x,y,z=record['xyz'];ix,iz=x-bb[0],z-bb[1]
        additions.append(dict(xyz=[x,y,z],passed=bool((ix,iz) in allowed and r.footprint_mask[iz,ix]
            and 69<=y<math.floor((upper[iz,ix]-25)*2)-1 and palette[int(grid[y+64,iz,ix])]['Name']=='minecraft:bricks')))
    slices=[];cap_exceptions=[]
    for y in range(64,82):
        points=[];missing=[];recessed=[];extras=[]
        for ix,ez in ordered:
            if y>=math.floor((upper[ez,ix]-25)*2)-1:continue
            zs=np.flatnonzero(strip[:,ix]&r.footprint_mask[:,ix]&(grid[y+64,:,ix]!=0))
            if not len(zs):missing.append(ix+bb[0]);continue
            az=int(zs.max());points.append([ix+bb[0],az+bb[1]])
            if az<ez:recessed.append([ix+bb[0],az+bb[1],ez+bb[1]])
            if az>ez:extras.append([ix+bb[0],az+bb[1],ez+bb[1]])
            state=palette[int(grid[y+64,ez,ix])]
            if state['Name'].endswith(('_slab','_stairs')):
                half=math.floor((r.heights[ez,ix]-25)*4+.5);cap=(half-1)//2
                cap_exceptions.append(dict(xyz=[ix+bb[0],y,ez+bb[1]],face=int(r.face_indices[ez,ix]),
                    state=state,preserved_source_cap=y==cap))
        steps=[b[1]-a[1] for a,b in zip(points,points[1:]) if b[0]-a[0]==1]
        slices.append(dict(y=y,trace_xz=points,reverse_steps=sum(q<0 for q in steps),
            steps_above_one=sum(q>1 for q in steps),missing=missing,recessed=recessed,extras=extras))
    report=dict(archive_sha256=digest(out/'sample-blocks.npz'),added_cells_checked=len(additions),
        addition_failures=[q for q in additions if not q['passed']],height_slices=slices,
        preserved_partial_cap_cells=cap_exceptions,
        interpretation='One exact-footprint monotone south wall trace, with original localized low cap occupancy retained by explicit source authority. Partial caps are retained source roof geometry, not a full-height wall setback.',
        passed=bool(all(q['passed'] for q in additions) and all(q['preserved_source_cap'] for q in cap_exceptions)
            and all(not q['reverse_steps'] and not q['steps_above_one'] and not q['missing'] and not q['recessed'] and not q['extras'] for q in slices)))
    write_json(out/'south-plane-classification.json',report)
    print(json.dumps(dict(passed=report['passed'],added_cells=len(additions),slices=len(slices),
        preserved_partial_cap_cells=len(cap_exceptions),failures=[q for q in slices if q['reverse_steps'] or q['recessed'] or q['extras']]),indent=2))
    return report['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True)
    raise SystemExit(0 if run(parser.parse_args().study.resolve()) else 1)
