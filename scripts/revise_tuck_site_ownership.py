"""Clone accepted Tuck geometry and bind its existing north site ownership."""

import json
from pathlib import Path
import shutil

import numpy as np

from assemble_hill_campus_studies import prepare_component
from audit_hill_block_artifact import audit
from build_hill_chapel_sample import Canvas, ROLES, build_ground, terrain_arrays
from campus_paving import smooth_exposed_measured_pavement
from campus_study_io import digest, write_json

ROOT=Path(__file__).resolve().parents[1]


def main():
    old=ROOT/'runtime/campus-reconstruction/tuck-rink-v5-2x'
    out=ROOT/'runtime/campus-reconstruction/tuck-rink-v6-2x'
    assert not out.exists()
    shutil.copytree(old,out)
    p=json.loads((old/'profile.json').read_text(encoding='utf-8'))
    p['revision']='2026-09-19-tuck-rink-6-2x-retained-north-site-ownership'
    p['assembly_site_bounds_uv_m']=[[-13,-170.8,55,-168.65],[40.7,-169.0,50.3,-165.8]]
    p['ownership_metadata_revision']=dict(
        unchanged_geometry_source=str(old.relative_to(ROOT)).replace('\\','/'),
        archive_sha256=digest(old/'sample-blocks.npz'),
        reason='V11 campus native view clipped the accepted north sidewalk outside the default architecture margin.',
        basis='Exact existing sidewalk and entry-landing masks in the immutable v5 generator and detail register; no new blocks or site design.')
    write_json(out/'profile.json',p)
    write_json(ROOT/'server-assets/hill-tuck-rink-reference.json',p)
    m=json.loads((old/'manifest.json').read_text(encoding='utf-8'))
    m['revision']=p['revision']
    m['profile']={'path':str(out/'profile.json'),'sha256':digest(out/'profile.json')}
    m['reference_profile']={'path':str(ROOT/'server-assets/hill-tuck-rink-reference.json'),
                            'sha256':digest(ROOT/'server-assets/hill-tuck-rink-reference.json')}
    m['ownership_metadata_revision']=p['ownership_metadata_revision']
    write_json(out/'manifest.json',m)
    cache=ROOT/'runtime/campus-reconstruction/component-cache'
    previous=prepare_component(old,cache,2,-25,.5)
    current=prepare_component(out,cache,2,-25,.5)
    added=current.mask & ~previous.mask
    registered=json.loads((old/'detail-register.json').read_text(encoding='utf-8'))
    site=registered['sidewalk']+registered['entry']['landing']
    site_columns={(q[0],q[2]) for q in site}
    site_owned=sum(bool(current.mask[z-current.meta['z_min'],x-current.meta['x_min']]) for x,z in site_columns)
    site_previously_unowned=sum(not bool(previous.mask[z-previous.meta['z_min'],x-previous.meta['x_min']]) for x,z in site_columns)
    manifest=json.loads((ROOT/'runtime/campus-reconstruction/campus-context-v11-2x/manifest.json').read_text(encoding='utf-8'))
    collisions=[]
    checked=0
    for spec in manifest['components']:
        if Path(spec['study']).resolve()==old.resolve():continue
        other=prepare_component(Path(spec['study']),cache,2,-25,spec['margin_m'])
        cx,cz=current.meta['x_min'],current.meta['z_min']
        ox,oz=other.meta['x_min'],other.meta['z_min']
        left,top=max(cx,ox),max(cz,oz)
        right,bottom=min(cx+current.mask.shape[1],ox+other.mask.shape[1]),min(cz+current.mask.shape[0],oz+other.mask.shape[0])
        checked+=1
        if left<right and top<bottom:
            overlap=current.mask[top-cz:bottom-cz,left-cx:right-cx] & other.mask[top-oz:bottom-oz,left-ox:right-ox]
            if overlap.any():collisions.append(dict(study=spec['study'],columns=int(overlap.sum())))
    bb=m['source_roof']['world_bounds_blocks']
    terrain=ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz'
    h,ids,meta=terrain_arrays(terrain,2,[v/2 for v in bb])
    ground=Canvas(bb[0],bb[1],bb[2]-bb[0],bb[3]-bb[1],2)
    build_ground(ground,h,ids,meta['materials'],-25)
    smooth_exposed_measured_pavement(ground,h,ground.ground_heights,vertical_offset=-25)
    palette={json.dumps(s,sort_keys=True):i for i,s in enumerate(current.meta['palette'])}
    lookup=np.array([palette.get(json.dumps(s,sort_keys=True),65535) for s in ground.palette])
    role_ids=[ROLES.index('terrain'),ROLES.index('pavement')]
    changed=(((current.data!=lookup[ground.data]) | (current.roles!=ground.roles)) &
        (np.isin(current.roles,role_ids)|np.isin(ground.roles,role_ids))).any(0)
    world_files=[]
    for path in sorted((old/'world').rglob('*')):
        if path.is_file():
            rel=path.relative_to(old)
            world_files.append(dict(path=str(rel).replace('\\','/'),sha256=digest(path),
                byte_identical=digest(path)==digest(out/rel)))
    proof=dict(format='hill-tuck-owned-site-proof-v1',
        archive_sha256=digest(out/'sample-blocks.npz'),previous_study=str(old.relative_to(ROOT)).replace('\\','/'),
        previous_profile_sha256=digest(old/'profile.json'),profile_sha256=digest(out/'profile.json'),
        block_archive_byte_identical=digest(old/'sample-blocks.npz')==digest(out/'sample-blocks.npz'),
        world_files=world_files,site_bounds_uv_m=p['assembly_site_bounds_uv_m'],
        registered_site_columns=len(site_columns),registered_site_columns_owned=site_owned,
        previously_unowned_registered_site_columns=site_previously_unowned,
        previous_owned_columns=int(previous.mask.sum()),current_owned_columns=int(current.mask.sum()),
        added_owned_columns=int(added.sum()),all_changed_ground_columns=int(changed.sum()),
        changed_ground_columns_outside_old_ownership=int((changed&~previous.mask).sum()),
        changed_ground_columns_outside_new_ownership=int((changed&~current.mask).sum()),
        neighbor_components_checked=checked,ownership_collisions=collisions,
        scope='Ownership only. Exact accepted v5 sample, source controls, states, roles, camera poses, world files and site construction retained.',
        passed=bool(site_owned==len(site_columns) and not (changed&~current.mask).any()
            and not collisions and all(q['byte_identical'] for q in world_files)))
    write_json(out/'site-ownership-proof.json',proof)
    assert proof['passed'],proof
    artifact=audit(out)
    write_json(out/'artifact-audit.json',artifact)
    assert artifact['passed']
    review=json.loads((old/'native-review.json').read_text(encoding='utf-8'))
    review['revision']='v6 metadata-only site-ownership correction'
    review['native_evidence_note']='All listed fresh four-view images were captured from v5, not v6. The v6 archive and complete world files are byte-identical to v5; site-ownership-proof.json proves this. No new standalone native geometry claim is made.'
    review['profile_sha256']=digest(out/'profile.json')
    review['site_ownership_proof_sha256']=digest(out/'site-ownership-proof.json')
    image=ROOT/'runtime/campus-reconstruction/chapel-native-qa/runs/campus-v11-integration-20260919/screenshots/tuck-north-overview.png'
    review['integration_defect']={'path':str(image.relative_to(ROOT)).replace('\\','/'),'sha256':digest(image),
        'finding':'V11 context loses most pale north sidewalk to grass because default architecture-derived ownership excludes pavement-only columns.',
        'disposition':'V6 explicitly owns the existing bounded sidewalk/landing masks. Fresh combined native correction verification remains required.'}
    review['findings'].append('Metadata-only v6 preserves every v5 block and world byte while adding bounded assembly ownership for the already reviewed north sidewalk and entrance. All authored ground mutation columns are now owned; no ownership overlap with any other campus component.')
    review['remaining_limits'].append('V6 site-ownership correction is analytically checked; the next combined-campus capture must verify the restored north sidewalk. V11 campus is not accepted evidence of the correction.')
    review['audit_files'].append('site-ownership-proof.json')
    write_json(out/'native-review.json',review)
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    files=json.loads((old/'final-hashes.json').read_text(encoding='utf-8'))['files']
    for name in ('site-ownership-proof.json','revise_tuck_site_ownership.py'):files[name]=None
    write_json(out/'final-hashes.json',dict(status=review['status'],created='2026-09-19',
        files={name:digest(out/name) for name in files}))
    print(json.dumps({'output':str(out),'archive':digest(out/'sample-blocks.npz'),
        'review':digest(out/'native-review.json'),'final_hashes':digest(out/'final-hashes.json'),
        'proof':{k:v for k,v in proof.items() if k!='world_files'}},indent=2))


if __name__=='__main__':main()
