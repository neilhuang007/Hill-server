"""Construct each authored building and retain a separate native review package."""

import argparse
import importlib
import json
import math
from pathlib import Path

from build_hill_chapel_sample import (
    Canvas,
    build_ground,
    connect_window_panes,
    terrain_arrays,
)
from campus_athey_details import connect_iron_rails
from campus_measured_shell import build_measured_shell
from campus_paving import smooth_exposed_measured_pavement
from campus_reference_details import ReferenceExterior, connect_wood_fences
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study

ROOT = Path(__file__).resolve().parents[1]


def build(profile_path, output, terrain):
    p = json.loads(profile_path.read_text(encoding="utf-8"))
    if output.exists():
        raise FileExistsError(output)
    b = load_measured_building(parent_id=p["parent_id"])
    x0, z0, x1, z1 = b.footprint.bounds
    margin = p.get("study_margin_m", 12)
    bounds = (
        math.floor((x0 - margin) / 8) * 8,
        math.floor((z0 - margin) / 8) * 8,
        math.ceil((x1 + margin) / 8) * 8,
        math.ceil((z1 + margin) / 8) * 8,
    )
    s, offset = 2, -25
    h, ids, meta = terrain_arrays(terrain, s, bounds)
    c = Canvas(round(bounds[0] * s), round(bounds[1] * s), h.shape[1], h.shape[0], s)
    build_ground(c, h, ids, meta["materials"], offset)
    smooth_exposed_measured_pavement(c, h, c.ground_heights, vertical_offset=offset)
    r = rasterize_roof(b, bounds, resolution=0.5)
    module = importlib.import_module(p["detail_module"])
    if hasattr(module, "prepare_roof"):
        r = module.prepare_roof(r, ReferenceExterior(c, p, r, offset), p)
    shell = build_measured_shell(
        c,
        b,
        r,
        vertical_offset=offset,
        floor_navd88=p["geometry"]["entrance_floor_navd88_m"],
        facade=p["materials"]["facade"],
        foundation=p["materials"]["foundation"],
        roof_family=p["materials"]["roof_family"],
        roof_backing_metres=0.4,
    )
    f = ReferenceExterior(c, p, r, offset)
    module.build_details(f, p)
    connect_window_panes(c)
    connect_iron_rails(c)
    connect_wood_fences(c)
    cameras = []
    for v in p["camera_views"]:

        def point(uvh):
            x, z = f.world(*uvh[:2])
            return [x * s, (uvh[2] + offset) * s, z * s]

        cameras.append(
            {
                "name": v["name"],
                "eye": point(v["eye_uv_navd88_m"]),
                "target": point(v["target_uv_navd88_m"]),
                "fov": v.get("fov", 65),
            }
        )
    return finish_study(
        c,
        p,
        output,
        cameras,
        {
            "source_roof": shell.to_manifest(),
            "features": dict(f.features),
            "photo_interpreted_roof_corrections": list(r.authored_roof_patches),
            "terrain": {
                "path": str(terrain),
                "sha256": digest(terrain),
                "resolution_m": 0.5,
                "surface_datum_corrected": True,
            },
            "reference_profile": {
                "path": str(profile_path),
                "sha256": digest(profile_path),
            },
            "detail_generator": {
                "path": str(Path(module.__file__)),
                "sha256": digest(module.__file__),
            },
            "uncertainties": p.get("uncertainties", []),
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--terrain",
        type=Path,
        default=ROOT
        / "runtime/campus-reconstruction/campus-full-detail-preparation/terrain.npz",
    )
    a = parser.parse_args()
    build(a.profile, a.output, a.terrain)


if __name__ == "__main__":
    main()
