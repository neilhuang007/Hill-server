# Mercer / Day / Sweeney construction — 19 September 2026

Accepted individual study: `runtime/campus-reconstruction/mercer-sweeney-v6-2x`.
The coordinator integrated this exact study into the current `campus-context-v13-2x` with Annan v2. The [combined native review](../../runtime/campus-reconstruction/campus-context-v13-2x/native-review.json), complete export audit and full-state study comparison pass. The existing player saves remain preserved. Work stopped after this current batch, as requested.

The study replaces the athletics parent's measured shell with separately
authored Mercer panel walls, Day north arches and Sweeney brick facades. It
keeps the fixed campus mapping, measured 9-degree frame, connected volumes,
all 58 connected-parent roof faces and each retained physical roof top. The
sole source exclusion is the packet-authorized tiny detached child `-1`,
faces 58–60; it previously appeared as an unsupported tall tower.

The owned source files are [the profile](../../server-assets/hill-mercer-sweeney-reference.json),
[detail module](../../scripts/hill_mercer_sweeney_details.py),
[builder](../../scripts/build_mercer_sweeney_study.py) and
[auditor](../../scripts/audit_mercer_sweeney_study.py). Shared helpers and the
selected campus are unchanged by this builder.

## Source authority and inspected coverage

The [Sol handoff](hill-mercer-sweeney-reference-handoff-20260919.md) and frozen
packet `runtime/research/campus-full-detail-20260905/mercer-sweeney-reference-packet-20260919.json`
have SHA256 `7fd67dbd08c28e842c028ed8aa14a1980b902ed732530d947c82ad574c2ea3f7`.
The measured baseline parent is `160015116006-1f19950994`; its archive SHA256
is `31c51bc88721f580d79f00f007247edc3d34c1f89aa68889db8dda268482c793`.

Four frozen source addenda resolve interpreted facade-plane and native details:

- `mercer-sweeney-gable-opening-registration-addendum-20260919.json`, SHA256
  `7c7b2d74077678d1ec90326c60b88db8fe3d993b05f9065880afbded324cb20e`:
  Sweeney's north arch is on its measured projecting front at V≈−130.285 m;
  east arches 2 and 9 register to measured gable centres V≈−117 and −82.5 m.
- `mercer-sweeney-measured-wall-opening-plane-addendum-20260919.json`, SHA256
  `a6b45b10e50327fca7170b6b9e463900b244f7c716faff144c4f1c957056d7a2`:
  Mercer/Day upper openings follow the measured high face behind low face 44;
  lower north Sweeney openings follow their separate measured shoulders.
  Both east gable arches use U=88.12 m. The irregular eastern roof spur stays
  roof geometry and does not generate a masonry buttress below it.
- `mercer-sweeney-v4-arch-roof-spur-addendum-20260919.json`, SHA256
  `f2f5a0cbc56f6de25f03e629103fca48c8dfd6d6235045024b49836c66473e6f`:
  visible semicircular heads may rebalance interpreted crown/spring heights;
  gray polished-andesite full/slab/stair shapes replace only the overly dark
  Sweeney pitched-slate roof proxy. Exactly one bottom slab at world `(201,80,−132)` joins the diagonal
  source spur from below. Existing spur/main cap cells remain unchanged in
  occupied shape, with no post or second bridge.

- `mercer-sweeney-v5-roof-retint-mask-correction-20260919.json`, SHA256
  `65207a98dbeba2cde1a3c3a0b777ae5e22f7c29be515908645758769f8d704be`:
  the gray roof is limited to measured faces 0, 1, 18, 30, 32, 34, 36, 37,
  38, 49 and 51, with their one immediate roof-role substrate. Other roof
  faces and the separate face 8 seam backing retain their v4 dark states.
  V6 preserves all reviewed v5 arches and all 43 quartz coping cells.

The builder inspected all 45 original 1920×1080 drone frames, 258.0–280.0 s
at half-second intervals, both contact sheets, the 270 s Mercer crop, the
272 s Sweeney crop, the current aerial's Mercer south crop and both official
interior photographs. Frames 029–044 have a central logo overlay; the clear
270–272 s sequence controls the visible sports-building details. Sequence
manifest SHA256 is `2c10a15df580b2ff2b085437feacc9efd3016bc3e5115afee360710ee00b7fa7`;
aggregate SHA256 is `0c408a80a778a43a0974236a408ac0a70a164d92558dc26432eaece9a78e59fb`.

The six actual native baseline PNGs in
`chapel-native-qa/runs/mercer-sweeney-baseline-20260919/` were also inspected.
They show the former blank masonry, uniformly gray roofs, exaggerated
detached artifact and rotation cadence before facade construction.

## Construction scope and limits

Sweeney has ten tall east round-headed openings, with taller openings under
the second and penultimate measured gables, a central north arch, lower
rectangular openings, thin pale courses and source-shaped coping. The final
interpreted east centres are V `[−122, −117, −112.07, −107.14, −102.21,
−97.29, −92.36, −87.43, −82.5, −77.8]` m. Count/order and the two gable
registrations are fixed; the other centres and opening dimensions remain
interpreted. The small pane texture represents fine sash work.

Mercer uses a pale opaque upper-panel field with narrow light-gray panes,
three source-scheduled south glazed entry groups and a pale manufactured
roof proxy. Day retains its distinct red low volumes and dark roof surfaces,
with eight interpreted north arches. Only the explicitly classified Sweeney pitched roof field uses the approved
gray polished-andesite family. Day, the middle roofs and excluded roof backing
retain their original dark family. The entry groups are fixed scaled
glazing; operational doors and complete interior routes remain unresolved.

Walls use regular cardinal traces inside the measured face. Source roof
caps and their backing are protected while unsupported wall projections
inside the facade strip are cleared. A full-cell centre inset seats the
upper glass on the tall-wall side of retained low roof strips. The detailed
register records analytic planes, actual columns, removed/added cells and
every opening. Native rotation steps remain expected at this measured bearing.

All panes have occupied heads, sills and jambs. Partial arch heads have inward
brick backing. V5 fits complete cells inside a semicircle, tapers outer jamb
tops and uses backed thin sills. Interpreted opening heights are now 4.6 m for
ordinary Sweeney east arches, 5.6 m under its two gables, 4.7 m at the north
central arch and 3.2 m for Day. Counts, widths, centres and wall planes are
unchanged. Every arch has one to three blocks of visible crown rise, with
clear space under the fixed roof. Solid stone completes a pane's side contact
where a stair would otherwise leave a disconnected end; the shaped shoulder
continues above it when space under the measured roof permits. The face 8/13 roof seam
receives an additional inward substrate cell below the unchanged source cap
to close a quarter-block underside slit at a 0.75 m roof step.

Regional floor surfaces use the packet's grade controls: Mercer main floor
56.4 m NAVD88 (quantized 56.5 m), Sweeney hall 56.25 m, south lobby 58.7 m
(quantized 58.75 m). The low north service level remains 53.6 m. Floors are
bounded interior surfaces, not a complete structural or circulation model.
No external sidewalk, terrace or step is authored. The measured surrounding
terrain, Tuck passage, Annan gap and open Davy approach are preserved.

## Revision and verification record

V1 is preserved and rejected before native capture: upper pane-side contacts
and approximate north planes needed correction. V2 is preserved and rejected:
cell-centre traces crossed onto retained low roof strips. V3 fits every
scheduled opening but exposed one arch contact and one inherited partial-roof
seam in the occupied-shape flood test. V4 addresses those local contacts, but
all six actual native PNGs were rejected for rectangular-looking arch heads
and an overly dark roof. V5 changes those interpreted details and connects
the one source roof fragment identified by the wider connectivity check.

V4 passed its initial geometry and export audit: all eight occupied-shape
wall slices are closed, all scheduled openings are present, and there are zero
roof-top, retint-shape, pane-contact, pane-perimeter, unsupported-partial or
protected-gap failures. No ground changes occur outside the facade footprint
and bounded wall strip. The ownership preflight against all 43 other v12
components has zero overlaps or clipped columns. All 28,489 modified
grade/foundation columns are owned; no explicit external site rectangle is
needed because no external site work is authored. All three regional floor
surfaces connect to the main architectural component.

V6 archive SHA256:
`7be5cab0fc799b14e2627700d8b069273d2571e380fa89a67c5dd83200d4f811`.
Its eight native cameras include two close arch comparisons. Root owns the
capture queue. Seven combined-campus cameras retain both an actual player
view in the Tuck/Mercer passage and one on the Sweeney/Davy approach; each
eye is 1.62 blocks above its measured assembled terrain surface.

The auditor independently checks source face fingerprints, untouched retained
roof raster values, exact vanilla occupied roof tops, identical occupied
shape after material retints, all vertical pane contacts, pane joins and
perimeters, partial-block support, actual wall cadence, grade preservation
and three protected gap cores. Eight 1/16-block occupied-shape flood slices
test wall enclosure, including the upper and lower half of partial blocks.
V5 also checks full-block architectural components and occupied contacts on
the authorized one-slab spur bridge, so a floating full-block roof fragment
cannot pass merely because its partial-block checks pass.
Exact block-archive/Anvil export parity is checked separately. All eight actual
v5 native PNGs were inspected. The lower arch heads and medium-gray Sweeney
roof improved the comparison, but v5 is rejected because its roof retint also
changed Day and the middle roofs, contrary to the source addendum. V6
preserves the reviewed v5 geometry and restricts the gray family by explicit
measured roof owners. Its full geometry/export audit passes. The independent
material-only comparison finds precisely 15,567 restored roof states, each
matching v4, with identical occupied coordinates, roles and opening geometry.
All 8,827 approved gray roof cells plus the one bridge satisfy the face/layer
rule. Ownership is clear against all 43 neighbors and with Annan v2; seven
campus camera eyes and sightlines are clear. All eight fresh v6 PNGs have now
been inspected by builder and coordinator, and bounded acceptance is frozen.


## Accepted native review and integration handoff

The complete run is
`runtime/campus-reconstruction/chapel-native-qa/runs/mercer-sweeney-v6-review-20260919/`.
The eight inspected views cover Sweeney east, north gable and oblique roof,
Mercer north and south, the middle north front, and close Sweeney/Day arches.
They show Sweeney's medium-gray pitched roof and retained stepped heads, Day's
restored dark flat roof and unchanged Mercer pale panels. The native review
records the visible coarse and locally asymmetric trim as a remaining limit;
it does not claim exact thin semicircular masonry or complete unseen detail.

`native-review.json` has status `accepted_for_bounded_integration` and SHA256
`97f1dc083f455f75f6ed8dbaf9c9bca7693f0ee389bd6542a4c8cce25dd472db`.
The complete native report SHA256 is
`c4bb0c4aec43fa7b6bca9782ad274a26ffeb1f7691e7df8b8eb022c1082e7256`.
All eight screenshot hashes match; three source files match the native
pre-upgrade backup. The 4,104,536-block archive has exact Anvil parity, with
zero missing, extra or mismatched states and no material-policy violations.
An independent Astra reviewer also reconstructed the exact v6 state array
from the frozen source mask, v5 geometry and v4 roof materials: zero mismatches,
all 43 quartz coping states unchanged and no nonroof or shape/property changes.

The study includes `ownership-preflight.json`,
`ownership-with-annan-v2-preflight.json`, `integration-camera-views.json`,
`integration-camera-preflight.json` and
`integration-player-camera-floor-controls.json`. Ownership is clear against all
43 other v12 components, including substitution of accepted Annan v2. All
28,489 changed foundation/grade columns are owned. No external sitework is
authored, so the explicit site-bounds list is empty. Seven combined views
include actual player-height observers in the Tuck/Mercer passage and the
Sweeney/Davy approach. All seven eyes and neighboring-component sightlines
are clear; their two terrain-floor controls are tied to v12 assembled tiles.

Coordinator work is the final combined-campus assembly, exact transfer checks,
native context review and intentional current-manifest update. This builder
stops after the current Mercer/Day/Sweeney handoff; no additional building is
started. Earlier revisions, source material, native runs and player saves
remain preserved.
