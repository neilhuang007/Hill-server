# Quadrivium facade refinement — reviewed 2026-09-16

Accepted individual study: `runtime/campus-reconstruction/quadrivium-v8-2x`.
Its [native review](../../runtime/campus-reconstruction/quadrivium-v8-2x/native-review.json)
is `accepted_for_bounded_integration`, following independent builder and
coordinator inspection of all seven native PNGs against the four saved SMP and
Wohlsen source originals. No campus manifest has been changed by this builder;
the coordinator must assemble and review a fresh campus revision before changing
the working campus.

## Source registration

The original September 15 packet was bound to SHA-256
`d79ce28f4e8472924283fd52efc29f7c83f7fd8a6cf419cbebce313b50233eb5`.
Independent source-face extraction during the build corrected three registration
controls. The current packet is
`runtime/research/quadrivium-reference-20260915/quadrivium-reference-packet-20260915.json`,
SHA-256 `7abc84d6531ec7dd559040d4c0027640efb0778eafed496f658d69820c8c28e0`.
See the [source handoff](hill-quadrivium-reference-handoff-20260915.md).

The tint and dormer-proportion addendum is
`runtime/research/quadrivium-reference-20260915/quadrivium-v6-appearance-addendum-20260915.json`,
SHA-256 `e36916f67faf4161e0758549598a8b61202664ccee90e871f6cd1df1e569af24`.
Its gray/black pane controls supersede the older iron-bar appearance notes in the
historical profile. All four source image hashes are bound in the v8 review.

- The west wing genuinely bends near U=-33.5. Its straight source segments are
  retained as separate planes, each rasterized as a connected cardinal path.
- The link's actual roof is already present in source faces 1 and 21. Its front
  ridge is U=-6.277, V=-8.318, H=83.790m. The glass is registered at U=-6.25,
  V=-8.3. The previous roof patch centered at U=-9.4 created a duplicate gable
  and is removed. Only the measured two-face roof is recolored pale quartz.
- The east ridge reaches U=44.199, V=-3.139, H=82.816m. Its 6/6/2 window stack
  is centered near V=-3.1. The tall wall ends at V=2.2; the source face beyond
  it is a low walk, so the measured rear inset is retained instead of a tall
  flat shoulder through V=4.85.

All coordinates remain `X=2*east_m`, `Z=2*south_m`,
`Y=2*(NAVD88_m-25)`. The parent, origin, scale and measured rotation are unchanged.

## Geometry and scope

Owned generator: `scripts/hill_quadrivium_details.py`.
Owned profile: `server-assets/hill-quadrivium-reference.json`.
Each completed study contains a frozen `detail-generator.py` and `profile.json`.

The lower generic shell walls were replaced with deliberate facade paths. Raw
roof discontinuities no longer drop random buttresses through the teaching
floors. Window sheets, jambs and caps follow those paths; the roof raster no
longer chooses a window's recess separately at each sample. The two photographed
historic bays use shallow stepped curves with bounded host-wall opening cuts.
Three historic portals now have connected pointed surrounds around peaked dark
apertures and recessed double doors. The modern link has one continuous glazed
gable, connected side returns, continuous pale masonry panels, three floor rails
and only principal vertical divisions. Gray glass fields and black glass-pane
divisions replace the former bright iron lattice. The window sills of the five
historic cross gables are at 76.0m, within unchanged roof bounds, so that a
readable brick triangle remains above each window.

Five photographed cross-gable roof patches remain. The main historic roof faces
are retained. The low source roof return at the modern west panel is locally
removed below 79.95m because the architect photo shows an unbroken three-storey
panel there. This is a bounded source contradiction, not a replacement of the
historic roof. The unsupported old ground-level frontage facet likewise does
not determine the photographed upper walls.

North door floors remain about 67.75m. The south lower storey and falling campus
grade remain exposed. Eight operable door leaves have occupied thresholds and
bounded approach aprons; the central pair meets higher ground with a stair.
Actual occupied support is checked because shell excavation leaves old DTM
ground metadata behind. No broad terrain grading is applied.

The rear window rhythm remains inferred. Fine limestone carving and sash
subdivision remain vanilla proxies at two blocks per metre. V8 contains no iron
bars; pane tint is an appearance proxy rather than a claim about the real glazing
product. No building, roof or terrain coordinates were moved for the tint change.

## Revisions and verification

| Revision | Status | Relevant evidence |
|---|---|---|
| v2 | Baseline, never accepted | Original four native images; 62 diagonal pane gaps |
| v3 | Rejected after seven native images | Rectangular link crown cap, missing side returns, rectangular-looking portal heads, misplaced east attic notch |
| v4 | Superseded contact diagnostic | Pane contacts corrected; v3 silhouette still not accepted |
| v5 | Superseded registration diagnostic | Corrected roof/front registration; two inward cap backings missing |
| v6 | Rejected after seven native images | Thick rectangular link frame, brown panel belts, detached-looking portal trim, small dormer caps and bright lattice |
| v7 | Superseded contact diagnostic | Source-reviewed tint and dormer controls; v8 completes the remaining bay/dormer backing contact |
| v8 | Accepted for bounded integration | All seven native views independently inspected; exact export/native provenance and physical contacts pass |

V8 archive SHA-256:
`ac00e48f24aa52ce3a349398a7a710ab09cb3d94578df09a4d49d381978a83da`.
The archive and Anvil world have exactly 2,487,049 occupied states with no missing,
extra or mismatched blocks and no forbidden palette entries.

The shared pane audit finds 2,691 panes and zero diagonal gaps, disconnected
pairs, horizontal contact candidates or vertical contact candidates. The
building-specific `scripts/audit_hill_quadrivium_contacts.py` checks positive
face area for pane/bar/slab/stair states, inward backing and actual door
approaches. It passes for v8: zero pane positive-area failures, zero missing
partial-block inward backings across 967 records, and eight supported operable
door leaves. These are physical-contact checks; the separate native close views
also show attached bay corners, glazed link returns and occupied heads and sills.

The completed native run is
`runtime/campus-reconstruction/chapel-native-qa/runs/quadrivium-v8-review-20260916-175th`.
It contains west historic, link, east oblique, east end, rear grade, historic bay
corner and link corner views, captured with original vanilla resources in
Minecraft 26.1.2. The report SHA-256 is
`9520b9e16c8c155a19428f0e3c9cdc4c48324bd8086b88f1eec0ce55c58706aa`.
Native provenance checks match the pre-upgrade source world, and all seven image
hashes match the report. The accepted review SHA-256 is
`5959ce0ac60151ae68a765fb46425cd42ff5fb44660783b439c20a744ca6db01`.

## Acceptance limits and integration handoff

V8 visibly resolves the v6 rejection items: a sole pitched glass crown, continuous
pale side panels, dark sparse glazing, pointed portals, and stronger brick dormer
triangles. It retains the measured west bend, east 6/6/2 light schedule, original
placement, two-block scale, rear inset and falling grade. The owned generator and
profile remain `scripts/hill_quadrivium_details.py` and
`server-assets/hill-quadrivium-reference.json`; use the frozen v8 `detail-generator.py`
and `profile.json` when reproducing this accepted artifact. Earlier completed
directories and their rejected reviews remain immutable.

This acceptance permits a fresh building-only campus assembly; it does not claim
complete photographic likeness or whole-campus acceptance. The modern pale
spandrels still read as stacked rails in close views, and quartz surrounds,
pointed arches and curved bays remain coarse at half-metre resolution. Local
measured roof-edge irregularities remain. The rear openings and blank modern
rear wall are conservative interpretations, the low east black railing is not
yet modeled, and landscape, approach and pavement finish remain incomplete.
Fine historic carving, inscriptions and sash detail are unresolved.

The coordinator should use the accepted v8 archive with the frozen current
campus configuration and `--preserve-existing`, retaining all other components,
landscape, terrain and margins. A new campus native review must precede updating
the current manifest and working-state documentation.
