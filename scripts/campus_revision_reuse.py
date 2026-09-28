"""Reuse unchanged, audited campus tiles during a building-only revision.

This preserves the previously reviewed terrain export exactly. Changed component
extents are rebuilt; reused archives and worlds are still independently decoded.
"""

import json
from pathlib import Path

from campus_study_io import digest


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def component_bounds(meta):
    return (meta["x_min"], meta["z_min"],
            meta["x_min"] + meta["shape"][2],
            meta["z_min"] + meta["shape"][1])


def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def changed_extents(old, new):
    if len(old) != len(new):
        raise ValueError("Tile reuse requires the same component count/order")
    boxes = []
    for before, after in zip(old, new):
        # A path change alone cannot affect pasted states, roles or ownership.
        a = {k: v for k, v in before.items() if k != "study"}
        b = {k: v for k, v in after.items() if k != "study"}
        if a != b:
            boxes.extend((component_bounds(before), component_bounds(after)))
    return boxes


class ReusableAssembly:
    def __init__(self, directory, profile, components, terrain_hash, bounds, base,
                 landscape):
        self.directory = Path(directory).resolve()
        manifest_path = self.directory / "manifest.json"
        manifest = read(manifest_path)
        audit = read(self.directory / "artifact-audit.json")
        review = read(self.directory / "native-review.json")
        manifest_hash = digest(manifest_path)
        if (not audit.get("passed") or audit.get("manifest_sha256") != manifest_hash
                or not str(review.get("status", "")).startswith("accepted")
                or review.get("manifest_sha256") != manifest_hash):
            raise ValueError("Reuse source needs an accepted, exact audited manifest")
        old_profile = read(self.directory / "profile.json")
        if digest(self.directory / "profile.json") != manifest["profile"]["sha256"]:
            raise ValueError("Reuse source profile changed")
        if (manifest["terrain"]["sha256"] != terrain_hash
                or manifest["bounds_xz_blocks"] != list(bounds)
                or manifest["terrain_base_y"] != base
                or old_profile.get("tile_size_blocks", 256) != profile.get("tile_size_blocks", 256)
                or manifest["blocks_per_metre"] != profile["blocks_per_metre"]
                or manifest["vertical_offset_m"] != profile["vertical_offset_m"]):
            raise ValueError("Reuse source terrain/frame differs")
        if manifest.get("resource_pack") or profile.get("resource_pack"):
            raise ValueError("Tile reuse currently supports vanilla-only assemblies")
        old_landscape = None
        if manifest.get("landscape"):
            path = self.directory / "landscape-profile.json"
            if digest(path) != manifest["landscape"]["sha256"]:
                raise ValueError("Reuse source landscape changed")
            old_landscape = read(path)
        if old_landscape != landscape:
            raise ValueError("Tile reuse cannot change landscape")
        for component in manifest["components"]:
            if digest(Path(component["study"]) / "sample-blocks.npz") != component["archive_sha256"]:
                raise ValueError("Reuse source component archive changed")
        self.changed = changed_extents(manifest["components"], [c.meta for c in components])
        self.tiles = {Path(t["path"]).name: t for t in manifest["tiles"]}
        self.manifest_hash = manifest_hash

    def candidate(self, name, bounds):
        if any(intersects(bounds, box) for box in self.changed):
            return None
        specification = self.tiles.get(name)
        if specification is None:
            raise ValueError(f"Reuse source lacks tile {name}")
        path = (self.directory / specification["path"]).resolve()
        if not path.is_relative_to(self.directory / "tiles"):
            raise ValueError("Reuse tile path escapes source tiles")
        for filename, field in (("sample-blocks.npz", "archive_sha256"),
                                ("audit.json", "audit_sha256")):
            if digest(path / filename) != specification[field]:
                raise ValueError(f"Reuse tile changed: {name}/{filename}")
        report = read(path / "audit.json")
        if report.get("errors") or report["block_count"] != specification["blocks"]:
            raise ValueError(f"Reuse tile has invalid audit: {name}")
        return path, report
