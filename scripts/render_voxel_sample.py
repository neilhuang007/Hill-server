"""Render an exact-state Minecraft voxel sample as a diagnostic PNG.

This is an offscreen textured preview, not an in-game screenshot or photographic
evidence.  Blockstates, models, and textures are read from a supplied vanilla
client JAR; no network or browser is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from array import array
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


DIRECTIONS: Mapping[str, tuple[int, int, int]] = {
    "down": (0, -1, 0),
    "up": (0, 1, 0),
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "west": (-1, 0, 0),
    "east": (1, 0, 0),
}
AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


@dataclass(frozen=True)
class BlockState:
    name: str
    properties: Mapping[str, str]


@dataclass(frozen=True)
class ModelApplication:
    model: str
    x: int = 0
    y: int = 0
    uvlock: bool = False


@dataclass
class Mesh:
    batches: dict[tuple[str, tuple[float, float, float]], array]
    blocks: int
    quads: int


def resource_location(value: str, default_namespace: str = "minecraft") -> tuple[str, str]:
    if ":" in value:
        namespace, path = value.split(":", 1)
    else:
        namespace, path = default_namespace, value
    if not namespace or not path or ".." in path.split("/"):
        raise ValueError(f"invalid resource location: {value!r}")
    return namespace, path


def parse_vec3(values: Sequence[str | float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise argparse.ArgumentTypeError("expected three coordinates")
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def load_sample(path: Path) -> tuple[np.ndarray, np.ndarray, list[BlockState]]:
    with np.load(path, allow_pickle=False) as sample:
        missing = {"coords", "state_ids", "palette_json"} - set(sample.files)
        if missing:
            raise ValueError(f"sample is missing arrays: {sorted(missing)}")
        coords = np.asarray(sample["coords"], dtype=np.int32)
        state_ids = np.asarray(sample["state_ids"])
        raw_palette = sample["palette_json"]
        if raw_palette.shape != ():
            raise ValueError("palette_json must be a scalar JSON string")
        palette_text = raw_palette.item()
        if isinstance(palette_text, bytes):
            palette_text = palette_text.decode("utf-8")
        palette_payload = json.loads(str(palette_text))

    if coords.ndim != 2 or coords.shape[1] != 3:
        raise ValueError(f"coords must have shape (N, 3), got {coords.shape}")
    if state_ids.ndim != 1 or len(state_ids) != len(coords):
        raise ValueError("state_ids must have shape (N,) matching coords")
    if state_ids.dtype.kind not in "ui":
        raise ValueError("state_ids must be an unsigned or signed integer array")
    if not isinstance(palette_payload, list) or not palette_payload:
        raise ValueError("palette_json must contain a non-empty list")

    palette: list[BlockState] = []
    for index, entry in enumerate(palette_payload):
        if not isinstance(entry, Mapping) or not entry.get("Name"):
            raise ValueError(f"palette entry {index} has no Name")
        properties = entry.get("Properties") or {}
        if not isinstance(properties, Mapping):
            raise ValueError(f"palette entry {index} Properties is not an object")
        palette.append(
            BlockState(
                str(entry["Name"]).lower(),
                {str(key): str(value).lower() for key, value in properties.items()},
            )
        )
    if len(state_ids) and (int(state_ids.min()) < 0 or int(state_ids.max()) >= len(palette)):
        raise ValueError("state_ids contains a palette index outside palette_json")
    if len(coords) != len({tuple(int(value) for value in row) for row in coords}):
        raise ValueError("coords contains duplicate block positions")
    return coords, state_ids.astype(np.uint32, copy=False), palette


class VanillaResources:
    def __init__(self, jar: Path):
        self.jar_path = jar
        self.archive = zipfile.ZipFile(jar)
        self._json_cache: dict[str, dict[str, Any]] = {}
        self._model_cache: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self.archive.close()

    def __enter__(self) -> "VanillaResources":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def read_json(self, archive_path: str) -> dict[str, Any]:
        if archive_path not in self._json_cache:
            try:
                raw = self.archive.read(archive_path)
            except KeyError as exc:
                raise FileNotFoundError(
                    f"resource {archive_path!r} is absent from {self.jar_path}"
                ) from exc
            self._json_cache[archive_path] = json.loads(raw)
        return self._json_cache[archive_path]

    def blockstate(self, block_name: str) -> dict[str, Any]:
        namespace, name = resource_location(block_name)
        return self.read_json(f"assets/{namespace}/blockstates/{name}.json")

    def model(self, model_name: str, stack: tuple[str, ...] = ()) -> dict[str, Any]:
        namespace, name = resource_location(model_name)
        canonical = f"{namespace}:{name}"
        if canonical in self._model_cache:
            return self._model_cache[canonical]
        if canonical in stack:
            raise ValueError(f"cyclic model inheritance: {' -> '.join((*stack, canonical))}")
        child = self.read_json(f"assets/{namespace}/models/{name}.json")
        parent_name = child.get("parent")
        if parent_name:
            parent_namespace, parent_path = resource_location(str(parent_name), namespace)
            parent = self.model(
                f"{parent_namespace}:{parent_path}", (*stack, canonical)
            )
            merged = dict(parent)
            textures = dict(parent.get("textures") or {})
            textures.update(child.get("textures") or {})
            merged.update(child)
            if textures:
                merged["textures"] = textures
            if "elements" not in child and "elements" in parent:
                merged["elements"] = parent["elements"]
        else:
            merged = dict(child)
        merged["_namespace"] = namespace
        self._model_cache[canonical] = merged
        return merged

    def texture_png(self, texture_name: str, default_namespace: str = "minecraft") -> bytes:
        namespace, name = resource_location(texture_name, default_namespace)
        archive_path = f"assets/{namespace}/textures/{name}.png"
        try:
            return self.archive.read(archive_path)
        except KeyError as exc:
            raise FileNotFoundError(
                f"texture {archive_path!r} is absent from {self.jar_path}"
            ) from exc


def variant_matches(key: str, properties: Mapping[str, str]) -> bool:
    if not key:
        return True
    for assignment in key.split(","):
        if assignment.count("=") != 1:
            raise ValueError(f"invalid blockstate variant key: {key!r}")
        name, expected = assignment.split("=", 1)
        actual = properties.get(name)
        alternatives = expected.split("|")
        if any(value.startswith("!") for value in alternatives):
            rejected = {value[1:] for value in alternatives if value.startswith("!")}
            if actual is None or actual in rejected:
                return False
        elif actual not in alternatives:
            return False
    return True


def variant_compatible_with_omitted_defaults(
    key: str, properties: Mapping[str, str]
) -> bool:
    """Accept a variant when every explicitly serialized property agrees.

    Minecraft's default state may be serialized with no Properties compound by
    generated samples (for example grass_block omits snowy=false).  In that
    case the first compatible variant in vanilla JSON is the default fallback.
    """

    if not key:
        return True
    for assignment in key.split(","):
        if assignment.count("=") != 1:
            raise ValueError(f"invalid blockstate variant key: {key!r}")
        name, expected = assignment.split("=", 1)
        if name not in properties:
            continue
        if not variant_matches(f"{name}={expected}", properties):
            return False
    return True


def condition_matches(condition: Any, properties: Mapping[str, str]) -> bool:
    if not condition:
        return True
    if isinstance(condition, list):
        return all(condition_matches(item, properties) for item in condition)
    if not isinstance(condition, Mapping):
        raise ValueError(f"invalid multipart condition: {condition!r}")
    if "OR" in condition:
        return any(condition_matches(item, properties) for item in condition["OR"])
    if "AND" in condition:
        return all(condition_matches(item, properties) for item in condition["AND"])
    return all(variant_matches(f"{key}={value}", properties) for key, value in condition.items())


def stable_choice(options: Any, coordinate: tuple[int, int, int], salt: str) -> Mapping[str, Any]:
    if isinstance(options, Mapping):
        return options
    if not isinstance(options, list) or not options:
        raise ValueError(f"invalid model application: {options!r}")
    weights = [max(1, int(option.get("weight", 1))) for option in options]
    digest = hashlib.blake2b(
        f"{coordinate[0]},{coordinate[1]},{coordinate[2]}:{salt}".encode(), digest_size=8
    ).digest()
    pick = int.from_bytes(digest, "little") % sum(weights)
    for option, weight in zip(options, weights):
        if pick < weight:
            return option
        pick -= weight
    return options[-1]


def parse_application(payload: Mapping[str, Any]) -> ModelApplication:
    if not payload.get("model"):
        raise ValueError(f"model application has no model: {payload!r}")
    x = int(payload.get("x", 0)) % 360
    y = int(payload.get("y", 0)) % 360
    if x % 90 or y % 90:
        raise ValueError(f"blockstate rotations must be multiples of 90: {payload!r}")
    return ModelApplication(str(payload["model"]), x, y, bool(payload.get("uvlock", False)))


def applications_for_state(
    definition: Mapping[str, Any],
    properties: Mapping[str, str],
    coordinate: tuple[int, int, int],
) -> list[ModelApplication]:
    applications: list[ModelApplication] = []
    variants = definition.get("variants")
    if variants is not None:
        matches = [
            (key, value)
            for key, value in variants.items()
            if variant_matches(str(key), properties)
        ]
        if not matches:
            matches = [
                (key, value)
                for key, value in variants.items()
                if variant_compatible_with_omitted_defaults(str(key), properties)
            ]
        if not matches:
            raise ValueError(f"no blockstate variant matches properties {dict(properties)!r}")
        key, value = max(matches, key=lambda pair: pair[0].count("=") if pair[0] else 0)
        applications.append(parse_application(stable_choice(value, coordinate, f"variant:{key}")))
    for index, part in enumerate(definition.get("multipart") or []):
        if condition_matches(part.get("when"), properties):
            applications.append(
                parse_application(
                    stable_choice(part.get("apply"), coordinate, f"multipart:{index}")
                )
            )
    if not applications:
        raise ValueError(f"blockstate definition selects no models for {dict(properties)!r}")
    return applications


def rotate_x(point: tuple[float, float, float], degrees: float) -> tuple[float, float, float]:
    x, y, z = point
    radians = math.radians(degrees)
    cosine, sine = round(math.cos(radians), 12), round(math.sin(radians), 12)
    return x, y * cosine - z * sine, y * sine + z * cosine


def rotate_y(point: tuple[float, float, float], degrees: float) -> tuple[float, float, float]:
    x, y, z = point
    radians = math.radians(degrees)
    cosine, sine = round(math.cos(radians), 12), round(math.sin(radians), 12)
    return x * cosine - z * sine, y, x * sine + z * cosine


def rotate_z(point: tuple[float, float, float], degrees: float) -> tuple[float, float, float]:
    x, y, z = point
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return x * cosine - y * sine, x * sine + y * cosine, z


def rotate_about(
    point: tuple[float, float, float],
    origin: tuple[float, float, float],
    axis: str,
    degrees: float,
    rescale: bool = False,
) -> tuple[float, float, float]:
    shifted = tuple(point[index] - origin[index] for index in range(3))
    if rescale:
        factor = 1.0 / math.cos(math.radians(abs(degrees)))
        scales = {
            "x": (1.0, factor, factor),
            "y": (factor, 1.0, factor),
            "z": (factor, factor, 1.0),
        }[axis]
        shifted = tuple(shifted[index] * scales[index] for index in range(3))
    if axis == "x":
        rotated = rotate_x(shifted, degrees)
    elif axis == "y":
        rotated = rotate_y(shifted, degrees)
    elif axis == "z":
        rotated = rotate_z(shifted, degrees)
    else:
        raise ValueError(f"invalid element rotation axis: {axis!r}")
    return tuple(rotated[index] + origin[index] for index in range(3))  # type: ignore[return-value]


def rotate_model_point(
    point: tuple[float, float, float], application: ModelApplication
) -> tuple[float, float, float]:
    centered = tuple(value - 8.0 for value in point)
    centered = rotate_x(centered, application.x)
    centered = rotate_y(centered, application.y)
    return tuple(value + 8.0 for value in centered)  # type: ignore[return-value]


def rotate_direction(direction: str, application: ModelApplication) -> str:
    vector = tuple(float(value) for value in DIRECTIONS[direction])
    vector = rotate_x(vector, application.x)
    vector = rotate_y(vector, application.y)
    rounded = tuple(int(round(value)) for value in vector)
    return next(name for name, candidate in DIRECTIONS.items() if candidate == rounded)


def face_corners(
    direction: str, start: Sequence[float], end: Sequence[float]
) -> list[tuple[float, float, float]]:
    x1, y1, z1 = start
    x2, y2, z2 = end
    return {
        "north": [(x1, y1, z1), (x1, y2, z1), (x2, y2, z1), (x2, y1, z1)],
        "south": [(x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2)],
        "west": [(x1, y1, z1), (x1, y1, z2), (x1, y2, z2), (x1, y2, z1)],
        "east": [(x2, y1, z1), (x2, y2, z1), (x2, y2, z2), (x2, y1, z2)],
        "down": [(x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2)],
        "up": [(x1, y2, z1), (x1, y2, z2), (x2, y2, z2), (x2, y2, z1)],
    }[direction]


def default_uv(direction: str, start: Sequence[float], end: Sequence[float]) -> list[float]:
    x1, y1, z1 = start
    x2, y2, z2 = end
    return {
        "down": [x1, 16 - z2, x2, 16 - z1],
        "up": [x1, z1, x2, z2],
        "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
        "south": [x1, 16 - y2, x2, 16 - y1],
        "west": [z1, 16 - y2, z2, 16 - y1],
        "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1],
    }[direction]


def face_uvs(rectangle: Sequence[float], rotation: int = 0, direction: str = "north") -> list[tuple[float, float]]:
    if len(rectangle) != 4:
        raise ValueError(f"face UV must contain four numbers: {rectangle!r}")
    u1, v1, u2, v2 = (float(value) / 16.0 for value in rectangle)
    values = [(u1, v2), (u1, v1), (u2, v1), (u2, v2)]
    if direction in {"south", "west"}:
        values = [(u1, v2), (u2, v2), (u2, v1), (u1, v1)]
    steps = (rotation % 360) // 90
    return values[steps:] + values[:steps]


def resolve_texture(model: Mapping[str, Any], reference: str) -> str:
    textures = model.get("textures") or {}
    value = reference
    seen: set[str] = set()
    while value.startswith("#"):
        key = value[1:]
        if key in seen or key not in textures:
            raise ValueError(f"unresolved or cyclic texture reference {reference!r}")
        seen.add(key)
        entry = textures[key]
        # 26.1.2 can wrap a sprite with render metadata (for example glass).
        # Preserve reference resolution instead of stringifying that object.
        value = entry.get("sprite") if isinstance(entry, Mapping) else entry
        if not isinstance(value, str) or not value:
            raise ValueError(f"invalid texture entry for {key!r}: {entry!r}")
    namespace, path = resource_location(value, str(model.get("_namespace") or "minecraft"))
    return f"{namespace}:{path}"


def tint_for(block: BlockState, face: Mapping[str, Any]) -> tuple[float, float, float]:
    if "tintindex" not in face:
        return 1.0, 1.0, 1.0
    name = block.name
    if "water" in name:
        return 0.247, 0.463, 0.894
    if "leaves" in name or "vine" in name:
        return 0.345, 0.553, 0.255
    return 0.42, 0.67, 0.27


def transformed_element_corners(
    corners: Iterable[tuple[float, float, float]],
    element: Mapping[str, Any],
    application: ModelApplication,
) -> list[tuple[float, float, float]]:
    transformed = list(corners)
    rotation = element.get("rotation")
    if rotation:
        origin = tuple(float(value) for value in rotation.get("origin", (8, 8, 8)))
        transformed = [
            rotate_about(
                point,
                origin,  # type: ignore[arg-type]
                str(rotation["axis"]),
                float(rotation["angle"]),
                bool(rotation.get("rescale", False)),
            )
            for point in transformed
        ]
    return [rotate_model_point(point, application) for point in transformed]


def normal_for(corners: Sequence[tuple[float, float, float]]) -> tuple[float, float, float]:
    first = tuple(corners[1][i] - corners[0][i] for i in range(3))
    second = tuple(corners[2][i] - corners[0][i] for i in range(3))
    cross = (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )
    length = math.sqrt(sum(value * value for value in cross))
    if length <= 1e-12:
        return 0.0, 1.0, 0.0
    return tuple(value / length for value in cross)  # type: ignore[return-value]


def state_is_opaque_cube(
    resources: VanillaResources,
    state: BlockState,
) -> bool:
    if any(part in state.name for part in ("air", "glass", "ice", "leaves", "pane", "water")):
        return False
    applications = applications_for_state(
        resources.blockstate(state.name), state.properties, (0, 0, 0)
    )
    if len(applications) != 1:
        return False
    model = resources.model(applications[0].model)
    elements = elements_for_state(model, state)
    if len(elements) != 1:
        return False
    element = elements[0]
    return (
        element.get("from") == [0, 0, 0]
        and element.get("to") == [16, 16, 16]
        and not element.get("rotation")
        and set((element.get("faces") or {}).keys()) == set(DIRECTIONS)
    )


def elements_for_state(model: Mapping[str, Any], state: BlockState) -> list[Mapping[str, Any]]:
    elements = model.get("elements") or []
    if elements:
        return list(elements)
    if state.name == "minecraft:water":
        raw_level = int(state.properties.get("level", "0"))
        height = 15.0 if raw_level == 0 or raw_level >= 8 else max(2.0, 16.0 - 2.0 * raw_level)
        return [
            {
                "from": [0, 0, 0],
                "to": [16, height, 16],
                "shade": False,
                "faces": {
                    direction: {"texture": "minecraft:block/water_still"}
                    for direction in DIRECTIONS
                },
            }
        ]
    raise ValueError(
        f"block {state.name} uses a non-model renderer unsupported by this diagnostic"
    )


def build_mesh(
    resources: VanillaResources,
    coords: np.ndarray,
    state_ids: np.ndarray,
    palette: Sequence[BlockState],
    origin: tuple[float, float, float],
) -> Mesh:
    occupied = {
        tuple(int(value) for value in coordinate): int(state_id)
        for coordinate, state_id in zip(coords, state_ids)
        if palette[int(state_id)].name not in AIR_BLOCKS
    }
    opaque = [False] * len(palette)
    for state_id in set(occupied.values()):
        opaque[state_id] = state_is_opaque_cube(resources, palette[state_id])
    batches: dict[tuple[str, tuple[float, float, float]], array] = {}
    quad_count = 0

    for coordinate, state_id in occupied.items():
        state = palette[state_id]
        definition = resources.blockstate(state.name)
        applications = applications_for_state(definition, state.properties, coordinate)
        for application in applications:
            model = resources.model(application.model)
            for element in elements_for_state(model, state):
                start = element.get("from")
                end = element.get("to")
                if not start or not end:
                    continue
                for direction, face in (element.get("faces") or {}).items():
                    cullface = face.get("cullface")
                    if cullface:
                        world_direction = rotate_direction(str(cullface), application)
                        delta = DIRECTIONS[world_direction]
                        neighbor = tuple(coordinate[i] + delta[i] for i in range(3))
                        neighbor_state_id = occupied.get(neighbor)
                        if neighbor_state_id is not None and opaque[neighbor_state_id]:
                            continue
                    corners = transformed_element_corners(
                        face_corners(str(direction), start, end), element, application
                    )
                    normal = normal_for(corners)
                    texture = resolve_texture(model, str(face["texture"]))
                    tint = tint_for(state, face)
                    batch = batches.setdefault((texture, tint), array("f"))
                    uv_rotation = int(face.get("rotation", 0))
                    if application.uvlock and direction in {"up", "down"}:
                        uv_rotation = (uv_rotation - application.y) % 360
                    uvs = face_uvs(
                        face.get("uv") or default_uv(str(direction), start, end),
                        uv_rotation,
                        str(direction),
                    )
                    world_corners = [
                        (
                            coordinate[0] + point[0] / 16.0 - origin[0],
                            coordinate[1] + point[1] / 16.0 - origin[1],
                            coordinate[2] + point[2] / 16.0 - origin[2],
                        )
                        for point in corners
                    ]
                    shade = 1.0 if element.get("shade", True) else 0.0
                    for vertex_index in (0, 1, 2, 0, 2, 3):
                        batch.extend(
                            (*world_corners[vertex_index], *normal, *uvs[vertex_index], shade)
                        )
                    quad_count += 1
    return Mesh(batches, len(occupied), quad_count)


def look_at(
    eye: tuple[float, float, float], target: tuple[float, float, float]
) -> np.ndarray:
    eye_vector = np.asarray(eye, dtype=np.float64)
    target_vector = np.asarray(target, dtype=np.float64)
    forward = target_vector - eye_vector
    length = np.linalg.norm(forward)
    if length < 1e-9:
        raise ValueError("eye and target must differ")
    forward /= length
    up = np.array((0.0, 1.0, 0.0))
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-9:
        up = np.array((0.0, 0.0, 1.0))
        right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    camera_up = np.cross(right, forward)
    view = np.identity(4, dtype=np.float64)
    view[0, :3] = right
    view[1, :3] = camera_up
    view[2, :3] = -forward
    view[:3, 3] = -view[:3, :3] @ eye_vector
    return view


def perspective(fov: float, aspect: float, near: float, far: float) -> np.ndarray:
    if not 1.0 <= fov < 179.0:
        raise ValueError("fov must be in [1, 179)")
    scale = 1.0 / math.tan(math.radians(fov) / 2.0)
    matrix = np.zeros((4, 4), dtype=np.float64)
    matrix[0, 0] = scale / aspect
    matrix[1, 1] = scale
    matrix[2, 2] = (far + near) / (near - far)
    matrix[2, 3] = 2.0 * far * near / (near - far)
    matrix[3, 2] = -1.0
    return matrix


def is_translucent_texture(texture_name: str) -> bool:
    return any(part in texture_name for part in ("glass", "water", "ice"))


def render_mesh(
    resources: VanillaResources,
    mesh: Mesh,
    output: Path,
    eye: tuple[float, float, float],
    target: tuple[float, float, float],
    width: int,
    height: int,
    fov: float,
) -> None:
    try:
        import moderngl
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "rendering requires moderngl and Pillow; run with uv --with moderngl --with pillow"
        ) from exc

    context = moderngl.create_standalone_context()
    samples = min(4, int(context.info.get("GL_MAX_SAMPLES", 1)))
    draw_target = context.simple_framebuffer((width, height), components=4, samples=samples)
    read_target = (
        context.simple_framebuffer((width, height), components=4)
        if samples > 1
        else draw_target
    )
    draw_target.use()
    context.viewport = (0, 0, width, height)
    context.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
    context.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    draw_target.clear(0.62, 0.78, 0.92, 1.0, depth=1.0)

    vertex_shader = """
        #version 330
        uniform mat4 mvp;
        in vec3 in_position;
        in vec3 in_normal;
        in vec2 in_uv;
        in float in_shade;
        out vec3 normal;
        out vec2 uv;
        out float shade;
        void main() {
            gl_Position = mvp * vec4(in_position, 1.0);
            normal = in_normal;
            uv = in_uv;
            shade = in_shade;
        }
    """
    fragment_shader = """
        #version 330
        uniform sampler2D block_texture;
        uniform vec3 tint;
        in vec3 normal;
        in vec2 uv;
        in float shade;
        out vec4 color;
        void main() {
            vec4 texel = texture(block_texture, uv);
            if (texel.a < 0.08) discard;
            vec3 sun = normalize(vec3(-0.45, 0.82, -0.35));
            float diffuse = max(dot(normalize(normal), sun), 0.0);
            float lit = mix(1.0, 0.40 + 0.60 * diffuse, shade);
            color = vec4(texel.rgb * tint * lit, texel.a);
        }
    """
    program = context.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)
    relative_eye = tuple(eye[index] - target[index] for index in range(3))
    relative_target = (0.0, 0.0, 0.0)
    camera_distance = math.sqrt(sum(value * value for value in relative_eye))
    projection = perspective(fov, width / height, 0.05, max(1024.0, camera_distance * 8.0))
    mvp = projection @ look_at(relative_eye, relative_target)
    program["mvp"].write(np.asarray(mvp.T, dtype="f4").tobytes())
    program["block_texture"].value = 0

    texture_cache: dict[str, Any] = {}

    def gl_texture(texture_name: str):
        if texture_name not in texture_cache:
            namespace, _path = resource_location(texture_name)
            image = Image.open(
                BytesIO(resources.texture_png(texture_name, namespace))
            ).convert("RGBA")
            if image.height > image.width and image.height % image.width == 0:
                image = image.crop((0, 0, image.width, image.width))
            texture = context.texture(image.size, 4, image.tobytes())
            texture.filter = moderngl.NEAREST, moderngl.NEAREST
            texture.repeat_x = False
            texture.repeat_y = False
            texture_cache[texture_name] = texture
        return texture_cache[texture_name]

    batches = sorted(mesh.batches.items(), key=lambda item: is_translucent_texture(item[0][0]))
    translucent_started = False
    for (texture_name, tint), vertices in batches:
        translucent = is_translucent_texture(texture_name)
        if translucent and not translucent_started:
            context.depth_mask = False
            translucent_started = True
        buffer = context.buffer(vertices.tobytes())
        vao = context.vertex_array(
            program,
            [(buffer, "3f 3f 2f 1f", "in_position", "in_normal", "in_uv", "in_shade")],
        )
        program["tint"].value = tint
        gl_texture(texture_name).use(location=0)
        vao.render(mode=moderngl.TRIANGLES)
        vao.release()
        buffer.release()
    context.depth_mask = True
    if read_target is not draw_target:
        context.copy_framebuffer(read_target, draw_target)
    pixels = read_target.read(components=4, alignment=1)
    image = Image.frombytes("RGBA", (width, height), pixels).transpose(
        Image.Transpose.FLIP_TOP_BOTTOM
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    for texture in texture_cache.values():
        texture.release()
    program.release()
    draw_target.release()
    if read_target is not draw_target:
        read_target.release()
    context.release()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="sample-blocks.npz")
    parser.add_argument("--output", type=Path, required=True, help="output PNG")
    parser.add_argument("--jar", type=Path, required=True, help="matching Minecraft client JAR")
    parser.add_argument("--eye", nargs=3, required=True, metavar=("X", "Y", "Z"))
    parser.add_argument("--target", nargs=3, required=True, metavar=("X", "Y", "Z"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--fov", type=float, default=65.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.width < 1 or args.height < 1:
        raise SystemExit("width and height must be positive")
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    jar_path = args.jar.resolve()
    eye = parse_vec3(args.eye)
    target = parse_vec3(args.target)
    coords, state_ids, palette = load_sample(input_path)
    with VanillaResources(jar_path) as resources:
        mesh = build_mesh(resources, coords, state_ids, palette, target)
        if mesh.blocks == 0:
            raise SystemExit("sample contains no renderable non-air blocks")
        render_mesh(resources, mesh, output_path, eye, target, args.width, args.height, args.fov)
    print(
        f"Saved textured diagnostic preview: {output_path} "
        f"({mesh.blocks} blocks, {mesh.quads} quads)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
