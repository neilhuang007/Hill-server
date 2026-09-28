#!/usr/bin/env python3
"""Prepare/install Hill's nginx site from the protected environment; no manual nginx edits."""

import argparse
import importlib.util
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("hill_auth_config", ROOT / "ops/check-auth-config.py")
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)
MARKER = "# Managed by Hill175 configure-auth-proxy.py; change /etc/hill175/hill175.env instead.\n"
TARGET = Path("/etc/nginx/conf.d/hill175-auth.conf")


def certificate_paths(values):
    paths = [PurePosixPath(values.get(key, default)) for key, default in (
        ("HILL175_ORIGIN_CERT", "/etc/hill175/tls/origin.pem"),
        ("HILL175_ORIGIN_KEY", "/etc/hill175/tls/origin.key"),
        ("HILL175_AOP_CA", "/etc/hill175/tls/aop-ca.pem"),
    )]
    for path in paths:
        if not path.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)) or ".." in path.parts:
            raise ValueError("Certificate paths must be absolute Linux paths without spaces or nginx syntax")
    return paths


def parse_ranges(text, version):
    ranges = [ipaddress.ip_network(line.strip(), strict=True) for line in text.splitlines() if line.strip()]
    if not ranges or len(ranges) > 256 or any(r.version != version or r.prefixlen < (8 if version == 4 else 16) for r in ranges):
        raise ValueError("Cloudflare returned an invalid address range list")
    return ranges


def cloudflare_ranges():
    result = []
    for version in (4, 6):
        request = Request(f"https://www.cloudflare.com/ips-v{version}", headers={"User-Agent": "Hill175-deployment"})
        with urlopen(request, timeout=15) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("Cloudflare address response exceeded size limit")
        result.extend(parse_ranges(body.decode("ascii"), version))
    return result


def render(values, ranges):
    _, port = CONFIG.validate(values, "microsoft")
    host = urlsplit(values["HILL175_AUTH_PUBLIC_URL"]).hostname.lower()
    if len(host) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}", host):
        raise ValueError("The public auth URL must use a DNS hostname")
    cert, key, ca = certificate_paths(values)
    template = (ROOT / "ops/nginx/hill175-auth.conf.example").read_text(encoding="utf-8")
    template = template[template.index("server {"):]
    template = template.replace("auth.example.org", host).replace("127.0.0.1:8087", f"127.0.0.1:{port}")
    for old, new in (("/etc/nginx/certs/hill175-origin.pem", cert),
                     ("/etc/nginx/certs/hill175-origin.key", key),
                     ("/etc/nginx/certs/hill175-aop-ca.pem", ca)):
        template = template.replace(old, str(new))
    # realip_remote_addr retains the TCP peer even if a global real-IP rule rewrites remote_addr.
    peers = "geo $realip_remote_addr $hill175_cloudflare_peer {\n    default 0;\n"
    peers += "".join(f"    {network} 1;\n" for network in ranges)
    peers += "}\n\n"
    template = template.replace("    location / {", "    if ($hill175_cloudflare_peer = 0) { return 444; }\n\n    location / {")
    return MARKER + peers + template


def run(*args):
    result = subprocess.run(args, capture_output=True, timeout=30)
    if result.returncode:
        # nginx diagnostics may contain request information from another site; keep deployment output bounded.
        raise RuntimeError(f"{args[0]} validation/action failed; inspect the operator configuration and service logs")
    if args[0] == "nginx" and b"conflicting server name" in result.stderr:
        raise RuntimeError("Another nginx site already uses the authentication hostname")
    return result.stdout


def validate_certificates(values):
    cert, key, ca = map(Path, certificate_paths(values))
    for path in (cert, key, ca):
        if not path.is_file():
            raise ValueError("Place the Origin certificate, private key and AOP CA at the configured paths first")
    if key.stat().st_uid != 0 or key.stat().st_mode & 0o077:
        raise ValueError("Origin private key must be root-owned with mode 0600")
    host = urlsplit(values["HILL175_AUTH_PUBLIC_URL"]).hostname
    # OpenSSL handles -checkend as an early exit; run hostname validation separately.
    match = run("openssl", "x509", "-in", str(cert), "-noout", "-checkhost", host)
    if b"does match certificate" not in match:
        raise ValueError("Origin certificate does not cover the authentication hostname")
    run("openssl", "x509", "-in", str(cert), "-noout", "-checkend", "86400")
    run("openssl", "x509", "-in", str(ca), "-noout", "-checkend", "86400")
    public_cert = run("openssl", "x509", "-in", str(cert), "-pubkey", "-noout")
    public_key = run("openssl", "pkey", "-in", str(key), "-passin", "pass:", "-pubout")
    if public_cert.strip() != public_key.strip():
        raise ValueError("The Origin certificate and private key do not match")


def require_managed(path):
    if path.is_symlink() or (path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER)):
        raise ValueError("Existing Hill nginx site is not managed by this tool; preserve and review it before adoption")


def prepare(values, stage):
    require_managed(TARGET)
    validate_certificates(values)
    content = render(values, cloudflare_ranges())
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / "hill175-auth.conf"
    staged.write_text(content, encoding="utf-8")
    probe = stage / "nginx-probe.conf"
    probe.write_text(f'error_log stderr crit;\nevents {{}}\nhttp {{ include "{staged}"; }}\n', encoding="utf-8")
    run("nginx", "-t", "-c", str(probe))
    return staged


def validate_prepared(values, staged):
    content = staged.read_text(encoding="utf-8")
    peers = content.split("}\n", 1)[0]
    networks = re.findall(r"^    ([0-9a-fA-F:./]+) 1;$", peers, re.MULTILINE)
    ranges = [ipaddress.ip_network(network, strict=True) for network in networks]
    for version in (4, 6):
        parse_ranges("\n".join(str(network) for network in ranges if network.version == version), version)
    if content != render(values, ranges):
        raise ValueError("Prepared nginx configuration differs from the environment; run prepare again")
    validate_certificates(values)


def install_site(staged, target=TARGET):
    require_managed(target)
    content = staged.read_bytes()
    if not content.startswith(MARKER.encode()):
        raise ValueError("Prepared nginx configuration is not managed")
    previous = target.read_bytes() if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    if previous == content:
        run("nginx", "-t")
        run("systemctl", "reload-or-restart", "nginx.service")
        return
    backup = Path(tempfile.mkdtemp(prefix="previous-site-", dir=staged.parent))
    if previous is not None:
        (backup / "hill175-auth.conf").write_bytes(previous)
    temporary = target.with_suffix(".conf.tmp")
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o644)
        os.replace(temporary, target)
        run("nginx", "-t")
        run("systemctl", "reload-or-restart", "nginx.service")
    except Exception:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            temporary.write_bytes(previous)
            os.replace(temporary, target)
        # Restore the last on-disk configuration even when a service action fails.
        # A successful validation followed by failed reload may have changed service state.
        try:
            run("nginx", "-t")
            run("systemctl", "reload-or-restart", "nginx.service")
        except (OSError, RuntimeError, subprocess.SubprocessError):
            pass
        raise
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "install"])
    parser.add_argument("--env-file", type=Path, default=Path("/etc/hill175/hill175.env"))
    parser.add_argument("--stage", type=Path, default=Path("/var/lib/hill175-deploy/auth-proxy"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root")
    try:
        values = CONFIG.read_environment(args.env_file)
        CONFIG.validate(values, "microsoft")
        stage = args.stage.resolve()
        if args.action == "prepare":
            prepare(values, stage)
        else:
            validate_prepared(values, stage / "hill175-auth.conf")
            install_site(stage / "hill175-auth.conf")
        print(f"Hill authentication proxy {args.action} complete.")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Authentication proxy {args.action} failed: {error.__class__.__name__}. Check certificate paths/permissions, hostname, Cloudflare connectivity and nginx configuration.\n")


if __name__ == "__main__":
    main()
