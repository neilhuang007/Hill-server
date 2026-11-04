# Shared campus checks, November 3, 2026

The local preview uses V60 from `E:\projects\Hill-campus-work`, Java port
25568 and gallery port 8789. An isolated second runtime on port 25569 exercises
destructive recovery checks without changing the preview's student worlds.

The Java suite passes 260 tests. The official illustrated campus assets pass
five Python tests. These checks verify behavior, not campus appearance.

The clickable label update passes fifteen live dialog checks. Its full map
contains all 51 printed numbers, with 50 active destinations. Brookside Country
Club, number 28, explains that it is outside the preserved campus and has no
teleport action. The building zoom contains 37 active numbers. Clicking Alumni
Chapel, Shirley Quadrivium and Nam Family Field reaches the corresponding
shared campus destination without a confirmation page. The named fallback also
travels directly. Tests cover another student's callback, stale and consumed
callbacks, closing during pack loading, authentication, Undo and command closure.
The downloaded pack matches SHA1 `3c4abcb3a76fd6a4310e32a596657c7e84a1aaf3`.

The installed 26.3 client classes independently verify all 51 full map and 37
zoom label centers through the actual text widget click finder, and 179 blank
segment centers per view have no click action. The original row checks omitted
the full dialog layout and did not catch the misaligned strips Neil reported.
Both reconstructed images match the official source crops pixel for pixel. The initial wide strip
pack failed the native font atlas allocator at 360 by 9 pixels. Splitting strips
at 128 pixels makes all 558 glyphs fit. These checks use actual client geometry
and click handling, without a GPU upload or native screenshot review.

The strip regression now constructs the actual `FocusableTextWidget` used by
`PlainMessageHandler`. The old width of 362 leaves only 354 pixels after native
padding and produces 80 rendered lines in a widget 728 pixels tall. Increasing
the outer width to 370 fixes the displayed wrapping, but the final negative
spacing character still causes a second wrap during height calculation.
Removing that final spacing character fixes both calculations. Both views now
produce forty aligned rows, a 370 by 368 padded widget and a continuous 360
pixel square image. The regression checks every bitmap rectangle and inherited
click style after native text preparation. The resource pack and map images
remain unchanged.

The corrected server also passes all fifteen live dialog checks. The full and
zoom dialog packets were captured from that running server, decoded with the
installed client's component codec, and passed through its complete native
widget layout. Both captured views produce forty aligned rows and a 370 by 368
widget, with the expected image glyph order, rectangles and label click targets.
Replaying the earlier captured packet reproduces the 80 row failure. Desktop
control remains unavailable, so this evidence does not claim a live screenshot.

The official map update passes seven live held map checks. A fresh player gets
the filled map in hotbar slot 9 and the Undo clock in slot 8. Holding the map
receives all 16,384 palette pixels without accepting a resource pack. Creative
replacement and dropping are rejected. Navigation and reconnect preserve the
tools, and reconnect delivers identical artwork. The map has no position cursor
because the source illustration is not a geographic projection.

The earlier item based native dialog passed eleven live checks. It opened without an inventory
window, serves the optional pack with its advertised SHA1, and selects the
full and building zoom models in 256 by 256 item bodies. This initial protocol
check did not verify the size at which Minecraft drew the artwork. Building choices use
the official numbers, with twelve choices per page. Declining the pack retains
named navigation. Stale and other player callbacks are rejected. Close remains
closed when pack loading completes, and a command closes the current dialog.
The real destination action reaches Alumni Chapel in the shared Creative campus.
The map screen Undo callback reaches the recent edit service.

Neil's report of a tiny or apparently missing image exposed a rendering error.
Minecraft reserves the requested dialog item dimensions but still draws an
ordinary item at 16 by 16 pixels. The original resource pack omitted the model
transform needed to fill the reserved space. A regression using the installed
26.3 client's actual item codec, transforms and GUI bounds failed on the old
pack with rectangle `[0,0,16,16]`. After correcting the local model transform,
both the full map and building zoom produce `[0,0,256,256]`. The held map and
source PNGs are unchanged. This verifies native render bounds without claiming
a screenshot review of the final screen.

Ten live Undo behaviors pass across two preserved runs against the same plugin.
The protected slot 8 clock undoes an actual placement. Breaking restores the
previous block, and repeated edits reverse in order. A peer replacing a block
with the same material, or restoring it with Undo, prevents an older player
history from overwriting that work. Door and bed changes restore or remove both
parts with exact block states. An edit left for sixteen seconds is not undone.
The first run passed seven cases before an invalid oversized bed stack in the
test client stopped the bed checks. Correcting the fixture to respect the item
stack limit let both bed cases and expiry pass without changing production code.
Both temporary platforms were completely removed, with zero retained blocks.

Protocol clients simulate resource pack load status after checking the download
and its hash. They verify delivered map pixels and dialog structure, but do not
certify native screen rendering or Bedrock forms. The desktop control helper was
unavailable. The source artwork and cropped PNG assets were visually inspected.

Before the official illustration update, the campus menu smoke passed ten checks: authentication, optional resource
pack download and SHA1, all 45 tile models, named fallback, geographic selection,
confirmation, stale clicks and two students joining the same Creative campus.
Resource pack load status is simulated after downloading and verifying its bytes.
This earlier inventory menu has been replaced by the native dialog described above.

The live safety smoke passes nine checks: ordinary placement and breaking, TNT,
spawn eggs, creature buckets, both directions of lava casting, edits shared by
two students, unauthenticated isolation and a nearby building caption. All test
blocks and fluids were removed. The earlier failed run's leftovers were also
removed with exact position and material guards.

The camera smoke reproduced the reported self interaction disconnect before the
fix. After the fix, both self interaction and attack packets exit the camera
without disconnecting. Ordinary invalid self interaction remains protected.

Backups save the campus directly with Paper's synchronous `World.save(true)`
before copying files. The first live recovery experiment exposed that dispatching
`save-all flush` from another command could queue the save after the copy. A
regression now checks pending edits reach the snapshot before it is finalized.

The corrected live recovery test passes all eleven checks. Two students see the
same edits. A normal restart preserves a later gold block. Staff then restore
the chosen snapshot and both clients see the earlier blue wool block again.
The account registered after that snapshot still logs in. Direct region file
inspection confirms blue wool in the snapshot and restored save, and gold in
the preserved previous world. The isolated fixture was stopped after testing.
The preview also produced an initial snapshot and a scheduled snapshot about
five minutes apart. The successful recovery test uses the same final plugin as
the local preview.

Detailed local evidence stays outside Git:

* `runtime/local-server-control/shared-campus-build.log`
* `runtime/local-server-control/clickable-map-build.log`
* `runtime/local-server-control/map-strip-fix-build.log`
* `runtime/local-server-control/map-strip-fix-smoke-report.json`
* `runtime/campus-map-strips-20261103/native-capture-red.log`
* `runtime/campus-map-strips-20261103/root-native-capture-green.log`
* `runtime/campus-map-strips-20261103/native-layout-red.log`
* `runtime/campus-map-strips-20261103/native-layout-width370.log`
* `runtime/campus-map-strips-20261103/native-layout-green.log`
* `runtime/local-server-control/clickable-map-smoke-report.json`
* `runtime/campus-map-official-20261103-labels/native-atlas-red.log`
* `runtime/campus-map-official-20261103-labels-atlas-safe/root-native-label-hits.log`
* `runtime/campus-map-official-20261103-labels-atlas-safe/labels-verification.json`
* `runtime/local-server-control/official-map-build.log`
* `runtime/local-server-control/held-campus-map-smoke-report.json`
* `runtime/local-server-control/dialog-smoke-report.json`
* `runtime/local-server-control/dialog-sizing-fix-smoke-report.json`
* `runtime/campus-map-official-20261103-dialog-fix/client-red.log`
* `runtime/campus-map-official-20261103-dialog-fix/live-client-bounds.log`
* `runtime/local-server-control/undo-smoke-report-761779110.json`
* `runtime/local-server-control/undo-smoke-report-761947070.json`
* `runtime/local-server-control/canvas-smoke-report.json`
* `runtime/local-server-control/safety-smoke-report.json`
* `runtime/local-server-control/safety-cleanup-report.json`
* `runtime/local-server-control/camera-shared-smoke.log`
* `runtime/campus-backup-smoke/verification.json` (contains no credentials)
