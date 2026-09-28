# Davy House revision study, 8 September 2026

Davy is being refined as an individual 2 blocks/metre model. All source collection, roof classifications and material choices come from Sol xhigh packets. Astra performs geometry, native comparison and construction refinement. The local frame remains origin `[0,0]`, axis 9 degrees, with `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`. Neither the source footprint nor the Davy–Sweeney gap is moved.

The material correction retains one stone-brick masonry field, original deepslate-tile roof textures and pale quartz trim. The roof/railing handoff chooses pale oak fence as a thin painted-white proxy; it does not identify the real rail substrate or wood species. No resource pack is used.

## Source controls

- Required roof/rail packet: `runtime/research/sol-reference-20260908/davy-roof-railings-handoff.json`, SHA256 `3fc2ae3b556d518d8b0405c36e1ce4ad1fa2130765f32b291eb3a066da2e9905`.
- Exact fingerprint supplement: `runtime/research/sol-reference-20260908/davy-source-face-fingerprint-provenance.json`, SHA256 `a9eee0906e943a42992e6026e0b2b2173e90a90bd9198c1286211ec777eb04a5`. This supersedes only the main packet's unprovenanced display fingerprints. It binds all 13 stored exterior polygons, exact plane arrays, source surfaces, complete SHA256 values and 16-character prefixes to the original CityJSON and loader.
- Roofer CityJSON SHA256 `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`; Davy parent `16001511600633C-c14400ca75`.
- Retain source roof faces `{3,4,6,7,8,9,11}`: 2,873 raster columns. Faces 9/11 are the long roof, 4/6 the high cross-gable, and 3/7/8 the broad lower canopy.
- Exclude low faces `{0,1,2,5,10,12}` only from the building shell: 1,499 columns. Their terrace/ground evidence and local site plan remain. The original source raster has 4,372 columns; bounded overlays produce a 2,905-column shell, wholly clipped to the original footprint.

The old main-roof, cross-gable and broad-canopy authored rectangles are removed. Only seven photographed east small gables, seven explicitly provisional west roof projections and the small outer hood remain authored. All combine by maximum over the retained planes. Unaffected source heights and gradients remain exact.

## Native v8 diagnosis

`runtime/campus-reconstruction/davy-v8-2x`, archive SHA256 `b6e305b6261642b470f176741b265a95ce390628beb1129dbe04cc201a6a04b5`, has 643,912 occupied blocks and exact Anvil parity. Astra and root inspected all six native views in `chapel-native-qa/runs/davy-v8-2x-20260908/screenshots`. V8 is rejected and retained as a diagnosis, not an accepted study.

Its source roof mass and open two-stage porch read coherently. The four pale rail runs connect and better approach the supplied white rail appearance. The window graph has 84 panes and zero raw joint or perimeter flags. However, native close views show small, low glazing within heavy quartz corners and east peaks that read as a jagged horizontal band. The original-model audit also finds five missing positive-area door-head contacts and one actual roof-substrate slit; other roof-pair candidates require classification against the main masonry wall.

The specified 61.4m east max overlays affect only 3–6 source cells per gable because the existing measured roof is already near 61m at those fronts. Root therefore authorizes an east-only, bounded interpreted ridge refinement toward 62m, retaining all existing patch footprints and every source column outside them. West ridges stay at their separately provisional 61.4m control. Sol has been notified for an addendum; this is not a new surveyed height claim.

## Next refinement and acceptance boundary

The next revision raises the glass head by one block while retaining the 1m clear width, removes the full quartz horns outside the local head/sill, and keeps one inset pane sheet with exactly one inward return at each diagonal seam. Five transparent full-depth door-transom blocks connect original thin doors to the centred upper panes without an opaque interior cap band. Roof substrate repairs extend downward within existing columns and preserve every final cap top.

Seven observed east gables and four plain east windows are retained. West apertures remain unresolved and are not mirrored. The north end has one arched exit without unsupported flanking windows. Four porch posts are fitted to the actual source canopy and hood; their exact positions and section remain interpreted.

Final acceptance requires fresh native inspection plus exact baseline and preceding-revision deltas, canonical source-face fingerprints, retained height/gradient checks, original-model roof/wall and pane contacts, partial-cap backings, whole-wall occupied cross sections, reciprocal rails, material checks and Anvil parity. No exact photographic completion is claimed for unseen elevations.
