# Hill campus reconstruction — two blocks per metre

## Current demonstration campus: v14

[Open-Hill-Campus.cmd](../Open-Hill-Campus.cmd) opens **campus-context-v14-2x**
in Creative mode at the Quad. [hill-campus-current.json](../server-assets/hill-campus-current.json)
selects its source world and prepared persistent `campus-playable-v14-2x` save.
Earlier worlds and player saves remain preserved.

The [frozen configuration](../server-assets/hill-campus-context-v14.json) retains
all 44 accepted v13 component specifications, including Annan v2, Mercer/Day/Sweeney v6,
Dining/Athey v6, CFTA v5, Tuck/Rink v6 and all earlier reviewed buildings.
There are 44 components, fifteen individually reviewed studies and **23 measured shells**.

The environment overlay repairs Quadrivium frontage/crossing, Hunt west and Dining west
drive joins, Ryan and Chapel paving, and isolated grass contour defects. Exactly 1,770
state/role cells change; 53 tile archives are byte-identical and 264,241,152 states
including air are checked in the eleven affected tiles. Architecture remains unchanged.

Both Athey courtyard passages retain all twenty actual-player routes across 2,104 samples.
Their architecture and roof states match the accepted study exactly. Eight new exterior
routes pass with at most half-block steps. The full 3,999,744-column ground scan finds no
missing ground, missing shared base, exterior subsurface gaps or exterior depressions
over 1 m against the DEM. Six sealed inherited underground Dining cells are retained.

The [assembly audit](../runtime/campus-reconstruction/campus-context-v14-2x/artifact-audit.json)
passes exact parity for **262,433,770 occupied blocks, 15,624 chunks and 64 tiles**.
The [native review](../runtime/campus-reconstruction/campus-context-v14-2x/native-review.json)
records 22 distinct useful inspected views in two runs, with particular attention to
Athey-Dining junctions. Original placement, ordinary construction palettes,
connected details and measured grade controls are retained.

This is bounded exterior acceptance; unseen elevations, interpreted dimensions, interiors
and other campus shells remain unfinished. See the [demo handoff](hill-campus-demo-20260923.md)
for launch instructions, evidence and the environment rebuild command.

## Historical v7 integration record

The remaining sections document the preceding v7 assembly and its audit results.
Their revision-specific counts, review decisions and queued work describe v7;
the current v14 state is recorded above and in AGENTS.md.

The previous launcher selection was **campus-context-v7-2x**, starting on the Quad with original Minecraft textures. Earlier worlds and player saves remain available.

This version combines five individually reviewed houses/dormitories with the older academic and pavilion studies and **32 unfinished measured envelopes**. It is a working campus, not a completed replica. The [native review](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v7-2x/native-review.json) records remaining defects. Research uses Sol xhigh; construction and refinement use Astra max, following the [delegation workflow](hill-building-agent-workflow.md).

## Placement and terrain

The frame is **X = 2 × east metres**, **Z = 2 × south metres**, **Y = 2 × (NAVD88 metres − 25)**, from latitude 40.24516, longitude −75.63516. All 44 component ownership masks pass the [placement audit](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v7-2x/ownership-audit.json): zero overlap, clipping, translation or assembly rotation.

The expanded terrain covers **992 × 1,008 metres**, X −288 to 704 m and Z −800 to 208 m, sampled at native half-metre cell centres. The block-top correction removes the former systematic half-metre height offset. Measured hills and depressions remain.

All **18,560 Dell Pond water columns** have nominal block tops at **55.0 m NAVD88**. The [assembled ground audit](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v7-2x/ground-control-audit.json) checks 32 saved controls: 24 of 26 uncovered controls are within ±0.25 m of the measured grid. Sol's [surface review](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v7-2x/ground-surface-review.json) supports retaining the other two sampled tops: Ryan's engineered approach at 67.5 m and Hunt's raised north terrace at 62.5 m. Their exact finished levels and full terrace outlines remain interpretations; the review does not establish surveyed accuracy. Covered building levels are classified separately from bare earth. The report distinguishes slab tops, stair maximum tops and nominal water tops.

## Current components

| Building | Integrated revision | Review scope |
| --- | --- | --- |
| Meigs / Admission Office | meigs-v4-2x | Continuous shallow porch roof, supported posts and connected windows. Roof product, campaign orientation and concealed elevations remain uncertain. |
| Thomas House | thomas-v5-2x | Connected diagonal window returns, backed caps and dormer sill. West reference observed; other opening schedules provisional. |
| East Faculty Village Unit3 | east-faculty3-v8-2x | South/west porch and two-gable study; bay slit closed. Vanilla siding colour/grain remains a compromise. |
| Foster Dormitory | foster-v14-2x | Clearer sash centres, closed frames and rear roof junction. Rear/end schedules and portal detail remain approximate. |
| Rolfe Dormitory | rolfe-v7-2x | Connected embedded panes, triangular portals and lower rear roof. Fine vent/trim and unseen elevations remain approximate. |
| Alumni House, Chapel, Athey/Dining, Ryan, Hunt | campus-developed-ground-v6-2x | Refreshed grade and bounded pane repairs. Older frame/detail candidates remain unresolved; Athey is being refined further. Dining remains an envelope. |
| Kipp Pavilion and Madden press box | campus-developed-ground-v6-2x/pavilions | Existing interpretations retained. Registration, heights, stands and site details remain uncertain. |
| Other named county parents | campus-envelopes-v2-ground |32 measured footprint/roof envelopes with incomplete facades and provisional material families. |

Feroe v7 and Business Office v4 have completed their standalone native reviews and are queued for the next integration. Sherrill v6 remains rejected because its dormer surrounds obscure the glazing. These separate studies are not included in this revision.

The wider [structure ledger](../runtime/research/campus-full-detail-20260905/terrain-final-campus-structure-ledger.json) includes additional support housing, probable ancillary structures and unresolved adjacent uses. Its106 review tasks are not a verified count of completed or currently occupied school buildings. The earlier [atlas](../runtime/campus-reconstruction/campus-plan-v1/index.html) remains useful for footprint identity and gaps, but its development-status layer predates this revision.

## Verification and remaining work

The world contains **262,314,795 occupied blocks, 15,624 chunks and 64 checked tiles**. The [artifact audit](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v7-2x/artifact-audit.json) independently decodes every tile's Anvil blocks and verifies merged chunk records, input hashes and vanilla-only rendering. Export parity establishes file correctness, not photographic likeness.

Twelve initial native views were inspected. Eleven show house integrations, Quad, faculty village, pond and pavilion context. The initial Hunt north observer sits inside the neighboring gym and is unusable. A [supplemental ground review](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v7-2x/native-ground-review.json) replaces it with a clear lower-drive view; a second oblique is only partly usable. Hunt's retained wall is visible, but the drive is largely grass instead of photographed paving, the stone pattern differs and its glazing and dormers need refinement. The point-height disposition does not accept this unfinished site or facade.

The Quad retains its interpreted lawn, red crossing, perimeter paths, entrance approach, planting beds and eight trees. Landscape beyond the Quad, sports stands/markings, entrances and the remaining buildings need individual reference-based construction. Athey's thick surrounds and partial-block contacts are being repaired separately. Zero connected-component or diagonal-pair errors alone never establishes enclosure or photographic accuracy.

Sources and decisions remain in [Sol's handoffs](research/hill-sol-reference-handoffs-20260908.md), [terrain research](research/hill-terrain-correction-20260905.md), individual building documents and [Quad research](research/hill-quad-landscape-20260905.md). The [official map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf) and [school drone footage](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) are primary visual references.

## Rebuild

The frozen [v7 configuration](../server-assets/hill-campus-context-v7.json) records component paths and accepted individual archive hashes. Pass it to scripts/assemble_hill_campus_studies.py with --config and choose a fresh --output directory.

Use scripts/prepare_hill_campus_revision.py to prepare the next configuration from refreshed terrain studies and individually reviewed buildings. It rejects missing, stale or rejected native verdicts for new individual replacements. Do not promote a changed building by copying an older review label.
