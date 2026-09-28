# Athey Academic Center: identity, base-map split and exterior references

Researched 2026-09-05 by the `alumni_sources` research agent. This is a source inventory for the campus base map and first detailed campus building. It is not an in-game likeness approval. The official map, current aerial, selected current video frames, campaign page and local CityJSON were visually or directly inspected. No code, world or browser session was changed.

## Verified identity and base-map location

**Athey Academic Center is number 3 on the current school map; Dining Hall is number 4.** Athey forms the south side of the main Quadrangle, opposite Hunt Upper School, with Ryan Library to the east and the Chapel to the west. A second, smaller court lies south of Athey, between it and the Dining Hall. The school owns the [current labeled PDF](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), available through the working [Our Campus page](https://www.thehill.org/about/our-campus) and its [download link](https://www.thehill.org/fs/resource-manager/view/6348615e-173c-47b6-8837-2096d4771d99). The older `/admission/visiting-campus/campus-map` page returned 404 after the September 2026 site redesign, although search still indexes its text.

The current county API was queried directly on the research date. It returns the following **aggregate**, not a separate Athey-only polygon:

| Identifier | Verified value |
| --- | --- |
| County layer | [Montgomery County Building Outlines, layer 6](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6) |
| `OBJECTID` | `406016` |
| `STRUCTUREID` | `16001511600613C` |
| `PARID` | `160015116006` |
| `IMPRNAME` | `ACADEMIC CENTER #25` — county numbering, distinct from school map number 3 |
| Roofer parent | `16001511600613C-92645e8573` |
| Roofer children | `16001511600613C-92645e8573-0` and `16001511600613C-92645e8573-1` |
| County WGS84 aggregate bounding box | Longitude −75.635059476 to −75.634050965; latitude 40.244114643 to 40.244858331 |

The exact returned geometry and attributes are cached in [athey-county-wgs84-source.geojson](../../runtime/research/campus-priority-20260905/athey-county-wgs84-source.geojson). Reproduce the read-only request against the layer's `/query` endpoint using `where=STRUCTUREID='16001511600613C'`, `outFields=*`, `outSR=4326`, `returnGeometry=true`, `f=geojson`.

**The county geometry is one Polygon with one 49-coordinate ring and no courtyard hole.** Consequently, filling this polygon as solid construction would cover an open court seen in the school's current imagery. Keep the county ring as source geometry; draw separately identified Athey, Dining Hall, connecting roofs and the court as interpretation layers. Google Maps ring comparison belongs in the base-map review and has not been performed by this research agent.

The [existing roof-plan study](hill-academic-quad-reference-20260904.md) aligned the current map with the measured roof plan. In the project frame, origin `40.24516,-75.63516`, X east and Z south, before conversion to two blocks per metre, it estimates:

| Interpreted component | Approximate location; not a surveyed wall polygon |
| --- | --- |
| Athey main bar | X20–94, Z34–72; long axis approximately 18.2° south of east |
| Dining Hall | X10–65, Z78–116; includes irregular lower appendages |
| Open court | Corners approximately `(36,60), (65,70), (60,87), (29,78)` |

Use these to locate the parts, then snap the actual split to roof faces and visible exterior walls. They are not final dimensions.

## Direct school-owned exterior references

| Reference | What it resolves |
| --- | --- |
| [2026 aerial, original 1500 × 843 JPEG](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg), [local copy](../../runtime/research/campus-priority-20260905/campus-2026-aerial-original.jpg) | Best newly verified overview: Athey's long steep roof, cross-gables, courtyard-facing brick facade, two covered links, the open paved court and the broad dark Dining Hall roof are visible together. This is an oblique image, not an orthophoto. |
| [Official 2026 drone fly-through MP4](https://resources.finalsite.net/videos/t_video_mp4_480/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4), about 105–107 s | Quad-facing facade and approach. Local [105 s frame](../../runtime/research/hill-reference-20260904/chapel-drone-11.jpg): larger central projecting gable with oculus, smaller outer gables, pale-framed rectangular groups and round-arched lower flank openings. Shadows limit exact counts. |
| Same MP4, about 97 s; [local frame](../../runtime/research/hill-reference-20260904/chapel-drone-03.jpg) | East return: brick wall, broad pale surrounds, multi-pane glazing, low projecting bay with notched parapet, dark door, pink/brown stone-looking foundation, steps and black rails. |
| Same MP4, about 90 s; [local frame](../../runtime/research/hill-reference-20260904/drone-08.jpg) | Court-facing Athey and Dining Hall, open space below the east connector's gray standing-seam-looking roof, brick piers and red paving with pale crossing strips. |
| Same MP4, about 138–139 s; [138 s frame](../../runtime/research/hill-reference-20260904/chapel-drone-44.jpg) | Near-overhead Athey roof, gable intersections, north facade alignment and narrow court-link roofs. This is the strongest orientation check against the main Quad. |

The images establish red/brown **brick walls**, pale dimensional courses and surrounds, gray main roofing, recessed glazing and a stone-looking lower base. The aerial shows three conspicuous courtyard-facing gables, with the central one larger, and small triangular roof features between them. Resolve their exact count and function from closer imagery before making repeated dormers. Neither the exact trim stone nor the main roof product has been verified. A gray surface in a photograph is not sufficient evidence of a particular roofing material. [Current aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg)

The school's campaign account confirms **four floors** and renovation of the existing Academic Center, including its renaming. It does not provide exterior elevations or establish a new exterior addition. Four occupied floors should not be translated automatically into four equally exposed rows on sloping terrain. [Campaign report, printed page 14](https://resources.finalsite.net/images/v1706640886/thehillorg/jw0ysayvvi02ln5dsucr/FY24HTFlipCampaignInsertPRINTedits.pdf), [inspected local page](../../runtime/research/hill-reference-20260904/athey-campaign-2024-page-14.png)

## Measured geometry versus visual interpretation

The parent identity and following values were re-read directly from [hill-campus-roofer.city.json](../../runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json). Its horizontal reference system is EPSG:6347. They describe the reconstructed aggregate and must not be assigned indiscriminately to every subpart.

| Direct CityJSON value | Interpretation limit |
| --- | --- |
| `rf_h_ground = 65.879997` | Aggregate base reference, not grade at all facades |
| `rf_h_roof_ridge = 89.148682` | NAVD88 ridge attribute; geometry maximum is 89.153412 |
| `rf_roof_planes = 158` | Includes lower connected parts |
| `rf_rmse_lod22 = 0.653044` | LiDAR fit statistic, not facade accuracy |
| `STORIES = 0`, `Height = 56`, `YRBLT = 1998` | Preserve as county attributes. Zero is not an observed storey count; do not interpret 56 as metres. |

The earlier [semantic roof-face analysis](hill-academic-quad-reference-20260904.md) measured Athey's dominant opposed planes at approximately 44.9°, eave-side minima 81.802/82.452 m and ridge 89.1534 m NAVD88. Its Dining Hall planes are much lower and predominantly flat. These component calculations were not recomputed in this source-inventory task.

## First detailing and review sequence

These are implementation recommendations, not surveyed facts:

1. Approve the campus positions and Athey/Dining/court split against the current map, measured roof plan and the aerial before changing facade details.
2. Preserve Athey's measured steep roof and cross-gables. Add the pale coping and recessed oculi as separate details; do not replace the entire county aggregate with one gabled box.
3. Establish the corner bay, grade changes and pale bands before repeating windows. Use separate north, south and end profiles; the available imagery does not justify assuming all elevations share one grid.
4. Use brick-family blocks for the walls and restrained pale stone-family trim. Keep roof, structural brick, dressed trim, glass and foundation in different semantic palettes. The user's ban on exposed ores and sculk applies throughout.
5. Compare native Minecraft views at the Quad approach, east steps, south court and overhead roof angle against their respective source frames. Adjust silhouette, opening rhythm and terrain exposure before adding decorative variation.

Exact facade bay totals, pane counts, trim stone, roof product, unseen west-end details and the complete ground-level west connector enclosure remain unresolved. The source archive supports building the base and an evidence-led first facade pass; it does not support claiming that Athey already matches Street View or that the whole campus has passed visual review.
