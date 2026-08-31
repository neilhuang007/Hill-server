# Existing LiDAR and 3D-city voxelizers for the Hill School Minecraft map

Verified: 2026-08-31 from primary sources only: official repositories, official project documentation, and inspected source clones under `runtime/tools/voxelizer-research` (ignored by git). Scope: candidates that could replace or substantially improve the current unrealistic GIS generator for a Hill School Minecraft Java map using cached USGS LAZ/DEM, Montgomery County footprints, and authorized imagery/reference material.

## Recommendation

Fork and modify **VoxCity** as the core Hill School voxel model engine. It is the best upstream for this job because it is MIT-licensed, actively maintained, Python/geospatial-native, and already has a semantic 3D voxel model that combines terrain, buildings, trees, and land cover. Its gaps are clear and bounded: it needs a local USGS LAZ/DEM adapter, an imagery/material sampler, and a Minecraft exporter. ([VoxCity README](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/README.md), [voxel model concept](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/docs/concepts/voxel_model.md), [data sources](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/docs/reference/data_sources.md), [MIT license metadata](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/pyproject.toml))

Do **not** use CityMinecraft as the fork base unless we obtain a license grant from its author. Technically, it is the closest match: it reads `.laz`, fuses LiDAR, OSM, CityGML, aerial imagery, and writes Minecraft schematic/world artifacts. The repository, however, has no license file in the inspected tree, which makes reuse unsafe for an ongoing project. It is also Turku-specific: defaults reference Finnish EPSG/data services and Turku WFS/WMS endpoints. Treat it as a technical reference, not code to copy. ([CityMinecraft README](https://github.com/andreiBe/CityMinecraft/blob/928d7152476acb947c253fe8654b59cb4d8888b6/README.md), [LAS reader source](https://github.com/andreiBe/CityMinecraft/blob/928d7152476acb947c253fe8654b59cb4d8888b6/LAS/src/main/java/org/patonki/reader/LasReader.java), [Turku-specific default source configuration](https://github.com/andreiBe/CityMinecraft/blob/928d7152476acb947c253fe8654b59cb4d8888b6/Main/src/main/java/org/patonki/serialize/JsonSerializer.java))

Keep **Arnis** as the operational fallback and output reference. It is Apache-2.0, very active, cross-platform-oriented, and already writes modern Minecraft Java and Bedrock worlds. It is not a direct cached-LAZ pipeline: it consumes OSM/Overture and online elevation providers rather than local LAZ point clouds, but its world-writing and block-placement architecture is relevant if the deliverable shifts from `structure.nbt` to complete Anvil regions. ([Arnis README](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/README.md), [Cargo metadata](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/Cargo.toml), [Java world writer](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/src/world_editor/java.rs), [Bedrock writer](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/src/world_editor/bedrock.rs))

## Comparison matrix

| Project | Actual LAS/LAZ support | Semantic buildings / textures / roofs | Minecraft output | Windows viability | License and maintenance | Hill adaptation effort |
| --- | --- | --- | --- | --- | --- | --- |
| **VoxCity** | No direct LAS/LAZ ingestion found in docs/source; documented terrain sources include DEM products such as USGS 3DEP, and dependency metadata does not include `laspy` or PDAL. | Strong semantic voxel grid: terrain, building, canopy/tree, and land-cover classes; footprint/height extrusion; OBJ import can preserve authored solids and window/glass material hints. | No native Minecraft exporter; exports OBJ, MagicaVoxel VOX, NetCDF/HDF5-style analysis outputs. | Viable, but use a pinned Python/conda or uv environment because `geopandas`/`rasterio`/GDAL-style dependencies are heavier on Windows. | MIT; inspected head `41d766f` from 2026-08-29. | **Medium**: add local LAZ/DEM source adapter and Minecraft exporter. Best balance of clean license, semantic model, and controllable implementation. |
| **Arnis** | No direct LAS/LAZ ingestion; uses OSM/Overture plus elevation providers, including USGS 3DEP image-service terrain. | Good OSM/Overture building semantics; Overture integration can use upstream height hints derived from Microsoft/Esri/USGS 3DEP LiDAR, but it does not reconstruct roofs from our cached LAZ. | Strong: writes Minecraft Java Anvil and Bedrock worlds, plus map preview and multiple generation modes. | Strong: Rust project with Windows dependency handling and a cross-platform goal. | Apache-2.0; inspected head `97a2a7f` from 2026-08-31. | **Medium-high**: excellent world writer, but local county-footprint/LAZ/imagery integration would fight its OSM/Overture-first pipeline. |
| **CityMinecraft** | Yes: README uses `.laz`; source reads LAS/LAZ through `laszip4j`. | Strong: LiDAR classification, OSM, CityGML buildings, WMS/orthophoto texture conversion, roads/fields/land-cover blocks. | Yes: schematic and Minecraft world stages are part of the documented pipeline. | Likely viable through Java/Maven plus Python tooling, but not packaged as a general Windows CLI. | **No license file found** in inspected repository; inspected head `928d715` from 2023-12-21. | **High unless licensed**: technically the closest match, but legally blocked for forking and regionally hard-coded for Turku/Finland data services. |
| **Cloud2Craft** | Yes: explicitly accepts `.las` and `.laz`; source uses `laspy.open` and chunked point-cloud reading. | Weak: color point-cloud voxelization only; no GIS semantics, roof model, roads, fields, or authored building hierarchy. | Not file-first; uploads blocks to an old Spigot 1.14/RaspberryJuice server through `mcpi`. | Moderate: Python/GUI and old Minecraft server plugin workflow; dependency stack includes `laspy`, `lazrs`, `laszip`, and `open3d`. | GPLv3; inspected head `8c9f346` from 2023-04-12. | **High**: useful as a direct-LAZ voxelization reference, not as a campus generator. |
| **GeoCraft** | Uses UK LiDAR-derived DSM/DTM raster products, not local LAS/LAZ point clouds. | Moderate: fuses LiDAR terrain/surface with OSM tags and procedural material rules; not detailed facade/roof reconstruction. | Yes: writes Minecraft saves/region data. | Weak: Perl + GDAL workflow with UK-specific APIs and documented macOS/QGIS assumptions. | GPLv3; inspected head `55da390` from 2024-06-26. | **High**: old UK-specific implementation and GPL constraints; useful concepts only. |
| **VoxelEarth** | No LAS/LAZ; GLB/3D Tiles/photogrammetry mesh voxelizer. | Mesh-color voxelization rather than GIS semantics; useful for Hill-owned/right-cleared GLB sidecar assets. | Yes-ish: browser/client and plugin paths export or place NBT/schem/mcfunction/blocks depending on workflow. | Good Java/browser viability; server plugin expects Paper/Spigot/Bukkit 1.20+ and Java 21+. | README claims MIT for VoxelEarth and companion CLIs unless otherwise noted, but no root license file was present in the inspected clone; inspected head `ed68433` from 2026-02-14. | **Medium for GLB sidecar only**: not the replacement GIS generator. Good for authorized 3D mesh voxelization. |
| **OSM2World** | No LAS/LAZ. | Strong OSM procedural geometry and roofs; supports many OSM tags and exports textured 3D models. | No Minecraft output; exports formats such as glTF/glb/OBJ. | Strong Java/Maven viability. | MIT; inspected head `e58e986` from 2026-08-26. | **High**: useful roof/building geometry reference, but would require a separate voxelizer and Minecraft writer. |
| **mesh_to_schematic** | No LAZ pipeline; starts from existing 3D mesh models. | Inherits texture/color from mesh conversion, not GIS semantics. | Yes: creates `.schematic`/world artifacts through FileToVox/MagicaVoxel/vox2schematic chain. | Windows-oriented batch workflow, but fragile because it drives GUI tools/VBS. | MIT; inspected head `7d3fed1` from 2021-10-21. | **High**: good historical converter chain, not a data-fusion engine. |
| **FileToVox** | No direct LAS/LAZ found; supports many mesh/raster/point formats including OBJ/PLY/XYZ/TIF and `.schematic`. | Format conversion only; textured mesh to VOX is useful for assets. | Indirect: can read/write voxel formats and `.schematic`-related formats, but not a campus/world generator. | Good Windows/.NET fit. | MIT; inspected head `e860ee2` from 2023-10-15. | **Medium as a utility**, high as a core engine. |
| **2schematic** | No LAS/LAZ; input is Octomap `.ot` and PCL `.pcd`. | Weak: colored real-world RGB-D model conversion, not GIS semantics. | Yes: outputs MCEdit `.schematic`. | Weak/old: CMake + PCL + Octomap, 2013-era MCEdit format. | README says GPLv3 / COPYING present; inspected head `ebd3508` from 2013-03-08. | **Very high**: not a practical base. |

I did not identify a maintained primary-source repository named `point2block` that was a better exact match. The verifiable direct LAS/LAZ-to-Minecraft candidates in this pass were CityMinecraft and Cloud2Craft.

## Detailed findings

### 1. VoxCity — recommended fork target

VoxCity models urban environments as a grid-based 3D voxel model where terrain, buildings, trees/canopy, and land cover are assigned semantic classes. The documented coordinate model is a mesh-size-aligned voxel grid, which maps naturally to a Minecraft `1 voxel = 1 block` or `1 voxel = N blocks` conversion. Its generator fills ground, building, tree, and land-cover classes into a combined voxel array, and its exporters already include OBJ and MagicaVoxel `.vox`. ([voxel model concept](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/docs/concepts/voxel_model.md), [voxelizer source](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/src/voxcity/generator/voxelizer.py), [MagicaVoxel exporter](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/src/voxcity/exporter/magicavoxel.py), [exporter module](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/src/voxcity/exporter/__init__.py))

The data-source model is close to what we need. VoxCity documents building sources including OSM, Microsoft Building Footprints, Google Open Buildings, EUBUCCO, UT-GLOBUS, and Overture; canopy/land-cover sources; and terrain sources including USGS 3DEP 1 m DEM. That makes Montgomery County building footprints, local DEM rasters, and orthophoto-derived land/material masks straightforward custom sources. ([data sources](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/docs/reference/data_sources.md))

It also has an escape hatch for high-value campus buildings: the Rhino/OBJ import guide supports adding closed building solids, one building per object/layer, and reclassifying facade voxels to glass when material or group names contain window/glass/glazing hints. That is useful for Hill-authorized landmark meshes or manually repaired building OBJ exports. ([Rhino/OBJ import guide](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/docs/guides/rhino_obj_import.md))

The main missing feature is direct LAZ ingestion. VoxCity talks about LiDAR-derived products and DEMs, but the inspected docs/source/dependency metadata do not show a direct `laspy`, PDAL, LAS, or LAZ point-cloud reader. That is acceptable because the adapter is bounded: rasterize the cached USGS LAZ into terrain DSM/DTM/nDSM/building/canopy grids outside or inside a Hill-specific VoxCity fork, then feed those grids into VoxCity’s existing voxel model. ([pyproject dependency metadata](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/pyproject.toml), [data sources](https://github.com/kunifujiwara/VoxCity/blob/41d766f5a34cd294b9e945c54f17a06c82daacc6/docs/reference/data_sources.md))

Proposed Hill fork plan:

1. Add a `LocalHillSources` adapter that reads local Montgomery County footprints, cached USGS DEM/LAZ, OSM extracts, and authorized orthophotos from fixed project paths.
2. Add LAZ rasterization using `laspy`/`lazrs` plus `rasterio`/`numpy`: ground points to DTM, first/high returns to DSM, classified building/vegetation masks where available, and nDSM for height estimation.
3. Map county footprints to building voxels, using footprint polygons for plan shape and LAZ/DSM/DEM differences for per-building height. Where roof/facade fidelity matters, override the procedural mass with school-authored OBJ/GLB-to-OBJ assets.
4. Add an imagery sampler that assigns Minecraft block palettes from orthophoto color plus semantic class. Keep semantic priority above raw color so grass, turf, roofs, asphalt, stone, trees, water, and glass remain readable in game.
5. Add a Minecraft exporter that converts VoxCity class arrays to this repository’s `structure.nbt` writer first. Add Anvil/Sponge `.schem` later only if the deliverable requires a complete standalone world.

This path keeps the hard geospatial problem in a geospatial codebase and keeps the Minecraft write path small and testable.

### 2. Arnis — best Minecraft-world fallback, not the best LAZ core

Arnis is the strongest maintained Minecraft output project in the set. It creates Minecraft Java 1.17+ and Bedrock worlds from real-world geography/topography/architecture and supports generation modes such as terrain-only, geo-only, and combined geo-terrain. Its Rust dependencies include Java Anvil and Bedrock world-writing crates, and the source contains dedicated Java and Bedrock world editors. ([Arnis README](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/README.md), [argument parser](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/src/args.rs), [Cargo metadata](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/Cargo.toml), [world editor module](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/src/world_editor/mod.rs))

Arnis already handles U.S. elevation through a USGS 3DEP provider that calls the National Map elevation image service, with documented native 1 m coverage for the continental U.S. It also has an Overture provider; the source comments describe building hints from Overture sources including Microsoft, Esri, and USGS 3DEP LiDAR-derived height/floor information. That is useful, but it is still not direct local LAZ ingestion or county-footprint-first generation. ([USGS 3DEP provider](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/src/elevation/providers/usgs_3dep.rs), [Overture integration](https://github.com/louis-e/arnis/blob/97a2a7f44ca42d33741a46b8274c8e2e19a48509/src/overture.rs))

Arnis should remain the QA baseline: run the same Hill bounding box through Arnis and compare roads, water, gross terrain, and building placement. If we later need a full playable world instead of a structure import, porting a VoxCity class grid into Arnis-style region writing is a credible route.

### 3. CityMinecraft — technically closest, legally blocked

CityMinecraft is the closest technical match found. The README describes a generation pipeline for Turku that reads LiDAR, downloads aerial images, uses OSM/GML, decorates the result, and emits schematic/Minecraft-world outputs. It documents `.laz` input and user-configurable LiDAR-to-block mappings. The LAS reader imports `laszip4j`, opens LAS/LAZ files, maps classification codes, scales points, and returns `LazData`. ([CityMinecraft README](https://github.com/andreiBe/CityMinecraft/blob/928d7152476acb947c253fe8654b59cb4d8888b6/README.md), [LAS reader source](https://github.com/andreiBe/CityMinecraft/blob/928d7152476acb947c253fe8654b59cb4d8888b6/LAS/src/main/java/org/patonki/reader/LasReader.java))

The blocker is licensing. The inspected repository tree has no license file. Without a license or direct permission, we should not fork, copy, or incorporate its implementation. The second issue is regional coupling: its serialized defaults include Finnish/Turku services, EPSG:3877, Geofabrik Finland shapefiles, Turku point-cloud URLs, and Turku WFS/WMS endpoints. ([repository tree](https://github.com/andreiBe/CityMinecraft/tree/928d7152476acb947c253fe8654b59cb4d8888b6), [Turku-specific default source configuration](https://github.com/andreiBe/CityMinecraft/blob/928d7152476acb947c253fe8654b59cb4d8888b6/Main/src/main/java/org/patonki/serialize/JsonSerializer.java))

Use it to validate architecture-level decisions only: stage separation, block-class mappings, and the idea of treating point-cloud, orthophoto, vector, and building-model sources as separate cacheable phases.

### 4. Cloud2Craft — direct LAZ point-cloud voxelizer, wrong output model

Cloud2Craft is a direct point-cloud-to-Minecraft uploader. Its README states that it accepts `.las` and `.laz`, exposes voxel size in millimetres per block, and supports multiple color palettes. Its Python dependencies include `laspy`, `laszip`, `lazrs`, `open3d`, and `mcpi`; the source opens LAS/LAZ with `laspy.open`, processes chunks, creates an Open3D voxel grid, maps colors to blocks, and sends blocks into Minecraft through RaspberryJuice/`mcpi`. ([Cloud2Craft README](https://github.com/AntoineMiras/Cloud2Craft/blob/8c9f346077b8f7b32cc92efca932f18367b98d88/README.md), [requirements](https://github.com/AntoineMiras/Cloud2Craft/blob/8c9f346077b8f7b32cc92efca932f18367b98d88/requirements.txt), [main source](https://github.com/AntoineMiras/Cloud2Craft/blob/8c9f346077b8f7b32cc92efca932f18367b98d88/Cloud2Craft/cloud2craft.py), [GPLv3 license file](https://github.com/AntoineMiras/Cloud2Craft/blob/8c9f346077b8f7b32cc92efca932f18367b98d88/Licence))

It is not a good core for Hill. It has no terrain/building/roof/road/land-cover semantics and does not emit a durable world or structure file as its primary output. It is still useful for small algorithm checks: LAZ chunking, voxel-size tradeoffs, color-palette matching, and point-density thinning.

### 5. GeoCraft — good historical LiDAR + OSM concept, UK-specific and GPL

GeoCraft generates Minecraft maps of real locations using UK LiDAR and OSM. It reads DEFRA DSM/DTM raster products, uses GDAL conversion, and writes Minecraft saves/region data. Its README and source are tightly coupled to UK postcode/easting/northing workflows and DEFRA APIs. ([GeoCraft README](https://github.com/cgutteridge/geocraft/blob/55da3901ba4072ef43be003f88302ec7f15026cb/README.md), [DEFRA LiDAR source](https://github.com/cgutteridge/geocraft/blob/55da3901ba4072ef43be003f88302ec7f15026cb/lib/Elevation/UKDEFRA.pm), [GPLv3 license](https://github.com/cgutteridge/geocraft/blob/55da3901ba4072ef43be003f88302ec7f15026cb/LICENSE))

Its design validates the same core thesis as VoxCity: use terrain/surface rasters plus OSM semantics rather than generic heightmap-only generation. It is not a good Hill fork base because the data sources, projection assumptions, Perl/GDAL workflow, and GPLv3 license all increase adaptation cost.

### 6. VoxelEarth — keep for authorized GLB/3D Tiles sidecar voxelization

VoxelEarth is relevant because the user explicitly mentioned VoxelEarth-style tooling and GitHub reuse. The official code page describes an open-source stack for GPU kernels/plugins/viewers, Minecraft server setup on Paper/Spigot/Bukkit 1.20+ with Java 21+, and browser exports to NBT/schem/mcfunction. The README describes a pipeline for 3D Tiles/GLB meshes, CPU voxelization, FAWE placement, browser preview, and companion CLIs. ([VoxelEarth code page](https://voxelearth.org/code/), [VoxelEarth README](https://github.com/ryanhlewis/VoxelEarth/blob/ed68433d762ca070d2cdbd68a2222142b0a08d30/README.md))

VoxelEarth is not a replacement for the GIS generator because it operates on photogrammetry/3D Tiles/GLB mesh sources rather than local LAZ + county-footprint + DEM semantics. It is useful for a separate right-cleared mesh path: take Hill-authorized GLB/OBJ assets, voxelize them robustly, and import them as landmark overlays or replacement building shells.

License note: the README says the VoxelEarth project and companion CLIs are MIT unless otherwise noted, but the inspected clone did not include a root license file. If we reuse more than small ideas, verify the license with the upstream maintainer or use only code paths that have explicit license files. ([VoxelEarth README license section](https://github.com/ryanhlewis/VoxelEarth/blob/ed68433d762ca070d2cdbd68a2222142b0a08d30/README.md))

### 7. OSM2World — best procedural roof/OSM geometry reference

OSM2World converts OSM data into 3D models and exports formats such as glTF/glb and OBJ. Its project site describes broad OSM tag/material support, and the source includes building/roof modules for procedural roof geometry. It is MIT-licensed and current, but it does not read LAZ or write Minecraft worlds. ([OSM2World README](https://github.com/tordanik/OSM2World/blob/e58e986546aa4af927d1e74929996ae4f311c5c3/README.md), [official project site](https://osm2world.org/), [CLI output modes](https://github.com/tordanik/OSM2World/blob/e58e986546aa4af927d1e74929996ae4f311c5c3/desktop/src/main/java/org/osm2world/console/legacy/CLIArgumentsUtil.java), [building roof modules](https://github.com/tordanik/OSM2World/tree/e58e986546aa4af927d1e74929996ae4f311c5c3/core/src/main/java/org/osm2world/world/modules/building/roof), [MIT license metadata](https://github.com/tordanik/OSM2World/blob/e58e986546aa4af927d1e74929996ae4f311c5c3/pom.xml))

Use it as a reference only if we decide to generate better roofs from OSM/building tags before voxelization. It should not be the main Hill engine.

### 8. mesh_to_schematic and FileToVox — useful format converters, not geodata engines

The Helsinki `mesh_to_schematic` project converts 3D city mesh models into colored Minecraft models and can produce `.schematic`/world artifacts through a Windows batch workflow involving FileToVox, MagicaVoxel, and vox2schematic. It is MIT-licensed but old and fragile because parts of the workflow automate GUI tools. ([mesh_to_schematic README](https://github.com/City-of-Helsinki/mesh_to_schematic/blob/7d3fed1574d10b89df49dc8db5dfc7fc676d5785/README.md), [batch workflow](https://github.com/City-of-Helsinki/mesh_to_schematic/blob/7d3fed1574d10b89df49dc8db5dfc7fc676d5785/mesh_to_schematic.bat), [MIT license](https://github.com/City-of-Helsinki/mesh_to_schematic/blob/7d3fed1574d10b89df49dc8db5dfc7fc676d5785/LICENSE))

FileToVox is a MIT-licensed converter to MagicaVoxel `.vox` that supports many mesh, raster, point, and schematic-adjacent formats, including OBJ/PLY/XYZ/TIF and textured mesh conversion. It does not provide the geodata fusion we need. ([FileToVox README](https://github.com/Zarbuz/FileToVox/blob/e860ee2c269121982419ca08da84e045e5c68940/README.md), [MIT license](https://github.com/Zarbuz/FileToVox/blob/e860ee2c269121982419ca08da84e045e5c68940/LICENSE))

These tools are candidates for one-off asset conversion tests, not for the main campus pipeline.

### 9. 2schematic — historical RGB-D/point-cloud converter

2schematic converts colored real-world RGB-D 3D models to MCEdit `.schematic`, using Octomap/PCL input formats such as `.ot` and `.pcd`. It is old, GPLv3, and not a GIS/LiDAR/campus data-fusion engine. ([2schematic README](https://github.com/idryanov/2schematic/blob/ebd3508585ad93b906229f81c898c38becd0a385/README.md), [build metadata](https://github.com/idryanov/2schematic/blob/ebd3508585ad93b906229f81c898c38becd0a385/CMakeLists.txt), [license text](https://github.com/idryanov/2schematic/blob/ebd3508585ad93b906229f81c898c38becd0a385/COPYING))

## Concrete Hill implementation path

The most defensible route is a two-layer system:

1. **VoxCity-derived semantic voxel core.** Read Hill-local DEM/LAZ/footprints/imagery, create a metre-scale semantic voxel array, and preserve class labels through the pipeline.
2. **Repository-native Minecraft exporter.** Convert semantic voxels to `structure.nbt` using this repository’s existing import contract. Keep world/Anvil output as a later layer only if required.

Initial class mapping should be explicit and auditable:

| VoxCity / Hill class | Minecraft block strategy |
| --- | --- |
| Bare-earth terrain | grass block / dirt / stone by surface and slope |
| Orthophoto grass | grass block, moss, short grass, leaf litter variants |
| Athletic turf | green concrete/terracotta/wool palette, field-line overlays |
| Roads and parking | black/gray concrete, stone, smooth basalt, stripe overlays |
| Sidewalks/paths | smooth stone, stone bricks, gravel variants |
| Water | water plus shoreline blocks |
| Tree canopy | leaf palette by imagery/season; trunk inferred from canopy centroid |
| Building mass | stone/brick/quartz/terracotta by footprint class and imagery roof sample |
| Roof | sampled roof color, fallback by building type/known campus style |
| Glass/windows | explicit from authored OBJ materials or procedural facade pass |

This gives the Hill School project a maintainable path: local authoritative data controls geometry; authorized school imagery/meshes can improve landmark fidelity; and third-party code is limited to permissively licensed infrastructure.

## Bottom line

Use **VoxCity as the fork target**. Use **Arnis as the playable-world benchmark/output reference**. Use **CityMinecraft as a design reference only pending license permission**. Use **VoxelEarth only for Hill-owned/right-cleared GLB or 3D Tiles assets**, not as the core LiDAR/GIS generator.
