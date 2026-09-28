"""Inspect exported Quadrivium occupied-shape contacts and entrance thresholds.

This supplements exact Anvil parity and the shared pane component audit. It
uses positive-area intersections of vanilla pane/bar, slab, stair and full
block shapes. It does not equate graph connectivity with exterior enclosure.
"""

import argparse
from functools import lru_cache
import json
from pathlib import Path

from audit_hill_window_joints import ArchiveStates
from campus_study_io import digest, write_json

AXES=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))


@lru_cache(maxsize=None)
def shapes(key):
    state=json.loads(key)
    n,p=state["Name"],state.get("Properties",{})
    if n=="minecraft:air":return ()
    if n.endswith("_pane") or n=="minecraft:iron_bars":
        boxes=[(7,0,7,9,16,9)]
        for direction,box in [("north",(7,0,0,9,16,8)),("south",(7,0,8,9,16,16)),
                              ("east",(8,0,7,16,16,9)),("west",(0,0,7,8,16,9))]:
            if p.get(direction)=="true":boxes.append(box)
        return tuple(boxes)
    if n.endswith("_slab"):
        if p.get("type")=="double":return ((0,0,0,16,16,16),)
        return ((0,8,0,16,16,16),) if p.get("type")=="top" else ((0,0,0,16,8,16),)
    if n.endswith("_stairs"):
        upper=p.get("half")=="top"
        boxes=[(0,8,0,16,16,16) if upper else (0,0,0,16,8,16)]
        y0,y1=(0,8) if upper else (8,16)
        facing=p.get("facing","north")
        boxes.append({"north":(0,y0,0,16,y1,8),"south":(0,y0,8,16,y1,16),
                      "east":(8,y0,0,16,y1,16),"west":(0,y0,0,8,y1,16)}[facing])
        return tuple(boxes)
    if n.endswith("_door"):
        # These authored closed north-facing doors occupy the south skin.
        facing=p.get("facing","north")
        return ({"north":(0,0,13,16,16,16),"south":(0,0,0,16,16,3),
                 "east":(0,0,0,3,16,16),"west":(13,0,0,16,16,16)}[facing],)
    return ((0,0,0,16,16,16),)


def audit(study):
    lookup=ArchiveStates(study/"sample-blocks.npz")
    keys=[json.dumps(s,sort_keys=True) for s in lookup.palette]
    def state(q):return lookup.palette[lookup.get(*q)]
    def name(q):return state(q)["Name"]
    @lru_cache(maxsize=None)
    def contacts(a,b,d):
        axis=next(i for i,v in enumerate(d) if v)
        tangent=[i for i in range(3) if i!=axis]
        score=0
        for left in shapes(keys[a]):
            for right in shapes(keys[b]):
                translated=[right[i]+16*d[i%3] for i in range(6)]
                if abs(left[axis+3 if d[axis]>0 else axis]-translated[axis if d[axis]>0 else axis+3])>1e-9:continue
                overlap=[min(left[i+3],translated[i+3])-max(left[i],translated[i]) for i in tangent]
                if all(v>0 for v in overlap):score+=overlap[0]*overlap[1]
        return score
    def area(q,d):
        b=tuple(q[i]+d[i] for i in range(3))
        return contacts(lookup.get(*q),lookup.get(*b),d)
    panes=list(lookup.iter_panes())
    bars=[tuple(map(int,q)) for q,s in zip(lookup.coords,lookup.states)
          if lookup.palette[int(s)]["Name"]=="minecraft:iron_bars"]
    pane_holes=[]
    for q in panes:
        horizontal=[d for d in AXES if d[1]==0 and area(q,d)>0]
        vertical=[d for d in AXES if d[1]!=0 and area(q,d)>0]
        if len(horizontal)<2 or len(vertical)<2:
            pane_holes.append(dict(xyz=q,horizontal_contacts=horizontal,vertical_contacts=vertical))
    bar_holes=[]
    for q in bars:
        all_contacts=[d for d in AXES if area(q,d)>0]
        if not all_contacts:bar_holes.append(q)
    profile=json.loads((study/"profile.json").read_text(encoding="utf-8"))
    backing_checks=[]
    for q,b in profile["facade_path_evidence"]["partial_backing"]:
        q,b=tuple(q),tuple(b)
        if not name(q).endswith(("_slab","_stairs")):continue
        d=tuple(b[i]-q[i] for i in range(3))
        positive=area(q,d)>0
        supports=[v for v in AXES if area(q,v)>0]
        backing_checks.append(dict(xyz=q,backing=b,positive_area_inward_backing=positive,
                                   occupied_face_supports=supports))
    lower_doors=[tuple(map(int,q)) for q,s in zip(lookup.coords,lookup.states)
                 if lookup.palette[int(s)]["Name"].endswith("_door") and
                 lookup.palette[int(s)].get("Properties",{}).get("half")=="lower"]
    access=[]
    for x,y,z in lower_doors:
        approach=[(x,y,z-distance) for distance in (1,2,3)]
        obstructions=[q for q in approach if name(q)!="minecraft:air" or name((q[0],q[1]+1,q[2]))!="minecraft:air"]
        supported=lookup.get(x,y-1,z)!=0
        tops=[]
        head_obstructions=[]
        for q in approach:
            support=next((yy for yy in range(y+1,y-7,-1) if lookup.get(q[0],yy,q[2])),None)
            tops.append(support+1 if support is not None else None)
            if support is not None:
                for yy in (support+1,support+2):
                    if lookup.get(q[0],yy,q[2]):head_obstructions.append((q[0],yy,q[2]))
        levels=[y,*tops]
        traversable=all(a is not None and b is not None and abs(a-b)<=1
                        for a,b in zip(levels,levels[1:])) and not head_obstructions
        access.append(dict(door_xyz=(x,y,z),threshold_occupied=supported,
                           three_cell_approach_obstructions=obstructions,
                           actual_approach_support_tops=tops,
                           approach_traversable_with_maximum_one_block_step=traversable,
                           approach_floor_states=[state((q[0],q[1]-1,q[2])) for q in approach]))
    report=dict(format="hill-quadrivium-physical-contact-audit-v1",
                archive_sha256=digest(study/"sample-blocks.npz"),panes=len(panes),
                pane_positive_area_failures=pane_holes,iron_bars=len(bars),
                completely_unanchored_bars=bar_holes,partial_block_checks=backing_checks,
                missing_partial_inward_backing=[r for r in backing_checks if not r["positive_area_inward_backing"]],
                doors=access,
                passed=not pane_holes and not bar_holes and all(r["positive_area_inward_backing"] for r in backing_checks)
                       and all(r["threshold_occupied"] and r["approach_traversable_with_maximum_one_block_step"] for r in access),
                limitations=["A positive area proves physical contact, not photographic fidelity.",
                             "Aperture and whole-facade enclosure also require native oblique/corner inspection.",
                             "Door access reports three exterior columns without modifying measured terrain.",
                             "Full blocks, authored straight stairs, slabs, connected panes/bars and closed doors are modeled explicitly; no unsupported shape approximations enter the reported authored contacts."])
    write_json(study/"physical-contact-audit.json",report)
    print(json.dumps({k:report[k] for k in ("archive_sha256","panes","iron_bars","passed")}))
    print(json.dumps(dict(pane_failures=len(pane_holes),bar_failures=len(bar_holes),
                          missing_backing=len(report["missing_partial_inward_backing"]),
                          door_approach_obstructions=sum(bool(r["three_cell_approach_obstructions"]) for r in access))))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study",type=Path)
    audit(parser.parse_args().study)
