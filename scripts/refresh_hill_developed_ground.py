"""Regenerate existing authored studies against the native 0.5 m terrain.

Building profiles retain individual construction rules and explicitly inherit
their reviewed legacy palette. Output is a fresh revision; native review is
still required and this does not promote any campus launcher.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--terrain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    crops = json.loads((ROOT / "runtime/campus-reconstruction/campus-full-detail-preparation/manifest.json").read_text(encoding="utf-8"))["crops"]
    tasks = [(0, "alumni-house", "build_hill_alumni_house.py"),
             (2, "athey", "build_hill_athey.py"),
             (3, "ryan-library", "build_hill_ryan_library.py"),
             (4, "hunt-hall", "build_hill_hunt_hall.py")]
    components = []
    for index, slug, script in tasks:
        source = config["components"][index]
        source_study = ROOT / source["study"]
        profile = json.loads((source_study / "profile.json").read_text(encoding="utf-8"))
        profile.pop("material_review", None)
        profile.setdefault("name", source["name"])
        profile["revision"] += "-native-ground-20260907"
        profile["terrain_bounds_m"] = crops[slug]["physical_bounds"]
        profile["terrain_revision"] = {
            "source": args.terrain.resolve().as_posix(), "sha256": digest(args.terrain),
            "surface_datum": "Block top represents measured NAVD88 ground; no extra half-metre offset.",
            "previous_study": source["study"],
        }
        profile_path = args.output / "profiles" / (slug + ".json")
        write_json(profile_path, profile)
        output = args.output / slug
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--profile", str(profile_path),
                        "--terrain", str(args.terrain), "--output", str(output)], check=True, cwd=ROOT)
        components.append({**source, "study": output.resolve().relative_to(ROOT).as_posix(),
                           "ground_status": "regenerated_native_half_metre_grid_pending_native"})
        write_json(args.output / "components.json", components)
    output = args.output / "chapel"
    subprocess.run([sys.executable, str(ROOT / "scripts/build_hill_chapel_context.py"),
                    "--output", str(output), "--scale", "2", "--terrain", str(args.terrain),
                    "--terrain-bounds", *map(str, crops["chapel"]["physical_bounds"])], check=True, cwd=ROOT)
    components.append({**config["components"][1], "study": output.resolve().relative_to(ROOT).as_posix(),
                       "ground_status": "regenerated_native_half_metre_grid_pending_native"})
    write_json(args.output / "components.json", components)
    pavilions = args.output / "pavilions"
    subprocess.run([sys.executable, str(ROOT / "scripts/build_hill_current_pavilions.py"),
                    "--output", str(pavilions), "--terrain", str(args.terrain)], check=True, cwd=ROOT)
    components.extend(json.loads((pavilions / "components.json").read_text(encoding="utf-8")))
    write_json(args.output / "components.json", components)


if __name__ == "__main__":
    main()
