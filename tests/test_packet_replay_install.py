"""Offline policy/installer checks; invoke with uv run --python 3.13 python."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load("replay_policy", "ops/replay/flashback_hardening.py")
installer = load("replay_installer", "ops/packet-replay-install.py")


class PacketReplayInstallTest(unittest.TestCase):
    def test_patch_fails_closed_when_upstream_source_changes(self):
        with self.assertRaises(ValueError):
            policy.patch_recorder("not the pinned source")
        with self.assertRaises(ValueError):
            policy.patch_refused("unexpected source")
        self.assertIn("default: false", policy.patch_plugin_yml("    default: op"))
        self.assertEqual("  auto-clip-on-death: false\n  enabled: false",
                         policy.patch_config_yml("  auto-clip-on-death: true\n  enabled: true"))

    def test_private_packet_filter_covers_auth_channels_not_world_updates(self):
        source = policy.patch_refused("    private static final Set<String> REFUSED = Set.of(")
        for packet in ("ClientboundSystemChatPacket", "ClientboundDisguisedChatPacket",
                       "ClientboundSetActionBarTextPacket", "ClientboundSetTitleTextPacket"):
            self.assertIn(packet, source)
        self.assertNotIn("ClientboundBlockUpdatePacket", source)
        manifest = json.loads((ROOT / "server-assets/packet-replay-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(16777216, manifest["retained_bytes_per_recording"])
        self.assertEqual(100000, manifest["retained_actions_per_recording"])

    def test_rejects_duplicate_raw_recorder_regardless_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            plugins = runtime / "plugins"
            plugins.mkdir()
            jar = plugins / "innocent-name.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("plugin.yml", "name: FlashbackServer\n")
            with self.assertRaises(ValueError):
                installer.reject_duplicates(runtime)
            jar.unlink()
            with zipfile.ZipFile(plugins / installer.NAME, "w") as archive:
                archive.writestr("plugin.yml", "name: FlashbackServer\n")
            installer.reject_duplicates(runtime)


if __name__ == "__main__":
    unittest.main()
