"""Combine physical-coordinate studies over measured terrain, one tile at a time.

Each component owns architectural columns, enclosed courts and a narrow site
margin. Copying air above its foundation preserves hollow rooms, recessed
windows and open arcades. Terrain outside that ownership stays continuous.
Every tile retains its block archive and independently checked Anvil export.
"""

import argparse
import gc
import json
import math
import shutil
from collections import Counter
from pathlib import Path

import hybridize_voxelearth_roofer_world as anvil
import numpy as np
from build_hill_chapel_sample import ROLES, Canvas, terrain_arrays, write_world
from campus_export_parity import compare_world, read_archive
from campus_materials import audit_role_materials
from campus_paving import smooth_exposed_measured_pavement
from campus_quad_landscape import build_quad_landscape
from campus_revision_reuse import ReusableAssembly
from campus_study_io import digest, material_roles, write_json
from scipy.ndimage import binary_dilation, binary_fill_holes

ROOT = Path(__file__).resolve().parents[1]


def site_local_coordinates(profile, x, z):
    """Use the authored building frame, including the Chapel's older sign convention."""
    geometry = profile["geometry"]
    if "origin_xz_m" in geometry and "axis_degrees" in geometry:
        origin = geometry["origin_xz_m"]
        angle = math.radians(geometry["axis_degrees"])
    elif "rotation_degrees" in geometry and "nave_half_width_m" in geometry:
        # Chapel.xyz uses x=cos(a)*u+sin(a)*v, z=-sin(a)*u+cos(a)*v.
        origin = (0, 0)
        angle = math.radians(-geometry["rotation_degrees"])
    else:
        raise ValueError("Explicit site bounds require a recognized building frame")
    dx, dz = x - origin[0], z - origin[1]
    return dx * math.cos(angle) + dz * math.sin(angle), -dx * math.sin(angle) + dz * math.cos(angle)


def prepare_component(study, cache_root, scale, offset, margin_m=2.0):
    study = Path(study)
    manifest = json.loads((study / "manifest.json").read_text(encoding="utf-8"))
    profile = json.loads((study / "profile.json").read_text(encoding="utf-8"))
    source_scale = manifest["blocks_per_metre"]
    source_offset = manifest.get("vertical_offset_m", profile.get("vertical_offset_m"))
    if source_offset is None:
        # Alumni v3 stores the frame in its reference profile geometry.
        source_offset = profile.get("navd88_to_world_y_offset_m")
    if source_scale != scale or source_offset != offset:
        raise ValueError(
            f"Component frame mismatch: {study}: {source_scale}, {source_offset}"
        )
    source_hash = digest(study / "sample-blocks.npz")
    identity = {
        "archive_sha256": source_hash,
        "margin_m": margin_m,
        "scale": scale,
        "offset": offset,
        "format": 2,
        "site_bounds_uv_m": profile.get("assembly_site_bounds_uv_m", []),
    }
    key = (
        __import__("hashlib")
        .sha256(json.dumps(identity, sort_keys=True).encode())
        .hexdigest()[:20]
    )
    target = Path(cache_root) / key
    if (target / "metadata.json").exists():
        return Component(target)
    target.mkdir(parents=True, exist_ok=False)
    archive = read_archive(study / "sample-blocks.npz")
    coords = archive["coords"]
    x0, _, z0 = coords.min(axis=0)
    x1, _, z1 = coords.max(axis=0) + 1
    shape = (384, int(z1 - z0), int(x1 - x0))
    data = np.lib.format.open_memmap(
        target / "data.npy", mode="w+", dtype=np.uint16, shape=shape
    )
    roles = np.lib.format.open_memmap(
        target / "roles.npy", mode="w+", dtype=np.uint8, shape=shape
    )
    data[:] = 0
    roles[:] = 0
    minimum = np.full(shape[1:], 320, dtype=np.int16)
    mask = np.zeros(shape[1:], dtype=bool)
    role_map = np.array(
        [ROLES.index(name) for name in archive["role_names"]], dtype=np.uint8
    )
    excluded = {ROLES.index(name) for name in ("air", "terrain", "pavement")}
    for start in range(0, len(coords), 500_000):
        sl = slice(start, start + 500_000)
        x, y, z = (coords[sl] - [x0, -64, z0]).T
        if y.min() < 0 or y.max() >= 384:
            raise ValueError("Component exceeds vanilla height")
        role = role_map[archive["role_ids"][sl]]
        data[y, z, x] = archive["state_ids"][sl]
        roles[y, z, x] = role
        np.minimum.at(minimum, (z, x), coords[sl, 1])
        selected = ~np.isin(role, list(excluded))
        mask[z[selected], x[selected]] = True
    # Fill enclosed rooms and courts before and after the narrow margin joins
    # near-touching covered walkways. Open exterior surroundings stay unowned.
    mask = binary_fill_holes(mask)
    if profile.get("assembly_site_bounds_uv_m"):
        zz, xx = np.indices(mask.shape)
        u, v = site_local_coordinates(profile, (xx + x0 + 0.5) / scale, (zz + z0 + 0.5) / scale)
        for u0, v0, u1, v1 in profile["assembly_site_bounds_uv_m"]:
            mask |= (u >= u0) & (u < u1) & (v >= v0) & (v < v1)
    mask = binary_dilation(mask, iterations=max(1, math.ceil(margin_m * scale)))
    mask = binary_fill_holes(mask)
    if (mask & (minimum == 320)).any():
        raise ValueError("Component ownership includes columns without a foundation")
    data.flush()
    roles.flush()
    np.save(target / "mask.npy", mask)
    np.save(target / "minimum_y.npy", minimum)
    palette = [
        {"Name": key[0], **({"Properties": dict(key[1])} if key[1] else {})}
        for key in archive["palette_keys"]
    ]
    write_json(
        target / "metadata.json",
        {
            **identity,
            "study": str(study.resolve()),
            "x_min": int(x0),
            "z_min": int(z0),
            "shape": shape,
            "palette": palette,
            "owned_columns": int(mask.sum()),
        },
    )
    del archive, coords, data, roles
    gc.collect()
    return Component(target)


class Component:
    def __init__(self, path):
        self.path = Path(path)
        self.meta = json.loads((self.path / "metadata.json").read_text())
        self.data = np.load(self.path / "data.npy", mmap_mode="r")
        self.roles = np.load(self.path / "roles.npy", mmap_mode="r")
        self.mask = np.load(self.path / "mask.npy", mmap_mode="r")
        self.minimum = np.load(self.path / "minimum_y.npy", mmap_mode="r")

    def paste(self, canvas, owners, number):
        x0, z0 = self.meta["x_min"], self.meta["z_min"]
        left, top = max(x0, canvas.x_min), max(z0, canvas.z_min)
        right = min(x0 + self.data.shape[2], canvas.x_min + canvas.data.shape[2])
        bottom = min(z0 + self.data.shape[1], canvas.z_min + canvas.data.shape[1])
        if left >= right or top >= bottom:
            return 0
        src = (slice(top - z0, bottom - z0), slice(left - x0, right - x0))
        dst = (
            slice(top - canvas.z_min, bottom - canvas.z_min),
            slice(left - canvas.x_min, right - canvas.x_min),
        )
        mask = self.mask[src]
        if not mask.any():
            return 0
        owner_view = owners[dst]
        if np.any(mask & (owner_view != 0)):
            raise ValueError(
                f"Overlapping building ownership at {left},{top}: {self.meta['study']}"
            )
        owner_view[mask] = number
        mapping = np.array(
            [
                canvas.state(p["Name"], p.get("Properties"))
                for p in self.meta["palette"]
            ],
            dtype=np.uint16,
        )
        source_data = self.data[(slice(None),) + src]
        source_roles = self.roles[(slice(None),) + src]
        target_data = canvas.data[(slice(None),) + dst]
        target_roles = canvas.roles[(slice(None),) + dst]
        minimum = self.minimum[src]
        for y in range(384):
            selected = mask & (y - 64 >= minimum)
            target_data[y, selected] = mapping[source_data[y, selected]]
            target_roles[y, selected] = source_roles[y, selected]
        return int(mask.sum())


def audit_component_ownership(components, x_min, z_min, shape):
    """Reject overlap/clipping before exporting any of the campus tiles."""
    owners = np.zeros(shape, dtype=np.uint16)
    rows = []
    for number, component in enumerate(components, 1):
        x0, z0 = component.meta["x_min"], component.meta["z_min"]
        left, top = max(x0, x_min), max(z0, z_min)
        right = min(x0 + component.mask.shape[1], x_min + shape[1])
        bottom = min(z0 + component.mask.shape[0], z_min + shape[0])
        total = int(component.mask.sum())
        if left >= right or top >= bottom:
            raise ValueError(f"Building ownership outside campus: {component.meta['study']}")
        selected = component.mask[top - z0:bottom - z0, left - x0:right - x0]
        if int(selected.sum()) != total:
            raise ValueError(f"Building ownership clipped by campus: {component.meta['study']}")
        target = owners[top - z_min:bottom - z_min, left - x_min:right - x_min]
        overlap = selected & (target != 0)
        if overlap.any():
            previous = [components[int(i) - 1].meta["study"] for i in np.unique(target[overlap])]
            raise ValueError(f"Overlapping building ownership: {component.meta['study']}; {previous}; {int(overlap.sum())} columns")
        target[selected] = number
        rows.append({
            "study": component.meta["study"],
            "archive_sha256": component.meta["archive_sha256"],
            "owned_columns": total,
            "translation_blocks": [0, 0, 0],
            "rotation_degrees": 0,
        })
    return {
        "format": "hill-campus-ownership-audit-v1",
        "passed": True,
        "overlapping_columns": 0,
        "clipped_owned_columns": 0,
        "owned_columns": int(np.count_nonzero(owners)),
        "components": rows,
        "scope": "All component masks occupy their original physical world coordinates, with no assembly translation or rotation. Margins reserve ground around architecture; this test does not establish the accuracy of the source footprints.",
    }


def ground_tile(canvas, elevations, ids, materials, offset, base):
    """A common basement prevents seams between independently generated tiles."""
    heights = np.rint((elevations + offset) * canvas.scale).astype(np.int16) - 1
    if base < -64 or heights.max() >= 319 or base > heights.min() - 4:
        raise ValueError("Invalid shared terrain build-height range")
    stone, dirt = canvas.state("stone"), canvas.state("dirt")
    palette = {int(m["id"]): m["minecraft_block"] for m in materials.values()}
    for iz, ix in np.ndindex(heights.shape):
        top = int(heights[iz, ix])
        canvas.data[base + 64 : top + 61, iz, ix] = stone
        canvas.data[top + 61 : top + 64, iz, ix] = dirt
        canvas.roles[base + 64 : top + 65, iz, ix] = ROLES.index("terrain")
        block = palette[int(ids[iz, ix])]
        canvas.data[top + 64, iz, ix] = canvas.state(block)
        if block not in {
            "minecraft:grass_block",
            "minecraft:dirt",
            "minecraft:water",
            "minecraft:coarse_dirt",
        }:
            canvas.roles[top + 64, iz, ix] = ROLES.index("pavement")
        if block == "minecraft:water":
            canvas.data[top + 62 : top + 65, iz, ix] = canvas.state(
                block, {"level": "0"}
            )
    canvas.ground_heights = heights


def merge_tile_world(tile_world, target_world, registered):
    """Copy exact chunk records; fail rather than silently overwrite a neighbor."""
    (target_world / "region").mkdir(parents=True, exist_ok=True)
    if not (target_world / "level.dat").exists():
        shutil.copyfile(tile_world / "level.dat", target_world / "level.dat")
    count = 0
    for path in sorted((tile_world / "region").glob("*.mca")):
        source = anvil.RegionEditor(path)
        target = anvil.RegionEditor(target_world / "region" / path.name)
        for index, record in source.raw_records.items():
            address = (path.name, index)
            if address in registered or index in target.raw_records:
                raise ValueError(f"Duplicate assembly chunk {address}")
            target.raw_records[index] = record
            target.modified.add(index)
            registered[address] = digest_bytes(record)
            count += 1
        target.save()
    return count


def digest_bytes(data):
    return __import__("hashlib").sha256(data).hexdigest()


def verify_merged_world(world, registered):
    actual = {}
    for path in sorted((world / "region").glob("*.mca")):
        for index, record in anvil.RegionEditor(path).raw_records.items():
            actual[(path.name, index)] = digest_bytes(record)
    if actual != registered:
        raise ValueError("Assembled chunk records differ from the checked tile exports")
    return len(actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "server-assets/hill-campus-context.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-from", type=Path,
                        help="Preserve unchanged tiles from an accepted audited campus; decode each copied tile again")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a fresh assembly revision")
    p = json.loads(args.config.read_text(encoding="utf-8"))
    if p.get("environment"):
        raise ValueError(
            "This revision includes a source-bound environment overlay. Rebuild it with "
            "refine_hill_campus_environment.py and its recorded base/plan; a plain assembly "
            "would discard the reviewed site repairs."
        )
    scale, offset = p["blocks_per_metre"], p["vertical_offset_m"]
    landscape = (
        json.loads((ROOT / p["landscape"]).read_text(encoding="utf-8"))
        if p.get("landscape")
        else None
    )
    components = []
    for spec in p["components"]:
        print(f"Preparing component {spec['name']}", flush=True)
        components.append(
            prepare_component(
                ROOT / spec["study"],
                ROOT / "runtime/campus-reconstruction/component-cache",
                scale,
                offset,
                spec.get("margin_m", 2),
            )
        )
        expected_hash = spec.get("source_archive_sha256")
        if expected_hash and components[-1].meta["archive_sha256"] != expected_hash:
            raise ValueError(f"Building changed after campus configuration was prepared: {spec['study']}")
        review = spec.get("native_review")
        if isinstance(review, dict):
            if digest(ROOT / review["path"]) != review["sha256"]:
                raise ValueError(f"Building native verdict changed: {spec['study']}")
    elevations, ids, meta = terrain_arrays(ROOT / p["terrain"], scale)
    xmin, zmin = meta["x_min"] * scale, meta["z_min"] * scale
    base = int(np.rint((elevations.min() + offset) * scale)) - 12 * scale
    tile_size = p.get("tile_size_blocks", 256)
    if (
        tile_size % 16
        or xmin % 16
        or zmin % 16
        or any(n % 16 for n in elevations.shape)
    ):
        raise ValueError("Assembly and tile boundaries must align to Minecraft chunks")
    args.output.mkdir(parents=True)
    ownership = audit_component_ownership(components, xmin, zmin, elevations.shape)
    reusable = ReusableAssembly(
        args.reuse_from, p, components, digest(ROOT / p["terrain"]),
        [xmin, zmin, xmin + elevations.shape[1], zmin + elevations.shape[0]],
        base, landscape,
    ) if args.reuse_from else None
    write_json(args.output / "ownership-audit.json", ownership)
    write_json(args.output / "profile.json", p)
    if landscape:
        write_json(args.output / "landscape-profile.json", landscape)
    cameras = [
        {
            **v,
            "eye": [
                v["eye_xz_navd88_m"][0] * scale,
                (v["eye_xz_navd88_m"][2] + offset) * scale,
                v["eye_xz_navd88_m"][1] * scale,
            ],
            "target": [
                v["target_xz_navd88_m"][0] * scale,
                (v["target_xz_navd88_m"][2] + offset) * scale,
                v["target_xz_navd88_m"][1] * scale,
            ],
        }
        for v in p["camera_views"]
    ]
    for view in cameras:
        if view.get("player_eye_height_blocks"):
            ix = math.floor(view["eye"][0]) - xmin
            iz = math.floor(view["eye"][2]) - zmin
            if not (0 <= iz < elevations.shape[0] and 0 <= ix < elevations.shape[1]):
                raise ValueError("Player view must stand on the assembled terrain")
            ground_y = round((float(elevations[iz, ix]) + offset) * scale)
            view["eye"][1] = ground_y + view["player_eye_height_blocks"]
    cameras = [
        {key: view[key] for key in ("name", "eye", "target", "fov")} for view in cameras
    ]
    write_json(
        args.output / "camera-views.json",
        {"format": "hill-native-camera-views-v1", "views": cameras},
    )
    write_json(
        args.output / "play-start.json",
        {"format": "hill-native-camera-views-v1", "views": cameras[1:2]},
    )
    totals, registered, tile_reports = Counter(), {}, []
    reused_tiles = []
    for z in range(0, elevations.shape[0], tile_size):
        for x in range(0, elevations.shape[1], tile_size):
            h = min(tile_size, elevations.shape[0] - z)
            w = min(tile_size, elevations.shape[1] - x)
            tile = args.output / "tiles" / f"x{xmin + x}_z{zmin + z}"
            candidate = reusable.candidate(
                tile.name, (xmin + x, zmin + z, xmin + x + w, zmin + z + h)
            ) if reusable else None
            if candidate:
                source_tile, report = candidate
                shutil.copytree(source_tile, tile)
                archive = read_archive(tile / "sample-blocks.npz")
                _, errors, _, _ = compare_world(archive, tile / "world")
                violations = audit_role_materials(report["material_roles"])
                if errors or violations:
                    raise ValueError({"reused_tile": tile.name, "parity": errors, "materials": violations})
                del archive
                gc.collect()
                chunks = merge_tile_world(tile / "world", args.output / "world", registered)
                totals.update(blocks=report["block_count"], chunks=chunks, tiles=1)
                tile_reports.append({
                    "path": str(tile.relative_to(args.output)),
                    "blocks": report["block_count"], "chunks": chunks,
                    "audit_sha256": digest(tile / "audit.json"),
                    "archive_sha256": digest(tile / "sample-blocks.npz"),
                })
                reused_tiles.append(tile.name)
                print(f"Reused and decoded {tile.name}; {totals['tiles']} verified tiles", flush=True)
                continue
            tile.mkdir(parents=True)
            print(f"Terrain and components {tile.name}", flush=True)
            c = Canvas(xmin + x, zmin + z, w, h, scale)
            elev = elevations[z : z + h, x : x + w]
            ground_tile(
                c, elev, ids[z : z + h, x : x + w], meta["materials"], offset, base
            )
            smooth_exposed_measured_pavement(
                c, elev, c.ground_heights, vertical_offset=offset
            )
            owners = np.zeros((h, w), dtype=np.uint8)
            counts = [
                component.paste(c, owners, i + 1)
                for i, component in enumerate(components)
            ]
            landscape_evidence = (
                build_quad_landscape(c, elev, landscape, offset) if landscape else None
            )
            roles = material_roles(c)
            violations = audit_role_materials(roles)
            if violations or c.clipped:
                raise ValueError(
                    {"tile": tile.name, "materials": violations, "clipped": c.clipped}
                )
            c.export(tile / "sample-blocks.npz")
            write_world(
                c,
                tile / "world",
                p["name"],
                tuple(round(v) for v in cameras[1]["eye"]),
                anvil.DEFAULT_SOURCE_WORLD / "level.dat",
            )
            del c, owners
            gc.collect()
            archive = read_archive(tile / "sample-blocks.npz")
            parity, errors, _, _ = compare_world(archive, tile / "world")
            if errors:
                raise ValueError({"tile": tile.name, "parity": errors})
            report = {
                "tile": tile.name,
                "block_count": len(archive["coords"]),
                "ownership_columns": counts,
                "parity": parity,
                "material_roles": roles,
                "landscape": landscape_evidence,
                "errors": [],
            }
            write_json(tile / "audit.json", report)
            del archive
            gc.collect()
            chunks = merge_tile_world(tile / "world", args.output / "world", registered)
            totals.update(blocks=report["block_count"], chunks=chunks, tiles=1)
            tile_reports.append(
                {
                    "path": str(tile.relative_to(args.output)),
                    "blocks": report["block_count"],
                    "chunks": chunks,
                    "audit_sha256": digest(tile / "audit.json"),
                    "archive_sha256": digest(tile / "sample-blocks.npz"),
                }
            )
            print(
                f"Verified {totals['tiles']} tiles; {totals['blocks']:,} blocks",
                flush=True,
            )
    verify_merged_world(args.output / "world", registered)
    manifest = {
        "format": "hill-campus-assembly-v1",
        "blocks_per_metre": scale,
        "vertical_offset_m": offset,
        "bounds_xz_blocks": [
            xmin,
            zmin,
            xmin + elevations.shape[1],
            zmin + elevations.shape[0],
        ],
        "terrain_base_y": base,
        "terrain": {"path": p["terrain"], "sha256": digest(ROOT / p["terrain"])},
        "profile": {
            "path": str((args.output / "profile.json").resolve()),
            "sha256": digest(args.output / "profile.json"),
        },
        "resource_pack": {
            "path": str((ROOT / p["resource_pack"]).resolve()),
            "files": {
                f.relative_to(ROOT / p["resource_pack"]).as_posix(): digest(f)
                for f in sorted((ROOT / p["resource_pack"]).rglob("*"))
                if f.is_file()
            },
        }
        if p.get("resource_pack")
        else None,
        "components": [component.meta for component in components],
        "ownership_audit": {
            "path": "ownership-audit.json",
            "sha256": digest(args.output / "ownership-audit.json"),
            "overlapping_columns": 0,
            "clipped_owned_columns": 0,
        },
        "landscape": {
            "path": str((args.output / "landscape-profile.json").resolve()),
            "source_profile": p["landscape"],
            "sha256": digest(args.output / "landscape-profile.json"),
        }
        if landscape
        else None,
        "totals": dict(totals),
        "tiles": tile_reports,
        "exact_export_audit": "pass: every tile archive decoded against Anvil; assembled raw chunk hashes equal checked tile records",
        "visual_review": "pending",
        "uncertainties": p["uncertainties"],
    }
    if reusable:
        manifest["tile_reuse"] = {
            "source": str(reusable.directory),
            "manifest_sha256": reusable.manifest_hash,
            "tiles": reused_tiles,
            "validation": "Copied archives match source manifest hashes; each copied Anvil tile decoded again; changed old/new component extents rebuilt.",
        }
    write_json(args.output / "manifest.json", manifest)
    print(
        json.dumps({"output": str(args.output), **totals, "audit": "pass"}), flush=True
    )


if __name__ == "__main__":
    main()
