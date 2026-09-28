# Rolfe Dormitory construction study — 7 September 2026

The separate Rolfe study is in `runtime/campus-reconstruction/rolfe-v7-2x`.
It contains the standalone vanilla world and ZIP, exact block archive,
six camera positions, input profile, generator snapshot, and reproducible
structural validation. All six v7 native views have been inspected. The bounded
perimeter repair is suitable for integration; unobserved facades remain
explicit proposals rather than visually verified reconstructions.

Rolfe is Roofer parent `16001511600625C-c108a9b9b6`, research source index 25,
and school-map building 37. Foster is the other building in the paired drone
crop. Rolfe uses its own source outline and five-degree frame, separate
module and profile. It does not import Foster's module or geometry.

## Evidence and identity

The [school's current drone video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4)
at 238–240 seconds shows **Rolfe on the right** of the paired pitch-facing
view. The retained crop is
`runtime/research/campus-full-detail-20260905/foster-rolfe-pitch-238s-crop.png`.
It shows six windows per floor on each wing, four per floor in the centre,
two upper windows above separate entrance portals, triangular door
pediments, a small diamond attic vent, pale fascia and weathered gray roofs.
These are counted groups with estimated metric positions and dimensions,
not surveyed openings.

The [Scott Simons Architects 2013 master plan](https://www.slideshare.net/slideshow/hilll-school-master-plan-2013/58408750)
is an architect-authored primary document held in a third-party reprint.
Local page 10 explicitly identifies Foster and Rolfe as red brick, unlike
the darker masonry of the historic quadrangle. Local page 11 photographs
Rolfe's west gable in the foreground: three windows on each of the two upper
visible floors, a diamond vent and triangular entrance pediments. This is
historical evidence, not proof that every opening remains unchanged in 2026.
The building in the far background of that image is Foster.

The school [2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg)
and paired drone views establish the buildings' separate roofs and gap.
The source records are the exact parent entries in
`housing-facades.json`, `housing-major-roof-face-masks.json` and
`housing-entrance-ground-profiles.json` under the same research directory.

## Geometry and distinct levels

The build uses exactly 2 blocks per metre, with X = 2 × east metres,
Z = 2 × south metres and Y = 2 × (NAVD88 metres − 25).
The local origin is `(256.0009653336, 68.2182276987)` metres, U points
`(0.9961959313, -0.0871416463)`, and V points
`(0.0871416463, 0.9961959313)`. The source angle is −4.9991892479 degrees.
No world-axis rotation or global palette normalisation is applied.

Thirty independent front-ground samples, 1–18 metres outward, remain near
67.90–68.24 m NAVD88. The proposed entrance floor is 68.1 m and quantizes to
68.0 m. The rear grade reaches about 61.24 m, with side grades around 63.85
and 64.66 m. Rolfe therefore has two proposed basement levels at 62.1 and
65.1 m beneath the pitch entrance level, plus an upper plate at 71.0 m.
The exterior terrain retains the production DEM; only the building interior
is hollowed, and basement panes are clipped where exterior grade buries them.

The Roofer main ridge is 76.2983 m. The rear T hip uses source faces 5, 6
and 7, with approximately 71.0–73.4 m roof heights: it is materially lower
than the main ridge. Three rear end window levels fit below that roof.
The unsupported fourth-storey end row in the saved generic proposal is
omitted. Roof face 16, approximately 71.1 m, covers a **closed lower front
block**. Its four ground-floor windows are on V≈1.44 m; the four upper centre
windows are on the recessed wall at V≈4.9 m. That source block is not opened
as an invented Foster-like porch.

All thirteen faces listed by the source major-face audit retain their
original sampled heights. This list includes source face 19, a low east
grade/stair strip at 65.83–68.08 m: its geometry is retained, while the shared
shell correctly skips it below the 68.1 m entrance floor. Near-ground faces
0, 1, 4, 13 and 14 are excluded from architecture. All high faces, including
face 18, and the closed front roof 16 remain. There are no authored roof
patches in this Rolfe study.

## Individual material selection

The original 26.1.2 client resources and the 85-candidate construction
catalogue provide the comparison. The profile stores the catalogue hash,
exact source-image hashes, pixel rectangles, linear-light RGB/Lab statistics
and both raw and equal-lightness CIEDE2000 rankings. Image values are
lighting-dependent appearance samples, not calibrated material reflectance.

| Surface sample | Linear-light mean RGB | Selected construction | Rationale |
| --- | --- | --- | --- |
| Current east roof, crop pixels 1400,213–1480,232 | 147.96,143.17,145.44 | stone-brick full blocks, slabs and stairs | Weathered gray overlapping units; raw ΔE2000 7.852 and equal-lightness 2.366. Stone alone scores 7.264 raw but lacks the bond and useful pitched-roof construction family. |
| Current shadowed brick, pixels 1400,275–1510,281 | 70.41,65.96,81.28 | bricks | Blue-shadow contamination means raw colour ranking alone is misleading. The architect document explicitly identifies red brick. |
| Historical sunny west-gable brick, full-resolution page 11 pixels 1860,990–1871,1000 | 196.53,135.77,81.00 | bricks | Warm direct sunlight is also uncalibrated; brick bond and the primary description are more decisive than its nearest colour swatch. Bricks score 18.411 raw and 13.169 with equal lightness. |

The historical sample coordinates use the actual 2048×1582 page, not the
resized preview. Quartz slabs and stairs represent pale painted trim; this
does not claim literal quartz or stone trim substrate. Pale-oak doors retain
ordinary vanilla construction textures. White stained glass panes supply a
thin pale sash rim without opaque jamb panels or a projecting cage. Rolfe's
native colour and texture were independently inspected in all six v7 views;
this does not calibrate the different source lighting.

## Openings, closure and roof trim

The 34 current pitch-facing sash groups use Rolfe's own observed rhythm.
The six historically visible west-gable sashes are labelled separately.
Another 77 built sash groups on unobserved rear/end/basement faces remain
proposals, and two proposed groups are omitted at grade or the low roof.
No hidden window count is described as measured.

Each sash replaces actual exterior wall cells. White glass stays at the
outer wall, with quarter-metre heads and sills behind its upper and lower
edges. The short diagonal returns are restricted to the same authorised
aperture, never overwrite masonry and never enter the neighboring facade.
The original six pair-return panes were insufficient to prove frame closure.
V5 native and perimeter inspection exposed 72 pane-to-frame free ends. V7
adds 27 interior L-return panes, fills 35 concealed brick cap cells, and
completes 41 embedded quartz caps; all 696 existing v5 pane positions and
materials are preserved. No roof-role cells change. The final connected
glass audit has zero unbridged diagonal pairs and zero disconnected adjacent
pairs. Glass-component support is checked separately from wall closure.

The two entrance doors are actual two-block operable vanilla doors in painted
panels. Their triangular heads use inward-sloping stairs and a narrow crown
slab within the existing wall sheet. Solid timber backing closes partial
pediment cells. The rear door is a stated access interpretation. The small
diamond vents use the shared shaped opening with stair-cut trim; their
silhouettes require native inspection at this half-metre horizontal grid.

Painted fascia follows the main wing eaves, the closed front block and the
lower rear hip independently. Original source-shaped gable/verge cells
retain their physical roof tops. The first internal export exposed 82
quarter-metre reductions where a board shared a roof voxel. V2 preserves
those source surfaces, at the cost of quarter-metre steps in some painted
board tops. There are 175 eave-board cells, 160 source-shaped verge cells,
346 backing placements and 124 exposed substrate cells recoloured as brick.
These counts describe operations, not surveyed trim measurements. V3 adds the photographed pale verge along the recessed upper central gable: 39 source-edge columns retain the original roof shape and physical top. Its absence was apparent in the offline V2 full-pitch view because the closed lower front block hid this edge from a generic footprint-perimeter trim pass. V4 recolours the exposed substrate immediately below those gable/verge cells to brick, retaining continuous backing without a thick invented gray stripe under the pale trim. Roof tops and glass are unchanged.

## Validation and native cameras

`validate-study.py` reconstructs the exported world, the production grade,
the original measured shell and roof raster. It verifies:

- 723 panes in 123 supported components; zero panes outside the architectural
  roof envelope, open diagonal joints or disconnected adjacent joints.
- Zero empty cells among 5,961 checked wall cells. The check covers the full
  exterior down to the low basement and the original recessed/roof-step
  wall masks above the pitch floor; below-grade cells are excluded.
- All three operable doors have both halves and a supported threshold.
- All 2,432 columns belonging to audited major source faces retain identical
  plane heights. All 2,694 architectural roof columns outside the approximate
  chimney cluster have exactly the original quantized physical top, with
  zero minimum or maximum height error.
- No material-policy violations or clipped writes. The world has 771,936
  blocks, 77 chunks and two region files.

The production terrain SHA256 is
`96b3061a63c16b1dbc4fc0f0438bdb853b991cc62c068918d7d4a2b57665a485`;
the Roofer source SHA256 is
`b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`.
Source footprint distance to Foster is 24.698338 m. Rolfe's narrow 0.65 m
ownership buffer and specified front terrace retain a 24.049058 m gap to
Foster's source outline, with zero overlap. The 12 m study margin is not
assembly ownership.

The six native cameras in `camera-views.json` are:

| Camera | Reference or purpose |
| --- | --- |
| `rolfe-pitch-full` | Right building in current drone crop; roof colour, six-window wings, stepped centre and overall proportions. |
| `rolfe-triangular-portal-close` | Current triangular portal, flush door panel, head/crown backing and neighbouring sash. |
| `rolfe-west-gable-historical-match` | Historical page-11 gable with three windows per visible floor and small diamond vent. |
| `rolfe-rear-lower-hip-and-basements` | Measured rear roof-level change and steep grade; opening counts remain unverified. |
| `rolfe-east-return-grade` | Actual end-wall contour, glazing contact and exposed lower storeys. |
| `rolfe-roof-level-change` | Main roof intersections, lower rear hip and approximate central chimney cluster. |

All six v7 original-client native screenshots have been inspected against the
supplied reference images. Their hashes and per-view limitations are in
`native-review.json`. Glass/frame closure is accepted for this bounded repair.
The earlier original-texture offline diagnostics have also been inspected. They show the distinct closed front block, lower rear hip, deep rear grade and three-window west gable. The triangular heads remain coarse, the two small vents read as stepped narrow openings rather than clean diamonds, and the pane rim varies with the raster phase. These diagnostics are explicitly not native screenshots. The native views confirm these remaining visual approximations. The
remaining specific uncertainties are the photo-proportional aperture
dimensions, unobserved rear rows, current status of historically visible
openings, exact chimney/flue geometry, small vent shapes and quarter-metre
fascia/pediment quantization. Structural checks alone do not resolve those
visual or evidential limits.

## Expanded perimeter audit — 8 September 2026

The v7 exported archive has zero candidates with fewer than two horizontal
joins, zero vertical air/reversed-cap contacts across 1,446 checked edges,
and zero candidate diagonal pane-to-solid-jamb seams. All 51 partial
roof-under-cap flags are level fascia slabs with verified full masonry
backing inward. These are separately recorded checks, not a claim that
component support proves every possible three-dimensional sightline closed.
The exact v5-to-v7 delta preserves source roofs, all existing glass positions
and materials, operable doors, terrain and building axes.
