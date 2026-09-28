"""Build a source-bounded Wendell exterior in a fresh, immutable study directory.

The three source RoofSurface strips at grade are explicitly site surfaces.
No south/east facade schedule is inferred and native acceptance is separate.
"""

import argparse
from dataclasses import replace
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil

import numpy as np
from scipy.ndimage import binary_erosion, binary_propagation, distance_transform_cdt
from shapely import contains_xy
from shapely.ops import unary_union

from audit_hill_block_artifact import audit as audit_export
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_quad_landscape import set_surface
from campus_reference_details import ReferenceExterior
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study, write_json
from campus_window_frames import pane_joint_report, pane_support_report, pane_perimeter_report
from render_voxel_sample import BlockState, VanillaResources, applications_for_state, elements_for_state, rotate_model_point

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'runtime/research/campus-full-detail-20260905/wendell-reference-packet-20260919.json'
PACKET_SHA = 'a8249734e35fd9075d03aced08ff1cf80c9c2cbfe2ab7a00b4d0ab82555a6de7'
TERRAIN = ROOT / 'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz'
HIGH = [0, 1, 2, 3, 6, 7, 8, 9, 10, 12]
LOW = [4, 5, 11]
CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))


def canonical(face):
    return dict(xz=list(map(list, face.polygon.exterior.coords)),
                holes=[list(map(list, ring.coords)) for ring in face.polygon.interiors],
                plane=[face.a, face.b, face.c], source_surface_index=face.surface_index,
                min_h=face.min_h, max_h=face.max_h)


def solid_wall_corners(c, r, shell):
    """Join the inward corner of diagonal measured-boundary cells, below roof."""
    body = r.footprint_mask
    boundary = shell.exterior_wall_mask
    columns = set(map(tuple, np.argwhere(boundary)))
    bridges = []
    for iz, ix in sorted(columns):
        for dz in (-1, 1):
            end = (iz + dz, ix + 1)
            if end not in columns:
                continue
            candidates = [q for q in ((iz, ix + 1), (iz + dz, ix)) if body[q]]
            if len(candidates) != 1:
                continue
            jz, jx = candidates[0]
            columns.add((jz, jx))
            low = shell.floor_y + 1
            high = min(int(shell.roof_block_y[iz, ix]), int(shell.roof_block_y[end]),
                       int(shell.roof_block_y[jz, jx])) - 1
            for y in range(low, high):
                x, z = int(jx) + c.x_min, int(jz) + c.z_min
                if c.get(x, y, z) == 0:
                    c.set(x, y, z, 'bricks', 'facade')
                    bridges.append([x, y, z])
    mask = np.zeros_like(body)
    for iz, ix in columns:
        mask[iz, ix] = True
    return mask, bridges


def window(f, wall, side, centre, width, bottom, height, name):
    """Glaze the existing wall trace; pale quarter-metre heads/sills are backed."""
    c = f.c
    normal, along = (f.v, f.u) if side == 'north' else (f.u, f.v)
    plane = .0030785879334772476 * f.u - 6.037006675521414 if side == 'north' else -21.36
    selected = wall & (abs(normal - plane) < 1.05) & (abs(along - centre) <= width / 2)
    a, b = f.height_y(bottom), f.height_y(bottom + height)
    pane_cells, caps, backers = [], [], []
    inward = f.n if side == 'north' else f.t
    for x, z, iz, ix in f.each_column(selected):
        for y in range(a, b):
            assert c.get(x, y, z), (name, 'missing original wall', x, y, z)
            c.set(x, y, z, 'light_gray_stained_glass_pane', 'window', PANE_PROPS)
            pane_cells.append([x, y, z])
        for y, typ in ((a - 1, 'top'), (b, 'bottom')):
            c.set(x, y, z, 'smooth_stone_slab', 'trim', {'type': typ, 'waterlogged': 'false'})
            caps.append([x, y, z])
            # A full inward brick immediately behind each partial frame cap
            # closes the unused half of its wall cell without projecting out.
    backing = f.r.footprint_mask & ~wall & (abs(normal-plane) < 1.8) & (abs(along-centre) <= width/2+1.0)
    for bx, bz, iz, ix in f.each_column(backing):
        for y in (a-1, b):
            c.set(bx, y, bz, 'bricks', 'facade')
            backers.append([bx, y, bz])
    assert pane_cells, name
    return dict(name=name, side=side, centre_m=centre, width_m=width,
                bottom_navd88_m=bottom, height_m=height, pane_cells=pane_cells,
                cap_cells=caps, cap_backing_cells=backers,
                observation='Four north rows and west centered stack observed; exact centre/size/height interpreted.')


def shape_audit(c, r, entry_columns):
    """Read vanilla model geometry for enclosure, pane caps and partial contacts."""
    jar = Path('C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar')
    cache = {}
    with VanillaResources(jar) as resources:
        def shape(q):
            state = c.palette[c.get(*q)]
            key = json.dumps(state, sort_keys=True)
            if key not in cache:
                grid = np.zeros((16, 16, 16), bool)
                if state['Name'] != 'minecraft:air':
                    bs = BlockState(state['Name'], state.get('Properties', {}))
                    for app in applications_for_state(resources.blockstate(bs.name), bs.properties, q):
                        for e in elements_for_state(resources.model(app.model), bs):
                            points = np.array([rotate_model_point(p, app) for p in itertools.product(*zip(e['from'], e['to']))])
                            lo = np.maximum(0, np.rint(points.min(0)).astype(int))
                            hi = np.minimum(16, np.rint(points.max(0)).astype(int))
                            grid[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = True
                cache[key] = grid
            return cache[key]

        pane_caps, partial, roof_caps, roof_backing = [], [], [], []
        arch = [ROLES.index(q) for q in ('roof', 'facade', 'trim', 'window', 'floor')]
        for iy, iz, ix in np.argwhere(np.isin(c.roles, arch)):
            q = (int(ix) + c.x_min, int(iy) - 64, int(iz) + c.z_min)
            state = c.palette[c.data[iy, iz, ix]]
            name = state['Name']
            if not name.endswith(('_pane', '_slab', '_stairs')):
                continue
            a = shape(q); x, y, z = q
            if name.endswith('_pane'):
                for dy, face, other in ((-1, 0, 15), (1, 15, 0)):
                    if not (a[:, face, :] & shape((x, y + dy, z))[:, other, :]).any():
                        pane_caps.append([*q, dy])
            else:
                contact = (a[:, 0, :] & shape((x, y - 1, z))[:, 15, :]).any()
                contact |= (a[0, :, :] & shape((x - 1, y, z))[15, :, :]).any()
                contact |= (a[15, :, :] & shape((x + 1, y, z))[0, :, :]).any()
                contact |= (a[:, :, 0] & shape((x, y, z - 1))[:, :, 15]).any()
                contact |= (a[:, :, 15] & shape((x, y, z + 1))[:, :, 0]).any()
                if not contact:
                    partial.append(list(q))
        for iz, ix in np.argwhere(r.footprint_mask):
            x, z = int(ix) + c.x_min, int(iz) + c.z_min
            expected = math.floor((float(r.heights[iz, ix]) - 25) * 4 + .5) / 2
            y = math.ceil(expected) - 1
            a = shape((x, y, z))
            actual = y + (np.nonzero(a)[1].max() + 1) / 16 if a.any() else None
            if expected != actual:
                roof_caps.append(dict(xz=[x, z], expected=expected, actual=actual))
            if not shape((x, y - 1, z)).all():
                roof_backing.append([x, y - 1, z])
        rows, cols = np.nonzero(r.footprint_mask)
        lz, hz = int(rows.min()) - 2, int(rows.max()) + 3
        lx, hx = int(cols.min()) - 2, int(cols.max()) + 3
        slices = []
        # Every half-block height through the facade: exact 1/16 block model
        # masks sampled below/above the centre catch slab and pane leaks.
        for y in range(81, 105):
            interior = distance_transform_cdt(r.footprint_mask & (r.heights > (y + 1) / 2 + 25 + .5), metric='taxicab') >= 3
            for sub in (4, 12):
                layer = np.zeros(((hz - lz) * 16, (hx - lx) * 16), bool)
                for iz, ix in np.argwhere(c.data[y + 64, lz:hz, lx:hx] != 0):
                    iz, ix = int(iz) + lz, int(ix) + lx
                    a = shape((ix + c.x_min, y, iz + c.z_min))
                    layer[(iz-lz)*16:(iz-lz+1)*16, (ix-lx)*16:(ix-lx+1)*16] = a[:, sub, :].T
                # The deliberately traversable entry is a declared exception
                # for facade enclosure only; its actual route is checked apart.
                for x, z in entry_columns:
                    iz, ix = z - c.z_min, x - c.x_min
                    layer[(iz-lz)*16:(iz-lz+1)*16, (ix-lx)*16:(ix-lx+1)*16] = True
                seeds = np.zeros_like(layer); seeds[0, :] = seeds[-1, :] = seeds[:, 0] = seeds[:, -1] = True
                outside = binary_propagation(seeds, mask=~layer)
                leak = []
                for iz, ix in np.argwhere(interior):
                    if outside[(iz-lz)*16+8, (ix-lx)*16+8]:
                        leak.append([int(ix)+c.x_min, y, int(iz)+c.z_min])
                slices.append(dict(y=y, subvoxel_height=sub, tested_interior_columns=int(interior.sum()),
                                   leaks=len(leak), examples=leak[:4]))
    return dict(pane_head_sill_failures=pane_caps, unsupported_partial_blocks=partial,
                architectural_cap_failures=roof_caps, roof_backing_failures=roof_backing,
                facade_slices=slices, declared_enclosure_exception='The one provisional usable entry corridor only.',
                passed=not(pane_caps or partial or roof_caps or roof_backing or any(q['leaks'] for q in slices)))


def build(output):
    if output.exists():
        raise FileExistsError(output)
    assert digest(PACKET) == PACKET_SHA
    packet = json.loads(PACKET.read_text(encoding='utf-8'))
    for key in ('cityjson', 'roof_face_analysis', 'terrain_controls'):
        source = packet['measured_sources'][key]
        assert digest(ROOT / source['path']) == source['sha256']
    assert digest(TERRAIN) == packet['measured_sources']['terrain_controls']['terrain_sha256']
    b = load_measured_building(parent_id=packet['parent_id'])
    bounds = (144, -40, 232, 40)
    heights, ids, meta = terrain_arrays(TERRAIN, 2, bounds)
    c = Canvas(288, -80, heights.shape[1], heights.shape[0], 2)
    build_ground(c, heights, ids, meta['materials'], -25)
    smooth_exposed_measured_pavement(c, heights, c.ground_heights, vertical_offset=-25)
    initial_ground = c.ground_heights.copy()
    source = rasterize_roof(b, bounds, .5)
    active = np.isin(source.face_indices, HIGH) & source.footprint_mask
    r = replace(source, footprint_mask=active, missing_mask=np.zeros_like(active),
                face_indices=np.where(active, source.face_indices, -1),
                heights=np.where(active, source.heights, np.nan),
                authored_roof_patches=({'face_index': -1, 'reclassified_source_faces': LOW,
                                       'disposition': 'at-grade walk/landing/ramp, excluded from wall/roof extrusion'},))
    frame = packet['coordinate_frame']
    p = dict(name='Wendell Dormitory - measured exterior outline', revision='2026-09-27-wendell-v1-2x',
             parent_id=packet['parent_id'], school_names=['Wendell Dormitory'], school_map_numbers=[30],
             blocks_per_metre=2, vertical_offset_m=-25,
             geometry=dict(origin_xz_m=frame['origin_xz_m'], axis_degrees=frame['axis_degrees'],
                           entrance_floor_navd88_m=65.5, main_roof_threshold_navd88_m=75),
             materials=dict(facade='bricks', foundation='bricks', roof_family='polished_andesite'),
             material_review=dict(status='Frozen Sol source packet appearance proxies; native review pending'),
             reference_packet=dict(path=str(PACKET.relative_to(ROOT)), sha256=PACKET_SHA),
             assembly_site_bounds_uv_m=[[-22, -8.0, 22, 9]],
             uncertainties=packet['uncertainties'] + ['Rough exterior only; unfinished interior. Door registration and local landing are provisional within the clipped source opening tolerance.'])
    shell = build_measured_shell(c, b, r, vertical_offset=-25, floor_navd88=65.5,
                                 facade='bricks', foundation='bricks', roof_family='stone_brick', roof_backing_metres=.5)
    f = ReferenceExterior(c, p, r, -25)
    # Retain exact cap state/facing/half while selecting the packet's gray family.
    mapping = {'minecraft:stone_bricks': 'polished_andesite', 'minecraft:stone_brick_slab': 'polished_andesite_slab',
               'minecraft:stone_brick_stairs': 'polished_andesite_stairs'}
    for iy, iz, ix in np.argwhere(c.roles == ROLES.index('roof')):
        old = c.palette[c.data[iy, iz, ix]]
        c.set(int(ix)+c.x_min, int(iy)-64, int(iz)+c.z_min, mapping[old['Name']], 'roof', old.get('Properties'))
    wall, bridges = solid_wall_corners(c, r, shell)
    openings = []
    schedule = packet['facade_schedule']
    north = schedule['north_pitch_face']['interpreted_full_length_schedule']
    for row, bottom in enumerate(north['row_bottoms_navd88_m']):
        for bay, centre in enumerate(north['bay_centres_u_m']):
            if row == 0 and bay == 6:
                continue  # The source-bounded door replaces the conflicting lowest interpreted bay.
            openings.append(window(f, wall, 'north', centre, 1.55, bottom, 1.1, f'north-row-{row+1}-bay-{bay+1}'))
    for row, bottom in enumerate(schedule['west_hip_end']['main_row_bottoms_navd88_m']):
        openings.append(window(f, wall, 'west', .7, 2.0, bottom, 1.1, f'west-row-{row+1}'))
    openings.append(window(f, wall, 'west', .7, .8, 75.3, .9, 'west-attic'))
    # The directly visible thin basement course is flush in the same wall.
    belt = []
    y = 85
    for x, z, iz, ix in f.each_column(wall & ((abs(f.v + 6.0) < 1.0) | (f.u < -20.3))):
        if c.palette[c.get(x, y, z)]['Name'] == 'minecraft:bricks':
            c.set(x, y, z, 'smooth_stone_slab', 'trim', {'type': 'top', 'waterlogged': 'false'})
            belt.append([x, y, z])
            # Fill a single inward backing ring, never an exterior projection.
            for dx, dz in CARDINAL:
                if r.footprint_mask[iz+dz, ix+dx] and not wall[iz+dz, ix+dx]:
                    c.set(x+dx, y, z+dz, 'bricks', 'facade')
    # The exact low source planes become supported site surfaces.
    site = []
    for face_id in LOW:
        face = b.roof_faces[face_id]
        mask = contains_xy(face.polygon, f.x, f.z) & ~r.footprint_mask
        for x, z, iz, ix in f.each_column(mask):
            surface = (float(face.height_at(f.x[iz, ix], f.z[iz, ix])) - 25) * 2
            set_surface(c, iz, ix, surface, 'smooth_stone', 'smooth_stone_slab')
            site.append(dict(xz=[x, z], source_face=face_id, source_surface_y=surface,
                             quantized_surface_y=round(surface*2)/2))
    # One narrow observed-but-clipped entry: 14.5m U +/-1.2m in the packet.
    # The real Minecraft door is 1 block wide; the tall dark recess carries scale.
    ex, ez = np.floor(f.world(14.5, -6.0) * 2).astype(int)
    door_z = int(ez)
    entry_columns = []
    for z in range(door_z - 2, door_z + 4):
        x = int(ex); iz, ix = z-c.z_min, x-c.x_min
        if r.footprint_mask[iz, ix]:
            for y in range(81, 85):
                c.set(x, y, z, 'air', 'air')
            c.set(x, 80, z, 'smooth_stone', 'floor')
        else:
            set_surface(c, iz, ix, 81.0, 'smooth_stone', 'smooth_stone_slab')
        entry_columns.append([x, z])
    for half, y in (('lower', 81), ('upper', 82)):
        c.set(int(ex), y, door_z, 'dark_oak_door', 'door',
              dict(half=half, facing='north', hinge='left', open='true', powered='false'))
    # Preserve a 4-block-tall dark recess; ordinary brick above is retained.
    connect_window_panes(c)
    shape_report = shape_audit(c, r, entry_columns)
    if not shape_report['passed']:
        diagnostic = ROOT / 'runtime/campus-reconstruction/wendell-v1-construction-diagnostic.json'
        write_json(diagnostic, shape_report)
        raise ValueError(f'Physical construction failed: {diagnostic}')
    cameras = json.loads((ROOT / packet['baseline_camera_config']['path']).read_text(encoding='utf-8'))['views']
    for camera in cameras:
        assert c.get(*[math.floor(q) for q in camera['eye']]) == 0, camera['name']
    register = dict(source_faces=[dict(id=i, canonical=canonical(face)) for i, face in enumerate(b.roof_faces)],
                    architectural_faces=HIGH, reclassified_at_grade_faces=LOW,
                    openings=openings, inward_wall_corner_bridge_cells=bridges, belt_cells=belt,
                    source_site_surfaces=site, entry_columns=entry_columns)
    anchors = dict(format='hill-exterior-connection-anchors-v1',
                   status='provisional entry placement; measured source walk/grade',
                   door=dict(xyz=[int(ex)+.5, 81.0, door_z+.5], clear_width_blocks=.8125,
                             opening_height_blocks=4, source_uv_m=[14.5, -6.0], source_registration_tolerance_m=1.2,
                             note='One open vanilla dark-oak door. One-block corridor quantization of the clipped roughly 1m opening.'),
                   north_approach=dict(xyz=[int(ex)+.5, 81.0, door_z-1.5], clear_width_blocks=1),
                   inside=dict(xyz=[int(ex)+.5, 81.0, door_z+3.5]),
                   route=dict(points_xyz=[[int(ex)+.5,81.0,z+.5] for z in range(door_z-2,door_z+4)],
                              purpose='Ground connector to one usable provisional entrance',
                              maximum_step_blocks=0, player_width_blocks=.6, player_height_blocks=1.8))
    grade = dict(north_navd88_m=packet['terrain_and_site']['grade_by_face_navd88_m']['north_long_face'],
                 south_navd88_m=packet['terrain_and_site']['grade_by_face_navd88_m']['south_long_face'],
                 median_source_cross_slope_m=3.032196044921875,
                 unchanged_external_ground_columns=int(((c.ground_heights==initial_ground)&~active).sum()),
                 architectural_base_navd88_m=65.5,
                 note='North/south external DEM remains sloped; only the three measured site strips and tiny entry corridor are authored.')
    evidence = dict(source_roof=shell.to_manifest(), features=dict(north_windows=27, west_windows=5, source_bounded_entry=1),
                    terrain=dict(path=str(TERRAIN), sha256=digest(TERRAIN), resolution_m=.5, surface_datum_corrected=True),
                    source_packet=dict(path=str(PACKET), sha256=PACKET_SHA),
                    detail_generator=dict(path=str(Path(__file__)),sha256=digest(__file__)),
                    roof_disposition=dict(architectural_faces=HIGH, reclassified_at_grade_faces=LOW,
                                          high_face_source_max_navd88_m=80.595,
                                          rule='All high face polygons, planes and quantized caps retained exactly.'),
                    grade=grade, physical_construction=shape_report, uncertainties=p['uncertainties'])
    finish_study(c, p, output, cameras, evidence)
    write_json(output/'detail-register.json', register)
    write_json(output/'connection-anchors.json', anchors)
    write_json(output/'construction-audit.json', shape_report)
    write_json(output/'grade-audit.json', grade)
    for name, raster in [('source-roof-raster.npz', source), ('authored-roof-raster.npz', r)]:
        np.savez_compressed(output/name, heights=raster.heights, mask=raster.footprint_mask,
                            face_indices=raster.face_indices, gradient_x=raster.gradient_x, gradient_z=raster.gradient_z)
    shutil.copyfile(__file__, output/Path(__file__).name)
    export = audit_export(output)
    assert export['passed'], export['errors']
    write_json(output/'native-review.json',dict(status='pending_native_review', archive_sha256=digest(output/'sample-blocks.npz'),
               inspected_images=[], findings=['Generated and structurally audited; no native client launched.'],
               limitations=p['uncertainties']))
    print(json.dumps(dict(status='native_ready', directory=str(output), archive_sha256=digest(output/'sample-blocks.npz'),
                          blocks=export['exact_export_parity'], anchors=anchors), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'runtime/campus-reconstruction/wendell-v1-2x')
    args = parser.parse_args()
    build(args.output.resolve())
