"""Start, inspect or gracefully stop a prepared local Hill175 preview."""
import argparse
import importlib.util
import ipaddress
import json
import os
import re
from pathlib import Path
import shutil
import socket
import time

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_runner', root / 'ops/run-bedrock-smoke.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def local_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        # Select the local route without transmitting a datagram.
        probe.connect(('192.0.2.1', 9))
        value = probe.getsockname()[0]
    address = ipaddress.ip_address(value)
    if not address.is_private or address.is_loopback or address.is_link_local:
        raise ValueError('A private LAN address is needed for local NetherNet. Supply --bedrock-address.')
    return value


def main():
    base = Path(os.environ.get('LOCALAPPDATA', str(root))) / 'Hill175'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--runtime', type=Path, default=base / 'runtime/area-bedrock-v54-20261029')
    parser.add_argument('--java', default=str(base / 'jdk25/bin/java.exe'))
    parser.add_argument('--bedrock-address')
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    if not runner.isFixturePath(runtime) or not (runtime / '.hill175-smoke-fixture').is_file():
        raise ValueError('Use a prepared disposable Hill175 fixture.')
    status = runtime / 'local-preview.json'
    stop = runtime / 'local-preview.stop'
    if args.action == 'status':
        print(status.read_text() if status.exists() else 'Local preview is stopped.')
        return
    if args.action == 'stop':
        if status.exists():
            stop.write_text('Stop requested\n')
            print('Graceful stop requested. The server will save its worlds.')
        else:
            print('Local preview is stopped.')
        return
    args.javaPort, args.bedrockPort, args.galleryPort = 25568, 19134, 8789
    for port, kind in [(25568, socket.SOCK_STREAM), (19134, socket.SOCK_STREAM),
                       (19134, socket.SOCK_DGRAM), (19135, socket.SOCK_DGRAM), (8789, socket.SOCK_STREAM)]:
        runner.availablePort(port, kind)
    address = args.bedrock_address or local_address()
    parsed = ipaddress.ip_address(address)
    if parsed.version != 4 or not parsed.is_private or parsed.is_loopback or parsed.is_link_local:
        raise ValueError('Bedrock preview must bind a private IPv4 LAN address.')
    with runner.installer.stopped_world(runtime):
        shutil.copy2(root / 'build/libs/Hill-server-1.0-SNAPSHOT.jar', runtime / 'plugins/Hill175.jar')
    config_file = runtime / 'plugins/Geyser-Spigot/config.yml'
    original = config_file.read_bytes()
    header, body = original.decode().split('\n', 1)
    config = json.loads(body)
    if config['advanced']['bedrock']['validate-bedrock-login'] is not True:
        raise ValueError('Restore secure Bedrock authentication before starting the preview.')
    config['bedrock']['address'] = address
    config['bedrock']['transport'] = 'both'
    config['bedrock']['signaling'] = {'mode': 'builtin', 'stun-discovery': False,
                                    'advertise-addresses': [f'{address}:19135']}
    metadata = (runtime / 'world-templates/hill_people_template/hill-campus-template.yml').read_text(encoding='utf-8')
    revision = re.search(r'^revision:\s*(\S+)', metadata, re.MULTILINE)
    if not revision:
        raise ValueError('Campus template must identify its explicitly selected revision.')
    info = {'state': 'starting', 'supervisor_pid': os.getpid(), 'java': '127.0.0.1:25568',
            'bedrock': f'{address}:19134', 'gallery': 'http://localhost:8789',
            'campus': revision.group(1), 'authentication': 'development with Xbox validation for Bedrock'}
    with status.open('x', encoding='utf-8') as output:
        json.dump(info, output, indent=2)
    stop.unlink(missing_ok=True)
    os.environ.pop('HILL175_GALLERY_PUBLIC_URL', None)
    try:
        config_file.write_text(header + '\n' + json.dumps(config, indent=2) + '\n', encoding='utf-8')
        restore_restarts = 0
        while True:
            with runner.runningServer(args, runtime, 'local-preview') as server:
                if not (runtime / 'campus-shared-restore-request.properties').exists():
                    restore_restarts = 0
                status.write_text(json.dumps(info | {'state': 'ready', 'pid': server.pid}, indent=2))
                print(status.read_text(), flush=True)
                while server.poll() is None and not stop.exists():
                    time.sleep(0.25)
            if stop.exists() or not (runtime / 'campus-shared-restore-request.properties').exists():
                break
            restore_restarts += 1
            if restore_restarts > 3:
                raise RuntimeError('Campus restore could not finish. The pending request and previous worlds are preserved.')
            status.write_text(json.dumps(info | {'state': 'restoring'}, indent=2))
            print('Restarting to restore the requested campus backup.', flush=True)
    finally:
        config_file.write_bytes(original)
        status.unlink(missing_ok=True)
        stop.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
