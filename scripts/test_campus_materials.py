from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("campus_materials.py")


def load_module():
    spec = importlib.util.spec_from_file_location("campus_materials_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_state_strings_are_normalized_before_policy_checks():
    module = load_module()

    block, properties = module.parse_block_state(
        " Stone_Brick_Stairs [ facing=north, half=bottom ] "
    )

    assert block == "minecraft:stone_brick_stairs"
    assert properties == {"facing": "north", "half": "bottom"}
    assert module.is_allowed_for_role(
        "minecraft:stone_brick_stairs[facing=north,half=bottom]", "trim"
    )


@pytest.mark.parametrize(
    "block",
    [
        "minecraft:stone[",
        "minecraft:stone[]",
        "minecraft:stone[facing]",
        "minecraft:stone[facing=north,facing=south]",
    ],
)
def test_malformed_state_strings_are_rejected(block):
    module = load_module()

    with pytest.raises(ValueError):
        module.parse_block_state(block)


@pytest.mark.parametrize(
    ("block", "reason"),
    [
        ("minecraft:diamond_ore", "ore"),
        ("minecraft:deepslate_coal_ore", "ore"),
        ("minecraft:sculk_sensor[waterlogged=false]", "sculk"),
        ("minecraft:warped_planks", "Nether material"),
        ("mod:bricks", "non-minecraft namespace"),
    ],
)
def test_unambiguous_non_campus_blocks_are_globally_forbidden(block, reason):
    module = load_module()

    assert module.forbidden_reason(block) == reason


def test_role_policy_does_not_infer_intent_from_color_or_block_type():
    module = load_module()

    assert module.is_allowed_for_role("minecraft:grass_block", "terrain")
    assert not module.is_allowed_for_role("minecraft:grass_block", "facade")
    assert module.is_allowed_for_role("minecraft:deepslate_tiles", "roof")
    assert not module.is_allowed_for_role("minecraft:deepslate_tiles", "facade")


def test_chapel_details_are_allowed_only_in_their_semantic_roles():
    module = load_module()

    assert module.is_allowed_for_role("minecraft:mud_bricks", "facade")
    assert module.is_allowed_for_role(
        "minecraft:waxed_weathered_cut_copper_stairs[facing=east]", "trim"
    )
    assert module.is_allowed_for_role("minecraft:iron_bars", "railing")
    assert module.is_allowed_for_role("minecraft:lantern[hanging=true]", "lighting")
    assert not module.is_allowed_for_role("minecraft:iron_bars", "facade")
    assert not module.is_allowed_for_role("minecraft:lantern", "roof")


def test_manifest_audit_reports_wrong_roles_and_missing_site_semantics():
    module = load_module()
    manifest = {
        "materials": ["minecraft:bricks", "minecraft:sculk_sensor[waterlogged=false]"],
        "facade_palette": {
            "material_counts": {"minecraft:grass_block": 4},
            "roof_material_counts": {"minecraft:deepslate_tiles": 4},
            "trim_material_counts": {"minecraft:stone_bricks": 4},
            "window_material_counts": {"minecraft:glass": 4},
        },
        "site_feature_overlay": {
            "enabled": True,
            "stats": {"materials": ["minecraft:grass_block", "minecraft:gray_concrete"]},
        },
    }

    result = module.audit_hybrid_manifest(manifest)

    assert not result["passed"]
    assert result["global_violations"] == [
        {"block": "minecraft:sculk_sensor", "reason": "sculk"}
    ]
    assert result["role_violations"] == [
        {
            "role": "facade",
            "block": "minecraft:grass_block",
            "reason": "not allowlisted for facade",
        }
    ]
    assert result["semantic_gaps"] == [
        "site_feature_overlay.stats.materials is an unclassified union; record material_by_feature",
        "manifest material union contains blocks with no recorded semantic role",
    ]
    assert result["unclassified_materials"] == [
        "minecraft:bricks",
        "minecraft:sculk_sensor",
    ]


def test_explicit_material_roles_cover_chapel_details():
    module = load_module()
    manifest = {
        "materials": [
            "minecraft:bricks",
            "minecraft:deepslate_tiles",
            "minecraft:glass_pane",
            "minecraft:iron_bars",
            "minecraft:lantern",
            "minecraft:waxed_cut_copper_slab",
        ],
        "facade_palette": {
            "material_counts": {"minecraft:bricks": 20},
            "roof_material_counts": {"minecraft:deepslate_tiles": 10},
            "trim_material_counts": {"minecraft:waxed_cut_copper_slab": 2},
            "window_material_counts": {"minecraft:glass_pane": 4},
        },
        "material_roles": {
            "railing": {"minecraft:iron_bars": 8},
            "lighting": {"minecraft:lantern": 2},
        },
    }

    result = module.audit_hybrid_manifest(manifest)

    assert result["passed"]
    assert result["semantic_complete"]
    assert result["unclassified_materials"] == []


def test_reserved_trapdoor_states_have_intentional_semantic_roles():
    module = load_module()

    assert module.is_allowed_for_role(
        "minecraft:iron_trapdoor[facing=east,half=bottom,open=true,powered=true,waterlogged=false]",
        "fixture",
    )
    assert module.is_allowed_for_role(
        "minecraft:birch_trapdoor[facing=east,half=bottom,open=true,powered=true,waterlogged=false]",
        "window",
    )


def test_copied_palette_audit_must_name_the_candidate_world(tmp_path):
    module = load_module()
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    (candidate / "palette-audit.json").write_text(
        json.dumps({"world": str(source)}), encoding="utf-8"
    )

    result = module.audit_copied_palette_provenance(candidate)

    assert result is not None
    assert result["matches_world"] is False
    assert result["recorded_world"] == str(source.resolve())
    assert result["expected_world"] == str(candidate.resolve())


def test_manifest_without_complete_material_union_fails_semantic_audit():
    module = load_module()
    result = module.audit_hybrid_manifest(
        {
            "facade_palette": {
                "material_counts": {"minecraft:bricks": 1},
                "roof_material_counts": {"minecraft:deepslate_tiles": 1},
                "trim_material_counts": {"minecraft:stone_bricks": 1},
                "window_material_counts": {"minecraft:glass_pane": 1},
            }
        }
    )

    assert not result["passed"]
    assert "manifest records no complete material union" in result["semantic_gaps"]
