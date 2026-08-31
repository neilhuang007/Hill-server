"""Voxelize rights-cleared GLB files into VoxelEarth JSON or Minecraft NBT.

This is a small local replacement for the fragile parts of VoxelEarth's public
CPU/browser path.  It keeps VoxelEarth's useful output shape, but it is designed
for offline Hill-owned GLBs: it applies node transforms, supports several
scenes, skips primitives without POSITION data, and can write the structure NBT
format consumed by this server.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from minecraft_structure import StructureWriter, read_structure_metadata


GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

COMPONENT_DTYPES = {
    5120: np.dtype("<i1"),
    5121: np.dtype("<u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
TYPE_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}

MC_BLOCK_COLORS = [
    ("minecraft:white_concrete", (207, 213, 214)),
    ("minecraft:light_gray_concrete", (125, 125, 115)),
    ("minecraft:gray_concrete", (54, 57, 61)),
    ("minecraft:black_concrete", (8, 10, 15)),
    ("minecraft:brown_terracotta", (77, 51, 36)),
    ("minecraft:red_terracotta", (143, 61, 47)),
    ("minecraft:orange_terracotta", (161, 83, 37)),
    ("minecraft:yellow_terracotta", (186, 133, 35)),
    ("minecraft:sandstone", (216, 203, 155)),
    ("minecraft:smooth_stone", (158, 158, 158)),
    ("minecraft:stone_bricks", (122, 121, 122)),
    ("minecraft:deepslate_tiles", (51, 48, 52)),
    ("minecraft:dark_oak_planks", (66, 43, 20)),
    ("minecraft:green_concrete", (73, 91, 36)),
    ("minecraft:lime_concrete", (94, 169, 24)),
    ("minecraft:blue_concrete", (45, 47, 143)),
]


@dataclass(frozen=True)
class Triangle:
    vertices: np.ndarray
    color: tuple[int, int, int]


@dataclass
class LoadStats:
    nodes: int = 0
    primitives: int = 0
    skipped_no_position: int = 0
    skipped_mode: int = 0
    triangles: int = 0


class GltfAsset:
    def __init__(self, path: Path, document: dict, buffers: list[bytes]) -> None:
        self.path = path
        self.document = document
        self.buffers = buffers

    @classmethod
    def load(cls, path: Path) -> "GltfAsset":
        raw = path.read_bytes()
        magic, version, total_length = struct.unpack_from("<III", raw, 0)
        if magic != GLB_MAGIC or version != 2:
            raise ValueError(f"{path} is not a GLB 2.0 file")
        if total_length > len(raw):
            raise ValueError(f"{path} has a truncated GLB header")

        offset = 12
        document: dict | None = None
        bin_chunk: bytes | None = None
        while offset + 8 <= total_length:
            chunk_length, chunk_type = struct.unpack_from("<II", raw, offset)
            offset += 8
            chunk = raw[offset : offset + chunk_length]
            offset += chunk_length
            if chunk_type == JSON_CHUNK:
                document = json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))
            elif chunk_type == BIN_CHUNK:
                bin_chunk = bytes(chunk)
        if document is None:
            raise ValueError(f"{path} is missing a JSON chunk")

        buffers: list[bytes] = []
        for index, buffer_def in enumerate(document.get("buffers", [])):
            uri = buffer_def.get("uri")
            if index == 0 and uri is None:
                buffers.append(bin_chunk or b"")
            elif isinstance(uri, str) and uri.startswith("data:"):
                _, encoded = uri.split(",", 1)
                buffers.append(base64.b64decode(encoded))
            elif isinstance(uri, str):
                buffers.append((path.parent / uri).read_bytes())
            else:
                buffers.append(b"")
        if not buffers and bin_chunk is not None:
            buffers.append(bin_chunk)
        return cls(path, document, buffers)

    def read_accessor(self, accessor_index: int) -> np.ndarray:
        accessor = self.document["accessors"][accessor_index]
        count = int(accessor.get("count", 0))
        component_type = int(accessor["componentType"])
        component_dtype = COMPONENT_DTYPES[component_type]
        component_count = TYPE_COUNTS[accessor.get("type", "SCALAR")]

        if "bufferView" not in accessor:
            values = np.zeros((count, component_count), dtype=component_dtype)
        else:
            view = self.document["bufferViews"][int(accessor["bufferView"])]
            buffer_data = self.buffers[int(view.get("buffer", 0))]
            view_offset = int(view.get("byteOffset", 0))
            accessor_offset = int(accessor.get("byteOffset", 0))
            start = view_offset + accessor_offset
            packed_stride = component_dtype.itemsize * component_count
            stride = int(view.get("byteStride", packed_stride))
            if stride == packed_stride:
                values = np.frombuffer(
                    buffer_data,
                    dtype=component_dtype,
                    count=count * component_count,
                    offset=start,
                ).reshape((count, component_count))
            else:
                values = np.empty((count, component_count), dtype=component_dtype)
                for row in range(count):
                    row_offset = start + row * stride
                    values[row, :] = np.frombuffer(
                        buffer_data,
                        dtype=component_dtype,
                        count=component_count,
                        offset=row_offset,
                    )

        if "sparse" in accessor:
            values = values.copy()
            sparse = accessor["sparse"]
            indices = self._read_sparse_indices(sparse)
            replacement = self._read_sparse_values(sparse, component_dtype, component_count)
            values[indices] = replacement

        if accessor.get("normalized") and component_type != 5126:
            values = normalize_accessor_values(values, component_type)
        if component_count == 1:
            return values.reshape((count,))
        return values.copy()

    def _read_sparse_indices(self, sparse: dict) -> np.ndarray:
        index_def = sparse["indices"]
        view = self.document["bufferViews"][int(index_def["bufferView"])]
        dtype = COMPONENT_DTYPES[int(index_def["componentType"])]
        start = int(view.get("byteOffset", 0)) + int(index_def.get("byteOffset", 0))
        buffer_data = self.buffers[int(view.get("buffer", 0))]
        return np.frombuffer(buffer_data, dtype=dtype, count=int(sparse["count"]), offset=start).astype(np.int64)

    def _read_sparse_values(self, sparse: dict, dtype: np.dtype, component_count: int) -> np.ndarray:
        value_def = sparse["values"]
        view = self.document["bufferViews"][int(value_def["bufferView"])]
        start = int(view.get("byteOffset", 0)) + int(value_def.get("byteOffset", 0))
        buffer_data = self.buffers[int(view.get("buffer", 0))]
        return np.frombuffer(
            buffer_data,
            dtype=dtype,
            count=int(sparse["count"]) * component_count,
            offset=start,
        ).reshape((int(sparse["count"]), component_count))

    def gather_triangles(self) -> tuple[list[Triangle], LoadStats]:
        stats = LoadStats()
        triangles: list[Triangle] = []
        scenes = self.document.get("scenes") or []
        if scenes:
            scene_index = int(self.document.get("scene", 0))
            root_nodes = scenes[scene_index].get("nodes", [])
        else:
            root_nodes = list(range(len(self.document.get("nodes", []))))
        identity = np.eye(4, dtype=np.float64)
        for node_index in root_nodes:
            self._gather_node(int(node_index), identity, triangles, stats)
        return triangles, stats

    def _gather_node(
        self,
        node_index: int,
        parent_matrix: np.ndarray,
        triangles: list[Triangle],
        stats: LoadStats,
    ) -> None:
        nodes = self.document.get("nodes", [])
        node = nodes[node_index]
        stats.nodes += 1
        world_matrix = parent_matrix @ node_matrix(node)
        if "mesh" in node:
            self._gather_mesh(int(node["mesh"]), world_matrix, triangles, stats)
        for child in node.get("children", []):
            self._gather_node(int(child), world_matrix, triangles, stats)

    def _gather_mesh(
        self,
        mesh_index: int,
        world_matrix: np.ndarray,
        triangles: list[Triangle],
        stats: LoadStats,
    ) -> None:
        meshes = self.document.get("meshes", [])
        mesh = meshes[mesh_index]
        for primitive in mesh.get("primitives", []):
            stats.primitives += 1
            if int(primitive.get("mode", 4)) != 4:
                stats.skipped_mode += 1
                continue
            attributes = primitive.get("attributes") or {}
            position_index = attributes.get("POSITION")
            if position_index is None:
                stats.skipped_no_position += 1
                continue
            positions = self.read_accessor(int(position_index)).astype(np.float64)
            if positions.ndim != 2 or positions.shape[1] < 3:
                stats.skipped_no_position += 1
                continue
            positions = positions[:, :3]
            transformed = transform_points(positions, world_matrix)
            indices = self._read_primitive_indices(primitive, len(transformed))
            if len(indices) < 3:
                continue
            material_color = self._material_color(primitive.get("material"))
            for start in range(0, len(indices) - 2, 3):
                tri_indices = indices[start : start + 3]
                vertices = transformed[tri_indices]
                if triangle_area(vertices) <= 1e-10:
                    continue
                triangles.append(Triangle(vertices=vertices, color=material_color))
                stats.triangles += 1

    def _read_primitive_indices(self, primitive: dict, position_count: int) -> np.ndarray:
        if "indices" not in primitive:
            return np.arange(position_count, dtype=np.int64)
        return self.read_accessor(int(primitive["indices"])).astype(np.int64).reshape((-1,))

    def _material_color(self, material_index: int | None) -> tuple[int, int, int]:
        if material_index is None:
            return (180, 180, 180)
        materials = self.document.get("materials", [])
        if material_index < 0 or material_index >= len(materials):
            return (180, 180, 180)
        pbr = materials[material_index].get("pbrMetallicRoughness", {})
        factor = pbr.get("baseColorFactor", [0.7, 0.7, 0.7, 1.0])
        return tuple(int(max(0, min(255, round(float(value) * 255)))) for value in factor[:3])


def normalize_accessor_values(values: np.ndarray, component_type: int) -> np.ndarray:
    values = values.astype(np.float32)
    if component_type == 5120:
        return np.maximum(values / 127.0, -1.0)
    if component_type == 5121:
        return values / 255.0
    if component_type == 5122:
        return np.maximum(values / 32767.0, -1.0)
    if component_type == 5123:
        return values / 65535.0
    return values


def node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape((4, 4), order="F")
    translation = np.array(node.get("translation", [0.0, 0.0, 0.0]), dtype=np.float64)
    rotation = np.array(node.get("rotation", [0.0, 0.0, 0.0, 1.0]), dtype=np.float64)
    scale = np.array(node.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)

    t_matrix = np.eye(4, dtype=np.float64)
    t_matrix[:3, 3] = translation
    r_matrix = quaternion_matrix(rotation)
    s_matrix = np.diag([scale[0], scale[1], scale[2], 1.0]).astype(np.float64)
    return t_matrix @ r_matrix @ s_matrix


def quaternion_matrix(quaternion: np.ndarray) -> np.ndarray:
    x, y, z, w = quaternion
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm == 0.0:
        return np.eye(4, dtype=np.float64)
    x /= norm
    y /= norm
    z /= norm
    w /= norm
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy), 0.0],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx), 0.0],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy), 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    ones = np.ones((points.shape[0], 1), dtype=np.float64)
    homogeneous = np.concatenate([points, ones], axis=1)
    transformed = homogeneous @ matrix.T
    return transformed[:, :3]


def triangle_area(vertices: np.ndarray) -> float:
    return float(np.linalg.norm(np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])) * 0.5)


def compute_bounds(triangles: Iterable[Triangle], *, tiles3d: bool) -> tuple[np.ndarray, np.ndarray]:
    all_vertices = np.concatenate([triangle.vertices for triangle in triangles], axis=0)
    min_xyz = all_vertices.min(axis=0)
    max_xyz = all_vertices.max(axis=0)
    if tiles3d:
        center = (min_xyz + max_xyz) * 0.5
        half = np.array([46.0, 38.0, 24.0], dtype=np.float64) * 1.3 * 0.5
        min_xyz = center - half
        max_xyz = center + half
    span = max_xyz - min_xyz
    max_span = float(max(span.max(), 1e-6))
    center = (min_xyz + max_xyz) * 0.5
    min_cube = center - max_span * 0.5
    max_cube = center + max_span * 0.5
    return min_cube, max_cube


def voxelize_triangles(
    triangles: list[Triangle],
    *,
    grid: int,
    tiles3d: bool,
    solid_fill: bool,
) -> tuple[dict[tuple[int, int, int], tuple[int, int, int]], dict[str, object]]:
    if not triangles:
        raise ValueError("No triangles to voxelize")
    min_xyz, max_xyz = compute_bounds(triangles, tiles3d=tiles3d)
    unit = float((max_xyz - min_xyz).max() / grid)
    if unit <= 0.0:
        raise ValueError("Computed a non-positive voxel unit")

    voxels: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for triangle in triangles:
        normalized = (triangle.vertices - min_xyz) / unit
        emit_triangle_samples(normalized, triangle.color, grid, voxels)

    if solid_fill:
        voxels = fill_vertical_columns(voxels)

    metadata = {
        "bounds_min": min_xyz.tolist(),
        "bounds_max": max_xyz.tolist(),
        "unit": unit,
        "grid": grid,
        "tiles3d_bounds": tiles3d,
    }
    return voxels, metadata


def emit_triangle_samples(
    vertices: np.ndarray,
    color: tuple[int, int, int],
    grid: int,
    voxels: dict[tuple[int, int, int], tuple[int, int, int]],
) -> None:
    area = triangle_area(vertices)
    longest_edge = max(
        np.linalg.norm(vertices[1] - vertices[0]),
        np.linalg.norm(vertices[2] - vertices[1]),
        np.linalg.norm(vertices[0] - vertices[2]),
    )
    steps = max(1, int(math.ceil(max(math.sqrt(area) * 2.25, longest_edge * 1.75))))
    for i in range(steps + 1):
        for j in range(steps + 1 - i):
            a = i / steps
            b = j / steps
            c = 1.0 - a - b
            point = vertices[0] * c + vertices[1] * a + vertices[2] * b
            add_voxel(point, color, grid, voxels)
    for start, end in ((0, 1), (1, 2), (2, 0)):
        sample_edge(vertices[start], vertices[end], color, grid, voxels)


def sample_edge(
    start: np.ndarray,
    end: np.ndarray,
    color: tuple[int, int, int],
    grid: int,
    voxels: dict[tuple[int, int, int], tuple[int, int, int]],
) -> None:
    length = float(np.linalg.norm(end - start))
    steps = max(1, int(math.ceil(length * 2.0)))
    for index in range(steps + 1):
        point = start + (end - start) * (index / steps)
        add_voxel(point, color, grid, voxels)


def add_voxel(
    point: np.ndarray,
    color: tuple[int, int, int],
    grid: int,
    voxels: dict[tuple[int, int, int], tuple[int, int, int]],
) -> None:
    coords = np.floor(point).astype(np.int64)
    coords = np.clip(coords, 0, grid - 1)
    voxels[(int(coords[0]), int(coords[1]), int(coords[2]))] = color


def fill_vertical_columns(
    voxels: dict[tuple[int, int, int], tuple[int, int, int]]
) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    columns: dict[tuple[int, int], list[tuple[int, tuple[int, int, int]]]] = {}
    for (x, y, z), color in voxels.items():
        columns.setdefault((x, z), []).append((y, color))
    filled = dict(voxels)
    for (x, z), values in columns.items():
        values.sort(key=lambda item: item[0])
        if not values:
            continue
        low = values[0][0]
        high = values[-1][0]
        color = values[len(values) // 2][1]
        for y in range(low, high + 1):
            filled.setdefault((x, y, z), color)
    return filled


def write_voxelearth_json(
    path: Path,
    voxels: dict[tuple[int, int, int], tuple[int, int, int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color_to_index: dict[tuple[int, int, int], int] = {}
    blocks: dict[str, list[int]] = {}
    xyzi: list[list[int]] = []
    for x, y, z in sorted(voxels):
        color = voxels[(x, y, z)]
        if color not in color_to_index:
            color_to_index[color] = len(color_to_index) + 1
            blocks[str(color_to_index[color])] = [int(color[0]), int(color[1]), int(color[2])]
        xyzi.append([x, y, z, color_to_index[color]])
    path.write_text(json.dumps({"blocks": blocks, "xyzi": xyzi}, separators=(",", ":")), encoding="utf-8")


def nearest_block(color: tuple[int, int, int]) -> str:
    c = np.array(color, dtype=np.float64)
    best_name = MC_BLOCK_COLORS[0][0]
    best_distance = float("inf")
    for name, rgb in MC_BLOCK_COLORS:
        distance = float(np.sum((c - np.array(rgb, dtype=np.float64)) ** 2))
        if distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def write_structure(
    path: Path,
    voxels: dict[tuple[int, int, int], tuple[int, int, int]],
) -> dict[str, int]:
    if not voxels:
        raise ValueError("No voxels to write")
    max_x = max(x for x, _, _ in voxels) + 1
    max_y = max(y for _, y, _ in voxels) + 1
    max_z = max(z for _, _, z in voxels) + 1
    block_to_state: dict[str, int] = {}
    palette: list[str] = []
    for color in sorted(set(voxels.values())):
        block = nearest_block(color)
        if block not in block_to_state:
            block_to_state[block] = len(palette)
            palette.append(block)
    with StructureWriter(path, (max_x, max_y, max_z), palette) as writer:
        for (x, y, z), color in sorted(voxels.items()):
            writer.add_block(block_to_state[nearest_block(color)], x, y, z)
        block_count = writer.block_count
    metadata = dict(read_structure_metadata(path))
    metadata["written_blocks"] = block_count
    return metadata


def make_self_test_glb(path: Path) -> None:
    positions = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype="<f4",
    )
    bin_data = positions.tobytes()
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"translation": [2.0, 0.0, 0.0], "children": [1]}, {"mesh": 0, "scale": [2.0, 2.0, 2.0]}],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0}, "mode": 4, "material": 0},
                    {"attributes": {}, "mode": 4, "material": 0},
                    {"attributes": {"POSITION": 0}, "mode": 1, "material": 0},
                ]
            }
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.1, 0.1, 1.0]}}],
        "buffers": [{"byteLength": len(bin_data)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(bin_data)}],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            }
        ],
    }
    json_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_data += b"\x00" * ((4 - len(bin_data) % 4) % 4)
    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    payload = bytearray()
    payload.extend(struct.pack("<III", GLB_MAGIC, 2, total_length))
    payload.extend(struct.pack("<II", len(json_bytes), JSON_CHUNK))
    payload.extend(json_bytes)
    payload.extend(struct.pack("<II", len(bin_data), BIN_CHUNK))
    payload.extend(bin_data)
    path.write_bytes(payload)


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="hill-glb-voxelizer-") as tmp_name:
        tmp = Path(tmp_name)
        glb = tmp / "synthetic.glb"
        out_json = tmp / "synthetic_16.json"
        out_nbt = tmp / "synthetic.nbt"
        make_self_test_glb(glb)
        asset = GltfAsset.load(glb)
        triangles, stats = asset.gather_triangles()
        if stats.skipped_no_position != 1:
            raise AssertionError(f"Expected one skipped POSITION-less primitive, got {stats.skipped_no_position}")
        if stats.skipped_mode != 1:
            raise AssertionError(f"Expected one skipped non-triangle primitive, got {stats.skipped_mode}")
        bounds_min, _ = compute_bounds(triangles, tiles3d=False)
        if bounds_min[0] < 1.9:
            raise AssertionError("Node translation/scale was not applied")
        voxels, _ = voxelize_triangles(triangles, grid=16, tiles3d=False, solid_fill=True)
        if not voxels:
            raise AssertionError("Self-test produced no voxels")
        write_voxelearth_json(out_json, voxels)
        metadata = write_structure(out_nbt, voxels)
        if metadata["block_count"] <= 0:
            raise AssertionError("Self-test structure contains no blocks")
        print(
            "self-test ok:",
            f"triangles={stats.triangles}",
            f"skipped_no_position={stats.skipped_no_position}",
            f"voxels={len(voxels)}",
            f"nbt_blocks={metadata['block_count']}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path, help="Rights-cleared .glb files to voxelize")
    parser.add_argument("-o", "--out-dir", type=Path, default=Path("runtime/campus-output/glb-voxels"))
    parser.add_argument("-s", "--grid", type=int, default=128)
    parser.add_argument("--tiles3d", action="store_true", help="Use VoxelEarth's 3D Tiles cube bounds before cube fitting")
    parser.add_argument("--solid-fill", action="store_true", help="Fill vertical columns between surface samples")
    parser.add_argument("--json", action="store_true", help="Write VoxelEarth-compatible JSON")
    parser.add_argument("--nbt", action="store_true", help="Write Minecraft structure NBT")
    parser.add_argument("--self-test", action="store_true", help="Run a synthetic GLB robustness test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return
    if not args.inputs:
        raise SystemExit("Provide at least one GLB file or use --self-test")
    if not args.json and not args.nbt:
        args.json = True
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for input_path in args.inputs:
        asset = GltfAsset.load(input_path)
        triangles, stats = asset.gather_triangles()
        voxels, bounds = voxelize_triangles(
            triangles,
            grid=max(8, int(args.grid)),
            tiles3d=bool(args.tiles3d),
            solid_fill=bool(args.solid_fill),
        )
        base = input_path.stem
        if args.json:
            write_voxelearth_json(args.out_dir / f"{base}_{args.grid}.json", voxels)
        nbt_meta: dict[str, int] | None = None
        if args.nbt:
            nbt_meta = write_structure(args.out_dir / f"{base}.nbt", voxels)
        report = {
            "input": str(input_path),
            "triangles": stats.triangles,
            "nodes": stats.nodes,
            "primitives": stats.primitives,
            "skipped_no_position": stats.skipped_no_position,
            "skipped_non_triangles": stats.skipped_mode,
            "voxels": len(voxels),
            "bounds": bounds,
            "nbt": nbt_meta,
        }
        (args.out_dir / f"{base}.manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            f"{input_path.name}: triangles={stats.triangles} voxels={len(voxels)} "
            f"skipped_no_position={stats.skipped_no_position} skipped_non_triangles={stats.skipped_mode}"
        )


if __name__ == "__main__":
    main()
