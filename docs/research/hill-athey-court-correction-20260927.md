# Athey south-court arcade correction — 2026-09-27

The earlier five-stair interpretation is rejected. The school’s 2026 drone and aerial show **one broad central stair** entering a **continuous recessed covered walk** behind a pointed arcade. The user confirmed that the feature is a curved covering over the recessed walkway and required no exposed grass. This handoff supplies corrected, registered controls for a new immutable Athey/Dining study; it does not modify a building or world.

The machine packet is [`court-correction-controls.json`](../../runtime/research/core-demo-20260927/court-correction/court-correction-controls.json). Its evidence and hashes are in [`evidence-manifest.json`](../../runtime/research/core-demo-20260927/court-correction/evidence-manifest.json).

## What the sources establish

The official 88-second view resolves one compact flight with dark side rails and a middle rail. About seven short risers span roughly 1.4 metres from court grade near NAVD88 69.5 m to the covered-walk landing near 70.9 m. It does not show a flight at every arch. The broad stair belongs on the existing central U=37 axis. [Official 88-second crop](../../runtime/research/core-demo-20260927/court-correction/evidence/official-drone-088s-athey-south-crop.png), [school-hosted 1080p video](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4).

The same close sequence directly resolves four broad pointed recesses, while the complete current aerial shows the rest of the wall between both gallery attachments. Together they support an approximately nine-opening arcade rhythm: five broad pointed bays and four narrower pointed recesses around the central gable/vertical strips. Shadow, people and shrubs prevent a complete door or glazing schedule. These are openings onto one continuous covered corridor; they are not nine exterior doors. [Aerial arcade enlargement](../../runtime/research/core-demo-20260927/court-correction/evidence/official-2026-aerial-athey-south-3x.png), [pixel-grid enlargement](../../runtime/research/core-demo-20260927/court-correction/evidence/official-2026-aerial-arcade-grid.png), [school 2026 aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg).

The contributed October 2016 Google panorama faces Athey’s north side. It corroborates the building’s central-gable, continuous pale-belt and deep pointed-recess language, but it does **not** provide south-court dimensions, opening count, stair geometry or current surfaces. [Historical Google crop](../../runtime/research/core-demo-20260927/court-correction/evidence/google-2016-athey-north-detail.png), [provenance](../../runtime/research/core-demo-20260927/evidence/google-contributed-quad-panorama-source.json).

## Builder controls

Keep the accepted frame `origin=[22,37] m`, axis `18.25°`, and `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`.

Build the lower court feature as a continuous paved corridor behind a pointed front shell, from west gallery `U=21.8` to east gallery `U=52.2`. Use a working front datum near `V=16.5` and recess the clear corridor northward to about `V=14.5..15.0`, giving about `1.5..2.0 m` clear depth. The overhead soffit must read as a connected curved/pointed shell under the retained body. Piers divide the court view but must not partition the walk behind them.

Use this photo-registered opening schedule at the half-metre construction scale:

| Type | Local U centres | Width | Status |
|---|---|---:|---|
| Broad pointed bays | `25, 30, 37, 44, 49 m` | about `2.8 m` | Four broad bays resolve directly in frame 88; the complete five-bay broad rhythm is supported by the aerial. |
| Narrow pointed recesses | `27.5, 33.5, 40.5, 46.5 m` | about `1.0–1.4 m` | Aerial-registered; exact jambs are unresolved. |

All nine recesses begin at the covered-walk floor near `H=70.9` and share the pointed head/shell zone to about `H=73.5`, followed by the continuous pale belt around `H=73.8`. Do not lower the openings to court grade. Keep dark set-back glazing or open depth where the source is unresolved, and do not infer a door at every bay.

Place exactly one stair at `U=34.2..39.8`, `V=18.3..21.0`. This is approximately `5.6 m` wide and `2.7 m` in run, centered on U=37. The source has about seven 0.2 m risers. At two blocks per metre, the closest ordinary proxy is six supported quarter-metre rises over `2.5..3.0 m`; avoid a deep ramp. Keep dark rails at both edges and one middle rail. The registered block polygon is approximately `[(97.5,130.2),(108.1,133.7),(106.4,138.8),(95.8,135.3)]` in X/Z.

Keep a continuous upper landing from about `V=16.5..18.3` at `H=70.9`. The court is near `H=69.5`. A thin court-edge curb may continue along `V≈21.0` on `U=21.8..34.2` and `39.8..52.2`, interrupted only by the stair. Its exposed face should stay at or below about `0.5 m`; it must not become the tall repeated gray wall seen in the rejected revision. The user’s no-grass instruction governs the finish: use hardscape for the walk/stair and dark mulch/coarse dirt or restrained low planting behind any retained curb, with **zero exposed grass blocks**.

## Upper facade and roof boundary

Do not propagate the lower shell datum through the whole upper building. The measured roof remains authoritative. Inside the court run, the source supports one main cross-gable centered at `U=37` with about `5 m` half-width. That central mass may reach the retained southmost source edge near `V=16.56`; the flanking upper walls sit farther north near `V=14.0..14.7`.

The current source-raster `edge_v` values were sampled independently at the old five lower centers (`13.60..16.56 m`) and turned ordinary openings into separate deep projections. Regularize the flanking brick planes and pale belts with minimal monotone steps at the registered bearing. U=25, 30, 44 and 49 are opening positions, not four extra gabled masses. Preserve the central cross-gable and measured roof while removing the per-window accordion effect and jagged stringcourses.

## Acceptance boundary

A corrected study should show one central stair, about five broad plus four narrow pointed recesses, a continuous player-clear covered walk joining both end galleries, a visibly curved/pointed connected shell, and no exposed grass anywhere in the south arcade/landing/stair/curb strip. The exact narrow jambs, door/glazing subdivisions, wall curve and eave overhang remain photo-registered interpretations rather than surveyed facts.

The rejected screenshot is SHA-256 `ba6aac309004f4b96b513f28216d5a831fe9dcf3dda8028a012fbe301851d768`. Its five deep flights, high repeated retaining walls, five-opening total, per-bay door approaches and accordion facade should not be retained.
