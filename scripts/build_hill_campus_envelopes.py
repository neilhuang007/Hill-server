"""Place every resolved campus building before developing individual facades.

These are explicitly measured envelope studies, not photographically completed
buildings. No generic window grid is stamped over unrelated school buildings.
Each output retains its source identity, exact roof and individual gap audit.
"""

import argparse
import gc
import json
import math
from pathlib import Path

import numpy as np
from build_hill_chapel_sample import Canvas, build_ground, terrain_arrays
from campus_measured_shell import build_measured_shell
from campus_roof_geometry import load_measured_building, rasterize_roof
from campus_study_io import digest, finish_study, write_json

ROOT = Path(__file__).resolve().parents[1]


def material_proposal(numbers):
    """Broad aerial colour families; concealed facades remain provisional."""
    number = min(numbers)
    if number in {12, 13, 14}:
        return {
            "facade": "bricks",
            "foundation": "stone_bricks",
            "roof_family": "stone_brick",
        }
    if number == 9:
        return {
            "facade": "light_gray_concrete",
            "foundation": "bricks",
            "roof_family": "deepslate_tile",
            "upper_facade": "terracotta",
            "upper_from_floor_m": 10.5,
        }
    if number in {31, 32, 33, 34, 40}:
        return {
            "facade": "white_terracotta",
            "foundation": "bricks",
            "roof_family": "deepslate_tile",
            "lower_facade": "bricks",
            "lower_above_floor_m": 3.0,
        }
    if number in {41, 42, 43, 44}:
        return {
            "facade": "birch_planks",
            "foundation": "mud_bricks",
            "roof_family": "stone_brick",
            "lower_facade": "mud_bricks",
            "lower_above_floor_m": 3.0,
        }
    if number in {1, 7, 45, 46, 47, 51}:
        return {
            "facade": "mud_bricks",
            "foundation": "stone_bricks",
            "roof_family": "stone_brick",
        }
    return {
        "facade": "bricks",
        "foundation": "stone_bricks",
        "roof_family": "stone_brick",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--terrain",
        type=Path,
        default=ROOT
        / "runtime/campus-reconstruction/campus-complete-preparation/terrain.npz",
    )
    parser.add_argument(
        "--identities",
        type=Path,
        default=ROOT / "server-assets/hill-campus-building-identities.json",
    )
    parser.add_argument(
        "--developed-config",
        type=Path,
        default=ROOT / "server-assets/hill-campus-context-quad-review.json",
    )
    parser.add_argument("--material-source-config", type=Path,
                        help="Explicitly migrate the reviewed materials of these archived studies.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    identities = json.loads(args.identities.read_text(encoding="utf-8"))
    developed = json.loads(args.developed_config.read_text(encoding="utf-8"))
    material_sources = {}
    if args.material_source_config:
        source_config = json.loads(args.material_source_config.read_text(encoding="utf-8"))
        for spec in source_config["components"]:
            source_study = ROOT / spec["study"]
            source_profile = json.loads((source_study / "profile.json").read_text(encoding="utf-8"))
            if source_profile.get("parent_id"):
                material_sources[source_profile["parent_id"]] = digest(source_study / "sample-blocks.npz")
    built = set()
    for spec in developed["components"]:
        p = json.loads(
            (ROOT / spec["study"] / "profile.json").read_text(encoding="utf-8")
        )
        parent = p.get("parent_id")
        if not parent:
            parent = next(
                r["roofer_parent_id"]
                for r in identities["buildings"]
                if r["name"] == spec["name"]
            )
        built.add(parent)
    grouped = {}
    for r in identities["buildings"]:
        if r.get("roofer_parent_id"):
            grouped.setdefault(r["roofer_parent_id"], []).append(r)
    components, source_shapes, reports = [], {}, []
    for parent, records in grouped.items():
        b = load_measured_building(parent_id=parent)
        source_shapes[parent] = b.footprint
        if parent in built:
            continue
        numbers = sorted({r["school_map_number"] for r in records})
        names = [r["name"] for r in records]
        name = " / ".join(names)
        output = args.output / parent
        relative = output.resolve().relative_to(ROOT).as_posix()
        components.append(
            {
                "name": name,
                "study": relative,
                "margin_m": 0.5,
                "detail_status": "measured_envelope",
            }
        )
        if (output / "manifest.json").exists():
            reports.append(
                {
                    "parent_id": parent,
                    "names": names,
                    "study": relative,
                    "status": "existing_envelope",
                }
            )
            continue
        print(f"Building measured envelope: {name}", flush=True)
        bx0, bz0, bx1, bz1 = b.footprint.bounds
        x0, z0 = math.floor((bx0 - 3) / 8) * 8, math.floor((bz0 - 3) / 8) * 8
        x1, z1 = math.ceil((bx1 + 3) / 8) * 8, math.ceil((bz1 + 3) / 8) * 8
        h, materials, meta = terrain_arrays(args.terrain, 2, (x0, z0, x1, z1))
        c = Canvas(x0 * 2, z0 * 2, (x1 - x0) * 2, (z1 - z0) * 2, 2)
        build_ground(c, h, materials, meta["materials"], -25)
        p = {
            "name": "Hill — " + name,
            "revision": "2026-09-07-measured-envelope-2-native-half-metre-ground",
            "parent_id": parent,
            "school_names": names,
            "school_map_numbers": numbers,
            "blocks_per_metre": 2,
            "vertical_offset_m": -25,
            "detail_status": "Measured roof and footprint; facade openings and architectural detail await individual photographic studies.",
            "materials": material_proposal(numbers),
            "evidence": {
                "identity_file": str(args.identities),
                "identity_sha256": digest(args.identities),
                "roof_source_sha256": b.source_sha256,
                "aerial": "runtime/research/campus-priority-20260905/campus-2026-aerial-original.jpg",
            },
            "uncertainties": [
                "This is an envelope placement, not a completed facade replica.",
                "Construction palette colours are provisional aerial interpretations with original Minecraft textures.",
                "All source roof parts retain their measured coordinates, with one common scale/datum. No per-building position fitting.",
            ],
        }
        if parent in material_sources:
            p["material_assignment_source_sha256"] = material_sources[parent]
        r = rasterize_roof(b, (x0, z0, x1, z1), resolution=0.5)
        if r.missing_mask.any():
            raise ValueError(f"Roof source missing inside {name}: {r.coverage_report}")
        shell = build_measured_shell(
            c,
            b,
            r,
            vertical_offset=-25,
            facade=p["materials"]["facade"],
            foundation=p["materials"]["foundation"],
            roof_family=p["materials"]["roof_family"],
            roof_backing_metres=0.4,
        )
        from build_hill_chapel_sample import ROLES

        for direction, key, delta in (
            ("lower", "lower_facade", "lower_above_floor_m"),
            ("upper", "upper_facade", "upper_from_floor_m"),
        ):
            if key not in p["materials"]:
                continue
            split = round((b.source_base + p["materials"][delta] - 25) * 2) + 64
            region = (
                slice(shell.floor_y + 65, split)
                if direction == "lower"
                else slice(split, 384)
            )
            data, roles = c.data[region], c.roles[region]
            data[roles == ROLES.index("facade")] = c.state(p["materials"][key])
        center = b.footprint.centroid
        distance = max(bx1 - bx0, bz1 - bz0) * 1.1 + 10
        cameras = [
            {
                "name": "measured-envelope",
                "eye": [
                    (center.x - distance * 0.5) * 2,
                    (b.source_max + distance * 0.5 - 25) * 2,
                    (center.y + distance) * 2,
                ],
                "target": [center.x * 2, (b.source_base + 5 - 25) * 2, center.y * 2],
                "fov": 68,
            }
        ]
        manifest = finish_study(
            c,
            p,
            output,
            cameras,
            {
                "source_roof": shell.to_manifest(),
                "roof_coverage": r.coverage_report,
                "terrain": {"path": str(args.terrain), "sha256": digest(args.terrain)},
            },
        )
        reports.append(
            {
                "parent_id": parent,
                "names": names,
                "study": relative,
                "block_count": manifest["block_count"],
                "status": "measured_envelope",
            }
        )
        del c, r, h, shell
        gc.collect()
    gaps = []
    keys = list(source_shapes)
    for i, parent in enumerate(keys):
        for other in keys[i + 1 :]:
            a, b = source_shapes[parent], source_shapes[other]
            distance = a.distance(b)
            if distance < 10:
                gaps.append(
                    {
                        "parents": [parent, other],
                        "measured_gap_m": distance,
                        "gap_at_2_blocks_per_metre": distance * 2,
                        "intersection_m2": a.intersection(b).area,
                    }
                )
    if any(r["intersection_m2"] > 0.05 for r in gaps):
        raise ValueError("Source building footprints overlap; resolve before assembly")
    write_json(args.output / "components.json", components)
    write_json(
        args.output / "coverage.json",
        {
            "resolved_named_footprints": len(grouped),
            "developed_footprints": len(built),
            "new_envelopes": reports,
            "nearby_building_gaps": gaps,
            "unresolved": identities.get("unresolved", []),
            "scope": "Named official-map structures with individually resolved county footprints; envelope coverage is separate from facade completion.",
        },
    )
    print(
        json.dumps(
            {
                "new_envelopes": len(components),
                "total_named_footprints": len(grouped),
                "output": str(args.output),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
