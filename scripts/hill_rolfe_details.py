"""Rolfe's own source roof, closed front block, and individually stated facades.

Coordinates are Rolfe-local metres and NAVD88.  Current pitch photographs,
the historical west-gable image, and unobserved rear proposals stay distinct.
"""

from dataclasses import replace
import math

import numpy as np
from scipy.ndimage import binary_erosion

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_window_frames import close_diagonal_pane_corners, pane_perimeter_report


TOP = {"type": "top", "waterlogged": "false"}
BOTTOM = {"type": "bottom", "waterlogged": "false"}


def prepare_roof(r, f, p):
    ground = np.isin(r.face_indices, p["roof_interpretation"]["ground_faces"])
    keep = r.footprint_mask & ~ground
    # Face 16 is a closed lower front room, not an authored open porch.  The
    # three lower rear hip planes and all high source planes remain untouched.
    return replace(r, footprint_mask=keep, missing_mask=r.missing_mask & keep,
                   face_indices=np.where(keep, r.face_indices, -1))


def _body(f):
    return f.r.footprint_mask & (f.r.heights >= 69.0)


def _wall_sheet(f, side, at, centre, width, roof_min, tolerance=0.65):
    end = side in {"east", "west"}
    along, across = (f.v, f.u) if end else (f.u, f.v)
    normal = (f.t * (1 if side == "east" else -1) if end
              else f.n * (1 if side == "south" else -1))
    body = _body(f) & (f.r.heights >= roof_min)
    edge = np.zeros_like(body)
    for axis, component in ((1, normal[0]), (0, normal[1])):
        if abs(component) > 1e-6:
            edge |= ~np.roll(body, -int(np.sign(component)), axis=axis)
    aperture = (abs(along - centre) <= width / 2) & (abs(across - at) <= tolerance)
    return body & edge & aperture, body, normal, along, aperture


def _inward(normal):
    return ((-int(np.sign(normal[0])), 0) if abs(normal[0]) > abs(normal[1])
            else (0, -int(np.sign(normal[1]))))


def _facing(vector):
    return (("east" if vector[0] > 0 else "west")
            if abs(vector[0]) > abs(vector[1])
            else ("south" if vector[1] > 0 else "north"))


def _back_cell(f, x, z, sheet, body, normal):
    dx, dz = _inward(normal)
    for depth in (1, 2, 3):
        bx, bz = x + dx * depth, z + dz * depth
        iz, ix = bz - f.c.z_min, bx - f.c.x_min
        if not body[iz, ix]:
            return None
        if not sheet[iz, ix]:
            return bx, bz
    return None


def _basements(f, p):
    body = _body(f)
    inside = binary_erosion(body, iterations=2)
    edge = body & ~binary_erosion(body)
    low, entrance = p["geometry"]["basement_floor_navd88_m"], 68.1
    bounds = (-1, -1, 53, 24)
    # The footprint alone is excavated.  Exterior grades, the pitch, and the
    # roughly 7 m rear slope retain their measured elevations.
    f.box(bounds, low, entrance, "air", "air", mask=inside)
    f.box(bounds, low, entrance, "bricks", "facade", mask=edge)
    for floor in (low, 65.1, entrance):
        f.box(bounds, floor - 0.5, floor, "smooth_stone", "floor", mask=inside)
    f.features["separate_rear_basement_floor_levels"] = 2
    f.features["basement_interior_columns"] = int(inside.sum())
    f.features["pitch_entrance_navd88_cm"] = 6810
    f.features["lowest_rear_floor_navd88_cm"] = 6210


def _sash_row(f, row):
    y0 = math.ceil((row["sill_navd88_m"] + f.offset) * f.c.scale - 0.5 - 1e-9)
    height = max(2, round(row["height_m"] * f.c.scale))
    groups = 0
    for centre in row["centres_m"]:
        at = row.get("surface_at_by_centre_m", {}).get(str(centre), row["at_m"])
        sheet, body, normal, _, aperture = _wall_sheet(
            f, row["side"], at, centre, row["width_m"],
            row["sill_navd88_m"] + row["height_m"], row.get("surface_tolerance_m", 0.65),
        )
        placed = 0
        for x, z, iz, ix in f.each_column(sheet):
            exterior = np.floor(np.array([x + 0.5, z + 0.5]) + normal * 2).astype(int)
            grade = f.c.ground_at(int(exterior[0]), int(exterior[1]))
            for y in range(y0, y0 + height):
                if y > grade:
                    f.c.set(x, y, z, "white_stained_glass_pane", "window", PANE_PROPS)
                    placed += 1
            back = _back_cell(f, x, z, sheet, body, normal)
            if back:
                for y, properties in ((y0, BOTTOM), (y0 + height - 1, TOP)):
                    if y > grade and f.c.get(back[0], y, back[1]) == 0:
                        f.c.set(back[0], y, back[1], "quartz_slab", "trim", properties)
        if placed:
            allowed = {(x, y, z) for x, z, _, _ in f.each_column(body & aperture)
                       for y in range(y0, y0 + height)}
            if not hasattr(f.c, "window_opening_regions"):
                f.c.window_opening_regions = []
            f.c.window_opening_regions.append((allowed, -normal))
            f.features["authorised_diagonal_sash_returns"] += close_diagonal_pane_corners(
                f.c, allowed, inward=-normal,
            )
            groups += 1
        else:
            f.features["openings_omitted_at_grade_or_roof"] += 1
    status = row["evidence_status"]
    key = ("unobserved_proposed_sash_groups" if status.startswith("interpreted")
           else "historically_evidenced_sash_groups" if "historical" in status
           else "current_pitch_photo_sash_groups")
    f.features[key] += groups
    f.features[row["side"] + "_sash_groups"] += groups


def _door(f, door, pediment=False):
    side, at, centre = door.get("side", "north"), door["at_m"], door["centre_m"]
    floor, width = door["floor_navd88_m"], door["width_m"]
    top = floor + door["height_m"]
    sheet, body, normal, along, _ = _wall_sheet(f, side, at, centre, width, top)
    base, upper = f.height_y(floor), f.height_y(top)
    choices = []
    for x, z, iz, ix in f.each_column(sheet):
        for y in range(base, upper):
            f.c.set(x, y, z, "pale_oak_planks", "facade")
        choices.append((abs(float(along[iz, ix]) - centre), x, z))
    if not choices:
        raise ValueError("Rolfe door does not intersect its specified actual wall")
    _, x, z = min(choices)
    for half, dy in (("lower", 0), ("upper", 1)):
        f.c.set(x, base + dy, z, "pale_oak_door", "door", {
            "half": half, "facing": _facing(normal), "hinge": "left",
            "open": "false", "powered": "false",
        })
    f.features["operable_reference_doors"] += 1
    if not pediment:
        return

    surround = door["surround_width_m"]
    trim, body, normal, along, _ = _wall_sheet(f, side, at, centre, surround, top)
    tangent = f.n if side in {"east", "west"} else f.t
    crown = f.height_y(door["pediment_top_navd88_m"])
    # The triangular head replaces existing front-wall cells.  It does not
    # create a white projecting box or opaque full-height window-like jambs.
    for x, z, iz, ix in f.each_column(trim):
        d = float(along[iz, ix]) - centre
        back = _back_cell(f, x, z, trim, body, normal)
        y = crown - 1 if abs(d) < surround * 0.22 else crown - 2
        if abs(d) < surround * 0.22:
            f.c.set(x, y, z, "quartz_slab", "trim", TOP)
        else:
            f.c.set(x, y, z, "quartz_stairs", "trim", {
                "facing": _facing(tangent * (-1 if d > 0 else 1)),
                "half": "bottom", "shape": "straight", "waterlogged": "false",
            })
        if back:
            f.c.set(back[0], y, back[1], "pale_oak_planks", "facade")
        # The lintel is narrow and continuously backed by the existing room.
        lintel = crown - 3
        f.c.set(x, lintel, z, "quartz_slab", "trim", TOP)
        if back:
            f.c.set(back[0], lintel, back[1], "pale_oak_planks", "facade")
    f.features["separate_triangular_pitch_pediments"] += 1


def _vent(f, vent):
    side = vent["side"]
    f.window_row(side, vent["at_m"], [vent["centre_m"]], vent["sill_navd88_m"],
                 vent["width_m"], vent["height_m"], shape="circle", lights=1)
    along, across = (f.v, f.u) if side in {"east", "west"} else (f.u, f.v)
    tangent = f.n if side in {"east", "west"} else f.t
    normal = f.t * -1 if side == "west" else f.n * -1
    mask = (abs(along - vent["centre_m"]) < 0.85) & (abs(across - vent["at_m"]) < 0.8)
    middle = vent["sill_navd88_m"] + vent["height_m"] / 2
    for x, z, iz, ix in f.each_column(mask):
        d = float(along[iz, ix]) - vent["centre_m"]
        if abs(d) < 0.16:
            continue
        for y in range(f.height_y(middle - 0.7), f.height_y(middle + 0.7) + 1):
            state = f.c.palette[f.c.get(x, y, z)]["Name"]
            if state != "minecraft:quartz_block":
                continue
            f.c.set(x, y, z, "quartz_stairs", "trim", {
                "facing": _facing(tangent * (1 if d > 0 else -1)),
                "half": "top" if (y + 0.5) / 2 - f.offset >= middle else "bottom",
                "shape": "straight", "waterlogged": "false",
            })
            dx, dz = _inward(normal)
            bx, bz = x + dx, z + dz
            if _body(f)[bz - f.c.z_min, bx - f.c.x_min] and not f.c.get(bx, y, bz):
                f.c.set(bx, y, bz, "bricks", "facade")
    f.features[side + "_diamond_attic_vents"] += 1


def _fascia(f, p):
    body = _body(f)
    edge = body & ~binary_erosion(body)
    for verge in p.get("photographed_recessed_roof_verges", []):
        a, b = verge["ends_m"]
        observed, _, _, _, _ = _wall_sheet(
            f, verge["side"], verge["at_m"], (a + b) / 2, b - a,
            verge["minimum_roof_navd88_m"],
        )
        edge |= observed
        f.features["photographed_recessed_gable_verge_columns"] += int(observed.sum())
    aligned = np.zeros_like(body)
    bands = []
    for band in p["eave_bands"]:
        a, b = band["ends_m"]
        minimum = band["top_navd88_m"] - 0.25
        mask, _, normal, _, _ = _wall_sheet(
            f, band["side"], band["at_m"], (a + b) / 2, b - a, minimum,
        )
        aligned |= mask
        bands.append((band, mask, normal))
    for x, z, iz, ix in f.each_column(edge & ~aligned):
        levels = np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("roof"))
        if not levels.size:
            continue
        y = int(levels[-1]) + f.c.y_min
        original = f.c.palette[f.c.get(x, y, z)]
        name = original["Name"]
        block = "quartz_stairs" if name.endswith("_stairs") else "quartz_slab" if name.endswith("_slab") else "quartz_block"
        f.c.set(x, y, z, block, "trim", original.get("Properties"))
        # At a gable/verge this substrate is the visible top of the masonry
        # wall.  Keep its support, but do not expose an invented thick gray
        # stripe below the photographed thin pale fascia.
        if f.c.roles[y - 1 - f.c.y_min, iz, ix] == ROLES.index("roof"):
            f.c.set(x, y - 1, z, "bricks", "facade")
            f.features["gable_substrate_backing_recoloured_brick"] += 1
        f.features["source_shaped_gable_and_hip_verge_cells"] += 1
    for band, mask, normal in bands:
        half = round((band["top_navd88_m"] + f.offset) * f.c.scale * 2)
        y = half // 2 - 1 if half % 2 == 0 else half // 2
        properties = TOP if half % 2 == 0 else BOTTOM
        for x, z, iz, ix in f.each_column(mask):
            source_half = math.floor((float(f.r.heights[iz, ix]) + f.offset) * 4 + 0.5)
            if half > source_half:
                continue
            for lower in range(f.height_y(band["top_navd88_m"] - 1.5), y):
                if f.c.roles[lower - f.c.y_min, iz, ix] == ROLES.index("roof"):
                    f.c.set(x, lower, z, "bricks", "facade")
                    f.features["visible_roof_substrate_replaced_by_brick"] += 1
            dx, dz = _inward(normal)
            for depth in (1, 2):
                bx, bz = x + dx * depth, z + dz * depth
                bi, bj = bz - f.c.z_min, bx - f.c.x_min
                if body[bi, bj] and (y + 1) / 2 - f.offset <= f.r.heights[bi, bj] + 0.125:
                    f.c.set(bx, y, bz, "bricks", "facade")
                    f.features["solid_fascia_backing_cells"] += 1
            roof_y = source_half // 2 - 1 if source_half % 2 == 0 else source_half // 2
            # A quarter-metre board can share the source roof's voxel.  In
            # that case keep its original physical top; never lower the
            # measured surface merely to force a constant paint-band height.
            cell_properties = properties
            if roof_y == y and half != source_half:
                cell_properties = TOP if source_half % 2 == 0 else BOTTOM
                f.features["fascia_cells_preserving_source_surface_top"] += 1
            f.c.set(x, y, z, "quartz_slab", "trim", cell_properties)
            f.features["level_painted_eave_board_cells"] += 1


def _chimney(f, p):
    for chimney in p["chimneys"]:
        bounds = chimney["bounds_uv_m"]
        footprint = f.local_mask(bounds) & _body(f)
        base = float(f.r.heights[footprint].min()) - 0.5
        top = chimney["top_navd88_m"]
        f.box(bounds, base, top - 0.25, "bricks", "facade", mask=footprint)
        f.box(bounds, top - 0.5, top, "brick_slab", "trim", TOP, mask=footprint)
        f.features["photo_interpreted_central_chimney_clusters"] += 1


def _closure(f):
    body = _body(f)
    edge = body & ~binary_erosion(body)
    checked = repaired = 0
    for x, z, iz, ix in f.each_column(edge):
        half = math.floor((float(f.r.heights[iz, ix]) + f.offset) * 4 + 0.5)
        high = half // 2 - 1 if half % 2 == 0 else half // 2
        low = max(f.c.ground_at(x, z) + 1, f.height_y(62.1))
        for y in range(low, high):
            checked += 1
            if not f.c.get(x, y, z):
                f.c.set(x, y, z, "bricks", "facade")
                repaired += 1
    f.features["outer_wall_cells_audited"] = checked
    f.features["unintended_outer_wall_air_cells_closed"] = repaired


def _complete_embedded_return_caps(f):
    """Close partial inner caps met by the added diagonal glass returns.

    These caps are inside the same authorised sash region, behind its outer
    panes. Completing them keeps the thin external frame and every pane in
    place while closing both the pane contact and the remaining half-void.
    """
    repaired = set()
    for allowed, _ in getattr(f.c, "window_opening_regions", []):
        for x, y, z in allowed:
            if not f.c.palette[f.c.get(x, y, z)]["Name"].endswith("_pane"):
                continue
            for dy, need in ((-1, "top"), (1, "bottom")):
                cap = (x, y + dy, z)
                if cap not in allowed:
                    continue
                state = f.c.palette[f.c.get(*cap)]
                if not state["Name"].endswith("_slab"):
                    continue
                if state.get("Properties", {}).get("type") in {need, "double"}:
                    continue
                iy, iz, ix = cap[1] - f.c.y_min, cap[2] - f.c.z_min, cap[0] - f.c.x_min
                if f.c.roles[iy, iz, ix] != ROLES.index("trim"):
                    raise ValueError("Rolfe cap completion would modify a non-trim cell")
                f.c.set(*cap, "quartz_block", "trim")
                repaired.add(cap)
    f.features["completed_embedded_diagonal_return_caps"] = len(repaired)


def _close_diagonal_jamb_returns(f, regions):
    """Join a free sash end to its existing jamb through one interior corner.

    The photographed outer sheet is unchanged. Any extension beyond its
    centre-sampled width is a single empty corner behind the adjacent intact
    jamb, inside the measured body. No masonry, roof, or pane is overwritten.
    """
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    body = _body(f)

    def value(position):
        return f.c.palette[f.c.get(*position)]

    def inside(position):
        x, y, z = position
        iz, ix = z - f.c.z_min, x - f.c.x_min
        return body[iz, ix] and (y + 1) / 2 - f.offset <= f.r.heights[iz, ix] + 0.125

    def frame(position):
        x, y, z = position
        name = value(position)["Name"]
        role = f.c.roles[y - f.c.y_min, z - f.c.z_min, x - f.c.x_min]
        return role in (ROLES.index("facade"), ROLES.index("trim")) and not name.endswith(
            ("_slab", "_stairs", "_pane", "_door", "_trapdoor", "_fence", "_wall"))

    def joins(position):
        x, y, z = position
        return sum(frame((x + dx, y, z + dz)) or value((x + dx, y, z + dz))["Name"].endswith("_pane")
                   for dx, dz in directions)

    for _ in range(3):
        changed = 0
        for allowed, inward in regions:
            for x, y, z in sorted(allowed):
                if not value((x, y, z))["Name"].endswith("_pane") or joins((x, y, z)) >= 2:
                    continue
                # A diagonal sash turn can meet an embedded inner head/sill
                # slab. Completing that concealed cell retains a thin outer
                # trim surface and provides an actual full contact face.
                for dx, dz in directions:
                    adjacent = (x + dx, y, z + dz)
                    hidden = dx * inward[0] + dz * inward[1] >= -1e-6
                    ai, az, ax = y - f.c.y_min, adjacent[2] - f.c.z_min, adjacent[0] - f.c.x_min
                    if (inside(adjacent) and (adjacent in allowed or hidden)
                            and value(adjacent)["Name"] == "minecraft:quartz_slab"
                            and f.c.roles[ai, az, ax] == ROLES.index("trim")):
                        f.c.set(*adjacent, "quartz_block", "trim")
                        f.features["completed_embedded_horizontal_frame_caps"] += 1
                        changed += 1
                        break
                if joins((x, y, z)) >= 2:
                    continue
                candidates = []
                for dx in (-1, 1):
                    for dz in (-1, 1):
                        jamb = (x + dx, y, z + dz)
                        if not frame(jamb):
                            continue
                        corners = ((x + dx, y, z), (x, y, z + dz))
                        if any(frame(corner) or value(corner)["Name"].endswith("_pane") for corner in corners):
                            continue
                        for corner in corners:
                            displacement = (corner[0] - x) * inward[0] + (corner[2] - z) * inward[1]
                            if not f.c.get(*corner) and inside(corner) and displacement >= -1e-6:
                                candidates.append((displacement, corner))
                if candidates:
                    _, corner = max(candidates)
                    allowed.add(corner)
                    f.c.set(*corner, "white_stained_glass_pane", "window", PANE_PROPS)
                    f.features["interior_pane_to_jamb_corner_returns"] += 1
                    changed += 1
        connect_window_panes(f.c)
        if not changed:
            break

    # New return columns have solid concealed caps rather than unsupported
    # half slabs. Existing exterior masonry and glass remain untouched.
    checked = set()
    for allowed, _ in regions:
        for position in sorted(allowed):
            if position in checked or not value(position)["Name"].endswith("_pane"):
                continue
            checked.add(position)
            x, y, z = position
            for dy, need in ((-1, "top"), (1, "bottom")):
                cap = (x, y + dy, z)
                state = value(cap)
                name = state["Name"]
                if name == "minecraft:air":
                    if not inside(cap):
                        raise ValueError(f"Rolfe return cap would leave its measured envelope: {cap}")
                    f.c.set(*cap, "bricks", "facade")
                    f.features["concealed_return_cap_backing_cells"] += 1
                elif name == "minecraft:quartz_slab" and state.get("Properties", {}).get("type") != "double":
                    ci, cz, cx = cap[1] - f.c.y_min, cap[2] - f.c.z_min, cap[0] - f.c.x_min
                    if inside(cap) and f.c.roles[ci, cz, cx] == ROLES.index("trim"):
                        f.c.set(*cap, "quartz_block", "trim")
                        f.features["completed_return_perimeter_caps"] += 1
    connect_window_panes(f.c)
    report = pane_perimeter_report(f.c)
    f.features["horizontal_frame_review_candidates"] = report["fewer_than_two_horizontal_joins"]
    f.features["vertical_frame_review_candidates"] = report["vertical_air_or_reversed_slab_contacts"]


def build_details(f, p):
    first_region = len(getattr(f.c, "window_opening_regions", []))
    _basements(f, p)
    for row in p["window_rows"]:
        _sash_row(f, row)
    for portal in p["pitch_portals"]:
        _door(f, portal, pediment=True)
    _door(f, p["rear_door"])
    for vent in p["attic_vents"]:
        _vent(f, vent)
    _fascia(f, p)
    _chimney(f, p)
    f.site_surface([(15.25, -0.8), (34.5, -0.8), (34.5, 1.75), (15.25, 1.75)],
                   68.1, "bricks", "brick_slab")
    for a, b in ((0.1, 15.25), (34.5, 49.8)):
        f.site_surface([(a, -0.1), (b, -0.1), (b, 1.75), (a, 1.75)], 68.0)
    f.floor_plate(71.0)
    _closure(f)
    # The final pass is still restricted to each original aperture's saved
    # authorised cells; later fascia/vent work cannot leave open glass joints.
    for allowed, inward in getattr(f.c, "window_opening_regions", []):
        f.features["final_authorised_corner_returns"] += close_diagonal_pane_corners(
            f.c, allowed, inward=inward,
        )
    _complete_embedded_return_caps(f)
    _close_diagonal_jamb_returns(f, f.c.window_opening_regions[first_region:])
    f.features["source_major_roof_faces_retained"] = len(p["roof_interpretation"]["major_faces"])
    f.features["closed_source_front_block_preserved"] = 1
    f.features["lower_rear_hip_source_faces_retained"] = 3
