**Hill campus terrain and structure completeness audit — 5 September 2026**

The current native elevation source is suitable for reconstruction. The previous Minecraft terrain introduced a systematic half-metre surface-height error and lost some sharp grade changes through an unnecessary 1 m intermediate raster. The substantial descent behind Hunt is real. Campus completeness also failed before modelling: parcel-ID filtering omitted several buildings, and the world boundary clipped school facilities and athletic fields.

This research supplies numerical controls and a larger, explicitly qualified building worklist. It does not certify that the current world matches street view or that all facades have been inspected. Source presence, school use, legal ownership, geometry accuracy and modelling completion are separate checks.

**Elevation source and datum**

Use the existing `runtime/campus-reconstruction/roofer-chapel-trial/inputs/hill-campus-dem-0p5m.tif` directly. Its 13,260,000 pixels exactly match the nine downloaded native D24 DEM tiles: maximum absolute difference is zero. The raster is 3400 columns × 3900 rows, has 0.5 m cells, bounds E445650–447350/N4454925–4456875, and float nodata −999999. SHA-256 is `cd9f190360b727db7d612682d759b155b88ef430d1a487fb7041aa19b31d858e`. The numerical comparison is in [terrain-source-crop-parity.json](../../runtime/research/campus-full-detail-20260905/terrain-source-crop-parity.json).

USGS accepted the PA_17Co_5_D24 DEM, point cloud and breaklines. The project is QL1, horizontal EPSG:6347, vertical EPSG:5703, with GEOID18. Preserve NAVD88 metres; do not treat these as ellipsoid heights or feet. [USGS validation report](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/PA_17County_D24/PA_17Co_5_D24/reports/USGS_PA_17County_5_D24_Summary_Report.pdf), [vendor DEM metadata](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/PA_17County_D24/PA_17Co_5_D24/reports/vendor_provided_xml/PA_17County_2024_WU301078_DEM.xml).

The local LAS GPS times span 17 December 2024–28 March 2025; these campus returns are much newer than the old 2021 orthophoto. Product publication is 18 April 2026. The project acquisition window is wider than the local tile dates. The latest National Map LPC query returned this project and older 2006–08 coverage. [USGS product metadata](https://thor-f5.er.usgs.gov/ngtoc/metadata/waf/elevation/lidar_point_cloud/laz/PA_17Co_5_D24/USGS_LPC_PA_17County_D24_18TVK445455.xml), [National Map product query](https://tnmaccess.nationalmap.gov/api/v1/products?datasets=Lidar%20Point%20Cloud%20%28LPC%29&bbox=-75.638,40.243,-75.628,40.251&max=100).

Four campus LAS tiles yielded 14,144,476 non-withheld class-2 ground points. They are cached in [terrain-classified-ground-current-campus.npz](../../runtime/research/campus-full-detail-20260905/terrain-classified-ground-current-campus.npz), key `points_utm6347_navd88_m`, columns E/N/H. Same-source ground returns check raster interpolation and classification support, not independent absolute accuracy. A valid 2015 Delaware Valley 1 m DEM provides the independent historical comparison below. The cached 2018 tile and a downloaded 2014 crop are nodata here and must not be counted as independent evidence. [2015 USGS DEM](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/DE_DelawareValley_HD_2015/TIFF/USGS_one_meter_x44y446_DE_DelawareValley_HD_2015.tif).

**Measured error in the previous pipeline**

At two blocks per metre, target physical top-surface coordinate is `Y = 2 × (H_NAVD88 − 25)`. A full block at integer Y occupies Y through Y+1. The old top-block index `round(2 × (H−25))` therefore put its visible/collision top one block too high. Paving and landscape layers also used extra top offsets. The production owner is correcting those conventions; all floor, path, soil and water placement must use the same physical-surface interpretation.

For 872,617 open-ground cells within the cached parcel union and outside 1.5 m building buffers:

| Baseline comparison against the native 0.5 m raster | Result |
| --- | ---: |
| 1 m preparation, interpolated back to 0.5 m: RMSE | 0.0183 m |
| Absolute resampling error, 95th / 99th percentile | 0.0315 / 0.0671 m |
| Largest local resampling error | 1.0391 m |
| Old full-block physical top: mean signed error | +0.4969 m |
| Old full-block physical top: 95th-percentile absolute error | 0.7276 m |

The large resampling errors are localized near abrupt terrain; they do not justify changing the entire campus datum. Sample the native raster once at the final 0.5 m cell centres, preserve hardscape breaks as explicit geometry, and avoid smoothing measured retaining-wall transitions into long ramps. Calculations, regional summaries and the worst cells are in [terrain-control-checkpoints.json](../../runtime/research/campus-full-detail-20260905/terrain-control-checkpoints.json); the reproducible read-only baseline is [terrain-audit.py](../../runtime/research/campus-full-detail-20260905/terrain-audit.py).

| Physical project X,Z (metres) | Native D24 H | Nearby class-2 plane H | Independent 2015 H |
| --- | ---: | ---: | ---: |
| Quad west: 16,10 | 66.028 | 66.022 | 65.963 |
| Quad centre: 66,10 | 66.247 | 66.250 | 66.203 |
| Quad east: 119,10 | 67.032 | 67.025 | 66.848 |
| Hunt south lawn: 77,−20 | 66.092 | 66.093 | 66.049 |
| Hunt north low court: 77,−53 | 58.526 | 58.524 | 58.461 |
| Ryan west garden: 105,26 | 67.511 | 67.514 | 67.767 |
| Ryan arcade vicinity: 118,26 | 69.049 | 69.046 | 69.057 |

The Hunt checkpoints demonstrate a real 7.57 m descent. Under roof overhangs, a bare-earth DEM may interpolate across missing ground observations; these values are approach controls, not proof of a door threshold or finished floor.

![Native elevation, historical controls and old rendering bias](../../runtime/research/campus-full-detail-20260905/terrain-elevation-corrections.png)

The research-only direct-grid NPZ has `ground_elevation_navd88_m` float32 `[1536,1536]`, `material_id` with the same shape, block origins `x_min=-448`, `z_min=-1216`, and `metadata_json`. Physical coordinates are X=−224+(column+0.5)/2, Z=−608+(row+0.5)/2. Thus its physical bounds remain the old crop [−224,−608,544,160]. Material labels repeat the old 1 m semantic raster and are not new elevation evidence. The production terrain preparation should explicitly carry `resolution_m=0.5` and physical bounds; this research file must not be interpreted by a legacy 1 m-origin loader. [Direct-grid artifact](../../runtime/research/campus-full-detail-20260905/terrain-direct-native-0p5m.npz).

**Building approaches and earthworks**

[All-component perimeter controls](../../runtime/research/campus-full-detail-20260905/terrain-all-components-perimeter-controls.json) contain 1,663 approach samples for all 44 existing build components: 1,318 have a class-2 return within 0.75 m and 1,182 support a local plane fit. Unsupported samples are marked. The [priority controls](../../runtime/research/campus-full-detail-20260905/terrain-priority-building-approach-controls.json) use the root agent's exact building-local UV frames and include 1 m and 3 m setbacks.

| Building approach, sampled 1 m outside wall | Native NAVD88 range |
| --- | ---: |
| Quadrivium north long facade | 67.61–68.43 m |
| Quadrivium west curved bays | 63.56–67.82 m |
| Quadrivium east side | 62.74–67.49 m |
| Quadrivium south long facade | 62.74–66.52 m |
| Warner north / south | 55.53–55.71 / 57.75–58.00 m |
| Music House north / south | 61.76–62.17 / 64.54–64.69 m |
| Wendell north / south | 64.88–65.60 / 67.81–68.28 m |

Their source minimum bases, respectively 62.71/55.38/61.67/64.65 m, cannot be assigned to every entrance. Floors must follow identified entrances, stairs and building levels while exterior grade remains measured.

The Dell Pond outline has area about 4,640 m² (1.15 acres). The native DEM varies from 54.871 to 56.086 m inside it, which is unsuitable as a sloping water surface. The vendor only required lake/pond hydroflattening above 2 acres; the campus LAS crop has no class-9 or class-20 points. [Vendor processing report, printed pp. 11–12](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/PA_17County_D24/PA_17Co_5_D24/reports/WU301078_PA_17County_2024_Lidar_Report.pdf).

Use a single nominal **55.000 m NAVD88** water plane: 1,708 class-2 returns at least 8 m inside the mapped shoreline have median 55.000 m and IQR 54.99–55.02 m. The dominant 25 mm height bin is consistent at 2, 5 and 8 m shoreline insets. This is strong modal-plane evidence, not a surveyed water gauge; classify shoreline and any bed depth as separate uncertainties. [Exact shoreline and water controls](../../runtime/research/campus-full-detail-20260905/terrain-dell-pond-controls.json), [shore-point cache](../../runtime/research/campus-full-detail-20260905/terrain-dell-pond-shore-ground-points.npz).

[Sports surface controls](../../runtime/research/campus-full-detail-20260905/terrain-sports-surface-controls.json) cover 18 mapped fields/courts with native height percentiles, fitted grade planes and residuals. Preserve their measured drainage slopes and crowns. Dell Field's fitted grades are approximately −0.0052 m/m along X and −0.0222 m/m along Z; the track infield is nearly flat at about 75.59 m. Those polygons originate in older OSM and do not prove current sport names, markings or exact 2026 boundaries.

A published Kipp phasing sheet provides building dimensions and level annotations, but its datum is unstated and the referenced full grading sheets were not located. The 2022 athletic review describes site changes and a stormwater basin; it is not an as-built contour survey. No full campus as-built grading plan was obtained, so numerical steps or retaining-wall tops must not be invented from those documents. [Kipp plan](https://www.pottstown.org/AgendaCenter/ViewFile/Item/14290?fileID=6442), [2022 borough review packet](https://www.pottstown.org/AgendaCenter/ViewFile/Agenda/_04112022-766?packet=true).

**Campus-wide structure worklist**

The [final structure ledger](../../runtime/research/campus-full-detail-20260905/terrain-final-campus-structure-ledger.json) separates map use, ownership evidence, geometry source and current image-verification status. Its 114 county footprint records comprise the original 108 parents plus six spatial additions. The current school identity file has 44 named records joined to 42 unique county parents; two more current structures, Kipp Pavilion and the Madden press box, have separately interpreted geometry. [Current school map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf).

| Worklist category | Footprint records |
| --- | ---: |
| Current named campus county parents | 42 |
| Additional campus uses documented on the 2021 map | 24 |
| Unlabelled probable campus ancillary structures | 25 |
| Adjacent school-owned properties with unresolved campus use | 13 |
| **Campus county-footprint worklist** | **104** |
| Current named structures absent county rings | 2 |
| **Campus worklist including these two structures** | **106** |
| Separately owned, school-map-associated Hobart's Run house | 1 |
| Brookside golf context, excluded from campus count | 8 |
| Outlying school-owned property, excluded from campus count | 1 |

The 106 figure is a worklist for review, not a verified number of completed or currently occupied campus buildings. Additional 2021 uses include service buildings and faculty housing absent from the shorter current visitor map. The 24 older mapped footprint records correspond to 24 distinct map labels after accounting for joined duplexes and multi-building groups. Current use still needs confirmation where only the older map documents it. [Official 2021 facility map](https://resources.finalsite.net/images/v1633097238/thehillorg/ewtimjvxagjkgblsqf5q/fy22campusmapgraphic.pdf).

The general spatial query covered 948 county outlines. Five records use obsolete parcel strings: `16113 014`, `16113 015`, two `16112 015` rings, and `16121 004`. Filtering by the current numeric Hill assessment IDs omitted them. Current parcel geometry still contains the obsolete IDs with blank tax pins, so legal ownership cannot be filled by guessing. Map placement and the old orthophoto identify the main maintenance pair and 645 King house; the rear shed and small roof north of Grounds Maintenance remain probable ancillary uses. [County building outlines](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6), [current parcel service](https://gis.montcopa.org/arcgis/rest/services/Parcels/Montgomery_County_Parcels/FeatureServer/10).

| Added physical roof/ring | Centre X,Z m | Ground-ring median | Main roof evidence |
| --- | --- | ---: | --- |
| Maintenance north | −108.213,−132.528 | 52.64 m | two gable planes; upper roof about 58.09 m |
| Maintenance south | −104.832,−110.811 | 52.59 m | four planes for L-shaped roof; upper ridge about 60.99 m |
| 645 King house | −213.138,−19.989 | 52.80 m | hipped main roof about 62.75 m plus lower porch |
| 645 King rear shed | −212.777,−46.153 | 52.83 m | fitted roof 55.27–55.81 m; canopy pollutes raw percentiles |
| Small north service-area roof | 298.583,−428.825 | 72.67 m | mostly shallow roof, about 75.4 m; function unverified |
| 59 Edgewood associated house | 510.834,39.281 | 61.64 m | measured complex roof; separate legal owner |

All six exact XZ rings, roof support hulls, plane equations, candidate height percentiles and 2 m ground-ring controls are in [terrain-new-footprint-roof-controls.json](../../runtime/research/campus-full-detail-20260905/terrain-new-footprint-roof-controls.json). The [point cache](../../runtime/research/campus-full-detail-20260905/terrain-new-footprint-lidar-points.npz) columns are X,Z,NAVD88,LAS class,return number. There is no LAS building class in this delivery: roof candidates are non-withheld class-1 first returns, inside a 0.3 m eroded ring, above bare earth by at least 1.8 m. Robust plane fits reduce vegetation contamination; they still require roof-image review.

![Fresh county rings absent from the old selected data, over the county orthophoto](../../runtime/research/campus-full-detail-20260905/terrain-new-legacy-footprint-ortho-evidence.png)

County ownership queries also establish why spatial intersection alone is unsafe: one nearby 6 m² shed overlaps the cached school parcel union by 71.9%, but its assessed parcel is privately owned. The nearest map-number centroid can likewise select a garage or the wrong half of a row of houses. Matching the exact 59 Edgewood address resolves the associated Hobart's Run building; neighboring twins are excluded. Fresh query responses and exclusions are preserved in the `terrain-spatial-*` artifacts. [County assessment source](https://gis.montcopa.org/arcgis/rest/services/Parcels/GIS_BOA_LAND/FeatureServer/0).

Eight distant structures lie in Brookside golf context, despite the Hill owner record. The official club identifies its Pottstown facility at 850 North Adams Street; it is separate from the campus school-building worklist. An additional 807 Sheridan structure remains an outlying school-owned property, not an inferred campus facility. [Brookside's official site](https://brooksidepottstown.clubhouseonline-e3.com/Golf).

Use provisional physical extent **X −288 to 704 m, Z −800 to 208 m** for the central campus, adjacent faculty/support buildings and mapped athletics. It includes Security at X≈−266, the southeast storage building, the track to X≈680 and north fields to Z≈−773. The previous [−224,−608,544,160] crop misses these. The complete school-owned parcel union extends far into golf property and is not a defensible campus crop by itself. Check the proposed perimeter against the [2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) before declaring coverage complete.

**Required reconstruction acceptance checks**

Keep native-grade measurements and uncertainty attached to each building and landscape feature. Identify doors and finished levels from current images, then construct each facade and its retaining walls, stairs, ramps and paths against those levels. Preserve footprint gaps. Do not flatten the campus to the minimum building elevations or fit all doors to one minimum base.

Audit the finished blocks at recorded physical checkpoints, including top surfaces rather than block indices. Review matching ground-level and aerial views for every ledger entry; record unresolved identity, missing roofs, facade detail and outdated outlines separately. The final full-campus view must include the expanded athletic area, auxiliary structures and measured grade transitions. This report provides the source controls for that process; it does not replace the in-game comparison.
