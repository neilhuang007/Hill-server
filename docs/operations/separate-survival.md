# Separate Java survival

`/survival` and the Survival guide use the same authenticated route. By default
that route preserves the existing local survival worlds. Operators can enable a
separate Java destination after securing it. Bedrock then stays in the existing
local survival worlds, or receives a Java-only message if the local fallback is
disabled. The Java destination must not install Geyser/Floodgate.

## Choose the runtime before generating a world

The current campus runs Paper 26.2. For the simplest vanilla-client experience,
use a second Paper 26.2 process with the existing pinned datapacks in
`server-assets/survival-worldgen-manifest.tsv`. These provide Terralith,
Terratonic terrain shaping, Structory and Towers, Towns and Towers, Incendium
Legacy and Nullscape. No player mod or resource pack is required.

The supplied cinematic profile contains Fabric jars, custom-content mods and
mixed Minecraft versions. Paper cannot load those jars. See
[survival generation profile](survival-generation-profile.md) for the broader
inventory and exclusions. Do not put the entire client profile in any server.
An expanded Fabric selection needs a separate version-aligned runtime and a
vanilla-client join check before opening admission. It cannot load Hill175's
Paper plugin.

## Stage an independent server

1. Use a new runtime such as `/opt/hill175-survival`, a separate unprivileged
   service account, service, backup repository and TCP port `25567`. Do not reuse
   the campus runtime or symlink its worlds, player inventories or permissions.
2. For Paper, install the pinned Paper/JDK versions from
   `server-assets/server-binaries.env`. Copy `server-config/survival/server.properties`
   into the new runtime. Accept the Minecraft EULA only after reviewing it.
   The template enables online-mode and an enforced whitelist and disables
   resource-pack requirements, RCON and PvP.
3. With the new server stopped, install the selected generation packs before
   its first world generation. For the existing Paper selection:

   ```bash
   bash /opt/Hill-server/ops/install-survival-worldgen.sh /opt/hill175-survival
   ```

   Use this only for the intended new runtime. The worldgen installer has
   migration behavior for changed manifests; it is not a generic mod installer.
4. Keep the Java whitelist empty until school staff approve each authenticated
   Java account. Direct connections can bypass the campus command, so the
   destination must enforce admission independently. A whitelist is an
   independently managed roster, not inherited Microsoft SSO. Remove revoked
   accounts on both servers. Never use offline-mode to make transfers easier.
5. Start the independent service and test with an approved vanilla Java client
   matching the destination version. Check Overworld, Nether, End, respawn,
   inventories, reconnect and backups. Confirm an unlisted Java account cannot
   join and there is no Bedrock listener. Install staff recording separately on
   this instance: the campus recorder cannot see another process. Also install
   equivalent school profanity filtering and disable all private-message aliases
   on the destination before opening transfers. Hill175's bundled chat safety
   protects its campus and local survival worlds, not a separate server process.
   Keep transfers disabled until both destination admission and moderation are ready.

## Enable the campus route

In the protected `/etc/hill175/hill175.env`:

```text
HILL175_SURVIVAL_MODE=transfer
HILL175_SURVIVAL_JAVA_HOST=survival.your-school-domain.example
HILL175_SURVIVAL_JAVA_PORT=25567
HILL175_SURVIVAL_DESTINATION_ACCESS_CONFIGURED=true
HILL175_SURVIVAL_BEDROCK_LOCAL=true
```

These settings override `survival-navigation` in the plugin YAML and survive
routine deployment, which installs fresh YAML defaults. The managed deployment
requires Microsoft/online mode for transfer; the offline development demo keeps
local survival. Local testing without an environment file can use the equivalent
YAML keys `mode`, `java-host`, `java-port`, `destination-access-configured` and
`bedrock-local` under `survival-navigation`.

Use a real DNS-only Minecraft hostname, not an HTTP Cloudflare proxy hostname.
The destination needs `accepts-transfers=true` (included in the template).
The acknowledgement above must only be set after destination admission is
configured. Transfer mode also requires online-mode on the campus and uses
Floodgate's authenticated identity API, never username prefixes, to keep
Bedrock off the Java destination. If identity resolution fails, transfer is
refused.

Restart the campus through the normal deployment procedure. `/survival` now
sends authenticated Java players to that host; the Survival guide does the same.
No inventory or school authentication session is forwarded. Students rejoin the
campus address to return, and authenticate normally. `/hub` only returns from
local survival; it is not installed on the independent server by this change.
A separate Fabric Minecraft version requires students to launch that vanilla
version first; a transfer packet does not translate protocols.

Set `HILL175_SURVIVAL_MODE=local` to restore the original route, or `disabled` to close
survival navigation. Existing local worlds and inventories are preserved in all
modes. Neither the independent service nor firewall/DNS/roster is provisioned by
the campus deployment wrapper.
