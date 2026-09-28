# September 27 world download and stopping point

Construction is paused at the user's explicit request. All builders stopped and checkpointed their work. The latest combined world is **campus v19**, at **two blocks per metre**, for **Minecraft Java Edition 26.1.2** in **Creative mode**.

A separate [Minecraft Java 1.21.11 port](hill-campus-port-12111.md) of this v19 campus is also available. Choose the ZIP matching your Minecraft version.

[Download the world ZIP](../runtime/campus-reconstruction/exports/Hill-School-175th-v19-Java-26.1.2.zip) (10,746,614 bytes). Extract `Hill-School-175th-v19` into the selected Minecraft profile's `saves` folder, then open it in Java 26.1.2. The default Windows location is `%APPDATA%\.minecraft\saves`. No mods or extra resource packs are required. Double-tap Space to toggle flight; use Space/Shift to rise/descend.

The package contains the persistent demonstration save from `runtime/campus-reconstruction/campus-preview-v19-2x/saves/hill_chapel_qa`. That client closed normally after the user demonstration. The archive preserves all 79 save files byte-for-byte except `session.lock` is omitted; the world includes 28 region files and 17,532 saved chunks after native conversion/player exploration. The 15,624 authored campus chunks are included. ZIP CRC and every archived file's SHA-256 match passed. The [export report](../runtime/campus-reconstruction/exports/Hill-School-175th-v19-export-report.json) records complete provenance and file hashes.

ZIP SHA-256: `dd412c284c922893db9fd1cf36895a123b10a5533bbdbb98b9d1a3a189be2e04`.

V19 contains the corrected Athey/Dining recessed arcade, compact central stair, attached covered galleries and paved court, the Ryan/Chapel entry connections, and the detailed core garden/path environment. Root inspected 22 useful native screenshots in two completed runs, including the benches, bell, planting, court, gallery joins and entrance thresholds. Full export, preservation and documented physical route checks are recorded in [v19 native review](../runtime/campus-reconstruction/campus-context-v19-2x/native-review.json). Acceptance is bounded to these core exterior checks; the whole campus and interiors remain unfinished, and 23 older measured shell components remain.

The following work is preserved separately and is **not included in the download**:

- `wendell-v1-2x`, `ferenbach-v1-2x`, `robins-outline-v1-2x`: generated rough studies with export/geometry checks; native review and integration pending.
- `warner-outline-review-20260927`: retained measured-shell review; no new integrated facade.
- `lehrman-outline-draft-20260927/working-handoff.json`: incomplete, unexecuted generator checkpoint; no new world exists.
- `campus-exterior-draft-20260927/roads/plan-v2`: latest complete road/parking plan; no application/integration. Its roughly six-metre inherited CFTA source-layer drive gap remains unresolved. Plan-v3 was interrupted and is incomplete; see `roads/STOP-CHECKPOINT.md` before resuming.

`server-assets/hill-campus-current.json` and `Open-Hill-Campus.cmd` still select the earlier v14 save. This v19 download is explicitly separate; no server deployment or launcher selection change was made. Previous worlds, player saves and rejected diagnostic revisions remain preserved. Read the [session checkpoint](../runtime/campus-reconstruction/core-demo-20260927/working-handoff.json) before any future continuation.
