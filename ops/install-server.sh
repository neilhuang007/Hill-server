#!/usr/bin/env bash
set -euo pipefail

# Choose a mode explicitly, before downloading anything or stopping the service.
case "${1:-}" in
  --help|-h)
    echo "Usage: bash ops/install-server.sh --microsoft | --allow-development-auth"
    echo "Microsoft mode requires /etc/hill175/hill175.env; see .env.example."
    exit 0
    ;;
  --allow-development-auth)
    [[ "$#" -eq 1 ]] || { echo "Unexpected installer arguments." >&2; exit 2; }
    AUTH_MODE=development
    ;;
  --microsoft)
    [[ "$#" -eq 1 ]] || { echo "Unexpected installer arguments." >&2; exit 2; }
    AUTH_MODE=microsoft
    ;;
  *)
    echo "Select --microsoft or --allow-development-auth explicitly." >&2
    exit 2
    ;;
esac

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_DIR}/ops/deployment-lock.sh"
source "${REPO_DIR}/ops/load-server-binaries.sh"
load_server_binaries "${REPO_DIR}/server-assets/server-binaries.env"
AUTH_ENV_FILE=/etc/hill175/hill175.env
command -v python3 >/dev/null || { echo "Install python3 before running this installer." >&2; exit 1; }
if [[ "${AUTH_MODE}" == development && ! -e "${AUTH_ENV_FILE}" && ! -L "${AUTH_ENV_FILE}" ]]; then
  install -d -m 0700 -o root -g root /etc/hill175
  (umask 077; printf 'HILL175_AUTH_MODE=development\n' > "${AUTH_ENV_FILE}")
fi
python3 "${REPO_DIR}/ops/check-auth-config.py" --file "${AUTH_ENV_FILE}" --expect-mode "${AUTH_MODE}"
RUNTIME_DIR="/opt/hill175"
JAVA_HOME="/opt/java25"
SERVICE_USER="hill175"
SERVICE_NAME="hill175.service"
# Paper's first start on a new or slow host can take longer than the default.
STARTUP_WAIT_SECONDS="${HILL175_STARTUP_WAIT_SECONDS:-180}"
[[ "${STARTUP_WAIT_SECONDS}" =~ ^[1-9][0-9]{1,3}$ ]] || {
  echo "HILL175_STARTUP_WAIT_SECONDS must be a whole number of seconds from 10 to 9999." >&2
  exit 2
}
service_was_active=false
service_was_stopped=false
runtime_files_committed=false
runtime_rollback_dir=""
worldgen_transition_created=false
startup_rollback_failed=false
primary_transition_marker_existed=false
paper_start_attempted=false
replaced_worlds_before=""
BEDROCK_ENABLED="$(python3 "${REPO_DIR}/ops/check-auth-config.py" --file "${AUTH_ENV_FILE}" --print bedrock-enabled)"
BEDROCK_PORT="$(python3 "${REPO_DIR}/ops/check-auth-config.py" --file "${AUTH_ENV_FILE}" --print bedrock-port)"
bedrock_paths=()
if [[ "${BEDROCK_ENABLED}" == true ]]; then
  bedrock_file_list="$(python3 "${REPO_DIR}/ops/install-bedrock.py" files)"
  mapfile -t bedrock_paths <<< "${bedrock_file_list}"
elif [[ -f "${RUNTIME_DIR}/assets/bedrock-managed.json" ]]; then
  echo "Bedrock is already installed. Preserve/review its runtime files before disabling transport." >&2
  exit 1
fi
if [[ "${AUTH_MODE}" == microsoft ]]; then
  python3 "${REPO_DIR}/ops/configure-auth-proxy.py" prepare --env-file "${AUTH_ENV_FILE}"
fi

backup_runtime_file() {
  local target="$1"
  local label="$2"
  if [[ -e "${target}" ]]; then
    cp -a "${target}" "${runtime_rollback_dir}/${label}"
  else
    touch "${runtime_rollback_dir}/${label}.absent"
  fi
}

restore_runtime_file() {
  local target="$1"
  local label="$2"
  if [[ -e "${runtime_rollback_dir}/${label}" ]]; then
    install -d "$(dirname "${target}")"
    cp -a "${runtime_rollback_dir}/${label}" "${target}"
  elif [[ -f "${runtime_rollback_dir}/${label}.absent" ]]; then
    rm -f -- "${target}"
  fi
}

restore_runtime_files() {
  local index
  restore_runtime_file "${RUNTIME_DIR}/paper.jar" paper.jar
  restore_runtime_file "${RUNTIME_DIR}/plugins/Hill175.jar" plugin.jar
  restore_runtime_file "${RUNTIME_DIR}/plugins/Hill175/config.yml" plugin-config.yml
  restore_runtime_file "${RUNTIME_DIR}/server.properties" server.properties
  restore_runtime_file "${RUNTIME_DIR}/spigot.yml" spigot.yml
  restore_runtime_file "${RUNTIME_DIR}/plugins/${CHUNKY_FILENAME}" chunky.jar
  restore_runtime_file "${RUNTIME_DIR}/plugins/Chunky/config.yml" chunky-config.yml
  restore_runtime_file "${RUNTIME_DIR}/eula.txt" eula.txt
  restore_runtime_file "${RUNTIME_DIR}/plugins/Hill175/imported-worlds.yml" imported-worlds.yml
  for index in "${!bedrock_paths[@]}"; do
    restore_runtime_file "${RUNTIME_DIR}/${bedrock_paths[index]}" "bedrock-${index}"
  done
}

wait_for_server_ready() {
  local probe_marker="$1"
  local attempt
  local latest_log="${RUNTIME_DIR}/logs/latest.log"

  for ((attempt=1; attempt<=STARTUP_WAIT_SECONDS; attempt++)); do
    if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
      echo "${SERVICE_NAME} stopped before Paper reported ready." >&2
      return 1
    fi
    if [[ -f "${latest_log}" && "${latest_log}" -nt "${probe_marker}" ]] \
        && grep -Fq 'Done (' "${latest_log}"; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting ${STARTUP_WAIT_SECONDS} seconds for Paper's ready marker." >&2
  echo "A slow first start can be given longer: HILL175_STARTUP_WAIT_SECONDS=600 bash ops/install-server.sh ..." >&2
  return 1
}

rollback_primary_transition_after_start_failure() {
  local pointer="${RUNTIME_DIR}/assets/survival-worldgen/last-transition-archive.txt"
  local archive_dir
  local recovery_dir
  local label
  local old_name
  local source
  local target

  [[ -f "${pointer}" ]] || {
    echo "Cannot roll back first primary transition: missing ${pointer}" >&2
    return 1
  }
  archive_dir="$(tr -d '\r\n' < "${pointer}")"
  case "${archive_dir}" in
    "${RUNTIME_DIR}/assets/survival-worldgen-archives/"*) ;;
    *)
      echo "Cannot roll back unsafe transition archive path: ${archive_dir}" >&2
      return 1
      ;;
  esac
  [[ -d "${archive_dir}" ]] || {
    echo "Cannot roll back missing transition archive: ${archive_dir}" >&2
    return 1
  }

  recovery_dir="$(mktemp -d "${RUNTIME_DIR}/assets/failed-primary-start.XXXXXX")"
  for label in world world_nether world_the_end hill_survival hill_survival_nether hill_survival_the_end; do
    target="${RUNTIME_DIR}/${label}"
    if [[ -e "${target}" ]] && ! mv "${target}" "${recovery_dir}/${label}"; then
      echo "Could not preserve failed-start world ${target}; automatic rollback stopped." >&2
      return 1
    fi
  done

  for label in world world_nether world_the_end hill_survival hill_survival_nether hill_survival_the_end; do
    source="${archive_dir}/${label}"
    target="${RUNTIME_DIR}/${label}"
    if [[ -e "${source}" ]] && ! mv "${source}" "${target}"; then
      echo "Could not restore archived world ${source}; automatic rollback stopped." >&2
      return 1
    fi
  done
  for old_name in hill_survival hill_survival_nether hill_survival_the_end; do
    label="world__dimensions__minecraft__${old_name}"
    source="${archive_dir}/${label}"
    target="${RUNTIME_DIR}/world/dimensions/minecraft/${old_name}"
    if [[ -e "${source}" ]]; then
      mkdir -p "$(dirname "${target}")"
      if ! mv "${source}" "${target}"; then
        echo "Could not restore archived nested world ${source}; automatic rollback stopped." >&2
        return 1
      fi
    fi
  done

  rm -f -- \
    "${RUNTIME_DIR}/assets/survival-worldgen/primary-trio-managed.env" \
    "${RUNTIME_DIR}/assets/survival-worldgen/installed-manifest.sha512" \
    "${RUNTIME_DIR}/assets/survival-worldgen/installed-manifest.tsv" \
    "${RUNTIME_DIR}/assets/survival-worldgen/pregen-plan.txt" \
    "${pointer}"
  echo "Rolled back the first primary transition; failed generated worlds remain recoverable at ${recovery_dir}." >&2
  return 0
}

rollback_imported_world_replacement() {
  local label="$1"
  local legacy_target="$2"
  local modern_target="$3"
  local backup_dir="$4"
  local recovery_dir

  recovery_dir="$(mktemp -d "${RUNTIME_DIR}/assets/failed-${label}-start.XXXXXX")"
  if [[ -e "${legacy_target}" ]] && ! mv "${legacy_target}" "${recovery_dir}/legacy-replacement"; then
    echo "Could not preserve failed ${label} legacy replacement; automatic rollback stopped." >&2
    return 1
  fi
  if [[ -e "${modern_target}" ]] && ! mv "${modern_target}" "${recovery_dir}/modern-replacement"; then
    echo "Could not preserve failed ${label} modern replacement; automatic rollback stopped." >&2
    return 1
  fi
  if [[ -d "${backup_dir}/legacy" ]] && ! mv "${backup_dir}/legacy" "${legacy_target}"; then
    echo "Could not restore previous ${label} legacy world; automatic rollback stopped." >&2
    return 1
  fi
  if [[ -d "${backup_dir}/modern" ]]; then
    mkdir -p "$(dirname "${modern_target}")"
    if ! mv "${backup_dir}/modern" "${modern_target}"; then
      echo "Could not restore previous ${label} modern world; automatic rollback stopped." >&2
      return 1
    fi
  fi
  echo "Rolled back ${label} replacement; failed replacement remains recoverable at ${recovery_dir}." >&2
  return 0
}

# The plugin imports supplied maps as Paper starts and keeps whatever it replaced
# under replaced-worlds/<world>-<UTC time>/. Put those back when this start is undone.
rollback_supplied_world_imports() {
  local retained base world
  local restored=false

  for retained in "${RUNTIME_DIR}"/replaced-worlds/*; do
    [[ -d "${retained}" ]] || continue
    base="$(basename "${retained}")"
    [[ "${base}" =~ ^([a-z0-9_]+)-[0-9]{8}T[0-9]{6}Z$ ]] || continue
    world="${BASH_REMATCH[1]}"
    [[ $'\n'"${replaced_worlds_before}"$'\n' != *$'\n'"${base}"$'\n'* ]] || continue
    rollback_imported_world_replacement "${world}" "${RUNTIME_DIR}/${world}" \
      "${RUNTIME_DIR}/world/dimensions/minecraft/${world}" "${retained}" || return 1
    rmdir "${retained}" 2>/dev/null || true
    restored=true
  done
  if [[ "${restored}" == true ]]; then
    # The folders still select those maps; this only undoes the failed start.
    echo "The supplied maps remain in ${RUNTIME_DIR}/world-templates and are imported again when Paper next starts with this plugin." >&2
  fi
  return 0
}

validate_people_template_root() {
  python3 "${REPO_DIR}/ops/check-campus-template.py" "${PEOPLE_TEMPLATE_TARGET}"
}

# Maps are chosen by what the operator placed in the designated folders. The hub
# is required; a lobby is optional because the plugin can build a plain one.
validate_supplied_maps() {
  if [[ ! -e "${HUB_TEMPLATE_TARGET}" && ! -L "${HUB_TEMPLATE_TARGET}" ]]; then
    echo "Missing exhibition hub map. Copy the supplied world-templates/hill_hub folder to ${HUB_TEMPLATE_TARGET}" >&2
    echo "(level.dat directly inside) before installing; see docs/operations/deployment.md." >&2
    return 1
  fi
  python3 "${REPO_DIR}/ops/check-world-template.py" "${HUB_TEMPLATE_TARGET}"
  if [[ -e "${AUTH_TEMPLATE_TARGET}" || -L "${AUTH_TEMPLATE_TARGET}" ]]; then
    python3 "${REPO_DIR}/ops/check-world-template.py" "${AUTH_TEMPLATE_TARGET}"
  elif [[ -d "${RUNTIME_DIR}/hill_auth" || -d "${RUNTIME_DIR}/world/dimensions/minecraft/hill_auth" ]]; then
    echo "No lobby map in ${AUTH_TEMPLATE_TARGET}; keeping the lobby that is already installed."
  else
    echo "No lobby map in ${AUTH_TEMPLATE_TARGET}; the plugin will build its plain lobby."
  fi
}

install_people_template() {
  # This directory belongs to the operator. Never replace it with an older archive.
  validate_people_template_root
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${PEOPLE_TEMPLATE_TARGET}"
  echo "Using operator-selected People template at ${PEOPLE_TEMPLATE_TARGET}"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "${status}" -ne 0 && -n "${runtime_rollback_dir}" ]]; then
    systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
    if [[ "${paper_start_attempted}" == true ]] && ! rollback_supplied_world_imports; then
      startup_rollback_failed=true
    fi
    if [[ "${startup_rollback_failed}" == false && "${worldgen_transition_created}" == true ]]; then
      if rollback_primary_transition_after_start_failure; then
        runtime_files_committed=false
      else
        startup_rollback_failed=true
        echo "WARNING: first-transition rollback needs manual recovery; leaving ${SERVICE_NAME} stopped." >&2
      fi
    elif [[ "${startup_rollback_failed}" == false ]]; then
      runtime_files_committed=false
    fi
  fi
  if [[ "${status}" -ne 0 && -n "${runtime_rollback_dir}" && "${runtime_files_committed}" == false \
      && "${startup_rollback_failed}" == false ]]; then
    echo "Installer failed before runtime commit; restoring the previous runtime files." >&2
    restore_runtime_files
  fi
  if [[ "${status}" -ne 0 && "${service_was_stopped}" == true && "${service_was_active}" == true \
      && "${startup_rollback_failed}" == false && "${AUTH_MODE}" == development ]]; then
    echo "Installer failed; restarting the previously active ${SERVICE_NAME}." >&2
    if ! systemctl start "${SERVICE_NAME}"; then
      echo "WARNING: ${SERVICE_NAME} could not be restarted automatically." >&2
    fi
  fi
  if [[ "${status}" -ne 0 && "${service_was_stopped}" == true && "${AUTH_MODE}" == microsoft ]]; then
    # A restored JAR may predate SSO and ignore the environment. Never reopen
    # admission using an unknown authentication implementation after failure.
    echo "Microsoft-mode deployment failed; leaving Paper stopped for reviewed recovery." >&2
  fi
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Designated folders for operator-supplied maps; their contents select the maps.
PEOPLE_TEMPLATE_TARGET="${RUNTIME_DIR}/world-templates/hill_people_template"
HUB_TEMPLATE_TARGET="${RUNTIME_DIR}/world-templates/hill_hub"
AUTH_TEMPLATE_TARGET="${RUNTIME_DIR}/world-templates/hill_auth"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

verify_sha256() {
  local file="$1"
  local expected="$2"
  echo "${expected}  ${file}" | sha256sum --check --status
}

verify_sha512() {
  local file="$1"
  local expected="$2"
  echo "${expected}  ${file}" | sha512sum --check --status
}

require_command curl
require_command tar
require_command borg
require_command flock
require_command find
require_command grep
require_command sha256sum
require_command sha512sum
require_command systemctl
require_command journalctl
require_command ss
require_command wc
require_command git

# Everything the operator supplies must be in place before an outage.
if [[ ! -d "${RUNTIME_DIR}/world-templates" ]]; then
  echo "No maps found. Copy the asset packet's world-templates folder to ${RUNTIME_DIR}/world-templates" >&2
  echo "before installing; see docs/operations/deployment.md." >&2
  exit 1
fi
validate_people_template_root
validate_supplied_maps

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${RUNTIME_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${RUNTIME_DIR}" "${RUNTIME_DIR}/plugins" "${RUNTIME_DIR}/assets"

if [[ ! -x "${JAVA_HOME}/bin/java" ]] || ! "${JAVA_HOME}/bin/java" -version 2>&1 | head -n 1 | grep -q '25\.'; then
  if [[ "$(uname -m)" != x86_64 ]]; then
    echo "Only an x86-64 JDK is listed for download. Install a JDK 25 at ${JAVA_HOME} for $(uname -m) first." >&2
    exit 1
  fi
  java_archive="$(mktemp /tmp/hill175-java25.XXXXXX.tar.gz)"
  curl --fail --location --silent --show-error "${JAVA_LINUX_X64_URL}" --output "${java_archive}"
  verify_sha256 "${java_archive}" "${JAVA_LINUX_X64_SHA256}"
  install -d -m 0755 "${JAVA_HOME}"
  tar --extract --gzip --file "${java_archive}" --directory "${JAVA_HOME}" --strip-components=1
  rm -f "${java_archive}"
fi

cd "${REPO_DIR}"
JAVA_HOME="${JAVA_HOME}" PATH="${JAVA_HOME}/bin:${PATH}" bash ./gradlew clean test jar --no-daemon

paper_target="${RUNTIME_DIR}/assets/paper-pinned.jar"
if [[ ! -f "${paper_target}" ]] || ! verify_sha256 "${paper_target}" "${PAPER_SHA256}"; then
  curl --fail --location --silent --show-error "${PAPER_URL}" --output "${paper_target}.tmp"
  verify_sha256 "${paper_target}.tmp" "${PAPER_SHA256}"
  mv "${paper_target}.tmp" "${paper_target}"
fi

chunky_asset="${RUNTIME_DIR}/assets/${CHUNKY_FILENAME}"
if [[ ! -f "${chunky_asset}" ]] || ! verify_sha512 "${chunky_asset}" "${CHUNKY_SHA512}"; then
  curl --fail --location --silent --show-error "${CHUNKY_URL}" --output "${chunky_asset}.tmp"
  verify_sha512 "${chunky_asset}.tmp" "${CHUNKY_SHA512}"
  mv "${chunky_asset}.tmp" "${chunky_asset}"
fi

for existing_chunky in "${RUNTIME_DIR}"/plugins/*[Cc]hunky*.jar; do
  [[ -e "${existing_chunky}" ]] || continue
  if [[ "$(basename "${existing_chunky}")" != "${CHUNKY_FILENAME}" ]]; then
    echo "Unexpected Chunky plugin jar already exists: ${existing_chunky}" >&2
    echo "Remove it deliberately before installing pinned ${CHUNKY_FILENAME}." >&2
    exit 1
  fi
done

validate_people_template_root
validate_supplied_maps
if [[ "${BEDROCK_ENABLED}" == true ]]; then
  python3 "${REPO_DIR}/ops/install-bedrock.py" prepare --runtime "${RUNTIME_DIR}" --port "${BEDROCK_PORT}"
fi

# A failed cold snapshot blocks upgrades before any active runtime file is changed.
# Update the timer's entry point before the outage so it also observes our lock.
install -m 0644 -o root -g root "${REPO_DIR}/ops/deployment-lock.sh" /usr/local/bin/deployment-lock.sh
install -m 0750 -o root -g root "${REPO_DIR}/ops/backup-hill175.sh" /usr/local/bin/hill175-backup.sh
if [[ -f "${RUNTIME_DIR}/plugins/Hill175.jar" ]]; then
  if systemctl is-active --quiet "${SERVICE_NAME}"; then service_was_active=true; fi
  service_was_stopped=true
  HILL175_BACKUP_ARCHIVE_PREFIX=hill175-predeploy HILL175_BACKUP_LEAVE_STOPPED=true \
    bash "${REPO_DIR}/ops/backup-hill175.sh"
fi

# Runtime files, datapacks, and fresh survival world folders are updated while Paper is stopped.
if systemctl is-active --quiet "${SERVICE_NAME}"; then
  service_was_active=true
  systemctl stop "${SERVICE_NAME}"
else
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
fi
service_was_stopped=true
runtime_rollback_dir="$(mktemp -d "${RUNTIME_DIR}/assets/install-rollback.XXXXXX")"
backup_runtime_file "${RUNTIME_DIR}/paper.jar" paper.jar
backup_runtime_file "${RUNTIME_DIR}/plugins/Hill175.jar" plugin.jar
backup_runtime_file "${RUNTIME_DIR}/plugins/Hill175/config.yml" plugin-config.yml
backup_runtime_file "${RUNTIME_DIR}/server.properties" server.properties
backup_runtime_file "${RUNTIME_DIR}/spigot.yml" spigot.yml
backup_runtime_file "${RUNTIME_DIR}/plugins/${CHUNKY_FILENAME}" chunky.jar
backup_runtime_file "${RUNTIME_DIR}/plugins/Chunky/config.yml" chunky-config.yml
backup_runtime_file "${RUNTIME_DIR}/eula.txt" eula.txt
backup_runtime_file "${RUNTIME_DIR}/plugins/Hill175/imported-worlds.yml" imported-worlds.yml
for index in "${!bedrock_paths[@]}"; do
  backup_runtime_file "${RUNTIME_DIR}/${bedrock_paths[index]}" "bedrock-${index}"
done
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${paper_target}" "${RUNTIME_DIR}/paper.jar"
if [[ "${BEDROCK_ENABLED}" == true ]]; then
  python3 "${REPO_DIR}/ops/install-bedrock.py" install --runtime "${RUNTIME_DIR}" --port "${BEDROCK_PORT}"
fi

install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/build/libs/Hill-server-1.0-SNAPSHOT.jar" \
  "${RUNTIME_DIR}/plugins/Hill175.jar"
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${chunky_asset}" \
  "${RUNTIME_DIR}/plugins/${CHUNKY_FILENAME}"
verify_sha512 "${RUNTIME_DIR}/plugins/${CHUNKY_FILENAME}" "${CHUNKY_SHA512}"
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${RUNTIME_DIR}/plugins/Chunky"
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/server-config/chunky-config.yml" \
  "${RUNTIME_DIR}/plugins/Chunky/config.yml"
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/server-config/server.properties" \
  "${RUNTIME_DIR}/server.properties"
if [[ "${AUTH_MODE}" == microsoft ]]; then
  sed -i 's/^online-mode=false$/online-mode=true/' "${RUNTIME_DIR}/server.properties"
fi
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/server-config/spigot.yml" \
  "${RUNTIME_DIR}/spigot.yml"
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${RUNTIME_DIR}/plugins/Hill175"
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/src/main/resources/config.yml" \
  "${RUNTIME_DIR}/plugins/Hill175/config.yml"
printf 'eula=true\n' > "${RUNTIME_DIR}/eula.txt"

install_people_template

if [[ -f "${RUNTIME_DIR}/assets/survival-worldgen/primary-trio-managed.env" ]]; then
  primary_transition_marker_existed=true
fi
bash "${REPO_DIR}/ops/install-survival-worldgen.sh" \
  "${RUNTIME_DIR}" \
  "${REPO_DIR}/server-assets/survival-worldgen-manifest.tsv"
if [[ "${primary_transition_marker_existed}" == false \
    && -f "${RUNTIME_DIR}/assets/survival-worldgen/primary-trio-managed.env" ]]; then
  worldgen_transition_created=true
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${RUNTIME_DIR}"
chmod 0640 "${RUNTIME_DIR}/eula.txt" "${RUNTIME_DIR}/server.properties" "${RUNTIME_DIR}/spigot.yml" "${RUNTIME_DIR}/paper.jar"

install -m 0644 -o root -g root "${REPO_DIR}/ops/systemd/hill175.service" /etc/systemd/system/hill175.service
install -m 0644 -o root -g root "${REPO_DIR}/ops/systemd/hill175-backup.service" /etc/systemd/system/hill175-backup.service
install -m 0644 -o root -g root "${REPO_DIR}/ops/systemd/hill175-backup.timer" /etc/systemd/system/hill175-backup.timer
systemctl daemon-reload
systemctl enable hill175.service
systemctl enable --now hill175-backup.timer
startup_probe_marker="${runtime_rollback_dir}/startup-probe"
if [[ -f "${RUNTIME_DIR}/logs/latest.log" ]]; then
  mv "${RUNTIME_DIR}/logs/latest.log" "${runtime_rollback_dir}/previous-latest.log"
fi
touch "${startup_probe_marker}"
# Paper imports the supplied lobby and hub maps during this start.
replaced_worlds_before="$(ls -1 "${RUNTIME_DIR}/replaced-worlds" 2>/dev/null || true)"
paper_start_attempted=true
systemctl restart "${SERVICE_NAME}"
wait_for_server_ready "${startup_probe_marker}"
bash "${REPO_DIR}/ops/verify-server.sh"
if [[ "${AUTH_MODE}" == microsoft ]]; then
  python3 "${REPO_DIR}/ops/configure-auth-proxy.py" install --env-file "${AUTH_ENV_FILE}"
fi
systemctl --no-pager --full status "${SERVICE_NAME}"
runtime_files_committed=true
service_was_stopped=false
rm -rf -- "${runtime_rollback_dir}"
runtime_rollback_dir=""

# Record only a verified, committed source deployment, separately from game data.
# The nightly updater must compare against this, not just the checkout's HEAD:
# a successful pull can be followed by a failed build/install.
update_state="${HILL175_UPDATE_STATE_DIR:-/var/lib/hill175-update}"
install -d -m 0700 -o root -g root "${update_state}"
if [[ -z "$(git -C "${REPO_DIR}" status --porcelain --untracked-files=all)" ]]; then
  (umask 077; git -C "${REPO_DIR}" rev-parse HEAD > "${update_state}/deployed-commit.tmp")
  mv "${update_state}/deployed-commit.tmp" "${update_state}/deployed-commit"
  rm -f -- "${update_state}/failed-commit"
else
  rm -f -- "${update_state}/deployed-commit"
  echo "Uncommitted source deployment; automatic updates require a clean committed install."
fi

echo "Hill 175 is installed. Minecraft TCP port 25566 must be allowed by the host firewall/provider firewall. Daily Borg backups are scheduled by hill175-backup.timer."
