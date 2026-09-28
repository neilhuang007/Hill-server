# Hill campus exterior rough-draft handoff — 2026-09-27

The campus-wide exterior inventory is ready at `runtime/research/campus-exterior-draft-20260927/`. It accounts for all 44 v16 component frames, supplies one source-bounded building/exterior task per component, and indexes reusable road, parking and path source geometries. It changes no study, generated world, builder code or launcher selection.

## Integration boundary

Final core v19 is the moving target. The protected rectangle supplied by root is in Minecraft blocks: **X -80..360 / Z -110..250 blocks**. At two blocks per metre it is **project X -40..180 m / Z -55..125 m**. Chapel, Athey/Dining, Ryan, Hunt, Music House and Quadrivium lie inside it; Wendell intersects it partly. Other work may enter it only through a registered outer join with exact changed-column bounds and preservation checks.

## Deliverables

- [`component-jobs.tsv`](../../runtime/research/campus-exterior-draft-20260927/component-jobs.tsv) is the machine-readable 44-job queue. It records exact measured architecture bounds, study/state, corrected core overlap, entrance evidence, path/parking/planting limits, shared sector and primary packet.
- [`component-worklist.md`](../../runtime/research/campus-exterior-draft-20260927/component-worklist.md) is the human-readable one-row-per-component worklist.
- [`surface-source-index.tsv`](../../runtime/research/campus-exterior-draft-20260927/surface-source-index.tsv) indexes exact OSM/source geometry IDs, transformed bounds, loader source and validation state for the useful shared road, parking and path candidates.
- [`shared-sectors.md`](../../runtime/research/campus-exterior-draft-20260927/shared-sectors.md) divides common hardscape/planting into CFTA/Dell, athletic, Dell Village, west residence, East Faculty, arrival and stadium sectors so roads and lots are built once.
- [`source-index.md`](../../runtime/research/campus-exterior-draft-20260927/source-index.md) records the fixed measured data, 2026 visual evidence, reusable scripts and broad site gaps.
- [`next-builder-packets.md`](../../runtime/research/campus-exterior-draft-20260927/next-builder-packets.md) gives concrete source paths and stop conditions for Warner, Robins and the following Lehrman pair.

The v16 manifest was used only as the stable 44-component inventory. V14 remains the historical launcher selection; v17 is not treated as accepted; Athey and the final core staging were still moving. The component frames are identical across those campus manifests.

## Main findings

- The exact building inventory is complete: 17 individually photographed studies, four developed/interpreted components and 23 measured shells.
- Vegetation is the largest campus-wide visual gap. Only Alumni House, Chapel, Athey/Dining, Ryan Library and Thomas currently contain any vegetation-role blocks; the other 39 studies contain none. Terrain grass is not a tree/shrub inventory.
- `campus-full-detail-terrain-v2` already carries the best broad surface raster: 17 parking, 139 road and 8 path features intersect campus bounds. Its geometry comes from older cached OSM/exported surfaces and must be checked against the stored 2026 aerial before current curb, stall or route claims.
- The CFTA lot (`way/263135537`) is the largest high-value parking candidate. Dell Village roads/pockets and the East Campus loop are the next most useful shared geometry groups. Exact source geometry should be loaded through `scripts/build_hill_measured_terrain.py::load_surface_features`; rounded bounds in this handoff are an index only.
- Perimeter grade evidence is strong: 1,663 approach samples cover all 44 components. Grade does not prove a door, stair, finished floor or retaining-wall top.
- Current visual evidence does not support campus-wide stall striping, curb furniture, exact tree species/trunks, or hidden service entries. The rough draft should build broad verified pavement and planting mass first.

## Builder queue

Wendell and Ferenbach were assigned during this pass. The next two source-ready independent shells are:

1. **Warner Center** — exact measured roof/footprint, dense north/south grade controls, and the stored current close image `runtime/research/campus-priority-20260905/warner-2026.jpg`. No entrance is authorized unless the image resolves one.
2. **Robins Dormitory** — current 2026 aerial supports the south stone-pattern gable, white return, dark shutters, gray overlapping roof and visible chimneys; north/east remain unresolved.

The next joined landmark job is the two-component **Lehrman '56 Pavilion**, using the stored contractor photo and institutional evidence. Build its south round pavilion and north service bar as one connected study rather than two detached shells.

For grounds, freeze final core v19 first, then build the CFTA lot/pond edge and Dell Village shared pavement. Local building studies should stop at a small declared seam and report any source-supported entrance anchor; the sector owner should make the road/path connection once.
