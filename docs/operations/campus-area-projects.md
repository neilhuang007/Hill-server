# Campus area projects

The Place category now offers a campus area project. Its existing storage identifier remains PLACE, so previous building projects and small plots keep their owners, worlds and submissions. Journey and People retain their purposes. New projects use V54, explicitly selected by Neil on October 29, 2026. V54 is an inspection draft, not a claim of completed campus appearance.

## Student journey

1. Sign in and use the Competition Compass or the Place guide.
2. Choose one of seven campus areas. Review its description and exact rectangles, then choose Build Here. A smaller single building project is also available.
3. Build in a private copy. The map outlines the editable rectangles in green. Space outside those rectangles remains protected, including gaps inside an area's overall bounding box.
4. Open Build Options for the boundary, team invitations, optional details and camera views. The main menu exposes incoming team invitations. Every invitation and edit is checked against the authenticated participant.
5. Save at least one camera view. Submit Entry leads to camera controls if no view exists. Otherwise, confirmation starts image generation, pauses editing, publishes the submission and locks the build.
6. Resume Editing withdraws the published submission and restores editing. Reset, delete, category changes and leaving a team have confirmations.

## Data and implementation

The seven areas preserve the inclusive rectangles in the campus workspace's `scripts/hill_owner_20261020.py`. They describe construction work areas, not surveyed property ownership. Their configuration is `hill-areas.yml`; a prepared campus may supply its own copy. Buildings keep the separate `hill-buildings.yml` catalog.

An entry persists both its outer world extent and the exact editable rectangles. These rectangles are frozen when the entry is created. Direct edits, fluids, pistons, growth and entity interactions use the same boundary decision. Catalog changes do not silently change existing permissions. Reset retains the saved boundary. Existing entries without rectangle data retain their original single region.

New area worlds copy the required Anvil terrain from `world-templates/hill_people_template`. Updating that template affects new entries and explicit resets. Existing student worlds are preserved. Stage an explicitly chosen campus with `ops/stage-campus-draft.py`; never select a revision by timestamp or highest number.

## Java and Bedrock

This revision is for local inspection only. Neil requested local addresses and no publication. No DNS records, remote server installation or public gallery were changed for this work.

Both editions join the same Paper server. Geyser translates the connection; Floodgate supplies the Bedrock identity. The entry, blocks, permissions, submission state and team rules live once on Paper. Microsoft mode associates each edition with the same school participant after verification. Demo nickname accounts remain separate identities.

The pinned deployment uses Paper 26.2, Geyser 2.12.1 build 1276, Floodgate 2.2.5 build 141 and ViaVersion 5.12.2. Geyser currently emulates Java 26.3 and supports Bedrock 26.40 through 26.60. ViaVersion connects that client protocol to Paper 26.2. See the [Geyser version documentation](https://geysermc.org/wiki/geyser/supported-versions/) and [ViaVersion release](https://github.com/ViaVersion/ViaVersion/releases/tag/5.12.2).

Java uses inventory buttons and Bedrock uses native forms with the same actions. Identical client rendering is not possible: resource packs, camera presentation, controls and some edition mechanics differ. Custom head textures need explicit Bedrock mappings and a generated pack, according to [Geyser's skull documentation](https://geysermc.org/wiki/geyser/custom-skulls/). Essential controls therefore use clear labels and ordinary item icons.

Bedrock 26.60 requires NetherNet. The managed bridge enables both transports: the configured base port serves legacy RakNet over UDP and built in signaling over TCP; the next port serves WebRTC over UDP. A future public deployment must block direct TCP access to signaling and use the optional Cloudflare and nginx project proxy with an Origin certificate, Cloudflare source restrictions and Authenticated Origin Pulls. The gallery binds to loopback. `HILL175_GALLERY_PUBLIC_URL` and `HILL175_BEDROCK_PUBLIC_URL` configure future public addresses; they are not set for local review. See [Geyser's transport migration guide](https://geysermc.org/blog/preparing-for-nethernet/).

## Offline world conversion

`ops/convert-world.py` uses checksum pinned Chunker 1.21.0. It snapshots a stopped world into a new output directory and converts only that copy. It refuses an active Java world lock, overlapping paths and an existing output. The original and intermediate snapshot are preserved.

```powershell
uv run --python 3.13 python ops/convert-world.py --source runtime/assets/campus-v54-area-projects --output runtime/conversions/campus-v54-bedrock --format BEDROCK_1_26_60 --java <JDK25>/bin/java.exe
```

The result is an offline world export. Hill accounts, teams, submissions, Java plugins and server rules are not portable Bedrock server programs. Inspect unsupported content, entities, inventories, redstone and resource packs before distributing a converted world. Running one shared Paper server avoids maintaining divergent live copies. See [Chunker's official repository](https://github.com/HiveGamesOSS/Chunker).

## Verification

`ops/run-campus-area-smoke.py` starts a disposable loopback server and drives two actual Java protocol players through area creation, building, team actions, cameras, submission and management. `ops/run-bedrock-smoke.py` separately checks real Bedrock packets through Geyser, secure admission rejection, gameplay, reconnect and restart. Use `--campus` to supply the explicitly prepared V54 folder. Test reports and native review limitations belong in the delivery record; automated packet results do not certify visual quality or physical controller ergonomics.

The [October 29 verification record](area-verification-20261029.md) records the completed player checks, conversion results and remaining native client review limits.

## Local inspection

The prepared preview lives under `%LOCALAPPDATA%/Hill175/runtime/area-bedrock-v54-20261029`. Its source and conversion artifacts remain in this repository's ignored runtime folder. The system drive fixture avoids slow runtime file reads observed during testing on E:.

```powershell
.\ops\local-preview.ps1 -Action Start
.\ops\local-preview.ps1 -Action Status
.\ops\local-preview.ps1 -Action Stop
```

Java uses `127.0.0.1:25568`; the gallery uses `http://localhost:8789`. Bedrock uses the private LAN address reported by Status, port `19134`, with WebRTC on UDP `19135`. No firewall or router ports are opened by this launcher. NetherNet cannot use a loopback game connection, so its local listener binds the private LAN interface. Xbox validation remains enabled. The development event password is separate from a Microsoft password. Stopping saves worlds and restores the secured managed bridge configuration.

The converted Bedrock import is `runtime/conversions/campus-v54-bedrock-20261029/Hill-Campus-V54.mcworld`. Both the original Java to Bedrock conversion and a Bedrock to Java 26.2 conversion completed with pinned Chunker. Conversion success does not establish identical rendering or lossless transfer of every edition specific mechanic.
