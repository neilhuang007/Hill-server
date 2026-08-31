# Hill 175 Survival Worldgen

The public survival world uses a fresh Paper 26.2 vanilla-client datapack stack. The selected stack is pinned in `server-assets/survival-worldgen-manifest.tsv` from official Modrinth project/version API records:

- Terralith plus Terratonic for the Overworld. Tectonic is intentionally forbidden in the installer because Terralith datapack installs use Terratonic for this combination.
- Structory, Structory Towers, and Towns and Towers for additional Overworld structures.
- Incendium Legacy for the Nether.
- Nullscape for the End.

No Fabric, Forge, NeoForge, Quilt, shader, resource-pack, or client-required files from the cinematic profile are installed. Downloaded zip archives are fetched directly from Modrinth into the runtime asset cache and must not be committed or redistributed from this repository.

Chunky is installed separately as a Paper/Bukkit server plugin only for operator-controlled pregeneration after smoke testing. The pinned file is Modrinth project `fALzjamp`, version `MdY6JATr`, `Chunky-Bukkit-1.5.3.jar`, SHA-512 `43ffecc6e6a734b752da41575bbb316526c124c3f878942437d5133c377bfbd9b78bda975520dc074d7158c15dade58a444ccd0fd8d8a25d165b6fc450140422`. It requires no student client mod. The installer stages the plugin with restart-safe task continuation enabled; it does not create a pregeneration task.

## Runtime Layout

Paper reads datapacks from the primary world configured by `server.properties -> level-name=world`, so installers place the zips in:

```text
/opt/hill175/world/datapacks/
```

The survival area now uses Paper's primary world trio so Terralith, Incendium Legacy, and Nullscape dimension JSON overrides apply during generation:

```text
world
world_nether
world_the_end
```

The survival seed is generated once by the installer and persisted outside Git at:

```text
/opt/hill175/assets/survival-worldgen/survival-seed.txt
```

The same seed is written to runtime `server.properties` as `level-seed` before Paper starts. It is also injected into the runtime plugin config as a fallback, and the plugin's survival world names are rewritten to `world`, `world_nether`, and `world_the_end`. The source config remains seedless so a repository checkout does not accidentally pin or leak the production survival seed.

## Fresh World Policy

The first primary-trio transition is tracked by:

```text
/opt/hill175/assets/survival-worldgen/primary-trio-managed.env
```

If that marker is missing, the installer recoverably archives these exact live world targets when they exist:

```text
/opt/hill175/world
/opt/hill175/world_nether
/opt/hill175/world_the_end
/opt/hill175/hill_survival
/opt/hill175/hill_survival_nether
/opt/hill175/hill_survival_the_end
/opt/hill175/world/dimensions/minecraft/hill_survival
/opt/hill175/world/dimensions/minecraft/hill_survival_nether
/opt/hill175/world/dimensions/minecraft/hill_survival_the_end
```

The archive destination is `assets/survival-worldgen-archives/primary-trio-transition-<timestamp>/`. The installer keeps the full archived `world` recoverable, then copies safe primary-world state into the new `world` before Paper starts:

- Every `world/dimensions/<namespace>/*` custom dimension is restored. Within the `minecraft` namespace only, Paper's primary built-ins `overworld`, `the_nether`, and `the_end`, plus the old survival trio `hill_survival`, `hill_survival_nether`, and `hill_survival_the_end`, stay archived.
- This preserves arbitrary current or future competition dimensions such as `hill_auth`, `hill_hub`, `hill_journey`, `hill_place`, and `hill_people_*` without hardcoding the full set.
- Primary-root `world/players`, `world/playerdata`, `world/data`, `world/stats`, and `world/advancements` are copied back to preserve player/account, inventory, statistics, advancements, scoreboard, and custom world data that does not pin terrain generation.

The installer does not copy `level.dat`, `session.lock`, or old `datapacks`. It then recreates `world/datapacks` and installs the pinned datapacks before Paper starts. It never silently deletes these worlds.

After the marker exists, the installer verifies the marker/seed/manifest and preserves the generated primary trio. Changing worldgen after launch should be treated as a deliberate new-world operation, not an in-place update.

## Pregeneration Plan

Target pregen radius: 4000 blocks.

The installer records this plan in `assets/survival-worldgen/pregen-plan.txt` but does not create a pregeneration task. After the server smoke test proves the datapacks load cleanly, use Chunky manually if launch traffic needs it. Its managed config has `continue-on-restart: true`, so a saved task resumes under the normal systemd-managed Paper service after an interruption. Keep the Overworld, Nether, and End on the same manifest and seed.

## Smoke Test

Before students enter the world:

1. Start Paper 26.2 from a clean runtime after `scripts/install-server.sh` or `scripts/prepare-local-runtime.ps1`.
2. Confirm `/datapack list` shows the seven selected packs and no Tectonic pack.
3. Enter through the Survival Guide and confirm the destination is the primary `world`.
4. Confirm mobs, damage, hunger, death drops, explosions, fire behavior, and PvP follow normal survival rules.
5. Build and use Nether and End portals, confirming Paper's normal primary-world routing works across all three dimensions.
6. Locate at least one structure from Structory, Structory Towers, and Towns and Towers.
7. Review `logs/latest.log` for datapack parse errors, registry warnings, structure-set errors, or watchdog stalls.
