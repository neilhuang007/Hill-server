"""Survey every assembled column, keeping exterior defects separate from buildings."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union

from campus_export_parity import read_archive
from campus_study_io import digest, write_json
from build_hill_chapel_sample import terrain_arrays

ROOT = Path(__file__).resolve().parents[1]
SITE = {"terrain", "pavement"}


def clusters(mask, xmin, zmin, limit=100):
    components, count = label(mask)
    sizes = np.bincount(components.ravel())
    order = sorted(range(1, count + 1), key=lambda n: int(sizes[n]), reverse=True)
    rows = []
    for number in order[:limit]:
        zz, xx = np.where(components == number)
        rows.append({"columns": len(xx), "bounds_xz_blocks":
                     [int(xx.min() + xmin), int(zz.min() + zmin),
                      int(xx.max() + xmin + 1), int(zz.max() + zmin + 1)],
                     "example_xz_blocks": [int(xx[0] + xmin), int(zz[0] + zmin)]})
    return {"columns": int(mask.sum()), "clusters": count, "largest": rows}


def survey(directory, output):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    profile = json.loads((directory / "profile.json").read_text(encoding="utf-8"))
    xmin, zmin, xmax, zmax = manifest["bounds_xz_blocks"]
    bounds = (zmax - zmin, xmax - xmin)
    base = manifest["terrain_base_y"]
    ground = np.full(bounds, -320, np.int16)
    ground_half = np.zeros(bounds, np.uint8)
    terrain_gaps = np.zeros(bounds, np.int16)
    minimum = np.full(bounds, 320, np.int16)
    architecture = np.zeros(bounds, bool)
    surface = np.zeros(bounds, np.uint16)
    palette = ["minecraft:air"]
    site_roles = np.zeros(bounds, np.uint8)
    materials = Counter()
    hashes = []
    for specification in manifest["tiles"]:
        tile = directory / specification["path"]
        archive_path = tile / "sample-blocks.npz"
        a = read_archive(archive_path)
        coords, roles, states = a["coords"], a["role_ids"], a["state_ids"]
        names = a["role_names"]
        tx, tz = int(coords[:, 0].min()), int(coords[:, 2].min())
        w, h = int(coords[:, 0].max()) - tx + 1, int(coords[:, 2].max()) - tz + 1
        x, y, z = coords[:, 0] - tx, coords[:, 1], coords[:, 2] - tz
        site = np.isin(roles, [names.index(n) for n in SITE])
        arch = ~np.isin(roles, [names.index(n) for n in (*SITE, "air", "vegetation")])
        local_g = np.full((h, w), -320, np.int16)
        np.maximum.at(local_g, (z[site], x[site]), y[site])
        local_min = np.full((h, w), 320, np.int16)
        np.minimum.at(local_min, (z, x), y)
        local_arch = np.zeros((h, w), bool)
        local_arch[z[arch], x[arch]] = True
        below = (y <= local_g[z, x]) & (y >= base)
        filled = np.zeros((h, w), np.int16)
        np.add.at(filled, (z[below], x[below]), 1)
        gaps = np.maximum(0, local_g - base + 1 - filled)
        top = site & (y == local_g[z, x])
        local_surface = np.zeros((h, w), np.uint16)
        local_half = np.zeros((h, w), np.uint8)
        local_role = np.zeros((h, w), np.uint8)
        mapping, halves = [], []
        for name, props in a["palette_keys"]:
            if name not in palette:
                palette.append(name)
            mapping.append(palette.index(name))
            halves.append(int(name.endswith("_slab") and dict(props).get("type") == "bottom"))
        mapping, halves = np.array(mapping, np.uint16), np.array(halves, np.uint8)
        local_surface[z[top], x[top]] = mapping[states[top]]
        local_half[z[top], x[top]] = halves[states[top]]
        local_role[z[top], x[top]] = roles[top]
        dst = (slice(tz - zmin, tz - zmin + h), slice(tx - xmin, tx - xmin + w))
        ground[dst], ground_half[dst] = local_g, local_half
        minimum[dst], architecture[dst] = local_min, local_arch
        terrain_gaps[dst], surface[dst], site_roles[dst] = gaps, local_surface, local_role
        for state_id, count in zip(*np.unique(states, return_counts=True)):
            materials[a["palette_keys"][state_id][0]] += int(count)
        hashes.append({"path": str(archive_path), "sha256": digest(archive_path)})
        if len(hashes) % 8 == 0:
            print(f"Surveyed {len(hashes)}/{len(manifest['tiles'])} tiles", flush=True)
    elevations, source_materials, meta = terrain_arrays(ROOT / profile["terrain"], profile["blocks_per_metre"])
    expected = np.rint((elevations + profile["vertical_offset_m"]) * profile["blocks_per_metre"]) - 1
    quad = np.zeros(bounds, bool)
    if manifest.get("landscape"):
        land = json.loads((directory / "landscape-profile.json").read_text(encoding="utf-8"))
        shapes = [shape(land["lawn"]["outer_polygon_xz"])]
        for group in ("paths", "planting_beds", "engineered_terraces", "steps_and_terraces"):
            shapes.extend(shape(p["polygon_xz"]) for p in land.get(group, []) if "polygon_xz" in p)
        zz, xx = np.indices(bounds)
        quad = contains_xy(unary_union(shapes).buffer(0.75), (xx + xmin + 0.5) / 2, (zz + zmin + 0.5) / 2)
    grass = surface == palette.index("minecraft:grass_block")
    source_pave = np.isin(source_materials, [meta["materials"][name]["id"] for name in ("path", "road", "parking") if name in meta["materials"]])
    grass_paving = grass & source_pave & ~architecture & ~quad
    # Missing volume beneath a site's own top is a physical hole. A depression
    # against bare-earth data alone is a candidate, not proof of a defect.
    report = {
        "format": "hill-demo-ground-survey-v1", "manifest_sha256": digest(directory / "manifest.json"),
        "bounds_xz_blocks": manifest["bounds_xz_blocks"], "columns": int(ground.size),
        "no_ground": clusters(ground == -320, xmin, zmin),
        "missing_shared_base": clusters(minimum != base, xmin, zmin),
        "subsurface_gap_columns": clusters(terrain_gaps > 0, xmin, zmin),
        "subsurface_missing_blocks": int(terrain_gaps.sum()),
        "exterior_subsurface_gap_columns": clusters((terrain_gaps > 0) & ~architecture, xmin, zmin),
        "exterior_depressions_over_1m": clusters((ground < expected - 2) & ~architecture, xmin, zmin),
        "grass_over_source_paving_candidates": clusters(grass_paving, xmin, zmin),
        "materials": dict(materials), "tiles": hashes,
        "scope": "Every tile archive and XZ column; the separate artifact audit binds archives to Anvil. Ground means terrain/pavement roles. Buildings and current Quad override older road geometry. Source paving candidates and DEM depressions require context before repair.",
    }
    np.savez_compressed(output / "surface-survey.npz", ground=ground, ground_half=ground_half,
                        minimum=minimum, terrain_gaps=terrain_gaps, architecture=architecture,
                        surface=surface, palette=np.asarray(palette), site_roles=site_roles,
                        expected=expected.astype(np.int16), source_materials=source_materials,
                        quad=quad, grass_paving=grass_paving, bounds=np.asarray(manifest["bounds_xz_blocks"]))
    write_json(output / "ground-survey.json", report)
    colors = np.zeros((len(palette), 3), np.uint8)
    for i, name in enumerate(palette):
        colors[i] = (166, 164, 155)
        if name == "minecraft:air": colors[i] = (240, 40, 60)
        elif "grass" in name: colors[i] = (95, 137, 76)
        elif "dirt" in name: colors[i] = (119, 92, 59)
        elif "water" in name: colors[i] = (75, 135, 178)
        elif "brick" in name and "stone" not in name: colors[i] = (159, 84, 67)
        elif any(s in name for s in ("gray_concrete", "andesite", "gray_wool")): colors[i] = (98, 101, 104)
        elif "smooth_stone" in name: colors[i] = (209, 205, 192)
    pixels = colors[surface]
    pixels[architecture] = (218, 202, 170)
    pixels[terrain_gaps > 0] = (236, 38, 60)
    overview = Image.fromarray(pixels)
    overview.save(output / "campus-ground-plan.png")
    crop = (-260, -280, 460, 360)
    core = overview.crop((crop[0] - xmin, crop[1] - zmin, crop[2] - xmin, crop[3] - zmin)).resize((1440, 1280))
    draw = ImageDraw.Draw(core)
    for x in range(-200, 461, 100):
        px = (x - crop[0]) * 2
        draw.line((px, 0, px, 1280), fill=(170, 179, 177), width=1)
        draw.text((px + 3, 3), f"X {x}", fill="black", stroke_fill="white", stroke_width=1)
    for z in range(-200, 361, 100):
        pz = (z - crop[1]) * 2
        draw.line((0, pz, 1440, pz), fill=(170, 179, 177), width=1)
        draw.text((3, pz + 3), f"Z {z}", fill="black", stroke_fill="white", stroke_width=1)
    core.save(output / "core-ground-plan.png")
    print(json.dumps({key: report[key] for key in ("columns", "subsurface_missing_blocks")}), flush=True)
    print(json.dumps({key: {k: report[key][k] for k in ("columns", "clusters")} for key in ("no_ground", "missing_shared_base", "subsurface_gap_columns", "exterior_depressions_over_1m", "grass_over_source_paving_candidates")}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    survey(args.directory, args.output)
