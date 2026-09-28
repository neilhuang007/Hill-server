from __future__ import annotations

import hashlib
import gzip
import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("run_chapel_native_qa.py")
SPEC = importlib.util.spec_from_file_location("run_chapel_native_qa", MODULE_PATH)
assert SPEC and SPEC.loader
qa = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qa
SPEC.loader.exec_module(qa)


class NativeQaLauncherTests(unittest.TestCase):
    def test_jdk_selection_skips_path_21_for_installed_jdk_26(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_home = root / "jdk-21"
            new_home = root / ".jdks" / "openjdk-26.0.1"
            suffix = ".exe" if os.name == "nt" else ""
            for home in (old_home, new_home):
                (home / "bin").mkdir(parents=True)
                for name in ("javac", "jar", "java"):
                    tool = home / "bin" / f"{name}{suffix}"
                    tool.touch()
                    tool.chmod(0o755)

            def version(command: Path) -> str:
                return "javac 26.0.1" if new_home in command.parents else "javac 21.0.6"

            with (
                patch.dict(os.environ, {"PATH": str(old_home / "bin"), "JAVA_HOME": str(old_home)}),
                patch.object(Path, "home", return_value=root),
                patch.object(qa, "command_version", side_effect=version),
            ):
                for name in ("javac", "jar", "java"):
                    self.assertEqual(qa.find_jdk_tool(name), new_home / "bin" / f"{name}{suffix}")

    def test_valid_camera_config_replaces_default_views_and_records_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "academic-quad-cameras.json"
            path.write_text(
                json.dumps(
                    {
                        "format": "hill-native-camera-views-v1",
                        "views": [
                            {
                                "name": "quad-overview",
                                "eye": [120.5, 220, -30],
                                "target": [42, 190.25, 85],
                                "fov": 55,
                            },
                            {
                                "name": "dining.court",
                                "eye": [80, 198, 160],
                                "target": [55, 190, 95],
                                "fov": 70,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            args = qa.build_parser().parse_args(["--camera-config", str(path)])
            views, source = qa.selected_camera_views(args)
            expected_path = str(path.resolve())
            expected_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual([view.name for view in views], ["quad-overview", "dining.court"])
        self.assertEqual(views[0].eye, (120.5, 220.0, -30.0))
        self.assertEqual(views[0].fov, 55)
        self.assertEqual(source["path"], expected_path)
        self.assertEqual(source["sha256"], expected_sha256)

    def test_camera_config_rejects_dangerous_nonfinite_and_duplicate_views(self) -> None:
        invalid_views = {
            "no views": [],
            "too many views": [
                {
                    "name": f"view-{index}",
                    "eye": [index, 100, 0],
                    "target": [index, 100, 1],
                    "fov": 55,
                }
                for index in range(13)
            ],
            "dangerous name": [
                {"name": "../escape", "eye": [0, 100, 0], "target": [1, 100, 0], "fov": 55}
            ],
            "non-finite eye": [
                {"name": "bad-eye", "eye": [0, math.nan, 0], "target": [1, 100, 0], "fov": 55}
            ],
            "duplicate name": [
                {"name": "same", "eye": [0, 100, 0], "target": [1, 100, 0], "fov": 55},
                {"name": "same", "eye": [2, 100, 0], "target": [3, 100, 0], "fov": 55},
            ],
            "coincident pose": [
                {"name": "same-point", "eye": [1, 100, 2], "target": [1, 100, 2], "fov": 55}
            ],
            "unsafe height": [
                {"name": "too-high", "eye": [0, 401, 0], "target": [1, 100, 0], "fov": 55}
            ],
            "invalid fov": [
                {"name": "wide", "eye": [0, 100, 0], "target": [1, 100, 0], "fov": 111}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            for label, views in invalid_views.items():
                with self.subTest(label=label):
                    path = Path(directory) / f"{label.replace(' ', '-')}.json"
                    path.write_text(
                        json.dumps(
                            {"format": "hill-native-camera-views-v1", "views": views}
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        qa.load_camera_views(path)

    def test_camera_cli_conflicts_and_defaults_are_preserved(self) -> None:
        parser = qa.build_parser()
        default_views, default_source = qa.selected_camera_views(parser.parse_args([]))
        reference_views, reference_source = qa.selected_camera_views(
            parser.parse_args(["--reference-views"])
        )
        interactive_views, interactive_source = qa.selected_camera_views(
            parser.parse_args(["--interactive"])
        )

        self.assertEqual(default_views, qa.VIEWS)
        self.assertIsNone(default_source)
        self.assertEqual(reference_views, qa.VIEWS + qa.REFERENCE_VIEWS)
        self.assertIsNone(reference_source)
        self.assertEqual(interactive_views, qa.VIEWS)
        self.assertIsNone(interactive_source)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--camera-config", "cameras.json", "--reference-views"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--camera-config", "cameras.json", "--interactive"])

    def test_native_classifier_matches_host_architecture(self) -> None:
        windows_x64 = {"name": "windows", "arch": "x86_64", "version": "11"}
        self.assertTrue(qa.library_matches_architecture("x:y:1:natives-windows", windows_x64))
        self.assertFalse(qa.library_matches_architecture("x:y:1:natives-windows-x86", windows_x64))
        self.assertFalse(qa.library_matches_architecture("x:y:1:natives-windows-arm64", windows_x64))

    def test_version_arguments_obey_features_and_expand_placeholders(self) -> None:
        entries = [
            "--username",
            "${auth_player_name}",
            {
                "rules": [{"action": "allow", "features": {"is_quick_play_singleplayer": True}}],
                "value": ["--quickPlaySingleplayer", "${quickPlaySingleplayer}"],
            },
            {
                "rules": [{"action": "allow", "features": {"is_demo_user": True}}],
                "value": "--demo",
            },
        ]
        result = qa.expand_arguments(
            entries,
            {"auth_player_name": "HillQA", "quickPlaySingleplayer": "hill_chapel_qa"},
            {"name": "windows", "arch": "x86_64", "version": "11"},
            {"is_quick_play_singleplayer": True, "is_demo_user": False},
        )
        self.assertEqual(
            result,
            ["--username", "HillQA", "--quickPlaySingleplayer", "hill_chapel_qa"],
        )

    def test_properties_pin_all_three_requested_views(self) -> None:
        text = qa.properties_text(qa.VIEWS, "HillQA", 8000)
        self.assertIn("view.count=3", text)
        self.assertIn("view.0.eye=-35.000000,185.000000,88.000000", text)
        self.assertIn("view.0.fov=70", text)
        self.assertIn("view.1.eye=85.000000,186.000000,24.000000", text)
        self.assertIn("view.2.eye=85.000000,245.000000,110.000000", text)
        self.assertIn("player.name=HillQA", text)

    def test_reference_views_are_close_photo_scale_and_use_55_degree_fov(self) -> None:
        views = qa.VIEWS + qa.REFERENCE_VIEWS
        text = qa.properties_text(views, "HillQA", 8000)
        south, east, oblique = qa.REFERENCE_VIEWS

        self.assertIn("view.count=6", text)
        self.assertIn("view.3.name=south-reference", text)
        self.assertIn("view.3.fov=55", text)
        self.assertIn("view.4.name=east-arcade", text)
        self.assertIn("view.4.fov=55", text)
        self.assertIn("view.5.name=south-oblique", text)
        self.assertIn("view.5.fov=55", text)
        self.assertEqual(south.eye[1], 184.3)
        self.assertEqual(east.eye[1], 185.3)
        self.assertEqual(oblique.eye[1], 183.62)
        self.assertAlmostEqual(
            math.dist((south.eye[0], south.eye[2]), (south.target[0], south.target[2]))
            / 2.0,
            12.4535,
            places=3,
        )

    def test_materialize_asset_view_builds_complete_isolated_cache(self) -> None:
        payload = b"verified shared Minecraft asset"
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared" / digest
            staged = root / "qa" / digest[:2] / digest
            shared.parent.mkdir()
            shared.write_bytes(payload)
            artifact = qa.Artifact(
                "test asset",
                shared,
                len(payload),
                digest,
                "https://example.invalid/asset",
                staged,
            )
            qa.materialize_asset_view([artifact])
            self.assertEqual(staged.read_bytes(), payload)
            self.assertIsNone(
                qa.verify_artifact(qa.replace(artifact, path=staged), verify_hash=True)
            )

    def test_default_source_is_current_v11_world(self) -> None:
        self.assertEqual(qa.DEFAULT_WORLD.name, "world")
        self.assertEqual(qa.DEFAULT_WORLD.parent.name, "chapel-study-v11")

    def test_world_version_gate_rejects_a_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            world = Path(directory)
            marker = b"\x03\x00\x0bDataVersion"
            (world / "level.dat").write_bytes(
                gzip.compress(b"\x0a\x00\x00" + marker + (qa.PINNED_DATA_VERSION + 1).to_bytes(4, "big"))
            )
            with self.assertRaisesRegex(ValueError, "downgrade"):
                qa.validate_world_version(world)

    def test_seed_options_disables_startup_prompts_clouds_and_enables_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_dir = Path(directory)
            (game_dir / "options.txt").write_text(
                "narrator:3\nrenderClouds:\"true\"\nresourcePacks:[]\n",
                encoding="utf-8",
            )
            qa.seed_options(game_dir, "file/hill-brownstone")
            options = (game_dir / "options.txt").read_text(encoding="utf-8")
            self.assertIn("narrator:0", options)
            self.assertIn('renderClouds:"false"', options)
            self.assertIn("soundCategory_music:0.0", options)
            self.assertIn('resourcePacks:["vanilla","file/hill-brownstone"]', options)
            self.assertIn("tutorialStep:none", options)
            self.assertIn("onboardAccessibility:false", options)

    def test_resource_pack_accepts_exact_26_1_2_format_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "hill-brownstone"
            source.mkdir()
            (source / "pack.mcmeta").write_text(
                '{"pack":{"description":"test","min_format":[84,0],"max_format":[84,0]}}',
                encoding="utf-8",
            )
            game_dir = root / "game"
            pack_id = qa.install_resource_pack(source, game_dir)
            self.assertEqual(pack_id, "file/hill-brownstone")
            self.assertTrue((game_dir / "resourcepacks" / "hill-brownstone" / "pack.mcmeta").is_file())

    def test_preupgrade_backup_contains_world_and_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world = root / "world"
            world.mkdir()
            marker = b"\x03\x00\x0bDataVersion"
            (world / "level.dat").write_bytes(
                gzip.compress(b"\x0a\x00\x00" + marker + (3700).to_bytes(4, "big"))
            )
            (world / "payload.txt").write_text("world payload", encoding="utf-8")
            game_dir = root / "game"
            poisoned = game_dir / "pre-upgrade-backups" / "hill_chapel_qa-data-3700.zip"
            poisoned.parent.mkdir(parents=True)
            poisoned.write_bytes(b"x")
            first = qa.ensure_preupgrade_backup(world, game_dir, "hill_chapel_qa")
            second = qa.ensure_preupgrade_backup(world, game_dir, "hill_chapel_qa")
            self.assertEqual(first, second)
            self.assertGreater(first.stat().st_size, 0)
            self.assertTrue(qa.validate_preupgrade_backup(first, world, "hill_chapel_qa", 3700))

    def test_missing_source_does_not_poison_playable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            playable = root / "playable"
            with self.assertRaises((FileNotFoundError, ValueError)):
                qa.prepare_playable_world(source, playable, "hill_chapel_qa")
            self.assertFalse(playable.exists())

            source.mkdir()
            (source / "region").mkdir()
            marker = b"\x03\x00\x0bDataVersion"
            (source / "level.dat").write_bytes(
                gzip.compress(b"\x0a\x00\x00" + marker + (3700).to_bytes(4, "big"))
            )
            world, created = qa.prepare_playable_world(source, playable, "hill_chapel_qa")
            self.assertTrue(created)
            self.assertTrue((world / "level.dat").is_file())


if __name__ == "__main__":
    unittest.main()
