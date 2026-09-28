#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${HILL175_RUNTIME_DIR:-/opt/hill175}"
MANIFEST="${HILL175_WORLDGEN_MANIFEST:-${REPO_DIR}/server-assets/survival-worldgen-manifest.tsv}"
DATAPACKS_DIR="${RUNTIME_DIR}/world/datapacks"
SERVER_PROPERTIES="${RUNTIME_DIR}/server.properties"
PLUGIN_CONFIG="${RUNTIME_DIR}/plugins/Hill175/config.yml"
WORLDGEN_STATE_DIR="${RUNTIME_DIR}/assets/survival-worldgen"
SURVIVAL_SEED_FILE="${WORLDGEN_STATE_DIR}/survival-seed.txt"
PRIMARY_TRANSITION_MARKER="${WORLDGEN_STATE_DIR}/primary-trio-managed.env"
LAST_TRANSITION_ARCHIVE_FILE="${WORLDGEN_STATE_DIR}/last-transition-archive.txt"
EXPECTED_HEADER=$'load_order\trole\tdimension\tproject_title\tslug\tproject_id\tversion_id\tversion_number\tgame_versions\tloader\tclient_side\tserver_side\tfilename\tsize\tsha512\tsha1\tdownload_url\tlicense_id\tlicense_url\tproject_url'
CHUNKY_FILENAME="Chunky-Bukkit-1.5.3.jar"
CHUNKY_SHA512="43ffecc6e6a734b752da41575bbb316526c124c3f878942437d5133c377bfbd9b78bda975520dc074d7158c15dade58a444ccd0fd8d8a25d165b6fc450140422"
CHUNKY_CONFIG="${RUNTIME_DIR}/plugins/Chunky/config.yml"
source "${REPO_DIR}/server-assets/campus-template.env"
PEOPLE_TEMPLATE_ARCHIVE="${RUNTIME_DIR}/assets/campus/${PEOPLE_TEMPLATE_ARCHIVE_NAME}"
PEOPLE_TEMPLATE_DIR="${RUNTIME_DIR}/world-templates/${PEOPLE_TEMPLATE_ARCHIVE_ROOT}"

fail() {
  echo "verify-server failed: $*" >&2
  exit 1
}

verify_sha512() {
  local file="$1"
  local expected="$2"
  echo "${expected}  ${file}" | sha512sum --check --status
}

verify_sha256() {
  local file="$1"
  local expected="$2"
  echo "${expected}  ${file}" | sha256sum --check --status
}

count_mca_files() {
  local directory="$1"

  find "${directory}" -maxdepth 1 -type f -name 'r.*.mca' | wc -l | tr -d '[:space:]'
}

verify_worldgen_datapacks() {
  local header_seen=false
  local expected_count=0
  local line
  local load_order role dimension project_title slug project_id version_id version_number game_versions loader client_side server_side filename size sha512 sha1 download_url license_id license_url project_url extra
  local expected_files=()
  local existing
  local expected
  local found

  [[ -f "${MANIFEST}" ]] || fail "missing worldgen manifest: ${MANIFEST}"
  [[ -d "${DATAPACKS_DIR}" ]] || fail "missing datapacks directory: ${DATAPACKS_DIR}"

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line:0:1}" == "#" ]] && continue
    if [[ "${header_seen}" == false ]]; then
      [[ "${line}" == "${EXPECTED_HEADER}" ]] || fail "unexpected worldgen manifest header"
      header_seen=true
      continue
    fi
    IFS=$'\t' read -r load_order role dimension project_title slug project_id version_id version_number game_versions loader client_side server_side filename size sha512 sha1 download_url license_id license_url project_url extra <<< "${line}"
    [[ -z "${extra:-}" ]] || fail "manifest has unexpected extra columns"
    [[ "${slug}" != "tectonic" && "${project_title}" != "Tectonic" ]] || fail "Tectonic is forbidden in the installed worldgen stack"
    [[ "${loader}" == "datapack" ]] || fail "${slug} is not a datapack"
    [[ ",${game_versions}," == *",26.2,"* ]] || fail "${slug} is not pinned for Minecraft 26.2"
    [[ "${sha512}" =~ ^[0-9a-f]{128}$ ]] || fail "${slug} has an invalid SHA-512 hash"
    [[ -f "${DATAPACKS_DIR}/${filename}" ]] || fail "missing installed datapack: ${DATAPACKS_DIR}/${filename}"
    verify_sha512 "${DATAPACKS_DIR}/${filename}" "${sha512}" || fail "datapack hash mismatch: ${filename}"
    expected_files+=("${filename}")
    expected_count=$((expected_count + 1))
  done < "${MANIFEST}"

  [[ "${header_seen}" == true ]] || fail "manifest header was not found"
  [[ "${expected_count}" -eq 7 ]] || fail "expected 7 worldgen datapacks, found ${expected_count} in manifest"

  shopt -s nullglob
  for existing in "${DATAPACKS_DIR}"/*.zip; do
    found=false
    for expected in "${expected_files[@]}"; do
      if [[ "$(basename "${existing}")" == "${expected}" ]]; then
        found=true
        break
      fi
    done
    [[ "${found}" == true ]] || fail "unexpected datapack zip installed: ${existing}"
  done
  shopt -u nullglob
}

check_latest_log() {
  local latest_log="${RUNTIME_DIR}/logs/latest.log"
  local pattern='Failed to load datapack|Could not load datapack|Failed to parse|Couldn.t parse|registry.*error|Unknown registry|Missing required feature|watchdog|Exception|ERROR'

  [[ -f "${latest_log}" ]] || fail "missing latest log: ${latest_log}"
  grep -Fq 'Hill 175 competition server enabled with development identity linking.' "${latest_log}" \
    || fail "Paper started without the expected Hill175 development authentication provider"
  if grep -Eiq "${pattern}" "${latest_log}"; then
    grep -Ein "${pattern}" "${latest_log}" >&2
    fail "latest.log contains datapack, registry, watchdog, exception, or ERROR lines"
  fi
}

verify_chunky_plugin() {
  local plugin_path="${RUNTIME_DIR}/plugins/${CHUNKY_FILENAME}"
  local existing

  [[ -f "${plugin_path}" ]] || fail "missing pinned Chunky plugin: ${plugin_path}"
  verify_sha512 "${plugin_path}" "${CHUNKY_SHA512}" || fail "Chunky plugin hash mismatch: ${plugin_path}"
  [[ -f "${CHUNKY_CONFIG}" ]] || fail "missing managed Chunky config: ${CHUNKY_CONFIG}"
  require_line "${CHUNKY_CONFIG}" "continue-on-restart: true"
  require_line "${CHUNKY_CONFIG}" "update-interval: 60"
  shopt -s nullglob
  for existing in "${RUNTIME_DIR}"/plugins/*[Cc]hunky*.jar; do
    if [[ "$(basename "${existing}")" != "${CHUNKY_FILENAME}" ]]; then
      fail "unexpected Chunky plugin jar installed: ${existing}"
    fi
  done
  shopt -u nullglob
}

verify_people_template() {
  local marker
  local nested_dimensions
  local region_count
  local poi_count

  [[ -f "${PEOPLE_TEMPLATE_ARCHIVE}" ]] || fail "missing pinned People template archive: ${PEOPLE_TEMPLATE_ARCHIVE}"
  verify_sha256 "${PEOPLE_TEMPLATE_ARCHIVE}" "${PEOPLE_TEMPLATE_SHA256}" \
    || fail "People template archive hash mismatch: ${PEOPLE_TEMPLATE_ARCHIVE}"

  [[ -f "${PLUGIN_CONFIG}" ]] || fail "missing Hill175 plugin config: ${PLUGIN_CONFIG}"
  grep -Eq '^  template-folder:[[:space:]]*world-templates/hill_people_template[[:space:]]*$' "${PLUGIN_CONFIG}" \
    || fail "Hill175 config does not point People entries at world-templates/hill_people_template"
  grep -Eq '^  require-template:[[:space:]]*true[[:space:]]*$' "${PLUGIN_CONFIG}" \
    || fail "Hill175 config must fail closed when the People template is unavailable"
  grep -Eq "^  template-region-file-count:[[:space:]]*${PEOPLE_TEMPLATE_REGION_MCA_COUNT}[[:space:]]*$" "${PLUGIN_CONFIG}" \
    || fail "Hill175 config must require all ${PEOPLE_TEMPLATE_REGION_MCA_COUNT} campus region files"
  grep -Eq '^  template-poi-file-count:[[:space:]]*0[[:space:]]*$' "${PLUGIN_CONFIG}" \
    || fail "Hill175 config must require zero campus POI files"
  grep -Eq "^  structure-file:[[:space:]]*(''|\"\"|)[[:space:]]*$" "${PLUGIN_CONFIG}" \
    || fail "Hill175 config must leave people.structure-file blank for the Anvil template"

  [[ ! -L "${PEOPLE_TEMPLATE_DIR}" ]] || fail "People template path must not be a symlink: ${PEOPLE_TEMPLATE_DIR}"
  [[ -d "${PEOPLE_TEMPLATE_DIR}" ]] || fail "missing People template directory: ${PEOPLE_TEMPLATE_DIR}"
  [[ -f "${PEOPLE_TEMPLATE_DIR}/.hill175-people-ready" ]] || fail "missing People template ready marker"
  marker="$(tr -d '\r\n' < "${PEOPLE_TEMPLATE_DIR}/.hill175-people-ready")"
  [[ "${marker}" == "${PEOPLE_TEMPLATE_READY_MARKER}" ]] \
    || fail "People template marker was '${marker}', expected '${PEOPLE_TEMPLATE_READY_MARKER}'"
  [[ -f "${PEOPLE_TEMPLATE_DIR}/hill-campus-template.json" ]] \
    || fail "missing People template hill-campus-template.json"
  [[ -f "${PEOPLE_TEMPLATE_DIR}/hill-campus-template.yml" ]] \
    || fail "missing People template hill-campus-template.yml"
  [[ -d "${PEOPLE_TEMPLATE_DIR}/region" ]] || fail "missing People template region directory"
  if [[ "${PEOPLE_TEMPLATE_POI_MCA_COUNT}" != "0" ]]; then
    [[ -d "${PEOPLE_TEMPLATE_DIR}/poi" ]] || fail "missing People template POI directory"
  fi

  region_count="$(count_mca_files "${PEOPLE_TEMPLATE_DIR}/region")"
  [[ "${region_count}" == "${PEOPLE_TEMPLATE_REGION_MCA_COUNT}" ]] \
    || fail "People template has ${region_count} region MCA files; expected ${PEOPLE_TEMPLATE_REGION_MCA_COUNT}"
  poi_count="0"
  if [[ -d "${PEOPLE_TEMPLATE_DIR}/poi" ]]; then
    poi_count="$(count_mca_files "${PEOPLE_TEMPLATE_DIR}/poi")"
  fi
  [[ "${poi_count}" == "${PEOPLE_TEMPLATE_POI_MCA_COUNT}" ]] \
    || fail "People template has ${poi_count} POI MCA files; expected ${PEOPLE_TEMPLATE_POI_MCA_COUNT}"
  nested_dimensions="$(find "${PEOPLE_TEMPLATE_DIR}" -type d -name dimensions -print -quit)"
  [[ -z "${nested_dimensions}" ]] \
    || fail "People template contains nested dimensions directory: ${nested_dimensions}"
}

require_line() {
  local file="$1"
  local expected="$2"

  grep -Fxq "${expected}" "${file}" || fail "missing expected line in ${file}: ${expected}"
}

is_excluded_restored_dimension() {
  local name="$1"

  case "${name}" in
    overworld|the_nether|the_end|hill_survival|hill_survival_nether|hill_survival_the_end)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

verify_archived_primary_world_state_restored() {
  local archive_dir
  local source_root
  local destination_root
  local namespace_source
  local namespace
  local source
  local name
  local state_name

  [[ -f "${LAST_TRANSITION_ARCHIVE_FILE}" ]] || return
  archive_dir="$(tr -d '\r\n' < "${LAST_TRANSITION_ARCHIVE_FILE}")"
  [[ -n "${archive_dir}" ]] || fail "empty transition archive pointer: ${LAST_TRANSITION_ARCHIVE_FILE}"
  [[ -d "${archive_dir}" ]] || fail "missing transition archive directory: ${archive_dir}"

  source_root="${archive_dir}/world/dimensions"
  destination_root="${RUNTIME_DIR}/world/dimensions"
  if [[ -d "${source_root}" ]]; then
    shopt -s nullglob
    for namespace_source in "${source_root}"/*; do
      [[ -d "${namespace_source}" ]] || continue
      namespace="$(basename "${namespace_source}")"
      for source in "${namespace_source}"/*; do
        [[ -d "${source}" ]] || continue
        name="$(basename "${source}")"
        if [[ "${namespace}" == "minecraft" ]] && is_excluded_restored_dimension "${name}"; then
          continue
        fi
        [[ -d "${destination_root}/${namespace}/${name}" ]] || fail "archived custom dimension was not restored into new primary world: ${namespace}:${name}"
      done
    done
    shopt -u nullglob
  fi

  for state_name in players playerdata data stats advancements; do
    source="${archive_dir}/world/${state_name}"
    [[ -d "${source}" ]] || continue
    [[ -d "${RUNTIME_DIR}/world/${state_name}" ]] || fail "archived primary world ${state_name} directory was not restored"
  done
}

verify_primary_trio_seed_and_config() {
  local seed
  local old_name
  local nested

  [[ -f "${SURVIVAL_SEED_FILE}" ]] || fail "missing survival seed file: ${SURVIVAL_SEED_FILE}"
  seed="$(tr -d '[:space:]' < "${SURVIVAL_SEED_FILE}")"
  [[ "${seed}" =~ ^[0-9]+$ ]] || fail "survival seed file is not a positive integer"
  [[ -f "${PRIMARY_TRANSITION_MARKER}" ]] || fail "missing primary-trio transition marker: ${PRIMARY_TRANSITION_MARKER}"
  [[ -f "${SERVER_PROPERTIES}" ]] || fail "missing server.properties: ${SERVER_PROPERTIES}"
  [[ -f "${PLUGIN_CONFIG}" ]] || fail "missing Hill175 plugin config: ${PLUGIN_CONFIG}"

  require_line "${PRIMARY_TRANSITION_MARKER}" "format=hill175-primary-trio-worldgen-v1"
  require_line "${PRIMARY_TRANSITION_MARKER}" "primary_world=world"
  require_line "${PRIMARY_TRANSITION_MARKER}" "survival_world=world"
  require_line "${PRIMARY_TRANSITION_MARKER}" "survival_nether_world=world_nether"
  require_line "${PRIMARY_TRANSITION_MARKER}" "survival_end_world=world_the_end"
  require_line "${PRIMARY_TRANSITION_MARKER}" "seed=${seed}"

  require_line "${SERVER_PROPERTIES}" "level-name=world"
  require_line "${SERVER_PROPERTIES}" "level-seed=${seed}"
  require_line "${SERVER_PROPERTIES}" "generate-structures=true"
  require_line "${SERVER_PROPERTIES}" "allow-nether=true"
  require_line "${SERVER_PROPERTIES}" "difficulty=normal"
  require_line "${SERVER_PROPERTIES}" "pvp=true"

  require_line "${PLUGIN_CONFIG}" "  survival: world"
  require_line "${PLUGIN_CONFIG}" "  survival-nether: world_nether"
  require_line "${PLUGIN_CONFIG}" "  survival-end: world_the_end"
  require_line "${PLUGIN_CONFIG}" "  seed: ${seed}"

  for old_name in hill_survival hill_survival_nether hill_survival_the_end; do
    [[ ! -e "${RUNTIME_DIR}/${old_name}" ]] || fail "old custom survival world still exists live: ${RUNTIME_DIR}/${old_name}"
    nested="${RUNTIME_DIR}/world/dimensions/minecraft/${old_name}"
    [[ ! -e "${nested}" ]] || fail "old custom survival world still exists live: ${nested}"
  done

  verify_archived_primary_world_state_restored
}

systemctl is-active --quiet hill175.service
systemctl --no-pager --full status hill175.service
ss -ltnp | grep -E '(:25566)([[:space:]]|$)'
verify_chunky_plugin
verify_people_template
verify_worldgen_datapacks
verify_primary_trio_seed_and_config
require_line "${PLUGIN_CONFIG}" "  provider: always-approve-development-stub"
require_line "${PLUGIN_CONFIG}" "  development-stub-acknowledged: true"
check_latest_log
journalctl -u hill175.service -n 160 --no-pager | grep -E 'Hill175|Done \(|datapack|ERROR|WARN' || true
echo "File/log smoke checks passed. In-game smoke still must run /datapack list and survival chunk/structure checks."
