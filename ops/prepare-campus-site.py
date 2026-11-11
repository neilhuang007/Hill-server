"""Prepare a private local campus website from the explicitly selected source world.

Run with uv run --python 3.13 --with nbtlib python ops/prepare-campus-site.py.
World files, rendered tiles and artwork remain in ignored runtime storage.
"""
import argparse
from array import array
import gzip
import hashlib
import io
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
OPENING_LOCATION = 'campus:124:105:178:0:0.35:1.57:0:0:free'
OPENING_DETAIL_DISTANCE = 256


def opening_visible(bounds, start, aspect=21 / 9):
    """Conservative opening camera test for the optional landing page cache."""
    if float(start[7]) != 0 or float(start[8]) != 0:
        return True
    x, y, z, distance, rotation, angle = map(float, start[1:7])
    sr, cr, sa, ca = math.sin(rotation), math.cos(rotation), math.sin(angle), math.cos(angle)
    forward, right, up = (sr * sa, -ca, -cr * sa), (cr, 0, sr), (sr * ca, sa, -cr * ca)
    origin = [v - d * distance for v, d in zip((x, y, z), forward)]
    tangent = math.tan(math.radians(75 / 2))
    corners = []
    for bx in (bounds[0] - 1, bounds[3] + 1):
        for by in (bounds[1] - 1, bounds[4] + 1):
            for bz in (bounds[2] - 1, bounds[5] + 1):
                delta = [v - o for v, o in zip((bx, by, bz), origin)]
                depth, horizontal, vertical = [sum(a * b for a, b in zip(delta, axis)) for axis in (forward, right, up)]
                corners.append((depth, depth * tangent * aspect - horizontal, depth * tangent * aspect + horizontal,
                                depth * tangent - vertical, depth * tangent + vertical))
    return not any(all(corner[plane] < 0 for corner in corners) for plane in range(5))


def mesh_bounds(path):
    """Read position bounds from BlueMap 5.23 PRBM without changing geometry."""
    raw = gzip.decompress(path.read_bytes())
    if raw[0] != 1:
        raise ValueError(f'Unsupported PRBM version in {path}')
    big_endian = bool(raw[1] & 32)
    count = int.from_bytes(raw[2:5], 'big' if big_endian else 'little')
    widths = {1: 4, 3: 1, 4: 2, 6: 4, 7: 1, 8: 2, 10: 4}
    position = 8
    for _ in range(raw[1] & 31):
        end = raw.index(0, position)
        name = raw[position:end].decode('ascii')
        flags = raw[end + 1]
        cardinality = ((flags >> 4) & 3) + 1
        encoding = flags & 15
        position = (end + 5) // 4 * 4
        length = widths[encoding] * cardinality * count
        if name == 'position':
            if encoding != 1 or cardinality != 3:
                raise ValueError(f'Unsupported PRBM positions in {path}')
            if not count:
                return [0, 0, 0, 0, 0, 0]
            values = array('f', raw[position:position + length])
            if big_endian != (sys.byteorder == 'big'):
                values.byteswap()
            axes = [values[axis::3] for axis in range(3)]
            return [min(axis) for axis in axes] + [max(axis) for axis in axes]
        position += length
    raise ValueError(f'Missing PRBM positions in {path}')


def write_preload_manifest(web):
    """Warm a small first-view cache from the complete server-rendered export."""
    app_settings_path = web / 'settings.json'
    app_settings = json.loads(app_settings_path.read_text())
    map_id = app_settings['maps'][0]
    map_root = web / 'maps' / map_id
    if not (map_root / 'settings.json').is_file():
        raise ValueError('Render the campus before preparing its preload list.')
    settings = json.loads((map_root / 'settings.json').read_text())
    app_settings['startLocation'] = map_id + ':' + OPENING_LOCATION.split(':', 1)[1]
    app_settings['hiresSliderDefault'] = OPENING_DETAIL_DISTANCE
    app_settings_path.write_text(json.dumps(app_settings) + '\n', encoding='utf-8')
    start = app_settings['startLocation'].split(':')
    center_x, center_z = float(start[1]), float(start[3])
    tile_x, tile_z = settings['hires']['tileSize']
    translate_x, translate_z = settings['hires']['translate']
    scale_x, scale_z = settings['hires']['scale']
    initial = [web / 'index.html', web / 'settings.json', map_root / 'settings.json',
               map_root / 'textures.json.gz']
    initial += sorted(p for p in (web / 'assets').iterdir() if p.suffix in {'.js', '.css', '.ttf'})
    tiles = []
    coordinates = []
    bounds_cache_path = web.parent / 'bluemap/tile-bounds.json'
    bounds_cache = json.loads(bounds_cache_path.read_text()) if bounds_cache_path.exists() else {}
    tile_root = map_root / 'tiles/0'
    for path in tile_root.rglob('*.prbm.gz'):
        match = re.fullmatch(r'x(-?\d+)z(-?\d+)\.prbm\.gz', path.relative_to(tile_root).as_posix().replace('/', ''))
        if not match:
            continue
        x, z = map(int, match.groups())
        metadata = path.stat()
        key = path.relative_to(tile_root).as_posix()
        stamp = [metadata.st_size, metadata.st_mtime_ns]
        cached = bounds_cache.get(key)
        if not cached or cached['stamp'] != stamp:
            cached = {'stamp': stamp, 'bounds': mesh_bounds(path)}
            bounds_cache[key] = cached
        bounds = list(cached['bounds'])
        if bounds[:3] == bounds[3:]:
            continue
        for index in (0, 3):
            bounds[index] = bounds[index] * scale_x + x * tile_x + translate_x
        for index in (2, 5):
            bounds[index] = bounds[index] * scale_z + z * tile_z + translate_z
        coordinates.append([x, z, bounds, metadata.st_size])
        distance = (x * tile_x + translate_x + tile_x * scale_x / 2 - center_x) ** 2
        distance += (z * tile_z + translate_z + tile_z * scale_z / 2 - center_z) ** 2
        if distance <= OPENING_DETAIL_DISTANCE ** 2 and opening_visible(bounds, start):
            tiles.append((distance, path))
    # Readiness requires the real meshes, not just completion of network requests.
    (web / 'ready.json').write_text(json.dumps({
        'map': map_id, 'center': [center_x, center_z],
        'detailDistance': OPENING_DETAIL_DISTANCE, 'tiles': sorted(coordinates),
    }) + '\n', encoding='utf-8')
    bounds_cache_path.write_text(json.dumps(bounds_cache), encoding='utf-8')
    candidates = initial + [path for _, path in sorted(tiles)]
    paths, sizes, total_bytes = [], [], 0
    # Idle loading uses the first 8 MiB. Intent to visit raises the cap to 32 MiB.
    for path in candidates:
        size = path.stat().st_size
        if total_bytes + size > 32 * 1024 * 1024 or len(paths) >= 512:
            break
        paths.append('/map/' + path.relative_to(web).as_posix())
        sizes.append(size)
        total_bytes += size
    (web / 'preload.json').write_text(json.dumps({'paths': paths, 'sizes': sizes, 'bytes': total_bytes}) + '\n', encoding='utf-8')
    print(f'Opening view preload: {len(paths)} files, {total_bytes / 1024 / 1024:.1f} MiB', flush=True)


def normalize_render_states(snapshot, output):
    """Make vanilla defaults explicit for BlueMap, without changing chosen block states."""
    import nbtlib
    report = ROOT / 'runtime/smoke-bot/mineflayer/vendor/minecraft-data/pc/26.2/blocks.json'
    report_hash = hashlib.sha256(report.read_bytes()).hexdigest()
    marker = output / 'normalization.json'
    if marker.exists() and json.loads(marker.read_text()).get('defaults_sha256') == report_hash:
        return 0
    defaults = {}
    for block in json.loads(report.read_text()):
        index = block['defaultState'] - block['minStateId']
        properties = {}
        for state in reversed(block.get('states', [])):
            value = index % state['num_values']
            index //= state['num_values']
            values = ['true', 'false'] if state['type'] == 'bool' else state.get('values')
            if values is None:
                raise ValueError(f'No property values for {block["name"]}.{state["name"]}')
            properties[state['name']] = str(values[value])
        defaults['minecraft:' + block['name']] = properties
    changed_chunks = 0
    for region in sorted((snapshot / 'region').glob('*.mca')):
        raw = region.read_bytes()
        header = bytearray(raw[:8192])
        payload = bytearray()
        dirty = False
        for chunk in range(1024):
            location = int.from_bytes(raw[chunk * 4:chunk * 4 + 4], 'big')
            if not location:
                continue
            start = (location >> 8) * 4096
            length = int.from_bytes(raw[start:start + 4], 'big')
            compression = raw[start + 4]
            if compression != 2:
                raise ValueError('Expected zlib compressed chunks in the exported campus.')
            original = raw[start + 5:start + 4 + length]
            nbt = nbtlib.File.parse(io.BytesIO(zlib.decompress(original)))
            changed = False
            for section in nbt.get('sections', []):
                for state in section.get('block_states', {}).get('palette', []):
                    for key, value in defaults.get(str(state['Name']), {}).items():
                        if 'Properties' not in state:
                            state['Properties'] = nbtlib.Compound()
                        if key not in state['Properties']:
                            state['Properties'][key] = nbtlib.String(value)
                            changed = True
            if changed:
                buffer = io.BytesIO()
                nbt.write(buffer)
                original = zlib.compress(buffer.getvalue())
                changed_chunks += 1
                dirty = True
                header[4096 + chunk * 4:4100 + chunk * 4] = int(time.time()).to_bytes(4, 'big')
            encoded = (len(original) + 1).to_bytes(4, 'big') + bytes([2]) + original
            sectors = (len(encoded) + 4095) // 4096
            offset = len(payload) // 4096 + 2
            header[chunk * 4:chunk * 4 + 4] = ((offset << 8) | sectors).to_bytes(4, 'big')
            payload.extend(encoded + bytes(sectors * 4096 - len(encoded)))
        if dirty:
            temporary = region.with_suffix('.mca.tmp')
            temporary.write_bytes(header + payload)
            temporary.replace(region)
    marker.write_text(json.dumps({'defaults_sha256': report_hash, 'changed_chunks': changed_chunks,
        'purpose': 'Explicit vanilla default properties for browser rendering. Original campus is unchanged.'}, indent=2) + '\n')
    print('Prepared vanilla block defaults for the browser renderer.', flush=True)
    return changed_chunks


def prepare(output, logo, render, selection_path):
    import nbtlib
    selection = json.loads(selection_path.read_text())
    source = (ROOT / selection['workspace'] / selection['draft'] / 'world').resolve(strict=True)
    revision = selection['revision']
    if not re.fullmatch(r'[a-z0-9_-]+', revision):
        raise ValueError('The website revision must be a safe map identifier.')
    # BlueMap normalizes config names to underscores for storage identifiers.
    map_id = revision.replace('-', '_')
    pack_root = (ROOT / selection['workspace'] / selection['resource_pack']).resolve(strict=True)
    if not (pack_root / 'pack.mcmeta').is_file():
        raise ValueError('The selected campus resource pack is missing.')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'campus.json').exists():
        previous = json.loads((output / 'campus.json').read_text())
        if previous.get('revision') != revision:
            raise ValueError('This output belongs to a different campus. Use a new --output directory.')
    snapshot = output / 'snapshot' / revision
    if not snapshot.exists():
        snapshot.mkdir(parents=True)
        # Only terrain and level settings are copied. No accounts, player records or plugins.
        shutil.copytree(source / 'region', snapshot / 'region')
        level = nbtlib.load(source / 'level.dat')
        data = level['Data']
        data.pop('Player', None)
        data['LevelName'] = nbtlib.String('The Hill School | 175th Anniversary')
        data['GameType'] = nbtlib.Int(1)
        data['allowCommands'] = nbtlib.Byte(1)
        data['SpawnX'], data['SpawnY'], data['SpawnZ'] = map(nbtlib.Int, [137, 85, 24])
        level.save(snapshot / 'level.dat')
        # Package the textures explicitly selected for this campus revision.
        with zipfile.ZipFile(snapshot / 'resources.zip', 'w', zipfile.ZIP_DEFLATED) as pack:
            for path in sorted(pack_root.rglob('*')):
                if path.is_file():
                    pack.write(path, path.relative_to(pack_root).as_posix())
    normalized = normalize_render_states(snapshot, output)
    downloads = output / 'downloads'
    downloads.mkdir(exist_ok=True)
    archive = downloads / 'hill-campus.zip'
    if not archive.exists() or normalized:
        temporary = archive.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(snapshot.rglob('*')):
                if path.is_file():
                    bundle.write(path, 'Hill 175 Campus/' + path.relative_to(snapshot).as_posix())
        with zipfile.ZipFile(temporary) as bundle:
            if bundle.testzip() is not None:
                raise ValueError('World archive did not pass its integrity check.')
        temporary.replace(archive)
    assets = output / 'assets'
    assets.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'runtime/gallery-assets/minecraft.woff2', assets / 'minecraft.woff2')
    if logo:
        shutil.copy2(logo, assets / 'hill-175-gold.png')
    config = output / 'bluemap/config'
    (config / 'maps').mkdir(parents=True, exist_ok=True)
    (config / 'storages').mkdir(exist_ok=True)
    web = output / 'map'
    data_root = output / 'bluemap/data'
    path_string = lambda p: json.dumps(p.resolve().as_posix())
    (config / 'core.conf').write_text(f'accept-download: true\ndata: {path_string(data_root)}\nrender-thread-count: 8\nmetrics: false\n', encoding='utf-8')
    (config / 'webapp.conf').write_text(f'''enabled: true
webroot: {path_string(web)}
use-cookies: false
client-decompression: true
start-location: "{map_id}:{OPENING_LOCATION.split(':', 1)[1]}"
hires-slider-default: {OPENING_DETAIL_DISTANCE}
hires-slider-max: 700
''', encoding='utf-8')
    (config / 'webserver.conf').write_text(f'enabled: false\nwebroot: {path_string(web)}\nip: "127.0.0.1"\nport: 18129\n', encoding='utf-8')
    (config / 'storages/file.conf').write_text(f'storage-type: file\nroot: {path_string(web / "maps")}\ncompression: gzip\n', encoding='utf-8')
    (config / f'maps/{map_id}.conf').write_text(f'''world: {path_string(snapshot)}
dimension: "minecraft:overworld"
name: "The Hill School"
start-pos: {{ x: 137, z: 24 }}
sky-color: "#b4d4e5"
void-color: "#b4d4e5"
ambient-light: 1.0
remove-caves-below-y: -10000
ignore-missing-light-data: true
storage: "file"
''', encoding='utf-8')
    packs = config / 'resourcepacks'
    packs.mkdir(exist_ok=True)
    shutil.copy2(snapshot / 'resources.zip', packs / 'hill-asphalt.zip')
    manifest = {
        'revision': revision, 'label': selection['label'], 'edition': 'Java Edition', 'gameVersion': selection['game_version'],
        'download': '/downloads/hill-campus.zip', 'bytes': archive.stat().st_size,
        'sha256': hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(),
        'selectedOn': selection['selected_on'],
        'status': 'Campus draft', 'mapReady': False,
    }
    manifest_path = output / 'campus.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        manifest['mapReady'] = not render and previous.get('mapReady', False) and previous.get('revision') == revision
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'provenance.json').write_text(json.dumps({'source': str(source), 'selection': selection}, indent=2) + '\n', encoding='utf-8')
    if render:
        java = Path(os.environ['LOCALAPPDATA']) / 'Hill175/jdk25/bin/java.exe'
        subprocess.run([str(java), '-Xmx4G', '-jar', str(ROOT / 'runtime/tools/bluemap/bluemap-5.23-cli.jar'),
                        '-c', str(config), '-v', '1.21.11', '-g', '-s', '-r', '-f', '--markers',
                        '-l', str(output / 'bluemap/render.log')], check=True)
        if not (web / 'maps' / map_id / 'settings.json').is_file():
            raise ValueError('BlueMap did not produce the selected campus.')
        manifest['mapReady'] = True
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if manifest['mapReady']:
        write_preload_manifest(web)
    print(f'Campus site assets: {output}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/campus-site')
    parser.add_argument('--logo', type=Path)
    parser.add_argument('--selection', type=Path, default=ROOT / 'server-assets/campus-website-source.json')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--preload-only', action='store_true', help='Prepare the opening view cache from an existing map render')
    args = parser.parse_args()
    if args.preload_only:
        write_preload_manifest(args.output.resolve() / 'map')
    else:
        prepare(args.output.resolve(), args.logo, args.render, args.selection.resolve())
