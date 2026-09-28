# Hill School Sol reference handoffs — 2026-09-08

This log contains build decisions prepared from first-party school sources, the saved public Street View capture, measured county/Roofer geometry, original vanilla 26.1.2 textures, and the existing ROI audit. Photo colour is treated as appearance under unknown illumination and white balance, not material identification.

## Meigs House — verified for export

Packet: [`runtime/research/sol-reference-20260908/meigs-verification.json`](../../runtime/research/sol-reference-20260908/meigs-verification.json)

Approve the singular spruce roof family (`spruce_planks`, `spruce_slab`, `spruce_stairs`) and retain the current white-terracotta wall choice. Spruce is the best visual match to the close campaign photograph's warm brown overlapping units; it does not identify real wood roofing. The gray appearance in the low-resolution school drone remains a native-comparison caveat, not a reason to block export.

The campaign western-half/north-façade registration remains moderate-confidence. Keep the measured central dormer and authored smaller western dormer. Keep the porch correction on faces 6, 7, 19 and 20 plus only the north strip of face 2 at `V<=4.3 m`; the wraparound-porch text and drone continuity support that bounded correction. Do not broaden it into the unresolved eastern remainder of face 2 or face 3.

## Hillhouse & Moore Business Office — ready

Packet: [`runtime/research/sol-reference-20260908/hillhouse-moore-business-office.json`](../../runtime/research/sol-reference-20260908/hillhouse-moore-business-office.json)

The observed west façade is rough warm gray render with white sash/bay/rail trim and very small dark green cap profiles. A blanket brick envelope conflicts with the source photograph. Use the exact source footprint and all measured roof faces; the photographed northern low appendage supports retaining low face 16, and there is no evidence for a roof deletion or reorientation. The selected wall proxy is one consistent polished-andesite field because it best preserves the neutral coarse appearance across both lit and shaded ROIs. This is a visual substitute, not an andesite material claim. Major roofs use provisional deepslate tiles because the covering is clipped and unresolved.

Observed west-side signature: three upper single sashes on the broad plane; one lower single plus one triple group; a two-level polygonal bay with one tall sash on each visible face; and a white-railed terrace on the north low extension. Other elevations, doors, thresholds, exact aperture coordinates, roof product and chimney assignment remain provisional.

## The Sherrill Guest House — ready

Packet: [`runtime/research/sol-reference-20260908/sherrill-guest-house.json`](../../runtime/research/sol-reference-20260908/sherrill-guest-house.json)

The first-party drone frames show a red brick long house with a steep dark blue-gray small-unit roof, two pale dormers on the north/near slope, and three peak tips on the south/opposite slope. Use one `bricks` wall field and the `deepslate_tiles` family for visible pitched roof surfaces. The small roof ROI slightly favours gray concrete by colour alone, but gray concrete lacks both the observed unit pattern and the stair/slab forms needed for the roof; deepslate tiles are the stronger construction proxy. The brick decision follows visible bond/material character because no clean large wall ROI exists and aerial colour is heavily compressed and lit.

Keep all four measured roof faces. No source mask marks an artifact for deletion. Add the two north and three south dormers at the packet's interpreted UV bounds; the south fronts/windows remain provisional because only their peaks are visible. Ground-floor rows, doors, entrances, east/west apertures, floor plates and the possible pale east-end stack remain interpreted or unresolved.

## Davy House — material correction

Packet: [`runtime/research/sol-reference-20260908/davy-material-correction.json`](../../runtime/research/sol-reference-20260908/davy-material-correction.json)

Replace the flat `light_gray_terracotta` wall field with one coherent `stone_bricks` construction family. The corrected shaded ROI and its source context show coarse horizontal masonry courses; stone bricks preserve that evidence and have lower equal-lightness error than the old flat finish (8.385 versus 13.501). Blue terracotta and gray concrete are close to the deep-shadow colour but contradict the visible construction pattern. The Minecraft block is a coursed-masonry proxy, not an identification of the real stone or cladding product. Do not add cracked or mossy texture patches.

Keep the `deepslate_tiles` roof family. The first-party drone shows a dark blue-gray field of small overlapping units. Gray concrete is slightly closer by colour alone, but it cannot supply the observed unit pattern or pitched-roof shapes. Keep pale quartz trim and preserve all current geometry and measured roof planes.

## East Faculty Village Unit 3 — final native palette decision

Packet: [`runtime/research/sol-reference-20260908/east-faculty-unit3-material-review.json`](../../runtime/research/sol-reference-20260908/east-faculty-unit3-material-review.json)

Retain the v8 palette: `white_terracotta` for the single coherent facade field and `oak_planks` only in the two observed gable-tip zones. No audited original vanilla texture improves both the contractor photograph's tan colour and its horizontal lap grain at 2 blocks per metre. Birch planks add useful courses but shift the native building toward yellow/olive and have worse raw and equal-lightness error in both source siding ROIs. Pale oak is too light; oak and jungle families are too dark or chromatic for the whole facade. White terracotta therefore remains the least-bad tested choice, with its smooth pink-taupe native cast explicitly unresolved.

The native oak gable tips also read too mustard. The alternatives do not establish a net improvement: jungle lowers raw distance only slightly while adding red cast, spruce is much too dark, and birch/pale oak are much too light. Keep one coherent oak infill rather than forcing a second unverified change or adding mixed pixels. This decision does not alter the photographed south/front and west/return geometry, roof, porch, openings or cameras.

## Davy House — roof and railing correction

Packet: [`runtime/research/sol-reference-20260908/davy-roof-railings-handoff.json`](../../runtime/research/sol-reference-20260908/davy-roof-railings-handoff.json)

The raw Roofer shell is complete inside the source footprint. Keep the seven elevated source faces identified in the packet, including both long main-roof planes, the central cross-gable, and the broad lower canopy complex. The current whole-footprint clear and three axis-aligned replacement roofs are unsupported: they duplicate and flatten measured faces. Restrict authored roof work to the seven photographed east small gables, provisionally mirrored west projections, and the small outer entry hood. Combine them by maximum height and clip the result to the original source footprint.

Replace yellow-reading birch fence only in the existing Davy railing roles with connected `pale_oak_fence`. It is the closest original thin, near-white construction part; the choice is a visual proxy and does not identify the actual railing substrate. Preserve the interpreted runs and height, and do not add a thick quartz cap.

## Hillhouse & Moore Business Office — native facade addendum

Packet: [`runtime/research/sol-reference-20260908/hillhouse-moore-office-native-material-addendum.json`](../../runtime/research/sol-reference-20260908/hillhouse-moore-office-native-material-addendum.json)

The native v2 views invalidate polished andesite as the wall proxy because its dark bordered half-metre squares dominate the facade, unlike the continuous fine rough source render. Swap the complete gray facade/foundation field coherently to ordinary `andesite`. It removes the explicit border and improves the lit ROI result while remaining close in shade. Keep the white trim, green hoods, roof and geometry unchanged.

## Ryan and Hunt — engineered-ground exception review

Packet: [`runtime/research/sol-reference-20260908/ryan-hunt-ground-exception-review.json`](../../runtime/research/sol-reference-20260908/ryan-hunt-ground-exception-review.json)

Keep both flagged checkpoint heights. Ryan's continuous `quad_east` approach plane is 67.449 m, 0.389 m above the 67.060 m bare-earth grid; rounding to the built 67.5 m top adds only 0.051 m. The 18-second drone view directly shows broad pale engineered paving across this approach, supporting the continuous-plane shift. Round-to-nearest half-metre quantization alone would be at most 0.25 m and does not explain the whole checkpoint difference.

Hunt's `hunt_mid_north_slope` transforms to local `U=34.761, V=-0.172 m`, immediately outside the north wall on the authored upper terrace. The +2.722 m departure from bare-earth grade is supported by Isett's photographs of a narrow raised walk/bed and black rail above an intermediate planted ledge, tall outer retaining wall and lower drive. Those images validate the retained section, but they do not survey the full rectangular terrace extents or exact levels. Future correction should refine the terrace edges and stair interruptions from plan or orthophoto; it should not lower this point to DEM, flatten the north court to Quad grade, or fill beneath stair flights and overhangs merely to match the terrace plane.
