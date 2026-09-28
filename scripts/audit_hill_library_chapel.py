"""Audit the new entry cells, exact original frame and retained body/roof bounds."""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from audit_hill_quadrivium_contacts import AXES
from refine_hill_library_chapel import BASE, ROOT, load_canvas, occupied_shapes
from build_hill_chapel_sample import ROLES
from campus_study_io import digest, write_json


def audit(study):
    p=json.loads((study/"profile.json").read_text(encoding="utf-8"))
    baseline=ROOT/p["baseline_study"]
    original,current=load_canvas(baseline),load_canvas(study)
    if (original.x_min,original.z_min,original.data.shape)!=(current.x_min,current.z_min,current.data.shape):
        raise ValueError("Source canvas changed")
    delta=np.load(study/"entry-delta.npz")

    def contact(q,d):
        b=tuple(q[i]+d[i] for i in range(3))
        axis=next(i for i,v in enumerate(d) if v)
        other=[i for i in range(3) if i!=axis]
        area=0
        for left in occupied_shapes(current.palette[current.get(*q)]):
            for right in occupied_shapes(current.palette[current.get(*b)]):
                right=[right[i]+16*d[i%3] for i in range(6)]
                if left[axis+3 if d[axis]>0 else axis]!=right[axis if d[axis]>0 else axis+3]:
                    continue
                overlap=[min(left[i+3],right[i+3])-max(left[i],right[i]) for i in other]
                if min(overlap)>0:area+=math.prod(overlap)
        return area

    contacts,failures=[],[]
    for row in delta["coords"]:
        q=tuple(map(int,row))
        state=current.palette[current.get(*q)]
        name=state["Name"]
        if not (name.endswith(("_pane","_slab","_stairs","_door")) or name=="minecraft:iron_bars"):
            continue
        directions=[list(d) for d in AXES if contact(q,d)>0]
        record={"xyz":list(q),"state":state,"positive_area_contacts":directions}
        contacts.append(record)
        if not directions:
            failures.append({**record,"reason":"No occupied face contact"})
        elif name=="minecraft:iron_bars" and [0,-1,0] not in directions:
            failures.append({**record,"reason":"Rail post has no occupied foot contact"})
        elif name.endswith("_pane") and (sum(d[1]==0 for d in directions)<2 or sum(d[1]!=0 for d in directions)<2):
            failures.append({**record,"reason":"Amended pane lacks complete lateral/vertical contacts"})

    def bounds(c,roles):
        yy,zz,xx=np.nonzero(np.isin(c.roles,[ROLES.index(r) for r in roles]))
        low=[int(xx.min()+c.x_min),int(yy.min()-64),int(zz.min()+c.z_min)]
        high=[int(xx.max()+c.x_min+1),int(yy.max()-64+1),int(zz.max()+c.z_min+1)]
        return {"min_xyz_blocks":low,"max_xyz_blocks_exclusive":high,
            "span_xyz_metres":[(b-a)/2 for a,b in zip(low,high)],
            "min_navd88_m":low[1]/2+25,"max_navd88_m":high[1]/2+25}
    source_bounds=bounds(original,("facade","roof"))
    current_bounds=bounds(current,("facade","roof"))
    roofs=original.roles==ROLES.index("roof")
    roof_changes=0
    for y,z,x in np.argwhere(roofs):
        roof_changes+=original.palette[int(original.data[y,z,x])]!=current.palette[int(current.data[y,z,x])]
    report={"format":"hill-library-chapel-entry-physical-audit-v1","archive_sha256":digest(study/"sample-blocks.npz"),
        "baseline_archive_sha256":digest(baseline/"sample-blocks.npz"),"auditor_sha256":digest(Path(__file__)),
        "frame":{"x_min":current.x_min,"z_min":current.z_min,"shape_yzx":list(current.data.shape),"same_as_baseline":True},
        "source_body_and_roof_bounds":source_bounds,"candidate_body_and_roof_bounds":current_bounds,
        "same_body_and_roof_bounds":source_bounds==current_bounds,"existing_roof_cells":int(roofs.sum()),"changed_existing_roof_states":roof_changes,
        "changed_partial_cells":len(contacts),"contacts":contacts,"failures":failures,
        "passed":not failures and not roof_changes and source_bounds==current_bounds,
        "limitations":["Bounds include the established authored historic/addition envelope, not a new architectural survey.","The Chapel southern addition remains the inherited ~19.6 by 7.7 m interpretation of proposed SP-1, with about 1 m raster uncertainty.","Contact checks use the existing full-block/straight-stair/slab/pane/bar shape model and explicit installed-vanilla door/trapdoor skin rotations. They do not certify photographic detail or collision for untested decorative blocks."]}
    write_json(study/"entry-physical-audit.json",report)
    print(json.dumps({k:report[k] for k in ("passed","changed_partial_cells","same_body_and_roof_bounds","changed_existing_roof_states","failures")}),flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study",type=Path)
    result=audit(parser.parse_args().study)
    raise SystemExit(0 if result["passed"] else 1)
