# East Campus Faculty Village, Unit 3 — 7 September 2026

The current separate study is [east-faculty3-v8-2x](../../runtime/campus-reconstruction/east-faculty3-v8-2x/manifest.json). It has an individually interpreted south/front and west/return, an open wraparound porch, two overlapping gables, a pale external chimney, and a graded entrance. **All six v7 native views were inspected against the supplied Unit3 photograph. V8 closes two brow-induced wall slits and bevels seven heavy gable caps. All six v8 native views were inspected; root independently confirmed the slit closure and bevels. V8 is accepted for bounded integration with the material, mesh and unseen-face limitations below.** The east and north apertures remain unresolved; those elevations are not presented as visually complete.

The only authored shared-workspace sources are [the profile](../../server-assets/hill-east-faculty3-reference.json), [the detail module](../../scripts/hill_east_faculty3_details.py), and this report. Existing builders, source geometry, terrain, material policy and other building files were not edited by this agent. All studies are fresh outputs; v1–v7 and the preview studies are superseded by v8. V5 was withheld from native review after the stronger perimeter audit found gaps that component support had missed.

## Source inspection and the orientation correction

I independently inspected the original [numbered Unit 3 contractor photograph](https://wohlsenconstruction.com/wp-content/uploads/2016/03/the-hill-school-east-faculty-housing-East_Faculty_Housing_2.jpg), its local JPEG, the [separate duplex photograph](https://wohlsenconstruction.com/wp-content/uploads/2016/03/the-hill-school-east-faculty-housing-East_Faculty_Housing.jpg), and the [contractor project page](https://wohlsenconstruction.com/project/the-hill-school-east-faculty-housing/). The contractor distinguishes three single-family houses from four earlier duplexes and names Hord Coplan & Macht as architect. The duplex photo is material-family corroboration only; its dormer, hip roof and window arrangement are not copied onto Unit 3.

The Unit 3 photo shows the long return and external chimney on image-left, with the projecting gable on image-right. With the source frame’s +U pointing east, that handedness implies a **south-facing front viewed from the southwest**. The measured low pitched porch facets 0 and 3 are at the south end, V approximately 10–14.7 m, supporting that inference. The inherited research’s north-facing interpretation would mirror the visible arrangement. v1 made that mistake; the comparison caught it, and v2 corrects the layout without moving the measured footprint.

This is a geometric inference, not a calibrated photogrammetric registration. The visible “3” remains the direct identity evidence. Exact window sizes and camera pose are not surveyed.

The facade counts were also re-read from the photograph rather than blindly copied from the proposal. The visible upper windows near image X≈272 and 324 belong to the setback front face; X≈215 is the narrow near-corner return sash. The far return has a paired group around X≈120. Earlier prose conflated some of these planes.

## Measured geometry and roof interpretation

The parent is `160006438008-47b633ec2f`, with an exact measured footprint of **133.097468 m²**. Its local frame is retained, with origin `[454.6204382103378, -25.41819484233224]` m and the exact source U-vector angle. World construction uses X=2·east_m, Z=2·south_m and Y=2·(NAVD88_m−25). Native terrain is the existing corrected 0.5 m production surface.

The source roof is imperfect: the stored fit RMSE is 0.702831 m, faces 2 and 4 lie around ground level, and faces 1/5 describe one long ridge rather than the two separate front gables in the numbered photograph. The corrected roof therefore uses the measured footprint, the source **75.1702 m ridge datum**, and an approximately **30° dominant pitch** as controls for a coherent, explicitly authored roof topology. The smaller projecting gable is photo proportioned. It is not an unchanged measured roof.

| Source faces | Evidence and disposition |
|---|---|
| 1, 5 | Original main roof planes provide ridge and slope controls. Their single-ridge placement is replaced by the photographed overlapping gables. |
| 2, 4 | Large ground-height patches contradict the occupied body and open porch in the photo. Their covered areas are corrected, while the unused outer-west ground strip stays non-roof. |
| 0, 3 | Lower pitched facets occur at the south/front porch end. They support the corrected orientation; the final continuous porch surface also replaces their sampled cells. |

All six original face IDs, fingerprints, part IDs, surface indexes, metric polygons and height planes are recorded in `manifest.json → photo_interpreted_roof_corrections[0]`. The finished roof has **508 authored columns and zero columns outside the exact measured footprint**. Twenty-five original ground-level columns remain non-roof. No literal measured roof-face cells remain in the current study after the overlapping corrections; the source controls and provenance survive, not the old topology.

The small roof brow uses a fractional-metre eave projection in front of the photographed triple sash. It does not grow the occupied building plan. There is one photographed chimney, with estimated metric position and height. No dormer is visible on Unit 3, so none is invented.

## Materials: actual observation versus vanilla proxy

Only original vanilla textures are used. The source client JAR is `26.1.2.jar`, SHA-256 `b1b3158572666445eff01e82fad8c7de2e4953db6d354f311730d77a8359d0b0`. The comparison data are [photo-texture-comparison.json](../../runtime/research/campus-material-audit-20260905/photo-texture-comparison.json), based on separately labelled photo ROIs and original vanilla texture averages.

| Actual visible surface | Minecraft proxy | CIEDE2000 evidence and limitation |
|---|---|---|
| Warm tan horizontal lap-profile siding; substrate unknown | `white_terracotta` | Raw ΔE00 7.616 on lit return, 14.492 on darker front; equal-L values 6.594 and 7.288. Native v3 birch appeared yellow/olive. This muted warm finish improves the color compromise, while its smooth surface loses the observed narrow lap courses. It does not identify the actual siding as terracotta. |
| Irregular gray/brown stone-pattern plinth; natural versus manufactured veneer unknown | `tuff` | Raw 12.131, equal-L 7.956. Irregular texture is closer to the observed surface structure than regular brick courses. This does not identify the actual rock as tuff. |
| Cream painted posts, sash surrounds, fascia and corner boards | Quartz blocks/slabs/stairs | Raw 8.948, equal-L 5.675. The material is a visual proxy for a pale painted finish. White horizontal window trim uses half-height slabs, not deep projecting borders. |
| Gray-brown overlapping shingle units; roofing product unknown | Stone brick full/slab/stairs | Raw ΔE00 8.858, equal-L 5.921. Native v2 showed the numerically closer tuff texture reading dark green. Original stone-brick mean Lab `[51.9132,0.4788,-0.3401]` is more neutral than tuff `[43.9885,-2.8315,3.363]`; v3 confirmed a neutral gray appearance. Stone brick is retained in v6; the photo’s warm brown weathering is still imperfectly reproduced. The porch cap contains only quarter-metre slabs. |
| Tan/beige small-shingle infill in the two gable tips | `oak_planks` | New independently inspected ROI `[416,43,441,60]` in the original Unit 3 photo has mean RGB `[135.18,117.26,96.38]` under shadow. Oak raw ΔE00 is 11.458, versus birch 21.474 and pale oak 30.941. Oak retains a timber-profile surface; fine fishscale curvature remains unresolved. |

No ore, sculk, sandstone substitute, resource pack, random moss or speculative vines are used. The current windows use a **single white-stained-pane sheet in the outer wall opening**, with no duplicate front fence posts. The original pale pane perimeter adds horizontal sash cues; its repeated 0.5 m texture edges remain a simplification of the source’s meeting rails. Three specifically authorised diagonal returns and four frame returns close the rotated-wall joins. Quartz slab heads and sills physically contact every vertical perimeter edge; one embedded transom cap and one facade contact complete the remaining boundaries. The porch posts remain minimum full-grid square columns; at 0.5 m, they are wider than the estimated 0.25 m photographed posts.

The final siding choice explicitly compares five original construction candidates. Each pair below is **raw / equal-lightness ΔE00**; the complete source statistics and texture hashes are in the profile.

| Candidate | Lit return ROI | Darker front ROI | Decision |
|---|---:|---:|---|
| Birch planks | 9.582 / 9.377 | 14.785 / 10.201 | Lap texture useful, but native v3 has a strong yellow/olive cast. |
| Stripped birch log | 9.656 / 9.429 | 15.069 / 10.497 | Retains the yellow cast and loses the fine horizontal plank courses. |
| Oak planks | 13.087 / 8.196 | 10.092 / 9.984 | Browner, but darker and still too chromatic for the main siding; retained only in the small shaded gable tips. |
| Pale oak planks | 16.573 / 10.433 | 23.196 / 8.783 | Too light and pink-gray for the broad wall field. |
| White terracotta | 7.616 / 6.594 | 14.492 / 7.288 | Selected color compromise; lack of lap grain is an explicit limitation. |

The photo samples have L* 69.8256 and 59.2597. Their difference reflects illumination, not evidence of two siding paints. Raw ΔE includes that exposure difference; equal-L comparison isolates hue/chroma error and does **not** recover intrinsic reflectance. Birch’s mean Lab `[72.4085,-1.8939,30.2297]` carries substantially more yellow and some green relative to the source return `[69.8256,3.7424,15.7417]`. White terracotta `[74.8891,8.8111,12.7724]` reduces that bias, with a remaining warm/pink tendency. No checkerboard mixtures or custom texture corrections are used.

For the roof, stone brick’s equal-L ΔE00 5.921 is lower than tuff brick’s 6.338, while native v2 showed the latter’s green cast. Deepslate bricks have raw error 13.019 and are too dark; exposed cut copper has raw 14.218 / equal-L 10.915 and adds an unsupported metal appearance. The final roof therefore retains coherent stone-brick slab/stair forms. Color metrics do not establish the real roofing product.

## Comparison and validation

The local original-texture [southwest diagnostic](../../runtime/campus-reconstruction/east-faculty3-v6-2x/east3-photo-southwest-offline.png) and [entrance diagnostic](../../runtime/campus-reconstruction/east-faculty3-v6-2x/east3-entrance-close-offline.png) are offline renders, not native screenshots. They are intended to catch silhouette, handedness and facade mistakes. Deep underground terrain was omitted from the diagnostic mesh to reduce rendering cost; the full Anvil world and block archive retain it.

The source-photo comparison corrected the mirrored front in v1. Native v2 then exposed dark unframed windows, a thick green porch-roof band, pale pink gable infill, a broad chimney cap and a projecting door cube. Subsequent native comparisons established muted white-terracotta siding, neutral stone-brick roofing, tan oak gable tips, a thin open porch cap and a thin operable entry door. Native v4 still showed an excessive glass setback and two exposed yellow strips below the front windows.

V6 places the white panes directly in the outer wall sheet. The stronger check found that the generic 1.35 m reveal cut had also cleared part of the perpendicular wall beside the entry. The residential module now cuts only the bounded 0.65 m wall zone, preserving that adjacent wall. Authorised corner panes close diagonal joins. The fixed bay brow had overwritten four contacting window heads with upper-half roof slabs; lower-half quartz heads now meet the pane tops. One embedded transom/sidelight cap corner is solid so its short return is continuous.

The yellow strips were **nine exposed cells in the upper floor-role birch plate**, not a second siding color or the gable fishscale infill. Those front rim cells now carry the established facade finish. Interior floor material and the nine oak gable cells remain distinct. The photo-estimated entry ensemble moves 0.20 m into the front wall to avoid replacing a convex raster corner with a free pane. The partially visible ground pair moves 0.15 m right and is fitted to 1.0 m width to retain a real jamb beside the door. The broad ground triple uses three full pane rows (1.5 m) below its fixed brow instead of intersecting that roof cap. These are explicit grid fits, not surveyed dimensions.

The custom roof fascia also had the shared backing defect: replacing a full substrate block with a top slab could leave a quarter-metre daylight slit. Its 61 edge columns now retain solid facade backing below pale trim that matches the existing roof-top slab/stair shape. Main roof heights and the measured footprint remain unchanged.

Remaining likeness limits are the lost fine lap texture, warm/pink facade bias, 0.5 m porch-post thickness, native pane-center placement, repeated pane-grid borders, simplified fishscale texture, incomplete brown roof weathering and photo-derived roof relief. The two unphotographed elevations cannot be claimed to match photographs.

[Geometric validation](../../runtime/campus-reconstruction/east-faculty3-v6-2x/geometric-validation.json) reports:

- 376,851 non-air blocks; zero clipped writes and zero role/material violations.
- 103 pane blocks in 11 connected components; zero unsupported components.
- Every pane has at least two continuous horizontal joins, with zero free endpoints.
- All 66 vertical perimeter contacts meet solid material or the contacting half of a slab; zero vertical gaps.
- Shared `pane_joint_report`: zero unbridged diagonal pairs and zero disconnected adjacent pairs.
- Exact frame-origin error 0 m and correct 2 blocks/m / −25 m datum conversion.
- 508 roof columns inside the measured plan; zero authored roof-mask columns outside it.
- Sampled roof peak 75.162790 m, consistent with the 75.1702 m source ridge before quantization.
- Original source provenance retained for all six facets; final roof topology explicitly remains authored.
- The porch roof remains a single slab cap; four lower bay-head caps close physical contact without adding general roof backing.
- Nine exposed floor-rim cells match the facade; no duplicate front fence posts remain.
- All 61 main roof-edge substrate columns are solid beneath matching trim shapes.
- Terrain, paving and all six native cameras are unchanged from v4. Source profile and detail-module hashes match the export.

These checks establish continuous pane joints and contacting perimeter blocks. The final native comparison is still needed to judge their visual appearance.

Rebuild into a fresh versioned directory:

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/build_hill_detailed_buildings.py --profile server-assets/hill-east-faculty3-reference.json --output runtime/campus-reconstruction/east-faculty3-v9-2x --terrain runtime/campus-reconstruction/campus-full-detail-preparation/terrain.npz
```

## V7 concealed head/sill backing correction

A stronger physical-wall check found a limit in v6: the heads and sills contacted the panes, but the unused half of a slab could still form a quarter-metre daylight slot against the next full masonry course. Most caps had air immediately inward. Component support and diagonal-joint checks do not detect this condition.

V7 adds **51 concealed facade backing cells** and completes **nine embedded partial cap cells**. It preserves every pane position and material, all roof-role cells/states, terrain, paving, roof correction geometry, footprint and cameras. One pane gains an east connection to its completed backing support. There is no additional glass setback, front frame, palette experiment or roof change.

The [v7 validation](../../runtime/campus-reconstruction/east-faculty3-v7-2x/geometric-validation.json) reports 376,902 non-air blocks, 61 changed cells from v6 (51 facade, nine trim and one pane connection state), zero clipped writes, and zero material violations. All 103 pane positions/materials remain identical. The 11 pane components are supported; there are zero unbridged diagonal pairs or disconnected adjacent pairs. All 103 pane perimeters pass horizontal/vertical contact checks, and all 62 remaining half-slab caps are checked for solid concealed backing. Existing full cap blocks are already closed. Profile/module hashes match the export.

Native v7 southwest/front/close comparison showed connected glazing and exposed a separate bay-brow defect, corrected below.

## V8 native bay-brow and gable correction

The six v7 native views were inspected against the numbered contractor photograph. The entrance view revealed a daylight slit at the projecting bay's floor/roof edge. The archive identifies two exact cells, X/Y/Z `[917,88,-22]` and `[923,88,-21]`, where the decorative brow had replaced full occupied wall cells with upper slabs. Those slabs opened the lower halves of the wall. V8 limits the brow to the exterior overhang and preserves the existing occupied wall and pane heads; both cells are now full matching siding.

Seven full quartz caps on the two observed gable rakes now use uphill bottom stairs. Each retains its previous maximum height and full siding substrate, reducing the square white teeth without adding roof relief or exposing a backing slit. Only these nine cells differ from v7. All 103 pane positions, materials and connection states remain identical. The authored roof surfaces/provenance, original footprint, terrain and cameras are unchanged; the two removed brow roof-role cells are the documented wall repairs.

The [v8 archive audit](../../runtime/campus-reconstruction/east-faculty3-v8-2x/geometric-validation.json) records 376,902 blocks, zero clipping/material violations, 103 panes in 11 supported components, 62 backed half-slab caps and matching input hashes. The [new shared perimeter audit](../../runtime/campus-reconstruction/east-faculty3-v8-2x/pane-perimeter-validation.json) reports zero horizontal-frame candidates, zero vertical air/reversed-slab candidates and zero diagonal/adjacent pane defects.

The upper sashes still look recessed from the southwest. Their pane sheets are already in the outer wall cells; the original vanilla pane mesh sits at the cell centre, **0.25 m behind a full-block face at 2 blocks/m**. There is no additional full-cell setback. The smooth proxy finish accentuates the vertical wall strips, and the photographed near-flush painted sash is not fully reproduced. Palette review remains with Sol; v8 makes no new material choice. Native entrance/SW/front review confirms that the slit is gone and the bevel is better. The hash-bound [native acceptance](../../runtime/campus-reconstruction/east-faculty3-v8-2x/native-review.json) retains the explicit window-depth, cladding, roof-grain and unseen-face limitations. Sol’s final material packet retains this palette because no audited vanilla alternative improves the combined colour/grain compromise.

## Native camera handoff

The ready [camera-views.json](../../runtime/campus-reconstruction/east-faculty3-v8-2x/camera-views.json) contains converted world-block coordinates. The first four are the requested native comparison views; two additional views audit roof and unresolved elevations.

| View | Eye U,V,NAVD88 m | Target U,V,NAVD88 m | Purpose |
|---|---|---|---|
| `east3-photo-southwest` | −10, 27.5, 70.7 | 4.9, 10.2, 70.6 | Match contractor photo handedness, massing, roof, porch and chimney. |
| `east3-south-two-gables` | 5, 32, 70.3 | 5.2, 12.6, 70.7 | Compare two distinct front gables and their individual window counts. |
| `east3-west-porch-chimney` | −15, 7.2, 70.2 | 2.2, 7.2, 70.4 | Compare return openings, wrap porch and chimney. |
| `east3-entrance-close` | −2.5, 20.4, 68.7 | 3.5, 12.25, 68.6 | Check glass-plane support, door/sidelight, porch openness and entrance grade. |
| `east3-roof-audit` | −9, 25.5, 80 | 5.2, 8.2, 72.5 | Inspect gable intersection, thin porch cap and main-roof backing. |
| `east3-unseen-east-north-audit` | 21, −13, 72 | 6, 5.5, 70.6 | Record unresolved elevations without claiming a photograph match. |
