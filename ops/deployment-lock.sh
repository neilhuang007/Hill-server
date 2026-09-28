# Sourced by install/backup. FD 8 is inherited from deploy.ps1 when it owns the lock.
# Taking flock on the same inherited open file description is safe and reentrant.
hill175_lock=/run/lock/hill175-deploy.lock
if [[ "$(readlink /proc/self/fd/8 2>/dev/null || true)" != "${hill175_lock}" ]]; then
  exec 8>"${hill175_lock}"
fi
flock -n 8 || { echo "Another Hill deployment or backup is running; retry after it finishes." >&2; exit 1; }
