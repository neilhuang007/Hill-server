# Chapel visual review — 2026-09-04

**V7 requires further work. The larger-area gate remains closed.** The primary
agent and an independent visual reviewer inspected the actual Minecraft views
against the current front photograph, the contractor's eastern elevation and
arcade photographs, and the school's current drone frames.

| Check | Finding and next correction |
| --- | --- |
| Southern approach | The measured grade is present, but quarter-metre steps still read as road terraces. Refine the road's supported surface and the separate landing, short entrance flight and masonry piers. Retain the measured ground datum. |
| Windows | Recessed panes and mullions are present, but the surrounds and upper tracery remain fragmented. Test finer architectural sampling on the same small footprint; make the three main lights and continuous pointed frame readable. |
| East arcade | The passage is structurally open, but reads squat and closed from the present camera. Improve arch proportions and capture a closer oblique view along the ambulatory. |
| Tower | Retain measured location/height. Replace the square tower's castle-like crenellation with its continuous slotted parapet, reduce the clock, and refine paired louvers and intermediate windows. |
| Materials and planting | The brownstone family is more appropriate than the previous mud-brick proxy. Reduce obvious texture repetition, compact copper lamp brackets, restore planted beds, and cover exposed branch stubs. |
| Sample boundary | The rectangular outer edge and void are intentional and do not fail this small-area test. |

Native evidence is in
`runtime/campus-reconstruction/chapel-native-qa/runs/v7-unattended-20260904T1620/`.
Its three PNGs have recorded hashes and validated camera poses. The live client
reports the brownstone resource pack active. Both initial conversion dialogs
were handled by the driver. The [reference report](research/hill-chapel-exterior-reference-20260904.md)
identifies the ground photographs and interpretation limits.

The machine-readable authored review is stored beside the v7 world as
`visual-review.json`, bound to the exact voxel archive and native report hashes.
It records AI reviewers explicitly; it is not a claim of user approval or a
completed Google Street View match.

The stable one-command playable profile currently uses v6. Its fresh conversion
and second launch were independently checked: the first handled both dialogs;
the second reused DataVersion 4790 without either dialog. Narration, music,
onboarding and clouds are disabled. V7's native capture is also unattended.
