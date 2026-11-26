# Player workflow

Your campus hotbar starts with four tools: the **Undo** clock (slot 6), the **Hill
Menu** compass (slot 7), the **Send My Build** emerald (slot 8) and the campus **map**
(slot 9). You can move them between your hotbar, inventory and offhand. These tools
stay with you: you can't drop them or put them in containers. Temporary controls
for selecting or reviewing a build stay in place until you finish.

The **Hill Menu** is a Hypixel-style chest. Open it with the compass, `/hillmenu`, or by
sneaking and using an empty hand on a block. In the sign in lobby, use an empty hand on
the floor. Your head at the top shows your build status. Bedrock players get the same
choices as a form.

| Item | Opens |
| --- | --- |
| **My Campus** (grass) | Takes you to your own campus. |
| **Shared Blueprint** (beacon) | Fly through the shared Hill campus that every campus copies. Look only; the barrier takes you back. |
| **Friends** (head) | Invite friends, answer invitations, manage guests, visit friends' campuses. |
| **Reset My Campus** (TNT) | After an "Are you sure?" check, your campus matches the newest shared blueprint again. |
| **Help** (book) | Rules, how to play, and the campus map download. |
| **Replays** (clock, staff only) | Choose a player, including an offline player, to watch their recorded building sessions. |
| **Staff** (spyglass) | **Review Builds**, **Edit Blueprint**, **Roll Back Blueprint** and other staff tools (staff only). |

Every page has **Go Back** and **Close** in the bottom row and only shows items that
apply right now. Removing a guest or leaving a campus asks "Are you sure?" first.
`/party` opens the Friends page directly.

1. Choose **My Campus** to build in your own copy. **Friends** → **Invite a Friend**
   lets another student help there. You own the review request, including your
   guests' edits.
   The **clock** in your hotbar undoes your block edits from the last 15 seconds.
2. Right-click the **Send My Build** emerald in your hotbar. Gray boxes show what
   you changed, and you can fly through walls. Fly to one corner of your build and
   right-click the **Box Corner**, then fly to the opposite corner and right-click
   again. A green box appears. Right-click **Send**, or **Cancel** to stop. Your
   hotbar comes back afterwards.
3. Keep building while a moderator looks. Only the snapshot is sent, and sending
   again replaces the waiting request.
4. Approved builds join the shared blueprint and reach every campus automatically,
   including while you are offline. Click **Show Me** in the chat notice to see blue
   boxes around the update.
5. If the blueprint changed a block that you also changed, you fly to each pink box
   and right-click **Keep Mine** or **Use Blueprint's**.

Staff choose Hill Menu → **Staff** → **Review Builds**, or type `/review`. Each waiting
build opens on the shared blueprint, visible only to the reviewer, with green boxes
around it and pink boxes at conflicts. The hotbar holds **Accept** and **Reject**,
and the next build opens after each decision. When you return to **My Campus**
after using staff tools, you resume where you left off if the spot is still safe.

Right-click the campus map in your hotbar to see the illustrated school map, and
click a number on it to go there. The map image downloads once after you join. If
you turn it off, a list of buildings appears instead.

Public chat is filtered, and private-message and party-chat commands are disabled.
See [campus parties](campus-parties.md), [blueprint review](blueprint-review.md)
and [chat safety](chat-safety.md) for details. Existing shared campus saves and
competition entries are preserved. The entry/camera sections below describe the
legacy competition workflow rather than personal-campus guest permissions.

The deployed demo remains in development mode until Hill IT configures Microsoft
sign-in. The server tells you which authentication flow to use.

With build replays enabled, signed-in movement and block edits are recorded for staff review. Staff watch a separate reconstruction; they do not enter or change your live campus. Recordings normally expire after seven days.

## WorldEdit in your campus

In **My Campus**, use `//wand` to get the WorldEdit wooden axe. Left-click one
corner block and right-click the opposite corner. You can also stand at opposite
corners and use `//pos1` and `//pos2`. Use `//size` to check the selection, then
`//set <block>`, `//replace <from> <to>`,
`//walls <block>`, or `//faces <block>`. `//copy` and `//paste` copy blocks;
`//paste -a` skips air. Use `//undo` or `//redo` for WorldEdit changes.

Each operation is limited to 16,384 blocks. WorldEdit skips protected blocks,
including blocks with saved data such as signs and chests. Only the campus owner
can use these commands, and only in their own campus. To share a build, use
**Send My Build** as usual. WorldEdit must be installed on the server.

## School sign-in

Join from a supported Java or Bedrock client. Open the link supplied in the lobby,
sign into your Hill Microsoft account, then choose **Enter Browser Code** and enter the
code shown in that browser. Never enter a code someone else sends you. Choose **Get Sign In Link** to request a fresh link. Your school name is shown to other verified
participants. Every connection requires verification; after at most 30 minutes,
reconnect and sign in again.

Authenticate your Java and Bedrock accounts using the same Hill account to share
your personal campus, guest invitations and legacy competition ownership. Only one linked account may play at a time. Bedrock requires operators to
install Geyser/Floodgate; see the [IT guide](microsoft-sso-setup.md).

After sign-in every player arrives in the hub. Two guides stand there: **My Campus**
takes you to your own campus with its building tools, and **Blueprint** opens the
shared server blueprint. `/hub` returns to the hub at any time.

## Development demo

Join using the Java version supported by the pinned Paper server (26.2). In the
authentication lobby, register a unique event password with
`/register <password> <repeatPassword>`. The server reads your Minecraft name
automatically, including Bedrock's account prefix. Returning players use
`/login <password>`. Never use a school/Microsoft password here. Command arguments
are not broadcast; the deployed Spigot configuration disables console command
logging, but the player's own command history can retain them.

## Legacy competition entries

After authentication, use the Competition Compass or the category guides.
Bedrock opens native buttons sized for touch and controllers; Java uses inventory
menus. Start a project, build, then take photos. Titles and descriptions are
optional and can be added later through **Build Options → Edit Details**.

* **Journey:** a 64×64 outdoor plot for a Hill spot or landmark.
* **Place:** choose one of seven campus areas, review its boundaries, then choose
  **Build Here**. Your private V54 copy preserves the original campus terrain.
  **Build Options → Build Boundary** lists the exact editable rectangles.
  **Choose a Single Building** also offers the earlier building selection map.
  Existing building projects and earlier 32×32 Place entries are preserved.
* **People:** a private campus copy for recreating a Hill scene.

The held Java map shows numbered footprints and your position and heading.
Open the map inside a campus build to choose a destination. Both editions provide a
**Go here** action for buildings within your project's available visiting area.
Creating a project takes you straight to the build, without a details form.

Each participant can join at most two entries in different categories, with at
most two members per entry. Microsoft mode applies those limits to the school
participant across all linked accounts. Demo accounts remain nickname-based.

Owners build in Creative mode inside their entry; visits and submitted entries
are read-only. **Build Options → Project Settings** groups reset, delete, and
category changes, with confirmations. Submission remains a separate action.
Use **Build Options → Team** to invite an online student. The invited student
opens the Competition Compass and chooses **Accept Team Invite**. Team members
share the same private build and submission. Leaving a team asks for confirmation.
The approved Hill command policy applies in both school and development modes. Private messages and emotes are blocked.

## Legacy and utility commands

The personal-campus commands are listed above. These utility and legacy project
commands remain available, with personal campus reset/delete/team conversion
blocked to preserve permanent ownership.

| Command | Purpose |
| --- | --- |
| `/verify`, `/verify <code>` | Request a school sign-in link or complete verification |
| `/hill175`, `/competition` | Open competition menus |
| `/hub` | Return to exhibition hub |
| `/rules` | Read rules |
| `/entry create <journey\|place\|people>` | Create an entry |
| `/entry home`, `/entry visit` | Go to your entry or browse others |
| `/entry map` | Open building selection or campus navigation |
| `/entry website` | Open your private draft or published entry on the local gallery |
| `/entry reset`, `/entry delete`, `/entry switch <category>` | Manage build space |
| `/entry title <text>`, `/entry description <text>` | Edit submission information |
| `/entry submit`, `/entry unlock` | Competition entries: capture/publish/lock or reopen. In a personal campus: Send My Build, or cancel the waiting request |
| `/team invite <nickname>`, `/team accept <nickname>`, `/team leave` | Manage teammates |
| `/camera save <1-3>`, `/camera list`, `/camera remove <1-3>` | Manage saved views |
| `/camera preview [1-3]`, `/camera exit` | Preview or leave a saved view |

## Cameras

Right-click Capture Camera View to save the current position and angle, up to three
poses. Each marker includes a floating eye item and a label; click it to preview.
You can fly outside your editable area for an exterior shot: Place buildings have
up to 96 extra blocks of photo space, clipped to the installed campus, while
shared plots have a 24-block margin. Editing remains limited to your project.
Outside the editing boundary, owners retain flight and their camera tools.
The view locks and **Exit Camera Preview**
is selected in the hotbar; use it to return. `/camera exit` is also available.
Owners have a separate remove-current-camera item; visitors cannot remove poses.

Each camera save also generates a website image automatically. Open **Entry
Controls → Website Preview** to see it. Images are server-rendered block previews,
not native client screenshots: client textures, shaders, entities and sign text
are not included. Replacing or removing a saved camera requires confirmation;
the capture item never silently overwrites a full set of three views.

Submission requires at least one saved camera; title and description are optional.
Confirm **Submit Entry** to pause editing, generate fresh images, then publish and
lock automatically. A capture failure restores editing and explains how to retry.
Unlocking immediately removes the public listing. Draft links remain private to
their holders. The initial gallery runs only at `http://localhost:8788` on the
server computer; see [local gallery setup](build-gallery.md).

Resetting/deleting/switching an entry changes its build space. Template upgrades
preserve existing People worlds until an explicit entry reset or replacement.
See [smoke tests](../SMOKE_TEST.md) for the full behavior checklist.
