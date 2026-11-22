#!/usr/bin/env python3
"""Prepare/install/verify the optional checksum-pinned private Paper packet recorder.

prepare downloads/compiles under runtime/assets, without touching plugins.
install is OFFLINE and must be called after the server has been stopped.
Windows invokes this via `uv run --python 3.13 python`; Linux wrapper uses python3.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "FlashbackServer-Hill-1.2.4.jar"
CONFIG = """# Managed Hill private replay policy; no HTTP delivery or student commands.
clips:
  window-seconds: 30
  auto-clip-on-death: false
telemetry:
  enabled: false
"""


def sha512(path: Path) -> str:
    return hashlib.sha512(path.read_bytes()).hexdigest()


def reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("Replay install path may not be a symlink: " + str(path))


def reject_duplicates(runtime: Path) -> None:
    plugins = runtime / "plugins"
    reject_symlink(plugins)
    if not plugins.exists():
        return
    for path in plugins.glob("*.jar"):
        reject_symlink(path)
        with zipfile.ZipFile(path) as jar:
            if "plugin.yml" not in jar.namelist():
                continue
            text = jar.read("plugin.yml").decode("utf-8")
        if re.search(r"(?m)^name:\s*['\"]?FlashbackServer['\"]?\s*$", text) and path.name != NAME:
            raise ValueError("Remove/backup the unapproved duplicate FlashbackServer JAR before deployment: " + path.name)


def validate(jar: Path) -> dict:
    expected = json.loads((ROOT / "server-assets/packet-replay-manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads(jar.with_suffix(jar.suffix + ".provenance.json").read_text(encoding="utf-8"))
    for key, value in expected.items():
        if provenance.get(key) != value:
            raise ValueError("Staged replay provenance does not match pinned manifest: " + key)
    if provenance.get("output_sha512") != sha512(jar):
        raise ValueError("Staged replay JAR checksum mismatch")
    if provenance.get("patch_recipe_sha512") != sha512(ROOT / "ops/replay/flashback_hardening.py"):
        raise ValueError("Staged replay policy recipe is stale; prepare again")
    with zipfile.ZipFile(jar) as archive:
        if json.loads(archive.read("META-INF/HILL-REPLAY-POLICY.json")) != expected:
            raise ValueError("Replay policy marker mismatch")
        if "dev/zeffut/flashbackserver/record/HillRecordingPolicy.class" not in archive.namelist():
            raise ValueError("Replay policy class missing")
        if "    default: false" not in archive.read("plugin.yml").decode("utf-8"):
            raise ValueError("Unsafe raw replay permission default")
    return provenance


def atomic_copy(source: Path, target: Path, mode: int = 0o600) -> None:
    reject_symlink(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".hill-replay-", dir=target.parent)
    os.close(fd)
    temp = Path(name)
    try:
        shutil.copyfile(source, temp)
        temp.chmod(mode)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install", "verify", "files"))
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--java-home", type=Path)
    args = parser.parse_args()
    if args.action == "files":
        for name in ("plugins/" + NAME, "plugins/" + NAME + ".provenance.json", "plugins/FlashbackServer/config.yml"):
            print(name)
        return
    if args.runtime is None:
        parser.error("--runtime is required for prepare/install/verify")
    runtime = args.runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    reject_duplicates(runtime)
    stage = runtime / "assets/packet-replay"
    reject_symlink(runtime / "assets")
    reject_symlink(stage)
    staged = stage / NAME
    installed = runtime / "plugins" / NAME
    if args.action == "prepare":
        if args.java_home:
            os.environ["JAVA_HOME"] = str(args.java_home)
        spec = importlib.util.spec_from_file_location("packet_replay_builder", ROOT / "ops/build-packet-replay.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.build(staged, stage / "downloads")
        validate(staged)
        print("Private packet recorder prepared; runtime plugins unchanged:", staged)
    elif args.action == "install":
        # No HTTP/compilation in this branch. Validate again after server stop.
        validate(staged)
        config_dir = runtime / "plugins/FlashbackServer"
        reject_symlink(config_dir)
        config_dir.mkdir(parents=True, exist_ok=True)
        config_dir.chmod(0o700)
        atomic_copy(staged, installed)
        atomic_copy(staged.with_suffix(".jar.provenance.json"), installed.with_suffix(".jar.provenance.json"))
        config = config_dir / "config.yml"
        reject_symlink(config)
        # Policy is managed deliberately: old telemetry-enabled configuration is never retained.
        with tempfile.TemporaryDirectory(prefix="hill-replay-policy-") as temp:
            source = Path(temp) / "config.yml"
            source.write_text(CONFIG, encoding="utf-8")
            atomic_copy(source, config)
        for folder in (config_dir / "replays", config_dir / "clips"):
            reject_symlink(folder)
            folder.mkdir(exist_ok=True)
            folder.chmod(0o700)
        print("Private packet recorder installed OFFLINE:", installed)
    else:
        validate(installed)
        config = runtime / "plugins/FlashbackServer/config.yml"
        reject_symlink(config)
        if config.read_text(encoding="utf-8") != CONFIG:
            raise ValueError("Installed replay privacy config differs from managed policy")
        print("Private packet recorder pinned artifact and privacy policy verified")


if __name__ == "__main__":
    main()
