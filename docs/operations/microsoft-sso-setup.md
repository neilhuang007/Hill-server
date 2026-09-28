# Hill IT setup: Microsoft sign-in and Java/Bedrock accounts

The plugin includes a Microsoft authentication service. IT supplies the values in
[.env.example](../../.env.example); no source changes are needed. The current public
demo remains in development mode until those values and the protected hostname
are configured. A real Hill tenant and actual Java/Bedrock clients must pass the
pilot below before student admission.

## 1. Register the school application

In Hill's Microsoft Entra tenant, create an **App registration** named Hill 175.
Select **Accounts in this organizational directory only**. Add a **Web** platform
with exactly this redirect URI, substituting the approved hostname:

```text
https://auth.example.org/auth/microsoft/callback
```

Record the **Directory (tenant) ID** and **Application (client) ID**. Under
Certificates & secrets, create a client secret and record its **value**, not its
identifier. Store it only in the protected host environment file. Set a rotation
reminder before expiry; this release uses a client secret, not certificate-based
client authentication.

Create an enabled app role with allowed member type **Users/Groups** and value
`Hill175.Student`. In the enterprise application, set **Assignment required = Yes**
and assign that role to the approved student group or individual students. Group
assignment needs appropriate Entra licensing and does not include nested groups.
Do not assign the role broadly to guests or all tenant users. The plugin requires
the exact role in the validated ID token. [Microsoft app roles](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps),
[user/group assignments](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/assign-user-or-group-access-portal).

The application requests `openid profile`. It uses the signed `name` claim for
presentation and `(tid, oid)` for the student's stable identity. IT should confirm
that the directory name is suitable for students to see and correct missing names
in Entra. No Graph directory-wide permission or email-domain test is needed.
The school account is separate from the student's Minecraft/Xbox account.
[Microsoft ID token claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

## 2. Install the environment file

After pushing locally and pulling the source in `/opt/Hill-server`, use a root shell
on the server. The [deployment guide](deployment.md) describes PuTTY access, assets,
backup and source builds.

```bash
install -d -m 0700 -o root -g root /etc/hill175
install -m 0600 -o root -g root /opt/Hill-server/.env.example /etc/hill175/hill175.env
editor /etc/hill175/hill175.env
python3 /opt/Hill-server/ops/check-auth-config.py --expect-mode microsoft
```

Run the copy command only when first creating the file; upgrades preserve it.
Use `KEY=value` or `KEY='value'`, one assignment per line. Do not add `export`, shell
commands, substitutions, inline comments, escapes, or multiline values. systemd
reads the file directly; the installer never executes it. Keep it root-owned with
mode `0600`; systemd passes the variables to the `hill175` service account.

| Variable | Required value / default |
| --- | --- |
| `HILL175_AUTH_MODE` | `microsoft`; `development` is only for the controlled demo |
| `HILL175_ENTRA_TENANT_ID` | Hill tenant GUID |
| `HILL175_ENTRA_CLIENT_ID` | Application/client GUID |
| `HILL175_ENTRA_CLIENT_SECRET` | Current client secret **value** |
| `HILL175_ENTRA_REQUIRED_ROLE` | `Hill175.Student` |
| `HILL175_AUTH_PUBLIC_URL` | Approved HTTPS origin, e.g. `https://auth.example.org`, without a path |
| `HILL175_AUTH_PORT` | `8087`, bound to `127.0.0.1` only; allowed range 1024–65535 |
| `HILL175_MAX_LINKED_ACCOUNTS` | `4` game accounts per student; allowed range 2–20 |

The Java process reads environment variables at startup. Editing the file requires
a service restart. A `.env` file in the checkout is not automatically loaded.
Local developers can set these variables in their shell before starting Paper;
Microsoft mode still requires online-mode game authentication and the trusted
HTTPS proxy. Missing or invalid Microsoft settings stop startup; there is no
fallback to development approval.

## 3. Protect the browser endpoint

Create a proxied Cloudflare DNS record for the approved hostname. Configure
**Full (strict)** with a matching Origin CA certificate/key on nginx, then configure
Authenticated Origin Pulls. Prefer a certificate specific to the zone/hostname.
Allow web ingress only from Cloudflare's current IPv4 and IPv6 ranges. Origin CA
alone does not restrict who can reach the origin. Keep public port 80 closed and
perform HTTPS redirects at Cloudflare. [Origin CA](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/),
[Authenticated Origin Pulls](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/).

Adapt [the nginx example](../../ops/nginx/hill175-auth.conf.example), replacing the
hostname and certificate paths. If changing the authentication port, change nginx's
upstream too. Check `nginx -t` before reloading nginx. The example sends the canonical
Host and HTTPS scheme, requires the client certificate, disables proxy caching,
and avoids logging authentication query strings. Bypass Cloudflare caching for
the entire auth hostname and do not add analytics to sign-in pages.

Never expose port 8087 publicly. The plugin has no public endpoint that can mark a
UUID authenticated. No database or separate identity daemon is required: the
embedded service and plugin share a process, while Microsoft network calls and
link persistence run away from the game tick thread.

## 4. Build and enable Microsoft mode

Back up the demo runtime before switching authentication modes. Existing demo
records are not proof of school identity and are not automatically reassigned by
nickname. Preserve them for reviewed recovery; the online UUID may also differ
from a prior offline UUID. Never rename player-data files by guesswork.

```bash
cd /opt/Hill-server
bash ops/install-server.sh --microsoft
bash ops/verify-server.sh
```

The installer builds and tests from the pulled source, preserves the environment
file, sets `online-mode=true`, restarts Paper and checks the authentication mode and
loopback listener. Java players need a verified Minecraft Java account. Do not set
offline mode to accommodate Bedrock; use Floodgate below. This release targets a
direct Paper installation, not a proxy network with offline backend servers.

For the controlled demo, use `HILL175_AUTH_MODE=development` and
`bash ops/install-server.sh --allow-development-auth`. A mismatch between the flag
and the existing environment file is rejected before the server is stopped.

## 5. Add Bedrock transport

Install compatible Geyser-Spigot and Floodgate-Spigot releases on this same Paper
server, following the official [Geyser setup](https://geysermc.org/wiki/geyser/setup/)
and [Floodgate setup](https://geysermc.org/wiki/floodgate/setup/). Record the exact
download versions and hashes in the deployment record. These third-party JARs are
not bundled or downloaded by the Hill installer.

Set Geyser's Java authentication type to `floodgate`; keep Paper online mode enabled.
Open a separate Bedrock UDP port (normally 19132). Keep Floodgate's private key out
of Git and restrict access to it. Hill175 reads Floodgate's authenticated XUID; it
does not infer Bedrock identity from a username prefix. Java TCP and Bedrock UDP
are game traffic, separate from the Cloudflare-protected web endpoint.

Join with each edition and authenticate using the **same Hill school account**.
Both game identities then resolve to one participant with the same entries,
permissions and two-category limit. One active connection per participant is
allowed. Survival inventories remain specific to each game identity; they are
not merged across editions.

## 6. Student experience and pilot

1. Join the server and remain in the restricted authentication lobby.
2. Open the supplied HTTPS link and select the Hill Microsoft account.
3. Check the name and game account on the browser page, then enter its one-time
   code in that same live game connection with `/verify <code>`.
4. Enter the hub with the school display name in chat, tab list and competition
   menus. The overhead label includes the school name and Minecraft handle.

Run `/verify` to replace an expired link. Every new game connection requires school
authentication. Sessions expire no later than 30 minutes or the ID token expiry;
reconnect and authenticate again. Role removal is enforced on the next exchange,
not through immediate Microsoft push notifications.

Before opening admission, test an assigned student in both editions, an unassigned
school account, an external/personal account, missing role, expired link, wrong
confirmation code, disconnect/rejoin, and switching linked devices. Confirm both
aliases see the same entries and cannot occupy both team slots. Check name display
and link/code entry on actual Bedrock devices: this release does not supply a
native Bedrock sign-in form. Repeat the camera exit and campus smoke tests.

Check that direct-origin web requests, wrong Host/SNI, missing AOP certificates and
public access to the loopback service fail. Test real Microsoft callbacks through
Cloudflare. Local automated tests cannot establish tenant configuration, external
firewall behavior, directory name policy or real-client presentation.

## Operations and recovery

Back up `plugins/Hill175/school-identities.json` with competition data and worlds.
It contains student identity mappings and names; restrict it and its backups.
Back up `/etc/hill175/hill175.env` separately in protected secret storage, never Git.
Changing tenant/client values is a migration, not routine credential rotation.

An existing game account cannot silently move to another student. For an ownership
conflict, preserve the files and have an authorized operator investigate both
proofs; this release has no automated unlink/legacy-owner migration command.
Do not edit identity mappings while Paper is running. A corrupt identity store
must prevent Microsoft-mode startup.

Before the event, Hill must set its real-name disclosure policy, help contact,
event-end data/backup retention date and operator recovery procedure. Automatic
purging, a staff suspension console and anonymous voting are separate future work.
See [implementation architecture and limits](../architecture/microsoft-sso.md).
