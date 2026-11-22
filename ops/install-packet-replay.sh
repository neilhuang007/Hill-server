#!/usr/bin/env bash
# Prepare while server runs; install only after caller stops the service.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/packet-replay-install.py" "$@"
