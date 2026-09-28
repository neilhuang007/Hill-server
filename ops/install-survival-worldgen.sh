#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${1:-/opt/hill175}"
MANIFEST="${2:-${REPO_DIR}/server-assets/survival-worldgen-manifest.tsv}"
PRIMARY_WORLD_NAME="world"
SURVIVAL_WORLD_NAME="world"
SURVIVAL_NETHER_NAME="world_nether"
SURVIVAL_END_NAME="world_the_end"
OLD_SURVIVAL_WORLD_NAMES=(hill_survival hill_survival_nether hill_survival_the_end)
PRIMARY_DIMENSION_DIR_NAMES=(overworld the_nether the_end)
PRIMARY_ROOT_STATE_DIR_NAMES=(players playerdata data stats advancements)
PREGEN_RADIUS_BLOCKS="4000"

TRANSITION_ACTIVE=false
TRANSITION_ARCHIVE_DIR=""
TRANSITION_MARKER_PATH=""
TRANSITION_REMOVE_NEW_PRIMARY_ON_ROLLBACK=false
TRANSITION_TARGETS=()
TRANSITION_LABELS=()

EXPECTED_HEADER=$'load_order\trole\tdimension\tproject_title\tslug\tproject_id\tversion_id\tversion_number\tgame_versions\tloader\tclient_side\tserver_side\tfilename\tsize\tsha512\tsha1\tdownload_url\tlicense_id\tlicense_url\tproject_url'
EXPECTED_SLUGS=(terralith terratonic structory structory-towers towns-and-towers incendium nullscape)
EXPECTED_VERSION_IDS=(CzijfXJQ cT2AsHrJ OIcllpSf uxUF2h4B E39wx2BN znNBZB6M prWWpjSv)

fail() {
  echo "survival worldgen install failed: $*" >&2
  exit 1
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required command: $1"
  fi
}

manifest_identity_sha512() {
  local line
  # Comments and line endings are documentation, not world-generation state.
  # Hash only the normalized manifest header/rows so a comment edit cannot
  # force a destructive new-world migration.
  line="$(awk 'NF && substr($0, 1, 1) != "#" { sub(/\r$/, ""); print }' "$1" | sha512sum)"
  printf '%s\n' "${line%% *}"
}

verify_sha512() {
  local file="$1"
  local expected="$2"
  echo "${expected}  ${file}" | sha512sum --check --status
}

archive_target_if_present() {
  local runtime_root="$1"
  local archive_dir="$2"
  local target="$3"
  local label="$4"
  local parent
  local resolved_parent
  local resolved

  [[ -e "${target}" ]] || return 1
  parent="$(dirname "${target}")"
  resolved_parent="$(cd "${parent}" && pwd -P)"
  resolved="${resolved_parent}/$(basename "${target}")"
  case "${resolved}" in
    "${runtime_root}"/*) ;;
    *) fail "transition target resolved outside runtime: ${resolved}" ;;
  esac
  [[ "${resolved}" != "${runtime_root}" ]] || fail "transition target resolved to runtime root"
  [[ "${label}" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "unsafe archive label: ${label}"
  mkdir -p "${archive_dir}"
  [[ ! -e "${archive_dir}/${label}" ]] || fail "archive destination already exists: ${archive_dir}/${label}"
  mv "${resolved}" "${archive_dir}/${label}"
  TRANSITION_TARGETS+=("${resolved}")
  TRANSITION_LABELS+=("${label}")
  echo "Archived ${resolved} to ${archive_dir}/${label}"
  return 0
}

is_excluded_archived_dimension() {
  local name="$1"
  local excluded

  for excluded in "${OLD_SURVIVAL_WORLD_NAMES[@]}" "${PRIMARY_DIMENSION_DIR_NAMES[@]}"; do
    [[ "${name}" == "${excluded}" ]] && return 0
  done
  return 1
}

restore_non_survival_custom_dimensions() {
  local archived_world="$1"
  local new_world="$2"
  local source_root="${archived_world}/dimensions"
  local destination_root="${new_world}/dimensions"
  local namespace_source
  local namespace
  local destination_dir
  local source
  local name

  [[ -d "${source_root}" ]] || return
  shopt -s nullglob
  for namespace_source in "${source_root}"/*; do
    [[ -d "${namespace_source}" ]] || continue
    namespace="$(basename "${namespace_source}")"
    destination_dir="${destination_root}/${namespace}"
    mkdir -p "${destination_dir}"
    for source in "${namespace_source}"/*; do
      [[ -d "${source}" ]] || continue
      name="$(basename "${source}")"
      if [[ "${namespace}" == "minecraft" ]] && is_excluded_archived_dimension "${name}"; then
        echo "Left archived primary/survival dimension out of new world: ${namespace}:${name}"
        continue
      fi
      [[ ! -e "${destination_dir}/${name}" ]] || fail "custom dimension restore target already exists: ${destination_dir}/${name}"
      cp -a "${source}" "${destination_dir}/${name}"
      echo "Restored custom dimension ${namespace}:${name} into new primary world"
    done
  done
  shopt -u nullglob
}

restore_primary_root_state_dirs() {
  local archived_world="$1"
  local new_world="$2"
  local state_name
  local source_dir
  local destination_dir

  for state_name in "${PRIMARY_ROOT_STATE_DIR_NAMES[@]}"; do
    source_dir="${archived_world}/${state_name}"
    [[ -d "${source_dir}" ]] || continue
    mkdir -p "${new_world}"
    destination_dir="${new_world}/${state_name}"
    [[ ! -e "${destination_dir}" ]] || fail "primary root state restore target already exists: ${destination_dir}"
    cp -a "${source_dir}" "${destination_dir}"
    echo "Restored primary world root state directory ${state_name} into new primary world"
  done
}

restore_archived_primary_world_state() {
  local archived_world="$1"
  local new_world="$2"

  restore_non_survival_custom_dimensions "${archived_world}" "${new_world}"
  restore_primary_root_state_dirs "${archived_world}" "${new_world}"
}

archive_first_transition_worlds() {
  local runtime_root="$1"
  local archive_root="$2"
  local timestamp
  local archive_dir
  local moved=false
  local old_name
  local nested_target

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive_dir="${archive_root}/primary-trio-transition-${timestamp}"
  TRANSITION_ACTIVE=true
  TRANSITION_ARCHIVE_DIR="${archive_dir}"
  if [[ -e "${runtime_root}/${PRIMARY_WORLD_NAME}" ]]; then
    TRANSITION_REMOVE_NEW_PRIMARY_ON_ROLLBACK=false
  else
    TRANSITION_REMOVE_NEW_PRIMARY_ON_ROLLBACK=true
  fi
  TRANSITION_TARGETS=()
  TRANSITION_LABELS=()
  mkdir -p "${archive_dir}"

  archive_target_if_present "${runtime_root}" "${archive_dir}" "${runtime_root}/${PRIMARY_WORLD_NAME}" "${PRIMARY_WORLD_NAME}" && moved=true
  archive_target_if_present "${runtime_root}" "${archive_dir}" "${runtime_root}/${SURVIVAL_NETHER_NAME}" "${SURVIVAL_NETHER_NAME}" && moved=true
  archive_target_if_present "${runtime_root}" "${archive_dir}" "${runtime_root}/${SURVIVAL_END_NAME}" "${SURVIVAL_END_NAME}" && moved=true

  for old_name in "${OLD_SURVIVAL_WORLD_NAMES[@]}"; do
    archive_target_if_present "${runtime_root}" "${archive_dir}" "${runtime_root}/${old_name}" "${old_name}" && moved=true
  done

  for old_name in "${OLD_SURVIVAL_WORLD_NAMES[@]}"; do
    nested_target="${runtime_root}/${PRIMARY_WORLD_NAME}/dimensions/minecraft/${old_name}"
    archive_target_if_present "${runtime_root}" "${archive_dir}" "${nested_target}" "${PRIMARY_WORLD_NAME}__dimensions__minecraft__${old_name}" && moved=true
  done

  if [[ "${moved}" == true ]]; then
    restore_archived_primary_world_state "${archive_dir}/${PRIMARY_WORLD_NAME}" "${runtime_root}/${PRIMARY_WORLD_NAME}"
  fi
  printf '%s\n' "${archive_dir}" > "${STATE_DIR}/last-transition-archive.txt"
}

rollback_active_transition() {
  local status=$?
  local index
  local target
  local label
  local archived

  trap - EXIT ERR INT TERM
  if [[ "${TRANSITION_ACTIVE}" == true ]]; then
    echo "Rolling back incomplete primary-world transition from ${TRANSITION_ARCHIVE_DIR}" >&2
    rm -f -- "${TRANSITION_MARKER_PATH}"
    if [[ -f "${STATE_DIR}/last-transition-archive.txt" ]] \
        && [[ "$(tr -d '\r\n' < "${STATE_DIR}/last-transition-archive.txt")" == "${TRANSITION_ARCHIVE_DIR}" ]]; then
      rm -f -- "${STATE_DIR}/last-transition-archive.txt"
    fi
    if [[ "${TRANSITION_REMOVE_NEW_PRIMARY_ON_ROLLBACK}" == true \
        && -e "${RUNTIME_DIR}/${PRIMARY_WORLD_NAME}" ]]; then
      rm -rf -- "${RUNTIME_DIR}/${PRIMARY_WORLD_NAME}"
    fi
    for ((index=${#TRANSITION_TARGETS[@]} - 1; index >= 0; index--)); do
      target="${TRANSITION_TARGETS[index]}"
      label="${TRANSITION_LABELS[index]}"
      archived="${TRANSITION_ARCHIVE_DIR}/${label}"
      case "${target}" in
        "${RUNTIME_DIR}"/*) ;;
        *) echo "Refusing unsafe rollback target ${target}" >&2; continue ;;
      esac
      if [[ -e "${archived}" ]]; then
        if [[ -e "${target}" ]]; then
          rm -rf -- "${target}"
        fi
        mkdir -p "$(dirname "${target}")"
        mv "${archived}" "${target}"
      fi
    done
  fi
  exit "${status}"
}

write_seed_if_missing() {
  local seed_file="$1"
  local hi
  local lo
  local seed

  if [[ -f "${seed_file}" ]]; then
    if ! grep -Eq '^[0-9]+$' "${seed_file}"; then
      fail "survival seed file is not a positive integer: ${seed_file}"
    fi
    return
  fi

  hi="$(od -An -N4 -tu4 /dev/urandom | tr -d '[:space:]')"
  lo="$(od -An -N4 -tu4 /dev/urandom | tr -d '[:space:]')"
  [[ -n "${hi}" && -n "${lo}" ]] || fail "could not read random bytes for survival seed"
  seed=$(( ((hi & 0x7fffffff) << 32) | lo ))
  [[ "${seed}" -gt 0 ]] || seed=1
  umask 077
  printf '%s\n' "${seed}" > "${seed_file}"
}

seed_value() {
  local seed_file="$1"
  local seed

  seed="$(tr -d '[:space:]' < "${seed_file}")"
  [[ "${seed}" =~ ^[0-9]+$ ]] || fail "survival seed file is not a positive integer: ${seed_file}"
  printf '%s\n' "${seed}"
}

write_runtime_survival_config() {
  local config_file="$1"
  local seed="$2"
  local tmp
  local mapped

  [[ -f "${config_file}" ]] || fail "missing Hill175 runtime config: ${config_file}"
  tmp="$(mktemp)"
  awk '
    /^# BEGIN Hill175 installer-managed survival$/ { skip = 1; next }
    /^# END Hill175 installer-managed survival$/ { skip = 0; next }
    skip != 1 { print }
  ' "${config_file}" > "${tmp}"

  if grep -Eq '^survival:[[:space:]]*$' "${tmp}"; then
    rm -f "${tmp}"
    fail "runtime config has an unmanaged top-level survival block; remove it before installer-managed seed injection"
  fi

  mapped="$(mktemp)"
  awk -v overworld="${SURVIVAL_WORLD_NAME}" -v nether="${SURVIVAL_NETHER_NAME}" -v end="${SURVIVAL_END_NAME}" '
    function emit_survival_worlds() {
      if (inserted == 1) {
        return
      }
      print "  survival: " overworld
      print "  survival-nether: " nether
      print "  survival-end: " end
      inserted = 1
    }
    /^worlds:[[:space:]]*$/ {
      in_worlds = 1
      print
      next
    }
    in_worlds == 1 && /^[^[:space:]#][^:]*:[[:space:]]*$/ {
      emit_survival_worlds()
      in_worlds = 0
      print
      next
    }
    in_worlds == 1 && /^  survival(-nether|-end)?:[[:space:]]*/ {
      next
    }
    {
      print
    }
    END {
      if (in_worlds == 1) {
        emit_survival_worlds()
      }
    }
  ' "${tmp}" > "${mapped}"
  mv "${mapped}" "${tmp}"

  {
    printf '\n# BEGIN Hill175 installer-managed survival\n'
    printf 'survival:\n'
    printf '  seed: %s\n' "${seed}"
    printf '  difficulty: NORMAL\n'
    printf '  keep-inventory: false\n'
    printf '  mob-griefing: true\n'
    printf '  pvp: true\n'
    printf '# END Hill175 installer-managed survival\n'
  } >> "${tmp}"
  mv "${tmp}" "${config_file}"
}

set_server_property() {
  local properties_file="$1"
  local key="$2"
  local value="$3"
  local tmp

  [[ -f "${properties_file}" ]] || fail "missing server.properties: ${properties_file}"
  tmp="$(mktemp)"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { written = 0 }
    index($0, key "=") == 1 {
      print key "=" value
      written = 1
      next
    }
    { print }
    END {
      if (written == 0) {
        print key "=" value
      }
    }
  ' "${properties_file}" > "${tmp}"
  mv "${tmp}" "${properties_file}"
}

write_server_properties_seed() {
  local properties_file="$1"
  local seed="$2"

  set_server_property "${properties_file}" "level-name" "${PRIMARY_WORLD_NAME}"
  set_server_property "${properties_file}" "level-seed" "${seed}"
  set_server_property "${properties_file}" "generate-structures" "true"
  set_server_property "${properties_file}" "allow-nether" "true"
  set_server_property "${properties_file}" "difficulty" "normal"
  set_server_property "${properties_file}" "pvp" "true"
}

write_primary_transition_marker() {
  local marker="$1"
  local seed="$2"
  local manifest_hash="$3"

  {
    printf 'format=hill175-primary-trio-worldgen-v1\n'
    printf 'primary_world=%s\n' "${PRIMARY_WORLD_NAME}"
    printf 'survival_world=%s\n' "${SURVIVAL_WORLD_NAME}"
    printf 'survival_nether_world=%s\n' "${SURVIVAL_NETHER_NAME}"
    printf 'survival_end_world=%s\n' "${SURVIVAL_END_NAME}"
    printf 'seed=%s\n' "${seed}"
    printf 'manifest_sha512=%s\n' "${manifest_hash}"
  } > "${marker}"
}

validate_primary_transition_marker() {
  local marker="$1"
  local seed="$2"
  local manifest_hash="$3"

  [[ -f "${marker}" ]] || return 1
  grep -Fxq 'format=hill175-primary-trio-worldgen-v1' "${marker}" || fail "invalid primary-trio transition marker"
  grep -Fxq "primary_world=${PRIMARY_WORLD_NAME}" "${marker}" || fail "primary world marker mismatch"
  grep -Fxq "survival_world=${SURVIVAL_WORLD_NAME}" "${marker}" || fail "survival world marker mismatch"
  grep -Fxq "survival_nether_world=${SURVIVAL_NETHER_NAME}" "${marker}" || fail "survival nether marker mismatch"
  grep -Fxq "survival_end_world=${SURVIVAL_END_NAME}" "${marker}" || fail "survival end marker mismatch"
  grep -Fxq "seed=${seed}" "${marker}" || fail "survival seed marker mismatch"
  grep -Fxq "manifest_sha512=${manifest_hash}" "${marker}" || fail "worldgen manifest marker mismatch"
  return 0
}

read_manifest() {
  local manifest="$1"
  local header_seen=false
  local line
  local expected_index=0
  local load_order role dimension project_title slug project_id version_id version_number game_versions loader client_side server_side filename size sha512 sha1 download_url license_id license_url project_url extra

  PACK_FILENAMES=()
  PACK_SHA512S=()
  PACK_URLS=()

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line:0:1}" == "#" ]] && continue
    if [[ "${header_seen}" == false ]]; then
      [[ "${line}" == "${EXPECTED_HEADER}" ]] || fail "unexpected manifest header"
      header_seen=true
      continue
    fi

    IFS=$'\t' read -r load_order role dimension project_title slug project_id version_id version_number game_versions loader client_side server_side filename size sha512 sha1 download_url license_id license_url project_url extra <<< "${line}"
    [[ -z "${extra:-}" ]] || fail "manifest row ${expected_index} has unexpected extra columns"
    [[ "${expected_index}" -lt "${#EXPECTED_SLUGS[@]}" ]] || fail "manifest has more packs than expected"
    [[ "${load_order}" =~ ^[0-9]+$ ]] || fail "invalid load_order for ${slug:-unknown}"
    [[ "${load_order}" -eq $((expected_index + 1)) ]] || fail "unexpected load_order for ${slug:-unknown}"
    [[ "${slug}" == "${EXPECTED_SLUGS[expected_index]}" ]] || fail "unexpected pack slug at load order ${load_order}: ${slug}"
    [[ "${version_id}" == "${EXPECTED_VERSION_IDS[expected_index]}" ]] || fail "unexpected version id for ${slug}"
    [[ "${slug}" != "tectonic" && "${project_title}" != "Tectonic" ]] || fail "Tectonic is forbidden in the Hill175 Terralith stack"
    [[ "${loader}" == "datapack" ]] || fail "${slug} is not pinned as a datapack"
    [[ ",${game_versions}," == *",26.2,"* ]] || fail "${slug} is not pinned for Minecraft 26.2"
    [[ "${client_side}" == "optional" && "${server_side}" == "required" ]] || fail "${slug} is not server-side datapack content"
    [[ "${download_url}" == "https://cdn.modrinth.com/data/${project_id}/versions/${version_id}/${filename}" ]] || fail "${slug} download URL does not match its Modrinth IDs"
    [[ "${sha512}" =~ ^[0-9a-f]{128}$ ]] || fail "${slug} has an invalid SHA-512 hash"
    [[ "${sha1}" =~ ^[0-9a-f]{40}$ ]] || fail "${slug} has an invalid SHA-1 hash"
    [[ "${size}" =~ ^[0-9]+$ && "${size}" -gt 0 ]] || fail "${slug} has an invalid file size"

    PACK_FILENAMES+=("${filename}")
    PACK_SHA512S+=("${sha512}")
    PACK_URLS+=("${download_url}")
    expected_index=$((expected_index + 1))
  done < "${manifest}"

  [[ "${header_seen}" == true ]] || fail "manifest header was not found"
  [[ "${expected_index}" -eq "${#EXPECTED_SLUGS[@]}" ]] || fail "manifest pack count ${expected_index} did not match expected ${#EXPECTED_SLUGS[@]}"
}

is_selected_filename() {
  local filename="$1"
  local selected

  for selected in "${PACK_FILENAMES[@]}"; do
    [[ "${filename}" == "${selected}" ]] && return 0
  done
  return 1
}

download_pack_cache() {
  local cache_dir="$1"
  local index
  local filename
  local sha512
  local url
  local cache_file

  mkdir -p "${cache_dir}"
  for index in "${!PACK_FILENAMES[@]}"; do
    filename="${PACK_FILENAMES[index]}"
    sha512="${PACK_SHA512S[index]}"
    url="${PACK_URLS[index]}"
    cache_file="${cache_dir}/${filename}"
    if [[ -f "${cache_file}" ]] && ! verify_sha512 "${cache_file}" "${sha512}"; then
      rm -f "${cache_file}"
    fi
    if [[ ! -f "${cache_file}" ]]; then
      curl --fail --location --silent --show-error "${url}" --output "${cache_file}.tmp"
      verify_sha512 "${cache_file}.tmp" "${sha512}" || fail "downloaded ${filename} failed SHA-512 verification"
      mv "${cache_file}.tmp" "${cache_file}"
    fi
    verify_sha512 "${cache_file}" "${sha512}" || fail "cached ${filename} failed SHA-512 verification"
  done
}

install_cached_packs() {
  local datapacks_dir="$1"
  local cache_dir="$2"
  local index
  local filename
  local sha512
  local cache_file
  local target_file
  local existing

  mkdir -p "${datapacks_dir}"
  for index in "${!PACK_FILENAMES[@]}"; do
    filename="${PACK_FILENAMES[index]}"
    sha512="${PACK_SHA512S[index]}"
    cache_file="${cache_dir}/${filename}"
    target_file="${datapacks_dir}/${filename}"
    verify_sha512 "${cache_file}" "${sha512}" || fail "cached ${filename} failed SHA-512 verification"
    if [[ ! -f "${target_file}" ]] || ! verify_sha512 "${target_file}" "${sha512}"; then
      install -m 0640 "${cache_file}" "${target_file}"
    fi
    verify_sha512 "${target_file}" "${sha512}" || fail "installed ${filename} failed SHA-512 verification"
  done

  shopt -s nullglob
  for existing in "${datapacks_dir}"/*.zip; do
    if ! is_selected_filename "$(basename "${existing}")"; then
      fail "unexpected datapack zip in primary world datapacks folder: ${existing}"
    fi
  done
  shopt -u nullglob
}

validate_runtime_survival_config() {
  local config_file="$1"
  local tmp

  [[ -f "${config_file}" ]] || fail "missing Hill175 runtime config: ${config_file}"
  tmp="$(mktemp)"
  awk '
    /^# BEGIN Hill175 installer-managed survival$/ { skip = 1; next }
    /^# END Hill175 installer-managed survival$/ { skip = 0; next }
    skip != 1 { print }
  ' "${config_file}" > "${tmp}"
  if grep -Eq '^survival:[[:space:]]*$' "${tmp}"; then
    rm -f "${tmp}"
    fail "runtime config has an unmanaged top-level survival block; remove it before installer-managed seed injection"
  fi
  rm -f "${tmp}"
}

write_pregen_plan() {
  local target="$1"

  {
    printf 'Hill175 survival pregen plan\n'
    printf 'radius_blocks=%s\n' "${PREGEN_RADIUS_BLOCKS}"
    printf 'primary_world=%s\n' "${PRIMARY_WORLD_NAME}"
    printf 'survival_world=%s\n' "${SURVIVAL_WORLD_NAME}"
    printf 'survival_nether_world=%s\n' "${SURVIVAL_NETHER_NAME}"
    printf 'survival_end_world=%s\n' "${SURVIVAL_END_NAME}"
    printf 'installer_runs_pregen=false\n'
    printf 'notes=Run a Paper-compatible pregenerator manually after smoke testing if launch load requires it.\n'
  } > "${target}"
}

require_command curl
require_command awk
require_command cp
require_command grep
require_command od
require_command sha512sum

[[ -f "${MANIFEST}" ]] || fail "missing manifest: ${MANIFEST}"
mkdir -p "${RUNTIME_DIR}"
RUNTIME_DIR="$(cd "${RUNTIME_DIR}" && pwd -P)"
MANIFEST="$(cd "$(dirname "${MANIFEST}")" && pwd -P)/$(basename "${MANIFEST}")"

STATE_DIR="${RUNTIME_DIR}/assets/survival-worldgen"
CACHE_DIR="${RUNTIME_DIR}/assets/survival-worldgen-cache"
ARCHIVE_ROOT="${RUNTIME_DIR}/assets/survival-worldgen-archives"
PRIMARY_WORLD_DIR="${RUNTIME_DIR}/${PRIMARY_WORLD_NAME}"
DATAPACKS_DIR="${PRIMARY_WORLD_DIR}/datapacks"
SEED_FILE="${STATE_DIR}/survival-seed.txt"
MANIFEST_MARKER="${STATE_DIR}/installed-manifest.sha512"
PRIMARY_TRANSITION_MARKER="${STATE_DIR}/primary-trio-managed.env"
CONFIG_FILE="${RUNTIME_DIR}/plugins/Hill175/config.yml"
SERVER_PROPERTIES_FILE="${RUNTIME_DIR}/server.properties"

mkdir -p "${STATE_DIR}" "${CACHE_DIR}" "${ARCHIVE_ROOT}"
TRANSITION_MARKER_PATH="${PRIMARY_TRANSITION_MARKER}"
trap rollback_active_transition EXIT ERR
trap 'exit 130' INT
trap 'exit 143' TERM
read_manifest "${MANIFEST}"
manifest_hash="$(manifest_identity_sha512 "${MANIFEST}")"
installed_hash=""
if [[ -f "${MANIFEST_MARKER}" ]]; then
  installed_hash="$(tr -d '[:space:]' < "${MANIFEST_MARKER}")"
fi
if [[ -n "${installed_hash}" && "${installed_hash}" != "${manifest_hash}" ]]; then
  installed_manifest="${STATE_DIR}/installed-manifest.tsv"
  if [[ ! -f "${installed_manifest}" ]] || [[ "$(manifest_identity_sha512 "${installed_manifest}")" != "${manifest_hash}" ]]; then
    fail "a different survival worldgen manifest is already installed; do not mutate the long-lived survival world in place"
  fi
fi

write_seed_if_missing "${SEED_FILE}"
seed="$(seed_value "${SEED_FILE}")"
validate_runtime_survival_config "${CONFIG_FILE}"
[[ -f "${SERVER_PROPERTIES_FILE}" ]] || fail "missing server.properties: ${SERVER_PROPERTIES_FILE}"
download_pack_cache "${CACHE_DIR}"
if ! validate_primary_transition_marker "${PRIMARY_TRANSITION_MARKER}" "${seed}" "${manifest_hash}"; then
  archive_first_transition_worlds "${RUNTIME_DIR}" "${ARCHIVE_ROOT}"
  write_primary_transition_marker "${PRIMARY_TRANSITION_MARKER}" "${seed}" "${manifest_hash}"
fi

mkdir -p "${DATAPACKS_DIR}"
install_cached_packs "${DATAPACKS_DIR}" "${CACHE_DIR}"
write_server_properties_seed "${SERVER_PROPERTIES_FILE}" "${seed}"
write_runtime_survival_config "${CONFIG_FILE}" "${seed}"
install -m 0640 "${MANIFEST}" "${STATE_DIR}/installed-manifest.tsv"
printf '%s\n' "${manifest_hash}" > "${MANIFEST_MARKER}"
write_pregen_plan "${STATE_DIR}/pregen-plan.txt"

TRANSITION_ACTIVE=false
trap - EXIT ERR INT TERM

echo "Installed Hill175 survival worldgen datapacks into ${DATAPACKS_DIR}"
