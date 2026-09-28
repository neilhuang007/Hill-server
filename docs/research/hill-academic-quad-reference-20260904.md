# Athey / Dining Hall exterior reference for the next bounded study

Researched 2026-09-04 by the `campus_reference` AI agent. This is source interpretation for implementation, not a visual acceptance result or a measured facade survey. The current school video, map, and local roof diagnostic were inspected directly. No builder or generated world was changed.

## Building identity and orientation

The county feature `STRUCTUREID=16001511600613C`, `IMPRNAME=ACADEMIC CENTER #25`, aggregates a connected complex. The school's [current labeled map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf) distinguishes **Athey Academic Center, 3**, from **Dining Hall / Millhiser Family Dining Room, 4**. Athey is the tall northern bar forming the south edge of the main Quadrangle; the lower Dining Hall stands south of it, across a smaller open court. The Chapel is west of the Quad, Hunt Upper School north, and Ryan Library east. Do not apply one Athey facade to the entire county outline. See the [cached labeled map](../../runtime/research/hill-reference-20260904/campus-map-2026-labeled.png).

Coordinates below use the existing project origin `40.24516,-75.63516`, X east and Z south, in metres before the two-blocks-per-metre conversion. Approximate part boundaries are interpretations of the [measured roof plan](../../runtime/campus-reconstruction/academic-quad-preparation/academic-roof-plan.png) aligned with the official map, not separate surveyed building polygons.

| Part | Local position and implementation consequence |
| --- | --- |
| Athey main bar | Approximately X20–94, Z34–72. Its long axis runs about 18.2 degrees south of east. Preserve the tall main roof, projecting cross-gables and lower bays independently. |
| Dining Hall | Approximately X10–65, Z78–116, including irregular appendages. Its broad low roof is mostly flat/terraced. The uses of individual rear appendages are unverified. |
| Small court | Open quadrilateral approximately `(36,60), (65,70), (60,87), (29,78)`. Red brick paving and pale paved strips are visible. Keep it open to the sky. |
| West and east links | Narrow roofed links flank the court. In the builder's proposed frame, origin `(22,37)`, U along 18.25 degrees south of east and V perpendicular toward the south, their approximate zones are U16.2–21.7/V14–35.8 and U52–57/V13.5–36.6. These zones are profile estimates, not finished wall dimensions. |

## Current facade evidence and its limits

The school's [2026 fly-through](https://resources.finalsite.net/videos/t_video_mp4_480/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) is the current exterior authority. The following are observations of its 480p frames; exact pane and bay totals remain unresolved where shadow, perspective or roofs obscure them.

| View / cached evidence | Visible architectural pattern |
| --- | --- |
| Quad / north, [105 s](../../runtime/research/hill-reference-20260904/chapel-drone-11.jpg), [106 s](../../runtime/research/hill-reference-20260904/chapel-drone-12.jpg), [107 s](../../runtime/research/hill-reference-20260904/chapel-drone-13.jpg) | Large central projecting gable with oculus; smaller outer gables; broad rectangular upper window groups and pale framing. At least two round-arched lower openings are clearly visible on the near eastern flank. Central glazing and vertical trim differ from the flanking repeats. |
| East return / corner, [95 s](../../runtime/research/hill-reference-20260904/chapel-drone-01.jpg), [97 s](../../runtime/research/hill-reference-20260904/chapel-drone-03.jpg) | Paired multi-pane groups with substantial pale divisions; low projecting window bay with a dark door, notched parapet and pale coping. Stone-looking foundation, black rails, steps, planting and a sloping approach. |
| South court, [90 s](../../runtime/research/hill-reference-20260904/drone-08.jpg) | Athey left/north, Dining Hall right/south. The east link has open passage below a gray standing-seam canopy on brick piers. Dining Hall's court edge has pale-trimmed broad openings and a shallow stepped/notched parapet. |
| Roofs, [138 s](../../runtime/research/hill-reference-20260904/chapel-drone-44.jpg), [139 s](../../runtime/research/hill-reference-20260904/chapel-drone-45.jpg) | Athey left/south, Chapel at image top/west. Three north gable projections and court-link roofs are visible. The west link's complete lower enclosure is not shown. |

The official [2013–2023 campaign report, printed page 14](https://resources.finalsite.net/images/v1706640886/thehillorg/jw0ysayvvi02ln5dsucr/FY24HTFlipCampaignInsertPRINTedits.pdf) explicitly identifies **four floors** in Athey. Its renovation account concerns classrooms and shared facilities; it does not establish an exterior addition. The [cached page](../../runtime/research/hill-reference-20260904/athey-campaign-2024-page-14.png) was inspected. Four occupied floors does not imply four unobstructed window rows on every elevation.

## Roof and terrain measurements

The local [CityJSON](../../runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json), parent `16001511600613C-92645e8573`, retains the county identity, a 1998 year field, `STORIES=0`, and `Height=56`; the latter two are unsuitable as a storey count or metre height. Its independently checked roof attributes include ridge 89.1487 m NAVD88, LoD2.2 RMSE 0.653 m, and successful reconstruction. Horizontal coordinates are EPSG:6347. These are LiDAR-derived reconstruction values, not architect elevations. County source: [Montgomery County Building Outlines](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6).

The `measured_terrain` agent's direct semantic-face calculations give:

| Measured component | NAVD88 elevation / interpretation |
| --- | --- |
| Athey opposed dominant roof faces | About 44.9-degree slope, combined projected area 834.57 m²; eave-side minima 81.802 and 82.452 m, shared maximum ridge 89.1534 m. Preserve these steep planes. |
| Lower Athey appendages | Roof clusters near 70.0 and 73.4 m. These are low bays/canopies, not the main bar's eave datum. |
| Dining Hall dominant roof | A 593.51 m² plane spans 76.328–76.551 m; other substantial flat levels occur near 72.96, 74.90, 77.45 and 77.96 m. The local maximum is 79.620 m. |
| Roofer footprint coverage | Main child `-0` ground area 3116.69 m²; tiny child `-1` 0.860 m². County aggregate is about 3661.65 m². The roughly 545 m² difference requires interpreting roofs, ground surfaces and open links separately. |

Terrain samples from the measured 1 m grid show why one global base floor is insufficient:

| Location (X,Z) | Ground NAVD88 m |
| --- | ---: |
| Quad front (55,42) | 66.438 |
| Court (48,73) | 69.408 |
| East end (92,62) | 68.712 |
| West end (21,44) | 67.792 |
| Dining Hall south (38,111) | 66.137 |

Apply the existing vertical registration `(NAVD88 + 24.25) × 2` once. Roofer's global minimum ground 65.88 m is not local grade everywhere. The east corner's stairs and retaining base are evidence of a real level change, not a reason to flatten the entire setting.

## Proposed facade profile — estimates for native review

These are modeling recommendations, explicitly separate from measured values above:

- Keep three gable landmarks in the main bar frame, roughly U10, U37 and U65; the central gable is larger. Use the actual measured roof intersections to place their walls. Preserve pale gable coping and the central round/polygonal oculus instead of extending ordinary window rows into the roof.
- Candidate four-floor window sills of **67.4, 71.5, 75.5 and 79.5 m NAVD88**, about 2 m opening height, are plausible starting values only. A bottom sill at 67.4 is exposed above the central Quad sample but partly hidden at the higher ends and court. Cut windows by actual exterior exposure; do not suppress the whole lowest Quad row.
- Start repeated rectangular groups around **2.5–3 m overall width**, with distinct pale mullions and recessed connected panes. In the central gable, the broader composition appears to occupy about 55–65% of the face: approximately **5–6 m** if the face is 9–10 m wide. Keep its narrow side lights and vertical trim distinct from regular paired groups. These dimensions and the precise light count need native comparison.
- A **1.2–1.6 m oculus** is an approximate starting size. Use a dark recessed glazed opening with a thin pale surround; a solid black disk or massive trim ring would lose its depth.
- Use **round arches** for the confirmed lower flanking openings. The evidence does not support copying the Chapel's pointed Gothic window/arcade module. Preserve the upper rectangular rhythm above them. Full facade bay totals are not verified; do not claim a uniformly generated grid is surveyed.
- The strongest continuous pale bands are beneath the upper window row and below the round-arched row. Central vertical frames and local spandrels add further pale lines. A third full-width middle stringcourse is not clearly supported in the shaded current frames; validate before extending one over every flank.
- Keep the east connector open below its roof. Matching the west connector to that open construction is a reasonable initial interpretation of the common roof form, but remains unverified at ground level. Model the low Dining Hall court edge separately from either connector, and preserve its parapet profile.

## Material and age handling

Current footage supports red/brown **brick masonry**, pale cream/gray dimensional surrounds and courses, dark gray Athey roofing, a gray metal-looking connector roof, and gray/dark Dining Hall flat roofs. Exact trim stone, roof product and brick blend are not established by the images. Use actual brick blocks with an appropriately scaled brick texture, compatible pale stone components for dressed trim, connected panes and dark timber/metal details. The Chapel's brownstone texture should not cover Athey's brick walls. Material texture improvements must preserve these different construction materials.

Athey was renamed from the existing Academic Center in 2021; that date is not a new-build date. Source: [school commencement account](https://www.thehill.org/about-us/hill-traditions/2021-commencement), whose URL and body concern 2021 despite an inconsistent page title. The school dates Dining Hall renovation work to June 2018 and reopening to March 19, 2019, including basement/kitchen work and a scullery addition. Prefer current footage over pre-2019 outlines or photographs for that complex. Source: [Dining at The Hill](https://www.thehill.org/student-life/dining-at-the-hill). No individual roof appendage was assigned a room name by guesswork.

The next native review should compare the northeast Quad approach, east-return steps/bay, court looking east beneath the connector, and an overhead roof view. Roof fit, successful world generation and the earlier Chapel pass do not establish acceptance of this new area. Unseen rear facade counts and exact architectural materials remain evidence gaps.
