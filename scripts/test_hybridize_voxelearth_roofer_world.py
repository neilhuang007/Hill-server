from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("hybridize_voxelearth_roofer_world.py")


def load_module():
    spec = importlib.util.spec_from_file_location("hill_hybrid_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_defaults_preserve_raw_voxelearth_ground():
    module = load_module()
    args = module.build_parser().parse_args([])

    assert args.building_source == "npz"
    assert args.apron_clear_radius == 0
    assert args.terrain_only_fallback is False
    assert args.fill_air_support is True
    assert args.min_source_column_coverage == 0.25
    assert args.min_support_column_coverage == 0.90


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
