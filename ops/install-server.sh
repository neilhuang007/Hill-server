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
service_was_active=false
service_was_stopped=false
runtime_files_committed=false
runtime_rollback_dir=""
worldgen_transition_created=false
startup_rollback_failed=false
primary_transition_marker_existed=false
auth_replacement_applied=false
auth_replacement_backup=""
hub_replacement_applied=false
hub_replacement_backup=""
people_template_replacement_applied=false
people_template_backup=""
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
  restore_runtime_file "${RUNTIME_DIR}/structure.nbt" structure.nbt
  restore_runtime_file "${RUNTIME_DIR}/assets/.small-medieval-church-1.0.5-installed" auth-install-marker
  restore_runtime_file "${RUNTIME_DIR}/assets/.hill175-exhibition-hub-2026-08-26-installed" hub-install-marker
  for index in "${!bedrock_paths[@]}"; do
    restore_runtime_file "${RUNTIME_DIR}/${bedrock_paths[index]}" "bedrock-${index}"
  done
}

wait_for_server_ready() {
  local probe_marker="$1"
  local attempt
  local latest_log="${RUNTIME_DIR}/logs/latest.log"

  for ((attempt=1; attempt<=180; attempt++)); do
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
  echo "Timed out waiting 180 seconds for Paper's ready marker." >&2
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

count_mca_files() {
  local directory="$1"

  find "${directory}" -maxdepth 1 -type f -name 'r.*.mca' | wc -l | tr -d '[:space:]'
}

remove_people_template_staging() {
  local staging_dir="$1"

  case "${staging_dir}" in
    "${RUNTIME_DIR}/assets/campus/install-staging/"*) ;;
    *)
      echo "Refused to remove unsafe People template staging path: ${staging_dir}" >&2
      return 1
      ;;
  esac
  rm -rf -- "${staging_dir}"
}

validate_people_template_root() {
  local template_root="$1"
  local label="$2"
  local marker
  local nested_dimensions
  local region_count
  local poi_count

  [[ -d "${template_root}" ]] || {
    echo "${label} is missing expected root directory: ${template_root}" >&2
    return 1
  }
  [[ -f "${template_root}/.hill175-people-ready" ]] || {
    echo "${label} is missing .hill175-people-ready" >&2
    return 1
  }
  marker="$(tr -d '\r\n' < "${template_root}/.hill175-people-ready")"
  [[ "${marker}" == "${PEOPLE_TEMPLATE_READY_MARKER}" ]] || {
    echo "${label} has unexpected People template marker: ${marker}" >&2
    return 1
  }
  [[ -f "${template_root}/hill-campus-template.json" ]] || {
    echo "${label} is missing hill-campus-template.json" >&2
    return 1
  }
  [[ -f "${template_root}/hill-campus-template.yml" ]] || {
    echo "${label} is missing hill-campus-template.yml" >&2
    return 1
  }
  [[ -d "${template_root}/region" ]] || {
    echo "${label} is missing region directory" >&2
    return 1
  }
  if [[ "${PEOPLE_TEMPLATE_POI_MCA_COUNT}" != "0" ]]; then
    [[ -d "${template_root}/poi" ]] || {
      echo "${label} is missing poi directory" >&2
      return 1
    }
  fi
  region_count="$(count_mca_files "${template_root}/region")"
  [[ "${region_count}" == "${PEOPLE_TEMPLATE_REGION_MCA_COUNT}" ]] || {
    echo "${label} has ${region_count} region MCA files; expected ${PEOPLE_TEMPLATE_REGION_MCA_COUNT}" >&2
    return 1
  }
  poi_count="0"
  if [[ -d "${template_root}/poi" ]]; then
    poi_count="$(count_mca_files "${template_root}/poi")"
  fi
  [[ "${poi_count}" == "${PEOPLE_TEMPLATE_POI_MCA_COUNT}" ]] || {
    echo "${label} has ${poi_count} POI MCA files; expected ${PEOPLE_TEMPLATE_POI_MCA_COUNT}" >&2
    return 1
  }
  nested_dimensions="$(find "${template_root}" -type d -name dimensions -print -quit)"
  [[ -z "${nested_dimensions}" ]] || {
    echo "${label} contains nested dimensions directory: ${nested_dimensions}" >&2
    return 1
  }
}

preflight_people_template_archive() {
  local archive="${PEOPLE_TEMPLATE_ASSET_DIR}/${PEOPLE_TEMPLATE_ARCHIVE_NAME}"

  if [[ ! -f "${archive}" ]]; then
    echo "Missing user-provided People template archive: ${archive}" >&2
    echo "Stage ${PEOPLE_TEMPLATE_ARCHIVE_NAME} under ${PEOPLE_TEMPLATE_ASSET_DIR} before running this installer." >&2
    exit 1
  fi
  verify_sha256 "${archive}" "${PEOPLE_TEMPLATE_SHA256}" || {
    echo "People template archive SHA-256 mismatch: ${archive}" >&2
    exit 1
  }
}

rollback_people_template_replacement() {
  local recovery_dir

  case "${people_template_backup}" in
    "${RUNTIME_DIR}/assets/people-template-backup."*) ;;
    *)
      echo "Cannot roll back unsafe People template backup path: ${people_template_backup}" >&2
      return 1
      ;;
  esac
  [[ -d "${people_template_backup}" ]] || {
    echo "Cannot roll back missing People template backup: ${people_template_backup}" >&2
    return 1
  }

  recovery_dir="$(mktemp -d "${RUNTIME_DIR}/assets/failed-people-template-start.XXXXXX")"
  if [[ -e "${PEOPLE_TEMPLATE_TARGET}" || -L "${PEOPLE_TEMPLATE_TARGET}" ]]; then
    if ! mv "${PEOPLE_TEMPLATE_TARGET}" "${recovery_dir}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}"; then
      echo "Could not preserve failed People template replacement; automatic rollback stopped." >&2
      return 1
    fi
  fi
  if [[ -e "${people_template_backup}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}" ]]; then
    install -d "$(dirname "${PEOPLE_TEMPLATE_TARGET}")"
    if ! mv "${people_template_backup}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}" "${PEOPLE_TEMPLATE_TARGET}"; then
      echo "Could not restore previous People template; automatic rollback stopped." >&2
      return 1
    fi
  elif [[ -f "${people_template_backup}/.absent" ]]; then
    :
  else
    echo "People template backup did not contain ${PEOPLE_TEMPLATE_ARCHIVE_ROOT} or .absent marker." >&2
    return 1
  fi
  people_template_replacement_applied=false
  echo "Rolled back People template replacement; failed replacement remains recoverable at ${recovery_dir}." >&2
  return 0
}

install_people_template() {
  local archive="${PEOPLE_TEMPLATE_ASSET_DIR}/${PEOPLE_TEMPLATE_ARCHIVE_NAME}"
  local staging_parent="${PEOPLE_TEMPLATE_ASSET_DIR}/install-staging"
  local extract_dir
  local staged_root
  local extra_top_level
  local backup_dir

  preflight_people_template_archive
  install -d -m 0750 -o root -g root "${PEOPLE_TEMPLATE_ASSET_DIR}" "${staging_parent}"
  install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "$(dirname "${PEOPLE_TEMPLATE_TARGET}")"
  extract_dir="$(mktemp -d "${staging_parent}/hill-template.XXXXXX")"
  if ! tar --extract --gzip --no-same-owner --no-same-permissions --file "${archive}" --directory "${extract_dir}"; then
    remove_people_template_staging "${extract_dir}"
    echo "Could not extract People template archive: ${archive}" >&2
    exit 1
  fi
  staged_root="${extract_dir}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}"
  extra_top_level="$(find "${extract_dir}" -mindepth 1 -maxdepth 1 ! -name "${PEOPLE_TEMPLATE_ARCHIVE_ROOT}" -print -quit)"
  if [[ -n "${extra_top_level}" ]]; then
    remove_people_template_staging "${extract_dir}"
    echo "People template archive contains unexpected top-level path: ${extra_top_level}" >&2
    exit 1
  fi
  if ! validate_people_template_root "${staged_root}" "Extracted People template"; then
    remove_people_template_staging "${extract_dir}"
    exit 1
  fi

  if [[ -L "${PEOPLE_TEMPLATE_TARGET}" || -e "${PEOPLE_TEMPLATE_TARGET}" && ! -d "${PEOPLE_TEMPLATE_TARGET}" ]]; then
    remove_people_template_staging "${extract_dir}"
    echo "Refusing to replace unexpected People template path: ${PEOPLE_TEMPLATE_TARGET}" >&2
    exit 1
  fi

  backup_dir="$(mktemp -d "${RUNTIME_DIR}/assets/people-template-backup.XXXXXX")"
  if [[ -d "${PEOPLE_TEMPLATE_TARGET}" ]]; then
    if ! mv "${PEOPLE_TEMPLATE_TARGET}" "${backup_dir}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}"; then
      remove_people_template_staging "${extract_dir}"
      echo "Could not move previous People template aside: ${PEOPLE_TEMPLATE_TARGET}" >&2
      exit 1
    fi
  else
    touch "${backup_dir}/.absent"
  fi
  people_template_backup="${backup_dir}"

  if ! mv "${staged_root}" "${PEOPLE_TEMPLATE_TARGET}"; then
    if [[ -d "${backup_dir}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}" ]]; then
      mv "${backup_dir}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}" "${PEOPLE_TEMPLATE_TARGET}"
    fi
    remove_people_template_staging "${extract_dir}"
    echo "People template replacement failed; the previous template was restored." >&2
    exit 1
  fi
  people_template_replacement_applied=true
  rmdir "${extract_dir}"

  validate_people_template_root "${PEOPLE_TEMPLATE_TARGET}" "Installed People template"
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${PEOPLE_TEMPLATE_TARGET}"
  find "${PEOPLE_TEMPLATE_TARGET}" -type d -exec chmod 0750 {} +
  find "${PEOPLE_TEMPLATE_TARGET}" -type f -exec chmod 0640 {} +
  echo "Installed People template ${PEOPLE_TEMPLATE_ARCHIVE_NAME} at ${PEOPLE_TEMPLATE_TARGET}"
  if [[ -d "${backup_dir}/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}" ]]; then
    echo "Previous People template retained for recovery at ${backup_dir}"
  fi
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "${status}" -ne 0 && -n "${runtime_rollback_dir}" ]]; then
    systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
    if [[ "${people_template_replacement_applied}" == true ]] \
        && ! rollback_people_template_replacement; then
      startup_rollback_failed=true
    fi
    if [[ "${hub_replacement_applied}" == true ]] \
        && ! rollback_imported_world_replacement hub "${hub_target}" "${hub_modern_target}" "${hub_replacement_backup}"; then
      startup_rollback_failed=true
    fi
    if [[ "${startup_rollback_failed}" == false && "${auth_replacement_applied}" == true ]] \
        && ! rollback_imported_world_replacement authentication "${auth_target}" "${auth_modern_target}" "${auth_replacement_backup}"; then
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

PAPER_URL="https://fill-data.papermc.io/v1/objects/a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629/paper-26.2-119.jar"
PAPER_SHA256="a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629"

JAVA_URL="https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jdk_x64_linux_hotspot_25.0.4.1_1.tar.gz"
JAVA_SHA256="dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e"

AUTH_URL="https://www.curseforge.com/api/v1/mods/1469713/files/8692252/download"
AUTH_SHA256="de98674487bcd69593c36a03b1204a7d14ff694f281508d156e53650e31e4630"

CHUNKY_PROJECT_ID="fALzjamp"
CHUNKY_VERSION_ID="MdY6JATr"
CHUNKY_FILENAME="Chunky-Bukkit-1.5.3.jar"
CHUNKY_URL="https://cdn.modrinth.com/data/fALzjamp/versions/MdY6JATr/Chunky-Bukkit-1.5.3.jar"
CHUNKY_SHA512="43ffecc6e6a734b752da41575bbb316526c124c3f878942437d5133c377bfbd9b78bda975520dc074d7158c15dade58a444ccd0fd8d8a25d165b6fc450140422"

HUB_ARCHIVE_NAME="Hill175-Exhibition-Hub-2026-08-26.zip"
HUB_ARCHIVE_ROOT="Hill175 Exhibition Hub 2026-08-26"
HUB_SHA256="d6ebfc048b5dc3351191182255ce77fe101c373bd6bb8a3330d8fc2672c858de"

source "${REPO_DIR}/server-assets/campus-template.env"
PEOPLE_TEMPLATE_ASSET_DIR="${RUNTIME_DIR}/assets/campus"
PEOPLE_TEMPLATE_TARGET="${RUNTIME_DIR}/world-templates/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}"

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
require_command unzip
require_command borg
require_command flock
require_command find
require_command grep
require_command sha256sum
require_command sha512sum
require_command systemctl
require_command wc

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${RUNTIME_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${RUNTIME_DIR}" "${RUNTIME_DIR}/plugins" "${RUNTIME_DIR}/assets"

if [[ ! -x "${JAVA_HOME}/bin/java" ]] || ! "${JAVA_HOME}/bin/java" -version 2>&1 | head -n 1 | grep -q '25\.'; then
  java_archive="$(mktemp /tmp/hill175-java25.XXXXXX.tar.gz)"
  curl --fail --location --silent --show-error "${JAVA_URL}" --output "${java_archive}"
  verify_sha256 "${java_archive}" "${JAVA_SHA256}"
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

preflight_people_template_archive
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
backup_runtime_file "${RUNTIME_DIR}/structure.nbt" structure.nbt
backup_runtime_file "${RUNTIME_DIR}/assets/.small-medieval-church-1.0.5-installed" auth-install-marker
backup_runtime_file "${RUNTIME_DIR}/assets/.hill175-exhibition-hub-2026-08-26-installed" hub-install-marker
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
if [[ -f "${REPO_DIR}/structure.nbt" ]]; then
  install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
    "${REPO_DIR}/structure.nbt" \
    "${RUNTIME_DIR}/structure.nbt"
fi
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

auth_install_marker="${RUNTIME_DIR}/assets/.small-medieval-church-1.0.5-installed"
auth_target="${RUNTIME_DIR}/hill_auth"
auth_modern_target="${RUNTIME_DIR}/world/dimensions/minecraft/hill_auth"
if [[ ! -f "${auth_install_marker}" || ! -d "${auth_target}" && ! -d "${auth_modern_target}" ]]; then
  auth_archive="${RUNTIME_DIR}/assets/Small-Medieval-Church-1.0.5.zip"
  curl --fail --location --silent --show-error "${AUTH_URL}" --output "${auth_archive}.tmp"
  verify_sha256 "${auth_archive}.tmp" "${AUTH_SHA256}"
  mv "${auth_archive}.tmp" "${auth_archive}"

  auth_extract="$(mktemp -d /tmp/hill175-auth.XXXXXX)"
  unzip -q "${auth_archive}" -d "${auth_extract}"
  if [[ ! -f "${auth_extract}/Small Medieval Church 1.0.5/level.dat" ]]; then
    echo "Authentication archive did not contain the expected Small Medieval Church 1.0.5 world root." >&2
    exit 1
  fi
  rm -rf "${auth_extract}/Small Medieval Church 1.0.5/playerdata" \
         "${auth_extract}/Small Medieval Church 1.0.5/stats" \
         "${auth_extract}/Small Medieval Church 1.0.5/advancements"
  rm -f "${auth_extract}/Small Medieval Church 1.0.5/uid.dat" \
        "${auth_extract}/Small Medieval Church 1.0.5/session.lock"

  # Move existing auth worlds aside only after the replacement has downloaded,
  # passed its checksum, and exposed a valid level.dat. Keep the previous world
  # recoverable just like the exhibition hub replacement.
  auth_backup="$(mktemp -d "${RUNTIME_DIR}/assets/auth-backup.XXXXXX")"
  auth_backup_has_world=false
  auth_move_failed=false
  if [[ -d "${auth_target}" ]]; then
    if mv "${auth_target}" "${auth_backup}/legacy"; then
      auth_backup_has_world=true
    else
      auth_move_failed=true
    fi
  fi
  if [[ "${auth_move_failed}" == false && -d "${auth_modern_target}" ]]; then
    if mv "${auth_modern_target}" "${auth_backup}/modern"; then
      auth_backup_has_world=true
    else
      auth_move_failed=true
    fi
  fi
  if [[ "${auth_move_failed}" == true ]]; then
    [[ -d "${auth_backup}/legacy" ]] && mv "${auth_backup}/legacy" "${auth_target}"
    if [[ -d "${auth_backup}/modern" ]]; then
      mkdir -p "$(dirname "${auth_modern_target}")"
      mv "${auth_backup}/modern" "${auth_modern_target}"
    fi
    echo "Authentication world could not be staged for replacement; the previous world was restored." >&2
    exit 1
  fi
  if ! mv "${auth_extract}/Small Medieval Church 1.0.5" "${auth_target}"; then
    [[ -d "${auth_backup}/legacy" ]] && mv "${auth_backup}/legacy" "${auth_target}"
    if [[ -d "${auth_backup}/modern" ]]; then
      mkdir -p "$(dirname "${auth_modern_target}")"
      mv "${auth_backup}/modern" "${auth_modern_target}"
    fi
    echo "Authentication world replacement failed; the previous world was restored." >&2
    exit 1
  fi
  auth_replacement_applied=true
  auth_replacement_backup="${auth_backup}"
  rm -rf "${auth_extract}"
  touch "${auth_install_marker}"
  if [[ "${auth_backup_has_world}" == true ]]; then
    echo "Previous authentication world retained for recovery at ${auth_backup}"
  else
    rmdir "${auth_backup}"
  fi
fi

hub_install_marker="${RUNTIME_DIR}/assets/.hill175-exhibition-hub-2026-08-26-installed"
hub_target="${RUNTIME_DIR}/hill_hub"
hub_modern_target="${RUNTIME_DIR}/world/dimensions/minecraft/hill_hub"
installed_hub_sha=""
if [[ -f "${hub_install_marker}" ]]; then
  installed_hub_sha="$(tr -d '[:space:]' < "${hub_install_marker}")"
fi
if [[ "${installed_hub_sha}" != "${HUB_SHA256}" || ! -d "${hub_target}" && ! -d "${hub_modern_target}" ]]; then
  hub_archive="${RUNTIME_DIR}/assets/${HUB_ARCHIVE_NAME}"
  if [[ ! -f "${hub_archive}" ]]; then
    echo "Missing user-provided hub archive: ${hub_archive}" >&2
    echo "Package it with ops/package-user-hub.ps1 and stage it before running this installer." >&2
    exit 1
  fi
  verify_sha256 "${hub_archive}" "${HUB_SHA256}"

  hub_extract="$(mktemp -d /tmp/hill175-hub.XXXXXX)"
  unzip -q "${hub_archive}" -d "${hub_extract}"
  if [[ ! -f "${hub_extract}/${HUB_ARCHIVE_ROOT}/level.dat" ]]; then
    echo "Hub archive did not contain the expected ${HUB_ARCHIVE_ROOT} world root." >&2
    exit 1
  fi
  rm -rf "${hub_extract}/${HUB_ARCHIVE_ROOT}/players" \
         "${hub_extract}/${HUB_ARCHIVE_ROOT}/playerdata" \
         "${hub_extract}/${HUB_ARCHIVE_ROOT}/stats" \
         "${hub_extract}/${HUB_ARCHIVE_ROOT}/advancements"
  rm -f "${hub_extract}/${HUB_ARCHIVE_ROOT}/uid.dat" \
        "${hub_extract}/${HUB_ARCHIVE_ROOT}/session.lock"

  # Validate the replacement before stopping Paper, then move the previous
  # world aside so an interrupted deployment remains recoverable.
  hub_backup="$(mktemp -d "${RUNTIME_DIR}/assets/hub-backup.XXXXXX")"
  hub_backup_has_world=false
  hub_move_failed=false
  if [[ -d "${hub_target}" ]]; then
    if mv "${hub_target}" "${hub_backup}/legacy"; then
      hub_backup_has_world=true
    else
      hub_move_failed=true
    fi
  fi
  if [[ "${hub_move_failed}" == false && -d "${hub_modern_target}" ]]; then
    if mv "${hub_modern_target}" "${hub_backup}/modern"; then
      hub_backup_has_world=true
    else
      hub_move_failed=true
    fi
  fi
  if [[ "${hub_move_failed}" == true ]]; then
    [[ -d "${hub_backup}/legacy" ]] && mv "${hub_backup}/legacy" "${hub_target}"
    if [[ -d "${hub_backup}/modern" ]]; then
      mkdir -p "$(dirname "${hub_modern_target}")"
      mv "${hub_backup}/modern" "${hub_modern_target}"
    fi
    echo "Hub world could not be staged for replacement; the previous world was restored." >&2
    exit 1
  fi
  if ! mv "${hub_extract}/${HUB_ARCHIVE_ROOT}" "${hub_target}"; then
    [[ -d "${hub_backup}/legacy" ]] && mv "${hub_backup}/legacy" "${hub_target}"
    if [[ -d "${hub_backup}/modern" ]]; then
      mkdir -p "${RUNTIME_DIR}/world/dimensions/minecraft"
      mv "${hub_backup}/modern" "${hub_modern_target}"
    fi
    echo "Hub replacement failed; the previous world was restored." >&2
    exit 1
  fi
  hub_replacement_applied=true
  hub_replacement_backup="${hub_backup}"
  rm -rf "${hub_extract}"
  printf '%s\n' "${HUB_SHA256}" > "${hub_install_marker}"
  if [[ "${hub_backup_has_world}" == true ]]; then
    echo "Previous hub retained for recovery at ${hub_backup}"
  else
    rmdir "${hub_backup}"
  fi
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

echo "Hill 175 is installed. Minecraft TCP port 25566 must be allowed by the host firewall/provider firewall. Daily Borg backups are scheduled by hill175-backup.timer."
