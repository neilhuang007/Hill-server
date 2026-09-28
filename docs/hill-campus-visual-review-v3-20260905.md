# Native Minecraft campus review — 2 blocks per metre

Reviewed the eight captures from `campus-context-v3-2x-20260905`, plus the five Hunt v4 captures. The current assembly is useful for inspecting the developed buildings together. It is **not yet a complete photographic match of the campus**. Every building and the measured ground use the same 2-block/metre scale and Y=(NAVD88−25)×2 frame.

![Hunt and Ryan in the shared Minecraft world](../runtime/campus-reconstruction/chapel-native-qa/runs/campus-context-v3-2x-20260905/screenshots/quad-hunt-and-ryan.png)

## What improved

Hunt closes the north side of the Quad opposite Athey, with Ryan to the east and the Chapel to the west. Alumni House retains its separate measured position near High Street. The county/school-map atlas now marks all five included footprints. These relationships were checked against the [official map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf) and the [2026 school footage](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4).

The first Hunt native pass exposed interior birch floor edges through stepped facades. The fourth study keeps floor plates inside the roof-level envelope and never overwrites facade blocks. Its inner wing faces now have windows. The equivalent floor-boundary correction was applied to Ryan. Native captures show the unwanted pale floor bands removed from Hunt's front.

Hunt's roof uses warm waxed cut copper in place of brick, a dark deepslate central strip, and green oxidized copper details. This gives roof and wall distinct materials using ordinary blocks. The south dormer rhythm differs from the six broad north dormers. The real low south arcade roof is retained near 70.1 m NAVD88. North source failures and the lost attic gables were corrected separately by extending nearby measured roof planes; the raw CityJSON remains unchanged. Those corrections are recorded in the Hunt profile and manifest, with source limitations described in the [Hunt report](research/hill-hunt-hall-reference-20260905.md).

![Hunt arcade and recessed windows after correction](../runtime/campus-reconstruction/chapel-native-qa/runs/hunt-hall-v4-2x-20260905/screenshots/hunt-arcade-detail.png)

## Remaining likeness work

| Area | Native observation and next correction |
| --- | --- |
| Quad landscape | Building placement reads clearly, but the bare lawn lacks the continuous walks, large trees and planting visible in the source footage. The stepped DEM is more conspicuous without those features. |
| Hunt | The broad U-shaped mass, roof colors, arcade and window rhythm are present. North stair-tower appendages, end-gable trim, small hooded roof openings, curved copper ornament and some outer roof strips remain incomplete. Some window frames are visually heavy at 0.5 m sampling. Nine front arches and the tree-obscured east dormer count remain provisional. |
| Ryan | The five-bay west arcade, separated arcade roof, upper groups and west approach survive assembly. North lower and hidden east elevations still need independent detailing. |
| Athey / Dining | Recessed connected panes, arch stairs, the open court and measured roofs survive the scale change. Fine facade proportions and Dining Hall's own detailed elevations remain unfinished. |
| Alumni House | The closer street-facing view resolves the house and porch. The rough upper approach and stepped bank still need a more careful site finish; the back remains less verified than the front. |
| Chapel | Existing detailed rules and the brownstone pack survive the shared coordinate conversion. The larger inferred tree crowns have not yet been integrated into this campus version. |
| Broad aerial view | Some distant chunks are visibly unloaded in the overview capture. This limits that image as visual evidence; the independently decoded source world is complete within its declared terrain bounds. |

The [assembly artifact audit](../runtime/campus-history/cleanup-20260915/outputs/runtime/campus-reconstruction/campus-context-v3-2x/artifact-audit.json) independently verified all **20,032,935 occupied blocks**, 1,632 chunks, source component hashes, copied native source files, screenshot hashes and material-pack files. No forbidden architectural materials were found. This establishes export fidelity, not a numerical likeness score. Camera matching remains approximate rather than a calibrated Street View comparison.

Relevant regression checks passed: **58 tests plus 8 subtests**, including recessed panes at both scales, roof-state preservation when changing to copper, preservation of the real low arcade during north roof correction, tile ownership/air-space preservation and detection of changed native source files or screenshots.
