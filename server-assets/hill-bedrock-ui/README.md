# Hill campus Bedrock UI

Build from the repository root with `uv run --script ops/package-bedrock-ui.py`.
The generated pack, coordinate mapping and authoring preview go to `build/bedrock-ui/`.
PNG textures and the `.mcpack` are generated files; they are not checked into Git.

Install `hill-campus-ui.mcpack` in the local server's `plugins/Geyser-Spigot/packs/`
directory, restart Geyser, and reconnect the Bedrock client. Geyser offers the pack
during login. `force-resource-packs: true` in Geyser's config requires acceptance;
leave it `false` to allow the ordinary named-button form when a player declines.
The server's building catalog and the pack's catalog must be identical. Rebuild
after changing `hill-buildings.yml`, and bump both manifest versions before
distributing a changed pack to clients that have cached an earlier version.

Only a SimpleForm with the exact title `Hill Campus Map` selects this layout.
Other SimpleForms still instantiate `server_form.long_form`; CustomForms retain
`server_form.custom_form`. Escape, controller Back, and the visible X close the
form through the vanilla `button.menu_exit` action. Every pin and named button
uses the original `button.form_button_click`, `form_buttons` collection and
`collection_index`. The final index is the Back button. Buttons are sorted by
`map-number`, then `name`, exactly as in `BuildingCatalog`.
Pin hover and controller focus show the full building name using the vanilla
button hover state; screen-reader headers also use the full name.

The chart uses the measured bounds and names in `src/main/resources/hill-buildings.yml`,
the same input as `CampusChartMapRenderer`. The palette follows that renderer.
Crowded pins are separated with leader lines to their measured footprint centers.
The athletics inset has its own labeled extent. The source metadata retains
draft/approximate labels. This is a schematic location map, not a claim that the
campus exterior is complete. The PNG preview checks authoring layout; native
Bedrock touch/controller behavior must still be smoke tested in the client.

Primary API/layout references:

- [Mojang vanilla server forms](https://github.com/Mojang/bedrock-samples/blob/main/resource_pack/ui/server_form.json)
- [Mojang common button controls](https://github.com/Mojang/bedrock-samples/blob/main/resource_pack/ui/ui_common.json)
- [Mojang static collection indexes](https://github.com/Mojang/bedrock-samples/blob/main/resource_pack/ui/store_common.json)
- [Floodgate public forms API](https://github.com/GeyserMC/Floodgate/blob/master/api/src/main/java/org/geysermc/floodgate/api/FloodgateApi.java)
- [Cumulus public form builders](https://github.com/GeyserMC/Cumulus/tree/master/src/main/java/org/geysermc/cumulus/form)
- [Geyser resource packs](https://geysermc.org/wiki/geyser/packs/)
