# Windows campus asset installation

Use the **V29 asset handoff ZIP** supplied by the project owner. It contains the
latest requested campus draft in a folder ready for the plugin, the exhibition
hub ZIP, an optional Java resource pack and checksums. V29 remains an unfinished
exterior draft. Construction research and internal notes are not in the packet.

1. Stop Paper and back up the server directory.
2. Extract the handoff to a separate staging directory with File Explorer or
   `Expand-Archive`. Compare file hashes with `SHA256SUMS` using `Get-FileHash`.
3. Copy its `world-templates/hill_people_template` directory into the directory
   containing `paper.jar`. If a template already exists, preserve it under a
   separate backup path first. Replace the whole folder; do not merge revisions.
4. Build the updated plugin from GitHub using JDK 25 and
   `.\gradlew.bat clean test jar`. Install the resulting
   `build\libs\Hill-server-1.0-SNAPSHOT.jar` as `plugins\Hill175.jar` while stopped.
5. In `plugins\Hill175\config.yml`, preserve other settings and use:

   ```yaml
   people:
     template-folder: world-templates/hill_people_template
     require-template: true
     structure-file: ""
   ```

6. Restart Paper. New People entries and explicit owner resets use the installed
   template. Existing participant worlds retain their data and geometry.

The resulting layout is:

```text
<server>/
  paper.jar
  plugins/
    Hill175.jar
    Hill175/config.yml
  world-templates/
    hill_people_template/
      region/r.*.*.mca
      hill-campus-template.yml
      hill-campus-template.json
      .hill175-people-ready
```

Future campus revisions go into the same folder. The plugin ignores the old
`template-region-file-count` and `template-poi-file-count` settings. It requires
nonempty, untruncated Anvil region files, accepts optional POI data and uses any
supplied bounds/spawn metadata. It does not select ZIPs or descend through nested
world folders. An invalid template blocks new entries/resets instead of creating
a replacement flat campus. Replace files only while Paper is stopped.

For the hub's first installation, extract the included hub ZIP and rename its
inner world directory to `hill_hub` beside `paper.jar`. Preserve any existing hub;
do not overwrite participant worlds. The Windows development helper
`ops/prepare-local-runtime.ps1` instead reads the hub ZIP from `runtime/assets/`
and validates the template already under `runtime/server/world-templates/`.
That helper is a development demo setup, not a school SSO/service installer.

Java players can enable `resourcepacks/Hill175-campus-resources.zip` in their
client's resource packs to get the asphalt slab/stair appearance. The pack is
optional for loading the world and does not install itself. Automatic delivery
requires hosting it and configuring Paper's resource-pack URL; Bedrock needs its
own compatible pack.

This is the asset installation procedure, not complete Windows service setup.
The [SSO guide](microsoft-sso-setup.md) explains required IT values and authentication
boundaries, but its systemd/nginx automation targets Linux. The existing nightly
systemd updater also targets Linux and has not been enabled for this Windows host.
