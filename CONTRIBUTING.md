# Working on Hill 175

Use JDK 25 and the Gradle wrapper: `gradlew.bat clean test jar` on Windows or
`bash ./gradlew clean test jar` on Linux. Keep the pinned Paper/world format during
an active event.

## Code organization

| Java package | Responsibility |
| --- | --- |
| `auth` | Game identity, school sessions and development password verification |
| `auth.sso` | Environment configuration, Microsoft OIDC, browser challenges and atomic identity links |
| `model` | Competition records and domain data |
| `data` | Durable competition and survival state |
| `competition` | Session, entry, team, camera workflows |
| `world` | World lifecycle, templates, plots, spawn, chart rendering |
| `ui` | Menus and NPC presentation |
| `command`, `listener` | Translate Bukkit commands/events into application actions |

Keep Bukkit mutations on the server thread and network/database work off it.
Authorize actions in the application layer shared by commands, menus, and listeners.
Use [CONTEXT.md](CONTEXT.md) for terminology and the
[SSO architecture](docs/architecture/microsoft-sso.md) for participant ownership.
Display names must not replace verified game identities or become authorization keys.

`ops/` contains server lifecycle tools; `ops/systemd/` contains service definitions
and `ops/nginx/` contains the authentication proxy example.
`server-config/` holds deployable defaults. `server-assets/` holds asset manifests,
checksum pins, and original resource packs. Keep packaging/verification pins synchronized.
Do not replace participant builds when updating a template.

Keep this branch focused on server source, deployment tools, configuration,
operator documentation, tests and asset/license manifests. Campus-authoring code,
AI agent scratchpads, construction handoffs and research stay local or in a
separate authoring repository. Do not add them to a deployment commit.

## Verification

- Java: Gradle tests and affected [player smoke scenarios](docs/SMOKE_TEST.md).
- Operations: Bash/PowerShell syntax checks, asset hashes, and controlled Paper startup.
- Documentation: check links/command paths; distinguish implemented, planned, tested,
  and deployed work.

Commit source, tests, original resource packs, defaults and deployment manifests.
Exclude generated maps, downloads, world archives, student data, credentials, logs,
proposal working copies, and caches. Preserve existing edits; inspect staged changes.
Do not use blanket `git clean`, hard resets, force pushes, or delete old world inputs.
Follow the [deployment guide](docs/operations/deployment.md).
