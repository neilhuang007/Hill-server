#!/usr/bin/env python3
"""Smoke-start a built Hill175 JAR in disposable, unpublished Docker Paper worlds.

This is a runtime boot smoke, not an in-game/SSO/production installer acceptance test.
Docker receives no host volumes, secrets, production network ports or existing saves.
"""
import argparse
import bz2
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BINARIES = ROOT / 'server-assets/server-binaries.env'
RECOVERY = ROOT / 'server-assets/campus-recovery-manifest.json'


def checked(*args, capture=False):
    return subprocess.run(args, check=True, text=True, capture_output=capture)


def download(url, destination, digest, algorithm='sha256'):
    if destination.is_file() and hashlib.new(algorithm, destination.read_bytes()).hexdigest() == digest:
        return destination
    request = urllib.request.Request(url, headers={'User-Agent': 'Hill175-deployment-smoke/1.0'})
    with urllib.request.urlopen(request, timeout=120) as source, destination.open('wb') as target:
        shutil.copyfileobj(source, target)
    if hashlib.new(algorithm, destination.read_bytes()).hexdigest() != digest:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f'{algorithm} mismatch: {url}')
    return destination


def run_script(docker, container, script):
    return checked(docker, 'exec', container, 'bash', '-lc', 'set -euo pipefail; ' + script, capture=True).stdout.strip()


def copy_file(docker, container, local, remote):
    checked(docker, 'cp', str(local), f'{container}:{remote}')


def wait_ready(docker, container, phase, timeout_seconds=210):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        log = run_script(docker, container, 'cat /srv/logs/latest.log 2>/dev/null || true')
        if 'Done (' in log:
            return log
        if run_script(docker, container, 'if test -f /tmp/paper.pid && kill -0 "$(cat /tmp/paper.pid)" 2>/dev/null; then echo running; fi') != 'running':
            raise RuntimeError(f'{phase} stopped before Paper was ready:\n{log[-7000:]}')
        time.sleep(2)
    raise TimeoutError(f'{phase} did not become ready in {timeout_seconds}s:\n{log[-7000:]}')


def start_paper(docker, container, phase):
    checked(docker, 'exec', '-d', container, 'bash', '-lc',
            f'cd /srv; java -Xms256M -Xmx3G -jar paper.jar nogui > /srv/{phase}.stdout 2>&1 & child=$!; echo "$child" > /tmp/paper.pid; wait "$child"')
    return wait_ready(docker, container, phase)


def stop_paper(docker, container):
    # Java launched by an asynchronous shell can inherit ignored SIGINT.
    # SIGTERM invokes Paper's JVM shutdown hook and flushes its worlds normally.
    run_script(docker, container, 'kill -TERM "$(cat /tmp/paper.pid)" 2>/dev/null || true')
    for _ in range(60):
        if run_script(docker, container, 'if kill -0 "$(cat /tmp/paper.pid)" 2>/dev/null; then echo running; fi') != 'running':
            return
        time.sleep(1)
    raise TimeoutError('Paper did not stop after SIGTERM')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, default=ROOT / 'build/libs/Hill-server-1.0-SNAPSHOT.jar')
    parser.add_argument('--docker', default=shutil.which('docker') or r'C:\Program Files\Docker\Docker\resources\bin\docker.exe')
    parser.add_argument('--output-dir', type=Path, help='Keep synthetic logs and a JSON result here (default: runtime/deployment-smoke/<UTC>-<random>)')
    parser.add_argument('--packet-replay-runtime', type=Path, help='A prepared/installed isolated recorder staging runtime to verify and copy into Docker')
    args = parser.parse_args()
    if not args.jar.is_file():
        parser.error('Build the plugin with JDK 25 first: bash ./gradlew clean test jar')
    if not Path(args.docker).exists() and not shutil.which(args.docker):
        parser.error('Docker CLI is required; start Docker Desktop or install Docker Engine')

    replay_files = []
    if args.packet_replay_runtime:
        checked(sys.executable, str(ROOT / 'ops/packet-replay-install.py'), 'verify', '--runtime', str(args.packet_replay_runtime))
        replay_files = checked(sys.executable, str(ROOT / 'ops/packet-replay-install.py'), 'files', capture=True).stdout.splitlines()

    binaries = dict(line.split('=', 1) for line in BINARIES.read_text().splitlines() if line and not line.startswith('#'))
    recovery = json.loads(RECOVERY.read_text())
    identifier = secrets.token_hex(6)
    container = 'hill175-smoke-' + identifier
    output = args.output_dir or ROOT / 'runtime/deployment-smoke' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + identifier)
    output.mkdir(parents=True, exist_ok=False)
    report = {
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'result': 'failed', 'container': container,
        'plugin_sha256': hashlib.sha256(args.jar.read_bytes()).hexdigest(),
        'paper_sha256': binaries['PAPER_SHA256'],
        'scope': 'isolated synthetic Paper boot, plugin enable, private invalid-token HTTP and graceful shutdown only',
    }
    print(f'Synthetic smoke artifacts: {output}', flush=True)
    with tempfile.TemporaryDirectory(prefix='hill175-deployment-smoke-') as temporary:
        stage = Path(temporary)
        paper = ROOT / 'runtime/server/paper.jar'
        if not paper.is_file() or hashlib.sha256(paper.read_bytes()).hexdigest() != binaries['PAPER_SHA256']:
            paper = download(binaries['PAPER_URL'], stage / 'paper.jar', binaries['PAPER_SHA256'])
        tools = {}
        for name in ('worldedit', 'luckperms'):
            entry = recovery[name]
            tools[name] = download(entry['url'], stage / (name + '.jar'), entry['sha512'], 'sha512')
        entry = recovery['restic']['linux']
        restic_archive = download(entry['url'], stage / 'restic.bz2', entry['sha256'])
        (stage / 'restic').write_bytes(bz2.decompress(restic_archive.read_bytes()))
        print('Verified pinned Paper, WorldEdit, LuckPerms, Restic checksums.')
        checked(args.docker, 'run', '-d', '--name', container, '--memory', '6g',
                '--cpus', '4', '--network', 'bridge',
                '-e', 'HILL175_GALLERY_PUBLIC_URL=https://builds.example.invalid',
                '-e', 'HILL175_STUDENT_DOWNLOAD_URL=https://builds.example.invalid/student-map/',
                '-e', 'HILL175_STUDENT_DOWNLOAD_EXPORT=/srv/approved-campus-export',
                '-e', 'HILL175_PACKET_REPLAY_ENABLED=' + ('true' if replay_files else 'false'),
                'eclipse-temurin:25-jdk', 'sleep', 'infinity', capture=True)
        try:
            run_script(args.docker, container, 'mkdir -p /srv/plugins/Hill175 /srv/tools /srv/campus-backups /srv/world-templates; printf "eula=true\\n" >/srv/eula.txt; printf "server-ip=127.0.0.1\\nserver-port=25579\\nlevel-name=world\\nview-distance=3\\nsimulation-distance=3\\nonline-mode=false\\nmax-players=2\\n" >/srv/server.properties')
            copy_file(args.docker, container, paper, '/srv/paper.jar')
            print('Bootstrapping synthetic private Paper world (no operator map or student data)...')
            bootstrap_log = start_paper(args.docker, container, 'bootstrap')
            (output / 'bootstrap.log').write_text(bootstrap_log, encoding='utf-8')
            stop_paper(args.docker, container)
            run_script(args.docker, container,
                'mkdir -p /srv/world-templates/hill_people_template /srv/world-templates/hill_hub /srv/approved-campus-export; '
                'source_region=/srv/world/region; '
                'if ! compgen -G "$source_region/r.*.mca" >/dev/null; then source_region=/srv/world/dimensions/minecraft/overworld/region; fi; '
                'compgen -G "$source_region/r.*.mca" >/dev/null || { echo "No generated Overworld region files" >&2; exit 1; }; '
                'cp -a "$source_region" /srv/world-templates/hill_people_template/; '
                'cp -a /srv/world/level.dat "$source_region" /srv/world-templates/hill_hub/; '
                'cp -a /srv/world/level.dat "$source_region" /srv/approved-campus-export/; '
                'rm -rf /srv/logs; '
                'printf "server-ip=127.0.0.1\\nserver-port=25579\\nlevel-name=world\\nview-distance=3\\nsimulation-distance=3\\nonline-mode=false\\nmax-players=2\\n" >/srv/server.properties')
            copy_file(args.docker, container, args.jar, '/srv/plugins/Hill175.jar')
            copy_file(args.docker, container, tools['worldedit'], '/srv/plugins/WorldEdit.jar')
            copy_file(args.docker, container, tools['luckperms'], '/srv/plugins/LuckPerms.jar')
            copy_file(args.docker, container, stage / 'restic', '/srv/tools/restic')
            for relative in replay_files:
                run_script(args.docker, container, 'mkdir -p /srv/' + str(Path(relative).parent).replace('\\', '/'))
                copy_file(args.docker, container, args.packet_replay_runtime / relative, '/srv/' + relative)
            copy_file(args.docker, container, ROOT / 'src/main/resources/config.yml', '/srv/plugins/Hill175/config.yml')
            copy_file(args.docker, container, ROOT / 'server-config/spigot.yml', '/srv/spigot.yml')
            run_script(args.docker, container,
                'chmod 700 /srv/tools/restic; head -c 32 /dev/urandom | od -An -tx1 | tr -d " \\n" >/srv/campus-backups/restic-password; '
                '/srv/tools/restic --repo /srv/campus-backups/restic --password-file /srv/campus-backups/restic-password init >/srv/restic-init.log')
            print('Starting built Hill175 plugin with isolated maps and a fresh Restic repository...')
            log = start_paper(args.docker, container, 'plugin')
            (output / 'plugin-startup.log').write_text(log, encoding='utf-8')
            if 'Hill 175 competition server enabled' not in log or 'Enabling Hill175' not in log:
                raise RuntimeError('Paper became ready but Hill175 did not enable:\n' + log[-9000:])
            if replay_files and 'Private packet replay enabled:' not in log:
                raise RuntimeError('Hardened packet recorder did not enable')
            if '[ERROR]' in log or 'Exception' in log:
                raise RuntimeError('Server log reported an error or exception:\n' + log[-9000:])
            response = run_script(args.docker, container,
                'exec 3<>/dev/tcp/127.0.0.1/8791; '
                'printf "GET /student-map/not-a-valid-token HTTP/1.1\\r\\nHost: builds.example.invalid\\r\\nConnection: close\\r\\n\\r\\n" >&3; '
                'cat <&3')
            (output / 'invalid-download-response.txt').write_text(response, encoding='utf-8')
            if '404 Not Found' not in response or 'no-store' not in response.lower():
                raise RuntimeError('Student-map HTTP denied-link response missing 404 or no-store:\n' + response[:3000])
            print('PASS: Paper ready; Hill175 enabled; no startup errors; private /student-map/ denied unknown token with no-store.')
            stop_paper(args.docker, container)
            report['result'] = 'passed'
            report['packet_replay_enabled'] = bool(replay_files)
        except Exception as error:
            report['error'] = str(error)
            print(run_script(args.docker, container, 'tail -150 /srv/logs/latest.log 2>/dev/null || true'))
            raise
        finally:
            try:
                for name in ('bootstrap.stdout', 'plugin.stdout', 'logs/latest.log'):
                    log = run_script(args.docker, container, f'cat /srv/{name} 2>/dev/null || true')
                    (output / name.replace('/', '-')).write_text(log, encoding='utf-8')
                report['finished_utc'] = datetime.now(timezone.utc).isoformat()
                (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            finally:
                checked(args.docker, 'rm', '-f', container, capture=True)


if __name__ == '__main__':
    main()
