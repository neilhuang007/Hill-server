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
    "HILL175_AUTH_PUBLIC_URL", "HILL175_AUTH_PORT", "HILL175_MAX_LINKED_ACCOUNTS",
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
    role = values.get("HILL175_ENTRA_REQUIRED_ROLE", "Hill175.Student")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", role):
        raise ValueError("HILL175_ENTRA_REQUIRED_ROLE must be a nonempty app role value")
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
    parser.add_argument("--print", dest="field", choices=["mode", "port"])
    args = parser.parse_args()
    try:
        mode, port = validate(read_environment(args.file), args.expect_mode)
    except (OSError, UnicodeError, ValueError):
        # Error values can contain credentials (including malformed URLs); never print them.
        print("Authentication environment invalid. Check required keys, format, mode, and file permissions against .env.example.", file=sys.stderr)
        return 1
    print({"mode": mode, "port": port}[args.field] if args.field else f"Authentication environment valid ({mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
