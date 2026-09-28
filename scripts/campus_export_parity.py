"""Exact archive/Anvil comparison with bounded memory for large building studies.

The expected volume is indexed once; independently decoded Anvil sections are
compared and consumed one at a time. Air, missing cells and unknown full states
are distinct. No global sort of tens of millions of block records is needed.
"""

from collections import Counter
import json
import numpy as np
import hybridize_voxelearth_roofer_world as anvil


def read_archive(path):
    with np.load(path, allow_pickle=False) as data:
        archive = {key: data[key] for key in ("coords", "state_ids", "role_ids")}
        archive["role_names"] = [str(v) for v in data["role_names"]]
        palette = json.loads(str(data["palette_json"]))
    archive["palette_keys"] = [
        (p["Name"], tuple(sorted(p.get("Properties", {}).items()))) for p in palette
    ]
    coords, states, roles = archive["coords"], archive["state_ids"], archive["role_ids"]
    if (
        coords.ndim != 2
        or coords.shape[1] != 3
        or states.shape != (len(coords),)
        or roles.shape != (len(coords),)
    ):
        raise ValueError("Malformed block archive arrays")
    if (
        not len(coords)
        or states.min() < 0
        or states.max() >= len(palette)
        or roles.min() < 0
        or roles.max() >= len(archive["role_names"])
    ):
        raise ValueError("Empty archive or invalid palette/role index")
    return archive


def role_histogram(archive):
    n = len(archive["palette_keys"])
    hist = np.zeros(n * len(archive["role_names"]), dtype=np.int64)
    for start in range(0, len(archive["coords"]), 1_000_000):
        sl = slice(start, start + 1_000_000)
        pairs = archive["role_ids"][sl].astype(np.int64) * n + archive["state_ids"][sl]
        hist += np.bincount(pairs, minlength=len(hist))
    return [(i // n, i % n, int(hist[i])) for i in np.flatnonzero(hist)]


def compare_world(archive, world, max_examples=8):
    coords, states, keys = (
        archive["coords"],
        archive["state_ids"],
        archive["palette_keys"],
    )
    minimum, maximum = coords.min(axis=0), coords.max(axis=0)
    size = maximum.astype(np.int64) - minimum + 1
    absent = len(keys)
    if absent >= 65534 or int(np.prod(size)) > 750_000_000:
        raise ValueError("Study exceeds the bounded parity grid capacity")
    grid = np.full((size[1], size[2], size[0]), absent, dtype=np.uint16)
    duplicates = set()
    for start in range(0, len(coords), 1_000_000):
        sl = slice(start, start + 1_000_000)
        local = coords[sl] - minimum
        flat = (local[:, 1].astype(np.int64) * size[2] + local[:, 2]) * size[0] + local[
            :, 0
        ]
        unique, counts = np.unique(flat, return_counts=True)
        duplicates.update(unique[counts > 1].tolist())
        duplicates.update(unique[grid.ravel()[unique] != absent].tolist())
        grid.ravel()[flat] = states[sl]
    lookup = {key: i for i, key in enumerate(keys)}
    totals = Counter(
        expected_occupied=len(coords),
        anvil_occupied=0,
        common_coordinates=0,
        missing_count=0,
        extra_count=0,
        state_mismatch_count=0,
        duplicate_npz_coordinate_count=len(duplicates),
        duplicate_anvil_coordinate_count=0,
    )
    examples = {
        k: [] for k in ("missing_examples", "extra_examples", "state_mismatch_examples")
    }
    actual_keys = set()
    bell_ids = [i for i, key in enumerate(keys) if key[0] == "minecraft:bell"]
    expected_bells = {tuple(map(int, xyz)) for xyz in coords[np.isin(states, bell_ids)]}
    actual_bells = Counter()
    chunks = 0
    seen_sections = set()
    for cx, cz, root in anvil.iter_world_chunks(world):
        chunks += 1
        for entity in root.get("block_entities", []):
            if str(entity.get("id", "")) == "minecraft:bell":
                actual_bells[tuple(int(entity[k]) for k in ("x", "y", "z"))] += 1
        for section in root.get("sections", []):
            parsed = anvil.section_block_states(section)
            if parsed is None:
                continue
            palette, packed = parsed
            palette_keys = [anvil.palette_state_key(p) for p in palette]
            nonair = np.array([key[0] not in anvil.AIR_BLOCKS for key in palette_keys])
            if not nonair.any():
                continue
            indices = np.asarray(
                anvil.unpack_indices(len(palette), packed), dtype=np.int32
            )
            flat = np.flatnonzero(nonair[indices])
            if not flat.size:
                continue
            used = np.unique(indices[flat])
            actual_keys.update(palette_keys[i] for i in used)
            sy = int(section["Y"])
            address = (cx, sy, cz)
            if address in seen_sections:
                totals["duplicate_anvil_coordinate_count"] += len(flat)
            seen_sections.add(address)
            actual = np.column_stack(
                (
                    cx * 16 + flat % 16,
                    sy * 16 + flat // 256,
                    cz * 16 + (flat % 256) // 16,
                )
            ).astype(np.int32)
            totals["anvil_occupied"] += len(actual)
            in_bounds = np.all((actual >= minimum) & (actual <= maximum), axis=1)
            expected = np.full(len(actual), absent, dtype=np.uint16)
            local = actual[in_bounds] - minimum
            expected[in_bounds] = grid[local[:, 1], local[:, 2], local[:, 0]]
            common = expected != absent
            totals["common_coordinates"] += int(common.sum())
            extra = np.flatnonzero(~common)
            totals["extra_count"] += len(extra)
            for index in extra[
                : max(0, max_examples - len(examples["extra_examples"]))
            ]:
                examples["extra_examples"].append(actual[index].tolist())
            translated = np.array(
                [lookup.get(key, absent + 1) for key in palette_keys], dtype=np.uint16
            )[indices[flat]]
            mismatch = np.flatnonzero(common & (expected != translated))
            totals["state_mismatch_count"] += len(mismatch)
            for index in mismatch[
                : max(0, max_examples - len(examples["state_mismatch_examples"]))
            ]:
                examples["state_mismatch_examples"].append(
                    {
                        "coord": actual[index].tolist(),
                        "expected": keys[int(expected[index])],
                        "actual": palette_keys[int(indices[flat[index]])],
                    }
                )
            # Consuming each occupied cell also detects missing chunks and
            # coordinates outside every independently decoded section.
            grid[local[:, 1], local[:, 2], local[:, 0]] = absent
    for y in range(grid.shape[0]):
        mask = grid[y] != absent
        totals["missing_count"] += int(mask.sum())
        if mask.any() and len(examples["missing_examples"]) < max_examples:
            for z, x in np.argwhere(mask)[
                : max_examples - len(examples["missing_examples"])
            ]:
                examples["missing_examples"].append(
                    [int(x + minimum[0]), int(y + minimum[1]), int(z + minimum[2])]
                )
    errors = []
    totals.update(expected_bell_block_entities=len(expected_bells),
                  actual_bell_block_entities=sum(actual_bells.values()),
                  missing_bell_block_entities=len(expected_bells - actual_bells.keys()),
                  extra_bell_block_entities=len(actual_bells.keys() - expected_bells),
                  duplicate_bell_block_entities=sum(n-1 for n in actual_bells.values()))
    for key in (
        "missing_count",
        "extra_count",
        "state_mismatch_count",
        "duplicate_npz_coordinate_count",
        "duplicate_anvil_coordinate_count",
        "missing_bell_block_entities",
        "extra_bell_block_entities",
        "duplicate_bell_block_entities",
    ):
        if totals[key]:
            errors.append(f"Exact export parity: {key}={totals[key]}")
    if any(keys[i][0] in anvil.AIR_BLOCKS for i in np.unique(states)):
        errors.append("Archive lists air as occupied")
    return {**dict(totals), **examples}, errors, sorted(actual_keys), chunks
