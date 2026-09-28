"""Seat thin glass in masonry openings without adding exterior window boxes."""

from collections import Counter

DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def close_diagonal_pane_corners(canvas, allowed, *, inward=None):
    """Add one authorised return pane at an otherwise open diagonal joint.

    Both endpoints and the corner must belong to this particular opening.
    No masonry is overwritten and exactly one of the two corner cells is used.
    An inward vector chooses the building-side corner when both are allowed.
    """
    allowed = set(allowed)
    panes = sorted(p for p in allowed if canvas.palette[canvas.get(*p)]["Name"].endswith("_pane"))
    additions = 0
    for x, y, z in panes:
        for dz in (-1, 1):
            endpoint = (x + 1, y, z + dz)
            if endpoint not in allowed or not canvas.palette[canvas.get(*endpoint)]["Name"].endswith("_pane"):
                continue
            corners = ((x + 1, y, z), (x, y, z + dz))
            # An existing return or masonry corner already joins this pair.
            # Partial-block ambiguities belong in the physical contact audit.
            if any(canvas.get(*q) for q in corners):
                continue
            candidates = [q for q in corners if q in allowed]
            if not candidates:
                continue
            if inward is None:
                corner = min(candidates)
            else:
                corner = max(candidates, key=lambda q: (q[0] * inward[0] + q[2] * inward[1], q))
            state = canvas.palette[canvas.get(x, y, z)]
            canvas.set(*corner, state["Name"], "window", state.get("Properties"))
            additions += 1
    return additions


def pane_joint_report(canvas):
    """Find unbridged diagonal glass pairs and disconnected adjacent panes.

    This supplements component support; it does not claim an entire wall is
    sealed or authorise a global fill outside individual window openings.
    """
    import numpy as np

    if hasattr(canvas, "iter_panes"):
        panes = set(canvas.iter_panes())
    else:
        ids = [i for i, p in enumerate(canvas.palette) if p["Name"].endswith("_pane")]
        panes = {(int(ix) + canvas.x_min, int(iy) + canvas.y_min, int(iz) + canvas.z_min)
                 for iy, iz, ix in np.argwhere(np.isin(canvas.data, ids))}
    diagonal, disconnected = [], []
    for x, y, z in sorted(panes):
        for dz in (-1, 1):
            end = (x + 1, y, z + dz)
            corners = ((x + 1, y, z), (x, y, z + dz))
            if end in panes and all(canvas.get(*q) == 0 for q in corners):
                diagonal.append({"from": [x, y, z], "to": list(end), "open_corners": list(corners)})
        state = canvas.palette[canvas.get(x, y, z)]
        for side, opposite, dx, dz in (("east", "west", 1, 0), ("south", "north", 0, 1)):
            end = (x + dx, y, z + dz)
            if end not in panes:
                continue
            neighbor = canvas.palette[canvas.get(*end)]
            if state.get("Properties", {}).get(side) != "true" or neighbor.get("Properties", {}).get(opposite) != "true":
                disconnected.append({"from": [x, y, z], "to": list(end), "direction": side})
    return {"panes": len(panes), "unbridged_diagonal_pairs": len(diagonal),
            "disconnected_adjacent_pairs": len(disconnected),
            "diagonal_pairs": diagonal, "disconnected_pairs": disconnected}


def close_diagonal_pane_jambs(canvas, allowed, *, inward=None):
    """Join a free pane end to a diagonal solid jamb inside its own frame.

    The jamb stays untouched. At most one of the two empty shared corners is
    used per contact, and an already two-sided pane never grows another arm.
    """
    from build_hill_chapel_sample import ROLES

    allowed = set(allowed)

    def joins(position):
        name = canvas.palette[canvas.get(*position)]["Name"]
        return name != "minecraft:air" and not name.endswith(
            ("_stairs", "_slab", "_door", "_trapdoor", "_fence", "_leaves")
        )

    added = 0
    panes = sorted(q for q in allowed
                   if canvas.palette[canvas.get(*q)]["Name"].endswith("_pane"))
    for x, y, z in panes:
        for _ in range(2):
            if sum(joins((x + dx, y, z + dz)) for dx, dz in DIRECTIONS) >= 2:
                break
            choices = set()
            for dx in (-1, 1):
                for dz in (-1, 1):
                    endpoint = (x + dx, y, z + dz)
                    state = canvas.palette[canvas.get(*endpoint)]
                    if not joins(endpoint) or state["Name"].endswith(("_pane", "iron_bars")):
                        continue
                    iy, iz, ix = y - canvas.y_min, z + dz - canvas.z_min, x + dx - canvas.x_min
                    if ROLES[int(canvas.roles[iy, iz, ix])] not in {"facade", "trim"}:
                        continue
                    corners = ((x + dx, y, z), (x, y, z + dz))
                    if any(canvas.get(*q) for q in corners):
                        continue
                    choices.update(q for q in corners if q in allowed)
            if not choices:
                break
            position = (min(choices) if inward is None else
                        max(choices, key=lambda q: (q[0] * inward[0] + q[2] * inward[1], q)))
            state = canvas.palette[canvas.get(x, y, z)]
            canvas.set(*position, state["Name"], "window", state.get("Properties"))
            added += 1
    return added


def bridge_frame_edges(canvas, allowed, *, inward=None, corner_allowed=None):
    """Add at most one pane across a raster gap to an existing frame.

    `allowed` is supplied by the opening itself, inside its wall/reveal. This
    prevents a global neighbour-fill from growing glass outside the building
    or across a doorway. A diagonal sheet may need a short return at its edge.
    """
    allowed = set(allowed)
    corner_allowed = allowed if corner_allowed is None else set(corner_allowed)
    if not hasattr(canvas, "window_opening_regions"):
        canvas.window_opening_regions = []
    canvas.window_opening_regions.append((corner_allowed, inward))
    additions = {}
    for x, y, z in allowed:
        state = canvas.palette[canvas.get(x, y, z)]
        if not state["Name"].endswith("_pane"):
            continue
        for dx, dz in DIRECTIONS:
            gap = (x + dx, y, z + dz)
            if gap not in allowed or canvas.get(*gap) != 0:
                continue
            for ex, ez in DIRECTIONS:
                endpoint = (gap[0] + ex, y, gap[2] + ez)
                if endpoint == (x, y, z):
                    continue
                end = canvas.palette[canvas.get(*endpoint)]
                name = end["Name"]
                if name == "minecraft:air" or name.endswith(
                    ("_stairs", "_slab", "_door", "_trapdoor", "_fence", "_leaves")
                ):
                    continue
                iy, iz, ix = (
                    y + 64,
                    endpoint[2] - canvas.z_min,
                    endpoint[0] - canvas.x_min,
                )
                if not (
                    0 <= iz < canvas.data.shape[1] and 0 <= ix < canvas.data.shape[2]
                ):
                    continue
                from build_hill_chapel_sample import ROLES

                role = ROLES[int(canvas.roles[iy, iz, ix])]
                # A diagonal frame may require an L-shaped return. Joining
                # two panes is restricted to a straight one-cell gap.
                if role in {"trim", "facade"} or (
                    name.endswith("_pane") and (ex, ez) == (dx, dz)
                ):
                    additions[gap] = state
                    break
    for position, state in additions.items():
        canvas.set(*position, state["Name"], "window", state.get("Properties"))
    return len(additions) + close_diagonal_pane_corners(canvas, corner_allowed, inward=inward)


def repair_registered_pane_corners(canvas):
    """Repeat authorised corner repair after later facade operations finish."""
    regions = getattr(canvas, "window_opening_regions", [])
    count = sum(close_diagonal_pane_corners(canvas, allowed, inward=inward)
                for allowed, inward in regions)
    count += sum(close_diagonal_pane_jambs(canvas, allowed, inward=inward)
                 for allowed, inward in regions)
    count += sum(close_diagonal_pane_corners(canvas, allowed, inward=inward)
                 for allowed, inward in regions)
    for panes, caps, block in getattr(canvas, "window_cap_regions", []):
        added = seal_opening_pane_caps(canvas, panes, caps, block)
        count += added
        canvas.window_cap_repair_count = getattr(canvas, "window_cap_repair_count", 0) + added
    return count


def seal_opening_pane_caps(canvas, pane_allowed, cap_allowed, block):
    """Close the head/sill of authorised return panes inside their frame.

    Existing stair trim, doors, glass and roof surfaces are retained. Only
    an empty cap or a slab occupying the wrong half of its cell is completed.
    """
    from build_hill_chapel_sample import ROLES

    additions = set()
    for x, y, z in pane_allowed:
        if not canvas.palette[canvas.get(x, y, z)]["Name"].endswith("_pane"):
            continue
        for dy in (-1, 1):
            position = (x, y + dy, z)
            if position not in cap_allowed:
                continue
            state = canvas.palette[canvas.get(*position)]
            name = state["Name"]
            wrong_half = name.endswith("_slab") and state.get("Properties", {}).get("type") == ("bottom" if dy < 0 else "top")
            if name != "minecraft:air" and not wrong_half:
                continue
            iy, iz, ix = position[1] - canvas.y_min, z - canvas.z_min, x - canvas.x_min
            if canvas.roles[iy, iz, ix] == ROLES.index("roof"):
                continue
            additions.add(position)
    for position in additions:
        canvas.set(*position, block, "trim")
    return len(additions)


def pane_perimeter_report(canvas):
    """Expose frame-contact candidates that pane-to-pane checks cannot see.

    This is a review report, not a proof of wall closure. Stair and trapdoor
    contacts depend on their occupied shape; a solid inward backing can close
    a sightline even when a pane edge itself does not touch its cap.
    """
    import numpy as np

    if hasattr(canvas, "iter_panes"):
        positions = list(canvas.iter_panes())
    else:
        ids = [i for i, state in enumerate(canvas.palette)
               if state["Name"].endswith("_pane")]
        positions = [(int(ix) + canvas.x_min, int(iy) + canvas.y_min,
                      int(iz) + canvas.z_min)
                     for iy, iz, ix in np.argwhere(np.isin(canvas.data, ids))]
    horizontal, vertical, partial = [], [], []
    for x, y, z in positions:
        state = canvas.palette[canvas.get(x, y, z)]
        props = state.get("Properties", {})
        joins = [d for d in ("north", "south", "east", "west")
                 if props.get(d) == "true"]
        if len(joins) < 2:
            horizontal.append({"xyz": [x, y, z], "connected_directions": joins})
        for direction, dy in (("below", -1), ("above", 1)):
            neighbor = canvas.palette[canvas.get(x, y + dy, z)]
            name = neighbor["Name"]
            nprops = neighbor.get("Properties", {})
            gap = name == "minecraft:air" or (
                name.endswith("_slab") and nprops.get("type") ==
                ("bottom" if dy < 0 else "top")
            )
            record = {"xyz": [x, y, z], "direction": direction,
                      "neighbor": neighbor}
            if gap:
                vertical.append(record)
            elif name.endswith(("_stairs", "_trapdoor", "_fence")):
                partial.append(record)
    return {
        "panes": len(positions),
        "fewer_than_two_horizontal_joins": len(horizontal),
        "vertical_air_or_reversed_slab_contacts": len(vertical),
        "shape_contacts_requiring_review": len(partial),
        "horizontal_candidates": horizontal,
        "vertical_candidates": vertical,
        "partial_shape_contacts": partial,
        "scope": "Candidate frame contacts only; inspect occupied partial-block shapes, inward backing and native views before claiming a visible hole or complete closure.",
    }


def pane_support_report(canvas):
    """Report glass components with no physical contact to a building frame."""
    import numpy as np
    from build_hill_chapel_sample import ROLES

    ids = [i for i, p in enumerate(canvas.palette) if p["Name"].endswith("_pane")]
    remaining = {
        (int(ix) + canvas.x_min, int(iy) - 64, int(iz) + canvas.z_min)
        for iy, iz, ix in np.argwhere(np.isin(canvas.data, ids))
    }
    counts = Counter(panes=len(remaining), components=0, unsupported_components=0)
    unsupported = []
    while remaining:
        seed = remaining.pop()
        pending, contacts, size = [seed], 0, 0
        while pending:
            x, y, z = pending.pop()
            size += 1
            for dx, dy, dz in (
                (1, 0, 0),
                (-1, 0, 0),
                (0, 1, 0),
                (0, -1, 0),
                (0, 0, 1),
                (0, 0, -1),
            ):
                position = (x + dx, y + dy, z + dz)
                if position in remaining:
                    remaining.remove(position)
                    pending.append(position)
                iy, iz, ix = y + dy + 64, z + dz - canvas.z_min, x + dx - canvas.x_min
                if (
                    0 <= iy < 384
                    and 0 <= iz < canvas.data.shape[1]
                    and 0 <= ix < canvas.data.shape[2]
                ):
                    role = ROLES[int(canvas.roles[iy, iz, ix])]
                    if role in {"facade", "trim", "roof"}:
                        contacts += 1
        counts["components"] += 1
        if not contacts:
            counts["unsupported_components"] += 1
            unsupported.append({"seed_xyz": seed, "panes": size})
    return {**counts, "unsupported": unsupported}
