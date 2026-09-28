# Build and deploy Hill 175 from source

This guide builds and deploys the plugin with either Microsoft school verification
or explicitly acknowledged development authentication. The existing demo remains
in development mode. For school mode, complete the [Hill IT setup](microsoft-sso-setup.md)
and pilot through the real tenant, proxy and supported game clients.

## Versions and locations

| Item | Value |
| --- | --- |
| Source | `https://github.com/neilhuang007/Hill-server.git` |
| Build | JDK 25, checked-in Gradle wrapper |
| Runtime | Paper 26.2 build 119; pinned URL/hash in installer |
| Host | `135.181.78.188`, Debian/Ubuntu-style Linux x86-64 with systemd |
| Checkout | `/opt/Hill-server` |
| Server data | `/opt/hill175` owned by service user `hill175` |
| Java | `/opt/java25` (installer stages pinned Temurin JDK) |
| Service | `hill175.service` |
| Current game port | TCP `25566`; existing TCP `25565` service stays separate |
| Plugin output | `build/libs/Hill-server-1.0-SNAPSHOT.jar` |

The service requests 4–8 GiB JVM heap. Allow additional memory for the OS, source
build, and other services, plus disk for worlds and recoverable backups. A clean
checkout builds the plugin without GIS dependencies or reconstruction runtime data.

## 1. Build and validate locally

From the repository root with JDK 25 selected:

```powershell
.\gradlew.bat clean test jar
git diff --check
git status --short
```

Linux/macOS equivalent: `bash ./gradlew clean test jar`.
The Gradle suite checks Java behavior; it is not a replacement for
[in-game smoke testing](../SMOKE_TEST.md). The CI workflow repeats the source build
and script syntax checks on a clean Linux runner.

For a local Paper demo, stage the assets below, then use
`./ops/prepare-local-runtime.ps1`. It prepares `runtime/server/`; stop an existing
local Paper process before preparing or replacing its files. Start from that folder
with `java -Xms1G -Xmx2G -jar paper.jar nogui`. This local helper also uses development
authentication. It must never point at a personal Minecraft save.

## 2. Stage separately supplied assets

Git contains source and provenance, not worlds or third-party binaries. Required
deployment assets are:

| Asset | Local staging path | Server staging path |
| --- | --- | --- |
| Owner exhibition hub | `runtime/assets/Hill175-Exhibition-Hub-2026-08-26.zip` | `/opt/hill175/assets/Hill175-Exhibition-Hub-2026-08-26.zip` |
| Frozen v19 People template | `runtime/assets/campus/hill_people_template_campus_v19_2x.tgz` | `/opt/hill175/assets/campus/hill_people_template_campus_v19_2x.tgz` |

Package the owner-supplied hub with `ops/package-user-hub.ps1`; its expected source
save and hash are recorded in [worlds.yml](../../server-assets/worlds.yml).
Obtain the verified frozen campus ZIP from the project custodian, then run:

```powershell
uv run --python 3.13 python ops/package-campus-template.py
```

The packaging tool validates the source ZIP hash and imported-region CRCs, then produces a deterministic
template archive, excluding player state and dimension metadata. Its default
input is the ignored `runtime/campus-reconstruction/exports/` download. Compare
the resulting SHA-256 to [campus-template.env](../../server-assets/campus-template.env).
Do not invent a replacement asset when the exact input is unavailable.

Use PuTTY tools for this host:

```powershell
plink.exe -batch -i "C:/Users/neil_/.ssh/hetzner.ppk" root@135.181.78.188 "mkdir -p /opt/hill175/assets/campus"
pscp.exe -batch -i "C:/Users/neil_/.ssh/hetzner.ppk" "runtime/assets/Hill175-Exhibition-Hub-2026-08-26.zip" root@135.181.78.188:/opt/hill175/assets/
pscp.exe -batch -i "C:/Users/neil_/.ssh/hetzner.ppk" "runtime/assets/campus/hill_people_template_campus_v19_2x.tgz" root@135.181.78.188:/opt/hill175/assets/campus/
```

Verify the SSH host key against a trusted fingerprint before first use; subsequent
batch connections use PuTTY's stored key. Never bypass host-key validation.

The installer separately downloads pinned Paper, Java, Chunky, the temporary
authentication-lobby asset, and survival datapacks with checksum verification.
The lobby's public-use permission is unresolved in the provenance manifest;
replace it with an approved asset before the student event.

## 3. Push source, then pull on the server

Inspect the staged changes before committing. Keep secrets and generated output
out of Git; shared `.gitignore` and local `.git/info/exclude` cover them.

```powershell
git add <reviewed-source-paths>
git diff --cached --stat
git commit -m "Describe the server change"
git push origin main
plink.exe -i "C:/Users/neil_/.ssh/hetzner.ppk" root@135.181.78.188
```

Inside the SSH session, for a first checkout:

```bash
apt-get update
apt-get install -y git curl ca-certificates tar gzip unzip borgbackup util-linux python3
git clone https://github.com/neilhuang007/Hill-server.git /opt/Hill-server
cd /opt/Hill-server
```

For an existing checkout:

```bash
cd /opt/Hill-server
git status --short
git pull --ff-only origin main
git rev-parse HEAD
```

Stop if the remote checkout has unexplained edits or cannot fast-forward; preserve
them rather than resetting. Record the previous and new commit IDs for recovery.
Do not copy edited source or a local plugin JAR over the deployment checkout.

## 4. Back up, build, install

Schedule the restart around active users. On an existing service, create a verified
cold snapshot using `bash ops/backup-hill175.sh` after the Borg configuration below
is ready. A complete `/opt/hill175` snapshot while Paper is stopped is an alternative.
The installer's rollback directories do not replace a complete data backup.

For school verification, prepare `/etc/hill175/hill175.env` from
[.env.example](../../.env.example) and follow the [IT guide](microsoft-sso-setup.md).
Run the installer as root:

```bash
cd /opt/Hill-server
bash ops/install-server.sh --microsoft
```

For the controlled logistics demo only:

```bash
cd /opt/Hill-server
bash ops/install-server.sh --allow-development-auth
```

The demo flag explicitly acknowledges automatic development identity approval.
It creates a development environment file only if none exists. Neither mode
overwrites an existing environment file; mode mismatches are rejected. Microsoft
mode sets `online-mode=true` and missing/invalid SSO configuration stops Paper.

The installer builds and tests the plugin from the pulled source, checks staged
assets, stops Paper before world/config changes, preserves replaced maps, installs
the template and pinned worldgen inputs, then starts the service and verifies it.
It writes `eula=true`; the operator must accept Minecraft's EULA before using it.

Configuration is deployed from `server-config/` and `src/main/resources/config.yml`.
Local edits to the deployed defaults are overwritten on installation. Persistent
accounts, entries, inventories, worlds, and the generated survival seed stay under
the runtime. Authentication mode and credentials live in the separate root-owned
`/etc/hill175/hill175.env` (mode `0600`), loaded by systemd at startup. This file is
required by the installed unit and must be backed up separately from server data.

The new campus is a template for newly created People worlds. Existing entries
are preserved; an owner-requested reset recreates an entry using the current template.
The 1.21.11 source is imported by Paper 26.2; clients still use the server's version.

## 5. Verify the deployed service

```bash
systemctl is-active hill175.service
bash /opt/Hill-server/ops/verify-server.sh
journalctl -u hill175.service -n 100 --no-pager
systemctl status hill175-backup.timer --no-pager
```

Check for a new Paper ready marker, enabled Hill175 plugin, no startup errors,
the expected commit and plugin build, and the pinned template checksum/counts.
Then run the [smoke checklist](../SMOKE_TEST.md), especially:

1. Restricted lobby and authentication for the selected mode: Microsoft link/code
   and reconnect verification, or demo registration/password login.
2. Hub navigation, Journey/Place creation, permissions and submission lock.
3. New People entry with v19 terrain, safe ground spawn, campus chart, reset/reentry.
4. Owner and visitor camera previews: exit item selected, right/left-click exits,
   `/camera exit`, no visitor camera removal.
5. Existing People worlds and survival inventories remain intact after restart.

For bot checks, prepare `ops/prepare-smoke-bot.ps1` locally, set
`HILL175_SMOKE_HOST`, `HILL175_SMOKE_PORT`, and for remote runs
`HILL175_SMOKE_SKIP_LOCAL_WORLD_FILES=1`, then run
`node ops/smoke-player.mjs camera-view` or `people-campus-template`.
Bots create test accounts/entries: use a controlled runtime and do not treat their
success as real Java/Bedrock client or Microsoft SSO acceptance.

## Backups and recovery

The installer enables a daily cold Borg backup timer at 04:25 with up to 30 minutes
jitter. Configure `/etc/minecraft-backup.env` for the existing backup script;
protect it with root-only permissions. The script requires `BORG_REPO_PATH` and
any repository unlock credentials through Borg's supported environment mechanism.
Read `ops/backup-hill175.sh` for retention/runtime overrides. Initialize the Borg
repository deliberately and test restore; a scheduled timer alone proves no backup.
Hill runtime/service/retention settings are resolved from `HILL175_*` after loading
the credential file. Generic `SRV_DIR` or `SERVICE_NAME` values belonging to another
Minecraft installation must not select the Hill backup target. Check the archive
log and stored paths for `/opt/hill175`, not just a successful Borg exit code.

On startup/verification failure, the installer attempts to restore prior config,
plugin, template and imported worlds. It retains failed replacements when needed
for recovery. Inspect the error and `/opt/hill175/assets/` recovery paths before
retrying; do not delete the rollback evidence or restart repeatedly into bad data.
Microsoft-mode failures leave Paper stopped after restoring recoverable files;
they never automatically restart an older JAR that might lack school verification.
Confirm the restored plugin supports SSO and the environment/proxy remain valid
before reopening admission.

For manual recovery: stop `hill175.service`, preserve the failed runtime, restore
a coherent snapshot (plugin/config/data/worlds together), correct ownership, then
restart and repeat verification. Rebuild an earlier source revision only with its
matching asset pins. Never downgrade converted world files without restoring their
pre-conversion snapshot. Keep the other Minecraft service on port 25565 untouched.

## Network and Microsoft SSO

Current demo game traffic uses TCP 25566. Bedrock UDP ingress and Geyser/Floodgate
are **not installed by the installer**; follow the [IT guide](microsoft-sso-setup.md)
and record a compatible, tested stack.
Do not put Minecraft ports behind the ordinary Cloudflare HTTP proxy.

Browser authentication must follow browser → Cloudflare → nginx → loopback
identity service. Use Cloudflare Full (strict), a valid Origin CA certificate,
Authenticated Origin Pulls, and firewall ingress restricted to Cloudflare networks;
Origin CA by itself does not prevent direct-origin requests. Keep database/internal
plugin endpoints private. The [SSO architecture](../architecture/microsoft-sso.md)
describes claims, account-linking rules and implementation limits.
