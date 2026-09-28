from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).with_name("render_voxel_sample.py")


def load_module():
    spec = importlib.util.spec_from_file_location("render_voxel_sample_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_minimal_jar(path: Path) -> None:
    cube = {
        "textures": {"all": "minecraft:block/stone"},
        "elements": [
            {
                "from": [0, 0, 0],
                "to": [16, 16, 16],
                "faces": {
                    direction: {"texture": "#all", "cullface": direction}
                    for direction in ("down", "up", "north", "south", "west", "east")
                },
            }
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "assets/minecraft/blockstates/stone.json",
            json.dumps({"variants": {"": {"model": "minecraft:block/stone"}}}),
        )
        archive.writestr("assets/minecraft/models/block/base_cube.json", json.dumps(cube))
        archive.writestr(
            "assets/minecraft/models/block/stone.json",
            json.dumps(
                {
                    "parent": "minecraft:block/base_cube",
                    "textures": {"all": "minecraft:block/stone"},
                }
            ),
        )


def test_load_sample_preserves_exact_palette_state(tmp_path):
    module = load_module()
    path = tmp_path / "sample.npz"
    np.savez(
        path,
        coords=np.asarray([[4, 90, -2]], dtype=np.int32),
        state_ids=np.asarray([0], dtype=np.uint16),
        palette_json=np.asarray(
            json.dumps(
                [
                    {
                        "Name": "minecraft:stone_brick_stairs",
                        "Properties": {"facing": "north", "half": "bottom"},
                    }
                ]
            )
        ),
    )

    coords, state_ids, palette = module.load_sample(path)

    np.testing.assert_array_equal(coords, [[4, 90, -2]])
    np.testing.assert_array_equal(state_ids, [0])
    assert palette[0].name == "minecraft:stone_brick_stairs"
    assert palette[0].properties == {"facing": "north", "half": "bottom"}


def test_model_rotations_follow_minecraft_world_axes():
    module = load_module()

    assert module.rotate_y((1.0, 0.0, 0.0), 90) == pytest.approx((0.0, 0.0, 1.0))
    assert module.rotate_x((0.0, 1.0, 0.0), 90) == pytest.approx((0.0, 0.0, 1.0))
    assert module.rotate_direction(
        "east", module.ModelApplication("model", y=90)
    ) == "south"


def test_object_texture_entry_resolves_the_vanilla_glass_sprite():
    module = load_module()
    model = {"textures": {
        "particle": "#pane",
        "pane": {"sprite": "minecraft:block/glass_pane_top", "force_translucent": True},
    }}
    assert module.resolve_texture(model, "#particle") == "minecraft:block/glass_pane_top"
    with pytest.raises(ValueError, match="invalid texture entry"):
        module.resolve_texture({"textures": {"pane": {"force_translucent": True}}}, "#pane")


def test_variants_and_multipart_select_from_exact_properties():
    module = load_module()
    definition = {
        "variants": {
            "facing=north": {"model": "block/north"},
            "facing=south": {"model": "block/south"},
        },
        "multipart": [
            {"when": {"connected": "true"}, "apply": {"model": "block/side"}},
            {
                "when": {"OR": [{"lit": "true"}, {"powered": "true"}]},
                "apply": {"model": "block/light"},
            },
        ],
    }

    applications = module.applications_for_state(
        definition,
        {"facing": "north", "connected": "true", "lit": "false", "powered": "true"},
        (1, 2, 3),
    )

    assert [application.model for application in applications] == [
        "block/north",
        "block/side",
        "block/light",
    ]


def test_omitted_default_property_uses_first_compatible_variant():
    module = load_module()
    definition = {
        "variants": {
            "snowy=false": {"model": "block/grass"},
            "snowy=true": {"model": "block/snowy_grass"},
        }
    }

    applications = module.applications_for_state(definition, {}, (0, 0, 0))

    assert [application.model for application in applications] == ["block/grass"]


def test_model_inheritance_and_neighbor_culling(tmp_path):
    module = load_module()
    jar = tmp_path / "client.jar"
    write_minimal_jar(jar)

    with module.VanillaResources(jar) as resources:
        model = resources.model("minecraft:block/stone")
        mesh = module.build_mesh(
            resources,
            np.asarray([[0, 0, 0], [1, 0, 0]], dtype=np.int32),
            np.asarray([0, 0], dtype=np.uint16),
            [module.BlockState("minecraft:stone", {})],
            (0.0, 0.0, 0.0),
        )

    assert model["elements"][0]["to"] == [16, 16, 16]
    assert model["textures"]["all"] == "minecraft:block/stone"
    assert mesh.blocks == 2
    assert mesh.quads == 10
    assert set(mesh.batches) == {("minecraft:block/stone", (1.0, 1.0, 1.0))}


def test_duplicate_coordinates_are_rejected(tmp_path):
    module = load_module()
    path = tmp_path / "sample.npz"
    np.savez(
        path,
        coords=np.asarray([[0, 0, 0], [0, 0, 0]], dtype=np.int32),
        state_ids=np.asarray([0, 0], dtype=np.uint16),
        palette_json=np.asarray(json.dumps([{"Name": "minecraft:stone"}])),
    )

    with pytest.raises(ValueError, match="duplicate"):
        module.load_sample(path)


def test_fluid_state_gets_dynamic_surface_geometry():
    module = load_module()
    elements = module.elements_for_state(
        {}, module.BlockState("minecraft:water", {"level": "0"})
    )

    assert elements[0]["to"] == [16, 15.0, 16]
    assert set(elements[0]["faces"]) == set(module.DIRECTIONS)


@pytest.mark.parametrize("direction", ["north", "south", "east", "west"])
def test_vertical_wall_edges_preserve_texture_v_axis(direction):
    """Brick courses must stay horizontal on all four facade orientations."""
    module = load_module()
    vertices = module.face_corners(direction, [0, 0, 0], [16, 16, 16])
    uvs = module.face_uvs([0, 0, 16, 16], direction=direction)
    for i in range(4):
        j = (i + 1) % 4
        if vertices[i][0] == vertices[j][0] and vertices[i][2] == vertices[j][2]:
            assert uvs[i][0] == uvs[j][0]
            assert uvs[i][1] != uvs[j][1]
