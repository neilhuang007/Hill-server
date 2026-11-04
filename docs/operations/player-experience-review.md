# Player experience review — October 15, 2026

Scope: competition gameplay and the local build gallery. This is not acceptance
of the campus exterior, a Microsoft tenant pilot, or a Bedrock client pilot.
The installed campus template and the separately selected V38 authoring save
remain separate inputs. Existing player builds are preserved.

## Player action map

| Stage | Actions a player can take | Expected result |
| --- | --- | --- |
| Admission | Join, register/login in the demo, reconnect, request help | Lobby remains protected until authentication; clear route to hub |
| Discover | Use compass, click category guides, read rules | Choose Journey (Hill spot), Place (interior/exterior remodel), or People (Hill scene) |
| Choose a building | Select Place, hold map, open numbered list, inspect choice, confirm | Private copy with the measured footprint and surrounding outdoor edit space |
| Build | Place/break blocks, decorate, use fluids and permitted entities | Owners and teammates edit within their region; visitors and neighboring builds remain protected |
| Navigate | Hold campus map, follow player arrow, view numbered destinations, return to hub/home | Map numbers match the selector; coordinates and direction are available in game |
| Team | Invite, accept, leave | Two members maximum, two categories per participant; submitted entries cannot change team |
| Camera | Hold camera, save slots 1–3, click markers, preview exact slot, exit, replace/remove | No silent overwrite; replacement/removal confirmation; locked preview always has an exit |
| Preview online | Open Entry Controls → Website Preview or `/entry website` | Private draft link displays automatically generated camera images |
| Submit | Confirm submission, wait for images | Build pauses, fresh images generate, successful entry publishes and locks automatically |
| Resume | Unlock or cancel preparation | Editing returns; public listing is withdrawn |
| Manage | Edit metadata, reset, delete, switch category | Destructive actions require confirmation; Place switching includes building selection |
| Visit | Browse builds, visit, click saved cameras | Read-only access; no access to another participant's private draft link |
| Survival | Enter survival, return to hub | Survival state stays separate from competition tools and Creative builds |
| Return later | Disconnect/reconnect, restart server | Entries, selected building, cameras, submission state and private preview identity persist |

## Local gallery

The gallery binds to `127.0.0.1:8788`; open `http://localhost:8788` on the server
computer. No public hostname or DNS is configured for this work. A localhost
link is only usable on that same computer. Public hosting is a separate step
requiring the project's Cloudflare ingress, origin certificate and authenticated
origin-pull controls.

The Stoneborn ZIP stays outside Git. Prepare its small UI asset subset with
`ops/prepare-gallery-assets.py`, then set `gallery.asset-directory` to that output
or place it in `plugins/Hill175/gallery-assets` in the local server folder.
The site works with a CSS fallback if those optional textures are unavailable.

Camera images are server-rendered perspective previews of actual saved world
blocks. They are not client F2 screenshots: client resource packs, shaders,
entities and sign text are not reproduced. Capturing and submitting require no
manual image upload. The public gallery includes submitted builds only; draft
links are unguessable capabilities and should only be shared intentionally.

## Evidence

The local JDK 25 `clean test jar` pass and final `test jar` run passed all
**140 Java tests**. These cover
world allocation and recovery, authority, submission state, gallery privacy and
persistence, and prefixed Bedrock account registration/persistence. The Bedrock
deployment suite passed 14 checks with one Windows symlink check skipped.

| Functional check | Observed result |
| --- | --- |
| Existing remote server | Protocol login lock, help/hub navigation, category NPC clicks and owner/visitor camera behavior passed through a PuTTY tunnel |
| Journey camera/gallery | Actual player placed blocks; saved three views; replaced/removed cameras; previewed a fixed pose; tested visitor denial and team editing; submitted, published, unlocked, withdrew and deleted the test entry |
| Place building | Selected Chapel; placed/broke blocks outside and inside after entering through its door; received numbered map/player cursor; crossed spectator/Creative boundaries; returned via hub/home; reset back to source |
| People scene | Installed campus-v19-2x template cloned with all 25 region files; safe spawn, map, reset and home return passed |
| Menus and return | Metadata dialog callback, reset/category/submission/delete confirmations, empty-air lobby tool, stable tool inventory, survival return and plot reset/reentry passed |
| Browser | Desktop/mobile, filters, three camera slots, keyboard navigation, errors, private/public access, publication/withdrawal and automatic image updates passed; final actual Chapel screenshots opened and inspected |

The full camera/gallery scenario is reproducible with
`node ops/smoke-camera-gallery.mjs`; it deletes its own entry on success. Building
selection is exercised by `node ops/smoke-building-selection.mjs`. The broader
scenarios are in `ops/smoke-player.mjs`. These are development-authentication
clients, not a Microsoft tenant pilot.

At the user's request, three clearly labelled smoke examples are now submitted
to the **local** gallery: Hill 175 monument (Journey, three views), Chapel remodel
(Place, three views), and Hill scene (People, two views). They were created by
protocol clients using normal placement, camera and submission actions. These
are demonstration entries, not student work. URLs are recorded in ignored
`runtime/gallery-journey-example/result.json` and
`runtime/gallery-smoke-building-examples.json`.
The reusable seeders are `ops/seed-gallery-journey.mjs` and
`ops/seed-gallery-examples.mjs`; unlike the cleanup smoke test, they deliberately
keep their submitted examples. Final browser screenshots are in
`runtime/gallery-final/`.
Other protocol transcripts are in
`runtime/player-experience-20261015/`. Existing user worlds and the V38 authoring
save were not replaced. Pinned Geyser/Floodgate are installed in the main local
runtime, with Xbox validation enabled and Bedrock UDP port 19132. Java remains on
25566; the website remains loopback-only on 8788. No code, bridge or website was
deployed to the remote server during this local implementation pass.

Protocol checks establish server behavior, not native-client visual quality.
The renderer produces approximate block previews, not native Minecraft screenshots.
The automated Bedrock runner passed actual protocol 2193 admission handling,
prefixed-name registration, touch/container input, editable forms, placement and
breaking, camera controls, automatic submission, map selection, reconnect and
Paper restart persistence. Its console supplies test blocks and reads assertions;
the Bedrock client sends the editing packets. The secured bridge rejects unsigned
Xbox admission; gameplay uses unsigned clients only in an isolated loopback
fixture. This does not verify Xbox or Hill tenant sign-in. See
[automated Bedrock checks](bedrock-smoke.md) for the reproducible command and logs.

The strict reconnect check exposed a camera-anchor tracking race immediately
after teleport. Preview focus now has a bounded first-second retry sequence,
guarded by the active preview. The retained Bedrock restart fixture passed the
same immediate-use check, including fixed pose under controller input and the
Exit Camera item. The final Java regression also verifies that focus resets stop
after initialization. The main local bridge independently passed the secured
unsigned-login rejection check with Node 24.22.0.
