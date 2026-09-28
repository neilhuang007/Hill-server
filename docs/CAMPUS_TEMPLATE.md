# Anniversary campus template

The competition's People category now uses the frozen **campus v19 at two blocks per metre**. Construction remains paused. This is the same authored geometry as the verified 1.21.11 download, packaged as overworld regions for Paper 26.2. The generic local campus launcher remains a separate v14 selection.

## Package and install

Obtain the verified `Hill-School-175th-v19-Java-1.21.11.zip` from the campus artifact handoff. Its SHA-256 is `afd71210f650f3e5adea9d4d6859b3c5295b1314b2330788af0bafbce0bd8c0f`. Place it under `runtime/campus-reconstruction/exports/`, then run from the repository root:

```sh
python3 ops/package-campus-template.py
```

On the project Windows workstation, use `uv run --python 3.13 python ops/package-campus-template.py`. The script uses only Python's standard library. It checks the source checksum and ZIP CRC, copies all 25 overworld regions byte for byte, and produces a deterministic archive at `runtime/assets/campus/hill_people_template_campus_v19_2x.tgz`.

The archive's pinned SHA-256 is `b913315523e35b8231b8a56647179830d5e8c4099e2908d610f1ef2ff320598e`; the installer reads this and the expected file counts from [`server-assets/campus-template.env`](../server-assets/campus-template.env). Stage the archive at `/opt/hill175/assets/campus/` before running the source deployment installer. World archives are deployment artifacts and are excluded from Git.

For local Paper testing, stop Paper and run `ops/prepare-local-campus-template.ps1`. The full local preparation script invokes it automatically. Previous templates are retained in runtime `assets/people-template-backup-*` folders.

## Existing entries and coordinates

- New People entries clone v19. Existing private People worlds keep their current blocks and legacy map coverage. No student's build is automatically replaced.
- An owner-confirmed **Reset Build** replaces that entry with the current v19 template. This is the normal explicit reset operation; it erases changes in that entry.
- Each new clone retains `hill-campus-template.yml` and `hill-campus-template.json`, recording its own scale, bounds, core spawn and original region hashes. This allows legacy and new campus worlds to coexist.
- V19 bounds are `X=-576..1407`, `Z=-1600..415`, with building permission from `Y=18..319`. The preferred core spawn is `[228,91,154]`; the safe standing-position check places players on grass at `[228.5,86,154.5]`. Its chart uses those bounds.
- The package omits player saves, session locks, `level.dat`, and extra dimensions. Paper owns each private world's metadata and upgrades the region data on load. Construction saves and both download ZIPs are untouched.

## Camera controls and checks

Entering a camera pose equips and selects the **Exit Camera Preview** barrier in hotbar slot 4. Left-click or right-click it to return to the pre-preview location. `/camera exit` is also available. Owners receive the separate confirmed removal control; visitors do not.

With local Paper running and smoke dependencies prepared:

```sh
node ops/smoke-player.mjs camera-view
node ops/smoke-player.mjs people-campus-template
```

The camera scenario checks capture, position/rotation locking, automatic selection of the exit item, owner and visitor exits, and owner-only removal. The campus scenario creates an isolated test entry, checks scale/provenance, all 25 region files, safe core arrival and the campus chart, then resets that test entry and rejoins it. These checks create disposable smoke accounts/entries; they do not modify existing participant entries.

The campus remains unfinished: v19 includes the reviewed core and the existing 44 components, including measured shells. It does not incorporate unfinished Wendell, Ferenbach, Robins, Lehrman or roads/parking drafts.
