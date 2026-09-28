# Annan Building reference handoff — 2026-09-19

Status: **builder-ready bounded exterior reference**. This is a source packet, not a completed Minecraft study or native acceptance.

The frozen machine-readable packet is [`runtime/research/campus-full-detail-20260905/annan-reference-packet-20260919.json`](../../runtime/research/campus-full-detail-20260905/annan-reference-packet-20260919.json), SHA-256 `59beeb1a36f1b94c87c37bf24fcad3959102e8662c9f61230a82a333805a421f`.

## Identity and scope

The current official Hill map identifies map number 15 as the **Annan Building**. The county/Roofer parent is `1600303920031C-4b7d18d798`, a stepped building between Tuck Arena and Davy and immediately north of the main gym aggregate. The identity registry is frozen at SHA-256 `1689e7b469b964a87ac2fec97a67792ed1ec07d7f943933545cd217b33de9baf`.

The packet authorizes a fresh immutable individual study of this parent. It does not authorize edits to the measured baseline, shared geometry modules, current campus worlds or the current manifest.

## Source result

The [official 2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) directly supports:

- one long medium-gray main gable;
- a straight red-brown masonry west wall;
- four small high west windows below the eave;
- at least four larger lower west opening patches, with part of the row blocked by neighboring roofs;
- a partly visible red-brown south gable with a shallow low canopy/entry form;
- a low flat-roof annex attached at the east/south end;
- open separation from Tuck and Davy.

The official aerial original is frozen at SHA-256 `fcf609c9cdac99ea54cc59ad143b04aa2d66f1963bac7f704973a9dfda85fcbe`. A provenance-preserving Annan context crop at source pixels `[250,285,710,585]` is frozen at `runtime/research/campus-full-detail-20260905/sports-drone-sequence-20260919/official-aerial-annan-context-crop.png`, SHA-256 `c68f822a0b6d6c04d30dc59869fe86e0c539a808a8f1f01ba1a800e01324f44f`.

The [official athletics-facilities page](https://www.thehill.org/athletics/facilities) says that the 3,915-square-foot Bissell Wrestling Room is above the fitness room. Its official interior photograph has four high rectangular windows on one long wall. The exterior aerial independently shows a four-window upper row. Treating the photographed interior wall as Annan's west upper wall is therefore a strong but explicit inference; the school page does not name Annan in that section. The photo is frozen at SHA-256 `ac36e47f6e1988bc7bb64ae2907ddac64d07efd1cb94c25eb7976e37f12e4d9b`.

The [school's Founders' Hall account](https://www.thehill.org/athletics/hall-of-fame/founders-hall) separately names construction of the Bissell Wrestling Room and Annan Strength Center during David Mercer's tenure. That supports athletics identity/use only; it does not supply an elevation or room-to-footprint plan.

## Consecutive drone review

The full 1920×1080 school drone was decoded into 45 consecutive lossless frames at 0.5-second intervals from 258.0 through 280.0 seconds. The manifest is frozen at SHA-256 `2c10a15df580b2ffb085437feacc9efd3016bc3e5115afee360710ee00b7fa7`; the sorted frame aggregate is `0c408a80a778a43a0974236a408ac0a70a164d92558dc26432eaece9a78e59fb`.

Frames through 272.0 seconds are unobscured. After 272.5 seconds, a large end logo covers the central campus. Across the unobscured sequence, Annan remains behind, beyond or clipped by the larger athletics roofs. No frame supplies a defensible new Annan door or window count. This negative finding is binding: the sequence establishes current context and roof hierarchy, but it must not be used to fill the unseen north/east facades.

The 270.0-second context crop is frozen at SHA-256 `3629f87e96d8a6d697315911679cec19e1faac5dd83fdf38b34eb74cefdcc31e`. It shows the surrounding athletics complex; Annan is concealed or beyond the east edge.

## Measured geometry

Use the shared project transform without per-building fitting:

```text
Xblock = 2 * east_m
Zblock = 2 * south_m
Yblock = 2 * (NAVD88_m - 25)
```

The local building axes are rotated 9 degrees: `U=(0.98768834,0.15643447)` and `V=(-0.15643447,0.98768834)` in X/Z.

Main bar controls:

- walls: `U=61.3..77.18`, `V=-170.44..-133.99` m;
- ridge: `U≈69.3`, `H=66.96` m;
- eaves: `H≈64.35` m;
- lower program floor: `H≈57.0` m;
- upper program floor: `H≈60.3` m;
- north street/entry terrain: `H≈59.0` m.

The low annex occupies `U=76.88..92.36`, `V=-144.65..-133.88` m with roof near `H=60.6` m. It remains a low wing; the tall gable must not continue over it.

The source contains 21 roof faces. Preserve all of them from the frozen CityJSON, SHA-256 `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`. The most important routing groups are:

- face 11: west main roof slope, X/Z `[81.503692,-151.632810,93.680228,-121.818422]`, `H=64.3907..66.9581`, 222.0951 m²;
- face 20: east main roof slope, X/Z `[89.066137,-150.507941,101.723958,-120.223989]`, `H=64.2870..66.9581`, 230.9007 m²;
- face 4: low annex, X/Z `[96.830279,-130.838503,113.791756,-118.941167]`, `H=60.5120..60.6298`, 150.6906 m²;
- faces 0, 3 and 17: attached north recess/entry-side faces, union X/Z `[86.142136,-158.744059,96.762538,-150.067408]`, `H=58.3001..63.7564`;
- faces 1, 5 and 6: south low transition/canopy/gable fragments, union X/Z `[81.902627,-122.702393,112.330907,-117.783485]`, `H=56.4951..64.0409`;
- faces 2, 7–10, 12–16, 18 and 19: localized north-east high-face cluster, union X/Z `[96.632633,-156.905452,102.894262,-149.570734]`, roughly `U=73.5..77.18`, `V=-170.43..-163.17`, `H=66.2359..76.3459`, combined area 35.7893 m².

The high cluster is measured and must remain localized. Preserve its exact faces in the first study, but do not turn the source maximum `H=76.3459` into the whole-building height, extrude the cluster into another storey, enlarge it, or label it as a chimney/tower/copper roof. The aerial contains too few pixels to identify the element reliably. Native review must judge the exact measured form.

## Facade controls

The west wall is the only face with a buildable repeated opening schedule.

On the west plane `U=61.3`, build four high windows at interpreted `V` centres `[-161.5,-154.0,-146.5,-139.0]` m. Use about 0.9 m width, bottom `H≈62.15` and height about 1.3 m, with ±0.75 m registration tolerance. Four is a direct exterior count. Keep the openings high and narrow, with dark panes, occupied heads and sills.

The proposed lower row has centres `[-161.5,-156.3,-151.1,-145.9,-140.7]` m, about 1.2 m width, bottom `H≈57.85` and height about 1.8 m. Five is a bounded length-scaled interpretation: at least four lower patches are visible, while neighboring roofs hide part of the facade. Record it as inferred and do not add a sixth without new source evidence.

The south gable permits one conservative low entry around `U≈65.8`, floor `H≈57.0`, width about 1.3 m and height about 2.25 m, under a thin connected canopy whose top is near `H=59.7`. Registration tolerance is ±1 m. Do not mirror the entry or add a repeated south grid.

The north gable and entry recess remain closed, straight and source-shaped. Their doors, stairs and windows are unseen. The main east gable and low annex opening counts are also unresolved. Do not copy the west schedule onto them.

## Materials

The photographs support appearance, not product chemistry.

- Use ordinary red-brown coursed masonry for main and annex walls. `bricks` is the primary proxy; `mud_bricks` may be limited to shadowed foundation zones. Avoid a whole smooth-terracotta facade or alternating stripe noise.
- Use one coherent medium-gray family for the main roof and the localized high cluster while preserving every cap state. `polished_andesite`, slabs and stairs are preferred if native texture remains continuous; the existing stone-brick family is a fallback. Do not claim slate, sheet metal or copper.
- Keep the annex roof low and gray with `gray_concrete`, `smooth_stone` and/or bottom slabs.
- Use `gray_stained_glass_pane` for west windows, with `black_stained_glass_pane` only if native comparison shows gray too bright. Panes must be in the wall plane, cardinally connected and enclosed by occupied heads/sills.
- Keep the west division, canopy and sparse trim thin. `smooth_stone` is the default; brighter quartz is a native-review option, not a full-block belt.

## Terrain and gaps

The source minimum `H=55.6699` is not a common floor. Retain the lower west/south program near `H=57`, the upper program near `H=60.3`, and the north street approach near `H=59`. Follow the measured terrain and expose foundations where grade drops.

Preserve three critical separations:

- Tuck east wall `U=53.52` to Annan west wall `U=61.3`: about 7.78 m, descending from roughly `H=59` north toward `H=57` south;
- Annan south `V=-133.99` to the nearest Sweeney extension `V=-130.29`: about 3.7 m;
- Annan annex east `U=92.36` to Davy west `U=102.8`: about 10.44 m.

No connector, enlarged annex or invented lawn is authorized in these gaps.

## Required review

The builder must produce source-roof parity for all 21 faces, whole-wall enclosure, pane support/contact, neighbor-gap, terrain and exact Anvil export audits. Native review needs west overview and close views, a south oblique, north limitation view, east-annex view, roof/high-cluster view, and context views proving all three gaps.

Acceptance may claim a measured, source-bounded Annan exterior with a photographically supported west upper row. It may not claim complete north/east facades, surveyed lower-window centres, identified high-cluster architecture, exact material products or completed interiors.
