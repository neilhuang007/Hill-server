# Athey frame refinement — 2026-09-08

`athey-frame-v4-2x` is **accepted_for_bounded_context_integration** as a native-verified improvement to the existing study. It closes the observed middle-sill slits, exposes more glazing, gives low-roof openings complete heads, and removes nine unsupported pale band blocks. It does not certify complete facade enclosure or photographic likeness. Dining Hall and hidden elevations remain unresolved.

## Immutable deliverable

- [Study world](../../runtime/campus-reconstruction/athey-frame-v4-2x/world), [ZIP](../../runtime/campus-reconstruction/athey-frame-v4-2x/athey-frame-v4-2x-world.zip), [block archive](../../runtime/campus-reconstruction/athey-frame-v4-2x/sample-blocks.npz), [six cameras](../../runtime/campus-reconstruction/athey-frame-v4-2x/camera-views.json).
- Archive SHA256: `8c925fdcd2e3ea8cf380c0e624f10b858d247d68c599b71ab75a6b3d56eacdb5`.
- ZIP SHA256: `5b80849cd7216df9a6935d73b7111719efa428f8397bae65c99871bbb76bd4fd`.
- [Native verdict](../../runtime/campus-reconstruction/athey-frame-v4-2x/native-review.json), [exact Anvil/native-provenance audit](../../runtime/campus-reconstruction/athey-frame-v4-2x/artifact-audit.json), [baseline delta](../../runtime/campus-reconstruction/athey-frame-v4-2x/baseline-delta-audit.json), [occupied-shape audit](../../runtime/campus-reconstruction/athey-frame-v4-2x/occupied-frame-shape-audit.json), [regression check](../../runtime/campus-reconstruction/athey-frame-v4-2x/frame-regression-check.json).

The baseline is `campus-developed-ground-v6-2x/athey`, archive `f2ca05971205e4b0939ea5553750863f693f80ac24622e2c4f08ac228bc6b514`. Terrain remains `campus-full-detail-terrain-v2/terrain.npz`, SHA256 `856bbb182f037ed014e7146c03b7d7909c4b002cb7b3563b52eb5ee6aca46216`. The scale remains two blocks per metre, X east, Z south, Y = 2 × (NAVD88 − 25).

## Construction change and cause

Only [Athey's local subclass](../../scripts/campus_athey_details.py) and [its profile](../../server-assets/hill-athey-reference.json) were edited. Shared academic/window/material/roof/terrain helpers and other building files were preserved. Source hashes and the local implementation snapshot accompany the study.

The baseline's minimum raster width expanded small sash dividers into broad quartz posts. Narrow groups up to 3 m now use the existing gray pane texture for those sub-voxel divisions. The original light counts remain in the profile; they are not newly verified photographic counts. Broad central groups retain structural posts. Thirteen divider cells remain at a measured diagonal setback where neither possible connecting corner belongs to the footprint; glass is not extended into those exterior cells.

The observed sill gaps had a distinct construction cause: terrain `ground_at` metadata remained after the hollow shell had cleared actual blocks to air. It was incorrectly accepted as sill support. The final pass adds 20 actual cap cells, changes 494 top sill slabs to inward-facing top stairs at the same upper Y, and supplies 664 brick backing cells inside the original cut reveal. The cap pass fills air below live glass and around the frame ring; it does not replace glazing with opaque cap bands. The source sill and opening controls remain unchanged.

Upper east windows also used the obsolete Roofer ramp after the bay itself had been corrected to its existing flat-roof profile. The local opening pass now sees that corrected envelope and requires room for the original complete head before cutting a wall column. Low link/eave columns retain their masonry and roof where the full opening cannot fit.

The east bay band had been written without the footprint mask used by its wall. Nine full-quartz cells, in five disconnected components outside the source footprint, had no occupied face neighbour. The final revision removes only these unsupported components. The exact v3-to-v4 comparison proves all other coordinates, states, semantic roles, and palette entries are identical.

## Numerical verification

| Study | Panes | Diagonal / adjacent errors | Horizontal candidates | Air or reversed-slab vertical contacts |
| --- | ---: | ---: | ---: | ---: |
| Ground-v6 baseline | 1,842 | 0 / 0 | 240 | 32 |
| Frame v1 | 2,547 | 0 / 0 | 287 | 37 |
| Frame v2 | 2,548 | 0 / 0 | 287 | 24 |
| Frame v3 | 2,555 | 0 / 0 | 283 | 0 |
| Frame v4 | 2,555 | 0 / 0 | 283 | 0 |

The final study has 4,873,296 blocks: 815 added coordinates, 168 removed coordinates, and 1,425 changed existing coordinates compared with baseline. Panes increase by 713 (38.7%). Pale trim cells decrease from 3,046 to 2,332; the retained palette is original vanilla brick, smooth quartz, gray glazing, and the existing roof/foundation materials.

All existing roof, terrain, pavement, and floor cells retain their exact states and roles. The guarded opening cuts restore 33 additional source roof cells previously cut away by windows. Geometry, elevations, roof and bay controls, coping controls, site details, floor levels, materials, scale, offset, and all six camera controls compare equal with baseline. The camera file is byte-identical. Every final pane and every nonair changed cell is inside the measured building footprint. The only changed exterior coordinates are the nine removed unsupported band cells.

Anvil decoding matches all 4,873,296 archive cells: zero missing, extra, mismatched, or duplicate coordinates; no forbidden materials or clipped writes. Native pre-upgrade source copies and screenshot hashes also pass their independent provenance audit.

## Native and occupied-shape review limits

All six [final native views](../../runtime/campus-reconstruction/chapel-native-qa/runs/athey-frame-v4-2x-20260908/screenshots) were inspected, including `window-reveal-detail`, `east-return`, `quad-straight`, `south-court`, `quad-reference`, and `roof-overview`. Root independently inspected the same six. Native Minecraft was launched only by root's single capture queue. v1 and v3 were also inspected during refinement; v2 was superseded before capture.

The middle-sill blue daylight visible in v1 is closed in the final close view. Glass remains broad and visible. The east-return floating band islands are absent and its upper openings have proper heads. Quad rhythm, court context, grade exposure, and overall roof silhouette remain stable in the fixed cameras. Outer surrounds and stepped arch contours remain coarse at the retained half-metre scale.

The original Minecraft 26.1.2 model elements and their state rotations were inspected on their 1/16-block occupied grid. All 413 pane contacts with slabs or stairs have positive real contact; 18 have partial contact at arch shapes. All 419 quartz components reach actual non-quartz support. A nonzero bounding cell or a terrain-height record is not used as evidence of occupied partial-block contact.

The **283 horizontal candidates are not all cleared**. Conservative probes just beyond free pane tips, at two heights and up to three blocks inward, find real shape intersections for all samples in 104 cases. In 178 cases both sampled rays remain open, and one case is mixed. These 179 open/mixed cases remain unresolved. The inward vectors are inferred from the facade frame, so they are neither 179 confirmed photographed holes nor proof that all other sightlines are closed. Future enclosure work should use declared opening planes and connected occupied shapes. No masonry is added on the strength of these probes, and dark glass or deep interiors are not reclassified as walls.

The accepted scope is the native-verified targeted repair within an ongoing campus context study. Complete window enclosure, exact sash details, Dining Hall detailing, hidden elevations, west-link enclosure, exact material species, and overall likeness remain open.

## Existing evidence and reproducibility

No new browsing, material selection, or reference collection was performed. The pass used the existing [reference inventory](hill-athey-academic-center-reference-20260905.md), [97 s east-return frame](../../runtime/research/athey-20260905/drone-97s.png), [105 s Quad frame](../../runtime/research/athey-20260905/drone-105s.png), and [earlier east-return frame](../../runtime/research/hill-reference-20260904/chapel-drone-03.jpg). These support the distinction between broad pale surrounds and fine recessed glazing; exact minor dimensions remain estimates.

Build to a fresh directory with the saved profile and required terrain:

```powershell
& 'C:/Users/neil_/AppData/Local/Python/pythoncore-3.14-64/python.exe' -X utf8 scripts/build_hill_athey.py --profile server-assets/hill-athey-reference.json --terrain runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz --output runtime/campus-reconstruction/athey-frame-v5-2x
```

The baseline diagnostic was red with `(240, 32)` horizontal/vertical candidates; the targeted final regression requires zero vertical gaps, zero pane pair errors, positive original-shape cap contact, no unsupported quartz components, and the exact nine-cell v3-to-v4 change. The [Athey audit harness](../../runtime/campus-reconstruction/athey-frame-qa-20260908/audit_athey_frames.py) reproduces the baseline comparison and occupied-shape classification. It remains explicit that those passing regressions do not certify full wall enclosure.
