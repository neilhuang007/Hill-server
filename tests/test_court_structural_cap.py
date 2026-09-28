"""The bounded floor exception must fail when any required geometry disappears."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_hill_court_terrain import validate_structural_cap


class StructuralCapTests(unittest.TestCase):
    def setUp(self):
        self.q = (74, 88, 119)
        self.cap = {"state": {"Name": "minecraft:smooth_stone"}, "role": "pavement"}
        self.source = {self.q: copy.deepcopy(self.cap)}
        self.contacts = []
        for q in ((73, 88, 119), (75, 88, 119), (74, 88, 118), (74, 88, 120)):
            value = {"state": {"Name": "minecraft:stone_bricks"}, "role": "facade"}
            self.source[q] = value
            self.contacts.append({"xyz": list(q), **copy.deepcopy(value)})
        self.actual = copy.deepcopy(self.source)
        self.before = {self.q: {"state": {"Name": "minecraft:air"}, "role": "air"}}
        self.record = {"xyz": list(self.q), **copy.deepcopy(self.cap), "contacts": self.contacts}

    def check(self):
        return validate_structural_cap(self.record, self.actual, self.source, self.before)

    def test_four_solid_contacts_accept(self):
        self.assertEqual(self.check(), [])

    def test_missing_cap_rejects(self):
        self.actual[self.q] = copy.deepcopy(self.before[self.q])
        self.assertTrue(self.check())

    def test_missing_side_contact_rejects(self):
        self.actual[(73, 88, 119)] = copy.deepcopy(self.before[self.q])
        self.assertTrue(self.check())

    def test_partial_contact_cannot_be_declared_as_support(self):
        q = (73, 88, 119)
        partial = {"state": {"Name": "minecraft:smooth_stone_slab", "Properties": {"type": "bottom"}}, "role": "pavement"}
        self.source[q] = self.actual[q] = partial
        self.contacts[0].update(partial)
        self.assertTrue(self.check())

    def test_wrong_role_rejects(self):
        self.actual[self.q]["role"] = "terrain"
        self.assertTrue(self.check())

    def test_duplicate_neighbor_cannot_replace_missing_face(self):
        self.contacts[-1] = copy.deepcopy(self.contacts[0])
        self.assertTrue(self.check())


if __name__ == "__main__":
    unittest.main()
