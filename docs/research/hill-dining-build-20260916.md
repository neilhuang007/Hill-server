# Dining Hall and courtyard passages — builder handoff

Integration update, September 19: Dining/Athey v6 replaces its shared parent in accepted campus v12. Native courtyard and eye-level passage views were inspected; exact combined-state checks preserve all twenty actual-player routes. The [campus review](../../runtime/campus-reconstruction/campus-context-v12-2x/native-review.json) records the bounded acceptance and the retained north-approach landscape exception.

This is a bounded amendment of the accepted Athey component, not a second overlapping campus building. Parent identity remains `16001511600613C-92645e8573`, with origin `[22,37]` metres, axis `18.25°`, two blocks per metre and `Y=2*(NAVD88-25)`.

## Source and ownership

- Base archive: `runtime/campus-reconstruction/athey-frame-v4-2x/sample-blocks.npz`, SHA-256 `8c925fdcd2e3ea8cf380c0e624f10b858d247d68c599b71ab75a6b3d56eacdb5`. It is loaded into Canvas without regeneration.
- [Sol reference handoff](hill-dining-hall-reference-handoff-20260916.md) and packet `runtime/research/dining-hall-reference-20260915/dining-hall-reference-packet-20260916.json`, SHA-256 `d302d1ebdb6a11b73a4e9c06bf4aa87b5920ff768494b11b445c33494e5f1b7c`.
- [Drone sequence correction](hill-dining-hall-drone-addendum-20260916.md) and addendum `runtime/research/dining-hall-reference-20260915/dining-hall-drone-addendum-20260916.json`, SHA-256 `3045b6ab739afa556380a96e6adeac6446f9c34c5dd6476f850fa9e7a1fccd44`.
- Site-detail exception: `runtime/research/dining-hall-reference-20260915/dining-hall-court-site-addendum-20260916.json`, SHA-256 `5efaf5629433a69dadc65a3e22d650e983378797e608aeccc9fcb50bcf8fb942`.
- Corrected complete-seal placement: `runtime/research/dining-hall-reference-20260915/dining-hall-seal-placement-addendum-20260916.json`, SHA-256 `ab9c0e3caa3d6815386a15f5cd2b07c6fcd23b2727d45849e08a976b3fec8706`.
- Owned profile: [hill-dining-reference.json](../../server-assets/hill-dining-reference.json). Owned scripts: [builder](../../scripts/build_hill_dining.py), [details](../../scripts/hill_dining_details.py), [physical/source audit](../../scripts/audit_hill_dining.py).
- Root owns native launches, campus assembly and current selection. No server or campus manifest is changed by this builder.

The sequence establishes that the close photographed connector is the **west** link, source faces 5 and 32. The earlier packet's east label is superseded by the frozen addendum. Frames 88–89 resolve at least four broad Dining lower bays and four upper rectangles; five plus five is still an interpreted complete schedule. The visible west pier minimum is ten shafts; exact total, center positions and the east support schedule remain interpreted.

## Construction and limits

Dining's north frontage has a low screen with backed pale notched coping, chamfered broad openings and a distinct recessed gray-pane wall approximately 2.5 metres behind it. The upper wall is one analytical line at `V=38.7`, with only the required cardinal raster steps. Its 94-column path has 70 east and 23 south steps, zero reversals and no extra facade cells outside its two-column thickness at NAVD88 73.5–76.0 metres. The repeat shade bands in close native views are this regular rotation raster, not retained facade buttresses.

Both courtyard side passages are open longitudinally and through inter-pier bays, as the user explicitly required on September 16. Square 0.5-metre brick shafts carry pale caps and bases. Their floors meet the interpreted retained court threshold of NAVD88 69.5 metres; measured terrain outside the amendment is unchanged. The west southern roof narrows where face 32 ends, so its final broadside route follows the remaining face-5 span. Two routes shift 0.3 metres inside their bays to avoid preserved low Athey attachment corners.

The measured west roof slopes retain every original occupied shape and stair/slab property. Their material changes to the source-approved smooth-quartz family as a pale sheet-metal appearance proxy. Its coarse stepped appearance is inherited source voxel quantization; no new ridge caps are added. East uses smooth stone and has a bounded source-gap closure to the Dining attachment. The dark Dining roof uses deepslate tiles with original shapes; rear roof fragments and source footprints are retained.

Rear/south openings, interiors, roof-fragment functions, exact stone species and fine standing seams remain unresolved. The unrefined rear facades are measured shells. This does not claim full Dining or full Athey photographic completion.

## Revision record

- `athey-dining-v1-2x`: rejected after five inspected native views. Unamended east-corner strips, panes facing solid brick, ten incomplete shoulder contacts and eleven overwritten face-60 top slabs.
- `athey-dining-v2-2x`: diagnostic export. Better recessed bays; superseded by the user's explicit two-passage requirement and source roof preservation corrections. Not integrated.
- `athey-dining-v3-2x`: diagnostic export. Both passages open. Three fixed straight broadside probes caught source attachment corners/narrowed canopy geometry. Not integrated.
- `athey-dining-v4-2x`: all ten native views inspected; rejected for one preserved gray-capped face-10 spur intruding into a Dining bay. Otherwise both passages appear open and connected. All 20 actual-player routes, 388 new pane contacts, partial backing, exact Anvil export and outside-mask preservation pass. Archive SHA-256 `da5affce67ddd17e1a9799a0a16cd9f753afdbd8b7824b002afb29c86bb143b4`.
- `athey-dining-v5-2x`: accepted for bounded integration after all ten native PNGs were inspected. Includes the photo-supported spur correction and a surface-only paving medallion. Archive SHA-256 `3c30759415976b68036ac7b8c0506706168e8db4f2bf3f691ccb5ef0f75f8641`; 4,877,046 occupied blocks. [Bound review](../../runtime/campus-reconstruction/athey-dining-v5-2x/native-review.json), SHA-256 `af679d3fb680371634da382adff38b69e71ecb987c2c45cd84b63de6598788ff`, records every inspected image and the exact evidence hashes. Native run: `athey-dining-v5-review-20260916-175th`, Minecraft 26.1.2 with vanilla resources, complete with ten views.
- `athey-dining-v6-2x`: accepted for bounded integration on September 19 after root inspected all ten native images in `athey-dining-v6-review-20260919`. It corrects the seal's placement to one complete circle inside the brick field. Archive SHA-256 `b63750c8b8fb5ce76be445d5eeb1d693c65b9ba8df5f879da5a2f2f28d2681b4`; 4,877,046 occupied blocks. Exact export, native provenance, all 20 player routes and physical contacts pass. V6 is the intended integration candidate; v5 remains immutable.

V5 changes just 61 cells from v4, exclusively inside the approved spur and surface-medallion masks. Six face-10 spur columns are cleared above finished grade and repaved; 16 of the original 22 court-source fringe columns remain protected, including every face-52/Athey cell. The seal uses 18 paving cells, retaining grade and clipping around the pale crossing. Every face-10 cell outside the spur mask is exact relative to v4. No connector or facade geometry changes between v4 and v5.

Final native views show both passages open and connected, the source spur removed and a consistent recessed Dining frontage. The tiny medallion is a coarse paving marker, not exact school-seal artwork. Acceptance covers this visible frontage, courtyard and the two functional passages; rear facade and interior limitations remain explicit. Integration must replace the existing shared Athey component, retain all other current components and terrain, and receive its own campus-context review.

V5 verification reports zero outside-mask state/role changes from accepted Athey, zero exported Anvil differences, zero pane contact failures across 388 new panes, zero missing partial backing across 414 checks, and 2,084 collision samples across the 20 level-floor player routes. The independent root artifact audit also passes. Only source face 10 has occupied roof-shape changes, within the declared screen and spur exceptions; original main Dining and both west-canopy roof shapes remain preserved.

The movement audit samples a 0.6 × 1.8-block vanilla player body every 0.1 block along two longitudinal and eighteen broadside routes, checking real occupied shapes and floor contact. A separate conservative 2 × 4-block box probe clips diagonal corners or source attachments on 13 of the 20 v4 routes; that larger envelope is **not** claimed to pass. Root confirmed actual vanilla-player clearance is the required functional minimum.

V6 changes 45 surface cells from v5: restores the previous 18 marker cells to original brick paving and places one complete 27-cell pale/gray circle at interpreted `U=44,V=24.5,r=1.4` metres. The two markers do not overlap. It has one cardinally connected component; both pale crossings, all retained source cells, grades, connector geometry and facade/roof states remain exact. The updated physical/source and exact export checks pass. This remains a coarse paving marker without crest lettering; only its placement and circular continuity have been corrected.

## Reproduce a fresh revision

```powershell
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/build_hill_dining.py --output runtime/campus-reconstruction/athey-dining-vNEXT-2x
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/audit_hill_dining.py runtime/campus-reconstruction/athey-dining-vNEXT-2x
```

The builder refuses an existing study directory, validates baseline and packet hashes, checks exact state/role parity outside the declared mutation mask, freezes its generator sources, and independently compares the archive with decoded Anvil blocks. Geometry changes require another fresh revision and new native captures. Native review must name the exact archive hash and actual inspected PNGs before root can integrate this single replacement component.
