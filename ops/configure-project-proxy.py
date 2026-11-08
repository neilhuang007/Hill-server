"""Publish the gallery and Bedrock signaling through Cloudflare and nginx."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('auth_proxy', ROOT / 'ops/configure-auth-proxy.py')
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)
MARKER = '# Managed by Hill175 configure-project-proxy.py.\n'
TARGET = Path('/etc/nginx/conf.d/hill175-projects.conf')


def sites(values):
    auth.CONFIG.validate(values)
    result = []
    for key, port, signaling in (
        ('HILL175_GALLERY_PUBLIC_URL', 8788, False),
        ('HILL175_BEDROCK_PUBLIC_URL', int(values.get('HILL175_BEDROCK_PORT', '19132')), True),
    ):
        if key in values:
            result.append((urlsplit(values[key]).hostname.lower(), port, signaling))
    if len({site[0] for site in result}) != len(result):
        raise ValueError('Use different hostnames for gallery and Bedrock signaling')
    return result


def render(values, ranges):
    cert, key, ca = auth.certificate_paths(values)
    content = MARKER + 'geo $realip_remote_addr $hill175_project_cloudflare {\n    default 0;\n'
    content += ''.join(f'    {network} 1;\n' for network in ranges) + '}\n'
    for host, port, signaling in sites(values):
        location = '/v1/join' if signaling else '/'
        content += f'''
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {host};
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_client_certificate {ca};
    ssl_verify_client on;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log off;
    error_log /var/log/nginx/hill175-projects-error.log crit;
    client_max_body_size 64k;
    if ($host != {host}) {{ return 444; }}
    if ($ssl_server_name != {host}) {{ return 444; }}
    if ($hill175_project_cloudflare = 0) {{ return 444; }}
    location {location} {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host {host};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $http_cf_connecting_ip;
        proxy_buffering off;
        proxy_cache off;
        proxy_connect_timeout 3s;
        proxy_read_timeout 45s;
        add_header Cache-Control "no-store" always;
    }}
'''
        if signaling:
            content += '    location / { return 404; }\n'
        content += '}\n'
    return content


def configure(values, install):
    selected = sites(values)
    managed_hosts = {host for host, _, _ in selected}
    if not selected:
        if TARGET.exists():
            raise ValueError('Existing project proxy needs its public URLs preserved')
        print('Project proxy is not configured.')
        return
    if TARGET.is_symlink() or (TARGET.exists() and not TARGET.read_text().startswith(MARKER)):
        raise ValueError('Refusing to replace an unmanaged nginx site')
    for host, _, _ in selected:
        auth.validate_certificates(values | {'HILL175_AUTH_PUBLIC_URL': 'https://' + host})
    content = render(values, auth.cloudflare_ranges())
    with tempfile.TemporaryDirectory(prefix='hill175-proxy-') as directory:
        staged = Path(directory) / 'projects.conf'
        staged.write_text(content)
        probe = Path(directory) / 'nginx.conf'
        probe.write_text(f'error_log stderr crit;\nevents {{}}\nhttp {{ include "{staged}"; }}\n')
        auth.run('nginx', '-t', '-c', str(probe))
        if not install:
            return
        previous = TARGET.read_bytes() if TARGET.exists() else None
        backup = Path(tempfile.mkdtemp(prefix='hill175-project-proxy-', dir='/var/backups'))
        if previous is not None:
            (backup / TARGET.name).write_bytes(previous)
        try:
            TARGET.write_text(content)
            TARGET.chmod(0o644)
            auth.run('nginx', '-t', conflict_hosts=managed_hosts)
            auth.run('systemctl', 'reload', 'nginx.service')
        except Exception:
            if previous is None:
                TARGET.unlink(missing_ok=True)
            else:
                TARGET.write_bytes(previous)
            auth.run('nginx', '-t', conflict_hosts=managed_hosts)
            auth.run('systemctl', 'reload', 'nginx.service')
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install'])
    parser.add_argument('--env-file', type=Path, default=Path('/etc/hill175/hill175.env'))
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError('Run as root')
        configure(auth.CONFIG.read_environment(args.env_file), args.action == 'install')
        print(f'Project proxy {args.action} complete.')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Project proxy failed: {type(error).__name__}. Check URLs, certificates and nginx.\n')
