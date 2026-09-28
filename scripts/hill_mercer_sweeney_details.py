"""Source-bound Mercer, Day and Sweeney exteriors in the measured 9-degree frame."""

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_cdt
from shapely import contains_xy

from build_hill_chapel_sample import ROLES
from campus_academic_building import PANE_PROPS
from campus_roof_geometry import load_measured_building

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {}
SLAB = {'type': 'bottom', 'waterlogged': 'false'}


def prepare_roof(r, f, p):
    for item in (p['reference_packet'], *p['reference_addenda']):
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == item['sha256']
    building = load_measured_building(parent_id=p['parent_id'])
    assert building.source_sha256 == p['source_roof_sha256']
    faces = []
    for index, face in enumerate(building.roof_faces):
        value = dict(xz=list(map(list, face.polygon.exterior.coords)),
                     holes=[list(map(list, ring.coords)) for ring in face.polygon.interiors],
                     plane=[face.a, face.b, face.c], surface=face.surface_index,
                     part=face.part_id)
        faces.append(dict(index=index, geometry=value,
                          sha256=hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()))
    parts = list(building.footprint.geoms)
    detached = min(parts, key=lambda polygon: polygon.area)
    assert detached.area < 30 and detached.bounds[0] > 110
    excluded = contains_xy(detached, f.x, f.z)
    assert set(np.unique(r.face_indices[excluded])) <= {-1, 58, 59, 60}
    heights, gx, gz, ids = (array.copy() for array in
                           (r.heights, r.gradient_x, r.gradient_z, r.face_indices))
    heights[excluded] = np.nan
    gx[excluded] = gz[excluded] = 0
    ids[excluded] = -1
    adjusted = replace(r, heights=heights, gradient_x=gx, gradient_z=gz,
                       face_indices=ids, footprint_mask=r.footprint_mask & ~excluded,
                       missing_mask=r.missing_mask & ~excluded)
    SOURCE.clear()
    SOURCE.update(building=building, original_raster=r, raster=adjusted,
                  details=dict(source_faces=faces, excluded_child_columns=[
                      [x, z, int(r.face_indices[iz, ix]), float(r.heights[iz, ix])]
                      for x, z, iz, ix in f.each_column(excluded)],
                      wall_planes=[], openings=[], roof_material_cells=[],
                      inward_wall_bridges=[], floors=[], trim_cells=[], arch_contact_repairs=[], roof_spur_wall_removals=[], roof_seam_backing=[], roof_spur_bridge=[],
                      source_sequence=p['source_sequence'], limitations=[]))
    return adjusted


def uv(f, x, z):
    iz, ix = z-f.c.z_min, x-f.c.x_min
    return float(f.u[iz, ix]), float(f.v[iz, ix])


def path_columns(f, points, inward):
    """Minimal cardinal trace just inside the measured full-block wall face.

    A full-cell facade occupies the inside of its physical plane. Its centre
    is inset by 0.31 m so the cell-centre sampling never places upper glazing
    over a lower roof strip on the outside of the measured tall wall.
    """
    chain = []
    for start, end in zip(points, points[1:]):
        a, b = (f.world(*start)+inward*.31)*2-.5, (f.world(*end)+inward*.31)*2-.5
        for point in np.linspace(a, b, max(2, math.ceil(max(abs(b-a))*12))):
            q = tuple(int(round(value)) for value in point)
            if chain and q == chain[-1]:
                continue
            if chain and sum(abs(q[i]-chain[-1][i]) for i in (0, 1)) == 2:
                old = chain[-1]
                chain.append(max(((old[0], q[1]), (q[0], old[1])),
                                 key=lambda cell: np.dot(cell, inward)))
            chain.append(q)
    return list(dict.fromkeys(chain))


def cap_y(f, x, z):
    iz, ix = z-f.c.z_min, x-f.c.x_min
    if not f.r.footprint_mask[iz, ix] or not np.isfinite(f.r.heights[iz, ix]):
        return None
    return (math.floor((float(f.r.heights[iz, ix])-25)*4+.5)-1)//2


def wall_plane(f, name, side, at, ends, low, high, *, points=None):
    """Authored skin stays within 0.75 m of its measured straight facade."""
    east = side in ('east', 'west')
    inward = (-f.t if side == 'east' else f.t) if east else (f.n if side == 'north' else -f.n)
    points = points or ([(at, ends[0]), (at, ends[1])] if east else [(ends[0], at), (ends[1], at)])
    trace = path_columns(f, points, inward)
    normal, along = (f.u, f.v) if east else (f.v, f.u)
    slope = ((points[1][0]-points[0][0])/(points[1][1]-points[0][1])) if east else ((points[1][1]-points[0][1])/(points[1][0]-points[0][0]))
    start_normal, start_along = (points[0][0], points[0][1]) if east else (points[0][1], points[0][0])
    analytic_normal = start_normal+slope*(along-start_along)
    strip = (abs(normal-analytic_normal) < .75) & (along >= ends[0]+.5) & (along <= ends[1]-.5)
    trace_set = set(trace)
    cleared, filled = [], []
    # A source roof cap and its backing are never touched by the wall-plane operation.
    for x, z, iz, ix in f.each_column(strip):
        if (x, z) in trace_set:
            continue
        for y in range(f.height_y(low), f.height_y(high)):
            if ROLES[f.c.roles[y+64, iz, ix]] == 'facade':
                f.c.set(x, y, z, 'air', 'air')
                cleared.append([x, y, z])
    for x, z in trace:
        roof = cap_y(f, x, z)
        if roof is None:
            # A centre trace can lie one cell outside the measured footprint.
            # Its cap is bounded by the immediately inward source column.
            dx, dz = (int(np.sign(inward[0])), 0) if abs(inward[0]) > abs(inward[1]) else (0, int(np.sign(inward[1])))
            roof = cap_y(f, x+dx, z+dz)
        if roof is None:
            continue
        for y in range(max(f.height_y(low), f.c.ground_at(x, z)), min(f.height_y(high), roof-1)):
            role = ROLES[f.c.roles[y+64, z-f.c.z_min, x-f.c.x_min]]
            if role in ('air', 'facade'):
                f.c.set(x, y, z, 'bricks', 'facade')
                filled.append([x, y, z])
    record = dict(name=name, side=side, plane_m=at, ends_m=ends,
                  low_navd88_m=low, high_navd88_m=high, columns=trace, analytic_points_uv_m=points,
                  cleared_cells=cleared, filled_cells=filled,
                  normal_max_cell_centre_error_m=max(abs(uv(f, *q)[0 if east else 1]-(start_normal+slope*(uv(f, *q)[1 if east else 0]-start_along))) for q in trace))
    SOURCE['details']['wall_planes'].append(record)
    return trace


def opening(f, name, side, at, centre, width, bottom, height, *, arched=False, glass='light_gray_stained_glass_pane'):
    """Cardinal pane trace, narrow solid jambs and backed partial arch heads."""
    east = side in ('east', 'west')
    inward = (-f.t if side == 'east' else f.t) if east else (f.n if side == 'north' else -f.n)
    ends = [centre-width/2-.5, centre+width/2+.5]
    points = [(at, q) for q in ends] if east else [(q, at) for q in ends]
    columns = path_columns(f, points, inward)
    along = lambda q: uv(f, *q)[1 if east else 0]
    pane_columns = [q for q in columns if abs(along(q)-centre) <= width/2]
    if not pane_columns:
        raise ValueError(name)
    first, last = columns.index(pane_columns[0]), columns.index(pane_columns[-1])
    columns = columns[max(0, first-1):min(len(columns), last+2)]
    pane_set = set(pane_columns)
    a = f.height_y(bottom)
    heights = {}
    for q in pane_columns:
        # Fit the complete pane cell below the semicircle rather than only
        # testing its centre. The outer columns therefore form visible
        # shoulders and a narrower crown at this half-metre resolution.
        distance = min(width/2, abs(along(q)-centre)+(.25 if arched else 0))
        radius = min(width/2, height/2)
        top = bottom+height-radius+math.sqrt(max(0, radius*radius-distance*distance)) if arched else bottom+height
        roof = cap_y(f, *q)
        if roof is None:
            dx, dz = (int(np.sign(inward[0])), 0) if abs(inward[0]) > abs(inward[1]) else (0, int(np.sign(inward[1])))
            roof = cap_y(f, q[0]+dx, q[1]+dz)
        # Retain both the original roof cap and one full substrate cell.
        target_y = math.floor((top-25)*2+1e-7) if arched else f.height_y(top)
        heights[q] = min(target_y, (roof-2 if roof is not None else target_y))
    if min(heights.values()) < a+2:
        SOURCE['details']['limitations'].append(dict(opening=name, reason='source low roof leaves insufficient height', proposed=dict(at=at, centre=centre, bottom=bottom, height=height)))
        return
    highest = max(heights.values())
    # Clear only the source wall thickness at the exact aperture, including
    # an inward turn cell that could otherwise hide a pane from one direction.
    normal, along_grid = (f.u, f.v) if east else (f.v, f.u)
    clear = (abs(normal-at) < .76) & (abs(along_grid-centre) <= width/2+.24)
    for x, z, iz, ix in f.each_column(clear):
        for y in range(a, highest):
            if (x, z) not in pane_set and ROLES[f.c.roles[y+64, iz, ix]] == 'facade':
                f.c.set(x, y, z, 'air', 'air')
    panes, heads, frames = [], [], []
    dx, dz = (int(np.sign(inward[0])), 0) if abs(inward[0]) > abs(inward[1]) else (0, int(np.sign(inward[1])))
    for i, (x, z) in enumerate(columns):
        if (x, z) not in pane_set:
            nearest_pane = min(pane_columns, key=lambda q: abs(along(q)-along((x,z))))
            jamb_top = heights[nearest_pane]+1 if arched else highest+1
            for y in range(a-1, jamb_top):
                roof = cap_y(f, x, z)
                if roof is not None and y >= roof-1:
                    continue
                f.c.set(x, y, z, 'smooth_quartz', 'trim')
                frames.append([x, y, z])
            for y in range(jamb_top, highest+1):
                roof = cap_y(f, x, z)
                if roof is not None and y < roof-1:
                    f.c.set(x, y, z, 'bricks', 'facade')
            continue
        b = heights[x, z]
        f.c.set(x, a-1, z, 'quartz_slab' if arched else 'smooth_quartz', 'trim',
                {'type':'top','waterlogged':'false'} if arched else None)
        if arched:
            bx, bz = x+dx, z+dz
            while (bx,bz) in columns:
                bx, bz = bx+dx, bz+dz
            f.c.set(bx, a-1, bz, 'bricks', 'facade')
        frames.append([x, a-1, z])
        for y in range(a, b):
            f.c.set(x, y, z, glass, 'window', PANE_PROPS)
            panes.append([x, y, z])
        if arched and b < highest:
            tangent = f.n if east else f.t
            direction = tangent * (1 if along((x, z)) < centre else -1)
            facing = ('east' if direction[0] > 0 else 'west') if abs(direction[0]) > abs(direction[1]) else ('south' if direction[1] > 0 else 'north')
            f.c.set(x, b, z, 'quartz_stairs', 'trim', dict(facing=facing, half='bottom', shape='straight', waterlogged='false'))
        else:
            f.c.set(x, b, z, 'quartz_slab' if arched else 'smooth_quartz', 'trim', SLAB if arched else None)
        heads.append([x, b, z])
        # Solid inward backing anchors every arch head and fills its upper
        # reveal without substituting opaque blocks for the tall pane face.
        for y in range(b, highest+1):
            backroof = cap_y(f, x+dx, z+dz)
            if backroof is not None and y < backroof-1:
                f.c.set(x+dx, y, z+dz, 'bricks', 'facade')
        for y in range(b+1, highest+1):
            roof = cap_y(f, x, z)
            if roof is None or y < roof-1:
                f.c.set(x, y, z, 'bricks', 'facade')
    SOURCE['details']['openings'].append(dict(name=name, side=side, plane_m=at,
        centre_m=centre, width_m=width, bottom_navd88_m=bottom, height_m=height,
        arched=arched, columns=columns, panes=panes, heads=heads, frames=frames,
        actual_pane_tops=[[*q, heights[q]] for q in pane_columns],
        source_roof_height_clipped=any(heights[q] < f.height_y(bottom+height)-2 for q in pane_columns)))


def retint_roofs(f, p):
    pitched_faces = set(p['roof_retint_scope']['sweeney_pitched_face_indices'])
    source_family = {'minecraft:deepslate_tiles', 'minecraft:deepslate_tile_slab', 'minecraft:deepslate_tile_stairs'}
    for iy, iz, ix in np.argwhere(f.c.roles == ROLES.index('roof')):
        state = f.c.palette[f.c.data[iy, iz, ix]]
        name = state['Name']
        x, y, z = int(ix)+f.c.x_min, int(iy)+f.c.y_min, int(iz)+f.c.z_min
        face = int(f.r.face_indices[iz, ix])
        layer = y-cap_y(f, x, z)
        if f.u[iz, ix] < 27.5:
            target = 'smooth_stone_slab' if name.endswith('_slab') else 'smooth_quartz_stairs' if name.endswith('_stairs') else 'smooth_stone'
            scope = 'retained Mercer pale roof'
        elif face in pitched_faces and layer in (0,-1) and name in source_family:
            target = 'polished_andesite_slab' if name.endswith('_slab') else 'polished_andesite_stairs' if name.endswith('_stairs') else 'polished_andesite'
            scope = 'Sweeney pitched cap and immediate roof-role substrate'
        else:
            target = name
            scope = 'retained dark roof or wall-facing substrate'
        f.c.set(x, y, z, target, 'roof', state.get('Properties'))
        SOURCE['details']['roof_material_cells'].append(dict(xyz=[x, y, z], before=state,
            after=f.c.palette[f.c.get(x, y, z)], source_face=face, layer_below_cap=layer, material_scope=scope))


def interior_floor(f, name, bounds, level, block):
    mask = f.local_mask(bounds) & (distance_transform_cdt(f.r.footprint_mask, metric='taxicab') >= 3) & (f.r.heights > level+2)
    half = math.floor((level-25)*4+.5)
    y = (half-1)//2
    cells = []
    for x, z, iz, ix in f.each_column(mask):
        if ROLES[f.c.roles[y+64, iz, ix]] not in ('air', 'floor'):
            continue
        f.c.set(x, y, z, 'smooth_stone_slab' if half % 2 else block, 'floor', SLAB if half % 2 else None)
        cells.append([x, y, z])
    SOURCE['details']['floors'].append(dict(name=name, proposed_navd88_m=level, actual_navd88_m=half/4+25,
        cells=cells, limitation='Regional floor surface only; structure, circulation and fit-out remain incomplete'))


def inward_corner_bridges(f):
    """Close only interior diagonal masonry joins; never project a buttress."""
    solid_roles = {ROLES.index('facade'), ROLES.index('trim')}
    for y in range(f.height_y(53.6), f.height_y(73.5)):
        body = f.r.footprint_mask & (f.r.heights > (y+2)/2+25)
        boundary = body & ~binary_erosion(body, iterations=2)
        for x, z, iz, ix in f.each_column(boundary):
            if f.c.get(x, y, z):
                continue
            neighbors = [(dx, dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if f.c.roles[y+64, iz+dz, ix+dx] in solid_roles]
            if not any(a[0]*b[0]+a[1]*b[1] == 0 for a in neighbors for b in neighbors):
                continue
            # Aperture reveals are owned by their explicit pane/frame trace.
            if any(f.c.palette[f.c.get(x+dx, y, z+dz)]['Name'].endswith('_pane') for dx, dz in ((1,0),(-1,0),(0,1),(0,-1))):
                continue
            f.c.set(x, y, z, 'bricks', 'facade')
            SOURCE['details']['inward_wall_bridges'].append([x, y, z])


def complete_arch_jamb_contacts(f):
    """A pane edge meets solid stone, with the thin shaped shoulder above it."""
    for record in SOURCE['details']['openings']:
        columns = [tuple(q) for q in record['columns']]
        pane_cells = {tuple(q) for q in record['panes']}
        heads = {tuple(q) for q in record['heads']}
        for x, y, z in sorted(pane_cells):
            index = columns.index((x, z))
            for neighbor_index in (index-1, index+1):
                if not 0 <= neighbor_index < len(columns):
                    continue
                nx, nz = columns[neighbor_index]
                q = (nx, y, nz)
                state = f.c.palette[f.c.get(*q)]
                if state['Name'].endswith(('_stairs', '_slab')) and q in heads:
                    f.c.set(*q, 'smooth_quartz', 'trim')
                    above = (nx, y+1, nz)
                    roof = cap_y(f, nx, nz)
                    adjacent_upper_pane = any((nx+dx, y+1, nz+dz) in pane_cells
                        for dx, dz in ((1,0),(-1,0),(0,1),(0,-1)))
                    if above not in pane_cells and not adjacent_upper_pane and roof is not None and y+1 < roof-1:
                        f.c.set(*above, state['Name'], 'trim', state.get('Properties'))
                    SOURCE['details']['arch_contact_repairs'].append(dict(opening=record['name'],xyz=list(q),before=state,
                        rule='Solid masonry contacts the upper pane side; shaped head is retained above when below the source substrate'))


def back_middle_roof_seam(f):
    """Back the 0.75 m face8/13 drop below its unchanged measured cap.

    At one grid turn the shared shell's single backing block ends above the
    neighboring stair's empty upper half. One further inward substrate cell
    closes that underside contact; no measured surface is lifted or filled.
    """
    for x, z, iz, ix in f.each_column(f.r.footprint_mask & (f.r.face_indices == 8)):
        top = cap_y(f, x, z)
        y = top-2
        if f.c.get(x, y, z):
            continue
        for dx, dz in ((1,0),(-1,0),(0,1),(0,-1)):
            if f.r.face_indices[iz+dz, ix+dx] != 13:
                continue
            neighbor = cap_y(f, x+dx, z+dz)
            if neighbor is not None and top-neighbor >= 2:
                f.c.set(x, y, z, 'deepslate_tiles', 'roof')
                SOURCE['details']['roof_seam_backing'].append(dict(xyz=[x,y,z],source_cap_y=top,
                    lower_neighbor=[x+dx,neighbor,z+dz],source_face=8,neighbor_face=13))
                break


def build_details(f, p):
    retint_roofs(f, p)
    # Retain surveyed terrain outside the existing parent. Different floor
    # plates respect the low north Mercer grade and the higher south rooms.
    interior_floor(f, 'Mercer main floor', [-63, -116, 27.5, -76.5], 56.4, 'smooth_stone')
    interior_floor(f, 'Sweeney hall floor', [64, -125, 88, -77], 56.25, 'birch_planks')
    interior_floor(f, 'Sweeney south lobby', [65, -77, 86.5, -71.4], 58.7, 'smooth_stone')

    # Roof-raster noise is removed from the bounded wall strip only. These
    # measured main planes deliberately do not erase the two gabled bays.
    wall_plane(f, 'Mercer north', 'north', -122.0, [-62, 26], 53.6, 64.1)
    wall_plane(f, 'Mercer south west', 'south', -77.46, [-62, -7], 56.4, 64.1)
    wall_plane(f, 'Mercer south east', 'south', -76.59, [-5, 26], 56.4, 64.1)
    wall_plane(f, 'Day measured high north front', 'north', -120.6, [29, 59], 58.5, 63.3,
               points=[(29, -120.93+(29-14.883)*.466/44.556), (59, -120.93+(59-14.883)*.466/44.556)])
    wall_plane(f, 'Sweeney straight east front', 'east', 88.12, [-124.4, -76.8], 56.25, 69.0)
    # Sol's measured-plane addendum identifies the penultimate gable's
    # irregular eastward source cells as a roof spur, not a wall extrusion.
    # Keep its exact cap/backing and remove only its inherited tall masonry.
    spur = f.local_mask([88.45, -86.5, 89.9, -79.4]) & f.r.footprint_mask
    for x, z, iz, ix in f.each_column(spur):
        roof = cap_y(f, x, z)
        for y in range(f.height_y(56.25), roof-1):
            if ROLES[f.c.roles[y+64, iz, ix]] == 'facade':
                f.c.set(x, y, z, 'air', 'air')
                SOURCE['details']['roof_spur_wall_removals'].append([x, y, z])
    wall_plane(f, 'Sweeney north gable', 'north', -130.285, [72, 80.7], 56.25, 70)

    # Mercer: pale opaque panel field, then narrow vertical glazing. The
    # precise strip rhythm is interpreted; it is not a glass curtain wall.
    for side, at, ends in [('north', -122.0, [-62, 26]), ('south', -77.46, [-62, -7]), ('south', -76.59, [-5, 26])]:
        trace = path_columns(f, [(ends[0], at), (ends[1], at)], f.n if side == 'north' else -f.n)
        for x, z in trace:
            roof = cap_y(f, x, z)
            for y in range(f.height_y(60.5), f.height_y(64.1)):
                role = ROLES[f.c.roles[y+64, z-f.c.z_min, x-f.c.x_min]]
                if role == 'facade' and (roof is None or y < roof-1):
                    f.c.set(x, y, z, 'white_concrete', 'facade')
        for centre in p['mercer_strip_centres_u_m']:
            if ends[0]+1 <= centre <= ends[1]-1:
                plane = at
                if side == 'north' and centre >= 12.147:
                    plane = (-122.019+(centre-12.147)*1.089/2.736) if centre < 14.883 else (-120.93+(centre-14.883)*.466/44.556)
                opening(f, f'mercer-{side}-strip-{centre:g}', side, plane, centre, 1.0, 60.5, 3.15,
                        glass='light_gray_stained_glass_pane')

    for centre, at in [(-59, -77.46), (-1.5, -76.59), (23, -76.59)]:
        opening(f, f'mercer-south-glazed-entry-{centre:g}', 'south', at, centre, 3.2, 56.4, 2.8)

    for index, centre in enumerate(p['sweeney_east_centres_v_m']):
        projected = index in (1, 8)
        at = 88.12
        opening(f, f'sweeney-east-tall-{index+1}', 'east', at, centre, 2.1, 60.35,
                5.6 if projected else 4.6, arched=True)
        opening(f, f'sweeney-east-lower-{index+1}', 'east', 88.12, centre, 1.2, 56.9, 1.65)
    opening(f, 'sweeney-north-central-arch', 'north', -130.285, 76.3, 2.5, 64.0, 4.7, arched=True)
    # The lower central opening is on the measured projecting front. The
    # shoulder openings follow the shallow measured shoulder fronts.
    for centre, at in [(67.8, -128.892+(67.8-64.595)*.171/6.142), (76.3, -130.285),
                       (84.5, -129.141+(84.5-80.963)*.566/7.17)]:
        opening(f, f'sweeney-north-lower-{centre:g}', 'north', at, centre, 1.15, 57.0, 1.6)
    for index, centre in enumerate(p['day_north_centres_u_m']):
        at = -120.93+(centre-14.883)*.466/44.556
        opening(f, f'day-north-arch-{index+1}', 'north', at, centre, 1.5, 59.0, 3.2, arched=True)

    # Narrow stone courses are retints of occupied wall cells, with no
    # projecting continuous ledge or unsupported half-block decoration.
    for level in (59.6, 65.9):
        f.wall_band('east', 88.12, [-126.0, -76.4], level, .25, 'smooth_quartz', .45)
    # Source gable coping retains each existing cap shape and physical top.
    outer = f.r.footprint_mask & ~binary_erosion(f.r.footprint_mask)
    coping = (f.v < -129.65) & (f.u > 71.6) & (f.u < 81.0)
    coping |= outer & (f.u > 87.75) & np.isin(f.r.face_indices, [0, 18, 1, 34])
    for x, z, iz, ix in f.each_column(f.r.footprint_mask & coping):
        y = cap_y(f, x, z)
        if y is None or ROLES[f.c.roles[y+64, iz, ix]] != 'roof':
            continue
        before = f.c.palette[f.c.get(x, y, z)]
        target = 'quartz_slab' if before['Name'].endswith('_slab') else 'quartz_stairs' if before['Name'].endswith('_stairs') else 'smooth_quartz'
        f.c.set(x, y, z, target, 'trim', before.get('Properties'))
        SOURCE['details']['trim_cells'].append(dict(xyz=[x, y, z], before=before, after=f.c.palette[f.c.get(x, y, z)]))
    complete_arch_jamb_contacts(f)
    back_middle_roof_seam(f)
    # Sol explicitly authorizes this single underside return across the
    # source's diagonal cell-centre gap. Existing spur and main caps stay put.
    assert not f.c.get(201,80,-132)
    f.c.set(201,80,-132,'polished_andesite_slab','roof',SLAB)
    SOURCE['details']['roof_spur_bridge'].append(dict(xyz=[201,80,-132],physical_top_y=80.5,
        contacts=[[202,80,-132],[201,80,-133]],authority='mercer-sweeney-v4-arch-roof-spur-addendum-20260919.json'))
    inward_corner_bridges(f)
    f.features.update(sweeney_tall_east_arches=10, sweeney_measured_gabled_bays=2,
                      sweeney_north_arch=1, day_north_arches=8,
                      mercer_panel_glazing_strips=sum(q['name'].startswith('mercer-') for q in SOURCE['details']['openings']))
