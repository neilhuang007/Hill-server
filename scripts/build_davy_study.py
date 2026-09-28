"""Freeze a new Davy study with its exact source and detail registers."""
import argparse
from pathlib import Path
import shutil
import numpy as np

from build_hill_detailed_buildings import build
from campus_study_io import digest, write_json
import hill_davy_details as detail

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    build(ROOT/"server-assets/hill-davy-reference.json", output,
          ROOT/"runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz")
    write_json(output/"detail-register.json", detail.SOURCE["details"])
    source = detail.SOURCE["raster"]
    np.savez_compressed(output/"source-roof-raster.npz", heights=source.heights,
                        face_indices=source.face_indices, mask=source.footprint_mask,
                        gradient_x=source.gradient_x, gradient_z=source.gradient_z)
    shutil.copyfile(ROOT/"scripts/hill_davy_details.py", output/"detail-generator.py")
    print("BUILT", str(output), digest(output/"sample-blocks.npz"), flush=True)


if __name__ == "__main__":
    main()
