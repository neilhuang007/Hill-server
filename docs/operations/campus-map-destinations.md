# Official campus map destinations

The bundled [destination data](../../src/main/resources/campus-map-destinations.json) accounts for all 51 numbered labels in the FY26 official illustrated map. It supplies 50 campus destinations and explicitly marks number 28, Brookside Country Club, unavailable. The shared campus boundary is preserved.

Names come from the legend of `runtime/campus-map-official-20261103/FY26CampusMap_Labeled.pdf`, checked by text extraction and inspection of its complete rendered page. Its SHA256 is `a815cf8e058df9bdbb2997fba3a272249508e7175c536b907f984e9966477e59`. Parentheses retain the legend's village and residence descriptions. Number 19 includes both the tennis center and pavilion named by that legend.

World coordinates come from the existing measured catalog, registered source polygons, or explicitly approximate reconstruction controls. No world position was inferred from the oblique illustration's pixel coordinates. Coordinates use the established frame, `X=2*east_m`, `Z=2*south_m`. Each record includes its source path and derivation.

## Building complexes

Building destinations use the same integer midpoint calculation as `BuildingCatalog.centerX()` and `centerZ()`. Number 4 shares the measured Athey and Dining footprint with number 3. Number 13 shares the measured Mercer, Day Squash and Sweeney footprint with number 12. These aliases deliberately use the same destination, because the catalog does not establish surveyed internal divisions.

Number 19 uses an existing Reese court, rather than the approximate Kipp pavilion footprint. Number 26 uses the registered Madden playing field, rather than the approximate press box. Their display names follow the current official map.

## Outdoor source controls

| Labels | Source and choice | Approximate |
| --- | --- | --- |
| 5 | Existing gravel garden terrace in `scripts/hill_audit_zone_athey_20261012.py`, local rectangle `[-17,82,3,114]` transformed by the recorded building frame | Yes |
| 10 | Standing point `(393,-444)` from `E:/projects/Hill-campus-work/runtime/research/videos-20261017/s3/locate.md`, located by panorama bearings and registered aerial geometry | Yes, approximately 3 blocks |
| 11 | Standing point `(318,-243)` from `E:/projects/Hill-campus-work/runtime/research/videos-20261017/s5/locate.md`, on the west pond bank, not in the water | Yes, approximately 3 blocks |
| 16, 19 | Registered tennis polygons `way/1488359323` and `way/956158568` in `source-sports-inspection.json`; ten blocks along each court's existing long axis from its center, avoiding the net | No additional approximation |
| 17, 18, 20, 22, 23, 24 | Centroids of registered field polygons `way/263155609`, `way/263135533`, `way/324146950`, `way/324146948`, `way/324146943`, `way/324146944` respectively | No additional approximation |
| 21 | Existing Jim Long mound control from `sports-completion-v1.json`, derived from georeferenced PEMA imagery | Yes |
| 26 | Center of the existing Madden field registration in `madden-fixtures-v1.json` | Yes, source fit uncertainty 7 to 8 metres |
| 27 | A point ten blocks beyond the existing inner track radius along its recorded short axis, within its 19.52 block lane band | Yes, PEMA controls approximately 3 pixels |

The full sports polygon source is `runtime/campus-reconstruction/exterior-completion-20261002/source-scan-v1/source-sports-inspection.json`, SHA256 `b8ac00c75c70e5f487a17b4d64ebd28699d9b3fc909003bd776935b53e1eb7ea`. Field identity joins are retained in `scripts/hill_sports_completion_20261003.py`. Number 22 represents the southern existing practice field within the broader Far Fields Athletic Complex. It does not claim a new entrance or a unique center for that entire complex.

The detailed Jim Long and Hauser controls are in `runtime/campus-reconstruction/exterior-floating-20261003/sports/sports-completion-v1.json`, SHA256 `a83cc498540bd3f12a8501a1ff478fc9d4dcc8d6fafd8b20f19dcff15d4b9a33`. The Madden controls are in `runtime/campus-reconstruction/exterior-completion-20261002/research/madden-fixtures-v1.json`.

## External label 28

`runtime/research/quad-landscape-20260905/campus-completeness-checklist.json` explicitly identifies Brookside Country Club as external context. Its cached geographic polygon is OSM `way/62119320` in `E:/projects/Hill-campus-work/runtime/research/v40-pass-20261015/gis/overpass.json`.

Transforming that polygon using the existing ECEF campus transform and intersecting it with the preserved V60 crop leaves only a boundary sliver of approximately 0.28 square blocks. It cannot provide a meaningful golf course landing. The record therefore contains `available:false`, the explanatory `unavailableReason`, source evidence, and no `x`, `z`, or `buildingId`. No substitute campus location is presented as the country club.

## Coordinate checks

All 51 numbers occur exactly once. All 50 available destination cells lie within `[-576,-1600,1471,415]` and within the preserved V60 crop. The eight destinations derived directly from sports polygons also remain inside their respective source polygons after rounding to blocks. These checks establish coordinate consistency, not exterior appearance or live teleport acceptance.

The crop source is `E:/projects/Hill-campus-work/runtime/campus-reconstruction/campus-context-v60-2x/campus-crop.geojson`, SHA256 `e0ab5989cb0f849210c23cc96cae5005650904c579d8895da650d49b45db82ed`. The measured building catalog is `src/main/resources/hill-buildings.yml`, SHA256 `70d9c70c198e0eb273c80d58484771d9f0f8ee66004fce113cc62853a283c1a1`.

The actual coordinate check command, complete Python input, timestamp, source hashes and result are recorded in `runtime/local-server-control/campus-map-destinations-validation.json`. It ran as `py -3.14 -c <recorded command[3]>` from `E:/projects/Hill-server`. It checked each available destination's block center `(X+0.5,Z+0.5)` against the crop polygon scaled from local metres to blocks. The result was 50 supported cells, no failures, approximate numbers `[5,10,11,21,26,27]`, and unavailable number `[28]`. This was a read only coordinate check; it did not inspect or modify world appearance.

## Complete mapping

| Number | Official label | World X, Z | Destination | Approximate |
| --- | --- | --- | --- | --- |
| 1 | Meigs House - Admission Office | 400, 173 | meigs-house | No |
| 2 | John P. Ryan Library | 272, 54 | ryan-library | No |
| 3 | Athey Academic Center | 102, 149 | athey-dining | No |
| 4 | Dining Hall | 102, 149 | athey-dining | No |
| 5 | Class of 1971 Garden | 6, 164 | Outdoor point | Yes |
| 6 | Alumni Chapel | -2, 17 | alumni-chapel | No |
| 7 | Warner Center for Spiritual Life and Equity | -84, -136 | warner-center | No |
| 8 | Davy Hall Dormitory | 259, -196 | davy-hall | No |
| 9 | Center For The Arts (CFTA) | 379, -338 | center-for-the-arts | No |
| 10 | CFTA Lot | 393, -444 | Outdoor point | Yes |
| 11 | The Dell Pond | 318, -243 | Outdoor point | Yes |
| 12 | David H. Mercer Field House and Jerry Day ’37 Squash Center | 70, -188 | mercer-sweeney | No |
| 13 | Sweeney Gymnasium | 70, -188 | mercer-sweeney | No |
| 14 | Edward Tuck Hall Arena and Thomas Eccleston Jr. Rink | 86, -292 | tuck-eccleston | No |
| 15 | Annan Building | 194, -277 | annan-building | No |
| 16 | Chapel Tennis Courts | -79, 27 | Outdoor point | No |
| 17 | Wells-Davidson ’16 Soccer Pitch | 571, 21 | Outdoor point | No |
| 18 | Dell Field | 589, -383 | Outdoor point | No |
| 19 | Reese ’75 Tennis Center / Kipp ’46 Pavilion | 734, -509 | Outdoor point | No |
| 20 | Nam Family Field | 967, -625 | Outdoor point | No |
| 21 | Jim Long Field | 721, -852 | Outdoor point | Yes |
| 22 | Far Fields Athletic Complex | 668, -1172 | Outdoor point | No |
| 23 | Harry L. Price Field | 833, -1065 | Outdoor point | No |
| 24 | Briggs S. Cunningham ’26 ’50 Field | 988, -1249 | Outdoor point | No |
| 25 | Lehrman ’56 Pavilion | 1016, -1088 | lehrman-pavilion | No |
| 26 | Madden Stadium | 1013, -922 | Outdoor point | Yes |
| 27 | William West Hauser ’81 Track | 1202, -1053 | Outdoor point | Yes |
| 28 | Brookside Country Club | Unavailable | Outside the shared campus | No |
| 29 | Hunt Upper School Dormitory | 158, -64 | hunt-hall | No |
| 30 | Wendell Dormitory | 371, -2 | wendell-dormitory | No |
| 31 | Ferenbach Dormitory (Dell Village) | 625, -114 | ferenbach-dormitory-dell-village | No |
| 32 | Senter Dormitory (Dell Village) | 613, -162 | senter-dormitory-dell-village | No |
| 33 | Lowndes Dormitory (Dell Village) | 667, -176 | lowndes-dormitory-dell-village | No |
| 34 | Scheerer Dormitory (Dell Village) | 679, -129 | scheerer-dormitory-dell-village | No |
| 35 | East Campus Faculty Village | 924, -107 | east-faculty-village | No |
| 36 | Foster Dormitory | 707, 89 | foster-dormitory | No |
| 37 | Rolfe Dormitory | 564, 152 | rolfe-dormitory | No |
| 38 | Feroe House (Head of School Residence) | -345, 64 | feroe-house-head-of-school-residence | No |
| 39 | Thomas House | -349, -51 | thomas-house | No |
| 40 | Pine Court Faculty Village | -288, -127 | pine-court | No |
| 41 | Sherrerd Dormitory (Dutch Village) | -234, -11 | sherrerd-dormitory-dutch-village | No |
| 42 | Johnson Dormitory (Dutch Village) | -196, -47 | johnson-dormitory-dutch-village | No |
| 43 | Markle Dormitory (Dutch Village) | -140, -48 | markle-dormitory-dutch-village | No |
| 44 | Robins Dormitory (Dutch Village) | -120, 11 | robins-dormitory-dutch-village | No |
| 45 | Hillrest Dormitory (Dutch Village) | -207, 78 | hillrest-dormitory | No |
| 46 | The Sherrill Guest House | 571, -111 | the-sherrill-guest-house | No |
| 47 | Music House | 322, -58 | music-house | No |
| 48 | Class of 1960 Alumni House | -318, 190 | class-of-1960-alumni-house | No |
| 49 | Hillhouse & Moore Business Office | -396, 181 | hillhouse-moore-business-office | No |
| 50 | Shirley Quadrivium Center | 230, 211 | shirley-quadrivium | No |
| 51 | Gatehouse | 768, -399 | gatehouse | No |
