# Tuck Hall Arena / Eccleston Rink reference handoff — 2026-09-16

Machine-readable packet: [`tuck-rink-reference-packet-20260916.json`](../../runtime/research/campus-full-detail-20260905/tuck-rink-reference-packet-20260916.json).

This packet is builder-ready for the photographed north street facade, east-end entrance and exact measured arena mass. It changes no profile, model, world, integration or native capture. Start from `runtime/campus-reconstruction/campus-envelopes-v2-ground/16003036400434C-c86ee564a0`, sample SHA-256 `928e9af394e8e3fa0720baf5b0886cc0cf2a992ab1b1f5953f2be30280212310`. The baseline visual review remains pending.

## Sources and frame

The strongest exterior source is Wohlsen Construction's [project photograph](https://wohlsenconstruction.com/project/the-hill-school-hockey-arena-and-rink/), cached as [`rink-1.jpg`](../../runtime/research/campus-full-detail-20260905/rink-1.jpg), 1400×930, SHA-256 `1c1dad69010e9891c031f3a36c5aca27004027c613bc85ae8b93cd0cec063988`. It directly shows the north street wall and east entrance. The Hill School's official 2026 drone crop controls the detached mass, pale roof and neighboring gaps. Its official [facility image](https://www.thehill.org/athletics/facilities) confirms the clear-span gabled arena interior, but does not authorize exterior openings on hidden sides. A focused primary-source search found no stronger current exterior view of the south or west elevations.

Use the campus `U/V` frame rotated `9°`: `XZ=U*(cos9°,sin9°)+V*(-sin9°,cos9°)`. Minecraft remains `X=2×east_m`, `Z=2×south_m`, `Y=2×(NAVD88_m−25)`. The five roof-face bounds in the machine packet are source **X/Z**, while facade planes are **U/V**. Do not mix them.

## Preserve the measured arena

Keep all five canonical roof faces from parent `16003036400434C-c86ee564a0`. The two main faces rise from north/south eaves near `H=61.95/62.30 m` to the ridge at `V≈−150`, `H=65.27 m`. Small faces 0 and 1 form the measured southwest projection; face 3 is a north-entry/canopy-related source face. No roof-shape exception is authorized.

The source base `H=54.4199 m` is low southwest ground. It is not a common arena floor or north-door threshold. Keep the ice/lower service level near `H=54.6 m`, while the north entry and east sidewalk sit near `H=58.6 m`. This vertical separation is essential.

The primary walls occupy `U=−12.0..53.52`, `V=−167.6..−132.4`. Preserve the roughly `10.4 m` open service passage south to Mercer and the roughly `7.8 m` corridor east to Annan. Do not merge the three athletics parents.

## North street facade

Keep the photographed north wall on one straight plane at `V=−167.6`. Through the long portion `U=−12..37.83`, use a red-brown textured masonry plinth up to about `H=59.05`, broad pale smooth panel fields from `59.05..61.80`, and a thin pale eave/fascia.

At least seven tall dark glazing strips can be distinguished in the contractor photo. Nine slots centered at `U=−8.3,−3.0,2.3,7.6,12.9,18.2,23.5,28.8,34.1` are a length-scaled reconstruction, not an exact source count. Use about `0.85 m` width, `H=59.05..61.70`, and allow `±0.75 m` end adjustment. At two blocks per metre, one-pane-wide dark slots with occupied pale heads and sills preserve the rhythm. Do not use a thick block grid for every panel joint.

The east entrance projects to about `V=−168.65` around `U=45.5`. Build the ordinary red-brick bay about `8 m` wide, with the photographed four glazed door leaves spanning roughly `4.2 m` from the threshold `H=58.6` to about `61.1`. The shallow pale canopy is bounded by `U=40.7..50.3`, `V=−170.0..−167.2`, `H=61.3..61.7`. Keep it thin, backed and connected. The exterior photograph shows a nearly level sidewalk, so do not add a monumental stair.

## Other sides and palette

The east gable at `U=53.52` is red vertically ribbed sheet cladding with pale fascia. Author the one small louver visible near `(V,H)≈(−164.7,60.05)` and leave other opening totals unresolved. Preserve the south and west shell surfaces without copying the north slot rhythm. Retain the measured southwest service projection.

Use white or light-gray concrete for broad pale panels, with smooth quartz limited to fascia, heads, corners and canopy. Use `mud_bricks` for the coarse red-brown plinth and ordinary `bricks` for the entrance. Use coherent `red_terracotta` for the ribbed side cladding, with sparse shallow relief only if needed. Keep the exact measured roof pale with smooth stone slabs/blocks or a visually tested light-gray alternative.

Pane color may change after native comparison. Start the thin north slots and entry doors with `gray_stained_glass_pane`; use black panes if gray reads too bright. Keep all panes cardinally connected with occupied heads and sills.

Acceptance requires a fresh immutable study, exact source-roof parity, the vertical grade split, straight north plane, material hierarchy, four-leaf entrance, single supported east louver, open neighbor gaps and native views that show the south/west limitation rather than inventing hidden detail.
