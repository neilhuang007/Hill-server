"""Read-only rough-outline review of Warner's existing measured envelope.

Writes evidence beside, never into, the immutable source study. This does not
grant native acceptance or construct an entrance from a ground-level sample.
"""

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion, binary_propagation, label

from audit_hill_quadrivium_contacts import shapes
from campus_export_parity import compare_world, read_archive, role_histogram
from campus_materials import audit_role_materials
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'runtime/campus-reconstruction/campus-envelopes-v2-ground/160015116006389O-f1989780fb'
OUTPUT = ROOT / 'runtime/campus-reconstruction/warner-outline-review-20260927'


def main():
    before = {p.relative_to(STUDY).as_posix(): digest(p) for p in sorted(STUDY.rglob('*')) if p.is_file()}
    archive = read_archive(STUDY / 'sample-blocks.npz')
    parity, export_errors, _, chunks = compare_world(archive, STUDY / 'world')
    manifest = json.loads((STUDY / 'manifest.json').read_text())
    b = load_measured_building(parent_id='160015116006389O-f1989780fb')
    bounds = manifest['source_roof']['world_bounds_blocks']
    r = rasterize_roof(b, [v / 2 for v in bounds], .5)
    xyz, state_ids, role_ids = archive['coords'], archive['state_ids'], archive['role_ids']
    role_names, keys = archive['role_names'], archive['palette_keys']
    dimensions = (384, bounds[3]-bounds[1], bounds[2]-bounds[0])
    states, roles = np.zeros(dimensions, np.uint16), np.zeros(dimensions, np.uint8)
    where = (xyz[:, 1]+64, xyz[:, 2]-bounds[1], xyz[:, 0]-bounds[0])
    states[where], roles[where] = state_ids, role_ids
    state_boxes = {i: shapes(json.dumps({'Name': key[0], 'Properties': dict(key[1])}, sort_keys=True)) for i, key in enumerate(keys)}
    architecture = np.isin(roles, [role_names.index(n) for n in ('facade', 'roof', 'floor')])
    columns = architecture.any(axis=0)
    components, component_count = label(architecture)
    component_sizes = np.bincount(components.ravel())[1:]
    high = r.footprint_mask & np.isin(r.face_indices, [1, 2])
    roof_report = []
    for iz, ix in np.argwhere(high):
        ys = np.flatnonzero(roles[:, iz, ix] == role_names.index('roof'))
        expected = math.floor((r.heights[iz, ix]-25)*4+.5)/2
        actual = max((float(y-64)+max(box[4] for box in state_boxes[int(states[y, iz, ix])])/16 for y in ys), default=None)
        if actual is None or abs(actual-expected) > 1e-8:
            roof_report.append({'xz': [int(ix)+bounds[0], int(iz)+bounds[1]], 'expected_top_y': expected, 'actual_top_y': actual})
    ground_failures = []
    ground_roles = [role_names.index(n) for n in ('terrain', 'pavement')]
    for iz, ix in np.argwhere(~columns):
        occupied = np.flatnonzero(states[:, iz, ix])
        gy = np.flatnonzero(np.isin(roles[:, iz, ix], ground_roles))
        if not len(occupied) or not len(gy) or np.any(states[occupied.min():gy.max()+1, iz, ix] == 0):
            ground_failures.append([int(ix)+bounds[0], int(iz)+bounds[1]])
    # Physical half-block slices: full, stair and slab boxes, with no virtual doors.
    slices = []
    for y in range(61, 77):
        inner = binary_erosion(high & (r.heights > (y+1)/2+25+.5), iterations=2)
        for sub in (4, 12):
            occupied = np.zeros((dimensions[1]*16, dimensions[2]*16), bool)
            for iz, ix in np.argwhere(states[y+64] != 0):
                for q in state_boxes[int(states[y+64, iz, ix])]:
                    if q[1] <= sub < q[4]:
                        occupied[iz*16+int(q[2]):iz*16+int(q[5]), ix*16+int(q[0]):ix*16+int(q[3])] = True
            seed = np.zeros_like(occupied)
            seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
            outside = binary_propagation(seed, mask=~occupied)
            leaks = [[int(ix)+bounds[0], int(iz)+bounds[1]] for iz, ix in np.argwhere(inner) if outside[iz*16+8, ix*16+8]]
            slices.append({'y': y, 'subvoxel_height': sub, 'interior_columns': int(inner.sum()), 'leak_count': len(leaks), 'examples': leaks[:8]})
    materials = defaultdict(Counter)
    for role, state, count in role_histogram(archive):
        materials[role_names[role]][keys[state][0]] += count
    materials = {k: dict(v) for k, v in materials.items()}
    violations = audit_role_materials(materials)
    controls = json.loads((ROOT/'runtime/research/campus-full-detail-20260905/terrain-priority-building-approach-controls.json').read_text())['warner']
    grades = {}
    for face in ('north_long_face', 'south_long_face'):
        selected = [c['native_dem_navd88_m'] for c in controls['controls'] if c['feature'] == face and c['setback_from_wall_m'] == 1]
        grades[face] = {'setback_m': 1, 'samples': len(selected), 'range_navd88_m': [min(selected), max(selected)]}
    source_names = [
        'runtime/research/campus-exterior-draft-20260927/next-builder-packets.md',
        'runtime/research/campus-full-detail-20260905/root-building-metric-geometry.json',
        'runtime/research/campus-full-detail-20260905/terrain-priority-building-approach-controls.json',
        'runtime/research/campus-full-detail-20260905/terrain-all-components-perimeter-controls.json',
        'runtime/research/campus-priority-20260905/campus-2026-aerial-original.jpg',
        'runtime/research/campus-priority-20260905/campus-map-core-2026-zoom.png',
        'runtime/research/campus-priority-20260905/campus-footprint-index-west.png',
        'runtime/research/campus-priority-20260905/warner-2026.jpg',
        'runtime/research/campus-full-detail-20260905/sports-drone-sequence-20260919/manifest.json',
        'runtime/research/campus-full-detail-20260905/sports-drone-sequence-20260919/frame-040.png',
    ]
    sources = [{'path': n, 'sha256': digest(ROOT/n)} for n in source_names]
    after = {p.relative_to(STUDY).as_posix(): digest(p) for p in sorted(STUDY.rglob('*')) if p.is_file()}
    report = {
        'format': 'hill-warner-rough-outline-review-v1', 'date': '2026-09-27',
        'status': 'retain_existing_measured_outline_pending_native',
        'rough_outline_decision': 'accept existing source plan and high gable as rough massing only',
        'source_study': STUDY.relative_to(ROOT).as_posix(), 'archive_sha256': before['sample-blocks.npz'],
        'source_study_files': before, 'immutable_source_unchanged': before == after,
        'changed_cells': 0, 'changed_columns': 0, 'authored_exterior_columns': 0,
        'roof_source_sha256': b.source_sha256, 'footprint_bounds_xz_m': list(b.footprint.bounds),
        'frame': controls['frame'], 'ground_controls': grades,
        'high_roof_face_ids': [1, 2], 'high_roof_columns': int(high.sum()),
        'source_roof_faces': [{'id': i, 'height_navd88_m': [f.min_h, f.max_h], 'area_m2': f.polygon.area} for i, f in enumerate(b.roof_faces)],
        'high_roof_quantized_top_mismatches': roof_report,
        'exact_export_parity': parity, 'export_errors': export_errors, 'chunks': chunks,
        'ordinary_construction_palette_violations': violations,
        'architecture_cells': int(architecture.sum()), 'architecture_cell_components': int(component_count),
        'architecture_component_sizes': component_sizes.tolist(),
        'inherited_detached_low_facet_component': {'xz_blocks': [-93, -145], 'y_blocks_inclusive': [58, 61], 'cells': 4, 'note': 'Small inherited ground-level source-facet residue, separate from the 2271-cell main mass; not a facade addition or an entrance.'},
        'exterior_ground_columns': int((~columns).sum()), 'exterior_missing_ground_or_subsurface_gaps': ground_failures,
        'physical_wall_slices': slices,
        'entrance_anchor': None, 'new_apron': None, 'new_path': None,
        'sources': sources,
        'observations': [
            'Two high source planes retain the small elongated pitched roof at the measured bearing; no source-supported mass correction was identified in this bounded pass.',
            'The official map and footprint identity distinguish Warner from the nearby detached service structure and Chapel tennis courts.',
            'The 2026 aerial supplies site context; tree cover, distance and oblique scale prevent a reliable opening schedule.',
            'The 278 s drone crop shows a small warm brick-toned body beneath a light gray pitched roof. This supports the coarse gabled mass, not the existing exact mud-brick material or facade detail.',
            'Stored drone frame 040 is timestamp 278.0 s; Warner is at the unobscured right edge, but the central logo excludes that area from broader campus verification.',
            'warner-2026.jpg views an interior through glazing. It is not a complete exterior elevation or a registered entrance reference.',
        ],
        'limitations': [
            'No native screenshot was taken or inspected; no accepted_for_bounded_integration status is granted.',
            'Face 0 is a low north/west L-shaped source facet at 55.6081–57.365 m NAVD88; retain it as inherited source uncertainty, not as evidence of a canopy, entrance or paved apron.',
            'Facade mud_bricks, foundation stone_bricks and stone-brick roof remain ordinary provisional materials, not a verified material study.',
            'No entrance, threshold, glazing distribution, hidden facade, vegetation or interior is certified.',
            'Cell connectivity and physical slice enclosure do not prove route accessibility or full photographic fidelity.',
            'Protected core and shared road/parking geometry receive no changes.',
        ],
    }
    write_json(OUTPUT/'rough-outline-review.json', report)
    cameras = [
        {'name': 'warner-north-low-grade', 'eye': [-86, 73, -157], 'target': [-83, 69, -135], 'fov': 70},
        {'name': 'warner-northwest-roof', 'eye': [-108, 86, -151], 'target': [-83, 71, -135], 'fov': 70},
        {'name': 'warner-south-high-grade', 'eye': [-90, 80, -114], 'target': [-83, 70, -135], 'fov': 70},
        {'name': 'warner-east-gable', 'eye': [-65, 79, -134], 'target': [-84, 70, -135], 'fov': 74},
    ]
    write_json(OUTPUT/'camera-views.json', {'format': 'hill-native-camera-views-v1', 'views': cameras})
    Image.open(ROOT/source_names[-1]).crop((1500, 440, 1900, 655)).save(OUTPUT/'drone-278s-warner-context.png')
    camera_checks = []
    for camera in cameras:
        x, y, z = map(math.floor, camera['eye'])
        inside = bounds[0] <= x < bounds[2] and bounds[1] <= z < bounds[3]
        camera_checks.append({'name': camera['name'], 'inside_study_bounds': inside,
                              'eye_is_air': bool(inside and states[y+64, z-bounds[1], x-bounds[0]] == 0)})
    write_json(OUTPUT/'camera-checks.json', {'views': camera_checks, 'scope': 'Standalone study only; coordinator must recheck combined campus observers.'})
    print(json.dumps({k: report[k] for k in ('status', 'archive_sha256', 'immutable_source_unchanged', 'high_roof_columns', 'high_roof_quantized_top_mismatches', 'export_errors', 'architecture_cell_components', 'architecture_component_sizes', 'exterior_missing_ground_or_subsurface_gaps')}, indent=2))
    print('Physical slice leaks:', sum(s['leak_count'] for s in slices))


if __name__ == '__main__':
    main()
