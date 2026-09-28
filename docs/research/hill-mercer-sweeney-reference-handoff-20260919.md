# Mercer / Day / Sweeney reference handoff — 2026-09-19

Machine-readable packet: [`mercer-sweeney-reference-packet-20260919.json`](../../runtime/research/campus-full-detail-20260905/mercer-sweeney-reference-packet-20260919.json).

This packet is builder-ready for the shared measured parent `160015116006-1f19950994`: Mercer Field House and Day Squash Center, the intervening athletics volumes, and Sweeney Gymnasium. It changes no profile, model, world, shared module or campus manifest. Start from `runtime/campus-reconstruction/campus-envelopes-v2-ground/160015116006-1f19950994`, sample SHA-256 `31c51bc88721f580d79f00f007247edc3d34c1f89aa68889db8dda268482c793`, and create a fresh immutable study.

## What the new sequence establishes

The full 1920×1080 school drone was sampled every 0.5 seconds from 258.0 through 280.0 seconds. The 45 frozen PNGs and hashes are in [`sports-drone-sequence-20260919/manifest.json`](../../runtime/research/campus-full-detail-20260905/sports-drone-sequence-20260919/manifest.json), SHA-256 `2c10a15df580b2ff2b085437feacc9efd3016bc3e5115afee360710ee00b7fa7`; the sorted frame aggregate is `0c408a80a778a43a0974236a408ac0a70a164d92558dc26432eaece9a78e59fb`. Frames through 272.0 seconds are unobscured. The large end logo partly blocks the center after 272.5 seconds, so those later frames are secondary edge and roof context only.

The closest clear 270–272 second sequence confirms three different exterior systems in one county parent. Sweeney is the historic dark red-brown brick, pale limestone and slate hall. The middle volumes are distinct red masonry and dark/low roofs. Mercer is a long brick-like plinth under a pale framed translucent/opaque band and pale ribbed sheet roofs. Do not spread any one system across the entire parent.

## Measured frame and roofs

All physical values stay in campus metres with U rotated 9° from east and V approximately south. Export remains `X=2×east`, `Z=2×south`, `Y=2×(NAVD88−25)`. Mercer occupies about `U -63.1..28.0, V -122.0..-77.45`; its main ridge is about 68.1 m and eave 64.3 m. The middle complex occupies about `U 28.0..63.8, V -122.0..-76.6`. Sweeney occupies about `U 64.0..88.1, V -126.2..-75.5`; its main ridge is 73.34 m and eave 66.2 m.

The machine packet routes the critical exact source faces by zero-based face ID, CityJSON surface number, UV bounds, height range and role. Preserve the complete 61-face source in `institutional-roof-geometries.json`, SHA-256 `da641ab5d136c99ce2d6b4ec7139d30d64fd5d1f651b050bbaaeb44dd2aca6c3`. One explicit exception is authorized: exclude tiny detached child `160015116006-1f19950994-1` at X/Z about `[117.35,-67.93]..[121.64,-62.49]`. No official aerial or consecutive drone frame supports it as part of the athletics building; it must not become an extra tower. Audit the exact excluded cells.

## Visible facade schedule

Sweeney's straight east wall is registered at `U=88.1`, from `V=-126.2` to `-75.5`. Ten tall round-headed openings are directly visible. The second and penultimate sit in shallow gabled projections. Their centers and dimensions in the packet are scaled proposals; the count and form are observed. The lower rectangular row is visible but partly hidden, so one-for-one alignment remains proposed. Keep the wall plane straight except for the two supported projections.

The Sweeney north end at `V=-126.2` has a shaped/stepped pale coping, one central tall round arch and smaller low openings. West and south door schedules remain unresolved. The school's current interior photograph confirms the multi-pane tall-arch type but does not establish exterior color.

Mercer's south wall at `V=-77.45` shows the long pale upper band over the brick plinth and three gabled interruptions near `U=-59.0, -1.5, 23.0`. The north wall at `V=-122.0` repeats the upper band and brick base, with at least two visible gabled interruptions and a service/mechanical zone. Trees prevent a complete panel or door count. Use the supplied pitch only to organize a coherent rhythm; do not report obscured bays as photographed.

## Materials and site

The ScottSimonsArchitects master plan explicitly identifies Sweeney's dark reddish-brown brick, limestone trim/accents and slate roof. Use coherent brick, pale quartz-masonry and deepslate-tile families. The photographed tall glazing is lighter and more translucent than CFTA's dark curtain wall; begin with connected light-gray panes and pale principal frames.

Mercer's material products were not found in a specification. Photographs support ordinary red-brown coursed masonry, a pale framed system with translucent and opaque fields, and pale ribbed sheet roofing. Use pane texture for fine translucent rhythm and full blocks only for principal frames. Smooth stone with same-shape smooth-quartz stairs is a bounded manufactured-roof approximation, not a claim about the real metal or coating.

Mercer drops from about 56.4 m NAVD88 at the south entrance to about 53.6 m on the north service side. Preserve stepped foundations. Keep the approximately 10.4 m Tuck–Mercer service gap, the approximately 3.7 m Annan–Sweeney pinch point, and the paved rising Sweeney–Davy strip open.

## Native acceptance

Required views are Mercer south, Mercer north/service, Mercer roof/cross-gables, Sweeney east overview and close view, Sweeney north gable, the middle join, and the Tuck/Annan/Davy gaps. Acceptance requires exact source parity outside the named detached artifact, straight wall planes, connected and backed panes/partial blocks, coherent ordinary palettes, and a `native-review.json` bound to the exact new sample or archive hash. Hidden elevations remain bounded limitations rather than copied facade patterns.
