import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const botRoot = process.argv[2];
if (!botRoot) {
  throw new Error("Usage: node scripts/patch-smoke-bot-protocol.mjs <mineflayer-root>");
}

const protocolPath = path.join(
  path.resolve(botRoot),
  "vendor",
  "minecraft-data",
  "pc",
  "26.2",
  "protocol.json",
);
const protocol = JSON.parse(await readFile(protocolPath, "utf8"));
const types = protocol?.play?.toServer?.types;
const mappings = types?.packet?.[1]?.[0]?.type?.[1]?.mappings;
const fields = types?.packet?.[1]?.[1]?.type?.[1]?.fields;

if (!types || !mappings || !fields) {
  throw new Error("The pinned compatibility fork has an unexpected protocol-data shape.");
}

if (mappings["0x40"] === "spectate" && mappings["0x43"] === "use_item") {
  console.log("Minecraft 26.2 serverbound item packet IDs were already corrected.");
  process.exit(0);
}

if (
  mappings["0x40"] !== "test_instance_block_action"
  || mappings["0x41"] !== "block_place"
  || mappings["0x42"] !== "use_item"
  || mappings["0x43"] !== "custom_click_action"
) {
  throw new Error("Refusing to patch unrecognized Minecraft 26.2 serverbound packet IDs.");
}

// Protocol 776 retains Teleport to Entity at 0x40. The compatibility fork
// omitted it, shifting Use Item On/Use Item one ID too low and causing Paper to
// decode right-clicks as the wrong packet type.
types.packet_spectate = [
  "container",
  [{ name: "target", type: "UUID" }],
];
mappings["0x40"] = "spectate";
mappings["0x41"] = "test_instance_block_action";
mappings["0x42"] = "block_place";
mappings["0x43"] = "use_item";
mappings["0x44"] = "custom_click_action";
fields.spectate = "packet_spectate";

await writeFile(protocolPath, `${JSON.stringify(protocol, null, 2)}\n`);
console.log("Corrected Minecraft 26.2 serverbound item packet IDs.");
