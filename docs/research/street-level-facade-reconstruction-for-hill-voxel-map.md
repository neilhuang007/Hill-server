# Street-level facade reconstruction for the Hill voxel map

Verified: 2026-08-31. Scope: primary project repos/docs/pages plus current local VoxelEarth preview artifacts. This note evaluates whether street-level reconstruction or neural view synthesis should be added to the Hill School Minecraft/VoxelEarth pipeline to clean shadowed walls and recover recognizable facades.

## Executive finding

The current screenshots show two separate problems:

1. **Material sampling failure**: baked shadows in the VoxelEarth photogrammetry texture map to dark/random Minecraft blocks.
2. **Geometry failure**: occluded/crooked photogrammetry surfaces become rubble-like upper walls and side bleed. This is not only a palette problem.

The local v5/v6/V8 VoxelEarth-derived campus should not be treated as the whole-campus production base by itself. It preserves the Hill crop and real 3D-tile context, but its building bodies remain too photogrammetric: missing/crooked surfaces, noisy upper wall masses, shadow-darkened ground, and brick/gray material bleed make some buildings unrecognizable.

Street-level reconstruction is not the right whole-campus base fix. It is useful as a second-stage landmark enhancer for material/window priors on Chapel, Academic Center / Quadrivium, Upper School, Library, and major dorm clusters. The primary clean-building solution should be a structured shell layer: VoxelEarth for terrain/crop/context, footprint-backed procedural façades for clean walls, and optional LoD2 roof/building reconstruction later if we decide to use LiDAR again.

## Local engineering result

Implemented in the local VoxelEarth plugin copy:

- Restricted the material atlas to campus-safe blocks: masonry, concrete, stone, grass/dirt, water, glass, copper, and ordinary wood. Ores/sculk/wool/black-concrete are blocked from the generated campus palette.
- Added footprint-aware wall de-lighting: non-roof building voxels are voted by building/facade family instead of raw brightness.
- Added stronger building-body cleanup in `CampusBuildingShells`: erase shadowed photogrammetry mass up to an inferred roof plane with an 8 m footprint apron, while preserving adjacent ground.
- Made replacement shells denser and more MapSmith-like: two-block-thick walls plus interior floor decks to avoid black/empty building voids after noisy mesh removal.
- Fixed surface-mask priority so hardscape overrides grass when features overlap.

Focused core sample:

- World: `runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831/paper-runtime-wallclean-v7-1226/hill_school_voxelearth_core_shell_v10_thickfloors_1xg64_20260831_1254`
- BlueMap preview: `http://127.0.0.1:18115/#wallclean_v10:0:63:0:180:0.45:0.45:0:0:perspective`
- Voxel count after cleanup/place stage: `493,073`
- Palette audit: `0` forbidden/noisy-dark blocks; main blocks are smooth stone, bricks, deepslate tiles, smooth sandstone, stone, gray concrete, glass, and a small number of wood/trim blocks.

This is directionally better because building shells are now the source of truth for walls instead of raw VoxelEarth wall geometry. Remaining visible roughness comes mostly from non-building photogrammetry objects and incomplete semantic surface coverage, not from illegal palette choices.

## Why MapSmith/Arnis looks cleaner

MapSmith is powered by Arnis. The Arnis engine is designed around OpenStreetMap/elevation semantics: it builds Minecraft worlds from real geography/topography/architecture, and its `geo-terrain` mode creates buildings, roads, and other OSM objects on terrain instead of sampling photogrammetry colors directly. Source: MapSmith official page and Arnis README:

- https://arnismc.com/mapsmith/
- https://github.com/louis-e/arnis

Arnis building generation is clean because it procedurally resolves building categories, façade style, roofs, windows, wall depth, and related blocks. That is why its walls look intentional. The tradeoff is lower real-world façade/roof detail unless the OSM tags are rich.

## Street-level / image-based options

| Tool | Primary source | Fit for Hill | Constraint |
| --- | --- | --- | --- |
| COLMAP | https://colmap.github.io/index.html and https://github.com/colmap/colmap | Best default for local camera poses / sparse reconstruction from Hill-owned photo sets. CLI-friendly, mature, free/open source. | Does not directly produce Minecraft walls; needs meshing/plane fitting after reconstruction. |
| OpenMVS | https://github.com/cdcseacave/openMVS and https://cdcseacave.github.io/ | Good dense mesh/textured mesh stage after COLMAP/OpenMVG. Useful for one landmark façade at a time. | More tuning; photogrammetry output still needs cleanup before block conversion. |
| Nerfstudio Splatfacto / Splatfacto-W | https://docs.nerf.studio/nerfology/methods/splat.html and https://docs.nerf.studio/nerfology/methods/splatw.html | Useful visual/material reference, especially with lighting variation. Splatfacto-W targets unconstrained photo collections. | Gaussian splats are not directly Minecraft geometry; use for view/material reference, not final blocks. |
| OpenDroneMap | https://github.com/OpenDroneMap/ODM and https://docs.opendronemap.org/outputs/ | Practical if Hill supplies drone/ground imagery. Produces point clouds, DEMs, orthophotos, and textured OBJ. | Requires strong image overlap; output still needs semantic voxel conversion. |
| SAM 2 | https://github.com/facebookresearch/sam2 and https://ai.meta.com/research/sam2/ | Good masking tool for removing sky, trees, cars, people, and temporary occluders before reconstruction. | Segmentation only; not a reconstruction engine. |
| Mapillary API | https://www.mapillary.com/developer/api-documentation and https://github.com/mapillary/api-demo | Possible public street-level imagery source if coverage exists near Beech Street / campus edges. | Coverage likely misses interior campus; API token and terms review needed. |
| Roofer | https://github.com/3DBAG/roofer | Best practical clean-geometry engine if we choose LiDAR/footprint LoD2 geometry later. It reconstructs building models from point clouds and 2D roofprint polygons. | GPL-3.0; depends on classified point cloud and roofprint/footprint quality. |
| City3D | https://github.com/tudelft3d/City3D | Strong secondary LoD2 route for clean roof/building geometry from point clouds plus footprints. | C++/CGAL-style build complexity; again depends on LiDAR/footprints. |

## Recommended Hill pipeline

Do not synthesize a whole-campus Street View world. It will be incomplete, slow, and still needs hard conversion into Minecraft semantics.

Use this instead:

1. **Base world**: VoxelEarth local tile pipeline for the full Hill property crop, terrain context, trees, roads, sports fields, water, and roof/top context.
2. **Clean walls**: footprint-backed procedural façade layer, similar to MapSmith/Arnis. For every building footprint, erase noisy photogrammetry wall/body voxels up to the inferred roof plane and rebuild stable walls/windows/roof decks using a restricted campus palette.
3. **Landmark detail**: for a few important buildings, collect Hill-owned phone/drone/street-level photos. Run COLMAP + OpenMVS for aligned meshes or use Nerfstudio/Splatfacto-W as a material/window reference. Use SAM 2 masks before reconstruction to remove trees/sky/people/cars.
4. **Optional high-geometry pass**: if clean roof forms matter more than “do not use LiDAR,” use Roofer first, or City3D second, from the 2024/2025 classified point cloud and county footprints; then voxelize the resulting LoD2 models into the same building-shell overlay. This is the primary route for clean geometry, while street-level imagery is only a material/window/reference route.

## Practical recommendation

For the next deliverable, use the VoxelEarth full-campus crop plus the v10 wall-shell logic. Do not spend whole-campus effort on Street View/neural reconstruction right now. If v10 still has too much visible roughness, the next target should be non-building cleanup: replace VoxelEarth tree/vegetation blobs with procedural trees and expand semantic grass/hardscape masks. Street-level reconstruction should be reserved for landmark façade/window upgrades after the base campus is navigable and recognizable.
