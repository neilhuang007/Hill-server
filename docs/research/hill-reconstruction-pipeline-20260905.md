# Hill reconstruction pipeline: source audit, 5 September 2026

This research supports the 175th anniversary Minecraft reconstruction. It updates the tool comparison in [the existing pipeline note](hill-school-voxel-map-pipeline.md) and records evidence for the **Class of 1960 Alumni House**, the small non-chapel test building. It is a source and procedure audit; it does **not** certify a finished campus or a successful in-game likeness comparison.

## Recommended construction method

Use a **semantic model followed by deterministic Minecraft construction**. Derive terrain and major building geometry from LiDAR and county outlines, preserve them as measured reference layers, and describe each visible architectural element separately: brick walls, roof slopes, windows, trim, porch columns, railings, stairs, and planting. Generate the Minecraft shell and repeated facade elements directly from that description. Use Blender to inspect geometry, correct selected forms, and render comparison cameras.

This is an engineering recommendation from the capabilities below. A complete photorealistic Blender campus would add modelling work that is discarded when reduced to blocks. A raw coloured voxel cloud would retain photographic shadows and vegetation contamination while missing construction intent. A semantic intermediate representation can retain the efficiency of geodata generation and the deliberate material choices of a human builder.

| Tool | Verified capability | Appropriate Hill role and limit |
| --- | --- | --- |
| **MapSmith** | Arnis's official hosted generator accepts a drawn region and spawn point, offers Java or Bedrock downloads, and uses real-world map/elevation data. It explicitly says detail depends on OpenStreetMap coverage. | Quick baseline or comparison world. The reviewed page does not document importing our LiDAR, roof mesh, or custom architectural palette; do not assume the hosted service exposes a swappable terrain module. [Official MapSmith](https://arnismc.com/mapsmith/) |
| **Arnis v3.1.0** | The latest release URL resolved to v3.1.0 on the research date. The release adds local `.osm` input, canopy-height trees, Overture fallback building heights, and building details. Its source includes a USGS 3DEP provider with 1 m and coarser resolution levels. | Reusable open-source terrain/site generation and independent baseline. Prefer an explicit local geodata build for buildings whose facade information is absent from OSM. [Release](https://github.com/louis-e/arnis/releases/tag/v3.1.0), [USGS provider source](https://github.com/louis-e/arnis/blob/v3.1.0/src/elevation/providers/usgs_3dep.rs) |
| **Roofer** | Reconstructs buildings from a point cloud and 2D roofprint, offers LoD1.2/1.3/2.2, C++/Python interfaces and a CLI producing CityJSONSequence. | Best measured roof-shell stage here. Its piecewise-planar, vertical-wall model cannot represent balconies or roof overhangs; these require a separate architectural pass. [Official documentation](https://innovation.3dbag.nl/roofer/), [algorithm assumptions](https://innovation.3dbag.nl/roofer/reconstruct_params.html) |
| **Voxel Earth** | Modular download, decode and CPU voxelization pipeline; its CLI can emit RGB palette plus `xyzi` JSON. The plugin documents FAWE integration and focuses its tested support on Paper/Spigot 1.20.4. | Useful mesh sampling reference and optional adapter for independently sourced meshes. Its README does not establish compatibility with this repository's newer Minecraft runtime. [Project README](https://github.com/ryanhlewis/VoxelEarth) |
| **ObjToSchematic 1.0 source** | Public `LucasDower/ObjToSchematic` is explicitly the legacy 1.0 editor, now without regular updates. It documents texture multisampling, visible-face colour averaging, custom block palettes, a texture smoothness penalty, falling-block replacement, and `.nbt`, `.schem`, `.litematic` export. | A concrete code reference for sampling and restricted material assignment. Do not describe this repository as source for the current 2.0 editor. [Legacy source and documentation](https://github.com/LucasDower/ObjToSchematic/tree/ots-1.0) |
| **ObjToSchematic 2.0 website** | The current official wiki documents separate model → voxel → block stages, texture area sampling, block palettes, custom atlases, modifiers, and schematic/Litematica/MCFunction workflows. | Independent conversion and visual comparison of a small authored mesh. The public legacy source does not establish that 2.0 can be modified locally. [Current official wiki](https://objtoschematic.com/wiki) |
| **Blender** | The intended role in this project is editing selected architectural geometry, viewing the measured roof shell and generated blocks, and rendering repeatable cameras. | Treat this as our workflow choice, not a claim that Blender automatically knows the real facade or exports valid Minecraft block states. Keep the semantic model and exporter as the authoritative block description. |

### Specific sampling issue found in Voxel Earth source

The inspected `JavaCpuVoxelizer.java` loads **the first GLB image as one global texture**, samples clamped UV coordinates bilinearly, and writes colour-indexed voxel JSON. This is not a per-material architectural block classifier. A Blender model with several materials/textures must not be assumed to work correctly through that code unchanged. If borrowing the sampler, resolve each primitive's material and texture first, retain transforms, and carry a semantic material ID through voxelization. Apply colour matching only inside that material's allowed block family. [Inspected source](https://github.com/voxelearth/java-cpu-voxelizer/blob/main/src/main/java/com/example/voxelizer/JavaCpuVoxelizer.java)

Arnis identifies its code as Apache-2.0, Roofer documents GPLv3, and the legacy ObjToSchematic repository identifies BSD-3-Clause. Keep tools as separate stages unless code is deliberately incorporated with its applicable notices and obligations. An open-source tool's licence does not grant rights to third-party imagery fed into it. [Arnis source](https://github.com/louis-e/arnis), [Roofer licence](https://innovation.3dbag.nl/roofer/#license), [ObjToSchematic licence](https://github.com/LucasDower/ObjToSchematic/blob/ots-1.0/LICENSE)

## Geographic evidence and acquisition

| Source | Evidence available | Interpretation boundary |
| --- | --- | --- |
| Hill's current campus map | Names Class of 1960 Alumni House as **48**. | Use for identity, not dimensions. [Current official map page](https://www.thehill.org/admission/visiting-campus/campus-map) |
| Hill's July 2021 address map | Names Class of 1960 Alumni House at **715 High St.**, numbered **16** in that edition. | Map numbers changed; match by name/address, not number alone. [Official July 2021 PDF](https://resources.finalsite.net/images/v1633097238/thehillorg/ewtimjvxagjkgblsqf5q/fy22campusmapgraphic.pdf) |
| Montgomery County building outline | Fresh REST query on 2026-09-05 returned `STRUCTUREID=1600151120011C`, `PARID=160015112001`, `Height=31`, `STORIES=0`, `YRBLT=1900`, and mixed residential/commercial classification. | The height field's unit was not established by this query. Do not use `31` as metres or treat `STORIES=0` as an actual storey count. [County layer](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6) |
| USGS The National Map | A fresh campus query returned `PA_17County_D24` LAZ products; examples `18TVK445454` and `18TVK445455` have publication date **2026-04-18**. | Publication date is not flight date. Preserve the source product metadata and CRS with the local cache. [Reproducible LPC query](https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-75.63850,40.24338,-75.62273,40.25369&datasets=Lidar%20Point%20Cloud%20%28LPC%29&prodFormats=LAZ&max=100), [example LAZ](https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/PA_17County_D24/PA_17Co_5_D24/LAZ/USGS_LPC_PA_17County_D24_18TVK445454.laz) |
| PEMA/PASDA orthophotography | Cycle 2 project metadata describes 0.5 ft, four-band RGBN imagery and states no access/use restrictions, with acknowledgement appreciated. | Useful for roof/site alignment and horizontal material zones. Check the actual local tile's capture date and coverage; the generic metadata page's bounding coordinates do not cover Pottstown. It is not a facade survey. [Project metadata](https://www.pasda.psu.edu/uci/FullMetadataDisplay.aspx?file=PEMA_Cycle2_2021.xml), [regional imagery service](https://apps.pasda.psu.edu/arcgis/rest/services/PEMAImagery2021_2023/MapServer) |

Roofer requires a consistent projected metre CRS, aerial LAS/LAZ with ground/building classification, removal of outliers, roofprints aligned to the cloud, and ground points around buildings. Its authors report good results around 10 points/m², while also stressing even coverage. A dense cloud alone does not establish a correct model. [Input requirements](https://innovation.3dbag.nl/roofer/data_requirements.html)

### Measured model record for the Alumni House

The following values were read from the existing local [campus CityJSON](../../runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json) on 2026-09-05. The directory name is historical; the selected feature is the Alumni House, not the chapel.

| Item | Value |
| --- | --- |
| Building parent | `1600151120011C-e738fb4171` |
| LoD2.2 solid | Child `1600151120011C-e738fb4171-0`, geometry with `lod="2.2"` |
| Ground estimate | `rf_h_ground = 51.919998` m; project uses NAVD88 heights |
| Ridge estimate | `rf_h_roof_ridge = 63.238228` m |
| Ridge above estimated ground | About **11.32 m**, calculated by subtraction |
| Roof planes / ridgelines | `23` / `3` |
| Model fit diagnostic | `rf_rmse_lod22 = 0.410019` m |
| Point density diagnostic | `rf_pt_density = 29.376827` points/m² |
| Status fields | `rf_success=true`, `rf_pointcloud_unusable=false`, `rf_nodata_frac=0` |
| Embedded acquisition metadata gap | `rf_pc_year=0` and empty `rf_pc_source`; source year must come from the external acquisition manifest |

These are **algorithm-derived measurements**, not survey-certified heights or a facade validation score. The 0.410 m model-fit diagnostic does not mean every facade or roof detail is accurate to 0.410 m. County outline edges can represent a different building boundary from a roofprint. The roof mesh is useful evidence for massing and slope, while porch depth, cornices, columns, window recesses and material boundaries require separate evidence.

## Exterior photographic evidence

James Bradberry Architects identifies its project as the Hill School's renovated Queen Anne Revival alumni house. Its [project page](https://www.jamesbradberry.com/new-page) contains one confirmed exterior photograph: [full-resolution front/side view](https://images.squarespace-cdn.com/content/v1/5988a923c534a5f2895959c1/1541532697942-UB6KC7K5VBA4ZJ3WVLMT/Hill%2BAlumni%2BExt%2BAlt%2B2.jpg), cached as [architect-front.jpg](../../runtime/research/alumni-house-20260905/architect-front.jpg). The file's CDN timestamp indicates an upload in 2018, not a verified capture date.

**Visible interpretation:** red brick walls; light cream trim; a broad shingled front gable with clipped upper corners; a small balcony below paired attic windows; a single second-floor window on image left and paired arched windows to its right; a low wraparound porch with slender posts, lattice frieze and balustrade; a tall brick chimney on image right. Trees obscure parts of the side and roof. The extra architect image named `HillAlumn1 copy.jpg` was inspected and is an interior, so it supplies no additional exterior elevation.

The historical listing for the exact address also carries direct **TREND MLS photographs**, syndicated by Redfin. The page attributes listing `5527181` to Brian Kelly/Kelly Real Estate and records a December 2009 sale. Treat these as historical photographic evidence, not current-condition certification. Their visible front gable, balcony, windows and porch match the architect view. [Listing and provenance](https://www.redfin.com/PA/Pottstown/715-E-High-St-19464/home/40309836)

| Direct photograph | Useful visible evidence | Local cache |
| --- | --- | --- |
| [Front](https://ssl.cdn-redfin.com/photo/93/bigphoto/181/5527181_0.jpg) | Main facade and chimney | `listing-2009-front.jpg` |
| [Opposite front angle](https://ssl.cdn-redfin.com/photo/93/bigphoto/181/5527181_8_0.jpg) | Tall projecting bay/wing at image left | `listing-2009-8.jpg` |
| [Porch angle](https://ssl.cdn-redfin.com/photo/93/bigphoto/181/5527181_6_0.jpg) | Wraparound porch, side door, steps | `listing-2009-6.jpg` |
| [Lower front angle](https://ssl.cdn-redfin.com/photo/93/bigphoto/181/5527181_4_0.jpg) | Porch posts and entry approach | `listing-2009-4.jpg` |
| [Porch wall](https://ssl.cdn-redfin.com/photo/93/bigphoto/181/5527181_5_0.jpg) | Openings under porch; compass orientation unresolved | `listing-2009-5.jpg` |
| [Street-wide front](https://ssl.cdn-redfin.com/photo/93/bigphoto/181/5527181_11_0.jpg) | Raised frontage and retaining-wall context | `listing-2009-11.jpg` |

All listed caches are under [runtime/research/alumni-house-20260905](../../runtime/research/alumni-house-20260905/). The retrieved listing images are only 336 × 252 pixels. The separate three-door garage photograph is a different structure on the parcel and must not be merged into the house shell. None of the twelve inspected listing photographs establishes a complete rear/north elevation. Do not label these images “Street View”; they are photographer/listing images. No current rear facade or complete current side-elevation photo was verified in this research pass.

## Construction and audit procedure

The following is a proposed implementation and acceptance procedure, not completed QA results.

1. **Freeze the reference frame.** Store source URLs, acquisition dates, local hashes, horizontal CRS, vertical datum, metre origin, rotation and blocks-per-metre in a build manifest. Transform every source once into the same local metre frame. Keep the untouched footprint and reconstructed roof as comparison layers.
2. **Resolve scale on the small building.** Compare 1 and 2 blocks/metre for the Alumni House; use 4 only as a detail experiment if necessary. Select based on whether the paired windows, porch gaps and roof profile remain legible at planned ad-camera distances. A scale change must apply consistently to the world, with a corresponding camera height; it must not silently enlarge only one building.
3. **Generate terrain and shell.** Use ground returns/DEM for terrain, roof planes for slope, and explicit walls for the envelope. Inspect all roof components against points and orthophotography before adding ornament. Preserve doors, porch openings and space below overhangs; filling every cell of the bounding volume is not an acceptable shell.
4. **Author facade semantics.** Locate windows, corners, posts and material boundaries using the measured footprint and independently sourced photographs. Represent repetitive parts parametrically. Put confirmed elements and inferred elements in different model layers, so an unsupported rear wall is never confused with a measured facade.
5. **Assign a construction palette first.** Give each semantic surface a short allowlist. Initial choices to test are bricks for brickwork; stone/smooth stone for foundation and paths; deepslate tiles or stone brick variants for gray roofing; birch/appropriate pale construction blocks for cream trim; glass panes for glazing; and ordinary fences, walls, stairs and slabs where their shapes fit. These are proposed Minecraft approximations, not claims about the actual paint or roof material.
6. **Apply colour sampling inside those classes.** Limit any sampled colour variation to the selected family. Preserve broad material regions, window repetition and mortar/trim rhythm. Do not bake photographic shadows into permanent black patches or let foliage pixels recolour a wall. Avoid unrestricted RGB nearest-neighbour assignment across the game's entire block inventory.
7. **Enforce export rules.** Reject every block state outside the allowlist, including all ores and sculk as requested. Check that exterior gravity blocks have support, panes/railings connect, stairs face correctly, and the export's version/block IDs load in the actual runtime. Count forbidden blocks in the exported artifact, not just the configuration.
8. **Audit in two distinct stages.** Blender views test geometry and composition. Minecraft screenshots test actual textures, lighting, block states, collision and recognizable facade rhythm. A Blender render is not evidence that the in-game scene matches. Match camera position, direction, focal field and reference orientation before judging a comparison.
9. **Iterate by visible error.** Fix silhouette, roof breaks, width/height proportions, bay placement, porch depth and window grouping before fine colour changes. Capture the same front, oblique and overhead cameras after each revision. Record the reference, defect, change, new screenshot and unresolved uncertainty. Check rear/occluded views only to the level the available evidence supports.
10. **Expand across campus only after the trial is convincing.** Keep terrain/site layers reusable and replace each generic building with its own semantic architectural record. Do not infer campus-wide fidelity from one attractive prototype.

For the trial, the acceptance record should state whether the clipped front gable, left projection, right chimney, upper window grouping, balcony and open wraparound porch are recognizable at street distance. It should separately state whether the real game has been viewed, what reference was used, and which faces remain unresolved. Numerical roof-fit diagnostics and a zero-forbidden-block count are necessary checks, but neither proves visual likeness.

## Google Maps boundary

Google's current Maps Platform terms restrict exporting/scraping Maps content and creating content from it; the Map Tiles policy additionally restricts machine interpretation/geodata extraction and says an overlaid model must not be traced or derived from Photorealistic 3D Tiles. Keep the durable Minecraft geometry and sampling inputs on the independently sourced path described above. Do not assume that Voxel Earth's description of itself as a viewer grants permission to archive Google-derived meshes or voxel worlds. Google can remain an ordinary linked viewer for contextual comparison under the applicable service terms. [Maps Platform terms, §3.2.3](https://cloud.google.com/maps-platform/terms), [Map Tiles policies](https://developers.google.com/maps/documentation/tile/policies)

The remaining accuracy limit is evidence, not lack of a voxelizer: a roof point cloud and front photograph do not determine hidden facade details. Record those gaps while continuing all work that the measured geometry and verified photographs support.
