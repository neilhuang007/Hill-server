"""Run a prepared campus photo server and its resource pack on loopback only."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'status'))
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--java', type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    config = json.loads((runtime / 'photo-server.json').read_text())
    state_file = runtime / 'status.json'
    stop_file = runtime / 'stop.request'
    if args.action == 'status':
        print(state_file.read_text() if state_file.exists() else 'Not started.')
        return
    if args.action == 'stop':
        stop_file.touch()
        print('Graceful stop requested.')
        return
    if not args.java or not args.java.is_file():
        parser.error('Supply the Java executable with --java.')
    if state_file.exists():
        previous = json.loads(state_file.read_text())
        if previous.get('state') in ('starting', 'ready'):
            raise ValueError('This runtime may already be running. Inspect its saved PID before restarting.')
    stop_file.unlink(missing_ok=True)
    pack = runtime / 'campus-resources.zip'

    class PackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/campus-resources.zip':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Length', str(pack.stat().st_size))
            self.end_headers()
            with pack.open('rb') as stream:
                while block := stream.read(65536):
                    self.wfile.write(block)

        def log_message(self, *arguments):
            pass

    web = ThreadingHTTPServer(('127.0.0.1', config['pack_port']), PackHandler)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    state = {'state': 'starting', 'campus': config['campus'], 'version': config['version'],
             'address': f"127.0.0.1:{config['port']}", 'runtime': str(runtime)}

    def save_state():
        state['updated_utc'] = datetime.now(timezone.utc).isoformat()
        temporary = state_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(state_file)

    server = subprocess.Popen([str(args.java.resolve()), '-Xms1G', '-Xmx4G', '-XX:ActiveProcessorCount=6',
                               '-jar', 'server.jar', '--nogui'], cwd=runtime,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace', bufsize=1)
    state['pid'] = server.pid
    save_state()
    lock = threading.Lock()

    def command(text):
        with lock:
            if server.poll() is None:
                server.stdin.write(text + '\n')
                server.stdin.flush()

    def read_console():
        with (runtime / 'console.log').open('a', encoding='utf-8', buffering=1) as log:
            for line in server.stdout:
                log.write(line)
                if 'Done (' in line:
                    for text in ('time set 6000', 'weather clear', 'gamerule minecraft:advance_time false',
                                 'gamerule minecraft:advance_weather false', 'gamerule minecraft:random_tick_speed 0',
                                 'gamerule minecraft:fire_spread_radius_around_player 0', 'gamerule minecraft:spawn_mobs false',
                                 'gamerule minecraft:respawn_radius 0', 'setworldspawn 137 85 24'):
                        command(text)
                    state['state'] = 'ready'
                    save_state()
                joined = re.search(r': ([A-Za-z0-9_]{1,16}) joined the game', line)
                if joined:
                    # This isolated server accepts connections only from the operator's own machine.
                    player = joined.group(1)
                    command(f'op {player}')
                    command(f'gamemode creative {player}')
                    command(f'tp {player} 136.6 85 24 17 -9')

    reader = threading.Thread(target=read_console, daemon=True)
    reader.start()
    try:
        while server.poll() is None and not stop_file.exists():
            time.sleep(0.5)
        if server.poll() is None:
            command('stop')
            server.wait(timeout=120)
        reader.join(timeout=5)
        state['state'] = 'stopped' if server.returncode == 0 else 'failed'
        state['exit_code'] = server.returncode
        save_state()
    finally:
        if server.poll() is None:
            command('stop')
        web.shutdown()
        web.server_close()


if __name__ == '__main__':
    main()
