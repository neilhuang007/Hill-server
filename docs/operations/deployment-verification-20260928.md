# September 28 deployment verification

The logistics server is running the v19 two-blocks-per-metre People template and
updated camera controls. **Microsoft SSO and Bedrock linking remain unimplemented.**

## Deployed artifacts

| Item | Verified value |
| --- | --- |
| Application source commit | `d6300e0a55981b3c2f150cf9771307e89abce495` |
| Service | `hill175.service`, active |
| Runtime | Paper 26.2 build 119, server JDK 25 |
| Plugin SHA-256 | `eea6d7348d709f13c13252aacb4e4c5a2ec6f84144ba65a401b66f3b9f8a8ea2` |
| Campus archive | `hill_people_template_campus_v19_2x.tgz` |
| Archive SHA-256 | `b913315523e35b8231b8a56647179830d5e8c4099e2908d610f1ef2ff320598e` |
| Template | 25 region files; frozen campus v19; two blocks per metre |
| Pre-deployment Borg snapshot | `hill175-predeploy-v19-2026-09-28T18-40-24Z` |
| Previous template backup | `/opt/hill175/assets/people-template-backup.rMouPr` |

The server pulled GitHub source, built and tested it, then installed from that
build. The deployed plugin hash matches the server-built JAR. The later ignore-rule
and verification-document checkpoint does not change application code.

Existing People entries were preserved. The template applies to new entries and
owner-confirmed resets. All live reset checks targeted a newly created smoke entry.

## Checks performed

- **42 Java tests** passed locally and during the server source build, including
  invalid provider rejection, startup shutdown, and metadata eviction after world deletion.
- **88 selected Python tests plus 8 subtests** passed for the retained reconstruction
  sources. This was not an execution of every historical generator or GIS test.
- Bash, PowerShell, JavaScript and Python syntax checks passed; maintained documentation
  links resolved; the staged source scan found no world archives or credential files.
- The optimized campus packager reproduced the exact pinned archive hash.
- The installer and deployed verifier passed, including Hill175 readiness, template
  pins, worldgen configuration, and log checks. No startup/watchdog errors were found.
- Live authentication-lobby restrictions passed.
- Live camera checks passed: selected exit item, saved viewpoint lock, owner and
  visitor left/right-click exits, visible-entity exit, `/camera exit`, visitor removal
  denial, and owner-confirmed removal.
- Live People creation/reset/re-entry passed: chart, Creative owner mode, and safe
  grass arrival at `[228.5, 86, 154.5]`. Separate host-side inspection confirmed the
  created clone's v19 provenance, two-block scale and all 25 region files.

## Limits and remaining logistics

Live gameplay checks used the protocol smoke client through a temporary PuTTY SSH
forward to the running server. Direct connections from the test environment reset
twice before registration; the server remained active and later logged timeouts.
The same client passed via SSH forwarding. An idle SSH test connection also aborted;
a fresh active connection completed the campus test. This isolates a transport-path
dependency but does not identify the network component responsible. **Public direct
connectivity from student networks still needs a real-client check.** No firewall or
network-policy changes were made on insufficient evidence. The temporary tunnel is closed.

No new native-client visual screenshot run or Bedrock acceptance run was performed.
The v19 campus retains its documented unfinished buildings. CI was added, but its
hosted run status was unavailable through the unauthenticated GitHub API; the actual
server source build and local checks above are verified independently.

Local logs and structural results are retained outside Git under
`runtime/campus-reconstruction/server-integration-20260928/`. Server installation
output is `/opt/hill175/assets/deploy-v19-20260928.log`. The full deployment procedure
is in [deployment.md](deployment.md); identity requirements are in the
[Microsoft SSO design](../architecture/microsoft-sso.md).
