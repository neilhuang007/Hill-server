# High-fidelity Hill School Minecraft map pipeline

Verified: 2026-08-30. Target: The Hill School main campus, 860 Beech Street, Pottstown, Pennsylvania 19464, delivered as a Minecraft Java world for this repository's Paper 26.2 build 119 / Java 25 runtime. ([repository README](../../README.md), [world provenance manifest](../../server-assets/worlds.yml))

## Decision

For this repository, use a **direct, streamed `structure.nbt` generator at `1 block = 1 metre`** from current D24 elevation/lidar, Montgomery County GIS, OSM site features, PEMA orthophotos, and the official campus map. That matches the existing People-mode import contract and permits deterministic clipping/palette rules without first generating and reconverting a complete world.

Implemented local tools:

- `scripts/generate-hill-campus.py` writes the campus structure, preview PNG, and provenance manifest. The active phase 1 server asset is DataVersion `4903`, size `1338 x 117 x 1143`, `4,195,187` block records, 50/50 county building footprints placed on level cut/fill pads, and 900 lidar-derived trees. The generated NBT SHA-256 is `FCBBEF9200E73B04F1493BFB087B0E2FBF462AADB58DF7A3E1D336F82C34AA04`.
- `scripts/voxelearth_glb_to_structure.py` is a local VoxelEarth-compatible GLB voxelizer for Hill-owned/right-cleared meshes. It applies glTF node transforms, skips non-triangle primitives and primitives with no `POSITION` accessor, writes VoxelEarth `blocks`/`xyzi` JSON, and can also write this server's structure NBT.
- `scripts/minecraft_structure.py` contains an independent streamed structure-NBT writer/metadata reader used by the GLB path.

Keep **Arnis v3.1.0 as the off-the-shelf baseline, QA reference, and full-world fallback**. Its current terrain and local-OSM path are materially better than a generic MapSmith result; the documented Arnis workflow below also provides an independent comparison against the custom generator. If a standalone, explorable world becomes the deliverable instead of `structure.nbt`, generate a scale-1 baseline, then consider a scale-2 final world and hand-build the recognizable architecture.

MapSmith is the Arnis project's hosted/browser generation option, but this job needs v3.1.0's repeatable CLI, local `.osm` input, explicit scale/preview controls, and a private data-fusion step. Keep MapSmith for rough comparisons, not the master output. Cloud2Craft can upload LAS/LAZ point clouds into old Spigot/RaspberryJuice servers, and GeoCraft/VoxCity are useful references for lidar/geodata voxel models, but none is a drop-in importer for this Paper 26.2 structure workflow. WorldPainter can repair a heightmap/landscape locally, and WorldEdit/FAWE is useful for the architectural pass, but neither supplies the complete geodata-to-campus pipeline. ([Arnis README](https://github.com/louis-e/arnis/tree/v3.1.0), [Cloud2Craft README](https://github.com/AntoineMiras/Cloud2Craft), [GeoCraft README](https://github.com/cgutteridge/geocraft), [VoxCity README](https://github.com/kunifujiwara/VoxCity))

Do **not** use Google Photorealistic 3D Tiles from Voxel Earth as the source of an exported Minecraft world. Voxel Earth is useful only as a live preview or, for export, with a Hill-owned or otherwise rights-cleared GLB/3D Tiles source. Google's current terms prohibit exporting/caching Maps content and creating 3D building models from it; its tile policy also restricts extraction, offline use, and caching. The Voxel Earth code license does not grant rights to its source tiles. ([Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms), [Google Map Tiles policies](https://developers.google.com/maps/documentation/tile/policies), [Voxel Earth data-use notice](https://github.com/ryanhlewis/VoxelEarth#acknowledgements--data-usage))

The result should be described accurately:

- Automated generation can produce a strong terrain, road/path, field, pond, tree, and building-massing base.
- Public data does not contain authoritative facades or interiors. A convincing Hill map therefore needs a manual landmark pass using school-authorized plans, photographs, and/or a supervised site walk.
- Leave procedural interiors off. Do not infer or publish private dormitory, residential, security, or back-of-house layouts.

## Exact location and working extents

The school confirms the main-campus address as **860 Beech Street, Pottstown, PA 19464** and says the campus is more than 200 acres. Its current campus map names 51 locations. ([Hill contact page](https://www.thehill.org/about-us/people-of-the-hill/contact-us), [Hill at a glance](https://www.thehill.org/about-us/hill-at-a-glance), [Hill campus map](https://www.thehill.org/about-us/people-of-the-hill/contact-us/campus-map))

The US Census geocoder matches the address at longitude `-75.630525387636`, latitude `40.247130405299`. That point is an address-range geocode, useful as a sanity check but **not** a campus centroid or entrance survey. ([reproducible Census geocoder result](https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?address=860%20Beech%20Street%2C%20Pottstown%2C%20PA%2019464&benchmark=Public_AR_Current&vintage=Current_Current&format=json))

Use these WGS84 extents:

| Scope | GIS bbox `[west,south,east,north]` | Arnis bbox `min_lat,min_lng,max_lat,max_lng` | Approximate size | Use |
| --- | --- | --- | ---: | --- |
| Phase 1 academic/athletic campus | `[-75.63850,40.24338,-75.62273,40.25369]` | `40.24338,-75.63850,40.25369,-75.62273` | `1,342 x 1,145 m` | Active server asset |
| Full Hill-owned property envelope | `[-75.63850,40.24338,-75.61807,40.26086]` | `40.24338,-75.63850,40.26086,-75.61807` | `1,730 x 1,943 m` | Optional second phase, including northern/eastern holdings |

The Phase 1 rectangle is the rounded envelope of three adjoining county parcels keyed as `160015116006`, `160016044005`, and `160016052006`; it covers the main address parcel and the Jackson Street athletic area. The full envelope comes from 79 unique county parcel polygons whose assessment owner begins `HILL SCHOOL THE`. Their calculated geometry totals about 197.5 acres, while the assessment acreage fields total about 232.7 acres, consistent with the school's “more than 200 acres” statement. These are reproducible GIS work areas, **not legal campus or survey boundaries**; some school-owned property may not function as student campus. The county likewise says its parcel data is not a legal description. ([Montgomery County GIS data policy](https://www.montgomerycountypa.gov/departments/data-mapping-services/gis-data), [official parcel layer](https://gis.montcopa.org/arcgis/rest/services/Parcels/Montgomery_County_Parcels/FeatureServer/10), [official assessment owner table](https://gis.montcopa.org/arcgis/rest/services/Parcels/GIS_BOA_LAND/FeatureServer/0))

Useful coordinates:

- Phase 1 rectangle centre: approximately `40.24854,-75.63062`.
- Full property-envelope centre: approximately `40.25212,-75.62829`.
- Safe generation QA spawn: `40.2501706,-75.6278572`, near the centre of the mapped artificial-turf football field. Move the public-facing spawn only after reviewing the generated preview and official campus map. ([OSM way 324146951](https://www.openstreetmap.org/way/324146951))

At Arnis scale `1`, Phase 1 is approximately `1,342 x 1,145` blocks. At scale `2`, it is approximately `2,684 x 2,290` blocks. The full envelope at scale `2` is approximately `3,460 x 3,886` blocks and should not be the first expensive run.

## Best source stack

### Source priority

| Purpose | Primary source | What it contributes | Important limitation |
| --- | --- | --- | --- |
| Names and intended campus coverage | [Hill official campus map](https://www.thehill.org/about-us/people-of-the-hill/contact-us/campus-map) | 51 named buildings, fields, gates, housing, and landscape features | Diagrammatic, not survey geometry; school copyright applies |
| Terrain | [USGS 3DEP](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services) through Arnis, plus current D24 OPR/LAZ for QA | Bare-earth relief at approximately 1 m; current point cloud for local checks | Arnis does not accept a custom DEM directly |
| Footprints | [Montgomery County Building Outlines item](https://www.arcgis.com/home/item.html?id=b01273ff63df435dbe4cd8c3e95ce3f7) / [layer 6](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6) | More complete and more precise campus footprints than current OSM | `Height` has no documented unit in the service schema; validate before use |
| Roads, walks, pitches, land use, water | [OpenStreetMap](https://www.openstreetmap.org/copyright) | Useful semantic geometry already understood by Arnis | Campus buildings are sparse and mostly lack level, height, roof, and material tags |
| Visual alignment/material reference | [PEMA 2021–2023 imagery service](https://apps.pasda.psu.edu/arcgis/rest/services/PEMAImagery2021_2023/MapServer) / [metadata](https://www.pasda.psu.edu/uci/FullMetadataDisplay.aspx?file=PEMA_Cycle2_2021.xml) | 0.5 ft / 15 cm, four-band public orthophotos for Pottstown | Montgomery County tiles are 2021 capture; not facade photography |
| Building and tree heights | [USGS The National Map product API](https://tnmaccess.nationalmap.gov/api/v1/docs) and D24 lidar | Roof/canopy surface-minus-ground estimates | Trees touching roofs contaminate automatic height statistics |
| Facades, roof details, materials | Hill-authorized plans/photos/site walk | Recognizable school architecture | Permission and privacy review required |

### Montgomery County building data

The county building layer was originally derived from spring 2020 Nearmap data and is updated annually by Montgomery County; the item says it was last updated in December 2025. It includes `PARID`, `STRUCTUREID`, `Height`, `STORIES`, `DESCRIPTION`, `Category`, and `YRBLT`. The three Phase 1 parcel IDs select **50** footprints; all 79 owner-matched parcels select **108**. ([building item metadata](https://www.arcgis.com/sharing/rest/content/items/b01273ff63df435dbe4cd8c3e95ce3f7?f=json), [building REST schema](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6?f=pjson))

The layer schema does not state whether `Height` is feet or metres. Values look compatible with feet and some related county datasets use Pennsylvania State Plane feet, but that is not enough to justify an automatic conversion. Use `STORIES` only as a first-pass clue, calculate roof heights from current lidar, and spot-check landmark buildings before writing OSM `height` values in metres.

### Elevation and lidar

Arnis v3.1.0's US elevation selector prefers the official USGS 3DEP 1 m service before its other terrain fallbacks. Its USGS provider calls the 3DEP `ImageServer/exportImage` endpoint, so no separate DEM conversion is required for the practical generator. ([Arnis provider source](https://github.com/louis-e/arnis/blob/v3.1.0/src/elevation/providers/usgs_3dep.rs), [Arnis provider selector](https://github.com/louis-e/arnis/blob/v3.1.0/src/elevation/selector.rs), [USGS 3DEP ImageServer](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer))

For higher-confidence QA and building heights, the newest point cloud intersecting the site is the `PA_17County_D24 / PA_17Co_5_D24` project, collected from 2024-04-23 through 2025-04-02 and published in 2026. The expanded Phase 1 rectangle intersects the same nine current tiles used by the full-candidate run (`18TVK445454` through `18TVK447456` for the 445-447 by 454-456 tile grid), so the current local cache covers both scopes. Query The National Map rather than selecting the four returned legacy 2006-2008 files. ([Phase 1 LPC query](https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-75.63850,40.24338,-75.62273,40.25369&datasets=Lidar%20Point%20Cloud%20%28LPC%29&prodFormats=LAZ&max=100), [full-envelope LPC query](https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-75.63850,40.24338,-75.61807,40.26086&datasets=Lidar%20Point%20Cloud%20%28LPC%29&prodFormats=LAS%2CLAZ&max=100))

For direct terrain QA, use the same project's Original Product Resolution GeoTIFFs rather than assuming the older seamless “1 metre DEM” download is the newest local surface:

- OPR query: [full-envelope current GeoTIFF products](https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-75.63850,40.24338,-75.61807,40.26086&datasets=Original%20Product%20Resolution%20%28OPR%29%20Digital%20Elevation%20Model%20%28DEM%29&prodFormats=GeoTIFF&max=100)
- OPR filename pattern: `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/OPR/Projects/PA_17County_D24/PA_17Co_5_D24/TIFF/USGS_OPR_PA_17County_D24_{tile}.tif`
- LAZ filename pattern: `https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/PA_17County_D24/PA_17Co_5_D24/LAZ/USGS_LPC_PA_17County_D24_{tile}.laz`

The D24 metadata uses NAD83(2011) / UTM zone 18N with NAVD88 heights. Keep lidar/imagery processing in a metre grid such as EPSG:6347 and export final vector coordinates to WGS84/EPSG:4326 for Arnis.

### Rights-cleared orthophotos

The PEMA Cycle 2 metadata specifies 0.5 ft / 15 cm ground sampling distance, 8-bit four-band RGBN imagery, no access restrictions, an as-is disclaimer, and requested acknowledgement. For Pottstown, the four 2021 Pennsylvania South tiles are `34002550PAS`, `34002560PAS`, `35002550PAS`, and `35002560PAS`. They can be loaded through the official map service/WMS or downloaded from the official PASDA paths listed in the metadata and tile index. ([PEMA tile index summary](https://www.pasda.psu.edu/uci/DataSummary.aspx?dataset=5166), [PEMA WMS capabilities](https://imagery.pasda.psu.edu/arcgis/services/pasda/PEMAImagery2021_2023/MapServer/WMSServer?SERVICE=WMS&request=getcapabilities), [PASDA Imagery Navigator](https://maps.psiee.psu.edu/imagerynavigator/))

Direct official archives: [34002550PAS](https://www.pasda.psu.edu/download/pema/pema_imagery/cycle2/TIF/South/2021/Survey_Feet/30000000/34002550PAS_PEMA_2021.zip), [34002560PAS](https://www.pasda.psu.edu/download/pema/pema_imagery/cycle2/TIF/South/2021/Survey_Feet/30000000/34002560PAS_PEMA_2021.zip), [35002550PAS](https://www.pasda.psu.edu/download/pema/pema_imagery/cycle2/TIF/South/2021/Survey_Feet/30000000/35002550PAS_PEMA_2021.zip), and [35002560PAS](https://www.pasda.psu.edu/download/pema/pema_imagery/cycle2/TIF/South/2021/Survey_Feet/30000000/35002560PAS_PEMA_2021.zip).

Use the orthophotos to align walks, curbs, field markings, roof outlines, tree lines, and material zones. Do not attempt photorealistic texture projection onto Minecraft blocks; a deliberate Hill palette and manual facade pass will look cleaner and be much easier to maintain.

## Reproducible workflow

The commands below assume a scratch workspace at `E:\hill-map`; it should stay outside this Git repository until source licensing and final-world packaging are approved.

### 1. Generate a fast Arnis baseline

Download only the official Windows asset from [Arnis v3.1.0](https://github.com/louis-e/arnis/releases/tag/v3.1.0). This release added local `.osm` input, Overture fallback heights, canopy-height trees, and a building-realism overhaul. Arnis is Apache-2.0 licensed and produces Minecraft Java Edition worlds. Its CLI defines `--scale` as blocks per metre, defaults interiors off and Overture on, and can render a top-down preview. ([Arnis README at v3.1.0](https://github.com/louis-e/arnis/tree/v3.1.0), [v3.1.0 CLI arguments](https://github.com/louis-e/arnis/blob/v3.1.0/src/args.rs))

```powershell
New-Item -ItemType Directory -Force E:\hill-map\tools, E:\hill-map\baseline | Out-Null
Invoke-WebRequest `
  -Uri 'https://github.com/louis-e/arnis/releases/download/v3.1.0/arnis-windows.exe' `
  -OutFile 'E:\hill-map\tools\arnis-windows.exe'

& 'E:\hill-map\tools\arnis-windows.exe' `
  --output-dir 'E:\hill-map\baseline\hill-arnis-scale1' `
  --bbox '40.24338,-75.63850,40.25369,-75.62273' `
  --mode geo-terrain `
  --scale 1 `
  --spawn-lat 40.2501706 `
  --spawn-lng -75.6278572 `
  --interior=false `
  --no-3d `
  --map-preview `
  --signage full `
  --fillground
```

This deliberately keeps Overture's default building fallback for comparison. Treat the baseline as disposable QA: review terrain, orientation, field positions, roads, water, missing buildings, false-positive buildings, and tree density before spending time on the final input.

Do not enable `--disable-height-limit`; it is an experimental extended-height datapack, and the local relief does not require it. `--no-3d` avoids unrelated external/bundled props and their visual/licensing noise.

### 2. Download the authoritative Phase 1 footprints

```powershell
New-Item -ItemType Directory -Force E:\hill-map\data | Out-Null

$buildingQuery = 'https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6/query'
$buildingBody = @{
  where = "PARID IN ('160015116006','160016044005','160016052006')"
  outFields = 'PARID,STRUCTUREID,Height,STORIES,DESCRIPTION,Category,YRBLT'
  outSR = '4326'
  returnGeometry = 'true'
  f = 'geojson'
}
Invoke-WebRequest -Method Post -Uri $buildingQuery -Body $buildingBody `
  -OutFile 'E:\hill-map\data\county-buildings.geojson'
```

Open the result over the PEMA orthophotos in QGIS. Confirm there are 50 features, repair any obvious stale outlines, and flag every footprint touched by tree canopy. Keep the untouched county download as provenance; make edits in a versioned copy.

### 3. Fetch the non-building OSM site plan

The extract should contain only the feature classes Arnis can use; a naive “all relations plus all members” request can pull distant relation geometry and make Arnis derive an unexpectedly huge world. This query captures local semantic objects while keeping the request bounded:

```powershell
$overpassQuery = @'
[out:xml][timeout:180];
(
  nwr["building"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["highway"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["landuse"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["natural"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["leisure"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["amenity"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["barrier"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["waterway"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["railway"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["man_made"](40.24338,-75.63850,40.25369,-75.62273);
  nwr["historic"](40.24338,-75.63850,40.25369,-75.62273);
);
out body;
>;
out skel qt;
'@

$overpassBody = 'data=' + [uri]::EscapeDataString($overpassQuery)
Invoke-WebRequest -Method Post `
  -Uri 'https://overpass-api.de/api/interpreter' `
  -Headers @{ 'User-Agent' = 'HillSchoolVoxelMap/1.0' } `
  -ContentType 'application/x-www-form-urlencoded' `
  -Body $overpassBody `
  -OutFile 'E:\hill-map\data\osm-base.osm'
```

In a local, never-upload JOSM/QGIS working copy:

1. Delete OSM `building=*` objects that overlap the three selected campus parcels; retain OSM roads, walks, pitches, barriers, water, land-use areas, and buildings outside the campus parcels.
2. Convert `county-buildings.geojson` with [ogr2osm](https://github.com/roelderickx/ogr2osm) and a small translation that emits `building=yes`, the county structure reference, and `source=Montgomery County GIS Building Outlines`. Use `--never-upload --add-bounds` and negative IDs.
3. Merge the cleaned OSM site plan and converted county footprints. Sort first and validate all node/way references with [Osmium Tool](https://docs.osmcode.org/osmium/latest/).
4. Set the final file header bounds to exactly the Phase 1 rectangle. Remove any relation members extending outside it before trusting Arnis's auto-derived bbox.

Representative commands after the translation and overlap-cleaning steps:

```powershell
ogr2osm 'E:\hill-map\data\county-buildings.geojson' `
  -t 'E:\hill-map\data\hill-translation.py' `
  -o 'E:\hill-map\data\county-buildings.osm' `
  --never-upload --add-bounds --force

osmium sort 'E:\hill-map\data\osm-no-campus-buildings.osm' `
  -o 'E:\hill-map\data\osm-base.sorted.pbf' --overwrite
osmium sort 'E:\hill-map\data\county-buildings.osm' `
  -o 'E:\hill-map\data\county-buildings.sorted.pbf' --overwrite
osmium merge `
  'E:\hill-map\data\osm-base.sorted.pbf' `
  'E:\hill-map\data\county-buildings.sorted.pbf' `
  -o 'E:\hill-map\data\hill-campus.osm' --overwrite
osmium check-refs 'E:\hill-map\data\hill-campus.osm'
```

This fusion is a private generation input. Do not upload county-derived geometry to public OpenStreetMap without following OSM's import process, confirming source compatibility, and obtaining community review.

### 4. Enrich heights, roofs, names, and materials

Arnis reads common building tags including `height`, `building:levels`, roof shape/height/material/colour, building material/colour, and `building:part`. The v3.1.0 release specifically improved parts, colours, roofs, and height fallbacks. Write `height` and `roof:height` in metres. ([Arnis v3.1.0 release](https://github.com/louis-e/arnis/releases/tag/v3.1.0))

Use this evidence order for each campus structure:

1. Footprint: Montgomery County outline, corrected against PEMA imagery.
2. Name/function: Hill official campus map and school-provided records.
3. Total height: D24 lidar surface minus nearby bare-earth ground, manually checked.
4. Levels, roof geometry, facade/roof material and colour: school-authorized ground/oblique photos or plans.
5. Building parts such as towers, chapel volumes, wings, covered walks, and entrance projections: manual polygons rather than a single extruded box.

Optional lidar QA with [PDAL](https://pdal.io/en/stable/pipeline.html): download the six current Phase 1 LAZ files returned by The National Map, merge them with `pdal merge`, then crop in WGS84-aware bounds and rasterize ground and surface separately. The crop object below is valid even when the point cloud itself is in its native UTM CRS. ([PDAL crop bounds](https://pdal.io/en/stable/stages/filters.crop.html), [PDAL GDAL writer](https://pdal.io/en/stable/stages/writers.gdal.html))

```powershell
New-Item -ItemType Directory -Force 'E:\hill-map\data\laz' | Out-Null
$lidarTiles = @(
  '18TVK445455', '18TVK445456',
  '18TVK446455', '18TVK446456',
  '18TVK447455', '18TVK447456'
)
foreach ($tile in $lidarTiles) {
  $url = "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/PA_17County_D24/PA_17Co_5_D24/LAZ/USGS_LPC_PA_17County_D24_$tile.laz"
  Invoke-WebRequest -Uri $url -OutFile "E:\hill-map\data\laz\$tile.laz"
}
$lazInputs = (Get-ChildItem -LiteralPath 'E:\hill-map\data\laz' -Filter '*.laz').FullName
& pdal merge @lazInputs 'E:\hill-map\data\hill-lpc.laz'
```

The download is about 1.22 GB before merge; retain the TNM response and per-file hashes.

```json
[
  "hill-lpc.laz",
  {
    "type": "filters.crop",
    "bounds": {
      "minx": -75.63850,
      "miny": 40.24338,
      "maxx": -75.62273,
      "maxy": 40.25369,
      "crs": "EPSG:4326"
    }
  },
  {
    "type": "filters.expression",
    "expression": "Classification == 2"
  },
  {
    "type": "writers.gdal",
    "filename": "hill-dtm.tif",
    "resolution": 1,
    "output_type": "idw",
    "window_size": 2
  }
]
```

Run a second pipeline without `filters.expression` and with `output_type=max` to produce a DSM. Subtract DTM from DSM, then use footprint zonal statistics as a **candidate** height only. Trees, chimneys, spires, roof equipment, and ground slope require visual review. This processing enriches building tags; Arnis still obtains the generated world's bare-earth terrain from the official 3DEP service.

### 5. Generate the final scale-2 world

Once `hill-campus.osm` has correct bounds, no duplicate footprints, and enriched landmark tags:

```powershell
& 'E:\hill-map\tools\arnis-windows.exe' `
  --output-dir 'E:\hill-map\final\hill-campus-scale2' `
  --file 'E:\hill-map\data\hill-campus.osm' `
  --mode geo-terrain `
  --scale 2 `
  --spawn-lat 40.2501706 `
  --spawn-lng -75.6278572 `
  --interior=false `
  --overture=false `
  --no-3d `
  --map-preview `
  --signage full `
  --fillground
```

Disable Overture in the final run because the local file now owns campus building geometry; otherwise satellite-derived fallback footprints can duplicate or overlap the county polygons.

### 6. Perform the architectural craft pass

Do not stop at automatic extrusion. Use WorldEdit/FAWE or a staging client to rebuild the school-defining forms first: the Athey Academic Center/Quad ensemble, Dining Hall, Alumni Chapel, Center for the Arts, Mercer Field House, Sweeney Gymnasium, Tuck Hall, principal dormitory facades, gates, and major athletic/landscape anchors shown on the official map. The official map's 51-place list should become the completion checklist, with an explicit reason for every omitted private or out-of-scope feature.

Recommended manual order:

1. Correct parcel-edge roads, primary walks, curbs, terraces, retaining walls, Dell Pond, fields, track, and tree masses against orthophotos.
2. Replace landmark boxes with stepped `building:part`-equivalent Minecraft forms, roof pitches, towers, chimneys, arcades, and entrances.
3. Establish a restrained Hill material palette from approved references; prioritize silhouette and rhythm over noisy per-pixel colour matching.
4. Add official names and wayfinding, then relocate spawn to an approved public arrival point.
5. Exclude non-public interiors and sensitive operational detail.

The Hill contact page says photography/video and media visits require approval. Obtain school permission before on-site facade capture or commissioned drone photogrammetry, in addition to any aviation/privacy requirements. ([Hill contact and media policy](https://www.thehill.org/about-us/people-of-the-hill/contact-us))

### 7. Upgrade and test on the exact server version

Arnis v3.1.0 writes Java chunks with DataVersion `3955` (Minecraft 1.21.1). This repository's supplied hub is DataVersion `4903`, and its production target is Paper 26.2 build 119 on Java 25. Paper documents that opening an older world on a newer server upgrades it and that downgrading is unsupported. ([Arnis Java writer](https://github.com/louis-e/arnis/blob/v3.1.0/src/world_editor/java.rs#L17-L18), [local world manifest](../../server-assets/worlds.yml), [Paper basic troubleshooting](https://docs.papermc.io/paper/basic-troubleshooting/), [Paper updating](https://docs.papermc.io/paper/updating/), [Paper Java requirements](https://docs.papermc.io/paper/getting-started/))

Handoff procedure:

1. Preserve the untouched Arnis output and hash/archive it.
2. Copy the world into an isolated Paper 26.2 build 119 / Java 25 staging server.
3. Start once, wait for startup and conversion to finish, join and inspect all generated regions, then stop normally.
4. Review logs for chunk, datapack, block-state, and entity conversion errors.
5. Back up the upgraded copy. Never reopen it on an older Minecraft/Paper version.
6. Only then package/import it into the Hill server's normal world-asset workflow.

## Where Voxel Earth fits

The current public Voxel Earth plugin release is `1.1`. Its own README names Paper/Spigot 1.20.4 as the actively tested target, Java 21+ as the runtime, and version-specific 1.21+ builds as roadmap work. It merely says later 1.20/1.21 versions are expected to work with matching FAWE. That is not evidence of compatibility with this project's Paper 26.2 runtime, so do not install it on production. ([Voxel Earth requirements and compatibility](https://github.com/ryanhlewis/VoxelEarth#minecraft-plugin), [Voxel Earth releases](https://github.com/ryanhlewis/VoxelEarth/releases))

The VoxelEarth monorepo was inspected at commit `ed68433d762ca070d2cdbd68a2222142b0a08d30` (2026-02-14, `Add Open-Meteo/OSM Geocoding fallback and update jar`). Its companion CPU voxelizer was inspected at commit `044737c1c53db9d0f705d6aed3b4058f62c1e3d1` (2025-11-10, `Parallel`). Both cloned checkouts stay under ignored `runtime/tools/`.

The relevant VoxelEarth CPU code path already skips primitives whose mesh attributes lack `POSITION`, but its own source comment says "No node transforms"; the browser run for the campus also failed while processing a very large stitched glTF set with `Cannot read properties of null (reading 'attributes')`. The local GLB converter therefore keeps the useful VoxelEarth JSON shape while implementing the robust behavior needed here: transformed node traversal, non-triangle skips, missing-attribute skips, and direct NBT export.

There is one valid high-detail use: if the school commissions/owns a rights-cleared photogrammetry mesh or 3D Tiles dataset, run small landmark GLBs through Voxel Earth's offline CPU voxelizer in an isolated lab, clean the blocks, and paste the result into the Arnis base. Its documented command is:

```text
cd java-cpu-voxelizer
mvn -q -DskipTests clean package
java -jar target/voxelizer-cli-1.0.0-all.jar -f /path/to/tile.glb -s 128 -o out -3dtiles -v
```

The CLI emits block/coordinate JSON used by the plugin; it is not by itself a finished Paper 26.2 world importer. Validate the output in an isolated supported-version server, convert/paste only the cleaned landmark, and then perform the same forward-only 26.2 world upgrade. ([Voxel Earth CPU voxelizer documentation](https://github.com/ryanhlewis/VoxelEarth#3-cpu-voxelization--java-cpu-voxelizer))

The existing [browser-preview note](../voxel-earth-hill-school.md) remains useful for inspecting source coverage and SSE/density behavior, but its Google-backed scenes must remain in the viewer. It is not an export workflow.

## Licensing and provenance checklist

| Input/tool | Operational rule for this map |
| --- | --- |
| Arnis code | Apache-2.0; record exact release `v3.1.0` and its official download URL. ([license](https://github.com/louis-e/arnis/blob/v3.1.0/LICENSE)) |
| Voxel Earth code | MIT, but code licensing does not grant source-tile rights. Record each companion component/version. ([repository license notice](https://github.com/ryanhlewis/VoxelEarth#license)) |
| Google Maps / Photorealistic 3D Tiles | Viewer-only for this project; do not cache, trace, voxelize for export, or redistribute derived geometry/textures. ([terms](https://cloud.google.com/maps-platform/terms), [tile policy](https://developers.google.com/maps/documentation/tile/policies)) |
| OpenStreetMap | Attribute `© OpenStreetMap contributors` with a link to the copyright page. Keep the exact source extract and editing log. ODbL/database share-alike questions should be reviewed before public distribution; do not assume the rendered world erases attribution obligations. ([copyright/ODbL](https://www.openstreetmap.org/copyright)) |
| Montgomery County parcels/buildings | County describes the data as free/open, as-is, and not a legal description. Credit `Montgomery County GIS`; the building item asks for `Montgomery County GIS, NearMap` access credit. Preserve query, date, service/item IDs, and untouched downloads. ([county GIS policy](https://www.montgomerycountypa.gov/departments/data-mapping-services/gis-data), [building item JSON](https://www.arcgis.com/sharing/rest/content/items/b01273ff63df435dbe4cd8c3e95ce3f7?f=json)) |
| USGS 3DEP | USGS-produced data is generally public domain; credit USGS, retain project/tile metadata, and do not imply USGS endorsement of modified output. ([USGS copyright and credits](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits), [3DEP products](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services)) |
| PEMA/PASDA orthophotos | Metadata states no access restrictions and requests acknowledgement. Credit the Pennsylvania Emergency Management Agency/PASDA as specified by the metadata and retain the exact four tile IDs. ([metadata](https://www.pasda.psu.edu/uci/FullMetadataDisplay.aspx?file=PEMA_Cycle2_2021.xml)) |
| Hill campus map, plans, photos, and site capture | School copyright/privacy rules apply. Obtain written permission for derivative/public use and for any on-campus or drone capture; keep private interiors out unless explicitly approved. |

For every candidate build, keep a small provenance manifest outside the world save containing:

- generation date, Arnis/Voxel Earth/PDAL/Osmium versions, exact commands, bbox, scale, and target DataVersion;
- source item/service IDs, query strings, download URLs, acquisition/publication dates, and hashes;
- untouched and edited OSM/GeoJSON inputs plus an edit log;
- required attribution text and school approval references;
- a statement that no Google-derived geometry or textures were exported.

## Acceptance gate

The world is ready for integration only when all of the following are true:

- The Phase 1 extent, orientation, scale, terrain, track, pitches, Dell Pond, main roads, and primary walks align with the rights-cleared reference layers.
- There are no duplicate/overlapping campus buildings from OSM, county data, or Overture.
- All 50 Phase 1 county footprints are either represented or explicitly rejected as stale/out of scope.
- Landmark footprint parts, total heights, roof forms, materials, and official names were manually checked; generic extrusions are not accepted for the principal buildings.
- Each of the official campus map's 51 named locations is present, intentionally omitted, or deferred to the documented full-campus phase.
- Procedural/private interiors and sensitive details are absent.
- Attribution and provenance are packaged, and no Google Photorealistic 3D Tiles derivative is present.
- A backup copy upgrades and loads cleanly on the exact Paper 26.2 build 119 / Java 25 staging runtime, with no world-conversion errors.
