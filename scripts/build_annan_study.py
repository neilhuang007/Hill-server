"""Export a fresh immutable Annan study with building-owned source evidence."""

import argparse
from pathlib import Path
import shutil

import numpy as np

from build_hill_detailed_buildings import build
from campus_study_io import digest, write_json
import hill_annan_details as detail

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=ROOT/'server-assets/hill-annan-reference.json')
    args=parser.parse_args();out=args.output.resolve()
    build(args.profile.resolve(),out,ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz')
    write_json(out/'detail-register.json',detail.SOURCE['details'])
    for name,key in [('source-roof-raster.npz','source_raster'),('authored-roof-raster.npz','raster')]:
        r=detail.SOURCE[key]
        np.savez_compressed(out/name,heights=r.heights,mask=r.footprint_mask,
            face_indices=r.face_indices,gradient_x=r.gradient_x,gradient_z=r.gradient_z)
    for name in ('hill_annan_details.py','build_annan_study.py','audit_annan_study.py'):
        if (ROOT/'scripts'/name).exists():shutil.copyfile(ROOT/'scripts'/name,out/name)
    print('ANNAN_READY',out,digest(out/'sample-blocks.npz'),flush=True)


if __name__=='__main__':main()
