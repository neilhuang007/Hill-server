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
| Runtime | Paper 26.2 build 119; URL and checksum listed in `server-assets/server-binaries.env` |
| Host | `135.181.78.188`, Debian/Ubuntu-style Linux x86-64 with systemd |
| Checkout | `/opt/Hill-server` |
| Server data | `/opt/hill175` owned by service user `hill175` |
| Java | `/opt/java25` (installer stages the listed Temurin JDK) |
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

For a local Paper demo on Windows, put the map folders below in
`runtime/server/world-templates/`, then run `./ops/prepare-local-runtime.ps1`
(Windows PowerShell 5.1 or PowerShell 7). `-Runtime <folder>` prepares another
server folder. It uses an installed JDK 25 or newer, or downloads the listed one,
and prints the command that starts Paper. Stop a running local Paper first. This
helper uses development authentication. Never point it at a personal Minecraft save.

## 2. Stage separately supplied assets

The campus is selected by the contents of the server's
`world-templates/hill_people_template/` directory. The code does not pin a campus
revision, archive name or region-file count. A prepared folder contains `region/`
and optional `hill-campus-template.yml` bounds/spawn metadata. Replace the whole
folder while Paper is stopped, preserving the old folder separately. New entries
and explicit owner resets use it; existing participant worlds remain unchanged.
Do not merge region files from different revisions.

The current requested IT handoff is **V29**, an unfinished floating exterior draft
packaged from its preserved native Minecraft 26.1.2 conversion. This does not
claim that the existing deployed server was updated.

Every map is read from a designated folder under the server folder
(`/opt/hill175/` on Linux, the folder containing `paper.jar` on Windows). The code
names no map, version, archive or checksum; the folder's contents are the selection.

| Folder under `world-templates/` | Contents | Needed |
| --- | --- | --- |
| `hill_people_template/` | Campus: `region/` and optional metadata | Yes |
| `hill_hub/` | Exhibition hub world save, `level.dat` directly inside | Yes |
| `hill_auth/` | Sign-in lobby world save, `level.dat` directly inside | No |

A hub or lobby folder is an ordinary Minecraft Java world save. Paper imports it
when it next starts and records what it imported in
`plugins/Hill175/imported-worlds.yml`; unchanged folders are not imported again.
The world it replaces is kept under `replaced-worlds/<name>-<UTC time>/`. Without
a lobby folder the server keeps the lobby it already has, or builds its own plain
one. To build a folder from a save or an exported ZIP, leaving player data behind:

```powershell
./ops/stage-world-template.ps1 -Source <save folder or zip> -Destination <server>\world-templates\hill_hub
```

A map's coordinates travel with it in an optional `hill-world.yml` beside
`level.dat`. Without one, players arrive at the save's own spawn and the guides
stand around it.

```yaml
spawn: [70.5, 66.1, 42.5, 0.0, 0.0]        # x, y, z and optional yaw, pitch
npcs:                                      # hub only; any may be omitted
  journey: [70.5, 67.0, 70.5, 180.0, 0.0]
  place: [70.5, 75.0, 70.5, 180.0, 0.0]
  people: [70.5, 61.0, 70.5, 180.0, 0.0]
  survival: [70.5, 66.0, 31.5, 0.0, 0.0]
```

For Windows, use [the asset folder instructions](windows-assets.md).
Send the packet ZIP privately to the operator. Its README and `SHA256SUMS` explain
placement and verification. It excludes internal construction notes, research,
credentials and runtime account files. Deployment/SSO docs remain in GitHub.
The optional Java resource-pack ZIP requires client installation or separate
hosting; it does not install itself or provide Bedrock textures.

To package an explicitly selected prepared folder from the owner workspace:

```powershell
uv run --python 3.13 python ops/package-deployment-assets.py --campus-folder runtime/assets/campus-v29 --hub-folder runtime/server/world-templates/hill_hub --resource-pack server-assets/hill-exterior-asphalt-v1 --output runtime/handoff/Hill175-deployment-assets-v29-folders.zip
```

Use a new output filename for each handoff. The script preserves previous packets.
Only map data, `hill-world.yml`, template metadata, optional resource-pack assets,
checksums and the handoff README are included; player data is left out. Revision
numbers and timestamps never select assets automatically. `--lobby-folder` adds a
lobby map: use it only for a map the school may redistribute.

For transfers to the existing Linux host, use PuTTY `plink.exe`/`pscp.exe` with a
verified/cached host key. Transfer only assets; source changes still go through
GitHub and `git pull`. The installer checks the designated folders before it
stops Paper and never overwrites them.

The installer downloads Paper, Java and Chunky from the URLs listed with their
checksums in `server-assets/server-binaries.env`, and the survival datapacks from
`server-assets/survival-worldgen-manifest.tsv`. To move to another build, change
those lists; no script names a version. It downloads no map. The lobby used
during smoke testing is no longer offered by its creator's listing and its
public-use permission is unresolved, so it is not a deployment input:
supply an approved lobby map in `world-templates/hill_auth/`, or run with the
plugin's plain lobby.

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
apt-get install -y git curl ca-certificates tar gzip borgbackup util-linux python3 iproute2 nginx openssl
git clone https://github.com/neilhuang007/Hill-server.git /opt/Hill-server
cd /opt/Hill-server
mkdir -p /opt/hill175
```

Then copy the packet's `world-templates` folder to `/opt/hill175/world-templates`.
With the packet ZIP transferred to the host (no `unzip` package is needed):

```bash
python3 -m zipfile -e Hill175-deployment-assets-v29-folders.zip /root/hill175-assets
(cd /root/hill175-assets && sha256sum --check --quiet SHA256SUMS)
cp -a /root/hill175-assets/world-templates /opt/hill175/world-templates
```

The installer names the missing folder and changes nothing if a required map is absent.

A server installed before maps moved to these folders already has its campus in
`world-templates/hill_people_template`. Leave that folder as it is and add only
what is missing beside it:

```bash
cp -a /root/hill175-assets/world-templates/hill_hub /opt/hill175/world-templates/
```

Paper then imports the hub once on its next start and keeps the previous one
under `replaced-worlds/`. Without a `hill_auth` folder the installed lobby stays,
and players arrive at that world's own spawn point.

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

After initial host setup, use one command from a clean, committed local `main`:

```powershell
./ops/deploy.ps1 -Mode Microsoft
# Current controlled demo instead:
./ops/deploy.ps1 -Mode Development
```

This checks the checkout, pushes GitHub, connects through PuTTY, pulls with
`--ff-only`, requires that exact commit, and runs the installer. An unrecognized
SSH host key fails in PuTTY batch mode; verify/cache the host fingerprint during
initial access. Dirty or diverged checkouts are preserved and rejected. Deployment
output is retained in a root-only `/opt/hill175-deploy-<UTC>.log` on the server.

Schedule the restart around active users. Upgrades automatically take a cold Borg
snapshot and keep Paper stopped until installation is complete. A failed backup
blocks the upgrade. Configure and initialize Borg once as described below; the
rollback directories do not replace the full data backup. Deployment and scheduled
Hill backups share a lock, preventing overlapping service/world changes.

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
In Microsoft mode it also downloads checksum-pinned Geyser/Floodgate, generates
their configuration, verifies the UDP listener, and installs/reloads the protected
nginx site from the environment. Certificates and Cloudflare ranges are validated
before the outage. Managed Bedrock files participate in startup rollback. Secret
rotation needs no source changes; run the same command after updating the host file.
It writes `eula=true`; the operator must accept Minecraft's EULA before using it.

The installer waits 180 seconds for Paper to report ready and restores the previous
files if it does not. A first start on a slow host can be given longer:
`HILL175_STARTUP_WAIT_SECONDS=600 bash ops/install-server.sh --microsoft`.

Configuration is deployed from `server-config/` and `src/main/resources/config.yml`.
Local edits to the deployed defaults are overwritten on installation. Persistent
accounts, entries, inventories, worlds, and the generated survival seed stay under
the runtime. Authentication mode and credentials live in the separate root-owned
`/etc/hill175/hill175.env` (mode `0600`), loaded by systemd at startup. This file is
required by the installed unit and must be backed up separately from server data.

The new campus is a template for newly created People worlds. Existing entries
are preserved; an owner-requested reset recreates an entry using the current template.
The V29 packet contains Minecraft 26.1.2 region data for import by Paper 26.2; clients still use the server's version.

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
3. New People entry with the installed campus terrain, safe ground spawn, campus chart, reset/reentry.
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
plugin and imported hub/authentication worlds. The operator-managed map folders are never replaced by installation. It retains failed replacements when needed
for recovery. Inspect the error, `/opt/hill175/replaced-worlds/` and the
`/opt/hill175/assets/` recovery paths before retrying; do not delete the rollback evidence or restart repeatedly into bad data.
Microsoft-mode failures leave Paper stopped after restoring recoverable files;
they never automatically restart an older JAR that might lack school verification.
Confirm the restored plugin supports SSO and the environment/proxy remain valid
before reopening admission.

For manual recovery: stop `hill175.service`, preserve the failed runtime, restore
a coherent snapshot (plugin/config/data/worlds together), correct ownership, then
restart and repeat verification. Rebuild an earlier source revision only with its
matching program list and maps. Never downgrade converted world files without restoring their
pre-conversion snapshot. Keep the other Minecraft service on port 25565 untouched.

## Network and Microsoft SSO

Current demo game traffic uses TCP 25566. In Microsoft mode the installer installs
the pinned Geyser/Floodgate stack when Bedrock is enabled; IT supplies the UDP
firewall rule and real-client pilot described in the [IT guide](microsoft-sso-setup.md).
Do not put Minecraft ports behind the ordinary Cloudflare HTTP proxy.

Browser authentication must follow browser → Cloudflare → nginx → loopback
identity service. Use Cloudflare Full (strict), a valid Origin CA certificate,
Authenticated Origin Pulls, and firewall ingress restricted to Cloudflare networks;
Origin CA by itself does not prevent direct-origin requests. Keep database/internal
plugin endpoints private. The [SSO architecture](../architecture/microsoft-sso.md)
describes claims, account-linking rules and implementation limits.

## Optional automatic updates

After a successful initial deployment and backup setup, enable the
[nightly GitHub updater](automatic-updates.md) with
`bash ops/enable-auto-update.sh` on the host. It checks `main` at 04:00 server time
and uses the same build, backup, installation and verification workflow when
deployment inputs change. Enabling the timer is a separate operator action;
routine installation alone does not schedule automatic restarts.
