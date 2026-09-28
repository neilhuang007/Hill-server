# Wendell measured exterior outline — September 27, 2026

Status: **native-ready, not yet visually accepted or integrated**. The user's new rough-campus construction instruction supersedes the September 19 research stopping point. No Minecraft client was launched by this builder. The coordinator owns the six native views and any acceptance of this exact archive.

Study: `runtime/campus-reconstruction/wendell-v1-2x/`. Owned generator: `scripts/build_wendell_outline.py`; independent route/site auditor: `scripts/audit_wendell_outline.py`. The exact generator and auditor are copied into the study. The source envelope, previous studies, shared geometry helpers and current manifest were not changed.

## Frozen inputs and resulting geometry

- [Reference handoff](hill-wendell-reference-handoff-20260919.md), packet `runtime/research/campus-full-detail-20260905/wendell-reference-packet-20260919.json`, SHA-256 `a8249734e35fd9075d03aced08ff1cf80c9c2cbfe2ab7a00b4d0ab82555a6de7`.
- Roof analysis SHA-256 `c0958eff5a50928295fe96daded33af24daf46435a2f88da238926fd46098b35`; CityJSON SHA-256 `b5dd39b48b012224388a9d1310b22897ebca9ca40c1bcb5a4ef77075602478e8`; terrain SHA-256 `856bbb182f037ed014e7146c03b7d7909c4b002cb7b3563b52eb5ee6aca46216`.
- Exported archive SHA-256 **`d80e83490cede15f29a88200462a08a2f0f5623dd6ae4dc03eeb1fa886cf958d`**.
- Source frame is unchanged: two blocks/metre, X east, Z south, Y = 2 × (NAVD88 − 25). Local origin X/Z `[185.82813550955873,-0.9368977071072428]` m; U bearing `-24.909373923820297°`.
- Architectural roof faces **0,1,2,3,6,7,8,9,10,12** retain their exact source polygons, planes and quantized caps, including both hips and the small south interruption. Source maximum is H80.595 m. The coherent gray polished-andesite full/slab/stair family preserves the original cap state shapes.
- Source RoofSurface faces **4,5,11 are explicitly reclassified as at-grade site surfaces**. They are excluded from architectural roof/wall extrusion and become supported smooth-stone/slab walks or rising approach strips on their exact source planes. This is ten-face architectural parity, not a claim of unchanged thirteen-face building geometry.
- Brick walls follow the measured boundary planes; inward-only cardinal bridges close rotated raster corners. North and south keep their measured 3 m grade difference. Measured exterior sample medians are H65 north and H68 south after quantization.

## Observed and interpreted openings

The north's four-row rhythm is observed; its seven-bay completion, exact centers, dimensions and sills remain the frozen packet's interpretation. The study has 27 north windows: the last interpreted basement bay is omitted for the single source-bounded entry. There are five aligned west openings, including the attic, as supported by the source stack. Glass is light-gray pane; pale gray slab heads/sills and one restrained basement belt have inward brick backing. The half-metre grid uses pane texture for the fine paired sash divisions instead of oversized masonry mullions.

South and east remain closed masonry because their opening schedules are unresolved. No connector, porch, additional wing or roofed passage was invented.

## Entrance and immediate connection

The partly photographed dark north opening near the clipped east end supports **one provisional entrance**, registered near U14.5 m with the packet's ±1.2 m tolerance. Its exact placement is not a survey claim. A single open dark-oak Minecraft door sits in a four-block-high dark recess. The one-block-wide corridor is a coarse grid proxy for the approximately 1 m source opening; it has 0.8125 blocks of clear width at the open door and passes the actual 0.6 × 1.8-block player test.

| Anchor | Native X, feet Y, Z | Physical standing height |
| --- | --- | --- |
| Exterior apron / campus connection | `[392.5,81,-26.5]` | H65.5 m NAVD88 |
| Door | `[392.5,81,-24.5]` | H65.5 m NAVD88 |
| Interior endpoint | `[392.5,81,-21.5]` | H65.5 m NAVD88 |

The short route follows X392.5 from Z−26.5 to Z−21.5 at Y81. Its 55 samples at maximum 0.1-block spacing pass occupied-shape collision and foot support checks, with zero vertical step. This certifies the entrance connection only, not circulation through an unfinished interior or the wider campus approach.

`connection-anchors.json` holds the exact route. `detail-register.json` holds each exact site-strip column and its measured/quantized surface Y. Assembly site bounds are UV `[-22,-8,22,9]` m, plus 0.5 m margin. The resulting 3,215-column ownership mask includes all 2,369 authored architectural/site columns without omissions.

## Verification and review boundary

The exact Anvil export matches all **992,206 occupied blocks** with no missing, extra or mismatched states, no material violations and no clipped writes. The 300 panes form 32 supported components; no unbridged diagonal pairs, disconnected cardinal pairs, incomplete perimeter candidates or pane head/sill physical-contact failures remain. Roof cap heights and full backing pass; every partial architectural block has physical support/contact.

`all-height-enclosure-proof.json` passes **64 lower/upper-half facade slices from Y81 through Y112**. The single registered entry corridor is explicitly closed only in this enclosure test; its actual open geometry is checked independently by the player route. The proof certifies physical closure of the tested facade/roof section, not photographic completeness.

`site-route-ownership-audit.json` checks 26,028 exterior columns: no missing ground or subsurface gaps, no unauthorized exterior changes, and 25,791 completely unchanged exterior columns. Exact source footprint gaps remain Ryan 15.025 m, Music House 21.723 m and Meigs 66.923 m. Proposed ownership does not intersect those source footprints; the coordinator must still compare every combined component ownership mask before integration.

Six frozen packet cameras cover north overview, windows, west hip, east approach, south limitation and roof. Their eyes are in air in this standalone export. Root must inspect actual native PNGs, compare the supplied source images, check the entry and grade strips, bind the native capture to this archive, and only then change the pending native review status. Integrated camera air checks and whole-campus state preservation remain separate requirements.

Known limits: approximate window centers/sills and entry registration; simplified paired sash texture; unknown exact roof/trim products; concealed south/east details; hollow, unfinished interior; native appearance still unreviewed. This is a usable rough measured exterior, not a claim of finished reconstruction.

```powershell
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/build_wendell_outline.py --output runtime/campus-reconstruction/wendell-NEW-2x
uv run --python 3.13 --with numpy --with scipy --with shapely --with nbtlib --with pillow --with pyproj python scripts/audit_wendell_outline.py runtime/campus-reconstruction/wendell-NEW-2x
```
