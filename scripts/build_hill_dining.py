"""Amend Dining/court/link cells in the exact accepted Athey archive.

The accepted Athey is loaded, never regenerated. Every changed state and role
must lie in the source packet's declared amendment mask before export.
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from build_hill_chapel_sample import Canvas, ROLES
from campus_export_parity import compare_world, read_archive
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study, write_json
from hill_dining_details import DiningAmendment

ROOT = Path(__file__).resolve().parents[1]


def load_accepted_canvas(path, manifest, scale):
    """Rehydrate state IDs and semantic roles without changing either."""
    bounds = manifest["source_roof"]["world_bounds_blocks"]
    canvas = Canvas(bounds[0], bounds[1], bounds[2]-bounds[0], bounds[3]-bounds[1], scale)
    with np.load(path, allow_pickle=False) as archive:
        if list(archive["role_names"]) != list(ROLES):
            raise ValueError("Baseline role schema has changed")
        canvas.palette = json.loads(str(archive["palette_json"]))
        canvas.palette_lookup = {json.dumps(v, sort_keys=True): i for i,v in enumerate(canvas.palette)}
        xyz = archive["coords"]
        address = (xyz[:,1]-canvas.y_min, xyz[:,2]-canvas.z_min, xyz[:,0]-canvas.x_min)
        canvas.data[address] = archive["state_ids"]
        canvas.roles[address] = archive["role_ids"]
    ground = np.isin(canvas.roles, [ROLES.index("terrain"), ROLES.index("pavement")])
    canvas.ground_heights = np.max(np.where(ground, np.arange(384)[:,None,None]+canvas.y_min, -64),axis=0)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=ROOT/"server-assets/hill-dining-reference.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a fresh revision; completed studies are immutable")
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    baseline = ROOT/profile["baseline_study"]
    archive = baseline/"sample-blocks.npz"
    if digest(archive) != profile["baseline_archive_sha256"]:
        raise ValueError("Accepted Athey archive hash changed")
    packet = ROOT/profile["source_packet"]
    if digest(packet) != profile["source_packet_sha256"]:
        raise ValueError("Reference packet hash changed")
    for key in ("source_addendum","site_detail_addendum","seal_placement_addendum","core_source_packet","court_correction_packet","east_gallery_source_packet"):
        if profile.get(key) and digest(ROOT/profile[key]["path"])!=profile[key]["sha256"]:
            raise ValueError(f"Frozen {key} hash changed")
    base_manifest = json.loads((baseline/"manifest.json").read_text(encoding="utf-8"))
    print("Loading exact accepted Athey archive", flush=True)
    canvas = load_accepted_canvas(archive, base_manifest, profile["blocks_per_metre"])
    before_states, before_roles = canvas.data.copy(), canvas.roles.copy()
    building = load_measured_building(ROOT/profile["source_cityjson"],profile["parent_id"],ROOT/profile["measured_terrain_manifest"])
    roof_hash = (base_manifest.get("sources", {}).get("roof", {}).get("sha256")
                 or profile.get("source_cityjson_sha256"))
    if building.source_sha256 != roof_hash:
        raise ValueError("Source geometry differs from accepted baseline")
    bounds = [v/canvas.scale for v in base_manifest["source_roof"]["world_bounds_blocks"]]
    raster = rasterize_roof(building,bounds,1/canvas.scale)
    amendment = DiningAmendment(canvas,profile,raster,profile["vertical_offset_m"])
    amendment.measured_building = building
    print("Applying bounded Dining/court/link amendment", flush=True)
    if profile.get("exterior_refinement"):
        # Later exterior refinements start from the accepted shared component;
        # do not replay its earlier Dining reconstruction over accepted cells.
        evidence = {key: base_manifest[key] for key in (
            "dining_wall_paths", "dining_openings", "dining_partial_backing",
            "protected_source_court_fringe_columns", "original_source_court_fringe_columns",
        ) if key in base_manifest}
        evidence.update(amendment.refine_existing())
    else:
        evidence = amendment.build()
    changed = (canvas.data != before_states) | (canvas.roles != before_roles)
    invalid = changed & ~amendment.mutation_mask
    parity = {"baseline_archive_sha256":digest(archive),"declared_mutation_cells":int(amendment.mutation_mask.sum()),
              "changed_cells":int(changed.sum()),"outside_mask_state_or_role_changes":int(invalid.sum()),
              "state_changes":int((canvas.data != before_states).sum()),"role_changes":int((canvas.roles != before_roles).sum()),
              "preserved_state_and_role_cells":int((~amendment.mutation_mask).sum())}
    if invalid.any():
        yy,zz,xx = np.nonzero(invalid)
        raise ValueError({**parity,"examples":np.column_stack((xx+canvas.x_min,yy+canvas.y_min,zz+canvas.z_min))[:15].tolist()})
    del before_states,before_roles,changed,invalid
    evidence.update({"baseline": {"study":profile["baseline_study"],"archive_sha256":digest(archive)},
                     "source_packet":{"path":profile["source_packet"],"sha256":digest(packet)},
                     "source_roof":base_manifest["source_roof"],"roof_coverage":raster.coverage_report,
                     "bounded_mutation_parity":parity,"uncertainties":profile["uncertainties"]})
    evidence["sources"] = {"roof": {"path": profile["source_cityjson"], "sha256": building.source_sha256}}
    evidence["source_addenda"]={key:profile[key] for key in ("source_addendum","site_detail_addendum","seal_placement_addendum","core_source_packet","court_correction_packet","east_gallery_source_packet") if profile.get(key)}
    source_names = ["build_hill_dining.py", "hill_dining_details.py"]
    if profile.get("exterior_refinement"):
        source_names.append("campus_athey_details.py")
    evidence["generator_sources"]={name:digest(ROOT/"scripts"/name) for name in source_names}
    cameras=[]
    for spec in profile["camera_views"]:
        def point(p):
            x,z=amendment.world(*p[:2])
            return [float(x*canvas.scale),float((p[2]+profile["vertical_offset_m"])*canvas.scale),float(z*canvas.scale)]
        cameras.append({"name":spec["name"],"eye":point(spec["eye_uv_navd88_m"]),"target":point(spec["target_uv_navd88_m"]),"fov":spec["fov"]})
    finish_study(canvas,profile,args.output,cameras,evidence)
    shutil.copy2(ROOT/"scripts/hill_dining_details.py",args.output/"detail-generator.py")
    shutil.copy2(ROOT/"scripts/build_hill_dining.py",args.output/"build-generator.py")
    if profile.get("exterior_refinement"):
        shutil.copy2(ROOT/"scripts/campus_athey_details.py",args.output/"athey-detail-generator.py")
    write_json(args.output/"bounded-mutation-parity.json",parity)
    print("Checking exact exported Anvil states",flush=True)
    result,errors,_,chunks=compare_world(read_archive(args.output/"sample-blocks.npz"),args.output/"world")
    write_json(args.output/"export-parity.json",{"archive_sha256":digest(args.output/"sample-blocks.npz"),"chunks":chunks,"errors":errors,**result})
    if errors:
        raise ValueError(errors)
    print(json.dumps({"study":str(args.output),"archive_sha256":digest(args.output/"sample-blocks.npz"),"export_errors":errors,"mutation":parity}),flush=True)


if __name__=="__main__":
    main()
