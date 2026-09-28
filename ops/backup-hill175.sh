#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HILL175_BACKUP_ENV_FILE:-/etc/minecraft-backup.env}"

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

fail() {
  log "ERROR: $*"
  exit 1
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required command: $1"
  fi
}

restart_service_if_needed() {
  [[ "${was_running}" == true ]] || return 0
  log "starting ${SERVICE_NAME}"
  if ! systemctl start "${SERVICE_NAME}"; then
    return 1
  fi
  was_running=false
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM

  if [[ "${was_running}" == true ]]; then
    if ! restart_service_if_needed; then
      log "ERROR: failed to restart ${SERVICE_NAME}"
      [[ "${status}" -ne 0 ]] || status=1
    fi
  fi

  exit "${status}"
}

[[ "${EUID}" -eq 0 ]] || fail "run as root"
require_command borg
require_command flock
require_command stat
require_command systemctl

[[ -f "${ENV_FILE}" && -r "${ENV_FILE}" ]] || fail "backup env file missing or unreadable: ${ENV_FILE}"

env_uid="$(stat -c '%u' "${ENV_FILE}")"
env_mode="$(stat -c '%a' "${ENV_FILE}")"
[[ "${env_uid}" == "0" ]] || fail "backup env file must be owned by root: ${ENV_FILE}"
(( (8#${env_mode} & 8#077) == 0 )) || fail "backup env file must not be readable by group/other: ${ENV_FILE}"

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a
: "${BORG_REPO_PATH:?BORG_REPO_PATH must be set by ${ENV_FILE}}"

# Shared Borg credentials can also contain another server's SRV_DIR or SERVICE_NAME.
# Resolve Hill's namespaced settings after sourcing so those generic values cannot
# redirect a Hill snapshot, stop another service, or change its retention policy.
SERVICE_NAME="${HILL175_SERVICE_NAME:-hill175.service}"
SRV_DIR="${HILL175_RUNTIME_DIR:-/opt/hill175}"
LOCK_FILE="${MC_BACKUP_LOCK:-/run/lock/mc-backup.lock}"
LOCK_WAIT_SECONDS="${HILL175_BACKUP_LOCK_WAIT_SECONDS:-3600}"
ARCHIVE_PREFIX="${HILL175_BACKUP_ARCHIVE_PREFIX:-hill175-daily}"
KEEP_DAILY="${HILL175_BACKUP_KEEP_DAILY:-14}"

[[ "${SRV_DIR}" == /* ]] || fail "runtime directory must be absolute: ${SRV_DIR}"
[[ -d "${SRV_DIR}" ]] || fail "runtime directory does not exist: ${SRV_DIR}"
[[ "${LOCK_WAIT_SECONDS}" =~ ^[0-9]+$ ]] || fail "lock wait must be numeric: ${LOCK_WAIT_SECONDS}"
[[ "${KEEP_DAILY}" =~ ^[0-9]+$ && "${KEEP_DAILY}" -gt 0 ]] || fail "daily retention must be a positive number: ${KEEP_DAILY}"
[[ "${ARCHIVE_PREFIX}" =~ ^[A-Za-z0-9._-]+$ ]] || fail "archive prefix contains unsupported characters: ${ARCHIVE_PREFIX}"

SRV_DIR="$(cd "${SRV_DIR}" && pwd -P)"
[[ "${SRV_DIR}" != "/" && "${SRV_DIR}" != "/opt" ]] || fail "refusing to back up broad runtime path: ${SRV_DIR}"
ARCHIVE_ROOT="${SRV_DIR#/}"

mkdir -p "$(dirname "${LOCK_FILE}")"
exec 9>"${LOCK_FILE}"
if ! flock -w "${LOCK_WAIT_SECONDS}" 9; then
  fail "timed out waiting for backup lock: ${LOCK_FILE}"
fi

was_running=false
trap cleanup EXIT INT TERM

if systemctl is-active --quiet "${SERVICE_NAME}"; then
  was_running=true
  log "stopping ${SERVICE_NAME} for cold Borg snapshot"
  systemctl stop "${SERVICE_NAME}"
else
  log "${SERVICE_NAME} is not active; backing up current disk state"
fi

archive_name="${ARCHIVE_PREFIX}-$(date -u '+%Y-%m-%dT%H-%M-%SZ')"
exclude_args=(
  --exclude "${ARCHIVE_ROOT}/logs"
  --exclude "${ARCHIVE_ROOT}/crash-reports"
  --exclude "${ARCHIVE_ROOT}/cache"
  --exclude "${ARCHIVE_ROOT}/libraries"
  --exclude "${ARCHIVE_ROOT}/versions"
  --exclude "${ARCHIVE_ROOT}/downloads"
  --exclude "${ARCHIVE_ROOT}/tmp"
  --exclude "${ARCHIVE_ROOT}/.cache"
  --exclude "${ARCHIVE_ROOT}/usercache.json"
  --exclude "${ARCHIVE_ROOT}/assets/survival-worldgen-cache"
  --exclude "${ARCHIVE_ROOT}/assets/*-cache"
  --exclude "${ARCHIVE_ROOT}/assets/downloads"
  --exclude "${ARCHIVE_ROOT}/assets/*.zip"
  --exclude "${ARCHIVE_ROOT}/assets/*.zip.tmp"
  --exclude "${ARCHIVE_ROOT}/assets/*.tmp"
  --exclude "sh:${ARCHIVE_ROOT}/**/session.lock"
)

log "creating Borg archive ${archive_name} from ${SRV_DIR}"
borg create \
  --stats \
  --one-file-system \
  "${exclude_args[@]}" \
  "${BORG_REPO_PATH}::${archive_name}" \
  "${SRV_DIR}"

restart_service_if_needed

log "pruning ${ARCHIVE_PREFIX}-* Borg archives to ${KEEP_DAILY} daily copies"
borg prune \
  --list \
  --glob-archives "${ARCHIVE_PREFIX}-*" \
  --keep-daily "${KEEP_DAILY}" \
  "${BORG_REPO_PATH}"

log "backup complete: ${archive_name}"
