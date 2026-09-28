"""Recheck tiled exports and bind native Minecraft captures to the shared world."""

import argparse
import gc
import json
from collections import Counter, defaultdict
from pathlib import Path

import hybridize_voxelearth_roofer_world as anvil
from assemble_hill_campus_studies import digest_bytes, verify_merged_world
from audit_hill_block_artifact import audit_native_capture
from campus_export_parity import compare_world, read_archive, role_histogram
from campus_materials import audit_role_materials, forbidden_reason
from campus_study_io import digest, write_json


def audit(directory, native_report):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    errors, records, tiles, totals = [], {}, [], Counter()
    if digest(directory / "profile.json") != manifest["profile"]["sha256"]:
        errors.append("Assembly profile differs from recorded hash")
    ownership = manifest.get("ownership_audit")
    if ownership:
        ownership_path = directory / ownership["path"]
        if digest(ownership_path) != ownership["sha256"]:
            errors.append("Building ownership audit differs from recorded hash")
        ownership_report = json.loads(ownership_path.read_text(encoding="utf-8"))
        if not ownership_report["passed"] or ownership_report["overlapping_columns"] or ownership_report["clipped_owned_columns"]:
            errors.append("Building ownership overlaps or leaves the campus extent")
    if (
        manifest.get("landscape")
        and (directory / "landscape-profile.json").exists()
        and digest(directory / "landscape-profile.json")
        != manifest["landscape"]["sha256"]
    ):
        errors.append("Landscape input differs from its frozen snapshot")
    for component in manifest["components"]:
        study = Path(component["study"])
        if digest(study / "sample-blocks.npz") != component["archive_sha256"]:
            errors.append(f"Component archive changed: {study.name}")
        if (
            component["scale"] != 2
            or component["offset"] != manifest["vertical_offset_m"]
        ):
            errors.append(f"Component frame mismatch: {study.name}")
    for specification in manifest["tiles"]:
        tile = directory / specification["path"]
        for name, field in (
            ("audit.json", "audit_sha256"),
            ("sample-blocks.npz", "archive_sha256"),
        ):
            if digest(tile / name) != specification[field]:
                errors.append(f"Tile artifact changed: {tile.name}/{name}")
        archive = read_archive(tile / "sample-blocks.npz")
        parity, problems, actual, chunks = compare_world(archive, tile / "world")
        roles = defaultdict(Counter)
        for role, state, count in role_histogram(archive):
            roles[archive["role_names"][role]][archive["palette_keys"][state][0]] += (
                int(count)
            )
        violations = audit_role_materials(roles)
        forbidden = [key[0] for key in actual if forbidden_reason(key[0])]
        if violations or forbidden:
            problems.append("Non-construction materials found")
        if (
            len(archive["coords"]) != specification["blocks"]
            or chunks != specification["chunks"]
        ):
            problems.append("Tile count differs from assembly manifest")
        errors.extend(f"{tile.name}: {problem}" for problem in problems)
        totals.update(blocks=len(archive["coords"]), chunks=chunks, tiles=1)
        tiles.append({"tile": tile.name, "parity": parity, "errors": problems})
        for path in sorted((tile / "world/region").glob("*.mca")):
            for index, record in anvil.RegionEditor(path).raw_records.items():
                address = (path.name, index)
                if address in records:
                    errors.append(f"Duplicate tile chunk: {address}")
                records[address] = digest_bytes(record)
        del archive
        gc.collect()
    try:
        verify_merged_world(directory / "world", records)
    except ValueError as error:
        errors.append(str(error))
    if dict(totals) != manifest["totals"]:
        errors.append("Assembly totals disagree with independent decoded totals")
    pack = manifest.get("resource_pack")
    for relative, expected in (pack["files"] if pack else {}).items():
        if digest(Path(pack["path"]) / relative) != expected:
            errors.append(f"Resource pack changed: {relative}")
    native, problems = audit_native_capture(directory, native_report)
    errors.extend(problems)
    launch = json.loads(
        (native_report.parent / "launch-manifest.json").read_text(encoding="utf-8")
    )
    if pack and launch["resource_pack_id"] not in native["active_resource_packs"]:
        errors.append(
            "Expected campus resource pack was not active in native Minecraft"
        )
    if not pack and native["active_resource_packs"] != ["vanilla"]:
        errors.append("Vanilla-only campus loaded an unexpected resource pack")
    copied_pack = (
        Path(launch["game_directory"]) / "resourcepacks" / Path(pack["path"]).name
        if pack
        else None
    )
    for relative, expected in (pack["files"] if pack else {}).items():
        if digest(copied_pack / relative) != expected:
            errors.append(f"Native resource pack differs: {relative}")
    result = {
        "format": "hill-campus-assembly-audit-v1",
        "passed": not errors,
        "manifest_sha256": digest(directory / "manifest.json"),
        "totals": dict(totals),
        "tiles": tiles,
        "native_capture": native,
        "visual_likeness": "Separate visual review; export parity does not establish likeness.",
        "errors": errors,
    }
    write_json(directory / "artifact-audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--native-report", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory, args.native_report)
    print(json.dumps({k: result[k] for k in ("passed", "totals", "errors")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
