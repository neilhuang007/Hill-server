#!/usr/bin/env python3
"""Audit a generated Hill Chapel sample against its serialized Anvil world.

The sample NPZ is the authoritative list of intended occupied coordinates, full
Minecraft block states, and semantic roles.  This module independently reads
the Anvil region files back from disk and checks exact state parity, including
properties such as door halves, pane connections, and stair shapes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import numpy as np

import campus_materials
import hybridize_voxelearth_roofer_world as anvil


AIR_NAMES = frozenset(anvil.AIR_BLOCKS) | {"minecraft:cave_air", "minecraft:void_air"}
NON_SOLID_NAMES = AIR_NAMES | {
    "minecraft:water",
    "minecraft:lava",
    "minecraft:lantern",
    "minecraft:soul_lantern",
    "minecraft:iron_bars",
}
COORD_DTYPE = np.dtype([("x", "<i4"), ("y", "<i4"), ("z", "<i4")])


def _state_key(entry: Mapping[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    name = str(entry.get("Name", "minecraft:air"))
    raw_properties = entry.get("Properties") or {}
    properties = tuple(sorted((str(key), str(value)) for key, value in raw_properties.items()))
    return name, properties


def _state_dict(key: tuple[str, tuple[tuple[str, str], ...]]) -> dict[str, Any]:
    name, properties = key
    result: dict[str, Any] = {"Name": name}
    if properties:
        result["Properties"] = dict(properties)
    return result


def _coord_records(coords: np.ndarray) -> np.ndarray:
    records = np.empty(len(coords), dtype=COORD_DTYPE)
    records["x"] = coords[:, 0]
    records["y"] = coords[:, 1]
    records["z"] = coords[:, 2]
    return records


def _coord_list(records: np.ndarray, limit: int) -> list[list[int]]:
    return [
        [int(record["x"]), int(record["y"]), int(record["z"])]
        for record in records[:limit]
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_input_path(study_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    repo_candidate = _repo_root() / candidate
    if repo_candidate.exists():
        return repo_candidate
    return study_dir / candidate


def _read_npz(npz_path: Path) -> dict[str, Any]:
    with np.load(npz_path, allow_pickle=False) as data:
        required = {"coords", "state_ids", "role_ids", "role_names", "palette_json"}
        missing = sorted(required - set(data.files))
        if missing:
            raise ValueError(f"sample NPZ missing keys: {', '.join(missing)}")
        coords = np.asarray(data["coords"], dtype=np.int32)
        state_ids = np.asarray(data["state_ids"], dtype=np.int64)
        role_ids = np.asarray(data["role_ids"], dtype=np.int64)
        role_names = [str(value) for value in np.asarray(data["role_names"]).tolist()]
        palette = json.loads(str(np.asarray(data["palette_json"]).item()))

    if coords.ndim != 2 or coords.shape[1] != 3:
        raise ValueError(f"coords must have shape (N, 3), found {coords.shape}")
    if state_ids.shape != (len(coords),) or role_ids.shape != (len(coords),):
        raise ValueError("state_ids and role_ids must have one item per coordinate")
    if not isinstance(palette, list) or not palette:
        raise ValueError("palette_json must contain a non-empty JSON list")
    if min(state_ids, default=0) < 0 or max(state_ids, default=0) >= len(palette):
        raise ValueError("state_ids contains an index outside palette_json")
    if min(role_ids, default=0) < 0 or max(role_ids, default=0) >= len(role_names):
        raise ValueError("role_ids contains an index outside role_names")

    palette_keys = [_state_key(entry) for entry in palette]
    return {
        "coords": coords,
        "state_ids": state_ids,
        "role_ids": role_ids,
        "role_names": role_names,
        "palette_keys": palette_keys,
    }


def _read_anvil_blocks(
    world_path: Path,
) -> tuple[np.ndarray, list[tuple[str, tuple[tuple[str, str], ...]]], int]:
    """Return all non-air Anvil blocks as coordinates and exact state keys."""

    coord_parts: list[np.ndarray] = []
    state_keys: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    state_key_to_id: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
    state_id_parts: list[np.ndarray] = []
    chunk_count = 0

    for chunk_x, chunk_z, chunk_root in anvil.iter_world_chunks(world_path):
        chunk_count += 1
        sections = chunk_root.get("sections") or chunk_root.get("Sections") or []
        for section in sections:
            parsed = anvil.section_block_states(section)
            if parsed is None:
                continue
            palette, packed_data = parsed
            palette_keys = [anvil.palette_state_key(item) for item in palette]
            local_indices = np.asarray(
                anvil.unpack_indices(len(palette), packed_data), dtype=np.int64
            )

            registry_ids = np.empty(len(palette_keys), dtype=np.int64)
            for index, state_key in enumerate(palette_keys):
                state_id = state_key_to_id.get(state_key)
                if state_id is None:
                    state_id = len(state_keys)
                    state_key_to_id[state_key] = state_id
                    state_keys.append(state_key)
                registry_ids[index] = state_id

            names = np.asarray([key[0] for key in palette_keys], dtype=object)
            non_air_palette = np.asarray([name not in AIR_NAMES for name in names], dtype=bool)
            occupied = non_air_palette[local_indices]
            if not np.any(occupied):
                continue

            flat = np.flatnonzero(occupied)
            local_y = flat // 256
            remainder = flat % 256
            local_z = remainder // 16
            local_x = remainder % 16
            section_y = int(section["Y"])
            coords = np.column_stack(
                (
                    chunk_x * 16 + local_x,
                    section_y * 16 + local_y,
                    chunk_z * 16 + local_z,
                )
            ).astype(np.int32, copy=False)
            coord_parts.append(coords)
            state_id_parts.append(registry_ids[local_indices[flat]])

    if coord_parts:
        coords = np.concatenate(coord_parts, axis=0)
        state_ids = np.concatenate(state_id_parts, axis=0)
    else:
        coords = np.empty((0, 3), dtype=np.int32)
        state_ids = np.empty(0, dtype=np.int64)
    # Store Anvil state ids as an extra synthetic component on the returned array.
    combined = np.empty((len(coords), 4), dtype=np.int64)
    combined[:, :3] = coords
    combined[:, 3] = state_ids
    return combined, state_keys, chunk_count


def _count_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _manifest_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): int(count) for key, count in value.items() if int(count) != 0}


def _solid_support_name(name: str) -> bool:
    if name in NON_SOLID_NAMES:
        return False
    if name.endswith(("_door", "_pane", "_stairs", "_slab", "_trapdoor", "_fence")):
        return False
    return True


def _pane_attaches_to_name(name: str | None) -> bool:
    """Approximate the horizontal face test used by vanilla glass panes."""

    if name is None:
        return False
    # Vanilla 26.1.2 IronBarsBlock#attachsTo accepts another IronBarsBlock
    # (glass panes or iron bars), BlockTags.WALLS, or a neighbour whose face
    # toward the pane is sturdy.  Chapel full cubes satisfy the final case;
    # partial blocks and leaves do not.
    if name.endswith("_pane") or name == "minecraft:iron_bars":
        return True
    if name.endswith("_wall"):
        return True
    return not name.endswith("_leaves") and _solid_support_name(name)


class _ExpectedGrid:
    """Compact dense lookup for expected occupied blocks in the sample bounds."""

    def __init__(
        self,
        coords: np.ndarray,
        state_ids: np.ndarray,
        role_ids: np.ndarray,
        palette_keys: Sequence[tuple[str, tuple[tuple[str, str], ...]]],
    ) -> None:
        if not len(coords):
            raise ValueError("sample NPZ contains no occupied coordinates")
        self.minimum = coords.min(axis=0).astype(np.int64)
        self.maximum = coords.max(axis=0).astype(np.int64)
        span = self.maximum - self.minimum + 1
        # Array order is y, z, x to match Minecraft section conventions.
        self.state = np.full((int(span[1]), int(span[2]), int(span[0])), -1, dtype=np.int32)
        self.role = np.full_like(self.state, -1)
        indexes = coords.astype(np.int64) - self.minimum
        self.state[indexes[:, 1], indexes[:, 2], indexes[:, 0]] = state_ids
        self.role[indexes[:, 1], indexes[:, 2], indexes[:, 0]] = role_ids
        self.palette_keys = palette_keys

    def state_id(self, x: int, y: int, z: int) -> int:
        if (
            x < self.minimum[0]
            or y < self.minimum[1]
            or z < self.minimum[2]
            or x > self.maximum[0]
            or y > self.maximum[1]
            or z > self.maximum[2]
        ):
            return -1
        return int(self.state[y - self.minimum[1], z - self.minimum[2], x - self.minimum[0]])

    def key(self, x: int, y: int, z: int) -> tuple[str, tuple[tuple[str, str], ...]] | None:
        state_id = self.state_id(x, y, z)
        return self.palette_keys[state_id] if state_id >= 0 else None

    def role_id(self, x: int, y: int, z: int) -> int:
        if (
            x < self.minimum[0]
            or y < self.minimum[1]
            or z < self.minimum[2]
            or x > self.maximum[0]
            or y > self.maximum[1]
            or z > self.maximum[2]
        ):
            return -1
        return int(self.role[y - self.minimum[1], z - self.minimum[2], x - self.minimum[0]])

    def solid(self, x: int, y: int, z: int) -> bool:
        key = self.key(x, y, z)
        return key is not None and _solid_support_name(key[0])


def _audit_exact_parity(
    expected_coords: np.ndarray,
    expected_state_ids: np.ndarray,
    expected_keys: Sequence[tuple[str, tuple[tuple[str, str], ...]]],
    actual_combined: np.ndarray,
    actual_keys: Sequence[tuple[str, tuple[tuple[str, str], ...]]],
    max_examples: int,
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    expected_records = _coord_records(expected_coords)
    actual_coords = actual_combined[:, :3].astype(np.int32, copy=False)
    actual_records = _coord_records(actual_coords)

    expected_unique, expected_counts = np.unique(expected_records, return_counts=True)
    actual_unique, actual_counts = np.unique(actual_records, return_counts=True)
    duplicate_expected = expected_unique[expected_counts > 1]
    duplicate_actual = actual_unique[actual_counts > 1]
    if len(duplicate_expected):
        violations.append(f"NPZ has {len(duplicate_expected)} duplicate occupied coordinates")
    if len(duplicate_actual):
        violations.append(f"Anvil has {len(duplicate_actual)} duplicate occupied coordinates")

    common, expected_index, actual_index = np.intersect1d(
        expected_records, actual_records, assume_unique=False, return_indices=True
    )
    missing = np.setdiff1d(expected_records, actual_records, assume_unique=False)
    extra = np.setdiff1d(actual_records, expected_records, assume_unique=False)

    registry: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
    for key in list(expected_keys) + list(actual_keys):
        registry.setdefault(key, len(registry))
    expected_registry_ids = np.asarray([registry[key] for key in expected_keys], dtype=np.int64)
    actual_registry_ids = np.asarray([registry[key] for key in actual_keys], dtype=np.int64)
    expected_common_states = expected_registry_ids[expected_state_ids[expected_index]]
    actual_common_states = actual_registry_ids[actual_combined[actual_index, 3]]
    state_mismatch_mask = expected_common_states != actual_common_states
    mismatch_indexes = np.flatnonzero(state_mismatch_mask)

    if len(missing):
        violations.append(f"Anvil is missing {len(missing)} NPZ occupied coordinates")
    if len(extra):
        violations.append(f"Anvil has {len(extra)} extra occupied coordinates")
    if len(mismatch_indexes):
        violations.append(f"Anvil has {len(mismatch_indexes)} full-state mismatches")

    mismatch_examples: list[dict[str, Any]] = []
    for mismatch_index in mismatch_indexes[:max_examples]:
        record = common[mismatch_index]
        expected_key = expected_keys[int(expected_state_ids[expected_index[mismatch_index]])]
        actual_key = actual_keys[int(actual_combined[actual_index[mismatch_index], 3])]
        mismatch_examples.append(
            {
                "coord": [int(record["x"]), int(record["y"]), int(record["z"])],
                "expected": _state_dict(expected_key),
                "actual": _state_dict(actual_key),
            }
        )

    result = {
        "expected_occupied": int(len(expected_coords)),
        "anvil_occupied": int(len(actual_coords)),
        "common_coordinates": int(len(common)),
        "missing_count": int(len(missing)),
        "extra_count": int(len(extra)),
        "state_mismatch_count": int(len(mismatch_indexes)),
        "duplicate_npz_coordinate_count": int(len(duplicate_expected)),
        "duplicate_anvil_coordinate_count": int(len(duplicate_actual)),
        "missing_examples": _coord_list(missing, max_examples),
        "extra_examples": _coord_list(extra, max_examples),
        "state_mismatch_examples": mismatch_examples,
    }
    return result, violations


def _audit_counts_and_roles(
    manifest: Mapping[str, Any],
    state_ids: np.ndarray,
    role_ids: np.ndarray,
    role_names: Sequence[str],
    palette_keys: Sequence[tuple[str, tuple[tuple[str, str], ...]]],
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    material_counts: Counter[str] = Counter()
    role_material_counts: dict[str, Counter[str]] = defaultdict(Counter)
    role_material_sets: dict[str, set[str]] = defaultdict(set)
    state_counts: Counter[str] = Counter()

    used_state_ids = set(int(value) for value in np.unique(state_ids))
    duplicate_palette_count = len(palette_keys) - len(set(palette_keys))
    unused_non_air_palette_ids = {
        state_id
        for state_id, state_key in enumerate(palette_keys)
        if state_id not in used_state_ids and state_key[0] not in AIR_NAMES
    }
    unused_palette_count = len(unused_non_air_palette_ids)
    occupied_air_count = sum(
        int(np.count_nonzero(state_ids == state_id))
        for state_id in used_state_ids
        if palette_keys[state_id][0] in AIR_NAMES
    )
    if duplicate_palette_count:
        violations.append(f"NPZ palette has {duplicate_palette_count} duplicate full states")
    if occupied_air_count:
        violations.append(f"NPZ lists {occupied_air_count} air states as occupied coordinates")

    if np.any(role_ids == 0):
        violations.append(f"{int(np.count_nonzero(role_ids == 0))} occupied blocks have the air role")

    for state_id, role_id in zip(state_ids.tolist(), role_ids.tolist()):
        state_key = palette_keys[int(state_id)]
        name = state_key[0]
        role = role_names[int(role_id)]
        material_counts[name] += 1
        role_material_counts[role][name] += 1
        role_material_sets[role].add(name)
        state_counts[json.dumps(_state_dict(state_key), sort_keys=True, separators=(",", ":"))] += 1

    manifest_materials = _manifest_counts(manifest.get("materials"))
    recomputed_materials = _count_dict(material_counts)
    if manifest_materials != recomputed_materials:
        violations.append("manifest material counts do not equal NPZ material counts")

    manifest_roles_raw = manifest.get("material_roles")
    manifest_roles = (
        {
            str(role): _manifest_counts(counts)
            for role, counts in manifest_roles_raw.items()
            if _manifest_counts(counts)
        }
        if isinstance(manifest_roles_raw, Mapping)
        else {}
    )
    recomputed_roles = {
        role: _count_dict(counts)
        for role, counts in sorted(role_material_counts.items())
        if counts
    }
    if manifest_roles != recomputed_roles:
        violations.append("manifest role/material counts do not equal NPZ role/material counts")

    forbidden: list[dict[str, str]] = []
    for name in sorted(material_counts):
        reason = campus_materials.forbidden_reason(name)
        if reason:
            forbidden.append({"material": name, "reason": reason})
    if forbidden:
        violations.append(f"{len(forbidden)} globally forbidden materials are occupied")

    role_violations = campus_materials.audit_role_materials(role_material_sets)
    if role_violations:
        violations.append(f"{len(role_violations)} semantic role/material violations")

    manifest_audit = manifest.get("material_audit")
    if not isinstance(manifest_audit, list) or manifest_audit:
        violations.append("manifest material_audit is missing or non-empty")

    canonical_state_counts = json.dumps(
        _count_dict(state_counts), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return (
        {
            "materials_match_manifest": manifest_materials == recomputed_materials,
            "roles_match_manifest": manifest_roles == recomputed_roles,
            "recomputed_materials": recomputed_materials,
            "recomputed_material_roles": recomputed_roles,
            "full_state_variant_count": int(len(state_counts)),
            "full_state_counts_sha256": hashlib.sha256(canonical_state_counts).hexdigest(),
            "npz_palette_entry_count": int(len(palette_keys)),
            "npz_used_state_count": int(len(used_state_ids)),
            "duplicate_palette_count": int(duplicate_palette_count),
            "unused_palette_count": int(unused_palette_count),
            "occupied_air_count": int(occupied_air_count),
            "forbidden_materials": forbidden,
            "role_violations": role_violations,
        },
        violations,
    )


def _audit_doors_and_entrances(
    coords: np.ndarray,
    state_ids: np.ndarray,
    role_ids: np.ndarray,
    role_names: Sequence[str],
    palette_keys: Sequence[tuple[str, tuple[tuple[str, str], ...]]],
    grid: _ExpectedGrid,
    max_examples: int,
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    errors: list[dict[str, Any]] = []
    door_rows: list[int] = []
    for index, (state_id, role_id) in enumerate(zip(state_ids.tolist(), role_ids.tolist())):
        name = palette_keys[int(state_id)][0]
        role = role_names[int(role_id)]
        if name.endswith("_door") or role == "door":
            door_rows.append(index)
            if not name.endswith("_door") or role != "door":
                errors.append(
                    {
                        "coord": coords[index].astype(int).tolist(),
                        "problem": "door state and door role disagree",
                    }
                )

    lower_count = 0
    upper_count = 0
    entrance_clearance_failures = 0
    facing_counts: Counter[str] = Counter()
    checked_pair_origins: set[tuple[int, int, int]] = set()

    for index in door_rows:
        x, y, z = (int(value) for value in coords[index])
        key = palette_keys[int(state_ids[index])]
        name, property_items = key
        properties = dict(property_items)
        required = {"half", "facing", "hinge", "open", "powered"}
        missing_properties = sorted(required - properties.keys())
        if missing_properties:
            errors.append(
                {
                    "coord": [x, y, z],
                    "problem": f"door is missing properties: {', '.join(missing_properties)}",
                }
            )
            continue

        half = properties["half"]
        if half == "lower":
            lower_count += 1
            origin = (x, y, z)
            counterpart = grid.key(x, y + 1, z)
            support_ok = grid.solid(x, y - 1, z)
        elif half == "upper":
            upper_count += 1
            origin = (x, y - 1, z)
            counterpart = grid.key(x, y - 1, z)
            support_ok = True
        else:
            errors.append({"coord": [x, y, z], "problem": f"invalid door half {half!r}"})
            continue

        if origin not in checked_pair_origins:
            checked_pair_origins.add(origin)
        expected_other_half = "upper" if half == "lower" else "lower"
        counterpart_ok = counterpart is not None and counterpart[0] == name
        if counterpart_ok:
            other_properties = dict(counterpart[1])
            counterpart_ok = other_properties.get("half") == expected_other_half and all(
                other_properties.get(prop) == properties.get(prop)
                for prop in ("facing", "hinge", "open", "powered")
            )
        if not counterpart_ok:
            errors.append({"coord": [x, y, z], "problem": "door half has no matching counterpart"})
        if half == "lower" and not support_ok:
            errors.append({"coord": [x, y, z], "problem": "lower door lacks solid full-block support"})

        if half != "lower":
            continue
        facing = properties["facing"]
        facing_counts[facing] += 1
        direction = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}.get(
            facing
        )
        if direction is None:
            errors.append({"coord": [x, y, z], "problem": f"invalid door facing {facing!r}"})
            continue
        dx, dz = direction
        passage_ok = True
        # Check both exterior and interior foot/head spaces.  The door blocks
        # themselves form the native two-block entrance and are checked above.
        for side in (-1, 1):
            px, pz = x + dx * side, z + dz * side
            if grid.key(px, y, pz) is not None or grid.key(px, y + 1, pz) is not None:
                passage_ok = False
            if not grid.solid(px, y - 1, pz):
                passage_ok = False
        if not passage_ok:
            entrance_clearance_failures += 1
            errors.append(
                {
                    "coord": [x, y, z],
                    "problem": "entrance lacks clear two-block exterior/interior passage with support",
                }
            )

    if lower_count != upper_count:
        errors.append(
            {
                "problem": "door lower/upper counts differ",
                "lower_count": lower_count,
                "upper_count": upper_count,
            }
        )
    missing_facings = sorted({"south", "east"} - set(facing_counts))
    if missing_facings:
        errors.append({"problem": "required entrance facing is absent", "facings": missing_facings})
    if errors:
        violations.append(f"{len(errors)} door or entrance structural violations")

    return (
        {
            "door_block_count": int(len(door_rows)),
            "lower_count": int(lower_count),
            "upper_count": int(upper_count),
            "pair_origin_count": int(len(checked_pair_origins)),
            "facing_counts": _count_dict(facing_counts),
            "entrance_clearance_failure_count": int(entrance_clearance_failures),
            "error_count": int(len(errors)),
            "error_examples": errors[:max_examples],
        },
        violations,
    )


def _audit_foundations(
    manifest: Mapping[str, Any],
    coords: np.ndarray,
    role_ids: np.ndarray,
    role_names: Sequence[str],
    grid: _ExpectedGrid,
    max_examples: int,
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    bounds = manifest.get("bounds")
    if not isinstance(bounds, list) or len(bounds) != 6:
        return (
            {"floor_cell_count": 0, "unsupported_count": 0, "examples": []},
            ["manifest bounds are missing; original foundation base is unknown"],
        )
    base_y = int(bounds[1])
    floor_role_ids = {index for index, name in enumerate(role_names) if name == "floor"}
    structural_support_role_ids = {
        index
        for index, name in enumerate(role_names)
        if name in {"terrain", "pavement", "facade", "trim", "floor"}
    }
    floor_mask = np.isin(role_ids, list(floor_role_ids))
    floor_coords = coords[floor_mask]
    unsupported: list[dict[str, Any]] = []

    for raw_x, raw_y, raw_z in floor_coords:
        x, y, z = int(raw_x), int(raw_y), int(raw_z)
        first_gap: int | None = None
        if y <= base_y:
            first_gap = base_y
        else:
            for support_y in range(base_y, y):
                if (
                    not grid.solid(x, support_y, z)
                    or grid.role_id(x, support_y, z) not in structural_support_role_ids
                ):
                    first_gap = support_y
                    break
        if first_gap is not None:
            unsupported.append({"floor_coord": [x, y, z], "first_gap_y": first_gap})

    if unsupported:
        violations.append(f"{len(unsupported)} structural floor cells lack continuous support to base y={base_y}")
    return (
        {
            "base_y": base_y,
            "floor_cell_count": int(len(floor_coords)),
            "unsupported_count": int(len(unsupported)),
            "examples": unsupported[:max_examples],
        },
        violations,
    )


def _audit_architectural_clearance(
    coords: np.ndarray,
    state_ids: np.ndarray,
    role_ids: np.ndarray,
    role_names: Sequence[str],
    palette_keys: Sequence[tuple[str, tuple[tuple[str, str], ...]]],
    grid: _ExpectedGrid,
    max_examples: int,
) -> tuple[dict[str, Any], list[str]]:
    """Check native pane topology, window exposure, and local door traversal."""

    violations: list[str] = []
    occupied: dict[tuple[int, int, int], tuple[int, int]] = {
        tuple(int(value) for value in coord): (int(state_id), int(role_id))
        for coord, state_id, role_id in zip(coords, state_ids, role_ids)
    }
    window_coords = {
        coord
        for coord, (state_id, role_id) in occupied.items()
        if role_names[role_id] == "window" and palette_keys[state_id][0].endswith("_pane")
    }

    connection_errors: list[dict[str, Any]] = []
    # Positive directions visit every horizontal pane pair exactly once.
    for x, y, z in sorted(window_coords):
        state_id, _role_id = occupied[(x, y, z)]
        properties = dict(palette_keys[state_id][1])
        for direction, opposite, dx, dz in (
            ("east", "west", 1, 0),
            ("south", "north", 0, 1),
        ):
            neighbor_coord = (x + dx, y, z + dz)
            if neighbor_coord not in window_coords:
                continue
            neighbor_state_id, _neighbor_role_id = occupied[neighbor_coord]
            neighbor_properties = dict(palette_keys[neighbor_state_id][1])
            if properties.get(direction) != "true" or neighbor_properties.get(opposite) != "true":
                connection_errors.append(
                    {
                        "coord": [x, y, z],
                        "direction": direction,
                        "neighbor": list(neighbor_coord),
                        "property": properties.get(direction),
                        "neighbor_property": neighbor_properties.get(opposite),
                    }
                )

        # Check non-pane neighbours independently on every side.  Pane pairs
        # above need reciprocal properties, while these targets expose only the
        # pane's own arm state.
        for direction, dx, dz in (
            ("north", 0, -1),
            ("south", 0, 1),
            ("west", -1, 0),
            ("east", 1, 0),
        ):
            neighbor_coord = (x + dx, y, z + dz)
            if neighbor_coord in window_coords:
                continue
            neighbor_value = occupied.get(neighbor_coord)
            neighbor_name = (
                palette_keys[neighbor_value[0]][0]
                if neighbor_value is not None
                else None
            )
            expected_connected = _pane_attaches_to_name(neighbor_name)
            actual_connected = properties.get(direction) == "true"
            if actual_connected != expected_connected:
                connection_errors.append(
                    {
                        "coord": [x, y, z],
                        "direction": direction,
                        "neighbor": list(neighbor_coord),
                        "neighbor_block": neighbor_name,
                        "property": properties.get(direction),
                        "expected_connected": expected_connected,
                    }
                )

    # Components remain useful diagnostics, but their bounding boxes cannot
    # determine a pane's wall plane: a narrow upper light or a rasterized turn
    # can span farther along its normal than along its sheet.  Derive each
    # pane's represented sheet(s) from its actual arms instead.
    remaining = set(window_coords)
    pane_components: list[list[tuple[int, int, int]]] = []
    while remaining:
        seed = remaining.pop()
        queue = [seed]
        component: list[tuple[int, int, int]] = []
        while queue:
            x, y, z = queue.pop()
            component.append((x, y, z))
            for neighbor in (
                (x + 1, y, z),
                (x - 1, y, z),
                (x, y + 1, z),
                (x, y - 1, z),
                (x, y, z + 1),
                (x, y, z - 1),
            ):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        pane_components.append(component)

    component_by_coord: dict[
        tuple[int, int, int], tuple[int, np.ndarray, np.ndarray]
    ] = {}
    legacy_bbox_ambiguous_component_count = 0
    for component_index, component in enumerate(pane_components):
        component_array = np.asarray(component, dtype=np.int32)
        minimum = component_array.min(axis=0)
        maximum = component_array.max(axis=0)
        span_x = int(maximum[0] - minimum[0])
        span_z = int(maximum[2] - minimum[2])
        if span_x == span_z:
            legacy_bbox_ambiguous_component_count += 1
        for coord in component:
            component_by_coord[coord] = (component_index, minimum, maximum)

    blocked_panes: list[dict[str, Any]] = []
    arm_free_pane_count = 0
    axis_normals = {
        "x": ((-1, 0, 0), (1, 0, 0)),
        "z": ((0, 0, -1), (0, 0, 1)),
    }
    for x, y, z in sorted(window_coords):
        state_id, _role_id = occupied[(x, y, z)]
        properties = dict(palette_keys[state_id][1])
        normal_axes: list[str] = []
        # East/west arms form an X/Y sheet with a Z normal; north/south arms
        # form a Z/Y sheet with an X normal.  Corners and pluses represent both.
        if properties.get("east") == "true" or properties.get("west") == "true":
            normal_axes.append("z")
        if properties.get("north") == "true" or properties.get("south") == "true":
            normal_axes.append("x")
        if not normal_axes:
            # A serialized arm-free pane is a post, so either sheet orientation
            # is possible.  It is buried only when both axes are enclosed.
            normal_axes = ["x", "z"]
            arm_free_pane_count += 1

        blocked_axes: list[dict[str, Any]] = []
        for normal_axis in normal_axes:
            normals = axis_normals[normal_axis]
            neighbor_coords = [
                (x + dx, y + dy, z + dz) for dx, dy, dz in normals
            ]
            neighbor_values = [occupied.get(coord) for coord in neighbor_coords]
            if not all(value is not None for value in neighbor_values):
                continue
            neighbor_roles = [role_names[value[1]] for value in neighbor_values if value]
            if any(role == "window" for role in neighbor_roles):
                continue
            neighbor_states = [
                _state_dict(palette_keys[value[0]]) for value in neighbor_values if value
            ]
            blocked_axes.append(
                {
                    "normal_axis": normal_axis,
                    "neighbors": [
                        {
                            "coord": list(coord),
                            "role": role,
                            "state": state,
                        }
                        for coord, role, state in zip(
                            neighbor_coords, neighbor_roles, neighbor_states
                        )
                    ],
                }
            )
        if len(blocked_axes) == len(normal_axes):
            component_index, minimum, maximum = component_by_coord[(x, y, z)]
            blocked_panes.append(
                {
                    "coord": [x, y, z],
                    "component": component_index,
                    "component_bounds": [
                        minimum.astype(int).tolist(),
                        maximum.astype(int).tolist(),
                    ],
                    "normal_axes": normal_axes,
                    "blocked_normal_axes": blocked_axes,
                }
            )

    lower_doors: list[dict[str, Any]] = []
    for coord, (state_id, role_id) in occupied.items():
        state_key = palette_keys[state_id]
        properties = dict(state_key[1])
        if (
            role_names[role_id] == "door"
            and state_key[0].endswith("_door")
            and properties.get("half") == "lower"
            and properties.get("facing") in {"north", "south", "east", "west"}
        ):
            lower_doors.append({"coord": coord, "facing": properties["facing"]})

    # Adjacent same-facing lower halves form one paired entrance.
    remaining_door_indexes = set(range(len(lower_doors)))
    entrance_groups: list[list[dict[str, Any]]] = []
    while remaining_door_indexes:
        seed_index = remaining_door_indexes.pop()
        group_indexes = {seed_index}
        queue = [seed_index]
        while queue:
            current = queue.pop()
            current_door = lower_doors[current]
            cx, cy, cz = current_door["coord"]
            for other in list(remaining_door_indexes):
                other_door = lower_doors[other]
                ox, oy, oz = other_door["coord"]
                if (
                    other_door["facing"] == current_door["facing"]
                    and oy == cy
                    and abs(ox - cx) + abs(oz - cz) == 1
                ):
                    remaining_door_indexes.remove(other)
                    group_indexes.add(other)
                    queue.append(other)
        entrance_groups.append([lower_doors[index] for index in sorted(group_indexes)])

    structural_support_roles = {"terrain", "pavement", "facade", "trim", "floor"}

    def walkable(x: int, y: int, z: int) -> bool:
        if grid.key(x, y, z) is not None or grid.key(x, y + 1, z) is not None:
            return False
        support_key = grid.key(x, y - 1, z)
        support_role_id = grid.role_id(x, y - 1, z)
        return (
            support_key is not None
            and support_key[0] not in {"minecraft:water", "minecraft:lava"}
            and support_role_id >= 0
            and role_names[support_role_id] in structural_support_roles
        )

    entrance_results: list[dict[str, Any]] = []
    for group in entrance_groups:
        facing = group[0]["facing"]
        dx, dz = {
            "north": (0, -1),
            "south": (0, 1),
            "west": (-1, 0),
            "east": (1, 0),
        }[facing]
        door_coords = [door["coord"] for door in group]
        center_x = sum(coord[0] for coord in door_coords) / len(door_coords)
        center_z = sum(coord[2] for coord in door_coords) / len(door_coords)
        base_y = door_coords[0][1]
        x_min = min(coord[0] for coord in door_coords) - 12
        x_max = max(coord[0] for coord in door_coords) + 12
        z_min = min(coord[2] for coord in door_coords) - 12
        z_max = max(coord[2] for coord in door_coords) + 12

        def side_component(side: int) -> tuple[int, float, list[int] | None]:
            seeds = {
                (x + dx * side, y, z + dz * side)
                for x, y, z in door_coords
                if walkable(x + dx * side, y, z + dz * side)
            }
            visited = set(seeds)
            queue: deque[tuple[int, int, int]] = deque(seeds)
            while queue:
                x, y, z = queue.popleft()
                for move_x, move_z in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    for move_y in (0, 1, -1):
                        neighbor = (x + move_x, y + move_y, z + move_z)
                        nx, ny, nz = neighbor
                        if (
                            neighbor in visited
                            or nx < x_min
                            or nx > x_max
                            or nz < z_min
                            or nz > z_max
                            or ny < base_y - 3
                            or ny > base_y + 3
                            or not walkable(nx, ny, nz)
                        ):
                            continue
                        visited.add(neighbor)
                        queue.append(neighbor)
                        break
            if not visited:
                return 0, 0.0, None
            projections = {
                coord: side
                * ((coord[0] - center_x) * dx + (coord[2] - center_z) * dz)
                for coord in visited
            }
            furthest_coord, depth = max(projections.items(), key=lambda item: item[1])
            return len(visited), float(depth), list(furthest_coord)

        interior_count, interior_depth, interior_furthest = side_component(-1)
        exterior_count, exterior_depth, exterior_furthest = side_component(1)
        route_ok = interior_depth >= 3.0 and exterior_depth >= 3.0
        entrance_results.append(
            {
                "door_coords": [list(coord) for coord in door_coords],
                "facing": facing,
                "interior_component_size": interior_count,
                "interior_depth_blocks": interior_depth,
                "interior_furthest": interior_furthest,
                "exterior_component_size": exterior_count,
                "exterior_depth_blocks": exterior_depth,
                "exterior_furthest": exterior_furthest,
                "local_route_ok": route_ok,
            }
        )

    route_failures = [entry for entry in entrance_results if not entry["local_route_ok"]]
    if connection_errors:
        violations.append(
            f"{len(connection_errors)} pane arms disagree with vanilla horizontal attachment targets"
        )
    if blocked_panes:
        violations.append(f"{len(blocked_panes)} window panes are occupied on both wall-normal sides")
    if route_failures:
        violations.append(f"{len(route_failures)} entrances lack a local exterior-to-interior route")

    return (
        {
            "pane_count": int(len(window_coords)),
            "pane_component_count": int(len(pane_components)),
            "ambiguous_pane_component_count": 0,
            "legacy_bbox_ambiguous_component_count": int(
                legacy_bbox_ambiguous_component_count
            ),
            "arm_free_pane_count": int(arm_free_pane_count),
            "pane_connection_error_count": int(len(connection_errors)),
            "pane_connection_error_examples": connection_errors[:max_examples],
            "blocked_both_normal_sides_count": int(len(blocked_panes)),
            "blocked_both_normal_sides": blocked_panes[:max_examples],
            "entrance_group_count": int(len(entrance_groups)),
            "entrance_route_failure_count": int(len(route_failures)),
            "entrances": entrance_results,
        },
        violations,
    )


def _audit_evidence(
    manifest: Mapping[str, Any], study_dir: Path, sample_blocks_path: Path
) -> tuple[dict[str, Any], list[str]]:
    violations: list[str] = []
    official_inputs: dict[str, Any] = {}
    input_records: list[tuple[str, Any]] = [
        ("profile", manifest.get("profile")),
        ("terrain", manifest.get("terrain")),
    ]
    trees_record = manifest.get("trees")
    if trees_record is not None:
        input_records.append(("trees", trees_record))
        if isinstance(trees_record, Mapping) and trees_record.get("canopy") is not None:
            input_records.append(("trees.canopy", trees_record.get("canopy")))
    for input_name, record in input_records:
        raw_path = (
            record.get("path") or record.get("source") if isinstance(record, Mapping) else None
        )
        if not isinstance(record, Mapping) or not raw_path or not record.get("sha256"):
            official_inputs[input_name] = {"status": "missing"}
            violations.append(f"manifest {input_name} evidence record is missing")
            continue
        path = _resolve_input_path(study_dir, str(raw_path))
        if not path.is_file():
            official_inputs[input_name] = {"status": "missing", "path": str(path)}
            violations.append(f"official {input_name} input is missing")
            continue
        actual_sha = _sha256(path)
        expected_sha = str(record["sha256"]).lower()
        status = "verified" if actual_sha == expected_sha else "sha256_mismatch"
        official_inputs[input_name] = {
            "status": status,
            "path": str(path),
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
        }
        if status != "verified":
            violations.append(f"official {input_name} input SHA-256 does not match manifest")

    resource_pack, resource_pack_failures = _audit_resource_pack(manifest, study_dir)
    violations.extend(resource_pack_failures)
    visual_review, visual_review_failures = _audit_visual_review_evidence(
        manifest,
        study_dir,
        sample_blocks_path,
        resource_pack,
    )
    violations.extend(visual_review_failures)

    return (
        {
            "official_inputs": official_inputs,
            "resource_pack": resource_pack,
            **visual_review,
        },
        violations,
    )


def _audit_resource_pack(
    manifest: Mapping[str, Any], study_dir: Path
) -> tuple[dict[str, Any], list[str]]:
    """Verify the exact listed file inventory of a snapshotted resource pack."""

    record = manifest.get("resource_pack")
    if record is None:
        return {"status": "not_declared"}, []
    if not isinstance(record, Mapping) or not record.get("path"):
        return {"status": "missing_manifest_record"}, [
            "manifest resource_pack record is malformed"
        ]
    declared_files = record.get("files")
    if not isinstance(declared_files, Mapping) or not declared_files:
        return {"status": "missing_file_manifest"}, [
            "manifest resource_pack files mapping is missing or empty"
        ]

    pack_path = _resolve_input_path(study_dir, str(record["path"])).resolve()
    if not pack_path.is_dir():
        return {"status": "missing", "path": str(pack_path)}, [
            "snapshotted resource-pack directory is missing"
        ]

    failures: list[str] = []
    file_results: dict[str, dict[str, Any]] = {}
    normalized_declared: dict[str, str] = {}
    for raw_relative, raw_sha in declared_files.items():
        relative = Path(str(raw_relative))
        relative_key = relative.as_posix()
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            failures.append(f"resource-pack file path is unsafe: {raw_relative}")
            file_results[relative_key] = {"status": "unsafe_path"}
            continue
        file_path = (pack_path / relative).resolve()
        try:
            file_path.relative_to(pack_path)
        except ValueError:
            failures.append(f"resource-pack file escapes snapshot directory: {raw_relative}")
            file_results[relative_key] = {"status": "unsafe_path"}
            continue
        expected_sha = str(raw_sha).lower()
        normalized_declared[relative_key] = expected_sha
        if not file_path.is_file():
            failures.append(f"resource-pack file is missing: {relative_key}")
            file_results[relative_key] = {
                "status": "missing",
                "expected_sha256": expected_sha,
            }
            continue
        actual_sha = _sha256(file_path)
        status = "verified" if actual_sha == expected_sha else "sha256_mismatch"
        file_results[relative_key] = {
            "status": status,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
        }
        if status != "verified":
            failures.append(f"resource-pack file SHA-256 mismatch: {relative_key}")

    actual_files = {
        path.relative_to(pack_path).as_posix()
        for path in pack_path.rglob("*")
        if path.is_file()
    }
    declared_file_names = set(normalized_declared)
    extra_files = sorted(actual_files - declared_file_names)
    missing_files = sorted(declared_file_names - actual_files)
    if extra_files:
        failures.append(f"resource-pack snapshot has {len(extra_files)} unlisted files")
    # Missing files already have individual messages, but keep the exact
    # inventory in the compact result for downstream inspection.
    return (
        {
            "status": "verified" if not failures else "failed",
            "path": str(pack_path),
            "declared_file_count": len(declared_file_names),
            "actual_file_count": len(actual_files),
            "files": file_results,
            "missing_files": missing_files,
            "extra_files": extra_files,
        },
        failures,
    )


def _resolve_report_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    local_candidate = (base_dir / candidate).resolve()
    if local_candidate.exists():
        return local_candidate
    return _resolve_input_path(base_dir, raw_path).resolve()


def _load_hashed_json_record(
    record: Any,
    *,
    label: str,
    base_dir: Path,
) -> tuple[dict[str, Any] | None, Path | None, str | None, dict[str, Any], list[str]]:
    failures: list[str] = []
    if not isinstance(record, Mapping) or not record.get("path") or not record.get("sha256"):
        return None, None, None, {"status": "missing_record"}, [
            f"{label} evidence record is malformed"
        ]
    path = _resolve_report_path(base_dir, str(record["path"]))
    expected_sha = str(record["sha256"]).lower()
    if not path.is_file():
        return None, path, None, {
            "status": "missing",
            "path": str(path),
            "expected_sha256": expected_sha,
        }, [f"{label} evidence file is missing"]
    actual_sha = _sha256(path)
    if actual_sha != expected_sha:
        failures.append(f"{label} evidence SHA-256 does not match manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON root is not an object")
    except Exception as exc:
        failures.append(f"{label} evidence JSON is invalid: {type(exc).__name__}: {exc}")
        payload = None
    result = {
        "status": "verified" if not failures else "invalid",
        "path": str(path),
        "expected_sha256": expected_sha,
        "actual_sha256": actual_sha,
    }
    return payload, path, actual_sha, result, failures


def _numeric_vector(value: Any, length: int) -> tuple[float, ...] | None:
    if not isinstance(value, list) or len(value) != length:
        return None
    result: list[float] = []
    for raw in value:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        number = float(raw)
        if not math.isfinite(number):
            return None
        result.append(number)
    return tuple(result)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _angle_delta_degrees(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _view_angles(
    eye: tuple[float, float, float], target: tuple[float, float, float]
) -> tuple[float, float] | None:
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    dz = target[2] - eye[2]
    horizontal = math.hypot(dx, dz)
    if horizontal == 0.0 and dy == 0.0:
        return None
    yaw = math.degrees(math.atan2(-dx, dz))
    pitch = -math.degrees(math.atan2(dy, horizontal))
    return yaw, pitch


def _audit_native_capture_report(
    record: Any,
    *,
    launch_record: Any,
    study_dir: Path,
    resource_pack: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None, list[str]]:
    payload, report_path, report_sha, result, failures = _load_hashed_json_record(
        record,
        label="native capture report",
        base_dir=study_dir,
    )
    if payload is None or report_path is None or report_sha is None:
        return result, report_sha, failures

    if payload.get("format") != "hill-chapel-native-qa-v1":
        failures.append("native capture report format is not hill-chapel-native-qa-v1")
    if payload.get("status") != "complete":
        failures.append("native capture report status is not complete")
    if payload.get("mode") != "capture":
        failures.append("native capture report mode is not capture")
    if payload.get("renderer") != "native Minecraft client":
        failures.append("native capture report renderer is not the native Minecraft client")
    if payload.get("conversion_completed") is not True:
        failures.append("native capture report does not confirm world conversion completion")
    if payload.get("failure") is not None:
        failures.append("native capture report contains a failure")

    # Older native capture artifacts predate the in-process input-isolation
    # probe.  Once a report declares the field, only JSON `true` proves that
    # the held-forward probe observed inert ClientInput, an ungrabbed mouse,
    # and an unchanged camera pose.  In particular, Python's bool/int
    # relationship must not allow JSON `1` to stand in for the literal.
    if "capture_input_probe_passed" in payload:
        raw_probe_result = payload.get("capture_input_probe_passed")
        probe_passed = raw_probe_result is True
        result["capture_input_probe_passed"] = (
            raw_probe_result if isinstance(raw_probe_result, bool) else None
        )
        result["capture_input_probe_status"] = (
            "passed" if probe_passed else "invalid"
        )
        if not probe_passed:
            failures.append(
                "native capture report capture_input_probe_passed is not literal true"
            )
    else:
        result["capture_input_probe_passed"] = None
        result["capture_input_probe_status"] = "not_recorded"

    launch_payload, launch_path, _launch_sha, launch_result, launch_failures = (
        _load_hashed_json_record(
            launch_record,
            label="native launch manifest",
            base_dir=study_dir,
        )
    )
    failures.extend(launch_failures)
    result["launch_manifest"] = launch_result
    result["camera_config_source"] = {"status": "not_declared"}
    if launch_payload is not None and launch_path is not None:
        if launch_path.parent != report_path.parent:
            failures.append("native report and launch manifest are not adjacent run artifacts")
        if launch_payload.get("format") != "hill-chapel-native-qa-launch-v1":
            failures.append("native launch manifest format is invalid")
        if launch_payload.get("mode") != "capture":
            failures.append("native launch manifest mode is not capture")
        if launch_payload.get("minecraft_version") != payload.get("minecraft_version"):
            failures.append("native report and launch manifest Minecraft versions differ")

        raw_world_path = launch_payload.get("source_world")
        if not isinstance(raw_world_path, str) or not raw_world_path:
            failures.append("native launch manifest source_world is missing")
        else:
            source_world = _resolve_report_path(launch_path.parent, raw_world_path)
            expected_world = (study_dir / "world").resolve()
            result["source_world"] = str(source_world)
            result["expected_world"] = str(expected_world)
            if source_world != expected_world:
                failures.append("native launch manifest source_world does not match this study")

        raw_copied_world = launch_payload.get("copied_world")
        if not isinstance(raw_copied_world, str) or not raw_copied_world:
            failures.append("native launch manifest copied_world is missing")
        else:
            copied_world = _resolve_report_path(launch_path.parent, raw_copied_world)
            result["copied_world"] = str(copied_world)
            try:
                copied_world.relative_to(launch_path.parent.resolve())
                copied_world_contained = True
            except ValueError:
                copied_world_contained = False
            if not copied_world_contained or not copied_world.is_dir():
                failures.append("native launch manifest copied_world is not a run-local directory")
            elif not (copied_world / "level.dat").is_file():
                failures.append("native copied world has no level.dat")

        raw_pack_path = launch_payload.get("resource_pack")
        launch_pack_id = launch_payload.get("resource_pack_id")
        expected_pack_id = payload.get("expected_resource_pack")
        active_packs = payload.get("active_resource_packs")
        if resource_pack.get("status") != "verified":
            failures.append("native capture expects a resource pack that is not verified")
        elif not isinstance(raw_pack_path, str) or not raw_pack_path:
            failures.append("native launch manifest resource_pack path is missing")
        else:
            launched_pack_path = _resolve_report_path(launch_path.parent, raw_pack_path)
            expected_pack_path = Path(str(resource_pack["path"])).resolve()
            result["active_resource_pack"] = str(launched_pack_path)
            if launched_pack_path != expected_pack_path:
                failures.append(
                    "native launch manifest resource pack does not match this study"
                )
        if (
            not isinstance(launch_pack_id, str)
            or not launch_pack_id
            or launch_pack_id != expected_pack_id
        ):
            failures.append("native report expected resource pack does not match launch manifest")
        if (
            not isinstance(active_packs, list)
            or not expected_pack_id
            or expected_pack_id not in active_packs
        ):
            failures.append("expected resource pack was not active in the native client")

        if "camera_config_source" in launch_payload:
            (
                camera_payload,
                _camera_path,
                _camera_sha,
                camera_result,
                camera_failures,
            ) = _load_hashed_json_record(
                launch_payload.get("camera_config_source"),
                label="native camera config",
                base_dir=launch_path.parent,
            )
            if camera_payload is not None:
                if camera_payload.get("format") != "hill-native-camera-views-v1":
                    camera_failures.append("native camera config format is invalid")
                if camera_payload.get("views") != launch_payload.get("views"):
                    camera_failures.append(
                        "native camera config views do not match launch-manifest views"
                    )
            if camera_failures:
                camera_result["status"] = "invalid"
            result["camera_config_source"] = camera_result
            failures.extend(camera_failures)

    screenshots = payload.get("views")
    screenshot_results: list[dict[str, Any]] = []
    fov_recorded_count = 0
    fov_valid_count = 0
    if not isinstance(screenshots, list) or not screenshots:
        failures.append("native capture report has no captured views")
    else:
        launch_views_by_name: dict[str, Mapping[str, Any]] = {}
        if launch_payload is not None:
            raw_launch_views = launch_payload.get("views")
            if isinstance(raw_launch_views, list):
                for launch_view in raw_launch_views:
                    if isinstance(launch_view, Mapping) and isinstance(
                        launch_view.get("name"), str
                    ):
                        launch_views_by_name[str(launch_view["name"])] = launch_view
            else:
                failures.append("native launch manifest views are missing")
        seen_names: set[str] = set()
        seen_screenshots: set[Path] = set()
        for index, screenshot in enumerate(screenshots):
            item: dict[str, Any] = {"index": index}
            if not isinstance(screenshot, Mapping):
                failures.append(f"native view {index} record is malformed")
                item["status"] = "invalid"
                screenshot_results.append(item)
                continue
            name = screenshot.get("name")
            if not isinstance(name, str) or not name.strip() or name in seen_names:
                failures.append(f"native view {index} has a missing or duplicate name")
            else:
                seen_names.add(name)
                item["name"] = name
            raw_path = screenshot.get("screenshot")
            raw_sha = screenshot.get("sha256")
            if not isinstance(raw_path, str) or not raw_path or not raw_sha:
                failures.append(f"native view {index} screenshot path/SHA-256 is missing")
                item["status"] = "invalid"
                screenshot_results.append(item)
                continue
            screenshot_path = _resolve_report_path(report_path.parent, raw_path)
            expected_sha = str(raw_sha).lower()
            item.update({"path": str(screenshot_path), "expected_sha256": expected_sha})
            try:
                screenshot_path.relative_to(report_path.parent.resolve())
                screenshot_contained = True
            except ValueError:
                screenshot_contained = False
            if not screenshot_contained:
                failures.append(f"native view {index} screenshot is outside the capture run")
            if screenshot_path in seen_screenshots:
                failures.append(f"native view {index} reuses a screenshot file")
            seen_screenshots.add(screenshot_path)
            if not screenshot_path.is_file():
                failures.append(f"native view {index} screenshot file is missing")
                item["status"] = "missing"
            else:
                actual_sha = _sha256(screenshot_path)
                item["actual_sha256"] = actual_sha
                item["status"] = "verified" if actual_sha == expected_sha else "sha256_mismatch"
                if actual_sha != expected_sha:
                    failures.append(f"native view {index} screenshot SHA-256 does not match report")
                expected_bytes = screenshot.get("bytes")
                if (
                    isinstance(expected_bytes, bool)
                    or not isinstance(expected_bytes, int)
                    or expected_bytes != screenshot_path.stat().st_size
                ):
                    failures.append(f"native view {index} screenshot byte count is invalid")

            requested_eye = _numeric_vector(screenshot.get("requested_eye"), 3)
            actual_eye = _numeric_vector(screenshot.get("actual_eye"), 3)
            requested_target = _numeric_vector(screenshot.get("requested_target"), 3)
            requested_yaw = _finite_number(screenshot.get("requested_yaw"))
            requested_pitch = _finite_number(screenshot.get("requested_pitch"))
            actual_yaw = _finite_number(screenshot.get("actual_yaw"))
            actual_pitch = _finite_number(screenshot.get("actual_pitch"))
            commanded_feet_y = _finite_number(screenshot.get("commanded_feet_y"))
            launch_view = (
                launch_views_by_name.get(name) if isinstance(name, str) else None
            )
            pose_valid = all(
                value is not None
                for value in (
                    requested_eye,
                    actual_eye,
                    requested_target,
                    requested_yaw,
                    requested_pitch,
                    actual_yaw,
                    actual_pitch,
                    commanded_feet_y,
                )
            )
            if pose_valid:
                assert requested_eye is not None
                assert actual_eye is not None
                assert requested_target is not None
                assert requested_yaw is not None
                assert requested_pitch is not None
                assert actual_yaw is not None
                assert actual_pitch is not None
                assert commanded_feet_y is not None
                angles = _view_angles(requested_eye, requested_target)
                pose_valid = (
                    angles is not None
                    and -90.0 <= requested_pitch <= 90.0
                    and -90.0 <= actual_pitch <= 90.0
                    and max(abs(a - b) for a, b in zip(requested_eye, actual_eye)) <= 0.01
                    and _angle_delta_degrees(requested_yaw, actual_yaw) <= 0.01
                    and abs(requested_pitch - actual_pitch) <= 0.01
                    and abs(commanded_feet_y - (requested_eye[1] - 1.62)) <= 0.01
                    and _angle_delta_degrees(requested_yaw, angles[0]) <= 0.02
                    and abs(requested_pitch - angles[1]) <= 0.02
                )
                launch_eye = (
                    _numeric_vector(launch_view.get("eye"), 3)
                    if launch_view is not None
                    else None
                )
                launch_target = (
                    _numeric_vector(launch_view.get("target"), 3)
                    if launch_view is not None
                    else None
                )
                pose_valid = bool(
                    pose_valid
                    and launch_eye is not None
                    and launch_target is not None
                    and max(abs(a - b) for a, b in zip(requested_eye, launch_eye)) <= 0.001
                    and max(abs(a - b) for a, b in zip(requested_target, launch_target))
                    <= 0.001
                )
            if not pose_valid:
                failures.append(f"native view {index} has invalid or inconsistent pose evidence")
            item["pose_status"] = "valid" if pose_valid else "invalid"

            # Native QA reports before the FOV capture work did not contain any
            # FOV fields.  Keep those artifacts valid.  Once any of the three
            # records declares FOV, require the complete chain so a report or
            # launch manifest cannot silently omit or substitute the camera
            # lens used for the screenshot.
            fov_recorded = (
                "requested_fov" in screenshot
                or "actual_fov" in screenshot
                or (launch_view is not None and "fov" in launch_view)
            )
            if fov_recorded:
                fov_recorded_count += 1
                requested_fov = _finite_number(screenshot.get("requested_fov"))
                actual_fov = _finite_number(screenshot.get("actual_fov"))
                launch_fov = (
                    _finite_number(launch_view.get("fov"))
                    if launch_view is not None
                    else None
                )
                fov_valid = bool(
                    requested_fov is not None
                    and actual_fov is not None
                    and launch_fov is not None
                    and 30.0 <= requested_fov <= 110.0
                    and 30.0 <= actual_fov <= 110.0
                    and 30.0 <= launch_fov <= 110.0
                    and abs(requested_fov - actual_fov) <= 0.001
                    and abs(requested_fov - launch_fov) <= 0.001
                )
                item.update(
                    {
                        "requested_fov": requested_fov,
                        "actual_fov": actual_fov,
                        "launch_fov": launch_fov,
                        "fov_status": "valid" if fov_valid else "invalid",
                    }
                )
                if fov_valid:
                    fov_valid_count += 1
                else:
                    failures.append(
                        f"native view {index} has invalid or inconsistent FOV evidence"
                    )
            else:
                item["fov_status"] = "not_recorded"
            screenshot_results.append(item)
        if launch_views_by_name and set(launch_views_by_name) != seen_names:
            failures.append("native report views do not exactly match launch-manifest views")
    result["screenshots"] = screenshot_results
    result["screenshot_count"] = len(screenshot_results)
    result["fov_recorded_count"] = fov_recorded_count
    result["fov_valid_count"] = fov_valid_count
    result["status"] = "verified" if not failures else "invalid"
    return result, report_sha, failures


def _reviewer_identified(reviewer: Any) -> bool:
    if isinstance(reviewer, str):
        return bool(reviewer.strip())
    if isinstance(reviewer, Mapping):
        return any(
            isinstance(reviewer.get(field), str) and bool(reviewer[field].strip())
            for field in ("name", "id", "organization")
        )
    return False


def _valid_photo_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _finding_state(finding: Any) -> tuple[bool, bool] | None:
    if not isinstance(finding, Mapping) or not str(finding.get("summary") or "").strip():
        return None
    raw_blocking = finding.get("blocking")
    if isinstance(raw_blocking, bool):
        blocking = raw_blocking
    elif finding.get("severity") in {"blocking", "non_blocking"}:
        blocking = finding.get("severity") == "blocking"
    else:
        return None
    raw_resolved = finding.get("resolved")
    if isinstance(raw_resolved, bool):
        resolved = raw_resolved
    elif finding.get("status") in {"resolved", "unresolved"}:
        resolved = finding.get("status") == "resolved"
    else:
        return None
    return blocking, resolved


def _audit_authored_visual_review(
    record: Any,
    *,
    study_dir: Path,
    sample_blocks_path: Path,
    native_report_sha: str | None,
) -> tuple[dict[str, Any], str | None, list[str]]:
    payload, _review_path, review_sha, result, failures = _load_hashed_json_record(
        record,
        label="authored visual review",
        base_dir=study_dir,
    )
    if payload is None:
        return result, review_sha, failures
    if payload.get("format") != "hill-visual-review-v1":
        failures.append("authored visual review format is not hill-visual-review-v1")

    expected_npz_sha = _sha256(sample_blocks_path)
    result["expected_sample_blocks_sha256"] = expected_npz_sha
    if str(payload.get("sample_blocks_sha256") or "").lower() != expected_npz_sha:
        failures.append("authored visual review is not bound to this sample-blocks NPZ")
    if native_report_sha is None or (
        str(payload.get("native_capture_report_sha256") or "").lower()
        != native_report_sha
    ):
        failures.append("authored visual review is not bound to the native capture report")

    reviewers = payload.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers or not all(
        _reviewer_identified(reviewer) for reviewer in reviewers
    ):
        failures.append("authored visual review does not identify its reviewer(s)")
    photo_urls = payload.get("photo_reference_urls")
    if not isinstance(photo_urls, list) or not photo_urls or not all(
        _valid_photo_url(url) for url in photo_urls
    ):
        failures.append("authored visual review has no valid photo-reference URLs")

    findings = payload.get("findings")
    finding_states: list[tuple[bool, bool]] = []
    if not isinstance(findings, list):
        failures.append("authored visual review findings must be a list")
    else:
        for index, finding in enumerate(findings):
            state = _finding_state(finding)
            if state is None:
                failures.append(f"authored visual review finding {index} is malformed")
            else:
                finding_states.append(state)
    unresolved_blocking_count = sum(
        1 for blocking, resolved in finding_states if blocking and not resolved
    )
    result["unresolved_blocking_finding_count"] = unresolved_blocking_count

    decision = payload.get("decision")
    if decision not in {"pass", "changes_requested"}:
        failures.append("authored visual review decision is invalid")
        decision = None
    if decision == "pass" and unresolved_blocking_count:
        failures.append("authored visual review passes with unresolved blocking findings")
    result["decision"] = decision
    result["status"] = "verified" if not failures else "invalid"
    return result, review_sha, failures


def _audit_visual_review_evidence(
    manifest: Mapping[str, Any],
    study_dir: Path,
    sample_blocks_path: Path,
    resource_pack: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    raw_gate = manifest.get("visual_gate")
    if not isinstance(raw_gate, Mapping):
        raw_gate = {}
        failures.append("manifest visual_gate is missing")
    requested_larger_area = raw_gate.get(
        "larger_area_authorized_by_quality_gate",
        raw_gate.get("larger_area_authorized", False),
    )
    if not isinstance(requested_larger_area, bool):
        failures.append("visual gate larger-area authorization must be boolean")
        requested_larger_area = False

    native_record = raw_gate.get("native_capture_report")
    launch_record = raw_gate.get("native_launch_manifest")
    review_record = raw_gate.get("visual_review")
    native_result: dict[str, Any] = {"status": "not_declared"}
    review_result: dict[str, Any] = {"status": "not_declared"}
    native_sha: str | None = None
    if launch_record is not None and native_record is None:
        failures.append("native launch manifest is declared without a native capture report")
    if native_record is not None:
        native_result, native_sha, native_failures = _audit_native_capture_report(
            native_record,
            launch_record=launch_record,
            study_dir=study_dir,
            resource_pack=resource_pack,
        )
        failures.extend(native_failures)
    if review_record is not None:
        review_result, _review_sha, review_failures = _audit_authored_visual_review(
            review_record,
            study_dir=study_dir,
            sample_blocks_path=sample_blocks_path,
            native_report_sha=native_sha,
        )
        failures.extend(review_failures)

    native_verified = native_result.get("status") == "verified"
    review_verified = review_result.get("status") == "verified"
    review_decision = review_result.get("decision") if review_verified else None
    if requested_larger_area and not (
        native_verified and review_verified and review_decision == "pass"
    ):
        failures.append(
            "larger-area authorization is true without complete passing visual evidence"
        )

    if native_record is None:
        native_status = "pending"
    elif native_verified:
        native_status = "complete"
    else:
        native_status = "invalid"
    if review_record is None:
        photo_status = "pending"
    elif review_verified and native_verified:
        photo_status = str(review_decision)
    else:
        photo_status = "invalid"
    larger_area_authorized = bool(
        requested_larger_area
        and native_verified
        and review_verified
        and review_decision == "pass"
    )
    return (
        {
            "native_minecraft_review": native_status,
            "matched_current_photo": photo_status,
            "larger_area_authorized": larger_area_authorized,
            "native_capture_report": native_result,
            "authored_visual_review": review_result,
            "reason": (
                "complete passing visual evidence verified"
                if larger_area_authorized
                else "larger-area expansion remains gated by authored visual evidence"
            ),
        },
        failures,
    )


def _audit_expanded_study_provenance(
    manifest: Mapping[str, Any],
    study_dir: Path,
    sample_blocks_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    """Verify the measured academic sources and the accepted small-study gate.

    This deliberately audits evidence only.  It does not recursively compare the
    accepted study's Anvil world; the accepted manifest, NPZ, native capture, and
    authored review are instead bound by their recorded byte hashes.
    """

    academic_declared = "academic_complex" in manifest
    accepted_declared = "accepted_previous_sample" in manifest
    if not academic_declared and not accepted_declared:
        return {"status": "not_declared"}, []

    failures: list[str] = []
    result: dict[str, Any] = {
        "status": "invalid",
        "current_study": str(study_dir),
        "current_sample_blocks_sha256": _sha256(sample_blocks_path),
        "academic_complex": {"status": "not_declared"},
        "accepted_previous_sample": {"status": "not_declared"},
    }
    if academic_declared != accepted_declared:
        failures.append(
            "expanded study must declare academic_complex and accepted_previous_sample together"
        )

    raw_academic = manifest.get("academic_complex")
    academic_result: dict[str, Any] = {"status": "invalid", "sources": {}}
    if not isinstance(raw_academic, Mapping):
        failures.append("manifest academic_complex record is malformed")
    else:
        source_payloads: dict[str, tuple[dict[str, Any] | None, Path | None]] = {}
        for key, label in (
            ("source_cityjson", "academic source CityJSON"),
            ("measured_terrain_manifest", "academic measured-terrain manifest"),
            ("profile", "academic profile snapshot"),
        ):
            payload, path, _sha, source_result, source_failures = (
                _load_hashed_json_record(
                    raw_academic.get(key),
                    label=label,
                    base_dir=study_dir,
                )
            )
            academic_result["sources"][key] = source_result
            source_payloads[key] = (payload, path)
            failures.extend(source_failures)

        profile_record = raw_academic.get("profile")
        profile_source_path: Path | None = None
        if not isinstance(profile_record, Mapping) or not isinstance(
            profile_record.get("source_path"), str
        ) or not str(profile_record.get("source_path")).strip():
            failures.append("academic profile source_path is missing")
        else:
            profile_source_path = _resolve_input_path(
                study_dir, str(profile_record["source_path"])
            ).resolve()
            academic_result["profile_source_path"] = str(profile_source_path)
            if not profile_source_path.is_file():
                failures.append("academic profile source file is missing")

        parent_id = raw_academic.get("parent_id")
        part_ids = raw_academic.get("part_ids")
        valid_parent_id = isinstance(parent_id, str) and bool(parent_id.strip())
        valid_part_ids = (
            isinstance(part_ids, list)
            and bool(part_ids)
            and all(isinstance(part_id, str) and part_id.strip() for part_id in part_ids)
            and len(set(part_ids)) == len(part_ids)
        )
        if not valid_parent_id:
            failures.append("academic complex parent_id is missing")
        if not valid_part_ids:
            failures.append("academic complex part_ids are missing, empty, or duplicated")
        academic_result["parent_id"] = parent_id
        academic_result["part_ids"] = part_ids if isinstance(part_ids, list) else None

        cityjson_payload, _cityjson_path = source_payloads["source_cityjson"]
        if cityjson_payload is not None:
            if cityjson_payload.get("type") != "CityJSON":
                failures.append("academic source CityJSON type is invalid")
            city_objects = cityjson_payload.get("CityObjects")
            if not isinstance(city_objects, Mapping):
                failures.append("academic source CityJSON has no CityObjects mapping")
            elif valid_parent_id and valid_part_ids:
                parent_object = city_objects.get(parent_id)
                if not isinstance(parent_object, Mapping):
                    failures.append("academic source CityJSON does not contain parent_id")
                else:
                    children = parent_object.get("children")
                    if not isinstance(children, list) or set(children) != set(part_ids):
                        failures.append(
                            "academic part_ids do not match the CityJSON parent children"
                        )
                missing_parts = [part_id for part_id in part_ids if part_id not in city_objects]
                if missing_parts:
                    failures.append(
                        f"academic source CityJSON is missing {len(missing_parts)} declared parts"
                    )

        terrain_payload, terrain_manifest_path = source_payloads[
            "measured_terrain_manifest"
        ]
        if terrain_payload is not None:
            if terrain_payload.get("format") != "hill-measured-terrain-v1":
                failures.append("academic measured-terrain manifest format is invalid")
            terrain_output = terrain_payload.get("output")
            current_terrain = manifest.get("terrain")
            if (
                not isinstance(terrain_output, Mapping)
                or not terrain_output.get("path")
                or not terrain_output.get("sha256")
            ):
                failures.append("academic measured-terrain output record is malformed")
            elif not isinstance(current_terrain, Mapping):
                failures.append("current terrain record is unavailable for academic binding")
            else:
                output_base = (
                    terrain_manifest_path.parent
                    if terrain_manifest_path is not None
                    else study_dir
                )
                measured_output_path = _resolve_report_path(
                    output_base, str(terrain_output["path"])
                )
                current_terrain_path = _resolve_input_path(
                    study_dir, str(current_terrain.get("path") or "")
                ).resolve()
                academic_result["measured_terrain_output"] = {
                    "path": str(measured_output_path),
                    "sha256": str(terrain_output.get("sha256") or "").lower(),
                }
                if measured_output_path != current_terrain_path or (
                    str(terrain_output.get("sha256") or "").lower()
                    != str(current_terrain.get("sha256") or "").lower()
                ):
                    failures.append(
                        "academic measured-terrain manifest is not bound to the current terrain"
                    )

        footprint_area = _finite_number(raw_academic.get("footprint_area_m2"))
        footprint_bounds = _numeric_vector(raw_academic.get("footprint_bounds_m"), 4)
        source_height = _numeric_vector(raw_academic.get("source_height_navd88_m"), 2)
        if footprint_area is None or footprint_area <= 0.0:
            failures.append("academic footprint_area_m2 is invalid")
        if (
            footprint_bounds is None
            or footprint_bounds[0] >= footprint_bounds[2]
            or footprint_bounds[1] >= footprint_bounds[3]
        ):
            failures.append("academic footprint_bounds_m is invalid")
        elif footprint_area is not None and footprint_area > (
            (footprint_bounds[2] - footprint_bounds[0])
            * (footprint_bounds[3] - footprint_bounds[1])
            + 1e-6
        ):
            failures.append("academic footprint area exceeds its declared bounds")
        if source_height is None or source_height[0] >= source_height[1]:
            failures.append("academic source_height_navd88_m range is invalid")
        academic_result["footprint_area_m2"] = footprint_area
        academic_result["footprint_bounds_m"] = (
            list(footprint_bounds) if footprint_bounds is not None else None
        )
        academic_result["source_height_navd88_m"] = (
            list(source_height) if source_height is not None else None
        )

        roof_coverage = raw_academic.get("roof_coverage")
        if not isinstance(roof_coverage, Mapping):
            failures.append("academic roof_coverage record is malformed")
        else:
            coverage_values: dict[str, int] = {}
            for key in (
                "footprint_columns",
                "covered_columns",
                "missing_covered_columns",
            ):
                raw_value = roof_coverage.get(key)
                if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
                    failures.append(f"academic roof_coverage {key} is invalid")
                else:
                    coverage_values[key] = raw_value
            if len(coverage_values) == 3:
                if (
                    coverage_values["covered_columns"]
                    + coverage_values["missing_covered_columns"]
                    != coverage_values["footprint_columns"]
                ):
                    failures.append("academic roof_coverage column counts do not conserve")
                if coverage_values["missing_covered_columns"] != 0:
                    failures.append("academic roof_coverage leaves footprint columns uncovered")
            academic_result["roof_coverage"] = dict(roof_coverage)

        shell = raw_academic.get("shell")
        if not isinstance(shell, Mapping):
            failures.append("academic shell evidence record is malformed")
        else:
            if shell.get("format") != "hill-measured-shell-v1":
                failures.append("academic shell evidence format is invalid")
            if valid_parent_id and shell.get("parent_id") != parent_id:
                failures.append("academic shell parent_id does not match academic complex")
            active_roof_columns = shell.get("active_roof_columns")
            if (
                isinstance(active_roof_columns, bool)
                or not isinstance(active_roof_columns, int)
                or active_roof_columns < 0
            ):
                failures.append("academic shell active_roof_columns is invalid")
            clipped_writes = shell.get("clipped_writes")
            if (
                isinstance(clipped_writes, bool)
                or not isinstance(clipped_writes, int)
                or clipped_writes != 0
            ):
                failures.append("academic shell clipped_writes is not zero")
            academic_result["shell"] = dict(shell)

        features = raw_academic.get("features")
        if not isinstance(features, Mapping):
            failures.append("academic features record is malformed")
        elif any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in features.values()
        ):
            failures.append("academic features contain invalid counts")
        else:
            academic_result["features"] = dict(features)

    result["academic_complex"] = academic_result

    raw_accepted = manifest.get("accepted_previous_sample")
    accepted_result: dict[str, Any] = {"status": "invalid"}
    if not isinstance(raw_accepted, Mapping):
        failures.append("manifest accepted_previous_sample record is malformed")
    else:
        required = (
            "study",
            "manifest_sha256",
            "visual_review_sha256",
            "sample_blocks_sha256",
        )
        if any(not isinstance(raw_accepted.get(key), str) or not raw_accepted[key] for key in required):
            failures.append("manifest accepted_previous_sample record is malformed")
        else:
            previous_dir = _resolve_input_path(
                study_dir, str(raw_accepted["study"])
            ).resolve()
            accepted_result["study"] = str(previous_dir)
            if previous_dir == study_dir:
                failures.append("current and accepted previous studies must be distinct")
            previous_manifest_path = previous_dir / "manifest.json"
            previous_npz_path = previous_dir / "sample-blocks.npz"
            accepted_files: dict[str, Any] = {}
            previous_manifest: dict[str, Any] | None = None
            for key, path, label in (
                ("manifest", previous_manifest_path, "manifest_sha256"),
                ("sample_blocks", previous_npz_path, "sample_blocks_sha256"),
            ):
                expected_sha = str(raw_accepted[label]).lower()
                item = {"path": str(path), "expected_sha256": expected_sha}
                if not path.is_file():
                    item["status"] = "missing"
                    failures.append(f"accepted previous sample {key} file is missing")
                else:
                    actual_sha = _sha256(path)
                    item["actual_sha256"] = actual_sha
                    item["status"] = (
                        "verified" if actual_sha == expected_sha else "sha256_mismatch"
                    )
                    if actual_sha != expected_sha:
                        failures.append(
                            f"accepted previous sample {key} SHA-256 does not match manifest"
                        )
                accepted_files[key] = item
            accepted_result["files"] = accepted_files

            if previous_manifest_path.is_file():
                try:
                    raw_previous_manifest = json.loads(
                        previous_manifest_path.read_text(encoding="utf-8")
                    )
                    if not isinstance(raw_previous_manifest, dict):
                        raise ValueError("JSON root is not an object")
                    previous_manifest = raw_previous_manifest
                except Exception as exc:
                    failures.append(
                        "accepted previous sample manifest JSON is invalid: "
                        f"{type(exc).__name__}: {exc}"
                    )

            previous_gate_result: dict[str, Any] = {"status": "not_audited"}
            if previous_manifest is not None and previous_npz_path.is_file():
                raw_previous_gate = previous_manifest.get("visual_gate")
                raw_previous_review = (
                    raw_previous_gate.get("visual_review")
                    if isinstance(raw_previous_gate, Mapping)
                    else None
                )
                if not isinstance(raw_previous_review, Mapping) or not raw_previous_review.get(
                    "path"
                ) or not raw_previous_review.get("sha256"):
                    failures.append(
                        "accepted previous sample has no authored visual-review record"
                    )
                else:
                    previous_review_path = _resolve_report_path(
                        previous_dir, str(raw_previous_review["path"])
                    )
                    expected_review_sha = str(
                        raw_accepted["visual_review_sha256"]
                    ).lower()
                    declared_review_sha = str(raw_previous_review["sha256"]).lower()
                    review_item = {
                        "path": str(previous_review_path),
                        "expected_sha256": expected_review_sha,
                        "previous_manifest_sha256": declared_review_sha,
                    }
                    if not previous_review_path.is_file():
                        review_item["status"] = "missing"
                        failures.append(
                            "accepted previous sample visual review file is missing"
                        )
                    else:
                        actual_review_sha = _sha256(previous_review_path)
                        review_item["actual_sha256"] = actual_review_sha
                        review_item["status"] = (
                            "verified"
                            if actual_review_sha
                            == expected_review_sha
                            == declared_review_sha
                            else "sha256_mismatch"
                        )
                        if review_item["status"] != "verified":
                            failures.append(
                                "accepted previous sample visual review SHA-256 binding is invalid"
                            )
                    accepted_files["visual_review"] = review_item

                previous_pack, previous_pack_failures = _audit_resource_pack(
                    previous_manifest, previous_dir
                )
                previous_gate_result, previous_gate_failures = (
                    _audit_visual_review_evidence(
                        previous_manifest,
                        previous_dir,
                        previous_npz_path,
                        previous_pack,
                    )
                )
                failures.extend(
                    f"accepted previous sample: {failure}"
                    for failure in (*previous_pack_failures, *previous_gate_failures)
                )
                if not (
                    previous_gate_result.get("native_minecraft_review") == "complete"
                    and previous_gate_result.get("matched_current_photo") == "pass"
                    and previous_gate_result.get("larger_area_authorized") is True
                ):
                    failures.append(
                        "accepted previous sample does not have a verified passing visual gate"
                    )
            accepted_result["visual_gate"] = previous_gate_result

    result["accepted_previous_sample"] = accepted_result
    provenance_failed = bool(failures)
    academic_result["status"] = "invalid" if provenance_failed else "verified"
    accepted_result["status"] = "invalid" if provenance_failed else "verified"
    result["status"] = "invalid" if provenance_failed else "verified"
    return result, failures


def audit_study(study_dir: Path, *, max_examples: int = 8) -> dict[str, Any]:
    study_dir = study_dir.resolve()
    manifest_path = study_dir / "manifest.json"
    npz_path = study_dir / "sample-blocks.npz"
    world_path = study_dir / "world"
    missing = [str(path) for path in (manifest_path, npz_path, world_path) if not path.exists()]
    if missing:
        return {
            "format": "hill-chapel-sample-audit-v1",
            "study_dir": str(study_dir),
            "status": "fail",
            "structural_violation_count": len(missing),
            "structural_violations": [f"required artifact is missing: {path}" for path in missing],
            "provenance": {"status": "not_audited"},
            "visual_gate": {
                "native_minecraft_review": "pending",
                "matched_current_photo": "pending",
                "larger_area_authorized": False,
            },
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sample = _read_npz(npz_path)
        actual_combined, actual_keys, chunk_count = _read_anvil_blocks(world_path)
    except Exception as exc:
        return {
            "format": "hill-chapel-sample-audit-v1",
            "study_dir": str(study_dir),
            "status": "fail",
            "structural_violation_count": 1,
            "structural_violations": [f"artifact read failed: {type(exc).__name__}: {exc}"],
            "provenance": {"status": "not_audited"},
            "visual_gate": {
                "native_minecraft_review": "pending",
                "matched_current_photo": "pending",
                "larger_area_authorized": False,
            },
        }

    coords = sample["coords"]
    state_ids = sample["state_ids"]
    role_ids = sample["role_ids"]
    role_names = sample["role_names"]
    palette_keys = sample["palette_keys"]
    structural_violations: list[str] = []

    parity, parity_violations = _audit_exact_parity(
        coords, state_ids, palette_keys, actual_combined, actual_keys, max_examples
    )
    structural_violations.extend(parity_violations)

    counts, count_violations = _audit_counts_and_roles(
        manifest, state_ids, role_ids, role_names, palette_keys
    )
    structural_violations.extend(count_violations)

    try:
        grid = _ExpectedGrid(coords, state_ids, role_ids, palette_keys)
        doors, door_violations = _audit_doors_and_entrances(
            coords, state_ids, role_ids, role_names, palette_keys, grid, max_examples
        )
        foundations, foundation_violations = _audit_foundations(
            manifest, coords, role_ids, role_names, grid, max_examples
        )
        architectural_clearance, clearance_violations = _audit_architectural_clearance(
            coords,
            state_ids,
            role_ids,
            role_names,
            palette_keys,
            grid,
            max_examples,
        )
        structural_violations.extend(door_violations)
        structural_violations.extend(foundation_violations)
        structural_violations.extend(clearance_violations)
    except Exception as exc:
        doors = {"error": f"{type(exc).__name__}: {exc}"}
        foundations = {"error": f"{type(exc).__name__}: {exc}"}
        architectural_clearance = {"error": f"{type(exc).__name__}: {exc}"}
        structural_violations.append(f"structural analysis failed: {type(exc).__name__}: {exc}")

    evidence, evidence_failures = _audit_evidence(manifest, study_dir, npz_path)
    provenance, provenance_failures = _audit_expanded_study_provenance(
        manifest, study_dir, npz_path
    )
    evidence_failures.extend(provenance_failures)

    manifest_world = manifest.get("world") if isinstance(manifest.get("world"), Mapping) else {}
    manifest_block_count = manifest.get("block_count")
    if manifest_block_count is not None and int(manifest_block_count) != len(coords):
        structural_violations.append("manifest block_count does not equal NPZ occupied count")
    manifest_chunk_count = manifest_world.get("chunks")
    if manifest_chunk_count is None or int(manifest_chunk_count) != chunk_count:
        structural_violations.append(
            "manifest world chunk count does not equal serialized Anvil chunk count"
        )

    if (structural_violations or evidence_failures) and evidence.get(
        "larger_area_authorized"
    ):
        evidence["larger_area_authorized"] = False
        evidence["reason"] = "larger-area authorization rejected because the full audit failed"
        evidence_failures.append(
            "larger-area authorization is true while the full sample audit has failures"
        )

    failure_count = len(structural_violations) + len(evidence_failures)

    return {
        "format": "hill-chapel-sample-audit-v1",
        "study_dir": str(study_dir),
        "status": "pass" if failure_count == 0 else "fail",
        "failure_count": int(failure_count),
        "structural_violation_count": int(len(structural_violations)),
        "structural_violations": structural_violations,
        "evidence_failure_count": int(len(evidence_failures)),
        "evidence_failures": evidence_failures,
        "artifacts": {
            "manifest": str(manifest_path),
            "sample_blocks": str(npz_path),
            "world": str(world_path),
            "anvil_chunk_count": int(chunk_count),
        },
        "exact_parity": parity,
        "conservation_and_material_intent": counts,
        "doors_and_entrances": doors,
        "foundation_support": foundations,
        "architectural_clearance": architectural_clearance,
        "provenance": provenance,
        "visual_gate": evidence,
    }


def _write_report(report: Mapping[str, Any], output_path: Path | None) -> None:
    compact = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(compact + "\n", encoding="utf-8")
    print(compact)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study_dir", type=Path, help="generated Chapel study directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="report path (default: STUDY_DIR/audit.json)",
    )
    parser.add_argument("--max-examples", type=int, default=8)
    args = parser.parse_args(argv)
    output_path = args.output if args.output is not None else args.study_dir / "audit.json"
    report = audit_study(args.study_dir, max_examples=max(1, args.max_examples))
    _write_report(report, output_path)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
