> Preserved September 27 construction handoff. For current server logistics, see [AGENTS.md](../../AGENTS.md).

# Hill School working state

Last checked: 2026-09-27 (construction paused at user request; v19 world download verified).

## Active project

We are reconstructing The Hill School in Minecraft at **two blocks per metre**, using measured terrain/building geometry and individual reference-based building studies. Following the September 15 cleanup, the user explicitly authorized continued construction and integration for the 175th anniversary, covering **all important campus buildings** and prioritizing buildings still represented by shells. Reference agents use **GPT-5.6 Sol xhigh**; builders use **GPT-6 Astra xhigh**. Keep photographed walls straight, components physically connected and ordinary construction palettes consistent. Tinted glass panes are explicitly permitted and should match the source glazing. See the [live progress record](../../docs/hill-anniversary-build-progress-20260915.md).

### Current combined campus

- **September 27 stopping point:** the user requested that construction stop after the latest work and asked for a world download. All builders have checkpointed and stopped. Do not resume construction without a new instruction. See the [download handoff](../../docs/hill-campus-download-20260927.md), [44-component task ledger](../../runtime/research/campus-exterior-draft-20260927/component-jobs.tsv) and [session checkpoint](../../runtime/campus-reconstruction/core-demo-20260927/working-handoff.json).
- **Latest downloadable combined world: v19, Minecraft Java Edition 26.1.2, Creative mode, two blocks per metre.** The verified ZIP is `runtime/campus-reconstruction/exports/Hill-School-175th-v19-Java-26.1.2.zip`. It contains the converted persistent demonstration save `campus-preview-v19-2x/saves/hill_chapel_qa`, copied unchanged except omission of `session.lock`. The interactive client closed normally at 21:45:46 UTC; the save is preserved. This download does not change `hill-campus-current.json`, which still selects v14.
- **1.21.11 port of the same v19 campus:** `runtime/campus-reconstruction/exports/Hill-School-175th-v19-Java-1.21.11.zip`. Built from the frozen pre-26.1 v19 source with the official 1.21.11 server's full conversion. All 15,624 chunks are DataVersion 4671; full source/port parity matches 1,535,901,696 block states and the bell block entity, and the converted world loaded and saved successfully in Creative mode. ZIP CRC and every file hash passed. See [port handoff](../../docs/hill-campus-port-12111.md). This port uses the frozen build source, so the 26.1.2 player's exploration position and extra generated terrain beyond the authored campus are not imported. No separate 1.21.11 client screenshot run was done.
- **Direct 1.21.11 launcher:** `Open-Hill-Campus-1.21.11.ps1` (or double-click `Open-Hill-Campus-1.21.11.cmd`) starts the official Java 1.21.11 client directly in a persistent isolated Creative save at `runtime/campus-reconstruction/campus-playable-v19-1.21.11/saves/hill_chapel_qa`. The first run stages missing official assets. Tested 2026-09-27: Quick Play recorded `HillBuilder joined the game`, Creative mode, and a visible responsive `Minecraft 1.21.11 - Singleplayer` window. A second invocation detects the active save and does not launch another client. The prior v14 launcher and both download ZIPs remain separate.
- V18 is an accepted immutable staging base containing Athey/Dining v20, Ryan entry v3 and Chapel entry v1. V19 adds the frozen detailed core environment: exact 7,260 state/role changes, no original architectural-column changes, all 44 components preserved, full 262,440,207-block export/native provenance passed. All 22 useful native images across two completed runs were inspected; `campus-context-v19-2x/native-review.json` records bounded core demonstration acceptance and remaining limits. The entire campus is not finished.
- Wendell v1, Ferenbach v1 and Robins outline v1 are generated and export/geometry checked, **not yet native-reviewed or integrated**. Warner's measured-shell review is saved. Lehrman has an unexecuted, incomplete generator only. Roads/parking plan-v2 is the latest complete draft; plan-v3 was interrupted, and the roughly six-metre CFTA source-layer drive gap remains unresolved. None of these drafts is included in v19. The older statements below describe the September 23 launcher baseline only.

- The unchanged launcher selection is **`campus-context-v14-2x`**, distinct from the latest v19 download above. [hill-campus-current.json](../../server-assets/hill-campus-current.json) remains authoritative for that launcher; [hill-campus-context-v14.json](../../server-assets/hill-campus-context-v14.json) freezes its assembly and environment inputs. See the [September 23 demonstration handoff](../../docs/hill-campus-demo-20260923.md).
- Generated source: `runtime/campus-reconstruction/campus-context-v14-2x/world`. Persistent player target: `runtime/campus-reconstruction/campus-playable-v14-2x/saves/hill_chapel_qa`. Earlier worlds and saves are preserved.
- **`./Open-Hill-Campus.cmd`** opens Minecraft 26.1.2 in Creative mode at the Quad and reuses that persistent save.
- V14 retains all 44 v13 components, including fifteen individually reviewed studies. **23 components remain measured shells.** The inventory found no newer eligible accepted individual study missing from v13. The campus remains unfinished.
- Integrated studies include Annan v2, Mercer/Day/Sweeney v6, Dining/Athey v6, CFTA v5, Tuck/Rink v6, Davy v11, Sherrill v11, Quadrivium v8, Rolfe v7 and Foster v14. US West remains part of the older Hunt aggregate; no independent verified split is claimed.
- V14 repairs Quadrivium frontage walks/crossing, the Hunt west and Dining west drive joins, Ryan and Chapel paving obscured by grass, and 55 isolated grass contour defects. It changes exactly 1,770 state/role cells in 1,414 exterior columns; all architectural columns and 44 component specifications are unchanged. Rebuild with `refine_hill_campus_environment.py` and its recorded base/plan, not the plain assembler.
- Both covered Athey courtyard passages remain open and visibly attached at their roof/floor junctions. All 20 actual-player routes pass 2,104 samples. Exact checks preserve 3,528,864 architectural states and 23,316 roof cells. Eight new exterior routes pass with maximum half-block steps. The wider conservative 2x4-block box does not pass everywhere; unfinished interiors are not certified.
- The [native review](../../runtime/campus-reconstruction/campus-context-v14-2x/native-review.json) records 22 distinct useful inspected views across two runs. Exact export/native provenance checks pass for **262,433,770 blocks, 15,624 chunks and 64 tiles**. Full terrain scan checks 3,999,744 columns: no missing ground, missing shared base, exterior subsurface gaps or exterior depressions over 1 m. Six sealed inherited underground Dining air cells are retained, not an exposed walking hole.
- Sherrill v11 remains unchanged: its supplemental all-height proof confirms minimum regular grid steps at the measured bearing. Hidden elevations and earlier individual-review limits remain unresolved.
- September 23 demonstration preparation supersedes the previous batch stopping point. The current task integrates existing accepted work and repairs the environment; it does not complete remaining shells. Wendell/Warner construction has not started; any collected references are preserved for later.

Do not infer the current campus from the highest-numbered directory, modification time, `hill-campus-next.json`, the old atlas, or the deployed People template. Use the explicit current manifest and distinguish generated, reviewed and integrated revisions.

### Individual building work

All study directories below are under `runtime/campus-reconstruction/`.

| Building | Latest relevant individual study | Current state |
| --- | --- | --- |
| Davy | `davy-v11-2x` | Bounded native acceptance and integration into campus v9. Straight walls, taller glazing, thin gable trim and connected porch; unseen elevations and fine details remain limited. See the [Davy handoff](../../docs/research/hill-davy-build-20260915.md). Preserve rejected v8/v9 baselines. |
| Sherrill Guest House | `sherrill-v11-2x` | Bounded dormer acceptance and integration into campus v10. The September 19 all-height proof confirms minimum measured-bearing wall steps; south fronts and concealed openings remain under review. See the [refinement handoff](../../docs/research/hill-sherrill-refinement-build-20260915.md). |
| Athey | `athey-dining-v6-2x` | Exact amendment of accepted frame v4, integrated v12. Remaining Athey enclosure and unseen details are unresolved. |
| Feroe | `feroe-v7-2x` | Individually reviewed and integrated into campus v8. |
| Business Office | `business-office-v4-2x` | Individually reviewed and integrated into campus v8. |
| Meigs / Thomas / East Faculty Unit 3 | `meigs-v4-2x`, `thomas-v5-2x`, `east-faculty3-v8-2x` | Individually reviewed and integrated into campus v8. |
| Foster / Rolfe | `foster-v14-2x`, `rolfe-v7-2x` | Individually reviewed and integrated into campus v8. |
| Quadrivium | `quadrivium-v8-2x` | Bounded acceptance and integration into campus v10 after seven native views; connected glazed link and portals, corrected pane/panel palette. Coarse trim and inferred rear detail remain limited. |
| Dining Hall / Athey courtyard | `athey-dining-v6-2x` | Accepted and integrated v12: open east/west covered passages, recessed frontage, corrected west canopy and whole courtyard marker. Both actual-player routes and combined state preservation pass. |
| CFTA | `cfta-v5-2x` | Accepted and integrated v12: gray/white curtain panes, pale screen/roof, red wall fields, curved return and graded pond terrace. Rear/interior details remain limited. |
| Tuck Hall / Eccleston Rink | `tuck-rink-v6-2x` | Accepted and integrated v12: north panel/slit facade, connected brick entrance, pale roof and 436 concealed corner connections. Measured rotated walls retain unavoidable one-cell steps; hidden opening counts remain unresolved. |
| Annan | `annan-v2-2x` | Accepted and integrated v13 after native refinement of the south wall and roof backing; unseen openings/interior detail remain limited. |
| Mercer / Day / Sweeney | `mercer-sweeney-v6-2x` | Accepted and integrated v13 with connected volumes, round-headed glazing, gray Sweeney roof and distinct Mercer/Day materials; interpreted dimensions and interiors remain limited. |


For building changes, read the relevant research handoff, source packet, profile and native review first. Preserve the measured placement and scale: `X = 2 * east_m`, `Z = 2 * south_m`, `Y = 2 * (NAVD88_m - 25)`. Keep completed revision directories immutable; put new refinements in a new directory and give changed geometry a fresh review. Follow [the building workflow](../../docs/hill-building-agent-workflow.md) when continuing construction.

### Native Minecraft launch and screenshots

Use the existing command-line tool [scripts/run_chapel_native_qa.py](../../scripts/run_chapel_native_qa.py). Desktop UI automation is not needed to launch, join or capture these worlds.

Interactive campus command (equivalent to the current launcher):

```powershell
./Open-Hill-Campus.cmd
```

Native screenshot command (use a fresh run name each time):

```powershell
uv run --python 3.13 python scripts/run_chapel_native_qa.py --world runtime/campus-reconstruction/campus-context-v14-2x/world --camera-config runtime/campus-reconstruction/campus-context-v14-2x/quad-start.json --run-name campus-v14-quad-YYYYMMDD-HHMMSS --render-distance 32
```

Capture mode opens an isolated copy, takes screenshots and exits. Interactive mode stays open. Check `chapel-native-qa-report.json` for `complete` or `ready`, respectively; inspect actual PNGs before claiming visual verification. Building studies have their own `world`, `camera-views.json` and `play-start.json`; use a separate playable directory for each. Avoid launching a second interactive client on an already-open save.

### Cleanup and project boundaries

- Start with [the workspace layout](../../docs/workspace-layout.md). Current work stays under `runtime/campus-reconstruction/`; superseded whole-campus exports and early generation attempts were moved to `runtime/campus-history/cleanup-20260915/`. That archive is historical, not an alternative current work area.
- The cleanup archived 113 generated outputs (about 7.33 GiB) and two older player saves. No files were deleted and no building geometry was changed. All 50 protected artifact hashes matched afterward, including the current assembly inputs and Davy/Sherrill/Quadrivium archives.
- Preserve current source files, individual building studies, research packets, audits, screenshots and player saves. The repository already contains substantial uncommitted work.
- Older-looking folders can still be required assembly inputs: v8 depends on `campus-developed-ground-v6-2x`, `campus-envelopes-v2-ground`, `campus-full-detail-terrain-v2` and the individual revisions in its frozen configuration. Check dependencies before archiving generated outputs.
- The competition server and its deployed one-block-per-metre People template are a separate deliverable. Their presence does not make them the current two-block-per-metre construction world. Local world selection does not deploy a server update.

## Server deployment instructions

- Server: `135.181.78.188`, login `root`, services under `/opt/`.
- Always use PuTTY `plink.exe` for SSH:

```powershell
plink.exe -i "C:/Users/neil_/.ssh/hetzner.ppk" root@135.181.78.188
```

- When updating server code: update locally, push to GitHub, then SSH to the server and run `git pull`.
- nginx proxies local service ports. All web requests must come from Cloudflare with a valid origin certificate.
- Browser-based tool interactions are authorized by the user; do not stop to request browser-interaction permission.
