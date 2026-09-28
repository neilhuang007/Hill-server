"""Produce local metric roof reference sheets for individually authored facades."""

import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import write_json

ROOT = Path(__file__).resolve().parents[1]
PARENTS = {
    "quadrivium": "16001511600615C-ee30229dd5",
    "warner": "160015116006389O-f1989780fb",
    "wendell": "16001511600617C-403d7b1a51",
    "music": "16001511600622C-57b5b354dc",
    "dining": "16001511600613C-92645e8573",
}


def main():
    output = ROOT / "runtime/research/campus-full-detail-20260905"
    records = {}
    for name, parent in PARENTS.items():
        b = load_measured_building(parent_id=parent)
        points = np.array(b.footprint.minimum_rotated_rectangle.exterior.coords)[:4]
        edges = np.roll(points, -1, axis=0) - points
        axis = edges[np.argmax(np.linalg.norm(edges, axis=1))]
        axis /= np.linalg.norm(axis)
        if axis[0] < 0:
            axis = -axis
        origin = np.array(b.footprint.centroid.coords[0])
        normal = np.array([-axis[1], axis[0]])
        bx0, bz0, bx1, bz1 = b.footprint.bounds
        r = rasterize_roof(
            b,
            (math.floor(bx0), math.floor(bz0), math.ceil(bx1), math.ceil(bz1)),
            resolution=0.25,
        )
        zz, xx = np.indices(r.heights.shape)
        x = r.bounds[0] + (xx + 0.5) * 0.25
        z = r.bounds[1] + (zz + 0.5) * 0.25
        u, v = (
            (x - origin[0]) * axis[0] + (z - origin[1]) * axis[1],
            (x - origin[0]) * normal[0] + (z - origin[1]) * normal[1],
        )
        f, axes = plt.subplots(1, 2, figsize=(18, 7))
        for a, cx, cz, label in [
            (axes[0], x, z, "World XZ metres"),
            (axes[1], u, v, "Local UV metres"),
        ]:
            mesh = a.scatter(
                cx[r.footprint_mask],
                cz[r.footprint_mask],
                c=r.heights[r.footprint_mask],
                s=2,
                cmap="terrain",
            )
            a.set_aspect("equal")
            a.invert_yaxis()
            a.grid()
            a.set_title(label)
        f.colorbar(mesh, ax=axes, label="Roof NAVD88 metres")
        f.suptitle(
            f"{name} — floor source {b.source_base:.2f}m; roof max {b.source_max:.2f}m"
        )
        f.savefig(output / f"{name}-metric-roof.png", dpi=130)
        plt.close(f)
        polys = (
            list(b.footprint.geoms) if hasattr(b.footprint, "geoms") else [b.footprint]
        )
        local_polys = [
            np.column_stack(
                (
                    (np.array(p.exterior.coords) - origin) @ axis,
                    (np.array(p.exterior.coords) - origin) @ normal,
                )
            )
            .round(3)
            .tolist()
            for p in polys
        ]
        records[name] = {
            "parent_id": parent,
            "origin_xz_m": origin.tolist(),
            "axis_degrees": math.degrees(math.atan2(axis[1], axis[0])),
            "source_base_navd88_m": b.source_base,
            "source_max_navd88_m": b.source_max,
            "polygons_uv_m": local_polys,
        }
    write_json(output / "root-building-metric-geometry.json", records)
    print(
        json.dumps(
            {
                k: {
                    a: v[a]
                    for a in [
                        "origin_xz_m",
                        "axis_degrees",
                        "source_base_navd88_m",
                        "source_max_navd88_m",
                    ]
                }
                for k, v in records.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
