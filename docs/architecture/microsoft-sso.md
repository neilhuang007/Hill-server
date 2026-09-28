# Microsoft school verification and linked game accounts

The source implements single-tenant Microsoft OIDC, browser/game confirmation,
durable account linking and participant-based competition ownership. Configuration
is entirely through environment variables; see the [Hill IT setup guide](../operations/microsoft-sso-setup.md).
The existing demo remains in development mode. Real Hill tenant, Cloudflare and
Java/Bedrock pilot acceptance are separate from automated source tests.

## Identity model

| Concept | Authority |
| --- | --- |
| School participant | Immutable Entra `(tid, oid)`, stored as `entra:<tenant>:<object>` |
| Student eligibility | Exact configured Hill tenant and `Hill175.Student` app role |
| Java account | UUID authenticated by an online-mode Paper server |
| Bedrock account | XUID returned by the trusted Floodgate API |
| Account link | One game identity belongs to one school participant; multiple game identities may link to that participant |
| Display name | Plain, sanitized `name` from the validated Microsoft ID token |
| Competition ownership | Participant key, shared across all linked game identities |
| Survival state | Game UUID; inventories are not merged between editions |

Email addresses, Minecraft names and display names never establish school
eligibility or account ownership. The exact tenant alone is insufficient: guests,
staff and students can coexist in a tenant, so the application also requires the
role assigned by IT. A recreated directory object has a new identity and needs
operator-reviewed recovery. [Microsoft claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

## Flow and trust boundaries

```mermaid
sequenceDiagram
    participant Game as Java / Bedrock client
    participant Paper as Hill175 plugin
    participant Web as Embedded loopback auth service
    participant Browser as Browser through Cloudflare / nginx
    participant Entra as Hill Microsoft Entra
    Game->>Paper: Join with verified game identity
    Paper->>Web: Create challenge for fresh connection nonce
    Paper-->>Game: HTTPS sign-in link; remain in lobby
    Browser->>Web: Open challenge URL
    Web-->>Browser: Tenant authorization URL, state, nonce, PKCE
    Browser->>Entra: Sign in to school account
    Entra-->>Browser: Redirect with authorization code
    Browser->>Web: Callback with browser cookie and state
    Web->>Entra: Redeem code with client credential and PKCE
    Web->>Web: Validate token and required Hill role
    Web-->>Browser: School name, game label, one-time confirmation code
    Game->>Paper: /verify browser-only-code
    Paper->>Web: Confirm exact live connection
    Web->>Web: Atomically persist participant and game link
    Web-->>Paper: Participant, display name, expiry
    Paper->>Paper: Recheck connection; enforce one active alias
    Paper-->>Game: Release lobby and apply participant ownership
```

The browser cannot directly unlock a game connection. The code shown after school
sign-in must be typed in the originating game session. Students must not enter
codes supplied by another person. State, a secure browser cookie, nonce and PKCE
bind the Microsoft exchange to its request. Disconnect, expiry, replacement or
restart invalidates pending challenges. The configured callback is fixed, and
Microsoft endpoints are derived from the configured tenant, never browser input.
[Authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

The service exchanges the authorization code over bounded HTTPS requests and uses
Nimbus OIDC for cryptographic ID-token verification. Application checks require
RS256, Microsoft signing keys, the exact
issuer and audience, current token lifetime, nonce, tenant, object ID, role and a
usable school name. Tokens and client credentials are never sent to the Minecraft
client or persisted in the identity store. The flow requests `openid profile`,
without `offline_access` or a Graph directory permission.
[Nimbus OIDC validation](https://connect2id.com/blog/how-to-validate-an-openid-connect-id-token).

Challenges last five minutes, are bounded in memory, and allow at most five code
attempts. Authorization lasts at most 30 minutes and never beyond token expiry.
Every new game connection requires a fresh school exchange. Microsoft may reuse
its own browser session under Hill's Conditional Access policy. Expired game
sessions are disconnected and must reconnect. Role removal is recognized on the
next exchange; there is no immediate Microsoft revocation feed.

## Implementation boundaries

- `auth.sso`: strict environment configuration, Microsoft client/validator,
  challenge and HTTP service, and atomic private identity storage. No Bukkit
  dependency and no public grant/UUID approval endpoint.
- `auth.SsoPlayerSessions`: trusted game identity, per-connection nonce, asynchronous
  confirmation, main-thread admission, one active connection per participant,
  session expiry and visibility/name presentation.
- `CompetitionModule`: resolves the authenticated participant before membership,
  entry limits, invitations, edits and building permission checks. Commands and
  menus use this same participant key.
- `auth.IdentityLinker` and password code: retained only for explicitly configured
  development mode. Microsoft mode does not accept `/register` or password login.

The earlier proposal used a separate identity service and SQL database. For this
single-server deployment the implementation uses an embedded HTTP service on
`127.0.0.1`, bounded worker pools, and one atomically replaced identity file. This
keeps the deployment to one service and avoids an internal network grant protocol.
The file is process-locked; participant and game-link changes persist together
before admission. Competing claims cannot reassign a game identity. This storage
design is for one Paper instance, not multiple writers or a server network.

Existing competition entries keep their IDs and world paths. SSO entries store
participant keys in the existing membership field. Old development nickname
records remain unverified and receive no automatic ownership transfer. Canonical
identity means a student's aliases cannot consume extra category slots or occupy
both places on a team. One participant can have only one active connection.

## Presentation and privacy

Chat, player list and competition menus use the school display name. Private
viewer scoreboards add the school name above the player's Minecraft handle;
the authenticated game profile itself is unchanged. Unauthenticated viewers are
hidden from other players and do not receive their school nameplates. School mode
suppresses public player samples, join/quit, death and advancement broadcasts.
The Hill command allowlist also applies in survival, preventing vanilla message
commands from bypassing authenticated chat audiences. Names are plain text,
not MiniMessage or command input.

Do not publish real student account files or screenshots in GitHub. Third-party
maps, chat bridges and telemetry need their own access review. Actual Geyser
rendering and console/mobile link handling still require device testing. Native
Bedrock sign-in forms, anonymous voting/name capture, duplicate-name UI badges,
and a broader privacy review of third-party plugins are not implemented here.

## Deployment and failure behavior

Use `HILL175_AUTH_MODE=microsoft` in the root-owned systemd environment file.
Missing/invalid configuration, an unreadable/corrupt identity file, unavailable
loopback port or invalid game authentication configuration prevents safe startup.
Microsoft failures reject authentication; there is no development fallback.
Game mutations happen on the server thread; Microsoft calls and identity writes
run off it. Existing verified sessions expire under the same bounded lifetime
during Microsoft outages.

Public web access must traverse Cloudflare, nginx with Origin CA and Authenticated
Origin Pulls, then loopback. Restrict origin web ingress to Cloudflare and reject
unknown Host/SNI. The proxy must supply the canonical Host and HTTPS scheme,
disable caching and avoid token-bearing query logs. An Origin CA certificate
alone does not stop direct-origin requests. The [IT guide](../operations/microsoft-sso-setup.md)
provides environment and nginx examples.

## Remaining operational work

Before student rollout, configure Hill's tenant/app/role assignments and host,
install compatible Geyser/Floodgate, and test permitted/rejected users through the
real proxy on both editions. Confirm name disclosure, recovery owners and a dated
retention policy. Automated tests use synthetic tokens and identities; they do
not prove the external configuration or real student eligibility.

There is no automated legacy migration, account unlink/reassignment UI, local
suspension console, Graph entitlement polling, multi-server database, automatic
retention purge or certificate client-credential flow. Preserve development
projects and perform any transfer only after a reviewed proof of both identities,
quota reconciliation and a coherent backup. Never infer ownership from matching
nicknames or emails. Recovery must restore identity mappings, competition data,
plugin version and worlds together; environment secrets are backed up separately.
