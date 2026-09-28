# Microsoft SSO implementation review — September 28, 2026

The implementation adds environment-configured Hill Microsoft verification,
browser/game pairing and shared Java/Floodgate participant ownership. It is ready
for IT configuration and a controlled pilot; no real Hill credentials or student
records were used in development. See the [setup guide](microsoft-sso-setup.md).

## Source validation

- `gradlew.bat clean test jar`: **79 Java tests passed**, including 37 new tests.
- Environment preflight: **5 Python tests passed**.
- Bash and PowerShell operation scripts parsed successfully.
- Maintained document links, whitespace and source/artifact/credential scan passed.
- The packaged JAR contains the pinned OIDC dependencies and license notices.

The tests include RSA signature, issuer/audience/tenant/role/nonce/lifetime checks;
remote signing-key refresh; a real loopback HTTP callback with synthetic identity;
secure cookie, PKCE, state, response headers and HTML escaping; replay, five-attempt
and expiry limits; disconnect/rejoin and concurrent alias handling; conflicting
durable links, corrupt storage and uncertain write failure; canonical entry
ownership and quotas; chat/status/death/advancement privacy; and survival expiry.

## Critical audit and simplification

Separate agents implemented OIDC/storage and Paper integration. The main review
then corrected admission, deployment and privacy boundaries. Four simplify reviews
covered reuse, simplicity, efficiency and module placement.

Applied improvements:

- Keep network and identity file writes outside the game thread and challenge lock;
  read immutable name snapshots without waiting for a disk write.
- Skip unchanged identity-file writes and update only affected private scoreboards.
- Share canonical game-identity validation; remove a duplicate link timer and
  redundant transport initialization.
- Pass participant/name data directly into admission; remove unused account getters
  and the fabricated password account used for school login.
- Preserve survival state before session-expiry shutdown and block announcement or
  vanilla-command paths that could bypass authenticated chat audiences.
- Reject incomplete mode configuration, replay and reassignment; freeze further
  identity writes after an uncertain persistence failure until operator recovery.
- Leave Paper stopped after failed Microsoft-mode deployment, including rollback
  to an older JAR that might not understand the new authentication environment.

One reuse suggestion was deliberately skipped: centralizing the small NPC-team
presentation block would couple authentication to the broader NPC configuration
module. Its cached private-viewer setup remains separate. No unrelated campus
geometry, frozen revisions or player saves were rewritten.

## External acceptance still required

IT must configure the Entra app/role and protected HTTPS hostname, install a
compatible Geyser/Floodgate stack, and test real Java and Bedrock clients. Automated
tests do not prove Hill tenant eligibility, Cloudflare/firewall configuration,
device link handling or real-name rendering. Existing development builds and
survival inventories are preserved; automatic legacy-owner migration is not
implemented. The deployed demo stays in development mode until those checks pass.
