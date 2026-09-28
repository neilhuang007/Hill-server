"""Compare pasted study columns, including air, with the combined campus.

This checks the composition itself: later terrain or landscaping operations
must not erase an accepted building's openings, passages or authored ground.
Archive-to-Anvil parity remains a separate whole-campus audit.
"""
import argparse
from collections import Counter
import gc
import json
import math
from pathlib import Path

import numpy as np
from assemble_hill_campus_studies import prepare_component
from campus_export_parity import read_archive
from campus_study_io import digest, write_json


def key(state):
    return state['Name'], tuple(sorted(state.get('Properties', {}).items()))


def audit(directory, studies, camera_config=None, retained_site_proof=None):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    integrated = {str(Path(c['study']).resolve()): c for c in manifest['components']}
    components = []
    for p in studies:
        existing = integrated.get(str(p.resolve()))
        if existing is None:
            raise ValueError(f'Study is absent from assembly: {p}')
        components.append(prepare_component(p, Path('runtime/campus-reconstruction/component-cache'),
                                            2, -25, existing['margin_m']))
    for c in components:
        if integrated.get(str(Path(c.meta['study']).resolve())) != c.meta:
            raise ValueError(f"Study does not exactly match integrated component: {c.meta['study']}")
    views = json.loads(camera_config.read_text(encoding='utf-8'))['views'] if camera_config else []
    cameras, totals, failures, examples = [], Counter(), Counter(), []
    x0, z0, x1, z1 = manifest['bounds_xz_blocks']
    for tile_spec in manifest['tiles']:
        tile = directory / tile_spec['path']
        tx, tz = map(int, tile.name[1:].split('_z'))
        right, bottom = min(tx + 256, x1), min(tz + 256, z1)
        relevant = [c for c in components if c.meta['x_min'] < right and tx < c.meta['x_min'] + c.data.shape[2]
                    and c.meta['z_min'] < bottom and tz < c.meta['z_min'] + c.data.shape[1]]
        eyes = [v for v in views if tx <= v['eye'][0] < right and tz <= v['eye'][2] < bottom]
        if not relevant and not eyes:
            continue
        archive = read_archive(tile / 'sample-blocks.npz')
        palette = archive['palette_keys']
        assert palette[0] == ('minecraft:air', ())
        grid = np.zeros((384, bottom-tz, right-tx), dtype=np.uint16)
        q = archive['coords']
        grid[q[:, 1]+64, q[:, 2]-tz, q[:, 0]-tx] = archive['state_ids']
        del archive, q
        palette_ids = {k:i for i,k in enumerate(palette)}
        for c in relevant:
            cx, cz = c.meta['x_min'], c.meta['z_min']
            left, top = max(tx,cx), max(tz,cz)
            r, b = min(right,cx+c.data.shape[2]), min(bottom,cz+c.data.shape[1])
            source = (slice(top-cz,b-cz), slice(left-cx,r-cx))
            target = (slice(top-tz,b-tz), slice(left-tx,r-tx))
            mask, minimum = c.mask[source], c.minimum[source]
            mapping = np.array([palette_ids.get(key(p),-1) for p in c.meta['palette']], dtype=np.int32)
            label = Path(c.meta['study']).name
            for y in range(384):
                selected = mask & (y-64 >= minimum)
                if not selected.any():
                    continue
                actual = grid[(y,)+target]
                expected = mapping[c.data[(y,)+source]]
                different = selected & (actual != expected)
                totals[label] += int(selected.sum())
                failures[label] += int(different.sum())
                # The retained-site proof must enumerate every difference; a
                # display-oriented cap would make large valid site overlays
                # impossible to verify. The CLI still prints only 12 examples.
                for iz,ix in np.argwhere(different):
                    s = int(c.data[y,top-cz+iz,left-cx+ix])
                    examples.append({'study':label,'xyz':[left+int(ix),y-64,top+int(iz)],
                                     'expected':c.meta['palette'][s], 'actual':palette[int(actual[iz,ix])]})
        for v in eyes:
            ex,ey,ez = map(math.floor,v['eye'])
            state = palette[int(grid[ey+64,ez-tz,ex-tx])]
            cameras.append({'name':v['name'], 'eye':v['eye'], 'state':state, 'air':state == ('minecraft:air',())})
        del grid
        gc.collect()
    unexplained = failures.copy()
    retained = None
    if retained_site_proof:
        proof = json.loads(retained_site_proof.read_text(encoding='utf-8'))
        if (proof.get('format') != 'hill-retained-site-proof-v1' or not proof.get('passed')
                or proof['manifest_sha256'] != digest(directory/'manifest.json')):
            raise ValueError('Retained site proof is not bound to this exact assembly')
        for source in proof['inputs']:
            if digest(Path(source['path'])) != source['sha256']:
                raise ValueError(f"Retained site proof input changed: {source['path']}")
        allowed = {json.dumps(e,sort_keys=True) for e in proof['site_cells']}
        if len(allowed) != proof['count']:
            raise ValueError('Retained site proof contains duplicate cells')
        applied = set()
        for e in examples:
            signature = json.dumps(e,sort_keys=True)
            if signature in allowed:
                applied.add(signature)
                unexplained[e['study']] -= 1
        if applied != allowed:
            raise ValueError('Retained site proof cells do not exactly match current differences')
        retained = {'path':str(retained_site_proof),'sha256':digest(retained_site_proof),
                    'applied_cells':len(applied)}
    passed = not any(unexplained.values()) and len(cameras) == len(views) and all(c['air'] for c in cameras)
    report = {'format':'hill-integrated-study-audit-v1', 'passed':passed,
              'manifest_sha256':digest(directory/'manifest.json'),
              'compared_cells_including_air':dict(totals), 'different_cells':dict(failures),
              'unexplained_different_cells':dict(unexplained), 'retained_site_proof':retained,
              'examples':examples, 'camera_eyes':cameras,
              'scope':'Exact full block states from each integrated study foundation through world height in its owned columns, including air and authored terrain. Any retained campus-site differences require an enumerated exact-state proof bound to this assembly and unchanged source files. Native inspection and occupied-shape source audits remain required.'}
    write_json(directory/'integrated-study-audit.json',report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--study', type=Path, action='append', required=True)
    p.add_argument('--camera-config', type=Path)
    p.add_argument('--retained-site-proof', type=Path)
    a = p.parse_args()
    r = audit(a.directory, a.study, a.camera_config, a.retained_site_proof)
    print(json.dumps({**{k:r[k] for k in ('passed','compared_cells_including_air','different_cells','unexplained_different_cells','retained_site_proof')},
                      'examples':r['examples'][:12]}))
    raise SystemExit(0 if r['passed'] else 1)
