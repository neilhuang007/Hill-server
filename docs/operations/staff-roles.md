# Staff roles and account moderation

The plugin separates ordinary players, staff, moderators and administrators.
These capabilities are server roles and do not require Minecraft operator status.
They are available after sign in. Every Hill permission defaults to off, so
Minecraft operator status grants no Hill staff tools; only the roles below do. The existing development preview still does
not verify school membership. Microsoft admission requires Hill IT configuration
and a real tenant pilot.

| Role | Capabilities |
| :--- | :--- |
| Player | Build in personal/invited campuses, manage their own guests and propose blueprint changes |
| Staff | Player tools, staff information, blueprint review and legacy campus recovery |
| Moderator | Staff tools, kick, timed or permanent mute and ban, unmute and unban |
| Administrator | Moderator tools, blueprint recovery snapshots and assignment of lower roles |

Staff, moderators and administrators receive `hill175.blueprint.review` for
[reviewing and merging proposals](blueprint-review.md). `/review` opens the
proposal inbox and private highlighted previews directly on the approved
blueprint, with Current/Proposed, navigation and Accept/Deny buttons. Administrators also
receive `hill175.blueprint.backup` for manual blueprint-only recovery snapshots.
Students cannot edit the accepted blueprint directly, and review permission does
not bypass invitations into another student's personal draft. The chat filter
and no-private-messaging policy also apply to staff.

In the optional legacy shared-campus mode, staff, moderators and administrators
receive `hill175.campus.rollback` and can use the existing Campus Map recovery
window to preview and restore individual areas. Each restore keeps the existing confirmation, safety snapshot and area
boundary checks. [Recovery instructions](shared-campus.md#staff-recovery)
describe the workflow and the optional LuckPerms permissions for staff restricted
to particular areas. A scoped LuckPerms grant does not grant a general staff role.

## Assigning roles

Microsoft roles come from the validated ID token. Hill IT can define these four
Users/Groups app roles on the same Entra application:

| Environment variable | Default value | Server role |
| :--- | :--- | :--- |
| `HILL175_ENTRA_REQUIRED_ROLE` | `Hill175.Student` | Player |
| `HILL175_ENTRA_STAFF_ROLE` | `Hill175.Staff` | Staff |
| `HILL175_ENTRA_MODERATOR_ROLE` | `Hill175.Moderator` | Moderator |
| `HILL175_ENTRA_ADMINISTRATOR_ROLE` | `Hill175.Administrator` | Administrator |

Values must be distinct. Any one of these assigned roles permits school admission
within the exact configured tenant. When several are present, the highest role
applies. IT must limit assignments to the intended school members. A staff member
does not need a student role as well. The role is refreshed on the next Microsoft
exchange, and the current verification lease lasts at most 30 minutes.
[Microsoft app role instructions](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps).

The console can also appoint an administrator after their first sign in:

```text
hillstaff role <game-name-or-UUID> administrator
```

An administrator can appoint staff and moderators in game:

```text
/hillstaff role <target> staff
/hillstaff role <target> moderator
/hillstaff role <target> player
```

Players can check their own role with `/hillstaff whoami`. Staff can inspect an
account with `/hillstaff info <target>`. Administrators can manage only lower
roles, and cannot promote anyone to their own level or change their own role.
The console and trusted Microsoft role assignments can appoint administrators.

Local appointments follow the school participant across linked Java and Bedrock
identities. The effective role is the higher of the local appointment and the
current Microsoft app role. To remove a capability completely, remove both grants
where applicable. A local appointment survives Microsoft app role removal until
an operator explicitly removes that appointment. Roles created in development
mode belong only to that game UUID and do not transfer to a school account.

## Moderation commands

| Command | Result |
| :--- | :--- |
| `/hillstaff mute <target> 10m <reason>` | Block public chat and messaging commands for ten minutes |
| `/hillstaff mute <target> permanent <reason>` | Mute until explicitly removed |
| `/hillstaff unmute <target>` | Remove the account mute |
| `/hillstaff ban <target> 7d <reason>` | Block server admission for seven days |
| `/hillstaff ban <target> permanent <reason>` | Ban until explicitly removed |
| `/hillstaff unban <target>` | Remove the account ban |
| `/hillstaff kick <target> <reason>` | Disconnect that participant's current game session |

Durations accept minutes (`m`), hours (`h`) and days (`d`), up to 365 days, or
`permanent`. Reasons are required and must be plain text, up to 240 characters.
Moderators can act only on lower roles. These commands do not grant general
WorldEdit, LuckPerms, filesystem, console or Minecraft operator access.

Use the exact game name of a previously signed in player, their game UUID, or
their full `entra:<tenant>:<object>` account identifier. Names that map to multiple
participants are rejected. Microsoft display names and email addresses are never
moderation identifiers. The info command shows known game names, UUIDs and school
display names. New records are added as players sign in after this update.

In Microsoft mode a ban attaches to the immutable tenant and user object IDs.
Known game aliases are rejected on connection or before school verification.
A fresh alias cannot complete verification or link to that banned school account.
Online aliases lose authenticated gameplay access and are disconnected. A mute
also applies across aliases and survives reconnection. Expiration, unban and
unmute use the same account record. This blocks use of the Hill Minecraft server;
it does not disable the person's Microsoft account or change their Microsoft 365
access. [Microsoft identity claim reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

The explicit `game:<UUID>` target can block one transport identity independently.
To remove such a separate sanction, use that same explicit identifier. Normal
game names and UUID targets resolve to their linked school account when known.
Development mode has only game UUID sanctions and provides no Microsoft account
ban assurance.

## Names and private storage

School mode continues to use the sanitized Microsoft `name` claim in chat and the
player list. Verified viewers see the school name alongside the Minecraft handle
in the nameplate. Unverified viewers cannot see those names. The Minecraft profile
and transport UUID remain unchanged. Names do not control authorization. Actual
Java and Bedrock presentation with Hill accounts still needs the tenant pilot.

Roles, sanctions, known game aliases and the moderation
audit are written atomically to `plugins/Hill175/moderation.json`. The file is
private, process locked and excluded from Git. Moderation writes run away from
the game thread. Invalid storage prevents startup. A persistence failure stops
Paper rather than reporting an unsaved sanction as successful. Sanctions apply
after durable storage, and the command acknowledges successful storage.

Back up this file together with `school-identities.json`, competition records and
worlds. Restoring an older moderation record can restore older bans and role
assignments. The audit retains the actor, account, action, time, reason and expiry;
review its retention with the school's account retention policy.
Keep `commands.log: false` in `spigot.yml` because
authentication commands contain private credentials. The plugin requires this
setting before enabling admission.

Use the Hill moderation commands for school account sanctions. Vanilla bans and
third party commands operate outside this school participant system and cannot
provide the same alias guarantees.
