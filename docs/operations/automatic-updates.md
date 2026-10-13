# Nightly GitHub updates

After the initial [deployment](deployment.md) succeeds, a root-run systemd timer
can check GitHub `main` every night at **04:00 in the server's timezone**. A change
to deployment inputs runs the existing installer: build/test, cold Borg backup,
install, restart and verification. This disconnects connected players. Research,
construction and documentation-only changes are pulled without restarting Paper.

## Enable on the installation host

Publish the reviewed source changes to GitHub, then pull them into the clean
`main` checkout at `/opt/Hill-server`. Use PuTTY `plink` for SSH access. Complete
the normal manual installation once with this version of the installer, using
the host's configured authentication mode. This creates a successful-deployment
record at `/var/lib/hill175-update/deployed-commit`.

```bash
cd /opt/Hill-server
git pull --ff-only origin main
bash ops/install-server.sh --microsoft
# Controlled demo instead: bash ops/install-server.sh --allow-development-auth
bash ops/enable-auto-update.sh
timedatectl
systemctl list-timers hill175-update.timer --no-pager
```

The enabling command installs the units and starts the timer; it does not trigger
an immediate deployment. An existing Borg repository and protected backup
configuration must work before enabling updates. The hub and campus folders must
be staged under `/opt/hill175/world-templates/`. Keep only reviewed changes on `main`: the job executes that repository's
installer as root, so protect repository write access and review changes before
merging. Tests run on the host; the updater does not wait for GitHub Actions status.

Use HTTPS for `origin`. A private repository needs noninteractive, read-only Git
credentials installed separately for root. Do not put a token in the remote URL,
unit, repository or handoff. SSH remotes require PuTTY `plink`, a configured key
and a previously verified/cached host key; no SSH prompt can be answered by a timer.

## Behavior and failure recovery

- Only a clean `main` checkout with the expected GitHub origin can update. Dirty,
  ahead, diverged or rewritten history is rejected without resetting local work.
- Pulls use `--ff-only`. Successful installation is recorded independently from
  Git's current checkout, so a pull followed by a failed build is not success.
- The updater reads the existing protected authentication configuration; it never
  switches a Microsoft server to development authentication.
- Deployment and backup share the existing lock. Overlapping operations fail
  without restarting Paper; check the journal and run manually or wait until the
  next maintenance window. The daily backup timer also uses this lock.
- A stopped server stays stopped. A missed 04:00 run is skipped, including after
  boot; it does not cause an unexpected daytime restart.
- A failed or interrupted revision is recorded before installation and is not
  retried every night. Review the journal, correct the cause and run the manual
  installer to retry. A newer commit can be attempted if the server is active.
- The installer's rollback policy applies. In Microsoft mode, a failure after
  stopping Paper may leave it stopped for reviewed recovery. There is no promise
  of automatic recovery from every failed deployment or world-format migration.

The updater preserves the environment file and participant worlds. Installer
defaults under `server-config/` and plugin defaults are managed from Git and may
replace runtime edits, as in a manual deployment. Map content is separate: replace a designated folder under `world-templates/` during a
maintenance window to update it. The updater does not overwrite these folders or
publish/fetch private world assets from GitHub.

```bash
# Fetch/report available code without pulling, installing or restarting:
bash /opt/Hill-server/ops/update-server.sh --check

# Run during an approved maintenance window:
systemctl start hill175-update.service
journalctl -u hill175-update.service -n 100 --no-pager

# Pause future runs (does not interrupt an in-progress installation):
systemctl disable --now hill175-update.timer
```

Unit changes take effect after rerunning `ops/enable-auto-update.sh`; the normal
installer never enables unattended restarts by itself. Monitor the journal with
the host's existing monitoring; no email/Slack alerts are configured here.

References: [Git fast-forward pulls](https://git-scm.com/docs/git-pull) and
[systemd timer scheduling](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
