# Voxel Earth plan for The Hill School

Prepared on 2026-08-25.

## Recommendation

Use Voxel Earth's **Single Scene** mode for a tight, high-detail hero view of the main Hill School building first. Do not begin with the whole 200+ acre campus: the browser client automatically adds more voxels as the capture grows, so combining a very large radius, low SSE, and high voxel density can become expensive quickly. The browser is best treated as an interactive voxel preview rather than a cinematic offline renderer. ([Voxel Earth beta](https://beta.voxelearth.org/), [Voxel Earth code page](https://voxelearth.org/code/), [The Hill School at a glance](https://www.thehill.org/about-us/hill-at-a-glance), [The Hill School campus map](https://www.thehill.org/about-us/people-of-the-hill/contact-us/campus-map))

### Best first-pass settings

| Control | Start here | Maximum-detail trial |
| --- | ---: | ---: |
| Coordinates | `40.24541,-75.63427` | same |
| Radius | `120-180 m` | `80-120 m` |
| Screen Space Error (SSE) | `4` | `2` |
| Voxel Density | `256` (**Ultra**) | custom `384`, then `512` |
| Rotation (Y) | `0deg` | test small increments only if walls look jagged |
| Voxels | on | on |
| Minecraft textures | off for the most faithful color render | on only for a Minecraft look |
| Debug Tiles | off | off |

The coordinate is the mapped centroid of the building/address at 860 Beech Street; the school confirms that as its main-campus address. ([The Hill School - Contact Us](https://www.thehill.org/about-us/people-of-the-hill/contact-us), [OpenStreetMap-derived location listing](https://mapcarta.com/22732996))

## Exact browser workflow

1. Open [beta.voxelearth.org](https://beta.voxelearth.org/) in a desktop Chromium-family browser and accept the Google Maps Platform usage notice.
2. Open the model/mode selector at the upper left and choose **Single Scene**.
3. Paste `40.24541,-75.63427` into **Select Location**. Coordinates are safer than relying on the place search to disambiguate "The Hill School."
4. Set **Radius** to `150 m` and **SSE** to `4` for the first fetch.
5. Open **+ Options**, turn **Voxels** on, leave **Minecraft textures** off, and keep **Debug imagery/tiles** off.
6. Set **Voxel Density** to **Ultra (256)** and click **Fetch Tiles**.
7. Wait for both tile loading and voxelization to finish. The log reports the computed resolution and approximate metres per voxel.
8. If the result is stable, lower SSE to `2`, refetch, then try custom density `384` and finally `512`. Change one quality control at a time so it is clear which setting caused a slowdown or failure.
9. Compose a three-quarter aerial view: orbit until the main roofline and quad read clearly, then zoom close enough that the building fills the frame without clipping.
10. For a still image, capture the browser viewport at the highest display/window resolution available. Voxel Earth exposes GLB and Minecraft-structure exports, but no dedicated PNG/JPEG render control. Keep Google's logo and data attribution visible and uncropped. ([Voxel Earth beta](https://beta.voxelearth.org/), [Google Map Tiles API attribution policy](https://developers.google.com/maps/documentation/tile/policies))

## Why these settings work

### SSE controls source-tile detail

In Single Scene traversal, Voxel Earth refines a tile while its geometric error is greater than the target SSE. A smaller SSE therefore requests finer source tiles and more work. The current UI range is `2-64`, with `2` at the high-detail end. ([SingleSceneFetcher source](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/SingleSceneFetcher.js#L221-L251), [Single Scene controls](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/index.html#L749-L828))

### Density controls voxel size per source tile

The presets are `32 / 64 / 128 / 256`; the custom control is clamped by the current JavaScript to `8-1024`. For Single Scene, the client estimates a typical loaded-tile diagonal, scales the combined grid resolution by the number of tiles across the scene, and logs approximately `tile diagonal / density setting` metres per voxel. This means a larger radius adds total voxels rather than simply making each voxel proportionally coarser. ([Single Scene density calculation](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/map.js#L906-L963), [Single Scene resolution clamp](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/map.js#L235-L242))

Use **Ultra (256)** as the reliable quality baseline. Treat `384-512` as an experimental high-detail range for a small radius. Although the code permits `1024`, that is a stress-test setting, not a sensible first attempt.

### Higher voxel density cannot invent missing geometry

Voxel Earth converts the loaded Photorealistic 3D Tiles mesh into voxels. If Google's source capture has blurred facades, merged trees, weak roof edges, or no detailed coverage at this location, raising density only samples those limitations more finely. Inspect the original tile view before deciding whether the bottleneck is source quality or voxel quality. ([Voxel Earth web-client overview](https://github.com/voxelearth/web-client), [Google Photorealistic 3D Tiles overview](https://developers.google.com/maps/documentation/tile/3d-tiles-overview))

## Larger Hill School views

The official campus map shows the academic core west of Beech Street and a long athletics area extending east toward Jackson Street, so the address point is not the visual centre of the whole campus. ([The Hill School campus map](https://www.thehill.org/about-us/people-of-the-hill/contact-us/campus-map))

| Goal | Centre | Radius | SSE | Density | Expected result |
| --- | --- | ---: | ---: | ---: | --- |
| Main building hero | `40.24541,-75.63427` | `120-180 m` | `2-4` | `256-512` | Best architectural detail |
| Western academic core | `40.2450,-75.6325` (approx.) | `250-350 m` | `2-4` | `256`, then `384` | Several recognizable buildings |
| Whole campus overview | `40.2458,-75.6280` (approx.) | `750-900 m` | `8-12` | `128`, then `256` | Campus massing and fields, not facade detail |

For an ultra-detailed **whole campus**, make multiple small, consistently framed passes rather than one maximum-radius scene. Only stitch or redistribute those passes if the source-data license allows derivative work; this is not safe to assume for Google Photorealistic 3D Tiles.

## Current implementation quirks

- The radius slider displays `20 m-3 km`, while the fetcher enforces an effective minimum of `50 m`. ([Single Scene controls](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/index.html#L733-L753), [SingleSceneFetcher source](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/SingleSceneFetcher.js#L133-L156))
- The options panel describes **3D SAT** as the most accurate method and **2.5D Scan Converter** as the faster default. However, in the current source the Single Scene rebuild does not forward the selected method to `voxelizeModel`, whose default is `2.5d-scan`. For this mode, SSE and density are the controls that clearly affect the result; changing the method selector may not. ([Voxelization method UI](https://beta.voxelearth.org/), [Single Scene voxelizer call](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/map.js#L954-L963), [`voxelizeModel` default](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/voxelize-model.js#L740-L772))
- If the tab freezes or reloads, halve density first; if tile fetching is the bottleneck, raise SSE or reduce radius. Do not maximize all three controls simultaneously.

## API key and cost notes

The current web client has an educational fallback tile endpoint when no key is entered, so try the preview without a key first. If tile requests fail, an owner-supplied key requires a billing-enabled Google Cloud project with the **Map Tiles API** enabled. Restrict the key to the Map Tiles API, set a conservative quota/budget, and remember that Google bills/counts Photorealistic 3D tile requests. The beta UI says a supplied key is stored locally in that browser. ([Voxel Earth client configuration](https://github.com/voxelearth/web-client/blob/83c5a6418d17889ad82f03dcb3518034c337f9dd/src/config.js), [Google Map Tiles setup](https://developers.google.com/maps/documentation/tile/get-api-key), [Google usage and billing](https://developers.google.com/maps/documentation/tile/usage-and-billing), [Google API security guidance](https://developers.google.com/maps/api-security-best-practices))

## Licensing/export boundary

This is the most important caveat:

- Voxel Earth's notice calls the site an educational/experimental preview and warns against prohibited caching, redistribution, and derivative uses of Google data.
- The export controls remain disabled until the user confirms both that the scene contains **no Google Photorealistic 3D Tiles or derivatives** and that they hold the required rights. A Hill School scene fetched from Google's Photorealistic 3D Tiles does not satisfy that first confirmation, so do not check it merely to unlock GLB, NBT, schem, schematic, or mcfunction export. ([Voxel Earth beta notice and export gate](https://beta.voxelearth.org/))
- Google's terms prohibit exporting/scraping Maps content for use outside the service and creating content based on Maps content except where Google expressly permits it. Its tile policy also restricts caching, extraction, machine analysis, and offline use, while requiring on-screen logo and data attribution. ([Google Maps Platform Terms, sections 3.2.3(a-c)](https://cloud.google.com/maps-platform/terms), [Google Map Tiles API policies](https://developers.google.com/maps/documentation/tile/policies))

For private evaluation, keep the result in the live viewer. For a publishable, editable, commercial, or Minecraft-distributable asset, use photogrammetry/mesh data that The Hill School owns or has licensed for derivatives, then run that rights-cleared GLB through the local Voxel Earth voxelization tools. The project documents a standalone GLB-to-voxel CPU path. ([Voxel Earth monorepo - CPU voxelization](https://github.com/ryanhlewis/VoxelEarth#3-cpu-voxelization--java-cpu-voxelizer))

This repo now includes `scripts/voxelearth_glb_to_structure.py` for that rights-cleared GLB case. It keeps VoxelEarth-compatible `blocks`/`xyzi` JSON output, adds glTF node-transform traversal, skips primitives without `POSITION` data, and can emit the `structure.nbt` format consumed by the Hill server. It is independent local code; the inspected VoxelEarth clones are kept only under ignored `runtime/tools/`.

Google's general Geo Guidelines allow certain static Google Maps/Earth screenshots when the stated use and attribution rules are followed, but a voxelized view may be considered significantly altered or derivative. Do not assume that the ordinary screenshot permission resolves that issue for publication or promotion. ([Google Geo Guidelines](https://about.google/brand-resource-center/products-and-services/geo-guidelines/))

## Primary sources

- [Voxel Earth beta](https://beta.voxelearth.org/)
- [Voxel Earth official site](https://voxelearth.org/)
- [Voxel Earth code page](https://voxelearth.org/code/)
- [Voxel Earth web-client source](https://github.com/voxelearth/web-client)
- [Voxel Earth monorepo](https://github.com/ryanhlewis/VoxelEarth)
- [Google Map Tiles API policies](https://developers.google.com/maps/documentation/tile/policies)
- [Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms)
- [The Hill School contact page](https://www.thehill.org/about-us/people-of-the-hill/contact-us)
- [The Hill School at a glance](https://www.thehill.org/about-us/hill-at-a-glance)
- [The Hill School campus map](https://www.thehill.org/about-us/people-of-the-hill/contact-us/campus-map)
