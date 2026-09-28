"""Foster Dormitory: measured T roof and separately evidenced facade parts.

All dimensions are metres in Foster's own UV frame and NAVD88.  The school
drone's pitch view is the observed facade; the rear opening schedule is an
explicit, editable interpretation rather than a claim of surveyed apertures.
"""

from dataclasses import replace
import math

import numpy as np
from scipy.ndimage import binary_erosion

from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_reference_details import roof_patch
from campus_window_frames import close_diagonal_pane_corners, pane_perimeter_report


SLAB_TOP = {"type": "top", "waterlogged": "false"}
SLAB_BOTTOM = {"type": "bottom", "waterlogged": "false"}


def prepare_roof(r, f, p):
    # These three individually identified source faces are at measured pitch
    # grade, not building roofs.  No high plane is removed or flattened.
    terrace = np.isin(r.face_indices, p["roof_interpretation"]["ground_faces"])
    main = r.footprint_mask & ~terrace
    r = replace(
        r,
        footprint_mask=main,
        missing_mask=r.missing_mask & main,
        face_indices=np.where(main, r.face_indices, -1),
    )
    # The current photograph shows this shallow cornice/canopy independently
    # of the two door portals.  max preserves every overlapping measured plane.
    porch = p["central_canopy"]
    return roof_patch(
        r, f, porch["bounds_uv_m"],
        eave=porch["eave_navd88_m"], ridge=porch["ridge_navd88_m"],
        ridge_axis="u", material=p["materials"]["roof_family"], combine="max",
    )


def _rear_basement(f, p):
    """Hollow the rear daylight basement beneath the existing entrance floor."""
    body = f.r.footprint_mask & (f.r.heights > 72.5)
    inside = binary_erosion(body, iterations=2) & (f.v > 8.6)
    edge = body & ~binary_erosion(body, iterations=1) & (f.v > 5.5)
    level = p["geometry"]["basement_floor_navd88_m"]
    f.box((-1, 8.6, 51, 23), level, 68.1, "air", "air", mask=inside)
    f.box((-1, 8.6, 51, 23), level - 0.5, level, "smooth_stone", "floor", mask=inside)
    f.box((-1, 5.5, 51, 23), level, 68.1, "bricks", "facade", mask=edge)
    f.features["rear_daylight_basement_interior_columns"] = int(inside.sum())
    f.features["front_entrance_level_preserved_navd88_cm"] = 6810


def _surface(f, side, at, centre, width, top):
    """The actual outer wall voxels, never a second contour in front of it."""
    end = side in {"east", "west"}
    along, across = (f.v, f.u) if end else (f.u, f.v)
    normal = f.t * (1 if side == "east" else -1) if end else f.n * (1 if side == "south" else -1)
    body = f.r.footprint_mask & (f.r.heights >= top)
    exposed = np.zeros_like(body)
    for axis, component in [(1, normal[0]), (0, normal[1])]:
        if abs(component) > 0.1:
            exposed |= ~np.roll(body, -int(np.sign(component)), axis=axis)
    sheet = body & exposed & (abs(across - at) < 2.4) & (abs(along - centre) <= width / 2)
    return sheet, body, normal, along


def _inside_step(normal):
    return (-int(np.sign(normal[0])), 0) if abs(normal[0]) > abs(normal[1]) else (0, -int(np.sign(normal[1])))


def _sash_treatment(f, row, centre):
    trials = f.p.get("sash_comparison", {}).get("trials", [])
    for trial in trials:
        if row["side"] == trial["side"] and abs(centre - trial["centre_m"]) < 0.05 and abs(row["sill_navd88_m"] - trial["sill_navd88_m"]) < 0.05:
            return trial["treatment"]
    return f.p.get("sash_treatment", "thin_inner_slab")


def _thin_timber_sash(f, row, centre, y0, rows, sheet, body, normal, treatment):
    """Compare narrow vanilla timber profiles entirely behind intact glazing."""
    if treatment not in {"trapdoor_frame", "fence_sash"}:
        return
    dx, dz = _inside_step(normal)
    end = row["side"] in {"east", "west"}
    along = f.v if end else f.u
    tangent = f.n if end else f.t
    back = {}
    for x, z, iz, ix in f.each_column(sheet):
        bx, bz = x + dx, z + dz
        for _ in range(2):
            if not sheet[bz - f.c.z_min, bx - f.c.x_min]:
                break
            bx, bz = bx + dx, bz + dz
        if body[bz - f.c.z_min, bx - f.c.x_min]:
            back[(bx, bz)] = float(along[iz, ix])
    if not back:
        return
    left = min(back, key=lambda c: back[c])
    right = max(back, key=lambda c: back[c])
    if treatment == "trapdoor_frame":
        # Open trapdoors stand perpendicular to the facade as thin jamb strips.
        for cell, sign in [(left, -1), (right, 1)]:
            direction = tangent * sign
            facing = ("east" if direction[0] > 0 else "west") if abs(direction[0]) > abs(direction[1]) else ("south" if direction[1] > 0 else "north")
            for y in range(y0, y0 + rows):
                f.c.set(cell[0], y, cell[1], "pale_oak_trapdoor", "trim", {"facing": facing, "half": "bottom", "open": "true", "powered": "false", "waterlogged": "false"})
        for bx, bz in back:
            if (bx, bz) not in {left, right}:
                f.c.set(bx, y0 + rows // 2, bz, "pale_oak_trapdoor", "trim", {"facing": "north", "half": "bottom", "open": "false", "powered": "false", "waterlogged": "false"})
    else:
        # Fence post/rails are a timber-profile experiment, never an exterior
        # cage: every component is on the interior side of the pane sheet.
        directions = {"east": "false", "west": "false", "north": "false", "south": "false", "waterlogged": "false"}
        if abs(tangent[0]) > abs(tangent[1]):
            directions.update(east="true", west="true")
        else:
            directions.update(north="true", south="true")
        for bx, bz in back:
            f.c.set(bx, y0 + rows // 2, bz, "pale_oak_fence", "trim", directions)
    f.features["sash_treatment_" + treatment] += 1


def _post_sash(f, row, centre, y0, rows, sheet, body, normal):
    """Native-tested isolated timber shafts with pale glazing in the reveal."""
    dx, dz = _inside_step(normal)
    # One outer cell on each major-axis line provides a stable facade path.
    columns = {}
    for x, z, iz, ix in f.each_column(sheet):
        key = x if dz else z
        outward = x * normal[0] + z * normal[1]
        old = columns.get(key)
        if old is None or outward > old[0]:
            columns[key] = (outward, x, z)
    columns = [(v[1], v[2]) for _, v in sorted(columns.items())]
    if not columns:
        return
    if any(not body[z + dz - f.c.z_min, x + dx - f.c.x_min] for x, z in columns):
        # A concave end-wall corner can have no interior cell along this
        # dominant cardinal step. Keep the accepted flush white-pane method
        # there, instead of extending glazing beyond the actual footprint.
        f.features["white_pane_reveal_corner_fallbacks"] += 1
        return
    for x, z, iz, ix in f.each_column(sheet):
        for y in range(y0, y0 + rows):
            if f.c.roles[y - f.c.y_min, iz, ix] == ROLES.index("window"):
                f.c.set(x, y, z, "air", "air")
    inside = []
    for index, (x, z) in enumerate(columns):
        # These false connections are preserved for trim-role fences by the
        # shared connector.  They remain isolated shafts rather than cages.
        jamb = index in {0, len(columns) - 1}
        for y in range(y0, y0 + rows):
            if y <= f.c.ground_at(x, z):
                continue
            if jamb:
                f.c.set(x, y, z, "pale_oak_fence", "trim", PANE_PROPS)
            f.c.set(x + dx, y, z + dz, "white_stained_glass_pane", "window", PANE_PROPS)
        inside.append((x + dx, z + dz))
        # The upper quarter-metre frame stays within the original opening;
        # a new course above it would collide with the low east-wing eave.
        for depth, y, props in [
            (0, y0 - 1, SLAB_TOP), (1, y0 - 1, SLAB_TOP),
            (0, y0 + rows - 1, SLAB_TOP), (1, y0 + rows, SLAB_BOTTOM),
        ]:
            bx, bz = x + dx * depth, z + dz * depth
            if y > f.c.ground_at(bx, bz):
                f.c.set(bx, y, bz, "quartz_slab", "trim", props)
        for y in (y0 - 1, y0 + rows):
            # Masonry behind the half-block frame closes oblique sightlines.
            bx, bz = x + dx * 2, z + dz * 2
            if body[bz - f.c.z_min, bx - f.c.x_min] and f.c.get(bx, y, bz) == 0:
                f.c.set(bx, y, bz, "bricks", "facade")
    for a, b in zip(inside, inside[1:]):
        if abs(a[0] - b[0]) == 1 and abs(a[1] - b[1]) == 1:
            candidates = [q for q in [(a[0], b[1]), (b[0], a[1])] if body[q[1] - f.c.z_min, q[0] - f.c.x_min]]
            if not candidates:
                continue
            x, z = min(candidates, key=lambda q: q[0] * normal[0] + q[1] * normal[1])
            for y in range(y0, y0 + rows):
                if y > f.c.ground_at(x, z):
                    f.c.set(x, y, z, "white_stained_glass_pane", "window", PANE_PROPS)
            for y, props in [(y0 - 1, SLAB_TOP), (y0 + rows, SLAB_BOTTOM)]:
                if y > f.c.ground_at(x, z):
                    f.c.set(x, y, z, "quartz_slab", "trim", props)
    f.features["sash_treatment_post_sash"] += 1


def _sash(f, row):
    """Glass replaces the wall, with thin slab trim behind its top and bottom."""
    count = 0
    y0 = math.ceil((row["sill_navd88_m"] + f.offset) * f.c.scale - 0.5 - 1e-9)
    rows = max(2, round(row["height_m"] * f.c.scale))
    for centre in row["centres_m"]:
        treatment = _sash_treatment(f, row, centre)
        pane = "white_stained_glass_pane" if treatment in {"white_pane", "white_pane_posts"} else "glass_pane" if treatment in {"trapdoor_frame", "fence_sash"} else "gray_stained_glass_pane"
        at = row.get("surface_at_by_centre_m", {}).get(str(centre), row["at_m"])
        sheet, body, normal, _ = _surface(
            f, row["side"], at, centre, row["width_m"],
            row["sill_navd88_m"] + row["height_m"],
        )
        across = f.u if row["side"] in {"east", "west"} else f.v
        # A wide nearest-facade search must not wrap glazing around the
        # perpendicular face of a concave end corner.
        tolerance = row.get("surface_tolerance_by_centre_m", {}).get(str(centre), row.get("surface_tolerance_m", 0.75))
        sheet &= abs(across - at) <= tolerance
        # A one-neighbor source-footprint tip cannot carry two pane edges
        # without extending glazing outside the measured building. Keep that
        # tip as masonry and use the adjoining actual wall for this sash.
        neighbors = sum(np.roll(body, shift, axis=axis).astype(np.uint8)
                        for axis in (0, 1) for shift in (-1, 1))
        f.features["isolated_masonry_tip_columns_excluded_from_sashes"] += int((sheet & (neighbors < 2)).sum())
        sheet &= neighbors >= 2
        dx, dz = _inside_step(normal)
        placed = 0
        for x, z, iz, ix in f.each_column(sheet):
            outside = np.floor(np.array([x + 0.5, z + 0.5]) + normal * 2).astype(int)
            grade = f.c.ground_at(int(outside[0]), int(outside[1]))
            for y in range(y0, y0 + rows):
                if y <= grade:
                    continue
                # The pane and its original wall share the same occupied cell.
                f.c.set(x, y, z, pane, "window", PANE_PROPS)
                placed += 1
            # Place the head and sill beyond the glazed vertical interval.
            # Completing an inner cap within the sash had obscured its upper
            # and lower thirds in the v13 native view. These thin surfaces
            # keep that glass clear while enclosing the same opening.
            for y, props in [(y0 - 1, SLAB_TOP), (y0 + rows, SLAB_BOTTOM)]:
                if y <= grade:
                    continue
                bx, bz = x + dx, z + dz
                for _ in range(2):
                    if not sheet[bz - f.c.z_min, bx - f.c.x_min]:
                        break
                    bx, bz = bx + dx, bz + dz
                if body[bz - f.c.z_min, bx - f.c.x_min] and f.c.get(bx, y, bz) == 0:
                    f.c.set(bx, y, bz, "quartz_slab", "trim", props)
        if placed:
            if treatment in {"post_sash", "white_pane_posts"}:
                _post_sash(f, row, centre, y0, rows, sheet, body, normal)
            else:
                _thin_timber_sash(f, row, centre, y0, rows, sheet, body, normal, treatment)
            along = f.v if row["side"] in {"east", "west"} else f.u
            authorised = body & (abs(along - centre) <= row["width_m"] / 2)
            authorised &= abs(across - at) <= tolerance
            allowed = {
                (x, y, z)
                for x, z, _, _ in f.each_column(authorised)
                for y in range(y0, y0 + rows)
            }
            if not hasattr(f.c, "window_opening_regions"):
                f.c.window_opening_regions = []
            f.c.window_opening_regions.append((allowed, -normal))
            f.features["authorised_diagonal_sash_return_panes"] += close_diagonal_pane_corners(
                f.c, allowed, inward=-normal,
            )
        count += bool(placed)
    f.features[f"{row['side']}_rectangle_window_groups"] += count
    key = (
        "interpreted_unseen_sash_groups"
        if row["evidence_status"].startswith("interpreted")
        else "partly_occluded_pitch_wing_sash_groups"
        if "occlusion" in row["evidence_status"]
        else "photographed_pitch_sash_groups"
    )
    f.features[key] += count


def _flush_door(f, side, at, centre, floor, width=1.55, height=2.35, rounded=False):
    sheet, body, normal, along = _surface(f, side, at, centre, width + 0.6, floor + height)
    base, high = f.height_y(floor), f.height_y(floor + height)
    door_cells = []
    columns = list(f.each_column(sheet))
    jambs = set()
    if rounded and columns:
        ordered = sorted(columns, key=lambda cell: along[cell[2], cell[3]])
        jambs = {(ordered[0][0], ordered[0][1]), (ordered[-1][0], ordered[-1][1])}
    dx, dz = _inside_step(normal)
    for x, z, iz, ix in f.each_column(sheet):
        d = abs(float(along[iz, ix]) - centre)
        for y in range(base, high):
            jamb = (x, z) in jambs if rounded else d > width / 2
            side_sign = 1 if along[iz, ix] > centre else -1
            arch_shoulder = rounded and jamb and y == high - 2
            arch_curve = rounded and not jamb and y == high - 1 and d > width * 0.23
            if arch_shoulder or arch_curve:
                direction = (f.n if side in {"east", "west"} else f.t) * side_sign * (1 if arch_shoulder else -1)
                facing = ("east" if direction[0] > 0 else "west") if abs(direction[0]) > abs(direction[1]) else ("south" if direction[1] > 0 else "north")
                f.c.set(x, y, z, "quartz_stairs", "trim", {"facing": facing, "half": "top" if arch_shoulder else "bottom", "shape": "straight", "waterlogged": "false"})
            elif rounded and y == high - 1:
                if jamb:
                    f.c.set(x, y, z, "bricks", "facade")
                else:
                    f.c.set(x, y, z, "quartz_slab", "trim", SLAB_TOP)
            else:
                f.c.set(x, y, z, "quartz_block" if jamb else "pale_oak_planks", "trim" if jamb else "facade")
            if rounded and y >= base + 2:
                # A painted timber back closes every partial arch corner;
                # the actual two-block door passage remains operable below.
                bx, bz = x + dx, z + dz
                if body[bz - f.c.z_min, bx - f.c.x_min] and not sheet[bz - f.c.z_min, bx - f.c.x_min]:
                    f.c.set(bx, y, bz, "pale_oak_planks", "facade")
        if not ((x, z) in jambs) and d <= width / 2:
            door_cells.append((d, x, z))
    if not door_cells:
        raise ValueError("Foster door misses its actual facade")
    _, x, z = min(door_cells)
    facing = ("east" if normal[0] > 0 else "west") if abs(normal[0]) > abs(normal[1]) else ("south" if normal[1] > 0 else "north")
    for half, dy in [("lower", 0), ("upper", 1)]:
        f.c.set(x, base + dy, z, "pale_oak_door", "door", {"half": half, "facing": facing, "hinge": "left", "open": "false", "powered": "false"})
    f.features["operable_reference_doors"] += 1


def _portal(f, portal):
    _flush_door(f, "north", portal["at_m"], portal["centre_m"], portal["floor_navd88_m"], rounded=True)
    f.features["separate_rounded_pitch_portals"] += 1


def _diamond_vent(f, vent):
    f.window_row(
        "north", vent["at_m"], [vent["centre_m"]], vent["sill_navd88_m"],
        vent["width_m"], vent["height_m"], shape="circle", lights=1,
    )
    # Four stair-cut corners give the small diagonal opening a diamond
    # silhouette at this resolution; the centre remains an attached pane.
    mask = (abs(f.u - vent["centre_m"]) < 0.95) & (abs(f.v - vent["at_m"]) < 0.8)
    mid = vent["sill_navd88_m"] + vent["height_m"] / 2
    for x, z, iz, ix in f.each_column(mask):
        d = f.u[iz, ix] - vent["centre_m"]
        if abs(d) < 0.18:
            continue
        direction = f.t * (1 if d > 0 else -1)
        facing = (
            ("east" if direction[0] > 0 else "west")
            if abs(direction[0]) > abs(direction[1])
            else ("south" if direction[1] > 0 else "north")
        )
        for y in range(f.height_y(mid - 0.8), f.height_y(mid + 0.8) + 1):
            state = f.c.palette[f.c.get(x, y, z)]["Name"]
            if state not in {"minecraft:quartz_block", "minecraft:quartz_stairs"}:
                continue
            f.c.set(x, y, z, "quartz_stairs", "trim", {
                "facing": facing,
                "half": "top" if (y + 0.5) / f.c.scale - f.offset >= mid else "bottom",
                "shape": "straight", "waterlogged": "false",
            })
            # The shallow stair-cut diamond has the same solid reveal
            # backing as the door arch. Its partial corner must not look
            # through an otherwise empty gable interior.
            dx, dz = _inside_step(-f.n)
            bx, bz = x + dx, z + dz
            bi, bj = bz - f.c.z_min, bx - f.c.x_min
            if (f.r.footprint_mask[bi, bj] and (y + 1) / f.c.scale - f.offset <= f.r.heights[bi, bj] + 0.125
                    and not f.c.get(bx, y, bz)):
                f.c.set(bx, y, bz, "bricks", "facade")
                f.features["diamond_vent_solid_stair_backing_cells"] += 1
    f.features["photographed_central_diamond_attic_vent"] = 1


def _fascia(f):
    """Separate a level painted eave board from the sloping roof substrate."""
    major = f.r.footprint_mask & (f.r.heights > 72.5)
    edge = major & ~binary_erosion(major, iterations=1)
    bands = []
    aligned = np.zeros_like(major)
    for band in f.p.get("eave_bands", []):
        a, b = band["ends_u_m"]
        mask, _, normal, _ = _surface(
            f, band["side"], band["at_v_m"], (a + b) / 2, b - a, 72.5,
        )
        # Exclude gable returns which the broader opening search also sees.
        mask &= abs(f.v - band["at_v_m"]) <= band["wall_tolerance_m"]
        aligned |= mask
        bands.append((band, mask, normal))

    # Sloping gable/verge trim retains the original surface shape and height.
    # Only external perimeter cells are painted; valleys remain gray.
    for x, z, iz, ix in f.each_column(edge & ~aligned):
        roof = np.flatnonzero(f.c.roles[:, iz, ix] == ROLES.index("roof"))
        if not roof.size:
            continue
        y = int(roof[-1]) + f.c.y_min
        original = f.c.palette[f.c.get(x, y, z)]
        suffix = original["Name"].removeprefix("minecraft:stone_brick")
        block = "quartz_stairs" if suffix == "_stairs" else "quartz_slab" if suffix == "_slab" else "quartz_block"
        f.c.set(x, y, z, block, "trim", original.get("Properties"))
        f.features["thin_measured_eave_and_gable_fascia_cells"] += 1

    for band, mask, normal in bands:
        # Measured eave endpoints are ~74.0 m (west) and ~73.54 m
        # (east). A constant upper slab surface removes the artificial
        # up/down white blocks caused by diagonal raster cell centres.
        y_band = round((band["top_navd88_m"] + f.offset) * f.c.scale) - 1
        dx, dz = _inside_step(normal)
        for x, z, iz, ix in f.each_column(mask):
            for y in range(f.height_y(71.0), y_band):
                if f.c.roles[y - f.c.y_min, iz, ix] == ROLES.index("roof"):
                    f.c.set(x, y, z, "bricks", "facade")
                    f.features["exposed_eave_backing_replaced_with_brick"] += 1
            # Full masonry behind the thin board closes its lower-half
            # reveal, including diagonal joins. It never rises above the
            # source roof surface or extends outside Foster's footprint.
            for depth in (1, 2):
                bx, bz = x + dx * depth, z + dz * depth
                bz_i, bx_i = bz - f.c.z_min, bx - f.c.x_min
                if not major[bz_i, bx_i] or (y_band + 1) / f.c.scale - f.offset > f.r.heights[bz_i, bx_i] + 0.125:
                    continue
                f.c.set(bx, y_band, bz, "bricks", "facade")
                f.features["continuous_inner_fascia_backing_cells"] += 1
            f.c.set(x, y_band, z, "quartz_slab", "trim", SLAB_TOP)
            f.features["level_wing_eave_fascia_cells"] += 1

    # At the rear high/low-roof junction, a neighbouring source plane can
    # lie below the board's lower half. Complete only an otherwise unbacked
    # board in its own column: top slabs and full cubes have identical tops,
    # so the measured roof surface above remains untouched.
    for band, mask, _ in bands:
        y = round((band["top_navd88_m"] + f.offset) * f.c.scale) - 1
        for x, z, _, _ in f.each_column(mask):
            state = f.c.palette[f.c.get(x, y, z)]
            if state["Name"] != "minecraft:quartz_slab" or state.get("Properties", {}).get("type") != "top":
                continue
            backed = False
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                name = f.c.palette[f.c.get(x + dx, y, z + dz)]["Name"]
                backed |= name != "minecraft:air" and not name.endswith(
                    ("_slab", "_stairs", "_pane", "_door", "_trapdoor", "_fence", "_wall"))
            if not backed:
                f.c.set(x, y, z, "quartz_block", "trim")
                f.features["unbacked_fascia_half_voids_closed_without_top_change"] += 1


def _chimneys(f, p):
    for chimney in p["chimneys"]:
        bounds = chimney["bounds_uv_m"]
        footprint = f.local_mask(bounds) & f.r.footprint_mask
        if not np.any(footprint):
            raise ValueError("Foster chimney misses its referenced roof")
        base = float(np.min(f.r.heights[footprint])) - 0.4
        cap = chimney["top_navd88_m"]
        f.box(bounds, base, cap - 0.25, "bricks", "facade", mask=footprint)
        f.box(bounds, cap - 0.5, cap, "brick_slab", "trim", SLAB_TOP, mask=footprint)
        f.features["photo_interpreted_brick_chimneys"] += 1


def _close_outer_wall(f):
    """Audit every main exterior wall cell below the sampled roof surface."""
    body = f.r.footprint_mask & (f.r.heights > 72.5)
    edge = body & ~binary_erosion(body, iterations=1)
    checked = closed = 0
    for x, z, iz, ix in f.each_column(edge):
        half_units = math.floor((float(f.r.heights[iz, ix]) + f.offset) * f.c.scale * 2 + 0.5)
        roof_y = half_units // 2 - 1 if half_units % 2 == 0 else half_units // 2
        low = max(f.c.ground_at(x, z) + 1, f.height_y(f.p["geometry"]["basement_floor_navd88_m"]))
        for y in range(low, roof_y):
            checked += 1
            # Every authored aperture has its pane/door in this same wall
            # sheet. An empty cell is therefore an unintended wall hole.
            if f.c.get(x, y, z) == 0:
                f.c.set(x, y, z, "bricks", "facade")
                closed += 1
    f.features["outer_wall_cells_checked_below_roof"] = checked
    f.features["unintended_empty_wall_cells_closed"] = closed


def _close_diagonal_jamb_returns(f, regions):
    """Join a free sash end to its existing jamb through one interior corner.

    The photographed outer sheet is unchanged. Any extension beyond its
    centre-sampled width is a single empty corner behind the adjacent intact
    jamb, inside the measured body. No masonry, roof, or pane is overwritten.
    """
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    body = f.r.footprint_mask & (f.r.heights > 72.5)
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
                            # A jagged source corner can turn away from the
                            # average facade normal. A cell surrounded on all
                            # four sides by the original body is still an
                            # interior reveal, irrespective of that vector.
                            fully_inside = interior[corner[2] - f.c.z_min, corner[0] - f.c.x_min]
                            if not f.c.get(*corner) and inside(corner) and (displacement >= -1e-6 or fully_inside):
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
                        raise ValueError(f"Foster return cap would leave its measured envelope: {cap}")
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
    _rear_basement(f, p)
    porch = p["central_canopy"]
    u0, v0, u1, v1 = porch["bounds_uv_m"]
    # The low canopy must be open.  It does not own the building's main wall.
    authored = f.r.face_indices >= 1_000_000
    f.box((u0, v0, u1, v1), 68.1, 70.75, "air", "air", mask=authored)
    for u, v in porch["posts_uv_m"]:
        f.box((u - 0.22, v - 0.22, u + 0.22, v + 0.22),
              68.1, 70.75, "quartz_block", "trim")
    f.box((u0, v0, u1, v0 + 0.35), 70.5, 71.0, "quartz_slab", "trim", SLAB_TOP)
    f.features["open_shallow_centre_canopy"] = 1

    original = f.r
    f.r = replace(f.r, footprint_mask=f.r.footprint_mask & ~authored)
    for row in p["window_rows"]:
        _sash(f, row)
    for portal in p["pitch_portals"]:
        _portal(f, portal)
    rear = p["rear_door"]
    _flush_door(f, "south", rear["at_m"], rear["centre_m"], rear["floor_navd88_m"],
                rear["width_m"], rear["height_m"])
    _diamond_vent(f, p["attic_vent"])
    f.r = original

    _fascia(f)
    _chimneys(f, p)
    # A narrow photographed brick terrace and concrete wing walk sit on the
    # independently measured pitch elevation.  Rear terrain keeps its slope.
    f.site_surface([(13.35, -1.85), (33.65, -1.85), (33.65, 0.85), (13.35, 0.85)],
                   68.1, "bricks", "brick_slab")
    for a, b in [(0, 13.35), (33.65, 49.0)]:
        f.site_surface([(a, -0.65), (b, -0.65), (b, 1.05), (a, 1.05)], 68.0)
    for level in p["geometry"]["upper_floor_plates_navd88_m"]:
        f.floor_plate(level)
    _close_outer_wall(f)
    _close_diagonal_jamb_returns(f, f.c.window_opening_regions[first_region:])
    f.features["source_major_roof_faces_retained"] = len(p["roof_interpretation"]["major_faces"])
