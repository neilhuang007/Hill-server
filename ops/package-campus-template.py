#!/usr/bin/env python3
"""Package the verified v19 campus as an immutable People competition template.

Only overworld region files are imported. Player data, vanilla dimensions and
level.dat are deliberately omitted: Paper owns dimension metadata for each copy.
The original download and all construction/player saves remain untouched.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

SOURCE_SHA256 = "afd71210f650f3e5adea9d4d6859b3c5295b1314b2330788af0bafbce0bd8c0f"
SOURCE_ROOT = "Hill-School-175th-v19-1.21.11/"
ARCHIVE_NAME = "hill_people_template_campus_v19_2x.tgz"
TEMPLATE_ROOT = "hill_people_template"
REGION_COUNT = 25
REVISION = "campus-v19-2x"
BLOCKS_PER_METRE = 2
BLOCK_BOUNDS = [-576, 18, -1600, 1407, 319, 415]
SPAWN = [228, 91, 154]
METADATA = (
    f"revision: {REVISION}\n"
    f"blocks-per-metre: {BLOCKS_PER_METRE}\n"
    f"block-bounds: {json.dumps(BLOCK_BOUNDS)}\n"
    f"spawn: {json.dumps(SPAWN)}\n"
)


def package(source: Path, destination: Path) -> str:
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Campus source ZIP does not match the verified v19 1.21.11 download")
    with zipfile.ZipFile(source) as world:
        # The pinned hash verifies the whole source; read() also checks the CRC
        # of each imported region. Avoid decompressing the entire ZIP twice.
        members = sorted(name for name in world.namelist()
                         if re.fullmatch(re.escape(SOURCE_ROOT) + r"region/r\.-?\d+\.-?\d+\.mca", name))
        if len(members) != REGION_COUNT:
            raise ValueError(f"Expected {REGION_COUNT} region files; got {len(members)}")
        files = {name.removeprefix(SOURCE_ROOT): world.read(name) for name in members}
    provenance = {
        "revision": REVISION, "blocks_per_metre": BLOCKS_PER_METRE,
        "source_zip_sha256": SOURCE_SHA256, "source_data_version": 4671,
        "source_chunks": 15624, "region_count": REGION_COUNT,
        "bounds_xz_inclusive": [BLOCK_BOUNDS[index] for index in (0, 2, 3, 5)],
        "spawn": SPAWN,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files[".hill175-people-ready"] = b"generated\n"
    files["hill-campus-template.yml"] = METADATA.encode()
    files["hill-campus-template.json"] = (json.dumps(provenance, indent=2) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Fixed metadata and gzip time make the pinned archive reproducible.
    with destination.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, data in sorted(files.items()):
                member = tarfile.TarInfo(f"{TEMPLATE_ROOT}/{name}")
                member.size, member.mode, member.mtime = len(data), 0o640, 0
                archive.addfile(member, io.BytesIO(data))
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(json.dumps({"archive": str(destination), "sha256": digest,
                      "bytes": destination.stat().st_size, "region_count": REGION_COUNT}))
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("runtime/campus-reconstruction/exports/Hill-School-175th-v19-Java-1.21.11.zip"))
    parser.add_argument("--output", type=Path, default=Path("runtime/assets/campus") / ARCHIVE_NAME)
    options = parser.parse_args()
    package(options.source, options.output)
