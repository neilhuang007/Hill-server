Hill175 campus and exhibition hub - map folder handoff
=====================================================

This packet holds the maps the Hill175 server reads, each already in the folder
the server expects. Nothing in the server code names a map, version or archive:
whatever is in these folders is what the server uses.

  world-templates/hill_people_template/   campus copied for each People entry
  world-templates/hill_hub/               exhibition hub world
  world-templates/hill_auth/              sign-in lobby world (only if included)

The campus revision and bounds are recorded in
world-templates/hill_people_template/hill-campus-template.yml. V29 is an
unfinished floating exterior draft. It has newer buildings and grounds than the
previous V19 server input; it is not a finished reconstruction.

Installation
------------
1. Stop Paper and back up the server folder.
2. Extract this ZIP to a temporary staging folder and check it (see Verification).
   On a Linux host without unzip:  python3 -m zipfile -e <this zip> <staging folder>
3. Copy the complete world-templates folder into the server folder:
     Windows: the folder containing paper.jar
     Linux:   /opt/hill175   (create it if needed; the installer sets file ownership)
   The result must be, for example:

     <server>/world-templates/hill_people_template/region/r.*.*.mca
     <server>/world-templates/hill_hub/level.dat
     <server>/world-templates/hill_hub/hill-world.yml

   If a folder already exists, move it aside as a backup first. Replace a whole
   folder; do not merge two revisions' files.
4. Install or update the Hill175 server from the GitHub source:
     Windows: .\ops\prepare-local-runtime.ps1 -Runtime <server folder>
     Linux:   bash ops/install-server.sh --microsoft   (or --allow-development-auth)
   Both check these folders first and say which one is missing or incomplete.
5. Start Paper. It imports the hub (and lobby, if supplied) on that start and
   keeps the world it replaces under <server>/replaced-worlds/. New People
   entries and explicit owner resets copy the campus folder. Existing participant
   worlds remain unchanged.

For the next revision of any map, stop Paper and replace the same folder; no
version pin, configuration or code change is needed.

Map coordinates
---------------
hill-world.yml inside a hub or lobby folder gives the arrival point and, for the
hub, where the category guides stand:

  spawn: [x, y, z, yaw, pitch]
  npcs:
    journey: [x, y, z, yaw, pitch]
    place: [x, y, z, yaw, pitch]
    people: [x, y, z, yaw, pitch]
    survival: [x, y, z, yaw, pitch]

Yaw and pitch are optional. Without the file, players arrive at the save's own
spawn and the guides stand around it.

Sign-in lobby
-------------
No lobby map is required. Without world-templates/hill_auth the server keeps the
lobby it already has, or builds its own plain one. To use a different lobby, put
an approved Minecraft Java world save (level.dat directly inside) in that folder.

The prepared campus uses standard Anvil region files from the native Java 26.1.2
conversion. The project server targets Paper 26.2. An empty, truncated or wrongly
nested folder is rejected. The server does not extract archives: the files must
be directly inside the folders above.

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
Linux, from the extracted folder:
  sha256sum -c SHA256SUMS
Compare the result to the matching entry in SHA256SUMS.

Server source, configuration examples and deployment notes remain at:
  https://github.com/neilhuang007/Hill-server
The Linux/systemd installer and updater are not Windows service installers.
No internal research, construction notes, agent instructions, credentials or player
account files are added to this packet. Paper, Java and third-party plugin binaries
are obtained separately through the deployment process, not redistributed here.
