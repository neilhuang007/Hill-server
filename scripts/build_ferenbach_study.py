"""Build a new native-ready Ferenbach exterior draft; never overwrite a study."""

import argparse
from pathlib import Path
import shutil

import numpy as np

from build_hill_detailed_buildings import build
from campus_study_io import digest, write_json
import hill_ferenbach_details as detail

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=ROOT/'server-assets/hill-ferenbach-reference.json')
    a=parser.parse_args();out=a.output.resolve()
    build(a.profile.resolve(),out,ROOT/'runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz')
    r=detail.SOURCE['raster']
    np.savez_compressed(out/'source-roof-raster.npz',heights=r.heights,mask=r.footprint_mask,
        face_indices=r.face_indices,gradient_x=r.gradient_x,gradient_z=r.gradient_z,
        body_mask=detail.SOURCE['body_mask'],wall_mask=detail.SOURCE['wall_mask'])
    write_json(out/'detail-register.json',detail.SOURCE['details'])
    for name in ('hill_ferenbach_details.py','build_ferenbach_study.py','audit_ferenbach_study.py'):
        if (ROOT/'scripts'/name).exists():shutil.copyfile(ROOT/'scripts'/name,out/name)
    write_json(out/'native-review.json',dict(status='pending_native_review',
        archive_sha256=digest(out/'sample-blocks.npz'),inspected_images=[],
        limitations=['Exterior draft only; hidden openings and exact entrance position unresolved.']))
    print('FERENBACH_READY',out,digest(out/'sample-blocks.npz'),flush=True)


if __name__=='__main__':main()
