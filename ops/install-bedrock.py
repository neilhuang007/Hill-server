#!/usr/bin/env python3
"""Stage and install pinned Geyser/Floodgate without controlling the Paper service.

Call prepare before stopping Paper, install after it stops, then verify after
startup. The outer installer must back up the paths printed by `files` for its
own startup rollback. Generated Floodgate keys and player data are never copied,
replaced, or printed. Only this helper's unmodified managed files are upgraded.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


MANIFEST = Path(__file__).resolve().parents[1] / "server-assets/bedrock-manifest.json"
FLOODGATE_CONFIG = Path(__file__).resolve().parents[1] / "server-config/floodgate-config.yml"
STATE = "assets/bedrock-managed.json"
MANAGED_PATHS = (
    "plugins/Geyser-Spigot.jar",
    "plugins/floodgate-spigot.jar",
    "plugins/Geyser-Spigot/config.yml",
    "plugins/floodgate/config.yml",
    STATE,
)
CONFIG_HEADER = "# Managed by Hill 175 ops/install-bedrock.py; configure HILL175_BEDROCK_PORT.\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def safe_path(runtime, relative):
    """Refuse symlinked managed files/directories before any reads or writes."""
    path = runtime / relative
    if path.is_absolute() and not path.is_relative_to(runtime):
        raise ValueError("Managed path is outside the runtime")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Refusing symlinked runtime path: {component}")
        if component == runtime:
            break
    return path


def load_manifest(path=MANIFEST):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    expected = {"geyser": ("Geyser-Spigot", "Geyser-Spigot.jar"),
                "floodgate": ("floodgate", "floodgate-spigot.jar")}
    if manifest.get("schema") != 1 or len(artifacts) != 2:
        raise ValueError("Invalid Bedrock artifact manifest")
    for artifact in artifacts:
        project = artifact.get("project")
        pair = expected.pop(project, None)
        if pair != (artifact.get("plugin_name"), artifact.get("filename")):
            raise ValueError("Unexpected Bedrock artifact name")
        version, build = artifact.get("version", ""), artifact.get("build")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or type(build) is not int or build < 1:
            raise ValueError("Bedrock artifacts must pin an exact version and build")
        url = f"https://download.geysermc.org/v2/projects/{project}/versions/{version}/builds/{build}/downloads/spigot"
        if artifact.get("url") != url or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", "")):
            raise ValueError("Bedrock artifacts require official immutable URLs and SHA-256")
    return manifest



def config_bytes(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Bedrock UDP port must be between 1024 and 65535")
    # Geyser's YAML loader supports JSON. Floodgate needs its native YAML template.
    # Pin schema versions to avoid an automatic migration changing managed files.
    # RakNet opens UDP only: NetherNet would introduce a separate web listener.
    geyser = {
        "bedrock": {"address": "0.0.0.0", "port": port, "clone-remote-port": False, "transport": "raknet"},
        "java": {"auth-type": "floodgate"},
        "motd": {"primary-motd": "Hill School 175", "secondary-motd": "School verification required",
                 "passthrough-motd": False, "passthrough-player-counts": False,
                 "integrated-ping-passthrough": False, "max-players": 100},
        "gameplay": {"server-name": "Hill School 175"},
        "log-player-ip-addresses": False,
        "saved-user-logins": [],
        "advanced": {"bedrock": {"validate-bedrock-login": True, "use-haproxy-protocol": False,
                                  "use-waterdogpe-forwarding": False},
                     "java": {"use-direct-connection": True, "use-haproxy-protocol": False}},
        "debug-mode": False,
        "config-version": 8,
    }
    return {"plugins/Geyser-Spigot/config.yml": (CONFIG_HEADER + json.dumps(geyser, indent=2) + "\n").encode(),
            "plugins/floodgate/config.yml": FLOODGATE_CONFIG.read_text(encoding="utf-8").encode()}


def plugin_name(path):
    try:
        with ZipFile(path) as archive:
            for descriptor in ("plugin.yml", "paper-plugin.yml"):
                if descriptor in archive.namelist():
                    info = archive.getinfo(descriptor)
                    if info.file_size > 65536:
                        raise ValueError(f"Oversized plugin descriptor: {path.name}")
                    match = re.search(r"(?m)^name:\s*['\"]?([^'\"\r\n]+)", archive.read(descriptor).decode("utf-8"))
                    if match:
                        return match.group(1).strip()
    except (BadZipFile, UnicodeError):
        return None
    return None


def preflight(runtime, manifest):
    paths = {relative: safe_path(runtime, relative) for relative in MANAGED_PATHS}
    for path in paths.values():
        if path.exists() and not path.is_file():
            raise ValueError(f"Managed target is not a regular file: {path}")
    marker = paths[STATE]
    state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None
    if state is not None:
        if state.get("schema") != 1 or set(state.get("files", {})) != set(MANAGED_PATHS) - {STATE}:
            raise ValueError("Invalid Bedrock management state; restore its backup before deploying")
    for relative, path in paths.items():
        if relative == STATE or not path.exists():
            continue
        if state is None or file_digest(path) != state["files"].get(relative):
            raise ValueError(f"Refusing to overwrite unmanaged or edited Bedrock file: {path}")
    plugins = safe_path(runtime, "plugins")
    expected = {item["plugin_name"].lower(): item["filename"] for item in manifest["artifacts"]}
    if plugins.exists():
        for path in plugins.iterdir():
            if path.suffix.lower() != ".jar":
                continue
            if path.is_symlink():
                raise ValueError(f"Resolve symlinked plugin before installing Bedrock: {path}")
            name = (plugin_name(path) or "").lower()
            if name in expected and path.name != expected[name]:
                raise ValueError(f"Duplicate/manual Bedrock plugin {path.name}; reconcile it before deploying")
    return state


def cache_path(runtime, artifact):
    return safe_path(runtime, f"assets/bedrock/{artifact['project']}-{artifact['version']}-{artifact['build']}.jar")


def validate_artifact(path, artifact):
    if not path.is_file() or file_digest(path) != artifact["sha256"]:
        raise ValueError(f"Bedrock SHA-256 mismatch or missing artifact: {path}")
    if plugin_name(path) != artifact["plugin_name"]:
        raise ValueError(f"Unexpected plugin inside Bedrock artifact: {path.name}")


def prepare(runtime, manifest, port):
    config_bytes(port)
    preflight(runtime, manifest)
    for artifact in manifest["artifacts"]:
        path = cache_path(runtime, artifact)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as target:
                    request = Request(artifact["url"], headers={"User-Agent": "Hill175-deployment/1.0"})
                    with urlopen(request, timeout=90) as response:
                        if not response.url.startswith("https://"):
                            raise ValueError("Bedrock download redirected away from HTTPS")
                        size = 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > 150 * 1024 * 1024:
                                raise ValueError("Bedrock artifact exceeds download size limit")
                            target.write(chunk)
                validate_artifact(Path(temporary), artifact)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        validate_artifact(path, artifact)


@contextmanager
def stopped_world(runtime):
    """NIO's POSIX byte-range lock detects Paper holding its primary world open."""
    properties = safe_path(runtime, "server.properties")
    level_name = "world"
    if properties.exists():
        for line in properties.read_text(encoding="utf-8").splitlines():
            if line.startswith("level-name="):
                level_name = line.split("=", 1)[1].strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", level_name):
        raise ValueError("Cannot safely locate the primary world lock; use a simple level-name")
    lock = safe_path(runtime, f"{level_name}/session.lock")
    if not lock.exists():
        yield
        return
    with lock.open("r+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.lockf(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("Paper is using the world; stop the service before installing Bedrock") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.lockf(stream.fileno(), fcntl.LOCK_UN)


def atomic_write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".hill175-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644 if path.suffix == ".jar" else 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def desired_files(runtime, manifest, port):
    files = config_bytes(port)
    for artifact in manifest["artifacts"]:
        path = cache_path(runtime, artifact)
        validate_artifact(path, artifact)
        files[f"plugins/{artifact['filename']}"] = path.read_bytes()
    state = {"schema": 1, "port": port, "files": {name: digest(data) for name, data in files.items()}}
    files[STATE] = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
    return files


def install(runtime, manifest, port):
    preflight(runtime, manifest)
    desired = desired_files(runtime, manifest, port)
    changed = {name: data for name, data in desired.items()
               if not (runtime / name).exists() or file_digest(runtime / name) != digest(data)}
    if not changed:
        return None
    with stopped_world(runtime):
        backup_parent = safe_path(runtime, "assets/bedrock-backups")
        backup_parent.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix="before-", dir=backup_parent))
        prior = {}
        for name in changed:
            path = runtime / name
            prior[name] = path.exists()
            if path.exists():
                destination = backup / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        (backup / "files.json").write_text(json.dumps(prior, indent=2) + "\n", encoding="utf-8")
        applied = []
        try:
            for name, data in changed.items():
                atomic_write(runtime / name, data)
                applied.append(name)
        except BaseException:
            for name in reversed(applied):
                path = runtime / name
                if prior[name]:
                    atomic_write(path, (backup / name).read_bytes())
                else:
                    path.unlink(missing_ok=True)
            raise
        return backup


def verify(runtime, manifest, port):
    preflight(runtime, manifest)
    for name, contents in config_bytes(port).items():
        path = runtime / name
        if not path.is_file() or file_digest(path) != digest(contents):
            raise ValueError(f"Bedrock configuration does not match the environment: {name}")
    for artifact in manifest["artifacts"]:
        validate_artifact(runtime / "plugins" / artifact["filename"], artifact)
    state = json.loads((runtime / STATE).read_text(encoding="utf-8"))
    if state.get("port") != port:
        raise ValueError("Bedrock management state has a different port")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install", "verify", "files"))
    parser.add_argument("--runtime", type=Path, default=Path("/opt/hill175"))
    parser.add_argument("--port", type=int, default=19132)
    args = parser.parse_args()
    try:
        if args.action == "files":
            print("\n".join(MANAGED_PATHS))
            return 0
        runtime = args.runtime.absolute()
        if runtime.is_symlink() or not runtime.is_dir():
            raise ValueError("Runtime must be an existing, non-symlinked directory")
        manifest = load_manifest()
        if args.action == "prepare":
            prepare(runtime, manifest, args.port)
            print("Pinned Bedrock artifacts and managed-file preflight passed.")
        elif args.action == "install":
            backup = install(runtime, manifest, args.port)
            print(f"Bedrock files installed; previous files: {backup}" if backup else "Bedrock files already match.")
        else:
            verify(runtime, manifest, args.port)
            print(f"Bedrock artifacts and configuration verified (UDP {args.port}).")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"Bedrock deployment failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
