"""Convert an offline world copy with pinned Chunker. Plugin and player records are not converted."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

VERSION = "1.21.0"
SHA256 = "63148e587f5ee5a2ca7ebae1079b235c82ae4d1eff8f7a8a8a3398332513dda6"
URL = f"https://github.com/HiveGamesOSS/Chunker/releases/download/{VERSION}/chunker-cli-{VERSION}.jar"


@contextmanager
def offline_world(source):
    lock = source / "session.lock" if (source / "session.lock").exists() else source / "db/LOCK"
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
            raise ValueError("This world is open in Minecraft. Use a stopped world or backup.") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.lockf(stream.fileno(), fcntl.LOCK_UN)


def convert(args):
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if not re.fullmatch(r"(?:JAVA|BEDROCK)_[0-9]+(?:_[0-9]+){1,3}", args.format):
        raise ValueError("Choose an explicit Chunker format, such as BEDROCK_1_26_60 or JAVA_26_2.")
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Choose a new output folder separate from the source world.")
    if not (source / "level.dat").is_file() or not any((source / name).is_dir() for name in ("region", "db", "dimensions/minecraft/overworld/region")):
        raise ValueError("Source needs level.dat and a Java region or Bedrock db directory.")
    cache = Path(__file__).resolve().parents[1] / f"runtime/tools/chunker/chunker-cli-{VERSION}.jar"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        data = urllib.request.urlopen(URL, timeout=90).read(150 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != SHA256: raise ValueError("Chunker download checksum mismatch.")
        cache.write_bytes(data)
    if hashlib.sha256(cache.read_bytes()).hexdigest() != SHA256: raise ValueError("Chunker cache checksum mismatch.")
    output.mkdir(parents=True)
    snapshot = output / "source-copy"
    converted = output / "world"
    with offline_world(source):
        snapshot.mkdir()
        for name in ("level.dat", "level.dat_old", "levelname.txt", "region", "entities", "poi", "data", "db", "DIM-1", "DIM1", "dimensions"):
            file = source / name
            if not file.exists(): continue
            if file.is_symlink() or file.is_dir() and any(child.is_symlink() for child in file.rglob('*')):
                raise ValueError("World snapshots must contain regular files, not links.")
            if file.is_dir(): shutil.copytree(file, snapshot / name)
            else: shutil.copy2(file, snapshot / name)
    with (output / "chunker.log").open('w', encoding='utf-8') as log:
        result = subprocess.run([args.java, '-Xmx1G', '-XX:ActiveProcessorCount=2', '-jar', str(cache), '-i', str(snapshot),
                                 '-o', str(converted), '-f', args.format], stdout=log, stderr=subprocess.STDOUT)
    required = ['db'] if args.format.startswith('BEDROCK') else ['region', 'dimensions/minecraft/overworld/region']
    success = result.returncode == 0 and (converted / 'level.dat').is_file() and any((converted / name).is_dir() for name in required)
    report = {"success": success, "converter": f"Chunker {VERSION}", "sha256": SHA256,
              "source": str(source), "format": args.format, "converted_world": str(converted),
              "scope": "World terrain and supported world content only. Hill entries, teams, submissions, accounts and Java plugins stay on Paper.",
              "review": "Inspect entities, inventories, redstone, unsupported blocks and resource packs in the destination edition before use."}
    (output / 'conversion-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not success: raise RuntimeError(f"Conversion failed. Original world is preserved. Inspect {output / 'chunker.log'}")
    print(f"Converted world: {converted}. Original and source snapshot are preserved.", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--format', required=True)
    parser.add_argument('--java', default='java')
    convert(parser.parse_args())
