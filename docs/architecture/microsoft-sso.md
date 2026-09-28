# Microsoft sign-in and linked Minecraft accounts

Status: proposed architecture, researched 2026-09-28. **Microsoft SSO, the identity service, database migration and Bedrock integration described here are not implemented.** The current plugin still uses development authentication. This document is the logistics and implementation handoff, not evidence that school verification is live.

The requested experience is: join from Java or Bedrock, receive a school sign-in link, authenticate with Microsoft, prove control of that same game connection, then enter as the student's Hill-managed name. Repeat the school authorization flow on **every new game connection**. A remembered Microsoft browser session can make this quick; a previously linked Minecraft account alone must never skip it.

## Recommended decisions

| Concern | Decision |
| --- | --- |
| School identity | One Hill Microsoft Entra tenant; a participant is keyed by the immutable pair `(tid, oid)`. |
| Eligibility | Require an explicit `Hill175.Student` app role assigned by Hill IT to the eligible student group. Define a separate staff role and policy if needed. |
| Minecraft identity | Verified Java account UUID or Floodgate-verified Bedrock XUID; usernames are labels. |
| Linking | Many Minecraft accounts may belong to one participant; each Minecraft identity belongs to only one participant. No automatic reassignment. |
| Authentication | Browser authorization code flow with PKCE; a browser-only confirmation code must be entered in the originating live game session. |
| Ownership | Entry memberships, limits, votes and moderation follow participant IDs across all linked accounts. |
| Presentation | School-managed display name in chat, player list and competition UI; separately implement and test overhead nameplates. |
| Services | Paper owns game state. A separate local identity web service owns OIDC, linking and short-lived session grants. Use transactional persistence. |

These are project recommendations. Hill IT must confirm the eligibility group and authoritative name field; students and staff in the same tenant are not automatically the same eligibility class.

## School registration and verification

Create a single-tenant Entra **Web** application for Hill 175 and use the tenant-specific authority `https://login.microsoftonline.com/<HILL_TENANT_ID>/v2.0`. A tenant can contain guests as well as members, so single tenancy alone does not prove student status. Require the exact approved app role after token validation; do not admit everybody whose email appears to end with a Hill domain. Microsoft's tenant and claim documentation supports these distinctions. [Tenant types](https://learn.microsoft.com/en-us/entra/identity-platform/single-and-multi-tenant-apps), [OIDC tenant endpoints](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc).

Define `Hill175.Student` for users/groups and assign it to a curated student security group. Set **Assignment required = Yes** on the enterprise application and arrange administrator consent. Group assignment requires suitable Entra licensing and does not include nested group members; direct user assignment is a fallback if IT cannot use groups. Require `roles` explicitly even when assignment is required. A disabled role definition can still appear for existing assignments, so revoke assignments when withdrawing eligibility. [App roles](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps), [Assignment rules](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/assign-user-or-group-access-portal).

Use `(tid, oid)` as the unique external school key and a separate internal participant UUID. `name` is a display value, while `email` and `preferred_username` can change and must not control authorization or account merging. `sub` is app-specific; the tenant/object pair also makes migration to another Hill application explicit. Ask IT whether `name` represents the approved student display name; it is not independent proof of a legal name. [Microsoft ID token claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

Start with `openid profile`. The validated ID token can provide the school identity, assigned role and name, so a broad directory query is unnecessary. If IT requires another name field, add the least necessary delegated Graph permission, normally `User.Read` for the signed-in student's own profile, and fetch only the chosen fields. Missing required name data should lead to a correction/help path, never a self-entered “verified” name. Graph `/me` is a delegated call; do not request directory-wide application permissions merely to display a name. [Graph Get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0).

The student's personal Microsoft/Xbox/Minecraft account and their Hill work/school account remain separate identities. School OIDC does not issue Minecraft ownership or Xbox credentials. The game authenticates its supported account first; the school flow then establishes Hill participation. Floodgate allows Bedrock accounts to connect without also owning a Java account. [Floodgate overview](https://geysermc.org/wiki/floodgate/).

## End-to-end connection flow

1. **Join and quarantine.** Derive the trusted game identity from the transport. Bind the server's startup instance ID to a fresh connection nonce, independent of the persistent player UUID. Keep the player in the authentication lobby with movement, chat, inventory, building and non-auth commands restricted. Do not expose other students' names there.
2. **Issue a challenge.** The plugin asks the identity service to create an expiring request bound to `(server instance, connection nonce, game identity)`. Suggested defaults: five-minute lifetime and one active request per connection. Return a random, unguessable browser URL and a short rendezvous code. The URL identifies a request; it cannot authorize a session by itself.
3. **Open the website.** Java receives a clickable HTTPS link. Always also show a short URL and code, including in a Bedrock form, so mobile/console users can use another browser. This is the application's pairing code, not Microsoft's device authorization grant. Never require the student to type their Microsoft password in Minecraft or the launcher. Test actual Bedrock devices; do not assume Java chat-link behavior transfers to them. Floodgate exposes a forms API. [Floodgate API](https://geysermc.org/wiki/floodgate/api/).
4. **Perform Microsoft sign-in.** Bind fresh `state`, `nonce` and an S256 PKCE verifier to that browser session and request. Use `response_type=code` with a fixed registered callback, such as `https://<AUTH_HOST>/auth/microsoft/callback`. Offer account selection so a shared browser cannot silently link the wrong student. Redeem the code on the service, validate the result, then require the Hill tenant and student role. A new connection must run this exchange again, even if the service has an old session cookie. Microsoft may reuse its own browser SSO session under Hill's Conditional Access rules. [Authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).
5. **Prove both sides.** The signed-in browser displays the approved school name, game edition/account label and request context, then generates a new one-time confirmation code visible **only in that browser**. The student returns to the originating game and runs `/verify <confirmation-code>`, or submits it in a game form. The plugin supplies the already-known connection nonce; the student cannot choose a different connection ID. A link opened by another person must not silently unlock the waiting player. Merely sending “Approve this name?” back to the waiting game is insufficient: an attacker who supplied the link could click that approval.
6. **Commit once.** In one database transaction, compare challenge state/version, expiry, failed attempts, expected game identity and live connection binding. Create/find the participant, insert the unique game link if absent, reject links owned by another participant, consume the challenge and issue a grant for this exact connection. Do not overwrite an existing link with an upsert. Retried requests may return the same committed outcome only to the same authenticated internal caller and connection.
7. **Enter the hub.** The plugin checks that the connection and server instance still match, applies the participant's name and permissions on the Paper thread, and releases the lobby lock. A disconnect, restart, new challenge or expired grant invalidates completion. A callback for yesterday's UUID cannot authenticate today's connection.

The two-stage proof and suggested limits are project security requirements. Suggested confirmation code: ten unambiguous random Base32 characters, stored as a keyed hash, maximum five attempts. Rate-limit rendezvous lookup, challenge creation and confirmation separately by request/account plus a bounded IP policy that accommodates the school NAT. Use at least 192 random bits for URL identifiers. Avoid token-bearing URLs in logs, analytics and referrers; prevent caching of all authentication pages.

## Token, session and service boundaries

Use maintained OIDC middleware/token validation libraries. MSAL4J is a supported Java option for token acquisition, but do not equate acquiring a token or decoding its JSON with implementing all application checks. Explicitly test signature verification with discovered keys, an algorithm allowlist, trusted issuer, exact audience/client ID, `tid`, `oid`, `exp`, `nbf`, expected nonce and required role. Support signing-key rotation with bounded metadata caching; unknown keys must not become an allow path. An ID token establishes the web sign-in; do not pass it as a bearer credential to the game or use a Graph access token as proof for a Hill API. [MSAL4J](https://learn.microsoft.com/en-us/entra/msal/java/), [ID token validation](https://learn.microsoft.com/en-us/entra/identity-platform/id-tokens), [Access token audiences](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens).

Keep the certificate credential/private key on the service host, outside Git and plugin resources; a certificate is preferred to a long-lived client secret. Do not request `offline_access` for this flow. Keep raw Microsoft tokens only as long as needed to complete sign-in/profile lookup. Use secure, HttpOnly host-only cookies; select the SameSite policy to match the callback response mode and test it. Protect state-changing browser requests against CSRF, rotate the local session after sign-in, fix allowed hosts/redirects and use restrictive CSP/referrer policy. These are implementation requirements, not additional Microsoft permissions.

The Paper plugin receives only a minimal authenticated grant: participant ID, school display name, authorized application roles, game identity, connection nonce, server instance, expiry and authorization version. Authenticate internal requests even on loopback; keep the internal route inaccessible from nginx and the public browser. A Unix socket with restrictive ownership is an alternative. No public “mark UUID authenticated” endpoint. Network/database work runs off the tick thread; return to Paper's scheduler to mutate players and check the session again.

Proposed operational policy: each connection gets a new OIDC exchange; school authorization lasts at most 30 minutes and never beyond the validated token's expiry. Renew through a fresh browser flow with a warning before expiry. The service grants short leases to the plugin, checked every 30 seconds, so a local suspension takes effect within a minute. If the service becomes unreachable, permit only the unexpired lease, then return to the locked lobby. These durations need operator approval before implementation; they are not Microsoft's token defaults.

Removing a group/role assignment or disabling a school account does not magically revoke an already issued local game session. Provide an audited local suspend action that revokes all grants and increments the participant's authorization version. IT must have a defined offboarding/suspension handoff to operators. Fresh Entra checks limit stale eligibility, subject to directory propagation; if Hill requires automated immediate directory-driven revocation, add and test a narrowly scoped provisioning/reconciliation integration. Do not claim generic OIDC or Microsoft Continuous Access Evaluation automatically covers this custom game service.

## Java, Bedrock and existing offline nicknames

Prefer the simplest deployment: a supported Paper release with Geyser and Floodgate, Java account verification enabled, and Geyser configured for Floodgate. Pin and test the compatible versions together. Resolve Bedrock identity through the trusted Floodgate API using its XUID; store it as a decimal string. Detect Floodgate before choosing the Java identity path. Do not identify Bedrock players by a username prefix, guessed UUID layout or client-supplied plugin message. Floodgate supplies XUID and account information through its API. [Floodgate setup](https://geysermc.org/wiki/floodgate/setup/), [FloodgatePlayer source](https://raw.githubusercontent.com/GeyserMC/Floodgate/master/api/src/main/java/org/geysermc/floodgate/api/player/FloodgatePlayer.java).

For Java, `online-mode=true` establishes a verified Minecraft account; the current repository's `online-mode=false` does not. If a Velocity proxy is introduced, authenticate Java at the proxy, protect its offline Paper backend with localhost/firewall and modern forwarding, and secure Floodgate forwarding keys. A publicly accessible offline backend bypasses the proxy's identity assurances. [Paper server properties](https://docs.papermc.io/paper/reference/server-properties/), [Velocity security](https://docs.papermc.io/velocity/security/).

Offline launcher support is a separate decision. If retained, nickname and offline UUID prove no account ownership: require school authentication on every connection, a pre-existing school-to-alias binding, no nickname-based staff/OP privileges, and a hardened admission layer. First claim, alias recovery, impersonation attempts and duplicate-connection denial still need explicit policy. Never silently enable password-only fallback when Microsoft fails. The recommended public student deployment uses verified Java and verified Bedrock identities.

Hill participant linking is separate from Floodgate's optional Java/Bedrock linking, which can change the effective Java UUID and share vanilla player data. For the initial deployment, explicitly configure and test a consistent Floodgate linking policy; avoid allowing global/local linking to change beneath the identity store. Always retain the original Bedrock XUID as its school link key. Sharing competition entries does **not** automatically merge survival inventory, advancements or ender chests. Keep survival state per verified game identity initially, unless a separately designed cross-edition inventory migration is requested. [Floodgate linking](https://geysermc.org/wiki/floodgate/linking/), [Offline UUID/linking behavior](https://geysermc.org/wiki/floodgate/issues/).

## Data model and competition rules

Use a relational store with migrations and explicit transactions. PostgreSQL is the recommended shared service/plugin store; bind it privately and grant each process only the tables/actions it needs. This is a proposed dependency, not part of today's installer. Do not let two processes rewrite `competition-data.yml`.

| Record | Key and invariants |
| --- | --- |
| Participant | Internal UUID; unique `(tenant_id, object_id)`; approved display name; eligibility state; authorization version; last verification time. |
| Game account | Unique `(JAVA, verified_uuid)` or `(BEDROCK, xuid)`; one participant FK; last observed nickname; linked/revoked timestamps. |
| Link challenge | Random request ID, hashed codes, browser binding, game identity, server instance, connection nonce, state/version, expiry, attempt counters. |
| Session grant | Random ID; participant and game-account FKs; exact connection binding; authorization version; lease expiry. |
| Entry membership | Unique `(entry_id, participant_id)`; participant/category constraints for active memberships. |
| Audit event | Actor participant/operator, action, target, timestamp, reason and correlation ID; no passwords/tokens. |

All linked accounts resolve to the same participant before any entry creation, invite, edit, category change, build permission, submission or vote decision. Retain the existing rule of at most two active entry memberships in different categories and at most two distinct participants per team. One person's Java and Bedrock accounts cannot occupy both team positions. Lock affected participant rows in deterministic order during membership/category transactions; recheck the count and uniqueness inside the transaction. Distinct accounts racing must not create extra slots. Votes must similarly be unique per participant/category.

Default to one active game connection per participant, with a deliberate switch-device flow, to simplify shared permissions and prevent conflicting inventory actions. If concurrent Java/Bedrock use is later allowed, quotas and mutation authority must still resolve to the same participant and have race tests. A configurable linked-account cap controls abuse without changing entry limits; the initial policy should support at least one Java and one Bedrock account.

## Names and student privacy

Apply the approved school name as plain Adventure text in chat, tab list and competition menus. Use a chat renderer so every game-facing message follows the same policy. Preserve the verified game identity beneath presentation, including commands and moderation records. Identical school names need a non-sensitive local disambiguator; never append email, student number, tenant ID or object ID. Support Unicode, apostrophes and spaces, and strip formatting/control characters without parsing names as MiniMessage. [Paper chat rendering](https://docs.papermc.io/paper/dev/chat-events/).

`displayName` and `playerListName` do not by themselves replace the overhead player name. Treat nameplates as a distinct feature: choose a maintained compatible nameplate component, or hide the vanilla tag and render a controlled label, then test it through Geyser. Do not change the authenticated profile name to a full name. If a full replacement cannot be verified on both editions, report that limitation explicitly; chat/tab success is not nameplate acceptance. [Paper Player API](https://jd.papermc.io/paper/1.21.11/org/bukkit/entity/Player.html).

Expose real names only after both viewer and subject are authorized. Suppress names from public server status/query samples and pre-auth join/quit broadcasts. Review death messages, advancements, tab completion, scoreboards, hover text and third-party chat/map integrations. Anonymous voting/capture mode must hide names in UI, overhead labels and generated artifacts. Do not publish account mappings, real-name screenshots or directory data to GitHub. Before opening registration, Hill must approve the displayed-name policy, help contact, event-end retention date and who can access recovery/audit records.

Store only the identifiers needed for linking, the approved display name, current entitlement, timestamps and minimal audit history. Set an actual purge schedule for connection addresses, expired challenges, revoked sessions and event data, covering backups too. The current `connection-audit-retention-days-after-event` configuration is a stated intent, not an implemented dated purge. Preserve entries/worlds according to the approved event archive policy while removing unnecessary identity data.

## Hosting behind Cloudflare

The browser path is `browser -> Cloudflare -> nginx HTTPS -> identity service on 127.0.0.1`. Public web requests must pass through Cloudflare. Install a hostname-valid Cloudflare Origin CA certificate at nginx and use **Full (strict)**. Origin CA protects the Cloudflare-to-origin TLS connection; it does not authenticate the caller or alone block direct-origin requests. [Origin CA](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/).

Require **Authenticated Origin Pulls** at nginx (`ssl_verify_client on`) with the appropriate client-certificate trust and permit web ingress only from Cloudflare's current IPv4/IPv6 ranges. Prefer an account-specific zone/hostname AOP certificate: the shared global certificate proves only that traffic came from Cloudflare's network. Reject unrecognized Host/SNI and keep port 80 closed or Cloudflare-restricted; perform browser HTTPS redirects at the edge. Monitor certificate expiry. [AOP](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/), [Origin protection](https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/).

Trust forwarded scheme/client-IP headers only from the configured proxy chain. Bypass edge/nginx caching for sign-in, callback, pairing and account pages. Redact query strings and secrets from access/application logs. The Microsoft browser callback returns through this same HTTPS hostname, so no public origin exception is needed. Keep internal plugin APIs and the database private. Minecraft TCP and Bedrock UDP are separate ingress services; an HTTP proxy/certificate is not game authentication.

Use dedicated unprivileged service accounts, restricted credential files, encrypted backups and a tested restoration procedure. Missing identity configuration, a failed database migration or a disabled Hill175 plugin must prevent admission to the competition. Simply disabling the plugin while Paper keeps listening loses the protective listeners. Startup/readiness controls must keep public game ingress closed until required components pass, and shutdown/revoke sessions if essential protection fails.

## Current implementation gaps and migration

The following findings come from this repository, not Microsoft documentation:

- [IdentityLinkerFactory](../../src/main/java/org/thehill/hill175/auth/IdentityLinkerFactory.java) supports only `always-approve-development-stub` with explicit development acknowledgment. [Hill175Plugin](../../src/main/java/org/thehill/hill175/Hill175Plugin.java) now stops Paper when that authentication configuration is invalid. Setting `authentication.provider` to `microsoft` is rejected; it cannot enable SSO or silently fall back to the stub. This safeguard does not implement school verification or establish complete failure handling for every plugin component.
- [IdentityLinker](../../src/main/java/org/thehill/hill175/auth/IdentityLinker.java) is a synchronous stub-shaped begin/complete interface. [AlwaysApproveIdentityLinker](../../src/main/java/org/thehill/hill175/auth/AlwaysApproveIdentityLinker.java) approves from a nickname URL and synthesizes the name. Replace it with asynchronous challenge state and session-bound completion.
- [Account](../../src/main/java/org/thehill/hill175/model/Account.java), [Entry](../../src/main/java/org/thehill/hill175/model/Entry.java), [CompetitionStore](../../src/main/java/org/thehill/hill175/data/CompetitionStore.java) and [CompetitionModule](../../src/main/java/org/thehill/hill175/competition/CompetitionModule.java) use nickname keys for account lookup, team ownership and limits. Merely assigning the same `schoolIdentity` to two records would not combine their entry quotas or permissions.
- Registration uses a delayed callback without a fresh connection nonce. Password-only login does not revalidate school eligibility, and its in-memory failure window is removed on quit. Password hashing/verification currently runs in the command path. The SSO flow should retire these student password commands instead of putting Microsoft credentials through them.
- [YamlCompetitionStore](../../src/main/java/org/thehill/hill175/data/YamlCompetitionStore.java) provides per-file writes, not multi-record identity/link/membership transactions. [SurvivalInventoryStore](../../src/main/java/org/thehill/hill175/data/SurvivalInventoryStore.java) and vanilla player files also depend on game UUIDs and need separate migration decisions.
- [CONTEXT.md](../../CONTEXT.md) currently defines one nickname per school identity and competition passwords. Update those definitions when the new implementation lands, explicitly marking the transition until then.

Migration procedure:

1. Freeze admissions/writes; take consistent copies of plugin data, all worlds/player data, operator/permission lists and configuration. Produce a dry-run inventory and hashes before any conversion.
2. Import entries with their existing IDs and world paths intact. Import old nickname accounts as **unverified legacy claims**, never trusted student identities. No `stub:*` record is eligible by default.
3. Establish each participant with fresh school sign-in and each Java/Bedrock account with transport proof. To transfer existing work, require the legacy competition-password proof where reliable plus new school/game proof, or a documented staff recovery review. Nickname equality alone cannot transfer ownership.
4. Aggregate memberships across aliases. Flag same-category duplicates, more than two active memberships, two aliases on one team, existing ownership disputes and conflicting inventory/UUID records. Freeze affected actions pending staff resolution; do not delete projects or silently select a winner. A deleted/recreated Entra account has a new object ID and follows recovery, not email-based automatic merging.
5. Migrate participant ownership transactionally with an auditable old-to-new map. Offline UUIDs, online UUIDs and Floodgate-linked UUIDs can differ: inventory, ender chest, advancements and survival snapshots need explicit reviewed mappings, with originals preserved. Reconcile counts and permissions before activation.
6. Rehearse rollback using a compatible plugin/database/world snapshot set. Remove password/stub admission from the student production profile, invalidate all pending requests and old sessions, then pilot a small assigned group before opening registration.

Unlinking never deletes the participant's entries, votes or sanctions. Fresh school sign-in can revoke a lost game account; moving an account to another student requires a staff-reviewed transfer and proof, not an automatic re-link. Keep a restricted operator recovery path that cannot fabricate arbitrary `(tid, oid)` identities.

## Inputs and delivery sequence

Hill IT and operators must supply these values through appropriate configuration/secret channels, not commit credentials to this repository:

| Input | Required decision or value |
| --- | --- |
| Tenant and application | Hill tenant GUID; application/client GUID; app owner and backup owner; production and separate test app registrations. |
| Callback | Approved public auth hostname; exact HTTPS callback and logout URLs; Cloudflare zone and DNS ownership. |
| Eligibility | Student group object ID; direct or group role assignment; licensing/nested-group check; guest/staff policy and test users. |
| Display name | IT-approved claim/profile field, missing-name correction route and student display/privacy policy. |
| Credentials | Certificate credential and rotation owner; private-key delivery; session/internal-service secrets and ownership. |
| Game accounts | Verified Java + Bedrock as recommended, or an explicit offline-launcher requirement; supported devices and Geyser/Floodgate version matrix. |
| Operations | Session/lease durations; offboarding contact and response target; simultaneous-session/account caps; event-end date, retention and recovery operators. |
| Ingress | Origin CA certificate/key, AOP trust and client-certificate configuration, nginx host, Cloudflare allowlists, private service/database endpoints. |

Build in reviewable stages: (1) approve the above policy and register the test application; (2) implement participant storage and migration dry-run; (3) implement/test the web OIDC and pairing service; (4) replace plugin password/stub admission with session-bound grants; (5) integrate verified Java/Floodgate identities and names; (6) rehearse migration, backup/restore and fail-closed deployment; (7) pilot with actual students on both editions. The source build/deployment guide for today's server must continue to label SSO as planned until these stages pass.

Required acceptance tests before production:

- A permitted student signs in from Java and Bedrock and sees the same entries/name; an unassigned Hill user, external tenant, guest without the approved role and personal Microsoft account are rejected.
- Wrong issuer/audience/signature/tenant/nonce/state, expired tokens, missing role, replayed codes and unknown keys fail closed; legitimate key rotation succeeds.
- A copied login link cannot unlock an attacker's game without the browser-only code; code reuse, wrong connection, disconnect/rejoin, service restart, stale callbacks and two competing claims cannot change ownership.
- Concurrent alias entry creation cannot exceed two categories; aliases cannot form a two-person team or duplicate a vote. Name changes preserve IDs and ownership.
- Role removal, local suspension, expired leases, Microsoft outage, identity-service outage and plugin startup/disable failure follow the documented admission policy. No production fallback to the development stub.
- Test actual Java and Bedrock clients for link/code entry, chat/tab/overhead names, long/Unicode/duplicate names, device switching, anonymous voting, camera entry/exit and unauthorized-world interactions. Confirm no names in unauthenticated status or external integrations.
- Direct origin IP/Host spoofing and public internal-API/database access fail; Cloudflare with valid AOP succeeds; missing/wrong client certificates fail; auth responses are never cached and logs do not reveal credentials/codes.
- Migration dry-run reports all collisions without deleting work; restore reproduces entry ownership, worlds and inventory; staff recovery and retention purge are exercised with test data.
