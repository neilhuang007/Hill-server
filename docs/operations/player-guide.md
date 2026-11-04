# Player workflow

The active local server is the [shared V60 campus](shared-campus.md). After
signing in, everyone builds in the same campus. Open `/campus` or use the
map in hotbar slot 9 to choose a location. Holding it shows the official school
illustration; right clicking opens the larger map. Accept its artwork pack,
hover a printed number to see the location name, then click the number to
teleport directly. The Buildings list also provides direct travel.
Slot 8 provides Undo for
your previous 15 seconds of supported block edits. No submission or merge is required.
Staff can restore a saved recovery point. The entry and camera instructions
below document the preserved competition features.

The deployed demo remains in development mode until Hill IT configures Microsoft
sign-in. The server tells you which authentication flow to use.

## School sign-in

Join from a supported Java or Bedrock client. Open the link supplied in the lobby,
sign into your Hill Microsoft account, then type `/verify <code>` using the one-time
code shown in that browser. Never enter a code someone else sends you. Use `/verify`
without a code to request a new link. Your school name is shown to other verified
participants. Every connection requires verification; after at most 30 minutes,
reconnect and sign in again.

Authenticate your Java and Bedrock accounts using the same Hill account to share
entries and team membership. Only one linked account may play at a time. Survival
inventories remain separate for each game account. Bedrock requires operators to
install Geyser/Floodgate; see the [IT guide](microsoft-sso-setup.md).

## Development demo

Join using the Java version supported by the pinned Paper server (26.2). In the
authentication lobby, register a unique event password with
`/register <password> <repeatPassword>`. The server reads your Minecraft name
automatically, including Bedrock's account prefix. Returning players use
`/login <password>`. Never use a school/Microsoft password here. Command arguments
are not broadcast; the deployed Spigot configuration disables console command
logging, but the player's own command history can retain them.

## Building and entries

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
Survival is a separate world/inventory flow.
Use **Build Options → Team** to invite an online student. The invited student
opens the Competition Compass and chooses **Accept Team Invite**. Team members
share the same private build and submission. Leaving a team asks for confirmation.
In school mode, the approved Hill commands apply in survival too; vanilla private
messages and emotes are blocked so they cannot bypass school-chat visibility.

## Commands

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
| `/entry submit`, `/entry unlock` | Automatically capture/publish/lock, or withdraw and reopen |
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
