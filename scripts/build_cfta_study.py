"""Create one immutable CFTA study and freeze the building-specific inputs."""

import argparse
from pathlib import Path
import shutil

import numpy as np

from build_hill_detailed_buildings import build
from campus_study_io import digest, write_json
import hill_cfta_details as detail

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT/'server-assets/hill-cfta-reference.json')
    args = parser.parse_args()
    output = args.output.resolve()
    build(args.profile.resolve(), output,
          ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz')
    write_json(output/'detail-register.json', detail.SOURCE['details'])
    source = detail.SOURCE['original_raster']
    prepared = detail.SOURCE['prepared_raster']
    np.savez_compressed(output/'source-roof-raster.npz',
                        heights=source.heights, face_indices=source.face_indices,
                        mask=source.footprint_mask, gradient_x=source.gradient_x,
                        gradient_z=source.gradient_z,
                        prepared_heights=prepared.heights,
                        prepared_mask=prepared.footprint_mask,
                        prepared_face_indices=prepared.face_indices)
    for file in ('hill_cfta_details.py', 'build_cfta_study.py'):
        shutil.copyfile(ROOT/'scripts'/file, output/file)
    print('CFTA_READY', output, digest(output/'sample-blocks.npz'), flush=True)


if __name__ == '__main__':
    main()
