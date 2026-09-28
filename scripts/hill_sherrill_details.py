"""Sherrill Guest House: four source faces and individually bounded dormers.

The Sol source packet distinguishes two observed north dormer fronts from
three south peak tips. Lower openings and doors are explicit proposals.
All dimensions use the original metric UV frame and NAVD88 elevations.
"""

import math
from dataclasses import replace

import numpy as np
from scipy.ndimage import binary_erosion

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_reference_details import roof_patch
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_window_frames import close_diagonal_pane_corners, pane_perimeter_report


TOP = {"type": "top", "waterlogged": "false"}
BOTTOM = {"type": "bottom", "waterlogged": "false"}


def prepare_roof(r, f, p):
    """Keep every measured face; add only five packet-bounded max patches."""
    source = r
    for dormer in p["dormers"]:
        r = roof_patch(r, f, dormer["bounds_uv_m"],
                       eave=dormer["eave_navd88_m"], ridge=dormer["ridge_navd88_m"],
                       ridge_axis="v", material="deepslate_tile", combine="max")
    # Centre sampling at the retained campus angle can leave a one-cell
    # finger ahead of a two-cell dormer front. Its full quartz sides mask
    # the entire sash in the reference direction. Omit only such authored
    # front fingers, restoring the original source face at that column.
    # The metric rectangle, eave, ridge and all measured roof values stay.
    if p.get("dormer_raster_refinement", {}).get("omit_single_neighbor_front_spurs"):
        omitted = np.zeros_like(r.footprint_mask)
        for dormer in p["dormers"]:
            bounded = f.local_mask(dormer["bounds_uv_m"]) & source.footprint_mask
            raised = bounded & (r.heights > source.heights + 1e-7)
            neighbors = sum(np.roll(raised, step, axis=axis).astype(np.uint8)
                            for axis in (0, 1) for step in (-1, 1))
            at = dormer["bounds_uv_m"][1 if dormer["side"] == "north" else 3]
            omitted |= raised & (neighbors == 1) & (abs(f.v - at) <= .55)
        if omitted.any():
            values = {}
            for name in ("heights", "gradient_x", "gradient_z", "face_indices"):
                values[name] = getattr(r, name).copy()
                values[name][omitted] = getattr(source, name)[omitted]
            r = replace(r, **values)
    if p.get("dormer_raster_refinement", {}).get("pointed_front_caps"):
        heights = r.heights.copy()
        records = []
        for dormer, record in zip(p["dormers"], r.authored_roof_patches):
            front = _dormer_front_mask(f, r, source, dormer)
            if dormer.get("single_front_apex"):
                levels, apex = _front_gable_levels(f, front, dormer)
                for iz, ix, level in levels:
                    heights[iz, ix] = level
                updated = dict(record)
                updated["raster_front_cap_refinement"] = {
                    "shape": "one occupied centre apex with lower inward-rising stair shoulders",
                    "apex_xz_blocks": [int(apex[1] + f.c.x_min), int(apex[0] + f.c.z_min)],
                    "columns": [{"xz_blocks": [ix + f.c.x_min, iz + f.c.z_min],
                                 "physical_top_navd88_m": level} for iz, ix, level in levels],
                }
                updated["source_control_exception"] = p["north_dormer_control_addendum"]
                records.append(updated)
                continue
            # Paired inward-rising stairs form a small gable instead of a
            # flat white beam. Their common top never exceeds the authored
            # ridge: north 75.50 m, south 76.00 m at this half-metre scale.
            top = math.floor((dormer["ridge_navd88_m"] + f.offset) * 2) / 2 - f.offset
            heights[front] = top
            updated = dict(record)
            updated["raster_front_cap_refinement"] = {
                "physical_top_navd88_m": top,
                "columns_xz_blocks": [[x, z] for x, z, _, _ in f.each_column(front)],
                "shape": "paired inward-rising quartz stairs, with full head backing",
            }
            updated["omitted_single_neighbor_front_spurs_xz_blocks"] = [
                [x, z] for x, z, _, _ in f.each_column(
                    f.local_mask(dormer["bounds_uv_m"]) & omitted)]
            records.append(updated)
        r = replace(r, heights=heights, authored_roof_patches=tuple(records))
    return r


def _source_roof(f, p):
    bounds = (f.c.x_min / 2, f.c.z_min / 2,
              (f.c.x_min + f.c.data.shape[2]) / 2, (f.c.z_min + f.c.data.shape[1]) / 2)
    return rasterize_roof(load_measured_building(parent_id=p["parent_id"]), bounds, resolution=0.5)


def _normal(f, side):
    return (f.t * (1 if side == "east" else -1) if side in {"east", "west"}
            else f.n * (1 if side == "south" else -1))


def _inward(normal):
    return (-int(np.sign(normal[0])), 0) if abs(normal[0]) > abs(normal[1]) else (0, -int(np.sign(normal[1])))


def _facing(normal):
    return ("east" if normal[0] > 0 else "west") if abs(normal[0]) > abs(normal[1]) else ("south" if normal[1] > 0 else "north")


def _dormer_front_mask(f, r, source, dormer):
    bounded = f.local_mask(dormer["bounds_uv_m"]) & source.footprint_mask
    raised = bounded & (r.heights > source.heights + 1e-7)
    neighbors = sum(np.roll(raised, step, axis=axis).astype(np.uint8)
                    for axis in (0, 1) for step in (-1, 1))
    exposed = np.zeros_like(raised)
    normal = _normal(f, dormer["side"])
    for axis, component in ((1, normal[0]), (0, normal[1])):
        if abs(component) > .05:
            exposed |= ~np.roll(raised, -int(np.sign(component)), axis=axis)
    at = dormer["bounds_uv_m"][1 if dormer["side"] == "north" else 3]
    front = raised & exposed & (neighbors >= 2) & (abs(f.v - at) <= .55)
    if f.p.get("dormer_raster_refinement", {}).get("compact_gable_heads"):
        # A rotated front includes the start of a cheek behind one sash end.
        # Do not carry the pale tympanum round that L: it becomes a cross cap
        # from the source bearing. Use each X column's outermost front cell.
        for ix in np.flatnonzero(front.any(axis=0)):
            rows = np.flatnonzero(front[:, ix])
            keep = rows[-1] if dormer["side"] == "south" else rows[0]
            front[rows, ix] = False
            front[keep, ix] = True
    return front


def _front_gable_levels(f, front, dormer):
    """Preserve a single ridge sample instead of flattening narrow gable tops.

    The source addendum permits the 1.75 m front to quantize to 1.5–2 m.
    At this fixed campus bearing both revised northern fronts have three
    contiguous columns. Their central occupied apex reaches the retained
    ridge; the two stair shoulders top out half a metre lower, with their
    outward lower tread a further quarter metre below that.
    """
    centre = (dormer["bounds_uv_m"][0] + dormer["bounds_uv_m"][2]) / 2
    points = [(int(iz), int(ix)) for iz, ix in zip(*np.nonzero(front))]
    if len(points) < 3:
        raise ValueError("The revised north gable needs at least three occupied front columns")
    apex = min(points, key=lambda q: abs(float(f.u[q]) - centre))
    ridge = math.floor((dormer["ridge_navd88_m"] + f.offset) * 2) / 2 - f.offset
    levels = [(iz, ix, ridge - abs(ix - apex[1]) * .5) for iz, ix in points]
    return levels, apex


def _sheet(f, side, at, centre, width, top, region=None, tolerance=1.35):
    end = side in {"east", "west"}
    along, across = (f.v, f.u) if end else (f.u, f.v)
    normal = _normal(f, side)
    body = f.r.footprint_mask if region is None else region
    exposed = np.zeros_like(body)
    neighbors = np.zeros(body.shape, dtype=np.uint8)
    for axis in (0, 1):
        for step in (-1, 1):
            neighbors += np.roll(body, step, axis=axis)
    for axis, component in ((1, normal[0]), (0, normal[1])):
        if abs(component) > 0.05:
            exposed |= ~np.roll(body, -int(np.sign(component)), axis=axis)
    aperture = (abs(along - centre) <= width / 2) & (abs(across - at) <= tolerance)
    # Height clipping follows the actual wall; a lower source roof does not
    # create a new exterior wall contour partway across its pitched surface.
    sheet = body & exposed & aperture & (f.r.heights >= top) & (neighbors >= 2)
    return sheet, body, normal, along, aperture


def _sash(f, row, centre, region=None):
    sill, height = row["sill_navd88_m"], row["height_m"]
    sheet, body, normal, _, aperture = _sheet(
        f, row["side"], row["at_m"], centre, row["width_m"], sill + height,
        region=region, tolerance=row.get("surface_tolerance_m", 1.35))
    y0 = math.ceil((sill + f.offset) * 2 - .5 - 1e-9)
    rows = max(2, round(height * 2))
    dx, dz = _inward(normal)
    placed = 0
    for x, z, iz, ix in f.each_column(sheet):
        outside = np.floor(np.array([x + .5, z + .5]) + normal * 2).astype(int)
        grade = f.c.ground_at(int(outside[0]), int(outside[1]))
        for y in range(y0, y0 + rows):
            if y > grade:
                f.c.set(x, y, z, f.p["window_reveal"]["glass_block"], "window", PANE_PROPS)
                placed += 1
        # Thin sill/head slabs are outside the glazed height, behind the
        # original masonry frame; they never fill half the transparent sash.
        bx, bz = x + dx, z + dz
        for _ in range(2):
            if not sheet[bz - f.c.z_min, bx - f.c.x_min]:
                break
            bx, bz = bx + dx, bz + dz
        if body[bz - f.c.z_min, bx - f.c.x_min]:
            for y, props in ((y0 - 1, TOP), (y0 + rows, BOTTOM)):
                if y > grade and not f.c.get(bx, y, bz) and (y + 1) / 2 - f.offset <= f.r.heights[bz - f.c.z_min, bx - f.c.x_min] + .125:
                    f.c.set(bx, y, bz, "quartz_slab", "trim", props)
    if placed:
        allowed = {(x, y, z) for x, z, _, _ in f.each_column(body & aperture)
                   for y in range(y0, y0 + rows)}
        if not hasattr(f.c, "window_opening_regions"):
            f.c.window_opening_regions = []
        f.c.window_opening_regions.append((allowed, -normal))
        f.features["authorised_initial_sash_returns"] += close_diagonal_pane_corners(f.c, allowed, inward=-normal)
    else:
        f.features["proposed_openings_clipped_by_grade_or_local_roof"] += 1
    return bool(placed)


def _door(f, door):
    floor, top = door["floor_navd88_m"], door["floor_navd88_m"] + door["height_m"]
    sheet, _, normal, along, _ = _sheet(f, door["side"], door["at_m"], door["centre_m"], door["width_m"], top)
    choices = []
    base, high = f.height_y(floor), f.height_y(top)
    for x, z, iz, ix in f.each_column(sheet):
        for y in range(base, high):
            f.c.set(x, y, z, "pale_oak_planks", "facade")
        choices.append((abs(float(along[iz, ix]) - door["centre_m"]), x, z))
    if not choices:
        raise ValueError("Sherrill's proposed door does not meet its actual measured wall")
    _, x, z = min(choices)
    for half, dy in (("lower", 0), ("upper", 1)):
        f.c.set(x, base + dy, z, "pale_oak_door", "door", {
            "half": half, "facing": _facing(normal), "hinge": "left", "open": "false", "powered": "false"})
    f.features["proposed_operable_doors"] += 1


def _dormers(f, p, source):
    for index, dormer in enumerate(p["dormers"]):
        mask = f.local_mask(dormer["bounds_uv_m"]) & source.footprint_mask
        raised = mask & (f.r.heights > source.heights + 1e-7)
        edge = raised & ~binary_erosion(raised)
        pale_front = (_dormer_front_mask(f, f.r, source, dormer)
                      if dormer.get("single_front_apex") else np.zeros_like(edge))
        for x, z, iz, ix in f.each_column(edge):
            low = math.floor((float(source.heights[iz, ix]) + f.offset) * 2)
            top = math.floor((float(f.r.heights[iz, ix]) + f.offset) * 4 + .5)
            roof_y = top // 2 - 1 if top % 2 == 0 else top // 2
            for y in range(low, roof_y):
                if pale_front[iz, ix]:
                    f.c.set(x, y, z, "quartz_block", "facade")
                    f.features["bounded_pale_north_front_cells"] += 1
                else:
                    f.c.set(x, y, z, "deepslate_tiles", "roof")
                    f.features["dark_dormer_front_and_cheek_cells"] += 1
        u0, v0, u1, v1 = dormer["bounds_uv_m"]
        row = {"side": dormer["side"], "at_m": v0 if dormer["side"] == "north" else v1,
               "width_m": dormer["window_width_m"], "height_m": dormer["window_height_m"],
               "sill_navd88_m": dormer["window_sill_navd88_m"], "surface_tolerance_m": .55}
        visible = _sash(f, row, (u0 + u1) / 2, region=raised)
        f.features["observed_north_dormer_front_windows" if dormer["side"] == "north"
                   else "peak_only_south_dormer_window_proposals"] += int(visible)
        f.features["separately_bounded_dormer_roof_appendages"] += 1


def _exposed_floor_edge(f):
    """The exposed edge of the floor plate is brick, not a gray wall band."""
    edge = f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    y = f.height_y(f.g["entrance_floor_navd88_m"]) - 1
    for x, z, iz, ix in f.each_column(edge):
        if f.c.roles[y - f.c.y_min, iz, ix] == ROLES.index("floor"):
            f.c.set(x, y, z, "bricks", "facade")
            f.features["exposed_floor_plate_edge_clad_in_brick"] += 1


def _fascia(f):
    """Continue the dark source roof to its edge without a quartz tooth fringe.

    The photographed fine fascia is sub-voxel in thickness. A full roof-edge
    replacement exaggerated it to half a metre. Keep the measured skin and
    its original substrate; only the compact dormer rakes receive pale caps.
    """
    edge = f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    for x, z, iz, ix in f.each_column(edge):
        roof = np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("roof"))
        if not roof.size:
            continue
        y = int(roof[-1]) + f.c.y_min
        f.features["continuous_measured_dark_roof_edge_columns"] += 1


def _finish_dormer_frames(f, p, source):
    """Dark cheeks merge into the roof; pale material is confined to the rake."""
    for dormer in p["dormers"]:
        bounded = f.local_mask(dormer["bounds_uv_m"]) & source.footprint_mask
        raised = bounded & (f.r.heights > source.heights + 1e-7)
        u0, v0, u1, v1 = dormer["bounds_uv_m"]
        at = v0 if dormer["side"] == "north" else v1
        front, _, _, _, _ = _sheet(f, dormer["side"], at, (u0 + u1) / 2,
                                   u1 - u0, 70, region=raised, tolerance=.55)
        for x, z, iz, ix in f.each_column(bounded):
            low = math.floor((float(source.heights[iz, ix]) + f.offset) * 2)
            half = math.floor((float(f.r.heights[iz, ix]) + f.offset) * 4 + .5)
            roof_y = half // 2 - 1 if half % 2 == 0 else half // 2
            for y in range(low, roof_y):
                if (f.c.roles[y - f.c.y_min, iz, ix] == ROLES.index("facade")
                        and f.c.palette[f.c.get(x, y, z)]["Name"] == "minecraft:bricks"):
                    f.c.set(x, y, z, "deepslate_tiles", "roof")
                    f.features["dark_dormer_caps_recoloured_after_perimeter_repair"] += 1
            if front[iz, ix]:
                state = f.c.palette[f.c.get(x, roof_y, z)]
                if f.c.roles[roof_y - f.c.y_min, iz, ix] != ROLES.index("roof"):
                    continue
                name = state["Name"]
                block = "quartz_stairs" if name.endswith("_stairs") else "quartz_slab" if name.endswith("_slab") else "quartz_block"
                f.c.set(x, roof_y, z, block, "trim", state.get("Properties"))
                f.features["pale_dormer_front_rake_cells"] += 1
        if p.get("dormer_raster_refinement", {}).get("pointed_front_caps"):
            cap_front = _dormer_front_mask(f, f.r, source, dormer)
            if dormer.get("single_front_apex"):
                levels, apex = _front_gable_levels(f, cap_front, dormer)
                for iz, ix, level in levels:
                    x, z = ix + f.c.x_min, iz + f.c.z_min
                    top = round((level + f.offset) * 2)
                    f.c.set(x, top - 2, z, "quartz_block", "trim")
                    if (iz, ix) == apex:
                        f.c.set(x, top - 1, z, "quartz_block", "trim")
                        f.features["single_occupied_north_gable_apex"] += 1
                    else:
                        f.c.set(x, top - 1, z, "quartz_stairs", "trim", {
                            "facing": "east" if ix < apex[1] else "west",
                            "half": "bottom", "shape": "straight", "waterlogged": "false"})
                        f.features["lower_north_gable_stair_shoulders"] += 1
                continue
            top = math.floor((dormer["ridge_navd88_m"] + f.offset) * 2)
            for x, z, iz, ix in f.each_column(cap_front):
                normal = f.t * (1 if f.u[iz, ix] < (u0 + u1) / 2 else -1)
                if p.get("dormer_raster_refinement", {}).get("compact_gable_heads"):
                    f.c.set(x, top - 2, z, "quartz_block", "trim")
                    f.features["compact_pale_dormer_tympanum_cells"] += 1
                f.c.set(x, top - 1, z, "quartz_stairs", "trim", {
                    "facing": _facing(normal), "half": "bottom", "shape": "straight", "waterlogged": "false"})
                f.features["paired_inward_rising_dormer_gable_stairs"] += 1


def _closure(f):
    edge = f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    checked = closed = 0
    for x, z, iz, ix in f.each_column(edge):
        half = math.floor((float(f.r.heights[iz, ix]) + f.offset) * 4 + .5)
        high = half // 2 - 1 if half % 2 == 0 else half // 2
        low = max(f.c.ground_at(x, z) + 1, f.height_y(f.g["entrance_floor_navd88_m"]))
        for y in range(low, high):
            checked += 1
            if not f.c.get(x, y, z):
                f.c.set(x, y, z, "bricks", "facade")
                closed += 1
    f.features["outer_wall_cells_checked"] = checked
    f.features["unintended_outer_wall_air_cells_closed"] = closed


def _close_diagonal_jamb_returns(f, regions):
    """Join a free sash end to its existing jamb through one interior corner.

    The photographed outer sheet is unchanged. Any extension beyond its
    centre-sampled width is a single empty corner behind the adjacent intact
    jamb, inside the measured body. No masonry, roof, or pane is overwritten.
    """
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    body = f.r.footprint_mask
    interior = binary_erosion(body)

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
        return role in (ROLES.index("facade"), ROLES.index("trim"), ROLES.index("roof")) and not name.endswith(
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
                            # A jagged source corner can turn away from the
                            # average facade normal. A cell surrounded on all
                            # four sides by the original body is still an
                            # interior reveal, irrespective of that vector.
                            fully_inside = interior[corner[2] - f.c.z_min, corner[0] - f.c.x_min]
                            if not f.c.get(*corner) and inside(corner) and (displacement >= -1e-6 or fully_inside):
                                candidates.append((displacement, corner))
                # A rotated dormer cheek can sit two cardinal cells from a
                # sash turn, leaving one empty reveal cell between them.
                # Join that existing cheek only through the interior cell.
                for dx, dz in directions:
                    corner = (x + dx, y, z + dz)
                    jamb = (x + 2 * dx, y, z + 2 * dz)
                    displacement = dx * inward[0] + dz * inward[1]
                    if (not f.c.get(*corner) and inside(corner) and frame(jamb)
                            and displacement >= -1e-6):
                        candidates.append((displacement, corner))
                if candidates:
                    _, corner = max(candidates)
                    # Keep the return transparent over the opening's full
                    # height; a mid-sash opaque cap would hide the glazing.
                    for cy in sorted({position[1] for position in allowed}):
                        extension = (corner[0], cy, corner[2])
                        if not f.c.get(*extension) and inside(extension):
                            allowed.add(extension)
                            f.c.set(*extension, f.p["window_reveal"]["glass_block"], "window", PANE_PROPS)
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
                        raise ValueError(f"Sherrill return cap would leave its measured envelope: {cap}")
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


def _smooth_measured_wall_steps(f, p):
    """Chamfer only convex voxel corners of the four measured straight planes.

    Grid rotation requires one regular step about every four blocks. A brick
    stair removes the outward upper quadrant at those tips; the inward face
    always contacts full brick. No cell is added outside the source mask and
    the real north setback is excluded from this operation. Complete solid
    window jambs, heads and sills take precedence over this surface shaping.
    """
    body = f.r.footprint_mask
    if not p["facade_plane_refinement"].get("chamfer_convex_tips", True):
        f.features["regular_measured_wall_grid_preserved"] = 1
        return
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for segment in p["facade_plane_refinement"]["segments_uv_m"]:
        a, b = np.array(segment["from"]), np.array(segment["to"])
        south = segment["id"] == "south_main"
        slope = (b[1] - a[1]) / (b[0] - a[0])
        plane = a[1] + slope * (f.u - a[0])
        distance = (f.v - plane) * (-1 if south else 1)
        # Exclude measured segment ends/returns. The corner's centre is inside
        # the exact footprint and close to the measured line, never roof-led.
        candidates = body & (f.u > a[0] + .3) & (f.u < b[0] - .3) & (distance >= 0) & (distance < .15)
        normal = _normal(f, "south" if south else "north")
        dx, dz = _inward(normal)
        for x, z, iz, ix in f.each_column(candidates):
            exterior = [(ex, ez) for ex, ez in directions if not body[iz + ez, ix + ex]]
            if len(exterior) != 2 or not body[iz + dz, ix + dx]:
                continue
            top = math.floor((float(f.r.heights[iz, ix]) + f.offset) * 2) - 2
            for y in range(f.c.ground_at(x, z) + 1, top):
                if f.c.palette[f.c.get(x, y, z)]["Name"] != "minecraft:bricks":
                    continue
                neighbors = [(x + ex, y, z + ez) for ex, ez in directions]
                neighbors += [(x, y - 1, z), (x, y + 1, z)]
                if any(f.c.palette[f.c.get(*q)]["Name"].endswith(("_pane", "_door")) for q in neighbors):
                    continue
                behind = (x + dx, y, z + dz)
                state = f.c.palette[f.c.get(*behind)]
                if state["Name"] not in {"minecraft:air", "minecraft:bricks"}:
                    continue
                f.c.set(*behind, "bricks", "facade")
                f.c.set(x, y, z, "brick_stairs", "facade", {
                    "facing": _facing(-normal), "half": "bottom",
                    "shape": "straight", "waterlogged": "false"})
                f.features["inward_backed_brick_stair_corner_cells"] += 1


def build_details(f, p):
    first_region = len(getattr(f.c, "window_opening_regions", []))
    source = _source_roof(f, p)
    _dormers(f, p, source)
    for row in p["window_rows"]:
        for centre in row["centres_m"]:
            f.features["unobserved_wall_sash_proposals_built"] += int(_sash(f, row, centre))
    for door in p["doors"]:
        _door(f, door)
    _fascia(f)
    for level in p["geometry"]["upper_floor_plates_navd88_m"]:
        f.floor_plate(level)
    _exposed_floor_edge(f)
    _closure(f)
    _close_diagonal_jamb_returns(f, f.c.window_opening_regions[first_region:])
    _finish_dormer_frames(f, p, source)
    _smooth_measured_wall_steps(f, p)
    f.features["measured_source_roof_faces_retained"] = 4
