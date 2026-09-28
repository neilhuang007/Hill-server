"""Build Lehrman's joined rough exterior and two disjoint integration archives.

The source roof caps stay fixed. The photographed connector, open balcony and
awnings are explicit interpretations; unseen opening grids are not invented.
"""

import argparse
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import shutil

import numpy as np
from scipy.ndimage import binary_erosion
from shapely import contains_xy
from shapely.geometry import Polygon, box

from audit_hill_block_artifact import audit as audit_export
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays, connect_window_panes
from campus_academic_building import PANE_PROPS
from campus_athey_details import connect_iron_rails
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_quad_landscape import set_surface
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study, write_json

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / 'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz'
FACADES = ROOT / 'runtime/research/campus-full-detail-20260905/institutional-facades.json'
IDS = {'round': '160015116006-081aa7dcac', 'bar': '160015116006-f7611d45c7'}
BOUNDS = (480, -572, 532, -516)
SPLIT_Z = -1078
ORIGIN = np.array([499.28, -531.1])
ANGLE = math.radians(-52.5)
T = np.array([math.cos(ANGLE), math.sin(ANGLE)])
N = np.array([-math.sin(ANGLE), math.cos(ANGLE)])
SLAB = {'type': 'bottom', 'waterlogged': 'false'}


def world(u, v):
    return (ORIGIN + T*u + N*v)*2


def boundary(mask):
    # Inward shared corners make the oblique pane trace physically continuous.
    return mask & ~binary_erosion(mask, structure=np.ones((3, 3), bool))


def dodecagon(radius):
    return Polygon([(radius*math.cos(k*math.pi/6), radius*math.sin(k*math.pi/6)) for k in range(12)])


def fresh_ground():
    h, ids, meta = terrain_arrays(TERRAIN, 2, BOUNDS)
    c = Canvas(2*BOUNDS[0], 2*BOUNDS[1], h.shape[1], h.shape[0], 2)
    build_ground(c, h, ids, meta['materials'], -25)
    smooth_exposed_measured_pavement(c, h, c.ground_heights, vertical_offset=-25)
    return c


def crop(c, low, high):
    z0, z1 = low-c.z_min, high-c.z_min
    out = Canvas(c.x_min, low, c.data.shape[2], z1-z0, 2)
    out.data = c.data[:, z0:z1].copy()
    out.roles = c.roles[:, z0:z1].copy()
    out.ground_heights = c.ground_heights[z0:z1].copy()
    out.palette = deepcopy(c.palette)
    out.palette_lookup = deepcopy(c.palette_lookup)
    return out


def build(output):
    if output.exists():
        raise FileExistsError(output)
    source = next(q for q in json.loads(FACADES.read_text())['buildings'] if q['id'] == 'lehrman')
    c = fresh_ground()
    zz, xx = np.indices(c.data.shape[1:])
    x, z = (xx+c.x_min+.5)/2, (zz+c.z_min+.5)/2
    u = (x-ORIGIN[0])*T[0] + (z-ORIGIN[1])*T[1]
    v = (x-ORIGIN[0])*N[0] + (z-ORIGIN[1])*N[1]
    sel = lambda poly: contains_xy(poly, u, v)
    columns = lambda mask: [(int(ix)+c.x_min, int(iz)+c.z_min, int(iz), int(ix)) for iz, ix in np.argwhere(mask)]

    def fill(mask, y0, y1, block, role, props=None):
        c.data[y0+64:y1+64, mask] = c.state(block, props)
        c.roles[y0+64:y1+64, mask] = ROLES.index(role) if block != 'air' else 0

    # First produce independent exact measured roof states, then author the
    # photo-based body without extruding roof-raster noise down the facade.
    rasters, shell_records, roof_cells, source_mapping = {}, {}, [], []
    for kind, parent in IDS.items():
        b = load_measured_building(parent_id=parent)
        raw = rasterize_roof(b, BOUNDS, .5)
        ids = [0, 3, 4, 7, 8, 9] if kind == 'round' else [1]
        mask = raw.footprint_mask & np.isin(raw.face_indices, ids)
        r = replace(raw, footprint_mask=mask, missing_mask=np.zeros_like(mask),
                    face_indices=np.where(mask, raw.face_indices, -1), heights=np.where(mask, raw.heights, np.nan))
        temp = fresh_ground()
        shell = build_measured_shell(temp, b, r, vertical_offset=-25, floor_navd88=75.1,
                                     facade='mud_bricks', foundation='stone_bricks',
                                     roof_family='deepslate_tile' if kind == 'round' else 'stone_brick',
                                     roof_backing_metres=.5)
        rasters[kind] = (b, raw, r, shell)
        shell_records[kind] = shell.to_manifest()
        for iy, iz, ix in np.argwhere(temp.roles == ROLES.index('roof')):
            state = temp.palette[int(temp.data[iy, iz, ix])]
            q = [int(ix)+c.x_min, int(iy)-64, int(iz)+c.z_min]
            roof_cells.append(dict(xyz=q, state=state, role='roof', source_parent_id=parent,
                                   owner='round' if q[2] >= SPLIT_Z else 'bar'))
        for xc, zc, iz, ix in columns(mask):
            source_mapping.append(dict(xz=[xc, zc], source_parent_id=parent,
                                       source_face=int(raw.face_indices[iz, ix]),
                                       source_height_navd88_m=float(raw.heights[iz, ix]),
                                       quantized_surface_y=float(shell.quantized_roof_surface_y[iz, ix]),
                                       owner='round' if zc >= SPLIT_Z else 'bar'))

    round_lower = sel(dodecagon(6.1))
    balcony = sel(dodecagon(6.85))
    core = sel(dodecagon(4.6))
    # Source flat roof stays exact. Its west edge varies by about a metre;
    # the photographed straight wall uses the measured source endpoints.
    bar_poly = Polygon([(9.79, -3.74), (36.25, -2.75), (36.15, 3.81), (9.89, 3.96)])
    bar = sel(bar_poly)
    join = sel(box(3.8, -4.2, 10.2, 4.2))
    body = round_lower | bar | join
    deck = balcony | join | bar | rasters['round'][1].footprint_mask
    apron = sel(dodecagon(9.4)) | sel(box(6.0, -5.8, 36.7, -3.0))
    # Only the sheltered apron is levelled; long shared paths stay external.
    paving_records = []
    for xc, zc, iz, ix in columns(apron | body):
        level = 100.0
        if not body[iz, ix] and u[iz, ix] > 10:
            level = 100 + .5*min(1, max(0, (u[iz, ix]-10)/26))
        set_surface(c, iz, ix, level, 'smooth_stone', 'smooth_stone_slab', role='floor' if body[iz, ix] else 'pavement')
        paving_records.append([xc, zc, round(level*2)/2])
    # The low county strip is explicitly an at-grade west apron, not a roof.
    low_surfaces = []
    for kind, low_ids in [('bar', [0]), ('round', [1, 5])]:
        b, raw, _, _ = rasters[kind]
        for idx in low_ids:
            face = b.roof_faces[idx]
            mask = contains_xy(face.polygon, x, z) & ~body
            for xc, zc, iz, ix in columns(mask):
                level = (float(face.height_at(x[iz, ix], z[iz, ix]))-25)*2
                set_surface(c, iz, ix, level, 'smooth_stone', 'smooth_stone_slab')
                apron[iz, ix] = True
                low_surfaces.append(dict(xz=[xc, zc], parent_id=IDS[kind], face=idx,
                                         source_surface_y=level, quantized_surface_y=round(level*2)/2))
    wall = boundary(body)
    fill(wall, 100, 107, 'mud_bricks', 'facade')
    fill(body, 99, 100, 'smooth_stone', 'floor')
    fill(deck, 107, 108, 'smooth_stone', 'floor')
    # Preserve source deck strips at their measured quarter-metre cap levels.
    source_deck = []
    b, raw, _, _ = rasters['round']
    for xc, zc, iz, ix in columns(raw.footprint_mask & np.isin(raw.face_indices, [2, 6])):
        surface = math.floor((float(raw.heights[iz, ix])-25)*4+.5)/2
        top = math.ceil(surface)-1
        c.set(xc, top, zc, 'smooth_stone' if surface.is_integer() else 'smooth_stone_slab', 'floor', None if surface.is_integer() else SLAB)
        source_deck.append(dict(xz=[xc, zc], face=int(raw.face_indices[iz, ix]), surface_y=surface))

    visible_round = wall & round_lower & ((u < .8) | (v < -1))
    fill(visible_round, 100, 107, 'white_concrete', 'trim')
    fill(visible_round, 101, 106, 'light_gray_stained_glass_pane', 'window', PANE_PROPS)
    posts = []
    for radius, bottom, top, purpose in [(6.1, 100, 107, 'ground'), (6.65, 108, 114, 'upper')]:
        for k in range(12):
            pu, pv = radius*math.cos(k*math.pi/6), radius*math.sin(k*math.pi/6)
            if purpose == 'ground' and pu > 3.8 and abs(pv) < 4.2:
                continue
            xp, zp = np.floor(world(pu, pv)).astype(int)
            iz, ix = int(zp)-c.z_min, int(xp)-c.x_min
            # At two blocks/metre the half-metre source post is one block.
            for yy in range(bottom, top):
                c.set(int(xp), yy, int(zp), 'white_concrete', 'trim')
            posts.append(dict(xz=[int(xp), int(zp)], y=[bottom, top], kind=purpose, corner=k))
    corewall = boundary(core)
    fill(corewall, 108, 114, 'white_concrete', 'trim')
    fill(corewall & ((u < .8) | (v < -1)), 109, 113, 'light_gray_stained_glass_pane', 'window', PANE_PROPS)

    # Three clearly photographed broad glazed service-bar bays, no hidden grid.
    bar_west = wall & bar & (v < -2.2)
    openings = []
    for centre in (20.8, 26.7, 33.4):
        frame = bar_west & (abs(u-centre) <= 1.95)
        glass = bar_west & (abs(u-centre) <= 1.45)
        fill(frame, 100, 107, 'white_concrete', 'trim')
        fill(glass, 100, 106, 'light_gray_stained_glass_pane', 'window', PANE_PROPS)
        openings.append(dict(centre_u_m=centre, width_m=2.9, side='west', status='source visible; centre tolerance 1m'))
    junction = wall & join & (v < -3) & (abs(u-6.25)<1.1)
    fill(junction, 100, 107, 'white_concrete', 'trim')
    fill(junction, 101, 106, 'light_gray_stained_glass_pane', 'window', PANE_PROPS)
    # Concession hatch remains visually distinct from the ordinary service door.
    hatch = bar_west & (abs(u-10.9) < 1.25)
    fill(hatch, 102, 106, 'dark_oak_planks', 'facade')

    # Missing north sector of the round high roof is an explicit photo infill;
    # every actual county high roof cap below is restored unchanged afterward.
    measured_high = rasters['round'][2].footprint_mask
    infill = balcony & ~measured_high
    infill_caps = []
    for xc, zc, iz, ix in columns(infill):
        angle = math.atan2(v[iz, ix], u[iz, ix])
        local = (angle + math.pi/12) % (math.pi/6) - math.pi/12
        outer = 6.85*math.cos(math.pi/12)/math.cos(local)
        level = 82.05+(84.2-82.05)*(1-min(1, math.hypot(u[iz, ix], v[iz, ix])/outer))
        surface = math.floor((level-25)*4+.5)/2
        top = math.ceil(surface)-1
        c.set(xc, top-1, zc, 'deepslate_tiles', 'roof')
        c.set(xc, top, zc, 'deepslate_tiles' if surface.is_integer() else 'deepslate_tile_slab', 'roof', None if surface.is_integer() else SLAB)
        infill_caps.append(dict(xz=[xc, zc], surface_y=surface))
    # Continuous thin pale eave ring under the high canopy; exposed balcony
    # stays open between supports from deck to this ring.
    fill(boundary(balcony), 113, 114, 'white_concrete', 'trim')
    # Roof rails follow the straight bar/deck border and the round balcony.
    rails = boundary(deck) & ~core
    for xc, zc, iz, ix in columns(rails):
        if c.palette[c.get(xc,108,zc)]['Name'] == 'minecraft:air':
            c.set(xc,108,zc,'iron_bars','railing',PANE_PROPS)
            c.set(xc,109,zc,'iron_bars','railing',PANE_PROPS)

    # Blue fabric proxy is a supported carpet above a pale solid/half-block
    # canopy. The colour does not claim a particular real fabric or paint code.
    canopy = sel(dodecagon(9.1)) & ~round_lower & ~join & ~bar
    canopy_caps, canopy_posts = [], []
    for xc, zc, iz, ix in columns(canopy):
        outer_band = math.hypot(u[iz,ix],v[iz,ix]) >= 7.55
        top = 105 if outer_band else 106
        c.set(xc, top, zc, 'smooth_stone', 'roof')
        if not outer_band:
            c.set(xc,top-1,zc,'smooth_stone_slab','roof',{'type':'top','waterlogged':'false'})
        c.set(xc,top+1,zc,'blue_carpet','furniture')
        canopy_caps.append([xc,top+1,zc])
    for k in range(12):
        pu,pv=8.9*math.cos(k*math.pi/6),8.9*math.sin(k*math.pi/6)
        xp,zp=np.floor(world(pu,pv)).astype(int)
        iz,ix=int(zp)-c.z_min,int(xp)-c.x_min
        if not canopy[iz,ix]:continue
        for yy in range(100,106):
            c.set(int(xp),yy,int(zp),'iron_bars','railing',PANE_PROPS)
        canopy_posts.append([int(xp),int(zp)])

    # Source roof caps/backing are the final immutable authority at their cells.
    for q in roof_cells:
        c.set(*q['xyz'], q['state']['Name'], 'roof', q['state'].get('Properties'))
    # Back every outer balcony post to a real roof cell, avoiding a suspended
    # cap over the source's jagged footprint. A small horizontal beam is part
    # of the same pale eave ring, never a new enclosing wall.
    support_extensions = []
    for post in posts:
        if post['kind'] != 'upper':continue
        xc,zc=post['xz']
        roof_y=[yy for yy in range(113,121) if c.roles[yy+64,zc-c.z_min,xc-c.x_min]==ROLES.index('roof')]
        if roof_y:
            for yy in range(113,min(roof_y)):
                c.set(xc,yy,zc,'white_concrete','trim')
                support_extensions.append([xc,yy,zc])

    # A rough roll-up-style open portal is functional without inventing a
    # smaller domestic door inside the photographed broad glazing.
    entry_masks, routes = [], []
    for name, along, outward, inward in [('round-south', 0, -9.1, -4.8), ('bar-west',29.9,-5.6,-2.0)]:
        if name=='round-south':
            mask=(abs(v)<.65)&(u>=outward)&(u<=inward)
            uv=[[outward,0],[inward,0]]
        else:
            mask=(abs(u-along)<.65)&(v>=outward)&(v<=inward)
            uv=[[along,outward],[along,inward]]
        for xc,zc,iz,ix in columns(mask):
            for yy in range(min(99,int(c.ground_heights[iz,ix])),100):
                c.set(xc,yy,zc,'smooth_stone','floor' if body[iz,ix] else 'pavement')
            for yy in range(100,104):c.set(xc,yy,zc,'air','air')
            c.ground_heights[iz,ix]=99
        entry_masks.append(mask)
        routes.append(dict(name=name,waypoints_uv_m=uv,feet_hints_blocks=[100,100],
                           observation='Source-visible portal; exact open sub-bay is a rough functional interpretation.'))
    # Connected internal floor/deck crossing is verified in addition to entries.
    routes += [dict(name='ground-round-to-bar',waypoints_uv_m=[[0,0],[14,0]],feet_hints_blocks=[100,100]),
               dict(name='upper-balcony-to-service-deck',waypoints_uv_m=[[4.8,-1],[8,-1],[14,-1]],feet_hints_blocks=[108,108,108])]
    connect_window_panes(c)
    connect_iron_rails(c)

    def camera(name, eye, target, fov=66):
        e,t=world(*eye[:2]),world(*target[:2])
        return dict(name='lehrman-'+name,eye=[float(e[0]),2*(eye[2]-25),float(e[1])],
                    target=[float(t[0]),2*(target[2]-25),float(t[1])],fov=fov)
    cameras=[camera('joined-west', [15,-33,84],[14,0,78],70),
             camera('south-round',[-23,-10,81],[0,0,79],64),
             camera('balcony-close',[-11,-11,82],[0,0,80.5],66),
             camera('bar-north',[44,-12,80],[25,0,77],68),
             camera('east-context',[17,27,86],[14,0,78.5],70),
             camera('entry-eye',[-10.5,0,76],[0,0,76],70)]
    for q in cameras:
        assert c.get(*[math.floor(a) for a in q['eye']])==0,q['name']
    sources = [FACADES, TERRAIN,
               ROOT/'runtime/research/campus-full-detail-20260905/institutional-materials.json',
               ROOT/'runtime/research/campus-full-detail-20260905/institutional-roof-geometries.json',
               ROOT/'runtime/research/quad-landscape-20260905/current-pavilion-proposals.json',
               ROOT/'runtime/research/campus-priority-20260905/lehrman-1.jpg',
               ROOT/'runtime/research/campus-full-detail-20260905/lehrman-4.jpg']
    p=dict(name="Lehrman '56 Pavilion - joined rough exterior review",revision='2026-09-27-lehrman-outline-v1-2x',
           blocks_per_metre=2,vertical_offset_m=-25,school_map_numbers=[25],
           geometry=dict(origin_xz_m=ORIGIN.tolist(),axis_degrees=-52.5),
           assembly_site_bounds_uv_m=[[-9.6,-9.6,9.6,9.6],[6,-5.8,36.7,-3]],
           material_review=dict(status='ordinary provisional appearance proxies, native comparison pending',
                                split_face_block_proxy='mud_bricks',Hardie_trim_proxy='white_concrete',
                                roof='deepslate tile round; stone brick service deck',
                                fabric_proxy='blue carpet on supported canopy',glass='light gray panes'),
           uncertainties=source['uncertainties']+[
               'Rough exterior only: no detailed interiors or route between storeys; hidden east openings are unresolved.',
               'Measured high caps and source low deck/grade are retained; photo-interpreted roof infill closes the absent north sector only.',
               'Entry sub-bays are open for this exterior draft. No operable roll-up mechanism is claimed.',
               'Dodecagon posts, glazing radii and canopy dimensions are image-scaled, not survey measurements.',
               'Two identities use disjoint cropped block-Z archive domains; archive partition is not a physical construction joint.'])
    register=dict(source_roofs=source_mapping,source_roof_cells=roof_cells,source_grade_surfaces=low_surfaces,
                  source_deck_caps=source_deck,authored_roof_infill=infill_caps,posts=posts,
                  support_extensions=support_extensions,canopy_posts=canopy_posts,canopy_blue_caps=canopy_caps,
                  openings=openings,entry_columns=[list(q[:2]) for mask in entry_masks for q in columns(mask)],
                  paved_columns=paving_records,body_columns=[list(q[:2]) for q in columns(body)],
                  balcony_columns=[list(q[:2]) for q in columns(balcony)],core_columns=[list(q[:2]) for q in columns(core)],
                  routes=routes,source_packet=source,
                  partition=dict(split_z_blocks=SPLIT_Z,round_rule='Z >= -1078',bar_rule='Z < -1078'))
    # All construction must pass before final output creation.
    from audit_lehrman_outline import construction_audit
    checks=construction_audit(c,register)
    if not checks['passed']:
        diagnostic=output.with_name(output.name+'-construction-diagnostic.json')
        write_json(diagnostic,checks)
        raise ValueError(f'Construction audit failed: {diagnostic}')
    output.mkdir(parents=True,exist_ok=False)
    source_record=[dict(path=q.relative_to(ROOT).as_posix(),sha256=digest(q)) for q in sources]
    write_json(output/'detail-register.json',register)
    write_json(output/'construction-audit.json',checks)
    write_json(output/'source-hashes.json',source_record)
    write_json(output/'connection-anchors.json',dict(format='hill-exterior-connection-anchors-v1',
        path_candidate='way/1247750688',routes=routes,
        anchors=[dict(name=q['name'],uv_m=q['waypoints_uv_m'][0],xyz_blocks=[float(world(*q['waypoints_uv_m'][0])[0]),100,float(world(*q['waypoints_uv_m'][0])[1])]) for q in routes[:2]],
        footprint_and_site='See exact ownership masks from split-ownership-proof.json; shared paths stop outside them.'))
    evidence=dict(source_roof_components=shell_records,terrain=dict(path=TERRAIN.as_posix(),sha256=digest(TERRAIN)),
                  sources=source_record,physical_construction=checks,detail_generator=dict(path=str(Path(__file__)),sha256=digest(__file__)))
    manifests={}
    for kind,part,extent in [('joined',c,(c.z_min,c.z_min+c.data.shape[1])),
                             ('round',crop(c,SPLIT_Z,c.z_min+c.data.shape[1]),(SPLIT_Z,c.z_min+c.data.shape[1])),
                             ('bar',crop(c,c.z_min,SPLIT_Z),(c.z_min,SPLIT_Z))]:
        profile=deepcopy(p)
        if kind!='joined':
            profile['parent_id']=IDS[kind]
            profile['name']="Lehrman '56 Pavilion - "+('south round viewing pavilion' if kind=='round' else 'north service bar')
            profile['partition']=dict(block_z_half_open=list(extent),shared_review='../joined',
                                      source_parent_id=IDS[kind],proof='../split-ownership-proof.json')
        else:
            profile['review_only']=True
        manifests[kind]=finish_study(part,profile,output/kind,cameras,evidence)
        report=audit_export(output/kind)
        assert report['passed'],report['errors']
        write_json(output/kind/'native-review.json',dict(status='pending_native_review',archive_sha256=digest(output/kind/'sample-blocks.npz'),
                    inspected_images=[],findings=['Generated and structurally audited. Joined native review required.'],limitations=p['uncertainties']))
    shutil.copyfile(__file__,output/Path(__file__).name)
    from audit_lehrman_outline import audit
    final=audit(output)
    assert final['passed'],final
    print(json.dumps(dict(status='pending_native_review',output=str(output),checks=checks['summary'],partition=final['summary']),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/campus-reconstruction/lehrman-outline-v1-2x')
    build(parser.parse_args().output.resolve())
