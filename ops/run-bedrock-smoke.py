#!/usr/bin/env python3
"""Run real Bedrock packets through a private, temporary Paper/Geyser/Floodgate server.

Copies templates, never player worlds. It checks secure rejection first, enables
unsigned clients on loopback for gameplay, restarts to check persistence, then
stops and restores the installer's secured configuration even on failure.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid


repository = Path(__file__).resolve().parents[1]
installerSpec = importlib.util.spec_from_file_location("bedrockInstaller", repository / "ops/install-bedrock.py")
installer = importlib.util.module_from_spec(installerSpec)
installerSpec.loader.exec_module(installer)


def availablePort(port, transport):
    with socket.socket(socket.AF_INET, transport) as listener:
        listener.bind(("127.0.0.1", port))


def copyDependencies(source, runtime):
    for folderName in ("cache", "libraries", "versions"):
        copyDependencyFolder(source / folderName, runtime / folderName)


def copyDependencyFolder(sourceFolder, targetFolder):
    for sourceFile in sourceFolder.rglob("*"):
        if sourceFile.is_file():
            linkOrCopy(sourceFile, targetFolder / sourceFile.relative_to(sourceFolder))


def linkOrCopy(sourceFile, targetFile):
    targetFile.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(sourceFile, targetFile)
    except OSError:
        shutil.copy2(sourceFile, targetFile)


def isFixturePath(runtime):
    roots = [(repository / 'runtime').resolve()]
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        roots.append((Path(os.environ['LOCALAPPDATA']) / 'Hill175/runtime').resolve())
    return any(runtime != root and runtime.is_relative_to(root) for root in roots)


def stageRuntime(args):
    runtime = args.output.resolve()
    if not isFixturePath(runtime):
        raise ValueError("Use the ignored repository runtime folder or LOCALAPPDATA/Hill175/runtime for a disposable server.")
    runtime.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.source / "paper.jar", runtime / "paper.jar")
    copyDependencies(args.source, runtime)
    pluginFolder = runtime / "plugins/Hill175"
    pluginFolder.mkdir(parents=True)
    shutil.copy2(args.plugin, runtime / "plugins/Hill175.jar")
    campusPack = repository / "build/bedrock-ui/hill-campus-ui.mcpack"
    if campusPack.is_file():
        packFolder = runtime / "plugins/Geyser-Spigot/packs"
        packFolder.mkdir(parents=True)
        shutil.copy2(campusPack, packFolder / campusPack.name)
    config = (repository / "src/main/resources/config.yml").read_text(encoding="utf-8")
    config = config.replace("port: 8788", f"port: {args.galleryPort}")
    config = config.replace("http://localhost:8788", f"http://localhost:{args.galleryPort}")
    (pluginFolder / "config.yml").write_text(config, encoding="utf-8")
    for folderName in ("hill_auth", "hill_hub", "hill_people_template"):
        source = args.campus if folderName == "hill_people_template" and args.campus else args.source / "world-templates" / folderName
        shutil.copytree(source, runtime / "world-templates" / folderName)
    shutil.copy2(repository / "server-config/spigot.yml", runtime / "spigot.yml")
    (runtime / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (runtime / "server.properties").write_text(serverProperties(args.javaPort), encoding="utf-8")
    (runtime / '.hill175-smoke-fixture').write_text('Disposable Hill175 fixture\n', encoding='utf-8')
    return runtime


def serverProperties(javaPort):
    layers = {"layers": [{"block": "minecraft:bedrock", "height": 1},
                         {"block": "minecraft:dirt", "height": 2},
                         {"block": "minecraft:grass_block", "height": 1}], "biome": "minecraft:plains"}
    return (f"server-ip=127.0.0.1\nserver-port={javaPort}\nonline-mode=false\n"
            "enforce-secure-profile=false\nallow-flight=true\nenable-rcon=false\n"
            "view-distance=3\nsimulation-distance=3\nmax-players=10\nspawn-protection=0\n"
            "level-type=minecraft:flat\ngenerate-structures=false\ngamemode=adventure\n"
            f"generator-settings={json.dumps(layers)}\n")


def writeBridgeConfig(runtime, securedConfig, shouldValidate):
    header, body = securedConfig.decode().split("\n", 1)
    config = json.loads(body)
    config["bedrock"]["address"] = "127.0.0.1"
    # Unsigned fixtures stay exclusively on loopback. NetherNet refuses a
    # loopback bind; its public signaling is verified separately with auth on.
    config["bedrock"]["transport"] = "raknet"
    config["advanced"]["bedrock"]["validate-bedrock-login"] = shouldValidate
    target = runtime / "plugins/Geyser-Spigot/config.yml"
    target.write_text(header + "\n" + json.dumps(config, indent=2) + "\n", encoding="utf-8")


def awaitServer(server, logFile, timeout=420):
    deadline = time.monotonic() + timeout
    lastUpdate = time.monotonic()
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"Isolated Paper exited during startup; inspect {logFile}")
        log = logFile.read_text(encoding="utf-8", errors="replace") if logFile.exists() else ""
        if "Started Geyser on " in log and re.search(r"Done \([0-9.]+s\)! For help", log):
            return
        if time.monotonic() - lastUpdate >= 25:
            print("Waiting for isolated Paper/Geyser startup...", flush=True)
            lastUpdate = time.monotonic()
        time.sleep(0.25)
    raise TimeoutError(f"Isolated Paper startup timed out; inspect {logFile}")


@contextmanager
def runningServer(args, runtime, phase):
    logFile = runtime / f"server-{phase}.log"
    with logFile.open("w", encoding="utf-8") as output:
        environment = {**os.environ, "HILL175_AUTH_MODE": "development"}
        server = subprocess.Popen([args.java, "-Xms256M", "-Xmx2G", "-XX:ActiveProcessorCount=4", "-jar", "paper.jar", "--nogui"],
                                  cwd=runtime, stdin=subprocess.PIPE, stdout=output,
                                  stderr=subprocess.STDOUT, text=True, env=environment,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            awaitServer(server, logFile)
            yield server
        finally:
            if server.poll() is None:
                stopServer(server)


def stopServer(server):
    try:
        server.communicate("stop\n", timeout=60)
    except subprocess.TimeoutExpired:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def fixtureCommand(request):
    nickname = request.get("nickname", "")
    if not re.fullmatch(r"\.Bed[0-9]{9}", nickname):
        raise ValueError("Unexpected Bedrock fixture nickname.")
    if request.get("action") == "give-stone":
        return f"minecraft:item replace entity {nickname} hotbar.2 with minecraft:stone 64"
    if request.get("action") == "exterior-view":
        return f"minecraft:execute as {nickname} at @s run minecraft:tp @s ~70 ~12 ~ -90 10"
    if request.get("action") != "query-block":
        raise ValueError("Unknown Bedrock fixture action.")
    position = request["position"]
    if len(position) != 3 or any(type(value) is not int or abs(value) > 30_000_000 for value in position):
        raise ValueError("Invalid fixture block coordinates.")
    expected = request["expected"]
    marker = request["marker"]
    if expected not in ("stone", "air") or not re.fullmatch(r"BEDROCK_[A-Z_]+", marker):
        raise ValueError("Invalid block assertion.")
    coordinates = " ".join(map(str, position))
    return (f"minecraft:execute as {nickname} at @s if block {coordinates} minecraft:{expected} "
            f"run minecraft:tellraw @s {json.dumps({'text': marker})}")


def runClient(args, runtime, server, phase, environment):
    print(f"Running automated Bedrock {phase}...", flush=True)
    environment = {**environment, "HILL175_BEDROCK_SMOKE_REPORT": str(runtime / f"report-{phase}.json")}
    command = [args.node, str(repository / "ops/smoke-bedrock.mjs"), phase]
    with subprocess.Popen(command, cwd=repository, env=environment, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as client:
        deadline = threading.Timer(600, client.kill)
        deadline.start()
        try:
            streamClient(client, runtime, phase, server)
        finally:
            deadline.cancel()
        if client.wait(timeout=10):
            raise RuntimeError(f"Automated Bedrock {phase} failed; evidence is in {runtime}")


def streamClient(client, runtime, phase, server):
    with (runtime / f"client-{phase}.log").open("w", encoding="utf-8") as log:
        for line in client.stdout:
            log.write(line)
            log.flush()
            relayClientLine(line, server)


def relayClientLine(line, server):
    if not line.startswith("SMOKE_FIXTURE "):
        print(line, end="", flush=True)
        return
    request = json.loads(line.removeprefix("SMOKE_FIXTURE "))
    server.stdin.write(fixtureCommand(request) + "\n")
    server.stdin.flush()


def parseArguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repository / "runtime/server")
    parser.add_argument("--campus", type=Path, help="Explicitly selected prepared campus folder for this disposable test")
    parser.add_argument("--reuse", action="store_true", help="Resume an existing disposable loopback fixture")
    parser.add_argument("--gameplay-only", action="store_true", help="Resume gameplay only after this fixture has passed secure admission")
    parser.add_argument("--plugin", type=Path, default=repository / "build/libs/Hill-server-1.0-SNAPSHOT.jar")
    parser.add_argument("--output", type=Path, default=repository / "runtime" / datetime.now().strftime("bedrock-script-%Y%m%d-%H%M%S"))
    parser.add_argument("--java", default="java")
    parser.add_argument("--node", default="node")
    parser.add_argument("--java-port", dest="javaPort", type=int, default=25568)
    parser.add_argument("--bedrock-port", dest="bedrockPort", type=int, default=19134)
    parser.add_argument("--gallery-port", dest="galleryPort", type=int, default=8789)
    return parser.parse_args()


def main():
    args = parseArguments()
    availablePort(args.javaPort, socket.SOCK_STREAM)
    availablePort(args.bedrockPort, socket.SOCK_DGRAM)
    availablePort(args.galleryPort, socket.SOCK_STREAM)
    runtime = args.output.resolve()
    if args.reuse:
        if not isFixturePath(runtime) or not any((runtime / name).is_file() for name in ('.hill175-smoke-fixture', 'server-secure.log')):
            raise ValueError('Only a previous disposable Bedrock fixture can be resumed.')
        if 'server-ip=127.0.0.1' not in (runtime / 'server.properties').read_text():
            raise ValueError('The resumed fixture must be loopback only.')
        with installer.stopped_world(runtime):
            shutil.copy2(args.plugin, runtime / 'plugins/Hill175.jar')
    else:
        runtime = stageRuntime(args)
    manifest = installer.load_manifest()
    installer.prepare(runtime, manifest, args.bedrockPort)
    installer.install(runtime, manifest, args.bedrockPort)
    configFile = runtime / "plugins/Geyser-Spigot/config.yml"
    securedConfig = configFile.read_bytes()
    environment = {**os.environ, "HILL175_BEDROCK_SMOKE_SERVER": str(runtime),
                   "HILL175_BEDROCK_SMOKE_PORT": str(args.bedrockPort),
                   "HILL175_BEDROCK_ISOLATED_OFFLINE": "1", "HILL175_BEDROCK_FIXTURES": "1",
                   "HILL175_BEDROCK_SMOKE_USERNAME": "Bed" + str(time.time_ns())[-9:],
                   "HILL175_BEDROCK_SMOKE_PASSWORD": "LocalSmoke" + uuid.uuid4().hex + "!"}
    try:
        if args.gameplay_only:
            if not (runtime / 'report-reject-offline.json').is_file():
                raise ValueError('This fixture must first pass secure admission.')
        else:
            writeBridgeConfig(runtime, securedConfig, True)
            with runningServer(args, runtime, "secure") as server:
                runClient(args, runtime, server, "reject-offline", environment)
        writeBridgeConfig(runtime, securedConfig, False)
        with runningServer(args, runtime, "gameplay") as server:
            runClient(args, runtime, server, "gameplay", environment)
        with runningServer(args, runtime, "restart") as server:
            runClient(args, runtime, server, "reconnect", environment)
    finally:
        configFile.write_bytes(securedConfig)
        installer.verify(runtime, manifest, args.bedrockPort)
    print(f"PASS: isolated server stopped; secured managed configuration restored. Evidence: {runtime}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        print(f"Bedrock smoke failed: {error}", file=sys.stderr)
        sys.exit(1)
