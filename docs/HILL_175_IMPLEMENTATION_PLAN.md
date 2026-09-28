# Hill School 175th Anniversary Minecraft Competition — Implementation Plan

> Historical August product specification. It includes unimplemented services.
> Use the [current README](../README.md), [deployment guide](operations/deployment.md),
> and [September SSO design](architecture/microsoft-sso.md) for current logistics.

**Document date:** 2026-08-26
**Implementation target:** Minecraft Java Edition, Paper 26.2, Java 25
**Capacity target:** 100 concurrent players, approximately 150 entries
**Competition year:** 2026
**Authoritative timezone:** `America/New_York`
**Requirement status:** product decisions approved; schedule and Hill identity-provider details remain placeholders

---

## 0. Implementation rules

- Implement the system described here; do not infer a different competition model.
- Use the canonical terms in [`CONTEXT.md`](../CONTEXT.md).
- Keep Minecraft Nickname, School Identity, School Display Name, and Competition Password separate.
- Treat School Identity as the authority for eligibility, entry limits, team membership, voting, and recovery.
- Treat Minecraft Nickname as an offline protocol identifier only.
- Never treat an offline UUID, source IP, or nickname as proof of identity.
- Never request, receive, store, proxy, or log a Hill/Microsoft password.
- Never store a Competition Password in plaintext.
- Never echo `/login` or `/register` arguments into public chat, console output, command spy, analytics, exception text, or audit payloads.
- Student clients require no mods.
- Litematica is optional and unsupported; a participant using it remains subject to normal placement, ownership, rate, and material rules.
- The controlled Capture Worker may use a custom client mod because it is infrastructure, not a student requirement.
- Do not redistribute Mojang/Microsoft-owned client JARs, libraries, assets, or natives in Git, release artifacts, the launcher archive, or Hill-hosted downloads.
- The requested demo package originally included a Minecraft client JAR; this requirement is intentionally rejected because purchase of accounts does not grant redistribution rights. Demo mode may reference a developer-owned authorized local installation, but the demo/release archive must still exclude Minecraft-owned files.
- Launcher implementation must use an authorized local Minecraft installation or files obtained through an authorized Microsoft/Mojang distribution process.
- Use exact dependency versions in production. Do not use floating versions during the event.
- Pin the production server/client/resource-pack/map-template versions before the pilot.
- Do not upgrade Paper, Velocity, the client version, world format, or hard dependencies while building or voting is open.
- All public HTTP traffic must use `browser -> Cloudflare -> nginx with valid Cloudflare origin certificate -> application`.
- Minecraft TCP traffic must use a dedicated Velocity port; do not expose the Paper backend.
- Implement locally -> test locally -> push to GitHub -> use `plink.exe` -> run `git pull` on the server -> build/restart through the documented deployment procedure.

---

## 1. Master participant flow

```text
receive Hill launcher package
-> run Hill175.bat
-> enter Minecraft Nickname
-> launcher validates nickname format
-> launcher stores nickname locally
-> launcher locates authorized Minecraft client files
-> launcher writes Hill server entry and resource-pack configuration
-> launcher starts Minecraft using the nickname
-> client connects to Velocity
-> Velocity forwards player to Paper authentication world
-> Paper places player in Authentication Lobby
-> Paper blocks all actions except authentication/help/quit
-> Paper displays title + dialog + private chat instructions
-> first-time player enters /register <nickname> <password> <repeatPassword>
-> returning player enters /login <password>
-> authentication command is handled privately
-> first-time registration creates Pending Registration
-> plugin creates short-lived School Identity linking URL
-> player opens browser link
-> identity-provider adapter authenticates eligible Hill person
-> backend links School Identity to Minecraft Nickname
-> backend stores School Display Name
-> Pending Registration becomes Account Link
-> plugin marks Minecraft session authenticated
-> plugin teleports player to Exhibition Hub
-> plugin gives Competition Compass + Rules item in the hub; entry hotbars add Camera, Return to Hub, and Entry Controls
-> player opens Competition Compass or interacts with category NPC
-> player creates or opens Entry
-> optional second Participant is invited
-> invitee accepts
-> system allocates category Build Space
-> owner teleports into Owner Mode
-> visitors enter Visitor Mode
-> owners build and may reset/change category/change Place template before lock
-> owners set project title and description
-> owners place up to three Camera Poses
-> owners submit Entry
-> submission creates preview/final capture jobs
-> Capture Worker renders images
-> moderators review project and images
-> deadline transitions Competition Phase to LOCKING
-> every Build Space becomes read-only
-> final capture jobs run from saved Camera Poses
-> approved entries become anonymously visible on voting website
-> each eligible School Identity casts at most one Vote per Category
-> voting closes
-> winners are calculated and staff-confirmed
-> winner names and archive records are published according to Hill policy
-> IP data is purged 30 days after the event
```

---

## 2. System topology

```text
student Minecraft client
-> public DNS name / Minecraft port
-> Velocity proxy in offline mode
-> private Paper backend
-> Hill175 Paper plugin
-> internal Competition API
-> PostgreSQL
```

```text
student/faculty browser
-> Cloudflare
-> nginx with Cloudflare origin certificate
-> web application
-> Competition API
-> PostgreSQL + image storage
```

```text
Capture Worker
-> Velocity using reserved infrastructure account
-> Paper backend
-> saved Camera Pose
-> standardized client screenshot
-> internal Competition API
-> image storage
-> moderation queue
-> voting website
```

### 2.1 Deployable processes

| Process | Runtime | Responsibility | Public exposure |
|---|---|---|---|
| `hill175-velocity` | Java 25 | Minecraft edge, connection controls, backend isolation | Minecraft TCP only |
| `hill175-paper` | Java 25 / Paper 26.2 | worlds, players, competition interactions | private localhost/LAN only |
| `hill175-plugin` | Paper plugin | authentication lobby, entries, teams, protection orchestration, camera poses | through Paper only |
| `hill175-api` | Java 25 or approved backend runtime | identity linking, password hashes, domain rules, voting, moderation, render queue | nginx/internal only |
| `hill175-web` | TypeScript web application | registration-link pages, staff dashboard, gallery, voting | Cloudflare/nginx only |
| `hill175-capture` | exact Minecraft client + infrastructure-only mod | standardized screenshots | no inbound public port |
| `postgresql` | supported PostgreSQL release | authoritative persistent data | localhost/private only |
| `object-storage` | local S3-compatible store or filesystem adapter | source and published images | application only |
| `nginx` | system package | web reverse proxy and origin TLS | HTTPS from Cloudflare only |

### 2.1.1 Exact proxy/backend mode

```text
Velocity public listener -> online-mode=false because approved offline nicknames must connect
-> Velocity modern forwarding enabled with secret
-> Paper server.properties online-mode=false because Velocity is authoritative edge
-> Paper proxies.velocity.enabled=true
-> Paper proxies.velocity.online-mode=false
-> Paper forwarding secret matches Velocity
-> firewall permits Paper backend connection only from local/private Velocity address
```

- Do not interpret modern forwarding as Microsoft account verification in this topology.
- Hill `/register` and `/login` remain the gameplay authorization layer.
- Do not expose the Paper port even temporarily during testing on production.

### 2.2 Deep module seams

Use these Modules and keep their Interfaces small:

| Module | Interface | Hidden implementation |
|---|---|---|
| `IdentityModule` | `startRegistration`, `completeLink`, `authenticate`, `recover` | provider callbacks, password hashing, rate limits, account-link invariants |
| `EntryModule` | `create`, `changeCategory`, `reset`, `submit`, `lock` | slot enforcement, Team checks, snapshots, state transitions |
| `TeamModule` | `invite`, `accept`, `leave`, `remove` | expiry, capacity, conflicts, audit records |
| `BuildSpaceModule` | `allocate`, `enterOwner`, `enterVisitor`, `reset`, `release` | PlotSquared Adapter, private-world Adapter, loading, unloading, templates |
| `ProtectionModule` | `authorize(ActionContext)` | block/entity/fluid/command/event rules across all worlds |
| `CameraModule` | `place`, `replace`, `remove`, `preview` | marker entities, pose validation, slot rules |
| `CaptureModule` | `enqueue`, `claim`, `complete`, `fail` | worker leases, retries, image checksums, standardized profiles |
| `VotingModule` | `listAnonymousEntries`, `castVote`, `calculateResults` | random ordering, unique constraints, self-vote rule, phase checks |
| `ModerationModule` | `report`, `freeze`, `hide`, `restore`, `revoke` | permissions, evidence, audit log, CoreProtect integration |
| `PhaseModule` | `current`, `transition`, `assertAllowed` | exact timestamps, automatic jobs, recovery after restart |

Adapters required at real seams:

- `SchoolIdentityProvider` -> `PlaceholderProvider` during development -> Hill-selected provider later.
- `PlotBuildSpaceAdapter` -> PlotSquared for Journey and Place.
- `PrivateWorldBuildSpaceAdapter` -> cropped world clone/load/unload for People.
- `ImageStorageAdapter` -> local filesystem in development -> production object storage.
- `NotificationAdapter` -> Minecraft private messages/dialogs -> optional email/admin notification later.
- `ClockAdapter` -> system UTC clock -> deterministic test clock.

---

## 3. Repository target structure

```text
/
-> CONTEXT.md
-> docs/HILL_175_IMPLEMENTATION_PLAN.md
-> docs/research/minecraft-competition-stack.md
-> plugin/
   -> build.gradle.kts
   -> src/main/java/org/thehill/hill175/
   -> src/main/resources/
-> velocity-plugin/
   -> build.gradle.kts
   -> src/main/java/org/thehill/hill175/velocity/
-> launcher/
   -> build.gradle.kts
   -> src/main/java/org/thehill/hill175/launcher/
   -> src/main/dist/Hill175.bat
-> api/
   -> backend source
   -> database migrations
-> web/
   -> voting and moderation web application
-> capture-client/
   -> infrastructure-only client mod
   -> capture worker launcher
-> maps/
   -> README.md
   -> manifests only
   -> no third-party map binaries committed unless license explicitly permits it
-> resource-pack/
   -> source assets
   -> generated zip and hash during release
-> deploy/
   -> systemd units
   -> nginx templates
   -> environment templates
   -> backup scripts
   -> health-check scripts
```

Initial repository migration:

```text
preserve current build
-> create multi-project Gradle settings
-> move existing Paper source into plugin module
-> rename AniversaryServer to Hill175Plugin
-> rename package thehill.org.aniversaryServer to org.thehill.hill175
-> rename plugin from aniversaryServer to Hill175
-> keep Paper 26.2 and Java 25 pinned
-> add CI build for every module
-> add test server configuration
```

---

## 4. Launcher implementation

### 4.1 Distributed files

```text
Hill175/
-> Hill175.bat
-> launcher/hill175-launcher.jar
-> launcher/launcher-config.json
-> launcher/README-FIRST.txt
-> optional licensed redistributable Java runtime
-> no Minecraft client JAR
-> no Mojang assets
-> no Mojang libraries
-> no Microsoft tokens
-> no participant password
```

Developer demo override:

- may point to an existing local authorized Minecraft installation/client cache;
- may not copy that client JAR, libraries, assets, or natives into the launcher package;
- packaging verification must fail if Minecraft-owned files are detected.

### 4.2 `Hill175.bat` flow

```text
double-click Hill175.bat
-> set console title to Hill School Minecraft Competition 2026
-> locate launcher Java runtime
-> if runtime missing show actionable error
-> run hill175-launcher.jar
-> launcher reads local nickname config if present
-> prompt "Minecraft nickname"
-> validate nickname
-> store nickname only
-> locate authorized Minecraft installation/cache
-> validate exact competition client version
-> install/update Hill server entry
-> install/update competition resource pack
-> construct complete Minecraft classpath/native arguments
-> launch Minecraft with selected offline nickname
-> close bootstrap console after successful client start
```

### 4.3 Nickname validation

```text
read user input
-> trim surrounding whitespace
-> require 3-16 characters
-> allow A-Z, a-z, 0-9, underscore only
-> reject reserved infrastructure names
-> reject obvious staff impersonation names
-> reject empty or malformed input
-> persist normalized nickname to %APPDATA%/Hill175/launcher.properties
-> preserve original case for launch
```

Canonical casing:

- first successful Account Link stores `nickname_display_case` from the exact connected nickname;
- all uniqueness and lookup operations use lowercase `normalized_nickname`;
- later clients must connect with the same characters, case-insensitive;
- chat/tab/GUI may preserve the originally registered case;
- staff rename/migration is the only operation that changes canonical nickname casing after registration.

Reserved names include:

- `HillCapture`
- `HillAdmin`
- `Administrator`
- `Moderator`
- `Staff`
- `Server`
- category NPC names
- names beginning with implementation-reserved prefixes

### 4.4 Local storage

Allowed local fields:

- selected Minecraft Nickname;
- launcher version;
- game version;
- installation path;
- resource-pack hash;
- server hostname;
- non-sensitive UI preferences.

Forbidden local fields:

- Competition Password;
- Competition Password hash;
- Hill identity tokens;
- Microsoft refresh/access tokens owned by the competition system;
- School Identity identifier unless encrypted and explicitly approved;
- School Display Name cache unless required for UI and approved;
- moderation data;
- voting data.

### 4.5 Authorized game-file resolution

```text
launcher starts
-> check configured official-launcher installation
-> check exact client version manifest and required libraries
-> if complete use local files
-> if incomplete invoke authorized provisioning path
-> personal computer path may reuse official launcher-installed files
-> Hill-managed computer path may use IT-prestaged files obtained using purchased accounts
-> verify file hashes
-> never download game files from Hill API or GitHub
-> never include game files in launcher release
-> fail closed when files cannot be lawfully resolved
```

### 4.6 Server entry

```text
launcher loads servers.dat
-> create backup
-> add/update Hill 175 server entry
-> preserve unrelated entries
-> set approved hostname
-> set required resource-pack policy
-> save atomically
-> restore backup if serialization fails
```

### 4.7 Launcher acceptance criteria

- `.bat` launches with a double click on supported Windows systems.
- Nickname persists across launches.
- No password or identity-provider token is written locally.
- Existing Minecraft installations remain usable.
- Existing `servers.dat` entries remain intact.
- Missing files produce an actionable error instead of a partial launch.
- Launcher release contains no Minecraft-owned binaries/assets.
- Launcher starts the exact client version tested with production Paper.

### 4.8 Official Microsoft Launcher fallback

```text
participant owns/receives licensed Minecraft account
-> launch through official Microsoft/Minecraft Launcher
-> add Hill server hostname/IP manually
-> connect using official Minecraft profile name
-> offline-mode Hill server does not treat Microsoft profile authentication as the Hill competition login
-> first connection uses /register with the exact connected profile name as nickname
-> complete School Identity link
-> every later connection still uses /login
```

- The official-launcher profile name becomes that Participant's Minecraft Nickname unless staff performs an account migration.
- A School Identity already linked to a different nickname cannot create a second Account Link.
- Microsoft/Minecraft game ownership authentication and Hill School Identity linking are separate operations.

---

## 5. Authentication Lobby and session authentication

### 5.1 Connection state machine

```text
CONNECTING
-> UNAUTHENTICATED
-> PENDING_REGISTRATION or PENDING_LOGIN
-> PENDING_SCHOOL_LINK when first registration requires browser completion
-> AUTHENTICATED
-> DISCONNECTED
```

Failure states:

```text
UNAUTHENTICATED
-> RATE_LIMITED
-> BANNED
-> REGISTRATION_EXPIRED
-> LINK_REJECTED
-> PASSWORD_REJECTED
-> ACCOUNT_CONFLICT
-> PROVIDER_UNAVAILABLE
```

### 5.2 Join flow

```text
Velocity receives connection
-> validate nickname syntax
-> apply connection/IP rate limit
-> reject banned network/account when allowed by policy
-> forward to private Paper backend
-> Paper checks session cache
-> no authenticated session found
-> teleport to Authentication Lobby spawn
-> set Adventure mode
-> clear temporary effects
-> prevent leaving lobby bounds
-> prevent block/entity/inventory/world interaction
-> allow only /login, /register, /help, /rules, /quit
-> suppress normal chat or route only to staff-help channel
-> show title "Please sign in using your Hill credentials"
-> show instructional Paper Dialog with exact /register and /login command examples, Login Help, link status, and Rules
-> send private chat examples
-> start authentication timeout
```

The canonical approved authentication operation remains the command flow. The dialog is instructional and may offer a later optional private-input path, but it must not silently replace `/register` or `/login`.

Session rule:

```text
every new network connection
-> no authenticated gameplay session is reused
-> require /login unless Account Link does not exist, then require /register
-> Paper/Velocity restart invalidates all active gameplay sessions
-> /logout invalidates current session immediately
```

- No reconnect grace period bypasses `/login`.
- `session cache` means current live connection state only; it is not a persisted login token.

### 5.3 First registration command

Canonical syntax:

```text
/register <nickname> <password> <repeatPassword>
```

Processing flow:

```text
receive command packet
-> never broadcast command
-> never copy raw arguments into logs
-> disable command history integrations for sensitive commands
-> compare <nickname> to connected Minecraft Nickname case-insensitively
-> reject mismatch
-> validate password match
-> validate password policy
-> check nickname availability
-> check IP/connection registration limits
-> send password to IdentityModule over authenticated localhost/private channel
-> IdentityModule hashes Competition Password immediately with server-side salt/pepper policy
-> discard plaintext values in plugin and backend after hashing
-> reserve nickname in Pending Registration
-> generate cryptographically random one-use school-link token
-> set token expiry to 10 minutes
-> create HTTPS link
-> send clickable private chat component
-> show link in Paper Dialog
-> poll backend or subscribe for completion
```

Registration completion:

```text
participant opens HTTPS link
-> Cloudflare forwards to nginx
-> web app validates link token
-> web app starts SchoolIdentityProvider flow
-> provider authenticates participant
-> adapter validates eligibility
-> adapter returns immutable School Identity + approved School Display Name + role
-> backend checks School Identity is not linked to another nickname
-> backend checks Participant entry/voting/moderation status
-> backend transaction creates Account Link
-> backend marks Pending Registration completed
-> backend deletes one-use token
-> plugin receives completion
-> plugin authenticates current session
-> plugin applies School Display Name
-> plugin teleports player to Exhibition Hub
```

Registration rejection:

```text
provider rejects or user is ineligible
-> mark link attempt rejected
-> keep Pending Registration only until expiry
-> do not create Account Link
-> do not permit /login
-> delete pending password hash after expiry
-> release nickname reservation
-> show private failure message with Hill help route
```

### 5.4 Returning login command

Canonical syntax:

```text
/login <password>
```

Processing flow:

```text
receive command packet
-> never broadcast command
-> never log raw argument
-> normalize connected nickname
-> load Account Link by normalized nickname
-> if missing show /register instructions
-> check account status
-> check attempt limits
-> verify Competition Password hash
-> discard plaintext password
-> on failure increment handle + IP counters
-> apply increasing delay
-> return generic failure text
-> on success clear relevant failure counters
-> create authenticated session record
-> update last-seen and IP record
-> apply School Display Name and role
-> teleport to Exhibition Hub or last safe owned Build Space
```

### 5.5 Password requirements

- Competition Password must be explicitly labeled: “Do not use your Hill or Microsoft password.”
- Minimum length: 10 characters.
- Maximum length: 128 characters.
- Hash with Argon2id or security-reviewed equivalent.
- Generate unique salt per Account Link.
- Store optional server-side pepper only in environment/secret manager.
- Never return hash through normal API responses.
- Never compare passwords in the Minecraft plugin if the backend is available.
- Plugin may hold plaintext only for the duration of one verification request.
- Clear mutable password buffers where practical.
- Five failed attempts per nickname/IP within 15 minutes -> temporary rate limit.
- Repeated distributed failures -> moderation/security alert.
- Password reset -> school identity linking flow -> new hash -> all current sessions revoked.

### 5.6 Known offline-mode limitation

```text
attacker learns nickname
-> attacker may attempt to occupy that offline nickname before authentication
-> password prevents account access
-> password does not inherently prevent connection-level nuisance or duplicate-name denial
-> Velocity rate limits + connection limits + temporary bans reduce abuse
-> private Hill audience + moderation lowers exposure
-> record as accepted residual risk
```

Duplicate handling:

```text
second connection presents nickname already online
-> existing session authenticated? reject new connection and record attempt
-> existing session unauthenticated? reject new connection by default with clear duplicate-name message
-> staff/session-recovery override may evict stale unauthenticated session
-> never let a new unauthenticated connection evict an authenticated participant automatically
```

- Track last activity and authentication state so staff can clear a stale connection.
- Apply IP/handle cooldowns to repeated duplicate attempts.
- Include duplicate-name recovery in the student help page.

### 5.7 Sensitive command controls

- Register `/login` and `/register` through the plugin command framework.
- Disable tab completion after the command label.
- Do not include supplied arguments in syntax errors.
- Do not use `PlayerCommandPreprocessEvent` logging for these commands.
- Audit installed plugins for command-spy behavior.
- Disable or configure command logging features that record player arguments.
- Sanitize exception traces and structured logs.
- Add automated tests asserting plaintext test passwords never appear in captured logs.
- Document that offline-mode Minecraft transport is not a replacement for HTTPS.
- Require a unique competition-only password.
- Test whether the exact competition client persists command history to disk; the server cannot guarantee deletion of client-side history without a client mod.
- Warn that `/login` and `/register` passwords may remain temporarily visible in the local client's in-session command history.
- Offer a Paper Dialog password input as an optional safer UI over the same IdentityModule while retaining the approved command workflow.
- Record command-history and offline-transport exposure as accepted residual risks if Hill elects to keep command-based passwords.

### 5.8 Authentication provider placeholder

Define Interface:

```java
interface SchoolIdentityProvider {
    LinkStart start(LinkRequest request);
    LinkResult complete(ProviderCallback callback);
    EligibilityResult verify(ProviderIdentity identity);
}
```

Development Adapter:

```text
PlaceholderProvider
-> enabled only outside production
-> uses seeded test identities
-> cannot be enabled when production flag is true
-> displays visible non-production warning
```

Production replacement flow:

```text
Hill selects Microsoft Entra ID or internal system
-> implement new Adapter
-> configure tenant/issuer/client credentials
-> map immutable provider subject
-> map approved full name and role
-> test MFA/federation/conditional-access behavior
-> complete Hill security review
-> disable PlaceholderProvider
```

### 5.9 School Display Name surfaces

```text
School Identity link completes
-> load approved School Display Name
-> apply to Adventure chat rendering
-> apply to tab/player list
-> apply to Team and Entry interfaces
-> apply to Competition Compass visit cards
-> apply to moderation and faculty tools
-> apply to winner/archive interfaces according to publication policy
-> show above-player full-name tag through tested scoreboard/packet/display implementation
```

- The Minecraft Nickname remains the protocol username and staff troubleshooting identifier.
- Hide the vanilla nickname nametag when the full-name tag is active, if the selected implementation can do so reliably.
- Full names may exceed the vanilla 16-character username limit; do not attempt to rewrite the protocol username.
- Preferred implementation seam: `DisplayNameModule`; test packet/scoreboard implementation against 100 players before production.

---

## 6. Exhibition Hub and map recommendation

### 6.1 Recommended map stack

1. **Authentication Lobby:** original small protected room; do not use a large downloaded map.
2. **Exhibition Hub:** original Hill-themed ceremonial hall; primary recommendation.
3. **Journey/Place shared worlds:** generated plot worlds with custom roads, buffers, and category decoration.
4. **People template:** rights-cleared Hill-owned/licensed survey, photography, site-plan, terrain, and OpenStreetMap-derived reference data -> manual correction -> approved cropped template. Existing MapSmith/Voxel Earth output may be used only after its source-data and derivative-use rights are documented.
5. **Fallback schedule option:** purchase one licensed lobby schematic -> record license -> re-theme it -> keep binary outside public source control.

### 6.2 Exhibition Hub design specification

```text
authenticated player arrives at central entrance
-> sightline points directly to 3D Hill ram centerpiece
-> anniversary title visible behind ram
-> Journey wing on left
-> Place wing ahead
-> People wing on right
-> rules/help desk near spawn
-> Competition Compass instructions on floor/wall
-> winners archive behind central hall
-> staff/moderation entrance separated from participant flow
```

Minimum spaces:

- central arrival pad;
- original block-built Hill ram sculpture;
- “Hill 175” anniversary display;
- Journey NPC and example plot portal;
- Place NPC and example interior portal;
- People NPC and example future-campus portal;
- rules wall;
- timeline wall populated from configuration;
- project management kiosk;
- Team invitation help panel;
- Camera Item tutorial display;
- voting-status panel;
- faculty help desk;
- winners/archive gallery;
- hidden maintenance area;
- no command blocks or map-embedded logic.

Recommended dimensions:

- main build envelope: approximately `128 × 128` blocks;
- central hall clear span: approximately `48 × 48`;
- category wings: approximately `24 × 32` each;
- entity budget: minimal;
- pre-generated visible chunks;
- no uncontrolled redstone clocks;
- no portals.

### 6.3 Map sourcing recommendations

#### Primary recommendation: original Hill hub

Implementation status (2026-08-26): the project owner supplied the Minecraft 26.2 world now used as the main exhibition hub. Deployment sanitizes session/player/entity data, pins the external archive checksum, and uses the supplied safe spawn and category-personnel anchors recorded in `server-assets/worlds.yml`.

```text
collect Hill logo/ram/anniversary references
-> convert references into approved block palette
-> create ram sculpture schematic
-> build neutral ceremonial architecture around it
-> add category color/material language
-> run accessibility/readability review
-> remove hidden mechanics
-> freeze hub template
```

Benefits:

- Hill-specific identity;
- no third-party map ambiguity;
- small performance footprint;
- exact NPC/navigation placement;
- easier anniversary archive reuse.

#### Campus base recommendation

```text
inventory every source used by the existing voxelized map
-> record owner, license, derivative-use right, attribution duty, and redistribution limit
-> if any source prohibits export/derivatives, discard that generated geometry from the production template
-> use Hill-owned/licensed campus plans, Hill-approved photographs/direct observation, and rights-cleared terrain data
-> optionally generate an OpenStreetMap/elevation reference with Arnis
-> preserve required OpenStreetMap attribution
-> compare references with the official campus map and photographs
-> reconcile roads, elevations, footprints, parking, tree lines, and Dell area
-> edit terrain in WorldPainter or Minecraft/WorldEdit
-> manually rebuild recognizable architecture rather than treating generated geometry as authoritative
-> remove inaccurate interiors/security-sensitive details
-> crop approved competition extent
-> set world border
-> remove generated entities/data packs/commands
-> complete Hill rights/security review
-> produce immutable Cropped Campus Template
```

Do not export or use Google Photorealistic 3D Tiles-derived Voxel Earth geometry as the editable People template unless Hill receives explicit rights permitting that derivative/export use. Treat the current Voxel Earth output as a visual evaluation reference only until its provenance passes review. See [`docs/voxel-earth-hill-school.md`](voxel-earth-hill-school.md) and [`docs/research/minecraft-competition-stack.md`](research/minecraft-competition-stack.md).

#### Purchased lobby fallback

```text
select small modern lobby from reputable marketplace
-> verify license permits private server use and modification
-> retain purchase/license evidence
-> do not commit binary to public repository
-> scan map for command blocks, data packs, functions, entities, and scheduled ticks
-> strip original server branding
-> add Hill ram and category wings
```

Avoid:

- another real school’s campus map;
- a generic “high school” map presented as Hill;
- massive fantasy hubs unrelated to Hill;
- maps with unclear server-use terms;
- maps requiring old server versions;
- maps containing command blocks, custom executables, unreviewed data packs, or hidden teleport systems.

#### Concrete candidates to inspect first

| Candidate | Intended use | Decision rule |
|---|---|---|
| Owner-supplied Hill 175 exhibition world | production hub | selected; package outside Git, checksum-pin, and preserve the supplied spawn/personnel anchors |
| [Arnis](https://github.com/louis-e/arnis) | rights-cleared OSM/elevation campus reference | use as rough terrain/footprint reference; preserve OSM attribution |
| PlotSquared-generated worlds | Journey/Place production base | use generated protected plots rather than a downloaded static plot map |
| [Server Spawn/Lobby by mikele12327](https://www.curseforge.com/minecraft/worlds/server-spawn-lobby) | authentication-lobby prototype | inspect exact file/license/version; do not redistribute without permission |
| [Aquatic Lobby 150x150](https://builtbybit.com/resources/aquatic-lobby-150x150.93246/) | prototype/fallback lobby | use only if current license permits Hill server use; do not redistribute |
| Paid [BuiltByBit](https://builtbybit.com/resources/categories/minecraft-maps.13/) lobby | schedule fallback | purchase under project owner; archive resource EULA and attribution evidence |
| Generic school maps | Place visual reference only | never present another school/generic campus as Hill |

Selection flow:

```text
inspect original custom-hub estimate
-> if schedule permits build original hub
-> otherwise inspect licensed fallback candidates
-> record acquisition terms
-> security scan/import
-> re-theme with Hill assets
```

### 6.4 Hub interaction flow

```text
player enters hub
-> plugin gives hotbar navigation items
-> player right-clicks category NPC or Competition Compass
-> plugin opens category/entry UI
-> player may preview examples without consuming an Entry Slot
-> player confirms Entry creation
-> plugin creates Entry and Build Space
-> player teleports to safe owner spawn
```

NPC implementation:

- Use Citizens if exact production build passes compatibility tests.
- Store NPC IDs in configuration; never identify NPCs only by display name.
- Provide interaction-entity fallback if Citizens is unavailable.
- Every NPC action must also exist through Competition Compass and commands.

The current Paper 26.2 smoke runtime uses a version-pinned synthetic Player bridge; [Citizens has previously reported Paper 26.2 linkage failures](https://github.com/CitizensDev/Citizens2/issues/3331), so any migration must still pass the exact pinned-build smoke suite. Each guide has a validated skin texture, a hidden native name tag, a floating category/title prompt, and both attack and interact handlers.

---

## 7. Competition phases and schedule placeholders

### 7.1 Phase state machine

```text
SETUP
-> PILOT
-> REGISTRATION_BUILDING
-> LOCKING
-> MODERATION_CAPTURE
-> VOTING
-> RESULTS_PENDING
-> ARCHIVED
```

### 7.2 Configuration placeholders

```yaml
competition:
  timezone: America/New_York
  pilot-opens-at: TBD
  registration-opens-at: TBD
  building-opens-at: TBD
  lock-at: TBD
  moderation-completes-at: TBD
  voting-opens-at: TBD
  voting-closes-at: TBD
  results-publish-at: TBD
  ip-purge-at: calculated as event-end + 30 days
```

### 7.3 Phase permissions

| Operation | SETUP | PILOT | REGISTRATION_BUILDING | LOCKING | MODERATION_CAPTURE | VOTING | ARCHIVED |
|---|---:|---:|---:|---:|---:|---:|---:|
| Register account | staff/test | pilot | yes | no | no | optional voter-only | no |
| Create Entry | staff/test | pilot | yes | no | no | no | no |
| Change Category | staff/test | pilot | yes | no | no | no | no |
| Reset/Change Template | staff/test | pilot | yes | no | staff only | no | no |
| Build | staff/test | pilot | yes | no | staff correction only | no | no |
| Place Camera Pose | staff/test | pilot | yes | no | staff correction only | no | no |
| Submit/Withdraw | staff/test | pilot | yes | no | staff review only | no | no |
| Visit | yes | yes | yes | controlled | controlled | read-only | read-only/optional |
| Vote | no | no | no | no | no | yes | no |

Voter-only browser identity:

```text
eligible person visits voting site without Minecraft participation
-> authenticate through SchoolIdentityProvider
-> create/use School Identity voting record
-> do not create Minecraft Nickname, Account Link, or Competition Password
-> permit Vote operations only
```

Minecraft participation still requires `/register` and an Account Link.

### 7.4 Automatic lock flow

```text
PhaseModule reaches lock-at
-> acquire distributed lock
-> transition phase to LOCKING
-> reject new owner edits immediately
-> finish or cancel in-flight safe operations
-> reject new resets/template/category changes
-> flush plugin outbox
-> save loaded worlds
-> unload empty People worlds
-> snapshot all Build Spaces
-> mark every active Entry locked
-> validate Camera Poses
-> enqueue final capture jobs
-> transition to MODERATION_CAPTURE
-> notify participants and staff
```

Restart recovery:

```text
server starts
-> read authoritative phase
-> compare timestamps
-> detect interrupted transition
-> resume idempotent lock steps
-> never reopen builds merely because Paper restarted
```

---

## 8. Entry and Team rules

### 8.1 Entry constraints

- One Entry belongs to exactly one Category.
- One Entry has one or two Team members.
- One Participant has at most two active Entry memberships.
- One Participant cannot participate in two Entries in the same Category.
- Team membership consumes one Entry Slot for each member.
- A Participant may be solo in one Category and teamed in another.
- A Participant may be teamed in two different Categories.
- Entry limits are enforced by School Identity, not Minecraft Nickname.
- Category changes remain available until lock.
- Category change is rejected if any Team member already occupies that Category through another Entry.

### 8.2 Entry creation flow

```text
open Competition Compass
-> select Create Entry
-> system checks phase
-> system checks Participant Entry Slots
-> show Journey, Place, People cards
-> select Category
-> show exact category rules and Build Space type
-> choose solo start
-> confirm destructive/limit consequences
-> transaction creates Entry in ALLOCATING state
-> BuildSpaceModule allocates Build Space
-> entry becomes BUILDING
-> grant owner permissions
-> teleport to safe owner spawn
-> open short tutorial
```

### 8.3 Team invite flow

```text
owner opens Team menu
-> choose Invite Participant
-> search by Minecraft Nickname or School Display Name
-> select exact person
-> backend checks invitee eligibility
-> backend checks two-entry and category constraints
-> create invitation with 5-minute expiry
-> invitee receives private clickable message + GUI notification
-> invitee opens invitation
-> interface shows inviter, Category, Entry title, current status, Entry Slot consequence
-> invitee accepts
-> transaction rechecks all constraints
-> add invitee as co-owner
-> update PlotSquared ownership or People world access
-> notify both members
-> audit event
```

### 8.4 Team authority

Both members may:

- build;
- place/remove allowed blocks/entities;
- reset build;
- change Place template;
- change Category;
- edit title/description;
- place/replace/remove Camera Poses;
- submit or withdraw before lock;
- invite while solo;
- cancel pending invite;
- teleport home;
- view capture status.

Membership changes:

```text
member chooses Leave Team
-> show build/slot consequences
-> confirm
-> if other member exists transfer sole ownership
-> remove leaving member permissions
-> free leaving member Entry Slot
-> retain build and Entry
-> audit
```

```text
member requests removal of accepted teammate
-> require mutual confirmation or staff action
-> if approved update ownership transactionally
-> never orphan Entry
-> audit
```

- Locked/submitted membership changes require staff action.
- No Team has more than two members.
- No hidden “leader” controls are required after invitation acceptance.

### 8.5 Reset flow

```text
owner opens Manage Entry
-> choose Reset Build
-> show warning: blocks, entities, cameras, title, description, submission will be cleared
-> owner confirms
-> check phase and cooldown
-> create Emergency Snapshot
-> mark Entry RESETTING
-> remove owners/visitors from unsafe area
-> reset Plot or reclone Private Campus World
-> remove Camera markers and capture jobs
-> clear title/description/submission
-> preserve Team and Category
-> restore owner access
-> mark Entry BUILDING
-> teleport owners to safe spawn
-> audit
```

Defaults:

- reset cooldown: 15 minutes;
- self-service reset limit: five per Entry;
- staff override: allowed and audited;
- Emergency Snapshot retention: seven days;
- reset after lock: prohibited.

### 8.6 Category change flow

```text
owner selects Change Category
-> choose new Category
-> ensure new Category differs
-> check every Team member category/slot constraints
-> show total-destruction warning
-> confirm
-> create Emergency Snapshot
-> mark Entry MIGRATING
-> remove users from old Build Space
-> release/archive old Build Space
-> allocate new Category Build Space
-> clear cameras/title/description/submission
-> retain Team
-> set new Category
-> mark BUILDING
-> teleport owners
-> audit
```

---

## 9. Competition Compass and navigation

### 9.1 Hotbar placement

Recommended authenticated hotbar:

| Slot | Item | Action |
|---:|---|---|
| 1 | Competition Compass | My Entries, Visit Builds, Create Entry |
| 2 | Camera Item | Camera placement/management when held |
| 7 | Rules Book | category and server rules |
| 8 | Return to Hub | safe hub teleport |
| 9 | Report/Help | support and moderation report |

Current smoke implementation uses context-specific kits: the hub reserves slots 1 and 8 for the Compass and Rules Book; owned entries reserve slots 1, 4, 8, and 9 for Return, Camera, Rules, and Entry Controls. Reset, submission lock, delete, and category change live in the Build Options GUI instead of consuming hotbar slots. Visitor entries keep Return, Camera Preview, Rules, and navigation. This keeps the Camera actionable only while an Entry is active.

Context kits are applied only when the player changes between hub, owner, and visitor modes. Ordinary movement never clears or recreates the hotbar.

Do not force items into student inventory while actively building if it harms Creative use. Alternative:

```text
hub/world join
-> give navigation items in reserved slots
-> owner enters build mode
-> save navigation items to virtual menu
-> use /project or configurable key-equivalent item access
```

Preferred implementation:

- retain Compass and Camera Item using PDC identity;
- prevent dropping, crafting, storing, renaming, or destroying system items;
- restore missing system items on world transition;
- let configuration select reserved slots.

### 9.2 Compass home

```text
right-click Compass
-> load Participant entries and phase
-> render My Entries on left
-> render Visit Builds in center
-> render Create Entry on right when fewer than two Entry Slots occupied
-> render Team Invitations at bottom
-> render Submission Status and Hub controls
```

No entries:

```text
open Compass
-> show Create Entry prominently
-> click
-> select Category
-> confirm
-> allocate
-> teleport
```

- `Create Entry` is the primary card.
- `Visit Builds` remains available before creating an Entry.
- Allocation always requires a category-specific confirmation.

One entry:

```text
open Compass
-> existing Entry card on left
-> Create Second Entry card on right
-> click existing Entry
-> show Teleport, Manage, Team, Reset, Change Category, Submission
```

Two entries:

```text
open Compass
-> show both Entry cards
-> disable Create Entry
-> explain Entry Slot limit
```

### 9.3 Visit Builds

```text
click Visit Builds
-> choose Category
-> show paginated Entry cards rendered with player-head/skull icons where possible
-> filter by School Display Name, nickname, or project title during building
-> hide disqualified/unsafe/resetting Entries
-> select Entry
-> show confirmation and status
-> request BuildSpaceModule visitor entry
-> load People world if needed
-> teleport to safe visitor spawn
-> apply Visitor Mode
```

- Solo Entry card -> owner head.
- Two-person Team card -> alternating member heads or dedicated Team icon.
- Head rendering failure -> category icon fallback; navigation must remain functional.

Voting anonymity applies to the website, not necessarily in-game building visits. Staff configuration may hide names in-game during the voting phase.

### 9.4 Safe teleport rules

```text
resolve destination
-> load required world/chunk
-> verify safe spawn block and headroom
-> prevent fluid/lava/fire destination
-> prevent boundary intersection
-> preserve owner inventory
-> apply correct game mode before exposing interaction
-> teleport
-> verify mode/permissions next tick
```

Fallback:

```text
safe destination unavailable
-> teleport to Exhibition Hub
-> log structured error
-> notify technical operator
```

---

## 10. Category implementation

## 10.1 Journey

Purpose rule:

- recreate one recognizable Hill building, landmark, façade, parking area, pathway, landscape feature, or bounded campus location;
- target approximately one hour of building;
- do not require a full district or full campus.

Build Space:

- shared `journey_plots` world;
- `64 × 64` horizontal area;
- approximately `48` usable vertical blocks;
- protected visual buffer/road between plots;
- category-themed visitor path;
- configurable terrain preset.

Creation flow:

```text
select Journey
-> choose terrain preset
-> allocate PlotSquared Plot
-> paste selected clean terrain template
-> set plot biome/time defaults
-> set owner spawn
-> set visitor spawn
-> grant Team ownership
-> teleport owner
```

Terrain presets:

- flat grass;
- paved/parking surface;
- landscaped terrain;
- shallow slope;
- blank platform;
- additional approved presets after pilot.

## 10.2 Place

Purpose rule:

- design one usable Hill interior;
- target approximately one hour of building;
- focus on layout, visual design, usability, and Hill community use.

Build Space:

- shared `place_plots` world;
- `32 × 32` footprint;
- approximately `20` usable vertical blocks;
- PlotSquared ownership;
- protected exterior buffer;
- template metadata stored with Entry.

Interior Templates:

- classroom;
- dorm room;
- study area;
- social space;
- dining space;
- blank white-box room.

Creation flow:

```text
select Place
-> choose Interior Template
-> preview dimensions and protected shell rules
-> allocate Plot
-> paste template at canonical origin/orientation
-> mark protected shell blocks when template requires it
-> set owner and visitor spawns
-> teleport owner
```

Template change:

```text
open Manage Entry
-> choose Change Template
-> select new template
-> show reset warning
-> confirm
-> create Emergency Snapshot
-> clear Plot
-> paste new template
-> clear cameras/title/description/submission
-> preserve Team and Category
-> teleport owner
```

## 10.3 People

Purpose rule:

- modify the complete approved cropped Hill campus map to imagine Hill’s future;
- participant may add one or two structures, landscape changes, sustainability features, technology, residences, classrooms, or community facilities;
- the entire cropped template is editable inside its world border.

Build Space:

- one Private Campus World per People Entry;
- source is immutable versioned Cropped Campus Template;
- exact dimensions are `TBD` after map correction and crop review;
- Nether and End disabled;
- world border fixed to crop;
- only active worlds loaded.

Creation flow:

```text
select People
-> create Entry ALLOCATING
-> reserve unique world identifier
-> clone approved Cropped Campus Template
-> write Entry/world metadata
-> validate level.dat and border
-> load world
-> set owner/visitor spawns
-> apply protection policy
-> mark Entry BUILDING
-> teleport owner
```

Load/unload flow:

```text
owner or visitor requests world
-> acquire per-world lifecycle lock
-> if unloaded validate files and load
-> pre-load safe spawn chunks
-> increment active user count
-> teleport
```

```text
last user exits
-> start 5-minute idle timer
-> if no user returns save world
-> flush region files
-> unload world
-> release runtime resources
```

Reset flow:

```text
confirm reset
-> Emergency Snapshot
-> evacuate world
-> unload world
-> delete working copy safely
-> reclone exact template version
-> load and validate
-> clear submission metadata
-> restore access
```

Storage controls:

- run template-size and projected-entry-count calculation before production;
- require free disk budget for 150 entries plus snapshots and captures;
- use filesystem copy-on-write/reflink when available, with verified fallback to normal copy;
- never hard-link writable region files in a way that allows one Entry to mutate the template or another Entry;
- cap simultaneously loaded People worlds based on load test;
- queue visitor entry if safe load capacity is reached;
- unload empty worlds aggressively;
- back up only changed data when the chosen backup tooling safely supports it.

Architecture decision gate:

```text
measure corrected template compressed size + normal clone duration + first-load duration
-> values remain below approved storage/load thresholds? use normal isolated world copies
-> values exceed thresholds? stop production implementation
-> select and prototype copy-on-write/reflink, sparse region copy, or approved instancing Adapter
-> repeat corruption/isolation/load tests
-> proceed only after 150-entry projection passes
```

Do not ship naive full copies merely because the development template is small. Set numeric storage, clone-time, and load-time thresholds after the corrected map exists.

---

## 11. Owner Mode, Visitor Mode, and protection

### 11.1 Mode selection

```text
player enters Build Space
-> query Team ownership
-> owner found -> Owner Mode
-> no ownership -> Visitor Mode
```

Owner Mode:

- Creative mode;
- flight enabled;
- may modify owned Build Space;
- may not modify outside bounds;
- may use allowed non-living entities;
- may use fluids/fire under bounded rules;
- may use optional Litematica printer as normal placements;
- may not execute blocked commands;
- may not spawn living mobs;
- may not create functioning portals/explosions.

Visitor Mode:

- Spectator mode;
- flight retained;
- no block/entity/container/redstone interaction;
- no item transfer;
- no Camera Pose placement;
- no spectator-following another player/entity if it creates abuse;
- safe exit through Compass or Hub item;
- return to Owner Mode when reentering an owned Build Space.

### 11.2 Plot border transition

```text
owner crosses owned Plot boundary
-> start small debounce/buffer check
-> verify player is no longer inside any owned Plot
-> switch to Visitor Mode
-> preserve inventory
-> disable modifications
-> player reenters owned Plot
-> verify ownership
-> switch to Owner Mode
-> restore Creative and flight
```

- Do not rapidly toggle mode near a border; use coordinate hysteresis/debounce.
- Cancel modification events independently of game mode; game mode is not the only protection.
- Recheck after teleports, respawns, world changes, plugin reload avoidance, and reconnect.

### 11.3 Action matrix

| Action | Owner inside owned Build Space | Owner outside | Visitor | Staff observer | Staff edit mode |
|---|---:|---:|---:|---:|---:|
| Break/place blocks | yes | no | no | no | yes |
| Open containers | yes | no | no | configurable read-only | yes |
| Modify signs/books | yes | no | no | no | yes |
| Place fluids | yes | no | no | no | yes |
| Ignite fire | yes, no spread/burn | no | no | no | yes under rules |
| Ignite TNT/explosives | no | no | no | no | no by default |
| Place TNT decoratively | yes | no | no | no | yes |
| Place end crystal decoratively | yes, bounded/limited | no | no | no | yes |
| Trigger end crystal explosion | no | no | no | no | no |
| Place/move minecart or boat | yes, bounded | no | no | no | yes |
| Spawn living mob | no | no | no | no | explicit admin only |
| Use Camera Item | yes | no | no | review only | yes for correction |
| Use redstone | yes, bounded/rate-limited | no | no | no | yes |
| Execute vanilla commands | no | no | no | permission-specific | permission-specific |

### 11.4 Explosion rules

```text
player places TNT/end crystal/respawn anchor/decorative explosive
-> allow placement if inside owned bounds and within entity/block limits
-> detect ignition/activation/damage event
-> cancel explosion creation
-> cancel block/entity damage
-> cancel chain reactions
-> keep decorative item when safe
-> log repeated activation abuse
```

- End crystals may be placed inside owned Build Space.
- End crystals may not explode or damage.
- Cancel end-crystal activation through direct attack, projectile hit, fire/lava interaction, chained explosion, dispenser placement outside allowed rules, piston/cross-boundary movement, and plugin-caused explosion paths.
- Prevent end crystals from damaging players, blocks, entities, neighboring Entries, or system infrastructure.
- Hide or preserve end crystals during capture according to the standardized profile; do not remove legitimate decorative crystals from the saved build.
- TNT may be placed as decoration.
- TNT ignition is canceled.
- Beds/respawn anchors must not explode.
- Wither creation is blocked.
- Fireworks may be restricted during capture/performance-sensitive periods.

### 11.5 Fire and fluid rules

```text
owner places water/lava
-> verify source inside owned bounds
-> allow normal flow inside bounds
-> cancel flow crossing boundary
-> remove leaked boundary fluid if race occurs
```

```text
owner places/ignites fire
-> verify owned bounds
-> allow visible fire
-> cancel spread
-> cancel permanent block burning
-> cancel lava-caused ignition
```

### 11.6 Entity rules

Allowed, with per-Entry limits:

- paintings;
- item frames/glow item frames;
- armor stands;
- minecarts;
- boats;
- end crystals as non-exploding decoration;
- plugin-owned displays/interactions;
- Camera markers;
- other explicitly configured non-living entities.

Blocked:

- zombies;
- creepers;
- skeletons;
- villagers;
- animals;
- bosses;
- all living mob spawn reasons except explicit infrastructure cases;
- spawn eggs;
- spawners;
- wither construction;
- persistent projectile spam;
- portals and dimension transfer.

Processing:

```text
entity spawn event
-> identify Build Space and cause
-> infrastructure whitelist? allow
-> allowed non-living type + owner action + within budget? allow
-> otherwise cancel
-> periodic reconciliation removes escaped/prohibited entities
-> audit only abnormal/repeated cases
```

Blocked-item feedback:

```text
participant attempts blocked spawn egg/mob/explosive activation/portal item
-> cancel action
-> show concise private action-bar reason
-> identify allowed decorative alternative when useful
-> rate-limit repeated feedback
-> escalate only repeated abuse
```

### 11.7 Redstone and physics

- Redstone allowed inside owned bounds.
- Pistons cannot push/pull blocks across bounds.
- Falling blocks cannot cross bounds.
- Dispensers cannot spawn prohibited entities or projectiles across bounds.
- Hopper/container transfer cannot cross bounds.
- Excessive clocks are rate-limited or disabled through server configuration.
- Block physics canceled when it would mutate another Entry or system area.
- Capture mode may temporarily freeze volatile physics in the target world.

### 11.8 Litematica

```text
participant optionally installs Litematica independently
-> participant loads local schematic
-> printer/easy-place produces ordinary placement attempts
-> server validates every placement through ProtectionModule
-> allowed blocks inside bounds are placed
-> blocked materials/entities/actions are rejected
-> no server-side .schem upload exists
-> no WorldEdit permission is granted to participant
```

- Litematica is not included in the Hill launcher.
- Litematica is not required to participate.
- Hill support documentation may state that third-party mods are unsupported.
- Server placement limits must support reasonable printer speed without allowing denial-of-service behavior.
- Every placement remains attributable through CoreProtect/custom logs.
- Participant schematic use means client-side Litematica/EasyPlace/Printer-style ordinary block placement only.
- The server does not parse, import, approve, store, or paste participant schematic files.
- Do not add a compile/runtime dependency on Litematica or a printer implementation.
- Staff/admin schematic imports for the hub, ram sculpture, Journey presets, and Place templates remain available through WorldEdit/FAWE tooling.

---

## 12. Commands, dialogs, and private interaction

### 12.1 Allowed participant commands

- `/register <nickname> <password> <repeatPassword>`
- `/login <password>`
- `/help`
- `/rules`
- `/hub`
- `/project`
- `/visit`
- `/team`
- `/camera`
- `/submission`
- `/report`
- `/logout`

### 12.2 Blocked command classes

- `/kill`;
- `/setblock`;
- `/fill`;
- `/summon`;
- `/give` command use;
- `/gamemode`;
- `/tp` and arbitrary teleport aliases;
- `/execute`;
- `/function`;
- `/data`;
- `/clone`;
- `/worldedit`, `//...`, FAWE commands for participants;
- plugin listing/version commands;
- administrative/moderation commands without permission;
- command blocks and minecart command blocks.

### 12.3 GUI-first rule

```text
NPC/Compass/item interaction
-> open Paper Dialog or inventory GUI
-> perform same domain operation used by command
-> return structured result
-> show private success/failure
```

Commands are fallbacks. Domain rules must not be duplicated in GUI listeners and command handlers.

### 12.4 Text input

- Title maximum: 80 characters.
- Description maximum: 750 characters.
- Optional reference attribution maximum: 500 characters.
- Validate Unicode, formatting codes, URLs, and prohibited content.
- Store plain semantic text; render with escaped components.
- Use Paper Dialog input or authenticated website fallback.
- Do not use chat for passwords other than the explicit private command packet.

Category-specific prompts:

- Journey -> “What Hill location did you recreate, what details make it recognizable, and what references did you use?”
- Place -> “What Hill interior is this, who would use it, and what design choices improve usability?”
- People -> “What future-Hill idea did you add, where is it located, and how does it connect to the development roadmap?”

---

## 13. Camera Item and submission

### 13.1 Camera Item

Base item:

- renamed spyglass or approved resource-pack model;
- Persistent Data Container key identifies system item;
- cannot be dropped, crafted, stored, burned, or used as normal material;
- restored when missing;
- usable only by Entry owners in owned Build Space.

### 13.2 Placement flow

```text
owner selects active Entry
-> holds Camera Item
-> stands at desired screenshot viewpoint
-> aims at build
-> right-clicks
-> CameraModule validates owner, phase, world, position, direction, and slot availability
-> open slot selection 1/2/3
-> choose empty slot or replace existing slot
-> save exact eye position + yaw + pitch + capture profile
-> create small owner/staff-visible Camera marker
-> show confirmation
-> optionally enqueue preview capture
```

Saved fields:

- Entry ID;
- slot 1-3;
- world identifier;
- x/y/z double precision;
- yaw/pitch;
- FOV profile identifier;
- target Build Space identifier;
- template/map version;
- created by School Identity;
- created timestamp UTC;
- latest preview/final render status.

Validation:

- pose must be inside the Entry world or approved perimeter;
- ray/view direction must intersect or point toward owned Build Space;
- pose cannot be inside a solid block or dangerous fluid;
- pose cannot expose another Entry as the primary subject;
- People pose must remain inside world border;
- Journey/Place external perimeter allowance is configurable;
- no more than three active slots.

Smoke implementation enforces the primary-subject rule by requiring a point six blocks along the saved view ray to remain inside the owned Build Space. It also revalidates the player body, eye block, Entry bounds, and world border before every preview, so later building changes cannot turn an old pose into an unsafe teleport.

### 13.3 Marker behavior

```text
save Camera Pose
-> spawn a tagged camera-head marker
-> tag marker with Entry ID and slot
-> show only to Team and staff when possible
-> hide from visitors by default
-> left-click or right-click enters its exact Camera Preview
-> hide all markers during Camera Preview
-> restore markers when preview exits
```

The smoke preview uses the saved player-eye viewpoint while keeping the player's safe feet location exact, locks position/yaw/pitch and pose changes, displays the numbered preview as a title and persistent boss bar, and replaces the Camera item with an exit item that accepts either click direction.

### 13.4 Camera management

```text
/camera or Camera Item secondary action
-> list slots 1/2/3
-> show pose coordinates, preview status, created-by, timestamp
-> Teleport Preview
-> Replace
-> Remove
-> Request Preview Capture
```

### 13.5 Submission flow

```text
owner opens Submission
-> enter/edit title
-> enter/edit description
-> optional reference attribution
-> validate at least one Camera Pose
-> validate Entry not resetting/migrating/frozen
-> show final checklist
-> confirm Submit
-> mark SUBMITTED
-> enqueue rate-limited PREVIEW renders
-> notify both Team members
```

Before lock:

- either Team member may withdraw submission;
- either may edit and resubmit;
- building remains available;
- changing blocks after capture marks images stale;
- changing category/template/reset clears submission and cameras;
- final deadline capture always uses locked build state.

---

## 14. Capture Worker

### 14.1 Capture profile

Default standardized profile:

- exact competition Minecraft client version;
- exact competition resource pack;
- no user shaders;
- fixed 1920×1080 output;
- fixed FOV, default `70` unless Camera Pose selects approved preset;
- fixed GUI hidden;
- fixed render distance after load testing, target 12-16 chunks;
- fixed entity distance;
- fixed graphics mode;
- fixed brightness/gamma;
- fixed weather and time policy;
- no chat, nametags, Camera markers, selection outlines, or staff entities visible;
- deterministic screenshot filename and metadata;
- PNG master; derived WebP/JPEG for web delivery.

### 14.2 Worker flow

```text
worker starts
-> authenticate infrastructure identity
-> poll internal render queue
-> claim job with expiring lease
-> ensure exact client/profile/resource-pack versions
-> join Velocity as reserved HillCapture identity
-> plugin grants capture-only role
-> load target world
-> teleport to Camera Pose
-> apply spectator/invisible state
-> set time/weather/capture controls
-> hide HUD and overlays
-> wait for required chunks, textures, lighting, and entities
-> remove/hide Camera markers
-> capture screenshot
-> validate dimensions and non-empty pixels
-> calculate checksum
-> upload master image
-> create web derivatives
-> report success with metadata
-> release job lease
-> leave/unload target when safe
```

Infrastructure admission:

```text
normal public connection requests reserved HillCapture-like nickname
-> Velocity rejects before Paper
```

```text
Capture Worker connects through localhost/private capture listener
-> presents signed short-lived infrastructure admission token
-> Velocity validates token, source restriction, purpose, and expiry
-> create capture-only session
-> Paper never trusts reserved nickname alone
```

### 14.3 Retry rules

```text
job failure
-> classify transient or permanent
-> transient -> retry with exponential delay, maximum 3 automatic attempts
-> client crash -> restart client and reclaim expired job
-> missing world/pose -> permanent failure and staff alert
-> image validation failure -> retry once after longer chunk wait
-> repeated failure -> moderation dashboard manual action
```

### 14.4 Preview and final images

- Preview capture may occur after Camera Pose placement or submission.
- Preview image is marked non-final.
- Build change after preview marks preview stale.
- Final capture runs only after authoritative lock snapshot.
- Final image record includes world/template version and snapshot identifier.
- Moderator can request recapture from identical pose.
- Moderator cannot silently move pose; pose correction must create audited revision.
- Before-lock renders are always `PREVIEW`; never label them final-candidate in user or moderator interfaces.
- Rate-limit previews per Camera Pose and Entry to prevent stale capture queue flooding.
- Only post-lock `FINAL` renders are eligible for voting publication.

### 14.5 Capture infrastructure validation

```text
prototype one exterior Journey build
-> prototype one dark Place interior
-> prototype one large People world
-> compare client visual output
-> measure chunk-ready time
-> test headless/virtual-display stability
-> calculate time for 450 final images
-> size storage and moderation window
-> approve hardware or move worker to dedicated machine
```

---

## 15. Voting website

### 15.1 Voting flow

```text
eligible person opens voting site
-> Cloudflare/nginx/web application
-> SchoolIdentityProvider authentication
-> verify current Competition Phase is VOTING
-> load anonymous Journey entries in voter-specific deterministic random order
-> voter opens entries and images
-> voter selects one Journey Entry
-> repeat for Place
-> repeat for People
-> submit/change votes before close
-> backend enforces one current Vote per School Identity per Category
-> show confirmation without totals
```

### 15.2 Anonymity

During voting, hide:

- School Display Name;
- Minecraft Nickname;
- Team member names;
- plot/world identifiers that reveal identity;
- live totals;
- submission timestamps that create recognizable ordering;
- moderation notes;
- direct server coordinates.

Display:

- anonymous Entry number;
- Category;
- title;
- description;
- approved images;
- optional approved reference attribution.

### 15.3 Ordering

```text
voter + Category + competition secret seed
-> deterministic shuffle
-> stable order for that voter
-> different order for other voters
-> no global submission-order advantage
```

### 15.4 Vote constraints

- Unique database constraint: `(competition_id, voter_school_identity_id, category)`.
- Vote insert/update runs transactionally.
- Vote changes allowed until voting close.
- Self-voting policy: unresolved launch decision; proposed default is disabled.
- Staff accounts may vote only if Hill eligibility rules permit.
- No Minecraft Nickname-based vote limits.
- No IP-based vote identity.
- IP data may support abuse investigation but cannot replace School Identity constraint.

### 15.5 Result calculation

```text
voting closes
-> PhaseModule prevents further writes
-> snapshot vote table
-> calculate valid totals per Category
-> exclude disqualified Entries
-> detect ties
-> generate staff-only result report
-> authorized staff confirms tie policy and winners
-> transition RESULTS_PENDING -> ARCHIVED
-> publish winners
```

Tie policy placeholder:

- Hill must select runoff, faculty panel, shared award, or deterministic tie-break before voting opens.

### 15.6 Winner titles, awards export, and archive

```text
authorized staff confirms winners
-> create immutable winner records for Journey, Place, and People
-> grant each winning Team member LuckPerms title group hill175_og_builder_2026
-> display "OG Builder" title in server chat/tab/profile interfaces
-> store Category, project title, description, approved images, Team attribution, and competition year in archive
-> generate staff-only winner export for physical backpack-tag production
-> publish approved winner archive page
-> preserve title across future server seasons unless moderation revokes it
```

Winner export fields:

- School Display Name;
- School Identity reference for staff reconciliation;
- Minecraft Nickname;
- winning Category;
- project title;
- solo/Team membership;
- award text: `Minecraft OG Builder`;
- reverse text: `Hill Minecraft Competition 2026`;
- publication/consent status.

Physical tag design/printing remains a Hill operational project; the competition system supplies the approved winner list and archive assets.

---

## 16. Moderation and faculty operations

### 16.1 Roles

| Role | Capabilities |
|---|---|
| Participant | own Entries, Team actions, visit, submit, vote if eligible |
| Faculty Observer | visit all, view ownership, no edits |
| Moderator | reports, mute, freeze, hide, rollback workflow, revoke access |
| Submission Reviewer | approve/reject images and text for voting |
| Capture Operator | retry/review capture jobs |
| Competition Administrator | phases, entries, roles, restoration, result confirmation |
| Technical Operator | deployment, backups, logs, health, database recovery |

- Do not grant Minecraft operator status as a substitute for roles.
- Use LuckPerms groups and explicit plugin permissions.
- Staff edit mode must be opt-in, time-bounded, and audited.

### 16.2 Report flow

```text
participant uses Report item or /report
-> select player/chat/Entry reason
-> enter short description
-> capture current world/coordinates/target identifiers
-> create moderation case
-> notify online moderators
-> preserve relevant log references
-> moderator reviews
-> resolve with outcome and notes
```

### 16.3 Entry moderation

```text
moderator opens Entry
-> inspect in Visitor Mode
-> review CoreProtect history and reports
-> choose Warn, Freeze, Hide, Restore, Disqualify, Revoke
-> require reason
-> execute domain operation
-> create Moderation Event
-> notify Team when policy permits
```

Freeze:

```text
freeze Entry
-> deny owner modifications
-> keep staff inspection
-> cancel pending reset/category/template operations
-> pause capture publication
-> preserve current world
```

### 16.4 Chat

- Chat enabled after authentication.
- Authentication Lobby chat restricted.
- School Display Name used in chat; nickname available to staff details.
- Chat messages logged with timestamp, School Identity, nickname, world, and moderation context.
- Provide mute, temporary mute, and permanent competition chat restriction.
- Filter/flag prohibited content according to Hill policy.
- Do not send Competition Password commands to chat logging.

### 16.5 Rollback

```text
moderator identifies harmful edits
-> CoreProtect lookup by School Identity/nickname/time/area
-> create evidence reference
-> freeze Entry
-> preview rollback scope
-> apply rollback
-> verify Build Space integrity
-> unfreeze or escalate
-> audit
```

---

## 17. Data model

Use UUID/ULID primary identifiers. Store all timestamps in UTC. Display Eastern Time.

### 17.1 Core tables

#### `competition`

- `id`
- `year`
- `name`
- `timezone`
- `phase`
- phase timestamps
- `created_at`
- `updated_at`

#### `school_identity`

- `id`
- `provider_type`
- `provider_tenant`
- `provider_subject`
- `display_name`
- `role_type`
- `eligibility_status`
- `created_at`
- `updated_at`
- unique `(provider_type, provider_tenant, provider_subject)`

#### `account_link`

- `id`
- `school_identity_id`
- `normalized_nickname`
- `nickname_display_case`
- `password_hash`
- `password_algorithm`
- `password_changed_at`
- `status`
- `created_at`
- `last_authenticated_at`
- unique `school_identity_id`
- unique `normalized_nickname`

#### `pending_registration`

- `id`
- `normalized_nickname`
- `nickname_display_case`
- `password_hash`
- `link_token_hash`
- `source_ip_encrypted_or_restricted`
- `expires_at`
- `completed_at`
- `created_at`

#### `auth_session`

- `id`
- `account_link_id`
- `minecraft_connection_id`
- `source_ip`
- `started_at`
- `authenticated_at`
- `ended_at`
- `result`
- `failure_reason_code`

#### `entry`

- `id`
- `competition_id`
- `category`
- `status`
- `build_space_id`
- `title`
- `description`
- `reference_attribution`
- `template_id`
- `created_at`
- `updated_at`
- `submitted_at`
- `locked_at`
- `moderation_status`
- `published_anonymous_number`

#### `entry_member`

- `entry_id`
- `school_identity_id`
- `joined_at`
- `left_at`
- unique active membership constraints enforced transactionally

#### `team_invitation`

- `id`
- `entry_id`
- `inviter_identity_id`
- `invitee_identity_id`
- `status`
- `expires_at`
- `created_at`
- `responded_at`

#### `build_space`

- `id`
- `type` (`PLOT`, `PRIVATE_WORLD`)
- `world_name`
- `plot_identifier`
- bounds/world border
- owner spawn
- visitor spawn
- template version
- lifecycle state
- `created_at`
- `reset_count`
- `last_loaded_at`
- `last_saved_at`

#### `camera_pose`

- `id`
- `entry_id`
- `slot`
- `world_name`
- x/y/z
- yaw/pitch
- `fov_profile`
- `created_by_identity_id`
- `created_at`
- `updated_at`
- unique `(entry_id, slot)`

#### `render_job`

- `id`
- `entry_id`
- `camera_pose_id`
- `render_type` (`PREVIEW`, `FINAL`)
- `status`
- `attempt_count`
- `lease_owner`
- `lease_expires_at`
- `requested_at`
- `started_at`
- `completed_at`
- `failure_code`
- `capture_profile_version`

#### `image_asset`

- `id`
- `render_job_id`
- `storage_key`
- `content_type`
- `width`
- `height`
- `checksum`
- `moderation_status`
- `created_at`
- `published_at`

#### `vote`

- `id`
- `competition_id`
- `voter_school_identity_id`
- `category`
- `entry_id`
- `created_at`
- `updated_at`
- unique `(competition_id, voter_school_identity_id, category)`

#### `moderation_event`

- `id`
- `actor_school_identity_id` or system actor
- target type/id
- action
- reason code
- notes
- evidence references
- `created_at`

#### `emergency_snapshot`

- `id`
- `entry_id`
- `build_space_id`
- `reason`
- `storage_path`
- `created_by_identity_id`
- `created_at`
- `expires_at`
- `restored_at`

### 17.2 IP retention

```text
event ends
-> schedule purge at +30 days
-> delete raw source_ip from auth/session/security records unless active legal/security hold exists
-> expire or rewrite application logs containing raw IPs
-> ensure web access logs follow the same retention window
-> ensure backup retention/encryption-key policy does not preserve recoverable raw IPs beyond the approved window
-> retain non-identifying aggregate counts
-> record purge job completion
-> alert if purge fails
```

- Restrict raw IP access to Technical Operator/security role.
- Do not show IPs in normal faculty moderation screens.
- Never publish IPs.
- Document legal/security hold override and approval authority.
- Configure Paper/Velocity/application logging to avoid duplicating raw IPs outside the restricted retention store where feasible.
- Trust `CF-Connecting-IP` or equivalent only on requests proven to originate from Cloudflare; otherwise ignore the header.

---

## 18. Internal interfaces and endpoints

Representative internal HTTP Interfaces; exact paths may change only with synchronized clients.

### 18.1 Authentication

```text
POST /internal/v1/registrations
-> nickname + plaintext Competition Password over authenticated localhost/private channel
-> IdentityModule validates and hashes immediately
-> plaintext is never queued, logged, or returned
-> pending registration + link URL
```

```text
GET /link/{token}
-> browser identity-provider start
```

```text
GET/POST /auth/provider/callback
-> provider completion
-> Account Link transaction
```

```text
POST /internal/v1/sessions/login
-> nickname + plaintext password over localhost/private authenticated channel
-> success/failure + School Display Name + role
```

```text
GET /internal/v1/registrations/{id}/status
-> pending/completed/rejected/expired
```

### 18.2 Entries and teams

- `POST /internal/v1/entries`
- `POST /internal/v1/entries/{id}/change-category`
- `POST /internal/v1/entries/{id}/reset`
- `POST /internal/v1/entries/{id}/change-template`
- `POST /internal/v1/entries/{id}/submit`
- `POST /internal/v1/entries/{id}/withdraw`
- `POST /internal/v1/entries/{id}/invitations`
- `POST /internal/v1/invitations/{id}/accept`
- `POST /internal/v1/invitations/{id}/decline`
- `POST /internal/v1/entries/{id}/leave`

### 18.3 Cameras/capture

- `PUT /internal/v1/entries/{id}/cameras/{slot}`
- `DELETE /internal/v1/entries/{id}/cameras/{slot}`
- `POST /internal/v1/entries/{id}/captures`
- `POST /internal/v1/render-jobs/claim`
- `POST /internal/v1/render-jobs/{id}/complete`
- `POST /internal/v1/render-jobs/{id}/fail`

### 18.4 Reliability

```text
plugin performs domain operation
-> API unavailable
-> authentication operations fail closed with clear message
-> non-auth event writes enter local durable outbox when safe
-> retry with idempotency key
-> API deduplicates
-> remove outbox record after acknowledgment
```

- Do not queue plaintext passwords.
- Do not queue one-use identity-provider tokens longer than their expiry.
- Every mutation uses idempotency identifier.
- API validates phase and domain rules; plugin-side checks improve UX but are not authoritative.

---

## 19. Resource pack

```text
create Hill palette + ram model + Camera model + category icons
-> build deterministic resource-pack zip
-> calculate SHA-1 required by server protocol
-> publish through Cloudflare-backed HTTPS
-> configure launcher and Paper with exact hash
-> Capture Worker uses identical pack
```

Assets:

- Hill ram Camera Item model;
- Journey/Place/People icons;
- Hill 175 title textures;
- GUI icons;
- category color palette;
- no unauthorized third-party textures.

Policy:

- preconfigured launcher installs/accepts pack;
- official-launcher users receive server pack prompt;
- require pack if essential to UI/capture consistency;
- provide clear failure message and retry;
- version pack independently and record version on render jobs.

---

## 20. Performance targets

### 20.1 Capacity

- 100 concurrent authenticated players.
- Approximately 150 Entries.
- Up to 300 Entry memberships, subject to individual two-entry limit.
- Up to 450 final Camera images.
- Multiple loaded plot worlds plus bounded active People worlds.

### 20.2 Performance budgets

- Paper tick target: 20 TPS under expected peak.
- No sustained main-thread task above 50 ms.
- World clone/reset work off main thread where filesystem operations permit; Bukkit world access remains correctly scheduled.
- GUI response target: under 500 ms under normal load.
- Login API response target: under 1 second excluding participant typing/linking.
- Plot teleport target: under 3 seconds after chunks are available.
- People unloaded-world entry target: under 10 seconds or explicit loading UI.
- Capture job throughput sized to complete all final images inside moderation window.

### 20.3 Load controls

- pre-generate hub and plot-world chunks;
- cap living entities globally at zero except infrastructure exceptions;
- per-Entry non-living entity budget;
- cap item drops;
- clear prohibited entities;
- rate-limit redstone clocks and physics abuse;
- unload empty People worlds;
- limit simultaneous world clone/reset jobs;
- limit simultaneous capture jobs;
- configure view/simulation distance from load tests;
- do not use Folia unless every dependency and custom Module is proven compatible.

---

## 21. Backups and recovery

### 21.1 Backup schedule

```text
every 15 minutes
-> PostgreSQL WAL/transaction backup strategy
```

```text
nightly
-> stop/coordinate world saves
-> snapshot database
-> snapshot map templates
-> snapshot changed build worlds
-> snapshot image metadata/assets
-> encrypt backup
-> copy off primary disk/server
-> verify checksum
```

```text
before deployment or phase transition
-> manual verified backup
-> record commit SHA + plugin versions + map/resource-pack versions
```

### 21.2 Recovery scenarios

#### Paper crash

```text
systemd restarts Paper
-> plugin reads phase
-> validate worlds
-> restore authenticated players through new login
-> resume idempotent jobs
```

#### API outage

```text
existing logged-in play continues when cached authorization is safe
-> new registrations/logins show unavailable message
-> no insecure bypass
-> non-sensitive events queue locally
-> recover API
-> drain outbox
```

#### Corrupted Plot

```text
freeze Entry
-> select latest valid snapshot/CoreProtect rollback
-> restore to staging
-> validate
-> replace working Plot
-> unfreeze
-> audit
```

#### Corrupted People world

```text
freeze Entry
-> unload world
-> restore snapshot
-> validate level/regions
-> load staging copy
-> approve
-> replace working world
-> audit
```

#### Accidental category/reset action

```text
locate seven-day Emergency Snapshot
-> staff approves restore
-> freeze current Entry
-> snapshot current state
-> restore prior state
-> reconcile category/team/cameras/submission
-> audit
```

---

## 22. Observability

### 22.1 Structured logs

Log:

- process/service;
- timestamp UTC;
- request/correlation ID;
- School Identity ID where authorized;
- nickname where operationally needed;
- Entry/Build Space identifiers;
- operation;
- result/error code;
- duration;
- no plaintext passwords/tokens.

### 22.2 Metrics

- online players;
- authenticated/unauthenticated sessions;
- login success/failure/rate-limit counts;
- active Entries by Category;
- loaded People worlds;
- world load/unload duration;
- reset/category migration duration;
- TPS/MSPT/memory/GC;
- entity/block counts;
- API latency/error rate;
- database connections/slow queries;
- render queue depth/success/failure;
- image storage usage;
- votes by Category without exposing live totals to users;
- backup age and verification status;
- IP purge job status.

### 22.3 Alerts

- Paper/Velocity/API/web down;
- TPS below threshold;
- disk free space below world/snapshot budget;
- database unavailable;
- backup stale/failed;
- render queue cannot finish before voting;
- repeated auth attack pattern;
- unexpected living-mob count;
- world clone corruption;
- failed phase transition;
- IP purge overdue.

---

## 23. Security checklist

```text
Velocity is only public Minecraft process
-> Paper binds private interface
-> modern forwarding secret configured
-> backend port firewalled
```

```text
public web request
-> Cloudflare validation
-> nginx origin certificate
-> strict HTTPS
-> application session protections
```

Required controls:

- secrets in environment/root-readable files, not Git;
- database not public;
- internal API authenticated;
- CSRF protection on browser mutations;
- OIDC state/nonce when provider selected;
- secure cookies;
- rate limits on registration/login/link/vote/report;
- account/entry/vote unique constraints;
- HTML/component escaping;
- image content-type and size validation;
- path traversal prevention;
- map/schematic binary scanning when staff imports assets;
- command-block/data-pack/function stripping from imported worlds;
- dependency pinning and vulnerability review before launch;
- moderator least privilege;
- audit logs protected from participant modification;
- Competition Password warning against reuse;
- accepted offline-mode duplicate-name/transport risks documented to Hill.

---

## 24. Deployment layout

Recommended server directories:

```text
/opt/hill175/
-> repo/
-> velocity/
-> paper/
-> api/
-> web/
-> capture/
-> maps/templates/
-> worlds/
-> images/
-> backups/
-> secrets/
-> logs/
```

Public network:

- `25565/tcp` -> Velocity only;
- `80/443` -> nginx, restricted to Cloudflare source ranges when operationally required;
- Paper backend port -> localhost/private only;
- PostgreSQL -> localhost/private only;
- internal API -> localhost/private only;
- capture control -> localhost/private only.

Deployment flow:

```text
edit locally
-> run unit/integration/build tests
-> commit scoped changes
-> push GitHub
-> plink -i "C:/Users/neil_/.ssh/hetzner.ppk" root@135.181.78.188
-> cd /opt/hill175/repo
-> git pull --ff-only
-> build exact commit
-> run migrations
-> install artifacts
-> restart affected systemd units in dependency order
-> health checks
-> Minecraft smoke test
-> web smoke test through Cloudflare
-> record deployment commit/version
```

Restart order:

```text
PostgreSQL ready
-> API ready
-> web ready
-> Velocity ready
-> Paper ready
-> Capture Worker ready when capture queue enabled
```

Do not run `git pull` before local code has been pushed. Do not edit production code directly except documented emergency procedure followed by immediate repository reconciliation.

---

## 25. Test plan

### 25.1 Authentication tests

- register valid nickname/password/link;
- reject nickname mismatch;
- reject duplicate nickname;
- reject School Identity already linked;
- reject expired link;
- reject ineligible identity;
- login success/failure;
- rate limit by nickname and IP;
- restart during pending registration;
- password reset;
- ensure plaintext password absent from logs/outbox/database;
- command not visible in public chat;
- duplicate offline nickname nuisance scenario;
- provider unavailable;
- authenticated session disconnect/rejoin.

### 25.2 Entry/team tests

- solo Entry creation;
- second Entry in different Category;
- reject third Entry;
- reject duplicate Category membership;
- invite/accept/decline/expire;
- accept race with another Entry consuming slot;
- both members reset/change template/change category/submit;
- member leaves;
- mutual/staff removal;
- category change conflict across both members;
- restart during allocation/reset/migration.

### 25.3 Protection tests

Test every action inside own Plot, outside own Plot, in another Plot, in hub, and in People world:

- block break/place;
- buckets and fluid flow;
- fire spread/burning;
- TNT ignition;
- end crystal placement/activation;
- beds/respawn anchors;
- pistons/slime/honey;
- redstone clocks;
- dispensers;
- hoppers;
- item frames/paintings/armor stands;
- boats/minecarts crossing bounds;
- falling blocks;
- containers;
- signs/books;
- spawn eggs/spawners;
- portals;
- Litematica placement speed;
- vanilla commands;
- disconnect during mode transition.

### 25.4 Build-space tests

- Journey allocation/reset;
- Place every template and template change;
- People clone/load/unload/reset;
- world border;
- disk-full handling;
- corrupted template handling;
- 20+ simultaneous private-world loads;
- 100-player traversal/load test;
- emergency snapshot restore.

### 25.5 Camera/capture tests

- slots 1-3;
- replace/remove;
- invalid pose;
- stale preview after edit;
- marker visibility;
- marker hidden in screenshot;
- dark interior;
- exterior/weather;
- large People map;
- client crash/retry;
- image checksum/dimensions;
- final capture from locked snapshot;
- 450-image throughput rehearsal.

### 25.6 Voting tests

- one Vote per Category;
- vote change before close;
- reject after close;
- anonymity fields absent;
- deterministic per-voter shuffle;
- self-vote policy;
- team ownership exclusion;
- disqualified Entry removal;
- tie result;
- concurrent double submit;
- result snapshot and staff confirmation.

### 25.7 Pilot

```text
internal staff technical test
-> reset data
-> 10-20 participant pilot
-> one-hour Journey build
-> one-hour Place build
-> People map modification
-> Team workflow
-> Camera workflow
-> automatic lock
-> complete capture
-> mock moderation
-> mock anonymous voting
-> backup restore
-> collect issues
-> fix
-> reset production data
-> launch
```

---

## 26. Implementation phases

### Phase 0 — Repository and build foundation

```text
create multi-module structure
-> correct plugin naming/package
-> pin Java/Paper/Velocity versions
-> add formatter/lint/test/build CI
-> add local run configurations
-> document environment variables
```

Exit criteria:

- all modules build;
- empty Paper and Velocity plugins load;
- CI passes;
- no secrets committed.

### Phase 1 — Domain and persistence

```text
implement canonical domain types
-> create migrations
-> implement PhaseModule
-> implement audit records
-> add repository adapters and transaction tests
```

Exit criteria:

- database enforces nickname, School Identity, Entry Slot, Team, camera, and Vote uniqueness;
- phase transitions are restart-safe.

### Phase 2 — Authentication backend and lobby

```text
implement Pending Registration
-> implement password hashing/login
-> implement PlaceholderProvider
-> implement linking web page
-> implement /register and /login
-> implement Authentication Lobby restrictions
-> implement School Display Name
```

Exit criteria:

- registration cannot complete without school link;
- every join requires `/login`;
- sensitive arguments absent from logs;
- authenticated player reaches hub.

### Phase 3 — Launcher

```text
implement .bat bootstrap
-> nickname prompt/persistence
-> authorized installation detection
-> exact client launch
-> server/resource-pack configuration
-> packaging checks
```

Exit criteria:

- clean Windows test machine launches;
- only nickname stored locally;
- release contains no Minecraft-owned files.

### Phase 4 — Hub and navigation

```text
build Authentication Lobby
-> build/import Exhibition Hub
-> add ram centerpiece
-> add NPCs
-> implement Compass/Dialog UI
-> implement safe teleports
```

Exit criteria:

- every major operation reachable without remembering commands;
- hub cannot be modified by participants.

### Phase 5 — Entries and Teams

```text
Entry creation
-> two-slot enforcement
-> invite/accept
-> ownership
-> reset/category migration state machines
-> GUI management
```

Exit criteria:

- all approved solo/team/category scenarios pass transactional tests.

### Phase 6 — Journey and Place

```text
configure PlotSquared worlds
-> implement Plot Adapter
-> create terrain/interior templates
-> implement reset/template change
-> visitor spawns
```

Exit criteria:

- protected plot lifecycle works;
- `64×64×48` Journey and `32×32×20` Place pilot completed.

### Phase 7 — People

```text
correct/crop campus template
-> implement Private World Adapter
-> clone/load/unload/reset
-> storage/load test
-> visitor directory integration
```

Exit criteria:

- multiple People worlds load safely;
- reset restores exact template;
- disk and load budgets approved.

### Phase 8 — Protection and moderation

```text
centralize ActionContext authorization
-> implement event matrix
-> integrate WorldGuard/PlotSquared/CoreProtect/LuckPerms
-> implement entity/explosion/fluid/redstone controls
-> reports/freeze/rollback
```

Exit criteria:

- full protection matrix passes;
- visitors cannot modify;
- owners cannot affect neighbors/system areas.

### Phase 9 — Camera and submissions

```text
Camera Item
-> marker/pose slots
-> title/description
-> submit/withdraw
-> stale-image tracking
```

Exit criteria:

- each Entry stores up to three valid poses and complete submission text.

### Phase 10 — Capture

```text
capture client mod
-> worker queue
-> standardized profile
-> upload/storage
-> retries
-> moderation approval
```

Exit criteria:

- Journey/Place/People images generated automatically;
- 450-image rehearsal fits schedule.

### Phase 11 — Voting website

```text
School Identity login
-> anonymous gallery
-> randomized ordering
-> one Vote per Category
-> result calculation
-> archive pages
```

Exit criteria:

- no owner identity leaks during voting;
- concurrency and unique constraints pass.

### Phase 12 — Operations and launch

```text
systemd/nginx/Cloudflare
-> monitoring
-> backups
-> restore rehearsal
-> phase schedule
-> staff runbooks
-> pilot
-> production reset
-> launch
```

Exit criteria:

- end-to-end rehearsal succeeds;
- Hill approves identity provider, dates, privacy, map, rules, and tie policy.

---

## 27. Required configuration

```yaml
server:
  environment: development|staging|production
  public-hostname: TBD
  public-fallback-address: 135.181.78.188:25565
  show-fallback-address-in-launcher-readme: true
  minecraft-port: 25565
  exact-client-minecraft-version: 26.2
  exact-paper-minecraft-line: 26.2
  exact-paper-build: TBD_PINNED
  exact-velocity-build: TBD_PINNED

auth:
  provider: placeholder|entra|internal
  registration-link-ttl: 10m
  login-timeout: 10m
  password-min-length: 10
  password-max-length: 128
  max-failures: 5
  failure-window: 15m

entries:
  max-members-per-entry: 2
  max-active-memberships-per-person: 2
  allow-category-change-until-lock: true
  reset-cooldown: 15m
  max-self-resets: 5
  emergency-snapshot-retention: 7d

journey:
  plot-width: 64
  plot-depth: 64
  build-height: 48

place:
  plot-width: 32
  plot-depth: 32
  build-height: 20

people:
  template-version: TBD
  template-path: TBD
  idle-unload-after: 5m
  max-loaded-worlds: TBD_AFTER_LOAD_TEST

camera:
  max-poses: 3
  allowed-fov-profiles: [default]

capture:
  width: 1920
  height: 1080
  render-distance: TBD_AFTER_TEST
  max-attempts: 3
  profile-version: 2026-v1

voting:
  self-voting-allowed: TBD_DEFAULT_FALSE
  live-totals-visible: false
  names-visible: false
  tie-policy: TBD

privacy:
  raw-ip-retention-after-event: 30d
```

---

## 28. Launch blockers and placeholders

The system is not production-ready until every item below is resolved:

- Hill selects School Identity provider.
- Hill supplies provider tenant/issuer/client configuration.
- Hill confirms eligibility claims/groups.
- Hill confirms legal Minecraft account provisioning and authorized client-file staging.
- Exact event timestamps are configured.
- Tie policy is selected.
- Public name/archive policy for non-winners is approved.
- Self-voting policy is explicitly confirmed before voting opens.
- Every campus-map source has documented derivative/export rights; prohibited Google/Voxel Earth-derived geometry is excluded.
- Rights-cleared voxelized campus map is corrected, cropped, security-reviewed, and frozen.
- Hill ram/logo/anniversary assets are approved.
- Journey and Place sizes pass one-hour pilot.
- People world storage/load budget passes.
- Capture Worker hardware completes 450-image rehearsal.
- Downloaded/purchased assets have documented licenses.
- Cloudflare/nginx origin configuration is validated.
- Backup restore rehearsal succeeds.
- IP purge procedure is validated.
- Faculty roles and named operators are assigned.

---

## 29. Definition of done

```text
participant runs launcher
-> selects nickname
-> connects
-> registers with competition-only password
-> links eligible School Identity
-> full Hill name displays in server
-> login required on every new join
-> participant creates up to two Entries in different Categories
-> participant invites one teammate and teammate accepts
-> both Team members build/manage
-> Journey/Place plots protect owners and visitors correctly
-> People receives private editable cropped campus copy
-> participant may fly everywhere but modify only owned Build Space
-> living mobs blocked
-> decorative non-living entities allowed within limits
-> end crystals/TNT may be placed but cannot explode
-> fluids/fire remain bounded and non-destructive
-> vanilla commands blocked
-> optional Litematica placements remain protected
-> participant saves up to three Camera Poses
-> dedicated Capture Worker produces standardized images
-> Entry title/description/images reach moderation
-> automatic deadline locks every Build Space
-> voting website hides identities and totals
-> one School Identity casts at most one Vote per Category
-> winners are staff-confirmed and published
-> backups, logs, moderation, and recovery operate
-> raw IP data is purged 30 days after event
```
