# Personal campuses and guest parties

Each authenticated student owns a separate, persistent **full campus** copied from
the current approved blueprint export. Inviting a friend grants guest access to that
campus; it does not combine entries, transfer ownership, replace either student's
campus, or consume an old competition project. A student may be a guest of several
campuses and still return to their own with `/party home`.

This module supplies campus access and management only. It does **not** implement
party chat, private messages, or arbitrary-text/chat subcommands. Invitation,
acceptance and removal notices are server-generated system messages.

## Player controls

The shortest flow is **`/invite <player>` → click [Accept & Join]**. The invitation
is a compact system message with a green **[Accept & Join]** link and a gray
**[Decline]** link. Accept closes the current party inventory/Bedrock form, saves
guest access, then automatically travels to **the owner's campus**, not the
invitee's home. A blocked teleport does not undo the saved guest grant: the player
receives a **[Try Join Again]** link, and can also use **Visit Friends**. The retry
link identifies the campus by its entry UUID, not a private school identity.

| Command | Action |
| --- | --- |
| `/party` | Open the simple party menu. |
| `/party home` | Create your personal campus once, or return to the existing one. |
| `/invite <player>` | Invite an online, authenticated student to **your** campus. |
| `/party <player>` | The same invitation shortcut when the name is not a reserved party action. |
| `/party invite <player>` | The original invitation command; still supported. |
| `/party invite` | Choose an online friend from the menu. |
| `/party accept` | Accept and join the sole active invitation; open Invitations if there are several. |
| `/party accept <owner>` | Accept that owner's current unexpired invitation and join their campus. |
| `/party decline [owner]` | Decline that owner's invitation, or the sole active invitation; open Invitations if there are several. |
| `/party join [owner]` | Accept and join an invitation, or revisit an already accepted campus. Without a name, prefer incoming invitations; otherwise join the sole friend campus or open Visit Friends when there are several. |
| `/party visit [owner]` | Visit your own campus or one where you are an accepted guest; without a name, open Visit Friends. |
| `/party leave [owner]` | Leave someone else's guest roster; without a name, open Visit Friends. |
| `/party remove [player]` | Remove a guest from your campus, including an offline student; without a name, open Friends/Guests. |
| `/party revoke [player]` | Cancel a pending invitation from your campus; without a name, open Friends/Guests. |

For `<owner>` and removal/revocation arguments, use the stored display name or an
online Minecraft name. Multiword display names remain supported after the
subcommand. Ambiguous names are rejected: use the inventory/form instead of
guessing. Invitations require an online Minecraft name. Names matching `home`,
`invite`, `accept`, `decline`, `join`, `visit`, `leave`, `remove` or `revoke` need the
explicit `/invite <player>` or `/party invite <player>` form. Self-invitation also
rejects a second game account linked to the same authenticated school identity.
Tab completion offers actions and eligible names, never private identity keys or
invitation tokens.

Chat links use `/party accept <token>` and `/party decline <token>` internally.
These opaque UUIDs identify **one particular invitation** and only resolve for
its authenticated canonical target, including another linked account for that
same student. Forwarding a link to someone else grants nothing. Expired, revoked,
declined or already-used links do not accept or decline a later replacement
invitation, even from the same owner. Named accept commands remain available for
manually choosing the owner's current invitation.

Party controls are the **Friends** page of the one central **Hill Menu** (the compass,
`/hillmenu`, or sneak and use an empty hand). `/party` opens the Friends page
directly. Like every Hill Menu page, it is a Hypixel-style chest: black glass, green
item names with a gray description and a yellow "Click to ...!" line, and **Go Back**
and **Close** in the bottom row. Bedrock players get the same choices as a form.
Only items that apply are shown:

- **Invite a Friend** (name tag): online, authenticated students, each shown by their head.
- **Invitations** (paper): only when there are invitations. Choose one for the
  green **Accept & Join** or red **Decline** terracotta.
- **My Guests** (head): only when there are guests or pending invitations. Remove a
  guest (including offline guests) or cancel an invitation, each through an
  "Are you sure?" chest with green Confirm and red Cancel.
- **Friends' Campuses** (door): only when you are a guest somewhere. Visit a friend's
  campus or leave its guest list.

Lists hold 28 items per page with **Previous Page / Next Page** arrows. The server rechecks authentication, the canonical
identity, current roster and relevant ownership on each action. Invitation menus
and their acceptance, decline and cancellation actions capture the particular
invitation token: a stale page cannot substitute a new invitation. Leaving any
menu open does not retain permission after removal or a sign-in change.

Only the owner can invite, remove guests, revoke invitations or submit their campus
blueprint. A guest may visit, build where authorized, and leave. Neither guests nor
pending invitees are ever added to `Entry.members`: that set contains **only the
canonical owner**. A guest's own campus and any historical competition entries
remain separate and unchanged.

Removal or leaving immediately revokes build/admission authorization. All online
accounts linked to that guest identity and physically in that campus have their
management inventory/form closed and spectator target cleared, are sent to the
hub, and have movement/build mode refreshed. If the normal hub teleport is
interrupted, a direct hub fallback is attempted; only a guest still stuck inside
the revoked campus afterward is disconnected, rather than retaining private-world
access. Pending visits to that campus are invalidated. An unrelated visit elsewhere is not interrupted. The owner cannot
leave, be removed, or transfer ownership through these commands.

## Configuration

The module reads these optional plugin configuration keys; defaults apply even
when they are not explicitly present. Restart after changing them.

```yaml
parties:
  max-guests: 12
  invite-expiry-seconds: 600
  invite-cooldown-seconds: 10
```

| Key | Default | Enforced range | Meaning |
| --- | --- | --- | --- |
| `parties.max-guests` | 12 | 1–100 | Guest spaces per owner. Accepted guests **plus active pending invitations** reserve spaces. |
| `parties.invite-expiry-seconds` | 600 | 30–86400 | Lifetime of a newly issued invitation. |
| `parties.invite-cooldown-seconds` | 10 | 1–3600 | Minimum interval between successful invitations by an owner, persisted across restart. |

Lowering the limit does not eject existing guests; it blocks new invitations and
acceptances beyond the new limit. Expiration is checked at acceptance and menu
render time, with persisted cleanup every 30 seconds. Restart preserves the original
invitation expiry times and the owner's last successful invitation timestamp.

## Persistence and conservative recovery

`plugins/Hill175/parties.yml` is a separate, schema-versioned registry containing:

- Canonical owner identity, owner display label, personal entry UUID and world name.
- Creation phase: `PROVISIONING`, `READY` or `LOCKED`.
- Canonical guest identities and stored display labels for offline management.
- Pending invitations with labels, issue/expiry times and an opaque UUID `token`,
  plus the owner's last successful invitation time.

Canonical identity strings are stored as values in lists, not YAML paths, so dots
and other separators in Entra identities cannot change the document structure.
Treat this file as private student access data: protect it like authentication and
competition data, exclude it from Git/public exports, and back it up with worlds,
competition entries and blueprint provenance.

Schema version 1 remains supported. Existing invitations without `token` derive a
stable UUID from their stored owner identity, target identity and original issue
time. Loading does not rewrite the file or reset any roster, allocation, expiry or
cooldown. The next ordinary atomic registry update serializes the derived tokens
alongside newly generated tokens; repeated loads before that update produce the
same legacy tokens. A malformed or duplicate stored token fails the complete load
rather than selecting an arbitrary invitation. Tokens are not authentication:
every action still verifies the currently signed-in target and invitation state.

Updates are copy-on-write: serialize to a unique temporary file in the same data
directory, force its contents to disk, then atomically replace `parties.yml`.
There is deliberately **no non-atomic replacement fallback**. The filesystem must
support same-directory atomic replacement. Invalid, duplicate or unsupported
registry data fails the whole load rather than partially granting access. A load
or save failure locks all personal-campus editing/admission through this service;
errors are logged internally and players receive a clean recovery message. Failed
changes are not announced as successful. The service does not periodically
reserialize unchanged rosters or overwrite an unreadable registry on shutdown.

Creating a campus follows this order:

1. Run `beforeCreate` before allocating any world.
2. Persist a `PROVISIONING` owner-to-new-UUID reservation. A failed or interrupted
   allocation therefore cannot cause the next `/party home` to adopt an old world.
3. Allocate `Category.PEOPLE` with index `0`, persist its world name, create an
   owner-only `Entry`, mark its `selectedBuildingId` as `personal-campus`, and save
   and flush the competition store. No historical competition entry is reused.
4. Only for an allocation made by this running service, wait for world readiness
   and invoke `registerNewBranch` once. No guest or owner may build before this.
5. Persist `READY` only after registration succeeds. The injected freeze predicate
   must also reject entries without registered provenance. Any failure preserves
   the world and locks the allocation; future home requests do not retry baseline
   registration against a world that may already contain student work.

The marker lets integration code recognize a personal entry even if its separate
registry is missing. Marker-only entries are **not** adopted automatically; a
student with an orphaned marked entry cannot silently create a replacement. A
missing referenced entry, altered owner membership, changed category/world, missing
world directory, or interrupted allocation is an operator recovery case, not a
request to create/reset/adopt a world. No code in this module deletes worlds.

The competition store and party registry are separate durable records, not a
single filesystem transaction. A crash between their writes leaves a conservative
reservation/locked state; it does not grant guest access or synthesize provenance.
The `CompetitionStore` implementation must surface write failures from `saveEntry`
and `flush`. Preserve evidence and restore a coherent backup if persistence fails.
A `PROVISIONING` or `LOCKED` record after restart is not automatically made ready.

Recovery procedure:

1. Keep the affected runtime preserved; stop the server before editing/restoring
   registry, entry or provenance records.
2. Retain `parties.yml`, `competition-data.yml`, blueprint provenance and the actual
   campus world together. Diagnose the logged failure, including filesystem/full
   disk/permissions or interrupted initial preparation.
3. Restore the matching records and world from a known coherent backup, or arrange
   explicit staff recovery of an interrupted allocation. Never simply mark an old
   world `READY`, erase its registry to force recreation, or register its current
   state as a pristine template baseline.
4. Restart after recovery. Confirm ownership, invitations, private admission and
   the registered baseline in controlled Java/Bedrock client sessions. This guide
   does not claim those runtime checks or deployment have already occurred.

## Integration contract

`org.thehill.hill175.party.PartyService` implements `Listener`, `CommandExecutor`,
`TabCompleter` and `AutoCloseable`. Construction does not declare checked
exceptions:

```java
new PartyService(plugin, competition, store, worlds,
        beforeCreate, registerNewBranch, frozen);
```

The owning plugin registers its listener and the `/party` and `/invite` command
executor/tab completer, and closes the service on shutdown. Bukkit/player/world
operations and public service entry points must run on the server thread.

Public integration methods:

- `owns(Entry)`: recognizes a mapped personal entry or the persistent marker, even
  when its roster is invalid/unavailable, for blocking legacy reset/delete/team
  conversion paths. It is **not** an authorization grant.
- `isOwner(Player, Entry)`: checks authentication, the canonical owner, the current
  stored entry and exactly owner-only membership.
- `canVisit(Player, Entry)`: checks authentication and valid `READY` owner/guest
  access. It ignores blueprint freeze status so authorized visits to a campus
  stopped for recovery remain read-only. Waiting review requests never freeze a campus.
- `canBuild(Player, Entry)`: additionally requires world readiness and a false
  injected freeze predicate. Predicate failure denies editing.
- `home(Player)`: ensures the caller's own campus, then travels; returns `true`
  after actual authorized arrival or when a ready callback was queued, `false`
  when an immediate teleport fails or another clean failure occurs. Pending callbacks revalidate the session, entry and roster. Disconnect,
  removal or a subsequent teleport invalidates the pending request.
- `open(Player)`: opens the current management inventory or Bedrock form.
- `personalEntry(Player)`: returns the authenticated caller's mapped owner-only
  entry if valid, including a locked record for conservative integration checks;
  never chooses an entry by category, membership order or revision number.
- `refreshEntry(Entry)`: refreshes movement/build modes for online occupants.

Competition integration must route spawn/home and personal-entry controls here,
use `canBuild` for **all** editing paths, use `canVisit` before personal-world
teleports, retain owner-only metadata/submission controls, and guard legacy team,
category switch, reset and deletion operations with `owns`. Blueprint exploration
uses the canonical approved campus; staff review uses private overlays there,
not a staff bypass into a student's draft. The service itself denies unauthorized
destination-world teleports, portals, spectator targets and respawns, including marker-associated
worlds with invalid mappings. Existing registered worlds must be loaded through
a preserve-only loader: never run legacy template-mismatch reconstruction or
create a missing saved campus from a new template.
