# Hill School 175th Anniversary Server

Paper plugin and deployment tooling for the anniversary competition: Journey
outdoor plots, Place interiors, People campus worlds, teams, saved camera views,
submissions, and a separate survival area.

**Status: logistics and controlled testing.** The plugin implements Microsoft
school verification and shared participant ownership across Java/Floodgate accounts.
Hill IT configures it through environment variables; the existing deployed demo
continues to use development authentication until IT setup and a real-client pilot.

For the existing Linux host, after the
[one-time host and IT setup](docs/operations/microsoft-sso-setup.md), deploy
a clean, committed `main` checkout with `./ops/deploy.ps1 -Mode Microsoft`.
It pushes to GitHub, pulls on the host, builds/tests, backs up, installs pinned
Java/Bedrock components, configures nginx, restarts and verifies the service.
Use `-Mode Development` for the current demo.

## Start here

- [Windows asset and folder setup](docs/operations/windows-assets.md)
- [Build and deploy from source](docs/operations/deployment.md)
- [Microsoft SSO setup for Hill IT](docs/operations/microsoft-sso-setup.md)
- [Authentication architecture and limits](docs/architecture/microsoft-sso.md)
- [Player workflow and commands](docs/operations/player-guide.md)
- [Smoke tests](docs/SMOKE_TEST.md)
- [Repository conventions](CONTRIBUTING.md) and [documentation index](docs/README.md)

## Build

Use JDK 25 and the checked-in Gradle wrapper:

```powershell
.\gradlew.bat clean test jar
```

On Linux/macOS: `bash ./gradlew clean test jar`. Output:
`build/libs/Hill-server-1.0-SNAPSHOT.jar`. Paper is pinned to **26.2 build 119**.
Campus world archives are supplied separately from GitHub.

For school sign-in, copy [.env.example](.env.example) to the protected server
environment file, configure the Entra application and HTTPS proxy, then install
with `--microsoft`. A student opens the in-game link, signs into their Hill account,
and enters the browser's code with `/verify`. The same school account links their
Java and Bedrock identities. The [IT guide](docs/operations/microsoft-sso-setup.md)
includes the exact configuration, rollout checks and recovery limits.

## Campus map

People entries copy the campus installed in
`world-templates/hill_people_template/` under the server folder. Replace that
folder while Paper is stopped to choose another revision; no version pin or
file-count change is required. Existing participant worlds are preserved.
The requested IT handoff contains **V29** and the exhibition hub; follow the
[Windows asset instructions](docs/operations/windows-assets.md). V29 is an
unfinished exterior draft. Installing the code does not replace an existing
campus folder or participant worlds.

## Layout

| Directory | Contents |
| --- | --- |
| `src/main`, `src/test` | Java plugin and tests |
| `ops/` | Install, verify, backup, packaging, smoke tools, systemd units |
| `server-config/` | Versioned server defaults |
| `server-assets/` | Deployment manifests, asset credits and original resource packs |
| `tests/` | Deployment and packaging tests |
| `docs/` | Installation, operation, authentication architecture and credits |
| `runtime/` | Ignored local assets and server data |

World archives, credentials, student records, and third-party binaries stay outside
Git. Deployment follows **local changes → tests → GitHub push → PuTTY `plink.exe`
→ server `git pull` → source build/install**.

The remote branch contains the server and its deployment support. Campus-authoring
tools, internal agent notes, research and working drafts are kept outside this
branch. Private assets and credentials are delivered separately.
