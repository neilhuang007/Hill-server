"""Pinned downloads, file ownership and rollback protect an existing runtime."""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


SPEC = importlib.util.spec_from_file_location(
    "bedrock_deployment", Path(__file__).resolve().parents[1] / "ops/install-bedrock.py"
)
bedrock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bedrock)


def jar_bytes(name):
    contents = io.BytesIO()
    with ZipFile(contents, "w") as archive:
        archive.writestr("plugin.yml", f"name: {name}\nversion: test\n")
    return contents.getvalue()


class BedrockDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = Path(self.temporary.name)
        self.manifest = bedrock.load_manifest()
        for artifact in self.manifest["artifacts"]:
            data = jar_bytes(artifact["plugin_name"])
            artifact["sha256"] = bedrock.digest(data)
            path = bedrock.cache_path(self.runtime, artifact)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def installed(self):
        bedrock.prepare(self.runtime, self.manifest, 19132)
        return bedrock.install(self.runtime, self.manifest, 19132)

    def test_manifest_uses_official_exact_builds(self):
        manifest = bedrock.load_manifest()
        for artifact in manifest["artifacts"]:
            self.assertNotIn("latest", artifact["url"])
            self.assertEqual(64, len(artifact["sha256"]))
        self.assertEqual("26.2", manifest["java_minecraft"])

    def test_generated_configuration_authenticates_bedrock_and_defers_linking_to_hill(self):
        data = bedrock.config_bytes(19135)
        geyser = json.loads(data["plugins/Geyser-Spigot/config.yml"].split(b"\n", 1)[1])
        floodgate = data["plugins/floodgate/config.yml"].decode()
        self.assertEqual("floodgate", geyser["java"]["auth-type"])
        self.assertEqual(19135, geyser["bedrock"]["port"])
        self.assertEqual("raknet", geyser["bedrock"]["transport"])
        self.assertTrue(geyser["advanced"]["bedrock"]["validate-bedrock-login"])
        self.assertFalse(geyser["motd"]["passthrough-player-counts"])
        self.assertFalse(geyser["log-player-ip-addresses"])
        linking = floodgate.split("player-link:\n", 1)[1].split("metrics:", 1)[0]
        self.assertIn("  enabled: false\n", linking)
        self.assertIn("  enable-global-linking: false\n", linking)

    def test_prepare_does_not_modify_runtime_plugin_files(self):
        bedrock.prepare(self.runtime, self.manifest, 19132)
        self.assertFalse((self.runtime / "plugins").exists())
        self.assertFalse((self.runtime / bedrock.STATE).exists())

    def test_install_and_verify_are_idempotent_and_preserve_generated_keys(self):
        self.installed()
        key = self.runtime / "plugins/floodgate/key.pem"
        key.write_bytes(b"never-replace-this-generated-secret")
        paths = [self.runtime / name for name in bedrock.MANAGED_PATHS]
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        bedrock.verify(self.runtime, self.manifest, 19132)
        self.assertIsNone(bedrock.install(self.runtime, self.manifest, 19132))
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])
        self.assertEqual(b"never-replace-this-generated-secret", key.read_bytes())

    def test_port_change_has_recoverable_backup(self):
        self.installed()
        previous = (self.runtime / "plugins/Geyser-Spigot/config.yml").read_bytes()
        backup = bedrock.install(self.runtime, self.manifest, 19133)
        self.assertEqual(previous, (backup / "plugins/Geyser-Spigot/config.yml").read_bytes())
        bedrock.verify(self.runtime, self.manifest, 19133)
        with self.assertRaisesRegex(ValueError, "environment"):
            bedrock.verify(self.runtime, self.manifest, 19132)

    def test_rejects_unknown_config_before_downloading_or_writing(self):
        path = self.runtime / "plugins/Geyser-Spigot/config.yml"
        path.parent.mkdir(parents=True)
        path.write_text("manual: true\n")
        with patch.object(bedrock, "urlopen") as download:
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                bedrock.prepare(self.runtime, self.manifest, 19132)
            download.assert_not_called()
        self.assertEqual("manual: true\n", path.read_text())
        self.assertFalse((self.runtime / bedrock.STATE).exists())

    def test_rejects_edited_managed_file(self):
        self.installed()
        path = self.runtime / "plugins/Geyser-Spigot/config.yml"
        path.write_text("manual: true\n")
        with self.assertRaisesRegex(ValueError, "edited"):
            bedrock.install(self.runtime, self.manifest, 19132)
        self.assertEqual("manual: true\n", path.read_text())

    def test_rejects_renamed_duplicate_plugin_by_descriptor(self):
        self.installed()
        path = self.runtime / "plugins/renamed-manual.jar"
        path.write_bytes(jar_bytes("floodgate"))
        with self.assertRaisesRegex(ValueError, "Duplicate/manual"):
            bedrock.prepare(self.runtime, self.manifest, 19132)
        self.assertTrue(path.exists())

    def test_bad_cached_hash_fails_before_any_plugin_write(self):
        artifact = self.manifest["artifacts"][0]
        bedrock.cache_path(self.runtime, artifact).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            bedrock.install(self.runtime, self.manifest, 19132)
        self.assertFalse((self.runtime / "plugins").exists())

    def test_download_hash_failure_never_promotes_or_leaves_partial_file(self):
        artifact = self.manifest["artifacts"][0]
        path = bedrock.cache_path(self.runtime, artifact)
        path.unlink()
        response = io.BytesIO(b"bad-download")
        response.url = artifact["url"]
        with patch.object(bedrock, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                bedrock.prepare(self.runtime, self.manifest, 19132)
        self.assertFalse(path.exists())
        self.assertEqual([], list(path.parent.glob(".download-*")))

    def test_incorrect_plugin_descriptor_fails_even_with_valid_hash(self):
        artifact = self.manifest["artifacts"][0]
        path = bedrock.cache_path(self.runtime, artifact)
        contents = jar_bytes("UnrelatedPlugin")
        path.write_bytes(contents)
        artifact["sha256"] = bedrock.digest(contents)
        with self.assertRaisesRegex(ValueError, "Unexpected plugin"):
            bedrock.install(self.runtime, self.manifest, 19132)

    def test_write_failure_restores_previous_files_and_state(self):
        self.installed()
        before = {name: (self.runtime / name).read_bytes() for name in bedrock.MANAGED_PATHS}
        original = bedrock.atomic_write
        calls = 0

        def fail_second(path, contents):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk failure")
            original(path, contents)

        with patch.object(bedrock, "atomic_write", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated"):
                bedrock.install(self.runtime, self.manifest, 19133)
        self.assertEqual(before, {name: (self.runtime / name).read_bytes() for name in bedrock.MANAGED_PATHS})
        bedrock.verify(self.runtime, self.manifest, 19132)

    def test_rejects_symlinked_managed_directory(self):
        outside = self.runtime / "outside"
        outside.mkdir()
        try:
            (self.runtime / "plugins").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable to this test user")
        with self.assertRaisesRegex(ValueError, "symlink"):
            bedrock.prepare(self.runtime, self.manifest, 19132)
        self.assertEqual([], list(outside.iterdir()))

    def test_rejects_invalid_port_before_writing(self):
        for port in (0, 443, 65536, True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                bedrock.install(self.runtime, self.manifest, port)
        self.assertFalse((self.runtime / "plugins").exists())

    def test_refuses_mutation_when_another_process_holds_world_lock(self):
        self.installed()
        world = self.runtime / "world"
        world.mkdir()
        lock = world / "session.lock"
        lock.write_bytes(b"xxx")
        code = """
import os, sys
with open(sys.argv[1], 'r+b') as stream:
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.lockf(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    print('locked', flush=True)
    sys.stdin.readline()
"""
        process = subprocess.Popen([sys.executable, "-c", code, str(lock)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual("locked\n", process.stdout.readline())
            with self.assertRaisesRegex(ValueError, "stop the service"):
                bedrock.install(self.runtime, self.manifest, 19133)
            bedrock.verify(self.runtime, self.manifest, 19132)
        finally:
            process.communicate("stop\n", timeout=10)


if __name__ == "__main__":
    unittest.main()
