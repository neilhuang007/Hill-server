#!/usr/bin/env bash
# Sourced by the installer and verifier. Reads server-assets/server-binaries.env
# as data: nothing in it is executed, and only the names below are accepted.

load_server_binaries() {
  local manifest="$1"
  local line name value
  local -A seen=()

  [[ -f "${manifest}" ]] || { echo "Missing server program list: ${manifest}" >&2; return 1; }
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line:0:1}" == "#" ]] && continue
    name="${line%%=*}"
    value="${line#*=}"
    case "${name}" in
      PAPER_URL|JAVA_LINUX_X64_URL|JAVA_WINDOWS_X64_URL|CHUNKY_URL)
        [[ "${value}" =~ ^https://[A-Za-z0-9._~/%+-]+$ ]] || { echo "Invalid ${name} in ${manifest}" >&2; return 1; }
        ;;
      PAPER_SHA256|JAVA_LINUX_X64_SHA256|JAVA_WINDOWS_X64_SHA256)
        [[ "${value}" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid ${name} in ${manifest}" >&2; return 1; }
        ;;
      CHUNKY_SHA512)
        [[ "${value}" =~ ^[0-9a-f]{128}$ ]] || { echo "Invalid ${name} in ${manifest}" >&2; return 1; }
        ;;
      CHUNKY_FILENAME)
        [[ "${value}" =~ ^[A-Za-z0-9._-]+\.jar$ ]] || { echo "Invalid ${name} in ${manifest}" >&2; return 1; }
        ;;
      *)
        echo "Unknown entry in ${manifest}: ${name}" >&2
        return 1
        ;;
    esac
    [[ -z "${seen[${name}]:-}" ]] || { echo "Duplicate ${name} in ${manifest}" >&2; return 1; }
    seen[${name}]=1
    printf -v "${name}" '%s' "${value}"
  done < "${manifest}"

  for name in PAPER_URL PAPER_SHA256 JAVA_LINUX_X64_URL JAVA_LINUX_X64_SHA256 \
      CHUNKY_FILENAME CHUNKY_URL CHUNKY_SHA512; do
    [[ -n "${seen[${name}]:-}" ]] || { echo "Missing ${name} in ${manifest}" >&2; return 1; }
  done
}
