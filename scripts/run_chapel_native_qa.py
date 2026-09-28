"""Launch an isolated vanilla Minecraft 26.1.2 Chapel screenshot run.

The launcher uses only the installed version metadata, client JAR, libraries,
and assets. It builds a non-transforming Java test agent, copies the requested
world into a new game directory, launches Quick Play singleplayer, waits for
the configured native screenshots, and verifies the agent report. It never reads the
user's launcher accounts or normal saves.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import asdict, dataclass, replace
import gzip
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
MINECRAFT_ROOT = Path(os.environ.get("APPDATA", "")) / ".minecraft"
PINNED_VERSION = "26.1.2"
VERSION_DIR = MINECRAFT_ROOT / "versions" / PINNED_VERSION
VERSION_JSON = VERSION_DIR / f"{PINNED_VERSION}.json"
VERSION_JAR = VERSION_DIR / f"{PINNED_VERSION}.jar"
LIBRARY_ROOT = MINECRAFT_ROOT / "libraries"
ASSET_ROOT = MINECRAFT_ROOT / "assets"
AGENT_ROOT = REPO_ROOT / "scripts" / "chapel-native-qa"
DEFAULT_WORLD = (
    REPO_ROOT / "runtime" / "campus-reconstruction" / "chapel-study-v11" / "world"
)
DEFAULT_QA_ROOT = REPO_ROOT / "runtime" / "campus-reconstruction" / "chapel-native-qa"
DEFAULT_CACHE_ROOT = DEFAULT_QA_ROOT / "cache"
DEFAULT_PLAYABLE_DIR = DEFAULT_QA_ROOT / "playable-v11"
PINNED_DATA_VERSION = 4790
RUN_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
CAMERA_VIEW_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
CAMERA_Y_MIN = -64.0
CAMERA_Y_MAX = 400.0


@dataclass(frozen=True)
class CameraView:
    name: str
    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    fov: int = 70


def _camera_vector(value: Any, *, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must be a three-number JSON array")
    parsed: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise ValueError(f"{label} must contain only numbers")
        number = float(component)
        if not math.isfinite(number):
            raise ValueError(f"{label} must contain only finite numbers")
        parsed.append(number)
    return parsed[0], parsed[1], parsed[2]


def load_camera_views(path: Path) -> tuple[tuple[CameraView, ...], dict[str, str]]:
    """Load bounded capture poses and bind them to their exact source bytes."""

    source_path = path.resolve()
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"camera config could not be read: {source_path}") from exc
    try:
        payload = json.loads(source_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"camera config is not valid UTF-8 JSON: {source_path}"
        ) from exc
    if (
        not isinstance(payload, Mapping)
        or payload.get("format") != "hill-native-camera-views-v1"
    ):
        raise ValueError("camera config format must be hill-native-camera-views-v1")
    raw_views = payload.get("views")
    if not isinstance(raw_views, list) or not 1 <= len(raw_views) <= 12:
        raise ValueError("camera config must contain 1..12 views")

    views: list[CameraView] = []
    seen_names: set[str] = set()
    for index, raw_view in enumerate(raw_views):
        if not isinstance(raw_view, Mapping) or set(raw_view) != {
            "name",
            "eye",
            "target",
            "fov",
        }:
            raise ValueError(
                f"camera view {index} must contain exactly name, eye, target, and fov"
            )
        name = raw_view.get("name")
        if (
            not isinstance(name, str)
            or CAMERA_VIEW_NAME.fullmatch(name) is None
            or name.endswith(".")
            or ".." in name
        ):
            raise ValueError(f"camera view {index} name is not filename-safe")
        if name.split(".", 1)[0].upper() in WINDOWS_RESERVED_FILENAMES:
            raise ValueError(f"camera view {index} name is reserved on Windows")
        normalized_name = name.casefold()
        if normalized_name in seen_names:
            raise ValueError(f"camera view {index} name is duplicated")
        seen_names.add(normalized_name)

        eye = _camera_vector(raw_view.get("eye"), label=f"camera view {index} eye")
        target = _camera_vector(
            raw_view.get("target"), label=f"camera view {index} target"
        )
        if not (
            CAMERA_Y_MIN <= eye[1] <= CAMERA_Y_MAX
            and CAMERA_Y_MIN <= target[1] <= CAMERA_Y_MAX
        ):
            raise ValueError(
                f"camera view {index} eye/target Y must be within "
                f"{CAMERA_Y_MIN:g}..{CAMERA_Y_MAX:g}"
            )
        if math.dist(eye, target) <= 1e-9:
            raise ValueError(f"camera view {index} eye and target must differ")
        fov = raw_view.get("fov")
        if isinstance(fov, bool) or not isinstance(fov, int) or not 30 <= fov <= 110:
            raise ValueError(
                f"camera view {index} fov must be an integer within 30..110"
            )
        views.append(CameraView(name=name, eye=eye, target=target, fov=fov))

    return tuple(views), {
        "path": str(source_path),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
    }


def selected_camera_views(
    args: argparse.Namespace,
) -> tuple[tuple[CameraView, ...], dict[str, str] | None]:
    camera_config = getattr(args, "camera_config", None)
    reference_views = bool(getattr(args, "reference_views", False))
    interactive = bool(getattr(args, "interactive", False))
    start_view_config = getattr(args, "start_view_config", None)
    if start_view_config is not None:
        if not interactive or camera_config is not None or reference_views:
            raise ValueError(
                "--start-view-config requires --interactive and no capture-view options"
            )
        return load_camera_views(start_view_config)
    if camera_config is not None and reference_views:
        raise ValueError("--camera-config cannot be combined with --reference-views")
    if camera_config is not None and interactive:
        raise ValueError("--camera-config is only used for screenshot QA runs")
    if camera_config is not None:
        return load_camera_views(camera_config)
    return (VIEWS + REFERENCE_VIEWS if reference_views else VIEWS), None


VIEWS = (
    CameraView("south", (-35.0, 185.0, 88.0), (-5.0, 191.0, 53.0)),
    CameraView("east-quad", (85.0, 186.0, 24.0), (8.0, 195.0, 22.0)),
    CameraView("aerial", (85.0, 245.0, 110.0), (0.0, 185.0, 20.0)),
)


def chapel_world_xz(u: float, v: float) -> tuple[float, float]:
    """Map documented Chapel-local metres into the two-block world X/Z grid."""
    angle = math.radians(-8.5)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        (cosine * u + sine * v) * 2.0,
        (-sine * u + cosine * v) * 2.0,
    )


def reference_camera(
    name: str,
    eye_uv: tuple[float, float],
    eye_y: float,
    target_uv: tuple[float, float],
    target_y: float,
) -> CameraView:
    eye_x, eye_z = chapel_world_xz(*eye_uv)
    target_x, target_z = chapel_world_xz(*target_uv)
    return CameraView(name, (eye_x, eye_y, eye_z), (target_x, target_y, target_z), 55)


# The reference eyes are 3.3 blocks (1.65 model metres) above the measured
# surface. Their oblique local positions follow the front and east photographs.
REFERENCE_VIEWS = (
    reference_camera("south-reference", (-7.0, 38.5), 184.3, (0.0, 28.2), 190.0),
    reference_camera("east-arcade", (16.0, 15.0), 185.3, (5.0, 7.0), 190.0),
    reference_camera("south-oblique", (-12.0, 35.0), 183.62, (-1.0, 28.2), 190.0),
)


@dataclass(frozen=True)
class Artifact:
    label: str
    path: Path
    expected_size: int | None = None
    expected_sha1: str | None = None
    url: str | None = None
    stage_path: Path | None = None


class MissingInstallArtifacts(RuntimeError):
    def __init__(self, artifacts: Iterable[Artifact]):
        self.artifacts = list(artifacts)
        lines = ["Minecraft 26.1.2 installation is incomplete:"]
        lines.extend(
            f"  {artifact.label}: {artifact.path}" for artifact in self.artifacts
        )
        super().__init__("\n".join(lines))


def current_os_context() -> dict[str, str]:
    machine = platform.machine().lower()
    architecture = "x86" if machine in {"x86", "i386", "i686"} else "x86_64"
    if machine in {"arm64", "aarch64"}:
        architecture = "arm64"
    return {
        "name": "windows",
        "arch": architecture,
        "version": platform.version(),
    }


def rule_matches(
    rule: Mapping[str, Any],
    os_context: Mapping[str, str],
    features: Mapping[str, bool],
) -> bool:
    os_rule = rule.get("os") or {}
    if os_rule.get("name") and os_rule["name"] != os_context["name"]:
        return False
    if os_rule.get("arch") and os_rule["arch"] != os_context["arch"]:
        return False
    if os_rule.get("version") and not re.search(
        str(os_rule["version"]), os_context["version"]
    ):
        return False
    return all(
        features.get(name, False) == bool(value)
        for name, value in (rule.get("features") or {}).items()
    )


def allowed_by_rules(
    rules: Iterable[Mapping[str, Any]] | None,
    os_context: Mapping[str, str],
    features: Mapping[str, bool],
) -> bool:
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if rule_matches(rule, os_context, features):
            allowed = rule.get("action") == "allow"
    return allowed


def library_matches_architecture(name: str, os_context: Mapping[str, str]) -> bool:
    """Disambiguate native classifiers whose Mojang rules only name the OS."""
    if os_context["name"] != "windows" or ":natives-windows" not in name:
        return True
    classifier = name.rsplit(":", 1)[-1]
    if classifier == "natives-windows-arm64":
        return os_context["arch"] == "arm64"
    if classifier == "natives-windows-x86":
        return os_context["arch"] == "x86"
    if classifier == "natives-windows":
        return os_context["arch"] == "x86_64"
    return True


def expand_arguments(
    entries: Iterable[Any],
    replacements: Mapping[str, str],
    os_context: Mapping[str, str],
    features: Mapping[str, bool],
) -> list[str]:
    expanded: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            values = [entry]
        elif isinstance(entry, Mapping):
            if not allowed_by_rules(entry.get("rules"), os_context, features):
                continue
            raw_value = entry.get("value")
            values = raw_value if isinstance(raw_value, list) else [raw_value]
        else:
            raise ValueError(f"unsupported version argument entry: {entry!r}")
        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"version argument is not a string: {value!r}")
            rendered = value
            for key, replacement in replacements.items():
                rendered = rendered.replace("${" + key + "}", replacement)
            unresolved = re.findall(r"\$\{[^}]+\}", rendered)
            if unresolved:
                raise ValueError(
                    f"unresolved version argument placeholders: {unresolved}"
                )
            expanded.append(rendered)
    return expanded


def load_version_metadata() -> dict[str, Any]:
    missing = [
        Artifact("version metadata", VERSION_JSON),
        Artifact("version client", VERSION_JAR),
    ]
    absent = [artifact for artifact in missing if not artifact.path.is_file()]
    if absent:
        raise MissingInstallArtifacts(absent)
    metadata = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    if metadata.get("id") != PINNED_VERSION:
        raise ValueError(
            f"expected version {PINNED_VERSION}, got {metadata.get('id')!r}"
        )
    if int((metadata.get("javaVersion") or {}).get("majorVersion", 0)) > 26:
        raise ValueError(
            "installed JDK 26 cannot run the requested Minecraft Java version"
        )
    return metadata


def selected_libraries(
    metadata: Mapping[str, Any],
    os_context: Mapping[str, str],
    features: Mapping[str, bool],
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for library in metadata.get("libraries") or []:
        name = str(library.get("name"))
        if not allowed_by_rules(
            library.get("rules"), os_context, features
        ) or not library_matches_architecture(name, os_context):
            continue
        download = (library.get("downloads") or {}).get("artifact")
        if not download:
            raise ValueError(
                f"library has no artifact download metadata: {library.get('name')}"
            )
        installed_path = LIBRARY_ROOT / download["path"]
        staged_path = cache_root / "libraries" / download["path"]
        artifacts.append(
            Artifact(
                name,
                installed_path if installed_path.is_file() else staged_path,
                int(download["size"]) if download.get("size") is not None else None,
                str(download["sha1"]) if download.get("sha1") else None,
                str(download["url"]) if download.get("url") else None,
                staged_path,
            )
        )
    return artifacts


def asset_index_artifact(
    metadata: Mapping[str, Any],
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> Artifact:
    asset_index = metadata.get("assetIndex") or {}
    index_id = str(asset_index.get("id") or metadata.get("assets") or "")
    installed_path = ASSET_ROOT / "indexes" / f"{index_id}.json"
    staged_path = cache_root / "assets" / "indexes" / f"{index_id}.json"
    return Artifact(
        f"asset index {index_id}",
        installed_path if installed_path.is_file() else staged_path,
        int(asset_index["size"]) if asset_index.get("size") is not None else None,
        str(asset_index["sha1"]) if asset_index.get("sha1") else None,
        str(asset_index["url"]) if asset_index.get("url") else None,
        staged_path,
    )


def verify_artifact(artifact: Artifact, *, verify_hash: bool = False) -> str | None:
    if not artifact.path.is_file():
        return "missing"
    if (
        artifact.expected_size is not None
        and artifact.path.stat().st_size != artifact.expected_size
    ):
        return f"size mismatch ({artifact.path.stat().st_size} != {artifact.expected_size})"
    if verify_hash and artifact.expected_sha1:
        digest = hashlib.sha1(
            artifact.path.read_bytes(), usedforsecurity=False
        ).hexdigest()
        if digest != artifact.expected_sha1:
            return f"SHA-1 mismatch ({digest} != {artifact.expected_sha1})"
    return None


def read_level_data_version(level_dat: Path) -> int:
    """Read the root DataVersion tag without adding an NBT package dependency."""
    return read_level_data_version_bytes(level_dat.read_bytes(), label=str(level_dat))


def read_level_data_version_bytes(
    compressed: bytes, *, label: str = "level.dat"
) -> int:
    payload = gzip.decompress(compressed)
    marker = b"\x03\x00\x0bDataVersion"
    offsets = [
        index for index in range(len(payload)) if payload.startswith(marker, index)
    ]
    if len(offsets) != 1:
        raise ValueError(
            f"expected one DataVersion tag in {label}, found {len(offsets)}"
        )
    value_offset = offsets[0] + len(marker)
    if value_offset + 4 > len(payload):
        raise ValueError(f"truncated DataVersion tag in {label}")
    return int.from_bytes(payload[value_offset : value_offset + 4], "big", signed=True)


def validate_world_version(world: Path) -> int:
    level_dat = world / "level.dat"
    if not level_dat.is_file():
        raise ValueError(f"source is not a Java world: {world}")
    data_version = read_level_data_version(level_dat)
    if data_version > PINNED_DATA_VERSION:
        raise ValueError(
            f"refusing to open newer world DataVersion {data_version} with pinned "
            f"Minecraft {PINNED_VERSION} ({PINNED_DATA_VERSION}); this would be a downgrade"
        )
    return data_version


def read_asset_objects(
    index: Artifact,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> list[Artifact]:
    payload = json.loads(index.path.read_text(encoding="utf-8"))
    artifacts: list[Artifact] = []
    seen_hashes: set[str] = set()
    for logical_name, entry in (payload.get("objects") or {}).items():
        digest = str(entry["hash"])
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        installed_path = ASSET_ROOT / "objects" / digest[:2] / digest
        staged_path = cache_root / "assets" / "objects" / digest[:2] / digest
        artifacts.append(
            Artifact(
                f"asset {logical_name}",
                installed_path if installed_path.is_file() else staged_path,
                int(entry["size"]),
                digest,
                f"https://resources.download.minecraft.net/{digest[:2]}/{digest}",
                staged_path,
            )
        )
    return artifacts


def preflight_install(
    metadata: Mapping[str, Any],
    os_context: Mapping[str, str],
    features: Mapping[str, bool],
    *,
    verify_hashes: bool,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> tuple[list[Artifact], Artifact]:
    libraries = selected_libraries(metadata, os_context, features, cache_root)
    asset_index = asset_index_artifact(metadata, cache_root)
    required = [*libraries, asset_index]
    problems = [
        artifact
        for artifact in required
        if verify_artifact(artifact, verify_hash=verify_hashes)
    ]
    if problems:
        raise MissingInstallArtifacts(problems)
    asset_problems = [
        artifact
        for artifact in read_asset_objects(asset_index, cache_root)
        if verify_artifact(artifact, verify_hash=verify_hashes)
    ]
    if asset_problems:
        raise MissingInstallArtifacts(asset_problems[:50])
    return libraries, asset_index


def download_artifact(artifact: Artifact) -> Artifact:
    """Download one pinned artifact into the isolated QA cache atomically."""
    if not artifact.url or not artifact.stage_path:
        raise ValueError(f"artifact has no staging metadata: {artifact.label}")
    target = artifact.stage_path
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    request = urllib.request.Request(
        artifact.url,
        headers={"User-Agent": "HillChapelNativeQA/1"},
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)
        staged = replace(artifact, path=temporary)
        problem = verify_artifact(staged, verify_hash=True)
        if problem:
            raise ValueError(
                f"download verification failed for {artifact.label}: {problem}"
            )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return replace(artifact, path=target)


def resolve_or_download(artifact: Artifact, *, download_missing: bool) -> Artifact:
    if verify_artifact(artifact, verify_hash=True) is None:
        return artifact
    if artifact.stage_path and artifact.stage_path != artifact.path:
        staged = replace(artifact, path=artifact.stage_path)
        if verify_artifact(staged, verify_hash=True) is None:
            return staged
    if not download_missing:
        return artifact
    print(f"Downloading {artifact.label}: {artifact.url}", flush=True)
    return download_artifact(artifact)


def materialize_asset_view(objects: Iterable[Artifact]) -> None:
    """Make the staged asset root complete using verified shared-cache files."""
    for artifact in objects:
        target = artifact.stage_path
        if target is None or artifact.path == target:
            continue
        if verify_artifact(artifact, verify_hash=True):
            raise ValueError(f"cannot stage invalid shared asset: {artifact.label}")
        if target.is_file():
            staged = replace(artifact, path=target)
            if verify_artifact(staged, verify_hash=True) is None:
                continue
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(artifact.path, target)
        except OSError:
            shutil.copy2(artifact.path, target)
        staged = replace(artifact, path=target)
        problem = verify_artifact(staged, verify_hash=True)
        if problem:
            raise ValueError(
                f"staged shared asset failed verification: {artifact.label}: {problem}"
            )


def prepare_install(
    metadata: Mapping[str, Any],
    os_context: Mapping[str, str],
    features: Mapping[str, bool],
    *,
    cache_root: Path,
    download_missing: bool,
    maximum_asset_download_bytes: int = 1_000_000_000,
) -> tuple[list[Artifact], Artifact]:
    """Resolve shared files and stage missing pinned files under the QA root."""
    libraries = [
        resolve_or_download(artifact, download_missing=download_missing)
        for artifact in selected_libraries(metadata, os_context, features, cache_root)
    ]
    index = resolve_or_download(
        asset_index_artifact(metadata, cache_root),
        download_missing=download_missing,
    )
    problems = [
        artifact
        for artifact in [*libraries, index]
        if verify_artifact(artifact, verify_hash=True)
    ]
    if problems:
        raise MissingInstallArtifacts(problems)

    objects = read_asset_objects(index, cache_root)
    missing_objects = [
        artifact for artifact in objects if verify_artifact(artifact, verify_hash=True)
    ]
    missing_bytes = sum(artifact.expected_size or 0 for artifact in missing_objects)
    print(
        f"Asset cache: {len(objects) - len(missing_objects)}/{len(objects)} objects available; "
        f"{missing_bytes:,} bytes missing",
        flush=True,
    )
    if missing_bytes > maximum_asset_download_bytes:
        raise RuntimeError(
            f"missing assets total {missing_bytes:,} bytes, exceeding the "
            f"{maximum_asset_download_bytes:,}-byte download gate"
        )
    if missing_objects and not download_missing:
        raise MissingInstallArtifacts(missing_objects[:50])
    if missing_objects:
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [
                executor.submit(download_artifact, artifact)
                for artifact in missing_objects
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
                completed += 1
                if completed == len(futures) or completed % 250 == 0:
                    print(
                        f"Downloaded {completed}/{len(futures)} asset objects",
                        flush=True,
                    )
    materialize_asset_view(objects)
    return libraries, index


def find_jdk_tool(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    homes: list[Path] = []
    if os.environ.get("JAVA_HOME"):
        homes.append(Path(os.environ["JAVA_HOME"]))
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        javac = Path(entry) / f"javac{suffix}"
        if entry and javac.is_file():
            homes.append(javac.resolve().parent.parent)
    install_roots = [Path.home() / ".jdks"]
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        install_roots.extend(
            program_files / vendor
            for vendor in ("Java", "Zulu", "Eclipse Adoptium", "Microsoft")
        )
    for root in install_roots:
        if root.is_dir():
            homes.extend(sorted(root.glob("*26*"), reverse=True))

    seen: set[Path] = set()
    for home in homes:
        home = home.resolve()
        if home in seen:
            continue
        seen.add(home)
        javac = home / "bin" / f"javac{suffix}"
        tool = home / "bin" / f"{name}{suffix}"
        if (
            javac.is_file()
            and tool.is_file()
            and re.search(r"\bjavac\s+26(?:[.\s+-]|$)", command_version(javac))
        ):
            return tool.resolve()
    raise FileNotFoundError(
        f"JDK 26 {name} was not found; install JDK 26 or set JAVA_HOME to its directory"
    )


def command_version(command: Path) -> str:
    result = subprocess.run(
        [str(command), "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def build_agent(build_root: Path) -> Path:
    javac = find_jdk_tool("javac")
    jar_tool = find_jdk_tool("jar")
    if " 26" not in command_version(javac):
        raise RuntimeError(f"JDK 26 javac is required, found: {command_version(javac)}")
    source = AGENT_ROOT / "src" / "org" / "thehill" / "qa" / "ChapelNativeQaAgent.java"
    manifest = AGENT_ROOT / "MANIFEST.MF"
    if not source.is_file() or not manifest.is_file():
        raise FileNotFoundError("native QA agent source or manifest is missing")
    classes = build_root / "classes"
    classes.mkdir(parents=True)
    subprocess.run(
        [str(javac), "--release", "25", "-Xlint:all", "-d", str(classes), str(source)],
        check=True,
    )
    agent_jar = build_root / "chapel-native-qa-agent.jar"
    subprocess.run(
        [
            str(jar_tool),
            "cfm",
            str(agent_jar),
            str(manifest),
            "-C",
            str(classes),
            "org",
        ],
        check=True,
    )
    return agent_jar


def validate_agent_configuration(
    agent_jar: Path, config: Path, expected_backup: Path
) -> None:
    java = find_jdk_tool("java")
    subprocess.run(
        [
            str(java),
            "-cp",
            str(agent_jar),
            "org.thehill.qa.ChapelNativeQaAgent",
            "--validate-config",
            str(config),
            expected_backup.as_posix(),
        ],
        check=True,
    )


def extract_natives(libraries: Iterable[Artifact], native_dir: Path) -> list[str]:
    native_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    for artifact in libraries:
        if "natives-windows" not in artifact.label:
            continue
        with zipfile.ZipFile(artifact.path) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or not entry.filename.lower().endswith(".dll"):
                    continue
                filename = Path(entry.filename).name
                target = native_dir / filename
                payload = archive.read(entry)
                if target.exists() and target.read_bytes() != payload:
                    raise ValueError(f"conflicting native library payload: {filename}")
                if not target.exists():
                    target.write_bytes(payload)
                extracted.append(filename)
    return sorted(set(extracted))


def copy_world(source: Path, game_dir: Path, world_name: str) -> Path:
    validate_world_version(source)
    if not (source / "region").is_dir():
        raise ValueError(f"source is not a Java world: {source}")
    target = game_dir / "saves" / world_name
    target.parent.mkdir(parents=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("session.lock", "*.lck"),
    )
    return target


def source_world_identity(source: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    for path in sorted(
        p for p in source.rglob("*") if p.is_file() and p.name != "session.lock"
    ):
        relative = path.relative_to(source).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    profile_path = source.parent / "profile.json"
    revision = None
    if profile_path.is_file():
        revision = json.loads(profile_path.read_text(encoding="utf-8")).get("revision")
    return {
        "source_fingerprint_sha256": digest.hexdigest(),
        "source_profile_revision": revision,
    }


def prepare_playable_world(
    source: Path, game_dir: Path, world_name: str
) -> tuple[Path, bool]:
    """Create once, then reuse the version-pinned isolated playable world."""
    manifest_path = game_dir / "playable-manifest.json"
    world = game_dir / "saves" / world_name
    if game_dir.exists():
        if not manifest_path.is_file() or not world.is_dir():
            raise ValueError(
                f"refusing to reuse incomplete playable directory without manifest: {game_dir}"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("minecraft_version") != PINNED_VERSION:
            raise ValueError(
                f"playable world is pinned to {manifest.get('minecraft_version')!r}, "
                f"not {PINNED_VERSION}"
            )
        validate_world_version(world)
        requested_identity = source_world_identity(source) if source.is_dir() else None
        if requested_identity and manifest.get("source_fingerprint_sha256") not in {
            None,
            requested_identity["source_fingerprint_sha256"],
        }:
            print(
                "Persistent playable world differs from the requested source; preserving its edits. "
                "Use a new --playable-dir for an intentional fresh import.",
                flush=True,
            )
        return world, False

    source_version = validate_world_version(source)
    if not (source / "region").is_dir():
        raise ValueError(f"source is not a Java world: {source}")
    game_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = game_dir.with_name(game_dir.name + ".staging-" + uuid.uuid4().hex)
    staging.mkdir()
    copy_world(source, staging, world_name)
    world = game_dir / "saves" / world_name
    manifest = {
        "format": "hill-chapel-playable-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "minecraft_version": PINNED_VERSION,
        "maximum_data_version": PINNED_DATA_VERSION,
        "source_world": str(source),
        "source_data_version": source_version,
        "world": str(world),
        "conversion_complete": False,
        **source_world_identity(source),
    }
    (staging / "playable-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    staging.replace(game_dir)
    return world, True


def mark_playable_ready(game_dir: Path, world: Path) -> None:
    manifest_path = game_dir / "playable-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_version = validate_world_version(world)
    manifest.update(
        {
            "conversion_complete": data_version == PINNED_DATA_VERSION,
            "current_data_version": data_version,
            "last_ready_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def profile_resource_pack(world: Path) -> Path | None:
    profile_path = world.parent / "profile.json"
    if not profile_path.is_file():
        return None
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    specification = profile.get("resource_pack") or (
        profile.get("materials") or {}
    ).get("resource_pack")
    value = (
        specification.get("path")
        if isinstance(specification, Mapping)
        else specification
    )
    if not value:
        return None
    source = Path(value)
    return source.resolve() if source.is_absolute() else (REPO_ROOT / source).resolve()


def install_resource_pack(source: Path | None, game_dir: Path) -> str | None:
    if source is None:
        return None
    metadata_path = source / "pack.mcmeta"
    if not metadata_path.is_file():
        raise ValueError(f"resource pack metadata is missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pack = metadata.get("pack") or {}
    pack_format = pack.get("pack_format")
    format_range = (pack.get("min_format"), pack.get("max_format"))
    if pack_format != 84 and format_range != ([84, 0], [84, 0]):
        raise ValueError(
            "resource pack must use 26.1.2 format 84.0; found "
            f"pack_format={pack_format!r}, range={format_range!r}"
        )
    target = game_dir / "resourcepacks" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return f"file/{target.name}"


def seed_options(game_dir: Path, resource_pack_id: str | None) -> None:
    """Seed startup-sensitive settings before vanilla loads its resources/screens."""
    options_path = game_dir / "options.txt"
    lines = (
        options_path.read_text(encoding="utf-8").splitlines()
        if options_path.is_file()
        else []
    )
    values = {
        "version": str(PINNED_DATA_VERSION),
        "narrator": "0",
        "narratorHotkey": "false",
        "pauseOnLostFocus": "false",
        "tutorialStep": "none",
        "skipMultiplayerWarning": "true",
        "onboardAccessibility": "false",
        "renderClouds": '"false"',
        "soundCategory_music": "0.0",
    }
    if resource_pack_id:
        values["resourcePacks"] = json.dumps(
            ["vanilla", resource_pack_id], separators=(",", ":")
        )
        values["incompatibleResourcePacks"] = "[]"
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        key, separator, _ = line.partition(":")
        if separator and key in remaining:
            updated.append(f"{key}:{remaining.pop(key)}")
        else:
            updated.append(line)
    updated.extend(f"{key}:{value}" for key, value in remaining.items())
    options_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def validate_preupgrade_backup(
    backup: Path,
    world: Path,
    world_name: str,
    data_version: int,
) -> bool:
    try:
        with zipfile.ZipFile(backup) as archive:
            if archive.testzip() is not None:
                return False
            level_name = (Path(world_name) / "level.dat").as_posix()
            manifest_name = "hill-chapel-backup-manifest.json"
            if (
                level_name not in archive.namelist()
                or manifest_name not in archive.namelist()
            ):
                return False
            if read_level_data_version_bytes(archive.read(level_name)) != data_version:
                return False
            manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
            return (
                manifest.get("format") == "hill-chapel-preupgrade-backup-v1"
                and manifest.get("world_name") == world_name
                and manifest.get("data_version") == data_version
                and manifest.get("source_world") == str(world.resolve())
            )
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        return False


def ensure_preupgrade_backup(world: Path, game_dir: Path, world_name: str) -> Path:
    """Create a stable launcher-side backup before native conversion is allowed."""
    backup_dir = game_dir / "pre-upgrade-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    data_version = validate_world_version(world)
    existing = sorted(backup_dir.glob(f"{world_name}-data-*.zip"))
    for candidate in existing:
        if validate_preupgrade_backup(candidate, world, world_name, data_version):
            return candidate
    target = backup_dir / f"{world_name}-data-{data_version}.zip"
    temporary = target.with_name(target.name + ".part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(world.rglob("*")):
            if path.is_file() and path.name != "session.lock":
                archive.write(path, Path(world_name) / path.relative_to(world))
        archive.writestr(
            "hill-chapel-backup-manifest.json",
            json.dumps(
                {
                    "format": "hill-chapel-preupgrade-backup-v1",
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source_world": str(world.resolve()),
                    "world_name": world_name,
                    "data_version": data_version,
                },
                sort_keys=True,
            )
            + "\n",
        )
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError(f"pre-upgrade backup was not written: {temporary}")
    temporary.replace(target)
    if not validate_preupgrade_backup(target, world, world_name, data_version):
        raise RuntimeError(
            f"pre-upgrade backup failed ZIP/provenance validation: {target}"
        )
    return target


def properties_text(
    views: Iterable[CameraView],
    player_name: str,
    settle_millis: int,
    resource_pack_id: str | None = None,
    preupgrade_backup: Path | None = None,
    render_distance: int = 16,
) -> str:
    view_list = list(views)
    lines = [
        "# Generated Hill Chapel native QA configuration",
        f"player.name={player_name}",
        f"view.count={len(view_list)}",
        f"settle.millis={settle_millis}",
        "startup.timeout.seconds=180",
        "camera.timeout.seconds=20",
        "screenshot.timeout.seconds=30",
        "exit.delay.millis=1500",
        "camera.eye.height=1.62",
        f"render.distance={render_distance}",
        "simulation.distance=10",
        "fov=70",
    ]
    if resource_pack_id:
        lines.append(f"resource.pack.id={escape_property_value(resource_pack_id)}")
    if preupgrade_backup:
        lines.append(
            f"preupgrade.backup={escape_property_value(preupgrade_backup.as_posix())}"
        )
    for index, view in enumerate(view_list):
        lines.extend(
            [
                f"view.{index}.name={view.name}",
                f"view.{index}.eye={','.join(format(value, '.6f') for value in view.eye)}",
                f"view.{index}.target={','.join(format(value, '.6f') for value in view.target)}",
                f"view.{index}.fov={view.fov}",
            ]
        )
    return "\n".join(lines) + "\n"


def escape_property_value(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("=", "\\=")
        .replace(":", "\\:")
        .replace("#", "\\#")
        .replace("!", "\\!")
    )


def launch_command(
    metadata: Mapping[str, Any],
    libraries: Iterable[Artifact],
    asset_index: Artifact,
    game_dir: Path,
    natives: Path,
    agent_jar: Path,
    config: Path,
    report: Path,
    world_name: str,
    width: int,
    height: int,
    player_name: str,
    mode: str = "capture",
    exit_when_ready: bool = False,
) -> list[str]:
    java = find_jdk_tool("java")
    if " 26" not in command_version(java):
        raise RuntimeError(f"JDK 26 java is required, found: {command_version(java)}")
    classpath = (
        os.pathsep.join(str(artifact.path) for artifact in libraries)
        + os.pathsep
        + str(VERSION_JAR)
    )
    features = {
        "has_custom_resolution": True,
        "has_quick_plays_support": True,
        "is_quick_play_singleplayer": True,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
        "is_demo_user": False,
    }
    asset_id = str(
        (metadata.get("assetIndex") or {}).get("id") or metadata.get("assets")
    )
    offline_uuid = uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + player_name).hex
    replacements = {
        "natives_directory": str(natives),
        "launcher_name": "HillChapelNativeQA",
        "launcher_version": "1",
        "classpath": classpath,
        "auth_player_name": player_name,
        "version_name": PINNED_VERSION,
        "game_directory": str(game_dir),
        "assets_root": str(asset_index.path.parent.parent),
        "assets_index_name": asset_id,
        "auth_uuid": offline_uuid,
        "auth_access_token": "0",
        "clientid": "0",
        "auth_xuid": "0",
        "version_type": "release",
        "resolution_width": str(width),
        "resolution_height": str(height),
        "quickPlayPath": str(game_dir / "quickplay.log"),
        "quickPlaySingleplayer": world_name,
        "quickPlayMultiplayer": "",
        "quickPlayRealms": "",
    }
    os_context = current_os_context()
    jvm_arguments = expand_arguments(
        (metadata.get("arguments") or {}).get("jvm") or [],
        replacements,
        os_context,
        features,
    )
    game_arguments = expand_arguments(
        (metadata.get("arguments") or {}).get("game") or [],
        replacements,
        os_context,
        features,
    )
    return [
        str(java),
        "-Xms1G",
        "-Xmx4G",
        f"-javaagent:{agent_jar}",
        f"-Dchapel.qa.config={config}",
        f"-Dchapel.qa.report={report}",
        f"-Dchapel.qa.mode={mode}",
        f"-Dchapel.qa.exit.when.ready={str(exit_when_ready).lower()}",
        *jvm_arguments,
        str(metadata["mainClass"]),
        *game_arguments,
    ]


def redact_command(command: list[str]) -> list[str]:
    redacted = list(command)
    for index, value in enumerate(redacted[:-1]):
        if value == "--accessToken":
            redacted[index + 1] = "<offline-placeholder>"
    return redacted


def wait_for_run(
    process: subprocess.Popen[bytes], report: Path, timeout_seconds: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest_status = None
    while time.monotonic() < deadline:
        if report.is_file():
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                if payload.get("status") != latest_status:
                    latest_status = payload.get("status")
                    print(f"native QA status: {latest_status}", flush=True)
                if latest_status in {"complete", "failed"}:
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=10)
                    return payload
            except (json.JSONDecodeError, OSError):
                pass
        exit_code = process.poll()
        if exit_code is not None:
            if report.is_file():
                return json.loads(report.read_text(encoding="utf-8"))
            raise RuntimeError(
                f"Minecraft exited with {exit_code} before writing a QA report"
            )
        time.sleep(0.5)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    raise TimeoutError(f"native QA run exceeded {timeout_seconds} seconds")


def wait_for_interactive_ready(
    process: subprocess.Popen[bytes],
    report: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if report.is_file():
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                if payload.get("status") == "ready":
                    return payload
                if payload.get("status") == "failed":
                    raise RuntimeError(
                        payload.get("failure") or "interactive agent failed"
                    )
            except json.JSONDecodeError:
                pass
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Minecraft exited with {exit_code} before the playable world was ready"
            )
        time.sleep(0.5)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    raise TimeoutError(
        f"interactive Minecraft startup exceeded {timeout_seconds} seconds"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--qa-root", type=Path, default=DEFAULT_QA_ROOT)
    parser.add_argument("--playable-dir", type=Path, default=DEFAULT_PLAYABLE_DIR)
    parser.add_argument("--run-name")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--settle-seconds", type=float, default=8.0)
    parser.add_argument(
        "--render-distance",
        type=int,
        default=16,
        help="native render distance in chunks (2–32)",
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--player-name", default="HillQA")
    parser.add_argument(
        "--start-view-config",
        type=Path,
        help="use the first view of a camera file as the interactive starting position",
    )
    parser.add_argument("--verify-hashes", action="store_true")
    capture_mode = parser.add_mutually_exclusive_group()
    capture_mode.add_argument(
        "--interactive",
        action="store_true",
        help="open the persistent isolated Chapel world for normal play",
    )
    capture_mode.add_argument(
        "--reference-views",
        action="store_true",
        help="add close 55-degree front and east-arcade comparison views",
    )
    capture_mode.add_argument(
        "--camera-config",
        type=Path,
        help="replace capture views with a hill-native-camera-views-v1 JSON file",
    )
    parser.add_argument(
        "--exit-when-ready",
        action="store_true",
        help="verification mode: exit an interactive client after the world is ready",
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="stage missing official pinned files in the isolated QA cache",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="verify the local pinned installation without copying or launching",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.width < 320 or args.height < 240:
        raise SystemExit("width and height must be at least 320x240")
    if not 2 <= args.render_distance <= 32:
        raise SystemExit("render distance must be between 2 and 32 chunks")
    if args.settle_seconds < 0 or args.timeout_seconds < 30:
        raise SystemExit(
            "settle time must be nonnegative and timeout at least 30 seconds"
        )
    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", args.player_name):
        raise SystemExit("player name must be 1-16 Minecraft-safe characters")
    if args.exit_when_ready and not args.interactive:
        raise SystemExit("--exit-when-ready requires --interactive")
    if args.interactive and args.run_name:
        raise SystemExit("--run-name is only used for screenshot QA runs")
    if args.interactive and args.reference_views:
        raise SystemExit("--reference-views is only used for screenshot QA runs")
    if args.interactive and args.camera_config:
        raise SystemExit("--camera-config is only used for screenshot QA runs")
    if args.reference_views and args.camera_config:
        raise SystemExit("--camera-config cannot be combined with --reference-views")

    try:
        views, camera_config_source = selected_camera_views(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    metadata = load_version_metadata()
    os_context = current_os_context()
    features = {
        "has_custom_resolution": True,
        "has_quick_plays_support": True,
        "is_quick_play_singleplayer": True,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
        "is_demo_user": False,
    }
    try:
        if args.download_missing or args.interactive:
            libraries, asset_index = prepare_install(
                metadata,
                os_context,
                features,
                cache_root=args.qa_root.resolve() / "cache",
                download_missing=True,
            )
        else:
            libraries, asset_index = preflight_install(
                metadata,
                os_context,
                features,
                verify_hashes=args.verify_hashes,
                cache_root=args.qa_root.resolve() / "cache",
            )
    except MissingInstallArtifacts as exc:
        print(str(exc), file=sys.stderr)
        for artifact in exc.artifacts:
            if artifact.url:
                print(f"    official URL: {artifact.url}", file=sys.stderr)
        return 2
    print(
        f"Pinned Minecraft {PINNED_VERSION} preflight passed: "
        f"{len(libraries)} libraries, asset index {asset_index.path.name}"
    )
    if args.preflight_only:
        return 0

    qa_root = args.qa_root.resolve()
    world_name = "hill_chapel_qa"
    if args.interactive:
        game_dir = args.playable_dir.resolve()
        copied_world, _ = prepare_playable_world(
            args.world.resolve(),
            game_dir,
            world_name,
        )
        build_root = (
            qa_root / "builds" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        build_root.mkdir(parents=True)
    else:
        run_name = args.run_name or datetime.now(timezone.utc).strftime(
            "run-%Y%m%dT%H%M%SZ"
        )
        if not RUN_NAME.fullmatch(run_name):
            raise SystemExit(
                "run name may contain only letters, numbers, dot, underscore, and dash"
            )
        game_dir = qa_root / "runs" / run_name
        if game_dir.exists():
            raise FileExistsError(
                f"refusing to overwrite existing native QA run: {game_dir}"
            )
        game_dir.mkdir(parents=True)
        copied_world = copy_world(args.world.resolve(), game_dir, world_name)
        build_root = game_dir / "agent"
        build_root.mkdir()
    resource_pack_source = profile_resource_pack(args.world.resolve())
    resource_pack_id = install_resource_pack(resource_pack_source, game_dir)
    seed_options(game_dir, resource_pack_id)
    preupgrade_backup = ensure_preupgrade_backup(copied_world, game_dir, world_name)
    agent_jar = build_agent(build_root)
    natives = game_dir / "natives"
    native_files = extract_natives(libraries, natives)
    config = game_dir / "chapel-native-qa.properties"
    report = game_dir / "chapel-native-qa-report.json"
    if report.exists():
        report.unlink()
    config.write_text(
        properties_text(
            views,
            args.player_name,
            int(args.settle_seconds * 1000),
            resource_pack_id,
            preupgrade_backup,
            args.render_distance,
        ),
        encoding="utf-8",
    )
    validate_agent_configuration(agent_jar, config, preupgrade_backup)
    command = launch_command(
        metadata,
        libraries,
        asset_index,
        game_dir,
        natives,
        agent_jar,
        config,
        report,
        world_name,
        args.width,
        args.height,
        args.player_name,
        "interactive" if args.interactive else "capture",
        args.exit_when_ready,
    )
    launch_manifest = {
        "format": "hill-chapel-native-qa-launch-v1",
        "mode": "interactive" if args.interactive else "capture",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "minecraft_version": PINNED_VERSION,
        "source_world": str(args.world.resolve()),
        "render_distance_chunks": args.render_distance,
        "copied_world": str(copied_world),
        "game_directory": str(game_dir),
        "asset_index": str(asset_index.path),
        "library_count": len(libraries),
        "native_files": native_files,
        "java": command_version(Path(command[0])),
        "agent_jar": str(agent_jar),
        "resource_pack": str(resource_pack_source) if resource_pack_source else None,
        "resource_pack_id": resource_pack_id,
        "preupgrade_backup": str(preupgrade_backup),
        "views": [asdict(view) for view in views],
        "command": redact_command(command),
    }
    if camera_config_source is not None:
        launch_manifest["camera_config_source"] = camera_config_source
    (game_dir / "launch-manifest.json").write_text(
        json.dumps(launch_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.interactive:
        log_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = game_dir / f"minecraft-{log_stamp}.log"
    else:
        log_path = game_dir / "minecraft.log"
    print(f"Launching visible native Minecraft client in {game_dir}")
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=game_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        if args.interactive:
            result = wait_for_interactive_ready(process, report, args.timeout_seconds)
            mark_playable_ready(game_dir, copied_world)
            print(f"Playable Chapel world ready: {copied_world}", flush=True)
            if args.exit_when_ready:
                process.wait(timeout=60)
            else:
                process.wait()
        else:
            result = wait_for_run(process, report, args.timeout_seconds)
    if args.interactive:
        return 0 if result.get("status") == "ready" else 1
    if result.get("status") != "complete" or len(result.get("views") or []) != len(
        views
    ):
        print(f"Native QA failed; inspect {report} and {log_path}", file=sys.stderr)
        return 1
    print(f"Native QA complete: {report}")
    for view in result["views"]:
        print(f"  {view['name']}: {view['screenshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
