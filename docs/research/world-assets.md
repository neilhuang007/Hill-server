# Hill 175 Minecraft world asset research

Verified: 2026-08-26. Scope: downloadable Minecraft Java world/schematic/data-pack assets that can lawfully be used as a private Hill 175 competition server hub or category template. Exclusions: Google/Voxel Earth-derived geometry, pirated/reposted packs, Bedrock-only `.mcworld` assets, assets with no visible permission for server use, and assets whose source page could not be traced to the creator/platform listing.

## Recommendation

1. **Use `Server Spawn/Lobby` by `mikele12327` as the temporary polished hub/spawn candidate.**
   - It is already the candidate the project downloaded (`Server Spawn 1.03.zip`, CurseForge project `1421699`, file `7604500`).
   - It is a compact modern Java world archive, currently available from CurseForge/ForgeCDN, and the author explicitly permits personal/general use while prohibiting reuploading as your own.
   - Risk: CurseForge lists the project license as `All Rights Reserved`, so treat the author page text as a specific permission grant; keep attribution in `docs/credits/world-assets.md` or in a hub sign, do not redistribute the zip outside the server deployment, and replace with a custom Hill 175 hub before public launch if possible.
2. **Do not use downloaded third-party school/campus maps for Journey/People production templates.**
   - The Hill campus map should be generated in-house from rights-cleared school-provided/OSM/local survey inputs, not Google/Voxel Earth/Google Photorealistic 3D Tiles-derived geometry.
   - Generic school maps found on CurseForge are useful as style references only unless the author grants explicit server/event use.
3. **Use generated worlds/templates for build spaces.**
   - Journey: plugin-generated flat/void plot with pasted Hill-provided reference shell, not a public map.
   - Place: plugin-generated blank interior shells/classroom/dorm templates built in-house.
   - People: private copy of the rights-cleared Hill campus world once the campus generation pipeline is approved.
4. **Keep `Minecraft Universal Lobby Build (1.19.4)` as a manual fallback/import schematic only if attribution is acceptable.**
   - It explicitly permits server use with credit and modification, but the primary download endpoint is Planet Minecraft-protected and is a schematic rather than a complete ready-to-run server world.

## Candidates

### 1. `Server Spawn/Lobby` by `mikele12327` — hub/spawn world

- Fit: polished temporary hub/spawn world.
- Current availability: CurseForge page live; latest file `1.03`; uploaded `2026-02-10`; file ID `7604500`; ForgeCDN archive returned HTTP `200` and `application/zip` on 2026-08-26.
- License / usage: CurseForge project says `All Rights Reserved`; author description says anyone may use it for personal/general use and must not reupload it as their own.
- Project URL: https://www.curseforge.com/minecraft/worlds/server-spawn-lobby
- File URL: https://www.curseforge.com/minecraft/worlds/server-spawn-lobby/files/7604500
- Direct archive: https://edge.forgecdn.net/files/7604/500/Server%20Spawn%201.03.zip
- Filename: `Server Spawn 1.03.zip`.
- Size: CurseForge reports `3.2 MB`; HEAD reports `3323473` bytes.
- Decision: **use now for testing/staging hub**; add visible credit; do not redistribute zip.

### 2. `Minecraft Universal Lobby Build (1.19.4)` by `superscratch4` — alternative hub schematic

- Fit: alternative hub/lobby schematic.
- Current availability: Planet Minecraft page live; page lists 100% complete, download/schematic option, Minecraft `1.19.4`; author says it can be uploaded to newer versions.
- License / usage: author permits multiplayer/server/live-event use, modification, and server use if credit is given somewhere.
- Project URL: https://www.planetminecraft.com/project/minecraft-universal-lobby-build-1-19-4/
- Observed PMC mirror endpoint: https://www.planetminecraft.com/project/minecraft-universal-lobby-build-1-19-4/download/mirror/680110/
- Filename: not exposed in page text; treat as manual browser download/import.
- Decision: **fallback only**; good rights language, but schematic workflow/manual download adds setup friction.

### 3. `Vanila Lobby for Servers` by `TheDukDev` — lobby datapack reference

- Fit: auth/lobby dimension datapack; not a polished visual hub.
- Current availability: Modrinth page/API live; version `1`; version ID `oDQkv55l`; Minecraft Java `1.19.4-1.20.4`; datapack only.
- License / usage: Modrinth lists `CC-BY-SA-4.0`.
- Project URL: https://modrinth.com/datapack/vanila-lobby-for-servers
- Version URL: https://modrinth.com/datapack/vanila-lobby-for-servers/version/1
- API URL: https://api.modrinth.com/v2/version/oDQkv55l
- Direct archive: https://cdn.modrinth.com/data/v8OhGqI4/versions/oDQkv55l/lobby-1.19.4-plus.zip
- Filename: `lobby-1.19.4-plus.zip`.
- Size/hash: `3133` bytes; SHA1 `d9546461698364148a0536975ed0de1be0bfb59d`.
- Decision: **do not use as main hub**; keep as reference/fallback for lobby-dimension mechanics only; not verified for 26.2.

### 4. `"Worlds" - Server Lobby/Spawn [FREE DOWNLOAD]` by `EvilMuffin253` — old legal fallback

- Fit: legal fallback hub/spawn, visually old.
- Current availability: Planet Minecraft page live; PMC lists downloadable map; 2014 asset.
- License / usage: author explicitly grants permission for public-server use and states the purpose is download/run on servers.
- Project URL: https://www.planetminecraft.com/project/worlds---server-lobbyspawn-free-download/
- Observed PMC mirror endpoint: https://www.planetminecraft.com/project/worlds---server-lobbyspawn-free-download/download/mirror/456118/
- Filename: not exposed in page text.
- Decision: **avoid unless needed**; rights are clear, but age/visual quality likely below Hill 175 standard.

### 5. `Middle School` by `MrBickmann` — reference only

- Fit: possible style reference for Journey/Place school scale.
- Current availability: CurseForge page live; project ID `916088`; latest file `Middle School 1.20.4 (2).zip`; file ID `8597445`; uploaded `2026-08-07`; Minecraft `26.2`.
- License / usage: CurseForge lists `All Rights Reserved`; page description does not grant server/event reuse.
- Project URL: https://www.curseforge.com/minecraft/worlds/middle-school
- File URL: https://www.curseforge.com/minecraft/worlds/middle-school/files/8597445
- Filename: `Middle School 1.20.4 (2).zip`.
- Decision: **do not use in server**; use only as visual/reference unless direct written permission is obtained.

### 6. `Nothing by ManojTheReaper` — rejected void template

- Fit: empty/void template.
- Current availability: CurseForge search/page snippets show project ID `1582718`; latest `Nothing.zip`; Minecraft `26.2`; uploaded `2026-06-21`.
- License / usage: no explicit server-use permission found in verified page snippets; do not assume rights from availability.
- Project URL: https://www.curseforge.com/minecraft/worlds/nothing-by-manojthereaper
- Filename from listing: `Nothing.zip`.
- Decision: **do not use**; generate a void/flat template in-house instead.
## Source notes

### `Server Spawn/Lobby` by `mikele12327`

- Official project page: https://www.curseforge.com/minecraft/worlds/server-spawn-lobby
- Official file page: https://www.curseforge.com/minecraft/worlds/server-spawn-lobby/files/7604500
- Project facts verified from the CurseForge page:
  - Project ID `1421699`.
  - Category `Worlds` / `Creation` / `Game Map`.
  - License shown as `All Rights Reserved`.
  - Main file `1.03`, file name `Server Spawn 1.03.zip`.
  - File ID `7604500`.
  - Uploaded `Feb 10, 2026`.
  - Supported versions listed include `1.21.11`, `1.21.10`, `1.21.9`, `1.21.8`, `1.21.7`, `1.21.6`, `1.21.5`, `1.21.4`, `1.21.3`, `1.21.2`, `1.21.1`, `1.21`, `1.20.x`, `1.19.x`, `1.18.x`, `1.17.x`, `1.16.x`, `1.15.x`, `1.14.x`, `1.13.x`, plus snapshot tags.
- Rights text verified on project page: author permits personal/general use and forbids reuploading as your own.
- Direct archive tested with HEAD on 2026-08-26:
  - `https://edge.forgecdn.net/files/7604/500/Server%20Spawn%201.03.zip`
  - Response: HTTP `200`, `application/zip`, `3323473` bytes.
- Server-use action:
  - Download archive from ForgeCDN/CurseForge.
  - Extract to a staging world folder.
  - Open once in Paper 26.2 test server and run region upgrade before production use.
  - Add in-game/world-assets credit: `Server Spawn/Lobby by mikele12327, CurseForge project 1421699`.
  - Do not publish the archive on the Hill website or repo.

### `Minecraft Universal Lobby Build (1.19.4)` by `superscratch4`

- Official project page: https://www.planetminecraft.com/project/minecraft-universal-lobby-build-1-19-4/
- Observed PMC mirror endpoint: https://www.planetminecraft.com/project/minecraft-universal-lobby-build-1-19-4/download/mirror/680110/
- Project facts verified from the Planet Minecraft page:
  - Published `Apr 11, 2023`; updated `Jun 1, 2023`.
  - 100% complete.
  - Download type shown as `Free Download Schematic`.
  - Described as a lobby with spawn, leaderboard, abandoned house, and teleporter doors.
  - Version stated as `1.19.4`; author says it can be uploaded to any Minecraft version but warns versions before 1.19 will not load newer blocks.
- Rights text verified on project page:
  - May be used for a multiplayer server/live event.
  - May be changed as needed.
  - May be used on any server if credit is given somewhere.
- Availability constraint:
  - Planet Minecraft blocks automated HEAD/download checks from this environment with Cloudflare; use browser/manual download or an approved server-side browser session.
- Server-use action:
  - Manual download from PMC.
  - Import schematic into a generated hub world using WorldEdit/FAWE as staff.
  - Add credit sign/about-page entry before launch.

### `Vanila Lobby for Servers` by `TheDukDev`

- Official project page: https://modrinth.com/datapack/vanila-lobby-for-servers
- Official version page: https://modrinth.com/datapack/vanila-lobby-for-servers/version/1
- Official API version record: https://api.modrinth.com/v2/version/oDQkv55l
- Project/version facts verified from Modrinth page/API:
  - Version ID `oDQkv55l`, project ID `v8OhGqI4`.
  - Filename `lobby-1.19.4-plus.zip`.
  - Direct file URL `https://cdn.modrinth.com/data/v8OhGqI4/versions/oDQkv55l/lobby-1.19.4-plus.zip`.
  - SHA1 `d9546461698364148a0536975ed0de1be0bfb59d`; SHA512 `f99124dc2880041fcde8b918780b62dcfcc28d3a89913de6eecb7e1100e74b6fdd47e9af293495e8ea69409803acd9a740a97e2e2f78ce561f2ff4a678255538`.
  - Minecraft Java `1.19.4`, `1.20`, `1.20.1`, `1.20.2`, `1.20.3`, `1.20.4`.
  - Loader/platform `datapack`.
  - License `CC-BY-SA-4.0`.
- Direct archive tested with HEAD on 2026-08-26:
  - Response: HTTP `200`, `application/zip`, `3133` bytes.
- Server-use action:
  - Do not use as visual hub.
  - If used, comply with CC-BY-SA attribution/share-alike requirements and test compatibility because it is not marked for 26.2.

### `"Worlds" - Server Lobby/Spawn [FREE DOWNLOAD]` by `EvilMuffin253`

- Official project page: https://www.planetminecraft.com/project/worlds---server-lobbyspawn-free-download/
- Observed PMC mirror endpoint: https://www.planetminecraft.com/project/worlds---server-lobbyspawn-free-download/download/mirror/456118/
- Project facts verified from Planet Minecraft page:
  - Published `Nov 30, 2014`; updated `Dec 14, 2014`.
  - 100% complete.
  - Download type shown as `Downloadable Map`.
- Rights text verified on project page:
  - Explicit permission for public-server use.
  - Author states the build was made for people to download and run on servers.
- Availability constraint:
  - Planet Minecraft blocks automated HEAD/download checks from this environment with Cloudflare; use browser/manual download.
- Server-use action:
  - Keep only as legal fallback if CurseForge candidate fails.
  - Upgrade/test thoroughly because the map is old.

### Rejected / reference-only assets

- `Middle School` by `MrBickmann`
  - Official project page: https://www.curseforge.com/minecraft/worlds/middle-school
  - Official file page: https://www.curseforge.com/minecraft/worlds/middle-school/files/8597445
  - Useful facts: project ID `916088`; latest file `Middle School 1.20.4 (2).zip`; file ID `8597445`; uploaded `Aug 7, 2026`; Minecraft `26.2`; page describes hallways, classrooms, lunchroom, library, gym, pool, fields, and unfurnished spaces.
  - Rejection reason: CurseForge lists `All Rights Reserved`, and no explicit server/event usage permission was found on the page. Do not place this map on the Hill server unless written permission is obtained from the author.
- `Nothing by ManojTheReaper`
  - Official project page: https://www.curseforge.com/minecraft/worlds/nothing-by-manojthereaper
  - Search/page snippets identify a 26.2 `Nothing.zip` void world.
  - Rejection reason: no explicit server-use permission found; a void/flat template is trivial to generate in-house and avoids third-party rights risk.
- Minecraft Education lesson worlds, including `Digital Classroom`.
  - Rejection reason: primarily Bedrock/Education `.mcworld` format and tied to Minecraft Education distribution/use, not a Java Paper server asset pipeline.
- BlockMySchool.
  - Rejection reason: site currently emphasizes Bedrock `.mcworld`; not a Java world source for the Paper server; school identity/location outputs need legal review before use.
- Google/Voxel Earth/Google Photorealistic 3D Tiles-derived worlds.
  - Rejection reason: previous repo note flags derivative/export rights risk; excluded from this search by requirement.

## Download/deployment notes for the server operator

- Download only from the project page or the direct CDN URLs above.
- Store downloaded third-party zips outside the public repo, e.g. `/opt/hill175/assets/originals/`, with a checksum and source URL manifest.
- Extract into staging, not directly into production:
  - `assets/originals/Server Spawn 1.03.zip` -> `staging/worlds/server-spawn-lobby-1.03/` -> Paper upgrade test -> sanitized copy -> production hub import.
- Keep attribution in both places:
  - `docs/credits/world-assets.md` in repo.
  - A small in-game credit sign or credits NPC in a staff-only/credits corner of the hub.
- Never redistribute third-party map zips through the launcher, website, GitHub repo, or student download package.
- If Hill needs a public showcase/archive download later, use only original Hill-created worlds or obtain explicit written redistribution rights.
