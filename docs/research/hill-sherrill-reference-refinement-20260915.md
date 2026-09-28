# Sherrill Guest House reference refinement — 15 September 2026

## Builder handoff

Use the machine-readable packet at
[`runtime/research/sherrill-reference-20260915/sherrill-reference-refinement-packet.json`](../../runtime/research/sherrill-reference-20260915/sherrill-reference-refinement-packet.json),
SHA256 `e28fb954a8efeec966a1fc0beb9e4bd1f0af29cfa02b5cd88d1f85d42ff7cb21`.
It is bound to `sherrill-v8-2x` sample blocks
`4b938b7bb574e9df0bb33a09c4be433c2757be10dbbd538399618b19201c829c`
and the complete native baseline report at
`runtime/campus-reconstruction/chapel-native-qa/runs/sherrill-v8-baseline-20260915-175th/chapel-native-qa-report.json`,
SHA256 `cf662168c0cad5ff14bd9e2b056c2156bf97018362e73ed53ff02a2790f5f0cf`.
V8 has no accepted `native-review.json`; treat it as a diagnostic baseline and
build the refinement in a new immutable study directory.

The next revision should fix four visual blockers before any broader opening
work: straight facade planes, compact gabled dormers, dark recessed glazing,
and a fine roof edge. Preserve the measured footprint and campus placement,
all four source roof faces, the five dormer centroids/bounds, the grade and the
5.188331 m Ferenbach gap. Coordinates remain `X = 2 * east_m`,
`Z = 2 * south_m`, `Y = 2 * (NAVD88_m - 25)`.

## What the current footage establishes

The strongest source remains The Hill School's
[current first-party drone video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4),
linked from the school's [Our Campus](https://www.thehill.org/about/our-campus)
and [Schedule Your Interview](https://www.thehill.org/admission/schedule-your-interview)
pages. The saved 1920×1080 file is
`runtime/research/athey-20260905/campus-2026-drone-1080.mp4`, SHA256
`b4c03c8d5462030ce8e95e5f56b3260da044501144f7390cbfc24e89c3894b21`.
The useful interval is 238.0–240.0 seconds. New crops use source rectangle
`x=350..739, y=650..1079`; the contact sheet is
[`sherrill-drone-238-240s-contact.png`](../../runtime/research/sherrill-reference-20260915/sherrill-drone-238-240s-contact.png),
SHA256 `fcc1395c6d5dbcfab9afac3e8824593166d9043e586099f69685dc0fe39bea4c`.
The contact sheet is enlarged only for inspection, not metric measurement.

Visible with high confidence:

- The house is a long red masonry volume under a steep dark blue-gray
  small-unit roof.
- Two compact sharply peaked dormers face the camera on the north slope.
  Each has a small pale triangular/rake area, a dark recessed frontal opening
  and dark roof cheeks merging into the main roof. They do not read as tall
  white towers.
- Three pale dormer peak tips appear beyond the ridge on the south slope.
  Their fronts and windows are hidden.
- The eave and gable edges are fine, nearly continuous lines. The footage does
  not show v8's alternating half-metre quartz/deepslate teeth.
- The north wall reads as a comparatively flat brick plane. At least three
  dark upper openings are partly readable. Trees and shadow obscure the entry
  and prevent a complete opening count.

Visible with moderate confidence:

- The lit east gable has dark apertures, but foliage and compression prevent a
  reliable schedule. The pale end silhouette does not establish a chimney.
- A narrow straight pale walk rises from the foreground campus path toward the
  tree-screened north-front zone. Its exact building contact is hidden.

The search also checked first-party Hill pages and the official Hill Vimeo
result *Our Outdoor Campus*. The current Hill pages embed the same drone file;
the Vimeo public thumbnail was unrelated and no additional usable Sherrill
elevation was found. Doors, porch, chimney, exact path endpoint, hidden wall
rows and all south-dormer fronts therefore remain inferred or unseen.

## Straight facade controls

The deep repeating vertical brick teeth in the v8 native north and south views
are raster returns, not source-supported buttresses. Use these measured local
`U,V` footprint segments as the true facade planes. Smooth voxel steps along
each segment independently with inward-backed brick stairs/slabs while keeping
every occupied shape inside the source footprint:

| Segment | Measured endpoints, metres | Plane | Treatment |
| --- | --- | --- | --- |
| North main | `(3.11975, 0.00000)` to `(12.74196, 0.02672)` | `V = 0.002776 * (U - 3.11975)` | One continuous flat brick facade. |
| North east setback plane | `(12.70376, 0.93721)` to `(18.68173, 1.14402)` | `V = 0.93721 + 0.034596 * (U - 12.70376)` | Smooth as one plane after the real setback. |
| North west low appendage | `(0.33657, 1.04746)` to `(2.61195, 1.11609)` | `V = 1.04746 + 0.030162 * (U - 0.33657)` | Smooth the short appendage plane only. |
| South main | `(2.57726, 8.68404)` to `(17.37072, 8.68404)` | `V = 8.68404` | One continuous flat brick facade. |

Allow at most the half-block centre-quantization tolerance, 0.25 m, around each
plane. Preserve the intentional roughly 0.91 m north setback near
`U=12.72 m`, the measured western low appendage and its returns, the irregular
east end and all source-footprint corners. Do not use the roof or trim
silhouette to create wall projections, fill the building to a replacement
rectangle or move the facade centreline. Any stair/slab shaping needs full
brick backing on its interior face.

## Dormer and opening correction

Within the existing UV dormer envelopes, rebuild the two observed north
dormers as compact gabled projections. Use deepslate stair/slab roof cheeks,
dark panes below and only a small quartz stair/slab gable/rake. Remove the
broad full-height quartz cheeks and flat/cross-shaped caps that make v8 read as
white towers. Apply the compact construction to the three south dormers only
as a clearly recorded consistency proposal: the source shows their count and
peak tips, not their fronts.

Native-test `gray_stained_glass_pane` first for the two north dormers and the
source-visible north/east openings. It is a tonal proxy for a dark recess, not
a claim that the real glass is gray. If it remains too bright in the matched
aerial, test black panes as a bounded second variant. V8's white stained panes
are rejected for source-visible openings because all five native views make
them read as bright milky patches. Keep solid backed heads and sills, connected
diagonal pane returns and window trim inside each opening. Do not add or
regularize hidden wall rows.

Carry the deepslate roof skin continuously to the measured edge. Replace the
alternating full-block quartz fringe with a thin backed line of quartz
slabs/stairs only where a pale fascia or rake is needed. The retained material
families are ordinary vanilla construction blocks: bricks/brick stairs/slabs,
deepslate tiles/stairs/slabs and narrowly bounded quartz blocks/stairs/slabs.
Do not use sculk, ore or organic/decorative blocks.

## Terrain, uncertainty and acceptance

Measured perimeter grades are 64.2245 m north, 65.7691 m south, 65.6181 m
west and 65.7631 m east NAVD88. Keep the 1.5446 m north-to-south rise. A later
terrain/access pass should retain or restore the narrow straight walk toward
the north-front tree-screened zone, but it must not move a door to meet the
path because the building contact is unseen.

After refinement, re-run pane-joint, perimeter, component, wall-closure,
partial-block-backing, roof-top and assembly-gap checks. Confirm that all four
measured roof faces remain unchanged outside the five bounded dormer envelopes.
Then compare a new native northeast aerial directly with the 238.0–240.0 s
contact sheet. Acceptance requires a new `native-review.json` bound to the
exact new sample-block or archive hash; structural success alone does not
establish photographic likeness.
