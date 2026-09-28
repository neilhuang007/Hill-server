"""A bell must retain its renderer data through real Anvil serialization."""

import nbtlib
from nbtlib import tag
import pytest

from build_hill_chapel_sample import Canvas, write_world
from campus_export_parity import compare_world, read_archive
import hybridize_voxelearth_roofer_world as anvil


def bell_world(tmp_path):
    template = tmp_path / "level.dat"
    nbtlib.File({"Data": tag.Compound({
        "WorldGenSettings": tag.Compound({
            "dimensions": tag.Compound({
                "minecraft:overworld": tag.Compound({"generator": tag.Compound({})})
            })
        })
    })}, gzipped=True).save(template)
    canvas = Canvas(-1, -1, 18, 2, 2)
    for x, y, z in [(-1, -10, -1), (16, 90, 0)]:
        canvas.set(x, y, z, "bell", "fixture",
                   {"attachment": "ceiling", "facing": "north", "powered": "false"})
        canvas.set(x, y + 1, z, "stone", "fixture")
    archive = tmp_path / "sample-blocks.npz"
    canvas.export(archive)
    world = tmp_path / "world"
    write_world(canvas, world, "Bell export test", (0, 92, 0), template)
    return read_archive(archive), world


def test_bells_have_exact_entities_across_chunk_and_height_boundaries(tmp_path):
    archive, world = bell_world(tmp_path)
    entities = [entity for _, _, chunk in anvil.iter_world_chunks(world)
                for entity in chunk["block_entities"]]
    assert {(str(e["id"]), int(e["x"]), int(e["y"]), int(e["z"])) for e in entities} == {
        ("minecraft:bell", -1, -10, -1), ("minecraft:bell", 16, 90, 0)
    }
    parity, errors, _, _ = compare_world(archive, world)
    assert not errors
    assert parity["expected_bell_block_entities"] == parity["actual_bell_block_entities"] == 2


@pytest.mark.parametrize("mutation, counter", [
    ("remove", "missing_bell_block_entities"),
    ("duplicate", "duplicate_bell_block_entities"),
    ("move", "extra_bell_block_entities"),
])
def test_parity_rejects_bell_renderer_data_loss_or_wrong_position(tmp_path, mutation, counter):
    archive, world = bell_world(tmp_path)
    region = anvil.RegionEditor(world / "region/r.0.0.mca")
    chunk = region.chunk(1, 0)
    entity = chunk.root["block_entities"][0]
    if mutation == "remove":
        chunk.root["block_entities"] = tag.List[tag.Compound]([])
    elif mutation == "duplicate":
        chunk.root["block_entities"].append(entity.copy())
    else:
        entity["x"] = tag.Int(17)
    region.mark_modified(1, 0)
    region.save()
    parity, errors, _, _ = compare_world(archive, world)
    assert parity[counter] == 1 and errors
