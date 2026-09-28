# Microsoft SSO implementation review — September 28, 2026

The implementation adds environment-configured Hill Microsoft verification,
browser/game pairing and shared Java/Floodgate participant ownership. It is ready
for IT configuration and a controlled pilot; no real Hill credentials or student
records were used in development. See the [setup guide](microsoft-sso-setup.md).

## Source validation

- `gradlew.bat clean test jar`: **79 Java tests passed**, including 37 new tests.
- Environment preflight: **5 Python tests passed**.
- Backup isolation: **2 Linux integration tests passed** with mocked services/Borg,
  including recovery after failed archive creation. These root-only tests skip on Windows.
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

## Deployed demo verification

| Item | Verified value |
| --- | --- |
| Application build commit | `659fa2b` |
| Backup correction commit | `ce121c3` |
| Service | `hill175.service`, active; Paper 26.2 build 119 / JDK 25 |
| Authentication | Explicit `HILL175_AUTH_MODE=development` in protected systemd environment |
| Plugin SHA-256 | `ca2c146addbe8a25d1f79b03b98258105b3e12fec9fdb314b0c8e325a2ab0239` |
| Verified Hill Borg archive | `hill175-verified-2026-09-28T20-36-59Z` |
| Archive fingerprint | `38a2b95f3027e215abaa0ab234fb6b54d2cbc78b3cf66bee483aede7370bbf71` |
| Campus | Frozen v19 at two blocks/metre, 25 region files; existing pin unchanged |

The server pulled GitHub source and passed all **79 Java tests** during its JDK 25
build. Its installed JAR matches the local build hash exactly. Both deployment
Python suites also passed on Linux. Configuration/assets/log verification passed,
and the installed backup script matches the corrected source. Later documentation
commits do not change this JAR.

Live protocol smoke checks passed through a temporary PuTTY SSH forward:
authentication-lobby restriction, owner/visitor camera entry and both exit controls,
People campus creation, chart, reset and re-entry at `(228.5, 86, 154.5)` on grass.
The temporary test tunnel was closed. This does not resolve the earlier direct
network connectivity limitation or replace real-client visual acceptance.

The first pre-SSO backup run exposed a legacy shared-environment collision:
`SRV_DIR` redirected the snapshot to the other Minecraft installation. That
archive is **not** a verified Hill backup. The corrected script resolves Hill's
namespaced settings after reading credentials. The new cold snapshot above
contains `/opt/hill175` (**3.82 GB / 2,694 files**); archive listing and dry-run
extraction verified its plugin and competition data. It is a post-deployment
snapshot, not a retroactive pre-deployment recovery point. The earlier v19 report
now carries the same backup qualification.

Server logs are retained at `/opt/hill175/assets/deploy-sso-20260928.log` and
`/opt/hill175/assets/verify-sso-20260928.log`. Local smoke logs remain ignored under
`runtime/campus-reconstruction/server-integration-20260928/sso-*-smoke.log`.

## External acceptance still required

IT must configure the Entra app/role and protected HTTPS hostname, supply the
certificates/environment, open the game ports, and test real Java and Bedrock clients. Automated
tests do not prove Hill tenant eligibility, Cloudflare/firewall configuration,
device link handling or real-name rendering. Existing development builds and
survival inventories are preserved; automatic legacy-owner migration is not
implemented. The deployed demo stays in development mode until those checks pass.

## Deployment automation follow-up

Deployment code `dc6ca28` was pushed to GitHub, pulled on the server, and exercised
using `ops/deploy.ps1 -Mode Development` from a clean local checkout. The command
completed push/pull, exact-revision validation, JDK 25 build/test/jar, cold backup,
one continuous restart window, installation and file/log checks. Gradle reused its
successful 79-test result; the plugin SHA-256 above is unchanged. The installed
backup and shared-lock scripts match source. The service remains active.

The automatic pre-deployment archive is
`hill175-predeploy-2026-09-28T21-06-25Z`, fingerprint
`e157dde67600ea2efe3ddab525845c976ad6400ad350fd9be9b2cd00c2bdca64`
(3.95 GB / 2,751 files, runtime root `/opt/hill175`). The full command log is
`/opt/hill175-deploy-20260928T210618Z.log`.

All **33 deployment tests passed on Linux**: 5 environment, 8 proxy, 15 Bedrock,
and 5 backup/locking tests. The proxy integration test generated disposable TLS
credentials and validated the generated site with real nginx/OpenSSL, including
rejection of a mismatched hostname; it did not install a public site. This caught
and fixed OpenSSL's early exit when combining hostname and expiry checks.

Two isolated Paper 26.2 starts loaded pinned Geyser 2.11.3 build 1247 and Floodgate
2.2.5 build 141. Geyser opened the test UDP listener and the managed configurations
survived restart unchanged. The test caught and fixed Floodgate's configuration
rewrite; Hill's own account linking remains authoritative. That compatibility test
used local JDK 26 and did not authenticate a real Xbox/student account. Logs remain
ignored under `runtime/bedrock-smoke-20260928/`.

The review also fixed backup's premature restart and serialized deployments with
scheduled Hill backups. Microsoft deployment now handles transport downloads,
configuration and nginx automatically after the one-time IT setup. Microsoft mode
and Bedrock transport were not activated on the public development demo.
