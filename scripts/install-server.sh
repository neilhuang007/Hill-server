#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="/opt/hill175"
JAVA_HOME="/opt/java25"
SERVICE_USER="hill175"

PAPER_URL="https://fill-data.papermc.io/v1/objects/a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629/paper-26.2-119.jar"
PAPER_SHA256="a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629"

JAVA_URL="https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jdk_x64_linux_hotspot_25.0.4.1_1.tar.gz"
JAVA_SHA256="dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e"

AUTH_URL="https://www.curseforge.com/api/v1/mods/1469713/files/8692252/download"
AUTH_SHA256="de98674487bcd69593c36a03b1204a7d14ff694f281508d156e53650e31e4630"

HUB_ARCHIVE_NAME="Hill175-Exhibition-Hub-2026-08-26.zip"
HUB_ARCHIVE_ROOT="Hill175 Exhibition Hub 2026-08-26"
HUB_SHA256="d6ebfc048b5dc3351191182255ce77fe101c373bd6bb8a3330d8fc2672c858de"

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

require_command curl
require_command tar
require_command unzip
require_command sha256sum
require_command systemctl

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

paper_target="${RUNTIME_DIR}/paper.jar"
if [[ ! -f "${paper_target}" ]] || ! verify_sha256 "${paper_target}" "${PAPER_SHA256}"; then
  curl --fail --location --silent --show-error "${PAPER_URL}" --output "${paper_target}.tmp"
  verify_sha256 "${paper_target}.tmp" "${PAPER_SHA256}"
  mv "${paper_target}.tmp" "${paper_target}"
fi

install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/build/libs/Hill-server-1.0-SNAPSHOT.jar" \
  "${RUNTIME_DIR}/plugins/Hill175.jar"
install -m 0640 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
  "${REPO_DIR}/server-config/server.properties" \
  "${RUNTIME_DIR}/server.properties"
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

auth_install_marker="${RUNTIME_DIR}/assets/.small-medieval-church-1.0.5-installed"
if [[ ! -f "${auth_install_marker}" ]]; then
  # The authentication world is immutable event scenery. Stop Paper before
  # replacing either its legacy world root or Paper's migrated dimension.
  systemctl stop hill175.service 2>/dev/null || true
  rm -rf "${RUNTIME_DIR}/hill_auth" \
         "${RUNTIME_DIR}/world/dimensions/minecraft/hill_auth"

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
  mv "${auth_extract}/Small Medieval Church 1.0.5" "${RUNTIME_DIR}/hill_auth"
  rm -rf "${auth_extract}"
  touch "${auth_install_marker}"
fi

hub_install_marker="${RUNTIME_DIR}/assets/.hill175-exhibition-hub-2026-08-26-installed"
installed_hub_sha=""
if [[ -f "${hub_install_marker}" ]]; then
  installed_hub_sha="$(tr -d '[:space:]' < "${hub_install_marker}")"
fi
if [[ "${installed_hub_sha}" != "${HUB_SHA256}" ]]; then
  hub_archive="${RUNTIME_DIR}/assets/${HUB_ARCHIVE_NAME}"
  if [[ ! -f "${hub_archive}" ]]; then
    echo "Missing user-provided hub archive: ${hub_archive}" >&2
    echo "Package it with scripts/package-user-hub.ps1 and stage it before running this installer." >&2
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
  systemctl stop hill175.service 2>/dev/null || true
  hub_backup="$(mktemp -d "${RUNTIME_DIR}/assets/hub-backup.XXXXXX")"
  hub_backup_has_world=false
  if [[ -d "${RUNTIME_DIR}/hill_hub" ]]; then
    mv "${RUNTIME_DIR}/hill_hub" "${hub_backup}/legacy"
    hub_backup_has_world=true
  fi
  if [[ -d "${RUNTIME_DIR}/world/dimensions/minecraft/hill_hub" ]]; then
    mv "${RUNTIME_DIR}/world/dimensions/minecraft/hill_hub" "${hub_backup}/modern"
    hub_backup_has_world=true
  fi
  if ! mv "${hub_extract}/${HUB_ARCHIVE_ROOT}" "${RUNTIME_DIR}/hill_hub"; then
    [[ -d "${hub_backup}/legacy" ]] && mv "${hub_backup}/legacy" "${RUNTIME_DIR}/hill_hub"
    if [[ -d "${hub_backup}/modern" ]]; then
      mkdir -p "${RUNTIME_DIR}/world/dimensions/minecraft"
      mv "${hub_backup}/modern" "${RUNTIME_DIR}/world/dimensions/minecraft/hill_hub"
    fi
    echo "Hub replacement failed; the previous world was restored." >&2
    exit 1
  fi
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

install -m 0644 "${REPO_DIR}/deploy/hill175.service" /etc/systemd/system/hill175.service
systemctl daemon-reload
systemctl enable hill175.service
systemctl restart hill175.service
systemctl --no-pager --full status hill175.service

echo "Hill 175 is installed. Minecraft TCP port 25566 must be allowed by the host firewall/provider firewall."
