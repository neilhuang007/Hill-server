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

The server saves an initial recovery point and another every five minutes.
Staff need `hill175.campus.rollback` (operators receive it by default).

1. `/campusbackup list` shows recent snapshots. Use a page number for older ones.
2. `/campusbackup save` creates a recovery point immediately.
3. `/campusbackup restore <backup> confirm` verifies the selected snapshot,
   saves the current campus, and stops the server for restoration.

The local preview supervisor and the supplied systemd service restart after a
requested restore. Students reconnect afterward.
Restore affects the whole campus, including all building changes since that
snapshot. It is not a rollback of one student's actions. Accounts and school
identity records remain current. The current campus is preserved before the
restore, so staff can recover from choosing the wrong snapshot.

Snapshots are stored in `campus-backups/shared-campus` inside the server folder.
The restore verifies file checksums before replacing the campus. An interrupted
replacement resumes from its saved request on startup. Backups remain on the
same disk and are retained until an operator archives them. Copy important
recovery points elsewhere for protection against disk failure.

The earlier private project worlds remain preserved. Shared building does not
require a project, review request, submission or merge.
