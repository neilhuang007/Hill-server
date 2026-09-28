# Dining Hall / Millhiser Family Dining Room reference handoff — 2026-09-16

Machine-readable packet: [`dining-hall-reference-packet-20260916.json`](../../runtime/research/dining-hall-reference-20260915/dining-hall-reference-packet-20260916.json).

This packet is ready for a bounded builder pass. It changes no model, profile, world, campus manifest, or native capture. The builder must load `runtime/campus-reconstruction/athey-frame-v4-2x` at archive SHA-256 `8c925fdcd2e3ea8cf380c0e624f10b858d247d68c599b71ab75a6b3d56eacdb5` and preserve its block state and semantic role exactly outside declared Dining/court/connector masks. The accepted Athey frame must not be regenerated from mutable helpers.

## Sources and registration

The current visual authorities are The Hill School's [2026 drone video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) and [2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg). The official map identifies Athey as item 3 and Dining Hall / Millhiser Family Dining Room as item 4. The school's [rededication history](https://www.thehill.org/about-us/news/detail/~board/archive-news/post/alumni-raise-their-spoons-during-the-rededication-of-the-hill-schools-dining-hall) says the renovated Dining Hall reopened March 19, 2019 and records basement kitchen/pantry work and a scullery addition. Current imagery therefore controls over pre-2019 outlines or photographs.

The saved 1080p frame is [`drone-90s.png`](../../runtime/research/athey-20260905/drone-90s.png), SHA-256 `aa6f4d1155de7d782163b9d3021751cef34836e8ae92ceae43ca2e14eaf563c8`. The connector crop is an exact `[0,350,1320,920]` pixel crop; the Dining-front crop is an exact `[1120,250,1920,960]` crop. Their hashes are in the packet. The aerial crop registers to `[610,390,1500,840]` of the official 1500×843 JPEG with a template score of `0.99579`.

The measured geometry authority is [`source-scope-inventory.json`](../../runtime/campus-reconstruction/athey-dining-preparation-20260915/source-scope-inventory.json), SHA-256 `282d738422bc1808ea643c3635a830494d565976fb995a2d62aa2a64aaf2dd55`, derived from the CityJSON SHA-256 `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`. It contains all 72 canonical loader faces. The older `rf_roof_planes=158` attribute is not that face count.

Use origin `[22,37] m`, axis `18.25°`, `X=2×east_m`, `Z=2×south_m`, and `Y=2×(NAVD88_m−25)`. The older `dining-metric-roof.png` uses a different UV frame; do not copy its local numbers.

## Builder controls

The high Athey source ends at local `V=16.5626779461 m`. The southern measured source union is `U=6.769663..57.234780`, `V=35.000149..72.184789 m` and contains face IDs `1,2,5,9,10,11,12,14,20,21,27,28,29,30,33,34,38,39,40,43,45,46,47,53,54,59,60,61,62`. This is a maximum envelope, not permission to replace all roofs or fill it as one block.

Face 60 is the dominant Dining roof: `U=10.262421..56.826987`, `V=38.225222..65.799620`, `H=76.3276..76.5507 m` NAVD88, projected area `580.867 m²`. Keep its irregular measured footprint and holes. It is a broad low dark roof; do not copy Athey's steep roof or gables.

Face 10 is the low court screen/canopy at `H=72.9405..72.9795 m`. Its north edge is a near-straight source run from approximately `U=17.709..52.036`, `V=35.697..35.784`. Model this as one straight wall/screen plane with deliberate returns only at source corners. The recessed main Dining wall and face-60 roof begin around `V=38.2`, giving the photographed two-depth composition. The exact face-10 polygon is in the packet.

Face 5 is the measured west-link roof at `U=18.974844..21.744418`, `V=13.940268..35.780433`, `H=72.5988..74.3563 m`. Preserve it. Its complete lower enclosure is hidden, so do not turn it into a closed wall or claim an exact pier schedule.

The east-link maximum interpretation box is `U=52..57`, `V=15..36.5 m`. The drone and aerial show one low continuous pale roof, open below, on repeated brick piers. Clip all work around existing face 52 at the Athey side and face 10 at Dining. Use this box only as an outer mutation bound. Physically attach the roof at both ends and retain walking-height clear openings.

The protected court core is `U=21.8..52.2`, `V=21.0..35.7 m`. Of its 1,785 half-metre grid columns, only 22 intersect source faces 10 and 52. Preserve those occupied fringe columns and every accepted Athey block; do not clear the rectangle as a volume. Keep the rest open to sky, follow measured grade, and use red brick paving with pale crossing strips. The measured court sample at `U=35.966,V=26.047` is `69.408 m` NAVD88. The Dining south grade sample at `U=38.369,V=65.267` is `66.137 m`; one flat building base is unsupported.

## Visible opening and pier evidence

The connector crop supports ten distinct brick pier shafts from roughly crop `x=300` through `x=1210`, plus concealed western/end conditions. Ten is a photographed minimum, not the total colonnade count, and no defensible image-to-UV control points exist. Do not carry forward the old five-pier assumption as a source fact. Use a regular, closely spaced pier rhythm inside the east-link box, keep every inter-pier bay open, and record the chosen total as an interpretation.

The Dining-front crop shows one complete broad lower dark recess and a second recess clipped by the right edge. The recessed brick wall behind the low screen shows two dark rectangular upper openings. This does not expose the full elevation: do not distribute `2+2` uniformly across the entire U span. Build a conservative regular rhythm consistent with the visible eastern portion, preserve broad brick negative space and narrow pale heads/coping, and mark every additional bay as inferred. Rear/south and full west opening totals remain unseen.

The court screen's pale coping is deliberately stepped/notched. Keep it shallow and backed. Do not turn it into white teeth, a crenellated fantasy wall, or an Athey gable module. Photographed straight walls must remain consistent planes with only the minimal half-metre step raster required by the 18.25° rotation.

## Palette and enclosure

Use a coherent `bricks`/brick stair/slab/wall family for Dining and connector masonry. For pale coping and narrow surrounds, test the warmer smooth-sandstone family first; use smooth quartz only if native context shows that the existing Athey trim is the closer match. The exact real trim species is unresolved. Keep the main Dining roof dark with a coherent deepslate-tile family and the connector roof visibly lighter using smooth stone/light-gray construction proxies.

Pane color may change. Start the recessed Dining glazing with `gray_stained_glass_pane`; use `black_stained_glass_pane` where the lower recesses need the source's near-black reading, and light gray only where the image reads reflective rather than black. Do not default the court bays to bright clear panes. Every pane needs cardinal connection, an occupied backed head and sill, and native close inspection; a single connected component does not prove enclosure.

Keep all rear and rooftop fragments in the measured inventory unless a new bounded contradiction is documented. Their room functions and many opening counts are unknown. This packet supports a useful visible-court reconstruction without claiming unseen-elevation completion.

The new immutable study needs court overview, connector broadside, Dining screen close, roof oblique and south/rear limitation cameras. Acceptance requires exact parity outside the patch, source-face parity or named bounded exceptions, structural pane/partial-block checks, inspected PNGs, and a `native-review.json` bound to the exact archive or sample hash.
