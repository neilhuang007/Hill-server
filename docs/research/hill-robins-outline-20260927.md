# Robins bounded rough outline — 27 September 2026

`runtime/campus-reconstruction/robins-outline-v1-2x` is generated and structurally checked. **Native review remains pending and the study is not integrated.** No Minecraft client was launched and the open campus demonstration was untouched.

## Owned artifacts and provenance

- Builder: [`scripts/build_robins_outline.py`](../../scripts/build_robins_outline.py). It owns Robins only and does not change shared helpers, terrain, manifests or another building.
- Frozen profile: [`profile.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/profile.json), SHA-256 `48fe36681f1b6fdda1bdaf1362ab898b1475360299e8b88fc590e71d7385a438`.
- Source packet: [`source-packet.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/source-packet.json), SHA-256 `50065b57bdb460657480a583bffa61830a32d2634efc8371009a541019f0251f`. It records the complete Robins facade/roof record and hashes all used research/source files.
- New archive SHA-256: `2eafdd265db92698567b498ba3bb5282eae79895b7a14fcede159382ae01f0b2`.
- Original shell: `campus-envelopes-v2-ground/160015116006-451a0df37b`, archive SHA-256 `d21dc932bd1e7b7d45fd3bd340a2441acf005d07732a3c8b20c3432e58e28b0a`; unchanged after export.
- The frozen builder copy is inside the study, SHA-256 `294b1f016c4e7453f9cd96c71fe0ce1307f40de378412476d18dbcd6ea2aa9b8`.

The measured frame remains X = 2 × east metres, Z = 2 × south metres and Y = 2 × (NAVD88 − 25). Exact footprint bounds are X `-67.78732271056958..-51.396505391192925`, Z `-5.092495809414286..16.50407591188656` metres. The facade ledger's rounded/projected bounds differ slightly; the live measured source is authoritative.

## Bounded exterior

The current school aerial and retained Dutch crop support an irregular stone-pattern south gable, white west return, one visible upper sash with dark shutters, one small pale attic vent, and a white lower door reached by a few steps. The outline uses cobblestone, white concrete, pale quartz trim, gray panes and small flush dark-oak shutter fields as ordinary vanilla proxies. The seven measured roof faces and all **1,951 source roof cells** remain exact, including backing and stair/slab states.

Only the observed south opening subset is translated. Exact coordinates and dimensions are interpretations: upper sash at block X `-128..-127`, Z `29`, Y `83..85`; attic vent at `(-123,91,30)`; door threshold at `(-127,78,29.5)`. The white door is a usable double vanilla door in a four-block-high rough recess. Its NAVD88 64 m threshold is inferred from the photographed rise above the nearby 63 m grade, not a survey control. The short supported route ends about one metre inside; it does not certify an interior circulation route.

North/east remain generic closed walls with no invented openings. West window counts and projecting bay dimensions remain unresolved. Visible brick chimney shafts are not placed because the source packet does not register their positions. Low source face 3 is retained as an unresolved near-grade reconstruction fragment; this outline neither removes it nor claims it represents a correct porch. No facade treatment is transferred to another Dutch house.

There are 308 concealed inward backing cells, all inside the measured footprint. These close diagonal raster corners and one inherited half-height eave opening while preserving the exterior roof caps and measured placement. The first failed construction diagnostic is preserved at `runtime/campus-reconstruction/robins-outline-v1-construction-diagnostic.json`.

## Road/path handoff

The walk seam is **world XYZ `[-127,76,36.5]`**, equivalent to east `-63.5 m`, NAVD88 `63 m`, south `18.25 m`. It is two blocks wide. The authored exterior site columns are exactly X `-128,-127`, Z `30..36` inclusive: half-open block bounds `[-128,30,-126,37]`, or metre bounds `[-64,15,-63,18.5]`. The shared path builder owns the continuation south of Z=36.

The door corridor runs north from this seam to `[-127,78,27.5]`. Its tread tops rise 76, 76.5, 77, 77.5, 78 blocks. All exact cells, route samples and inference flags are in [`connection-anchors.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/connection-anchors.json).

Profile site bounds are local UV `[4,19.5,5.5,23]`, with origin `[-64.67617711516898,-5.102045760333293]` m and axis `9.065210521806202°`. At the audited **0.5 m margin**, the ownership mask has 1,150 columns and bounding envelope X `[-68.5,-51]`, Z `[-5,19]` m. Every authored column is included. The ownership mask has no overlap with the nearest Dutch source footprints; its gaps are 10.55 m to Markle, 28.30 m to Johnson and 40.54 m to Sherrerd. Source-footprint gaps are separately recorded in the preservation recheck. The coordinator must still compare the actual combined component masks before integration.

## Verification and remaining review

- Exact archive/Anvil parity: **108,619 occupied blocks, 15 chunks**, zero missing, extra or mismatched states. No palette violations or clipped writes.
- All 1,016 source footprint raster columns, measured roof heights, gradients and face IDs compare exactly. No architecture extends outside the measured footprint.
- All 48 tested half-height facade slices pass physical enclosure. Only the explicitly open door is virtually closed for this test; its actual route is tested separately.
- All panes have connected heads/sills; roof backing and partial-block contacts pass.
- The actual 0.6 × 1.8-block player route passes 181 samples at 0.05-block spacing, with a maximum 0.5-block step.
- Fourteen exterior columns change for the step/apron. All other exterior columns are unchanged; no missing ground or exterior subsurface gaps were found.
- The physical audit was repeated from the exported archive. All recorded source-file hashes still match.

Evidence: [`artifact-audit.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/artifact-audit.json), [`physical-audit.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/physical-audit.json), [`preservation-recheck.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/preservation-recheck.json).

Six later-review cameras cover the south gable, southwest junction, west return, unresolved north/east outlines and entry steps. [`native-review.json`](../../runtime/campus-reconstruction/robins-outline-v1-2x/native-review.json) is bound to the exact archive with `pending_native_review` and no inspected images. The coordinator can run the normal native capture queue after the current demonstration is closed. Visual likeness and combined-campus acceptance remain unclaimed.
