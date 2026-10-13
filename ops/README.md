# Server operations

Start with the [deployment guide](../docs/operations/deployment.md). Run from the
repository root unless instructed otherwise.

| Tool | Purpose |
| --- | --- |
| `install-server.sh` | Build, check the supplied map folders, install the listed programs, restart and verify the selected authentication mode |
| `check-auth-config.py` | Validate the protected environment file without executing or printing credentials |
| `verify-server.sh` | Read-only deployed configuration and asset checks |
| `load-server-binaries.sh` | Read `server-assets/server-binaries.env` (Paper, Java, Chunky URLs and checksums) as data |
| `check-world-template.py` | Validate a hub or lobby map folder and its `hill-world.yml` |
| `backup-hill175.sh` | Cold Borg snapshot and service restart |
| `install-survival-worldgen.sh` | Pinned datapacks, persisted seed, recoverable initial transition |
| `prepare-local-runtime.ps1` | Prepare a Windows Paper server folder (`-Runtime`), downloading Java when none is installed |
| `prepare-local-survival-worldgen.ps1` | Local worldgen staging |
| `stage-world-template.ps1` | Copy a world save or exported ZIP into a designated map folder without player data |
| `package-deployment-assets.py` | Package explicitly chosen campus, hub and optional lobby folders for IT |
| `update-server.sh` | Check/apply GitHub changes using the existing backup and installer workflow |
| `enable-auto-update.sh` | Enable the optional 04:00 server-time update timer after initial deployment |
| `prepare-local-campus-template.ps1` | Validate the campus already placed in the local runtime folder |
| `prepare-smoke-bot.ps1` | Stage the pinned Mineflayer compatibility fork |
| `patch-smoke-bot-protocol.mjs` | Apply the pinned protocol-data correction |
| `smoke-player.mjs` | Player regression scenarios |
| `systemd/` | Paper and backup service/timer units |
| `nginx/` | Cloudflare-protected Microsoft sign-in proxy example |

Maps are supplied separately from Git and read from `<server>/world-templates/`;
no script names a map, version or checksum. Campus authoring tools and
internal working notes are not part of this deployment branch.
Use [the Hill IT guide](../docs/operations/microsoft-sso-setup.md) for environment
variables, tenant registration and the Java/Bedrock pilot.
