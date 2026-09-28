"""Explicit Minecraft material policy for the Hill campus reconstruction.

The policy deliberately separates material roles.  A block that is plausible
terrain is not automatically plausible on a facade, and an RGB match is never
treated as evidence of architectural intent.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


MINECRAFT_ID = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
PROPERTY_NAME = re.compile(r"^[a-z0-9_.-]+$")
PROPERTY_VALUE = re.compile(r"^[a-z0-9_.-]+$")


FACADE_BLOCKS = frozenset(
    {
        "minecraft:andesite",
        "minecraft:bricks",
        "minecraft:brick_stairs",
        "minecraft:brick_slab",
        "minecraft:blue_concrete",
        "minecraft:brown_concrete",
        "minecraft:brown_terracotta",
        "minecraft:calcite",
        "minecraft:clay",
        "minecraft:cobblestone",
        "minecraft:cut_red_sandstone",
        "minecraft:cut_sandstone",
        "minecraft:diorite",
        "minecraft:granite",
        "minecraft:gray_concrete",
        "minecraft:gray_terracotta",
        "minecraft:light_gray_concrete",
        "minecraft:light_gray_terracotta",
        "minecraft:mossy_cobblestone",
        "minecraft:mossy_stone_bricks",
        "minecraft:mud_bricks",
        "minecraft:polished_andesite",
        "minecraft:polished_diorite",
        "minecraft:polished_granite",
        "minecraft:quartz_block",
        "minecraft:quartz_bricks",
        "minecraft:quartz_pillar",
        "minecraft:red_sandstone",
        "minecraft:red_terracotta",
        "minecraft:sandstone",
        "minecraft:smooth_sandstone",
        "minecraft:smooth_red_sandstone",
        "minecraft:smooth_stone",
        "minecraft:stone",
        "minecraft:stone_bricks",
        "minecraft:cracked_stone_bricks",
        "minecraft:tuff",
        "minecraft:polished_tuff",
        "minecraft:tuff_bricks",
        "minecraft:smooth_quartz",
        "minecraft:iron_block",
        "minecraft:pale_oak_planks",
        "minecraft:terracotta",
        "minecraft:white_concrete",
        "minecraft:white_terracotta",
    }
    | {
        f"minecraft:{wood}_planks"
        for wood in (
            "acacia",
            "bamboo",
            "birch",
            "cherry",
            "dark_oak",
            "jungle",
            "mangrove",
            "oak",
            "spruce",
        )
    }
)

ROOF_BLOCKS = frozenset(
    {
        "minecraft:bricks",
        "minecraft:brick_slab",
        "minecraft:brick_stairs",
        "minecraft:dark_oak_planks",
        "minecraft:spruce_planks",
        "minecraft:spruce_slab",
        "minecraft:spruce_stairs",
        "minecraft:deepslate_bricks",
        "minecraft:deepslate_brick_slab",
        "minecraft:deepslate_brick_stairs",
        "minecraft:deepslate_tiles",
        "minecraft:deepslate_tile_slab",
        "minecraft:deepslate_tile_stairs",
        "minecraft:gray_concrete",
        "minecraft:smooth_stone",
        "minecraft:smooth_stone_slab",
        "minecraft:polished_andesite",
        "minecraft:polished_andesite_slab",
        "minecraft:polished_andesite_stairs",
        "minecraft:smooth_quartz",
        "minecraft:smooth_quartz_stairs",
        "minecraft:smooth_quartz_slab",
        "minecraft:stone_bricks",
        "minecraft:weathered_cut_copper",
        "minecraft:stone_brick_slab",
        "minecraft:stone_brick_stairs",
        "minecraft:tuff_bricks",
        "minecraft:tuff_brick_slab",
        "minecraft:tuff_brick_stairs",
        "minecraft:waxed_cut_copper",
        "minecraft:waxed_cut_copper_slab",
        "minecraft:waxed_cut_copper_stairs",
        "minecraft:waxed_exposed_cut_copper",
        "minecraft:waxed_exposed_cut_copper_slab",
        "minecraft:waxed_exposed_cut_copper_stairs",
        "minecraft:waxed_oxidized_cut_copper",
        "minecraft:waxed_oxidized_cut_copper_slab",
        "minecraft:waxed_oxidized_cut_copper_stairs",
        "minecraft:waxed_weathered_cut_copper",
        "minecraft:waxed_weathered_cut_copper_slab",
        "minecraft:waxed_weathered_cut_copper_stairs",
        "minecraft:iron_block",
    }
)

TRIM_BLOCKS = frozenset(
    {
        "minecraft:terracotta",
        "minecraft:brown_terracotta",
        "minecraft:light_gray_terracotta",
        "minecraft:white_terracotta",
        "minecraft:mud_brick_wall",
        "minecraft:bricks",
        "minecraft:brick_slab",
        "minecraft:brick_stairs",
        "minecraft:cobblestone_slab",
        "minecraft:cobblestone_stairs",
        "minecraft:cut_sandstone_slab",
        "minecraft:light_gray_concrete",
        "minecraft:mud_brick_slab",
        "minecraft:mud_brick_stairs",
        "minecraft:mud_bricks",
        "minecraft:polished_andesite",
        "minecraft:polished_andesite_slab",
        "minecraft:polished_andesite_stairs",
        "minecraft:quartz_block",
        "minecraft:quartz_slab",
        "minecraft:quartz_stairs",
        "minecraft:quartz_pillar",
        "minecraft:iron_bars",
        "minecraft:sandstone_slab",
        "minecraft:sandstone_wall",
        "minecraft:sandstone_stairs",
        "minecraft:smooth_sandstone_slab",
        "minecraft:smooth_sandstone_stairs",
        "minecraft:smooth_red_sandstone",
        "minecraft:smooth_red_sandstone_stairs",
        "minecraft:smooth_red_sandstone_slab",
        "minecraft:red_sandstone_wall",
        "minecraft:smooth_sandstone",
        "minecraft:smooth_stone",
        "minecraft:smooth_stone_slab",
        "minecraft:stone_brick_slab",
        "minecraft:stone_brick_stairs",
        "minecraft:stone_bricks",
        "minecraft:waxed_cut_copper",
        "minecraft:waxed_cut_copper_slab",
        "minecraft:waxed_cut_copper_stairs",
        "minecraft:waxed_exposed_cut_copper",
        "minecraft:waxed_exposed_cut_copper_slab",
        "minecraft:waxed_exposed_cut_copper_stairs",
        "minecraft:waxed_oxidized_cut_copper",
        "minecraft:waxed_oxidized_cut_copper_slab",
        "minecraft:waxed_oxidized_cut_copper_stairs",
        "minecraft:waxed_weathered_cut_copper",
        "minecraft:waxed_weathered_cut_copper_slab",
        "minecraft:waxed_weathered_cut_copper_stairs",
        "minecraft:white_concrete",
        "minecraft:calcite",
        "minecraft:polished_diorite",
        "minecraft:polished_diorite_slab",
        "minecraft:polished_diorite_stairs",
        "minecraft:smooth_quartz",
        "minecraft:smooth_quartz_slab",
        "minecraft:smooth_quartz_stairs",
        "minecraft:tuff_bricks",
        "minecraft:tuff_brick_slab",
        "minecraft:tuff_brick_stairs",
        "minecraft:tuff_brick_wall",
        "minecraft:iron_block",
    }
)

WINDOW_BLOCKS = frozenset(
    {
        "minecraft:white_stained_glass_pane",
        "minecraft:white_stained_glass",
        "minecraft:gray_stained_glass_pane",
        "minecraft:gray_stained_glass",
        "minecraft:black_stained_glass",
        "minecraft:black_stained_glass_pane",
        "minecraft:birch_trapdoor",
        "minecraft:acacia_trapdoor",
        "minecraft:pale_oak_trapdoor",
        "minecraft:glass",
        "minecraft:glass_pane",
    }
    | {
        f"minecraft:{colour}_stained_glass{shape}"
        for colour in (
            "white", "orange", "magenta", "light_blue", "yellow", "lime",
            "pink", "gray", "light_gray", "cyan", "purple", "blue",
            "brown", "green", "red", "black",
        )
        for shape in ("", "_pane")
    }
)

TERRAIN_BLOCKS = frozenset(
    {
        "minecraft:clay",
        "minecraft:coarse_dirt",
        "minecraft:dirt",
        "minecraft:grass_block",
        "minecraft:gravel",
        "minecraft:moss_block",
        "minecraft:mud",
        "minecraft:packed_mud",
        "minecraft:rooted_dirt",
        "minecraft:stone",
        "minecraft:water",
    }
)

PAVEMENT_BLOCKS = frozenset(
    {
        "minecraft:mud_bricks",
        "minecraft:mud_brick_slab",
        "minecraft:brick_slab",
        "minecraft:polished_deepslate",
        "minecraft:bricks",
        "minecraft:polished_deepslate_slab",
        "minecraft:polished_deepslate_stairs",
        "minecraft:blue_concrete",
        "minecraft:coarse_dirt",
        "minecraft:gray_concrete",
        "minecraft:green_concrete",
        "minecraft:light_gray_concrete",
        "minecraft:red_concrete",
        "minecraft:smooth_stone",
        "minecraft:smooth_stone_slab",
        "minecraft:stone_bricks",
        "minecraft:stone_brick_slab",
        "minecraft:stone_brick_stairs",
        "minecraft:white_concrete",
    }
)

_TREE_SPECIES = (
    "acacia",
    "birch",
    "cherry",
    "dark_oak",
    "jungle",
    "mangrove",
    "oak",
    "pale_oak",
    "spruce",
)
VEGETATION_BLOCKS = frozenset(
    {
        "minecraft:short_dry_grass",
        "minecraft:tall_dry_grass",
        "minecraft:azure_bluet",
        "minecraft:bamboo",
        "minecraft:bamboo_block",
        "minecraft:dandelion",
        "minecraft:fern",
        "minecraft:large_fern",
        "minecraft:lilac",
        "minecraft:moss_block",
        "minecraft:oxeye_daisy",
        "minecraft:peony",
        "minecraft:poppy",
        "minecraft:rose_bush",
        "minecraft:short_grass",
        "minecraft:tall_grass",
        "minecraft:vine",
    }
    | {
        f"minecraft:{species}_{suffix}"
        for species in _TREE_SPECIES
        for suffix in ("leaves", "log", "wood")
    }
    | {
        f"minecraft:stripped_{species}_{suffix}"
        for species in _TREE_SPECIES
        for suffix in ("log", "wood")
    }
)

RAILING_BLOCKS = frozenset(
    {
        "minecraft:cobblestone_wall",
        "minecraft:iron_bars",
        "minecraft:mossy_cobblestone_wall",
        "minecraft:mossy_stone_brick_wall",
        "minecraft:stone_brick_wall",
    }
) | frozenset(f"minecraft:{wood}_fence" for wood in _TREE_SPECIES)

# Painted timber porches need the same ordinary wood components as furniture.
# A construction role is still checked before any colour selection occurs.
TRIM_BLOCKS = TRIM_BLOCKS | frozenset(
    f"minecraft:{wood}_{part}"
    for wood in _TREE_SPECIES
    for part in ("planks", "slab", "stairs", "trapdoor", "fence")
)

LIGHTING_BLOCKS = frozenset(
    {
        "minecraft:lantern",
        "minecraft:torch",
        "minecraft:wall_torch",
    }
)

ROLE_ALLOWLISTS: Mapping[str, frozenset[str]] = {
    "furniture": frozenset(
        f"minecraft:{wood}_{part}"
        for wood in _TREE_SPECIES
        for part in (
            "planks",
            "slab",
            "stairs",
            "trapdoor",
            "fence",
            "pressure_plate",
            "button",
        )
    )
    | frozenset(
        f"minecraft:{color}_carpet"
        for color in (
            "white",
            "light_gray",
            "gray",
            "black",
            "brown",
            "red",
            "orange",
            "yellow",
            "lime",
            "green",
            "cyan",
            "light_blue",
            "blue",
            "purple",
            "magenta",
            "pink",
        )
    ),
    "fixture": frozenset(
        {
            "minecraft:white_concrete",
            "minecraft:black_concrete",
            "minecraft:iron_trapdoor",
            # Source-visible campus bell memorial and its thin metal support.
            "minecraft:bell",
            "minecraft:iron_bars",
        }
    ),
    "door": frozenset(f"minecraft:{wood}_door" for wood in _TREE_SPECIES),
    "floor": PAVEMENT_BLOCKS
    | frozenset(
        f"minecraft:{wood}_{part}"
        for wood in _TREE_SPECIES
        for part in ("planks", "slab")
    ),
    "facade": FACADE_BLOCKS,
    "roof": ROOF_BLOCKS,
    "trim": TRIM_BLOCKS,
    "window": WINDOW_BLOCKS,
    "terrain": TERRAIN_BLOCKS,
    "pavement": PAVEMENT_BLOCKS,
    "vegetation": VEGETATION_BLOCKS,
    "railing": RAILING_BLOCKS,
    "lighting": LIGHTING_BLOCKS,
}

FORBIDDEN_EXACT_BLOCKS = frozenset(
    {
        "minecraft:ancient_debris",
        "minecraft:blackstone",
        "minecraft:coal_block",
        "minecraft:crying_obsidian",
        "minecraft:diamond_block",
        "minecraft:emerald_block",
        "minecraft:end_stone",
        "minecraft:glowstone",
        "minecraft:gold_block",
        "minecraft:lapis_block",
        "minecraft:magma_block",
        "minecraft:netherrack",
        "minecraft:netherite_block",
        "minecraft:obsidian",
        "minecraft:polished_blackstone",
        "minecraft:polished_blackstone_bricks",
        "minecraft:redstone_block",
        "minecraft:soul_sand",
        "minecraft:soul_soil",
    }
)


def parse_block_state(block_state: str) -> tuple[str, dict[str, str]]:
    """Return canonical block id and validated properties from a state string."""

    if not isinstance(block_state, str) or not block_state.strip():
        raise ValueError("block state must be a non-empty string")
    text = block_state.strip().lower()
    properties: dict[str, str] = {}
    if "[" in text:
        if not text.endswith("]") or text.count("[") != 1 or text.count("]") != 1:
            raise ValueError(f"invalid block state syntax: {block_state!r}")
        text, raw_properties = text[:-1].split("[", 1)
        text = text.strip()
        if not raw_properties:
            raise ValueError(f"empty block state properties: {block_state!r}")
        for pair in raw_properties.split(","):
            if pair.count("=") != 1:
                raise ValueError(f"invalid block state property: {pair!r}")
            key, value = (part.strip() for part in pair.split("=", 1))
            if not PROPERTY_NAME.fullmatch(key) or not PROPERTY_VALUE.fullmatch(value):
                raise ValueError(f"invalid block state property: {pair!r}")
            if key in properties:
                raise ValueError(f"duplicate block state property: {key!r}")
            properties[key] = value
    elif "]" in text:
        raise ValueError(f"invalid block state syntax: {block_state!r}")

    if ":" not in text:
        text = f"minecraft:{text}"
    if not MINECRAFT_ID.fullmatch(text):
        raise ValueError(f"invalid block id: {block_state!r}")
    return text, properties


def block_id(block_state: str) -> str:
    return parse_block_state(block_state)[0]


def forbidden_reason(block_state: str) -> str | None:
    """Return the unambiguous global rejection reason, independent of role."""

    canonical = block_id(block_state)
    namespace, name = canonical.split(":", 1)
    if namespace != "minecraft":
        return "non-minecraft namespace"
    if canonical in FORBIDDEN_EXACT_BLOCKS:
        return "non-campus fantasy or storage material"
    if name.endswith("_ore"):
        return "ore"
    if name == "sculk" or name.startswith("sculk_"):
        return "sculk"
    if "nether" in name or name.startswith(("warped_", "crimson_", "blackstone")):
        return "Nether material"
    return None


def is_allowed_for_role(block_state: str, role: str) -> bool:
    if role not in ROLE_ALLOWLISTS:
        raise KeyError(f"unknown material role: {role}")
    canonical = block_id(block_state)
    return forbidden_reason(canonical) is None and canonical in ROLE_ALLOWLISTS[role]


def audit_role_materials(
    role_materials: Mapping[str, Iterable[str]],
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for role, materials in role_materials.items():
        if role not in ROLE_ALLOWLISTS:
            violations.append(
                {"role": role, "block": "", "reason": "unknown semantic material role"}
            )
            continue
        for raw_block in materials:
            try:
                canonical = block_id(raw_block)
                reason = forbidden_reason(canonical)
            except ValueError as exc:
                violations.append(
                    {"role": role, "block": str(raw_block), "reason": str(exc)}
                )
                continue
            if reason is None and canonical not in ROLE_ALLOWLISTS[role]:
                reason = f"not allowlisted for {role}"
            if reason is not None:
                violations.append({"role": role, "block": canonical, "reason": reason})
    return violations


def _counted_materials(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(block) for block, count in value.items() if int(count or 0) > 0]
    if isinstance(value, list):
        return [str(block) for block in value]
    return []


def audit_hybrid_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Audit material evidence in a hill-hybrid manifest without inventing roles."""

    facade = manifest.get("facade_palette") or {}
    role_materials = {
        "facade": _counted_materials(facade.get("material_counts")),
        "roof": _counted_materials(facade.get("roof_material_counts")),
        "trim": _counted_materials(facade.get("trim_material_counts")),
        "window": _counted_materials(facade.get("window_material_counts")),
    }
    for role, materials in (manifest.get("material_roles") or {}).items():
        role_materials.setdefault(str(role), []).extend(_counted_materials(materials))
    role_materials = {
        role: list(dict.fromkeys(materials))
        for role, materials in role_materials.items()
    }
    semantic_gaps: list[str] = []
    if not manifest.get("materials"):
        semantic_gaps.append("manifest records no complete material union")
    for role, materials in role_materials.items():
        if not materials:
            semantic_gaps.append(f"manifest records no {role} material counts")

    site_role_materials: dict[str, list[str]] = {"terrain": [], "pavement": []}
    for key in ("site_feature_overlay", "named_road_surface_overlay"):
        overlay = manifest.get(key) or {}
        stats = overlay.get("stats") or {}
        material_by_feature = stats.get("material_by_feature") or {}
        for feature, materials in material_by_feature.items():
            role = (
                "terrain" if feature in {"baseball", "field", "water"} else "pavement"
            )
            site_role_materials[role].extend(_counted_materials(materials))
        if (
            overlay.get("enabled")
            and stats.get("materials")
            and not material_by_feature
        ):
            semantic_gaps.append(
                f"{key}.stats.materials is an unclassified union; record material_by_feature"
            )
    for role, materials in site_role_materials.items():
        if materials:
            role_materials.setdefault(role, []).extend(materials)
            role_materials[role] = list(dict.fromkeys(role_materials[role]))

    global_violations: list[dict[str, str]] = []
    invalid_materials: list[dict[str, str]] = []
    global_materials = _counted_materials(manifest.get("materials"))
    canonical_global_materials: set[str] = set()
    for raw_block in global_materials:
        try:
            canonical = block_id(raw_block)
            reason = forbidden_reason(canonical)
        except ValueError as exc:
            invalid_materials.append({"block": raw_block, "reason": str(exc)})
            continue
        canonical_global_materials.add(canonical)
        if reason is not None:
            global_violations.append({"block": canonical, "reason": reason})

    classified: set[str] = set()
    for materials in role_materials.values():
        for raw_block in materials:
            try:
                classified.add(block_id(raw_block))
            except ValueError:
                pass
    unclassified_materials = sorted(canonical_global_materials - classified)
    if unclassified_materials:
        semantic_gaps.append(
            "manifest material union contains blocks with no recorded semantic role"
        )

    role_violations = audit_role_materials(role_materials)
    passed = not (
        global_violations or invalid_materials or role_violations or semantic_gaps
    )
    return {
        "format": "hill-campus-material-policy-audit-v1",
        "passed": passed,
        "semantic_complete": not semantic_gaps,
        "role_materials": role_materials,
        "role_violations": role_violations,
        "global_violations": global_violations,
        "invalid_materials": invalid_materials,
        "unclassified_materials": unclassified_materials,
        "semantic_gaps": semantic_gaps,
    }


def audit_copied_palette_provenance(world: Path) -> dict[str, Any] | None:
    audit_path = world / "palette-audit.json"
    if not audit_path.is_file():
        return None
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    recorded = Path(str(payload.get("world") or ""))
    if not recorded.is_absolute():
        recorded = Path.cwd() / recorded
    expected = world.resolve()
    recorded = recorded.resolve()
    return {
        "path": str(audit_path),
        "recorded_world": str(recorded),
        "expected_world": str(expected),
        "matches_world": recorded == expected,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--world", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest_path = args.manifest.resolve()
    result = audit_hybrid_manifest(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if args.world:
        world = args.world.resolve()
        provenance = audit_copied_palette_provenance(world)
        result["copied_palette_audit"] = provenance
        if provenance is not None and not provenance["matches_world"]:
            result["passed"] = False
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
