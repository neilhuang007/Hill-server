# Shared Hill campus

Neil selected V60 from `E:\projects\Hill-campus-work` as the starting campus
on November 3, 2026. The selection is recorded in
`server-assets/shared-campus-source.json`. It is still a visual review candidate.
The template seeds `hill_campus` once. Normal restarts preserve student work;
changing the template does not overwrite the shared campus.

## Join and build

The local Java preview is `127.0.0.1:25568`. Run
`.\ops\local-preview.ps1 -Action Start` to start it and use `-Action Stop`
to save and stop it. The preview uses development authentication:
`/register <password> <repeatPassword>`, then `/login <password>` on later visits.
Use a separate test password. This mode does not verify school membership.
Public school admission still requires the existing Hill IT setup.

Every signed in student arrives in the same Creative campus and can edit
anywhere inside its boundary. Hotbar slot 9 holds the campus map. Holding it
shows the official school illustration, even without a resource pack. Right
click it or use `/campus` to open the larger map screen. Java uses a native
dialog without the inventory panel. Accept the optional resource pack for
the larger illustration and its building zoom. Hover a printed map number to
see its name, then click that number to teleport directly. The Buildings list
also teleports directly. Named choices remain available if the pack is declined.
Bedrock uses native forms with building choices.

`/campus home` returns to campus. `/campus go <building>` travels directly.
Nearby building captions use Minecraft's action bar at the bottom center.
The artwork comes from the school's [official FY26 map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf).
It is an oblique illustration, so it does not display a position arrow. Each
number links to a reviewed campus destination, using the measured building
catalog or registered campus coordinates. There are 50 available destinations.
Number 28, Brookside Country Club, is outside the preserved campus and explains
this when hovered. [Destination provenance](campus-map-destinations.md) records
the mappings and the six approximate starting points.

To prepare the illustration again, download the PDF linked above and run
`uv run --python 3.13 --with pillow --with pymupdf python ops/build-official-campus-map.py --pdf <downloaded.pdf> --output <new-assets-folder>`.
The builder preserves existing output folders. With the server stopped, archive
the previous map assets and install `campus-pack.zip`, `campus-map.png`,
`campus-core.png`, `campus-held.png`, `campus-map-source.json` and
`campus-map-labels.json` in
`plugins/Hill175/gallery-assets`. Restart to load the held artwork and new pack
hash. Keep these generated assets outside Git. The source selection is recorded
in `server-assets/campus-map-source.json`.

Verify clickable artwork with
`uv run --python 3.13 --with pillow --with pymupdf python ops/check-official-map-labels.py --assets <assets-folder>`.
The default dialog renders a 360 pixel square illustration using a custom
bitmap font with native text click actions. It requires no client modification.
The dialog body reserves 370 pixels of width, including the client's four pixel
padding on each side. Negative spacing belongs only between image segments.
A spacing character at the end of a row makes the native height calculation
wrap that row again, even when the displayed row fits.
Check the installed client's actual font metrics and hit detection with
`./ops/check-official-map-dialog.ps1 -Pack <campus-pack.zip> -Labels <campus-map-labels.json>`.
For a live packet regression, set `HILL175_DIALOG_CAPTURE` to a new evidence
folder when running `node ops/smoke-campus-dialog.mjs`, then pass that folder as
`-DialogCapture <folder>` to the client check. This tests the delivered component
through the full native dialog widget, including its padding and height pass.
The label manifest must match the resource pack hash. If it is missing or
invalid, the image falls back to the item illustration and named destinations.

Verify that fallback image with
`./ops/check-official-map-dialog.ps1 -Pack <campus-pack.zip>` against the installed
26.3 client. The check uses Minecraft's actual item codec and render bounds.
Dialog width and height only reserve space; they do not enlarge an item model.
The pack therefore applies a local model transform as well as allowing drawing
beyond the normal item slot. Both image bounds must be `[0,0,256,256]`.

Hotbar slot 8 holds Undo. Right click it, choose Undo in the map screen, or use
`/campus undo` to reverse your block edits from the previous 15 seconds.
It processes your changes in reverse order and protects later edits by other
students. Doors and beds are handled together. Containers, other unsafe block
entities, flowing liquids, waterlogged blocks and falling blocks are excluded.
Undo does not rewind movement, chat or inventory transfers. It reports skipped
changes. Staff recovery points cover broader campus restoration.

Explosions, living mob spawning, spawn eggs, creature buckets, portals and
lava casting are blocked in the campus. Normal water and lava can flow inside
the campus boundary, but contact does not produce stone, cobblestone or obsidian.
These campus protections do not change the separate survival worlds.

## Staff recovery

The server saves an initial recovery point and another every five minutes using
[Restic](https://restic.readthedocs.io/en/stable/040_backup.html). Its compressed,
encrypted repository deduplicates data across recovery points. Unchanged campus
data is stored once. Each snapshot still represents the complete campus, so any
available area can be recovered independently from the same timestamp.
The five minute interval follows the wall clock rather than Minecraft tick speed.
If a restore is active when a backup becomes due, that backup runs when the
restore finishes.

[WorldEdit](https://worldedit.enginehub.org/en/latest/usage/snapshots/) restores
only the selected area's blocks and block entities, including chest contents.
Players stay connected. Account records, player inventories, free entities and
biomes are outside this area restore. Neighboring areas keep their current work.
Measured building footprints and exact construction area unions are reused.
Grounds tiles cover the rest of the campus. Every selection uses the world's
full build height and is clipped to the campus boundary.

Staff can use the recovery window without typing restore commands:

1. Right click the Campus Map and choose **Staff Recovery**.
2. Choose an area, then a saved timestamp.
3. Explore that version in a temporary world. The preview is read only.
4. Hotbar slot 1 holds **Confirm Restore**, slot 5 holds **Choose Another Version**,
   and slot 9 holds **Cancel Preview**. Right click the item to use it.
5. Confirm returns you to campus and restores only the selected area, with a new
   safety snapshot first. Cancel returns without changing the live campus.

Your inventory and movement settings are preserved. Disconnecting or restarting
ends the preview and recovers the inventory. Unused previews expire after ten
minutes, and up to three staff can preview independently. Temporary world data
is removed after use. `/campusbackup` opens the same recovery window.

The command controls remain available:

1. `/campusbackup here` shows the recovery areas covering your location.
2. `/campusbackup areas [page]` lists area IDs and names.
3. `/campusbackup list [page]` lists snapshot IDs and their UTC timestamps.
4. `/campusbackup save` creates a recovery point immediately.
5. `/campusbackup restore <snapshot> <area>` prepares a confirmation command.
6. `/campusbackup restore <snapshot> <area> confirm` verifies source data,
   creates a safety snapshot, and restores that area in small WorldEdit batches.

Building and interaction inside the selected area pause during recovery. Undo
pauses during an area restore. Other areas remain available. A persistent restore
request resumes on startup if the server stops during editing. Failed edits keep
the selected area locked and preserve the safety snapshot. Retry the recorded
snapshot and area to finish the request, then restore its safety snapshot if
needed. A source verification failure changes no blocks.

Use the installed [LuckPerms](https://luckperms.net/wiki/Permission-Commands)
from the server console to grant recovery access without operator privileges:

```text
lp user <player> permission set hill175.campus.rollback true
```

For access to one area only, use its exact permission node:

```text
lp user <player> permission set hill175.campus.rollback.area-s7 true
```

The player must sign in before using recovery commands. Bedrock uses the same
commands and permissions through Floodgate. Use the player's Floodgate UUID as
the LuckPerms subject for Bedrock accounts. Set the same permission
to `false` to revoke access. Area staff can list and create recovery points but
can restore only their assigned area. Do not grant broad WorldEdit or operator
permissions to this role.

Install the checksum verified Restic 0.19.1, WorldEdit 7.4.6 and LuckPerms 5.5.71
with `uv run --python 3.13 python ops/install-campus-recovery.py install --runtime <server>`
while Paper is stopped. The normal installer and new disposable fixtures do this
automatically. Existing local previews need the same one time installation.
Snapshot I/O runs away from the game thread, with world saving flushed and paused
until Restic finishes. Saving is restored after success, failure or shutdown.

The repository is `campus-backups/restic`; its required password file is
`campus-backups/restic-password`. Protect and back up both. Existing folder
snapshots in `campus-backups/shared-campus` are preserved as legacy recovery
material. The older pending whole campus recovery format remains readable.
Snapshots are retained until an operator archives them. The existing daily Borg
backup also captures the repository and key. Offsite storage remains an operator
responsibility.

Run `ops/run-campus-recovery-smoke.py` with the source runtime and unused ports
to test real Java and Bedrock staff clients, scoped authorization, confirmation,
area isolation, chest restoration, secure Xbox rejection and an actual scheduled
five minute snapshot. Evidence is written only in its disposable runtime.
Set `HILL175_RECOVERY_PREVIEW=1` for the window and hotbar workflow checks. This
mode also tests canceling, version switching, disconnecting and a server restart
while the preview is open.

The earlier private project worlds remain preserved. Shared building does not
require a project, review request, submission or merge.
