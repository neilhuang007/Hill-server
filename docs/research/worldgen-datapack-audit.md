# Hill 175 survival worldgen datapack audit

Research date: 2026-08-31

Scope: the local Modrinth profile at `C:\Users\neil_\AppData\Roaming\ModrinthApp\profiles\cinematic world backup 1.0.0`, narrowed to world-generation content that can be used for a long-lived Hill 175 survival world on the repository's pinned Paper server without requiring students to install client mods.

## Summary recommendation

Use custom world generation, but only from official `datapack` distributions that explicitly list Minecraft `26.2`. Do not install Fabric/Forge/NeoForge mods on the Paper server, and do not base the public survival world on the profile's local Minecraft `1.21.11` Fabric jars.

Recommended first-pass stack for a fresh Paper `26.2` survival world:

1. `Terralith_26.2_v2.6.4.zip`
2. `terratonic-3.0.27.zip`
3. `Structory_v1.3.7.zip`
4. `Structory_Towers_v1.0.17.zip`
5. `t_and_t-datapack-26.x.zip`
6. `Incendium_Legacy_26.2_v5.5.0.zip`
7. `Nullscape_26.2_v1.2.20.zip`

The Structory filename is not a version-selection typo: official Modrinth datapack version `OIcllpSf` is release `1.3.17`, but its upstream-published file is named `Structory_v1.3.7.zip`. The manifest pins both the version ID and file hashes.

This gives students a visibly custom Overworld plus structure variety, and it also upgrades Nether/End exploration, while staying vanilla-client friendly. It avoids All-Rights-Reserved packs unless Hill explicitly accepts that provenance risk. It also avoids stacking too many competing structure packs before the first generation smoke test.

Do not combine the Terralith datapack with the ordinary Tectonic datapack. Terralith's official Modrinth page says datapack users must use Terratonic instead of Tectonic, and Terratonic's official page describes it as the Tectonic-compatible variant adjusted for Terralith biomes. Sources: [Terralith page](https://modrinth.com/datapack/terralith), [Terratonic page](https://modrinth.com/datapack/terratonic), [Tectonic page](https://modrinth.com/datapack/tectonic).

Source basis: the exact Paper runtime is pinned locally to Paper `26.2` build `119`, and Paper's official Fill API records build `119` as `STABLE`, artifact `paper-26.2-119.jar`, SHA-256 `a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629`. Sources: local `build.gradle.kts`, local `ops/install-server.sh`, and [Paper Fill API build 119](https://fill.papermc.io/v3/projects/paper/versions/26.2/builds/119).

## Local profile facts

- The Modrinth profile latest log says it loads Minecraft `1.21.11` with Fabric Loader `0.19.3`. Source: local `logs/latest.log`.
- The profile's migration report says the migrated pack target was Minecraft `1.21.11`, Fabric Loader `0.19.3`, Java `25`, and that it booted with `160` jars and no duplicate mod ids during that migration pass. Source: local `MIGRATION_REPORT.md`.
- Current filesystem inventory found `202` active mod jars, `16` disabled mod jars, `2` active datapacks, `2` disabled datapacks, `556` config files, `81` resource-pack files, and `18` shaderpack files. Source: local filesystem inventory.
- Current active profile datapacks are `JJThunder_To_The_Max_1.21.11_v0.9.0.zip` and `Terraphilic v1.2.0.zip`. These are not the exact files to use for Paper `26.2`; the official `26.2` files are listed below where available. Source: local `datapacks` folder and Modrinth version APIs.
- The profile's resource packs and shaderpacks are client-side visual assets. They are not survival worldgen inputs and should not be required for student participation.
- The profile's config folder contains many stale configs for removed/disabled Fabric mods. Do not copy Fabric config files into a Paper datapack survival world; only copy final, version-pinned datapack zips into the new world's `datapacks/` directory.

## Compatibility definition

For this audit, a worldgen candidate is considered suitable for the public survival world only if:

- it has an official Modrinth version whose `loaders` includes `datapack`;
- that version's `game_versions` includes `26.2`;
- it does not require a Fabric/Forge/NeoForge server;
- it does not require students to install a client mod;
- the license/provenance is acceptable for a Hill school server and the zip is downloaded from the official project/CDN URL.

This does not replace runtime testing. The final stack still needs a Paper `26.2` fresh-world smoke test: server boot, `/datapack list`, chunk generation, structure location, vanilla-client join, and log review.

Rights interpretation used here:

- Installing an official datapack from Modrinth's own project/version download on Hill's own server is treated as ordinary use when the project is published as a datapack and marks itself server-side. Modrinth's environment guidance says server-only content should be compatible with vanilla clients when installed only on the server. Source: [Modrinth environment metadata article](https://modrinth.com/news/article/new-environments/).
- This is not a redistribution grant. For `LicenseRef-All-Rights-Reserved`, Modrinth's licensing guide says use is limited to what the owner specifies, and Modrinth's modpack permissions guide says ARR content cannot be redistributed without explicit author permission. Sources: [Modrinth licensing guide](https://modrinth.com/news/article/licensing-guide/), [Modrinth modpack permissions guide](https://support.modrinth.com/en/articles/8797527-obtaining-modpack-permissions).
- Practical consequence: MIT/CC/Stardust-licensed files can be tracked or mirrored only if their license conditions are satisfied; ARR files should not be committed to GitHub, mirrored, or redistributed as part of a Hill datapack bundle unless the project page grants that permission or Hill obtains permission.

## Recommended 26.2 datapacks

| Role | Project | Official 26.2 datapack | Project ID | Version ID | SHA-512 | License/provenance | Source |
|---|---|---:|---:|---:|---|---|---|
| Overworld terrain/biomes | Terralith | `Terralith_26.2_v2.6.4.zip` | `8oi3bsk5` | `CzijfXJQ` | `f5283548323149ecd3f218b8efbe03c1c582df3f40b6bb3b095ba9e4cac0c87108b98adabd6ebd3a8037ec239773a253f75b8bee7db52e6f5663bf9dc63c2ea3` | Stardust Labs License; server use permitted, standalone redistribution prohibited | [project](https://api.modrinth.com/v2/project/8oi3bsk5), [version](https://api.modrinth.com/v2/version/CzijfXJQ), [license](https://raw.githubusercontent.com/Stardust-Labs-MC/license/main/license.txt) |
| Terralith-compatible terrain shaping | Terratonic | `terratonic-3.0.27.zip` | `3L2L6sWL` | `cT2AsHrJ` | `86342db362b88d6ca8a1e7fdbd7ced1dbd522720ec6dc50d21c568d714896123e3f59995c3f4b6608e595a8eeeec8636b8b39524540f06e23a4e9070cdf71312` | MIT | [project](https://api.modrinth.com/v2/project/3L2L6sWL), [version](https://api.modrinth.com/v2/version/cT2AsHrJ) |
| Overworld structures | Structory | `Structory_v1.3.7.zip` | `aKCwCJlY` | `OIcllpSf` | `ac7d415d2000b531b82f3dc15eec598e13756f8c7d4de02bda02d40c85ef86e45da0f39a64500ad76952b20333e0d34765c99e3e23c172f089385bd206843fa6` | Stardust Labs License; server use permitted, standalone redistribution prohibited | [project](https://api.modrinth.com/v2/project/aKCwCJlY), [version](https://api.modrinth.com/v2/version/OIcllpSf), [license](https://raw.githubusercontent.com/Stardust-Labs-MC/license/main/license.txt) |
| Towers/landmarks | Structory: Towers | `Structory_Towers_v1.0.17.zip` | `j3FONRYr` | `uxUF2h4B` | `1c300616f0f5c7dd919f94d510773e450194ecfeeb8e1a41fb0cb3d3b88adb8ee51bb01b545756524d2c6d1098382b926bc500becec30979cc6be267003477fe` | Stardust Labs License; server use permitted, standalone redistribution prohibited | [project](https://api.modrinth.com/v2/project/j3FONRYr), [version](https://api.modrinth.com/v2/version/uxUF2h4B), [license](https://raw.githubusercontent.com/Stardust-Labs-MC/license/main/license.txt) |
| Villages/settlements | Towns and Towers | `t_and_t-datapack-26.x.zip` | `DjLobEOy` | `E39wx2BN` | `bd139bb99284f30a6e924d5a8f72a08ebf8b86c928ab2cd57fdf715c335c13dc87cf5e62b668674010dede5aeb6a4b9d3615247d920da21bd5449f1dbd7a25e5` | CC-BY-NC-SA-4.0; requires attribution/share-alike awareness, noncommercial use only | [project](https://api.modrinth.com/v2/project/DjLobEOy), [version](https://api.modrinth.com/v2/version/E39wx2BN) |
| Nether generation | Incendium Legacy | `Incendium_Legacy_26.2_v5.5.0.zip` | `ZVzW5oNS` | `znNBZB6M` | `cfb6a4310ab3895a0a4a35f1b668545a45316b2bc5159d4859797b0a559de839c163a3bbab038bdac0c4f81005a8b542866d6db7aeb72144a36f6ffaf534daf1` | Stardust Labs License; server use permitted, standalone redistribution prohibited | [project](https://api.modrinth.com/v2/project/ZVzW5oNS), [version](https://api.modrinth.com/v2/version/znNBZB6M), [license](https://raw.githubusercontent.com/Stardust-Labs-MC/license/main/license.txt) |
| End generation | Nullscape | `Nullscape_26.2_v1.2.20.zip` | `LPjGiSO4` | `prWWpjSv` | `3ace54c904600e449305547064b2e0087eb05827c06f406490e7fa18dfbe6ef42c357078d5e6ad9cc32129de30bc0de9e89dd1c7ff966f1812b1393581d82294` | Stardust Labs License; server use permitted, standalone redistribution prohibited | [project](https://api.modrinth.com/v2/project/LPjGiSO4), [version](https://api.modrinth.com/v2/version/prWWpjSv), [license](https://raw.githubusercontent.com/Stardust-Labs-MC/license/main/license.txt) |

Stardust Labs' license states that its datapacks/mods may be used on public or private Minecraft servers and that standalone redistribution is forbidden. It also says public modpack redistribution requires credit and links. Source: [Stardust Labs license](https://raw.githubusercontent.com/Stardust-Labs-MC/license/main/license.txt).

## Other official 26.2 datapacks found

These are official `26.2` datapack distributions, but I would not put them in the first survival-world cut. The issue is not vanilla-client compatibility; the issue is world feel, structure density, custom gameplay complexity, and redistribution posture.

If the first test world feels too sparse, choose exactly one of these additions and smoke test again:

- Prefer `Explorify v1.6.5.dp.zip` for a low-risk vanilla-feeling structure increase.
- Prefer `Dungeons and Taverns v5.3.1.zip` only if Hill wants custom enchantment loot and accepts that the datapack also works as an optional resource pack for custom key textures.
- Do not add Geophilic/JJThunder on top of Terralith/Terratonic. Their own pages describe terrain-generation compatibility constraints that make them better as alternative terrain systems, not add-ons to the recommended stack.

| Project | Official 26.2 datapack | Project ID | Version ID | SHA-512 | Rights/use note | Recommendation |
|---|---|---:|---:|---|---|---|
| Tectonic | `tectonic-datapack-3.0.25.zip` | `lWDHr9jE` | `CmzMQNDL` | `7b3c5dee391337b21bdfee5362f4a986417b4fffd6aa617dddaf3444b729b326e3651e7cd87cd7d68d39c301d28767648753784cd50f0a94eda904f85cd6d5bd` | MIT | Valid standalone terrain datapack, but do not pair its ordinary datapack with the Terralith datapack; use Terratonic for that combination. Sources: [project](https://api.modrinth.com/v2/project/lWDHr9jE), [version](https://api.modrinth.com/v2/version/CmzMQNDL), [Terralith page](https://modrinth.com/datapack/terralith). |
| Explorify | `Explorify v1.6.5.dp.zip` | `HSfsxuTo` | `BKKKBD2V` | `9ca01672759e9a84a14e3424f1a779bde3fdaad3bf77b853961e0a5902c4bbee0ab970adf5638e1e6934e0a70d926221caa8d89f29e6f88d56b73aad9ae4fb6b` | ARR; ordinary official-download server use only, no redistribution without permission | Best optional extra structure pack after first smoke; official description is vanilla-friendly. Sources: [project](https://api.modrinth.com/v2/project/HSfsxuTo), [version](https://api.modrinth.com/v2/version/BKKKBD2V), [project page](https://modrinth.com/datapack/explorify). |
| Dungeons and Taverns | `Dungeons and Taverns v5.3.1.zip` | `tpehi7ww` | `QaLOMwH2` | `c391c9d84b8921b58aedd4dfbbf54b6a767150ab485076cf25d70f07c6af915a7c0a9d631e6aeea07ae506924d0ce70dd7952d54114a9be594d10838e9bf4edf` | ARR; ordinary official-download server use only, no redistribution without permission | Good gameplay candidate, but not first pass: adds many structures, custom enchantment loot, and optional resource-pack textures. Sources: [project](https://api.modrinth.com/v2/project/tpehi7ww), [version](https://api.modrinth.com/v2/version/QaLOMwH2), [project page](https://modrinth.com/datapack/dungeons-and-taverns). |
| DnT Ancient City Overhaul | `DnT Ancient City Overhaul v3.4.zip` | `DNuNq5bb` | `CaqYtto5` | `37738531da3eea99b6b5cb11bfbfc5ecf80da38ed6c6e78dbba5bcb5bc760a1a6e072b45835a730ef292e46777f68836fa3cd39e00b3d553a9d689872b133b88` | ARR; ordinary official-download server use only, no redistribution without permission | Add only if D&T is selected and Ancient Cities need redesign. Sources: [project](https://api.modrinth.com/v2/project/DNuNq5bb), [version](https://api.modrinth.com/v2/version/CaqYtto5). |
| DnT Desert Temple Overhaul | `DnT Desert Temple Overhaul v2.1.zip` | `7JTDDmRT` | `tOWwOzy4` | `4f9af3b9d28873cfc1be0956601300761960da2a7b0eb99cf986ab4472e771ec66812186fb60fadd6b9b6ed4a800d3de0075df3372b4542efeba0e6e59109d82` | ARR; ordinary official-download server use only, no redistribution without permission | Add only after D&T core is proven stable. Sources: [project](https://api.modrinth.com/v2/project/7JTDDmRT), [version](https://api.modrinth.com/v2/version/tOWwOzy4). |
| DnT Jungle Temple Overhaul | `DnT Jungle Temple Overhaul v2.1.zip` | `oHjYCS0f` | `ljTHNYiU` | `33458705a6a03d0231d9a549427dcb94cce0d7ab92a78c82c0617914a6a268ff4d02b0dc18acebdbc305454ed18089b445c4a7794c321d834e9c30306b670942` | ARR; ordinary official-download server use only, no redistribution without permission | Add only after D&T core is proven stable. Sources: [project](https://api.modrinth.com/v2/project/oHjYCS0f), [version](https://api.modrinth.com/v2/version/ljTHNYiU). |
| DnT Nether Fortress Overhaul | `DnT Nether Fortress Overhaul v3.1.zip` | `8Dbnvm77` | `3u94EXVg` | `4553734b3eac9d4da2d14e1b99c291543c487909bfe018cdb2ac0a4c8db5dceae2b08158a2a2823ff5398fec244baeb2b66e8b0968ec8e7496a26a05ff2b9b45` | ARR; ordinary official-download server use only, no redistribution without permission | Avoid initially because Incendium already changes Nether generation. Sources: [project](https://api.modrinth.com/v2/project/8Dbnvm77), [version](https://api.modrinth.com/v2/version/3u94EXVg). |
| DnT Ocean Monument Overhaul | `DnT Ocean Monument Overhaul v2.2.1.zip` | `z6GJ3ycD` | `IX2JzD1k` | `cfce53f5a794ceed533dfdb018172620765abef7ad229bbb425decdf89a425a2f8400a4bc53aaf936bbee29e400dddb34366ad77c2d76d4d12001cd8ec8886fd` | ARR; ordinary official-download server use only, no redistribution without permission | Add only if ocean monument progression needs redesign. Sources: [project](https://api.modrinth.com/v2/project/z6GJ3ycD), [version](https://api.modrinth.com/v2/version/IX2JzD1k). |
| DnT Pillager Outpost Overhaul | `DnT Pillager Outpost Overhaul v3.3.zip` | `QIt10I7z` | `uAHOlrKb` | `bf3ae77f56642a82c217e417cdd6f6ead41ef13ac7da3cc3e70467833490f485cb6c7619c43db9714d00c70a200cdbde5e841b372d93d781e41c6021376fcae0` | ARR; ordinary official-download server use only, no redistribution without permission | Add only after D&T core is proven stable. Sources: [project](https://api.modrinth.com/v2/project/QIt10I7z), [version](https://api.modrinth.com/v2/version/uAHOlrKb). |
| DnT Stronghold Overhaul | `DnT Stronghold Overhaul v2.4.0.zip` | `rYocd2LE` | `L1ylllq1` | `98717889e12744c0625b4996c5471ad7938068b48749ef45aa80e82ed06512282386906b67a491ba144e6f692bdbf42a140dc85a90a4c7c201c0155a358724b4` | ARR; ordinary official-download server use only, no redistribution without permission | Avoid initially; changing strongholds increases launch risk for a student survival world. Sources: [project](https://api.modrinth.com/v2/project/rYocd2LE), [version](https://api.modrinth.com/v2/version/L1ylllq1). |
| DnT Swamp Hut Overhaul | `DnT Swamp Hut Overhaul v2.3.zip` | `nWSeFpQt` | `t2gIpNuq` | `f11571ed0c8c1b4b4f91a090f723a7bf02489ed8c56bde3c5f44714d2874b1bf2b7b80ebeaa68848041f90398087dd9be9d6bb9e220d1fcf7cd7276418a80f8f` | ARR; ordinary official-download server use only, no redistribution without permission | Add only after D&T core is proven stable. Sources: [project](https://api.modrinth.com/v2/project/nWSeFpQt), [version](https://api.modrinth.com/v2/version/t2gIpNuq). |
| DnT Woodland Mansion Overhaul | `DnT Woodland Mansion Overhual v2.1.zip` | `3GfxWFCy` | `sIwi7RFy` | `9f9fd2e7f4fd18f4dbab9c3391e708ce93a244f52142eebd7b238d2592dc044a2c8ce63b61086a22ed163661871bbbbdbdd9ddc0d9c7103cca25ff421ba734bb` | ARR; ordinary official-download server use only, no redistribution without permission | Add only after D&T core is proven stable. Filename spelling is exactly what Modrinth reports. Sources: [project](https://api.modrinth.com/v2/project/3GfxWFCy), [version](https://api.modrinth.com/v2/version/sIwi7RFy). |
| ATi Structures | `ATi Structures V1.4.5.zip` | `bii8qPSt` | `8r8yVrH2` | `40850f5cd853950df50934f8026de56c7943164ea73fdf518bd955e114b66937ffc4e8c89c37751874999e9e23f22fc5c9678f1c92d8a865af43591d03eb34e8` | ARR, but project page says modpack inclusion is allowed; still avoid mirroring without recording that permission | Hold for later. Project page says it uses vanilla features/no custom blocks, but also says the current version includes custom items and modified mobs; that is too much extra gameplay variance for the first worldgen cut. Sources: [project](https://api.modrinth.com/v2/project/bii8qPSt), [version](https://api.modrinth.com/v2/version/8r8yVrH2), [project page](https://modrinth.com/datapack/ati-structures-fabricforge). |
| Geophilic | `Geophilic v3.6.dp.zip` | `hl5OLM95` | `6uLCMJCR` | `504e3f1a6820b17a06fc4e7d2a318b36a66f3b910bef8cc3bfda470fe7250b65dfbd9922ef345d1af07846af14f4ae573a2e8b6e8466892f6959641d25a54ce5` | ARR; ordinary official-download server use only, no redistribution without permission | Alternative to Terralith, not an add-on here. Its page routes Terralith compatibility through Terraphilic, and no official `26.2` Terraphilic datapack was found. Sources: [project](https://api.modrinth.com/v2/project/hl5OLM95), [version](https://api.modrinth.com/v2/version/6uLCMJCR), [project page](https://modrinth.com/datapack/geophilic). |
| JJThunder To The Max | `JJThunder_To_The_Max_26.2_v0.9.0.zip` | `1NnAVIR5` | `IgqEqiO9` | `d1c838acb00ef071b3efa966330b0e001de61c963ba6d86a801574572824c314adea996b6447feb18ef991910960b28b55106504ece4a372f87ae2b0dd87576d` | ARR; ordinary official-download server use only, no redistribution without permission | Alternative terrain identity, not an add-on. Its page says it has no direct compatibility with other worldgen mods/datapacks and calls out Terralith/WWOO/BOP/BWG issues. Sources: [project](https://api.modrinth.com/v2/project/1NnAVIR5), [version](https://api.modrinth.com/v2/version/IgqEqiO9), [project page](https://modrinth.com/datapack/jjthunder-to-the-max). |

## Current profile worldgen projects rejected from the selected Paper 26.2 stack

These are rejected either because no official `26.2` datapack exists, because the project is a Fabric/Forge/NeoForge mod only for this target, because it requires a modded client, or because it conflicts with the recommended Terralith/Terratonic terrain identity.

| Local/profile project | Local file observed | Official 26.2 datapack alternative | Conclusion |
|---|---|---|---|
| Tectonic | `tectonic-3.0.19-fabric-1.21.11.jar` | Yes: `tectonic-datapack-3.0.25.zip`, version `CmzMQNDL`, SHA-512 `7b3c5dee391337b21bdfee5362f4a986417b4fffd6aa617dddaf3444b729b326e3651e7cd87cd7d68d39c301d28767648753784cd50f0a94eda904f85cd6d5bd`. | Valid only as standalone terrain shaping or with the Terralith mod; reject from the selected stack because Terralith datapack users must use Terratonic instead. Sources: [project](https://api.modrinth.com/v2/project/lWDHr9jE), [version](https://api.modrinth.com/v2/version/CmzMQNDL), [Terralith page](https://modrinth.com/datapack/terralith). |
| Geophilic | `Geophilic v3.6.mod.jar` | Yes: `Geophilic v3.6.dp.zip`, version `6uLCMJCR`, SHA-512 `504e3f1a6820b17a06fc4e7d2a318b36a66f3b910bef8cc3bfda470fe7250b65dfbd9922ef345d1af07846af14f4ae573a2e8b6e8466892f6959641d25a54ce5`. | Valid 26.2 datapack, but reject from the selected Terralith stack. Geophilic's page points Terralith users to Terraphilic; Terraphilic has no official 26.2 datapack. Sources: [Geophilic project](https://api.modrinth.com/v2/project/hl5OLM95), [Geophilic version](https://api.modrinth.com/v2/version/6uLCMJCR), [Terraphilic project](https://api.modrinth.com/v2/project/8T4mO5eV), [Geophilic page](https://modrinth.com/datapack/geophilic). |
| JJThunder To The Max | `JJThunder_To_The_Max_1.21.11_v0.9.0.zip` | Yes: `JJThunder_To_The_Max_26.2_v0.9.0.zip`, version `IgqEqiO9`, SHA-512 `d1c838acb00ef071b3efa966330b0e001de61c963ba6d86a801574572824c314adea996b6447feb18ef991910960b28b55106504ece4a372f87ae2b0dd87576d`. | Valid 26.2 datapack, but reject from the selected stack. Its page says it has no direct compatibility with other worldgen packs and calls out Terralith/WWOO/BOP/BWG issues. Source: [project](https://api.modrinth.com/v2/project/1NnAVIR5), [version](https://api.modrinth.com/v2/version/IgqEqiO9), [project page](https://modrinth.com/datapack/jjthunder-to-the-max). |
| Dungeons and Taverns plus overhaul add-ons | `dungeons-and-taverns-v5.1.0.jar`; active Fabric jars for Ancient City, Desert Temple, Jungle Temple, Nether Fortress, Ocean Monument, Pillager Outpost, Stronghold, Swamp Hut, Woodland Mansion overhauls | Yes; exact 26.2 datapack versions are listed in the optional table above. | Not rejected for compatibility, but rejected from the first-pass stack to avoid high structure density and custom enchantment/resource-pack complexity before launch smoke testing. Sources: [D&T project](https://api.modrinth.com/v2/project/tpehi7ww), [D&T version](https://api.modrinth.com/v2/version/QaLOMwH2), [D&T page](https://modrinth.com/datapack/dungeons-and-taverns). |
| ATi Structures | `ATi Structures V1.4.6.jar` | Yes: `ATi Structures V1.4.5.zip`, version `8r8yVrH2`, SHA-512 `40850f5cd853950df50934f8026de56c7943164ea73fdf518bd955e114b66937ffc4e8c89c37751874999e9e23f22fc5c9678f1c92d8a865af43591d03eb34e8`. | Not rejected for compatibility, but reject from first pass because its page says the current version includes custom items and modified mobs. Source: [project](https://api.modrinth.com/v2/project/bii8qPSt), [version](https://api.modrinth.com/v2/version/8r8yVrH2), [project page](https://modrinth.com/datapack/ati-structures-fabricforge). |
| Explorify | `Explorify v1.6.5.mod.jar` | Yes: `Explorify v1.6.5.dp.zip`, version `BKKKBD2V`, SHA-512 `9ca01672759e9a84a14e3424f1a779bde3fdaad3bf77b853961e0a5902c4bbee0ab970adf5638e1e6934e0a70d926221caa8d89f29e6f88d56b73aad9ae4fb6b`. | Good optional add-on, but reject from first pass to keep structure density measurable. Source: [project](https://api.modrinth.com/v2/project/HSfsxuTo), [version](https://api.modrinth.com/v2/version/BKKKBD2V), [project page](https://modrinth.com/datapack/explorify). |
| ChoiceTheorem's Overhauled Village | `[fabric]ctov-1.21.11-3.6.2a.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Local file is a Fabric jar. Source: [project](https://api.modrinth.com/v2/project/fgmhI8kH). |
| Blooming Biosphere | `blooming-biosphere-v1.1.12.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Local file is a Fabric/Forge/NeoForge/Quilt jar distribution, not a Paper datapack. Source: [project](https://api.modrinth.com/v2/project/Ds9FyUc7). |
| Formations | `formations-1.0.4-fabric-mc1.21.11.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Fabric structure-library jar. Source: [project](https://api.modrinth.com/v2/project/tPe4xnPd). |
| Formations Nether | `formationsnether-1.0.5a-mc1.21+.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Mod/plugin loader distribution only in the researched result. Source: [project](https://api.modrinth.com/v2/project/cGvQGRls). |
| Formations Overworld | `formationsoverworld-1.0.5a-mc1.21+.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Mod/plugin loader distribution only in the researched result. Source: [project](https://api.modrinth.com/v2/project/KX1XC0Oo). |
| Moog's End Structures | `MoogsEndStructures-1.21-2.0.3.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Local profile also includes Fabric-side Moog's Structure Lib. Sources: [MES project](https://api.modrinth.com/v2/project/r4PuRGfV), [Moog's Structure Lib project](https://api.modrinth.com/v2/project/1oUDhxuy). |
| Philip's Ruins | `PhilipsRuins-1.21.11-1.0-Fabric.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject. Modrinth marks the project client-side and server-side required, which conflicts with the no-client-mod requirement. Source: [project](https://api.modrinth.com/v2/project/KdJhOYVV). |
| Repurposed Structures - Fabric | `repurposed_structures-7.6.2+1.21.11-fabric.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper. Source: [project](https://api.modrinth.com/v2/project/muf0XoRe). |
| Revamped Shipwrecks | `Revamped Shipwrecks 1.1.0.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper 26.2, even though older datapack/mod-wrapper releases exist. Source: [project](https://api.modrinth.com/v2/project/ZnZ8uqXN). |
| Terraphilic | `Terraphilic v1.2.0.zip` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper 26.2. This is the Terralith/Geophilic compatibility path, but the active local zip targets older game versions. Source: [project](https://api.modrinth.com/v2/project/8T4mO5eV). |
| Tidal Towns | `tidal-towns-1.3.4.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper 26.2. Local file is a datapack-like mod wrapper, but no exact 26.2 datapack was found. Source: [project](https://api.modrinth.com/v2/project/EEIwvQVo). |
| William Wythers' Overhauled Overworld | `wwoo-fabric-2.6.4.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper 26.2. Fabric/NeoForge worldgen mod only in researched results. Source: [project](https://api.modrinth.com/v2/project/II7t6llZ). |
| Exosphere Worldgen / Exosphere Worldgen Refabricated | `exosphere generation 2.1.zip.disabled` | No official Paper-compatible `26.2` datapack found. Modrinth search found `Exosphere Worldgen Refabricated` with a `26.2` Fabric server jar, not a datapack. | Reject for Paper despite matching Minecraft version. Sources: [search result project](https://api.modrinth.com/v2/project/Bok4jiCt), [26.2 Fabric version](https://api.modrinth.com/v2/version/lecwGVx4). |
| JJThunder Hell Is Fire | `JJThunder_Hell_Is_Fire_1.21.0-1.21.1_v0.1.0.zip.disabled` | No official `26.2` datapack found in Modrinth project versions. | Reject for Paper 26.2. Source: [project](https://api.modrinth.com/v2/project/Q97CFELK). |
| Biomes O' Plenty | `BiomesOPlenty-fabric-1.21.11-21.11.0.32.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject. Modrinth marks the project client-side and server-side required, so students would need a modded client. Source: [project](https://api.modrinth.com/v2/project/HXF82T3G). |
| Oh The Biomes We've Gone | `Oh-The-Biomes-Weve-Gone-Fabric-4.4.0.jar` | No official `26.2` datapack found in Modrinth project versions. | Reject. Modrinth marks the project client-side and server-side required, so students would need a modded client. Source: [project](https://api.modrinth.com/v2/project/NTi7d3Xc). |
| Farmer's Delight / Friends&Foes / More Villagers / Serene Seasons / More Armor Trims and similar content mods | Multiple active Fabric jars in the profile | No Paper datapack substitution accepted here. | Reject because these add modded registries, items, blocks, entities, mobs, recipes, or client assets and are not acceptable for vanilla-client Paper survival. Sources: active local jar inventory plus each project's Modrinth `client_side` and `server_side` fields. |

## Inventory notes

The active profile is primarily a cinematic client pack, not a server pack. Modrinth project compatibility buckets from the active mod jars were:

| Modrinth client/server side fields | Active jar count | Server conclusion |
|---|---:|---|
| `required / unsupported` | 77 | Client-only; never install on Paper. |
| `required / required` | 33 | Modded-client content or shared libraries; reject for vanilla-client survival. |
| `required / optional` | 9 | Client-required; reject for vanilla-client survival. |
| `optional / required` | 29 | Potential server-side/Fabric-server candidates, but only usable on Paper if an official datapack distribution exists. |
| `unsupported / required` | 19 | Server-side Fabric candidates, but not Paper unless an official datapack distribution exists. |
| `optional / optional` | 32 | Libraries/tools/optional utilities; not Paper worldgen inputs. |
| unresolved or unknown | 3 | Do not use without separate authoritative sourcing. |

One active local jar, `physics-mod-pro-v183m-fabric-mc-1.21.11.jar`, did not resolve through Modrinth's hash endpoint. It is client visual/physics content and is irrelevant to server-side worldgen.

Disabled local datapacks were `exosphere generation 2.1.zip.disabled` and `JJThunder_Hell_Is_Fire_1.21.0-1.21.1_v0.1.0.zip.disabled`; neither should be used for the Paper `26.2` survival world without fresh primary-source research and runtime testing.

## Smoke-test checklist for implementation

1. Download only the exact official zip files from the Modrinth CDN URLs in the version API records.
2. Store the zips outside Git, with project URL, version ID, filename, license, SHA-512, download URL, acquisition date, and attribution notes.
3. Create a brand-new survival world; do not retrofit these datapacks into an existing production world.
4. Put the chosen zips in the new world's `datapacks/` folder before first boot.
5. Start the pinned Paper `26.2` build `119` runtime and verify `/datapack list`.
6. Join with an unmodified vanilla `26.2` client or the existing smoke-bot path and confirm login succeeds without client mods.
7. Generate representative Overworld, Nether, and End chunks; inspect logs for datapack parse errors, registry failures, malformed JSON, structure-set warnings, and watchdog stalls.
8. Use `/locate structure` for at least one structure family from each enabled structure pack.
9. If generation is slow, pre-generate the world border before students join rather than changing datapacks after launch.

## Decision record

The profile supports the user's direction to use custom worldgen, but it also proves why the server must not simply copy the cinematic profile. The public survival world should be a fresh Paper `26.2` world generated from official datapack zips only. Fabric client visual mods, shaders, resource packs, and modded content jars stay out of the student-required path.
