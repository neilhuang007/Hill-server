"""Independently verify an exported semantic block archive against its Anvil world.

This checks exported data and native capture provenance. Visual likeness is a
separate human/agent review and is never inferred from a successful export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from campus_export_parity import compare_world, read_archive, role_histogram
from campus_materials import audit_role_materials, forbidden_reason


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_native_capture(directory: Path, native_report: Path):
    errors = []
    capture = json.loads(native_report.read_text(encoding="utf-8"))
    launch_path = native_report.parent / "launch-manifest.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    if Path(launch["source_world"]).resolve() != (directory / "world").resolve():
        errors.append("Native launch names a different source world")
    backup = Path(launch["preupgrade_backup"])
    prefix = Path(launch["copied_world"]).name
    checked = 0
    with zipfile.ZipFile(backup) as z:
        for source_file in [
            (directory / "world/level.dat"),
            *(directory / "world/region").glob("*.mca"),
        ]:
            relative = source_file.relative_to(directory / "world").as_posix()
            try:
                with z.open(prefix + "/" + relative) as member:
                    copied_hash = hashlib.file_digest(member, "sha256").hexdigest()
                if copied_hash != digest(source_file):
                    errors.append(
                        f"Native pre-upgrade world differs from source: {relative}"
                    )
                checked += 1
            except KeyError:
                errors.append(f"Native backup lacks source file: {relative}")
    screenshots = []
    for view in capture.get("views", []):
        path = Path(view["screenshot"])
        valid = path.is_file() and digest(path) == view["sha256"]
        if not valid:
            errors.append(f"Native screenshot missing or changed: {view['name']}")
        screenshots.append(
            {"view": view["name"], "path": str(path), "hash_matches": valid}
        )
    if capture.get("status") != "complete" or capture.get("failure"):
        errors.append("Native capture did not complete")
    if not capture.get("capture_input_probe_passed"):
        errors.append("Native camera input isolation probe did not pass")
    if len(screenshots) < 4:
        errors.append("Native capture has fewer than four comparison views")
    native = {
        "report": str(native_report.resolve()),
        "report_sha256": digest(native_report),
        "minecraft_version": capture.get("minecraft_version"),
        "active_resource_packs": capture.get("active_resource_packs"),
        "source_files_matched_to_preupgrade_backup": checked,
        "screenshots": screenshots,
    }
    return native, errors


def audit(directory: Path, native_report: Path | None = None):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    archive = read_archive(directory / "sample-blocks.npz")
    parity, errors, actual_keys, chunks = compare_world(archive, directory / "world")
    roles = defaultdict(Counter)
    materials = Counter()
    for role_id, state_id, count in role_histogram(archive):
        role = archive["role_names"][role_id]
        name = archive["palette_keys"][state_id][0]
        roles[role][name] += int(count)
        materials[name] += int(count)
    role_counts = {role: dict(counts) for role, counts in roles.items()}
    if dict(materials) != manifest["materials"]:
        errors.append("Archive material counts disagree with manifest")
    if role_counts != manifest["material_roles"]:
        errors.append("Archive semantic roles disagree with manifest")
    if len(archive["coords"]) != manifest["block_count"]:
        errors.append("Archive block count disagrees with manifest")
    role_violations = audit_role_materials(role_counts)
    if role_violations:
        errors.append("Occupied blocks violate their construction role allowlist")
    # Count the independent Anvil palette, not just what the generator claims.
    forbidden = [
        {"block": name, "reason": forbidden_reason(name)}
        for name in sorted({key[0] for key in actual_keys})
        if forbidden_reason(name)
    ]
    if forbidden:
        errors.append("Anvil world contains forbidden blocks")
    if manifest["clipped_writes"]:
        errors.append("Generator recorded clipped writes")
    profile_hash = (
        manifest.get("profile_sha256")
        or manifest.get("profile", {}).get("sha256")
        or manifest.get("sources", {}).get("profile", {}).get("sha256")
    )
    if digest(directory / "profile.json") != profile_hash:
        errors.append("Profile hash disagrees with manifest")

    native = None
    if native_report:
        native, native_errors = audit_native_capture(directory, native_report)
        errors.extend(native_errors)
    result = {
        "format": "hill-block-artifact-audit-v1",
        "passed": not errors,
        "directory": str(directory.resolve()),
        "archive_sha256": digest(directory / "sample-blocks.npz"),
        "manifest_sha256": digest(directory / "manifest.json"),
        "chunk_count": chunks,
        "exact_export_parity": parity,
        "materials": dict(materials),
        "role_materials": role_counts,
        "forbidden_materials": forbidden,
        "role_violations": role_violations,
        "native_capture": native,
        "visual_likeness": "Not certified by this structural audit; see visual review.",
        "errors": errors,
    }
    (directory / "artifact-audit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--native-report", type=Path)
    args = parser.parse_args()
    result = audit(args.directory, args.native_report)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "passed",
                    "exact_export_parity",
                    "forbidden_materials",
                    "errors",
                )
            },
            indent=2,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
