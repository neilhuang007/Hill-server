"""Compare labelled architectural photo samples with ORIGINAL client textures.

The shortlist is material-family constrained. JPEG pixels are observations under
unknown lighting, never intrinsic reflectance. No nearest-colour result is
automatically applied to a building. The native comparison and reviewed role map
are separate, explicit steps.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.color import deltaE_ciede2000, rgb2lab

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JAR = Path.home() / "AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar"
DEFAULT_OUTPUT = ROOT / "runtime/research/campus-material-audit-20260905"

# A texture family is an admissible VISUAL representation, not a claim the real
# building is made from that Minecraft material. No ores, sculk or custom assets.
FAMILIES = {
    "coursed_masonry": [
        "stone_bricks", "mossy_stone_bricks", "cracked_stone_bricks",
        "tuff_bricks", "polished_tuff", "mud_bricks", "bricks",
        "polished_andesite", "polished_granite", "quartz_bricks",
    ],
    "rough_stone": [
        "stone", "cobblestone", "mossy_cobblestone", "tuff", "andesite",
        "granite", "diorite", "calcite", "polished_tuff",
    ],
    "pale_cut_stone": [
        "calcite", "quartz_block", "smooth_quartz", "quartz_bricks",
        "quartz_pillar", "polished_diorite", "diorite", "smooth_stone",
        "white_concrete", "light_gray_concrete", "white_terracotta",
    ],
    "brick": ["bricks", "mud_bricks", "terracotta", "red_terracotta", "brown_terracotta"],
    "slate_shingle": [
        "stone_bricks", "deepslate_tiles", "deepslate_bricks", "polished_deepslate",
        "cobbled_deepslate", "gray_concrete", "tuff_bricks", "stone",
    ],
    "clapboard_timber": [
        "birch_planks", "oak_planks", "spruce_planks", "dark_oak_planks",
        "jungle_planks", "acacia_planks", "mangrove_planks", "cherry_planks",
        "bamboo_planks", "pale_oak_planks",
        "stripped_birch_log", "stripped_oak_log", "stripped_spruce_log",
        "stripped_dark_oak_log", "stripped_jungle_log", "stripped_pale_oak_log",
    ],
    "metal": [
        "iron_block", "waxed_copper_block", "waxed_cut_copper",
        "waxed_exposed_copper", "waxed_exposed_cut_copper",
        "waxed_weathered_copper", "waxed_weathered_cut_copper",
        "waxed_oxidized_copper", "waxed_oxidized_cut_copper",
    ],
}
COLOURS = [
    "white", "light_gray", "gray", "black", "brown", "red", "orange",
    "yellow", "lime", "green", "cyan", "light_blue", "blue", "purple", "magenta", "pink",
]
FAMILIES["terracotta_finish"] = ["terracotta"] + [f"{c}_terracotta" for c in COLOURS]
FAMILIES["concrete_finish"] = [f"{c}_concrete" for c in COLOURS]

SHAPE_STEMS = {
    "bricks": "brick", "stone_bricks": "stone_brick", "mud_bricks": "mud_brick",
    "mossy_stone_bricks": "mossy_stone_brick", "tuff_bricks": "tuff_brick",
    "deepslate_tiles": "deepslate_tile", "deepslate_bricks": "deepslate_brick",
    "quartz_block": "quartz", "quartz_bricks": "quartz", "quartz_pillar": "quartz",
}


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get_model_texture(jar, block):
    """Resolve the actual blockstate model, including waxed-model aliases."""
    state = json.loads(jar.read(f"assets/minecraft/blockstates/{block}.json"))
    if "variants" in state:
        choices = state["variants"]
        key = "axis=y" if "axis=y" in choices else next(iter(choices))
        model = choices[key]
        if isinstance(model, list):
            model = model[0]
    else:
        model = state["multipart"][0]["apply"]
        if isinstance(model, list):
            model = model[0]
    model = model["model"]
    textures = {}
    visited = set()
    while model and model not in visited:
        visited.add(model)
        ns, name = model.split(":") if ":" in model else ("minecraft", model)
        record = json.loads(jar.read(f"assets/{ns}/models/{name}.json"))
        textures = {**record.get("textures", {}), **textures}
        model = record.get("parent")
        if model and model.startswith("builtin/"):
            break
    texture = next((textures[k] for k in ("side", "all", "texture", "top", "end") if k in textures), None)
    if texture is None:
        raise ValueError(f"No representative texture: {block}: {textures}")
    while texture.startswith("#"):
        texture = textures[texture[1:]]
    ns, name = texture.split(":") if ":" in texture else ("minecraft", texture)
    path = f"assets/{ns}/textures/{name}.png"
    raw = jar.read(path)
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    # Animated textures use their first complete frame; all curated solid
    # architectural texture candidates currently have a static square texture.
    im = im.crop((0, 0, im.width, im.width))
    return im, path, hashlib.sha256(raw).hexdigest()


def colour_stats(im):
    rgb = np.asarray(im.convert("RGB"), dtype=np.float64) / 255
    pixels = rgb.reshape(-1, 3)
    linear = np.where(pixels <= 0.04045, pixels / 12.92, ((pixels + 0.055) / 1.055) ** 2.4)
    mean_linear = linear.mean(axis=0)
    mean = np.where(mean_linear <= 0.0031308, mean_linear * 12.92,
                    1.055 * mean_linear ** (1 / 2.4) - 0.055)
    median = np.median(pixels, axis=0)
    return {
        "pixels": int(pixels.shape[0]),
        "srgb_median": (median * 255).round(2).tolist(),
        "srgb_mean_linear_light": (mean * 255).round(2).tolist(),
        "srgb_p10_p90": (np.percentile(pixels, [10, 90], axis=0) * 255).round(2).tolist(),
        "lab_d65_median": rgb2lab(median.reshape(1, 1, 3))[0, 0].round(4).tolist(),
        "lab_d65_linear_mean": rgb2lab(mean.reshape(1, 1, 3))[0, 0].round(4).tolist(),
        "lab_pixel_std": rgb2lab(rgb).reshape(-1, 3).std(axis=0).round(4).tolist(),
    }


def font(size):
    return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)


def texture_contact(catalogue, images, output):
    for family, names in FAMILIES.items():
        cell_w, cell_h, cols = 240, 222, 5
        rows = (len(names) + cols - 1) // cols
        out = Image.new("RGB", (cell_w * cols, rows * cell_h + 75), "#f0f0ed")
        draw = ImageDraw.Draw(out)
        draw.text((20, 14), family.replace("_", " "), fill="black", font=font(27))
        draw.text((20, 47), "Original Minecraft 26.1.2 textures, nearest-neighbour enlargement", fill="#555555", font=font(16))
        for i, name in enumerate(names):
            x, y = (i % cols) * cell_w + 16, (i // cols) * cell_h + 82
            im = images[name]
            # Four blocks wide: visible bond/course frequency at 2 blocks/metre.
            tiled = np.tile(np.asarray(im), (4, 4, 1))
            out.paste(Image.fromarray(tiled).resize((196, 144), Image.Resampling.NEAREST), (x, y))
            for line, label in enumerate([name.removeprefix("waxed_"), "RGB " + str(catalogue[name]["statistics"]["srgb_mean_linear_light"])]):
                draw.text((x, y + 150 + line * 20), label, fill="#222222", font=font(14))
        out.save(output / f"candidates-{family}.jpg", quality=95)


def load_samples(paths):
    samples = []
    for path in paths:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        for sample in doc["samples"]:
            samples.append({**sample, "sample_register": str(path)})
    return samples


def compare(samples, catalogue, output):
    results = []
    for sample in samples:
        path = ROOT / sample["file"]
        if "file_sha256" in sample and digest(path) != sample["file_sha256"]:
            raise ValueError(f"Changed source image: {path}")
        im = Image.open(path).convert("RGB")
        rect = sample["rectangle_pixels_xyxy"]
        if not (0 <= rect[0] < rect[2] <= im.width and 0 <= rect[1] < rect[3] <= im.height):
            raise ValueError(f"Invalid crop for {sample['id']}: {rect}, {im.size}")
        crop = im.crop(rect)
        statistics = colour_stats(crop)
        ref = np.array(statistics["lab_d65_linear_mean"])
        admitted = sample.get("candidate_families", list(FAMILIES))
        eligible = set(n for f in admitted for n in FAMILIES[f])
        ranking = []
        for name in sorted(eligible):
            candidate = catalogue[name]
            lab = np.array(candidate["statistics"]["lab_d65_linear_mean"])
            # Raw deltaE includes lighting. The diagnostic with matched L*
            # isolates colour bias, not an inferred exposure correction.
            matched = lab.copy()
            matched[0] = ref[0]
            ranking.append({
                "block": name,
                "delta_e_2000_raw": round(float(deltaE_ciede2000(ref, lab)), 3),
                "delta_e_2000_equal_lightness": round(float(deltaE_ciede2000(ref, matched)), 3),
                "delta_l_star": round(float(lab[0] - ref[0]), 3),
            })
        ranking.sort(key=lambda r: r["delta_e_2000_raw"])
        results.append({**sample, "statistics": statistics, "candidate_families": admitted,
                        "ranking": ranking, "decision": "manual material-pattern and native-lighting review required"})
    write_json(output / "photo-texture-comparison.json", {"method": "CIELAB D65, CIEDE2000; original PNG linear-light average versus labelled JPEG ROI linear-light average. Equal-L* diagnostic is not reflectance calibration.", "samples": results})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, default=DEFAULT_JAR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples", type=Path, action="append", default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    catalogue, images = {}, {}
    with ZipFile(args.jar) as jar:
        members = set(jar.namelist())
        for family, names in FAMILIES.items():
            for name in names:
                if name in catalogue:
                    catalogue[name]["families"].append(family)
                    continue
                im, texture_path, sha = get_model_texture(jar, name)
                stem = SHAPE_STEMS.get(name, name.removesuffix("_planks"))
                variants = [f"{stem}_{part}" for part in ("stairs", "slab", "wall")
                            if f"assets/minecraft/blockstates/{stem}_{part}.json" in members]
                images[name] = im
                catalogue[name] = {"block": f"minecraft:{name}", "families": [family],
                                   "texture": texture_path, "texture_sha256": sha,
                                   "statistics": colour_stats(im), "shape_variants": variants}
    write_json(args.output / "vanilla-construction-candidates.json", {
        "client_jar": str(args.jar), "client_jar_sha256": digest(args.jar),
        "scale_blocks_per_metre": 2,
        "selection_policy": "Role and documented/observed material family before colour. Sandstone withdrawn from current building substitutes. Vines and moss only where observed, not random full-wall noise. No automatic substitutions.",
        "families": FAMILIES, "candidates": catalogue,
    })
    texture_contact(catalogue, images, args.output)
    comparisons = compare(load_samples(args.samples), catalogue, args.output) if args.samples else []
    print(json.dumps({"output": str(args.output), "candidate_count": len(catalogue), "photo_samples": len(comparisons)}))


if __name__ == "__main__":
    main()
