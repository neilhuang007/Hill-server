# Hill campus exterior reference priorities

Researched 2026-09-05 by the `alumni_sources` research agent. The user's current sequence is to establish the campus base map, cross-check building rings, then detail **Athey first**. These seven facade priorities are a reconstruction recommendation, not a verified advertisement shot list. School-owned imagery establishes current campus relationships; architect and contractor photographs supply useful closer exterior evidence. Their upload directories do not establish their capture dates.

The current [2026 campus map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf), [school aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) and [2026 fly-through](https://resources.finalsite.net/videos/t_video_mp4_480/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) are the broad current references. The working landing page is now [Our Campus](https://www.thehill.org/about/our-campus); older visiting-campus URLs can return 404 after the September 2026 redesign.

## Identity crosswalk

The [building identity JSON](../../server-assets/hill-campus-building-identities.json) records the more extensive 27-name core-campus crosswalk, evidence, source centroids and unresolved matches. Its method compares the current labeled map and the [July 2021 facilities plan](https://resources.finalsite.net/images/v1633097238/thehillorg/ewtimjvxagjkgblsqf5q/fy22campusmapgraphic.pdf) with county outlines over the georeferenced cached orthophoto. It does not infer names solely from county assessment text. `STRUCTUREID` is repeated for many different shapes; use the unique local Roofer parent as the geometry join key.

| Priority | Current school map | Verified county / Roofer relationship |
| --- | --- | --- |
| Athey Academic Center | 3 | `16001511600613C` / `16001511600613C-92645e8573`; shared with Dining Hall and links |
| Dining Hall | 4 | Same parent; a separate named southern part with lower roof levels |
| John P. Ryan Library | 2 | `160015116006` / `160015116006-567a5eddd9` |
| Hunt Upper School Dormitory | 29 | `160015116006` / `160015116006-d4f3b48752` |
| Shirley Quadrivium Center | 50 | `16001511600615C` / `16001511600615C-ee30229dd5`; current joined academic frontage |
| Center For The Arts | 9 | `160031040003` / `160031040003-894f07a81a` |
| Lehrman '56 Pavilion | 25 | Exact county/Roofer correspondence not verified in this bounded inventory |

Do not substitute the eastern footprint `1600151160061C-551ba4628e`, despite its county `UPPER SCHOOL BLDG #24` label, for Hunt. The current school map and Quad geometry identify a different building. The [source identity JSON](../../server-assets/hill-campus-building-identities.json) records this rejected match explicitly.

## 1. Athey Academic Center

Use the [focused Athey evidence file](hill-athey-academic-center-reference-20260905.md) for exact source queries, timestamps, roof data and limits. It distinguishes the long steep-roof academic bar from the low Dining Hall, court and connectors. The school [aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) shows red/brown brick, pale trim, a gray pitched roof, projecting cross-gables and the open smaller court. The [drone video](https://resources.finalsite.net/videos/t_video_mp4_480/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4), approximately 97 and 105–107 seconds, resolves the east bay/steps and Quad-facing window composition. Exact pane/bay counts, trim stone and roofing product remain unknown.

Athey needs its own brick palette, pale dimensional bands, distinct end-bay profile and recessed oculi. Those are modeling recommendations. Measured LiDAR roof accuracy does not establish facade likeness.

## 2. Dining Hall

The same [aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) establishes the southern low mass with predominantly flat/terraced dark roof levels. At about 90 seconds, the [school fly-through](https://resources.finalsite.net/videos/t_video_mp4_480/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) shows the court edge's brick, pale-framed openings and shallow notched parapet, along with an open connector on brick piers. [Inspected local court frame](../../runtime/research/hill-reference-20260904/drone-08.jpg)

Keep the court open to the sky and separate its paving, links and Dining Hall walls from Athey. Room assignments of rear appendages and the full west connector's lower enclosure remain unresolved. Copying Athey's tall gable/window module around the county aggregate would erase a visible difference between the buildings.

## 3. John P. Ryan Library

The contractor identifies the project as an addition and renovation of the historic library and specifies imported German Dietenhan stone for the addition exterior. This does not establish the material of every historic wall. [Wohlsen project](https://wohlsenconstruction.com/project/the-hill-school-john-p-ryan-library/)

The [wide Quad exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_4.jpg) visibly distinguishes rough gray/brown coursed stone, warm pale/pink trim, tall pointed upper windows, a ground arcade, end gables and a gray pitched roof behind a low notched parapet. A [closer view](https://wohlsenconstruction.com/wp-content/uploads/2016/03/hill-school-library_1.jpg) shows historic masonry adjoining a lighter, smoother low addition with large rectangular glazing. Preserve these different portions and the arcade depth. Exact roof product and unseen facade counts are unknown.

Local inspected images: [wide](../../runtime/research/campus-priority-20260905/ryan-4.jpg), [addition](../../runtime/research/campus-priority-20260905/ryan-1.jpg).

## 4. Hunt Upper School Dormitory

The contractor's [project page](https://wohlsenconstruction.com/project/the-hill-school-upper-school-dormitory-renovation/) identifies the renovated Upper School. Its [front exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/k-12-schools-construction-the-hill-school-upper-school-dormitory-renovation-1.jpg) visibly shows red/brown brick upper walls, a heavy brown masonry ground arcade with round arches, projecting central bay, red/orange roof surfaces, dormers and green patinated-looking cornice/ornament. The central dormer crest and tall finial are strong silhouette markers. The photograph does not establish the exact tile or metal product.

The [current school aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) confirms the long red-roof mass on the opposite side of the Quad from Athey. Use the measured roof shell to resolve its tiered roof rather than simplifying it from the oblique photograph. [Inspected local front](../../runtime/research/campus-priority-20260905/hunt.jpg)

## 5. Shirley Quadrivium Center

The architect describes a completed 2020 project joining two 1930s brick buildings with new construction. Its construction account documents salvaged limestone surrounds and matching new brick to existing material. [SMP project](https://smparchitects.com/project/the-shirley-quadrivium/), [SMP construction account](https://smparchitects.com/construction-progress-the-shirley-quadrivium-center-at-the-hill-school/)

Three inspected architect photographs are complementary: [new glass link](https://smparchitects.com/wp-content/uploads/2025/04/Front-exteior-new-link-side-view_credit-Halkin-Mason-1280x960.jpg), [historic entrance](https://smparchitects.com/wp-content/uploads/2025/04/Front-exterior-historic-section_credit-Halkin-Mason-1280x960.jpg), and [end elevation](https://smparchitects.com/wp-content/uploads/2025/04/Front-exterior-from-end_credit-Halkin-Mason-1280x960.jpg). They show steep gray/green slate-looking roofs, brick chimneys, gabled roof projections, pale surrounds, curved bays and ornate pointed historic portals beside a tall glazed gable with a metal-looking roof. Keep the new central link geometrically and materially distinct. Exact historic roofing product is not verified by those visual observations.

Local copies are `quadrivium-new-link.jpg`, `quadrivium-historic.jpg` and `quadrivium-end.jpg` in `runtime/research/hill-reference-20260904/`.

## 6. Center For The Arts (CFTA)

The contractor documents a theatre fly tower and a two-storey glazed lobby. [Wohlsen project](https://wohlsenconstruction.com/project/the-hill-school-performing-arts-center/)

The [pond-facing exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/k-12-schools-construction-the-hill-school-performing-arts-center-1.jpg) shows rectangular flat/parapet-roof masses, a taller pink/tan fly volume, pale smooth square-panel surfaces with narrow dark horizontal stripes, large grid glazing, a red/pink lower band and a broad stair/terrace beside the Dell. The [current school aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) independently confirms the distinctive roof/pond relationship. Exact panel material is unknown; do not call it limestone or cast concrete without another source. [Inspected local exterior](../../runtime/research/campus-priority-20260905/cfta.jpg)

## 7. Lehrman '56 Pavilion

The contractor specifies split-face block and James Hardie Trim for the exterior, together with a circular atrium and second-floor observation deck. [Wohlsen project](https://wohlsenconstruction.com/project/the-hill-school-lehrman-pavilion/)

The [front exterior](https://wohlsenconstruction.com/wp-content/uploads/2016/03/k-12-schools-construction-the-hill-school-lehrman-pavilion-1.jpg) shows a faceted round central pavilion, dark hipped roof, pale posts and rails, glazed bays, a covered upper deck and lower roofed seating edges. Those traits make it a useful athletics-view detail after the Quad buildings. Exact roof product and current rear/service elevations remain unresolved. [Inspected local image](../../runtime/research/campus-priority-20260905/lehrman-1.jpg)

## Use in the reconstruction

Keep each building's structural material family separate before any color matching: Athey/Hunt/Quadrivium brick; library rough masonry and its distinct addition; CFTA smooth panels and glazing; pavilion split-face masonry, trim, rails and glazing. This is a proposed semantic palette strategy based on the references, not a source specification of Minecraft blocks. The user's exposed-ore/sculk ban applies to every palette.

For each finished exterior, record matched camera position, reference date, visible landmarks, differences corrected and remaining occlusions. Native Minecraft views must be compared with the applicable facade reference; a top-down footprint match, successful export or visually plausible render is not evidence that every facade matches Street View. Public visibility of a reference image does not itself grant republication rights; the links here are source attribution, not a blanket asset license.
