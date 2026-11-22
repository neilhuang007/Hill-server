#!/usr/bin/env python3
"""Validate the deployment environment without executing or printing credentials."""

import argparse
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit
from uuid import UUID


ASSIGNMENT = re.compile(r"([A-Z][A-Z0-9_]*)=(?:'([^'\\\r\n]*)'|\"([^\"\\\r\n]*)\"|([^\s'\"\\]+))")
SUPPORTED = {
    "HILL175_AUTH_MODE", "HILL175_ENTRA_TENANT_ID", "HILL175_ENTRA_CLIENT_ID",
    "HILL175_ENTRA_CLIENT_SECRET", "HILL175_ENTRA_REQUIRED_ROLE",
    "HILL175_ENTRA_STAFF_ROLE", "HILL175_ENTRA_MODERATOR_ROLE", "HILL175_ENTRA_ADMINISTRATOR_ROLE",
    "HILL175_AUTH_PUBLIC_URL", "HILL175_AUTH_PORT", "HILL175_MAX_LINKED_ACCOUNTS",
    "HILL175_ORIGIN_CERT", "HILL175_ORIGIN_KEY", "HILL175_AOP_CA",
    "HILL175_BEDROCK_ENABLED", "HILL175_BEDROCK_PORT",
    "HILL175_GALLERY_PUBLIC_URL", "HILL175_BEDROCK_PUBLIC_URL",
    "HILL175_NGINX_PROXY_PROTOCOL_PORT",
    "HILL175_ADMIN_UNLOCK_SHA256", "HILL175_PACKET_REPLAY_ENABLED",
    "HILL175_STUDENT_DOWNLOAD_EXPORT", "HILL175_STUDENT_DOWNLOAD_URL", "HILL175_STUDENT_DOWNLOAD_PORT",
    "HILL175_SURVIVAL_MODE", "HILL175_SURVIVAL_JAVA_HOST", "HILL175_SURVIVAL_JAVA_PORT",
    "HILL175_SURVIVAL_DESTINATION_ACCESS_CONFIGURED", "HILL175_SURVIVAL_BEDROCK_LOCAL",
}


def read_environment(path: Path, check_permissions: bool = True) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Environment file must be an existing regular file, not a symlink")
    metadata = path.stat()
    if check_permissions and os.name == "posix":
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("Environment file must be owned by root with mode 0600")
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = ASSIGNMENT.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported environment syntax on line {number}; use KEY='value'")
        key = match[1]
        if key not in SUPPORTED or key in values:
            raise ValueError(f"Unknown or repeated environment key on line {number}")
        values[key] = next(value for value in match.groups()[1:] if value is not None)
    return values


def validate(values: dict[str, str], expected_mode: str | None = None) -> tuple[str, int]:
    mode = values.get("HILL175_AUTH_MODE", "")
    if mode not in {"development", "microsoft"}:
        raise ValueError("HILL175_AUTH_MODE must explicitly be development or microsoft")
    if expected_mode and mode != expected_mode:
        raise ValueError("Installer mode differs from the environment file; no settings were changed")
    if "HILL175_ADMIN_UNLOCK_SHA256" in values and not re.fullmatch(r"[a-fA-F0-9]{64}", values["HILL175_ADMIN_UNLOCK_SHA256"]):
        raise ValueError("Invalid administrator bootstrap digest")
    if values.get("HILL175_PACKET_REPLAY_ENABLED", "false") not in {"true", "false"}:
        raise ValueError("HILL175_PACKET_REPLAY_ENABLED must be true or false")
    if values.get("HILL175_BEDROCK_ENABLED", "true") not in {"true", "false"}:
        raise ValueError("HILL175_BEDROCK_ENABLED must be true or false")
    if not 1024 <= int(values.get("HILL175_BEDROCK_PORT", "19132")) <= 65534:
        raise ValueError("HILL175_BEDROCK_PORT must be between 1024 and 65534")
    if "HILL175_NGINX_PROXY_PROTOCOL_PORT" in values:
        if not 1024 <= int(values["HILL175_NGINX_PROXY_PROTOCOL_PORT"]) <= 65535:
            raise ValueError("HILL175_NGINX_PROXY_PROTOCOL_PORT must be between 1024 and 65535")
    for key in ("HILL175_GALLERY_PUBLIC_URL", "HILL175_BEDROCK_PUBLIC_URL"):
        if key not in values:
            continue
        url = urlsplit(values[key])
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.port not in (None, 443) or url.path not in ("", "/") or url.query or url.fragment
                or not re.fullmatch(r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z][a-zA-Z0-9-]{0,62}", url.hostname)):
            raise ValueError(f"{key} must be an HTTPS origin on port 443 with a DNS hostname")
    survival_mode = values.get("HILL175_SURVIVAL_MODE", "local")
    if survival_mode not in {"local", "transfer", "disabled"}:
        raise ValueError("Invalid survival routing mode")
    for key in ("HILL175_SURVIVAL_DESTINATION_ACCESS_CONFIGURED", "HILL175_SURVIVAL_BEDROCK_LOCAL"):
        if key in values and values[key] not in {"true", "false"}:
            raise ValueError("Survival routing flags must be true or false")
    if not 1 <= int(values.get("HILL175_SURVIVAL_JAVA_PORT", "25567")) <= 65535:
        raise ValueError("Invalid survival destination port")
    if survival_mode == "transfer":
        if (mode != "microsoft" or values.get("HILL175_SURVIVAL_DESTINATION_ACCESS_CONFIGURED") != "true"
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", values.get("HILL175_SURVIVAL_JAVA_HOST", ""))):
            raise ValueError("Transfer requires online Microsoft mode, a hostname and confirmed destination admission")
    download_keys = {key for key in values if key.startswith("HILL175_STUDENT_DOWNLOAD_")}
    if download_keys:
        export = values.get("HILL175_STUDENT_DOWNLOAD_EXPORT", "")
        download = urlsplit(values.get("HILL175_STUDENT_DOWNLOAD_URL", ""))
        gallery = urlsplit(values.get("HILL175_GALLERY_PUBLIC_URL", ""))
        if (not export.startswith("/") or ".." in Path(export).parts
                or download.scheme != "https" or not gallery.hostname
                or download.netloc != gallery.netloc or download.username or download.password
                or download.path != "/student-map/" or download.query or download.fragment):
            raise ValueError("Student downloads require an absolute export and the gallery HTTPS origin with /student-map/ path")
        download_port = int(values.get("HILL175_STUDENT_DOWNLOAD_PORT", "8791"))
        reserved_ports = {8788, int(values.get("HILL175_AUTH_PORT", "8087")),
                          int(values.get("HILL175_BEDROCK_PORT", "19132"))}
        if not 1024 <= download_port <= 65535 or download_port in reserved_ports:
            raise ValueError("Student download port must be an unused unprivileged loopback port")
    if mode == "development":
        return mode, 8087
    for key in ("HILL175_ENTRA_TENANT_ID", "HILL175_ENTRA_CLIENT_ID"):
        value = values.get(key, "")
        try:
            parsed = UUID(value)
        except ValueError:
            raise ValueError(f"{key} must be a GUID") from None
        if str(parsed) != value.lower() or parsed.int == 0:
            raise ValueError(f"{key} must be a nonzero canonical GUID")
    secret = values.get("HILL175_ENTRA_CLIENT_SECRET", "")
    if not secret.strip() or secret.startswith("replace-with-"):
        raise ValueError("HILL175_ENTRA_CLIENT_SECRET must contain the client secret value")
    roles = [values.get(key, default) for key, default in (
        ("HILL175_ENTRA_REQUIRED_ROLE", "Hill175.Student"),
        ("HILL175_ENTRA_STAFF_ROLE", "Hill175.Staff"),
        ("HILL175_ENTRA_MODERATOR_ROLE", "Hill175.Moderator"),
        ("HILL175_ENTRA_ADMINISTRATOR_ROLE", "Hill175.Administrator"),
    )]
    if any(not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", role) for role in roles) or len(set(roles)) != 4:
        raise ValueError("Microsoft app role values must be valid and distinct")
    url = urlsplit(values.get("HILL175_AUTH_PUBLIC_URL", ""))
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.path not in {"", "/"} or url.query or url.fragment):
        raise ValueError("HILL175_AUTH_PUBLIC_URL must be an HTTPS origin without a path")
    try:
        port = int(values.get("HILL175_AUTH_PORT", "8087"))
        cap = int(values.get("HILL175_MAX_LINKED_ACCOUNTS", "4"))
        if url.port not in {None, 443}:
            raise ValueError()
    except ValueError:
        raise ValueError("Invalid authentication port, account cap, or public URL port") from None
    if not 1024 <= port <= 65535:
        raise ValueError("HILL175_AUTH_PORT must be between 1024 and 65535")
    if not 2 <= cap <= 20:
        raise ValueError("HILL175_MAX_LINKED_ACCOUNTS must be between 2 and 20")
    return mode, port


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("/etc/hill175/hill175.env"))
    parser.add_argument("--expect-mode", choices=["development", "microsoft"])
    parser.add_argument("--print", dest="field", choices=["mode", "port", "bedrock-enabled", "bedrock-port", "packet-replay-enabled"])
    args = parser.parse_args()
    try:
        values = read_environment(args.file)
        mode, port = validate(values, args.expect_mode)
        if "HILL175_STUDENT_DOWNLOAD_EXPORT" in values:
            export = Path(values["HILL175_STUDENT_DOWNLOAD_EXPORT"])
            level = export / "level.dat"
            if export.is_symlink() or not export.is_dir() or level.is_symlink() or not level.is_file():
                raise ValueError("Prepared student export must exist and contain a regular level.dat before deployment")
    except (OSError, UnicodeError, ValueError):
        # Error values can contain credentials (including malformed URLs); never print them.
        print("Authentication environment invalid. Check required keys, format, mode, and file permissions against .env.example.", file=sys.stderr)
        return 1
    fields = {"mode": mode, "port": port,
              "bedrock-enabled": values.get("HILL175_BEDROCK_ENABLED", "true" if mode == "microsoft" else "false"),
              "bedrock-port": values.get("HILL175_BEDROCK_PORT", "19132"),
              "packet-replay-enabled": values.get("HILL175_PACKET_REPLAY_ENABLED", "false")}
    print(fields[args.field] if args.field else f"Authentication environment valid ({mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
