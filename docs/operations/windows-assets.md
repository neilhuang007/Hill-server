# Windows map and server folder setup

Use the **asset handoff ZIP** supplied by the project owner. It contains the
campus and the exhibition hub as folders ready for the plugin, an optional Java
resource pack and checksums. The current campus is **V29**, an unfinished
exterior draft. Construction research and internal notes are not in the packet.

Every map is read from a designated folder beside `paper.jar`. Nothing in the
code names a map, a version or an archive: the folder's contents are the selection.

```text
<server>/
  paper.jar
  plugins/
    Hill175.jar
    Hill175/config.yml
  world-templates/
    hill_people_template/        campus (required)
      region/r.*.*.mca
      hill-campus-template.yml
    hill_hub/                    exhibition hub world save (required)
      level.dat
      hill-world.yml             arrival point and guide positions
      dimensions/...
    hill_auth/                   sign-in lobby world save (optional)
      level.dat
      hill-world.yml
```

## New server folder

1. Clone the GitHub repository. Create the server folder and extract the
   packet's `world-templates` folder into it. Compare file hashes with
   `SHA256SUMS` using `Get-FileHash`.
2. From the repository, in Windows PowerShell 5.1 or PowerShell 7:

   ```powershell
   .\ops\prepare-local-runtime.ps1 -Runtime D:\hill175-server
   ```

   Without `-Runtime` it prepares `runtime\server` in the checkout. It checks the
   map folders, uses an installed JDK 25 or newer (otherwise downloads the JDK
   listed in `server-assets\server-binaries.env`), builds and tests the plugin,
   downloads the listed Paper, Chunky and survival datapacks with checksum
   verification, and installs the configuration.
3. Start Paper with the command the script prints. On this first start the plugin
   imports the hub (and the lobby, if supplied) from `world-templates\`.

This helper sets up development sign-in for a demonstration. It is not a school
SSO or Windows service installer.

## Changing a map

Stop Paper, move the old folder aside as a backup, and put the new one in its
place; do not merge two revisions. Then start Paper.

- **Campus:** new People entries and explicit owner resets copy the folder.
  Existing participant worlds keep their data and geometry. The plugin requires
  nonempty, untruncated Anvil region files and uses any supplied bounds/spawn
  metadata. An invalid template blocks new entries/resets instead of creating a
  replacement flat campus.
- **Hub and lobby:** the plugin imports a changed folder on the next start and
  keeps the world it replaces under `replaced-worlds\<name>-<UTC time>\`. An
  unchanged folder is not imported again (`plugins\Hill175\imported-worlds.yml`
  records what was imported).

A hub or lobby folder is an ordinary Minecraft Java world save with `level.dat`
directly inside. To make one from a save folder or an exported ZIP, leaving
player data behind:

```powershell
.\ops\stage-world-template.ps1 -Source "<save folder or zip>" -Destination D:\hill175-server\world-templates\hill_hub
```

The map carries its own coordinates in `hill-world.yml`, so replacing a map
needs no configuration or code change:

```yaml
spawn: [70.5, 66.1, 42.5, 0.0, 0.0]        # x, y, z and optional yaw, pitch
npcs:                                      # hub only; any may be omitted
  journey: [70.5, 67.0, 70.5, 180.0, 0.0]
  place: [70.5, 75.0, 70.5, 180.0, 0.0]
  people: [70.5, 61.0, 70.5, 180.0, 0.0]
  survival: [70.5, 66.0, 31.5, 0.0, 0.0]
```

Without the file, players arrive at the save's own spawn and the guides stand
around it. An arrival point with nothing to stand on is ignored with a warning.

No lobby map is included in the packet. Without `hill_auth\` the server keeps the
lobby it already has, or builds its own plain one. Supply only a lobby map the
school is permitted to use.

## Existing server folder

To update a server that was set up by hand: stop Paper and back up the folder,
place the map folders as above, build with JDK 25 (`.\gradlew.bat clean test jar`)
and install `build\libs\Hill-server-1.0-SNAPSHOT.jar` as `plugins\Hill175.jar`.
In `plugins\Hill175\config.yml`, preserve other settings and use:

```yaml
worlds:
  authentication-template-folder: world-templates/hill_auth
  hub-template-folder: world-templates/hill_hub
people:
  template-folder: world-templates/hill_people_template
  require-template: true
  structure-file: ""
```

Paths are relative to the server folder; absolute paths also work. Coordinates
left in an older `config.yml` (`hub-spawn`, `authentication-spawn`, `hub-npcs`
positions) are still honored when a map supplies no `hill-world.yml`.

## Resource pack

Java players can enable `resourcepacks/Hill175-campus-resources.zip` in their
client's resource packs to get the asphalt slab/stair appearance. The pack is
optional for loading the world and does not install itself. Automatic delivery
requires hosting it and configuring Paper's resource-pack URL; Bedrock needs its
own compatible pack.

This is the map and folder procedure, not complete Windows service setup.
The [SSO guide](microsoft-sso-setup.md) explains required IT values and authentication
boundaries, but its systemd/nginx automation targets Linux. Nightly updates have
not been configured for the Windows host.
