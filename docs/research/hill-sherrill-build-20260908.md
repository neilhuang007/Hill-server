# Sherrill Guest House construction study — 8 September 2026

## Current pointer — checked 15 September 2026

The latest generated individual study is `runtime/campus-reconstruction/sherrill-v10-2x`.
Its native review rejected the dormer fronts. V8, v9 and v10 were natively inspected and rejected for
facade/dormer refinement; preserve both diagnoses. Campus v8 still contains
Sherrill's measured shell. See the [September 15 refinement handoff](hill-sherrill-refinement-build-20260915.md).

## Historical v6 construction record

The study recorded below is `runtime/campus-reconstruction/sherrill-v6-2x`, with
the vanilla world, ZIP, exact block archive, five native camera positions,
profile, generator snapshot and reproducible structural checks. Native
inspection of v6 is pending. All five v3 native views were inspected and
rejected for obscured dormer glass and a residual gray floor-edge stripe.
The v6 archive SHA256 is
`bee124c79a53652f7b364df550eb037377b7a8836b987dd8e86c8ee42f1116d1`.
The source-bounded proposal does not establish the
unobserved wall openings as measured or visually complete.

## Evidence and identity

The Sherrill Guest House is Roofer parent `16001511600619C-b4c5171aed`,
county structure `16001511600619C`, research source index 67 and current
school-map number 46. It is the small steep-roofed red house beside the Dell
Village complex in the supplied current drone crop, not one of Dell's larger
dormitories.

This model uses the Sol research packet at
`runtime/research/sol-reference-20260908/sherrill-guest-house.json`, SHA256
`c67776872f1ec410db7ab36d2931e19e3c329d9219ce5a7da3c50e645e751c52`.
Its primary visual evidence is the school's
[current drone video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4)
at 238–240 seconds. The current
[school map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf)
and the
[2021 facilities map](https://resources.finalsite.net/images/v1633097238/thehillorg/ewtimjvxagjkgblsqf5q/fy22campusmapgraphic.pdf)
support the identity crosswalk. Source image, map, texture and roof hashes
are preserved in the packet copied into the profile. No new visual or
material research was performed by this modeling agent.

The supplied `dell-sherrill-238s-crop.png` was inspected directly. It shows
two pale north dormer fronts and three pale peak tips beyond the ridge on
the south. The lower brick walls are substantially screened by trees and
shadow. The three opposite dormer fronts and their glazing remain proposals.
The possible pale end-stack silhouette is unresolved and has not been
converted into an invented chimney.

## Exact footprint, slope and source roof

Coordinates use exactly 2 blocks per metre: X = 2 × east metres,
Z = 2 × south metres and Y = 2 × (NAVD88 metres − 25). The original local
origin is `(276.4041570562, -56.8424030160)` metres and the long axis is
−14.1451527154 degrees. The stepped western low appendage and the irregular
eastern return are retained. No rectangular replacement, world-axis rotation
or terrain flattening is applied.

The proposed entrance floor is 65.95 m NAVD88. Upper plates at 68.8 and
71.65 m are typological proposals. Supplied perimeter ground values range
from about 64.22 m on the north to 65.77 m on the south; source grade gives
the north a more exposed base. V3 changed the foundation field to brick, but
native inspection exposed a remaining gray stripe. Its actual exported role
was `floor`: 100 perimeter `smooth_stone` cells at world Y81. V6 faces these
specific cells in brick while retaining the interior plate. No supplied
evidence supports an added gray stone plinth.

All four measured source roof faces remain represented:

| Face | Source fingerprint | Height range, NAVD88 m | Interpretation |
| --- | --- | --- | --- |
| 0 | `6d95a76e7ad34032` | 72.882–76.683 | Main south slope, 49.92 degrees. |
| 1 | `d9453852ea9e0eae` | 68.149–69.380 | Low western roof/detail, 23.53 degrees. |
| 2 | `4e69c5677117d6c1` | 71.936–74.330 | Small eastern return roof/detail, 50.16 degrees. |
| 3 | `df2ed4f1a4eae7d1` | 70.166–76.683 | Main north slope, 49.73 degrees. |

Five dormers use the packet's exact metric rectangles and max-combination
roof patches. Two north appendages are at U 5.65–7.05 and 13.45–14.85 m,
V 1.15–4.40 m, with proposed eave/ridge levels 74.55/75.50 m. Three south
appendages are at U 5.30–6.70, 9.80–11.20 and 14.30–15.70 m, V 6.10–8.10 m,
with eave/ridge levels 75.40/76.30 m. Their footprints stay inside the original
building. The source roof remains unchanged outside 63 raised appendage
columns; each patch is recorded separately rather than hidden in a flattened
or substituted main roof.

## Individual material interpretation

The packet compares the original 26.1.2 vanilla construction textures with
small source-image regions. These are lighting-dependent appearance metrics,
not calibrated material reflectance or an identification of the real product.

| Surface | Vanilla construction | Evidence and limitation |
| --- | --- | --- |
| Brick wall and visible base | `bricks` | Coursed red masonry character controls the choice. The tiny lit gable sample scores ΔE2000 15.233 for bricks versus 14.347 for polished granite; granite's speckled stone texture conflicts with the visible bond. Deep shadow is not used as brick albedo. |
| Main and dormer roofs | `deepslate_tiles`, slabs and stairs | Dark, slightly blue-gray small-unit roof. The 252-pixel roof sample scores raw/equal-lightness ΔE2000 9.701/9.444. Gray concrete is closer in raw colour but lacks the observed unit pattern and pitched construction forms. |
| Dormer fronts, cheeks and narrow eaves | Quartz full blocks, slabs and stairs | Pale painted appearance is observed on the two near dormers. This is a vanilla construction proxy, not a claim about the real trim substrate. |
| Glazing and provisional doors | White stained panes and pale-oak doors/panels | Pane texture supplies a slim sash rim. Lower opening layouts and door colours remain interpretations. |

V2 removes brick cap flecks introduced by the perimeter backing routine from
the bounded pale dormer envelopes and paints their front rake edges without
changing roof tops. V3 changes the foundation to brick; v6 also corrects the
exposed floor edge identified in native inspection. There are no ores,
sculk, custom textures or a uniform campus palette
substitution.

## Glazing and closure

Eighteen proposed wall-window groups and five dormer windows are built.
Six of the 24 proposed wall groups are omitted where the actual roof prevents
them, including the upper north row whose proposed head is at 70.75 m. The
source does not establish a complete wall count, so these omissions are not
described as missing observed windows. The broad blank northern left section
and missing proposed upper north row remain explicit source and model
limitations; the aerial image partly shows upper openings but does not give
a usable complete schedule or height. Both actual two-block operable doors
are provisional locations in the measured west and south walls.

Panes replace actual wall cells. Thin inner head/sill supports sit outside
the glazed vertical interval. Registered, bounded interior L-returns connect
diagonal glass to intact masonry; no projecting window cages are added.
Dormer cheek and gable cladding stays inside the corresponding source packet
rectangle. Following v3 native rejection, the interpreted dormer aperture
width is 1.05 m instead of 0.75 m. North glass is 1.5 m high instead of 1.2 m;
the south retains 1.2 m to stay below its unchanged eave. The packet's original
proposals remain in the profile. Sills, all five roof bounds, eave/ridge
controls and the four source roof faces are unchanged. A two-cell inner
glass column connects one rotated south sash end to its existing cheek;
its cap remains outside the glazed interval.

All 134 v3 pane positions and materials remain. The exact delta contains
115 changed cells: the 100 floor-edge cells and 15 changes inside the original
dormer rectangles, including 10 added panes and connection/cap adjustments.
The final exported archive verifies:

- 144 panes in 23 supported components, with no panes outside the envelope.
- Zero horizontal free ends, vertical air/reversed caps, diagonal pane-to-jamb
  candidates or partial cap contacts across 288 vertical edges.
- Zero empty cells among 1,898 outer and recessed wall cells.
- Both operable doors have matching halves and supported thresholds.
- All 521 final architectural roof tops match the quantized source-plus-
  appendage surface exactly; no physical roof-top error is present.
- All 324 partial source-roof caps have full direct backing.
- No clipped writes or material-policy violations; 289,049 exported blocks.

The pane perimeter, pane-pair, component, wall-volume and physical roof
checks are separate. They do not imply that support of a component alone
proves every possible sightline closed.

## Neighbour gaps and native views

The exact source gap to Ferenbach is 5.188331 m. Sherrill's narrow 0.45 m
ownership buffer leaves 4.738331 m to Ferenbach's source footprint and zero
overlap. The next nearest source gap is 9.513603 m to Senter. The study's
12 m terrain margin is not assembly ownership. Four nearest housing gaps
are recorded in `assembly-gap-check.json`.

The five cameras are `sherrill-northeast-drone-match`,
`sherrill-north-eye-level`, `sherrill-south-high-oblique`,
`sherrill-roof-plan` and `sherrill-west-entry-and-low-roof`. The first four
match the packet's requested visual studies; the fifth checks the low source
appendage and the provisional west entry.

All five current v6 offline projections were inspected against the supplied
crop. The base stripe is gone, and the north glass has a taller visible sash.
The narrow pale dormer cheeks still dominate some oblique bearings, and the
gable caps remain coarse; these are open native review questions. These
previews use original textures but are not native screenshots. The native
review must judge the narrow dormer gable silhouettes, light sash rims, roof
darkness and stepped fascia at the retained world angle. Lower
opening schedules, door positions, exact dormer proportions and unobserved
south fronts remain provisional even after a successful native inspection.
