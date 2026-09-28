# Hill Chapel study and repeatable Minecraft checks

The accepted small trial is `runtime/campus-reconstruction/chapel-study-v11`:
the Alumni Chapel and an 80 × 85 metre patch of surrounding terrain, at two
Minecraft blocks per metre. Its recorded native visual review passes and permits
work on the next bounded area; each larger result still needs its own review.

The earlier [v7 visual review](hill-chapel-visual-review-20260904.md) requested
architectural and landscape changes. V11 incorporates the follow-up corrections:
curved connected window tracery, stone arcade cornice, slotted square-tower
parapet, smaller open metal clock, fine louver blades, a Latin cross, timber
entrance panels and glazed head, compact lanterns, planted beds, supported
paving stairs, and the three upper windows on the west side of the addition.
The [v11 review](hill-chapel-visual-review-v11-20260904.md) records the comparison
and its remaining survey and resolution limits. Both reviewers are AI agents.

## Open the saved replica

Run `Open-Hill-Chapel.cmd` from the repository root. The dedicated client uses
the locally installed Minecraft **26.1.2**, a separate game directory, and its
own saved options. It starts at the Chapel approach in creative mode.

The current saved game is in `runtime/campus-reconstruction/chapel-native-qa/playable-v11`.
The earlier saved profiles are retained in their own directories.

The launcher retains the converted playable world between launches. Narration,
the narrator shortcut, music, clouds, and onboarding are disabled in this
profile. The brownstone material pack is selected before resources load.
Fresh source worlds receive a backup and pass through Minecraft's own file
conversion; both the backup confirmation and the successful conversion's
join confirmation are handled by the test driver. World version tags are not
falsified to hide a conversion requirement.

Normal Minecraft accounts, saves, and options are separate from this profile.
The local test profile uses an offline player identity and does not connect to
the production server.

## Generate and audit

The measured terrain and canopy caches are separate inputs. The reproducible
generation command is:

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/build_hill_chapel_sample.py --terrain runtime/campus-reconstruction/measured-terrain/hill-chapel-measured-terrain.npz --inferred-trees runtime/campus-reconstruction/measured-terrain/hill-chapel-inferred-trees.json --inferred-canopy runtime/campus-reconstruction/measured-terrain/hill-chapel-inferred-canopy.npz --output runtime/campus-reconstruction/chapel-study-NEXT
```

Choose a fresh output name. Each output includes the exact occupied coordinates,
complete block states, per-block material roles, a fresh Anvil world, and copies
of the profile and resource pack with input hashes. Generation rejects a
material-policy violation before writing the world.

```powershell
uv run --python 3.13 --with-requirements scripts/requirements-hill-campus.txt python scripts/audit_hill_chapel_sample.py runtime/campus-reconstruction/chapel-study-v11
uv run --python 3.13 python scripts/run_chapel_native_qa.py --world runtime/campus-reconstruction/chapel-study-v11/world --reference-views
```

The independent structural audit reads the actual Anvil files. It checks exact
coordinate/state parity, material intent, complete doors, entrance connections
to the interior, foundation support, pane connections and occlusion, and input
and resource-pack hashes. V11 has **991,753 matching occupied blocks**, with no
structural or provenance failures.

The native driver positions the camera inside the actual Minecraft client and
uses Minecraft's screenshot API. Each fresh run stores its launch manifest,
logs, camera poses, PNG hashes, handled startup screens, loaded resource packs,
and native report under `runtime/campus-reconstruction/chapel-native-qa`.
A successful capture does not itself approve visual fidelity. The reference
option adds close front, arcade and oblique views to the south-front, east-Quad
and elevated captures. Each screenshot records and verifies its actual pose
and field of view.

Capture mode releases Minecraft's mouse and substitutes its no-op input object.
This prevents a held movement key or mouse movement on the shared computer from
moving the camera. An in-game held-forward-key regression probe and strict
camera readback must pass before screenshots count as evidence. Interactive
play retains normal controls. The verified six-view run is
`runs/v11-input-isolated-20260904` under the native QA directory.

To exercise the saved-world startup without manual interaction, run
`uv run --python 3.13 python scripts/run_chapel_native_qa.py --interactive --exit-when-ready`.
Run it again to test reuse of the already converted save. A fresh profile
handles the backup and conversion-complete join screens; the repeat launch
opens the retained save directly.

## Material and geometry decisions

- Brownstone masonry uses ordinary `stone_bricks` with the project's original
  [brownstone texture pack](../server-assets/resourcepacks/hill-brownstone/README.md).
  Its two courses per block keep the stone pattern near the intended scale.
- Windows use recessed glass panes, narrow stone-wall mullions, and stair-shaped
  arch shoulders. Warm dimensional stone has its own original texture. Coping,
  roof edges, and entrance steps use stairs and slabs. The small metal clock
  and louver panels use documented, reserved trapdoor states with original
  component models in the material pack.
- Pews use wooden slabs, trapdoor backs, and timber ends. The plain table uses
  wooden legs and slabs. Upholstery colors are not established by the current
  photographs, so colored cushions have not been invented.
- Roads and paths retain the measured grade. Supported slabs add quarter-metre
  height increments; polished deepslate approximates asphalt, for which vanilla
  Minecraft has no exact block.
- Tree crowns use LiDAR outlines and heights, with an interpreted lower canopy
  and trunk structure. Species and exact trunk locations remain unverified;
  incomplete crowns at the crop boundary are omitted.

The [reference report](research/hill-chapel-exterior-reference-20260904.md)
distinguishes the old LiDAR/footprint envelope from the 2023–24 southern addition,
current photographs, proposed plans, and inferred details. The addition's plan
dimensions remain approximate. The bounded terrain edge and missing neighboring
buildings are part of this small trial's scope.

## Acceptance

The v11 manifest binds the six-view native report, launch manifest, and authored
`visual-review.json` to their SHA-256 hashes. The independent audit verifies those
records, the exact world, and the loaded pack before accepting the expansion gate.
Later studies start with their own gate closed. Neither passing tests nor merely
completing screenshots grants visual acceptance. The full-campus production world
remains separate from this local study.
