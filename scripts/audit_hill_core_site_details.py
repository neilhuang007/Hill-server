"""Check core fixture meaning and native survival, beyond exact plan replay."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import label

from build_hill_chapel_sample import ROLES
from campus_study_io import digest, write_json
import hybridize_voxelearth_roofer_world as anvil
from prepare_hill_core_environment import load_region, read
from refine_hill_campus_environment import SITE_ROLES, apply_site_block, apply_surface


def native_chunk(world, xyz):
    x, _, z = xyz
    path = world / "region" / f"r.{x//512}.{z//512}.mca"
    if not path.is_file():
        path = world / "dimensions/minecraft/overworld/region" / path.name
    region = anvil.RegionEditor(path)
    index = anvil.region_chunk_index(x//16, z//16)
    return anvil.parse_chunk_record(region.raw_records[index], path, index)


def native_state(chunk, xyz):
    x, y, z = xyz
    section = next(s for s in chunk["sections"] if int(s["Y"]) == y//16)
    palette, packed = anvil.section_block_states(section)
    ids = anvil.unpack_indices(len(palette), packed)
    key = anvil.palette_state_key(palette[ids[anvil.section_index(x%16, y%16, z%16)]])
    return {"Name": key[0], **({"Properties": dict(key[1])} if key[1] else {})}


def audit(source, plan_path, controls_path, output, native_world=None):
    if output.exists():
        raise FileExistsError("Choose a fresh detail audit; preserve previous reports")
    path = plan_path or source/"environment-plan.json"
    plan = read(path)
    manifest = read(source/"manifest.json")
    c = load_region(source, manifest, (-80, -110, 360, 250))
    if plan_path:
        if plan["source_manifest_sha256"] != digest(source/"manifest.json"):
            raise ValueError("Plan targets another base")
        architecture = np.any(~np.isin(c.roles, list(SITE_ROLES)), axis=0)
        for action in plan["columns"]:
            apply_surface(c, action)
        for action in plan["site_blocks"]:
            apply_site_block(c, action, architecture)
    actions = {tuple(a["xyz"]): a for a in plan["site_blocks"]}
    def state(xyz):
        return c.palette[c.get(*xyz)]
    def role(xyz):
        x,y,z=xyz
        return ROLES[int(c.roles[y+64,z-c.z_min,x-c.x_min])]
    rows=[]
    native_results=[]
    for registration in plan["registered_source_details"]:
        ident=registration["id"]
        cells=[tuple(q) for q in registration["authored_cells_xyz"]]
        errors=[]
        for q in cells:
            expected=actions[q]
            if state(q)!=expected["state"] or role(q)!=expected["role"]:
                errors.append({"xyz":q,"reason":"Exact state/role differs"})
        columns={(x,z) for x,_,z in cells}
        for x,z in columns:
            base=min(y for xx,y,zz in cells if (xx,zz)==(x,z))
            # An elevated crosspiece may span the open memorial; only feet or
            # the base of a freestanding vertical object require ground.
            if base!=min(y for _,y,_ in cells):
                continue
            support=(x,base-1,z)
            if role(support) not in {"terrain","pavement"} or state(support)["Name"]=="minecraft:air":
                errors.append({"xyz":support,"reason":"Missing site support beneath fixture foot"})
        meaning={}
        if "bench" in ident:
            seats=[q for q in cells if state(q)["Name"]=="minecraft:oak_stairs"]
            backs=[q for q in cells if state(q)["Name"]=="minecraft:oak_trapdoor"]
            facing="south" if "north_timber" in ident else "north"
            meaning={"length_blocks":len(seats),"length_metres":len(seats)/2,
                     "back_faces":sorted({state(q).get("Properties",{}).get("facing") for q in backs}),
                     "required_back_facing":facing,
                     "model_basis":"Vanilla open north trapdoor panel lies at south Z13..16 skin; south is its 180-degree rotation. Both backs must face inward toward the source island."}
            if len(seats)!=4 or len(backs)!=4 or any(state(q)["Properties"]["facing"]!=facing for q in backs):
                errors.append({"reason":"Bench length or inward-facing back is incorrect"})
        if "bell_memorial" in ident:
            bells=[q for q in cells if state(q)["Name"]=="minecraft:bell"]
            if len(bells)!=1:
                errors.append({"reason":"Expected exactly one central bell"})
            else:
                q=bells[0]; support=(q[0],q[1]+1,q[2])
                meaning={"bell_xyz":q,"ceiling_support":state(support),"footprint_blocks":[max(x for x,_,_ in cells)-min(x for x,_,_ in cells)+1,max(z for _,_,z in cells)-min(z for _,_,z in cells)+1]}
                if state(q)["Properties"].get("attachment")!="ceiling" or state(support)["Name"]!="minecraft:black_concrete":
                    errors.append({"reason":"Bell lacks its solid ceiling attachment"})
                if native_world:
                    chunk=native_chunk(native_world,q)
                    entities=[e for e in chunk.get("block_entities",[]) if str(e.get("id",""))=="minecraft:bell" and tuple(int(e[k]) for k in ("x","y","z"))==q]
                    actual=native_state(chunk,q)
                    native_results.append({"kind":"bell","xyz":q,"state":actual,"bell_block_entities":len(entities),"passed":actual==state(q) and len(entities)==1})
        rows.append({"id":ident,"passed":not errors,"cells":len(cells),"materials":dict(Counter(state(q)["Name"] for q in cells)),"semantic_checks":meaning,"errors":errors})
    controls=read(controls_path)
    turf=[]
    for action in controls["terrain_columns"]:
        x,z=action["xz"]; y=int(c.ground_heights[z-c.z_min,x-c.x_min])
        turf.append({"xz":[x,z],"actual_ground_y":y,"target_ground_y":action["target_y"],"passed":y==action["target_y"] and state((x,y,z))["Name"]=="minecraft:grass_block"})
    shrub_mask=np.zeros(c.ground_heights.shape,bool)
    for q,a in actions.items():
        if a["feature"]=="class_1971_seating_island_shrubs" and state(q)["Name"]=="minecraft:oak_leaves":
            shrub_mask[q[2]-c.z_min,q[0]-c.x_min]=True
    _,clumps=label(shrub_mask,structure=np.ones((3,3)))
    plants=[(q,a) for q,a in actions.items() if a["state"]["Name"] in {"minecraft:short_dry_grass","minecraft:tall_dry_grass"}]
    for q,a in plants:
        if native_world:
            actual=native_state(native_chunk(native_world,q),q)
            native_results.append({"kind":"dry_grass","xyz":q,"state":actual,"passed":actual["Name"]==a["state"]["Name"]})
    curb=[]
    for z in range(162,170):
        x=247; y=int(c.ground_heights[z-c.z_min,x-c.x_min]); st=state((x,y,z))
        top=y+(.5 if st["Name"].endswith("_slab") and st.get("Properties",{}).get("type")=="bottom" else 1)
        curb.append({"xz":[x,z],"top_y":top,"state":st,"paved":role((x,y,z))=="pavement"})
    curb_pass=all(p["paved"] for p in curb) and all(abs(a["top_y"]-b["top_y"])<=.5 for a,b in zip(curb,curb[1:]))
    bay=Counter(a["state"]["Name"] for a in plan["columns"] if a["feature"]=="class_1971_curved_paver_seating_bay")
    passed=(len(rows)==6 and all(r["passed"] for r in rows) and all(r["passed"] for r in turf)
            and clumps==6 and curb_pass and bay["minecraft:mud_bricks"]>0 and not bay["minecraft:bricks"]
            and all(r["passed"] for r in native_results))
    report={"format":"hill-core-site-detail-semantics-v1","passed":passed,
            "source_manifest_sha256":digest(source/"manifest.json"),"plan_sha256":digest(path),
            "native_touchups_sha256":digest(controls_path),"auditor_sha256":digest(Path(__file__)),
            "mode":"in-memory plan replay" if plan_path else "actual final archives",
            "fixtures":rows,"exact_turf_corrections":turf,"separate_eight_connected_shrub_clumps":clumps,
            "dry_grass_cells":len(plants),"bay_paving":dict(bay),"pavilion_north_curb_join":curb,
            "pavilion_north_curb_join_passed":curb_pass,"native_survival":native_results,
            "native_survival_checked":native_world is not None,
            "limits":"Native PNG review must still verify visual rendering; exact archive states alone cannot prove a block-entity model is visible."}
    write_json(output,report)
    print(json.dumps({"passed":passed,"fixtures":len(rows),"turf_columns":len(turf),"shrub_clumps":clumps,"native_checked":native_world is not None}))
    if not passed:
        raise SystemExit(1)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("--plan",type=Path)
    parser.add_argument("--native-touchups",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--native-world",type=Path)
    args=parser.parse_args()
    audit(args.source,args.plan,args.native_touchups,args.output,args.native_world)
