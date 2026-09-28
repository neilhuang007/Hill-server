"""Require one Annan architectural component through occupied face contacts."""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

from build_hill_chapel_sample import ROLES
from campus_study_io import digest, write_json
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point


def run(out):
    with np.load(out/'sample-blocks.npz',allow_pickle=False) as archive:
        palette=json.loads(str(archive['palette_json']))
        selected=np.isin(archive['role_ids'],[ROLES.index(q) for q in ('facade','roof','trim','window','door','floor','railing','fixture')])
        coords=archive['coords'][selected].astype(int);states=archive['state_ids'][selected];roles=archive['role_ids'][selected]
    surfaces={}
    jar=Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    with VanillaResources(jar) as resources:
        for sid in np.unique(states):
            state=palette[int(sid)];bs=BlockState(state['Name'],state.get('Properties',{}))
            grid=np.zeros((16,16,16),bool)
            for app in applications_for_state(resources.blockstate(bs.name),bs.properties,(0,0,0)):
                for element in elements_for_state(resources.model(app.model),bs):
                    corners=np.array([rotate_model_point(q,app) for q in itertools.product(*zip(element['from'],element['to']))])
                    lo=np.maximum(0,np.rint(corners.min(0)).astype(int));hi=np.minimum(16,np.rint(corners.max(0)).astype(int))
                    grid[lo[0]:hi[0],lo[1]:hi[1],lo[2]:hi[2]]=True
            surfaces[int(sid)]=[grid[0,:,:],grid[15,:,:],grid[:,0,:],grid[:,15,:],grid[:,:,0],grid[:,:,15]]
    lookup={tuple(q):i for i,q in enumerate(coords)}
    parent=np.arange(len(coords));sizes=np.ones(len(coords),int)
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    face_edges=0;noncontact_pairs=[]
    for i,(x,y,z) in enumerate(coords):
        a=surfaces[int(states[i])]
        for q,af,bf in [((x+1,y,z),1,0),((x,y+1,z),3,2),((x,y,z+1),5,4)]:
            j=lookup.get(q)
            if j is None:continue
            if not (a[af]&surfaces[int(states[j])][bf]).any():
                noncontact_pairs.append([coords[i].tolist(),coords[j].tolist()]);continue
            face_edges+=1;left,right=find(i),find(j)
            if left!=right:
                if sizes[left]<sizes[right]:left,right=right,left
                parent[right]=left;sizes[left]+=sizes[right]
    groups={}
    for i in range(len(coords)):groups.setdefault(int(find(i)),[]).append(i)
    components=[]
    for ids in sorted(groups.values(),key=len,reverse=True):
        q=coords[ids]
        components.append(dict(cells=len(ids),bounds_xyz=[q.min(0).tolist(),q.max(0).tolist()],
            examples=[dict(xyz=coords[i].tolist(),state=palette[int(states[i])],role=ROLES[int(roles[i])]) for i in ids[:20]]))
    report=dict(archive_sha256=digest(out/'sample-blocks.npz'),architectural_cells=len(coords),
        occupied_face_contact_edges=face_edges,component_count=len(components),components=components,
        adjacent_but_noncontact_partial_pairs=len(noncontact_pairs),
        noncontact_examples=noncontact_pairs[:20],
        method='Vanilla model occupancy at 1/16 block. Cardinal pairs join only when their opposing occupied faces overlap with positive area. Terrain is excluded.',
        passed=len(components)==1)
    write_json(out/'architectural-connectivity.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('components','noncontact_examples')},indent=2))
    return report['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True)
    raise SystemExit(0 if run(parser.parse_args().study.resolve()) else 1)
