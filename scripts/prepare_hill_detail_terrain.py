"""Normalize the independently sampled 0.5 m DEM for all architectural builders."""

import json
from pathlib import Path

import numpy as np
from build_hill_chapel_sample import terrain_arrays
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (
        ROOT
        / "runtime/research/campus-full-detail-20260905/terrain-direct-native-0p5m.npz"
    )
    old = (
        ROOT / "runtime/campus-reconstruction/campus-all-named-preparation/terrain.npz"
    )
    output = ROOT / "runtime/campus-reconstruction/campus-full-detail-preparation"
    output.mkdir(parents=True, exist_ok=True)
    with np.load(old, allow_pickle=False) as a:
        meta = json.loads(str(a["metadata_json"]))
    with np.load(source, allow_pickle=False) as a:
        h, ids = a["ground_elevation_navd88_m"], a["material_id"]
        evidence = json.loads(str(a["metadata_json"]))
    meta.update(
        resolution_m=0.5,
        physical_surface_formula="(NAVD88_m - 25) * blocks_per_metre",
        source_native_grid={
            "path": str(source),
            "sha256": digest(source),
            "evidence": evidence,
        },
    )
    target = output / "terrain.npz"
    np.savez_compressed(
        target,
        ground_elevation_navd88_m=h,
        material_id=ids,
        x_min=-224,
        z_min=-608,
        metadata_json=json.dumps(meta),
    )
    original = {
        "athey": "measured-terrain-academic-quad-v1/hill-academic-quad-measured-terrain.npz",
        "ryan-library": "ryan-library-preparation/terrain.npz",
        "hunt-hall": "hunt-hall-preparation/terrain.npz",
        "alumni-house": "alumni-house-preparation/terrain.npz",
        "chapel": "measured-terrain/hill-chapel-measured-terrain.npz",
    }
    crops = {}
    for name, relative in original.items():
        path = ROOT / "runtime/campus-reconstruction" / relative
        if not path.exists():
            continue
        with np.load(path, allow_pickle=False) as a:
            xmin, zmin = int(a["x_min"]), int(a["z_min"])
            rows, cols = a["ground_elevation_navd88_m"].shape
        bounds = (xmin, zmin, xmin + cols, zmin + rows)
        height, materials, metadata = terrain_arrays(target, 2, bounds)
        destination = output / f"{name}-terrain.npz"
        np.savez_compressed(
            destination,
            ground_elevation_navd88_m=height,
            material_id=materials,
            x_min=xmin,
            z_min=zmin,
            metadata_json=json.dumps(metadata),
        )
        crops[name] = {"path": str(destination), "physical_bounds": bounds}
    write_json(
        output / "manifest.json",
        {
            "terrain": str(target),
            "sha256": digest(target),
            "resolution_m": 0.5,
            "physical_bounds": [-224, -608, 544, 160],
            "crops": crops,
            "vertical_surface_correction_m": -0.5,
        },
    )


if __name__ == "__main__":
    main()
