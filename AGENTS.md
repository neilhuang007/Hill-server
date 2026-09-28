# Hill 175 working instructions

Updated 2026-09-28. Current work is anniversary-server logistics, campus-template
integration, Microsoft SSO implementation, and repository/deployment maintenance.

## Read first

- [README](README.md): current implementation status.
- [Deployment](docs/operations/deployment.md): build, assets, validation, recovery.
- [SSO setup](docs/operations/microsoft-sso-setup.md): IT environment and Entra configuration.
- [SSO architecture](docs/architecture/microsoft-sso.md): implemented boundaries and remaining limits.
- [Workspace layout](docs/workspace-layout.md): reconstruction dependencies and saves.
- [Preserved construction handoff](docs/campus/BUILD_STATE.md): full September 27 state.

## Boundaries

- Construction is paused. Do not resume geometry without a new instruction.
- Server People template: `server-assets/campus-template.env` and `worlds.yml`.
  Local demonstration selection: `server-assets/hill-campus-current.json`.
  These are separate deliverables; never infer selection from highest revision or timestamps.
- Latest accepted combined source is v19 at two blocks per metre; its verified
  1.21.11 port is the server template input. General local launcher remains v14.
- Preserve studies, research, geometry, audits, screenshots, dependencies, and
  player saves. Completed revision directories are immutable.
- For building work, read the research handoff, source packet, profile, native
  review, and `docs/hill-building-agent-workflow.md` first. Preserve measured placement:
  `X=2*east_m`, `Z=2*south_m`, `Y=2*(NAVD88_m-25)`.
- Use `scripts/run_chapel_native_qa.py` for native launch/screenshots; inspect PNGs
  before claiming visual verification. Never open one save in two clients.
- Reconstruction paths remain stable for frozen build/provenance records. Server
  operations belong in `ops/`. Historical cleanup archives are not active inputs.
- Microsoft SSO is environment-configured and requires a real Hill tenant pilot.
  The deployed demo remains development authentication until IT enables it.
  Never claim the stub verifies Hill membership; unsupported providers fail closed.
- Never commit secrets, student records, worlds, binaries, or runtime credentials.

## Deployment

- Build using JDK 25: `./gradlew.bat clean test jar` or `bash ./gradlew clean test jar`.
- Server `135.181.78.188`, login `root`, services under `/opt/`.
- Always use PuTTY SSH:

  ```powershell
  plink.exe -i "C:/Users/neil_/.ssh/hetzner.ppk" root@135.181.78.188
  ```

- Update locally, push GitHub, then SSH and `git pull` in `/opt/Hill-server`.
  Do not copy edited source directly to the deployment checkout.
- Routine deployment: `./ops/deploy.ps1 -Mode Microsoft` from clean, committed `main`;
  use `-Mode Development` for the current demo. The wrapper performs push/pull,
  build/test, backup, install and verification. Hill IT supplies the one-time
  environment, Entra/Cloudflare setup and certificates described in the IT guide.
- Runtime `/opt/hill175`, service `hill175.service`, demo TCP port `25566`.
- Web requests must come through Cloudflare and nginx with a valid origin certificate.
  Origin CA alone does not restrict callers: also enforce Cloudflare ingress and
  Authenticated Origin Pulls. Bind authentication services to loopback.
- Browser interactions are authorized; do not ask for browser-interaction permission.
