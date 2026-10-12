Hill175 campus and exhibition hub - Windows asset handoff
=======================================================

This packet includes the explicitly selected campus in a ready-to-copy folder,
the owner-supplied exhibition hub ZIP, and checksums. The campus revision and
bounds are recorded in world-templates/hill_people_template/hill-campus-template.yml.
V29 is an unfinished floating exterior draft. It has newer buildings and grounds
than the previous V19 server input; it is not a finished reconstruction.

Campus installation on Windows
------------------------------
1. Stop Paper and back up the server folder.
2. Extract this outer ZIP to a temporary staging folder.
3. Copy the complete world-templates/hill_people_template folder into the server
   folder (the directory containing paper.jar). The result must be:

   <server>\world-templates\hill_people_template\region\r.*.*.mca
   <server>\world-templates\hill_people_template\hill-campus-template.yml

   If a template already exists, move it aside as a backup first. Replace the
   entire template directory; do not merge two revisions' region files.
4. Install the updated Hill175 plugin built from the GitHub source. Its config at
   <server>\plugins\Hill175\config.yml should contain:

   people:
     template-folder: world-templates/hill_people_template
     require-template: true
     structure-file: ""

   Keep other existing settings. The old template-region-file-count and
   template-poi-file-count settings are no longer used by the updated plugin.
5. Restart Paper. New People entries and explicit owner resets copy this folder.
   Existing participant worlds remain unchanged. For the next campus revision,
   stop Paper and replace the same folder; no version pin or code change is needed.

The prepared campus uses standard Anvil region files from the native Java 26.1.2
conversion. The project server targets Paper 26.2. An empty, truncated or wrongly
nested template is rejected when creating/resetting a People entry. The plugin
is not an archive extractor: region/ must be directly inside the configured folder.

Exhibition hub (first installation only)
---------------------------------------
The assets/ directory contains Hill175-Exhibition-Hub-2026-08-26.zip. Extract its
inner world folder and rename it hill_hub alongside paper.jar while the server
is stopped. Do not replace an existing running hub or participant worlds. The
repository's Windows local-runtime helper instead takes this ZIP in runtime/assets/.
The same helper now expects the campus pre-extracted in runtime/server/world-templates/.

Optional campus resource pack
-----------------------------
If resourcepacks/Hill175-campus-resources.zip is present, Java players can place
it in their Minecraft resourcepacks folder and enable it. It contains the asphalt
slab/stair appearance used in the V29 review. It does not install automatically or
supply a Bedrock resource pack; automatic delivery requires a separately hosted
resource-pack URL. The world can load without it using vanilla block appearances.

Verification
------------
SHA256SUMS contains the SHA-256 of every included payload file. Windows PowerShell:
  Get-FileHash .\world-templates\hill_people_template\region\r.0.0.mca -Algorithm SHA256
Compare the result to the matching entry in SHA256SUMS.

Server source, configuration examples and deployment notes remain at:
  https://github.com/neilhuang007/Hill-server
The Linux/systemd installer and updater are not Windows service installers.
No internal research, construction notes, agent instructions, credentials or player
account files are added to this packet. Paper, Java and third-party plugin binaries
are obtained separately through the deployment process, not redistributed here.
