"""Read-only source/scope inventory for Dining inside the accepted Athey study."""
import json
from pathlib import Path
import hashlib
import numpy as np

from build_hill_chapel_sample import Canvas
from campus_reference_details import ReferenceExterior
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import write_json, digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'runtime/campus-reconstruction/athey-frame-v4-2x'
OUT = ROOT/'runtime/campus-reconstruction/athey-dining-preparation-20260915'


def main():
    assert digest(BASE/'sample-blocks.npz') == '8c925fdcd2e3ea8cf380c0e624f10b858d247d68c599b71ab75a6b3d56eacdb5'
    p = json.loads((BASE/'profile.json').read_text(encoding='utf-8'))
    m = json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    b = load_measured_building(ROOT/p['source_cityjson'], p['parent_id'], ROOT/p['measured_terrain_manifest'])
    assert b.source_sha256 == m['sources']['roof']['sha256']
    bb = m['source_roof']['world_bounds_blocks']
    r = rasterize_roof(b, [v/2 for v in bb], .5)
    c = Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    f = ReferenceExterior(c,p,r,-25)
    def uv(x,z):
        dx,dz=x-f.origin[0],z-f.origin[1]
        return [float(dx*f.t[0]+dz*f.t[1]),float(dx*f.n[0]+dz*f.n[1])]
    records = []
    for i,face in enumerate(b.roof_faces):
        xy = list(face.polygon.exterior.coords)
        local = np.array([uv(x,z) for x,z in xy])
        mask = r.footprint_mask & (r.face_indices==i)
        records.append({'face_id':i,'source_surface':face.surface_index,
            'area_m2':float(face.polygon.area),'bounds_uv_m':[*local.min(0).tolist(),*local.max(0).tolist()],
            'heights_navd88_m':[face.min_h,face.max_h],'plane_abc_xz': [face.a,face.b,face.c],
            'raster_columns':int(mask.sum()),'exterior_xz_m':xy,
            'holes_xz_m':[list(v.coords) for v in face.polygon.interiors],
            'source_part_id':face.part_id})
    high = r.footprint_mask & (r.heights>=p['geometry']['main_roof_threshold_navd88_m'])
    regions = {}
    for name,mask in (('athey_high_source',high),('southern_source',r.footprint_mask & (f.v>=35)),
                      ('court_rectangle',f.local_mask(p['geometry']['court_bounds_uv_m']))):
        regions[name]={'column_count':int(mask.sum()),'bounds_uv_m':[float(f.u[mask].min()),float(f.v[mask].min()),float(f.u[mask].max()),float(f.v[mask].max())],
                       'roof_face_ids':sorted(map(int,np.unique(r.face_indices[mask & r.footprint_mask]))),
                       'inside_source_ground_columns':int((mask&r.footprint_mask).sum())}
    OUT.mkdir(parents=True,exist_ok=True)
    write_json(OUT/'source-scope-inventory.json',{'status':'preparation_only_no_geometry_changed',
        'baseline_study':str(BASE),'baseline_archive_sha256':digest(BASE/'sample-blocks.npz'),
        'source_cityjson_sha256':b.source_sha256,'parent_id':p['parent_id'],
        'frame':{'origin_xz_m':p['geometry']['origin_xz_m'],'axis_degrees':p['geometry']['axis_degrees'],
                 'blocks_per_metre':2,'vertical_offset_m':-25},
        'regions':regions,'roof_faces':records,
        'proposed_mutation_strategy':'Load the exact accepted block archive, apply only packet-authorized Dining/court/link volumes, and require zero state or role changes outside those volumes. Export as one complete replacement component for the same parent.'})
    print(json.dumps({'output':str(OUT),'roof_face_count':len(records),'regions':regions},indent=2))


if __name__=='__main__':
    main()
