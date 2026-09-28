# Meigs House / Admission Office — individual build, 2026-09-07

The current **1925 Admission House** is parent `16001511600620C-fff89cfae9`, current school map number 1. This work does not use the original Meigs mansion destroyed in 1973.

The current study is [Meigs v4](../../runtime/campus-reconstruction/meigs-v4-2x/manifest.json), exported on 2026-09-08 with the original spruce roof family. Sol independently verified that family as an appearance proxy, retaining the unresolved real product and gray drone appearance; root added the shared roof support. The exported world has **586,854 blocks, zero clipped writes and zero material-role violations**. Final archive geometry, pane backing and occupied roof-shape checks pass. All six v4 native views were inspected against the supplied campaign reference. The [archive-bound native review](../../runtime/campus-reconstruction/meigs-v4-2x/native-review.json) accepts bounded integration of the corrected porch, backed cornice and connected sashes; no unseen elevation is claimed complete.

## Sources inspected independently

The [school campaign publication](https://resources.finalsite.net/images/v1706640886/thehillorg/jw0ysayvvi02ln5dsucr/FY24HTFlipCampaignInsertPRINTedits.pdf), printed page 15, identifies the 1925 Admission House, its renovation and wraparound porch. Its extracted [photograph](../../runtime/research/campus-full-detail-20260905/meigs-campaign-xref-63.jpeg) is the strongest close facade reference. I inspected the original image and page. It shows buff/tan stippled wall finish, pale painted posts and railings, brown overlapping roof units, two complete tall upper openings plus partial edge openings, partly obscured gabled dormers and at least two chimney portions. Trees prevent a complete frontage count. A single sash's internal light divisions cannot be counted reliably at this resolution.

The [official school drone video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) at 238 seconds contains a compatible house immediately west of Rolfe and south of the pitch. The county/register locations are Meigs XZ199.90,87.07m, Rolfe282.52,74.16m and Foster354.85,46.46m. That relative placement and the [official campus map](https://www.thehill.org/admission/visiting-campus/campus-map) support the aerial identification. Its broad roof has a larger central north-facing gabled dormer, a smaller dormer to its west, and a low porch continuing across the north front and around the western corner. This aerial supports configuration, not exact window counts or surveyed dimensions.

The [source audit](../../runtime/campus-reconstruction/meigs-v1-research-2x/primary-source-audit.md) records the independent primary-source search and rejected candidates. `school-admission-outside.png`, `school-admission-hero.jpg`, and `meigs-campaign-xref-61.jpeg` show other buildings and were excluded. No additional confidently identified ground facade was found. The 2026 aerial and drone were inspected without inventing detail hidden by trees.

**Orientation remains moderate-confidence inference.** The campaign crop is compatible with the western half of the north facade: image-left is east, so its large left dormer can correspond to the measured central dormer; the smaller western dormer lies to image-right. This is not calibrated photographic registration. South/east and most of the west face remain unresolved. No mirrored rows are authored there.

## Metric frame and roof provenance

All coordinates use 2 blocks/m: `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`. Origin is XZ190.0937983897,79.0076700044m; local U is approximately east, rotated −2.964 degrees. The exact measured footprint is **266.9911088209m²**, rasterised to 1,061 columns. Neither the footprint nor campus gaps are changed. The common floor/terrain pipeline uses `runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz`, native 0.5 m resolution and corrected physical surface datum.

The 21 original ordered Roofer faces, polygons, planes, part IDs, surface indices and fingerprints are copied into correction provenance. Source file SHA256 is `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`. Source roof RMSE is 1.141459 m. The register main ridge is 78.622719 m; the raw maximum 79.2146 m is not used as an eave height.

The [original face plan](../../runtime/campus-reconstruction/meigs-v1-research-2x/original-roof-plan.png) makes the following decisions reviewable:

- Main roof and large dormer faces 1/5 retain their source heights and topology. No generic replacement hip or gable is substituted for the measured main roof.
- Porch faces 6,7,19,20 are replaced by a continuous shallow cover around 70.95–71.55 m NAVD88. Photo continuity contradicts the near-ground ends of6/19; 20 supplies the approximately 71 m height control, and 7 is the contiguous narrow strip.
- Only the **north part of face2, V≤4.3m**, is added to that correction. The drone shows continuous cover across the frontage, contradicting its near-ground north strip. The eastern remainder of2 and all of3 remain unchanged and unresolved. They are not claimed as photographed occupied roofs.
- The smaller north dormer overlays 11 cells of face 16 where its authored gable rises above the original plane. It is supported by the separately visible school-drone dormer; exact dimensions are photo estimates. The larger measured dormer is preserved.
- Final correction masks change 193 porch cells and 11 smaller-dormer cells. The other 857 source-height columns are identical to the original sample, maximum delta 0 m. No authored column lies outside the measured footprint.

The roof polygon is an irregular overhang boundary, not a surveyed stucco wall line. Reusing it directly made metre-deep staggered sash. The photographed planar north wall is therefore explicitly interpreted at V3.8 m behind the source eaves. Its raster envelope includes a backing cell at rotated turns. This preserves the measured roof while making the wall and glazing continuous. It is not labelled measured.

## Individual construction

The profile authors four north upper openings: two complete campaign openings at estimated U5.7/9.15 m, plus separately labelled partial edge openings at U4.0/12.0 m. The large and smaller dormers each have an observed glazing group. Widths/heights are photo estimates, not surveys or exact sash counts.

Every aperture uses a single white-pane sheet in its outer wall cells. There is no duplicated front fence frame. Original white-pane borders approximate fine sash edges and horizontal meeting rails, based on the preceding Unit3/Foster native comparisons. The opening is bounded, and only necessary backing cells are removed. Shared authorised corner/frame helpers close raster turns. Contacting quartz half-slabs form sills and heads. Final validation checks horizontal free endpoints and actual head/sill contact as well as component support. Twelve concealed backing cells close the unused halves of thin caps against the adjacent wall courses. It does not equate a supported component with a sealed perimeter.

The porch uses quarter-metre slab/stair courses with local concealed overlaps at changes of level, nine narrow pale post shafts, three pale balustrade runs, an interpreted covered entry, and three quarter-metre entrance risers. The roof slab itself forms each shallow capital; an upper slab at a post becomes an inner-corner stair with the same physical top, so its lower body reaches the post and all neighbouring roof faces retain contact. The bottom railing cells are isolated balusters; only the upper cells carry connecting rails, avoiding four heavy horizontal rails from two stacked complete fences. Post spacing, stair location and doorway are interpretations of a partial photo and measured porch/grade, not measured counts.

Near the proposed west entrance the terrain is 67.18 m NAVD88, compared with 67.58 m near the north corner and 67.35 m on the north approach. The chosen 68.0 m floor and 67.25/67.5/67.75 m stair tops lead onto the porch without a high floating threshold. The lower doorway has an operable original pale-oak door; upper scaled panels use thin trapdoor skins.

Two warm masonry stack portions with restrained caps are represented. No exact source-facet correspondence is claimed. Their positions and heights remain estimates. Floors stay inside the body; the north stucco finish closes exposed floor-rim cells rather than exposing another exterior cladding colour.

## Actual materials and original vanilla proxies

The real wall is a tan stippled/stucco-like finish, with unknown substrate/product. The roof shows brown overlapping units; wood/asphalt/synthetic composition is unconfirmed. Painted trim substrate and chimney masonry are also unconfirmed. Minecraft material names below describe appearance and construction proxies only.

Original client resources come from `C:/Users/neil_/AppData/Roaming/.minecraft/versions/26.1.2/26.1.2.jar`. No custom texture, ore, sculk, invented sandstone identity or checkerboard mixture is used. The profile has its own `material_review`, excluding it from legacy generic recolouring.

| Role / candidate | Raw ΔE00 | Equal-L ΔE00 | Decision |
|---|---:|---:|---|
| Lit wall — white terracotta |5.337|4.892|Selected muted buff finish; fine texture underrepresents real stipple and retains a small pink bias.|
| Lit wall — diorite |12.778|12.025|Too neutral and strongly speckled.|
| Lit wall — white concrete |16.950|14.334|Too light/neutral; does not improve stucco colour.|
| Lit wall — light-gray terracotta |22.688|7.371|Too dark.|
| Roof — spruce planks |4.661|3.945|Selected appearance proxy, verified by Sol; fine horizontal courses and closest raw appearance.|
| Roof — mud bricks |5.570|1.968|Close colour; broad brick bond is less like narrow overlapping roof units.|
| Roof — exposed cut copper |13.092|4.046|Large square seams/green flecks poorly match the observed unit profile.|
| Roof — stone bricks |20.104|17.531|Too gray for the campaign photograph.|
| Roof — tuff bricks |19.445|19.342|Too green/gray for this roof.|
| Shaded post — quartz |12.605|1.319|Warm white trim; native shade supplies darkness.|
| Shaded post — pale oak planks |11.214|4.017|Narrow fence form selected for post/railing geometry, with visible timber-joint limitation.|

The [roof candidate sheet](../../runtime/campus-reconstruction/meigs-v1-research-2x/roof-candidates-original.png) and [expanded metrics](../../runtime/campus-reconstruction/meigs-v1-research-2x/roof-candidate-metrics.json) compare the unmodified original textures. Spruce texture SHA256 is `a1e4cd5b1eb20bc03e8d1f3fdae59034363c3b2dde7f505694e4323222e00e21`; white terracotta is `9feeb13f19514ea58a5b6e942df7a8595330e61173f8d0a13c83b78acd1bd62e`.

The deep porch wall has L* 33.21 while the lit wall has L* 72.02. The raw darkness is not used to paint the porch brown. Raw distances mix lighting and finish; equal-L distances isolate hue/chroma only, without pretending to recover albedo. The school drone roof appears gray in different light/date. Exposure, aging or a product change cannot be established, so the warm spruce choice is retained after native comparison as an appearance proxy with those limits.

## Validation and remaining work

The [final exported archive audit](../../runtime/campus-reconstruction/meigs-v4-2x/geometric-validation.json) passes:

- 586,854 nonair blocks; zero clipped writes and zero material-role violations.
- Exact metric frame and unchanged 1,061-column footprint; zero authored roof cells outside it.
- 857 unchanged source roof-height columns, maximum delta 0 m. Highest roof-surface corrections remain limited to the documented 193 porch and 11 small-dormer columns. A24-column lower cover return meets the interpreted north wall beneath the unchanged main roof.
- 63 panes in six components, zero unsupported components, zero unbridged diagonal pairs and zero disconnected adjacent pane pairs.
- All 63 panes checked for at least two horizontal joins and actual vertical contact; all 24 half-slab caps have full interior backing. The [shared perimeter audit](../../runtime/campus-reconstruction/meigs-v4-2x/pane-perimeter-validation.json) independently reports zero horizontal or vertical frame candidates.
- All nine porch shafts are continuous, meet their roof capitals physically and have full floor support.
- All376 adjacent roof-cover column pairs have positive-area contact in the original model shapes; neither facade nor post support is counted as roof contact.
- All15 thin exterior soffits retain full inset wall backing in the final archive.
- Profile, detail module and terrain hashes match the final manifest.

The world is [meigs-v4-2x/world](../../runtime/campus-reconstruction/meigs-v4-2x/world); the [camera file](../../runtime/campus-reconstruction/meigs-v4-2x/camera-views.json) contains six native views. Final archive SHA256 is `0317f8ade5f6dc3d313d5c7f9440718b6f6a6465b7047a18d4548414721a31a2`. The earlier geometry-only stone-shape diagnostic remains historical and is not the exported world.

The successful build command was:

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/build_hill_detailed_buildings.py --profile server-assets/hill-meigs-reference.json --output runtime/campus-reconstruction/meigs-v4-2x --terrain runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz
```

The native review compared the campaign roof hue, two-dormer silhouette, pale infill width, roof-edge trim, thin post support, sash meeting rails and entry panels. The six views and exact screenshot hashes are recorded in the archive-bound verdict. Spruce grain approximates small overlapping roof units without establishing the actual product. Pale post width 0.125 m is smaller than the approximate 0.2–0.3 m observed posts. The north orientation, window locations/widths, partial edge openings, west doorway and camera registration remain estimates. East/south and much of the west remain unresolved. The preserved low eastern source fragments are explicitly unresolved; they were not silently replaced or promoted to a photographed roof claim.

## Native porch and eave correction

All six v1 native views were compared with the supplied campaign image. The north porch read as a thin white ribbon and the west junction showed separated-looking rim pieces. The model had painted every boundary of the narrow porch mask as fascia, including the inner wall edge. It also treated V0 as the north eave for the whole building, although the measured footprint steps to V2.5m farther east. The v4 correction reserves quartz for the external footprint edge and keeps that fascia at one level. The shallow rise is fitted between the measured stepped exterior outline and the explicitly interpreted north/west wall, without enlarging the193-column correction mask.

A24-column inner cover return closes the small interval between irregular source roof overhangs and the interpreted north wall. This sits below the retained main roof and does not change its surveyed height controls. Quarter-course overlaps and stair shapes give the porch roof actual contact across its stepped courses. The [reusable audit](../../runtime/campus-reconstruction/meigs-v4-2x/validate-geometry.py) reads the original26.1.2 model elements and samples their exact half-block occupancy, checking all376 neighbouring roof column pairs independently of posts or facade backing. All pass.

The dormer/eave trim pass now excludes the lower porch and visits each main-roof column only once. The previous repeated pass descended into backing and produced an excessively thick cornice. The interpreted planar north wall now continues to the roof underside. Fifteen truly exterior soffit cells use thin upper slabs with full inset wall backing; three positions beside dormer openings retain full substrate because glass would not provide that backing. The final archive audit checks this after all apertures exist. V2 and v3 were withheld during these physical checks and were not native handoffs.

The final native comparison confirms the continuous brown roof strip, cream exterior fascia, joined corner capitals and reduced cornice. Root independently confirmed the improved campaign, entry and roof views. Exact roof product, exposure difference, porch dimensions and unseen elevations retain the qualifications above. The native-review record is tied to the final sample archive hash and all six screenshot hashes.

## Native comparison cameras

The six profile cameras convert directly to shared world-block coordinates at export. The first four are the requested facade/entry comparisons; the fifth checks the measured roof and two dormers, and the last records unresolved geometry without asserting a photo match.

| Name | Eye U,V,NAVD88m | Target U,V,NAVD88m | Purpose |
|---|---|---|---|
| `meigs-campaign-north-west` |2.5,−20,71.0|7.5,3.5,73.0|Campaign-western-half configuration and material comparison.|
| `meigs-north-full` |10,−27,72.0|9.5,5,73.0|Full north frontage; distinguish observed apertures from unresolved eastern field.|
| `meigs-northwest-porch` |−12,−9,71.0|4.8,4.4,70.8|Wrap porch, shafts, rails and north wall depth.|
| `meigs-entry-close` |−7,3.3,69.7|1.8,5.5,69.6|Thin entry, three risers, post/roof contact and balusters.|
| `meigs-roof-audit` |−6,−8,84|9,7.3,75|Large retained dormer, smaller authored dormer, chimney estimates and source roof joins.|
| `meigs-unseen-east-south` |30,28,73|11,10,72|Record unresolved eastern low fragments and unseen elevations.|
