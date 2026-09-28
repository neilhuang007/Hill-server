import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const botRoot = process.argv[2];
if (!botRoot) {
  throw new Error("Usage: node ops/patch-smoke-bot-protocol.mjs <mineflayer-root>");
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
const customClickFields = protocol?.types?.packet_common_custom_click_action?.[1];

if (!types || !mappings || !fields || !customClickFields) {
  throw new Error("The pinned compatibility fork has an unexpected protocol-data shape.");
}

const packetIdsCorrect = mappings["0x40"] === "spectate" && mappings["0x43"] === "use_item";
const packetIdsNeedCorrection =
  mappings["0x40"] === "test_instance_block_action"
  && mappings["0x41"] === "block_place"
  && mappings["0x42"] === "use_item"
  && mappings["0x43"] === "custom_click_action";
const customClickPayload = customClickFields.find((field) => field.name === "nbt");
const customClickLengthPrefixCorrect = customClickPayload?.type?.[0] === "buffer"
  && customClickPayload.type[1]?.countType === "varint";

if (packetIdsCorrect && customClickLengthPrefixCorrect) {
  console.log("Minecraft 26.2 serverbound item packet IDs were already corrected.");
  process.exit(0);
}

if (!packetIdsCorrect && !packetIdsNeedCorrection) {
  throw new Error("Refusing to patch unrecognized Minecraft 26.2 serverbound packet IDs.");
}

// Protocol 776 retains Teleport to Entity at 0x40. The compatibility fork
// omitted it, shifting Use Item On/Use Item one ID too low and causing Paper to
// decode right-clicks as the wrong packet type.
if (packetIdsNeedCorrection) {
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
}

// The 26.2 server wraps the optional custom-click NBT in a VarInt length
// prefix (ByteBufCodecs.lengthPrefixed). minecraft-data 3.113.0 omitted that
// wrapper, so otherwise-valid dialog responses are rejected by Paper.
customClickPayload.type = ["buffer", { countType: "varint" }];

await writeFile(protocolPath, `${JSON.stringify(protocol, null, 2)}\n`);
console.log("Corrected Minecraft 26.2 serverbound item packet IDs.");
