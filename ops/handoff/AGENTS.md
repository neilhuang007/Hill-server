# Hill175 server: placement and installation instructions

Follow these steps in order on a Debian/Ubuntu Linux host to get a running Hill175
server. This packet holds the map folders that are not in Git. Everything else
comes from https://github.com/neilhuang007/Hill-server: source, installer,
configuration examples, and pinned download lists for Paper, Java,
Geyser/Floodgate, Chunky and datapacks. The installer downloads and checksums
those itself. Do not copy plugin or server JARs by hand.

## Packet contents

| Path in this ZIP | Purpose |
| --- | --- |
| `world-templates/hill_people_template/` | Campus V76 (`campus-context-v76-2x`). Seeds the blueprint world and every personal campus on first start |
| `world-templates/hill_hub/` | Hub world. Every player arrives here after sign-in and finds the My Campus and Blueprint guides |
| `SHA256SUMS` | Checksums of every map file |
| `README.txt` | Longer map-folder reference |

No sign-in lobby map is included. Without `world-templates/hill_auth`, the server
builds its own plain sign-in lobby. That is expected.

Paths used below: runtime `/opt/hill175`, source checkout `/opt/Hill-server`,
service `hill175.service`, environment file `/etc/hill175/hill175.env`.
Run every command as root.

## 1. Prepare the host and source

```bash
apt-get update
apt-get install -y git curl ca-certificates tar gzip borgbackup util-linux python3 iproute2 nginx openssl
git clone https://github.com/neilhuang007/Hill-server.git /opt/Hill-server
mkdir -p /opt/hill175
```

If `/opt/Hill-server` already exists, run `cd /opt/Hill-server && git pull --ff-only`.
Never edit source on the server: changes go through GitHub.

## 2. Place the maps

Copy this ZIP to the server, then extract and verify it. `unzip` is not needed:

```bash
python3 -m zipfile -e Hill175-deployment-assets-v76-20261123.zip /root/hill175-assets
(cd /root/hill175-assets && sha256sum --check --quiet SHA256SUMS)
```

The check must print nothing. Then move aside any existing map folders and copy
in the new ones. Replace whole folders and never merge two revisions' files:

```bash
mkdir -p /opt/hill175/world-templates
for name in hill_people_template hill_hub; do
  if [ -e /opt/hill175/world-templates/$name ]; then
    mv /opt/hill175/world-templates/$name /root/$name.previous-$(date -u +%Y%m%dT%H%M%SZ)
  fi
done
cp -a /root/hill175-assets/world-templates/. /opt/hill175/world-templates/
```

Confirm the layout. Files must sit directly in these folders, not one level deeper:

```bash
ls /opt/hill175/world-templates/hill_people_template/region | head -3   # r.X.Z.mca files
head -1 /opt/hill175/world-templates/hill_people_template/hill-campus-template.yml   # revision: campus-context-v76-2x
ls /opt/hill175/world-templates/hill_hub/level.dat /opt/hill175/world-templates/hill_hub/hill-world.yml
```

The installer sets file ownership. On a server that already ran an older campus,
the existing blueprint and personal campuses keep their contents. The new
template only seeds worlds that do not exist yet.

## 3. Create the environment file

```bash
mkdir -p /etc/hill175/tls
cp /opt/Hill-server/.env.example /etc/hill175/hill175.env
chown root:root /etc/hill175/hill175.env && chmod 600 /etc/hill175/hill175.env
```

Fill in the Entra tenant ID, client ID, client secret and `HILL175_AUTH_PUBLIC_URL`.
Use `KEY=value` or `KEY='value'` only, with no `export`, inline comments or
multiline values. Unknown keys are rejected. Place the Cloudflare Origin
certificate, its private key (root-owned, mode `0600`) and the Authenticated
Origin Pulls CA at the paths in the file. To trust proxies other than Cloudflare,
set `HILL175_TRUSTED_PROXY_RANGES`, for example `cloudflare,203.0.113.0/24`.
Full details are in `docs/operations/microsoft-sso-setup.md`.

Check the file before installing:

```bash
python3 /opt/Hill-server/ops/check-auth-config.py --expect-mode microsoft
```

## 4. Install and start

```bash
cd /opt/Hill-server
bash ops/install-server.sh --microsoft
```

Use `--allow-development-auth` only for a demonstration without Microsoft SSO,
because it does not verify Hill membership. The installer checks the maps,
environment and certificates before stopping anything. It names any missing
folder and changes nothing in that case. It installs the service, the nginx site
and daily backups, then starts Paper.

Firewall: allow TCP `25566` (Java), UDP `19132` and `19133` (Bedrock), and TCP
`443` from the trusted proxy ranges only. Never expose `8087` or `8788`. They
bind to loopback.

## 5. Verify

```bash
systemctl is-active hill175.service
journalctl -u hill175.service --since "10 min ago" | grep -E "Hill175|Done"
```

The log must show `Personal campuses and blueprint ready`, `Hill 175 player hub
guides ready: 2/2.` and `Done`. In game, after Microsoft sign-in, a player must:

1. Arrive in the hub and see two guides, **My Campus** and **Blueprint**.
2. Use My Campus and land in their own campus in Creative mode, with the Hill
   Menu compass, Undo clock, Send My Build emerald and campus map in the hotbar.
3. Find that `/survival` is not a command.

## Staff access: closed by default

Nobody is staff after installation. Keep it that way:

- **Roles come only from the Hill role system.** That means Entra app-role
  assignments (`Hill175.Staff`, `Hill175.Moderator`, `Hill175.Administrator`),
  an administrator's `/hillstaff role <player> <role>`, or the one-time
  administrator unlock below. Every new account is an ordinary Player.
- **Entra:** assign `Hill175.Student` to students. Assign staff, moderator and
  administrator roles only to named individuals or a dedicated staff group,
  never to "All users" or a student group. Set "Assignment required" to Yes on
  the enterprise application, and keep the four role values distinct (the
  checker enforces this).
- **No operators.** Do not run `op`, and do not add entries to
  `/opt/hill175/ops.json`. Every Hill permission defaults to off, operator
  status grants no Hill staff tools, and it would still give vanilla
  server-command access.
- **LuckPerms:** do not grant `hill175.*` or any `hill175.` permission to the
  `default` group. Only grant per-person area permissions when staff recovery
  docs call for it.
- **First administrator:** after the first start, the server writes a one-time key
  to `/opt/hill175/plugins/Hill175/admin-unlock-key.txt`. Give it privately to
  the intended administrator. They sign in with Microsoft and run
  `/admin unlock <key>`. The key works once. Alternatively, an Entra
  `Hill175.Administrator` assignment grants the role at sign-in. From then on,
  the administrator appoints staff and moderators with `/hillstaff role`.
- Check any player's effective role with `/hillstaff info <player>` (staff and
  above) or `/hillstaff whoami`.

## Do not

- Do not commit worlds, the environment file, certificates or keys to Git.
- Do not open one world save in two servers at once.
- Do not delete `/opt/hill175/replaced-worlds/` or `/opt/hill175/assets/` rollback
  folders while troubleshooting a failed install.
