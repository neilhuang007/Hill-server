# Staff incident review and private visual recordings

There are **two distinct layers**. Neither is a rollback system or a promise that
literally every client action can be reconstructed.

| Layer | What it provides | Enabled by default |
| --- | --- | --- |
| Hill incident timeline, `/hillreplay` | Timestamped server events, sampled positions, staff-only text/particle playback | Yes |
| Hill-hardened Flashback Server 1.2.4 | Private server-side visual player-POV archives for authenticated players; staff import into Flashback | No, explicitly opt in |

The existing campus Restic/WorldEdit recovery tools remain the restoration layer.
Do not restore the live world merely to view a recording.

Open **Hill Menu**, choose **Staff**, then choose **Recent Incidents** or
**Play Incident Timeline**. Enter a time window and optionally an exact player
name or game UUID. Each linked Minecraft account has its own replay attribution.

## Staff-only access

`/hillreplay` requires **both** a signed-in canonical Hill `STAFF`, `MODERATOR` or `ADMINISTRATOR` role and
`hill175.replay`. The normal role attachment grants the permission. Bukkit OP or
an externally granted permission alone does **not** bypass the role check.
The local server console is an authorized operator surface. See
[staff roles](staff-roles.md) for role administration.

```text
/hillreplay recent
/hillreplay recent 30 ExactPlayerName
/hillreplay play 15 64c2e6fa-31d5-4819-97ef-e525139dd247
```

The optional window is 1–120 minutes (default 15), followed by an exact name or
UUID. `recent` returns at most the newest 30 matches; `play` returns at most 40,
chronologically, four ticks apart. Particle markers are sent **only to that staff
viewer**, within 48 blocks in their current world. The viewer is not teleported;
no entities, blocks or world time are changed. Sign-out or role/permission loss
stops playback. Names can change; use the UUID for account attribution.

Raw upstream `/replay`, including `/flashbackserver:replay`, is replaced with a
denial executor and empty completion list whenever FlashbackServer is present,
**even when visual capture is disabled**. Neither students nor in-game staff nor
console can use it to start uncontrolled captures or expose replay files. The
hardened upstream command permission also defaults to `false`.

Visual archives are retrieved by authorized **server operators**, not a public
site or in-game download command. A staff member may use a private workstation
with a Minecraft-version-matched [Flashback client mod](https://modrinth.com/mod/flashback)
to import/view the archive. Recorded students need **no client mod or resource
pack**. Do not copy archives into gallery assets, student map exports, a web root,
or a student-accessible shared folder.

## Incident timeline: exact coverage and limits

The event layer records:

- Successful, non-cancelled block break/place and bucket fill/empty events.
- Player-caused damage, damage received by players, environmental player damage,
  player deaths and entities killed by players.
- Entity/block explosions, with source type and affected-block count. A source
  the plugin cannot attribute is explicitly `environment` (all-zero UUID).
- Player block coordinates every 200 ticks **only if** the player moved at least
  two blocks since the preceding sample or changed worlds; first sample included.
  At 20 TPS that is roughly ten seconds, not a video or every movement packet.

Each row has UTC time, actor UUID/current name, world UUID/name, location, event
kind and short type/cause detail. It does **not** log chat, passwords, commands,
authentication/browser codes, map bearer URLs, inventories, every plugin edit,
redstone/fluid tick, or every player input. Cancelled attempted actions are not
recorded. Events a different plugin changes without these Bukkit events can be
absent. The audit records online players, including events in the login lobby;
visual capture separately waits for successful authentication.

Files live at `plugins/Hill175/incident-replay/`:

- Bounded 4,096-event asynchronous write queue; overload/disk failures drop events
  and issue rate-limited server warnings (at most one warning per minute).
- 8 MiB daily/numbered segments, approximately seven-day retention with UTC daily
  boundary grace (up to an extra day), and a 128 MiB pruning target. Pruning at
  segment rollover can temporarily add one active segment above that target.
- Queries scan at most the newest 16 MiB; the command warns when older data may be
  omitted. Malformed rows are skipped. Shutdown allows five seconds to drain.
- Writes flush to the OS but are not an immutable/tamper-proof or crash-proof
  security ledger. Backups and restricted operator access still matter.

Set `incident-replay.enabled: false` to disable this layer. Restrict the data
folder to the runtime account and authorized operators; unlike the dedicated
visual directory, the legacy incident directory inherits its parent permissions.

## Enable the optional visual recorder

Deployment has an explicit switch in the protected server environment:

```dotenv
HILL175_PACKET_REPLAY_ENABLED=true
```

The normal installer first prepares the hardened artifact while the server is
still running, then installs from those local staged files **after stopping the
service**. Install/verify perform no network download or source compilation.
The environment switch overrides plugin `packet-replay.enabled`. Without it,
existing configurations default to capture disabled. Never install the raw
upstream JAR and assume its defaults satisfy this policy.

For a disposable staging runtime, the equivalent explicit commands are:

```bash
# Linux, JDK 25 already installed; no production action implied.
bash ops/install-packet-replay.sh prepare --runtime /tmp/hill-replay-stage --java-home /path/to/jdk-25
# Only after the destination server is stopped:
bash ops/install-packet-replay.sh install --runtime /tmp/hill-replay-stage
bash ops/install-packet-replay.sh verify --runtime /tmp/hill-replay-stage
```

On Windows, avoid the Windows Store `python` alias:

```powershell
uv run --python 3.13 python ops/packet-replay-install.py prepare --runtime runtime/replay-stage --java-home "C:/path/to/jdk-25"
uv run --python 3.13 python ops/packet-replay-install.py install --runtime runtime/replay-stage
uv run --python 3.13 python ops/packet-replay-install.py verify --runtime runtime/replay-stage
```

`prepare` downloads a SHA512-pinned official JAR and an independently pinned
release-source archive, applies a strict narrow source overlay, compiles only
its NMS-free classes with `javac --release 21`, and runs policy/cap self-checks.
The official Paper 26.2 adapter is preserved unchanged. Files, checksums, source
commit and patch recipe digest are recorded in the provenance sidecar. MIT
license/attribution are embedded in the resulting JAR. Source of truth:

- `server-assets/packet-replay-manifest.json`
- `ops/replay/flashback_hardening.py`
- `ops/build-packet-replay.py`, `ops/packet-replay-install.py`

No built JAR, raw recording or generated world belongs in Git. The local
hardening is a small maintained overlay, **not** an upstream-supported security
configuration. Upgrades require source/checksum review, tests and sandbox checks;
never substitute an automatically selected latest release.

Installed rollback/verification files are listed by
`bash ops/install-packet-replay.sh files`:

```text
plugins/FlashbackServer-Hill-1.2.4.jar
plugins/FlashbackServer-Hill-1.2.4.jar.provenance.json
plugins/FlashbackServer/config.yml
```

A renamed duplicate raw FlashbackServer JAR is detected from its `plugin.yml`
and rejected before installation. The managed config disables telemetry and
automatic clips. Starting enabled capture with an absent/unpatched artifact,
wrong policy limits, incompatible Minecraft version, or unsafe upstream config
fails closed rather than silently providing unprotected recording.

## Visual archive behavior, privacy and gaps

- Every **authenticated** online player is considered, in every world of this
  Paper process. No authentication screen/token exchange is recorded on purpose.
  A separate survival **process** needs its own compatible recorder; this module
  cannot record another server.
- The default is 32 active-or-finalizing recorder slots, configurable via
  `packet-replay.max-recorders` (1–64). **The current
  `server-config/server.properties` admits up to 120 players; neither the default
  nor the supported maximum recorder setting covers 120 simultaneous POVs.**
  Exceeding capacity logs a conspicuous `REPLAY GAP`; some POVs will be absent.
  Operators must align admission limits with load-tested recording capacity and
  finalization headroom, rather than assuming every admitted player is covered.
  Do not raise recorder limits blindly: monitor heap, save latency and gap logs,
  and retain headroom for asynchronous ZIP writes and transient snapshot buffers.
- At most one recorder starts per server tick. The first segment lasts 30–60
  seconds, staggered by UUID; later segments last approximately 60 seconds.
  Segments stop at disconnect, authentication loss or shutdown.
- Segment save is asynchronous. The next segment for that player waits until the
  prior archive finishes saving; **there is a capture gap while it saves**, and
  possibly while waiting for a slot. This keeps finalization memory and gap
  attribution bounded rather than promising uninterrupted footage.
- A hard cap of **16 MiB retained payload-plus-action allowance and 100,000
  actions per recorder** drops further actions, logs `REPLAY GAP`, and causes a
  partial segment to rotate. An oversized/failed/missing initial snapshot is
  flagged, not represented as normal complete footage. This is not a bound on
  total JVM heap: NMS snapshot construction, packet encoding and ZIP writing use
  additional transient buffers. Thirty-two slots can retain roughly 512 MiB
  before such overhead. Load-test appropriate memory/player limits.
- At each start, native Paper 26.2 pairing data for **already-tracked entities the
  viewer can see** is injected into the recorder, with peer player-info before
  spawn/metadata/equipment. Nothing is resent to the real client, hidden entities
  are not revealed, and no live hide/show flicker is introduced. This repairs the
  upstream late-start snapshot omission without changing its NMS adapter.
- The upstream movement sampler examines a server AABB. The Hill hook filters
  its encoded movement records **before retention**, keeping self and currently
  visible/tracked entities only, so hidden/untracked coordinates are excluded.
- Signed/system/disguised chat, actionbar/title/subtitle, bossbar/scoreboard/team
  UI and custom payloads are excluded. This deliberately removes `/download`
  bearer links and `/verify` chat/browser credentials from current server message
  channels. Inventory GUI, books, cookie/transfer/custom-payload packets are also
  refused upstream. **Not every visual/UI element is retained.** Player identity,
  visible blocks/entities, signs and other world content can still be personal;
  future plugins must not put secrets into world-visible names/signs/items.

The recorder is not a screen capture, anti-cheat proof, every-click history, or
unloaded-world simulation. It cannot reproduce client-only shaders, local mods,
private UI deliberately excluded above, unreceived packets, or activity in areas
outside recorded client views. The initial upstream terrain snapshot is capped
at eight chunks of radius and captures loaded chunks only. A server crash can
lose the active in-memory segment. Confirm visual usability in a version-matched
staff viewer before relying on footage for a decision; packet/container tests
are not native visual acceptance.

## Archive attribution, retention and operator review

Private files live under `plugins/Hill175/packet-replay/`:

- `<UTC-epoch-ms>-<player-UUID>-<segment-UUID>.flashback`
- `segments.tsv`, with UTC timestamp, event, requesting player UUID, archive name
  and short status (`STARTED`, `BOOTSTRAPPED`, `SEGMENT_END`, `SAVED`,
  `SAVED_WITH_GAP`, `SAVE_FAILED`, disconnect/shutdown or cleanup status).
- `.flashback.pending` files while ZIP output is being written. Abandoned pending
  files are **not** normal completed footage; retention counts them too. Preserve
  a useful incident copy privately before routine expiry, not in a public export.

On POSIX the archive directory is mode `0700`, completed archives and index are
`0600`. Upstream fallback directories are private too. On Windows secure the
runtime ACL for the owning service account and authorized operators; POSIX mode
calls do not establish Windows ACLs. Filenames use UUIDs, not untrusted names.
The index is fsynced and rotated at 8 MiB (one previous generation retained), but
operator access/crashes/disk failure can still make an outcome uncertain. Raw
chat, bearer tokens, IPs and browser records are never put in this index.

Completed **and abandoned pending** archives expire after seven days and are
pruned oldest-first toward **2 GiB total**. Active writes are never deleted by
retention; they count toward the target, so in-flight writes can temporarily
exceed it. Pruning runs at startup, on save, and roughly once a minute. Errors
are logged; disk-full/index failures are gaps, not guaranteed recording.
A `SAVED` status means the server produced an archive, not that a staff viewer
has visually verified it or that no sampling/rotation gap exists. `SAVED_WITH_GAP`
requires extra caution and may be unrenderable if bootstrap failed.

Staff viewer import: if the matching Flashback build's file picker only accepts
`.zip`, copy the private `.flashback` archive to a private local filename ending
`.zip` (the container is ZIP; do not alter its contents). Keep the server index
filename/checksum with the staff case record. Do not change server suffixes or
retention patterns ad hoc. Native viewer import/playback is a separate required
pilot, not established merely by a successful headless server boot.

Tell players concisely that protected gameplay is recorded for incident review;
limit who can access recordings and obtain Hill's retention/privacy approval.
