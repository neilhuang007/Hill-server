"""Run the student area journey on a disposable loopback Paper server with the selected campus."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import shutil

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bedrock_runner', root / 'ops/run-bedrock-smoke.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

if __name__ == '__main__':
    args = runner.parseArguments()
    runner.availablePort(args.javaPort, socket.SOCK_STREAM)
    runner.availablePort(args.bedrockPort, socket.SOCK_DGRAM)
    runner.availablePort(args.galleryPort, socket.SOCK_STREAM)
    runtime = args.output.resolve()
    if args.reuse:
        if not runtime.is_relative_to(root / 'runtime') or not (runtime / 'server-java-areas.log').is_file():
            raise ValueError('Only a previous disposable area fixture can be resumed.')
        if 'server-ip=127.0.0.1' not in (runtime / 'server.properties').read_text():
            raise ValueError('The resumed fixture must be loopback only.')
        with runner.installer.stopped_world(runtime):
            shutil.copy2(args.plugin, runtime / 'plugins/Hill175.jar')
    else:
        runtime = runner.stageRuntime(args)
    manifest = runner.installer.load_manifest()
    runner.installer.prepare(runtime, manifest, args.bedrockPort)
    runner.installer.install(runtime, manifest, args.bedrockPort)
    config_file = runtime / 'plugins/Geyser-Spigot/config.yml'
    secured = config_file.read_bytes()
    runner.writeBridgeConfig(runtime, secured, True)
    try:
        with runner.runningServer(args, runtime, 'java-areas'):
            environment = {**os.environ, 'HILL175_SMOKE_PORT': str(args.javaPort),
                           'HILL175_AREA_REPORT': str(runtime / 'area-player-report.json')}
            subprocess.run([args.node, str(root / 'ops/smoke-campus-areas.mjs')], cwd=root,
                           env=environment, check=True, timeout=600)
    finally:
        config_file.write_bytes(secured)
        runner.installer.verify(runtime, manifest, args.bedrockPort)
