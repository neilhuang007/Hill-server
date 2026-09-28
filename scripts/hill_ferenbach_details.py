"""Ferenbach rough exterior, bounded to observed groups and measured roof.

The source roof remains untouched. Straight facade planes are deliberately set
slightly behind noisy eaves. Exact facade coordinates are draft interpretations.
"""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion
from shapely import contains_xy
from shapely.geometry import Polygon

from build_hill_chapel_sample import ROLES
from campus_academic_building import PANE_PROPS
from campus_quad_landscape import set_surface
from campus_roof_geometry import load_measured_building

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {}


def prepare_roof(r, f, p):
    for record in p['reference_inputs']:
        assert hashlib.sha256((ROOT / record['path']).read_bytes()).hexdigest() == record['sha256']
    b = load_measured_building(parent_id=p['parent_id'])
    assert b.source_sha256 == p['source_roof_sha256']
    SOURCE.clear()
    SOURCE.update(raster=r, initial_states=f.c.data.copy(), initial_roles=f.c.roles.copy(),
                  details={'openings': [], 'site_columns': [], 'roof_changes': [],
                           'roof_partial_supports': [], 'source_faces': []})
    for i, face in enumerate(b.roof_faces):
        value = dict(xz=list(map(list, face.polygon.exterior.coords)),
                     plane=[face.a, face.b, face.c], surface=face.surface_index)
        SOURCE['details']['source_faces'].append(dict(id=i, canonical=value,
            sha256=hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()))
    return r


def opening(f, p, spec):
    side, at, centre = spec['side'], spec['at_m'], spec['centre_m']
    along, normal = (f.v, f.u) if side in ('west', 'east') else (f.u, f.v)
    # The complete regular boundary is glazed within this opening, including
    # inward grid-corner closure cells. Adjacent masonry remains the jamb.
    select = SOURCE['wall_mask'] & (abs(normal-at) < .72) & (abs(along-centre) < spec['width_m']/2)
    a, b = f.height_y(spec['sill_navd88_m']), f.height_y(spec['sill_navd88_m']+spec['height_m'])
    cells = []
    for x,z,iz,ix in f.each_column(select):
        if not all(ROLES[int(f.c.roles[y+64,iz,ix])] == 'facade' for y in range(a-1,b+1)):
            continue
        for y in range(a,b):
            f.c.set(x,y,z,'light_gray_stained_glass_pane','window',PANE_PROPS)
            cells.append([x,y,z])
        f.c.set(x,a-1,z,'smooth_quartz','trim')
        f.c.set(x,b,z,'smooth_quartz','trim')
    assert cells, spec
    SOURCE['details']['openings'].append({**spec,'pane_cells':cells})


def build_details(f, p):
    c = f.c
    roof_mask = c.roles == ROLES.index('roof')
    roof_states, roof_roles = c.data[roof_mask].copy(), c.roles[roof_mask].copy()
    # Restore measured exterior grade instead of retaining the shell's entire
    # low flat floor below the roof overhangs.
    c.data[:] = SOURCE['initial_states']; c.roles[:] = SOURCE['initial_roles']
    c.data[roof_mask] = roof_states; c.roles[roof_mask] = roof_roles
    body = contains_xy(Polygon(p['wall_outline_uv_m']), f.u, f.v)
    assert not (body & ~f.r.footprint_mask).any(), 'Draft wall exceeds measured roof footprint'
    wall = body & ~binary_erosion(body, structure=np.ones((3,3),bool))
    SOURCE.update(body_mask=body,wall_mask=wall)
    floor_y = f.height_y(p['geometry']['entrance_floor_navd88_m'])-1
    for x,z,iz,ix in f.each_column(body):
        half = math.floor((f.r.heights[iz,ix]-25)*4+.5)
        top = (half-1)//2
        assert top > floor_y+6
        for y in range(min(c.ground_at(x,z)-2,floor_y-2),top):
            if roof_mask[y+64,iz,ix]: continue
            if y < floor_y:
                c.set(x,y,z,'bricks','facade')
            elif y == floor_y:
                c.set(x,y,z,'smooth_stone','floor')
            elif wall[iz,ix]:
                block = 'bricks' if y < f.height_y(67.75) else 'pale_oak_planks'
                # Narrow courses recolor the same straight wall; no projecting belts.
                if y in (f.height_y(67.75),f.height_y(70.5)):block='smooth_quartz'
                c.set(x,y,z,block,'facade')
            else:c.set(x,y,z,'air','air')
    for spec in p['window_groups']:
        opening(f,p,spec)
    # Provisional open threshold is explicitly distinct from observed windows.
    portal = p['provisional_entrance']
    selected = wall & (abs(f.v-portal['plane_v_m'])<.72) & (abs(f.u-portal['centre_u_m'])<portal['clear_width_m']/2)
    fy = floor_y+1
    portal_cells=[]
    for x,z,iz,ix in f.each_column(selected):
        for y in range(fy,fy+5):c.set(x,y,z,'air','air');portal_cells.append([x,y,z])
        c.set(x,fy+5,z,'smooth_quartz','trim')
    assert portal_cells
    SOURCE['details']['provisional_portal'] = {**portal,'air_cells':portal_cells}
    site = f.local_mask(p['assembly_site_bounds_uv_m'][0]) & ~body
    for x,z,iz,ix in f.each_column(site):
        set_surface(c,iz,ix,float(fy),'smooth_stone','smooth_stone_slab')
        SOURCE['details']['site_columns'].append([x,z,fy])
    # Source stair/slab caps already have full-block backing. Record and retain
    # that exact geometry: no roof editing is performed by the facade pass.
    assert np.array_equal(c.data[roof_mask],roof_states)
    SOURCE['details']['roof_states_preserved'] = int(roof_mask.sum())
    SOURCE['details']['wall_columns'] = int(wall.sum())
    SOURCE['details']['wall_outline_uv_m'] = p['wall_outline_uv_m']
    SOURCE['details']['body_columns'] = int(body.sum())
    f.features['source_bounded_window_groups'] = len(p['window_groups'])
    f.features['provisional_entry_apron_columns'] = int(site.sum())
