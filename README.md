# Hill 175 Minecraft Competition Server

Paper 26.2 server plugin implementing the testable competition workflow only. School identity linking is intentionally unconfigured and uses an always-approve development adapter.

## Player workflow

```text
join with an offline nickname
-> spawn in the authentication lobby
-> first join: /register <username> <password> <repeatPassword>
-> receive a temporary school-link URL
-> development adapter approves the link automatically
-> teleport to the exhibition hub
-> use the Competition Compass or the titled player category guides
-> create The Journey, The Place, or The People entry
-> build in a protected plot/private world
-> invite one teammate with /team invite <nickname>
-> save up to three camera poses
-> set title + description
-> submit and lock the entry
```

Returning players use `/login <password>` on every connection. `/login` and `/register` are plugin commands and are not sent to public chat.
Production copies `server-config/spigot.yml` with `commands.log: false` so Paper does not write sensitive command arguments to console or `latest.log`. Passwords still appear in the player's own local command history, so competition passwords must be unique to this event.

## Included server behavior

- Offline-mode nickname protection with salted PBKDF2 password hashes.
- Always-approve School Identity adapter for development testing.
- Authentication lobby title, popup instructions, and private command workflow.
- Owner-provided exhibition hub plus three skinned category guides and a fourth Survival Guide Player NPC; left- and right-click both open the relevant GUI.
- Journey 64x64 outdoor plots.
- Place 32x32 interior shells.
- People private worlds cloned from the cached world built from the supplied `structure.nbt`; generated campus-planning terrain is used only when that file is absent.
- Maximum two category entries per participant and maximum two team members per entry.
- Compass entry/visitor GUI with player heads and an Entry Controls GUI for reset, submission lock, delete, and category change instead of separate hotbar items.
- Owner Creative Mode inside an owned entry; Spectator Mode outside it and while visiting.
- Reset, delete, category switch, team invite/accept/leave, title, description, submit, and unlock flows.
- Up to three explicitly numbered camera poses per entry, managed through the Camera Controls UI with confirmation before replacement or removal.
- Full-screen, no-zoom camera preview mode with title and persistent status bar, exact position/angle lock, clickable camera markers, an exit item, and an owner-only remove-current-camera item.
- Reset operations stay in a tracked in-progress state until world restoration finishes, then restore returning owners to Creative Mode.
- Block/entity/command/portal/explosion protections.
- Water, lava, and manually placed fire are allowed inside entry bounds; spread and boundary escape are blocked.
- TNT and end crystals may be placed decoratively but cannot explode. Sneak-punch an end crystal to remove it safely.
- Living mobs are blocked; armor stands, paintings, item frames, boats, minecarts, and other nonliving decorations remain usable within entry limits.
- YAML persistence in `plugins/Hill175/competition-data.yml`.
- Join, quit, and successful-authentication IP audit records in the same data file; operational purge remains scheduled for 30 days after the event once the event-end date is configured.

## Commands

| Command | Purpose |
|---|---|
| `/register <username> <password> <repeatPassword>` | Register the current offline nickname. |
| `/login <password>` | Authenticate a registered nickname. |
| `/hill175` or `/competition` | Open the competition GUI. |
| `/hub` | Return to the exhibition hub. |
| `/entry create <journey|place|people>` | Create an entry. |
| `/entry home` | Return to the current entry. |
| `/entry visit` | Browse all builds. |
| `/entry reset` | Restore the current build space. |
| `/entry delete` | Delete the current entry. |
| `/entry switch <category>` | Replace the current entry with another category. |
| `/entry title <text>` | Set the project title. |
| `/entry description <text>` | Set the short description. |
| `/entry submit` | Lock the entry after metadata and camera poses are ready. |
| `/entry unlock` | Resume editing before the future competition deadline system is enabled. |
| `/team invite <nickname>` | Invite a second participant to the current entry. |
| `/team accept <nickname>` | Accept a team invite. |
| `/team leave` | Leave the current team; a one-person entry is deleted. |
| `/camera` or `/camera save` | Open the numbered Camera Controls UI. |
| `/camera save <1-3>` | Save the current view to an explicit camera slot. |
| `/camera list` | List saved poses. |
| `/camera remove <1-3>` | Remove a pose. |

## Build and local smoke test

```powershell
.\gradlew.bat clean test jar
```

The built plugin is `build/libs/Hill-server-1.0-SNAPSHOT.jar`.

The local smoke runtime is intentionally excluded from Git. Use Paper 26.2 build 119 and Java 25 or newer. The production setup script downloads the pinned Paper build, verifies its SHA-256 checksum, installs the separately staged user-provided hub archive, and installs the systemd service.

## World assets

`server-assets/worlds.yml` is the machine-readable provenance manifest. Third-party world archives are never committed or republished. The main hub is the user-provided Minecraft 26.2 save and is packaged outside Git with `scripts/package-user-hub.ps1`; its checksum is pinned in the manifest and deployment scripts. The authentication lobby is the separately downloaded Small Medieval Church smoke asset. Journey and Place are generated by the plugin. People entries use the supplied `structure.nbt` when present, imported once into a cached template and cloned per entry.

Survival world generation is pinned separately in `server-assets/survival-worldgen-manifest.tsv`. The installer stages the official Modrinth datapack zips, verifies SHA-512 before moving a live world, and installs them into the primary `world/datapacks` folder before the primary survival trio `world`, `world_nether`, and `world_the_end` is generated. The survival seed is generated once, persisted outside Git in the runtime asset directory, and written to runtime `server.properties` as `level-seed`. On the first primary-world transition, the old primary `world` remains archived recoverably while every non-survival custom dimension namespace plus primary-root player data, stats, advancements, and scoreboard/custom data are copied back into the fresh primary world.

The installer also pins Chunky `1.5.3` from Modrinth as a Paper/Bukkit server plugin at `plugins/Chunky-Bukkit-1.5.3.jar`. It is for manual operator pregeneration after smoke testing and requires no client mod. Install scripts do not create a pregeneration task, but saved tasks are configured to continue safely after a Paper restart.

The local Hill campus `structure.nbt` can be regenerated from rights-cleared GIS, DEM, lidar, OSM, and orthophoto inputs:

```powershell
py -3 -m pip install -r scripts\requirements-hill-campus.txt
py -3 scripts\generate-hill-campus.py --scope phase1 --data-dir runtime\campus-data --max-trees 900
```

The current generated phase 1 campus asset is DataVersion `4903`, size `1338 x 117 x 1143`, `4,195,187` block records, SHA-256 `FCBBEF9200E73B04F1493BFB087B0E2FBF462AADB58DF7A3E1D336F82C34AA04`. Its provenance manifest and preview are written to `runtime/campus-output/hill-campus-phase1-manifest.json` and `runtime/campus-output/hill-campus-phase1-preview.png`. Use `--scope full` only for the larger property/golf-course candidate.

Do not deploy `combined_3d_tiles.glb`. The generated `structure.nbt` is the authorized Hill campus asset and is deployed separately because it is a large binary excluded from Git. Verify its SHA-256 against `server-assets/worlds.yml` before installation.

Before a first production install (or when the pinned hub changes), copy `runtime/assets/Hill175-Exhibition-Hub-2026-08-26.zip` to `/opt/hill175/assets/` on the server. The installer refuses a missing or checksum-mismatched hub instead of silently falling back to another map.

## Production deployment

Repository workflow:

```text
edit locally
-> .\gradlew.bat clean test jar
-> push to GitHub
-> plink to 135.181.78.188
-> cd /opt/Hill-server
-> git pull
-> bash scripts/install-server.sh
```

The service runs as `hill175` from `/opt/hill175`. Minecraft TCP listens on port `25566` so it does not interrupt the existing server on `25565`; connect with `135.181.78.188:25566`. No web endpoint is added by this server-only implementation.

The installer stops Paper before mutating runtime files, installs the selected survival datapacks, archives exact pre-transition world targets into `assets/survival-worldgen-archives/`, restores archived non-survival custom dimensions and primary-root state into the fresh `world`, and refuses to change the installed worldgen manifest later without a deliberate new-world operation.
