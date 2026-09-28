# Hill campus demonstration — September 23, 2026

Run this from any PowerShell terminal on this computer:

```powershell
& "E:\projects\Hill-server\Open-Hill-Campus.cmd"
```

The launcher opens Minecraft 26.1.2 in Creative mode at the Quad, using campus v14
at two blocks per metre. The runtime, assets and persistent player save are prepared;
no manual setup is needed on this computer. Double-clicking the same CMD file also works.
The launcher was tested from `C:\Users\neil_` with its `-Verify` option; it reached `ready`
and exited successfully after opening the selected save. Normal launch stays open.

Use WASD to move, double-tap Space to fly, Space to rise and Shift to descend.
Start with the Quad, visit Athey and both covered Dining courtyard passages, then
follow the Chapel-side drive and Quadrivium frontage. The Hunt west path shows the
new connection from the Quad-side walk down to its west drive.

## What is integrated

The [current selection](../server-assets/hill-campus-current.json) selects
`runtime/campus-reconstruction/campus-context-v14-2x/world` and the persistent save
`runtime/campus-reconstruction/campus-playable-v14-2x/saves/hill_chapel_qa`.
All 44 v13 components are retained. The [inventory](../runtime/campus-reconstruction/demo-prep-20260923/study-inventory.md)
confirmed that v13 already included the latest eligible accepted individual studies:
Dining/Athey v6, Quadrivium v8, Davy v11, Sherrill v11, CFTA v5, Tuck/Rink v6,
Annan v2, Mercer/Day/Sweeney v6 and the earlier accepted buildings.

There are fifteen individually reviewed studies and 23 measured shells, plus older
academic/pavilion interpretations. US West remains within the older Hunt aggregate;
no separate verified building split or new facade is claimed. Earlier worlds and player
saves remain preserved. This local demonstration does not change the competition server.

## Environment and Athey-Dining work

The [reference handoff](research/hill-demo-site-reference-20260923.md) and
[frozen controls](../runtime/research/hill-demo-site-reference-20260923/site-controls.json)
guide the new exterior work. Photograph-derived dimensions are interpreted.

- Quadrivium has a continuous pale sidewalk, three historic portal walks, a broad brick
  apron at the glazed link and a contrasting crossing extending to the north curb.
- Hunt west and Dining's west covered passage connect to the adjacent drives through
  supported half-block transitions. Ryan north/east and compatible Chapel outer paving
  have been restored where grass obscured the authored surfaces.
- Fifty-five isolated one-block grass contour spikes/pits near paving are corrected.
  The current Quad lawn/beds, measured slopes and raised Hunt terrace remain intact.
- Both Athey-Dining covered colonnades retain their connected roofs, piers, open side bays
  and continuous floors. The new drive connection reaches the west passage without
  changing its accepted architecture. Construction uses ordinary masonry, brick,
  pale paving and partial-block steps; existing panes, arches and detail are retained.

The overlay changes exactly 1,770 state/role cells in 1,414 planned exterior columns.
It makes zero changes to original architectural columns. No building placement or scale changes.

## Verification

| Check | Result |
| --- | --- |
| [Full export and native provenance](../runtime/campus-reconstruction/campus-context-v14-2x/artifact-audit.json) | Pass: 262,433,770 occupied blocks, 15,624 chunks, 64 tiles. |
| [Exact environment preservation](../runtime/campus-reconstruction/campus-context-v14-2x/environment-preservation-audit.json) | Pass: 53 tiles byte-identical; 264,241,152 state/role comparisons including air in 11 changed tiles; exact 1,770-cell delta. |
| [Athey-Dining connections](../runtime/campus-reconstruction/campus-context-v14-2x/athey-dining-connections-audit.json) | Pass: all 20 routes and 2,104 samples for a 0.6 × 1.8-block player; all 3,528,864 architectural states and 23,316 roof cells preserved. |
| [New exterior routes](../runtime/campus-reconstruction/campus-context-v14-2x/environment-walk-audit.json) | Pass: all 8 routes; maximum sampled step 0.5 block. |
| [Whole-campus ground scan](../runtime/campus-reconstruction/campus-context-v14-2x/ground-review/ground-survey.json) | 3,999,744 columns; no missing ground, missing shared base, exterior subsurface gaps or exterior depressions over 1 m against the DEM. |
| [Native visual review](../runtime/campus-reconstruction/campus-context-v14-2x/native-review.json) | 22 distinct useful images inspected individually in Minecraft; 11 Athey-Dining views and 11 core campus/approach views. |
| Focused code checks | 24 tests pass across environment refinement, construction materials and assembly. |
| [Playable save report](../runtime/campus-reconstruction/campus-playable-v14-2x/chapel-native-qa-report.json) | Launcher verification reached `ready`, exit code 0. |

Six air cells at X70/Z157/Y82–87 are sealed inherited lower-storey shell space beneath
Dining paving, bounded by a floor and four brick sides. They are not an exposed walking
hole; their real architectural function is unresolved. The raised Hunt terrace and Ryan
approach intentionally differ from the bare-earth DEM. Block-scale grade steps remain.

The native screenshots include the [whole Athey-Dining connection](../runtime/campus-reconstruction/chapel-native-qa/runs/campus-v14-dining-review-20260923/screenshots/athey-dining-entire-connection.png),
[west drive join](../runtime/campus-reconstruction/chapel-native-qa/runs/campus-v14-dining-review-20260923/screenshots/dining-west-drive-join.png)
and [Quadrivium frontage](../runtime/campus-reconstruction/chapel-native-qa/runs/campus-v14-core-review-20260923/screenshots/quadrivium-frontage-overview.png).

This is an exterior demonstration revision. Remaining shells, unseen elevations, fixed
modeled doors and incomplete interiors are not certified as finished. The conservative
2 × 4-block clearance box does not pass all Dining routes; actual-player clearance does.

## Rebuild for future refinements

Use a fresh output directory and configuration name. Keep accepted v13 and v14 immutable.
The ordinary assembler deliberately rejects an environment-overlay configuration so it
cannot silently omit these repairs. V14 was generated with:

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/refine_hill_campus_environment.py --source runtime/campus-reconstruction/campus-context-v13-2x --plan runtime/campus-reconstruction/demo-prep-20260923/environment-plan.json --output runtime/campus-reconstruction/campus-context-v14-2x --config server-assets/hill-campus-context-v14.json
```

The script refuses to overwrite an existing output. Its frozen plan and exact mutation
journal are copied into v14. Final native reports, source bindings and review limitations
are recorded in `native-review.json`; generation-time pending-review text in the manifest
is historical and is resolved by that separate review.
