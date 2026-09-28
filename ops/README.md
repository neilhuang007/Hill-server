# Server operations

Start with the [deployment guide](../docs/operations/deployment.md). Run from the
repository root unless instructed otherwise.

| Tool | Purpose |
| --- | --- |
| `install-server.sh` | Build, install pinned assets, restart and verify the selected authentication mode |
| `check-auth-config.py` | Validate the protected environment file without executing or printing credentials |
| `verify-server.sh` | Read-only deployed configuration and asset checks |
| `backup-hill175.sh` | Cold Borg snapshot and service restart |
| `install-survival-worldgen.sh` | Pinned datapacks, persisted seed, recoverable initial transition |
| `prepare-local-runtime.ps1` | Prepare an ignored local Paper runtime |
| `prepare-local-survival-worldgen.ps1` | Local worldgen staging |
| `package-user-hub.ps1` | Package the supplied exhibition hub |
| `package-campus-template.py` | Package the frozen campus with deterministic checksums |
| `prepare-local-campus-template.ps1` | Stage the pinned campus locally |
| `prepare-smoke-bot.ps1` | Stage the pinned Mineflayer compatibility fork |
| `patch-smoke-bot-protocol.mjs` | Apply the pinned protocol-data correction |
| `smoke-player.mjs` | Player regression scenarios |
| `systemd/` | Paper and backup service/timer units |
| `nginx/` | Cloudflare-protected Microsoft sign-in proxy example |

These tools moved from `scripts/` and `deploy/` during cleanup. Reconstruction
tools retain their original paths. World archives are staged separately from Git.
Use [the Hill IT guide](../docs/operations/microsoft-sso-setup.md) for environment
variables, tenant registration and the Java/Bedrock pilot.
