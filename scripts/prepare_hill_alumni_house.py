"""Extract the measured Alumni House envelope without changing source data."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from campus_roof_geometry import load_measured_building

ROOT = Path(__file__).resolve().parents[1]
PARENT = "1600151120011C-e738fb4171"
ORIGIN = np.array([-163.02960920497407, 107.35795784181792])
ANGLE = math.atan2(108.63787914770231 - ORIGIN[1], -154.5962610239275 - ORIGIN[0])
U = np.array([math.cos(ANGLE), math.sin(ANGLE)])
V = np.array([math.sin(ANGLE), -math.cos(ANGLE)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runtime/campus-reconstruction/alumni-house-preparation",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    building = load_measured_building(parent_id=PARENT)

    def local(p):
        d = np.array(p) - ORIGIN
        return [float(d @ U), float(d @ V)]

    faces = []
    for i, f in enumerate(building.roof_faces):
        rings = [f.polygon.exterior, *f.polygon.interiors]
        faces.append(
            {
                "index": i,
                "area_m2": f.polygon.area,
                "min_navd88_m": f.min_h,
                "max_navd88_m": f.max_h,
                "plane_xz": [f.a, f.b, f.c],
                "rings_uvh": [
                    [[*local(p), float(f.height_at(*p))] for p in ring.coords]
                    for ring in rings
                ],
            }
        )
    report = {
        "format": "hill-alumni-measured-v1",
        "parent_id": PARENT,
        "source_sha256": building.source_sha256,
        "attributes": dict(building.attrs),
        "origin_xz_m": ORIGIN.tolist(),
        "u_xz": U.tolist(),
        "v_xz": V.tolist(),
        "axis_degrees": math.degrees(ANGLE),
        "front": "V=0 is measured south porch lip; V increases toward rear/north",
        "floor_source_navd88_m": building.source_base,
        "source_max_navd88_m": building.source_max,
        "footprint_uv": [local(p) for p in building.footprint.exterior.coords],
        "terrain_bounds_xz_m": [-183, 67, -134, 130],
        "roof_faces": faces,
        "identity_evidence": "715 High Street; official Hill map #48; county parcel 160015112001",
        "uncertainty": "Roof planes are LiDAR reconstructions; window/porch details require photographs. Ground source is minimum footprint elevation, not finished floor.",
    }
    (args.output / "measured-envelope.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    fig, ax = plt.subplots(figsize=(7, 11))
    for f in faces:
        p = np.array(f["rings_uvh"][0])
        color = plt.cm.viridis(
            (f["max_navd88_m"] - building.source_base)
            / (building.source_max - building.source_base)
        )
        ax.add_patch(Polygon(p[:, :2], facecolor=color, edgecolor="white", linewidth=1))
        ax.text(*p[:-1, :2].mean(axis=0), str(f["index"]), ha="center", fontsize=9)
    p = np.array(report["footprint_uv"])
    ax.plot(*p.T, color="black", linewidth=1)
    ax.set_aspect("equal")
    ax.autoscale()
    ax.set_xlabel("U: across front toward east (m)")
    ax.set_ylabel("V: from porch toward rear (m)")
    ax.set_title(
        "Alumni House — measured roof planes\nNumbers refer to measured-envelope.json"
    )
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(args.output / "roof-plan.png", dpi=150)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "parent_id",
                    "origin_xz_m",
                    "axis_degrees",
                    "footprint_uv",
                    "floor_source_navd88_m",
                    "source_max_navd88_m",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
