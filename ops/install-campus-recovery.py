#!/usr/bin/env python3
"""Install verified Restic, WorldEdit and LuckPerms. Run install only while Paper is stopped."""
import argparse
import bz2
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'server-assets/campus-recovery-manifest.json'
spec = importlib.util.spec_from_file_location('bedrock_install', ROOT / 'ops/install-bedrock.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def download(item, cache):
    cache.parent.mkdir(parents=True, exist_ok=True)
    algorithm = 'sha512' if 'sha512' in item else 'sha256'
    if cache.is_file() and hashlib.new(algorithm, cache.read_bytes()).hexdigest() == item[algorithm]:
        return cache.read_bytes()
    data = urllib.request.urlopen(urllib.request.Request(item['url'], headers={'User-Agent': 'Hill175/1.0'}), timeout=120).read()
    if hashlib.new(algorithm, data).hexdigest() != item[algorithm]:
        raise ValueError('Download checksum mismatch: ' + item['url'])
    cache.write_bytes(data)
    return data


def prepare(runtime):
    manifest = json.loads(MANIFEST.read_text())
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Only the pinned x86_64 recovery tools are supported.')
    cache = runtime / 'assets/campus-recovery'
    for name in ('worldedit', 'luckperms'):
        download(manifest[name], cache / (name + '.jar'))
    target_platform = 'windows' if os.name == 'nt' else 'linux'
    item = manifest['restic'][target_platform]
    download(item, cache / Path(item['url']).name)
    return manifest, cache, target_platform


def install(runtime):
    manifest, cache, target_platform = prepare(runtime)
    with installer.stopped_world(runtime):
        for name in ('worldedit', 'luckperms'):
            target = installer.safe_path(runtime, manifest[name]['target'])
            # Prevent duplicate plugin instances from an existing operator installation.
            for jar in (runtime / 'plugins').glob('*.jar'):
                if jar != target and installer.plugin_name(jar).lower() == name:
                    raise ValueError('Existing plugin must be reviewed before installing: ' + str(jar))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(download(manifest[name], cache / (name + '.jar')))
        data = download(manifest['restic'][target_platform], cache / Path(manifest['restic'][target_platform]['url']).name)
        binary = installer.safe_path(runtime, 'tools/restic.exe' if os.name == 'nt' else 'tools/restic')
        binary.parent.mkdir(parents=True, exist_ok=True)
        if target_platform == 'windows':
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = [name for name in archive.namelist() if name.endswith('.exe')]
                if len(members) != 1:
                    raise ValueError('Unexpected Restic archive layout.')
                binary.write_bytes(archive.read(members[0]))
        else:
            binary.write_bytes(bz2.decompress(data))
            binary.chmod(0o750)
        folder = installer.safe_path(runtime, 'campus-backups')
        folder.mkdir(mode=0o700, exist_ok=True)
        password = installer.safe_path(runtime, 'campus-backups/restic-password')
        repository = installer.safe_path(runtime, 'campus-backups/restic')
        if not password.exists():
            if repository.exists():
                raise ValueError('Existing Restic repository has no password file. Recover its original key.')
            with password.open('x', encoding='utf-8') as output:
                output.write(secrets.token_hex(32) + '\n')
            password.chmod(0o600)
        if not (repository / 'config').exists():
            subprocess.run([str(binary), '--repo', str(repository), '--password-file', str(password), 'init'], check=True)
        print('Campus recovery ready: Restic, WorldEdit and LuckPerms.')


def verify(runtime):
    manifest = json.loads(MANIFEST.read_text())
    for name in ('worldedit', 'luckperms'):
        target = installer.safe_path(runtime, manifest[name]['target'])
        if not target.is_file() or hashlib.sha512(target.read_bytes()).hexdigest() != manifest[name]['sha512']:
            raise ValueError('Recovery plugin checksum mismatch: ' + str(target))
    binary = installer.safe_path(runtime, 'tools/restic.exe' if os.name == 'nt' else 'tools/restic')
    output = subprocess.check_output([str(binary), 'version'], text=True)
    if not output.startswith('restic ' + manifest['restic']['version'] + ' '):
        raise ValueError('Unexpected Restic version.')
    for relative in ('campus-backups/restic-password', 'campus-backups/restic/config'):
        if not installer.safe_path(runtime, relative).is_file():
            raise ValueError('Recovery repository or key missing: ' + relative)
    print('Campus recovery plugins, Restic version and repository verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install', 'verify'])
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    if args.action == 'prepare':
        prepare(runtime)
    elif args.action == 'install':
        install(runtime)
    else:
        verify(runtime)
