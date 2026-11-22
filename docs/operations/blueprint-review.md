# Personal campuses and blueprint review

The accepted **blueprint** is the shared, read-only Hill campus everyone can visit.
Each owner builds in a personal campus copied from an accepted blueprint export.
Invited guests can help build there, but only the owner sends its build for review.
Blueprint review never sets or clears `Entry.submitted`, and its repository is
separate from gallery data. Existing campus worlds are never replaced or adopted.

The system works like Git at block level, but without Git storage or merging of
binary region files, and no external mod is required:

| Git idea | Hill blueprint |
| --- | --- |
| branch | a student's personal campus |
| stage + commit | **Send My Build** takes a snapshot of the campus |
| pull request | the waiting review request |
| merge to main | a moderator accepts; the blueprint gains update `#n` |
| pull / rebase | each personal campus merges every update automatically |
| merge conflict | a block changed both in the campus and in the update |

## Student workflow

Everything happens with a few hotbar items. Menus only show buttons that apply.

**Send a build.** Right-click the **Send My Build** emerald in the campus hotbar
(slot 8), the hub's **BLUEPRINT** guide, or `/blueprint`. The server takes a snapshot and gray boxes show
what changed. The hotbar is replaced by three items:

| Item | Use |
| --- | --- |
| **Box Corner** (glinting lime concrete) | Fly to one corner of the build and right-click, then fly to the opposite corner and right-click. A green box appears. A third click starts a new box. |
| **Send** (lime dye) | Sends the changes inside the green box for approval. |
| **Cancel** (barrier) | Stops without sending. |

Box Corner marks the block the player is in. After the first corner, a green particle
box stretches from that corner to the player until the second click. Players fly
freely through walls, floors and ceilings. Spectator mode hides the hotbar, so the
server switches the player to spectator only while they are inside blocks or moving
into them, and back to flying adventure (look only, invulnerable) in open air, where
the hotbar works. Corners are drawn as outline boxes and never change the campus.
**Send** names the request after the campus title, or "<player>'s build", and returns
the player to where they started with their own inventory and game mode.

Builders, owners and guests alike, also get **Undo Last 15 Seconds** (a clock in
hotbar slot 6). It undoes their own recent block edits in the campus, the same as in
the shared campus.

Building **never pauses**: only the snapshot is sent, and later edits stay in the
campus. Sending again replaces a waiting request (the old one is recorded as
`WITHDRAWN` with "Replaced by a newer snapshot").

**Choose what to keep.** When an update changed blocks the student also changed,
the student flies to each pink box in turn with two items: **Keep Mine** (lime dye)
and **Use Blueprint's** (light blue dye), plus **Finish Later** (barrier). Pressing
Send My Build while conflicts remain starts this automatically, and the chat notice
has a **[Choose What to Keep]** link.

Chat notices tell students about approvals, rejections and updates. **[Show Me]**
draws blue boxes around the latest update. A student who was offline gets one summary
when they next sign in.

| Command | Result |
| --- | --- |
| `/blueprint` | Same as the Send My Build emerald. |
| `/blueprint send` | Same as the Send My Build emerald. `/entry submit` in a personal campus does the same. |
| `/blueprint fix` | Same as Choose What to Keep. |
| `/blueprint cancel` | Withdraw the waiting request (`/entry unlock` does the same). |
| `/blueprint news [n]` | Visit update `n` (default latest) in the owner's campus. |
| `/blueprint visit` | Walk around the read-only shared blueprint. |
| `/blueprint history`, `list`, `help` | Text views of visible requests and commands. |

All actions require sign-in. Guests cannot send or cancel the owner's request.
Owners see only their own request history; reviewers see all requests.

### How snapshots work

The server journals every edited chunk (plus a one-chunk halo) before the edit.
Campuses never change on their own: like the blueprint, campus worlds run with
random ticks off, and decay, spread and fading (grass to dirt, leaf decay, ice melt)
are cancelled. Otherwise those natural changes would show up as student edits.
**Send My Build** requires the campus to have every accepted update and no
unresolved conflicts. It then:

1. loads the journaled chunks of the campus and the blueprint asynchronously,
   holding plugin chunk tickets;
2. captures chunk snapshots of **both worlds in the same tick**, including the full
   NBT of chests, signs and other block entities. This is the point in time that
   gets sent;
3. compares the two off the server thread and groups changed blocks into boxes
   (nearby changes share one box, with at most 40 boxes);
4. forgets journaled chunks that matched the blueprint and were not edited since
   the snapshot, which keeps later snapshots small.

Because a campus always contains every accepted update (see below), the live
blueprint is the common base, and no baseline world copies are needed. The diff
is `blueprint block → campus block` for each changed position inside the editable
bounds. Snapshots expire after 20 minutes, and a snapshot taken before a newer
update cannot be sent.

### Automatic updates and conflicts

Each accepted request is stored as an **update packet**: the blocks actually
written, with the blueprint block before and after. For every position in update
`#n`, the server compares the update's *before* (the shared base), its *after*
(theirs) and the campus block (mine):

- mine equals after: nothing to do;
- the update came from this campus's own request: nothing is written, so edits made
  after that snapshot survive;
- mine equals before: the campus block is replaced by the update;
- otherwise: a **conflict** is recorded and the student's block stays for now.

Clean blocks merge immediately and the campus advances to `#n` even when conflicts
remain, so a campus never stalls behind the blueprint. Campuses whose world is loaded
are processed first. Offline owners' campuses are opened, merged, saved and closed
in turn (one update every half second). The process is idempotent: repeating an
interrupted update rewrites nothing that already matches.

**Keep Mine** clears the conflict. The student's block then differs from the
blueprint and goes into their next snapshot as an ordinary change. **Use
Blueprint's** writes the update's block. A conflict that the student resolves by
hand (making the block match) clears itself, and a later update at the same
position replaces the recorded conflict.

## Staff review

Authenticated staff need `hill175.blueprint.review` (or the configured review
permission). Console can list and decide requests; the visual review needs a player.

Choose Hill Menu → **Staff** → **Review Builds**, or type `/review`.
The reviewer is taken to the oldest waiting build **on the shared blueprint** and sees
its proposed blocks, visible only to them. Glowing boxes, which show through walls,
surround each changed area: **green** for changes and **pink** where the blueprint
changed after the student's snapshot, with a small pink box on each conflicting block.
Bedrock reviewers see particle edges. The hotbar holds two items:

| Item | Use |
| --- | --- |
| **Accept** (lime dye) | Adds the whole build to the shared blueprint. The student's blocks win at conflicts, as previewed. Every campus then updates automatically. |
| **Reject** (red dye) | Sends it back with "A moderator asked you to improve this build. Keep building and send it again." |

After each decision the next waiting build opens. When none are left, the reviewer
returns to where they started with their own inventory. `/review` again stops early.
Reviewers fly and pass through walls like students. The action bar names the build
and student, and says how many green boxes it has.

Boxes are `BlockDisplay` entities that are non-persistent, hidden by default and
shown only to the viewer. They are tagged `hill175_blueprint_outline` and excluded
from the decorative entity limit. Previews use player-specific block packets and
never set a real block. A preview ends on disconnect, on leaving the blueprint, on
lost permission or when another reviewer decides the request. At most eight reviews
are open at once.

For automation, `/blueprint approve <id> confirm [keep-blueprint|use-student]` and
`/blueprint reject <id> <reason>` remain. Without a conflict choice, approval of a
conflicting request is refused and applies no blocks.

For each block, approval compares the request's *before* (the blueprint at the
snapshot), its *after* and the **current** blueprint block, including block-entity
NBT. When current equals before, the request's block is applied. When current
already equals after, the block is skipped. Anything else is a conflict and is
resolved by the moderator's choice. A request that would change nothing is refused.
Changes outside the campus's editable bounds are refused. Entities, inventories and
biomes are not merged.

## Visiting, staff editing, rollback and reset

Every change to the shared blueprint becomes a numbered update. Campuses only sync by
replaying updates, so approvals, staff edits and rollbacks all go through the same
journal-first transaction (journal, apply, save, export, decision).

**Visit (everyone).** Hill Menu → **Shared Blueprint** (or `/blueprint visit`) flies the
player through `hill_blueprint` in the look-only hotbar mode (through walls, invulnerable).
The only item is **Leave the Blueprint**, which returns them to where they started.
Visitors cannot change blocks or open containers.

**Edit (staff).** Staff → **Edit Blueprint** (or `/blueprint edit`) takes a reviewer into
the blueprint in creative with their own inventory. Before each chunk is first changed,
the server records how it looked (chunk snapshot plus chest/sign data, with the 3×3
chunk halo). Saving compares those records with the blueprint and stores the difference
as one update, **Staff edit by …**, which every campus merges like an approval. Edits
save when the last editor leaves the blueprint or signs out, after two minutes without
edits, with Staff → **Save Blueprint Changes** or `/blueprint save`, and on server stop.
While staff edits are unsaved, student sends, resets, approvals and rollbacks wait with a
short message. The blueprint's auto-save is off for that time, and edited chunks stay
loaded, so a crash loses only unsaved staff edits and never leaves the blueprint ahead of
its last update. Only editors can change the blueprint. Edits made by WorldEdit or other
plugins that skip Paper's block events are not recorded, so do not use them on
`hill_blueprint`.

**Roll back (staff).** Staff → **Roll Back Blueprint** lists every version, newest first:
the original campus, approved builds (paper), staff edits (bricks) and earlier rollbacks
(echo shard). Each shows who made it and when. Clicking a version copies its saved export
into a temporary look-only world (`hill_bp_preview_<id>`, copied off the server thread)
and flies the staff member there. The hotbar holds two items: **Roll Back to This** and
**Cancel**. Rolling back takes a recovery snapshot, then records a new update, **Rolled
back to update #k**, in which every block changed since version k gets the state it had
just before the first later update changed it. Campuses merge it like any update, and
student blocks that differ become conflicts as usual. Either choice returns the staff
member to where they started. The temporary world is unloaded and deleted, and leftover
previews are deleted at startup. Each update records the name of its export. Updates
made before this feature fall back to the single export named `revision-<n>-*`.

**Reset (owners).** Hill Menu → **Reset My Campus**, after an "Are you sure?" chest,
makes the owner's campus match the newest blueprint. The campus first receives any
waiting update. Building then pauses while the server compares the campus's journaled
chunks with the blueprint and writes the blueprint's blocks back, 2,048 per tick. Waiting
requests stay waiting. Entities such as item frames and armor stands are not reset.

Staff updates and rollbacks may hold up to 65,536 blocks (student requests stay capped at
8,192). Applying a very large update freezes each campus briefly while it syncs, so keep
staff edits and rollbacks reasonably sized.

## Selection and configuration

```yaml
personal-campus:
  enabled: true
shared-campus:
  enabled: false
blueprint:
  # Optional, used ONLY on first initialization. Otherwise people.template-folder.
  # source-folder: world-templates/hill_people_template
  maximum-changed-blocks: 4096     # per request, clamped to 1–8,192
  maximum-snapshot-chunks: 512     # journaled chunks compared per snapshot, 16–4,096
  review-permission: hill175.blueprint.review
  backup-permission: hill175.blueprint.backup
```

The selected source must be a prepared **Anvil campus folder** with nonempty,
valid `region/r.<x>.<z>.mca` files, plus measured bounds and spawn in
`hill-campus-template.yml`. First initialization copies it to `hill_blueprint`
and the immutable export `revision-0`. It refuses to overwrite an unregistered
`hill_blueprint`. Later starts read `plugins/Hill175/blueprint/current.properties`;
replacing the original source folder does not replace an initialized blueprint.

Every new export carries `hill-blueprint-revision.properties`. A new personal campus
is copied from the current export and records that revision when it is registered,
so updates accepted while the copy was being prepared are merged automatically.
Exports created before this marker existed fall back to the revision at registration.

A snapshot may hold up to four times `maximum-changed-blocks`, so that students can
box part of the build to split it into requests within the limit. The
binary format refuses packets above 8,192 blocks or 32 MiB, with at most 1 MiB per
block-entity snapshot and 16 MiB of block-entity data per snapshot.

## Persistence and recovery

State is under `plugins/Hill175/blueprint/`:

| Path | Purpose |
| --- | --- |
| `current.properties`, `exports/` | Accepted revision pointer and immutable creation templates. |
| `branches/<entry>.properties` | Owner, world UUID, bounds, synced revision, notice receipts and journaled chunks. |
| `branches/<entry>.conflicts-<id>.bin` | Checksummed unresolved conflicts (position, base, blueprint block). Each change writes a new file before the branch record points to it. |
| `submissions/<request>/` | Checksummed immutable block changes and atomic decision metadata. |
| `merge.properties`, `merge-rollback.bin` | Active approval transaction and the blocks it overwrites. |
| `merge-complete-<request>.{properties,bin}` | Update `#n`: its journal and checksummed applied-change packet. |
| `merge-recovered-*` | Retained records of rolled-back interrupted approvals. |

Branch files from the earlier freeze-based design load unchanged: their `baseline`
reference is preserved, and their old `hill_bp_base_*` / `hill_bp_review_*` worlds,
`operations/`, `submission-baselines/` and `import*` files are left in place and
no longer read. Nothing is deleted automatically; monitor disk use and archive old
folders only after a stopped-server review.

Approval first takes and verifies a recovery snapshot, then persists the rollback
data and merge journal **before** applying any block. The blueprint is saved, a new
export is published, the decision is committed, and the journal is retained as
update `#n`. If the process stops before the approved decision, startup restores the
recorded blocks and previous export pointer, and the request stays waiting. If the
decision is durable, startup finishes the journal instead. Journal or recovery
failure blocks further edits and merges and is logged; do not remove a journal
merely to unlock building.

Campus updates and **Use Blueprint's** save the campus world before recording the
new revision, so a crash cannot make an unsaved update look like a student edit.

### Recovery snapshot scope

Mandatory premerge snapshots, and explicit `/blueprint backup`, are stored under
the server folder's **`blueprint-backups/`**; `/blueprint backups` lists them.
Manual commands require authenticated `hill175.blueprint.backup`. Each snapshot
contains only `canonical/` (the loaded `hill_blueprint` folder without its session
lock) and the blueprint state (`current.properties`, `branches/`, `submissions/`),
with SHA-256 checksums. They are **not full-server backups**: personal campuses, the
hub, survival worlds and exports are excluded. There is deliberately no
`/blueprint restore`. For manual recovery, stop Paper, preserve everything, inspect
`merge.properties` and the logs first, and restore only matching blueprint data to
its recorded original location after verifying every checksum.

Large folder copies (premerge snapshot, export) are synchronous and can pause the
server briefly even for a small request. Schedule approvals during quiet periods.
Protection covers normal Paper events and integrated controls. Do not use WorldEdit,
filesystem replacement or another process on `hill_blueprint` while Paper owns it.
