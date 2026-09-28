# Hunt Upper School: measured massing, roof corrections and facade references

Researched 2026-09-05 for the combined campus reconstruction. **Hunt is the red-roofed U-shaped residence building on the north side of the Quad.** Its two tall end wings, lower connecting roof, round stone arcade, brick walls and green roof ornament are the main likeness controls. The outer north facade and retaining-wall drop differ substantially from the Quad facade. All dimensions below are physical metres; apply the shared **2 blocks per metre** scale only at output.

This is a reference and source-analysis report, not approval of an in-game replica. No builder, world output, campus identity file, Chrome or Blender session was changed.

## Name, location and exact source join

The official map calls the building **Hunt Upper School Dormitory, number 29**, and lists the Menkowitz Wellness Center and Counseling Center there. “Hunt Hall” in this reconstruction refers to that building. It faces Athey across the Quad; Ryan is at the Quad's east end and the Chapel at its west end. The school describes Upper School East and Upper School West as separate residential divisions/buildings, but the available county/CityJSON exterior outline is one joined U-shaped aggregate. No reliable internal East/West boundary was obtained. [Current school map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), [school campus page](https://www.thehill.org/about/our-campus), [school dormitory description](https://www.thehill.org/student-life/boarding-student-life/dormitories).

| Field | Verified value |
| --- | --- |
| Existing campus source index | **77**, footprint label **78** |
| Roofer parent | **`160015116006-d4f3b48752`** |
| LoD2.2 child | `160015116006-d4f3b48752-0` |
| County `STRUCTUREID` / `PARID` | `160015116006` / `160015116006` |
| Current county `OBJECTID` | **`412522`**, spatial query on 2026-09-05 |
| County `IMPRNAME`, `YRBLT`, `DESCRIPTION` | Null |
| County-outline centroid, longitude/latitude | `-75.63423114383279, 40.245462546259844` |
| County-outline centroid, EPSG:6347 | `446056.3826, 4455194.6339` m |
| County outline area in EPSG:6347 | 1,465.2049 m² |

The bare county `STRUCTUREID` repeats across many campus buildings. Use the complete Roofer parent. **Do not substitute** `1600151160061C-551ba4628e`, whose stale county name contains `UPPER SCHOOL BLDG #24`: that footprint is far east of the Quad. Wendell, Foster, Rolfe, Davy and the Dutch Village houses also have separate verified identities. [Existing identity inventory](../../server-assets/hill-campus-building-identities.json), [current county query response](../../runtime/research/hunt-hall-20260905/hunt-county-current-source.geojson), [county source layer](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6).

The school's older dormitory page says Upper School was renovated in 2009, including fourth-floor accommodation. That old URL remains indexed but may fail after the website redesign; do not use its occupancy description as a current room survey. Wohlsen identifies Hord Coplan Macht as architect for the dormitory renovations and lists stair towers and fourth-floor fitout among the work. HCM independently lists its Hill dormitory project. [School description](https://www.thehill.org/student-life/boarding-student-life/dormitories), [contractor project](https://wohlsenconstruction.com/project/the-hill-school-upper-school-dormitory-renovation/), [architect's project list](https://www.hcm2.com/wp-content/uploads/Hord-Coplan-Macht-Education-Independent-School-Experience.pdf).

## Measured local frame and plan

The local reference frame is derived from the minimum rotated rectangle of the reconstructed ground outline:

```text
O_project_XZ = (42.599311524, -47.518360512) metres
U_unit_XZ    = ( 0.996417922,  0.084565506)  along the building toward east
V_unit_XZ    = (-0.084565506,  0.996417922)  toward south / the Quad
project_XZ  = O + U * U_unit_XZ + V * V_unit_XZ
```

O is a mathematical northwest envelope corner, not a surveyed doorway or wall corner. The U bearing is **94.851° east of north**, about 4.85° south of east. This differs from Ryan's orientation; do not reuse Ryan's axes. The source [CityJSON](../../runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json) has SHA-256 `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`, horizontal CRS EPSG:6347. Project X is east and Z south. Complete ground rings, face polygons and planes are saved in [hunt-roof-measurements.json](../../runtime/research/hunt-hall-20260905/hunt-roof-measurements.json).

| Measurement | Value |
| --- | --- |
| Reconstructed ground envelope | **75.3533 m along U × 26.3187 m along V** |
| Project X/Z bounds | X 41.7026–117.1336; Z −47.3721 to −15.2603 m |
| Reconstructed ground area | **1,392.5297 m²**, one GroundSurface |
| County area in the same local project frame | 1,466.2727 m²; comparison must use the same projection |
| County-only area outside reconstructed ground | 73.7481 m², chiefly north-side strips/corners; reconstructed-only area about 0.0051 m² |
| West end wing, approximate source U span | U approximately 1.0–14.0; southern end near V 26.0 |
| East end wing, approximate source U span | U approximately 61.4–75.3; southern end near V 26.3 |
| Central Quad-facing ground edge | U approximately 13.86–61.40; V varies approximately 15.52–18.02 |

The last three rows summarize an irregular polygon, not replacement rectangles. The two wing ends project south of the connecting bar; its open court must remain open. The county/roof difference is material and should be reviewed before accepting a fully clipped shell. [Outline comparison JSON](../../runtime/research/hunt-hall-20260905/hunt-local-terrain-and-outline.json), [comparison plot](../../runtime/research/hunt-hall-20260905/hunt-terrain-and-outline.png).

## Roof measurements and confidence

Heights here are **NAVD88 metres**, without Minecraft offset. These are measurements of the reconstructed model, not an architectural survey:

| Attribute | Value / implication |
| --- | --- |
| Source ground attribute | 62.4100 m; not the Quad finished-floor level |
| Source ridge attribute | 86.788239 m |
| Highest reconstructed geometry vertex | 86.7939 m |
| LoD2.2 RMSE | **1.550174 m**, substantially less reliable than Ryan's 0.58 m fit |
| Point-cloud selection status | **`_HIGHEST_YET_INSUFFICIENT_COVERAGE`** |
| No-data fraction | 0.077907, about 7.8% |
| Segmentation / semantic face counts | `rf_roof_planes=70`; loader exposes **50 RoofSurfaces**, zero rejected faces; these counts describe different stages |
| Main central upper face 49 | 215.4754 m² projected; 81.7629–82.7802 m; fitted slope 10.007° |
| Central Quad-facing slope, face 45 | 152.6890 m²; 78.5802–82.1153 m; 40.054° |
| West wing large faces 23 / 40 | 102.3401 / 115.2169 m²; slopes 50.914° / 50.723°; reach 86.7878 m |
| East wing large faces 18 / 47 | 108.0143 / 108.1003 m²; slopes 50.824° / 50.767°; reach 86.7939 m |

The current overhead video confirms red, relatively steep side slopes and higher end-wing roofs, with a **dark elongated low-pitch strip on the central connecting roof**. Broad box dormers occur on the north slope; the south roof uses many smaller units and its ornamental central feature. Avoid replacing this with one gable roof or applying one dormer pattern to every slope. Roof finish appears tile-like in the contractor close-up, but its exact installed product is not documented. [12 s aerial](../../runtime/research/hunt-hall-20260905/drone-012s.png), [142 s overhead](../../runtime/research/hunt-hall-20260905/drone-142s.png), [contractor exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/k-12-schools-construction-the-hill-school-upper-school-dormitory-renovation-1.jpg).

![Hunt roof-face index](../../runtime/research/hunt-hall-20260905/hunt-measured-roof-plan.png)

### Correction classifications: preserve raw geometry separately

The following distinguishes likely reconstruction failures from real low architectural components. Face IDs refer to `hunt-roof-measurements.json`.

| Faces / region | Evidence assessment | Recommended treatment |
| --- | --- | --- |
| **43**, northwest north-edge strip, centre U 5.46/V 1.02, height 62.41–64.91 m | The north end wing in photographs rises through several stories to its red gable. No low roof of this shape is visible there. Its fitted slope also resembles the tall roof despite its ground-level altitude. | **Likely reconstruction failure**, not a measured stair-tower roof. Repair from neighboring wing form and county outline; retain the raw source unchanged. |
| **16**, northeast north-edge strip, centre U 66.35/V 1.17, 63.09–65.92 m | Same conflict at the opposite end. Current aerial shows the tall end mass continuing to the north edge. | **Likely reconstruction failure**; not evidence for a roof below the upper stories. |
| **33**, broad north-middle/east strip, centre U 47.89/V 2.74, area 45.90 m², 64.19–68.77 m | Too broad and low to match the continuous tall north wall and its dormer roof. The primary engineering photos show no corresponding low annex here. | **Likely reconstruction failure**; restore continuity of the main roof/wall using an explicitly interpreted correction. |
| **26**, north strip near U 58.3/V 2.0, 62.72–62.80 m | No corresponding low roof verified. A small door cover could exist at a low level, but this face does not establish one. | Keep as uncertain ancillary/source artifact; do not let it truncate the main building. |
| **7, 8, 9, 13**, narrow outer east areas, roughly U 73.7–75.1/V 14.6–22.0, below 70 m | Could include entry covers, ground-adjacent surfaces or fitting failures. The available photos do not identify these polygons individually. | **Unresolved**, rather than a confirmed tower roof. Preserve source evidence and add only photo-supported ancillary covers. |
| **44 / 35**, central **south/Quad** strip, centres U 24.88/V 17.36 and U 42.23/V 17.16, 69.87–70.22 m | Current overhead shows a real pale flat roof/terrace over the arcade. Its position agrees with these faces. | **Preserve the low arcade roof near 70.1 m.** A blanket rule lifting every roof below 75 m would destroy this feature. |

The plain brick stair-tower appendages in the engineering photos extend to the upper stories; their real roofs are far above the 62–69 m strips. At least two end appendages and the central projecting north bay are visible, but exact appendage polygons/heights were **not uniquely matched** to source semantic faces. Do not label any of the low north patches a confirmed stair-tower roof merely because a stair tower exists nearby. Flat tower-roof placement should be interpreted separately from the known photograph, not generated by flattening the whole wing. [North building detail](../../runtime/research/hunt-hall-20260905/isett-north-building.jpeg), [north complete context](../../runtime/research/hunt-hall-20260905/isett-north-retaining-wall.jpg), [current north aerial detail](../../runtime/research/hunt-hall-20260905/drone-012s-north-middle-detail.png).

## Quad-side bay and dormer rhythm

**Strongest current counts:** the west pavilion facing the Quad has **three columns × four rows of regular rectangular windows**, plus a separate attic window group under its gable. The connecting south roof has **eight clearly countable single dormers west of the ornate central unit**. Its east side appears to repeat eight, but several units are partly hidden by foliage/shadow. The north slope instead shows **six broad box dormers, three on each side of its central projecting bay**. [136 s west pavilion crop](../../runtime/research/hunt-hall-20260905/drone-136s-west-quad-end-detail.png), [142 s south roof crop](../../runtime/research/hunt-hall-20260905/drone-142s-quad-roof-rhythm-detail.png), [12 s north crop](../../runtime/research/hunt-hall-20260905/drone-012s-north-middle-detail.png).

| Component | Recommended first reconstruction | Confidence and limit |
| --- | --- | --- |
| Main south attic/dormer row | **8 single units + 1 central double-window ornamental unit + 8 single units**: 17 dormer units, 18 principal openings | West eight and central pair are clear. East eight is an informed completion, not a completely unobscured modern count. |
| Main long south arcade | **Provisional 9 front-facing arches: 4 + central + 4** | Inferred from two windows per arcade bay, the roof/window rhythm, contractor crop and matching historic frontage. Full modern ground arcade is tree-obscured. Keep count adjustable and do not call it surveyed. |
| Brick windows above arcade | Two regular rows; generally two openings per arch, including the paired central projecting bay | Photo-supported rhythm; a provisional 18-opening row accompanies the nine-arch reconstruction. |
| Arcade returns into end wings | Separate from the nine proposed front-facing openings | Full return counts remain unverified; do not automatically continue the straight rhythm around corners. |
| West pavilion facing Quad | **3 columns × 4 rows**, plus attic group | Clear in the current 136 s view. Lowest rectangular row is in a stone-faced band. |
| East pavilion facing Quad | Similar overall mass and repeated windows are visible obliquely | Complete pane/bay count is not independently confirmed here; distinguish any repeated interpretation. |
| North roof | **6 broad box dormers**, grouped 3 + central bay + 3 | Clear aerial evidence; not the south's single-window dormer sequence. |

For a first adjustable layout, the central front run between wing returns is approximately **47.5 m**. Nine arches imply an average pitch around **5.3 m**, and regular window/dormer spacing around **2.6 m**. These are **layout estimates**, not measured pier or opening widths. Start clear round arches around 4.0–4.5 m wide, leaving substantial stone piers. The central bay projects and has special framing; its paired windows should not be represented as one broad modern sheet of glass.

The much smaller hooded openings higher on the south roof slope are separate from the principal dormers. Keep them out of the 17-unit dormer count; their full modern count and function were not established. The contractor close-up also shows patterned upper glazing in the central paired dormer and smoother brown surrounds around ordinary windows. [Contractor exterior](../../runtime/research/hunt-hall-20260905/wohlsen-quad-front.jpg).

The historic supporting image is a Tichnor/Boston Public Library postcard, catalogued circa 1930–1945, accession 06_10_018162. Its facade matches the present ornament and arcade, but colors are printed and the image predates modern renovations. It supports a cautious rhythm comparison, not present-day material color or an exact modern hidden-opening count. [BPL catalogue reference](https://ark.digitalcommonwealth.org/ark:/50959/vh53wx40v), [reproduction and catalogue metadata](https://commons.wikimedia.org/wiki/File:Upper_school,_Hill_School,_Pottstown,_Pa_(64362).jpg), [local postcard](../../runtime/research/hunt-hall-20260905/bpl-upper-school-postcard-1930-1945.jpg).

The separately cached `hillstory-upper-school-historic.jpeg` shows a substantially different historic building form and is **excluded from the current elevation evidence**. Its presence in the research directory is not an endorsement for modeling today's Hunt.

## Height levels for the first facade pass

Keep measured roof heights distinct from these photo-based opening estimates. Window estimates allow approximately **0.7–1.0 m** uncertainty pending native-view comparison; they should not be treated as architectural sill schedules.

| Level / component | Initial NAVD88 height, metres | Evidence status |
| --- | --- | --- |
| Quad paving / main arcade entry | Approximately **66.0–66.2** | Native DEM outside facade; individual thresholds not surveyed |
| Arcade crown / front parapet | Crown approximately 69.5–69.9; roof around **70.1** | Crown estimated; source low roof faces measured at 69.87–70.22 |
| First brick window row above arcade | Approximately **70.6–73.0** | Photo estimate |
| Second brick window row | Approximately **74.5–76.9** | Photo estimate |
| Main cornice / eave zone | Approximately **77.8–78.5** | Photo estimate compared with face 45 minimum 78.58; fitting error is significant |
| South dormer glazing | Approximately **78.8–80.8** | Photo estimate |
| Main connecting low-pitch roof | **81.76–82.78** | Measured face 49 extrema |
| Central green ornamental crest/finial | Trial top approximately **86–87** | Image-proportion estimate, not an independently surveyed feature |
| End-wing ridges | **86.79** | Measured geometry |

The central ornament has an oval opening, curved green trim, small side pinnacles and a tall finial. A round medallion is set into the masonry bay below it. These separate shapes are better likeness controls than random facade texturing. Preserve the roof's low central strip and high wing ridges so the ornament reads correctly in the campus silhouette. [Wohlsen close exterior](../../runtime/research/hunt-hall-20260905/wohlsen-quad-front.jpg).

## Independent north and end references

The north facade shows a stone-faced lower story, several brick stories, aligned rectangular sash-like windows, green cornice trim, projecting brick stairs/towers, and broad upper dormers. It does **not** carry the Quad's continuous open arcade. The end gables have dark framing/trim and grouped attic windows. Several window air-conditioning units appear in the engineering photos; their presence and exact locations need a current check before modeling.

The project engineer describes a roughly **350 ft / 106.7 m retaining-wall project**, with the five-story dormitory approximately **15 ft / 4.57 m behind the wall**. Those figures describe the engineering project and setback, not the building's facade length. It documents a new supporting concrete wall and replacement steps; the photographs show two masonry-faced levels with planting, railings and long stair flights. [Barry Isett project record](https://www.barryisett.com/project/the-hill-school/).

| Primary image | Visible evidence |
| --- | --- |
| [Finished wall and north building](https://www.barryisett.com/wp-content/uploads/2020/12/Finished_Wall-1024x768.jpg), [local](../../runtime/research/hunt-hall-20260905/isett-north-retaining-wall.jpg) | Long north frontage, end gable, plain brick stair appendage, upper and lower roads, masonry retaining wall and stair landings |
| [Opposite driveway direction](https://www.barryisett.com/wp-content/uploads/2021/10/HillSchool-5.jpeg), [local](../../runtime/research/hunt-hall-20260905/isett-north-driveway.jpeg) | Continuous tall wall; stone lower story, repeated brick windows and retaining-wall planting strip |
| [Building and tower detail](https://www.barryisett.com/wp-content/uploads/2021/10/HillSchool-6-681x1024.jpeg), [local](../../runtime/research/hunt-hall-20260905/isett-north-building.jpeg) | Flat-topped brick appendage, vertically spaced stair windows, adjacent tall gable and stair geometry |
| [Stair detail](https://www.barryisett.com/wp-content/uploads/2021/10/HillSchool-4.jpeg), [local](../../runtime/research/hunt-hall-20260905/isett-north-stairs.jpeg) | Straight flights, masonry cheeks, contrasting caps and rails; photographed during work |
| [Other stair view](https://www.barryisett.com/wp-content/uploads/2021/10/HillSchool-7-681x1024.jpeg), [local](../../runtime/research/hunt-hall-20260905/isett-north-stairway.jpeg) | Additional side detail; no exact capture date verified |

At local U 35, the cached native 0.5 m bare-earth DEM samples approximately **58.54 m at V −8** on the lower north road and **66.15 m at V 20** by the Quad. This approximately 7.6 m difference is essential to the campus section. Samples under the building are interpolated bare earth and must not flatten its occupied floors into a ramp. The source ground attribute of 62.41 m is a separate statistic. The retaining-wall faces and stepped access need their own geometry. [Terrain probes and provenance](../../runtime/research/hunt-hall-20260905/hunt-local-terrain-and-outline.json), [terrain comparison](../../runtime/research/hunt-hall-20260905/hunt-terrain-and-outline.png).

## Materials, source limits and audit order

Use semantic material zones: red/brown brick for upper walls; rough warm gray/brown masonry for the arcade and lower bands; smoother darker stone for window frames and special trim; ordinary red roof blocks/stairs/slabs for the visible tile-like slopes; a dark material for the central low-pitch strip; green/patinated-looking conventional building material for cornices and ornament; glass and restrained frames for windows. The exact roof product, historic stone type and metal specification are unverified. The user's ban on exterior ores and sculk applies throughout; these source colors do not justify using such blocks. [Contractor front](https://wohlsenconstruction.com/wp-content/uploads/2016/03/k-12-schools-construction-the-hill-school-upper-school-dormitory-renovation-1.jpg), [current school drone](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4).

The school Archives inventory lists four partial Upper School blueprint sheets dated July, September and October 1909, attributed to Hewitt and Paist. The actual sheets were not obtained. The school inventory is currently available through indexed primary text while its old direct URL may return 404. Do not infer complete modern elevations from that inventory. [School Archives](https://www.thehill.org/about-us/hill-traditions/archives).

Audit the combined scene from the Quad first: U-shaped outline, low centre/high wings, roof colors, central ornament, arcade depth, end-pavilion grid and tree placement. Then inspect the north road view for tower masses and the retaining-wall drop. Finally inspect an overhead view for dormer counts, central roof strip and explicit source corrections. The full modern front arcade, obscured east dormers, arcade returns, exact sill heights and individually matched tower-roof polygons remain the main uncertainties. Sources are fully listed with asset hashes in [source-manifest.json](../../runtime/research/hunt-hall-20260905/source-manifest.json).
