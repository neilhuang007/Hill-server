#!/usr/bin/env bash
set -euo pipefail

# Define the complete operation before pulling: Git may replace this script.
main() {
  local action="${1:---check}"
  [[ "$#" -le 1 && ( "${action}" == --check || "${action}" == --apply ) ]] || {
    echo "Usage: bash ops/update-server.sh [--check | --apply]" >&2; return 2;
  }
  [[ "${EUID}" -eq 0 ]] || { echo "Run as root." >&2; return 1; }
  umask 077
  local repo state deployed target current mode failed status
  repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  state="${HILL175_UPDATE_STATE_DIR:-/var/lib/hill175-update}"
  source "${repo}/ops/deployment-lock.sh"
  cd "${repo}"
  [[ "$(git branch --show-current)" == main ]] || {
    echo "Updates require the main branch." >&2; return 1;
  }
  [[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
    echo "Checkout has local changes; preserve/review them before updating." >&2; return 1;
  }
  case "$(git remote get-url origin)" in
    https://github.com/neilhuang007/Hill-server.git|git@github.com:neilhuang007/Hill-server.git) ;;
    *) echo "Unexpected Git origin; update refused." >&2; return 1 ;;
  esac
  [[ -f "${state}/deployed-commit" ]] || {
    echo "Run the current installer successfully once before enabling updates." >&2; return 1;
  }
  deployed="$(cat "${state}/deployed-commit")"
  [[ "${deployed}" =~ ^[0-9a-f]{40}$ ]] && git cat-file -e "${deployed}^{commit}" || {
    echo "Invalid deployment record; run a reviewed manual deployment." >&2; return 1;
  }
  # No credential prompts in unattended jobs; SSH access uses PuTTY plink.
  export GIT_TERMINAL_PROMPT=0
  export GIT_SSH_COMMAND='plink -batch'
  export GIT_SSH_VARIANT=plink
  git fetch --no-tags origin refs/heads/main
  target="$(git rev-parse FETCH_HEAD)"
  current="$(git rev-parse HEAD)"
  git merge-base --is-ancestor "${current}" "${target}" || {
    echo "Local main is ahead/diverged or GitHub history changed; update refused." >&2; return 1;
  }
  git merge-base --is-ancestor "${deployed}" "${target}" || {
    echo "GitHub main does not descend from the deployed revision; update refused." >&2; return 1;
  }
  echo "Deployed: ${deployed}; checkout: ${current}; GitHub main: ${target}"
  if [[ "${action}" == --check ]]; then
    echo "Check complete; no pull, installation or restart performed."
    return 0
  fi
  # Never reopen a deliberately stopped server or one awaiting failure recovery.
  if ! systemctl is-active --quiet hill175.service; then
    echo "Hill175 is not active; skipping unattended deployment."
    return 0
  fi
  if [[ "${current}" != "${target}" ]]; then
    git -c merge.autoStash=false -c rebase.autoStash=false pull --ff-only --no-rebase origin main
    [[ "$(git rev-parse HEAD)" == "${target}" ]] || {
      echo "GitHub main changed during this run; defer installation to the next run." >&2; return 1;
    }
  fi
  # Documentation/construction work can advance main without restarting Paper.
  # Keep the true deployed SHA so a failed install is never mistaken for success.
  if git diff --quiet "${deployed}" "${target}" -- \
      src build.gradle.kts settings.gradle.kts gradle.properties gradlew gradlew.bat gradle \
      ops server-config server-assets/campus-template.env server-assets/server-binaries.env \
      server-assets/bedrock-manifest.json server-assets/survival-worldgen-manifest.tsv; then
    echo "No deployment input changes; no restart needed."
    return 0
  fi
  failed=""
  if [[ -f "${state}/failed-commit" ]]; then failed="$(cat "${state}/failed-commit")"; fi
  [[ "${failed}" != "${target}" ]] || {
    echo "This revision already failed; review the journal and deploy manually to retry." >&2; return 1;
  }
  mode="$(python3 ops/check-auth-config.py --print mode)"
  local install_option
  case "${mode}" in
    microsoft) install_option=--microsoft ;;
    development) install_option=--allow-development-auth ;;
    *) echo "Cannot determine configured authentication mode." >&2; return 1 ;;
  esac
  # Record the attempt before invoking the installer, including interrupted runs.
  printf '%s\n' "${target}" > "${state}/failed-commit.tmp"
  mv "${state}/failed-commit.tmp" "${state}/failed-commit"
  echo "Deploying ${target} using the existing ${mode} authentication configuration."
  if bash ops/install-server.sh "${install_option}"; then
    [[ "$(cat "${state}/deployed-commit")" == "${target}" ]] || {
      echo "Installer did not record the requested revision; review manually." >&2; return 1;
    }
    rm -f -- "${state}/failed-commit"
    echo "Deployment verified: ${target}"
  else
    status=$?
    echo "Deployment failed (exit ${status}). Review journalctl -u hill175-update.service." >&2
    echo "The installer's recovery policy applies; Microsoft mode may remain stopped." >&2
    return "${status}"
  fi
}

main "$@"
