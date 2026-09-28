#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import struct
import sys
import zlib
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Iterable

import nbtlib


SECTION_VOLUME = 16 * 16 * 16
FORBIDDEN_NAME_PARTS = (
    "ore",
    "sculk",
    "warped",
    "crimson",
    "blackstone",
    "ancient_debris",
    "coral",
    "glazed_terracotta",
)
NOISY_DARK_BLOCKS = {
    "minecraft:black_concrete",
    "minecraft:black_concrete_powder",
    "minecraft:black_wool",
    "minecraft:coal_block",
    "minecraft:obsidian",
    "minecraft:crying_obsidian",
}


def iter_region_files(world: Path) -> Iterable[Path]:
    region_dir = world / "region"
    if not region_dir.is_dir():
        raise SystemExit(f"missing region directory: {region_dir}")
    yield from sorted(region_dir.glob("r.*.*.mca"))


def decompress_chunk(payload: bytes) -> bytes:
    if len(payload) < 5:
        raise ValueError("chunk payload is too short")
    length = struct.unpack(">I", payload[:4])[0]
    compression = payload[4]
    compressed = payload[5 : 4 + length]
    if compression == 1:
        return gzip.decompress(compressed)
    if compression == 2:
        return zlib.decompress(compressed)
    if compression == 3:
        return compressed
    raise ValueError(f"unsupported region compression type {compression}")


def iter_chunk_nbt(region_path: Path) -> Iterable[nbtlib.Compound]:
    data = region_path.read_bytes()
    if len(data) < 8192:
        return
    for index in range(1024):
        location = data[index * 4 : index * 4 + 4]
        sector_offset = int.from_bytes(location[:3], "big")
        sector_count = location[3]
        if sector_offset == 0 or sector_count == 0:
            continue
        offset = sector_offset * 4096
        size = sector_count * 4096
        if offset + 5 > len(data):
            continue
        try:
            chunk_bytes = decompress_chunk(data[offset : offset + size])
            yield nbtlib.File.parse(BytesIO(chunk_bytes))
        except Exception as exc:
            print(f"warning: skipped corrupt chunk in {region_path.name}: {exc}", file=sys.stderr)


def palette_name(entry: object) -> str:
    if isinstance(entry, nbtlib.Compound):
        value = entry.get("Name") or entry.get("name")
        if value is not None:
            return str(value)
    return str(entry)


def block_states_for_section(section: nbtlib.Compound) -> tuple[list[str], list[int] | None]:
    block_states = section.get("block_states") or section.get("BlockStates")
    if block_states is None:
        return [], None
    raw_palette = block_states.get("palette") or block_states.get("Palette") or []
    palette = [palette_name(entry) for entry in raw_palette]
    raw_data = block_states.get("data") or block_states.get("Data")
    packed = None if raw_data is None else [int(value) for value in raw_data]
    return palette, packed


def unpack_counts(palette: list[str], packed: list[int] | None) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not palette:
        return counts
    if packed is None:
        counts[palette[0]] += SECTION_VOLUME
        return counts

    bits = max(4, (len(palette) - 1).bit_length())
    mask = (1 << bits) - 1
    values = [raw_long & ((1 << 64) - 1) for raw_long in packed]
    for block_index in range(SECTION_VOLUME):
        bit_index = block_index * bits
        long_index = bit_index >> 6
        bit_offset = bit_index & 63
        if long_index >= len(values):
            break
        palette_index = (values[long_index] >> bit_offset) & mask
        spill = bit_offset + bits - 64
        if spill > 0 and long_index + 1 < len(values):
            palette_index |= (values[long_index + 1] & ((1 << spill) - 1)) << (bits - spill)
        if palette_index < len(palette):
            counts[palette[palette_index]] += 1
    return counts


def section_y(section: nbtlib.Compound) -> int:
    return int(section.get("Y") or section.get("y") or 0)


def audit_world(world: Path) -> dict[str, object]:
    total = Counter()
    section_count = 0
    chunk_count = 0
    populated_regions = 0
    min_section_y = None
    max_section_y = None

    for region_path in iter_region_files(world):
        saw_chunk = False
        for chunk in iter_chunk_nbt(region_path):
            chunk_count += 1
            saw_chunk = True
            sections = chunk.get("sections") or chunk.get("Sections") or []
            for section in sections:
                palette, packed = block_states_for_section(section)
                if not palette:
                    continue
                y = section_y(section)
                min_section_y = y if min_section_y is None else min(min_section_y, y)
                max_section_y = y if max_section_y is None else max(max_section_y, y)
                section_count += 1
                total.update(unpack_counts(palette, packed))
        if saw_chunk:
            populated_regions += 1

    forbidden = Counter(
        {name: count for name, count in total.items() if any(part in name for part in FORBIDDEN_NAME_PARTS)}
    )
    noisy_dark = Counter({name: count for name, count in total.items() if name in NOISY_DARK_BLOCKS})
    air = total.get("minecraft:air", 0)
    non_air = sum(total.values()) - air
    return {
        "world": str(world),
        "region_files": len(list((world / "region").glob("r.*.*.mca"))) if (world / "region").is_dir() else 0,
        "populated_region_files": populated_regions,
        "chunks": chunk_count,
        "sections": section_count,
        "section_y_range": [min_section_y, max_section_y],
        "states": len(total),
        "non_air_blocks": non_air,
        "forbidden_blocks": dict(forbidden.most_common()),
        "noisy_dark_blocks": dict(noisy_dark.most_common()),
        "top_blocks": dict(total.most_common(40)),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Audit a Minecraft Java Anvil world palette.")
    parser.add_argument("world", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = audit_world(args.world)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"world={result['world']}")
        print(f"regions={result['populated_region_files']}/{result['region_files']} chunks={result['chunks']} sections={result['sections']}")
        print(f"states={result['states']} non_air_blocks={result['non_air_blocks']}")
        print(f"section_y_range={result['section_y_range']}")
        print(f"forbidden_blocks={result['forbidden_blocks']}")
        print(f"noisy_dark_blocks={result['noisy_dark_blocks']}")
        print("top_blocks:")
        for name, count in result["top_blocks"].items():
            print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
