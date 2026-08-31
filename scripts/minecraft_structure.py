"""Utilities for writing Minecraft Java structure NBT files.

The Hill server imports vanilla structure files directly.  This module keeps
generation scripts independent from Bukkit/Paper while emitting the exact NBT
shape that StructureNbtLoader streams: size, palette, blocks, and entities.
"""

from __future__ import annotations

import gzip
import os
import re
import struct
import tempfile
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping


TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

BLOCK_STATE_RE = re.compile(r"^(?P<name>[a-z0-9_.-]+:[a-z0-9_/.-]+)(?:\[(?P<props>.*)\])?$")


def parse_block_state(block_state: str) -> tuple[str, dict[str, str]]:
    match = BLOCK_STATE_RE.match(block_state)
    if not match:
        raise ValueError(f"Invalid Minecraft block state: {block_state!r}")
    properties: dict[str, str] = {}
    props = match.group("props")
    if props:
        for part in props.split(","):
            key, sep, value = part.partition("=")
            if not sep or not key or not value:
                raise ValueError(f"Invalid block-state property in {block_state!r}: {part!r}")
            properties[key] = value
    return match.group("name"), properties


def _write_name(out: BinaryIO, name: str) -> None:
    encoded = name.encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError(f"NBT name is too long: {name!r}")
    out.write(struct.pack(">H", len(encoded)))
    out.write(encoded)


def _write_named_header(out: BinaryIO, tag_type: int, name: str) -> None:
    out.write(bytes([tag_type]))
    _write_name(out, name)


def _write_string_payload(out: BinaryIO, value: str) -> None:
    encoded = value.encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError(f"NBT string is too long: {value[:80]!r}")
    out.write(struct.pack(">H", len(encoded)))
    out.write(encoded)


def _write_named_int(out: BinaryIO, name: str, value: int) -> None:
    _write_named_header(out, TAG_INT, name)
    out.write(struct.pack(">i", int(value)))


def _write_named_string(out: BinaryIO, name: str, value: str) -> None:
    _write_named_header(out, TAG_STRING, name)
    _write_string_payload(out, value)


def _write_named_int_list(out: BinaryIO, name: str, values: Iterable[int]) -> None:
    data = [int(value) for value in values]
    _write_named_header(out, TAG_LIST, name)
    out.write(bytes([TAG_INT]))
    out.write(struct.pack(">i", len(data)))
    for value in data:
        out.write(struct.pack(">i", value))


class StructureWriter:
    """Stream blocks to a temporary spool, then write a compressed structure NBT."""

    def __init__(
        self,
        output_path: str | Path,
        size: tuple[int, int, int],
        palette: Iterable[str],
        *,
        data_version: int = 4903,
    ) -> None:
        self.output_path = Path(output_path)
        self.size = tuple(int(v) for v in size)
        if len(self.size) != 3 or min(self.size) <= 0:
            raise ValueError(f"Structure size must contain three positive values: {self.size!r}")
        self.palette = list(palette)
        if not self.palette:
            raise ValueError("Structure palette cannot be empty")
        self.data_version = int(data_version)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        spool_dir = self.output_path.parent
        fd, spool_name = tempfile.mkstemp(prefix=self.output_path.stem + "-", suffix=".blocks", dir=spool_dir)
        self._spool_path = Path(spool_name)
        self._spool = os.fdopen(fd, "wb")
        self.block_count = 0
        self._closed = False

    def add_block(self, state: int, x: int, y: int, z: int) -> None:
        if self._closed:
            raise RuntimeError("StructureWriter is already closed")
        state = int(state)
        x = int(x)
        y = int(y)
        z = int(z)
        if state < 0 or state >= len(self.palette):
            raise ValueError(f"Palette index out of range: {state}")
        sx, sy, sz = self.size
        if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
            return
        self._spool.write(struct.pack("<IHHH", state, x, y, z))
        self.block_count += 1

    def add_blocks(self, state: int, positions: Iterable[tuple[int, int, int]]) -> None:
        for x, y, z in positions:
            self.add_block(state, x, y, z)

    def close(self) -> int:
        if self._closed:
            return self.block_count
        self._spool.flush()
        self._spool.close()
        try:
            self._write_nbt()
        finally:
            self._closed = True
            try:
                self._spool_path.unlink()
            except FileNotFoundError:
                pass
        return self.block_count

    def __enter__(self) -> "StructureWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()
        else:
            self._spool.close()
            try:
                self._spool_path.unlink()
            except FileNotFoundError:
                pass
            self._closed = True

    def _write_nbt(self) -> None:
        with gzip.open(self.output_path, "wb", compresslevel=6) as out:
            out.write(bytes([TAG_COMPOUND]))
            _write_name(out, "")
            _write_named_int(out, "DataVersion", self.data_version)
            _write_named_int_list(out, "size", self.size)
            self._write_palette(out)
            self._write_blocks(out)
            self._write_empty_compound_list(out, "entities")
            out.write(bytes([TAG_END]))

    def _write_palette(self, out: BinaryIO) -> None:
        _write_named_header(out, TAG_LIST, "palette")
        out.write(bytes([TAG_COMPOUND]))
        out.write(struct.pack(">i", len(self.palette)))
        for block_state in self.palette:
            block_name, properties = parse_block_state(block_state)
            _write_named_string(out, "Name", block_name)
            if properties:
                _write_named_header(out, TAG_COMPOUND, "Properties")
                for key in sorted(properties):
                    _write_named_string(out, key, properties[key])
                out.write(bytes([TAG_END]))
            out.write(bytes([TAG_END]))

    def _write_blocks(self, out: BinaryIO) -> None:
        _write_named_header(out, TAG_LIST, "blocks")
        out.write(bytes([TAG_COMPOUND]))
        out.write(struct.pack(">i", self.block_count))
        with self._spool_path.open("rb") as spool:
            record = spool.read(10)
            while record:
                state, x, y, z = struct.unpack("<IHHH", record)
                _write_named_int(out, "state", state)
                _write_named_int_list(out, "pos", (x, y, z))
                out.write(bytes([TAG_END]))
                record = spool.read(10)

    @staticmethod
    def _write_empty_compound_list(out: BinaryIO, name: str) -> None:
        _write_named_header(out, TAG_LIST, name)
        out.write(bytes([TAG_COMPOUND]))
        out.write(struct.pack(">i", 0))


def read_structure_metadata(path: str | Path) -> Mapping[str, int]:
    """Read the minimal metadata needed for verification."""

    with gzip.open(path, "rb") as raw:
        data = raw.read()
    offset = 0

    def read(fmt: str) -> tuple[int, ...]:
        nonlocal offset
        size = struct.calcsize(fmt)
        values = struct.unpack(fmt, data[offset : offset + size])
        offset += size
        return values

    def read_string() -> str:
        nonlocal offset
        (length,) = read(">H")
        value = data[offset : offset + length].decode("utf-8")
        offset += length
        return value

    def skip_payload(tag_type: int) -> None:
        nonlocal offset
        if tag_type == TAG_BYTE:
            offset += 1
        elif tag_type == TAG_SHORT:
            offset += 2
        elif tag_type == TAG_INT:
            offset += 4
        elif tag_type == TAG_LONG:
            offset += 8
        elif tag_type == TAG_FLOAT:
            offset += 4
        elif tag_type == TAG_DOUBLE:
            offset += 8
        elif tag_type == TAG_BYTE_ARRAY:
            (length,) = read(">i")
            offset += length
        elif tag_type == TAG_STRING:
            read_string()
        elif tag_type == TAG_LIST:
            element_type = data[offset]
            offset += 1
            (length,) = read(">i")
            for _ in range(length):
                skip_payload(element_type)
        elif tag_type == TAG_COMPOUND:
            while data[offset] != TAG_END:
                nested_type = data[offset]
                offset += 1
                read_string()
                skip_payload(nested_type)
            offset += 1
        elif tag_type == TAG_INT_ARRAY:
            (length,) = read(">i")
            offset += 4 * length
        elif tag_type == TAG_LONG_ARRAY:
            (length,) = read(">i")
            offset += 8 * length
        elif tag_type != TAG_END:
            raise ValueError(f"Unknown NBT tag type {tag_type}")

    if data[offset] != TAG_COMPOUND:
        raise ValueError("Root tag is not a compound")
    offset += 1
    read_string()
    result: dict[str, int] = {}
    while data[offset] != TAG_END:
        tag_type = data[offset]
        offset += 1
        name = read_string()
        if name == "DataVersion" and tag_type == TAG_INT:
            (result["data_version"],) = read(">i")
        elif name == "size" and tag_type == TAG_LIST:
            element_type = data[offset]
            offset += 1
            (length,) = read(">i")
            if element_type != TAG_INT or length != 3:
                raise ValueError("Unexpected size tag")
            sx, sy, sz = read(">iii")
            result["size_x"] = sx
            result["size_y"] = sy
            result["size_z"] = sz
        elif name == "palette" and tag_type == TAG_LIST:
            element_type = data[offset]
            offset += 1
            (length,) = read(">i")
            result["palette_count"] = length
            for _ in range(length):
                skip_payload(element_type)
        elif name == "blocks" and tag_type == TAG_LIST:
            element_type = data[offset]
            offset += 1
            (length,) = read(">i")
            result["block_count"] = length
            return result
        else:
            skip_payload(tag_type)
    raise ValueError("Structure is missing a blocks list")
