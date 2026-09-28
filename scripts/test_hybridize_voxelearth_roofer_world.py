from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("hybridize_voxelearth_roofer_world.py")


def load_module():
    spec = importlib.util.spec_from_file_location("hill_hybrid_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_defaults_use_flat_procedural_campus_ground():
    module = load_module()
    args = module.build_parser().parse_args([])

    assert args.building_source == "npz"
    assert args.building_name_filter is None
    assert args.apron_clear_radius == 6
    assert args.terrain_only_fallback is False
    assert args.procedural_campus_ground_y == 91
    assert args.sandlike_top_cleanup is True
    assert args.campus_architecture_cleanup is True
    assert module.build_parser().parse_args(["--no-campus-architecture-cleanup"]).campus_architecture_cleanup is False
    assert args.campus_core_radius == 512
    assert args.site_feature_overlay is True
    assert args.osm_site_features == module.DEFAULT_OSM_SITE_FEATURES
    assert args.named_road_surface_overlay is True
    assert args.campus_surfaces == module.DEFAULT_CAMPUS_SURFACES
    assert args.building_seam_fill_radius == 0
    assert args.official_building_seam_fill_radius == 0
    assert args.campus_buildings == module.DEFAULT_CAMPUS_BUILDINGS
    assert args.campus_boundary == module.DEFAULT_CAMPUS_BOUNDARY
    assert args.chapel_apron_cleanup_radius == 0
    assert args.chapel_procedural_section_radius == 0
    assert args.fill_air_support is True
    assert args.min_source_column_coverage == 0.25
    assert args.min_support_column_coverage == 0.90


def test_clean_roofer_buildings_do_not_enable_synthetic_ground_rings_by_default():
    module = load_module()
    args = module.build_parser().parse_args([])

    assert args.building_seam_fill_radius == 0
    assert args.official_building_seam_fill_radius == 0
    assert args.chapel_apron_cleanup_radius == 0
    assert args.chapel_procedural_section_radius == 0


def test_material_colors_come_from_voxelearth_vanilla_atlas():
    module = load_module()
    atlas = json.loads(module.DEFAULT_VANILLA_ATLAS.read_text(encoding="utf-8"))
    brick = next(block for block in atlas["blocks"] if block["name"] == "minecraft:bricks")
    expected = tuple(int(brick["colour"][channel] * 255) for channel in ("r", "g", "b"))

    assert module.MATERIAL_COLORS["minecraft:bricks"] == expected
    assert "minecraft:black_concrete" not in module.MATERIAL_COLORS
    assert "minecraft:coal_ore" not in module.MATERIAL_COLORS
    assert "minecraft:bricks" in module.FACADE_PALETTE


def test_overlay_clear_preserves_support_block_below_floor():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={(10, 20): (80, 85)},
        edit_columns=1,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["TEST"],
        anchors=[],
        skipped=[],
    )
    edit_mask = set()
    world = FakeWorld()

    module.clear_overlay_volumes(
        world,
        overlay,
        {(10, 20): (90, "minecraft:grass_block")},
        edit_mask,
    )

    cleared_ys = [y for _x, y, _z, _block in world.calls]
    assert min(cleared_ys) == 80
    assert (10, 79, 20) not in edit_mask


def test_source_palette_drives_overlay_wall_material():
    module = load_module()

    class FakeSource:
        def get_block(self, _x, _y, _z):
            return "minecraft:light_gray_concrete"

    raw_blocks = {(0, y, 0) for y in range(64, 69)}

    materials, sample = module.material_set_from_source(
        FakeSource(),
        raw_blocks,
        name="neutral facade",
        min_y=64,
        max_y=68,
    )

    assert materials["wall"] == "minecraft:light_gray_concrete"
    assert materials["wall"] != "minecraft:bricks"
    assert sample["source_wall_samples"] > 0


def test_chapel_materials_keep_dark_roof_and_stained_glass():
    module = load_module()

    class FakeSource:
        def get_block(self, _x, _y, _z):
            return "minecraft:stone_bricks"

    raw_blocks = {(0, y, 0) for y in range(92, 100)}

    materials, sample = module.material_set_from_source(
        FakeSource(),
        raw_blocks,
        name="CHAPEL - BLDG #23",
        min_y=92,
        max_y=99,
    )

    assert materials["wall"] == "minecraft:bricks"
    assert materials["roof"] == "minecraft:deepslate_tiles"
    assert materials["window"] == "minecraft:black_stained_glass"
    assert sample["material_override"] == "chapel-landmark"


def test_chapel_wall_rhythm_uses_buttresses_tracery_and_wide_windows():
    module = load_module()
    materials = dict(module.CHAPEL_LANDMARK_MATERIALS)

    assert module.chapel_overlay_wall_material(
        materials, "wall_x", 0, 96, 0, 92, 109
    ) == "minecraft:stone_bricks"
    assert module.chapel_overlay_wall_material(
        materials, "wall_x", 0, 96, 2, 92, 109
    ) == "minecraft:stone_bricks"
    assert module.chapel_overlay_wall_material(
        materials, "wall_x", 0, 96, 4, 92, 109
    ) == "minecraft:black_stained_glass"
    assert module.chapel_overlay_wall_material(
        materials, "wall_x", 0, 96, 7, 92, 109
    ) == "minecraft:bricks"


def test_chapel_landmark_blocks_add_cross_and_battlements():
    module = load_module()
    materials = dict(module.CHAPEL_LANDMARK_MATERIALS)
    raw_blocks = {
        (x, y, z)
        for x in range(0, 4)
        for z in range(0, 4)
        for y in range(72, 82)
    }

    feature_blocks = module.generate_chapel_landmark_blocks(raw_blocks, materials)
    roles = {role for _x, _y, _z, _block, role in feature_blocks}
    blocks = {block for _x, _y, _z, block, _role in feature_blocks}
    ys = [y for _x, y, _z, _block, _role in feature_blocks]

    assert "landmark_cross" in roles
    assert "landmark_trim" in roles
    assert "minecraft:deepslate_tiles" in blocks
    assert "minecraft:stone_bricks" in blocks
    assert max(ys) > 82

    cross_columns = [
        (x, z)
        for x, _y, z, _block, role in feature_blocks
        if role == "landmark_cross"
    ]
    assert max(abs(x - 2) for x, _z in cross_columns) <= 1
    assert max(abs(z - 2) for _x, z in cross_columns) <= 1


def test_chapel_shell_hollowing_keeps_floor_walls_and_roof():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(5)
        for y in range(70, 75)
        for z in range(5)
    }

    shell, removed = module.hollow_chapel_blocks(raw_blocks)

    assert (2, 70, 2) in shell  # one-block floor
    assert (0, 72, 2) in shell  # exterior wall
    assert (2, 72, 0) in shell  # exterior wall
    assert (2, 74, 2) in shell  # roof
    assert (2, 71, 2) not in shell
    assert (2, 72, 2) not in shell
    assert (2, 73, 2) not in shell
    assert removed == 27


def test_generic_building_shell_hollowing_keeps_only_floor_walls_and_roof():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(7)
        for y in range(70, 77)
        for z in range(7)
    }

    shell, removed = module.hollow_building_blocks(raw_blocks)

    assert (3, 70, 3) in shell
    assert (0, 73, 3) in shell
    assert (3, 73, 0) in shell
    assert (3, 76, 3) in shell
    assert (3, 71, 3) not in shell
    assert (3, 75, 3) not in shell
    assert removed == 125


def test_procedural_building_windows_use_panes_and_oriented_stair_frames():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(9)
        for y in range(70, 77)
        for z in range(9)
    }
    materials = {
        "wall": "minecraft:bricks",
        "trim": "minecraft:stone_bricks",
        "roof": "minecraft:deepslate_tiles",
        "window": "minecraft:glass",
        "floor": "minecraft:smooth_stone",
    }

    result = module.generate_procedural_building_blocks(
        raw_blocks,
        materials,
        name="ACADEMIC CENTER - BLDG #1",
    )
    by_coordinate = {
        (x, y, z): (block, role)
        for x, y, z, block, role in result.blocks
    }

    assert (4, 72, 4) not in by_coordinate
    assert by_coordinate[(0, 72, 2)] == ("minecraft:glass_pane", "window_pane")
    assert by_coordinate[(0, 73, 2)] == ("minecraft:glass_pane", "window_pane")
    assert by_coordinate[(0, 71, 2)] == ("minecraft:stone_brick_stairs", "window_sill")
    assert by_coordinate[(0, 74, 2)] == ("minecraft:stone_brick_stairs", "window_lintel")
    assert result.block_states[(0, 72, 2)] == {
        "east": "false",
        "north": "true",
        "south": "true",
        "waterlogged": "false",
        "west": "false",
    }
    assert result.block_states[(0, 71, 2)] == {
        "facing": "east",
        "half": "bottom",
        "shape": "straight",
        "waterlogged": "false",
    }
    assert result.block_states[(0, 74, 2)] == {
        "facing": "east",
        "half": "top",
        "shape": "straight",
        "waterlogged": "false",
    }
    assert not any(block == "minecraft:glass" for block, _role in by_coordinate.values())
    assert not any(role == "fill" for _block, role in by_coordinate.values())
    assert result.stats["hollowed_interior_voxels"] > 0
    assert result.stats["window_panes"] > 0
    assert result.stats["window_sills"] == result.stats["window_lintels"]


def test_google_voxelearth_window_evidence_drives_validated_window_assembly():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(9)
        for y in range(70, 77)
        for z in range(9)
    }
    detected = {(0, 72, 5), (0, 73, 5)}
    materials = {
        "wall": "minecraft:bricks",
        "trim": "minecraft:stone_bricks",
        "roof": "minecraft:deepslate_tiles",
        "window": "minecraft:black_stained_glass",
        "floor": "minecraft:smooth_stone",
    }

    result = module.generate_procedural_building_blocks(
        raw_blocks,
        materials,
        name="MEMORIAL HALL - BLDG #2",
        detected_window_voxels=detected,
    )
    by_coordinate = {
        (x, y, z): (block, role)
        for x, y, z, block, role in result.blocks
    }

    assert result.window_mode == "voxelearth-source-glass-detected"
    assert by_coordinate[(0, 72, 5)] == (
        "minecraft:black_stained_glass_pane",
        "window_pane",
    )
    assert by_coordinate[(0, 73, 5)] == (
        "minecraft:black_stained_glass_pane",
        "window_pane",
    )
    assert by_coordinate[(0, 71, 5)][1] == "window_sill"
    assert by_coordinate[(0, 74, 5)][1] == "window_lintel"
    assert not any(role == "window_pane" and z in {2, 3} for (x, _y, z), (_block, role) in by_coordinate.items() if x == 0)


def test_source_window_detector_uses_exact_google_voxelearth_glass_cells_only():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(5)
        for y in range(70, 75)
        for z in range(5)
    }

    class FakeSource:
        def get_block(self, x, y, z):
            if (x, y, z) in {(0, 72, 2), (0, 73, 2), (2, 72, 2)}:
                return "minecraft:blue_stained_glass"
            if (x, y, z) == (1, 72, 2):
                return "minecraft:glass_pane"
            return "minecraft:bricks"

    detected = module.detect_source_window_voxels(FakeSource(), raw_blocks)

    assert detected == {(0, 72, 2), (0, 73, 2)}


def test_section_editor_round_trips_pane_and_stair_block_states():
    module = load_module()
    section = module.tag.Compound(
        {
            "Y": module.tag.Byte(0),
            "block_states": module.tag.Compound(
                {
                    "palette": module.tag.List[module.tag.Compound](
                        [module.block_entry(module.AIR)]
                    )
                }
            ),
        }
    )
    editor = module.SectionEditor(section)
    pane_properties = {
        "east": "false",
        "north": "true",
        "south": "true",
        "waterlogged": "false",
        "west": "false",
    }
    stair_properties = {
        "facing": "west",
        "half": "top",
        "shape": "straight",
        "waterlogged": "false",
    }

    assert editor.set_state(1, 2, 3, "minecraft:glass_pane", pane_properties)
    assert editor.set_state(4, 5, 6, "minecraft:stone_brick_stairs", stair_properties)
    editor.compact()

    reloaded = module.SectionEditor(section)
    assert reloaded.get_state(1, 2, 3) == ("minecraft:glass_pane", pane_properties)
    assert reloaded.get_state(4, 5, 6) == (
        "minecraft:stone_brick_stairs",
        stair_properties,
    )


def test_section_editor_keeps_same_block_name_with_distinct_properties():
    module = load_module()
    section = module.tag.Compound(
        {
            "Y": module.tag.Byte(0),
            "block_states": module.tag.Compound(
                {
                    "palette": module.tag.List[module.tag.Compound](
                        [module.block_entry(module.AIR)]
                    )
                }
            ),
        }
    )
    editor = module.SectionEditor(section)
    along_z = module.pane_properties_for_wall("wall_x")
    along_x = module.pane_properties_for_wall("wall_z")

    assert editor.set_state(1, 2, 3, "minecraft:glass_pane", along_z)
    assert editor.set_state(2, 2, 3, "minecraft:glass_pane", along_x)
    editor.compact()

    reloaded = module.SectionEditor(section)
    assert reloaded.get_state(1, 2, 3) == ("minecraft:glass_pane", along_z)
    assert reloaded.get_state(2, 2, 3) == ("minecraft:glass_pane", along_x)
    assert sum(name == "minecraft:glass_pane" for name, _props in reloaded.state_keys) == 2


def test_window_stairs_face_inward_on_all_four_facades():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(9)
        for y in range(70, 77)
        for z in range(9)
    }
    materials = {
        "wall": "minecraft:bricks",
        "trim": "minecraft:stone_bricks",
        "roof": "minecraft:deepslate_tiles",
        "window": "minecraft:glass",
        "floor": "minecraft:smooth_stone",
    }
    result = module.generate_procedural_building_blocks(
        raw_blocks,
        materials,
        name="FOUR SIDED TEST BUILDING",
    )

    expected_sill_facings = {
        (0, 71, 2): "east",
        (8, 71, 2): "west",
        (2, 71, 0): "south",
        (2, 71, 8): "north",
    }
    for coordinate, facing in expected_sill_facings.items():
        assert result.block_states[coordinate]["facing"] == facing
        assert result.block_states[coordinate]["half"] == "bottom"


def test_place_overlay_blocks_writes_stateful_window_blocks():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.plain_calls = []
            self.state_calls = []

        def set_block(self, x, y, z, block_name):
            self.plain_calls.append((x, y, z, block_name))
            return True

        def set_block_state(self, x, y, z, block_name, properties):
            self.state_calls.append((x, y, z, block_name, properties))
            return True

    pane_properties = module.pane_properties_for_wall("wall_x")
    overlay = module.VoxelBuildingOverlay(
        blocks=[
            (1, 70, 1, "minecraft:smooth_stone", "floor"),
            (1, 72, 1, "minecraft:glass_pane", "window_pane"),
        ],
        support_blocks={},
        clear_columns={},
        edit_columns=0,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["TEST"],
        anchors=[],
        skipped=[],
        block_states={(1, 72, 1): pane_properties},
    )
    world = FakeWorld()
    edit_mask = set()

    stats = module.place_overlay_blocks(world, overlay, edit_mask)

    assert world.plain_calls == [(1, 70, 1, "minecraft:smooth_stone")]
    assert world.state_calls == [
        (1, 72, 1, "minecraft:glass_pane", pane_properties)
    ]
    assert edit_mask == {(1, 70, 1), (1, 72, 1)}
    assert stats["stateful_blocks"] == 1
    assert stats["window_pane"] == 1


def test_shell_window_audit_checks_hollow_air_and_serialized_states(monkeypatch):
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(9)
        for y in range(70, 77)
        for z in range(9)
    }
    materials = {
        "wall": "minecraft:bricks",
        "trim": "minecraft:stone_bricks",
        "roof": "minecraft:deepslate_tiles",
        "window": "minecraft:glass",
        "floor": "minecraft:smooth_stone",
    }
    result = module.generate_procedural_building_blocks(
        raw_blocks,
        materials,
        name="AUDITED BUILDING",
    )
    expected = {
        (x, y, z): block
        for x, y, z, block, _role in result.blocks
    }

    class FakeWorld:
        def __init__(self, _path):
            pass

        def get_block(self, x, y, z):
            return expected.get((x, y, z), module.AIR)

        def get_block_state(self, x, y, z):
            coordinate = (x, y, z)
            return (
                expected.get(coordinate, module.AIR),
                result.block_states.get(coordinate, {}),
            )

    monkeypatch.setattr(module, "AnvilWorld", FakeWorld)
    overlay = module.VoxelBuildingOverlay(
        blocks=result.blocks,
        support_blocks={},
        clear_columns={},
        edit_columns=0,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["AUDITED BUILDING"],
        anchors=[],
        skipped=[],
        block_states=result.block_states,
    )

    audit = module.audit_overlay_shell_windows(Path("world"), overlay)

    assert audit["non_air_interior_blocks"] == 0
    assert audit["interior_air_blocks_checked"] > 0
    assert audit["state_mismatches"] == 0
    assert audit["pane_blocks"] > 0
    assert audit["stair_blocks"] > 0
    assert audit["full_glass_blocks"] == 0


def test_procedural_chapel_shell_preserves_nave_and_tower_roof_profiles():
    module = load_module()
    raw_blocks = {
        (x, y, z)
        for x in range(5)
        for y in range(70, 75)
        for z in range(5)
    }
    raw_blocks.update(
        (x, y, z)
        for x in range(2)
        for y in range(75, 80)
        for z in range(2)
    )

    generated = module.generate_chapel_procedural_blocks(
        raw_blocks,
        dict(module.CHAPEL_LANDMARK_MATERIALS),
    )
    by_coordinate = {
        (x, y, z): (block, role)
        for x, y, z, block, role in generated
    }

    assert by_coordinate[(2, 70, 2)][0] == "minecraft:smooth_stone"
    assert by_coordinate[(2, 74, 2)] == ("minecraft:deepslate_tiles", "roof")
    assert (2, 79, 2) not in by_coordinate
    assert by_coordinate[(0, 79, 0)] == ("minecraft:deepslate_tiles", "roof")
    assert (2, 71, 2) not in by_coordinate
    assert (2, 72, 2) not in by_coordinate
    assert (2, 73, 2) not in by_coordinate
    assert not any(block == "minecraft:glowstone" for block, _role in by_coordinate.values())


def test_procedural_chapel_section_is_flat_solid_and_updates_surface_model():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.blocks = {}
            self.calls = []

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            changed = self.blocks.get((x, y, z), module.AIR) != block_name
            self.blocks[(x, y, z)] = block_name
            return changed

    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={(x, z): (72, 80) for x in range(3) for z in range(3)},
        edit_columns=9,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["CHAPEL - BLDG #23"],
        anchors=[
            {
                "name": "CHAPEL - BLDG #23",
                "bbox": [0, 72, 0, 2, 80, 2],
                "voxelearth_ring_ground_y": 72,
            }
        ],
        skipped=[],
    )
    source_top = {
        (-1, -1): (65, "minecraft:grass_block"),
        (3, 3): (90, "minecraft:oak_leaves"),
    }
    edit_mask = set()
    world = FakeWorld()

    stats = module.apply_chapel_procedural_section(
        world,
        overlay,
        source_top,
        radius=1,
        minimum_y=64,
        edit_mask=edit_mask,
    )

    expected_columns = {(x, z) for x in range(-1, 4) for z in range(-1, 4)}
    assert stats["enabled"] is True
    assert stats["chapel_count"] == 1
    assert stats["columns"] == 25
    assert stats["target_ground_y"] == 71
    assert stats["previous_ground_y_min"] == 65
    assert stats["previous_ground_y_max"] == 90
    assert all(source_top[column] == (71, module.CHAPEL_SECTION_SURFACE_BLOCK) for column in expected_columns)
    assert all(world.blocks[(x, 71, z)] == module.CHAPEL_SECTION_SURFACE_BLOCK for x, z in expected_columns)
    assert all(world.blocks[(x, 70, z)] == module.CHAPEL_SECTION_SUBSURFACE_BLOCK for x, z in expected_columns)
    assert all(world.blocks[(x, 64, z)] == module.CHAPEL_SECTION_DEEP_BLOCK for x, z in expected_columns)
    assert all(world.blocks[(x, 72, z)] == module.AIR for x, z in expected_columns)
    assert set(world.blocks) == edit_mask


def test_facade_palette_manifest_aggregates_sampled_materials():
    module = load_module()

    overlay = module.VoxelBuildingOverlay(
        blocks=[
            (1, 70, 1, "minecraft:bricks", "wall_x"),
            (1, 71, 1, "minecraft:stone_bricks", "wall_corner"),
            (1, 72, 1, "minecraft:deepslate_tiles", "roof"),
            (2, 70, 1, "minecraft:light_gray_concrete", "wall_z"),
        ],
        support_blocks={},
        clear_columns={},
        edit_columns=0,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=2,
        building_names=["A", "B"],
        anchors=[
            {
                "material_sample": {
                    "wall_material": "minecraft:bricks",
                    "trim_material": "minecraft:stone_bricks",
                    "roof_material": "minecraft:deepslate_tiles",
                    "window_material": "minecraft:glass",
                    "source_wall_samples": 10,
                    "source_roof_samples": 3,
                    "source_window_samples": 2,
                    "wall_source_blocks": {"minecraft:bricks": 10},
                    "roof_source_blocks": {"minecraft:deepslate_tiles": 3},
                }
            },
            {
                "material_sample": {
                    "wall_material": "minecraft:light_gray_concrete",
                    "trim_material": "minecraft:smooth_stone",
                    "roof_material": "minecraft:gray_concrete",
                    "window_material": "minecraft:glass",
                    "source_wall_samples": 8,
                    "source_roof_samples": 1,
                    "source_window_samples": 0,
                    "wall_source_blocks": {"minecraft:light_gray_concrete": 8},
                    "roof_source_blocks": {"minecraft:gray_concrete": 1},
                }
            },
        ],
        skipped=[],
    )

    manifest = module.aggregate_facade_palette(overlay)

    assert manifest["mode"] == "voxelearth-dominant-facade-nearest-block"
    assert manifest["colour_space"] == "oklab"
    assert manifest["sampled_buildings"] == 2
    assert manifest["material_counts"] == {
        "minecraft:bricks": 1,
        "minecraft:light_gray_concrete": 1,
    }
    assert manifest["placed_wall_block_counts"]["minecraft:stone_bricks"] == 1
    assert manifest["source_wall_block_counts"]["minecraft:bricks"] == 10


def test_sandstone_source_does_not_become_generic_repaired_ground_or_support():
    module = load_module()

    assert module.classify_ground_category("minecraft:smooth_sandstone") == 3
    assert module.GROUND_CATEGORY_BLOCKS[module.classify_ground_category("minecraft:smooth_sandstone")] == "minecraft:smooth_stone"
    assert module.subsurface_block_for("minecraft:smooth_sandstone") == "minecraft:smooth_stone"


def test_sandlike_top_cleanup_preserves_y_and_exempts_building_columns():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []
            self.tops = {
                (0, 0): 74,
                (1, 0): 75,
                (2, 0): 72,
            }

        def get_block(self, x, y, z):
            if self.tops.get((x, z)) == y:
                return "minecraft:smooth_sandstone"
            return module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    top_surface = {
        (0, 0): (70, "minecraft:smooth_sandstone"),
        (1, 0): (70, "minecraft:sandstone"),
        (2, 0): (70, "minecraft:grass_block"),
    }
    edit_mask = set()
    world = FakeWorld()

    stats = module.apply_sandlike_top_cleanup(
        world,
        top_surface,
        {(1, 0)},
        minimum_y=64,
        edit_mask=edit_mask,
    )

    assert world.calls == [(0, 74, 0, "minecraft:grass_block")]
    assert (1, 75, 0, "minecraft:grass_block") not in world.calls
    assert stats["changed"] == 1
    assert stats["sandlike_source_columns"] == 2
    assert stats["building_columns_exempted"] == 1
    assert edit_mask == {(0, 74, 0)}


def test_campus_architecture_cleanup_uses_building_free_samples_and_rebuilds_dense_ground(monkeypatch):
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def get_block(self, x, y, z):
            tops = {
                (1, 1): 95,
                (2, 1): 96,
                (8, 8): 100,
                (-1, 1): 88,
            }
            if tops.get((x, z)) == y:
                return "minecraft:oak_leaves"
            return module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    sampled_columns = set()

    def fake_build_terrain_surface(
        top_surface,
        *,
        smooth_radius,
        height_percentile,
        height_bias,
        target_columns=None,
    ):
        nonlocal sampled_columns
        assert smooth_radius == 2
        assert height_percentile == 20.0
        assert height_bias == 1.5
        sampled_columns = set(top_surface)
        return {
            column: (70, "minecraft:grass_block")
            for column in (target_columns or top_surface)
        }

    monkeypatch.setattr(module, "build_terrain_surface", fake_build_terrain_surface)
    top_surface = {
        (1, 1): (95, "minecraft:oak_leaves"),
        (2, 1): (96, "minecraft:bricks"),
        (8, 8): (100, "minecraft:oak_leaves"),
        (-1, 1): (88, "minecraft:oak_leaves"),
    }
    world = FakeWorld()
    edit_mask = set()

    stats = module.apply_campus_architecture_cleanup(
        world,
        top_surface,
        module.box(0, 0, 4, 4),
        protected_building_columns={(2, 1)},
        minimum_y=64,
        fill_depth=2,
        smooth_radius=2,
        height_percentile=20.0,
        height_bias=1.5,
        sampling_padding=2,
        edit_mask=edit_mask,
    )

    assert (8, 8) not in sampled_columns
    assert (-1, 1) in sampled_columns
    assert (2, 1) not in sampled_columns
    assert (1, 95, 1, module.AIR) in world.calls
    assert (1, 70, 1, "minecraft:grass_block") in world.calls
    assert (1, 69, 1, "minecraft:dirt") in world.calls
    assert (2, 96, 1, module.AIR) in world.calls
    assert (2, 70, 1, "minecraft:grass_block") in world.calls
    assert not any(x == 8 and z == 8 for x, _y, z, _block in world.calls)
    assert not any(x == -1 and z == 1 for x, _y, z, _block in world.calls)
    assert top_surface[(1, 1)] == (70, "minecraft:grass_block")
    assert top_surface[(2, 1)] == (70, "minecraft:grass_block")
    assert stats["columns"] == 16
    assert stats["target_columns"] == 16
    assert stats["sample_columns"] == 2
    assert edit_mask


def test_campus_architecture_cleanup_fills_missing_boundary_ground_columns(monkeypatch):
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    def fake_build_terrain_surface(
        top_surface,
        *,
        smooth_radius,
        height_percentile,
        height_bias,
        target_columns=None,
    ):
        del top_surface, smooth_radius, height_percentile, height_bias
        return {
            column: (80, "minecraft:grass_block")
            for column in (target_columns or ())
        }

    monkeypatch.setattr(module, "build_terrain_surface", fake_build_terrain_surface)
    top_surface = {
        (0, 0): (70, "minecraft:grass_block"),
        (2, 2): (70, "minecraft:grass_block"),
    }
    world = FakeWorld()

    stats = module.apply_campus_architecture_cleanup(
        world,
        top_surface,
        module.box(0, 0, 3, 3),
        protected_building_columns=set(),
        minimum_y=64,
        fill_depth=2,
        smooth_radius=2,
        height_percentile=20.0,
        height_bias=1.5,
        sampling_padding=2,
        edit_mask=set(),
    )

    expected_columns = {(x, z) for x in range(3) for z in range(3)}
    assert expected_columns <= set(top_surface)
    assert stats["target_columns"] == 9
    assert stats["missing_columns_filled"] == 7
    assert all(top_surface[column][0] == 80 for column in expected_columns)


def test_building_constrained_terrain_grades_into_floor_without_flat_ring():
    module = load_module()
    terrain = {
        (x, z): (70, "minecraft:grass_block")
        for x in range(7)
        for z in range(3)
    }

    graded = module.constrain_terrain_to_building_floors(
        terrain,
        {(3, 1): 76},
    )

    assert graded[(3, 1)] == (76, "minecraft:smooth_stone")
    assert graded[(2, 1)][0] == 75
    assert graded[(4, 1)][0] == 75
    assert graded[(1, 1)][0] == 74
    assert graded[(0, 1)][0] == 73
    assert graded[(2, 1)][0] != graded[(3, 1)][0]
    assert max(
        abs(graded[(x, 1)][0] - graded[(x + 1, 1)][0])
        for x in range(6)
    ) <= 1


def test_procedural_building_vertical_rebase_preserves_roles_and_states():
    module = load_module()
    state = {"facing": "east", "half": "bottom"}
    original = module.ProceduralBuildingResult(
        blocks=[(4, 73, 8, "minecraft:stone_brick_stairs", "window_sill")],
        block_states={(4, 73, 8): state},
        stats=module.Counter({"window_sills": 1}),
        window_mode="procedural-rhythm-fallback",
    )

    shifted = module.shift_procedural_building(original, 19)

    assert shifted.blocks == [
        (4, 92, 8, "minecraft:stone_brick_stairs", "window_sill")
    ]
    assert shifted.block_states == {(4, 92, 8): state}
    assert shifted.stats is original.stats
    assert shifted.window_mode == original.window_mode


def test_walkable_terrain_projection_removes_multi_block_cliffs():
    module = load_module()
    terrain = {
        (x, z): (
            70 if x < 3 else 90,
            "minecraft:grass_block",
        )
        for x in range(7)
        for z in range(3)
    }

    graded = module.constrain_terrain_to_building_floors(terrain, {})

    assert max(
        abs(graded[(x, z)][0] - graded[(x + 1, z)][0])
        for x in range(6)
        for z in range(3)
    ) <= 1
    assert min(height for height, _block in graded.values()) > 70
    assert max(height for height, _block in graded.values()) < 90


def test_site_overlay_adds_dark_roads_and_tennis_courts():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def get_block(self, _x, y, _z):
            if y == 73:
                return "minecraft:smooth_sandstone"
            return module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    class IdentityTransform:
        blocks_per_metre = 1.0

        def lonlat_to_block(self, longitude, latitude):
            return longitude, latitude

    payload = {
        "elements": [
            {
                "type": "way",
                "geometry": [
                    {"lon": 0.0, "lat": 2.0},
                    {"lon": 9.0, "lat": 2.0},
                ],
                "tags": {"highway": "residential"},
            },
            {
                "type": "way",
                "geometry": [
                    {"lon": 1.0, "lat": 4.0},
                    {"lon": 9.0, "lat": 4.0},
                    {"lon": 9.0, "lat": 28.0},
                    {"lon": 1.0, "lat": 28.0},
                    {"lon": 1.0, "lat": 4.0},
                ],
                "tags": {"leisure": "pitch", "sport": "tennis"},
            },
        ],
    }

    with tempfile.TemporaryDirectory() as directory:
        osm_path = Path(directory) / "site.json"
        osm_path.write_text(json.dumps(payload), encoding="utf-8")
        top_surface = {(x, z): (70, "minecraft:smooth_sandstone") for x in range(12) for z in range(30)}
        world = FakeWorld()
        edit_mask = set()

        stats = module.apply_site_surface_overlay(
            world,
            top_surface,
            osm_path,
            IdentityTransform(),
            edit_mask,
            minimum_y=64,
        )

    placed = [block for *_coords, block in world.calls]
    assert stats["features"]["road"] == 1
    assert stats["features"]["tennis"] == 1
    assert "minecraft:gray_concrete" in placed
    assert "minecraft:green_concrete" in placed
    assert "minecraft:white_concrete" in placed
    assert "minecraft:smooth_sandstone" not in placed
    assert {y for _x, y, _z, _block in world.calls} == {73}
    assert edit_mask


def test_site_feature_widths_match_authoritative_surface_buffers():
    module = load_module()

    class IdentityTransform:
        blocks_per_metre = 1.0

    transform = IdentityTransform()
    assert module.site_feature_width_blocks(
        "road", transform, {"highway": "service"}
    ) == 8.0
    assert module.site_feature_width_blocks(
        "road", transform, {"highway": "residential"}
    ) == 12.0
    assert module.site_feature_width_blocks(
        "road", transform, {"highway": "tertiary"}
    ) == 12.0
    assert module.site_feature_width_blocks(
        "path", transform, {"highway": "footway"}
    ) == 4.0


def test_named_road_surface_overlay_uses_official_hard_polygons():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def get_block(self, _x, y, _z):
            if y == 72:
                return "minecraft:smooth_stone"
            return module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    class IdentityTransform:
        def lonlat_to_block(self, longitude, latitude):
            return longitude, latitude

    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"kind": "hard", "name": "Rowan Alley"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[(1, 1), (6, 1), (6, 4), (1, 4), (1, 1)]],
                },
            },
            {
                "type": "Feature",
                "properties": {"kind": "hard", "name": "Unnamed pavement"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[(7, 1), (9, 1), (9, 4), (7, 4), (7, 1)]],
                },
            },
        ],
    }

    with tempfile.TemporaryDirectory() as directory:
        surface_path = Path(directory) / "surfaces.geojson"
        surface_path.write_text(json.dumps(payload), encoding="utf-8")
        top_surface = {(x, z): (70, "minecraft:smooth_stone") for x in range(10) for z in range(6)}
        world = FakeWorld()
        edit_mask = set()
        stats = module.apply_named_road_surface_overlay(
            world,
            top_surface,
            surface_path,
            IdentityTransform(),
            edit_mask,
            minimum_y=64,
        )

    assert stats["features"] == 1
    assert stats["cells"] == 15
    assert stats["changed"] == 15
    assert {block for *_coords, block in world.calls} == {"minecraft:gray_concrete"}
    assert {y for _x, y, _z, _block in world.calls} == {72}


def test_building_seam_fill_repairs_only_missing_in_parcel_columns():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={(5, 5): (72, 82)},
        edit_columns=1,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["TEST"],
        anchors=[],
        skipped=[],
    )
    # (6, 5) is already valid source terrain and must remain untouched.
    top_surface = {(6, 5): (71, "minecraft:grass_block")}
    parcel = module.box(3, 3, 7, 7)
    world = FakeWorld()
    edit_mask = set()

    stats = module.apply_building_seam_fill(
        world,
        top_surface,
        overlay,
        parcel,
        radius=2,
        minimum_y=69,
        edit_mask=edit_mask,
    )

    # Missing columns inside the parcel are restored to the VoxelEarth-anchored
    # building base (floor y 72 -> surrounding ground y 71).
    assert (4, 71, 5, "minecraft:grass_block") in world.calls
    assert (4, 70, 5, "minecraft:dirt") in world.calls
    assert (4, 69, 5, "minecraft:dirt") in world.calls
    assert not any(x == 6 and z == 5 for x, _y, z, _block in world.calls)
    assert not any(x == 7 or z == 7 for x, _y, z, _block in world.calls)
    assert top_surface[(4, 5)] == (71, "minecraft:grass_block")
    assert stats["filled_columns"] == 14
    assert stats["remaining_missing_columns"] == 0
    assert set((x, y, z) for x, y, z, _block in world.calls) == edit_mask


def test_chapel_apron_cleanup_clears_nonbuilding_rubble_only():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []
            self.tops = {
                (0, 0): 82,
                (1, 0): 82,
                (2, 0): 76,
            }

        def get_block(self, x, y, z):
            if self.tops.get((x, z)) == y:
                return "minecraft:stone_bricks"
            return module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={(0, 0): (72, 82), (9, 9): (72, 82)},
        edit_columns=2,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["CHAPEL - BLDG #23"],
        anchors=[
            {
                "name": "CHAPEL - BLDG #23",
                "voxelearth_ring_ground_y": 72,
                "bbox": [0, 72, 0, 0, 82, 0],
            }
        ],
        skipped=[],
    )
    source_top = {
        (0, 0): (82, "minecraft:stone_bricks"),
        (1, 0): (82, "minecraft:stone_bricks"),
        (2, 0): (72, "minecraft:stone_bricks"),
    }
    edit_mask = set()
    world = FakeWorld()

    stats = module.apply_chapel_apron_cleanup(
        world,
        overlay,
        source_top,
        radius=2,
        minimum_y=70,
        edit_mask=edit_mask,
    )

    assert not any(x == 0 and z == 0 for x, _y, z, _block in world.calls)
    assert any((x, y, z, block) == (1, 82, 0, module.AIR) for x, y, z, block in world.calls)
    assert any((x, y, z, block) == (1, 72, 0, "minecraft:grass_block") for x, y, z, block in world.calls)
    assert any((x, y, z, block) == (2, 76, 0, module.AIR) for x, y, z, block in world.calls)
    assert stats["chapel_count"] == 1
    assert stats["rubble_columns_cleared"] == 2
    assert stats["building_columns_exempted"] >= 1
    assert source_top[(1, 0)] == (72, "minecraft:grass_block")
    assert source_top[(2, 0)] == (72, "minecraft:grass_block")
    assert (1, 82, 0) in edit_mask


def test_building_apron_cleanup_protects_other_footprints_and_removes_trees():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def get_block(self, _x, y, _z):
            return "minecraft:grass_block" if y == 72 else module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={(0, 0): (72, 82)},
        edit_columns=1,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["MAIN BUILDING"],
        anchors=[
            {
                "name": "MAIN BUILDING",
                "voxelearth_ring_ground_y": 72,
                "bbox": [0, 72, 0, 0, 82, 0],
            }
        ],
        skipped=[],
    )
    source_top = {
        (0, 0): (82, "minecraft:bricks"),
        (1, 0): (78, "minecraft:bricks"),
        (2, 0): (76, "minecraft:oak_leaves"),
    }
    edit_mask = set()
    world = FakeWorld()

    stats = module.apply_overlay_apron_cleanup(
        world,
        overlay,
        source_top,
        radius=2,
        edit_mask=edit_mask,
        protected_building_columns={(1, 0)},
    )

    assert not any(x == 1 and z == 0 for x, _y, z, _block in world.calls)
    assert (2, 76, 0, module.AIR) in world.calls
    assert source_top[(2, 0)] == (72, "minecraft:grass_block")
    assert (2, 72, 0, "minecraft:grass_block") not in world.calls
    assert stats["protected_building_columns"] == 2
    assert stats["accepted_anchor_count"] == 1
    assert stats["cleared_columns"] == 1
    assert stats["surface_preserved"] == 1


def test_building_apron_cleanup_uses_real_footprint_not_only_bbox_border():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def get_block(self, _x, y, _z):
            return "minecraft:grass_block" if y == 72 else module.AIR

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    # (1, 1) is inside the L-shaped building's bbox, but it is immediately
    # outside the real footprint and therefore must be cleaned as an apron.
    building_columns = {(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)}
    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={column: (72, 82) for column in building_columns},
        edit_columns=len(building_columns),
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=1,
        building_names=["L-SHAPED MAIN BUILDING"],
        anchors=[
            {
                "name": "L-SHAPED MAIN BUILDING",
                "voxelearth_ring_ground_y": 72,
                "bbox": [0, 72, 0, 2, 82, 2],
            }
        ],
        skipped=[],
    )
    source_top = {(1, 1): (80, "minecraft:oak_leaves")}
    world = FakeWorld()
    edit_mask = set()

    stats = module.apply_overlay_apron_cleanup(
        world,
        overlay,
        source_top,
        radius=1,
        edit_mask=edit_mask,
        protected_building_columns=building_columns,
    )

    assert (1, 80, 1, module.AIR) in world.calls
    assert source_top[(1, 1)] == (72, "minecraft:grass_block")
    assert (1, 72, 1, module.BUILDING_APRON_SURFACE_BLOCK) not in world.calls
    assert stats["cleared_columns"] == 1
    assert stats["surface_preserved"] == 1


def test_official_building_seam_fill_samples_nearby_voxelearth_ground():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    building = module.box(5, 5, 7, 7)
    boundary = module.box(0, 0, 12, 12)
    top_surface = {
        (4, 5): (72, "minecraft:grass_block"),
        (8, 5): (74, "minecraft:smooth_stone"),
        # Photogrammetry roof heights inside the footprint must not lift the
        # repaired exterior terrain.
        (5, 5): (120, "minecraft:deepslate_tiles"),
    }
    world = FakeWorld()
    edit_mask = set()

    stats = module.apply_official_building_seam_fill(
        world,
        top_surface,
        building,
        boundary,
        radius=2,
        minimum_y=70,
        edit_mask=edit_mask,
        sample_radius=4,
    )

    assert stats["missing_columns"] > 0
    assert stats["filled_columns"] > 0
    assert stats["remaining_missing_columns"] == 0
    assert stats["ground_y_max"] <= 74
    assert not any(x == 4 and z == 5 for x, _y, z, _block in world.calls)
    assert any(block == "minecraft:grass_block" for *_coords, block in world.calls)
    assert {(x, y, z) for x, y, z, _block in world.calls} == edit_mask


def test_building_seam_fill_uses_nearby_voxelearth_ground_for_unaccepted_footprints():
    module = load_module()

    class FakeWorld:
        def __init__(self):
            self.calls = []

        def set_block(self, x, y, z, block_name):
            self.calls.append((x, y, z, block_name))
            return True

    overlay = module.VoxelBuildingOverlay(
        blocks=[],
        support_blocks={},
        clear_columns={},
        edit_columns=0,
        source_path=Path("overlay.npz"),
        manifest_path=Path("overlay.manifest.json"),
        building_count=0,
        building_names=[],
        anchors=[],
        skipped=[{"building_id": 1}],
    )
    top_surface = {(8, 10): (80, "minecraft:grass_block")}
    world = FakeWorld()
    edit_mask = set()

    stats = module.apply_building_seam_fill(
        world,
        top_surface,
        overlay,
        module.box(7, 7, 13, 13),
        all_building_columns={(10, 10)},
        radius=1,
        minimum_y=78,
        edit_mask=edit_mask,
    )

    assert stats["nearby_ground_candidate_columns"] == 8
    assert stats["nearby_ground_filled_columns"] == 8
    assert stats["remaining_missing_columns"] == 0
    assert all(top_surface[column][0] == 80 for column in top_surface if column != (8, 10))
    assert (9, 80, 10, "minecraft:grass_block") in world.calls
    assert (9, 79, 10, "minecraft:dirt") in world.calls
