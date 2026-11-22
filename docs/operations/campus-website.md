# Campus website

The local website brings the campus tour and world download together at `http://127.0.0.1:8788`. Students can explore the 3D campus without joining Minecraft. The download opens as a separate Java Edition world. The [student access guide](student-access.md) explains those choices alongside joining the shared server.

The homepage now keeps the campus artwork and three actions: Explore campus, Download map and Get server IP. The explanatory sections and automatic welcome guide are removed. Original Minecraft compass, map and ender pearl items identify the actions; a trial key appears in the download popup. Get server IP opens a popup with copy buttons for the placeholder addresses `java.thehill.org` and `bedrock.thehill.org`, labeled as preview addresses. These values do not claim live DNS or server availability. The popup opens only on request, closes with Escape or its close button, and returns focus to its opening button. Its compact Copy controls use the same Stoneborn sprites as the main actions, with borders at their native size.

The server popup includes short Java and Bedrock joining guides. The four example images are unchanged screenshots from Minecraft's official joining guide, stored in `runtime/campus-site/assets/join-*.jpg`. Their source URLs are recorded in `runtime/campus-site/join-guide-sources.json`. They are example interfaces, not captures from Neil's current clients.

Downloads require the organizer's password. The browser submits it to the server for each download, including when visitors follow the archive URL directly. A direct GET or HEAD request redirects to the password form. Missing or invalid password configuration disables downloads. The tour remains public.

Generate a password locally with `uv run --python 3.13 python ops/set-campus-download-password.py --generate`. It prints the password once and stores only a salted PBKDF2 verifier in the ignored `runtime/campus-site/download-password.properties`. Run without `--generate` to choose a password through a hidden prompt. Use `--site <campus directory>` for another installation. Changes take effect immediately. The service allows 30 password checks per minute across all visitors, including behind a proxy, and returns a retry message once that limit is reached. Public hosting must use the existing Cloudflare and HTTPS requirements.

The homepage uses the existing Stoneborn artwork and Minecraft font. Normal buttons retain the original 20/4/20/4 source pixel borders at twice their size. Hover, focus and pressed buttons use the highlighted sprite with 29/6/29/6 borders. Both retain the filled center, with accessible text drawn above it. Picture frames use the original demonstration window, with fixed corners and central ornaments at twice their native size. Only its plain edge strips stretch. Dividers also preserve their corner caps and central ornament. Asset provenance and preparation are described in [the gallery guide](build-gallery.md).

## Start the local preview

From the checkout root:

```powershell
./ops/campus-site.ps1 -Action Start
./ops/campus-site.ps1 -Action Status
./ops/campus-site.ps1 -Action Stop
```

The launcher compiles the application with the existing JDK 25 installation and starts a loopback HTTP service without starting Minecraft. It uses `runtime/gallery-assets` for Stoneborn and `runtime/campus-site` for the map, photographs and download. The optional `-Port` argument chooses another local port. This workflow does not publish the site or change the remote server.

## Prepare the campus

```powershell
uv run --python 3.13 --with nbtlib python ops/prepare-campus-site.py --render
```

Preparation reads the explicit selection in `server-assets/shared-campus-source.json`, currently V60. It copies terrain into an isolated snapshot, removes the saved player record and packages the world with its asphalt resource pack. It never edits the selected source or existing player saves. The public manifest contains the revision, edition, size and download checksum. Source paths remain in a private provenance file.

The exported palette omits some vanilla default properties. Preparation makes those defaults explicit in the copied world so BlueMap can render grass blocks and other affected models. The map uses daylight ambient lighting because this construction export has incomplete light data. Its initial camera is above the central campus. The tour has no school header or upper control strip.

Rendering uses the locally installed BlueMap 5.23 CLI, Minecraft 1.21.11 rendering assets and the campus asphalt pack. Download instructions recommend Java Edition 26.2, matching the current server runtime. A full render can take several minutes. `campus.json` marks the tour ready only after rendering succeeds. To prepare a different selected revision, use a separate `--output` directory so the previous export remains available.

The complete map geometry is generated before visitors arrive. Public map files support browser caching and ETag revalidation; configuration is revalidated each time, while live data and protected downloads remain uncached. The landing page quietly warms at most 8 MiB of useful opening view assets after loading, then continues up to 32 MiB when Explore campus is hovered or focused. Data saving and slow connections disable this optional work. It stops on navigation. Run `uv run --python 3.13 python ops/prepare-campus-site.py --preload-only` to refresh the loading metadata without rendering or changing a world. Interactive 3D drawing still happens in the visitor's browser.

The tour opens behind a campus photograph and loading indicator. Visitors begin in first person at X 124, Y 105, Z 178, with a detail distance of 256 blocks. Switching to a wider map view expands the detail distance to at least 512 blocks. The server prepares `map/ready.json` with the exact bounds of each nonempty rendered mesh. The viewer loads the camera's visible area first, followed by a small surrounding margin, and requests new areas as the camera moves. It keeps the cover until the visible detailed meshes are loaded and drawn. A failed tile or graphics error offers retry while keeping the partial view hidden. Close perspective views omit the coarse heightmap that makes distant buildings look like cliffs; the overview remains available when zoomed out or viewed flat. This reduces initial model data and processing while preserving the original geometry.

## Artwork

The compact anniversary title was built in Blockbench with Ewan Howell's Minecraft Title Generator. Its blue textured letters have a gold border, with two rockets behind them. The rockets use Minecraft's original `firework_rocket` item texture and its generated item silhouette. The editable project is `runtime/title-blockbench/hill-175-anniversary.bbmodel`; its transparent export is `runtime/title-blockbench/hill-175-blockbench.png`. The website uses that export at `runtime/campus-site/assets/hill-175-gold.png`.

The header uses the unmodified crest and wordmark supplied by [The Hill School website](https://www.thehill.org/), displayed on light gray so its navy lettering remains legible. The title uses the same navy (`#001C48`) and gold (`#FFC72C`) with blue texture highlights. The official artwork stays in runtime storage alongside its source URLs in `school-artwork.json`.

The landing page uses the five Minecraft screenshots Neil supplied on November 11, 2026. The second photo, showing the courtyard from above, opens first; the thumbnail selector switches between all five views without automatic rotation. The original JPEG pixels are preserved as `campus-photo-01.jpg` through `campus-photo-05.jpg` under `runtime/campus-site/assets`. Source filenames and checksums are recorded privately in `runtime/campus-site/campus-photos.json`. Earlier rendered PNGs remain preserved. This photo update does not change the separate browser tour or world download selection. The models, third party textures, world archive and rendered tiles stay in ignored runtime storage.

## Routes and boundaries

The root serves the landing page, `/visit/` contains the tour, `/map/` serves BlueMap, and `/download/` provides the password form. A valid password POST to `/downloads/hill-campus.zip` serves the prepared archive. The former competition gallery remains at `/gallery`, with its existing entry and private preview routes.

The HTTP service serves named artwork, the prepared archive and supported map files. It rejects traversal and does not expose the snapshot, source paths, private provenance or executable map scripts. BlueMap's local language formatter requires dynamic script compilation, so that permission is scoped to `/map/`. Gallery and authentication pages retain their separate policies. If the website is later hosted through Paper, its prepared campus directory belongs under the configured gallery asset directory as `campus-site`.
