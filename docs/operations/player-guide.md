# Player workflow

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
`/register <currentNickname> <password> <repeatPassword>`. Returning players use
`/login <password>`. Never use a school/Microsoft password here. Command arguments
are not broadcast; the deployed Spigot configuration disables console command
logging, but the player's own command history can retain them.

## Building and entries

After authentication, use the Competition Compass or the category guides:

- **Journey:** a 64×64 outdoor plot.
- **Place:** a 32×32 interior shell.
- **People:** a private copy of the pinned campus template.

Each participant can join at most two entries in different categories, with at
most two members per entry. Microsoft mode applies those limits to the school
participant across all linked accounts. Demo accounts remain nickname-based.

Owners build in Creative mode inside their entry; visits and submitted entries
are read-only. Entry Controls provides reset, delete, switch-category, and
submission actions with confirmations. Survival is a separate world/inventory flow.
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
| `/entry reset`, `/entry delete`, `/entry switch <category>` | Manage build space |
| `/entry title <text>`, `/entry description <text>` | Edit submission information |
| `/entry submit`, `/entry unlock` | Lock or reopen a submission |
| `/team invite <nickname>`, `/team accept <nickname>`, `/team leave` | Manage teammates |
| `/camera save <1-3>`, `/camera list`, `/camera remove <1-3>` | Manage saved views |
| `/camera preview [1-3]`, `/camera exit` | Preview or leave a saved view |

## Cameras

Right-click Capture Camera View to save the current position and angle, up to three
poses. Click a camera marker to preview it. The view locks and **Exit Camera Preview**
is selected in the hotbar; use it to return. `/camera exit` is also available.
Owners have a separate remove-current-camera item; visitors cannot remove poses.

Resetting/deleting/switching an entry changes its build space. Template upgrades
preserve existing People worlds until an explicit entry reset or replacement.
See [smoke tests](../SMOKE_TEST.md) for the full behavior checklist.
