# Hill175 asset packet: placement instructions

This packet holds the map folders the Hill175 server needs that are not in Git.
Everything else comes from https://github.com/neilhuang007/Hill-server: source,
installer, configuration examples, and the pinned download lists for Paper, Java,
Geyser/Floodgate, Chunky and datapacks. The installer fetches and checksums those
itself.

## Contents

| Path in this ZIP | Purpose |
| --- | --- |
| `world-templates/hill_people_template/` | Campus template. Seeds the blueprint world and every personal campus on first start |
| `world-templates/hill_hub/` | Hub world where every player arrives after sign-in, with the My Campus and Blueprint guides |
| `SHA256SUMS` | Checksums of every map file |
| `README.txt` | Longer map-folder reference |

No sign-in lobby map is included. Without `world-templates/hill_auth`, the server
builds its own plain sign-in lobby.

## Placement on the Linux server

The runtime folder is `/opt/hill175` and the source checkout is `/opt/Hill-server`.
Run these steps as root.

1. Copy this ZIP to the server, then extract and verify it:

   ```bash
   python3 -m zipfile -e Hill175-deployment-assets.zip /root/hill175-assets
   (cd /root/hill175-assets && sha256sum --check --quiet SHA256SUMS)
   ```

2. Move aside any existing map folders. Never merge two revisions' files:

   ```bash
   mkdir -p /opt/hill175/world-templates
   for name in hill_people_template hill_hub; do
     [ -e /opt/hill175/world-templates/$name ] && mv /opt/hill175/world-templates/$name /root/$name.previous-$(date -u +%Y%m%dT%H%M%SZ)
   done
   cp -a /root/hill175-assets/world-templates/. /opt/hill175/world-templates/
   ```

   The result must be `/opt/hill175/world-templates/hill_people_template/region/r.*.*.mca`
   and `/opt/hill175/world-templates/hill_hub/level.dat`. The installer sets file ownership.

3. Create `/etc/hill175/hill175.env` (root-owned, mode `0600`) from `.env.example`
   in the repository. Place the Origin certificate, key and AOP CA files at the
   configured paths. See `docs/operations/microsoft-sso-setup.md`.

4. Install from the checkout:

   ```bash
   cd /opt/Hill-server && git pull --ff-only
   bash ops/install-server.sh --microsoft
   ```

   Use `--allow-development-auth` only for a demonstration without Microsoft SSO.
   The installer checks the map folders before stopping Paper and names any
   missing folder without changing anything.

5. Verify with `journalctl -u hill175.service`. The log should show
   `Hill 175 player hub guides ready: 2/2.` After sign-in, a player should arrive
   in the hub. Using the My Campus guide should place them in their own campus
   with the Hill Menu compass, Undo clock, Send My Build emerald and campus map
   in the hotbar.

## Rules

- Replace whole folders only, and only while following the steps above.
- The campus template only seeds new worlds. Existing personal campuses and
  approved blueprint revisions are never overwritten by a new template.
- Keep worlds, credentials and the environment file out of Git.
