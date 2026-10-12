#!/usr/bin/env python3
"""Validate an operator-selected campus folder, without a revision or archive pin."""
import argparse
from pathlib import Path
import re


def validate(folder: Path) -> None:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Campus template must be an existing directory, not a link")
    if (folder / "dimensions").exists():
        raise ValueError("Use a flat template with region/ directly inside the designated folder")
    marker = folder / ".hill175-people-ready"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() != "generated":
        raise ValueError("Campus ready marker is invalid")
    for name in ("region", "poi"):
        directory = folder / name
        if name == "poi" and not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Missing or invalid {name} directory")
        files = [path for path in directory.iterdir()
                 if re.fullmatch(r"r\.-?\d+\.-?\d+\.mca", path.name)]
        if name == "region" and not files:
            raise ValueError("Campus template has no region files")
        for path in files:
            if path.is_symlink() or not path.is_file() or path.stat().st_size < 8192:
                raise ValueError(f"Invalid or truncated Anvil file: {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        validate(args.folder)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Campus template invalid: {error}\n")
    print(f"Campus template ready: {args.folder}")
