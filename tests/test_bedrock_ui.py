"""Behavioral contract for native map indexes, coordinate provenance and scoped routing."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

projectRoot = Path(__file__).resolve().parents[1]
moduleSpec = importlib.util.spec_from_file_location("hillBedrockUi", projectRoot / "ops/package-bedrock-ui.py")
packager = importlib.util.module_from_spec(moduleSpec)
sys.modules[moduleSpec.name] = packager
moduleSpec.loader.exec_module(packager)


class BedrockUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.metadata, _ = packager.buildFiles(packager.defaultCatalog)
        cls.screen = json.loads(cls.files["ui/hill_campus.json"])
        cls.catalog = packager.readCatalog(packager.defaultCatalog)

    def testEveryMapTargetMatchesItsRealFormIndexAndCatalogIdentity(self):
        self.assertEqual(36, len(self.catalog))
        self.assertEqual(len(self.catalog), self.metadata["backIndex"])
        rows = self.metadata["buttons"]
        self.assertEqual([building.id for building in self.catalog], [row["id"] for row in rows])
        for index, row in enumerate(rows):
            self.assertEqual(index, row["index"])
            self.assertEqual(self.catalog[index].mapNumber, row["mapNumber"])
            self.assertEqual(self.catalog[index].name, row["name"])

    def testPinLeadersResolveToTheMeasuredFootprintCenters(self):
        for building, row in zip(self.catalog, self.metadata["buttons"]):
            minX, minZ, maxX, maxZ = row["viewBoundsXz"]
            pointX, pointY = row["footprintCenter"]
            self.assertAlmostEqual(building.center[0], minX + pointX * (maxX - minX))
            self.assertAlmostEqual(building.center[1], minZ + pointY * (maxZ - minZ))
            self.assertTrue(all(0 < coordinate < 1 for coordinate in row["pinPosition"]))
            self.assertEqual(list(building.bounds), list(row["boundsXz"]))

    def testEveryBuildingHasBothANativePinAndANamedScrollableButton(self):
        indexes = []
        for view in ("central", "north"):
            for control in self.screen[f"{view}_map"]["controls"][1:]:
                button = next(iter(control.values()))
                indexes.append(button["collection_index"])
                self.assertIn(button["$button_tts_header"], [building.name for building in self.catalog])
        self.assertEqual(list(range(36)), sorted(indexes))
        for index, control in enumerate(self.screen["building_list"]["controls"]):
            self.assertEqual(index, next(iter(control.values()))["collection_index"])
        nativeButton = self.screen["form_button@common_buttons.light_text_button"]
        self.assertEqual("button.form_button_click", nativeButton["$pressed_button_name"])
        self.assertIn({"binding_type": "collection_details", "binding_collection_name": "form_buttons"},
                      nativeButton["bindings"])

    def testOnlyTheExactMapTitleUsesCustomUiAndVanillaFormsRemainIntact(self):
        hook = json.loads(self.files["ui/server_form.json"])
        self.assertEqual({"namespace", "main_screen_content"}, set(hook))
        factory = hook["main_screen_content"]["controls"][0]["server_form_factory"]
        self.assertEqual("@server_form.custom_form", factory["control_ids"]["custom_form"])
        controls = self.screen["form_router"]["controls"]
        vanilla = controls[0]["vanilla@server_form.long_form"]
        campus = controls[1]["map@hill_campus.map_screen"]
        self.assertEqual("(not (#title_text = 'Hill Campus Map'))", vanilla["bindings"][1]["source_property_name"])
        self.assertEqual("(#title_text = 'Hill Campus Map')", campus["bindings"][1]["source_property_name"])
        self.assertNotIn("third_party_server_screen", hook)  # Vanilla Escape / gamepad Back mappings survive.

    def testTextureReferencesAreAllPresentAndBackHasTheFinalIndex(self):
        for name in ("central_map", "north_map", "map_pin", "map_pin_hover", "screen_background"):
            self.assertIn(f"textures/hill175/{name}.png", self.files)
        controls = self.screen["map_screen"]["controls"]
        self.assertEqual(36, controls[-2]["back@hill_campus.form_button"]["collection_index"])
        self.assertEqual("button.menu_exit", controls[3]["close@common_buttons.light_text_button"]["$pressed_button_name"])

    def testPinsShowTheirBuildingNameOnNativeHoverAndControllerFocus(self):
        pin = self.screen["map_pin@hill_campus.form_button"]
        self.assertEqual("none", pin["$button_text_binding_type"])
        self.assertEqual("hill_campus.pin_state", pin["$button_state_panel"])
        tooltip = self.screen["pin_state"]["controls"][1]["building_name"]
        self.assertEqual("($hover_state or $pressed_state)", tooltip["visible"])
        self.assertEqual("$button_tts_header", tooltip["controls"][1]["name"]["text"])

    def testPackIsRepeatableAndContainsItsCatalogProvenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = [Path(temporary) / filename for filename in ("first.mcpack", "second.mcpack")]
            packager.package(packager.defaultCatalog, first)
            packager.package(packager.defaultCatalog, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(self.metadata, json.loads(archive.read("hill-campus-map.json")))
                self.assertIn("ui/_ui_defs.json", archive.namelist())
                self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
