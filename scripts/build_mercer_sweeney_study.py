"""Export an immutable Mercer / Day / Sweeney source-bound facade study."""

import argparse
import shutil
from pathlib import Path

import numpy as np

from build_hill_detailed_buildings import build
from campus_study_io import digest, write_json
import hill_mercer_sweeney_details as detail

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT/'server-assets/hill-mercer-sweeney-reference.json')
    args = parser.parse_args()
    out = args.output.resolve()
    build(args.profile.resolve(), out, ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz')
    write_json(out/'detail-register.json', detail.SOURCE['details'])
    for name in ('original_raster', 'raster'):
        r = detail.SOURCE[name]
        np.savez_compressed(out/f'{name}.npz', heights=r.heights, mask=r.footprint_mask,
                            face_indices=r.face_indices, gradient_x=r.gradient_x, gradient_z=r.gradient_z)
    for name in ('hill_mercer_sweeney_details.py', 'build_mercer_sweeney_study.py', 'audit_mercer_sweeney_study.py'):
        shutil.copyfile(ROOT/'scripts'/name, out/name)
    print('MERCER_SWEENEY_READY', out, digest(out/'sample-blocks.npz'), flush=True)


if __name__ == '__main__':
    main()
