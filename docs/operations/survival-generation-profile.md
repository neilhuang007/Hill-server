# Survival generation: inspected Modrinth profile

This is an inventory and staging recommendation, **not an installed modpack or a
successful vanilla-client join test**. No profile JARs or existing worlds were
changed. See [separate survival](separate-survival.md) for `/survival`, Java-only
routing, Bedrock fallback and destination admission requirements.

## Decision

Do not copy this whole profile onto either server. The campus runs **Paper 26.2**,
which cannot load Fabric mods. The profile's code mods largely target **1.21.11**,
but its bundled datapacks span several incompatible format ranges. A Fabric
`environment: "*"` means the mod can load on both physical sides; it does **not**
prove that unmodified clients can join, that a resource pack is unnecessary, or
that the JAR supports every Minecraft version permitted by a loose dependency.

The immediately available Paper baseline is the seven checksum-pinned datapacks
in [`server-assets/survival-worldgen-manifest.tsv`](../../server-assets/survival-worldgen-manifest.tsv):
Terralith 2.6.4, Terratonic 3.0.27, Structory 1.3.17, Structory: Towers 1.0.17,
Towns and Towers 26.1-datapack, Incendium Legacy 5.5.0 and Nullscape 1.2.20.
The manifest targets 26.2 and declares optional clients/required server. This is
not a claim that every profile feature has been reproduced. Use the existing
installer only against the chosen stopped runtime, **before generating fresh
survival worlds**; do not regenerate or replace player worlds to add packs.

For more of the profile, build a **separate Fabric server on one deliberately
chosen version**, with only server-side generators and their dependencies.
Keeping the Java destination on 26.2 aligns with the campus client's protocol;
that requires acquiring 26.2 builds rather than copying 1.21.11 code JARs. A
1.21.11 destination instead needs a separately validated protocol/version plan:
`Player.transfer` does not convert client protocols. No Fabric requirement may
be imposed on students, and no required resource pack should be configured.

## Evidence and scope

Source inspected:
`C:/Users/neil_/AppData/Roaming/ModrinthApp/profiles/cinematic world backup 1.0.0/mods`.
The tables below report actual `fabric.mod.json`, `pack.mcmeta`, entrypoints and
archive data/assets, not just filenames or the historic `server_mods.txt`.
Modrinth project metadata was also checked for the linked projects. Project-wide
support does not establish support for this exact local release or combined set.
Datapack-defined biomes/enchantments are not automatically client-required mod
registries; conversely, an absence of block textures alone is not proof of
vanilla compatibility.

## Server-only generation candidates

These are candidates for an isolated fresh-world build, **not permission to mix
all versions below**. `unsupported` in Modrinth's client field means clients do
not install that project, not that vanilla clients are unsupported.

| Observed local file / metadata | Classification and required action |
| --- | --- |
| `Terralith_1.21.11_v2.6.1_Fabric.jar`: id `terralith`, version 2.6.1; Fabric loader >=0.18, Lithostitched >=1.6.0; pack format exactly 94; Java entrypoint/mixin | [Upstream](https://modrinth.com/project/terralith): client optional/server required. Good vanilla-client terrain/biome candidate. Use the correct Fabric build and Lithostitched, or the pinned Paper datapack; do not treat this code JAR as a plain datapack. |
| `tectonic-3.0.19-fabric-1.21.11.jar`: id `tectonic`, version 3.0.19; loader >=0.18, Lithostitched >=1.4.11; version-specific `tectonic_1.21.11.mixins.json` | [Upstream](https://modrinth.com/project/tectonic): client optional/server required. Pair with the intended Terralith integration, not an arbitrary second terrain override. Paper baseline uses Terratonic instead. |
| `Geophilic v3.7.mod.jar`: id `geophilic`, version 3.7; Fabric API, Minecraft >=1.20; no Java entrypoint; pack formats 15–121 with explicit 1.21.11/26.2 overlays | [Upstream](https://modrinth.com/project/geophilic): client optional/server required. Data-driven decoration candidate. Check overlap with Terralith, Blooming Biosphere and WWOO instead of assuming their biome overrides all combine. |
| `Explorify v1.6.5.mod.jar`: id `explorify`, version 1.6.5; Fabric API, Minecraft >=1.20; no Java entrypoint; pack formats 15–512 with overlays | [Upstream](https://modrinth.com/project/explorify): client optional/server required. Strong structure candidate; obtain the official target-version datapack for Paper rather than installing the Fabric wrapper there. |
| `[fabric]ctov-1.21.11-3.6.2a.jar`: id `ctov`, version 3.6.2a; Fabric, Minecraft >=1.21, Lithostitched >=1.6.0; code entrypoint/mixins; embedded pack 18–48 | [Upstream](https://modrinth.com/project/ct-overhaul-village): client unsupported/server required. Candidate on Fabric, but the embedded old pack declaration is not evidence that extracted data works on Paper 26.2. Check village competition with Towns and Towers/Luki's. |
| `formations-1.0.4-fabric-mc1.21.11.jar`: id `formations`, version 1.0.4; Minecraft >=1.21.11 <1.22, loader >=0.18.0, Fabric >=0.138.4, Java >=21 | [Upstream library](https://modrinth.com/project/formations): client unsupported/server required. Required by the following two structure mods; includes Java/mixins and cannot be replaced by copying data alone. |
| `formationsoverworld-1.0.5c-mc1.21+.jar` / `formationsnether-1.0.5b-mc1.21+.jar`: ids `formationsoverworld` / `formationsnether`; versions 1.0.5+c / 1.0.5+b; Minecraft >=1.21, Formations >=1.0.0 | [Overworld](https://modrinth.com/project/formations-overworld) and [Nether](https://modrinth.com/project/formations-nether): client unsupported/server required. Include with a matching Formations build; their broad version ranges do not override the library's tighter constraint. |
| `repurposed_structures-7.6.2+1.21.11-fabric.jar`: matching internal version; Minecraft >=1.21.11, loader >=0.18.2, Java >=21, Fabric API, MidnightLib >=1.5.7 | [Upstream](https://modrinth.com/project/repurposed-structures-fabric): client unsupported/server required. Strong Fabric structure candidate; acquire a build for the selected runtime. |
| `wwoo-fabric-2.6.4.jar`: id `wwoo`, version 2.6.4; loader >=0.17.3, Fabric, Minecraft >=1.21.11, CristelLib >=3.1.0; Java entrypoint | [Upstream](https://modrinth.com/project/wwoo): client optional/server required. Alternative/compatibility-tested terrain-biome candidate, not automatically additive to Terralith. |
| `blooming-biosphere-v1.1.12.jar`: id `mr_blooming_biosphere`, version 1.1.12; Fabric resource loader; no Java entrypoint; pack min 71 with 1.21.9/1.21.11 overlays | [Upstream](https://modrinth.com/project/blooming-biosphere): client optional/server required. Candidate biome decoration pack; broad self-declared format maximum is not runtime validation. |
| `tidal-towns-2.0.jar`: id `mr_tidal_towns`, version 2.0; resource-loader-only wrapper; pack declarations disagree (`supported_formats` ends at 81, `max_format` 121) | [Upstream](https://modrinth.com/project/tidal-towns): client optional/server required. Candidate ocean villages, but select an official version and validate the contradictory pack metadata first. |
| `lukis-grand-capitals-1.1.3.jar`: id `mr_lukis_grandcapitals`, version 1.1.3; resource-loader-only wrapper; supported pack formats 14–100 | [Upstream](https://modrinth.com/project/lukis-grand-capitals): client optional/server required. Candidate for a matching older runtime, **not this local artifact on 26.2** (format 107.1). Check overlap with CTOV/Towns and Towers. |

## Data-driven candidates needing version/alignment checks

| Actual local evidence | Disposition |
| --- | --- |
| `Incendium_26.1_v5.4.12.jar`: internal 5.4.12, Minecraft >=1.21.11; no Java entrypoints; formats 94.1–101.1 with 26.1 overlay | Vanilla-style server datapack candidate, but local declared range excludes 26.2. Use the pinned 26.2 Incendium Legacy release for Paper. |
| `Nullscape_1.21.x_v1.2.17.jar`: **internal version 1.2.16**, Minecraft >=1.21.11; no Java entrypoints; format exactly 94.1 | Filename is not authoritative. Select a correctly pinned target-version release; Paper baseline uses 1.2.20 for 26.2. |
| `Structory_26.2_v1.3.7.jar`: **internal version 1.3.17**; `Structory_Towers_26.2_v1.0.17.jar`: internal 1.0.17; both Minecraft >=1.21, formats 48–107.1; no Java entrypoints | Broad data-driven candidates; filename/version anomaly matches why the manifest pins upstream version IDs and checksums. Prefer existing official datapack artifacts on Paper. |
| `t_and_t-fabric-neoforge-1.13.9.jar`: id `t_and_t`, internal 1.13.9; Minecraft >=1.21.11, Fabric API, CristelLib >=3.1.0; no `pack.mcmeta` at archive root | Candidate on matched Fabric with library. Not a drop-in Paper datapack; use pinned official Towns and Towers datapack there. |
| `MoogsEndStructures-universal-1.21-2.1.1.jar`: id `mes`, internal 2.1.1; resource loader **and `moogs_structures`** required; formats 48–121; no Java entrypoint | Promising data-driven End structures, but this is not a dependency-free pack. Resolve exact upstream version support and test alongside Nullscape. Local library below is strictly 1.21.11. No claim of vanilla join verification. |
| `ATi Structures V1.4.7.jar`: **internal version 1.4.5**, id `mr_ati_structuresfabricforge`; resource-loader-only; pack format 15 | Older/ambiguous artifact. Obtain a version explicitly supporting the selected Minecraft release; don't infer compatibility from renamed file. |
| `Revamped Shipwrecks 1.1.0.jar`: id `revamped_shipwrecks`, version 1.1.0; resource-loader-only; pack format 10 | Old pack declaration; require updated official release before inclusion. |
| `dungeons-and-taverns-v5.1.0.jar`: internal `1-v5.1.0`; resource-loader-only; `nova_structures` data, including datapack enchantments; pack exactly 88.0 | Main pack is not declared for either 1.21.11 format 94.1 or 26.2 format 107.1. Obtain matching release, do not edit metadata to force-load. |
| Dungeons and Taverns desert/jungle temple 2.1, fortress 3.1, outpost 3.3 and swamp hut 2.3 | Each local artifact declares exactly 88.0. Same exclusion pending aligned releases. |
| Dungeons and Taverns ancient city 3.2.3, ocean monument 2.2 and stronghold 2.4.0 | Each declares 94.1. Stronghold's own pack description additionally says **“not recomended for servers”**; leave that component out pending upstream clarification. |
| `dungeons-and-taverns-woodland-mansion-overhaul-2.1.jar` | Declares exactly 101.1, unlike the other D&T artifacts. Do not combine these local downloads as a coherent versioned set. Check whether full D&T plus separate overhauls intentionally duplicate/override structures. |

## Exclude from the no-client-install selection

- **Biomes O' Plenty** `21.11.0.32` (`minecraft: 1.21.11`) and **Oh The Biomes
  We've Gone** `4.4.0`: both contain extensive non-vanilla blockstates/assets and
  custom content. Their dependencies are not a mechanism for mapping that content
  to vanilla clients. Do not install these, their Farmer's Delight cutting addon,
  or assume a resource pack alone fixes the protocol/registry requirements.
- **PhilipsRuins-1.21.11-1.0-Fabric.jar**: internal version says `1.21.11`, exact
  Minecraft `~1.21.11`; [upstream](https://modrinth.com/project/philips-ruins)
  explicitly declares **client required/server required**. Exclude even though
  it is a structure mod. Its metadata also contains a literal control character;
  a lenient JSON inspection is not evidence that a loader accepts it.
- **StreamsReflowing 2.13.7**: exact Minecraft 1.21.11, main/client entrypoints and
  a custom `streamsreflowing` blockstate. Exclude pending explicit upstream proof
  of vanilla-client support; it is not just a vanilla river datapack.
- **Oh The Trees You'll Grow 9.1.0** is a code/mixin tree-generation library used
  by excluded BWG, not a proven independent vanilla-world preset. Do not include
  it merely because it generates trees.
- Custom-content gameplay mods (Farmer's Delight, Friends & Foes, More Villagers,
  Lootr, decorative blocks, etc.), shaders, sound/particle/UI mods and client
  optimizers are not server-only worldgen inputs for this request.
- Disabled `Terra`, `expanded_ecosphere` and `roadweaver` JARs are not the active
  profile selection; leave disabled. Do not revive them without a separate
  version/compatibility decision.

## Libraries: install only for selected generators

Observed relevant versions: Fabric API `0.141.6+1.21.11`; Lithostitched `1.7.2`
(loader >=0.18, Java entrypoints/mixins); CristelLib `3.1.7` (loader >=0.18.5,
Fabric API >=0.141.4+1.21.11, Minecraft >=1.21.11); MidnightLib
`1.9.3+1.21.11`; Formations `1.0.4`; Moog's Structure Lib
`3.3.1+fabric` (**Minecraft exactly 1.21.11**). Biolith `3.5.3` explicitly requires
Minecraft `>=1.21.11 <26`, so is not a 26.2 library. TerraBlender `21.11.0.0`,
GlitchCore `21.11.0.4`, CorgiLib `9.0.0.0` and GeckoLib `5.4.5` must not be copied
just to satisfy the excluded biome/content mods. Resolve only the dependency
closure of generators actually chosen for the target runtime.

## Safe next step

1. Keep the existing seven-pack Paper baseline available. Choose either that
   baseline or a separately maintained, version-aligned Fabric destination.
2. For Fabric, begin with Terralith + Tectonic + the matching Lithostitched and
   Fabric API; then add aligned Explorify, CTOV, Formations Overworld/Nether and
   Repurposed Structures with their libraries. These have explicit upstream
   no-required-client classification. Add compatible End/Nether packs separately.
3. Resolve and checksum exact target-version artifacts. Select coherent versions
   for D&T/Moog/ATi/shipwrecks instead of copying this mixed directory. Choose or
   explicitly merge conflicting biome/village overhauls; “server-only” does not
   mean all packs can safely be enabled together.
4. Generate **disposable new worlds** and join with the exact supported vanilla
   Java client, no mods, resource packs disabled. Exercise all dimensions, new
   structures, loot, save/restart and return travel. Record any registry/network
   errors and generation failures. This runtime join is still outstanding.
5. Only then provision the separate protected survival runtime and enable the
   existing `/survival` transfer route. Preserve original worlds/profile and keep
   Bedrock on its configured local/vanilla fallback.

Inspection used `uv run --python 3.13 python` with the standard-library ZIP/JSON
readers; no bare Windows `python` command, mod execution or live-server changes
were needed.
