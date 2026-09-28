# Hill School 175th Anniversary Server

Paper plugin and deployment tooling for the anniversary competition: Journey
outdoor plots, Place interiors, People campus worlds, teams, saved camera views,
submissions, and a separate survival area.

**Status: logistics and controlled testing.** The plugin implements Microsoft
school verification and shared participant ownership across Java/Floodgate accounts.
Hill IT configures it through environment variables; the existing deployed demo
continues to use development authentication until IT setup and a real-client pilot.

## Start here

- [Build and deploy from source](docs/operations/deployment.md)
- [Microsoft SSO setup for Hill IT](docs/operations/microsoft-sso-setup.md)
- [Authentication architecture and limits](docs/architecture/microsoft-sso.md)
- [SSO validation and review](docs/operations/microsoft-sso-verification-20260928.md)
- [Player workflow and commands](docs/operations/player-guide.md)
- [Smoke tests](docs/SMOKE_TEST.md)
- [Campus and camera deployment record](docs/operations/deployment-verification-20260928.md)
- [Repository conventions](CONTRIBUTING.md) and [documentation index](docs/README.md)

## Build

Use JDK 25 and the checked-in Gradle wrapper:

```powershell
.\gradlew.bat clean test jar
```

On Linux/macOS: `bash ./gradlew clean test jar`. Output:
`build/libs/Hill-server-1.0-SNAPSHOT.jar`. Paper is pinned to **26.2 build 119**.
Local reconstruction launchers target other Minecraft versions and are separate.

For school sign-in, copy [.env.example](.env.example) to the protected server
environment file, configure the Entra application and HTTPS proxy, then install
with `--microsoft`. A student opens the in-game link, signs into their Hill account,
and enters the browser's code with `/verify`. The same school account links their
Java and Bedrock identities. The [IT guide](docs/operations/microsoft-sso-setup.md)
includes the exact configuration, rollout checks and recovery limits.

## Campus map

People entries use the frozen **v19 campus at two blocks per metre**, packaged
from the verified Java 1.21.11 port for Paper 26.2. Deployment pins live in
[campus-template.env](server-assets/campus-template.env) and
[worlds.yml](server-assets/worlds.yml). Existing People builds are preserved;
a template change does not migrate students' worlds automatically.

The campus is unfinished and construction remains paused. Local launchers, source
geometry, and saved worlds are described in the [workspace guide](docs/workspace-layout.md).
The general local launcher still selects v14; the separate 1.21.11 launcher opens v19.

## Layout

| Directory | Contents |
| --- | --- |
| `src/main`, `src/test` | Java plugin and tests |
| `ops/` | Install, verify, backup, packaging, smoke tools, systemd units |
| `server-config/` | Versioned server defaults |
| `server-assets/` | Provenance, checksums, campus inputs, original resource packs |
| `scripts/`, `tests/` | Campus reconstruction tools and tests |
| `docs/` | Operations, architecture, research, historical plans |
| `runtime/` | Ignored local worlds, downloads, screenshots, archives |

World archives, credentials, student records, and third-party binaries stay outside
Git. Deployment follows **local changes → tests → GitHub push → PuTTY `plink.exe`
→ server `git pull` → source build/install**.
