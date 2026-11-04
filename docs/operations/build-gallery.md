# Local build gallery

The plugin serves the build gallery at `http://localhost:8788`. It binds only to
IPv4 loopback (`127.0.0.1`); this work does not publish a website or configure DNS.
The gallery and Microsoft sign-in use separate HTTP services.

```yaml
gallery:
  enabled: true
  port: 8788
  public-base-url: http://localhost:8788
  asset-directory: plugins/Hill175/gallery-assets
```

The asset directory is relative to the Paper working directory unless an absolute
path is supplied. Restart Paper after changing these settings. `/health` is the
local gallery health route.

## Stoneborn artwork

The site includes HTML, CSS and JavaScript in the plugin JAR. Optional Stoneborn
artwork is prepared from the supplied
`reference/Stoneborn-1.20.2-1.21.11-V3.3.1.zip`; it remains outside Git. This is the
same archive currently listed for Minecraft 26.2 by the
[original STONEBORN project](https://modrinth.com/resourcepack/stoneborn).
STONEBORN is by Sindavar and is listed as all rights reserved. This local preview
keeps the archive and extracted artwork in operator-managed runtime storage. The
page credits Sindavar and links to the original project. Plain colors and borders
remain usable if artwork is absent.

With Python 3.11 or newer, Pillow and `fonttools[woff]` installed, from the checkout root:

```powershell
py ops/prepare-gallery-assets.py reference/Stoneborn-1.20.2-1.21.11-V3.3.1.zip --output runtime/server/plugins/Hill175/gallery-assets
```

The script prepares 20 fixed PNGs and a local Minecraft WOFF2 font. Uncropped PNGs are byte-identical to the ZIP;
cropped files preserve its original pixels. `asset-source.json` records the exact
source paths, crop bounds and resource-pack checksum. The HTTP service serves
only these named PNGs and `minecraft.woff2`; the source manifest and arbitrary files are unreachable.

All paths below are under `assets/minecraft/textures/`, except `pack.png`:

| Website artwork | Original file and use |
| --- | --- |
| Normal buttons | `gui/sprites/widget/button.png`; nine-slice borders 20/4/20/4 source pixels, displayed at 2× |
| Hover, selected and pressed buttons | `gui/sprites/widget/button_highlighted.png`; nine-slice borders 29/6/29/6, displayed at 2× |
| Disabled buttons | `gui/sprites/widget/button_disabled.png`; nine-slice borders 29/6/29/6, matching its metadata |
| Dividers | `gui/container/inventory.png`; top strip `(0,0,176,6)` and bottom `(0,162,176,166)` exclude inventory contents |
| Divider corners and center | X 0/12/72/104/164/176; original 8px corner caps and central ornament stay at 2×, plain fill stretches between them |
| Card and camera frames | `gui/sprites/widget/slot_frame.png`; nine-slice original border |
| Crest | Original root `pack.png` |
| Forward and back arrows | `gui/sprites/widget/page_forward.png` and `page_backward.png` |
| Stone, wood and parchment | `gui/options_background.png`, `gui/hanging_signs/oak.png` crop `(1,6,15,15)`, `gui/book.png` crop `(40,20,145,160)` |

The pack supplies normal, highlighted and disabled button sprites; selected and
pressed states reuse its highlighted artwork. Button center slices explicitly use
`fill`; normal/hover/pressed centers retain the source RGB `(55,50,42)`, and the
disabled center uses `(21,19,16)`. The text layer sits above the full original sprite.

STONEBORN inherits Minecraft's Latin font. The preparer locates a local
Minecraft 1.21.11 client JAR in the standard Windows or Linux location, or accepts
`--minecraft-client <client.jar>`. `ops/gallery_minecraft_font.py` traces the actual
bitmap glyph pixel runs from `assets/minecraft/textures/font/ascii.png`,
`accented.png` and `nonlatin_european.png`, using their character maps, advances
and baselines in `assets/minecraft/font/include/default.json`. The resulting
`minecraft.woff2` contains 554 Latin and punctuation glyphs; it is served locally
as `font/woff2` and remains outside Git. Source bitmap hashes and the client hash
are recorded in `asset-source.json`. Labels remain ordinary accessible text.

## Public entries and private previews

| Route | Content |
| --- | --- |
| `/` | Submitted builds, filtered by Journey, Place or People |
| `/entries/<entry-id>` | One submitted build and its saved camera views |
| `/preview/<private-token>` | An unlisted entry preview, including drafts |
| `/api/entries` | Anonymous submitted-entry metadata |
| `/api/entries/<entry-id>` | Submitted-entry metadata |
| `/api/preview/<private-token>` | Entry metadata authorized by its private token |
| `/api/entries/<entry-id>/images/<1-3>` | A public submitted camera image |

Draft image URLs also require the corresponding `?token=<private-token>` query.
Anyone holding a private preview link can view that entry; treat it as a secret.
The gallery does not disclose school names, participant/member identifiers, world
names or camera coordinates. Entry titles and descriptions are authored content.
Do not put personal information in them.

Every entry and image request asks the publisher for current access. Unlocking,
withdrawing or removing an entry revokes its public access, and removal also
revokes its private preview. Responses forbid caching and referrers, so a private
token is not sent to another page as a referrer. The server accepts read-only
GET/HEAD requests, serves fixed application resources and rejects encoded or
traversing paths. It never exposes the gallery's storage directory directly.

Images are server-rendered block previews with an 80-block range. They approximate
materials and shapes. They do not capture players, entities, sign text, resource
pack textures or client shaders. These limits are displayed beside entry images.
The site does not create sample submissions when the gallery is empty.

Visible gallery and entry pages check for updates every four seconds. Private
previews fill in as camera images finish, index counts follow publication changes,
and a withdrawn public detail becomes unavailable. Unchanged responses preserve
the image element, selected camera and keyboard focus. Changed images carry a
SHA-256 revision query so a replacement in the same slot refreshes reliably.
Polling pauses and pending requests abort when the tab hides or the route changes.

## Local browser checks

The Java tests exercise private/public authorization, withdrawal, route and asset
bounds, method restrictions and browser security headers. The browser smoke
script requires Python Playwright and its Chromium browser:

```powershell
py tests/gallery_browser_smoke.py --base-url http://127.0.0.1:8788
```

It saves desktop/mobile PNGs under ignored `runtime/gallery-browser-review`.
`--fixture-image <png>` additionally intercepts API requests inside that test
browser with explicitly titled browser-test fixtures. That mode exercises category
filters, keyboard navigation, the three camera slots, private/withdrawn states,
refresh, errors/retry, empty states and untrusted metadata. It never writes entries
to Paper or the publisher. Use the command without that option to inspect the
actual backend. Visual screenshots must be opened and inspected separately.

The focused automatic-update check uses browser-only fixtures and a supplied PNG:

```powershell
py tests/gallery_live_updates_browser.py --base-url http://127.0.0.1:8788 --fixture-image runtime/gallery-review/camera-renderer-fixture.png
```

The sprite/font check uses actual submitted entries, verifies the loaded Minecraft
font, compares original button center pixels in all states and compares divider
pixels at desktop and phone sizes. It saves screenshots for visual inspection:

```powershell
py tests/gallery_assets_browser.py --base-url http://127.0.0.1:8788
```

`--source-overrides` previews local CSS, JavaScript and prepared artwork against
the real entry API before packaging; it does not replace entry data or images.
