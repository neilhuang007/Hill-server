#!/usr/bin/env python3
"""Package an explicitly selected campus folder plus the owner-supplied hub for IT."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('campus_check', Path(__file__).with_name('check-campus-template.py'))
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def assignment(path: Path, name: str) -> str:
    matches = re.findall(rf'^{re.escape(name)}="([^"\r\n]+)"$',
                         path.read_text(encoding='utf-8'), re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one {name} pin in {path.name}')
    return matches[0]


def archive_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100640 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def package(root: Path, destination: Path, campus: Path, resource_pack: Path | None = None) -> str:
    destination = destination.resolve()
    if not destination.is_relative_to((root / 'runtime/handoff').resolve()):
        raise ValueError('Write handoffs under runtime/handoff so they stay outside Git')
    if destination.exists():
        raise FileExistsError('Handoff already exists; choose a new output filename')
    CHECK.validate(campus)
    installer = root / 'ops/install-server.sh'
    hub_name = assignment(installer, 'HUB_ARCHIVE_NAME')
    expected = assignment(installer, 'HUB_SHA256')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.zip', hub_name) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid hub deployment pin')
    hub = (root / 'runtime/assets' / hub_name).read_bytes()
    if hashlib.sha256(hub).hexdigest() != expected:
        raise ValueError('Hub asset does not match deployment pin')
    files = {f'assets/{hub_name}': hub}
    # Explicit world-data allowlist; no recursive copies of saves or research.
    for name in ('region', 'poi'):
        for source in sorted((campus / name).glob('*')):
            if re.fullmatch(r'(?:r\.-?\d+\.-?\d+\.mca|c\.-?\d+\.-?\d+\.mcc)', source.name):
                if source.is_symlink() or not source.is_file():
                    raise ValueError('Template data must be regular files')
                files[f'world-templates/hill_people_template/{name}/{source.name}'] = source.read_bytes()
    for name in ('.hill175-people-ready', 'hill-campus-template.yml', 'hill-campus-template.json'):
        source = campus / name
        if source.is_file():
            files[f'world-templates/hill_people_template/{name}'] = source.read_bytes()
    if resource_pack is not None:
        pack_files = {'pack.mcmeta': (resource_pack / 'pack.mcmeta').read_bytes()}
        for source in sorted((resource_pack / 'assets').rglob('*')):
            if source.is_file() and source.suffix in {'.json', '.png', '.mcmeta'}:
                pack_files[source.relative_to(resource_pack).as_posix()] = source.read_bytes()
        files['resourcepacks/Hill175-campus-resources.zip'] = archive_bytes(pack_files)
    files['README.txt'] = (root / 'ops/handoff/README.txt').read_bytes()
    files['SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items())
    ).encode('utf-8')
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = archive_bytes(files)
    with destination.open('xb') as output:
        output.write(payload)
    digest = hashlib.sha256(payload).hexdigest()
    print(f'Handoff: {destination}\nBytes: {len(payload)}\nSHA-256: {digest}')
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campus-folder', required=True, type=Path,
                        help='Explicitly selected flat template with region/ and optional bounds/spawn metadata')
    parser.add_argument('--output', required=True, type=Path, help='New ZIP under runtime/handoff/')
    parser.add_argument('--resource-pack', type=Path)
    args = parser.parse_args()
    package(ROOT, args.output, args.campus_folder, args.resource_pack)


if __name__ == '__main__':
    main()
