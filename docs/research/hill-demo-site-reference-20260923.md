# Demo campus site reference — 2026-09-23

This is an environment-only reference handoff for the current `campus-context-v13-2x` demo cleanup. It does not authorize changes to accepted building architecture. The machine-readable controls are in [`site-controls.json`](../../runtime/research/hill-demo-site-reference-20260923/site-controls.json). Coordinates follow `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`; all proposed widths and horizontal placements that come from photographs are **interpreted, not surveyed**.

## Current evidence order

Use current first-party conditions before older proposals: the school's [campus page](https://www.thehill.org/about/our-campus), [2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg), [2026 labeled map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), and [official 1080p drone film](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4). The map is authoritative for current names and adjacency, not dimensions. It labels the joined complex as **Hunt Upper School Dormitory**; it does not draw an Upper School West geometry boundary.

The strongest local whole-campus frame is `runtime/research/quad-landscape-20260905/drone-139s-north-up.png`, SHA-256 `0145b1cf4df6b90405a8e6b35b05e015dd302bb5f2ab370f5b9f8ec1879eb48f`. It shows the open central Quad lawn, pale perimeter walk, red transverse walk, Chapel west, Hunt north, Athey south and Ryan east. Preserve that simple topology. Do not add diagonal walks, a lawn logo or central trees.

The fresh diagnostic views inspected here are under `runtime/campus-reconstruction/chapel-native-qa/runs/campus-v13-demo-baseline-20260923/screenshots/`. In particular, `quadrivium-new-glazed-link.png` shows the dark paving reaching the facade through an irregular edge, isolated elevated grass cells and no legible continuous pale sidewalk; `hunt-west-wing.png` shows the existing pale line ending before the west drive; `dining-west-passage-walk.png` confirms that the accepted covered route itself is open; `chapel-east.png` and `chapel-south.png` show that the cleanup should repair joins, not re-plan the Chapel grounds.

The paired whole-column baseline survey found no missing ground or common-base column among 3,999,744 checked columns. Its six subsurface air cells near X70/Z157 sit below Dining architecture and do not establish a general site-hole defect. Treat the visible problems as surface continuity and connection defects. The same baseline flagged 425 grass-over-source-paving candidates, concentrated at Hunt north (362) and Ryan north/east (63); resolve them only against the named source paths and current building/site ownership.

## Immediate controls

### Quadrivium north frontage — P0

SMP's [modern-link photograph](https://smparchitects.com/wp-content/uploads/2025/04/Front-exteior-new-link-side-view_credit-Halkin-Mason.jpg), [historic-front photograph](https://smparchitects.com/wp-content/uploads/2025/04/Front-exterior-historic-section_credit-Halkin-Mason.jpg), and [east-end photograph](https://smparchitects.com/wp-content/uploads/2025/04/Front-exterior-from-end_credit-Halkin-Mason.jpg), plus Wohlsen's [finished exterior](https://wohlsenconstruction.com/wp-content/uploads/2024/01/Hill-School-Quadrivium_3.jpg), agree on the site order:

`facade → contiguous planting/lawn setback → short entry connectors → continuous pale sidewalk/curb → black asphalt drive`.

The modern link interrupts that pattern with a broad red-brown entrance apron and a contrasting gray/white crossing through the drive. Wohlsen also records new paving, curbs, sidewalks, lighting and landscaping as part of the work. Exact walk and road widths are unavailable.

Use these block controls from `site-controls.json`:

| Control | Centreline X/Z blocks | Width | Confidence |
| --- | --- | ---: | --- |
| Continuous north sidewalk | `[[146,186],[167,188],[202,185],[215,184],[228,183],[243,186],[263,183],[296,179],[321,175]]` | 4 blocks / 2.0 m | High topology; medium placement; medium-low width |
| West historic portal | `[[178,194],[178,187]]` | 5 blocks / 2.5 m | Exact v8 apron start; interpreted outer join |
| Modern link brick apron | `[[221,189],[221,184]]` | 11 blocks / 5.5 m | Exact v8 apron start; photo-estimated width |
| Modern link drive crossing | `[[221,184],[221,163]]` | 9 blocks / 4.5 m | High topology; archive-fixed asphalt extent; interpreted width |
| East portal at local U=14.5 | `[[262,188],[263,183]]` | 4 blocks / 2.2 m | Exact v8 apron start; interpreted outer join |
| East portal at local U=31.3 | `[[296,186],[296,179]]` | 4 blocks / 2.2 m | Exact v8 apron start; interpreted outer join |

The four threshold cells come from the accepted v8 portal-apron transfer in `runtime/campus-reconstruction/demo-prep-20260923/study-inventory.json`; the north doors are at NAVD88 67.75 m. Actual archive inspection fixes the link start at full `smooth_stone` X221/Z189/Y85, top Y86; the west start at X178/Z194 is quartz stairs at Y86 with tops Y86.5/87; both east portal starts top at Y86. Preserve those accepted start cells. The asphalt at X221 spans Z163..186, so the contrasting crossing must continue to the first north curb at Z163 and leave grass beyond it. Follow current measured ground and use slabs/stairs where required. Remove lone grass blocks only where they conflict with a walk, apron or crossing. Retain a contiguous 1–3 m green/planting setback elsewhere. Do not turn the whole setback into pavement or flatten the eastward grade.

Local primary files inspected:

- `runtime/research/quadrivium-reference-20260915/quadrivium-smp-new-link-original-20260915.jpg`, SHA-256 `8c96a10af012ce93a1d9aa1f3431d65ff845703b8fa97f71ed4955f72eadce6e`.
- `runtime/research/quadrivium-reference-20260915/quadrivium-smp-historic-front-original-20260915.jpg`, SHA-256 `315ba351bc80fb6745b8619b4dea3cb4241869418ef1ecb5cf4e82b760969a27`.
- `runtime/research/quadrivium-reference-20260915/quadrivium-smp-east-end-original-20260915.jpg`, SHA-256 `6996f6cd29e99ff6387ec2e2a7142a3443b458874d55f0943d33ec208fd660c7`.
- `runtime/research/quadrivium-reference-20260915/quadrivium-wohlsen-exterior-original-20260915.jpg`, SHA-256 `d4d40db4653c6a2abc3c08f7a86dc41b59a26c3701583063da8a08e4edfec855`.

### Hunt west gap and west drive — P1

Continue the existing interpreted west-gap line to the first current west-drive curb contact:

```text
world metres: [[40.0,-27.3],[39.0,-31.0],[38.5,-35.0],[36.0,-38.5],[32.0,-40.0],[30.0,-41.0]]
2x blocks:     [[80,-55],[78,-62],[77,-70],[72,-77],[64,-80],[60,-82]]
width:         1.5 m / 3 blocks
```

This is a bounded continuation of the existing traced Quad control to the drive contact identified by the cleanup survey. The official 139 s frame supports the topology, but the intervening curve and width are low-confidence interpretations. Preserve natural grade; use short smooth-stone stairs or landings where terrain requires them. Stop at the first asphalt/curb cell rather than paving into the drive.

Actual archive tops on this candidate fall from Y77 at the start to Y74.5 at the drive contact. That is the governing local vertical control; do not import the much larger north-side drop into this west connector.

Do not confuse this southwest/west connector with the separate north retaining-wall system. Barry Isett's [project record](https://www.barryisett.com/project/the-hill-school/) and the inspected files `runtime/research/hunt-hall-20260905/isett-north-retaining-wall.jpg` and `isett-north-driveway.jpeg` show the north section as lower blacktop drive, masonry retaining wall, planted intermediate terrace, upper pale walk and black rail beside the building. The current study fixes its upper walk near NAVD88 62.15 m and lower drive near 58.5 m; preserve that section and its roughly 7.6 m overall Quad-to-road drop. Do not fill or flatten it.

### Dining west passage to drive — P1

The school aerial shows the west covered connector beside the Chapel-side turnaround, and official drone frames 92–93 s show it opening to that path network. The exact accepted `athey-dining-v6-2x` broadside route at local `V=30.5 m` is the secure start. The exterior join is interpreted:

```text
Dining local U/V: [[17.2,30.5],[14.5,30.5],[12.55,30.09]]
world metres:     [[28.783,71.352],[26.219,70.507],[24.5,69.5]]
2x blocks:        [[58,143],[52,141],[49,139]]
width:            2.5 m / 5 blocks
```

Start at the existing outer endpoint and stop at the archive-observed first road contact near X49/Z139. The accepted passage floor is Y89 and the drive top is Y88; use one supported slab step and preserve all covered-passage clearance. Evidence files are `runtime/research/dining-hall-reference-20260915/dining-aerial-context-crop-20260915.jpg`, SHA-256 `809cbf27c5f885dccd259f8acd52b010493e8e4dfbde4961211cb3423f70474a`, and `runtime/research/dining-hall-reference-20260915/drone-sequence-20260916/drone-092s.png`, SHA-256 `6ab928338c52d7de71361fd5c2c755d54347dd182179c765b4311e4e5ee51cf0`.

## Existing core controls to preserve

`runtime/research/quad-landscape-20260905/quad-landscape-measurements.json` is the reproducible source for the current Quad paths. Its numeric controls are exact file values but remain image-traced interpretations:

- North/west pale perimeter, width 3.2 m: `[[9.351,15.551],[11.164,6.917],[14.459,0.512],[20.424,-5.553],[28.333,-9.299],[35.996,-11.687],[44.224,-12.98],[52.808,-13.108],[61.101,-12.241],[68.545,-11.482],[74.871,-12.55],[82.362,-11.32],[91.014,-9.74],[101,-8],[112,-5.8],[121,-2],[126,3]]`.
- South/west pale perimeter, width 2.2 m: `[[9.351,15.551],[14.386,21.13],[19.617,25.827],[24.305,29.72],[27.648,31.064],[35.219,31.554],[43.959,31.689],[52.679,32.127],[60.009,32.209]]`.
- Athey terrace-front pale walk, width 2.3 m: `[[49.7,33.9],[56,33.4],[61.6,30.9],[64,31.7],[65.5,33.9],[71.5,37],[80,40.5],[90.5,45],[99.7,47.8],[104.5,46.8]]`.
- Central red transverse walk, width 2.7 m: `[[62.701,30.865],[68.964,9.784],[74.871,-12.55],[77.754,-23.82],[78.7,-26.7]]`.
- Chapel east/front perimeter link, width 2.6 m: `[[10.8,30],[11.6,22],[12,13],[13.1,4.5],[14.8,-2.5],[19,-7]]`.
- Ryan west walk, width 4.2 m: `[[104.973,39.524],[109.844,28.558],[114.31,18.505],[119.181,7.538],[124.531,1.16]]`.

The Athey main north threshold correction is independently pinned in `runtime/research/quad-landscape-20260905/quad-threshold-join-correction.json`: doorway `[58.73547095,43.74520904]` m, red-walk endpoint `[62.701,30.865]`, approach `[[62.701,30.865],[61.55,34.65],[60.25,38.6],[58.73547095,43.74520904]]`, interpreted width 4.0 m, threshold NAVD88 67.35 m quantized to 67.5 m.

### Chapel limits

The Chapel study has five older GKO-plan-derived routes in `scripts/build_hill_chapel_sample.py`, but `runtime/campus-reconstruction/demo-prep-20260923/study-inventory.json` proves that route 2 overlaps 186 current Quad-lawn columns and route 1 overlaps current planting/path ownership. The 2026 aerial and drone supersede those cross-lawn proposal traces. Do not restore them wholesale.

Restore only current outer-walk cells that the cleanup audit identifies as outside the named lawn and planting masks, keeping measured elevations. The current school [south-front photograph](https://resources.finalsite.net/images/v1752866412/thehillorg/bmtum5s58dvh26p6q2tl/2025-Alumni-Chapel.jpg) confirms a pale stair/landing with black rails meeting a curb and asphalt drive. The municipal [Chapel submission](https://www.pottstown.org/AgendaCenter/ViewFile/Item/13647?fileID=6169) supports grading, sidewalk, curb, retaining-wall, lighting and landscape scope, while the GKO drawings remain proposal evidence rather than a final survey. Witmer's [restoration record](https://thewitmergroup.com/project/the-hill-school-alumni-chapel/) supports real brownstone, dimensional stone and copper flashing, not an alternate site layout.

### Dining/Athey limits

The accepted court is red paving with pale crossing strips at interpreted NAVD88 69.5 m. Preserve both end-to-end covered routes and every broadside bay. Current building study geometry already supplies the courtyard and passage floors; environment work should only close exterior grass/road gaps. Do not repave the full court, alter the seal, fill an open passage or overwrite its measured/source fringe.

## Ordinary site palette

| Real condition | Vanilla family | Evidence boundary |
| --- | --- | --- |
| Black asphalt drive | `polished_deepslate`, slab/stair variants | Asphalt is directly observed; deepslate is the current ordinary proxy. |
| Pale concrete walk/curb | `smooth_stone`, `smooth_stone_slab`, restrained stairs | Pale concrete is directly observed; exact product and vanilla mapping are interpretations. |
| Red brick court/entry paving | `bricks`, `brick_slab` | Red pavers are visible at Dining and the Quadrivium link; bond/detail is unresolved. |
| Hunt retaining masonry | Existing `mud_bricks` wall with smooth-stone cap | Masonry wall is directly observed; block mapping follows the accepted Hunt palette. |
| Planting setback | `grass_block`; bounded `coarse_dirt`/ordinary leaves or flowers for beds | Green/bed continuity is observed; species and exact bed edges are inferred. |
| Black rails | Preserve accepted thin rail family; current Hunt uses `iron_bars` | Rail presence is observed; vanilla colour/section is an approximation. |

Use full blocks for supported surfaces and slabs/stairs only for grade transitions. Do not leave floating slabs, unsupported curb strips, single elevated grass cells, or one-block grass cuts through a photographed walk.

## Defect order and review

1. **P0:** establish the Quadrivium continuous pale sidewalk, threshold connectors, link apron and bounded drive crossing; eliminate grass/pavement holes inside those controls.
2. **P0:** preserve the current 2026 Quad lawn and named paths; reject older Chapel lines where they cross current lawn or planting.
3. **P1:** close the Hunt west-gap line to the first west-drive contact without flattening terrain or extending into the separate north retaining section.
4. **P1:** add the Dining west exterior join to the archive-observed first drive cell with one supported slab step; preserve all accepted Dining/Athey route cells.
5. **P2:** add contiguous low planting, curb refinement or lamps only after circulation is physically connected and supported.

Before accepting an environment revision, compare all building-owned blocks exactly against v13, re-run the existing actual-player route checks, inspect fresh native PNGs from the same archive, and verify that each new walk reaches a door apron or existing path/curb without an intervening grass cell.
