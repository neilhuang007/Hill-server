#!/usr/bin/env python3
"""Reproducibly overlay narrow Hill hardening on a checksum-pinned upstream JAR.

No server is started or modified. Requires JDK 25 (javac) and Python 3.13;
Windows: uv run --python 3.13 python ops/build-packet-replay.py --output ...
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "server-assets/packet-replay-manifest.json"
PATCH = ROOT / "ops/replay/flashback_hardening.py"
spec = importlib.util.spec_from_file_location("flashback_hardening", PATCH)
hardening = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hardening)


def fetch(url: str, expected: str, cache: Path, name: str) -> Path:
    path = cache / name
    if path.exists() and hashlib.sha512(path.read_bytes()).hexdigest() == expected:
        return path
    request = urllib.request.Request(url, headers={"User-Agent": "Hill175-replay-builder/1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or hashlib.sha512(data).hexdigest() != expected:
        raise ValueError("Upstream replay download checksum/size mismatch: " + name)
    path.write_bytes(data)
    return path


def source_files(archive: Path) -> dict[str, bytes]:
    wanted = {
        "core/src/main/java/dev/zeffut/flashbackserver/capture/RefusedPackets.java",
        "core/src/main/java/dev/zeffut/flashbackserver/record/FlashbackRecorder.java",
        "core/src/main/resources/plugin.yml", "core/src/main/resources/config.yml", "LICENSE",
    }
    result = {}
    with tarfile.open(archive, "r:gz") as source:
        for entry in source:
            parts = entry.name.split("/", 1)
            if len(parts) == 2 and parts[1] in wanted and entry.isfile():
                if entry.size > 128 * 1024 or parts[1] in result:
                    raise ValueError("Invalid upstream source archive")
                result[parts[1]] = source.extractfile(entry).read()
    if result.keys() != wanted:
        raise ValueError("Pinned upstream source files missing")
    return result


def build(output: Path, cache: Path) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cache.mkdir(parents=True, exist_ok=True)
    jar = fetch(manifest["jar_url"], manifest["jar_sha512"], cache, "FlashbackServer-1.2.4.jar")
    archive = fetch(manifest["source_url"], manifest["source_sha512"], cache, "FlashbackServer-1.2.4-source.tar.gz")
    source = source_files(archive)
    java_home = os.environ.get("JAVA_HOME")
    javac = str(Path(java_home) / "bin" / ("javac.exe" if os.name == "nt" else "javac")) if java_home else shutil.which("javac")
    java = str(Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")) if java_home else shutil.which("java")
    if not javac or not java:
        raise RuntimeError("JDK 25 is required: set JAVA_HOME to a complete JDK")
    with tempfile.TemporaryDirectory(prefix="hill-replay-build-") as temp:
        work = Path(temp)
        capture = work / "src/dev/zeffut/flashbackserver/capture/RefusedPackets.java"
        record = work / "src/dev/zeffut/flashbackserver/record/FlashbackRecorder.java"
        policy = record.with_name("HillRecordingPolicy.java")
        capture.parent.mkdir(parents=True)
        record.parent.mkdir(parents=True)
        capture.write_text(hardening.patch_refused(source["core/src/main/java/dev/zeffut/flashbackserver/capture/RefusedPackets.java"].decode("utf-8")), encoding="utf-8")
        record.write_text(hardening.patch_recorder(source["core/src/main/java/dev/zeffut/flashbackserver/record/FlashbackRecorder.java"].decode("utf-8")), encoding="utf-8")
        policy.write_text(hardening.POLICY_SOURCE, encoding="utf-8")
        classes = work / "classes"
        subprocess.run([javac, "--release", "21", "-encoding", "UTF-8", "-cp", str(jar.resolve()), "-d", str(classes), str(capture), str(record), str(policy)], check=True)
        replacements = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*.class")}
        replacements["plugin.yml"] = hardening.patch_plugin_yml(source["core/src/main/resources/plugin.yml"].decode("utf-8")).encode("utf-8")
        replacements["config.yml"] = hardening.patch_config_yml(source["core/src/main/resources/config.yml"].decode("utf-8")).encode("utf-8")
        replacements["META-INF/HILL-REPLAY-POLICY.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        replacements["META-INF/LICENSE-FlashbackServer.txt"] = source["LICENSE"]
        replacements["META-INF/HILL-REPLAY-PATCH.txt"] = ("Hill narrow source overlay v1; upstream MIT FlashbackServer 1.2.4.\n"
            "Privacy packet exclusions, hard retained action/byte caps, private operator-only control.\n"
            "Modified source/recipe: ops/replay/flashback_hardening.py; no changed NMS adapters.\n").encode("utf-8")
        merged = {}
        with zipfile.ZipFile(jar) as upstream:
            for entry in upstream.infolist():
                if entry.filename in merged:
                    if entry.is_dir() and merged[entry.filename] == b"":
                        continue
                    raise ValueError("Duplicate upstream JAR file entry")
                merged[entry.filename] = upstream.read(entry)
        merged.update(replacements)
        staged = work / "hardened.jar"
        # Stable entry order/timestamps; no local compiler paths or wall clock in JAR.
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as result:
            for name, data in sorted(merged.items()):
                entry = zipfile.ZipInfo(name, (2026, 9, 25, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                result.writestr(entry, data)
        self_test(java, javac, staged, work)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged, output)
    provenance = dict(manifest)
    provenance["output_sha512"] = hashlib.sha512(output.read_bytes()).hexdigest()
    provenance["patch_recipe_sha512"] = hashlib.sha512(PATCH.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return provenance


def self_test(java: str, javac: str, jar: Path, work: Path) -> None:
    # Does not instantiate NMS/Paper: exercise exact patched classes in the JAR.
    test = work / "PolicyCheck.java"
    test.write_text('''import dev.zeffut.flashbackserver.capture.RefusedPackets;
import dev.zeffut.flashbackserver.record.*;
import java.nio.file.Path;
import java.util.UUID;
public class PolicyCheck {
  public static void main(String[] args) {
    for (String name : new String[]{"ClientboundSystemChatPacket", "ClientboundPlayerChatPacket",
      "ClientboundDisguisedChatPacket", "ClientboundSetActionBarTextPacket", "ClientboundSetTitleTextPacket",
      "ClientboundSetSubtitleTextPacket", "ClientboundBossEventPacket"})
      if (!RefusedPackets.isRefused("net.minecraft.network.protocol.game." + name)) throw new AssertionError(name);
    if (RefusedPackets.isRefused("net.minecraft.network.protocol.game.ClientboundBlockUpdatePacket")) throw new AssertionError("blocks refused");
    if (HillRecordingPolicy.version() != 1 || HillRecordingPolicy.MAX_RETAINED_BYTES != 16777216) throw new AssertionError("policy");
    UUID uuid = UUID.fromString("f3864e6b-819a-4827-a363-0a58596d5a85");
    FlashbackRecorder recorder = new FlashbackRecorder(Path.of("Student-" + uuid + ".flashback"), "Student", 1, 1);
    recorder.onPacket(new byte[16 * 1024 * 1024]);
    if (!HillRecordingPolicy.consumeGap(uuid)) throw new AssertionError("byte cap absent");
    recorder = new FlashbackRecorder(Path.of("Student-" + uuid + ".flashback"), "Student", 1, 1);
    for (int i=0; i<=100_000; i++) recorder.onPacket(new byte[0]);
    if (!HillRecordingPolicy.consumeGap(uuid)) throw new AssertionError("action cap absent");
  }
}
''', encoding="utf-8")
    subprocess.run([javac, "--release", "21", "-cp", str(jar), "-d", str(work), str(test)], check=True)
    subprocess.run([java, "-cp", str(work) + os.pathsep + str(jar), "PolicyCheck"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="staged hardened JAR; never a live server")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "runtime/packet-replay-build-cache")
    args = parser.parse_args()
    provenance = build(args.output, args.cache_dir)
    print("Hardened replay staged:", args.output)
    print("SHA512:", provenance["output_sha512"])


if __name__ == "__main__":
    main()
