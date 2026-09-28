"""Export a fresh immutable Tuck/Rink study with its building-specific inputs."""

import argparse
from pathlib import Path
import shutil

import numpy as np

from build_hill_detailed_buildings import build
from campus_study_io import digest, write_json
import hill_tuck_rink_details as detail

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=ROOT/'server-assets/hill-tuck-rink-reference.json')
    args=parser.parse_args();out=args.output.resolve()
    build(args.profile.resolve(),out,ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz')
    write_json(out/'detail-register.json',detail.SOURCE['details'])
    r=detail.SOURCE['raster']
    np.savez_compressed(out/'source-roof-raster.npz',heights=r.heights,mask=r.footprint_mask,
        face_indices=r.face_indices,gradient_x=r.gradient_x,gradient_z=r.gradient_z)
    for name in ('hill_tuck_rink_details.py','build_tuck_rink_study.py','audit_tuck_rink_study.py'):
        shutil.copyfile(ROOT/'scripts'/name,out/name)
    print('TUCK_RINK_READY',out,digest(out/'sample-blocks.npz'),flush=True)


if __name__=='__main__':main()
