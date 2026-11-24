# Local school chat safety

Hill's moderation sidecar performs an **offline vocabulary check**, using an
imported open-source English vocabulary rather than a small hand-written list.
It does not send chat, books, signs, entry metadata or item names to any remote
API. It adds no private-message or party-chat feature. The same rules apply to
students, staff, operators, every world, and both authentication modes; there is
no staff bypass permission.

**A lexical filter cannot guarantee that all inappropriate content is detected.**
Staff supervision, reporting and the existing mute/ban tools remain necessary.
A message passing this filter is not an assurance that it is suitable for school.

## Imported source and default policy

The packaged vocabulary is [cuss 2.2.0](https://github.com/words/cuss), pinned to
commit `6bab3fef250481e34ba55bc400fac5c6d25f1429`, under the MIT license. The
original English source, full copyright/license notice, checksums and exact
provenance are in `src/main/resources/moderation/` and are included in the JAR.
See [the provenance record](../../src/main/resources/moderation/PROVENANCE.md).
No JavaScript runtime or additional Java dependency is required.

This exact version has 1,795 rated English words and phrases, including swearing,
slurs, insults, and sexual expressions. Cuss ratings measure **likelihood of
profane use**, not severity:

- **2:** likely profane, unlikely clean: 1,255 entries, enabled by default.
- **1:** context dependent: 285 entries, not all enabled by default.
- **0:** likely clean: 255 entries, never activated by the rating setting.

The default also promotes **88 explicit school-policy terms** from rating 1.
The exact list is
[`school-additions.txt`](../../src/main/resources/moderation/school-additions.txt).
It includes common swearing which cuss considers ambiguous, such as `shit`,
`bitch`, `bastard` and `damn`, along with genital/sexual terminology such as
`penis`, `vagina`, `anus`, `dick`, `cock`, `pussy`, `boobs`, `tits`, `dildo`,
`porn`, `sex` and `orgasm`. These are additions to the 1,255-entry imported
baseline, not the entire filter. The default activates **1,343 upstream entries**
before local configuration additions.

Neutral identity words such as `gay`, `queer` and `homosexual` are not promoted
by the school supplement. Raising the rating setting to include every rating-1
word also blocks many legitimate words, identities and discussions; use that
setting cautiously. Anatomy, quotations, surnames, reclaimed language and
historical or health discussion may produce false positives even with the
default policy. Staff can narrowly approve legitimate wording using the local
allowlist. The upstream author explicitly cautions against treating this data
as a reliable profanity filter; this implementation does not claim to solve
that inherent context problem.

## Covered surfaces

When the listener is registered:

| Surface | Enforcement |
| --- | --- |
| Public Paper `AsyncChatEvent` | Cancels an inappropriate message before normal public delivery, with clean private feedback to its author. |
| Sign edits | Cancels `SignChangeEvent` for either the front or the back, joining all lines of the side being edited so line splitting is checked. |
| Sign placement | Cancels `BlockPlaceEvent` for standing, wall and hanging signs when the placing item fails the shared bounded item check, including prefilled text on both sides. Other block placements do not run item inspection. |
| Book edits/signing | Cancels `PlayerEditBookEvent`, checking the title and all page text together. |
| Anvil rename | Removes an inappropriate prepared result and rechecks result-slot clicks, including shift/number-key clicks; checks entered rename text and runs the shared bounded item inspection on the result. |
| Creative inventory/hotbar imports and creative drops | Cancels `InventoryCreativeEvent` when its incoming cursor item fails the shared item check. This covers normal saved-hotbar restoration transactions, not just freshly typed text. |
| Entry names, descriptions and other metadata | Callers must use `allows` or `requireClean` before storing or publishing text. The pure string API does not discover metadata automatically. |

Adventure text is serialized to plain text for matching. Styling does not split
a word into independently accepted fragments. Sign lines and book pages are
joined for checks. Existing authentication listeners continue to reject
unauthenticated public chat; this sidecar does not inspect unauthenticated chat
for profanity, and unauthenticated sign placement and sign/book/anvil/creative-item
changes are rejected.

### Bounded item inspection

The Creative, anvil-result and sign-placement checks share the same read-only
inspection of the event-supplied item:

- Item display/custom name, the separate fixed item-name component, and lore.
- Book title, author and every page, including prewritten books.
- `BlockStateMeta` sign text on **both front and back** and custom names exposed
  by nameable block states.
- Every `TileStateInventoryHolder` **snapshot inventory**, including a lectern's
  book and container contents such as chests and nested shulker boxes.
- Bundle contents, using the same nested-item budget.

Text fields are joined before filtering, so splitting a prohibited term between
lore lines, book pages, sign lines or nested-item text does not automatically
escape the check. This can also cause false positives across unrelated fields.

Each event item has a fixed budget: **eight nesting levels below the root item,
256 inspected item/slot positions** (including the root and empty snapshot slots),
**1,024 non-null text fields**, **4,096 component nodes**, and a maximum component
nesting depth of **32**. Joined text must fit `moderation.max-text-length`, which
is 65,536 UTF-16 characters by default; normalized text is also subject to the
normal matcher limit. Text is appended through a bounded flattener rather than
first creating an unlimited joined string. An over-budget item, unsupported
text component, or failed metadata/snapshot inspection is **rejected**, not
partially inspected and accepted. Large legitimate nested containers may
therefore need to be imported in smaller pieces.

For items checked through these events, accepted rich-text content is deliberately
restricted to **styled plain `TextComponent` trees**. Any hover event, click event
or insertion action causes rejection, without inspecting its command/action payload.
Translatable components and their arguments are rejected as unresolved metadata,
as are keybind, selector, score, NBT, object and other non-text component types.
Thus a benign visible label cannot conceal unfiltered profanity inside a hover
or translated argument: that interactive/unresolved item is not accepted at all.
Legitimate interactive or translated books/items must be converted by their
author to plain text before import; the plugin does not silently strip actions
and accept a changed item. Colors, formatting and ordinary text children remain
supported within the component budget.

The listener cancels the Creative or sign-placement event or rejects the anvil
result. It does not edit the inspected stack, set a block state, update a snapshot,
mutate a world, clear a player's inventory, or confiscate preexisting items.
The inspection reads only event items and detached block-inventory snapshots,
never live inventories from placed blocks. It does not read command-block commands, lock tokens,
authentication credentials or arbitrary NBT strings as public text.

The plugin logs only a fixed startup error if rules cannot load, and a fixed
warning if moderation is explicitly disabled. Rejected text and matching terms
are not echoed in feedback, exceptions, or moderation console logs. Feedback is
rate-limited to one message per player per two seconds and dispatched on the
server thread. This is **not** a promise about unrelated plugins, packet
recorders, command loggers, or proxy/server logging configured elsewhere.

## Matching behavior

The Java matcher applies the following bounded checks locally:

- Case-insensitive Unicode NFKD normalization, removing diacritical marks,
  format/zero-width characters and legacy section-sign formatting sequences.
- A limited, explicit set of common Latin-looking Cyrillic/Greek substitutions,
  plus selected Latin variants. It is not full Unicode confusable detection.
- Literal matching plus two leetspeak variants: `0=o`, `1/!/|=i` or `l`, `2=z`,
  `3=e`, `4/@=a`, `5/$=s`, `6/9=g`, `7/+=t`, and `8=b`.
- Word boundaries against letters/digits, so ordinary words such as `class`,
  `assignment`, `Scunthorpe` or `cocktail` are not rejected merely for containing
  a shorter prohibited word. Prohibited compounds explicitly present in the
  imported vocabulary still match. A contiguous normalized word also matches if
  its entire span can be split into two or more blocked entries, including repeats
  or mixed entries (for example, `fuckfuck` or `fuckshit`). A blocked substring
  with unmatched letters before or after it is not enough.
- Ignoring punctuation/whitespace between the letters of a candidate, to catch
  spelling such as `f u c k` or `s.h.i.t`, and recognizing stretched letters.
  Required doubled letters remain required, so `ass` does not become `as`.
  Splitting a forbidden word across ordinary words can therefore also create a
  false positive, for example `pen is`.
- Each candidate spans at most **256 normalized characters**. Text longer than
  the configured total limit is rejected, not silently truncated. Rules are
  literal strings, never operator-supplied regexes, and each rule is at most
  256 characters. Each configured rule collection is limited to 4,096 entries
  and the combined active terms/allowlist to 65,536 input characters.

An allowlist entry exempts **only matching spans** of its word or phrase after
normalization; it does not exempt the whole message or the player. Another
prohibited word elsewhere still rejects the message. Allowlisting a standalone
prohibited word deliberately permits that word wherever it matches at word
boundaries. To exempt a glued compound, the allowlist must cover the compound's
full span. Prefer narrow approved phrases over broad exceptions. Matching is
deterministic and uses immutable rules, including when public chat arrives asynchronously.

## Configuration

Missing keys use these enabled defaults:

```yaml
moderation:
  enabled: true
  minimum-rating: 2
  max-text-length: 65536
  additions: []
  allowlist: []
```

| Key | Meaning |
| --- | --- |
| `moderation.enabled` | Defaults to `true`. Explicit `false` disables lexical, length and imported-item inspection checks, including the metadata API; it does not bypass authentication or command policy. |
| `moderation.minimum-rating` | `2` by default; accepts only `1` or `2`. The bundled school supplement stays enabled at either value. |
| `moderation.max-text-length` | Maximum raw and normalized UTF-16 length for one checked text; default 65,536, accepted range 256–131,072. The book limit includes its title and all joined page text, so very long legitimate books may be rejected. |
| `moderation.additions` | Local literal blocked words/phrases, in addition to the imported vocabulary and school supplement. |
| `moderation.allowlist` | Local literal approved words/phrases, applied only to matching spans. |

Rules are read once at construction. Restart the plugin/server after config
changes; no command or live-reload mechanism is added. Missing, unreadable,
corrupt or structurally incomplete vocabulary, out-of-range configuration, or
invalid/excessive rules leaves the sidecar **fail closed**: public text is
rejected and metadata checks return false. It does not fall back to an empty
list. Repair resources/configuration and restart rather than disabling safety
for student use.

## Integration API

Plugin startup owns registration and supplies an authentication predicate which
is safe to read from Paper's asynchronous chat thread:

```java
SchoolChatSafety safety = new SchoolChatSafety(this, competition::isAuthenticated);
getServer().getPluginManager().registerEvents(safety, this);
```

Before accepting each user-controlled public metadata field:

```java
if (!safety.allows(proposedText)) {
    player.sendMessage("Please use school-appropriate wording.");
    return;
}
```

Alternatively, `safety.requireClean(proposedText)` throws an
`IllegalArgumentException` with a clean, fixed rejection message; catch it at the
command/UI boundary. A healthy enabled filter accepts null/empty text (other
validators still enforce required fields), but a failed rule load rejects even
empty text. Check new values before committing state, including renames and
updates, not only object creation. Avoid raw-text logging on rejection.

**Do not apply this API to authentication credentials or entire commands.**
`/login`, `/register` and `/verify` arguments are authentication input, not public
content. This sidecar does not subscribe to command events and cannot suppress a
password or verification code merely because it resembles a vocabulary term.

## Private messaging and command policy

`ServerListener.onCommand` uses the authenticated Hill command allowlist in all
worlds and modes, with no development-survival exception. Unauthenticated players
retain only authentication/help/rules commands. Namespaced commands remain
forbidden. Generic vanilla or plugin commands such as `/msg`, `/tell`, `/w`,
`/whisper`, `/me`, `/teammsg`, `/tm`, `/say` and their unapproved aliases are not
in the allowlist; staff do not bypass it. The Hill `party`, `invite` and
`blueprint` command names are allowed for their separate project/group features,
not as a party-chat transport. No party chat command is added.

Installing another plugin which sends messages through allowed commands, menus,
channels or other non-command transports requires a separate security review.
The allowlist is not a universal guarantee that arbitrary future plugins cannot
create private communication.

## Known limits

- English lexical coverage only, with a small set of obfuscation transforms.
  It is not multilingual moderation or a semantic classifier.
- No reliable detection of threats, bullying, grooming, self-harm statements,
  addresses, phone numbers, advertising, links, spam or private information.
  Some such phrases happen to be in the vocabulary, but that is not coverage.
- New slang, deliberate misspellings, unsupported homoglyphs, long obfuscations,
  some mixed leetspeak, attached-letter evasions, and content spread across
  separate messages/events can evade detection.
- No retroactive scan of existing chat/history, signs, books, items, imported
  schematics or entries. Creative item metadata is checked only when it enters
  through `InventoryCreativeEvent`, and anvil results are checked at preparation
  and take time. Player placement checks the item only for signs and hanging
  signs. Other already-existing items or items created by a plugin/other
  transport without these events are not automatically scanned on placement,
  display, inventory transfer or lectern insertion.
- No inspection of images, map art, building shapes, voice, resource packs,
  display entities, arbitrary raw NBT or metadata components outside the
  explicitly covered Bukkit item APIs, or arbitrary third-party plugin output.
  Checked item text with click/hover/insertion actions or unresolved component
  types is rejected rather than interpreting potentially hidden action payloads;
  already-existing interactive items are not retroactively inspected.
- Other plugins can alter text after this listener or ignore event cancellation.
  Keep the plugin set controlled and review those interactions.

Deploy with a real-client review of public chat, front/back signs, books, anvil
renames, saved-hotbar restoration of named/lore items, prewritten books and signs,
placement of prefilled standing, wall and hanging signs, nested containers/lectern
books, all metadata entry points, authentication commands and the command allowlist
in every enabled mode/world. Automated checks do not establish that unseen content
is safe.
