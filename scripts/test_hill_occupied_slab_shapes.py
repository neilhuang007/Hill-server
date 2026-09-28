"""A double slab has full-height contact, unlike a single half slab."""
import json

from audit_hill_quadrivium_contacts import shapes


def test_double_slab_occupies_full_cube():
    state={"Name":"minecraft:stone_brick_slab","Properties":{"type":"double"}}
    assert shapes(json.dumps(state)) == ((0,0,0,16,16,16),)


def test_top_and_bottom_slabs_have_different_vertical_contact():
    def slab(kind):
        return shapes(json.dumps({"Name":"minecraft:smooth_stone_slab","Properties":{"type":kind}}))
    assert slab("bottom") == ((0,0,0,16,8,16),)
    assert slab("top") == ((0,8,0,16,16,16),)
