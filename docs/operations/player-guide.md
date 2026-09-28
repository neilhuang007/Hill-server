# Player workflow (current development server)

The current release is for controlled testing. School verification automatically
approves development identities; Microsoft SSO and Bedrock integration are planned
in the [identity design](../architecture/microsoft-sso.md).

Join using the Java version supported by the pinned Paper server (26.2). In the
authentication lobby, register a unique event password with
`/register <currentNickname> <password> <repeatPassword>`. Returning players use
`/login <password>`. Never use a school/Microsoft password here. Command arguments
are not broadcast; the deployed Spigot configuration disables console command
logging, but the player's own command history can retain them.

After development approval, use the Competition Compass or the category guides:

- **Journey:** a 64×64 outdoor plot.
- **Place:** a 32×32 interior shell.
- **People:** a private copy of the pinned campus template.

Each participant can join at most two entries in different categories, with at
most two members per entry. Current enforcement is nickname-based; the SSO
migration must make that limit apply across all linked accounts.

Owners build in Creative mode inside their entry; visits and submitted entries
are read-only. Entry Controls provides reset, delete, switch-category, and
submission actions with confirmations. Survival is a separate world/inventory flow.

## Commands

| Command | Purpose |
| --- | --- |
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
