from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import tag


SCRIPT_PATH = Path(__file__).with_name("audit_hill_chapel_sample.py")
SPEC = importlib.util.spec_from_file_location("audit_hill_chapel_sample", SCRIPT_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def _door(facing: str, half: str, hinge: str) -> dict[str, object]:
    return {
        "Name": "minecraft:dark_oak_door",
        "Properties": {
            "facing": facing,
            "half": half,
            "hinge": hinge,
            "open": "false",
            "powered": "false",
        },
    }


class _SyntheticStudy:
    def __init__(
        self,
        root: Path,
        *,
        corrupt_door_pair: bool = False,
        corrupt_pane_connection: bool = False,
        corrupt_wall_mullion_connection: bool = False,
        narrow_light: bool = False,
        buried_pane: bool = False,
    ) -> None:
        self.study_dir = root / "study"
        self.study_dir.mkdir(parents=True)
        self.profile = root / "official-profile.json"
        self.terrain = root / "official-terrain.npz"
        self.resource_pack = self.study_dir / "resourcepacks" / "test-pack"
        self.resource_pack.mkdir(parents=True)
        self.pack_metadata = self.resource_pack / "pack.mcmeta"
        self.pack_metadata.write_text(
            '{"pack":{"pack_format":22,"description":"audit fixture"}}\n',
            encoding="utf-8",
        )
        self.profile.write_text('{"source":"test fixture"}\n', encoding="utf-8")
        np.savez_compressed(self.terrain, elevation=np.asarray([[1.0]], dtype=np.float32))

        self.palette: list[dict[str, object]] = [
            {"Name": "minecraft:air"},
            {"Name": "minecraft:stone"},
            {"Name": "minecraft:smooth_stone"},
        ]
        for facing in ("south", "east"):
            for hinge in ("left", "right"):
                for half in ("lower", "upper"):
                    self.palette.append(_door(facing, half, hinge))
        left_pane = {
            "Name": "minecraft:gray_stained_glass_pane",
            "Properties": {
                "east": "false" if corrupt_pane_connection else "true",
                "north": "false" if corrupt_wall_mullion_connection else "true",
                "south": "false",
                "waterlogged": "false",
                "west": "false",
            },
        }
        right_pane = {
            "Name": "minecraft:gray_stained_glass_pane",
            "Properties": {
                "east": "false",
                "north": "false",
                "south": "false",
                "waterlogged": "false",
                "west": "true",
            },
        }
        wall_mullion = {"Name": "minecraft:sandstone_wall"}
        self.palette.extend((left_pane, right_pane, wall_mullion))
        narrow_corner_pane = {
            "Name": "minecraft:gray_stained_glass_pane",
            "Properties": {
                "east": "false",
                "north": "false",
                "south": "true",
                "waterlogged": "false",
                "west": "true",
            },
        }
        narrow_end_pane = {
            "Name": "minecraft:gray_stained_glass_pane",
            "Properties": {
                "east": "false",
                "north": "true",
                "south": "false",
                "waterlogged": "false",
                "west": "false",
            },
        }
        buried_plus_pane = {
            "Name": "minecraft:gray_stained_glass_pane",
            "Properties": {
                "east": "true",
                "north": "true",
                "south": "true",
                "waterlogged": "false",
                "west": "true",
            },
        }
        stair_jamb = {
            "Name": "minecraft:smooth_sandstone_stairs",
            "Properties": {
                "facing": "west",
                "half": "top",
                "shape": "straight",
                "waterlogged": "false",
            },
        }
        if narrow_light:
            self.palette.extend((narrow_corner_pane, narrow_end_pane, stair_jamb))
        if buried_pane:
            self.palette.append(buried_plus_pane)
        self.state_lookup = {
            json.dumps(state, sort_keys=True): index for index, state in enumerate(self.palette)
        }
        self.blocks: dict[tuple[int, int, int], tuple[int, int]] = {}
        # role ids: air=0, terrain=1, door=2, floor=3, window=4, trim=5
        path_supports = {
            (x, 1, z) for x in (0, 1) for z in range(-4, 5)
        } | {(x, 1, z) for x in range(2, 11) for z in (0, 1)}
        for coord in path_supports | {(10, 0, 0), (10, 1, 0)}:
            self.blocks[coord] = (1, 1)
        self.blocks[(10, 2, 0)] = (2, 3)
        self.blocks[(12, 2, 5)] = (
            self.state_lookup[json.dumps(left_pane, sort_keys=True)],
            4,
        )
        self.blocks[(13, 2, 5)] = (
            self.state_lookup[json.dumps(right_pane, sort_keys=True)],
            4,
        )
        self.blocks[(12, 2, 4)] = (
            self.state_lookup[json.dumps(wall_mullion, sort_keys=True)],
            5,
        )
        if narrow_light:
            self.blocks[(12, 2, 8)] = (
                self.state_lookup[json.dumps(narrow_corner_pane, sort_keys=True)],
                4,
            )
            self.blocks[(12, 2, 9)] = (
                self.state_lookup[json.dumps(narrow_end_pane, sort_keys=True)],
                4,
            )
            self.blocks[(11, 2, 8)] = (
                self.state_lookup[json.dumps(wall_mullion, sort_keys=True)],
                5,
            )
            self.blocks[(13, 2, 8)] = (
                self.state_lookup[json.dumps(stair_jamb, sort_keys=True)],
                5,
            )
        if buried_pane:
            self.blocks[(12, 2, 12)] = (
                self.state_lookup[json.dumps(buried_plus_pane, sort_keys=True)],
                4,
            )
            for neighbor in ((11, 2, 12), (13, 2, 12), (12, 2, 11), (12, 2, 13)):
                self.blocks[neighbor] = (1, 1)

        door_specs = [
            ((0, 2, 0), "south", "left"),
            ((1, 2, 0), "south", "right"),
            ((5, 2, 0), "east", "left"),
            ((5, 2, 1), "east", "right"),
        ]
        for (x, y, z), facing, hinge in door_specs:
            lower_id = self.state_lookup[json.dumps(_door(facing, "lower", hinge), sort_keys=True)]
            upper_id = self.state_lookup[json.dumps(_door(facing, "upper", hinge), sort_keys=True)]
            self.blocks[(x, y, z)] = (lower_id, 2)
            self.blocks[(x, y + 1, z)] = (upper_id, 2)
        if corrupt_door_pair:
            lower_id, role_id = self.blocks[(0, 2, 0)]
            self.blocks[(0, 3, 0)] = (lower_id, role_id)

        self._write_npz()
        self._write_world()
        self._write_manifest()

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _write_npz(self) -> None:
        ordered = sorted(self.blocks.items(), key=lambda item: (item[0][1], item[0][2], item[0][0]))
        coords = np.asarray([coord for coord, _value in ordered], dtype=np.int32)
        state_ids = np.asarray([value[0] for _coord, value in ordered], dtype=np.uint16)
        role_ids = np.asarray([value[1] for _coord, value in ordered], dtype=np.uint8)
        np.savez_compressed(
            self.study_dir / "sample-blocks.npz",
            coords=coords,
            state_ids=state_ids,
            role_ids=role_ids,
            role_names=np.asarray(
                ["air", "terrain", "door", "floor", "window", "trim"]
            ),
            palette_json=np.asarray(json.dumps(self.palette, separators=(",", ":"))),
        )

    def _write_world(self) -> None:
        world = self.study_dir / "world"
        region_dir = world / "region"
        region_dir.mkdir(parents=True, exist_ok=True)
        by_chunk: dict[tuple[int, int], list[tuple[tuple[int, int, int], int]]] = defaultdict(list)
        for coord, (state_id, _role_id) in self.blocks.items():
            by_chunk[(coord[0] // 16, coord[2] // 16)].append((coord, state_id))
        regions: dict[tuple[int, int], object] = {}
        for (chunk_x, chunk_z), blocks in by_chunk.items():
            section_data = np.zeros((16, 16, 16), dtype=np.uint16)
            for (x, y, z), state_id in blocks:
                section_data[y, z - chunk_z * 16, x - chunk_x * 16] = state_id
            used, inverse = np.unique(section_data, return_inverse=True)
            entries = [
                audit.anvil.block_entry(
                    str(self.palette[int(index)]["Name"]),
                    self.palette[int(index)].get("Properties"),
                )
                for index in used
            ]
            states = tag.Compound({"palette": tag.List[tag.Compound](entries)})
            if len(entries) > 1:
                states["data"] = tag.LongArray(
                    audit.anvil.pack_indices(inverse.ravel().tolist(), len(entries))
                )
            section = tag.Compound(
                {
                    "Y": tag.Byte(0),
                    "block_states": states,
                    "biomes": tag.Compound(
                        {"palette": tag.List[tag.String]([tag.String("minecraft:plains")])}
                    ),
                }
            )
            chunk_root = nbtlib.File(
                {
                    "DataVersion": tag.Int(3700),
                    "xPos": tag.Int(chunk_x),
                    "zPos": tag.Int(chunk_z),
                    "yPos": tag.Int(-4),
                    "Status": tag.String("minecraft:full"),
                    "sections": tag.List[tag.Compound]([section]),
                    "block_entities": tag.List[tag.Compound]([]),
                }
            )
            region_key = (chunk_x // 32, chunk_z // 32)
            editor = regions.setdefault(
                region_key,
                audit.anvil.RegionEditor(
                    region_dir / f"r.{region_key[0]}.{region_key[1]}.mca"
                ),
            )
            index = audit.anvil.region_chunk_index(chunk_x, chunk_z)
            editor.raw_records[index] = audit.anvil.serialize_chunk_record(chunk_root)
            editor.modified.add(index)
        for editor in regions.values():
            editor.save()

    def _write_manifest(self) -> None:
        material_counts: Counter[str] = Counter()
        role_counts: dict[str, Counter[str]] = defaultdict(Counter)
        roles = ["air", "terrain", "door", "floor", "window", "trim"]
        for state_id, role_id in self.blocks.values():
            name = str(self.palette[state_id]["Name"])
            material_counts[name] += 1
            role_counts[roles[role_id]][name] += 1
        manifest = {
            "format": "hill-chapel-study-v1",
            "profile": {"path": str(self.profile), "sha256": self._sha(self.profile)},
            "terrain": {"path": str(self.terrain), "sha256": self._sha(self.terrain)},
            "bounds": [-1, 0, -2, 12, 5, 3],
            "world": {"chunks": 2, "regions": 2},
            "materials": dict(material_counts),
            "material_roles": {role: dict(counts) for role, counts in role_counts.items()},
            "material_audit": [],
            "visual_gate": {
                "native_minecraft_review": "pending",
                "matched_current_photo": "pending",
                "larger_area_authorized_by_quality_gate": False,
            },
            "resource_pack": {
                "path": str(self.resource_pack),
                "files": {"pack.mcmeta": self._sha(self.pack_metadata)},
            },
        }
        (self.study_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def replace_anvil_state(self, coord: tuple[int, int, int], state: dict[str, object]) -> None:
        """Rebuild the fixture world with one serialized state changed."""
        state_id = self.state_lookup.get(json.dumps(state, sort_keys=True))
        if state_id is None:
            self.palette.append(state)
            state_id = len(self.palette) - 1
            self.state_lookup[json.dumps(state, sort_keys=True)] = state_id
        role_id = self.blocks[coord][1]
        self.blocks[coord] = (state_id, role_id)
        for region in (self.study_dir / "world" / "region").glob("*.mca"):
            region.unlink()
        self._write_world()

    def remove_expected_block(self, coord: tuple[int, int, int]) -> None:
        del self.blocks[coord]
        self._write_npz()
        for region in (self.study_dir / "world" / "region").glob("*.mca"):
            region.unlink()
        self._write_world()
        self._write_manifest()

    def add_visual_evidence(
        self,
        *,
        decision: str = "pass",
        authorize_larger_area: bool = True,
        include_fov: bool = False,
        capture_input_probe_passed: bool | None = None,
    ) -> Path:
        evidence_dir = self.study_dir / "native-review"
        evidence_dir.mkdir()
        copied_world = evidence_dir / "saves" / "test_world"
        copied_world.mkdir(parents=True)
        (copied_world / "level.dat").write_bytes(b"synthetic copied level")
        screenshot_path = evidence_dir / "south.png"
        screenshot_path.write_bytes(b"synthetic screenshot fixture")
        launch_path = evidence_dir / "launch-manifest.json"
        launch_view = {
            "name": "south",
            "eye": [0.0, 2.0, 0.0],
            "target": [0.0, 2.0, 1.0],
        }
        if include_fov:
            launch_view["fov"] = 70.0
        launch_path.write_text(
            json.dumps(
                {
                    "format": "hill-chapel-native-qa-launch-v1",
                    "mode": "capture",
                    "minecraft_version": "test-version",
                    "source_world": str(self.study_dir / "world"),
                    "copied_world": str(copied_world),
                    "resource_pack": str(self.resource_pack),
                    "resource_pack_id": "file/test-pack",
                    "views": [launch_view],
                }
            ),
            encoding="utf-8",
        )
        native_path = evidence_dir / "native-capture-report.json"
        native_view = {
            "name": "south",
            "requested_eye": [0.0, 2.0, 0.0],
            "requested_target": [0.0, 2.0, 1.0],
            "requested_yaw": 0.0,
            "requested_pitch": 0.0,
            "commanded_feet_y": 0.38,
            "actual_eye": [0.0, 2.0, 0.0],
            "actual_yaw": 0.0,
            "actual_pitch": 0.0,
            "screenshot": screenshot_path.name,
            "bytes": screenshot_path.stat().st_size,
            "sha256": self._sha(screenshot_path),
        }
        if include_fov:
            native_view["requested_fov"] = 70.0
            native_view["actual_fov"] = 70.0
        native_payload = {
            "format": "hill-chapel-native-qa-v1",
            "status": "complete",
            "mode": "capture",
            "renderer": "native Minecraft client",
            "minecraft_version": "test-version",
            "conversion_completed": True,
            "failure": None,
            "expected_resource_pack": "file/test-pack",
            "active_resource_packs": ["vanilla", "file/test-pack"],
            "views": [native_view],
        }
        if capture_input_probe_passed is not None:
            native_payload["capture_input_probe_passed"] = capture_input_probe_passed
        native_path.write_text(json.dumps(native_payload), encoding="utf-8")
        native_sha = self._sha(native_path)

        findings = (
            []
            if decision == "pass"
            else [
                {
                    "summary": "synthetic blocking visual finding",
                    "blocking": True,
                    "resolved": False,
                }
            ]
        )
        review_path = evidence_dir / "visual-review.json"
        review_path.write_text(
            json.dumps(
                {
                    "format": "hill-visual-review-v1",
                    "sample_blocks_sha256": self._sha(
                        self.study_dir / "sample-blocks.npz"
                    ),
                    "native_capture_report_sha256": native_sha,
                    "reviewers": [{"name": "Synthetic Reviewer"}],
                    "photo_reference_urls": ["https://example.test/current-photo"],
                    "findings": findings,
                    "decision": decision,
                }
            ),
            encoding="utf-8",
        )

        manifest_path = self.study_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["visual_gate"].update(
            {
                "native_capture_report": {
                    "path": str(native_path),
                    "sha256": native_sha,
                },
                "native_launch_manifest": {
                    "path": str(launch_path),
                    "sha256": self._sha(launch_path),
                },
                "visual_review": {
                    "path": str(review_path),
                    "sha256": self._sha(review_path),
                },
                "larger_area_authorized_by_quality_gate": authorize_larger_area,
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return screenshot_path

    def add_academic_provenance(self, previous: "_SyntheticStudy") -> Path:
        source_cityjson = self.study_dir / "academic-source.city.json"
        parent_id = "academic-parent"
        part_ids = ["academic-part-0", "academic-part-1"]
        source_cityjson.write_text(
            json.dumps(
                {
                    "type": "CityJSON",
                    "version": "2.0",
                    "CityObjects": {
                        parent_id: {"type": "Building", "children": part_ids},
                        part_ids[0]: {"type": "BuildingPart", "parents": [parent_id]},
                        part_ids[1]: {"type": "BuildingPart", "parents": [parent_id]},
                    },
                    "vertices": [],
                }
            ),
            encoding="utf-8",
        )
        profile_source = self.study_dir.parent / "academic-profile-source.json"
        profile_source.write_text('{"revision":"source"}\n', encoding="utf-8")
        profile_snapshot = self.study_dir / "academic-profile.json"
        profile_snapshot.write_text('{"revision":"snapshot"}\n', encoding="utf-8")
        terrain_manifest = self.study_dir / "measured-terrain.manifest.json"
        terrain_manifest.write_text(
            json.dumps(
                {
                    "format": "hill-measured-terrain-v1",
                    "output": {
                        "path": str(self.terrain),
                        "sha256": self._sha(self.terrain),
                    },
                }
            ),
            encoding="utf-8",
        )

        previous_manifest_path = previous.study_dir / "manifest.json"
        previous_manifest = json.loads(
            previous_manifest_path.read_text(encoding="utf-8")
        )
        previous_review = previous_manifest["visual_gate"]["visual_review"]
        previous_review_path = Path(previous_review["path"])

        manifest_path = self.study_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["academic_complex"] = {
            "source_cityjson": {
                "path": str(source_cityjson),
                "sha256": self._sha(source_cityjson),
            },
            "measured_terrain_manifest": {
                "path": str(terrain_manifest),
                "sha256": self._sha(terrain_manifest),
            },
            "profile": {
                "path": str(profile_snapshot),
                "sha256": self._sha(profile_snapshot),
                "source_path": str(profile_source),
            },
            "parent_id": parent_id,
            "part_ids": part_ids,
            "footprint_area_m2": 120.0,
            "footprint_bounds_m": [10.0, 20.0, 30.0, 40.0],
            "source_height_navd88_m": [65.0, 89.0],
            "roof_coverage": {
                "footprint_columns": 480,
                "covered_columns": 480,
                "missing_covered_columns": 0,
            },
            "shell": {
                "format": "hill-measured-shell-v1",
                "parent_id": parent_id,
                "active_roof_columns": 480,
                "clipped_writes": 0,
            },
            "features": {"north_window_groups": 4},
        }
        manifest["accepted_previous_sample"] = {
            "study": str(previous.study_dir),
            "manifest_sha256": self._sha(previous_manifest_path),
            "visual_review_sha256": self._sha(previous_review_path),
            "sample_blocks_sha256": self._sha(
                previous.study_dir / "sample-blocks.npz"
            ),
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return source_cityjson


class ChapelSampleAuditTests(unittest.TestCase):
    def test_valid_sample_passes_including_negative_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 0)
        self.assertEqual(report["doors_and_entrances"]["error_count"], 0)
        self.assertEqual(report["foundation_support"]["unsupported_count"], 0)
        self.assertEqual(report["visual_gate"]["native_minecraft_review"], "pending")
        self.assertEqual(report["provenance"]["status"], "not_declared")

    def test_changed_academic_cityjson_hash_fails_expanded_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = _SyntheticStudy(root / "previous")
            previous.add_visual_evidence()
            current = _SyntheticStudy(root / "current")
            source_cityjson = current.add_academic_provenance(previous)
            valid_report = audit.audit_study(current.study_dir)
            source_cityjson.write_text('{"tampered":true}\n', encoding="utf-8")
            report = audit.audit_study(current.study_dir)

        self.assertEqual(valid_report["provenance"]["status"], "verified")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["provenance"]["status"], "invalid")
        self.assertIn(
            "academic source CityJSON evidence SHA-256 does not match manifest",
            report["evidence_failures"],
        )

    def test_unauthorized_previous_gate_cannot_be_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = _SyntheticStudy(root / "previous")
            previous.add_visual_evidence(
                decision="changes_requested", authorize_larger_area=False
            )
            current = _SyntheticStudy(root / "current")
            current.add_academic_provenance(previous)
            report = audit.audit_study(current.study_dir)

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["provenance"]["status"], "invalid")
        self.assertIn(
            "accepted previous sample does not have a verified passing visual gate",
            report["evidence_failures"],
        )
        self.assertEqual(report["visual_gate"]["native_minecraft_review"], "pending")

    def test_changed_native_camera_config_fails_exact_byte_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.add_visual_evidence()
            camera_path = fixture.study_dir / "native-review" / "cameras.json"
            launch_path = fixture.study_dir / "native-review" / "launch-manifest.json"
            launch = json.loads(launch_path.read_text(encoding="utf-8"))
            camera_path.write_text(
                json.dumps(
                    {
                        "format": "hill-native-camera-views-v1",
                        "views": launch["views"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            launch["camera_config_source"] = {
                "path": str(camera_path),
                "sha256": fixture._sha(camera_path),
            }
            launch_path.write_text(json.dumps(launch), encoding="utf-8")
            manifest_path = fixture.study_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["visual_gate"]["native_launch_manifest"]["sha256"] = fixture._sha(
                launch_path
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            valid_report = audit.audit_study(fixture.study_dir)
            camera_path.write_text('{"changed":true}\n', encoding="utf-8")

            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(valid_report["status"], "pass")
        self.assertEqual(
            valid_report["visual_gate"]["native_capture_report"][
                "camera_config_source"
            ]["status"],
            "verified",
        )
        self.assertEqual(report["status"], "fail")
        camera = report["visual_gate"]["native_capture_report"][
            "camera_config_source"
        ]
        self.assertEqual(camera["status"], "invalid")
        self.assertIn(
            "native camera config evidence SHA-256 does not match manifest",
            report["evidence_failures"],
        )

    def test_serialized_world_property_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            changed_door = _door("south", "lower", "left")
            changed_door["Properties"]["open"] = "true"
            fixture.replace_anvil_state((0, 2, 0), changed_door)
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 1)
        self.assertEqual(report["exact_parity"]["missing_count"], 0)
        self.assertEqual(report["exact_parity"]["extra_count"], 0)

    def test_matching_npz_and_world_with_corrupt_door_pair_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary), corrupt_door_pair=True)
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 0)
        self.assertEqual(report["status"], "fail")
        self.assertGreater(report["doors_and_entrances"]["error_count"], 0)
        self.assertNotEqual(
            report["doors_and_entrances"]["lower_count"],
            report["doors_and_entrances"]["upper_count"],
        )

    def test_floor_gap_fails_even_when_npz_and_world_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.remove_expected_block((10, 1, 0))
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 0)
        self.assertEqual(report["foundation_support"]["unsupported_count"], 1)
        self.assertEqual(report["foundation_support"]["examples"][0]["first_gap_y"], 1)
        self.assertEqual(report["status"], "fail")

    def test_matching_disconnected_pane_state_fails_structural_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary), corrupt_pane_connection=True)
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 0)
        self.assertEqual(
            report["architectural_clearance"]["pane_connection_error_count"], 1
        )
        self.assertEqual(report["status"], "fail")

    def test_matching_missing_wall_mullion_arm_fails_structural_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(
                Path(temporary), corrupt_wall_mullion_connection=True
            )
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 0)
        clearance = report["architectural_clearance"]
        self.assertEqual(clearance["pane_connection_error_count"], 1)
        example = clearance["pane_connection_error_examples"][0]
        self.assertEqual(example["neighbor_block"], "minecraft:sandstone_wall")
        self.assertTrue(example["expected_connected"])
        self.assertEqual(report["status"], "fail")

    def test_narrow_l_shaped_upper_light_uses_arm_geometry_for_normal_axes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary), narrow_light=True)
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "pass")
        clearance = report["architectural_clearance"]
        self.assertEqual(clearance["pane_connection_error_count"], 0)
        self.assertEqual(clearance["blocked_both_normal_sides_count"], 0)

    def test_plus_pane_blocked_on_every_actual_sheet_normal_is_buried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary), buried_pane=True)
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["exact_parity"]["state_mismatch_count"], 0)
        clearance = report["architectural_clearance"]
        self.assertEqual(clearance["pane_connection_error_count"], 0)
        self.assertEqual(clearance["blocked_both_normal_sides_count"], 1)
        buried = clearance["blocked_both_normal_sides"][0]
        self.assertEqual(buried["coord"], [12, 2, 12])
        self.assertEqual(set(buried["normal_axes"]), {"x", "z"})
        self.assertEqual(report["status"], "fail")

    def test_resource_pack_hash_mismatch_is_an_evidence_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.pack_metadata.write_text("tampered\n", encoding="utf-8")
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["structural_violation_count"], 0)
        self.assertEqual(report["evidence_failure_count"], 1)
        self.assertEqual(report["visual_gate"]["resource_pack"]["status"], "failed")
        self.assertEqual(
            report["visual_gate"]["resource_pack"]["files"]["pack.mcmeta"]["status"],
            "sha256_mismatch",
        )
        self.assertEqual(report["status"], "fail")

    def test_complete_bound_visual_evidence_can_authorize_larger_area(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.add_visual_evidence(
                include_fov=True, capture_input_probe_passed=True
            )
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["visual_gate"]["native_minecraft_review"], "complete")
        self.assertEqual(report["visual_gate"]["matched_current_photo"], "pass")
        self.assertTrue(report["visual_gate"]["larger_area_authorized"])
        native = report["visual_gate"]["native_capture_report"]
        self.assertEqual(native["fov_recorded_count"], 1)
        self.assertEqual(native["fov_valid_count"], 1)
        self.assertEqual(native["screenshots"][0]["fov_status"], "valid")
        self.assertIs(native["capture_input_probe_passed"], True)
        self.assertEqual(native["capture_input_probe_status"], "passed")

    def test_hash_valid_failed_capture_input_probe_rejects_true_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.add_visual_evidence(capture_input_probe_passed=False)
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "fail")
        self.assertIn(
            "native capture report capture_input_probe_passed is not literal true",
            report["evidence_failures"],
        )
        native = report["visual_gate"]["native_capture_report"]
        self.assertIs(native["capture_input_probe_passed"], False)
        self.assertEqual(native["capture_input_probe_status"], "invalid")
        self.assertFalse(report["visual_gate"]["larger_area_authorized"])

    def test_hash_valid_launch_fov_tamper_rejects_true_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.add_visual_evidence(include_fov=True)
            launch_path = fixture.study_dir / "native-review" / "launch-manifest.json"
            launch = json.loads(launch_path.read_text(encoding="utf-8"))
            launch["views"][0]["fov"] = 111.0
            launch_path.write_text(json.dumps(launch), encoding="utf-8")
            manifest_path = fixture.study_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["visual_gate"]["native_launch_manifest"]["sha256"] = fixture._sha(
                launch_path
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "fail")
        self.assertIn(
            "native view 0 has invalid or inconsistent FOV evidence",
            report["evidence_failures"],
        )
        native = report["visual_gate"]["native_capture_report"]
        self.assertEqual(native["screenshots"][0]["fov_status"], "invalid")
        self.assertEqual(native["fov_recorded_count"], 1)
        self.assertEqual(native["fov_valid_count"], 0)
        self.assertEqual(native["screenshots"][0]["launch_fov"], 111.0)
        self.assertFalse(report["visual_gate"]["larger_area_authorized"])

    def test_tampered_native_screenshot_rejects_true_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            screenshot = fixture.add_visual_evidence()
            screenshot.write_bytes(b"tampered after native capture report")
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "fail")
        self.assertGreater(report["evidence_failure_count"], 0)
        self.assertEqual(report["visual_gate"]["native_minecraft_review"], "invalid")
        self.assertEqual(report["visual_gate"]["matched_current_photo"], "invalid")
        self.assertFalse(report["visual_gate"]["larger_area_authorized"])

    def test_changes_requested_is_valid_evidence_but_keeps_gate_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = _SyntheticStudy(Path(temporary))
            fixture.add_visual_evidence(
                decision="changes_requested", authorize_larger_area=False
            )
            report = audit.audit_study(fixture.study_dir)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["visual_gate"]["native_minecraft_review"], "complete")
        self.assertEqual(
            report["visual_gate"]["matched_current_photo"], "changes_requested"
        )
        self.assertFalse(report["visual_gate"]["larger_area_authorized"])
        native = report["visual_gate"]["native_capture_report"]
        self.assertEqual(native["screenshots"][0]["fov_status"], "not_recorded")


if __name__ == "__main__":
    unittest.main()
