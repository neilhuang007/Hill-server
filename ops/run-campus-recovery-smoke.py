#!/usr/bin/env python3
"""Check real scoped staff recovery over Java and Bedrock, and a real five minute timer."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bedrock_runner', ROOT / 'ops/run-bedrock-smoke.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def console_command(request):
    name = request['name']
    if not re.fullmatch(r'\.?Rec[0-9]{8}', name):
        raise ValueError('Unexpected recovery fixture player.')
    action = request['action']
    tell = lambda text: f'minecraft:tellraw {name} {json.dumps({"text": text})}'
    world = 'minecraft:execute in minecraft:hill_campus run '
    if action == 'campus':
        return [f'minecraft:execute as {name} at @s if dimension minecraft:hill_campus run minecraft:tellraw @s {{"text":"RECOVERY_CAMPUS"}}']
    if action == 'grant':
        # Floodgate assigns this UUID to unsigned clients with no XUID in the isolated fixture.
        subject = '00000000-0000-0000-0000-000000000000' if name.startswith('.') else name
        return [f'lp user {subject} permission set hill175.campus.rollback.area-s7 true', tell('RECOVERY_GRANT')]
    if action == 'inventory':
        return [f'minecraft:item replace entity {name} hotbar.3 with minecraft:netherite_ingot 7', tell('RECOVERY_INVENTORY')]
    if action == 'restart':
        return ['stop']
    if action in ('seed', 'damage'):
        block = 'blue_wool' if action == 'seed' else 'gold_block'
        neighbor = 'emerald_block' if action == 'seed' else 'diamond_block'
        chest = 'chest' if action == 'seed' else 'air'
        commands = [world + f'minecraft:forceload add 64 -48 80 -32',
                world + f'minecraft:setblock 70 200 -40 {block}',
                world + f'minecraft:setblock 69 200 -40 {neighbor}',
                world + f'minecraft:setblock 71 200 -40 {chest}']
        if action == 'seed':
            commands.append(world + 'minecraft:item replace block 71 200 -40 container.0 with minecraft:diamond 3')
            if os.environ.get('HILL175_RECOVERY_PREVIEW') == '1':
                commands.append(f'minecraft:item replace entity {name} hotbar.3 with minecraft:netherite_ingot 7')
        return commands + [tell('RECOVERY_SEEDED' if action == 'seed' else 'RECOVERY_DAMAGED')]
    if action == 'assert-damaged':
        return [world + f'minecraft:execute if block 70 200 -40 gold_block run {tell("RECOVERY_STILL_DAMAGED")}']
    if action == 'assert-preview':
        return [world + f'minecraft:execute if block 70 200 -40 gold_block as {name} at @s unless dimension minecraft:hill_campus '
                + 'if entity @s[gamemode=adventure] if block 70 200 -40 blue_wool if items block 71 200 -40 container.0 minecraft:diamond run '
                + tell('RECOVERY_PREVIEW_EXACT')]
    if action == 'load-preview':
        return [f'minecraft:execute as {name} at @s run minecraft:forceload add 64 -48 80 -32',
                f'minecraft:execute as {name} at @s run minecraft:tp @s 72 203 -37', tell('RECOVERY_PREVIEW_POSITION')]
    if action == 'assert-canceled':
        return [f'minecraft:execute as {name} at @s if dimension minecraft:hill_campus if entity @s[gamemode=creative] '
                + 'if block 70 200 -40 gold_block if items entity @s hotbar.3 minecraft:netherite_ingot run ' + tell('RECOVERY_CANCEL_EXACT')]
    if action == 'assert-restored':
        return [world + 'minecraft:execute if block 70 200 -40 blue_wool if block 69 200 -40 diamond_block '
                + 'if block 71 200 -40 chest if items block 71 200 -40 container.0 minecraft:diamond run '
                + tell('RECOVERY_EXACT_RESTORE')]
    raise ValueError('Unknown fixture action.')


def client(args, runtime, server, platform, phase='flow'):
    if platform == 'bedrock' and phase == 'flow':
        server.stdin.write('lp user 00000000-0000-0000-0000-000000000000 permission unset hill175.campus.rollback.area-s7\n')
        server.stdin.flush()
        time.sleep(1)
    env = os.environ | {'HILL175_RECOVERY_FIXTURE': str(runtime), 'HILL175_RECOVERY_JAVA_PORT': str(args.javaPort),
                        'HILL175_RECOVERY_BEDROCK_PORT': str(args.bedrockPort)}
    with subprocess.Popen([args.node, str(ROOT / 'ops/smoke-campus-recovery.mjs'), platform, phase], cwd=ROOT, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8') as process:
        with (runtime / f'client-recovery-{platform}-{phase}.log').open('w', encoding='utf-8') as log:
            for line in process.stdout:
                log.write(line); log.flush()
                if line.startswith('SMOKE_RECOVERY '):
                    for command in console_command(json.loads(line.removeprefix('SMOKE_RECOVERY '))):
                        server.stdin.write(command + '\n')
                    server.stdin.flush()
                else:
                    print(line, end='', flush=True)
        if process.wait(timeout=10):
            raise RuntimeError(platform + ' recovery smoke failed.')


def main():
    args = runner.parseArguments()
    if args.reuse:
        runtime = args.output.resolve(strict=True)
        if not runner.isFixturePath(runtime) or not (runtime / '.hill175-smoke-fixture').is_file() or 'server-ip=127.0.0.1' not in (runtime / 'server.properties').read_text():
            raise ValueError('Resume only a disposable loopback fixture.')
        with runner.installer.stopped_world(runtime):
            shutil.copy2(args.plugin, runtime / 'plugins/Hill175.jar')
    else:
        runtime = runner.stageRuntime(args)
    manifest = runner.installer.load_manifest()
    runner.installer.prepare(runtime, manifest, args.bedrockPort)
    runner.installer.install(runtime, manifest, args.bedrockPort)
    config = runtime / 'plugins/Geyser-Spigot/config.yml'
    secured = config.read_bytes()
    try:
        if not args.reuse or not (runtime / 'report-reject-offline.json').is_file():
            runner.writeBridgeConfig(runtime, secured, True)
            with runner.runningServer(args, runtime, 'recovery-secure') as server:
                environment = os.environ | {'HILL175_BEDROCK_SMOKE_SERVER': str(runtime), 'HILL175_BEDROCK_SMOKE_PORT': str(args.bedrockPort),
                                            'HILL175_BEDROCK_ISOLATED_OFFLINE': '1', 'HILL175_BEDROCK_SMOKE_USERNAME': 'Bed' + str(time.time_ns())[-9:]}
                runner.runClient(args, runtime, server, 'reject-offline', environment)
        runner.writeBridgeConfig(runtime, secured, False)
        with runner.runningServer(args, runtime, 'recovery') as server:
            started = time.monotonic()
            started_wall = time.time()
            if os.environ.get('HILL175_RECOVERY_PREVIEW_RESTART_ONLY') != '1':
                client(args, runtime, server, 'java')
                client(args, runtime, server, 'bedrock')
            log = runtime / 'server-recovery.log'
            if os.environ.get('HILL175_RECOVERY_PREVIEW') == '1':
                client(args, runtime, server, 'java', 'prepare-restart')
            else:
                while time.monotonic() - started < 390:
                    if any('five-minute' in snapshot.get('tags', []) and datetime.fromisoformat(snapshot['time']).timestamp() >= started_wall for snapshot in snapshots(runtime)):
                        print('PASS: real scheduled five minute recovery point created.', flush=True)
                        break
                    print('Waiting for the real five minute recovery timer...', flush=True)
                    time.sleep(20)
                else:
                    raise RuntimeError('Scheduled five minute recovery snapshot was not created.')
        if os.environ.get('HILL175_RECOVERY_PREVIEW') == '1':
            with runner.runningServer(args, runtime, 'recovery-preview-restart') as server:
                client(args, runtime, server, 'java', 'after-restart')
        print('PASS: Java and Bedrock recovery, neighbor isolation and chest NBT. Preview mode also checks menus, cancel, version switching, disconnect and restart. ' + str(runtime))
    finally:
        config.write_bytes(secured)
        runner.installer.verify(runtime, manifest, args.bedrockPort)


def snapshots(runtime):
    binary = runtime / ('tools/restic.exe' if os.name == 'nt' else 'tools/restic')
    output = subprocess.check_output([str(binary), '--repo', str(runtime / 'campus-backups/restic'), '--password-file',
                                      str(runtime / 'campus-backups/restic-password'), 'snapshots', '--json'], text=True)
    (runtime / 'recovery-snapshots.json').write_text(output)
    return json.loads(output)


if __name__ == '__main__':
    main()
