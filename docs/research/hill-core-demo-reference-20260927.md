# Hill core demonstration exterior reference — 2026-09-27

This packet governs the exterior demonstration area from the full Chapel approaches through Hunt, the Quad, Ryan Library, Athey/Dining and Quadrivium. It preserves the current `campus-context-v14-2x` building registration. Coordinates use `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`.

## Builder files

- [`core-site-controls-v1.json`](../../runtime/research/core-demo-20260927/core-site-controls-v1.json), SHA-256 `530aa11b46fa33a021b00bc4b65585a1f1e410277daedb71d05b1b5ffdc0017a`: exact paths, bed polygons, trees, lamps, hard exclusions, surface-audit envelopes and implementation order.
- [`core-registration-audit.json`](../../runtime/research/core-demo-20260927/core-registration-audit.json), SHA-256 `e8f9ce0692285355334f6e33bfb5de3eeedab128150c751a5154e10935b032f7`: source footprints, axes, current block envelopes and interbuilding gaps.
- [`core-building-controls.json`](../../runtime/research/core-demo-20260927/core-building-controls.json), SHA-256 `c7c8393c6cf079e57198b91aa99c9b7192e021d6fb7d7cef324ffc72429243a2`: bounded Ryan, Chapel, Athey and Dining exterior decisions.
- [`evidence-manifest.json`](../../runtime/research/core-demo-20260927/evidence-manifest.json), SHA-256 `c445af8c8887c93d3274af0273e8f908e32ba286e5940bedaf57db6e3cc23341`: copied evidence, source use and SHA-256 hashes.

The construction/audit extent is world metres `[-40,-55]..[180,125]`, blocks `X=-80..360`, `Z=-110..250`. Rectangular outer-road controls are audit envelopes only. They authorize repair of holes and seams inside pavement already connected in v14; they do not authorize paving the entire envelope.

## Source coverage and Google evidence

The strongest current source is the school-hosted 2026 aerial plus the school-hosted 1080p drone. The packet copies full frames 88, 92, 96, 100 and the north-up 139-second view. Quadrivium frontage photographs supply closer bed, curb and entry evidence. The older georeferenced 2021 PEMA orthophoto supplies topology and alignment checks, not current materials or current tree detail.

Live Google Maps was attempted on 2026-09-27, but neither a Chrome surface nor the in-app browser surface was available. The archive does contain a Google-hosted contributed Quad panorama: Jim Hilker, captured October 2016 and published August 2017. It confirms the relative arrangement, open lawn and principal red walks. Its user-photo geotag is explicitly unreliable and it is historical, so the 2026 aerial/drone govern current vegetation and materials. The copied panorama hash is `15664a1cf93b14ace5ff46e5612a15913adc1587bc570c371b57728cdbdc74b6`; provenance JSON hash is `3e619010670726213c4684f917f0990361595ef41b7da3ae3ee9a78e946df029`.

## Registration audit

| Building | Registered ground/source size | Current architecture block envelope | Result |
|---|---:|---:|---|
| Chapel | historical ring 21.115 × 32.679 m; axis −8.5° | inclusive `[-26,79,-22]..[24,116,65]` | Historical ring predates the modeled south addition. Preserve current axis and addition; no shift is supported. |
| Hunt | 75.431 × 32.112 m; axis 4.851° | `[83,66,-116]..[235,123,-32]` | Rotated footprint and projections explain the larger axis-aligned block box. Scale/placement are supported. |
| Athey/Dining | 84.554 × 82.578 m; axis 18.25° | `[20,79,67]..[189,128,231]` | 85.0 × 82.5 m raster envelope matches source within half-block tolerance. |
| Ryan Library | 43.248 × 44.335 m; axis 23.9505° | `[224,80,12]..[315,123,100]` | West stair/arcade approach explains the extra westward envelope. Preserve the measured bearing. |
| Quadrivium | local run 90.4 × 23.846 m; axis −2.9519° | `[143,73,186]..[323,123,238]` | 90.5 m block span matches the measured run; bearing and rear returns explain Z span. |

Axis-aligned registered gaps are 30.350 m Chapel-to-Hunt east/west, 13.015 m historical Chapel-to-Athey north/south, 48.757 m Hunt-to-Athey north/south, 21.244 m Hunt-to-Ryan north/south and 20.483 m Athey-to-Ryan east/west. These are audit figures rather than shortest polygon distances. No real-life scale or placement error was found. Do not move buildings to hide path mismatches.

The Athey projecting bay is resolved: measured source face 57 occupies local `U=72.739..75.319`, `V=-1.056..11.601`, `H=74.798..77.197`, area 30.16 m². It belongs at the accepted east-return registration. An earlier sequence-direction inference suggesting low U was wrong and is superseded. Do not move or mirror face 57.

## Exterior controls

The central Quad remains a large uninterrupted lawn. Do not add trees, diagonal shortcuts, a monument, sports markings or decorative paths. Preserve the two principal red-walk readings and pale perimeter circulation. The 2016 panorama corroborates this topology; the current drone supplies the present path/planting state.

The registered path controls are written in metres and blocks in the site JSON. They include the north-west and south-west Quad perimeter, central red walk, Hunt west drive connector, Chapel east link, broad Ryan west approach, Ryan north and south joins, Athey terrace/front approach, Dining west join and the Quadrivium north sidewalk. Keep their centerlines and measured grades. Use supported slabs/stairs for half-block changes rather than flattening the campus.

At Quadrivium, retain a continuous 1–3 m facade-to-walk setback with entry cuts. The packet supplies five clipped bed polygons across blocks `X146..322`, `Z177..192`, plus restrained black lamp candidates. Use low irregular flowering/evergreen shrubs over dark mulch; the real species are unresolved. The north-drive audit polygon is blocks `[[142,183],[325,174],[324,155],[141,164]]`. Inside connected road surface, remove isolated grass/dirt pockets and corrugated one-cell alternation while preserving crossings, curb separation and grade.

At Ryan, retain the broad 4.2 m west walk and full stair, a continuous curving mulched bed, two small existing trees and both crossing cuts. The bed polygon is blocks `[[193,74],[203,54],[211,32],[225,9],[240,-4],[240,1],[231,21],[222,43],[211,66],[205,79]]`. Keep the north and south joins open.

Around Hunt, enhance the two existing front beds and three existing tree crowns without duplicating trunks. Keep the central Quad side open and preserve the west stair/path down to the outer drive. Exact species remain unknown.

Around Chapel and the Chapel–Athey gap, preserve the east approach, south steps/railings and path junctions. Use the Chapel east bed only after clipping it from the arcade entrance and south landing. Frames 96–100 support richer low planting, one mature canopy and small ornamental trees in the gap, but candidate new trees remain collision-gated because exact trunks are partly concealed.

At Dining, preserve the west passage-to-drive join at blocks `[[58,143],[52,141],[49,139]]`, width five blocks. Passage floor Y89 meets drive top Y88 with a supported half-block transition. Both covered passages stay open end-to-end and broadside.

## Athey/Dining court: no terrain blocks

The open court is exact local UV `[21.8,21.0]..[52.2,35.7]`, world-metre polygon `[[36.127,63.771],[64.998,73.291],[60.394,87.251],[31.523,77.731]]`, block polygon `[[72,128],[130,147],[121,175],[63,155]]`. Frames 88–89 show connected red-brick/pale paving and open circulation. Remove every grass block, terrain cube, shrub crown or continuous ledge inside this polygon and from both covered gallery envelopes.

Authentic planting is a low raised terrace only on the Athey side, outside the court: local UV `[21.8,18.3]..[52.2,21.0]`, blocks `[[74,122],[132,141],[130,147],[72,128]]`. Represent it as contained mulch/coarse dirt with low plants and a restrained stone curb. Clip it around all arcade stairs and landings. It must never extend south of local V=21 or become a continuous grass-block barrier.

Frame 88 shows the Athey arcade landing roughly seven risers, about 1.2–1.4 m, above court grade. The bounded south/court arcade therefore begins at retained landing/floor H70.9, not court H69.5. Five controls use U `[25,30,37,44,49]`; four are directly visible and the fifth is inferred continuation. Pointed heads are about H73.5 and the court-only pale belt belongs just above at H73.8. Keep upper rectangular rows at H75.5 and H79.5.

## Building finish controls

Ryan’s west front has five pointed arcade bays, five upper pointed groups with three principal lights each, a central recessed paired door with transom and 3×2 upper panel pattern, and a separate south-west pointed entrance/landing. Use rough gray/brown stone for the historic body, coherent pale warm smooth-sandstone full/slab/stair blocks for dressed trim and dark gray tinted panes. The source does not support isolated orange arcade trim.

Chapel sources support fixing the south door/stair contact and keeping the east arcade entrance clear. They do not support a broad facade redesign. Preserve the measured roof/body and the existing warm masonry/pale-surround vocabulary.

No archived official image resolves a complete Dining rear/south opening schedule. A conservative completion may use plain vertically aligned rectangular punched openings on rear local V about `65.8..72.2` and end walls U about `6.8` and `57.2`: about 1.2–1.6 m wide on 3.6–4.2 m centers where wall runs permit. Counts and centers are interpreted. Retain every measured body/roof cell, keep service openings sparse and add no pointed arches, towers, projecting bays, parapet inventions or copied Athey vocabulary.

## Meaningful unfinished v14 scope

The v14 topology and major routes are usable, and its full terrain audit found no missing ground. Visual comparison still exposes demonstration defects:

- Quadrivium’s entire north setback reads as nearly bare grass, while sources show continuous low beds/green setback and lamps.
- Outer core canopy and beds are much sparser than the 2026 aerial/drone, especially Hunt margins, Ryan’s west garden and the Chapel–Athey gap.
- The Quadrivium drive and several outer joins read as corrugated strips with isolated grass/dirt pockets rather than continuous paved surfaces.
- The Athey/Dining interbuilding court can contain terrain/grass ledges despite source paving; the exact hard exclusion above governs removal.
- Ryan’s former shell lacked usable doors; source-grounded central and south-west entries are required.
- Athey’s south court facade needs its raised-landing pointed lower arcade, while Dining rear detail remains explicitly interpreted.

The eight registered trees in the machine packet already exist in v14. Enhance their forms and surrounding beds; do not add duplicate crowns. Three additional young-tree points are lower-confidence candidates and must be rejected if they intersect architecture, paths, sight lines or existing crowns. No exact tree or shrub species is claimed.
