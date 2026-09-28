"""CFTA construction from separately registered roof, screen and lobby controls.

The front screen is not a noisy roof edge. Straight authored sheets use one
regular grid path and one inward return at each diagonal step. All dimensions
are in the original campus U/V metres and NAVD88 heights; there is no fitting
translation or rescaling.
"""

from dataclasses import replace
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
from campus_roof_geometry import load_measured_building

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path_columns(f, uv_points, inward=(0, -1)):
    """Ordered four-neighbour connected half-metre trace, without wall noise."""
    chain = []
    for a, b in zip(uv_points, uv_points[1:]):
        start, end = f.world(*a)*f.c.scale-.5, f.world(*b)*f.c.scale-.5
        count = max(1, math.ceil(float(np.max(abs(end-start)))*8))
        for point in np.linspace(start, end, count+1):
            q = tuple(int(round(v)) for v in point)
            if chain and q == chain[-1]:
                continue
            if chain and abs(q[0]-chain[-1][0])+abs(q[1]-chain[-1][1]) == 2:
                prev = chain[-1]
                choices = ((prev[0],q[1]),(q[0],prev[1]))
                corner = max(choices, key=lambda r:r[0]*inward[0]+r[1]*inward[1])
                if corner != prev:
                    chain.append(corner)
            chain.append(q)
    return list(dict.fromkeys(chain))


def plane_columns(f, at, ends, *, axis='v', inward=(0,-1)):
    points = [[ends[0],at],[ends[1],at]] if axis == 'v' else [[at,ends[0]],[at,ends[1]]]
    return path_columns(f, points, inward)


def _uv(f, x, z):
    return float(f.u[z-f.c.z_min,x-f.c.x_min]), float(f.v[z-f.c.z_min,x-f.c.x_min])


def _put_columns(f, columns, low, high, block, role, props=None):
    for x,z in columns:
        for y in range(f.height_y(low),f.height_y(high)):
            f.c.set(x,y,z,block,role,props)


def _sheet(f, name, columns, low, high, glass, frame, *, frame_ends=True):
    """One continuous sheet; full caps and endpoint jambs seal every return."""
    if frame=='quartz_bricks':frame='smooth_quartz'
    a,b = f.height_y(low),f.height_y(high)
    panes = []
    for i,(x,z) in enumerate(columns):
        for y in range(a-1,b+1):
            cap = y in (a-1,b) or (frame_ends and i in (0,len(columns)-1))
            f.c.set(x,y,z,frame if cap else glass,'trim' if cap else 'window',
                    None if cap or not glass.endswith('_pane') else PANE_PROPS)
            if not cap:
                panes.append([x,y,z])
    SOURCE['details']['glazing'].append(dict(name=name,columns=columns,
        low_y=a,high_y_exclusive=b,glass=glass,frame=frame,
        frame_ends=frame_ends,pane_cells=panes))


def _roof_top_y(f, iz, ix):
    return (math.floor((f.r.heights[iz,ix]+f.offset)*f.c.scale*2+.5)-1)//2


def _pane_grid(f,name,columns,low,high,vertical_groups,horizontal_levels):
    """Thin transparent principal framing within the same enclosed pane sheet."""
    chosen={int(round(i)) for i in np.linspace(0,len(columns)-1,vertical_groups+1)[1:-1]}
    rows={f.height_y(h) for h in horizontal_levels}
    changed=[]
    for i,(x,z) in enumerate(columns):
        for y in range(f.height_y(low),f.height_y(high)):
            state=f.c.palette[f.c.get(x,y,z)]
            if not state['Name'].endswith('_pane') or not(i in chosen or y in rows):continue
            f.c.set(x,y,z,'white_stained_glass_pane','window',PANE_PROPS)
            changed.append([x,y,z])
    SOURCE['details'].setdefault('principal_transparent_grids',[]).append(dict(
        name=name,vertical_groups=vertical_groups,horizontal_levels_navd88_m=horizontal_levels,
        white_pane_cells=changed,rule='Sparse principal frames are transparent panes in the field plane; fine original pitch remains metadata'))


def prepare_roof(r, f, p):
    packet_info = p['reference_packet']
    assert _sha(ROOT/packet_info['path']) == packet_info['sha256']
    packet = json.loads((ROOT/packet_info['path']).read_text(encoding='utf-8'))
    for info in p.get('reference_addenda',[]):
        assert _sha(ROOT/info['path'])==info['sha256']
    building = load_measured_building(parent_id=p['parent_id'])
    assert building.source_sha256 == p['source_roof_sha256']
    face_records = []
    for i, face in enumerate(building.roof_faces):
        payload = dict(xz=list(map(list,face.polygon.exterior.coords)),
                       holes=[list(map(list,ring.coords)) for ring in face.polygon.interiors],
                       plane=[face.a,face.b,face.c],surface=face.surface_index)
        face_records.append(dict(id=i,canonical=payload,
            sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            height_range_navd88_m=[face.min_h,face.max_h]))
    SOURCE.clear()
    SOURCE.update(original_raster=r,building=building,packet=packet,
        details=dict(source_faces=face_records,glazing=[],screen={},rails=[],stairs=[],
                     structural_supports=[],roof_exceptions=[],closure_regions=[]))
    # Any explicit enclosure patch is supplied by the source agent. It may
    # add missing lobby columns but never lower or translate a retained face.
    for patch in p.get('lobby_roof_extensions',[]):
        polygon = Polygon([f.world(*uv) for uv in patch['polygon_uv_m']])
        selected = contains_xy(polygon,f.x,f.z) & ~r.footprint_mask
        height = patch['height_navd88_m']
        h,gx,gz,ids = (a.copy() for a in (r.heights,r.gradient_x,r.gradient_z,r.face_indices))
        h[selected],gx[selected],gz[selected],ids[selected]=height,0,0,1000000+len(r.authored_roof_patches)
        record = dict(**patch,added_columns=int(selected.sum()),face_index=1000000+len(r.authored_roof_patches),
                      source_packet_sha256=packet_info['sha256'],
                      rule='Outside-original-roof enclosure addition; every retained source roof cell unchanged')
        r=replace(r,heights=h,gradient_x=gx,gradient_z=gz,face_indices=ids,
            footprint_mask=r.footprint_mask|selected,missing_mask=r.missing_mask&~selected,
            authored_roof_patches=(*r.authored_roof_patches,record))
        SOURCE['details']['roof_exceptions'].append(record)
    SOURCE['prepared_raster']=r
    return r


def build_details(f,p):
    controls=p['cfta_controls']
    front=controls['facades'][0]
    groups={g['id']:g for g in front['glazing_groups']}
    material=p['materials']
    pale,red=material['screen'],material['coarse_red']
    darkglass,blockglass=material['glass'],material['glass_block']
    # The higher auditorium and flytower are closed red massing. The low
    # lobby remains pale; no unobserved residential window rows are invented.
    f.recolor((120,-225,195,-187.9),56,82,material['flytower'])
    f.recolor((142,-219,157.3,-187.8),56,68,red)
    f.recolor((120,-187.9,195,-171.5),56,68.5,pale)
    _make_terrace_and_stairs(f,p)

    # Replace just the old front shell wall below its unchanged cap with the
    # separately registered glass plane. Retained roof shapes are untouched.
    clear=(f.local_mask((132.5,-175.3,150.6,-173.4)) |
           f.local_mask((150.6,-177.7,182.0,-173.4)))
    for y in range(f.height_y(56.3),f.height_y(68.5)):
        selected=clear & np.isin(f.c.roles[y+64],[ROLES.index('facade'),ROLES.index('trim')])
        f.c.data[y+64,selected]=0
        f.c.roles[y+64,selected]=0
    rear=plane_columns(f,-174.6,(133.1,181.7))
    for x,z in rear:
        low=min(f.c.ground_at(x,z),f.height_y(56.65)-1)
        for y in range(low,f.height_y(68.54)):
            f.c.set(x,y,z,red if y<f.height_y(59.9) else pale,'facade')
    west_return=path_columns(f,[[133.1,-174.6],[133.17,-178.25]],inward=(1,0))
    _put_columns(f,west_return,56.3,68.5,pale,'facade')
    # Solid thickness below the lobby and thin, fully supported floors behind
    # the glazing. These do not fill the screen-to-glass air gap.
    for height in (59.9,63.6):
        f.box((133.0,-178.1,181.8,-174.45),height-.5,height,
              'smooth_stone','floor',mask=f.r.footprint_mask)

    for group_id in ('west_upper_five_apertures','west_lower_five_glass_block_bays'):
        g=groups[group_id]
        for i,u in enumerate(g['centres_u_m']):
            cols=plane_columns(f,-174.6,(u-g['width_m']/2-.25,u+g['width_m']/2+.25))
            _sheet(f,group_id+f'-{i+1}',cols,g['bottom_navd88_m'],g['top_navd88_m'],
                   blockglass if 'lower' in group_id else darkglass,pale)
    g=groups['main_curtain_wall']
    cols=plane_columns(f,-174.6,(g['u_range_m'][0]-.25,g['u_range_m'][1]+.25))
    _sheet(f,'main_curtain_wall',cols,g['bottom_navd88_m'],68.0,darkglass,pale)
    # Native black fields lost the photographed aluminium grid. The source
    # agent authorizes sparse white panes, preserving transparency and the
    # same physical sheet rather than adding opaque half-metre bars.
    _pane_grid(f,'main_curtain_wall',cols,g['bottom_navd88_m'],68.0,6,
               g['horizontal_mullion_levels_navd88_m'][1:-1])
    SOURCE['details']['curtain_wall_grid']=dict(
        photo_vertical_pitch_m=g['vertical_mullion_pitch_m'],
        photo_horizontal_levels_navd88_m=g['horizontal_mullion_levels_navd88_m'],
        photo_upper_cell_count=g['upper_photo_cell_count'],
        representation='Fine aluminium grid approximated by pane texture with sparse white-pane principal columns and photographed horizontal levels; no half-metre opaque bars every 1.11m')

    # The three photographed lower doors sit in their own brick infill field.
    doors=front['ground_entrance_doors']
    for i,u in enumerate(doors['centres_u_m']):
        infill=plane_columns(f,-174.6,(u-1.5,u+1.5))
        _put_columns(f,infill,56.3,59.9,'bricks','facade')
        cols=plane_columns(f,-174.6,(u-1.25,u+1.25))
        _sheet(f,f'lower_double_door_set-{i+1}',cols,56.65,59.05,darkglass,'smooth_quartz')
        # A transparent white centre member records the paired leaves without
        # replacing the narrow aluminium frames with opaque full-width blocks.
        middle=min(cols,key=lambda q:abs(_uv(f,*q)[0]-u))
        for y in range(f.height_y(56.65),f.height_y(59.05)):
            f.c.set(middle[0],y,middle[1],'white_stained_glass','window')
    SOURCE['details']['door_policy']='Three fixed glazed double-door representations at the photo-derived thresholds; no claim of operable scaled leaves or completed interiors'

    # Follow the measured rounded corner behind the east screen. The former
    # U188.42/V-174.6 pane instruction has explicitly been withdrawn by Sol.
    curve=p['southeast_enclosure_path_uv_m']
    curve_cols=path_columns(f,curve,inward=(-1,-1))
    for x,z in curve_cols:
        for y in range(min(f.c.ground_at(x,z),f.height_y(56.65)-1),f.height_y(68.54)):
            f.c.set(x,y,z,pale,'facade')
    # Remove only the old source contour inside this bounded curved facade
    # zone, then retain the exact authored contour as the enclosure boundary.
    mask=f.local_mask((181.5,-184.5,189.5,-174.0))
    keep=np.zeros_like(mask)
    for x,z in curve_cols:keep[z-f.c.z_min,x-f.c.x_min]=True
    for y in range(f.height_y(59.95),f.height_y(67.85)):
        remove=mask & ~keep & (f.c.roles[y+64]==ROLES.index('facade'))
        f.c.data[y+64,remove]=0;f.c.roles[y+64,remove]=0
    _sheet(f,'southeast_curved_glazing',curve_cols,59.95,67.85,darkglass,pale)
    _pane_grid(f,'southeast_curved_glazing',curve_cols,59.95,67.85,4,
               list(np.linspace(59.95,67.85,7)[1:-1]))
    # Junction to the straight lobby plane is a real enclosed return.
    joint=path_columns(f,[[181.7,-174.6],curve[0]],inward=(-1,-1))
    _sheet(f,'lobby_to_curve_return',joint,59.95,67.85,darkglass,pale)
    # Close the visible rounded wall back into retained source construction.
    tail=path_columns(f,[curve[-1],[188.901,-187.148]],inward=(-1,-1))
    _put_columns(f,tail,56.65,68.54,pale,'facade')

    _make_screen(f,p,groups)
    _make_balcony_and_drum(f,p)
    # Reassert constant-plane roofing ties only over the air gap. They meet
    # both the screen and the lobby cap and never become free-standing teeth.
    for u in p['screen_roof_tie_centres_u_m']:
        ties=plane_columns(f,u,(-174.6,-171.9),axis='u',inward=(0,-1))
        _put_columns(f,ties,67.6,68.1,'smooth_quartz','trim')
        SOURCE['details']['structural_supports'].append(dict(kind='screen_to_lobby_tie',u_m=u,
            columns=ties,low_y=f.height_y(67.6),high_y_exclusive=f.height_y(68.1)))
    SOURCE['details']['closure_regions'].append(dict(name='straight_lobby_front',
        v_m=-174.6,u_range_m=[133.1,181.7],screen_v_m=-171.9,
        rule='Panes have full end jambs and caps; screen apertures are intentional open-air voids'))
    if p.get('auditorium_east_wall_control'):
        _straight_auditorium_wall(f,p)
    if p.get('roof_surface_material_control'):
        _roof_materials(f,p)
    if p.get('interpreted_rooftop_boxes'):
        _roof_boxes(f,p)
    f.features.update(dict(west_upper_apertures=5,west_lower_glass_block_bays=5,
                          lower_double_door_sets=3,curved_southeast_glazed_return=1,
                          independent_front_screen=1,rounded_stair_drum=1))


def _straight_auditorium_wall(f,p):
    """Source-approved wall-only regularization beneath the untouched roof."""
    control=p['auditorium_east_wall_control']
    columns=path_columns(f,control['endpoints_uv_m'],inward=(-1,0))
    va,vb=control['correction_v_range_m']
    columns=[q for q in columns if va<=_uv(f,*q)[1]<=vb]
    # Snap the regular wall skin to the inward cell when the nearest centre
    # lies on the lower lobby roof. Raising a wall through that retained cap
    # would falsify the source. The high face7 remains the wall's support.
    inside=[]
    for x,z in columns:
        for retreat in range(3):
            if SOURCE['original_raster'].face_indices[z-f.c.z_min,x-retreat-f.c.x_min]==7:
                q=(x-retreat,z);break
        else:raise ValueError('Auditorium plane lacks retained face7 support')
        if inside and q!=inside[-1] and abs(q[0]-inside[-1][0])+abs(q[1]-inside[-1][1])==2:
            prev=inside[-1];inside.append((min(q[0],prev[0]),max(q[1],prev[1])))
        if not inside or q!=inside[-1]:inside.append(q)
    columns=list(dict.fromkeys(inside))
    strip=f.local_mask(control['removal_bounds_uv_m'])&(f.v>=va)&(f.v<=vb)
    low,high=control['height_zone_navd88_m']
    changes=[]
    for x,z,iz,ix in f.each_column(strip):
        for y in range(f.height_y(low),f.height_y(high)):
            if f.c.roles[y+64,iz,ix]==ROLES.index('facade'):
                f.c.set(x,y,z,'air','air');changes.append([x,y,z,'removed_raster_wall'])
    for x,z in columns:
        iz,ix=z-f.c.z_min,x-f.c.x_min
        assert f.r.footprint_mask[iz,ix]
        top=_roof_top_y(f,iz,ix)
        for y in range(f.height_y(low),top):
            if f.c.roles[y+64,iz,ix] not in (ROLES.index('roof'),ROLES.index('trim')):
                f.c.set(x,y,z,p['materials']['flytower'],'facade');changes.append([x,y,z,'regular_wall'])
    SOURCE['details']['auditorium_east_wall_regularization']=dict(
        control=control,columns=columns,changes=changes,
        roof_rule='Retained roof caps/backing, source raster and source silhouette untouched')


def _roof_materials(f,p):
    """Retint occupied roof states without changing their model shape or top."""
    control=p['roof_surface_material_control']
    field=control['field_state_replacements']
    changes=[]
    # The rare stair states retain their facing, shape and half; the selected
    # vanilla replacements use identical occupied models.
    allowed=np.isin(SOURCE['original_raster'].face_indices,control['source_face_ids'])
    for iy,iz,ix in np.argwhere((f.c.roles==ROLES.index('roof'))&allowed[None]):
        before=f.c.palette[f.c.data[iy,iz,ix]]
        short=before['Name'].removeprefix('minecraft:')
        if short not in field:continue
        x,y,z=int(ix)+f.c.x_min,int(iy)-64,int(iz)+f.c.z_min
        f.c.set(x,y,z,field[short],'roof',before.get('Properties'))
        changes.append([x,y,z,before['Name'],field[short]])
    perimeter_changes=[]
    original=SOURCE['original_raster']
    for faces in ((1,3),(4,7),(8,),(9,)):
        mask=original.footprint_mask&np.isin(original.face_indices,faces)
        boundary=mask&~binary_erosion(mask)
        pale=faces==(9,)
        for x,z,iz,ix in f.each_column(boundary):
            top=_roof_top_y(f,iz,ix)
            for y in (top-1,top):
                if f.c.roles[y+64,iz,ix]!=ROLES.index('roof'):continue
                state=f.c.palette[f.c.get(x,y,z)];name=state['Name']
                if name.endswith('_slab'):block='smooth_quartz_slab' if pale else 'brick_slab'
                elif name.endswith('_stairs'):block='smooth_quartz_stairs' if pale else 'brick_stairs'
                else:block='smooth_quartz' if pale else 'terracotta'
                f.c.set(x,y,z,block,'trim' if pale or name.endswith(('_slab','_stairs')) else 'facade',state.get('Properties'))
                perimeter_changes.append([x,y,z,name,block])
    SOURCE['details']['roof_material_only_changes']=dict(control=control,
        roof_field_cells=changes,source_perimeter_cells=perimeter_changes,
        rule='Same occupied cells, original block shape/properties and physical roof top; no new courses, parapet height or footprint')


def _roof_boxes(f,p):
    boxes=[]
    for box in p['interpreted_rooftop_boxes']:
        u,v=box['centre_uv_m'];w,d=box['size_uv_m']
        selected=f.local_mask((u-w/2,v-d/2,u+w/2,v+d/2))
        assert np.all(SOURCE['original_raster'].face_indices[selected]==3)
        cells=[]
        for x,z,iz,ix in f.each_column(selected):
            top=_roof_top_y(f,iz,ix)
            cap=f.c.palette[f.c.get(x,top,z)]
            assert not cap['Name'].endswith(('_slab','_stairs'))
            f.c.set(x,top+1,z,'white_concrete','facade')
            cells.append([x,top+1,z])
        boxes.append(dict(**box,occupied_cells=cells,source_face=3,
            interpretation='One of about six visible compact pale roof boxes; centre and exact size are interpreted, equipment type unresolved',
            attachment='Full footprint rests on existing full roof caps; no source cap is replaced or raised'))
    SOURCE['details']['interpreted_rooftop_boxes']=boxes


def _surface(f,mask,levels,block='smooth_stone',role='pavement'):
    levels=np.broadcast_to(levels,mask.shape)
    records=[]
    for x,z,iz,ix in f.each_column(mask):
        half=math.floor((float(levels[iz,ix])+f.offset)*f.c.scale*2+.5)
        cap=(half-1)//2
        start=min(f.c.ground_at(x,z),cap)
        for y in range(start,cap):f.c.set(x,y,z,block,role)
        props={'type':'bottom','waterlogged':'false'} if half%2 else None
        f.c.set(x,cap,z,block+'_slab' if half%2 else block,role,props)
        for y in range(cap+1,max(cap+2,f.c.ground_at(x,z)+2)):
            if ROLES[f.c.roles[y+64,iz,ix]] in ('terrain','pavement','vegetation'):
                f.c.set(x,y,z,'air','air')
        records.append([x,cap,z,half/2])
    return records


def _rail(f,name,columns,levels):
    records=[]
    for x,z in columns:
        u,v=_uv(f,x,z)
        navd=float(levels(u,v))
        base=round((navd+f.offset)*f.c.scale)
        # Complete the support's top quarter-metre under a thin guard when its
        # adjacent landing quantizes to a bottom slab. Never leave bars aloft.
        below=f.c.palette[f.c.get(x,base-1,z)]
        if below['Name']=='minecraft:air' or below['Name'].endswith('_slab'):
            f.c.set(x,base-1,z,'smooth_stone','floor')
        for y in range(base,base+2):f.c.set(x,y,z,'iron_bars','railing',PANE_PROPS)
        records.append([x,base,z])
    SOURCE['details']['rails'].append(dict(name=name,bases=records,height_blocks=2))


def _make_terrace_and_stairs(f,p):
    joins={v['id']:v for v in p['cfta_controls']['site_joins']}
    terrace=joins['pond_terrace']
    records=_surface(f,f.local_mask(terrace['bounds_uv_m']),terrace['height_navd88_m'])
    SOURCE['details']['terrace']=dict(source=terrace,surface_cells=records)
    steps=joins['front_west_stair_and_landings']
    profile=np.asarray(steps['profile_u_h_m'])
    levels=np.interp(f.u,profile[:,0],profile[:,1])
    records=_surface(f,f.local_mask(steps['bounds_uv_m']),levels)
    SOURCE['details']['stairs'].append(dict(source=steps,surface_cells=records,
        representation='Quarter-metre supported slab treads interpolate only the LiDAR-profile flights, retaining its level landing segments'))
    railcols=plane_columns(f,-168.6,(127.3,157.7))
    _rail(f,'front_west_stair_guard',railcols,lambda u,v:np.interp(u,profile[:,0],profile[:,1]))
    # Threshold apron connects the three measured door centres to the terrace.
    _surface(f,f.local_mask((165.6,-174.6,176.5,-172.4)),56.65)


def _make_screen(f,p,groups):
    g=p['cfta_controls']['geometry']
    columns=plane_columns(f,g['pond_facade_v_m'],g['pond_facade_u_range_m'])
    holes=[]
    for gid in ('west_upper_five_apertures','west_lower_five_glass_block_bays'):
        a=groups[gid]
        for u in a['centres_u_m']:
            # The lower screen portals expose backing infill below the glass.
            bottom=a['bottom_navd88_m'] if 'upper' in gid else 56.3
            holes.append([u-a['width_m']/2,u+a['width_m']/2,bottom,a['top_navd88_m'],gid])
    a=groups['far_west_tall_portal'];holes.append([*a['u_range_m'],a['bottom_navd88_m'],a['top_navd88_m'],a['id']])
    a=groups['main_curtain_wall'];holes.append([*a['u_range_m'],56.3,a['outer_screen_aperture_top_navd88_m'],a['id']])
    a=groups['east_bay_two_levels'];u=a['centres_u_m'][0]
    for b,h in zip(a['bottoms_navd88_m'],a['heights_m']):
        holes.append([u-a['width_m']/2,u+a['width_m']/2,b,b+h,a['id']])
    holes.append([u-a['width_m']/2,u+a['width_m']/2,56.3,59.55,'east_ground_void'])
    support_columns=[]
    for x,z in columns:
        u,_=_uv(f,x,z)
        bottom=min(f.c.ground_at(x,z),f.height_y(56.3)-1)
        for y in range(bottom,f.height_y(g['front_parapet_navd88_m'])):
            h=(y+.5)/f.c.scale-f.offset
            aperture=any(a<=u<=b and lo<=h<hi for a,b,lo,hi,_ in holes)
            if aperture:
                f.c.set(x,y,z,'air','air')
            else:f.c.set(x,y,z,p['materials']['screen'],'facade')
        if not any(a<=u<=b for a,b,lo,hi,_ in holes):
            support_columns.append([x,bottom,z,f.height_y(g['front_parapet_navd88_m'])])
    SOURCE['details']['screen']=dict(columns=columns,apertures=holes,
        plane_v_m=g['pond_facade_v_m'],top_navd88_m=g['front_parapet_navd88_m'],
        full_height_support_columns=support_columns,
        material=p['materials']['screen'],constant_plane=True)


def _make_balcony_and_drum(f,p):
    front=p['cfta_controls']['facades'][0]
    balcony=front['balcony']
    # Continuous deck meets the backing wall. Full supporting red masonry
    # extends under the rear edge; slab depth is a photographed balcony proxy.
    deck=f.local_mask((132.9,-174.9,181.8,-172.75))
    f.box((132.9,-174.9,181.8,-172.75),59.4,59.9,'smooth_stone','floor',mask=deck)
    railcols=plane_columns(f,balcony['front_plane_v_m'],(133.0,181.7))
    _rail(f,'continuous_lobby_balcony_guard',railcols,lambda u,v:59.9)
    drum=front['rounded_stair_balcony_drum']
    cu,cv=drum['centre_uv_m'];radius=drum['outer_radius_m']
    # Only the outward semicircle is exposed. A closed rear chord connects
    # this photographed projection to the lobby wall and deck.
    angles=np.linspace(0,math.pi,33)
    points=[[cu+radius*math.cos(a),cv+radius*math.sin(a)] for a in angles]
    arc=path_columns(f,points,inward=(0,-1))
    _sheet(f,'rounded_stair_drum_glass_block',arc,59.95,62.0,p['materials']['glass_block'],p['materials']['screen'])
    _put_columns(f,arc,62.0,63.55,p['materials']['screen'],'facade')
    region=((f.u-cu)**2+(f.v-cv)**2<=radius**2)&(f.v>=cv)
    for level in (59.9,63.55):
        f.box((cu-radius,cv,cu+radius,cv+radius),level-.5,level,'smooth_stone','floor',mask=region)
    _rail(f,'rounded_drum_upper_guard',arc,lambda u,v:63.55)
    SOURCE['details']['drum']=dict(source=drum,arc_columns=arc,
        interpretation='Photographed semicircular glass-block stair/balcony form at supplied approximate centre and radius; connected to lobby by rear chord and floor slabs')
