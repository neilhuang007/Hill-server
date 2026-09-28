"""Davy: source roof faces, bounded photographed openings and pale open rails."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt
from build_hill_chapel_sample import ROLES, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building
from campus_window_frames import bridge_frame_edges, close_diagonal_pane_corners

ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = "runtime/research/sol-reference-20260908/davy-roof-railings-handoff.json"
PACKET_SHA = "3fc2ae3b556d518d8b0405c36e1ce4ad1fa2130765f32b291eb3a066da2e9905"
FINGERPRINT_PATH = "runtime/research/davy-reference-20260915/verified-provenance/davy-source-face-fingerprint-provenance.json"
FINGERPRINT_SHA = "d8736a40b231e1322847321785cec2cf819d8a23c3e75f1add6fbc6d6328bc73"
CENTRES = [-136.1, -131.8, -127.5, -123.2, -108.0, -103.7, -99.4]
PLAIN = [-140.3, -119.6, -111.6, -94.8]
KEEP = (3, 4, 6, 7, 8, 9, 11)
LOW = (0, 1, 2, 5, 10, 12)
BOTTOM = {"type": "bottom", "waterlogged": "false"}
TOP = {"type": "top", "waterlogged": "false"}
SOURCE = {}


def _source(p):
    path = ROOT / PACKET_PATH
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PACKET_SHA
    packet = json.loads(path.read_text(encoding="utf-8"))
    b = load_measured_building(parent_id=p["parent_id"])
    assert b.source_sha256 == packet["sources"][0]["sha256"]
    assert len(b.roof_faces) == 13
    fingerprint_path = ROOT / FINGERPRINT_PATH
    assert hashlib.sha256(fingerprint_path.read_bytes()).hexdigest() == FINGERPRINT_SHA
    fingerprint_packet = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    assert hashlib.sha256((ROOT / fingerprint_packet["source_cityjson"]["loader"]).read_bytes()).hexdigest() == fingerprint_packet["source_cityjson"]["loader_sha256"]
    for face, control in zip(b.roof_faces, fingerprint_packet["faces"], strict=True):
        payload = {"xy": control["xy_world_xz_m"], "plane": control["plane_abc_world_xz"]}
        assert payload == control["canonical_payload"]
        sha = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert sha == control["sha256"] and sha[:16] == control["fingerprint16"]
        assert face.surface_index == control["source_surface"]
        assert np.allclose(np.array(face.polygon.exterior.coords), payload["xy"], atol=1e-8, rtol=0)
        assert np.allclose([face.a, face.b, face.c], payload["plane"], atol=1e-8, rtol=0)
        assert len(face.polygon.interiors) == len(control["holes_world_xz_m"])
        for ring, expected in zip(face.polygon.interiors, control["holes_world_xz_m"], strict=True):
            assert np.allclose(np.array(ring.coords), expected, atol=1e-8, rtol=0)
    for control in packet["source_face_controls"] + packet["nonbuilding_low_face_controls"]:
        face = b.roof_faces[control["id"]]
        assert face.surface_index == control["source_surface"]
        assert np.allclose([face.min_h, face.max_h], control["height_range_navd88_m"], atol=.000051)
        if "plane_abc_world_xz" in control:
            assert np.allclose([face.a, face.b, face.c], control["plane_abc_world_xz"], atol=1e-8, rtol=0)
    return b, packet


def _overlay(r, f, original, bounds, eave, ridge, record):
    u0, v0, u1, v1 = bounds
    levels = eave+(ridge-eave)*(1-abs(f.v-(v0+v1)/2)/((v1-v0)/2))
    mask = original & f.local_mask(bounds) & (~r.footprint_mask | (levels > r.heights))
    h, gx, gz, ids = (a.copy() for a in (r.heights, r.gradient_x, r.gradient_z, r.face_indices))
    dz, dx = np.gradient(levels, r.resolution)
    face_id = 1_000_000+len(r.authored_roof_patches)
    h[mask], gx[mask], gz[mask], ids[mask] = levels[mask], dx[mask], dz[mask], face_id
    return replace(r, heights=h, gradient_x=gx, gradient_z=gz, face_indices=ids,
        footprint_mask=r.footprint_mask | mask, missing_mask=r.missing_mask & ~mask,
        authored_roof_patches=(*r.authored_roof_patches, {
            **record, "face_index": face_id, "bounds_uv_m": list(bounds),
            "eave_navd88_m": eave, "ridge_navd88_m": ridge, "ridge_axis": "U",
            "combine": "max over retained source", "affected_columns": int(mask.sum()),
            "new_shell_columns": int((mask & ~r.footprint_mask).sum()),
            "plan_rule": "clipped to original measured footprint", "evidence_packet_sha256": PACKET_SHA,
        }))


def prepare_roof(r, f, p):
    b, packet = _source(p)
    SOURCE.clear()
    SOURCE.update(raster=r, building=b, packet=packet)
    original = r.footprint_mask.copy()
    keep = original & np.isin(r.face_indices, KEEP)
    low = original & np.isin(r.face_indices, LOW)
    assert (int(original.sum()), int(keep.sum()), int(low.sum())) == (4372, 2873, 1499)
    r = replace(r, footprint_mask=keep, missing_mask=r.missing_mask & keep)
    for side in ("east", "west"):
        for centre in CENTRES:
            bounds = ((114.25, centre-1.05, 116.75, centre+1.05) if side == "east"
                      else (102.65, centre-1.05, 105.15, centre+1.05))
            r = _overlay(r, f, original, bounds, 60.05, 62.0 if side == "east" else 61.4, {
                "kind": "small_gable", "side": side, "centre_v_m": centre,
                "status": ("photographed count; interpreted dimensions and positions" if side == "east"
                           else "provisional roof-only symmetry; west apertures unresolved"),
                "native_peak_refinement": ("Root-authorized interpreted62m ridge after nativev8:61.4m barely cleared measured east roof. All source columns outside this existing patch stay exact." if side == "east" else "unchanged provisional61.4m ridge"),
            })
    r = _overlay(r, f, original, (120.3, -117.7, 122.2, -113.4), 58.6, 60.3, {
        "kind": "small_outer_entry_hood", "status": "photographed form; interpreted bounds and levels",
    })
    assert int(r.footprint_mask.sum()) == 2905
    assert not np.any(r.footprint_mask & ~original)
    measured_body = original & np.isin(SOURCE["raster"].face_indices, (4, 6, 9, 11))
    body = measured_body.copy()
    straight_rows, west_rows = {}, {}
    for iz in range(body.shape[0]):
        # Nearest cell centre to one constant measured-orientation plane.
        x = round((116.60-f.z[iz, 0]*f.t[1])/f.t[0]*f.c.scale-.5)
        ix = x-f.c.x_min
        if 0 <= ix < body.shape[1] and -142.5 <= f.v[iz, ix] <= -92.7:
            assert original[iz, ix]
            eligible = f.u[iz] >= 114.5
            body[iz, eligible] = (np.arange(body.shape[1])[eligible] <= ix)
            straight_rows[iz+f.c.z_min] = (x, iz+f.c.z_min)
        wx = round((103.35-f.z[iz, 0]*f.t[1])/f.t[0]*f.c.scale-.5)
        wix = wx-f.c.x_min
        if 0 <= wix < body.shape[1] and -142.5 <= f.v[iz, wix] <= -92.7:
            eligible = f.u[iz] <= 105.5
            body[iz, eligible] = (np.arange(body.shape[1])[eligible] >= wix)
            west_rows[iz+f.c.z_min] = (wx, iz+f.c.z_min)
    _, nearest = distance_transform_edt(~measured_body, return_indices=True)
    SOURCE.update(body=body, measured_body=measured_body, straight_rows=straight_rows, west_rows=west_rows,
                  nearest_measured_body=nearest)
    return r


def _roof_y(f, iz, ix):
    return (math.floor((f.r.heights[iz, ix]+f.offset)*f.c.scale*2+.5)-1)//2


def _wall_y(f, iz, ix):
    rz, rx = (iz, ix) if f.r.footprint_mask[iz, ix] else SOURCE["nearest_measured_body"][:, iz, ix]
    return _roof_y(f, rz, rx)


def _wall_skin(f, body):
    """One straight pond plane; roof raster noise never becomes a pilaster."""
    floor = f.height_y(56.25)
    f.davy_wall_plane_changes = []
    strip = ((f.u >= 114.5) & (f.u <= 118.0)) | ((f.u >= 101.5) & (f.u <= 105.5))
    for x, z, iz, ix in f.each_column(strip):
        if z not in SOURCE["straight_rows"] and z not in SOURCE["west_rows"]:
            continue
        for y in range(floor, 82):
            if f.c.roles[y+64, iz, ix] == ROLES.index("facade"):
                f.c.set(x, y, z, "air", "air")
                f.davy_wall_plane_changes.append([x, y, z, "remove_roof_raster_wall"])
    boundary = body & ~binary_erosion(body)
    # One inward turn makes each diagonal step four-neighbour connected.
    rows = SOURCE["straight_rows"]
    for z in sorted(rows):
        if z+1 in rows and rows[z][0] != rows[z+1][0]:
            x = min(rows[z][0], rows[z+1][0])
            boundary[z-f.c.z_min, x-f.c.x_min] = True
    rows = SOURCE["west_rows"]
    for z in sorted(rows):
        if z+1 in rows and rows[z][0] != rows[z+1][0]:
            x = max(rows[z][0], rows[z+1][0])
            boundary[z+1-f.c.z_min, x-f.c.x_min] = True
    for x, z, iz, ix in f.each_column(boundary):
        top = _wall_y(f, iz, ix)
        for y in range(floor, top):
            if f.c.get(x, y, z) == 0:
                f.c.set(x, y, z, "stone_bricks", "facade")
                f.features["main_body_wall_cells_below_measured_canopy"] += 1
                f.davy_wall_plane_changes.append([x, y, z, "regular_wall_plane"])


def _contour(f, body, side):
    # Actual world rows avoid duplicate contour bins selecting interior cells.
    result = {}
    axis = 0 if side in ("east", "west") else 1
    sign = 1 if side in ("east", "south") else -1
    for x, z, iz, ix in f.each_column(body):
        key, q = (z if axis == 0 else x), (x, z)
        if key not in result or q[axis]*sign > result[key][axis]*sign:
            result[key] = q
    if side == "east":
        result.update(SOURCE["straight_rows"])
    if side == "west":
        result.update(SOURCE["west_rows"])
    return result


def _opening(f, body, side, centre, width, bottom, height, *, arched=False, door=False):
    """One inset sheet behind the front arch; local jambs and cap backing."""
    contour = _contour(f, body, side)
    axis = 0 if side in ("east", "west") else 1
    along = f.v if axis == 0 else f.u
    n = max(2, round(width*f.c.scale))
    keys = sorted(contour, key=lambda k: abs(along[contour[k][1]-f.c.z_min, contour[k][0]-f.c.x_min]-centre))[:n]
    keys.sort()
    assert keys == list(range(keys[0], keys[-1]+1))
    columns = [contour[k] for k in keys]
    inward = {"east": (-1, 0), "west": (1, 0), "north": (0, 1), "south": (0, -1)}[side]
    tangent = (0, 1) if axis == 0 else (1, 0)
    low, high = f.height_y(bottom), f.height_y(bottom+height)
    allowed, pane_columns = set(), set()
    door_plane = min(q[axis]*(-inward[axis]) for q in columns)*(-inward[axis])+inward[axis]
    if door and side == "east":
        # Preserve the exact v8 leaf/pane plane inside the now regular facade.
        door_plane = 264
    for j, (x, z) in enumerate(columns):
        bx, bz = x+inward[0], z+inward[1]
        if door:
            bx, bz = (door_plane, z) if axis == 0 else (x, door_plane)
        assert body[bz-f.c.z_min, bx-f.c.x_min]
        pane_columns.add((bx, bz))
        for y in range(low, high):
            f.c.set(x, y, z, "air", "air")
            if door:
                for depth in range(1, abs((x, z)[axis]-(bx, bz)[axis])):
                    f.c.set(x+inward[0]*depth, y, z+inward[1]*depth, "air", "air")
            f.c.set(bx, y, bz, "white_stained_glass_pane", "window", PANE_PROPS)
            allowed.add((bx, y, bz))
        if arched and j in (0, n-1):
            facing = (("north" if j == 0 else "south") if axis == 0 else ("west" if j == 0 else "east"))
            f.c.set(x, high-1, z, "quartz_stairs", "trim", {
                "half": "top", "facing": facing, "shape": "straight", "waterlogged": "false",
            })
        f.c.set(x, low-1, z, "quartz_slab", "trim", TOP)
        f.c.set(x, high, z, "quartz_slab", "trim", BOTTOM)
        f.c.set(bx, low-1, bz, "smooth_quartz", "trim")
        f.c.set(bx, high, bz, "smooth_quartz", "trim")
        if door:
            for depth in range(1,abs((x,z)[axis]-(bx,bz)[axis])):
                for y in (low-1,high):
                    f.c.set(x+inward[0]*depth,y,z+inward[1]*depth,"smooth_quartz","trim")
    for k, step in ((keys[0], -1), (keys[-1], 1)):
        x, z = contour[k]
        jx, jz = x+tangent[0]*step, z+tangent[1]*step
        exterior_jamb = contour[k+step]
        jambs = {(jx, jz), exterior_jamb, (jx+inward[0], jz+inward[1]),
                 (exterior_jamb[0]+inward[0], exterior_jamb[1]+inward[1])}
        if door:
            for qx, qz in list(jambs):
                for depth in range(abs((qx, qz)[axis]-door_plane)+1):
                    jambs.add((qx+inward[0]*depth, qz+inward[1]*depth))
        for qx, qz in jambs:
            if body[qz-f.c.z_min, qx-f.c.x_min]:
                for y in range(low, high):
                    if y < _wall_y(f, qz-f.c.z_min, qx-f.c.x_min)-1:
                        pale_front = (qx, qz) == exterior_jamb
                        f.c.set(qx, y, qz, "smooth_quartz" if pale_front else "stone_bricks",
                                "trim" if pale_front else "facade")
    ordered = sorted(pane_columns, key=lambda q: q[1-axis])
    for aa, bb in zip(ordered, ordered[1:]):
        if abs(aa[0]-bb[0]) == 1 and abs(aa[1]-bb[1]) == 1:
            # Exactly one inward turn, independent of whether the opposite
            # corner contains the front arch. Never create a square glass cage.
            qx, qz = max(((aa[0], bb[1]), (bb[0], aa[1])),
                         key=lambda q: q[0]*inward[0]+q[1]*inward[1])
            assert body[qz-f.c.z_min, qx-f.c.x_min]
            pane_columns.add((qx, qz))
    for x, z in pane_columns:
        for y in range(low, high):
            f.c.set(x, y, z, "white_stained_glass_pane", "window", PANE_PROPS)
            allowed.add((x, y, z))
        f.c.set(x, low-1, z, "smooth_quartz", "trim")
        f.c.set(x, high, z, "smooth_quartz", "trim")
    if door:
        for j, (x, z) in enumerate(columns):
            bx, bz = (door_plane, z) if axis == 0 else (x, door_plane)
            for dy, half in ((0, "lower"), (1, "upper")):
                f.c.set(bx, low+dy, bz, "dark_oak_door", "door", {
                    "facing": side, "half": half, "hinge": "left" if j < n/2 else "right",
                    "open": "false", "powered": "false",
                })
            # A transparent full-depth transom contacts the thin door's top
            # and the centred pane above. Opaque cap bands would hide the
            # photographed upper light; this stays inside its own reveal.
            f.c.set(bx, low+2, bz, "white_stained_glass", "window")
    f.davy_openings.append({
        "side": side, "centre_m": centre, "arched": arched, "door": door,
        "front_columns": [list(q) for q in columns], "pane_columns": [list(q) for q in sorted(pane_columns)],
        "allowed": [list(q) for q in sorted(allowed)], "inward": list(inward),
        "low_y": low, "high_y_exclusive": high, "width_blocks": n, "width_m": n/f.c.scale,
        "source_width_m": width, "physical_registration": "constant U116.60 east wall; glass one cell inward" if side == "east" else "measured end wall; glass one cell inward",
    })


def _open_porch(f, body):
    cover = f.r.footprint_mask & ~body
    f.davy_porch_columns, f.davy_posts = [], []
    floor = f.height_y(56.25)
    for x, z, iz, ix in f.each_column(cover):
        top = _roof_y(f, iz, ix)
        # Preserve the measured cap and original full substrate. A flat
        # clearing height would cut through the lower measured roof faces.
        for y in range(floor, top-1):
            f.c.set(x, y, z, "air", "air")
        f.davy_porch_columns.append([x, z, top-1, top])
    for u, v, kind in ((120.7, -120.9, "broad"), (120.7, -109.6, "broad"),
                       (121.85, -117.45, "hood"), (121.85, -113.65, "hood")):
        scope = cover & (np.isin(SOURCE["raster"].face_indices, (3, 7, 8)) if kind == "broad"
                         else (f.r.face_indices == 1_000_014))
        x, z, iz, ix = min(f.each_column(scope), key=lambda q: (f.u[q[2], q[3]]-u)**2+(f.v[q[2], q[3]]-v)**2)
        top = _roof_y(f, iz, ix)-1
        for y in range(floor, top):
            f.c.set(x, y, z, "smooth_quartz", "trim")
        f.davy_posts.append({"nominal_uv_m": [u, v], "actual_uv_m": [float(f.u[iz, ix]), float(f.v[iz, ix])],
                            "xyz_bottom": [x, floor, z], "contact_y": top, "kind": kind})
    f.features["open_porch_roof_columns"] = len(f.davy_porch_columns)
    f.features["pale_quartz_porch_posts"] = len(f.davy_posts)


def _fascia(f, body):
    """Colour the actual roof edge, preserving the complete original shape."""
    edge = f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    f.davy_fascia = []
    for x, z, iz, ix in f.each_column(edge):
        # Long-wall roof perimeter samples include survey/raster noise.
        # Colour only source end gables and the actual projecting porch.
        long_side = -142.0 < f.v[iz, ix] < -93.0
        porch = f.u[iz, ix] > 117.3 and -122.0 < f.v[iz, ix] < -109.0
        if long_side and not porch:
            continue
        y = _roof_y(f, iz, ix)
        state = f.c.palette[f.c.get(x, y, z)]
        name, props = state["Name"], state.get("Properties", {})
        block = "quartz_stairs" if name.endswith("_stairs") else "quartz_slab" if name.endswith("_slab") else "smooth_quartz"
        f.c.set(x, y, z, block, "trim", props)
        f.davy_fascia.append([x, y, z])
    f.davy_eaves = []
    for side, rows in (("east", SOURCE["straight_rows"]), ("west", SOURCE["west_rows"])):
        inward = -1 if side == "east" else 1
        for x,z in rows.values():
            iz,ix = z-f.c.z_min,x-f.c.x_min
            v = float(f.v[iz,ix])
            if -122.0 < v < -109.0 and side == "east":
                continue
            if side == "east" and any(abs(v-centre)<=1.15 for centre in CENTRES):
                continue
            y = 69
            if _wall_y(f,iz,ix)<=y:
                continue
            # A half-height line on the regular facade plane, fully backed.
            f.c.set(x,y,z,"quartz_slab","trim",TOP)
            f.c.set(x+inward,y,z,"stone_bricks","facade")
            f.davy_eaves.append([x,y,z])
    f.features["actual_outer_roof_fascia_columns"] = len(f.davy_fascia)


def _roof_contacts(f):
    """Back steep source/hood transitions downward, never raising any cap."""
    f.davy_roof_backing = []
    for x,z,iz,ix in f.each_column(f.r.footprint_mask):
        high = _roof_y(f,iz,ix)
        neighbors = [_roof_y(f,iz+dz,ix+dx) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))
                     if f.r.footprint_mask[iz+dz,ix+dx]]
        for y in range(min(neighbors, default=high), high-1):
            if f.c.get(x,y,z) == 0:
                f.c.set(x,y,z,"deepslate_tiles","roof")
                f.davy_roof_backing.append([x,y,z])
    f.features["local_roof_step_backing_cells"] = len(f.davy_roof_backing)


def _gable_fascia(f):
    """Thin sloping caps above masonry; never recolour vertical risers white."""
    outlines = []
    for i, centre in enumerate(CENTRES):
        rows = {}
        for x,z in SOURCE['straight_rows'].values():
            iz,ix=z-f.c.z_min,x-f.c.x_min
            if abs(f.v[iz,ix]-centre)>1.05:
                continue
            while f.u[iz,ix]>116.75 or not f.r.footprint_mask[iz,ix]:
                x-=1;ix-=1
            rows[z]=(x,z)
        route = []
        for q in [rows[k] for k in sorted(rows)]:
            if route and abs(q[0]-route[-1][0])+abs(q[1]-route[-1][1]) == 2:
                route.append(min(((q[0],route[-1][1]),(route[-1][0],q[1])),key=lambda v:v[0]))
            if q not in route: route.append(q)
        cells = []
        for x,z in route:
            iz,ix=z-f.c.z_min,x-f.c.x_min;top=_roof_y(f,iz,ix)
            for y in range(69,top):
                f.c.set(x,y,z,'stone_bricks','facade')
            state=f.c.palette[f.c.get(x,top,z)]
            if state['Name'].endswith('_slab'):
                block,props='quartz_slab',state.get('Properties',{})
            else:
                block,props='quartz_stairs',{'half':'bottom','facing':'south' if f.v[iz,ix]<centre else 'north','shape':'straight','waterlogged':'false'}
            f.c.set(x,top,z,block,'trim',props);cells.append([x,top,z])
        outlines.append({'centre_v_m':centre,'ridge_navd88_m':62.0,'route_xz':[list(q) for q in route],'trim_cells':cells})
    f.davy_gable_outlines=outlines


def _rails(f):
    f.davy_rails = []
    runs = [("east", 123, -144.4, -118), ("east", 123, -113.2, -89.2),
            ("north", -144.2, 108.5, 123), ("south", -89.4, 108.5, 123)]
    for side, at, a, b in runs:
        points = []
        for along in np.linspace(a, b, math.ceil((b-a)/.05)+1):
            world = f.world(at, along) if side == "east" else f.world(along, at)
            q = tuple(np.floor(world*f.c.scale).astype(int))
            if not points or q != points[-1]: points.append(q)
        joined = [points[0]]
        for q in points[1:]:
            previous = joined[-1]
            if abs(q[0]-previous[0])+abs(q[1]-previous[1]) == 2:
                joined.append((q[0], previous[1]))
            joined.append(q)
        for x, z in joined:
            for y in range(f.height_y(56.25), f.height_y(57.25)):
                f.c.set(int(x), y, int(z), "pale_oak_fence", "railing", PANE_PROPS)
        f.davy_rails.append({"side": side, "at_m": at, "ends_m": [a, b],
                            "columns": [list(map(int, q)) for q in joined],
                            "low_y": f.height_y(56.25), "high_y_exclusive": f.height_y(57.25)})
    f.features["photographed_pale_open_rail_runs"] = 4


def build_details(f, p):
    body = SOURCE["body"]
    f.davy_openings = []
    _wall_skin(f, body)
    f.deck((116.5, -144.4, 123.2, -89.2), 56.25, "grass_block", role="terrain")
    f.deck((116.5, -144.4, 117.9, -89.2), 56.25, "smooth_stone")
    f.deck((117.9, -121.2, 120.99, -109.3), 56.25, "stone_bricks")
    f.deck((120.99, -117.7, 123.2, -113.4), 56.25, "stone_bricks")
    f.deck((108.5, -144.4, 116.5, -142.5), 56.25)
    f.deck((108.5, -91.5, 116.5, -89.2), 56.25)
    _open_porch(f, body)
    _roof_contacts(f)
    _fascia(f, body)
    _gable_fascia(f)
    for centre in CENTRES:
        _opening(f, body, "east", centre, 1.15, 57.15, 2.0, arched=True)
    for centre in PLAIN:
        _opening(f, body, "east", centre, 1.15, 57.15, 2.0)
    _opening(f, body, "east", -115.6, 1.6, 56.25, 2.4, door=True)
    _opening(f, body, "north", 111, 1.25, 56.25, 2.3, arched=True, door=True)
    _rails(f)
    for v in np.arange(-143, -89, 4.8):
        f.box((122.4, v-.2, 122.9, v+.2), 54.8, 55.8, "stone_bricks", "facade")
    f.site_surface([(122.8, -118), (126.2, -118), (126.2, -113.2), (122.8, -113.2)], 55.75)
    f.deck((122.8, -118, 124, -113.2), 56.0)
    f.floor_plate(56.25)
    connect_window_panes(f.c)
    f.features.update(photographed_pond_gables=7, photographed_pond_plain_windows=4,
                      provisional_west_roof_gables=7, unverified_west_window_groups=0,
                      open_terrace=1, open_two_stage_porch=1)
    SOURCE["details"] = {"openings": f.davy_openings, "porch_columns": f.davy_porch_columns,
                         "posts": f.davy_posts, "fascia": f.davy_fascia, "rails": f.davy_rails,
                         "roof_step_backings": f.davy_roof_backing, "east_gable_outlines":f.davy_gable_outlines,
                         "wall_plane_changes": f.davy_wall_plane_changes,
                         "straight_wall_rows": [list(q) for _,q in sorted(SOURCE["straight_rows"].items())],
                         "west_wall_rows": [list(q) for _,q in sorted(SOURCE["west_rows"].items())],
                         "regular_eave_caps": f.davy_eaves}
