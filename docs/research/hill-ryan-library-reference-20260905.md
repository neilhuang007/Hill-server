# John P. Ryan Library: measured geometry and facade references

Researched 2026-09-05 for the campus reconstruction. **Ryan is a rough stone historic hall with an independently shaped low addition and a five-bay west arcade.** It needs separate west, east, north and south facade components. This report supplies physical dimensions and source observations; it does not approve a Minecraft likeness. No builder, world, campus identity file, Chrome or Blender session was changed.

## Identity and exact geometry join

Ryan is **number 2 on the current official map**, on the east side of the main Quadrangle, between Hunt to the north and Athey to the south. The footprint has been matched by position and shape against the school map and aerial, rather than by county building name. [Current school map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), [school campus page](https://www.thehill.org/about/our-campus), [school 2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg).

| Field | Verified value |
| --- | --- |
| Existing campus source footprint | **74**, zero-based source feature index **73** |
| Roofer parent | **`160015116006-567a5eddd9`** |
| LoD2.2 child | `160015116006-567a5eddd9-0` |
| County `STRUCTUREID` / `PARID` | `160015116006` / `160015116006` |
| Current county `OBJECTID` | `412511`, returned by a spatial point query on 2026-09-05 |
| Current county `IMPRNAME`, `YRBLT`, `DESCRIPTION` | All null |
| County-outline centroid, longitude/latitude | `-75.63354725873072, 40.24489558736162` |
| Projected centroid, EPSG:6347 | `446114.1003, 4455131.2879` m |
| County outline area, projected | **1,099.5995 m²** |

The bare county `STRUCTUREID` is shared by several campus outlines. Use the complete Roofer parent or the spatially verified outline, not that field as a unique key. Evidence: [county source layer](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6), [current query response](../../runtime/research/ryan-library-20260905/ryan-county-current-source.geojson), [existing identity join](../../server-assets/hill-campus-building-identities.json).

## Measured plan and roof

These are measurements of the **existing LiDAR-derived CityJSON**, not a new architectural survey. All heights in this section are **NAVD88 metres**, with no Minecraft offset. Horizontal project coordinates are X east and Z south in metres. The source is [hill-campus-roofer.city.json](../../runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json), SHA-256 `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`; its horizontal CRS is EPSG:6347. Full face coordinates and fitted planes are in [ryan-roof-measurements.json](../../runtime/research/ryan-library-20260905/ryan-roof-measurements.json).

| Measurement | Value and interpretation |
| --- | --- |
| Reconstructed ground footprint | 1,087.6510 m², one GroundSurface; about 11.95 m² smaller than county outline |
| Project footprint bounds | X 114.8488–158.0970; Z 5.9833–50.3186 m |
| Source ground attribute | 66.3000 m; **not a uniform finished-floor or perimeter-grade height** |
| Source ridge attribute | 85.4472 m |
| Highest source geometry vertex | 87.1301 m; distinct from the ridge attribute and including small upper features |
| Source reconstruction RMSE | 0.5832 m, `rf_rmse_lod22`; this is not a facade-position accuracy guarantee |
| Roof segmentation | `rf_roof_planes=57`; loader emits **26 semantic RoofSurfaces**, zero rejected faces. These counts describe different stages. |
| Main roof faces 23 / 20 | Projected areas 253.5361 / 245.0053 m²; fitted slopes 36.3735° / 36.5892° |
| Main-roof envelope | **42.1494 m long × 15.2624 m wide**, minimum rotated rectangle of faces 20 and 23; not the complete wall rectangle |
| Main roof axis | **23.9505° east of north**, NNE–SSW |
| Main roof vertex ranges | Face 23: 79.4342–85.7779 m; face 20: 80.2560–85.9290 m |
| Eastern low roofs | Face 9: 208.6169 m², 73.6199–73.7154 m, 0.267° slope. Nested face 4: 129.4218 m², 75.3117–75.4114 m, 0.383° slope. |
| Corner cross roofs | Paired smaller roof faces near both ends; mostly 35.9–38.7° slopes, maxima approximately 83.2–83.7 m |

The eastern addition has several levels, parapets and transitions. Preserve the faces and overlaps instead of summing projected roof areas into a footprint. Face 3 is steep (72.25°) and runs from about 71.41 to 80.82 m near the southeast junction; it needs image comparison before being treated as a conventional pitched roof. Several tiny surfaces near the ground also need classification. The source reports reconstruction success, but that does not validate these details.

![Measured Ryan roof plan](../../runtime/research/ryan-library-20260905/ryan-measured-roof-plan.png)

**West arcade caveat:** the 18 s overhead frame clearly shows a low flat roof over the five arches. It is not clearly preserved as its own west-side flat component in the 26-face roof model. The central west ground edge also stays close to the historic wall. Model and audit the arcade as a separate photo-supported component; do not raise its roof to the main eaves or fill the arches as walls. [School drone, 1080p](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4), [18 s frame](../../runtime/research/ryan-library-20260905/drone-018s.png).

## Recommended local frame and initial entrance dimensions

This optional frame makes facade placement reproducible:

```text
O_project_XZ = (115.249079686, 42.994671715) metres
U_unit_XZ    = ( 0.913896514,  0.405947240)   toward ESE
V_unit_XZ    = ( 0.405947240, -0.913896514)   toward NNE
project_XZ  = O + U * U_unit_XZ + V * V_unit_XZ
```

O is the southwest corner of the dominant-roof envelope, **not a surveyed corner of the west facade**. The measured central west wall lies near U 1.32–1.38, V 8.55–33.02 m. North and south corner projections extend approximately to U −0.4. The full irregular ground ring is in [ryan-local-frame-and-dem.json](../../runtime/research/ryan-library-20260905/ryan-local-frame-and-dem.json). “West” below means WNW, outward bearing about 294°; east means ESE, 114°; north/south ends face about 24°/204°.

The following are **initial photo estimates**, intended for a first render and subsequent correction. They combine the measured roof/wall extent with image proportions; they are not independent measurements of the arcade:

| Component | Trial dimensions in the frame above | Uncertainty |
| --- | --- | --- |
| Covered west arcade | U approximately −3.0 to +1.35; V approximately 10 to 33 m | About ±1 m at boundaries; independently compare its projection beyond corner bays |
| Five arcade bay centres | V approximately 12.3, 16.9, 21.5, 26.1, 30.7 m | Provisional even spacing; refine against the frontal photo |
| Clear arch opening | Approximately 3.0–3.5 m wide and 4.6–5.2 m high | Rough image-ratio estimate; do not infer exact gothic curvature at block scale |
| Main exterior stair run | Extends west to approximately U −8 m | Approximate run; tread count and side grades need an in-game check |
| Covered entry landing | **Start near 69.7 m NAVD88**, with ±0.8 m uncertainty | DEM- and photo-informed trial height, **not a surveyed door threshold** |
| Low arcade roof/parapet | Start with total height about 6–7 m above landing | Photo estimate only; check upper-window clearance and main eave relation |

The cached 0.5 m bare-earth DEM gives approximately 69.2–69.5 m at probes near U −4 to −2, V 15–20, versus approximately 67.8 m at U −8, V 20. The terrain drops toward the north end; the source ground attribute of 66.3 m reflects lower ground, not the raised west entrance. DEM cells beneath structures can be interpolated and cannot establish exact stair treads or finished floors. Probe locations and values are retained in the local-frame JSON, with a [DEM comparison plot](../../runtime/research/ryan-library-20260905/ryan-local-frame-and-dem.png). The DEM file and hash are recorded in the [existing measured-terrain manifest](../../runtime/campus-reconstruction/measured-terrain/hill-chapel-measured-terrain.manifest.json).

Keep these values in metres. Apply the campus's currently requested **2 blocks per metre** and shared vertical datum conversion once at output; none of these coordinates are already scaled block coordinates.

## Independent facade evidence

Primary exterior photos are provided by the project's contractor, Wohlsen. Current contextual evidence comes from the school-hosted drone advertised as its 2026 fly-through. The downloaded 1080p video is 1920×1080; upload/title year does not establish its exact filming date. Contractor photo paths contain 2016 but do not establish photo capture dates. Full source URLs, local assets and SHA-256 hashes are retained in [source-manifest.json](../../runtime/research/ryan-library-20260905/source-manifest.json).

| Side | Best reference | Coverage and limitations |
| --- | --- | --- |
| West / Quad | [Wohlsen frontal exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_4.jpg), [local photo](../../runtime/research/ryan-library-20260905/wohlsen-west-front.jpg); drone [18 s](../../runtime/research/ryan-library-20260905/drone-018s.png), [21 s](../../runtime/research/ryan-library-20260905/drone-021s.png), [24 s](../../runtime/research/ryan-library-20260905/drone-024s.png) | Strongest facade evidence: complete frontage, roof over arcade, steps and central recessed entry. Sun flare affects the current frontal frame. |
| North / Hunt end | Drone [12 s](../../runtime/research/ryan-library-20260905/drone-012s.png), [15 s](../../runtime/research/ryan-library-20260905/drone-015s.png), [north detail crop](../../runtime/research/ryan-library-20260905/drone-012s-north-end-detail.png) | Independent view of short gable end. Small image footprint and heavy shadows/foliage limit pane counts and lower openings. Enlarged crop adds no source detail. |
| South / Athey end | Drone [99 s](../../runtime/research/ryan-library-20260905/drone-099s-south-end.png), [south detail crop](../../runtime/research/ryan-library-20260905/drone-099s-south-end-detail.png) | Strong view of projecting central bay, upper rectangle and lower tall arched glazing. Flagpole obscures the east return; tree covers the west return. |
| East / low addition | [Wohlsen addition exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_1.jpg), [local photo](../../runtime/research/ryan-library-20260905/wohlsen-east-addition.jpg); drone 12–15 s for roof mass | East orientation is inferred from the unique addition in the plan, not photo compass metadata. Only part of the addition and historic wall is shown. No complete current east elevation was obtained. |

### West components

The frontal contractor image shows **five pointed arcade openings and five upper arched tracery-window groups**. Upper groups each have three principal vertical lights. The central entrance is recessed behind the middle arcade bay. Rough masonry piers support a smoother warm pink/tan parapet band; openings are deep and dark. The north projecting bay has stacked rectangular glazing, whereas the south gabled block has a broad rectangular upper window and a separate pointed lower entrance. These flanking blocks differ. Historic walls have horizontal coursing, small parapet steps, end gables and two visible ridge chimneys. [Wohlsen front photo](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_4.jpg).

The current 24 s frame separately resolves the recessed entry: paired open doors, a horizontal transom, then two rows of three larger rectangular panels above. The arcade ceiling and entry wall sit behind the front piers. At 18 s, broad stairs, dark railings, separate south steps and planting islands are visible. The roof over the arcade has a gravel-like flat surface. [24 s entry](../../runtime/research/ryan-library-20260905/drone-024s.png), [18 s overhead](../../runtime/research/ryan-library-20260905/drone-018s.png).

### North and south window groups: do not mirror

| End | Visible groups worth modeling | Count status |
| --- | --- | --- |
| North upper principal level | One broad central rectangular group and one smaller rectangular group on each side: **three groups** | Groups are visible; central group appears to have five principal lights, but fine counts are medium confidence in the shadowed aerial |
| North gable | **One small central group** beneath the gable apex | Too small to establish detailed frame profile |
| North middle level | One central horizontal rectangular group, plus partly visible flanking openings | Do not complete a repeated grid through obscured areas |
| North lowest visible level | At least **five separate dark rectangular openings/groups** can be distinguished across the visible portion | A visible minimum, not a complete verified elevation; right/lower portions are obscured |
| South upper central bay | **One broad rectangular group with five visible principal vertical lights** | Clearer than north; angled side glazing belongs to separate planes |
| South lower central bay | **One tall arched tracery group with five principal vertical lights**, plus lower panels | Clear primary group; not the lower rectangular composition of the north end |
| South angled east return | **One upper rectangular group and one lower arched group** are visible | Partial obstruction by flagpole; do not claim complete pane counts |
| South angled west return | Glass/openings partly suggested behind the tree | Full configuration unknown; do not assert symmetry as measured evidence |
| South gable | **One small paired rectangular group** | Two small windows/lights visibly separated |

The south bay projects in plan, with angled returns, stone bands, stepped shoulders and vertical buttress-like elements. The north end is flatter and has a different lower opening composition. Sources are the independent [12 s north frame](../../runtime/research/ryan-library-20260905/drone-012s.png) and [99 s south frame](../../runtime/research/ryan-library-20260905/drone-099s-south-end.png), extracted from the [school's video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4).

### East addition components and materials

The contractor photo shows large smooth pink/tan rectangular stone panels, angular parapet accents, broad rectangular glazing with warm brown/orange frames, rough stone at the base, and a low curved masonry terrace/retaining wall. Historic rough stone and a pointed upper window remain visible behind it. This addition needs its own window layout and low roof profile. The photo does not provide the whole east wall or all current replacements. [Wohlsen addition photo](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_1.jpg).

Wohlsen explicitly identifies **imported German Dietenhan stone for the new addition** and H2L2 as architect. It records 24,500 ft² of renovation and 9,800 ft² of addition; those are project floor areas, not measured footprint areas. Do not assign the addition's named stone to every historic wall. [Contractor project record](https://wohlsenconstruction.com/project/the-hill-school-john-p-ryan-library/).

The visual material classes are rough coursed stone, smoother warm trim/panels, dark framed glazing and pale gray/green pitched roof covering. **The historic library is visibly stone, not Athey's red brick treatment.** Exact historic stone lithology and the installed roof product have not been verified. Contractor photography has a greenish lighting/color cast; current video appears pinker. Keep semantic block choices constrained to normal masonry/trim/roof/glass materials, then adjust their proportions in the same Minecraft lighting as the audit view. A slate-like appearance is an interpretation, not a documented product identification. [Front photo](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_4.jpg), [current front frame](../../runtime/research/ryan-library-20260905/drone-021s.png).

## Remaining source gap and next visual checks

The school's publicly indexed Archives inventory identifies a **62-sheet H2L2 library addition/renovation set dated November 23, 1988, revised December 30, 1988**, and says a digital copy is held in Archives. It also dates the renovated library's dedication to June 1990. The actual drawings were **not obtained**; the inventory URL currently returns 404 directly after the website redesign while search still exposes its primary text. These drawings would be the best next source for exact sill heights and unseen elevations. No contact message was sent. [School Archives inventory](https://www.thehill.org/about-us/hill-traditions/archives).

For the first model audit, use four separately positioned cameras: west ground view aligned to the central arcade; north oblique view toward the short gable; south view from the Athey/Quadrivium approach; east addition view toward the historic hall. Also compare a top view for roof levels and the arcade projection. Check silhouettes and landing/door height first, followed by the five-bay west rhythm, unique south glazing, north rectangular groups and addition panels. The sources support a detailed first version, but **complete current east and lower north elevations, exact sill heights and hidden return windows remain unverified**.
