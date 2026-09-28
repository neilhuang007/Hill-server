# Archived four-block Athey development — 5 September 2026

**Superseded scale:** the user subsequently requested two blocks per metre throughout. The current buildings, combined world and launcher are documented in [Hill campus assembly](hill-campus-assembly.md). The four-block results below are retained as development evidence, not current launch instructions.

The reconstruction now has a [searchable campus footprint atlas](../runtime/campus-reconstruction/campus-plan-v1/index.html), an [exportable building register](../runtime/campus-reconstruction/campus-plan-v1/campus-register.json), and a bounded [Athey v4 Minecraft world](../runtime/campus-reconstruction/athey-v4/world). The windows in v4 are recessed glass panes with wall-integrated trim, slab sills and stair-shaped arch reveals. The full campus and Athey's complete architectural likeness remain in progress.

## Open and inspect

- Double-click [Open-Hill-Athey.cmd](../Open-Hill-Athey.cmd) for the separate, persistent Creative-mode copy. It starts on the Quad side and uses vanilla Minecraft 26.1.2 with a 32-chunk draw distance. The generated source world is preserved.
- [Window close-up](../runtime/campus-reconstruction/chapel-native-qa/runs/athey-v4-20260905/screenshots/window-reveal-detail.png)
- [Quad front](../runtime/campus-reconstruction/chapel-native-qa/runs/athey-v4-20260905/screenshots/quad-straight.png)
- [East entrance](../runtime/campus-reconstruction/chapel-native-qa/runs/athey-v4-20260905/screenshots/east-return.png)
- [South court](../runtime/campus-reconstruction/chapel-native-qa/runs/athey-v4-20260905/screenshots/south-court.png)
- [Roof overview](../runtime/campus-reconstruction/chapel-native-qa/runs/athey-v4-20260905/screenshots/roof-overview.png)

These are native Minecraft screenshots, not Blender or offline render approximations. The [capture report](../runtime/campus-reconstruction/chapel-native-qa/runs/athey-v4-20260905/chapel-native-qa-report.json) records actual camera poses, active packs and screenshot hashes.

## Campus positions

The atlas registers **108 county source footprints**, including nearby context and outbuildings. All join to their exact Roofer parents. **29 official names currently match 27 unique footprints**; names still requiring evidence remain unassigned. A school building and a county polygon are not always one-to-one. Athey is school-map **3**, Dining Hall **4**; Mercer/Sweeney also share an aggregate.

The [official 2026 map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf) supplies names and numbering. Exact source rings come from [Montgomery County's building layer](https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6). Ordinary [Google Maps viewing](https://www.google.com/maps/@40.2445816,-75.6345728,19z) confirmed Athey's location, orientation, nearby buildings and separate court relationship. Google's visible rings are simplified; this does not certify all 108 rings individually.

The county Athey/Dining aggregate fills the open court. The construction overlay instead uses the measured roof/ground union, retaining the court and connecting roofs. Original county geometry remains unchanged in [WGS84 GeoJSON](../runtime/campus-reconstruction/campus-plan-v1/footprints-wgs84.geojson). [CSV coordinates](../runtime/campus-reconstruction/campus-plan-v1/building-positions.csv) include stable IDs, verified names, school numbers, metres, four-block coordinates, latitude/longitude and Google links.

The shared detailed frame is origin **40.24516, −75.63516**, X east, Z south, **4 blocks per metre**, and **Y = (NAVD88 metres − 25) × 4**. Alumni House v3 and Athey v4 share it. Earlier campus/Chapel worlds use different scales and need an explicit assembly conversion; individual buildings must never be arbitrarily relocated or resized.

## Construction method

Use independent GIS footprints and measured LiDAR terrain/roof planes for the spatial framework. Apply building-specific facade profiles and architectural components, then export exact block states directly. Blender is useful for inspecting or correcting measured shapes and unusual details; constructing every repeated window by hand or voxelizing an undifferentiated textured mesh would discard the material and construction rules that matter here. The [tool research](research/hill-reconstruction-pipeline-20260905.md) compares Voxel Earth, MapSmith/Arnis, OBJ-to-schematic and this hybrid method.

The Athey builder combines the measured roof with brick walls, stone-family roof blocks, pale surrounds, recessed connected glass panes, the east bay/entrance, supported roof thickness, an open east connector, and an engineered paved court. Floor plates stay inside the walls. Ordinary block families are allowed per construction role; RGB similarity cannot select an ore or sculk for architecture.

The east bay's flat notched parapet and the court's smooth paving correct visibly incorrect parts of the raw reconstructed surface. Those overrides are explicitly recorded as estimated geometry in [the building profile](../server-assets/hill-athey-reference.json). The original LiDAR sources are preserved.

## Review results and limits

Four Athey revisions and four native capture runs were completed. The early passes exposed an undetailed end wall, visible floor edges, insufficient draw distance and projecting surrounds. The current close-up verifies that the glazing sits behind the masonry surface and that surrounds follow local wall setbacks. Rotated-wall regression cases independently check that trim remains within the footprint and pane centres remain inside the wall boundary.

The [independent v4 artifact audit](../runtime/campus-reconstruction/athey-v4/artifact-audit.json) passed **38,419,560 occupied blocks**, with zero missing, extra, duplicate or mismatched full states. It also found no forbidden blocks or role-policy violations. Native pre-upgrade region files were checked against the source world, and all six screenshot hashes matched. Structural export success is not a complete likeness approval.

Athey's remaining visual work includes the central south gable/oculus, exact opening counts and dimensions, facade plane irregularities inherited from Roofer, finer glazing bars, foundation/site details and landscaping. Dining Hall currently has its measured connected envelope; its facade needs an individual detailing pass. Interiors are unfurnished construction proxies. The LiDAR fit statistic of 0.653 m is not a facade-survey accuracy claim. The campus atlas is a planning artifact; complete campus world assembly remains pending.

## Sources and reproduction

The school publishes a [1080p version of its current drone film](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4). Cached frames at 90, 97, 105 and 138 seconds show the court, east entrance, Quad facade and roof layout respectively. [Reference inventory](research/hill-athey-academic-center-reference-20260905.md) records other primary sources. The earlier Alumni House v3 study remains separately available and was approved visually by the user.

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/prepare_hill_campus_plan.py
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/build_hill_athey.py --output runtime/campus-reconstruction/athey-next
uv run --python 3.13 python scripts/run_chapel_native_qa.py --world runtime/campus-reconstruction/athey-next/world --run-name athey-next-review --camera-config runtime/campus-reconstruction/athey-next/camera-views.json --render-distance 32 --width 1440 --height 1000 --settle-seconds 8
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/audit_hill_block_artifact.py runtime/campus-reconstruction/athey-next --native-report runtime/campus-reconstruction/chapel-native-qa/runs/athey-next-review/chapel-native-qa-report.json
```

Use fresh output/run directories. Building worlds and native review runs are never overwritten. No server deployment was performed for this phase.
