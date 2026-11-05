# Automated Bedrock compatibility

Geyser translates Bedrock packets into Java packets, so both editions use the
same Paper server, worlds, entries and building rules. Floodgate permits Bedrock
accounts without requiring a separate Java account. Two independent game servers
are unnecessary for this setup. See the [official Geyser overview](https://geysermc.org/)
and [Floodgate setup](https://geysermc.org/wiki/floodgate/setup/).

The deployment manifest pins **Geyser 2.12.1 build 1289**, **Floodgate 2.2.5
build 141**, **ViaVersion 5.12.2**, and Paper **26.2**. ViaVersion provides the
Java 26.3 protocol required by the bridge. The [pinned Geyser source](https://github.com/GeyserMC/Geyser/commit/3a1ebeb51901ddcbadb7d90c6bd9150053571ed6)
uses configuration schema 12 and accepts `both` or `nethernet` transport.
The smoke fixture uses `both`, loopback binds and disabled STUN discovery.
The manifest records immutable download URLs and SHA-256.

## Run the script

Build the plugin with the project's JDK 25 build command. Supply an existing
local runtime containing `paper.jar`, dependencies and the three template folders
(`hill_auth`, `hill_hub`, `hill_people_template`). The runner reads those files
and creates its own disposable server under ignored `runtime/`.

Install the protocol test dependency once (Node.js 24 or newer is the package's
supported runtime):

```powershell
npm install --prefix runtime/bedrock-protocol-smoke --no-fund --no-audit --allow-git=all bedrock-protocol@3.60.1
```

Then run:

```powershell
py -3 ops/run-bedrock-smoke.py --java E:/projects/Hill-server/runtime/tools/jdk25/jdk-25.0.4.1+1/bin/java.exe
```

Use `--source`, `--plugin`, `--java`, or `--node` to select installed components.
This workspace also has the verified official Node 24.22.0 portable binary at
`runtime/bedrock-protocol-smoke/node-v24.22.0-win-x64/node.exe`; pass that path
with `--node` when the system's Node installation is older than 24.
The default isolated ports are Java TCP 25568, Bedrock UDP 19134 and gallery TCP
8789. The runner refuses occupied ports and an existing output directory. It
does not restart the normal local server or change the remote deployment.

The runner:

1. Copies maps and installs checksum-verified Geyser/Floodgate through the existing installer.
2. Starts a loopback bridge with Xbox login validation enabled and checks that an unsigned Bedrock login is rejected.
3. Enables unsigned connections only in that disposable loopback bridge, then drives actual Bedrock packets through the shared Java gameplay.
4. Restarts Paper and logs in again to check the prefixed account and entry persistence.
5. Stops its server and restores the installer's secured managed configuration, including on a failed check.

The client uses **bedrock-protocol**, independently of the Java Mineflayer smoke
suite. It acknowledges Bedrock container closes, teleports, keepalives, and
forms. Its `1.26.51` packet schema is protocol 2193; its login reports game
version `1.26.52`, which the pinned Geyser source maps to that same codec.
Clientbound item display data is not echoed as a serverbound item
descriptor; those encodings differ in current Bedrock. Inventory actions use
server-provided stack IDs. The [pinned Geyser codec](https://github.com/GeyserMC/Geyser/blob/f66329d9d21b3c836edc014fbb9d8312fbe34285/core/src/main/java/org/geysermc/geyser/network/bedrock/CodecProcessor.java)
documents the distinction.

## What the automation measures

The script checks admission, two-argument registration that reads Floodgate's
actual player name, native project buttons, optional title/description forms,
floating camera items, preview and exit, automatic submission and unlock, all
36-building campus-map contents and a selection action, selected-building arrival, exterior camera
capture, and reconnect/restart persistence. It waits for Geyser's first-second
camera initialization before asserting that controller input cannot move or
rotate the saved view.

Build the campus UI pack with `uv run --script ops/package-bedrock-ui.py` before
running the smoke script to include it in the disposable server. For a normal
local server, copy `build/bedrock-ui/hill-campus-ui.mcpack` into
`plugins/Geyser-Spigot/packs/`, restart, then reconnect and accept the pack.
The [pack guide](../../server-assets/hill-bedrock-ui/README.md) explains packaging
and catalog matching. The packet client verifies the building actions; it does
not render or click the custom map layout.

For block editing, the runner's console supplies stone and queries the resulting
blocks. It also moves the test player outside the editable building area to
set up an exterior photo. Placement, breaking, camera capture, and preview must
come from the Bedrock client's interaction and input packets. The test sends touch and gamepad input modes;
that verifies their packet handling, not physical controller ergonomics.

Per-phase JSON reports and client/server logs remain in the printed output
directory. No Microsoft account tokens are requested or stored by this test.
Unsigned loopback gameplay is not a claim that Xbox Live or Hill tenant SSO was
tested, and protocol checks do not measure native textures, frame rate, or touch
layout. The deployed demo must have the bridge installed and its UDP port opened
before real Bedrock connections can join it.

## Recorded result — October 17 student interaction update

`./gradlew.bat test jar` passed 171 tests, and the campus pack's seven Python
checks passed. The complete Bedrock run at
`runtime/bedrock-ux-20261017-final/` passed secured admission rejection,
registration without a nickname argument, native buttons and optional details,
block placement/breaking, floating camera items, submission/unlock, selected
building arrival, exterior camera capture/preview, reconnect, and Paper restart.
The gameplay report observed six floating eye item packets and 120 fixed-camera
instructions. The disposable server stopped and its secured bridge configuration
was restored and verified.

The updated plugin and campus pack were installed in `runtime/server/`, with the
previous plugin and plugin data backed up under
`assets/local-deploy-backups/20261017-164019-student-ux/`. Java TCP 25566 and
Bedrock UDP 19132 responded after restart. The generated map artwork was
inspected; native Bedrock map rendering and touch/controller focus still need
manual review because the desktop review helper was unavailable.

## Recorded result — October 15

| Automated behavior | Observed result |
| --- | --- |
| Secure Bedrock negotiation | Unsigned Xbox admission rejected; no world spawn |
| Floodgate demo account | Exact prefixed nickname registers and survives reconnect/restart |
| Journey creation | Bedrock inventory clicks and editable native form save metadata |
| Block editing | Bedrock touch placement and gamepad input breaking change the queried Java blocks |
| Camera and submission | Capture item, native fixed view, Exit item, fresh images, publication and unlock succeed |
| Place selection | Map pixels, numbered selector, building detail and Start Building succeed |
| Camera immediately after returning | Fixed position and rotation survive gamepad movement; Exit restores the default camera |

The complete baseline pass is preserved under
`runtime/bedrock-script-20261015-final3/`. The Node 24 pass repeated the gameplay
actions and found a fast-return camera tracking race. The plugin now retries
camera focus only during the first second, at 1, 8 and 20 ticks. The strict replay
of the retained account after a Paper restart passed with 28 fixed-view camera
instructions and an explicit default-camera reset on Exit; see
`runtime/bedrock-script-20261015-final5/report-reconnect.json` and
`server-camera-fix.log`. That replay issues preview immediately after Enter Build;
it adds no arrival delay. The test servers were stopped and the secured managed
configuration passed installer verification afterward.

The normal local runtime also passed the secured admission probe on Bedrock UDP
19132 with Xbox validation enabled; Java continues on TCP 25566. The remote
deployment was unchanged by this work.
