"""Feroe's photographed cream, pedimented residence on its measured footprint.

All inputs are metres in the profile's wall-aligned frame and NAVD88 datum.
The original source remains immutable. Roof repairs are explicitly authored.
"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely import contains_xy

from build_hill_chapel_sample import ROLES
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building
from campus_window_frames import close_diagonal_pane_corners

ROOT = Path(__file__).resolve().parents[1]
BOTTOM = {"type": "bottom", "waterlogged": "false"}
TOP = {"type": "top", "waterlogged": "false"}


def _source(p):
    b = load_measured_building(parent_id=p["parent_id"])
    research = json.loads((ROOT / p["roof_evidence"]["ledger"]).read_text(encoding="utf-8"))
    rec = next(q for q in research["building_records"] if q["parent_id"] == p["parent_id"])
    if b.source_sha256 != rec["measured"]["roof_sha256"]:
        raise ValueError("Feroe source CityJSON hash changed; re-audit face identities")
    fr = rec["measured"]["local_frame"]
    origin = np.array(fr["origin_xz_m"])
    axes = np.array([fr["U_xz"], fr["V_xz"]])
    for i, (face, measured) in enumerate(zip(b.roof_faces, rec["measured"]["roof_planes"], strict=True)):
        fp = hashlib.sha256(json.dumps({"xy": measured["uv_polygon_m"], "plane": measured["height_plane_xz"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        if fp != rec["roof_face_audit"]["faces"][i]["fingerprint"]:
            raise ValueError(f"Feroe research face fingerprint changed: {i}")
        expected = origin + np.array(measured["uv_polygon_m"]) @ axes
        if not np.allclose(expected, np.array(face.polygon.exterior.coords), atol=0.00002):
            raise ValueError(f"Feroe source face polygon order changed: {i}")
        if not np.allclose([face.a, face.b, face.c], measured["height_plane_xz"], atol=1e-8):
            raise ValueError(f"Feroe source plane changed: {i}")
    return b


def _patch(r, mask, levels, gx, gz, record):
    """Change surfaces only inside the existing county footprint."""
    mask = mask & r.footprint_mask
    h, x, z, ids = r.heights.copy(), r.gradient_x.copy(), r.gradient_z.copy(), r.face_indices.copy()
    h[mask] = np.broadcast_to(levels, h.shape)[mask]
    x[mask] = np.broadcast_to(gx, h.shape)[mask]
    z[mask] = np.broadcast_to(gz, h.shape)[mask]
    face_id = 1_000_000 + len(r.authored_roof_patches)
    ids[mask] = face_id
    record = {"face_index": face_id, "source": "explicit photo-interpreted Feroe correction; not surveyed geometry", "affected_columns": int(mask.sum()), "footprint_change_columns": 0, **record}
    return replace(r, heights=h, gradient_x=x, gradient_z=z, face_indices=ids,
                   missing_mask=r.missing_mask & ~mask,
                   authored_roof_patches=(*r.authored_roof_patches, record))


def prepare_roof(r, f, p):
    b = _source(p)
    # Exact audited high fragments, not a campus-wide height cutoff. Their
    # plan area is retained and covered by the adjacent accepted hip plane.
    plane = b.roof_faces[6]
    mask = np.isin(r.face_indices, [1, 2])
    r = _patch(r, mask, plane.height_at(f.x, f.z), plane.a, plane.b,
               {"reason": "Audited high fragments 1/2 lie at 73.34–75.25m while the adjacent actual hip is 62.26–64.76m; no photographed chimney matches these fragments.",
                "replaced_source_face_ids": [1, 2], "adjacent_plane_extended_from_source_face": 6})
    # The ornate west projection is a photographed pediment. Its original
    # plan is not rectangularised; only this bounded roof receives a gable.
    bay = p["bay"]
    mid = bay["centre_v_m"]
    half = bay["width_m"] / 2
    slope = (bay["ridge_navd88_m"] - bay["eave_navd88_m"]) / half
    levels = bay["ridge_navd88_m"] - np.abs(f.v - mid) * slope
    dv = np.where(f.v < mid, slope, -slope)
    mask = f.local_mask(bay["roof_bounds_uv_m"])
    r = _patch(r, mask, levels, dv * f.n[0], dv * f.n[1],
               {"reason": "West photographed triangular pediment and projecting two-storey panelled bay.",
                "bounds_uv_m": bay["roof_bounds_uv_m"], "eave_navd88_m": bay["eave_navd88_m"],
                "ridge_navd88_m": bay["ridge_navd88_m"], "centre_v_m": mid,
                "source_photo": p["evidence"][0]["local"]})
    return r


def _thin_window(f, side, at, centre, sill, width=1.45, height=1.75, paired=False, shape="rectangle"):
    """Flush glazing, with no full-block mullions or added exterior cages."""
    f.window_row(side, at, [centre], sill, width, height, lights=1, shape=shape)
    along = f.v if side in {"east", "west"} else f.u
    depth = f.u if side in {"east", "west"} else f.v
    mask = (abs(along-centre) <= width/2+.30) & (abs(depth-at) < 2.0) & f.r.footprint_mask
    # Seat the bottom and top of each quantised pane column in the existing
    # wall envelope. A shallow half slab replacing that wall made v1's air
    # slits, and a diagonal pane otherwise can miss its jamb by one voxel.
    for x, z, iz, ix in f.each_column(mask):
        ys = [y for y in range(f.height_y(sill), f.height_y(sill+height)+1)
              if f.c.palette[f.c.get(x, y, z)]["Name"].endswith("_pane")]
        if not ys:
            continue
        for y in (min(ys)-1, max(ys)+1):
            navd = (y+.5)/f.c.scale-f.offset
            if navd < f.r.heights[iz, ix] and y > f.c.ground_at(x, z):
                f.c.set(x, y, z, "tuff_bricks" if navd < 56.75 else "smooth_quartz", "facade")
    if paired:
        f.features["paired_sash_groups_without_masonry_mullions"] += 1


def _stone_base(f, p):
    # Cohesive gray-green courses; no random contrasting red/brown patchwork.
    # Texture mineral identity is a proxy, not a claim about the real stone.
    floor = p["geometry"]["entrance_floor_navd88_m"]
    f.recolor((-1, -2, 20, 20), 52.5, floor, "tuff_bricks")
    f.features["rough_coursed_stone_base"] = 1


def _bay(f, p):
    bay = p["bay"]
    front, v0, v1 = bay["front_u_m"], 6.72, 12.95
    floor = p["geometry"]["entrance_floor_navd88_m"]
    # Continuous backing occupies only the original projecting bay. Slab
    # profiles are then attached outside it; they never replace this wall.
    mask = f.local_mask((-0.9, v0, .80, v1)) & f.r.footprint_mask
    fronts = {}
    for x, z, iz, ix in f.each_column(mask):
        fronts[z] = min(fronts.get(z, x), x)
        top = int(np.floor((f.r.heights[iz, ix] + f.offset) * f.c.scale))
        for y in range(f.height_y(floor), top + 1):
            if f.c.roles[y + 64, iz, ix] != ROLES.index("roof"):
                f.c.set(x, y, z, "smooth_quartz", "facade")
    # A continuous cream rake follows the existing sampled roof shape,
    # retaining full backing below every stair/slab instead of making slits.
    for z, x in fronts.items():
        iz, ix = z - f.c.z_min, x - f.c.x_min
        ys = np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("roof"))
        if ys.size:
            y = int(ys[-1]) - 64
            state = f.c.palette[f.c.get(x, y, z)]
            name = state["Name"]
            target = "smooth_quartz_stairs" if name.endswith("_stairs") else "smooth_quartz_slab" if name.endswith("_slab") else "smooth_quartz"
            f.c.set(x, y, z, target, "trim", state.get("Properties"))
            f.c.set(x, y-1, z, "smooth_quartz", "facade")
    # The two edge pilasters are fluted face strips. The two photographed
    # slender intermediate columns use pale original wood-fence geometry.
    for v in (6.91, 12.76):
        f.box((front-.07, v-.17, front+.42, v+.17), floor, 62.65,
              "quartz_pillar", "trim", {"axis": "y"})
    for v in (8.90, 10.94):
        x, z = np.floor(f.world(front, v) * f.c.scale).astype(int)
        bx = fronts.get(int(z), int(x)) - 1
        for y in range(f.height_y(floor), f.height_y(62.65)):
            f.c.set(bx, y, int(z), "pale_oak_fence", "railing", PANE_PROPS)
        for level in (floor, 62.55):
            f.c.set(bx, f.height_y(level), int(z), "smooth_quartz_slab", "trim", BOTTOM)
    for centre in (7.87, 9.92, 11.94):
        _thin_window(f, "west", front, centre, 57.40, 1.48, 1.85, paired=True)
        _thin_window(f, "west", front, centre, 60.50, 1.48, 1.60, paired=True)
    # Each cornice is one attached slab in depth with a full wall behind.
    for level in (floor, 59.70, 62.90):
        for z, x in fronts.items():
            f.c.set(x-1, f.height_y(level), z, "smooth_quartz_slab", "trim", BOTTOM)
    for n, (z, x) in enumerate(sorted(fronts.items())):
        if n % 2 == 0:
            f.c.set(x-1, f.height_y(62.40), z, "quartz_slab", "trim", TOP)
    # The photographed oculus is small relative to the pediment. Its entire
    # bevel fits a 2x2-cell (1m) opening; four corner stairs reduce the exposed
    # dark area further. The pane sits just behind that continuous surround.
    centre_z = int(np.floor(f.world(front, bay["centre_v_m"])[1] * f.c.scale))
    rows = [centre_z-1, centre_z]
    face_x = max(fronts[z] for z in rows)
    y0 = f.height_y(63.75)
    for j, z in enumerate(rows):
        for k, y in enumerate(range(y0, y0+2)):
            for x in range(fronts[z], face_x+3):
                f.c.set(x, y, z, "air", "air")
            f.c.set(face_x, y, z, "smooth_quartz_stairs", "trim",
                    {"facing": "north" if j == 0 else "south", "half": "bottom" if k == 0 else "top", "shape": "straight", "waterlogged": "false"})
            f.c.set(face_x+1, y, z, "black_stained_glass_pane", "window", PANE_PROPS)
    f.features.update(photographed_west_pediment=1, photographed_oculus=1,
                      photographed_two_storey_panelled_bay=1,
                      west_paired_sash_groups=6, inferred_tree_hidden_bay_groups=2,
                      continuous_bay_edge_pilasters=2, slender_bay_columns=2,
                      continuous_bay_wall_backing=1, stair_cut_oculus_corners=4,
                      oculus_maximum_opening_width_blocks=2,
                      oculus_maximum_opening_height_blocks=2)


def _other_elevations(f, p):
    # These openings are individually bounded interpretations on their own
    # measured walls. The unseen sides do not inherit the ornate west bay.
    for row in p["interpreted_window_rows"]:
        for centre in row["centres_m"]:
            _thin_window(f, row["side"], row["at_m"], centre, row["sill_navd88_m"],
                         row["width_m"], row["height_m"], row.get("paired", False))
    for side, at, ends in (("east", 16.25, (5.3, 16.6)), ("south", 12.94, (-0.2, 8.8)),
                            ("north", 2.30, (2.3, 15.2)), ("west", 8.91, (13.1, 18.2))):
        f.wall_band(side, at, ends, 56.70, 0.25, "quartz_block", 0.36)
        f.wall_band(side, at, ends, 62.1, 0.25, "quartz_block", 0.36)
    # A plausible, explicitly unverified entrance to the low north addition.
    f.door("north", -0.75, 12.15, 56.75, 1.15, 2.20)
    f.features["interpreted_north_operable_entry"] = 1


def _deck_and_site(f, p, b):
    floor = p["geometry"]["entrance_floor_navd88_m"]
    deck = contains_xy(b.roof_faces[4].polygon, f.x, f.z) & f.r.footprint_mask
    # The low source patch is an exposed balcony, not an enclosed room.
    f.box((8.85, 12.85, 10.7, 18.35), floor - 0.25, floor, "smooth_quartz_slab", "trim", TOP, mask=deck)
    for v in (13.4, 15.6, 18.0):
        x, z = np.floor(f.world(9.02, v) * f.c.scale).astype(int)
        grade = (f.c.ground_at(int(x), int(z)) + 1) / f.c.scale - f.offset
        f.box((8.80, v - 0.19, 9.31, v + 0.19), grade, floor,
              "quartz_pillar", "trim", {"axis": "y"})
    # Thin connected bars keep balusters readable at the shared scale.
    for side, at, ends in (("west", 8.87, (13.05, 18.15)),
                            ("south", 18.15, (8.9, 10.5)), ("north", 13.04, (8.9, 9.7))):
        f.railing(side, at, ends, floor, height=1.0, post_spacing=2.6)
        bounds = ((at - .18, ends[0], at + .18, ends[1]) if side == "west"
                  else (ends[0], at - .18, ends[1], at + .18))
        f.box(bounds, floor + .85, floor + 1.10, "smooth_quartz_slab", "trim", BOTTOM)
    # White newels, replacing the generic railing stone posts.
    for u, v in ((8.90, 13.05), (8.90, 15.60), (8.90, 18.15), (10.4, 18.15)):
        f.box((u-.19, v-.19, u+.19, v+.19), floor, floor+1.05, "quartz_pillar", "trim", {"axis": "y"})
    # Secondary photographed low extension and a modest return deck door.
    f.door("west", 9.8, 16.2, floor, 1.10, 2.2)
    # North terrace follows only its measured low patch, preserving the gaps.
    patio = contains_xy(b.roof_faces[11].polygon, f.x, f.z)
    for x, z, iz, ix in f.each_column(patio):
        top = f.height_y(floor) - 1
        if f.c.ground_at(x, z) < top:
            for y in range(f.c.ground_at(x, z) + 1, top):
                f.c.set(x, y, z, "tuff_bricks", "facade")
            f.c.set(x, top, z, "smooth_stone", "pavement")
    # Short, level access paving and three quarter-metre step surfaces.
    f.site_surface([(10.9, -4.3), (13.4, -4.3), (13.4, -1.45), (10.9, -1.45)], 56.0)
    for i, h in enumerate((56.25, 56.50, 56.75)):
        f.box((11.1, -3.25 + .6*i, 13.2, -2.60 + .6*i), 55.8, h - .25, "smooth_stone", "pavement")
        f.box((11.1, -3.25 + .6*i, 13.2, -2.60 + .6*i), h - .25, h, "smooth_stone_slab", "pavement", BOTTOM)
    # One horizontal basement opening is directly visible under the bay.
    _thin_window(f, "west", -.33, 9.90, 55.50, 1.35, .55)
    f.features.update(photographed_open_white_railed_south_deck=1,
                      interpreted_north_terrace=1, entrance_quarter_metre_steps=3,
                      photographed_bay_basement_window=1)


def _chimneys(f, p):
    for ch in p["chimneys"]:
        u, v = ch["centre_uv_m"]
        width, low, top = ch["width_m"], ch["base_navd88_m"], ch["top_navd88_m"]
        f.box((u-width/2, v-width/2, u+width/2, v+width/2), low, top,
              "smooth_quartz", "facade")
        f.box((u-width/2-.10, v-width/2-.10, u+width/2+.10, v+width/2+.10), top-.10, top+.15,
              "stone_brick_slab", "trim", BOTTOM)
    f.features["photographed_pale_chimney_shafts_interpreted_positions"] = len(p["chimneys"])


def _final_corner_returns(f,p):
    """Apply only the four joints audited on the accepted native study."""
    for joint in p.get("pane_corner_repair",{}).get("joints",[]):
        allowed={tuple(v) for v in joint["allowed_xyz"]}
        for x,_,z in allowed:
            if not f.r.footprint_mask[z-f.c.z_min,x-f.c.x_min]:
                raise ValueError("Feroe corner repair extends outside the source footprint")
        f.features["final_authorised_pane_corner_returns"]+=close_diagonal_pane_corners(f.c,allowed,inward=joint["inward_xz"])


def _accepted_baseline(f,p):
    """Preserve a reviewed archive exactly before a bounded repair.

    This optional, hash-bound path avoids importing unrelated shared builder
    changes into geometry that has already passed its native review. The
    original source-building generator remains above for research rebuilds.
    """
    base=p["accepted_baseline"]
    path=ROOT/base["archive"]
    if hashlib.sha256(path.read_bytes()).hexdigest()!=base["sha256"]:
        raise ValueError("Accepted Feroe baseline changed")
    manifest=json.loads((ROOT/base["manifest"]).read_text(encoding="utf-8"))
    if manifest["source_roof"]["world_bounds_blocks"] != [f.c.x_min,f.c.z_min,f.c.x_min+f.c.data.shape[2],f.c.z_min+f.c.data.shape[1]]:
        raise ValueError("Feroe baseline grid differs from this study")
    with np.load(path,allow_pickle=False) as archive:
        if tuple(str(v) for v in archive["role_names"])!=ROLES:
            raise ValueError("Feroe baseline role schema changed")
        xyz=archive["coords"]
        indexes=(xyz[:,1]+64,xyz[:,2]-f.c.z_min,xyz[:,0]-f.c.x_min)
        f.c.data.fill(0);f.c.roles.fill(0)
        f.c.data[indexes]=archive["state_ids"]
        f.c.roles[indexes]=archive["role_ids"]
        f.c.palette=json.loads(str(archive["palette_json"]))
        f.c.palette_lookup={json.dumps(state,sort_keys=True):i for i,state in enumerate(f.c.palette)}
    f.features.update(manifest["features"])
    f.features["hash_checked_accepted_baseline_preserved"]=1
    _final_corner_returns(f,p)


def _frame_contact_repairs(f, p):
    """Apply the reviewed exact-state patch, never a global neighbor fill.

    The patch distinguishes actual facade sheets, one-cell inward returns,
    isolated rear reveal stubs, and glazing leaked above low deck roofs.
    Every removal and concealed cap is enumerated with its prior state.
    """
    for change in p.get("frame_contact_repair", {}).get("changes", []):
        x, y, z = change["xyz"]
        iz, ix = z-f.c.z_min, x-f.c.x_min
        previous = f.c.palette[f.c.get(x,y,z)]
        role = ROLES[f.c.roles[y-f.c.y_min,iz,ix]]
        if previous != change["expected"] or role != change["expected_role"]:
            raise ValueError(f"Feroe frame patch baseline mismatch at {(x,y,z)}")
        if role == "roof" or change["role"] == "roof":
            raise ValueError("Feroe frame repair cannot alter a roof-role cell")
        after = change["state"]
        if after["Name"] != "minecraft:air":
            if not f.r.footprint_mask[iz,ix] or (y+1)/2-f.offset > f.r.heights[iz,ix]+.125:
                raise ValueError(f"Feroe frame repair leaves the measured envelope at {(x,y,z)}")
        if previous["Name"] == "minecraft:black_stained_glass_pane":
            raise ValueError("The reviewed 2x2 oculus cannot change in this repair")
        f.c.set(x,y,z,after["Name"],change["role"],after.get("Properties"))
        f.features["exact_bounded_frame_repairs"] += 1


def build_details(f, p):
    b = _source(p)
    if p.get("accepted_baseline"):
        _accepted_baseline(f,p)
        _frame_contact_repairs(f,p)
        return
    _stone_base(f, p)
    _bay(f, p)
    _other_elevations(f, p)
    _deck_and_site(f, p, b)
    _chimneys(f, p)
    for level in (56.75, 59.65):
        f.floor_plate(level)
    # Adjacent interpreted windows can touch the same raster corner. Run
    # their explicitly audited union after all openings, bands and doors,
    # so a later opening cannot cut the authorised return back out.
    _final_corner_returns(f,p)
    f.features["source_face_fingerprints_verified"] = len(b.roof_faces)
    f.features["independently_photographed_facades"] = 1
    f.features["interpreted_other_facades"] = 3
