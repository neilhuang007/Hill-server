# Server architecture and code hygiene review — September 28, 2026

Reviewed the current Java plugin, its tests, and the repository's implementation
contracts, starting at `3eafeea`. This is a review of the current implementation,
not only the latest commit. Existing operations/deployment edits are separate
work. No deployment, world migration, or reconstruction change was performed.

The authentication boundary is reasonably clear: `auth.sso` handles browser
verification and identity persistence, and `SsoPlayerSessions` handles game
connections. The weaker boundary is `CompetitionModule`, which combines entry
rules, development authentication, survival transitions, cameras, and item/UI
presentation. `WorldModule` similarly mixes persistent player-world lifecycle
with disposable template preparation. More generic “manager” classes would not
resolve those responsibility conflicts.

## Applied changes

| Finding | Change |
| --- | --- |
| Command, camera, menu, movement, and preview-restoration paths repeated different subsets of editing checks. | One application-level editing decision now handles authentication, participant ownership, submission, and reset state. Current-entry wrappers resolve the entry and delegate authorization to the action. Camera recording/removal and new invitations now also respect an active reset. |
| The submission form repeated limits and validation, then saved the whole competition file twice and emitted three success messages. | `saveSubmissionDetails` validates both fields before modifying either, persists once, and returns a result the menu can use to reopen invalid input or finish a successful edit. Commands use the same validation helper; limits live on `Entry`. |
| “Next camera” and explicit-slot preview duplicated their full execution paths. | Next-camera selection delegates to the same safe preview operation. `Entry.cameraPose` supplies slot validation. Camera ticks resolve/recreate the anchor once and pass the entity directly to the bridge. |
| Obsolete camera state and entry points remained after earlier interaction changes. | Removed the unused exit timestamp map and its reader/writes, unused reset/submit/preview-location/menu wrappers, and an unreachable range fallback on the private camera-slot map. Public slot validation and the live preview-click debounce remain. |
| Ownership methods described Entra participant keys as Minecraft nicknames. | Renamed membership and display-name parameters/locals to participant/member terminology. Development account names and persisted schemas remain compatible. Corrected the obsolete diagnostic claiming Microsoft SSO is unimplemented. |
| Entering survival read and parsed the same snapshot twice. | Load one snapshot, use it to choose the destination, and apply it after a successful teleport. Removed the I/O-hiding `lastLocation` convenience method and the trivial restore wrapper. |
| The periodic entity cleanup enumerated survival entities only to skip every one. | Skip survival worlds before obtaining their entity collections. Competition-world mob/TNT cleanup and the NPC exemption remain. |
| Invite and accept paths each requested the target's complete membership list twice. | Each operation reads that list once. Acceptance still rechecks membership limits because the state can change after an invitation. |

These are call-path reductions, not measured server-latency claims.

## Remaining findings, in priority order

### High: legacy template invalidation can delete participant worlds

In [WorldModule](../../src/main/java/org/thehill/hill175/world/WorldModule.java),
`createPeopleWorld` and `deleteStalePeopleWorldIfNecessary` apply template marker
freshness to both cache directories and saved participant worlds. With structure
metadata enabled, a missing, unreadable, or mismatching ready marker can trigger
world deletion. This conflicts with the documented requirement to preserve
existing People builds when a template changes.

The current native v19 configuration has `people.structure-file: ""`, so this
legacy branch is inactive under those defaults. This finding is not evidence of
data loss on the deployed server. Before enabling that path, separate disposable
template preparation from opening an existing entry world; only an explicit
reset/delete should replace a participant build. Regression coverage must include
loaded and unloaded player worlds with old, missing, and unreadable markers.
This world-lifecycle repair was left outside the local hygiene changes.

### High: persistence can report success after a failed disk write

[YamlCompetitionStore](../../src/main/java/org/thehill/hill175/data/YamlCompetitionStore.java)
mutates its in-memory maps, calls `flush`, and logs/absorbs I/O failures. Callers
then announce success. It also rewrites every account, entry, allocation counter,
and up to 20,000 connection audit rows on each mutation/join/quit. These writes
run on the game thread; synchronization does not make them asynchronous.

The next persistence change should give durable mutations explicit failure
semantics and separate the connection audit from the competition snapshot. If
writes move to a worker, use immutable snapshots, ordered writes, and an explicit
shutdown drain. Passing the current mutable `Entry` references to an asynchronous
writer would introduce races. The single-save form change reduces one existing
cost but does not repair this durability contract.

### Medium: team and submission transitions still have distinct lock rules

`CompetitionModule.leaveTeam` uses ownership access, so a member of a two-person
submitted entry can leave without unlocking. `acceptInvite` checks submission but
not an in-progress reset, and `submitEntry` also uses ownership access. These
paths remain outside the consolidated ordinary-edit policy. Specify the intended
team/submission transition rules, then cover delayed invitation acceptance and
reset completion before changing them. Unlock must remain an operation that can
act on a submitted entry.

### Medium: location lookup and rendering do work proportional to unrelated state

`CompetitionModule.entryAt` requests a new copy of all entries and scans it for
each location query, including movement across blocks and protection events.
The first useful index is per world, maintained by the store with entry changes;
a chunk index should follow only if entry counts or profiling justify it.

`CampusChartMapRenderer.render` rewrites 16,384 background pixels per callback.
Startup camera marker rebuilding repeatedly scans shared worlds per entry.
Both can be improved, but caching introduces lifetime/invalidation obligations.
Measure realistic player/entry counts before adding renderer or entity caches.

### Lower priority: extract a cohesive camera session boundary and clarify menu arguments

The next useful extraction from `CompetitionModule` is the camera session:
preview state, anchors, camera bridge, focus/exit, and restoration callbacks.
Keep entry authorization and durable camera poses in the application/domain
layer. Splitting by responsibility is more useful than renaming every `Module`
to `Service`.

`MenuAction.page` also represents a camera slot. Named action constructors or
separate page/slot payloads would clarify this when the menu code is next changed.
The repeated confirmation inventories can then reuse their existing helper,
without introducing a menu framework. These presentation changes were deferred
to avoid expanding the tested interaction surface of this pass.

## Checks that are necessary

Keep the SSO issuer/audience/tenant/role checks, browser state/cookie/PKCE/nonce
binding, expiry, and exact live-connection recheck after asynchronous work. They
protect different trust and timing boundaries. Unsupported-provider rejection
and explicit development-auth acknowledgement also remain intentional.

Keep application-layer authorization even when a menu hides an action; permission
can change while a menu is open. Likewise, invitation acceptance must recheck
eligibility, and pending world teleports must recheck connection and entry state.
Safe spawn/camera checks and template provenance checks are not dead defensive
code. The problem with the legacy template path is what it does on a mismatch,
not the existence of the check.

## Validation

Focused tests cover one-write details updates, invalid input leaving both fields
unchanged, the owner/visitor/unauthenticated/submitted/reset access matrix,
camera commands during reset, survival snapshot consistency across a teleport,
cancelled teleports, missing/corrupt snapshot fallback, and survival-world
destination filtering. Existing tests cover SSO, identity ownership, privacy,
camera slot semantics, safe poses/spawns, and world cloning.

`gradlew.bat clean test jar` passed on JDK 25: **91 tests, zero failures, errors,
or skips**, including 12 added regression cases. The plugin JAR was built, and
the reviewed source/document diff passed `git diff --check`. Native camera
interaction and a live Hill tenant pilot were not run as part of this local review.
