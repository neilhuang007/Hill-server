"""Open the verified Hill campus v19 save directly in Minecraft Java 1.21.11.

The launcher keeps a separate persistent player save and uses Mojang's installed
client, libraries, and assets. Missing official assets are staged in its own
cache. No newer-format world is ever opened by the older client.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

import run_chapel_native_qa as minecraft


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runtime" / "campus-reconstruction"
SOURCE = BASE / "campus-port-1.21.11-v19b" / "world"
PLAYABLE = BASE / "campus-playable-v19-1.21.11"
CACHE = BASE / "campus-launch-1.21.11" / "cache"
WORLD_NAME = "hill_chapel_qa"
VERSION = "1.21.11"
DATA_VERSION = 4671


def select_java() -> Path:
    candidates: list[Path] = []
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(
        [
            program_files / "Java" / "jdk-24" / "bin" / "javaw.exe",
            program_files
            / "Java"
            / "graalvm-community-openjdk-22.0.2+9.1"
            / "bin"
            / "javaw.exe",
        ]
    )
    if os.environ.get("JAVA_HOME"):
        candidates.append(Path(os.environ["JAVA_HOME"]) / "bin" / "javaw.exe")
    for executable in ("javaw.exe", "java.exe"):
        found = shutil.which(executable)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        version = minecraft.command_version(candidate)
        match = re.search(r'\bversion\s+"?(\d+)', version)
        if match and int(match.group(1)) >= 21:
            return candidate.resolve()
    raise FileNotFoundError("Minecraft 1.21.11 needs Java 21 or newer")


def configure_version() -> dict:
    minecraft.PINNED_VERSION = VERSION
    minecraft.PINNED_DATA_VERSION = DATA_VERSION
    minecraft.VERSION_DIR = minecraft.MINECRAFT_ROOT / "versions" / VERSION
    minecraft.VERSION_JSON = minecraft.VERSION_DIR / f"{VERSION}.json"
    minecraft.VERSION_JAR = minecraft.VERSION_DIR / f"{VERSION}.jar"
    return minecraft.load_version_metadata()


def launch_command(metadata: dict, libraries: list, game_dir: Path, player: str) -> list[str]:
    java = select_java()
    natives = game_dir / "natives"
    minecraft.extract_natives(libraries, natives)
    asset_root = CACHE / "assets"
    asset_id = str((metadata.get("assetIndex") or {}).get("id") or metadata["assets"])
    classpath = os.pathsep.join([*(str(lib.path) for lib in libraries), str(minecraft.VERSION_JAR)])
    features = {
        "has_custom_resolution": True,
        "has_quick_plays_support": True,
        "is_quick_play_singleplayer": True,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
        "is_demo_user": False,
    }
    values = {
        "natives_directory": str(natives),
        "launcher_name": "HillCampus12111",
        "launcher_version": "1",
        "classpath": classpath,
        "auth_player_name": player,
        "version_name": VERSION,
        "game_directory": str(game_dir),
        "assets_root": str(asset_root),
        "assets_index_name": asset_id,
        "auth_uuid": uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + player).hex,
        "auth_access_token": "0",
        "clientid": "0",
        "auth_xuid": "0",
        "version_type": "release",
        "resolution_width": "1280",
        "resolution_height": "900",
        "quickPlayPath": str(game_dir / "quickplay.log"),
        "quickPlaySingleplayer": WORLD_NAME,
        "quickPlayMultiplayer": "",
        "quickPlayRealms": "",
    }
    context = minecraft.current_os_context()
    jvm = minecraft.expand_arguments(
        (metadata.get("arguments") or {}).get("jvm") or [], values, context, features
    )
    game = minecraft.expand_arguments(
        (metadata.get("arguments") or {}).get("game") or [], values, context, features
    )
    return [str(java), "-Xms512M", "-Xmx4G", *jvm, str(metadata["mainClass"]), *game]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-name", default="HillBuilder")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", args.player_name):
        parser.error("player name must be 1–16 Minecraft-safe characters")
    lock = PLAYABLE / "saves" / WORLD_NAME / "session.lock"
    if lock.is_file():
        try:
            with lock.open("r+b") as handle:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except PermissionError:
            print("The Hill School 1.21.11 world is already open.", flush=True)
            return 0
    metadata = configure_version()
    java = select_java()
    assert minecraft.read_level_data_version(SOURCE / "level.dat") == DATA_VERSION
    context = minecraft.current_os_context()
    features = {
        "has_custom_resolution": True,
        "has_quick_plays_support": True,
        "is_quick_play_singleplayer": True,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
        "is_demo_user": False,
    }
    libraries, index = minecraft.prepare_install(
        metadata, context, features, cache_root=CACHE, download_missing=True
    )
    if args.prepare_only:
        print(f"Ready to launch Minecraft {VERSION}: {java}, {len(libraries)} libraries, asset index {index.path.name}")
        return 0

    world, first_copy = minecraft.prepare_playable_world(SOURCE, PLAYABLE, WORLD_NAME)
    minecraft.seed_options(PLAYABLE, None)
    command = launch_command(metadata, libraries, PLAYABLE, args.player_name)
    log_path = PLAYABLE / f"minecraft-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"
    (PLAYABLE / "launch-manifest.json").write_text(
        json.dumps(
            {
                "minecraft_version": VERSION,
                "data_version": DATA_VERSION,
                "world": str(world),
                "source": str(SOURCE),
                "copied_on_this_launch": first_copy,
                "java": str(java),
                "asset_index": str(index.path),
                "log": str(log_path),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Opening Minecraft Java {VERSION} directly into The Hill School...", flush=True)
    print(f"Your Creative save is {world}", flush=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command, cwd=PLAYABLE, stdout=log, stderr=subprocess.STDOUT
        )
        joined = False
        while process.poll() is None:
            if f"{args.player_name} joined the game" in log_path.read_text(
                encoding="utf-8", errors="replace"
            ):
                minecraft.mark_playable_ready(PLAYABLE, world)
                print("The Hill School is ready. Move freely in Creative mode.", flush=True)
                joined = True
                break
            time.sleep(0.5)
        result = process.wait()
    if not joined:
        print(f"Minecraft did not join the world; see {log_path}", file=sys.stderr)
        return 1
    if result:
        print(f"Minecraft exited with code {result}; see {log_path}", file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
