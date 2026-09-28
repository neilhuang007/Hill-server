# Quad landscape and complete official-map building inventory

Researched **2026-09-05**. The practical proposal preserves the measured buildings, a large open lawn, pale perimeter circulation, the central red cross-path, Ryan's raised west garden and stairs, and the major tree masses. **Landscaping coordinates are interpreted estimates; the underlying building positions and DEM are measured source geometry.** This report does not certify an in-game likeness or complete facades.

The authorized shared identity file was expanded from **29 name records / 27 county parents** to **44 records / 42 parents**, identifying **36 current official building groups**. Kipp Pavilion and the Madden Stadium press box have separate current-structure proposals without fabricated county IDs. Together the county matches and the interpreted Kipp footprint cover the **37 enclosed-building/pavilion groups named on the current map**; Madden contributes an additional enclosed structure within a stadium entry. This count excludes fields, courts, parking, pond, gardens, country-club context, unnamed maintenance/outbuildings and small landscape shelters. It is a naming/geometry inventory, not a statement that every campus structure has been built. [Official current campus map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), [merged identity file](../../server-assets/hill-campus-building-identities.json), [complete coordinate inventory](../../runtime/research/quad-landscape-20260905/full-named-campus-building-inventory.json).

## Deliverables and fixed frame

| File | Purpose |
|---|---|
| [quad-landscape-measurements.json](../../runtime/research/quad-landscape-20260905/quad-landscape-measurements.json) | Initial usable proposal: 11 path centerlines and polygons, main lawn polygon, 5 beds, 8 trees, steps and DEM profiles. Preserved after the parent began implementing it. |
| [quad-threshold-join-correction.json](../../runtime/research/quad-landscape-20260905/quad-threshold-join-correction.json) | Explicit later Athey door/terrace correction; supplements the initial proposal. |
| [quad-landscape-proposal.png](../../runtime/research/quad-landscape-20260905/quad-landscape-proposal.png) | Plan review image with source buildings fixed. |
| [current-pavilion-proposals.json](../../runtime/research/quad-landscape-20260905/current-pavilion-proposals.json) | Separate Kipp design-plan registration and Madden press-box photo interpretation. |
| [full-named-campus-building-inventory.json](../../runtime/research/quad-landscape-20260905/full-named-campus-building-inventory.json) | All 42 unique accepted county parents, names, source indices, polygons, bounds, source roof status and priority. |
| [campus-completeness-checklist.json](../../runtime/research/quad-landscape-20260905/campus-completeness-checklist.json) | Classifies all 51 official map labels: 37 named building/pavilion groups, Madden's press box, and 13 nonbuilding/external context labels. Keeps world/facade acceptance separate. |
| [source-manifest.json](../../runtime/research/quad-landscape-20260905/source-manifest.json) | Source URLs, local asset hashes and integrity checks. |

All horizontal coordinates are **physical metres**, project **X east / Z south**, origin latitude **40.24516**, longitude **−75.63516**. Vertical DEM and Roofer measurements are NAVD88 metres. Current export is **X = 2X_m, Z = 2Z_m, Y = 2(height_m − 25)**. Kipp's design-floor elevations have an explicit datum caveat below. The prior research and current building generators share this frame. [Campus register](../../runtime/campus-reconstruction/campus-plan-v1/campus-register.json), [raw source CityJSON](../../runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json).

## Primary imagery and dates

The main current source is the school's **1920 × 1080 video titled “2026 Drone Fly Through Full Video”**, cached as [campus-2026-drone-1080.mp4](../../runtime/research/athey-20260905/campus-2026-drone-1080.mp4), SHA-256 `b4c03c8d5462030ce8e95e5f56b3260da044501144f7390cbfc24e89c3894b21`. It is about 4:40 long. The title/publication year is not proof of a single filming date. Frames 253–259 show the tennis pavilion during roof construction, whereas the school's separately published 2026 aerial shows its finished gray roof. Use the aerial for the completed pavilion state. [Official video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4), [official aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg), [school campus page](https://www.thehill.org/about/our-campus).

| Reference | Reliable visible evidence |
|---|---|
| [9 s](../../runtime/research/quad-landscape-20260905/drone-009s.png) | Looking from Ryan toward the west: open lawn, pale perimeter paths, central red crossing and major Hunt-side crowns. |
| [18 s](../../runtime/research/quad-landscape-20260905/drone-018s.png) | Ryan west side: broad square-jointed pale paving, raised garden strip, wide stair flight, dark rails and narrower garden crossings. |
| [137 s](../../runtime/research/quad-landscape-20260905/drone-137s.png) | Western enclosure, Chapel/Hunt gap and Athey west tree mass. |
| [139 s](../../runtime/research/quad-landscape-20260905/drone-139s.png) | Primary central/west path trace; red path and broad Athey approach, perimeter curvature, Hunt planting. |
| [142 s](../../runtime/research/quad-landscape-20260905/drone-142s.png) | More of the eastern lawn and east Hunt tree crown. The large H is an editing overlay, not a ground marking. |

At **139 s, the upper-image building is Alumni Chapel at the west end**. Athey is image-left and Hunt image-right. Ryan lies toward the image-bottom/east and requires its separate 9/18 s references. A [90° counterclockwise viewing copy](../../runtime/research/quad-landscape-20260905/drone-139s-north-up.png) helps avoid that orientation error. The cached **PEMA 2021 orthophoto** is a georeferenced shape check, not authority for current paving color or vegetation. Its original 1 m sampling does not gain detail when resampled to a 0.25 m research grid. [Physical-frame orthophoto](../../runtime/research/quad-landscape-20260905/quad-pema-2021-project-frame.png), [county-footprint source service](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6).

## Alignment, uncertainty and the Athey correction

Four manually interpreted base/entry points establish an **exploratory ground-plane homography** for frame 139. Two Athey picks are partly obscured or tentative. Four control points give algebraically zero fit residual; that is **not accuracy evidence**. Independent older path checks differ by **2.27 m and 3.88 m**. The fit does not correct terrain-height differences or roof/crown parallax and is not an accepted calibrated camera solution. Exact matrices, picks and checks remain in [quad-alignment-trial.json](../../runtime/research/quad-landscape-20260905/quad-alignment-trial.json); [control crops](../../runtime/research/quad-landscape-20260905/control-pixel-regions-139s.png) make the uncertainty reviewable.

The parent subsequently located the generated Athey central north doorway on its real Roofer edge at **XZ [58.73547095, 43.74520904] m**, source threshold **67.35 m NAVD88**. Two-block quantization gives a block-bottom level of **67.5 m**. The old tentative alignment control was **[60, 40.5]**, a **3.483 m** discrepancy. The red path's southern endpoint **[62.701, 30.865]** is at the interpreted lawn/terrace edge, **13.477 m** from that actual doorway; the initial terrace polygon did not bridge the entire gap. The parent implemented a broad approach rising **67.2 → 67.5 m**, with the building fixed. The correction file records the endpoint, threshold and an optional 4 m wide approach centerline. Its width and outer terrace shape remain interpreted. [Threshold correction](../../runtime/research/quad-landscape-20260905/quad-threshold-join-correction.json), [frame 139](../../runtime/research/quad-landscape-20260905/drone-139s.png).

Do not stretch the entire Quad or shift Athey to force the old homography to fit. Prefer current component thresholds for the final joins. The Chapel's modeled south addition also extends beyond its historical county/Roofer ring: clip landscaping against the **current generated architecture**, including that addition, rather than only the raw source footprint. [Initial proposal limitations](../../runtime/research/quad-landscape-20260905/quad-landscape-measurements.json).

## Practical landscape proposal

The interpreted lawn is about **4,049 m² after proposed path subtraction**. Keep the middle open. The school footage supports perimeter circulation and one red transverse walk; it does not support extra diagonals, sports markings, an H decal, or a central tree grove. Proposed widths are estimated and rounded for implementation; detailed vertex arrays are in the JSON. [Frames 9, 18, 139 and 142](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4), [proposal plan](../../runtime/research/quad-landscape-20260905/quad-landscape-proposal.png).

| Feature | Proposed width | Implementation evidence |
|---|---:|---|
| Chapel–north lawn–Ryan perimeter | 3.2 m | Pale concrete/light paving; west and north curvature traced primarily from 139 s. Eastern continuation is less certain. |
| Chapel–Athey west walk | 2.2 m | Pale, often shaded gray; preserve the western building gap. |
| Athey lawn-side walk | 2.3 m | Curved walk broadens at the central terrace; use the threshold correction above. |
| Central red walk | 2.7 m | Brick-like paving from Athey terrace to Hunt entry. |
| Ryan continuous west walk | 4.2 m | Broad pale square-jointed surface visible at 18 s; lower than the arcade landing. |
| Ryan end connections | 2.5–3.2 m | Join the existing north/south component geometry locally. |
| Ryan garden crossings | 1.4 m | Two narrow crossings/small step connections; exact tread counts not resolved. |
| Hunt west gap passage | 1.5 m | Stepped passage to the lower north court; precise treads/landings remain obscured. |

Ryan's research frame is `O=[115.249079686,42.994671715]`, `U=[0.913896514,0.405947240]`, `V=[0.405947240,-0.913896514]`. Its broad stair proposal occupies research **U −8.5 to −3, V 10 to 33 m**, with the upper landing approximately **69.7 m**. The root builder uses the opposite sign for its own V coordinate, so translate through physical XZ rather than copying UV values blindly. Keep the broad flight and rails already owned by the Ryan component. [Ryan reference report](hill-ryan-library-reference-20260905.md), [18 s frame](../../runtime/research/quad-landscape-20260905/drone-018s.png).

The main beds are Ryan's long curving west garden, two Hunt arcade-front beds, the Athey west tree bed, and a Chapel east strip with door openings preserved. Current footage shows dark mulch with low mixed shrubs/perennials; species, exact planting boundaries and individual small bushes are unverified. Estimated planted heights are **0.3–1.6 m**. Use ordinary landscape/building blocks; avoid ore, sculk or unrelated specialty blocks just to match a pixel color. [Planting proposal](../../runtime/research/quad-landscape-20260905/quad-landscape-measurements.json), [18 s](../../runtime/research/quad-landscape-20260905/drone-018s.png), [139 s](../../runtime/research/quad-landscape-20260905/drone-139s.png).

| Tree mass | Proposed XZ m | Crown radius | Height above ground |
|---|---|---:|---:|
| Hunt west large | [65, −21] | 5.5 m | 15 m, plausible 12–18 |
| Hunt east large | [90, −19.5] | 8.5 m | 19 m, plausible 15–22 |
| Hunt west-end small | [54.7, −15.8] | 3.3 m | 5.5 m, plausible 4–8 |
| Athey west large | [21, 31] | 7.5 m | 16 m, plausible 12–20 |
| Chapel/Hunt grove south | [23, −22.5] | 6 m | 17 m, plausible 13–22 |
| Chapel/Hunt grove north | [31, −30] | 6 m | 17 m, plausible 13–22 |
| Ryan west garden small | [109.5, 26.5] | 3 m | 5.5 m, plausible 4–8 |
| Ryan south garden small | [104.5, 38] | 2.7 m | 4.8 m, plausible 3.5–7 |

These are **photo-proportion proposals, not classified-LiDAR tree measurements**. Centers are approximate trunk positions, typically ±3 m; crown radii ±2 m. Species are null. The 8 markers represent the most useful visible masses, not a complete arboricultural inventory. Do not apply the ground homography directly to a crown-top pixel. None of these proposed centers lies inside the raw four-building source rings, but current additions and component-owned trees still require collision/duplication checks. [Tree evidence and uncertainty fields](../../runtime/research/quad-landscape-20260905/quad-landscape-measurements.json).

## Grade and verification

The native **0.5 m bare-earth DEM** provides the grade evidence. Across the central lawn, samples are mostly **65.8–66.7 m NAVD88**. A west-to-east profile at Z=10 rises from **66.03 m at X=16** to **67.03 m at X=119**. Ryan's garden-to-step profile rises from roughly **66.5 m** to **69.3 m**, consistent with its raised landing. Hunt's north-side DEM drops from **65.13 m at [77,−28]** to **58.53 m at [77,−53]**; samples beneath the building are interpolated terrain, not floors. Do not flatten this north court up to Quad level. [DEM plot](../../runtime/research/quad-landscape-20260905/quad-dem-and-buildings.png), [native DEM](../../runtime/campus-reconstruction/roofer-chapel-trial/inputs/hill-campus-dem-0p5m.tif), [profile data](../../runtime/research/quad-landscape-20260905/quad-landscape-measurements.json).

The initial source-ring intersection check found only **2.845 m²** of path/building overlap at the intended Hunt central entry connection; other paths did not overlap these raw building polygons. This does not certify current generated stairs, additions or retaining walls. Audit a walk from Athey threshold across the red path to Hunt, the complete pale perimeter, and Ryan's stair-to-garden connection in native Minecraft. For likeness, compare the same 9 s, 18 s and 139 s view directions, lawn extent, tree silhouettes, paving brightness and actual building gaps. The research agent did not control Chrome/Blender or edit world outputs; the parent's reported native render is not an independent screenshot audit by this research pass. [Geometry audit](../../runtime/research/quad-landscape-20260905/research-validation.json).

## Expanded campus identities

The current official map supplies names, while the **July 2021 facilities/address plan** supplies useful explicit house and unit locations. Their map numbers are different. Matched county labels are only corroboration: some are stale or duplicated. Source feature indices below are **zero-based**; campus atlas labels are one greater. The complete Roofer parent, including its suffix, is the join key. [Current map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), [2021 facilities plan](https://resources.finalsite.net/images/v1633097238/thehillorg/ewtimjvxagjkgblsqf5q/fy22campusmapgraphic.pdf), [comparison assets](../../runtime/research/quad-landscape-20260905/additional-official-building-identities.json).

Thomas **#39** is one joined duplex parent (2021 9A/9B). Pine Court **#40** has **two L-shaped parents**, combining 2021 8A/8B and 8C/8D respectively; all four labeled housing blocks must be represented. Feroe **#38** matches 2021 building 11. Hillhouse & Moore **#49** matches the western larger joined High Street office footprint, 2021 63 at **701/703 High Street**; no internal division is asserted. The old “Advanced Eye Care / Anton Corp” county use label must not override the school's current identity. [West facilities crop](../../runtime/research/campus-priority-20260905/campus-map-2021-west-zoom.png), [office facilities crop](../../runtime/research/quad-landscape-20260905/facilities-business-office-2021-detail.png), [office county comparison](../../runtime/research/quad-landscape-20260905/identity-business-office-county-ortho.png).

East Faculty Village **#35** needs **seven county outlines**: four duplexes in its western row and three single houses around the courtyard, corresponding to 2021 46A–46D and 47–49. The group is south of Green Street; nearby houses across Green Street are separate context and were not added by proximity. Its union bounds are **[428.254, −96.889, 496.831, −9.994] m**. [Current-map detail](../../runtime/research/quad-landscape-20260905/current-map-east-village-detail.png), [facilities detail](../../runtime/research/quad-landscape-20260905/facilities-east-campus-2021-detail.png), [county comparison](../../runtime/research/quad-landscape-20260905/identity-east-faculty-village-county-ortho.png).

Gatehouse **#51** is the **12.55 m² tiny parent `160015116006-143655d070`**, at **[384.650, −198.856] m**, matching the 2021 entrance star 42. It already lies inside the parent's earlier [−224,−224,416,160] crop. The much larger house approximately 56 m east is **2021 Dellfield House 41**, parent `1600151160061C-551ba4628e`; it is neither Gatehouse nor Hunt despite its stale county Upper School label. Current use of that unnamed-on-current-map house is not asserted. [Facilities entrance detail](../../runtime/research/quad-landscape-20260905/facilities-east-campus-2021-detail.png), [approximate plan-label matching](../../runtime/research/quad-landscape-20260905/facilities-label-spatial-matches.json).

Lehrman **#25** consists of a **round south viewing pavilion** (source 53) and **long north service bar** (source 54). The school and contractor describe one pavilion; the county source leaves a small gap and omits porch/connecting sections, so the two shells should not be presented as detached buildings. Combined bounds are **[491.952, −563.128, 524.698, −523.915] m**. The school identifies the south upper viewing balcony; contractor photos show the round two-story form and joined bar. [School facilities](https://www.thehill.org/athletics/facilities), [Wohlsen primary project](https://wohlsenconstruction.com/project/the-hill-school-lehrman-pavilion/), [contractor exterior](../../runtime/research/campus-priority-20260905/lehrman-1.jpg), [county comparison](../../runtime/research/quad-landscape-20260905/identity-lehrman-county-ortho.png).

Warner **#7** was already resolved to source 40, parent `160015116006389O-f1989780fb`; the county garage classification reflects an earlier use. This pass found no separate officially named “Warner pavilion” requiring another county parent. Small landscape shelters may exist without current-map numbers and remain outside this bounded named-building inventory. [Current official map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), [existing Warner current reference](../../runtime/research/campus-priority-20260905/warner-2026.jpg).

The next facade research priority adjacent to the developed Quad is **Warner, the Mercer/Sweeney aggregate, Annan, Davy, Music House, Wendell and Quadrivium**, followed by Meigs, CFTA/rink and nearby housing. The inventory distinguishes the five developed component-study parents from the **37 remaining county parents**; even a developed parent may contain an unfinished subpart such as Dining Hall. Whole-parent facade completion is not asserted. [Prioritized inventory](../../runtime/research/quad-landscape-20260905/full-named-campus-building-inventory.json).

The [completeness checklist](../../runtime/research/quad-landscape-20260905/campus-completeness-checklist.json) accounts for every current-map label. No named enclosed-building/pavilion group lacks either an accepted county footprint or a separate explicit geometry proposal. The two missing county parents remain documented, as do Lehrman's connecting section and historical/source-outline limitations. Native placement, detailed facade completion and unnamed auxiliary structures remain separate work items.

## Current structures missing from the county source

**Kipp '46 Pavilion, map #19:** the borough hosts Langan's **20 June 2023 Phasing Plan**, printed drawing **CF-001** although the PDF internal title is CS-101. It specifies a **122 × 42 ft main rectangle**, **212 ft lower FFE**, **226 ft upper FFE**, and a small north entry projection; the footprint is attributed to Schrader Group. Converted main dimensions are **37.1856 × 12.8016 m**, with a **4.2672 m** floor-to-floor difference. These are design dimensions, not as-built measurements. The current aerial verifies a completed long pavilion with three prominent court-facing gables. [Published plan](https://www.pottstown.org/AgendaCenter/ViewFile/Item/14290?fileID=6442), [plan detail](../../runtime/research/quad-landscape-20260905/kipp-plan-pavilion-detail.png), [current aerial detail](../../runtime/research/quad-landscape-20260905/current-aerial-tennis-detail.png).

Using the printed scale and existing 801 Beech Street house bearing/midpoint gives a provisional Kipp center **[371.002, −286.740] m**, bounds **[351.825, −295.961, 390.315, −277.837] m**, horizontal uncertainty about **±2.5 m**. The transformed court fence agrees with the older orthophoto at the level appropriate for an approximate placement. The house is a simplified county roof outline, so this is not surveyed georeferencing. The north projection's precise vertical extent should be checked before extruding it through both floors. [Registration and polygon](../../runtime/research/quad-landscape-20260905/current-pavilion-proposals.json), [overlay review](../../runtime/research/quad-landscape-20260905/kipp_46_pavilion-proposal-ortho-review.png).

Converted Kipp design FFEs are **64.6176 / 68.8848 m**. **The retrieved sheet does not explicitly state the vertical datum.** They broadly agree with local DEM levels, but cannot be described as verified NAVD88 floors. Suggested blocking levels are lower 64.62, upper 68.88, eave 72.3 and ridge 76.3 m; the latter two are photo estimates, approximately ±1.5 m at ridge. Use gray ordinary roof blocks, white gable cladding/fascia, red-brown brick lower work and columns, recessed dark openings and the visible veranda. Exact window/door counts are unverified. The county review separately confirms the two-story proposal and distinguishes adjacent 801 Beech Street housing from it. [County primary review, April 2023](https://www.pottstown.org/AgendaCenter/ViewFile/Item/14090?fileID=6351), [plan](https://www.pottstown.org/AgendaCenter/ViewFile/Item/14290?fileID=6442), [current aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg).

**Madden Stadium press box, map #26:** the school names **Frank Puccio '66** in its account of the **8 September 2023** dedication. Current video frames 220, 250 and 253 show a compact elevated enclosed box over the west metal bleachers, separate from Lehrman's round pavilion. Its approximate proposed center is **[478.625, −490.028] m**, bounds **[473.654, −495.894, 483.595, −484.161] m**, room size **12 × 3.5 m**, with roughly **±5 m position / ±2 m height** uncertainty. Suggested DEM-based levels are support ground 74.86, box floor 79.66, flat roof 82.46 and filming guard 83.56 m NAVD88. These levels and sizes are photo proportions, not construction-plan measurements. [School dedication](https://www.thehill.org/about-us/news/detail/~board/archive-news/post/dedication-of-madden-stadium-is-celebrated-with-first-ever-friday-night-lights-football-game), [253 s frame](../../runtime/research/quad-landscape-20260905/drone-253s.png), [proposal and method](../../runtime/research/quad-landscape-20260905/current-pavilion-proposals.json).

The Madden method uses manually picked outer football field lines, assumed regulation dimensions and the measured Lehrman direction/approximate projected ground center. It is an approximate field-plane registration, not a solved camera calibration. Build the compact light-colored box, field-facing dark glazing, filming guard and open supports; do not turn the whole bleacher stand into an enclosed building. **Both Kipp and this box fit the expanded [−224,−608,544,160] m terrain**, although that crop does not cover every Far Fields surface. [Madden overlay review](../../runtime/research/quad-landscape-20260905/madden_puccio_66_press_box-proposal-ortho-review.png), [school facilities](https://www.thehill.org/athletics/facilities).

## Complete county-parent table

Bounds are `[Xmin, Zmin, Xmax, Zmax]` in metres from the unmodified county geometry in the shared frame. The “developed study” label identifies a studied component associated with that parent, not every facade of the entire aggregate. [Source county register](../../runtime/campus-reconstruction/campus-plan-v1/campus-register.json), [current naming evidence](../../server-assets/hill-campus-building-identities.json).

| Map | Building/part | Parent ID | Source index | County bounds XZ (m) | Status |
|---|---|---|---:|---|---|
| 29 | Hunt Upper School Dormitory | `160015116006-d4f3b48752` | 77 | 41.70, -47.55, 117.42, -15.15 | Developed study |
| 48 | Class of 1960 Alumni House | `1600151120011C-e738fb4171` | 84 | -164.55, 82.16, -152.58, 108.64 | Developed study |
| 2 | John P. Ryan Library | `160015116006-567a5eddd9` | 73 | 114.85, 4.62, 158.10, 50.32 | Developed study |
| 3,4 | Athey Academic Center / Dining Hall - Millhiser Family Dining Room | `16001511600613C-92645e8573` | 32 | 8.55, 33.50, 94.37, 116.08 | Developed study |
| 6 | Alumni Chapel | `1600151160068C-6108d587dc` | 64 | -9.76, -12.20, 11.58, 20.48 | Developed study |
| 7 | Warner Center for Spiritual Life and Equity | `160015116006389O-f1989780fb` | 40 | -47.76, -72.32, -35.21, -63.06 | Measured source; facade pending |
| 8 | Davy Hall Dormitory | `16001511600633C-c14400ca75` | 44 | 115.13, -126.60, 144.29, -68.80 | Measured source; facade pending |
| 12,13 | David H. Mercer Field House and Jerry Day '37 Squash Center / Sweeney Gymnasium | `160015116006-1f19950994` | 48 | -50.61, -130.41, 121.64, -56.92 | Measured source; facade pending |
| 15 | Annan Building | `1600303920031C-4b7d18d798` | 100 | 81.49, -158.74, 114.00, -117.78 | Measured source; facade pending |
| 30 | Wendell Dormitory | `16001511600617C-403d7b1a51` | 65 | 163.46, -16.23, 208.36, 15.25 | Measured source; facade pending |
| 47 | Music House | `16001511600622C-57b5b354dc` | 66 | 153.25, -33.23, 169.16, -23.56 | Measured source; facade pending |
| 50 | Shirley Quadrivium Center | `16001511600615C-ee30229dd5` | 86 | 68.52, 90.87, 162.31, 120.61 | Measured source; facade pending |
| 1 | Meigs House - Admission Office | `16001511600620C-fff89cfae9` | 24 | 190.11, 78.62, 210.08, 95.44 | Measured source; facade pending |
| 9 | Center For The Arts (CFTA) | `160031040003-894f07a81a` | 104 | 158.73, -192.42, 220.56, -145.19 | Measured source; facade pending |
| 14 | Edward Tuck Hall Arena and Thomas Eccleston Jr. Rink | `16003036400434C-c86ee564a0` | 97 | 7.53, -168.54, 79.24, -122.45 | Measured source; facade pending |
| 31 | Ferenbach Dormitory - Dell Village | `16001511600641C-fab9d4a2e4` | 68 | 300.05, -65.45, 325.67, -47.78 | Measured source; facade pending |
| 32 | Senter Dormitory - Dell Village | `16001511600641C-d333862570` | 42 | 295.31, -91.94, 318.93, -69.21 | Measured source; facade pending |
| 33 | Lowndes Dormitory - Dell Village | `16001511600641C-6607e4a8a8` | 43 | 320.87, -96.43, 346.66, -79.32 | Measured source; facade pending |
| 34 | Scheerer Dormitory - Dell Village | `16001511600641C-7e1d6bacf8` | 70 | 327.21, -75.52, 352.08, -52.21 | Measured source; facade pending |
| 36 | Foster Dormitory | `16001511600621C-2c9084ad78` | 31 | 329.84, 25.99, 377.71, 63.72 | Measured source; facade pending |
| 37 | Rolfe Dormitory | `16001511600625C-c108a9b9b6` | 25 | 256.01, 63.73, 308.90, 89.13 | Measured source; facade pending |
| 38 | Feroe House - Head of School Residence | `16001511600623C-ba74e78741` | 30 | -183.27, 21.67, -161.13, 43.21 | Measured source; facade pending |
| 39 | Thomas House | `16001511600610C-e7f1a01cbc` | 61 | -180.13, -36.18, -168.49, -13.68 | Measured source; facade pending |
| 40 | Pine Court Faculty Village - eastern joined pair | `16001511600611C-50fbc7ea98` | 69 | -137.34, -76.65, -113.15, -44.36 | Measured source; facade pending |
| 40 | Pine Court Faculty Village - western joined pair | `16001511600611C-a5bb4f8f72` | 71 | -174.25, -81.53, -146.29, -53.12 | Measured source; facade pending |
| 41 | Sherrerd Dormitory - Dutch Village | `160015116006-07f1d5b7e0` | 75 | -127.47, -15.32, -106.24, 4.68 | Measured source; facade pending |
| 42 | Johnson Dormitory - Dutch Village | `160015116006-36b81aa17d` | 58 | -105.16, -33.79, -89.64, -12.25 | Measured source; facade pending |
| 43 | Markle Dormitory - Dutch Village | `160015116006-53c8a9efca` | 59 | -80.23, -31.01, -58.77, -15.55 | Measured source; facade pending |
| 44 | Robins Dormitory - Dutch Village | `160015116006-451a0df37b` | 74 | -67.79, -5.09, -51.24, 16.50 | Measured source; facade pending |
| 45 | Hillrest Dormitory | `160015116006-c7b546273e` | 36 | -111.89, 31.05, -94.03, 47.48 | Measured source; facade pending |
| 46 | The Sherrill Guest House | `16001511600619C-b4c5171aed` | 67 | 276.94, -61.36, 295.37, -49.03 | Measured source; facade pending |
| 49 | Hillhouse & Moore Business Office | `1600151000041C-510dc616b8` | 3 | -205.86, 78.22, -189.03, 103.06 | Measured source; facade pending |
| 25 | Lehrman '56 Pavilion - south round viewing pavilion | `160015116006-081aa7dcac` | 53 | 491.95, -538.41, 506.61, -523.92 | Measured source; facade pending |
| 25 | Lehrman '56 Pavilion - north service bar | `160015116006-f7611d45c7` | 54 | 501.59, -563.13, 524.70, -536.53 | Measured source; facade pending |
| 35 | East Campus Faculty Village - west north-middle duplex | `160006438008-c0e2b642d9` | 6 | 438.41, -74.55, 454.44, -56.14 | Measured source; facade pending |
| 35 | East Campus Faculty Village - northeast single house | `160006438008-5e66af9ae7` | 7 | 485.76, -89.28, 496.83, -74.16 | Measured source; facade pending |
| 35 | East Campus Faculty Village - north middle single house | `160006438008-e070cb1680` | 8 | 473.10, -91.38, 484.51, -76.26 | Measured source; facade pending |
| 35 | East Campus Faculty Village - northwest duplex | `160006438008-8e22af513e` | 9 | 440.35, -96.89, 454.67, -78.82 | Measured source; facade pending |
| 35 | East Campus Faculty Village - south single house | `160006438008-47b633ec2f` | 14 | 452.28, -25.28, 464.26, -9.99 | Measured source; facade pending |
| 35 | East Campus Faculty Village - southwest duplex | `160006438008-ddefd3570f` | 15 | 428.25, -32.78, 446.51, -13.12 | Measured source; facade pending |
| 35 | East Campus Faculty Village - west south-middle duplex | `160006438008-b790426980` | 16 | 433.73, -53.58, 451.65, -34.03 | Measured source; facade pending |
| 51 | Gatehouse | `160015116006-143655d070` | 51 | 382.83, -200.60, 386.48, -197.14 | Measured source; facade pending |
