#!/usr/bin/env bash
set -euo pipefail

[[ "$#" -eq 0 ]] || { echo "Usage: bash ops/enable-auto-update.sh" >&2; exit 2; }
[[ "${EUID}" -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "${REPO_DIR}" == /opt/Hill-server ]] || {
  echo "Install the production checkout at /opt/Hill-server first." >&2; exit 1;
}
source "${REPO_DIR}/ops/deployment-lock.sh"
# Checks clean main, correct GitHub origin, deployment record and noninteractive access.
bash "${REPO_DIR}/ops/update-server.sh" --check
python3 "${REPO_DIR}/ops/check-auth-config.py"
systemctl is-active --quiet hill175.service || {
  echo "Complete a successful initial deployment before enabling updates." >&2; exit 1;
}
[[ "$(cat /var/lib/hill175-update/deployed-commit)" == "$(git -C "${REPO_DIR}" rev-parse HEAD)" ]] || {
  echo "Run the installer for the current checkout before enabling updates." >&2; exit 1;
}
install -m 0644 -o root -g root "${REPO_DIR}/ops/systemd/hill175-update.service" /etc/systemd/system/
install -m 0644 -o root -g root "${REPO_DIR}/ops/systemd/hill175-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hill175-update.timer
systemctl list-timers hill175-update.timer --no-pager
echo "Automatic updates enabled for 04:00 in the server's timezone."
