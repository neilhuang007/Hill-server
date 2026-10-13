#!/usr/bin/env python3
"""Validate a lobby or hub map in its designated folder, without a name, version or hash pin."""
import argparse
import os
from pathlib import Path
import re

PLACEMENT_FILE = "hill-world.yml"
NPC_NAMES = {"journey", "place", "people", "survival"}
POSE = re.compile(r"\[\s*(-?\d+(?:\.\d+)?)(?:\s*,\s*-?\d+(?:\.\d+)?){2}(?:(?:\s*,\s*-?\d+(?:\.\d+)?){2})?\s*\]")
REGION = re.compile(r"r\.-?\d+\.-?\d+\.mca")


def validate_placement(text: str) -> None:
    """Accepts exactly the documented form, so a typo fails here and not during startup."""
    seen: set[str] = set()
    in_npcs = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if "\t" in line:
            raise ValueError(f"{PLACEMENT_FILE} line {number}: indent with spaces")
        indented = line[0] == " "
        name, separator, value = line.strip().partition(":")
        value = value.strip()
        key = f"npcs.{name}" if indented else name
        if not separator or key in seen:
            raise ValueError(f"{PLACEMENT_FILE} line {number}: expected one 'name: [x, y, z]' entry")
        seen.add(key)
        if not indented and name == "npcs":
            if value:
                raise ValueError(f"{PLACEMENT_FILE} line {number}: list guide positions on indented lines below npcs:")
            in_npcs = True
            continue
        if indented and not (in_npcs and name in NPC_NAMES):
            raise ValueError(f"{PLACEMENT_FILE} line {number}: unknown entry '{name}'")
        if not indented:
            in_npcs = False
            if name != "spawn":
                raise ValueError(f"{PLACEMENT_FILE} line {number}: unknown entry '{name}'")
        if not POSE.fullmatch(value):
            raise ValueError(f"{PLACEMENT_FILE} line {number}: use [x, y, z] or [x, y, z, yaw, pitch]")


def validate(folder: Path) -> None:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Map folder must be an existing directory, not a link")
    level = folder / "level.dat"
    if level.is_symlink() or not level.is_file() or level.stat().st_size == 0:
        raise ValueError("Put the world save's level.dat directly inside the designated folder, "
                         "not a ZIP or a nested save folder")
    regions = 0
    for parent, directories, files in os.walk(folder, followlinks=False):
        for name in directories + files:
            path = Path(parent, name)
            if path.is_symlink():
                raise ValueError(f"Links are not allowed: {path.relative_to(folder)}")
        if Path(parent).name != "region":
            continue
        for name in files:
            # Saves legitimately contain empty region files; a partial header is a damaged copy.
            size = Path(parent, name).stat().st_size
            if REGION.fullmatch(name) and size:
                if size < 8192:
                    raise ValueError(f"Truncated region file: {Path(parent, name).relative_to(folder)}")
                regions += 1
    if not regions:
        raise ValueError("Map has no region data")
    placement = folder / PLACEMENT_FILE
    if placement.exists():
        validate_placement(placement.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        validate(args.folder)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Map folder invalid ({args.folder}): {error}\n")
    print(f"Map folder ready: {args.folder}")
