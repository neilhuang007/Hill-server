# Athey court and east-garden exterior addendum — 2026-09-27

This addendum extends the [Athey south-court correction](hill-athey-court-correction-20260927.md) without changing its frozen controls. It resolves the gallery floor relationship, corrects the 92–100 second drone-sequence orientation, registers the direct east-gallery-to-garden route, and supplies bounded exterior details between Athey, Ryan, Dining Hall and Quadrivium.

The frozen machine controls are:

| File | SHA-256 | Purpose |
|---|---|---|
| [`court-correction-addendum-v2.json`](../../runtime/research/core-demo-20260927/court-correction/court-correction-addendum-v2.json) | `2e158be006fd37308aef02fe48ca8f91f242c1f1b97a5e5ecd2fb33aba63a66b` | Gallery grade and registered east-garden path network. |
| [`core-exterior-detail-controls-v1.json`](../../runtime/research/core-demo-20260927/court-correction/core-exterior-detail-controls-v1.json) | `2fd8ee5e84fe898243923c2453a3a50bedf86d03b95a20f5be39da4a78ee3b9d` | Normalized paths, paver bays, beds, benches, fixtures and rail audit envelope. |
| [`core-exterior-fixture-placement-addendum-v2.json`](../../runtime/research/core-demo-20260927/court-correction/core-exterior-fixture-placement-addendum-v2.json) | `76a1b130945f2a02ec779ab64937f264e0b5dfc87cc68828e9a94330cdcda66c` | Conflict-free permitted polygons for the north lamp and bell memorial. |
| [`athey-east-gallery-garden-connection-v1.json`](../../runtime/research/core-demo-20260927/court-correction/athey-east-gallery-garden-connection-v1.json) | `43abb6c166970c7a7d0f48fa9c8c1aa4685ca53f778535535f5dff905217ed80` | East orientation proof, exact accepted gallery endpoint, direct garden route and roof-palette boundary. |
| [`evidence-addendum-v2.json`](../../runtime/research/core-demo-20260927/court-correction/evidence-addendum-v2.json) | `973ef32d5b7393385ac785c425ff52fbd12956229092f553ba0e5b4e6fc781fe` | Source, derivative and control hashes. |

## Orientation correction

The official 92–100 second sequence is east of Athey. Frame 92 uniquely shows Quadrivium’s modern glazed link on the right. Frames 96–100 show Ryan Library’s south Gothic gable ahead/right and the small brown-roof pavilion at the same location seen in the fixed-coordinate orthophoto and current aerial. Frame 88 has Athey on the left and Dining Hall on the right as the camera advances east across the court; frames 90–92 continue that motion over the east gallery roof.

These landmarks supersede the old September 16 addendum’s **directional label only**. The old frame observations of the pale two-slope covered roof, supports and open passage remain useful. The newly bounded east-gallery roof uses the measured local envelope `U=52..57`, `V=15..36.5`. Its current source character is pale cool standing-seam-looking metal. A coherent `smooth_quartz` full/stair/slab proxy is authorized inside the measured roof occupancy, while every existing slope, ridge, eave, attachment and block-state shape remains fixed. Gray stone-brick roof texture and geometric copying from the opposite gallery are rejected.

## Athey south court and gallery grade

The south arcade landing remains near NAVD88 `70.9 m`; the court and both covered galleries remain near `69.5 m`. Frames 88–91 show no auxiliary stair, ramp or lifted gallery floor at either attachment. The arcade may remain internally continuous behind its pointed openings, but it must terminate at the concealed attachment or door/wall condition. The supported circulation is the one central Athey stair down to the court, followed by the lower court-level gallery.

The court-side exterior remains governed by the base correction: one central stair, no additional arch stairs, approximately five broad plus four narrow pointed recesses, a curved/pointed covering over the recessed walk, low capped non-grass planting edges, coherent brick planes and pale belts, and zero exposed grass at the corrected Athey court edge. The individual door/glazing schedule and the concealed arcade/gallery thresholds remain unresolved.

## East gallery to garden

The accepted Athey/Dining v6 audit contains a player-clear east broadside route whose outer endpoint is local `U=56.4, V=20.5`, floor `Y=89`. Transforming that exact point through the established Athey frame gives world metres `[69.143,74.131]` and rounded X/Z blocks `[138,148]`.

The direct five-block-wide pale route is:

```text
[138,148] → [148,154] → [160,158] → [172,156]
          → [182,146] → [190,134] → [196,118]
```

This replaces the artificial long loop through the opposite gallery, Chapel and Quad. It follows the photographed open pale path between planted terraces and preserved stairs. Two inherited iron-rail groups near `X184/Z142` and `X186–187/Z138` are real fixed obstacles; route testing should select the clear side of the registered five-block corridor while preserving those architectural columns. The route follows current grade with slabs or half-block transitions and does not authorize a major stair, flat trench or filled ramp.

## East-of-Athey / Ryan garden path network

The 2021 PEMA orthophoto supplies fixed physical placement, while the current school aerial confirms the network, pavilion and drive relationship remain present. The primary near route connects the existing Ryan/Athey join to the existing Quadrivium-link crossing north curb:

```text
main, width 5:
[212,93] → [208,103] → [200,111] → [196,118] → [196,129]
         → [199,137] → [206,144] → [212,153] → [221,163]

seating cross-walk to Ryan south, width 4:
[196,118] → [210,118] → [224,121] → [236,126] → [249,128]
          → [260,129] → [267,123] → [268,113] → [267,102]

pavilion east loop, width 4:
[249,128] → [253,138] → [253,149] → [248,156] → [247,163]
```

The main route ends at the already registered Quadrivium link crossing `[221,163]`; it does not create a second asphalt crossing. The pavilion loop ends at the north curb. No diagonal shortcut crosses the open lawn.

The small brown-roof pavilion retains a short pale west approach inside `[[210,148],[219,147],[222,155],[216,160],[210,155]]`, clipped to its preserved footprint and the main walk. The exact door threshold is partly concealed.

## Paving, furniture and fixtures

The curved seating area is a paver bay, not a curved bench. Its construction envelope is `[[226,119],[251,120],[258,127],[255,139],[234,140],[224,132]]`, using muted red-brown pavers with a restrained pale curved border and clipped against both walks.

Two straight timber slat benches face each other across the shared paver/planting bay. Their physical length is `4 blocks` (`2.0 m`), distinct from the wider placement envelope:

| Fixture | Authoring line | Facing | Confidence |
|---|---|---|---|
| North bench | `[239,124] → [243,124]` | `+Z`, south toward the bay | Form/count high; facing medium; exact placement low. |
| South bench | `[239,136] → [243,136]` | `-Z`, north toward the bay | Form/count high; facing medium; exact placement low. |

The compact bell memorial consists of a small hanging bell between two nested dark curved supports. Its permitted source polygon is `[[214,120],[225,120],[225,131],[214,131]]`; the preferred point is `[220,126]`. Its actual object footprint is at most `5 × 4 blocks`, `[[218,124],[223,124],[223,128],[218,128]]`, and must stay west of the diagonal cross-walk. The larger polygon represents position uncertainty rather than object size.

The northern black square-lantern path light has permitted polygon `[[212,97],[217,98],[217,104],[212,104]]`, preferred point `[214,100]` and compact footprint `[[213,99],[215,99],[215,101],[213,101]]`. It stays on the east path edge outside the five-block clear walk. A second pavilion-side lamp near `[264,138]` is lower confidence and is collision-gated; omission is preferable to placing it on paving. The plain metal flagpole is registered near `[256,117]` with a small base footprint and must remain outside route clearance.

## Planting and edges

The seating island uses dark mulch or coarse dirt under pale ornamental-grass clumps, sparse low perennials and an arc of approximately six clipped round evergreen shrubs. Its registered envelope is `[[235,126],[250,126],[252,133],[244,137],[234,133]]`. The compact bell island uses only low groundcover so the memorial remains visible.

Along Athey, retain dark mulch, layered glossy low shrubs, pale ornamental grasses, flowering shrubs and small ornamental trees, with the photographed lawn strip between bounded beds and paths. Along Ryan, retain clipped evergreen mounds, larger pale flower clusters, low perennials and mature canopy. The broad planting rectangles in the machine packet are audit envelopes rather than fill polygons; current bed edges and path clearance govern the final raster.

Ordinary garden walks have flush lawn or mulch edges. Only the seating bay has a distinct curved pale paver border. Dark rails follow the preserved Athey stair and landing edges, and low pale-capped masonry contains nearby planting. The rail record is an audit envelope; it does not authorize free-standing rails or new stairs.

## Sector acceptance and evidence limits

| Between-building sector | Source-supported exterior detail | Concealed or unresolved |
|---|---|---|
| Athey–Dining south court | Red-brick court fields, broad gray bands, one central Athey stair with side/middle rails, two court-level galleries, low capped non-grass edge, upper recessed arcade. | Arcade/gallery end thresholds; individual lower door/glazing roles; fine furniture below gallery roofs. |
| East gallery–garden | Exact accepted broadside endpoint, continuous pale path, retained stair/rail obstacles, low planted terraces and current east-gallery pale roof character. | Fine path-edge curves below canopy; exact hidden threshold construction. |
| Athey–Ryan garden | Three registered pale path branches, brown-roof pavilion, curved paver bay, two opposing straight benches, bell memorial, flagpole, black lamps and layered planting. | Species; exact small-fixture placement within bounded source polygons; minor bed edges below tree canopy. |
| Garden–Quadrivium | Main route to existing link crossing, asphalt drive retained between pale curbs, pavilion branch ending at north curb, continuous Quadrivium frontage walk. | Any second east drive crossing; none is authorized. |

Every fixture, planting cell and path edge must remain inside its registered source polygon or corridor and outside preserved architecture. Keep a minimum four-block clear pedestrian center wherever fixtures or rails approach a route.
