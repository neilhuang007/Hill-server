# Ryan Library and Chapel entry amendments — September 27

The demonstration approach has a bounded Ryan v3 candidate and a natively accepted Chapel v1 amendment. **Ryan v3 native acceptance and combined-campus acceptance are pending.** The current-campus manifest remains unchanged. These revisions repair specific visible entries; they do not claim completion of concealed elevations or interiors.

| Component | Exact integrated baseline | New candidate | Archive SHA-256 |
| --- | --- | --- | --- |
| Ryan Library, parent `160015116006-567a5eddd9` | `campus-developed-ground-v6-2x/ryan-library` | `ryan-library-entry-v3-2x` | `ca375b55ffa00ef5b1277e98076685bb21606412a75f593ee23264ce8a3c46c9` |
| Alumni Chapel, existing manual Chapel component | `campus-developed-ground-v6-2x/chapel` | `chapel-entry-v1-2x` | `e47a92b94ef03b8bf6b76a7a42e69bf556f74e2e04e323ce689aeaf7eb0c6a1d` |

All study paths are beneath `runtime/campus-reconstruction/`. Use each candidate's `world` and `camera-views.json` for the coordinator-owned native capture queue. Source artifacts and earlier revisions are immutable.

## What changed

Ryan's former archive contains no door states: both the central recessed entry and separate southwest pointed doorway are sealed glazing. The amendment opens those existing reveals, adds recessed paired doors, restores the middle entry's upper panel rhythm, and adds the separate southwest landing/stair flight shown by the current drone. The latter stays within interpreted local U −10 to −0.4 m, V −9.8 to −1.6 m. Its 69.75 m rounded landing and 67.75 m apron retain the earlier interpreted grade controls.

The older arcade generator laid a half slab at Y89 and immediately erased it while clearing the passage. V3 retains v2's restoration of the declared Y89.5 walking surface in clear bays, preserving piers. Two new connected rail runs have feet embedded in supported stair columns; the six older central-flight rails are retained. Two simple recessed benches follow the 24 s entry view.

V3 also finishes the main flight's north cheek at interpreted V −33.12 m and the separator between the main and southern flights at V −9.96 m. Continuous stone-brick sides have smooth-sandstone coping following the retained rise. The separator replaces the thin unpaved DEM strip that had left tall turf/dirt pillars visible in v2. Adjacent arcade piers remain intact. These are supported site walls, not extensions of the measured building body.

The reference agent selected a coherent vanilla `smooth_sandstone` family for the dressed arcade band/arches. It replaces the saturated orange `smooth_red_sandstone` family locally, retaining every partial-block property. V3 also recolors the existing orange gable coping without changing its shape or placement. The rough historic stone-brick field and measured roofs remain unchanged. This is a pale warm stone proxy, not a claim that the historic arcade uses the addition's documented Dietenhan product.

Chapel changes are smaller: the south paired-door hinges now swing to the outside jambs, and a supported pale walk connects the east open arch to the existing Quad-side path across the former grass gap. The original east door hinges were checked and retained. Chapel's masonry, window schedules, addition, tower and all roofs remain unchanged.

## Source and scale controls

- [Ryan source study](hill-ryan-library-reference-20260905.md), its `source-manifest.json`, roof measurements and original builder/profile were read. Inspected reference images include `wohlsen-west-front.jpg`, `drone-018s.png` and `drone-024s.png` in `runtime/research/ryan-library-20260905/`. The 18 s view directly supports the separate southern flight and its two rails; 24 s supports the recessed doors, transom/panels and benches.
- [Chapel source study](hill-chapel-exterior-reference-20260904.md), the prior v11 review, current component/profile and native v14 south/east views were read. Inspected source photographs include `chapel-front-2025.jpg` and `chapel-witmer-SIDE-SHOT-2.png` in `runtime/research/hill-reference-20260904/`.
- All coordinates remain `X=2×east_m`, `Z=2×south_m`, `Y=2×(NAVD88_m−25)`. Ryan keeps its original 23.950499704° local axis and origin `(115.249079686, 42.994671715)` m. Chapel keeps its original −8.5° generator rotation and 66 m NAVD88 floor control. No building is moved to meet paving.
- Exact body/roof bounding cells are unchanged. Ryan's axis-aligned occupied envelope remains min `(230,80,12)`, max-exclusive `(316,124,101)` blocks, or 43×22×44.5 m; this rotated aggregate includes the existing addition and is not a rectangular floor-plan dimension. Chapel remains `(-26,79,-22)` to `(25,117,61)`, or 25.5×19×41.5 m.
- Ryan's measured roof is preserved cell for cell. Chapel's southern addition remains the earlier **approximately 19.6×7.7 m** interpretation of proposed SP-1, with approximately 1 m raster-reading uncertainty. Retaining it is not a new survey verification. New stairs and door dimensions remain photograph/grade interpretations.

## Verification and integration

Ryan v3 changes **2,621** state/role cells, all inside declared regions. Its entire 384×144×176 YZX canvas and X176/Z−16 origin match the baseline. All **8,680** original roof states remain exact. Chapel v1 changes **129** state/role cells; its 384×170×160 canvas and X−80/Z−80 origin are exact, including **3,318** roof states. Archive-to-Anvil comparison passes both candidates with no missing/extra/mismatched states or clipped writes.

Both candidates contain `entry-delta.npz`, `bounded-mutation-parity.json`, `entry-route-audit.json`, `entry-physical-audit.json`, `export-parity.json` and a frozen generator snapshot. All **780** changed Ryan partial cells and **10** changed Chapel partial cells pass positive-area contacts; amended panes have lateral and vertical closure contacts, and new rail feet have occupied support. The two Ryan entry routes and three Chapel entrance/arcade routes pass at 0.1-block sample spacing for a 0.6×1.8-block player, with maximum half-block steps. Chapel access is evaluated with its existing doors opened. This does not certify unfinished interiors or the larger 2×4-block envelope.

Root owns integration. Apply the **exact source-study delta onto accepted v14**, preserving unchanged v14 landscape cells. The profile explicitly records site bounds and mutation regions. Review cells whose old study value differs from the accepted combined-campus value before applying a conflicting delta. Do not regenerate the component or use ordinary assembly to overwrite the retained environment. Combined view and route verification remain required.

Ryan entry v1 is retained as **rejected**: its first new southern rails had half-slab foot gaps and sparse diagonal connections, and the newly cut glazing needed jamb/header completion. V2 resolves those physical defects but is also **rejected** after native inspection exposed the unpaved stair separator and raw north supports. Both rejected reviews are preserved. V3 is the candidate resolving those findings. Root accepted Chapel v1 after inspecting all four native views from `core-chapel-entry-v1-20260927-1520`.

Registered Ryan/Chapel garden enhancement belongs to the separate environment revision. The coordinator authorizes that work inside registered beds while preserving all architectural columns. No garden plants, tree positions or bed geometry were changed by these component amendments.

Owned code is [refine_hill_library_chapel.py](../../scripts/refine_hill_library_chapel.py) and [audit_hill_library_chapel.py](../../scripts/audit_hill_library_chapel.py). The shared Chapel builder was not modified. Rebuild into a fresh directory:

```powershell
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/refine_hill_library_chapel.py ryan-library --output runtime/campus-reconstruction/NEW-RYAN-REVISION
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/refine_hill_library_chapel.py chapel --output runtime/campus-reconstruction/NEW-CHAPEL-REVISION
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/audit_hill_library_chapel.py runtime/campus-reconstruction/NEW-REVISION
```

Native review must bind the exact archive above, inspect the actual PNGs and then record a bounded verdict. Fine tracery, historic sash/door profiles, hidden north/east Ryan openings, exact stair tread counts, Chapel fine stonework and interiors remain outside this entry amendment's completion claim.
