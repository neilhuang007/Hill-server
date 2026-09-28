# Center For The Arts reference handoff — 2026-09-16

Machine-readable packet: [`cfta-reference-packet-20260916.json`](../../runtime/research/campus-full-detail-20260905/cfta-reference-packet-20260916.json).

This is a builder-ready bounded pond-facade and massing packet. It changes no profile, model, world, campus integration or native capture. The current component is the measured envelope at `runtime/campus-reconstruction/campus-envelopes-v2-ground/160031040003-894f07a81a`, sample SHA-256 `97274ad135b42b4301c2e1a72ef5d7f3abdb3ca55d6f21b64d72f80e1e626896`. Its visual review remains pending.

## Sources and identity

Wohlsen documents a fly tower and a glass-walled two-storey lobby for the Hill School performing arts center. [Contractor project](https://wohlsenconstruction.com/project/the-hill-school-performing-arts-center/). The strongest facade views are the Montgomery County Planning Commission's [pond oblique](https://www.flickr.com/photos/75012107@N05/8182573471/) and [close pond view](https://www.flickr.com/photos/75012107@N05/6767681947/), cached at 1024×683 with hashes in the packet, plus Wohlsen's 1400×925 finished southeast oblique. The Hill School's current aerial controls present roof massing and pond orientation.

Raw LiDAR is cached in [`cfta-lidar-detail.npz`](../../runtime/research/campus-full-detail-20260905/cfta-lidar-detail.npz), SHA-256 `04a19d5ce9ee051b788c66573b3ebd12cd9887a26b5d9104961dc54ac40f2949`, with 163,196 points. Use global campus-local `U/V` axes rotated `9°`, `X=2×east_m`, `Z=2×south_m`, and `Y=2×(NAVD88_m−25)`.

## Three distinct front layers

The outer pale screen is a separate structure at nominal `V=-171.9`, spanning `U=126.97..193.58 m`. LiDAR top returns lie between `V=-172.43..-171.295`, with top `H=69.84 m`; the deep fascia begins near `H=66.60 m`. Keep its straight runs on consistent planes and about `0.5 m` deep. Do not stretch the building roof or glass to this plane.

The straight recessed glazing is nominally `V=-174.6 ±0.4 m`, about `2.7 m` behind the screen. Use that plane only through the five west bays and main curtain wall, approximately `U=133.1..181.7`. Keep the air/recess gap visible.

Source face 9 is the enclosed lobby roof at `H=68.542..68.545 m`. Preserve it. Its west front already reaches `(U,V)=(133.096,-174.325)` to `(150.599,-173.994)`. It then steps back through `(150.651,-176.570)` and runs to `(182.833,-175.961)`. The photographs and LiDAR prove enclosed lobby glass in front of that stepped edge, so the builder may add one shallow roof/ceiling apron at `H=68.54`, bounded by `[(150.599,-173.994),(150.651,-176.570),(182.833,-175.961),(182.833,-174.350),(150.599,-174.350)]`. Keep face 9 unchanged beneath/behind it. Do not extend the apron west of the step, east into the curved return, or forward to the outer screen.

The east aperture at `U=188.417` is not permission for another flat `V=-174.6` pane field. Its raw sill cluster is `(188.417,-171.661,63.63)` on the outer east frame. Behind it, face 9 turns from `(182.833,-175.961)` through `(186.997,-177.001)` and `(187.303,-177.331)` into the rounded southeast return. Follow that source/LiDAR turn as a deliberate stepped convex glazed wall. The contractor photograph shows about four principal columns by six rows. The outer screen ends in front of this curved enclosure.

## Pond facade schedule

The west screen contains exactly five upper openings and five aligned lower glass-block bays centered at `U=134.66, 139.52, 144.43, 149.42, 154.12 m`. The upper openings run approximately `H=63.60..66.60`, width `2.70 m`; the lower bays run `59.95..62.80`, width `3.55 m`. Five is independently visible in both county photographs and supported by LiDAR sill clusters. Their precise widths remain interpreted. The far-west tall portal spans about `U=127.7..131.4`, `H=59.9..64.9`.

The main curtain wall spans `U=158.3..181.7`, `H=59.90..68.40`, behind the screen. Roughly 21 narrow top-row cells are visible at limited resolution. Keep the `1.11 m` pitch and horizontal levels `59.90,61.12,62.40,63.60,64.85,66.05,67.30,68.40 m` in control metadata. At two blocks per metre, a full 0.5 m white bar at every subdivision would be too heavy. Use tinted pane texture for fine subdivisions and blocks only for principal edges, floors/spandrels, doors and a few major verticals.

The county close view shows repeated compact pale triangular/soffit ties above the curtain wall, crossing the recess from screen toward roof. Their endpoint count is concealed, so six interpreted ties centered near `U=159,163,167,171,175,179`, within `V=-174.6..-171.9` and `H=66.6..68.5`, are authorized. Use small backed quartz stair/slab wedges or short beams, retain open air between them, and record the count as interpreted. Do not build a continuous ceiling or dense lattice.

The photographed glass top is `H≈68.40 m` directly below the retained face-9 roof at `68.54 m`. At the half-metre grid, end pane cells at physical `H=68.0` and complete the head with occupied, backed cap/roof cells through approximately `68.5`. Do not push panes through the measured roof.

Exactly three double-door sets are visible beneath the broad curtain, centered near `U=167.6,171.0,174.9`, each about `2.0 m` wide from `H=56.65..59.05`; horizontal registration uncertainty is `±0.7 m`. Keep ordinary red brick around them, distinct from the coarse lower wall.

The rounded glass-block stair drum is approximately centered at `(U,V)=(162.2,-174.2)`, radius `1.8 m`, with `±1 m` plan uncertainty. Glass block spans about `H=59.95..62.0`, pale parapet `62.0..63.55`, and wraparound upper rail to `64.5`. Approximate it as a compact intentional curve, not a square projection.

The west stair descends in positive `U`, not negative `V`. Preserve the direct-return profile `(127,59.85),(132,59.85),(138,58.35),(142,58.35),(145,57.55),(150,57.50),(152,56.85),(156,56.80),(158,56.30)` with alternating flights and landings. The pond terrace is near `H=56.30`; the door threshold is an interpreted `56.65 ±0.3 m`.

## Roof faces and massing

Keep all ten canonical source faces. Faces 3 and 1 are the fly tower roof/parapet at about `80.01/81.23 m`; faces 4 and 7 are the auditorium roofs at `71.87..73.29 m`; face 8 is the west annex roof at `67.42 m`; face 9 is the lobby roof at `68.54 m`. Small faces 0, 2, 5 and 6 remain measured but functionally unidentified. The fly tower is a largely closed pink/red mass, not a residential facade. Side/back opening counts remain unresolved.

## Palette and enclosure

Use `quartz_bricks` for the pale coursed screen, with smooth quartz only on narrow caps and returns. The real pale unit material is unresolved; do not call it limestone or sandstone. Use `mud_bricks` for coarse red split-face-looking lower walls and ordinary `bricks` around the door infill. Use coherent terracotta/red-terracotta fields for the fly tower and deepslate tiles/slabs for dark flat roofs.

Pane color may change. Start the main curtain and rounded southeast glazing with `black_stained_glass_pane`; use gray panes if native comparison makes black too dead. Use light-gray or white stained panes for the glass-block bays and drum. Keep pale principal frames sparse and avoid a dense iron lattice. White rails may use connected iron bars with pale supports.

Every straight wall and screen segment must remain one consistent plane. Back all partial blocks, connect panes cardinally, and physically join screens, stairs and rails. A connected pane component does not prove enclosure.

Acceptance requires a fresh immutable study, source roof parity outside the two named exceptions, and native views of the pond overview, west five/five bays, curtain/doors, southeast curve, stair grade, roof oblique and an explicitly limited hidden side. Bind `native-review.json` to the exact archive or sample hash and record unresolved side/back facades.
