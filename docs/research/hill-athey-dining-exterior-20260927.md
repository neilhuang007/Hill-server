# Athey and Dining exterior refinement — 27 September 2026

The final candidate is `runtime/campus-reconstruction/athey-dining-v19-2x`. It repairs the Athey court facade into a continuous paved recessed arcade with pointed overhead vaults, one compact central stair, closed upper-wall returns, grass-free planting strips, and a working north entrance. Both covered galleries retain their open longitudinal and broadside routes and their physical roof/floor contacts. Dining receives conservative rear/end opening detail. The east gallery roof now has the source-visible pale finish.

The coordinator accepted v19 for bounded integration after inspecting all eight useful final native images and verifying exact 4,880,911-block export/native provenance. The study's coordinator-authored `native-review.json` records that acceptance. The coordinator owns exact transfer onto campus v14, final combined-route checks and current-manifest selection. This study does not change the launcher, deployment or any player save.

## Frozen artifacts and sources

| Artifact | SHA256 |
| --- | --- |
| v19 `sample-blocks.npz` | `9ee4726dca3a9334c77c939755faa7c9655ee2a1cd51546e0af808857eb2e002` |
| v19 `profile.json` | `c2222a51366e56aecaa2f36fe045bdb2105bef514ea92b15c2786f91862e8e40` |
| Accepted baseline v6 archive | `b63750c8b8fb5ce76be445d5eeb1d693c65b9ba8df5f879da5a2f2f28d2681b4` |
| Athey frame-v4 profile | `5318e730568ce5a10f645eab6786d031b789e1dd94636286cd30040b80967bc4` |
| Measured CityJSON | `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8` |
| Original Dining packet, 16 September | `d302d1ebdb6a11b73a4e9c06bf4aa87b5920ff768494b11b445c33494e5f1b7c` |
| `core-building-controls.json` | `c7c8393c6cf079e57198b91aa99c9b7192e021d6fb7d7cef324ffc72429243a2` |
| `court-correction-controls.json` | `7206b3b20f8df2ac343644ac96e86521d1a11254bf6ba791a8919d807c60cd96` |
| `court-correction-addendum-v2.json` | `2e158be006fd37308aef02fe48ca8f91f242c1f1b97a5e5ecd2fb33aba63a66b` |
| `athey-east-gallery-garden-connection-v1.json` | `43abb6c166970c7a7d0f48fa9c8c1aa4685ca53f778535535f5dff905217ed80` |

The three correction files are under `runtime/research/core-demo-20260927/court-correction/`. The associated written interpretation is [the court correction handoff](hill-athey-court-correction-20260927.md). The source CityJSON remains `runtime/campus-reconstruction/roofer-chapel-trial/campus-model/hill-campus-roofer.city.json`, parent `16001511600613C-92645e8573`.

The editable profile is `server-assets/hill-athey-dining-refinement-20260927.json`. Frozen generator copies are included in v19; their original names and hashes are:

- `build_hill_dining.py`: `1a60f9075f0e36fac15b790dee5d1c18aa40c26ff54c457117f4c12f71357b25`
- `hill_dining_details.py`: `16af0f965c05512e8ee65fe97183a8037203e5805a675c1daf119e3826043d8e`
- `campus_athey_details.py`: `97a262365387c74b79de4ee9c9475751058745d4a6cfa8edecb071d8621fdc79`

## Source interpretation and changes

Consecutive official frames 87.5–91 seconds and the complete 2026 aerial supersede the earlier five-door/five-stair assumption. They show one central stair, a continuous raised court-side walk, broad pointed recesses and narrower interleaved recesses. The user explicitly confirmed a **curved covering over the recessed walkway** and no grass. The result contains actual stepped pointed vaults over a connected corridor; the dark glazing is set back behind that corridor.

The photo-registered schedule uses broad centers U25,30,37,44,49, width 2.8 m, and narrow centers U27.5,33.5,40.5,46.5, width 1.2 m. Approximately nine openings are supported by the complete aerial; exact centers and widths are interpretations, not surveyed facade coordinates. The shell front is V16.5, the corridor is recessed toward V14.5, and the landing reaches V18.3. The source floor H70.9 quantizes to feet Y92; pointed heads are near H73.5/Y97 and the pale belt near H73.8/Y98.

Only the central stair remains: U34.2..39.8, V18.3..21.0, approximately 5.6 m wide and 2.7 m long. Six half-block rises represent the roughly seven small risers in the image. The stairs retain side and middle dark rails. Two flanking strips have coarse-dirt mulch, clipped shrubs, one small ornamental tree and low coping. They contain no exposed grass blocks and do not obstruct the corridor or stair.

The two upper flanking wall runs use regular planes and continuous bands. Four explicit perpendicular returns close the junctions with retained wall/gable portions. All 240 cells across those return volumes at Y99..113 are full occupied blocks. V18 added precisely 178 cells to close the thin seam visible in v17; v19 leaves this geometry unchanged.

The raised arcade does **not** invent direct end ramps into the lower galleries. Source review shows arcade feet Y92 and court/gallery feet Y89, with no visible auxiliary end stairs. The evidenced route is arcade → central stair → court → either gallery. Both gallery roofs remain physically attached at their Athey and Dining ends, and the floor routes turn onto the Dining court apron.

The north entrance retains its registered central frame. Mistaken glazing/timber that blocked the passage is replaced by two functional dark-oak door leaves and a glazed transom. A supported Y85 platform at X116..120,Z79..88 joins the landscape at `[118,85,79]`; it avoids the inherited drop to Y82.5. The door proof validates the exact closed states, then simulates their open hinge positions for a 0.6 × 1.8 block player. Final combined review must assess surrounding campus grade; isolated-study grass around the platform is not the accepted campus approach.

Dining's rear and ends receive 25 simple rectangular opening groups with restrained pale frames and dark glazing. The low-U Athey end receives eight conservative rectangular groups aligned with retained storey heights. Their counts and exact positions are explicitly inferred because the available photographs do not resolve those elevations. No extra towers, arches or projecting bays were invented there. Existing pane reveals are connected and backed; all 3,487 final exterior pane cells are checked individually.

The old September 16 description calling frames 92–100 “west” was wrong. The modern Quadrivium link in frame 92 and Ryan/pavilion in frames 96–100 establish the **east** side. No building or bay was moved or mirrored. Measured face57 remains at U72.739..75.319. V19 corrects only the east gallery roof palette: 751 roof cells become the pale smooth-quartz family while preserving exact positions, roles, properties and occupied shapes. The measured faces start at V13.78/13.93, so their attachment cells are included beyond the provisional V15 photo-control bound. Low Y88..92 ground fragments are excluded. Original roof/soffit geometry and the retained extension to V36.5 remain unchanged.

## Placement and scale

The source canvas is unchanged from v6. World registration remains X=2×east, Z=2×south and Y=2×(NAVD88−25). The facade reference origin is `[22,37]` m with axis 18.25 degrees. Original source polygons remain in their exact measured world coordinates; their longest roof edge has bearing 17.805 degrees, so the source was not forcibly rotated to the facade reference axis.

`measured-placement-audit.json` records source polygon corners, projected block landmarks and retained roof extents, in addition to the conversion formula. Local spans are:

| Measured group | Source U × V span, metres | Expected U × V span, blocks |
| --- | --- | --- |
| Athey high body/roof | 71.8097 × 24.4946 | 143.6193 × 48.9892 |
| Dining body/roof | 50.7623 × 38.7967 | 101.5246 × 77.5935 |
| West gallery | 5.5238 × 21.8402 | 11.0476 × 43.6803 |
| East gallery | 4.4938 × 21.1062 | 8.9877 × 42.2125 |
| Face57 projection | 2.5791 × 12.6578 | 5.1582 × 25.3157 |

The gallery-to-gallery court span U21.8..52.2 remains 30.4 m / 60.8 blocks. Rotated world X/Z bounding boxes should not be mistaken for local U/V dimensions. Athey high-roof source heights are H81.1719..89.1534; Dining source roofs H69.0576..79.6204. The retained face57 already contains an older photographed low-bay roof interpretation, so its raw surveyed sloped face is not claimed as an exact original height match.

Of 23,316 original roof-role cells, 881 change state: 751 shape-identical east-gallery palette substitutions, 112 low court-grade fragments (42 on sourceface52, 37 on face6, 33 on face13), and 18 north-grade slab support corrections. Every other original roof state remains identical. All **main building weather roof states** remain identical. All 68 original floor changes preserve their full occupied shape; these are exterior paving, flank band finishes and two brick/quartz return-face finishes. The six inherited sealed foundation voids at X70,Z157,Y82..87 are now backed with construction material.

## Verification and site ownership

The final source checks pass:

- Exact export: 4,880,911 occupied blocks, 420 chunks, no missing/extra/state-mismatched blocks, no clipping or material violations.
- 35 player routes and 6,633 samples: 20 original gallery routes, two gallery-to-Dining-apron turns, two central-stair halves, one full recessed corridor, nine stair-to-bay routes and the north-door route. Maximum rise is half a block.
- Positive occupied-area contacts: all 3,487 panes, all 534 pale trim components and all retained Dining partial-block backing. Main east gallery roof has 28 north and 12 south junction contacts; west has 44 north and 27 south contacts.
- Four upper wall returns: 240 inspected cells, no holes or partial gaps.
- All-height grass/support checks: zero exposed grass and zero unsupported pavement across court, both galleries, recessed arcade and north terrace/stairs. The only reported exposed substrate is 140 coarse-dirt cells inside the authentic planting strips.
- V19 versus v18: exactly 751 enumerated east-gallery roof material changes; zero occupied-shape changes, role changes or other differences.

The detailed passing records are `physical-source-audit.json`, `routes-audit.json`, `extended-route-audit.json`, `upper-junction-enclosure-audit.json`, `east-gallery-palette-audit.json`, `court-terrain-audit.json`, `site-ownership-audit.json` and `export-parity.json`. The earlier generic `exterior-audit.json` intentionally retains its strict zero-roof/floor-change result; its raw failure is superseded by the exact enumerated exceptions in `physical-source-audit.json`, not suppressed.

There are 7,849 changed state/role cells versus v6 in 1,648 columns. Ground changes include 2,519 cells in 975 columns, with inclusive world XZ bounds `[54,79]..[143,178]`. Every such column is inside the explicit site boxes `[16.1,12,57,36.5]` and `[34,-11,41,-3]` in local metres. Every changed column is inside the independently reconstructed component ownership with a 0.5 m margin. Exact before/after ground states are enumerated in the ownership audit. The coordinator must still audit neighbor overlap and three-way differences against actual campus v14; unchanged source-v6 ground must not overwrite retained campus approaches.

## Native comparison and integration checks

V17's diagnostic run `athey-v17-source-review-20260927-2014` exposed a thin upper-wall seam, corrected in v18. V18's `athey-v18-closure-review-20260927-2023` confirmed that closure and the continuous paved walk, but was superseded by the source palette correction. Final capture is `athey-v19-pale-gallery-review-20260927-2030`, with eight useful views plus warmup. The matched-source88 view places Athey left, Dining right and the east gallery ahead, matching the actual drone direction. The builder directly inspected final matched-source88, east-roof-close, Dining overview and east-passage views; the coordinator owns the complete eight-image review and native artifact provenance.

For a new reconstruction use a fresh output directory, never overwrite v19:

```powershell
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/build_hill_dining.py --profile server-assets/hill-athey-dining-refinement-20260927.json --output runtime/campus-reconstruction/athey-dining-NEW-2x
```

Audit entry points are in `runtime/campus-reconstruction/athey-dining-refinement-20260927/`. For the **final combined campus**, run the following with fresh report paths; the extended checker reads and verifies actual combined tile archives, not the source canvas:

```powershell
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python runtime/campus-reconstruction/athey-dining-refinement-20260927/audit_extended_routes.py runtime/campus-reconstruction/athey-dining-v19-2x --campus runtime/campus-reconstruction/FINAL-CAMPUS --output runtime/campus-reconstruction/FINAL-CAMPUS/athey-extended-routes.json
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/audit_hill_court_terrain.py runtime/campus-reconstruction/FINAL-CAMPUS --output runtime/campus-reconstruction/FINAL-CAMPUS/court-terrain-audit.json
```

The extended route checker reports physical pass and exact source-state parity separately. Differences may be retained campus terrain outside new work, but every difference remains listed for coordinator review. It covers the two Dining apron turns as well as all 20 baseline and 13 new routes. Continue using `audit_hill_athey_dining_connections.py` for its original combined roof/contact/state checks and the root transfer/export auditors for whole-campus provenance.

Unresolved limits remain the precise concealed gallery-end door/wall thresholds, rear/end facade opening counts, sub-block roof seams and arch curvature, fine glazing divisions, and interiors. This refinement provides explicit conservative exterior completion and tested circulation; it does not claim photographic certainty for unseen elevations or a surveyed interior plan. Rejected v7–v18 diagnostic revisions and user-rejection evidence remain preserved.
