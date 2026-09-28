# Hillhouse & Moore Business Office — individual west elevation, 2026-09-08

[Business Office v4](../../runtime/campus-reconstruction/business-office-v4-2x/manifest.json) is exported for native review, with **471,173 blocks, zero clipped writes and zero material-role violations**. The [world](../../runtime/campus-reconstruction/business-office-v4-2x/world), [six cameras](../../runtime/campus-reconstruction/business-office-v4-2x/camera-views.json), [archive geometry audit](../../runtime/campus-reconstruction/business-office-v4-2x/geometric-validation.json) and [shared pane audit](../../runtime/campus-reconstruction/business-office-v4-2x/pane-perimeter-validation.json) are ready. Archive SHA256 is `bf87cc2451ad924924a0fc437479307819730afd3fb3ba55935fa0cff6308a4a`. The six v2 native views reject the bordered masonry facade appearance and a disconnected terrace corner. V4 combines the connected terrace with Sol's ordinary-andesite facade field. Native comparison of the new surface remains pending. Unseen elevations are not complete.

## Supplied evidence and identity

Sol's build-ready packet is [hillhouse-moore-business-office.json](../../runtime/research/sol-reference-20260908/hillhouse-moore-business-office.json), SHA256 `089e33a46ec564e52a4064eef93183ca6e0566a4f42f3a341fae9f0a355a0ada`. I inspected the packet and its supplied [August 2019 west-elevation photograph](../../runtime/research/campus-full-detail-20260905/business-office-bailey-streetview-2019.jpg) before modeling and again during geometry verification. The [Street View panorama](https://www.google.com/maps/@?api=1&map_action=pano&pano=MaglwSohOgIjzpPSF6LNTA&heading=90&pitch=0&fov=70) looks east from North Bailey Street. The local image hash is `e8d47bd0d7a15cc14c3440265153151999ad8adfe3bd742aa5dd7746897010ba`. It establishes observed appearance in 2019, not the present paint date.

The combined measured parent is `1600151000041C-510dc616b8`, Hillhouse & Moore Business Office, current school map number 49 and older facilities number 63, at 701/703 High Street. The model does not invent an internal boundary between the two addresses. No new reference collection or independent palette research was performed during this modeling pass.

The photograph shows a rough warm-gray rendered wall, three upper singles on the main west plane, one lower single and a lower triple group, a two-level polygonal bay with tall facet sashes, and a white-railed northern terrace above a partly obscured lower opening. The far-right lower sash and clipped upper sash are recorded individually as partial observations. Shrubs conceal much of the base and all reliable door thresholds. No door or mirrored north/east/south window row is invented.

## Metric geometry and qualified roof correction

The exact measured footprint is **318.8028108233 m²**, represented by 1,276 half-metre columns. The frame origin is XZ `[-202.97506878786803, 77.52887282145714]` m, with local U rotated 8.975271921° from east. It uses `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`. There is no translation, rotation correction, rectangular replacement footprint or changed campus gap. Terrain is the corrected native 0.5 m [campus-full-detail-terrain-v2](../../runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz), SHA256 `856bbb182f037ed014e7146c03b7d7909c4b002cb7b3563b52eb5ee6aca46216`.

All twenty ordered original roof faces, polygons, planes, part IDs, surface indices and original fingerprints remain in provenance. Main ridge control is 61.246059 m NAVD88 and source roof RMSE is 0.431629 m. The main higher roofs, all 250 columns assigned to northern low face16, and all 37 columns of low southern face7 keep their original height samples. Face16 is compatible with the photographed northern appendage and has no deletion evidence.

Source face4 contains near-ground samples at the directly photographed two-storey bay. Root authorized the bounded geometry qualification: a ground-height face cannot be its visible upper roof. The authored six-vertex bay lies within the measured protruding footprint and overlays **only fourteen face4 columns**, with an estimated shallow cap rising from 57.0 to 57.35 m NAVD88. Those affected ground heights are explicitly superseded, not claimed exposed or unchanged. The remaining **1,262 source-height columns have maximum delta 0 m**, with zero authored columns outside the original footprint. The unseen cap slope, dimensions and height remain estimates.

The main west wall is interpreted as a planar rendered skin at U1.8 m behind the measured eave, over V3.8–11.7 m. This is a photo-based wall interpretation; the roof outline itself is not a surveyed stucco line. The two-storey bay follows its separately documented polygon. Floor levels 50.75/53.75/56.75 m are functional estimates from grade and storeys, not photographed thresholds. Local perimeter terrain varies around 49.22–50.46 m; no invented entrance has been graded to an arbitrary register ground value.

## Openings, trim and construction closure

Fourteen individually labelled opening groups cover the observed main singles/triple, partial edge windows and six bay-facet sashes. White stained panes occupy the outer wall sheet, with no duplicate projecting opaque frame. Original pane borders approximate white sash perimeters and meeting rails. The grid approximates the triple group; its exact three sash widths and fine muntins require native comparison.

Each aperture records its authorized wall/reveal cells. Necessary diagonal returns stay within those cells and retain masonry. The front and southern bay cheek initially removed the same inboard stucco corner; one continuous rendered corner column now separates those sashes. It is a wall corner, not a large white jamb. Lower tall bay and far-edge sash heights are estimated at 2.2 m, allowing separate contacting head/sill courses after grid rounding. Upper bay sash heights remain estimates. The supplied photograph clips their highest heads.

Quartz half-slabs provide sills and plain lower-window heads. Sparse weathered-copper slabs represent the tiny green driphoods. Three upper bay head cells meet the estimated roof cornice and retain its existing solid body; forcing separate half-slab hoods there would cut away the roof. Twenty-four concealed full backing cells close the unused halves of the thin window caps. The final archive has **165 panes in twelve supported components**, zero unbridged diagonal pairs, zero disconnected adjacent pairs, zero horizontal free ends, and zero vertical air/reversed-slab contacts. **All 53 partial caps have immediate full interior backing.** These checks are independent of merely finding one supporting block per component.

The northern terrace uses eight narrow pale-oak fence columns and one continuously connected upper L rail. Each post starts at the actual retained roof surface. Six bottom roof slabs need a bounded foot in the existing dark roof family, filling the quarter-metre interval below the post. The previous full white feet read as a heavy pedestal in native views and were rejected; these localized dark foot overlays do not flatten or delete face16. Original vanilla model elements establish positive contact area for all eight post bases. White timber-joint texture and approximate rail extent remain limitations.

The rendered field covers 139 exposed structural floor ends, removing an invented broad smooth-stone foundation stripe. Interior floor plates remain inside the shell. The archive audit checks visible west-facing floor ends with outward rays; air beside a hidden interior floor is not itself classified as an exterior wall hole.

All fourteen authored bay columns retain the exact intended quantized top surface. All nineteen neighboring bay-cover column pairs have positive-area contact through roof skin or its immediate solid fascia substrate. Eighteen have direct roof/trim contact; one stepped eave pair uses the immediate full fascia substrate. The audit records that distinction and limits substrate to one block beneath the sampled roof. Neither porch posts nor arbitrary full wall towers are counted as roof continuity. Unobserved main roof contacts are not globally reinterpreted from a clipped photograph.

## Real materials and original vanilla proxies

The profile carries its own `material_review` and evidence packet hash. Sol verified the appearance choices; Minecraft names do not identify the real building substrate or roof product. The original 26.1.2 client textures are used without custom assets or checkerboard mixtures.

| Role | Actual observation | Original vanilla proxy and limitation |
|---|---|---|
| Wall and covered structural ends | Warm-gray rough/stippled render; system and substrate unresolved | One coherent `andesite` field after Sol's native addendum. Lit raw/equal-L ΔE00 4.576/2.464; shaded 3.305/3.292. It removes the explicit polished block border; its irregular grain still simplifies real fine stucco. |
| White trim and sash | White painted sashes, fascia and rails | Quartz slabs/blocks, white stained panes, and narrow pale-oak fence rail shapes. Pane grids and off-white timber joints simplify the finer painted members. |
| Tiny green caps | Thin dark green metal-like profile, actual alloy/paint unresolved | Sparse `waxed_weathered_cut_copper_slab`. The ROI is deeply shadowed and the match is not strong; native brightness/cyan cast needs review. Sol permits a dark deepslate slab fallback if necessary. |
| Major pitched roof | Clipped dark roof edge; actual product unresolved | Provisional `deepslate_tiles` with original slabs/stairs. No roofing product or full visible silhouette is inferred from the photograph. |

Light-gray concrete is darker than the observed wall, with lit raw/equal-L 10.084/5.067 and shaded 5.180/2.431. Smooth stone gives a closer lit colour, 4.226/2.311, but loses the observed rough texture and has its own edge repetition. The selected ordinary-andesite texture hash is `7c7960dd3dd2084233907c1529dcbea0b8a2195fadaa608027f395b6f430fbd7`. Polished andesite was superseded after native pattern review. These are supplied image-appearance comparisons with unknown illumination, not recovered material reflectance. There is no blanket brick, ore, sculk or invented sandstone assignment.

## Validation and native handoff

The [reusable archive audit](../../runtime/campus-reconstruction/business-office-v4-2x/validate-geometry.py) reads final exported states and the original model cuboids. It verifies roof provenance/masks, exact source-height preservation, slab contact and immediate backing, terrace contact, bay top heights and fascia contact, visible floor ends, and input hashes. The separate shared perimeter CLI also passes with zero candidates. The v1 diagnostic render was used to inspect layout before the cornice/floor-rim correction; it is not a native material verdict. V1 was withheld from native handoff.

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/build_hill_detailed_buildings.py --profile server-assets/hill-business-office-reference.json --output runtime/campus-reconstruction/business-office-v4-2x --terrain runtime/campus-reconstruction/campus-full-detail-terrain-v2/terrain.npz
```

| Native camera | Eye U,V,NAVD88 m | Target U,V,NAVD88 m | Comparison |
|---|---|---|---|
| `office-primary-west` | −14,10.5,51.1 | 1.8,10.5,53.3 | Supplied west photograph, asymmetric opening count and bay. |
| `office-west-sash-close` | −9,7.7,52.1 | 1.8,7.7,53.8 | Sash proportions, triple group, cap thickness and wall depth. |
| `office-polygonal-bay` | −8,10,52.2 | 0.7,12.9,53.8 | Separate angled sash faces, retained stucco corner and solid cornice. |
| `office-north-terrace` | −7,−6,56 | 3.4,2.5,53.8 | Preserved low appendage, rail placement and post feet. |
| `office-roof-audit` | −15,27,66 | 7.5,12,56.5 | Original high roofs and bounded estimated bay cap. |
| `office-unseen-east-south` | 27,30,54.5 | 9,16,54.5 | Record unresolved elevations without a likeness claim. |

Native review should judge the ordinary-andesite rough gray field and removal of the explicit square border, small green cap brightness, window proportions and meeting rails, the actual bay projection/corner, and the northern terrace. Exact camera registration, rail bounds, the bay cap and incomplete edge windows remain estimates. Doors, thresholds, northern/eastern/southern openings, current paint and roof product remain unresolved. The unit is ready for that bounded native review, not declared photographically complete.


## Six-view native verdict and bounded v3 terrace correction

All six v2 native views were inspected against the supplied Bailey photograph. The [hash-bound v2 verdict](../../runtime/campus-reconstruction/business-office-v2-2x/native-review.json) rejects integration pending the terrace correction and facade review. Pane contacts, asymmetric openings and the attached two-storey bay are present and closed. The real fine warm-gray render reads in native as dark, square-bordered masonry; root independently identified the same mismatch and asked Sol to verify the already supplied alternatives. No new material was improvised during this geometry pass.

The north-terrace camera exposed a true disconnected railing corner. Samples near the rotated low-roof boundary had been discarded when their rounded cell belonged to low ground face17 or lay outside the measured outline. V3 snaps only those intended rail samples to the nearest retained face16 support, maximum distance 0.505741 m, and inserts the necessary orthogonal return. The complete eight-column rail now has one connected component, reciprocal adjacent fence states and positive original-model post contact at every base. Source16 height samples are unchanged; six local quarter-metre post feet remain explicitly authored surface overlays.

All 165 pane coordinates and exact states are identical to v2, as are the bay plan, roof heights, terrain and six cameras. The fine white pane edges remain thinner than the photographed painted bay sash; adding projecting opaque frames would compromise the wall plane. That width limitation, the intrinsic pane depth and approximate sash proportions remain explicit. No upper roof/terrace enlargement was inferred from the clipped photograph.

The [v4 native-review record](../../runtime/campus-reconstruction/business-office-v4-2x/native-review.json) remains pending. It asks for the north-terrace comparison after the bounded correction and a fresh native comparison of Sol's specified facade proxy. Native material likeness is not yet accepted.


## Sol facade addendum and exact v4 state delta

The [Sol native-material addendum](../../runtime/research/sol-reference-20260908/hillhouse-moore-office-native-material-addendum.json), SHA256 `f513d3bfcf2051bb1a85dbf1094228bf2d1f0fddc89ef1f2fdd2880614725325`, supersedes the polished-andesite choice. Ordinary andesite removes the explicit square-unit border and improves the supplied lit ROI from raw/equal-L 5.437/3.342 to 4.576/2.464. Its shaded score 3.305/3.292 is slightly worse but remains close; continuous render pattern controls the choice. Light-gray concrete is too dark/olive, smooth stone repeats its own dark edge, and white concrete is too bright/cool. This is a visual render proxy, not a stone-substrate claim.

The [exact material delta](../../runtime/campus-reconstruction/business-office-v4-2x/material-delta-validation.json) compares all 471,173 archived blocks against v3. Exactly **4,990 facade-role states** change from `polished_andesite` to `andesite`. Coordinates, roles, all remaining blockstates and camera file are identical. Glazing, quartz trim, green hoods, roof, bay, corrected terrace, terrain and campus gaps are unchanged. All archive geometry, backing, rail and shared perimeter checks still pass. Root will capture v4 directly; no v3 native acceptance is implied.
