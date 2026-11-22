# Hill School 175th Anniversary Server

Every student builds in a personal copy of campus. To send a build, the student
right-clicks the **Send My Build** emerald in the hotbar, clicks the **Box Corner**
on two opposite corners while flying through walls, and right-clicks **Send**. The
student keeps building while a moderator reviews it. Approved builds merge into
every personal campus automatically, including for offline owners. Blocks changed
on both sides are boxed in pink, and the owner picks **Keep Mine** or **Use
Blueprint's** from the hotbar. Staff choose **Review Builds** (or `/review`) and
decide each build on the shared blueprint with two hotbar items: **Accept** and
**Reject**.

Public chat uses a bundled open-source profanity vocabulary with school-specific
rules. Private-message commands and party chat are disabled.

See [campus parties](docs/operations/campus-parties.md),
[blueprint review](docs/operations/blueprint-review.md), and
[chat safety](docs/operations/chat-safety.md) for player and operator workflows.
Existing shared campus saves and competition projects are preserved. The
[shared campus guide](docs/operations/shared-campus.md) documents the optional
legacy shared mode and its Restic area recovery. New personal copies start from
the approved blueprint, initially seeded from the explicitly installed campus
template.

[Staff roles and moderation](docs/operations/staff-roles.md) describes staff,
moderator and administrator access, account bans, chat mutes and Microsoft names.

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
- [Local build gallery](docs/operations/build-gallery.md)
- [Player action map and smoke evidence](docs/operations/player-experience-review.md)
- [Smoke tests](docs/SMOKE_TEST.md)
- [Repository conventions](CONTRIBUTING.md) and [documentation index](docs/README.md)

## Build

Use JDK 25 and the checked-in Gradle wrapper:

```powershell
.\gradlew.bat clean test jar
```

On Linux/macOS: `bash ./gradlew clean test jar`. Output:
`build/libs/Hill-server-1.0-SNAPSHOT.jar`. The server programs (Paper **26.2 build 119**,
Java, Chunky) are listed with their checksums in `server-assets/server-binaries.env`.
Maps are supplied separately from GitHub.

For school sign-in, copy [.env.example](.env.example) to the protected server
environment file, configure the Entra application and HTTPS proxy, then install
with `--microsoft`. A student opens the in-game link, signs into their Hill account,
and enters the browser code in the game menu. The same school account links their
Java and Bedrock identities. The [IT guide](docs/operations/microsoft-sso-setup.md)
includes the exact configuration, rollout checks and recovery limits.

## Maps

The server reads every map from a designated folder under
`world-templates/` in the server folder: `hill_people_template/` (campus),
`hill_hub/` (exhibition hub) and optionally `hill_auth/` (sign-in lobby). No map
name, version or checksum is written into the code, and each hub or lobby map
carries its own arrival point in `hill-world.yml`.

The first blueprint is seeded from `world-templates/hill_people_template/`
(or an explicitly configured `blueprint.source-folder`). Later personal campuses
copy the approved blueprint revision, not a newly replaced staging folder.
Staff-approved proposals update that blueprint. Existing participant worlds
and their recorded baselines are preserved. In legacy competition mode, new
People entries continue to use the installed template folder.

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
