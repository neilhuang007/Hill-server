import { createRequire } from "node:module";
import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dependencyRoot = process.env.HILL175_BEDROCK_SMOKE_DEPS
  ?? path.join(repository, "runtime", "bedrock-protocol-smoke");
const requireDependencies = createRequire(path.join(dependencyRoot, "package.json"));
const bedrock = requireDependencies("bedrock-protocol");
const nbt = requireDependencies("prismarine-nbt");
const scenario = process.argv[2] ?? "gameplay";
const host = process.env.HILL175_BEDROCK_SMOKE_HOST ?? "127.0.0.1";
const port = Number(process.env.HILL175_BEDROCK_SMOKE_PORT ?? 19134);
const serverFolder = path.resolve(process.env.HILL175_BEDROCK_SMOKE_SERVER
  ?? path.join(repository, "runtime", "bedrock-player-20261015"));
const version = process.env.HILL175_BEDROCK_SMOKE_VERSION ?? "1.26.51";
// 26.52 is the same 2193 codec; minecraft-data names that schema 1.26.51.
const gameVersion = process.env.HILL175_BEDROCK_SMOKE_GAME_VERSION ?? "1.26.52";
const protocol = requireDependencies("minecraft-data")(`bedrock_${version}`).version.version;
const username = process.env.HILL175_BEDROCK_SMOKE_USERNAME ?? `Bed${String(Date.now()).slice(-9)}`;
const password = process.env.HILL175_BEDROCK_SMOKE_PASSWORD ?? `LocalSmoke${randomUUID()}!`;
const transcript = [];
const timings = [];
const inventories = new Map();
const forms = [];
const mapPackets = [];
const cameraPackets = [];
const floatingItems = [];
const itemNames = new Map();
const stackResponses = [];
const inventoryChanges = [];
let client;
let heartbeat;
let failure;
let hasSpawned = false;
let hasClosed = false;
let currentWindow;
let currentForm;
let windowSequence = 0;
let requestId = 1;
let tick = 0n;
let position;
let yaw = 0;
let pitch = 0;
let shouldAcknowledgeTeleport = false;

const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const cleanText = text => String(text ?? "").replace(/§[0-9a-fk-or]/gi, "");

function validateTarget() {
  if (!["127.0.0.1", "::1", "localhost"].includes(host)) {
    throw new Error("Unsigned Bedrock smoke clients may only connect to loopback.");
  }
  const file = path.join(serverFolder, "plugins", "Geyser-Spigot", "config.yml");
  const config = JSON.parse(readFileSync(file, "utf8").split("\n").slice(1).join("\n"));
  if (config.bedrock.port !== port) throw new Error("Bedrock smoke port does not match its isolated runtime.");
  if (scenario !== "gameplay") return;
  if (process.env.HILL175_BEDROCK_ISOLATED_OFFLINE !== "1"
      || config.bedrock.address !== "127.0.0.1"
      || config.advanced.bedrock["validate-bedrock-login"] !== false) {
    throw new Error("Gameplay needs the explicitly acknowledged isolated loopback bridge.");
  }
}

async function waitFor(predicate, description, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (failure) throw failure;
    const result = predicate();
    if (result) return result;
    if (hasClosed) throw new Error(`Bedrock connection closed while waiting for ${description}.`);
    await delay(50);
  }
  throw new Error(`Timed out waiting for ${description}.`);
}

async function measure(description, action) {
  const started = Date.now();
  const result = await action();
  const milliseconds = Date.now() - started;
  timings.push({ action: description, milliseconds });
  console.log(`PASS: ${description} (${milliseconds} ms)`);
  return result;
}

function itemText(item) {
  if (!item) return "";
  const tag = item.extra?.nbt?.nbt ?? item.extra?.nbt;
  const value = tag?.type ? nbt.simplify(tag) : tag;
  return cleanText(JSON.stringify(value ?? {}));
}

function itemName(item) {
  return itemNames.get(item?.network_id) ?? "";
}

function windowItems() {
  return currentWindow ? inventories.get(currentWindow.window_id) ?? [] : [];
}

function findWindowSlot(text) {
  return windowItems().findIndex(item => itemText(item).includes(text));
}

function windowSummary() {
  return windowItems().map((item, slot) => ({ slot, text: itemText(item), name: itemName(item) }))
    .filter(item => item.text !== "{}" && item.name !== "minecraft:gray_stained_glass_pane");
}

function recordPosition(packet) {
  if (packet.runtime_id != null && String(packet.runtime_id) !== String(client.entityId)) return;
  position = packet.position ?? packet.player_position;
  yaw = packet.yaw ?? yaw;
  pitch = packet.pitch ?? pitch;
  shouldAcknowledgeTeleport = true;
}

function queuePlayerAction(action) {
  client.queue("player_action", {
    runtime_entity_id: client.entityId, action,
    position: { x: 0, y: 0, z: 0 }, result_position: { x: 0, y: 0, z: 0 }, face: 0,
  });
}

function sendInput(inputMode = "touch", override = {}) {
  if (!position || !client.entityId || hasClosed) return;
  const inputData = shouldAcknowledgeTeleport ? ["handled_teleport"] : [];
  shouldAcknowledgeTeleport = false;
  client.queue("player_auth_input", {
    pitch, yaw, position, move_vector: { x: 0, z: 0 }, head_yaw: yaw,
    input_data: inputData, input_mode: inputMode, play_mode: "normal", interaction_model: "touch",
    interact_rotation: { x: pitch, z: yaw }, tick: ++tick,
    delta: { x: 0, y: 0, z: 0 }, analogue_move_vector: { x: 0, z: 0 },
    camera_orientation: { x: 0, y: 0, z: 1 }, raw_move_vector: { x: 0, z: 0 }, ...override,
  });
}

function attachClientEvents() {
  for (const event of ["connect", "network_settings", "server_to_client_handshake", "start_game", "spawn"])
    client.on(event, () => console.log(`Bedrock connection stage: ${event}`));
  client.on("error", error => { failure = error; });
  client.on("kick", packet => { failure = new Error(`Bedrock kick: ${cleanText(packet.message)}`); });
  client.on("disconnect", packet => { failure = new Error(`Bedrock disconnect: ${JSON.stringify(packet)}`); });
  client.on("close", () => { hasClosed = true; });
  client.on("spawn", () => { hasSpawned = true; });
  client.on("start_game", recordPosition);
  client.on("move_player", recordPosition);
  client.on("change_dimension", packet => { recordPosition(packet); queuePlayerAction("dimension_change_ack"); });
  client.on("item_registry", packet => packet.itemstates.forEach(item => itemNames.set(item.runtime_id, item.name)));
  client.on("text", packet => { transcript.push(cleanText(packet.message)); });
  client.on("modal_form_request", packet => {
    currentForm = { id: packet.form_id, data: JSON.parse(packet.data) };
    forms.push(currentForm);
  });
  client.on("clientbound_map_item_data", packet => mapPackets.push(packet));
  client.on("camera_instruction", packet => cameraPackets.push(packet));
  client.on("add_item_entity", packet => floatingItems.push(packet));
  client.on("container_open", packet => { currentWindow = packet; });
  client.on("container_close", packet => {
    if (packet.server) client.queue("container_close", { ...packet, server: false });
    if (currentWindow?.window_id === packet.window_id) currentWindow = null;
  });
  client.on("inventory_content", packet => { inventories.set(packet.window_id, packet.input); windowSequence++; });
  client.on("inventory_slot", packet => {
    inventoryChanges.push({ window: packet.window_id, slot: packet.slot, name: itemName(packet.item), count: packet.item?.count });
    const items = inventories.get(packet.window_id) ?? [];
    items[packet.slot] = packet.item;
    inventories.set(packet.window_id, items);
  });
  client.on("item_stack_response", packet => stackResponses.push(packet));
  heartbeat = setInterval(() => { try { sendInput(); } catch (error) { failure = error; } }, 50);
}

function command(text) {
  client.queue("command_request", {
    command: text,
    origin: { type: "player", uuid: randomUUID(), request_id: "", player_entity_id: 0n },
    internal: false, version: "latest",
  });
}

async function expectMessage(action, text, timeout = 20_000) {
  const start = transcript.length;
  await action();
  return await waitFor(() => transcript.slice(start).find(line => line.includes(text)), text, timeout);
}

async function expectWindow(action, text) {
  const sequence = windowSequence;
  const formCount = forms.length;
  await action();
  await waitFor(() => (windowSequence > sequence && findWindowSlot(text) >= 0)
    || (forms.length > formCount && currentForm?.data.type === "form"
      && cleanText(JSON.stringify(currentForm.data)).includes(text)), `menu containing ${text}`);
}

function clickSlot(slot) {
  const item = windowItems()[slot];
  if (!item?.network_id) throw new Error(`Menu slot ${slot} is empty: ${JSON.stringify(windowSummary())}`);
  client.queue("item_stack_request", { requests: [{
    request_id: requestId++, custom_names: [], cause: "chat_public",
    actions: [{ type_id: "take", legacy_type_id: 0, count: 1,
      source: { slot_type: { container_id: "container" }, slot, stack_id: item.stack_id },
      destination: { slot_type: { container_id: "cursor" }, slot: 0, stack_id: 0 },
    }],
  }] });
}

function clickText(text) {
  if (currentForm?.data.type === "form") {
    const index = currentForm.data.buttons.findIndex(button => cleanText(button.text).includes(text));
    if (index < 0) throw new Error(`Missing native button ${text}: ${JSON.stringify(currentForm.data)}`);
    const form = currentForm;
    currentForm = null;
    client.queue("modal_form_response", {
      form_id: form.id, has_response_data: true, data: JSON.stringify(index), has_cancel_reason: false,
    });
    return;
  }
  const slot = findWindowSlot(text);
  if (slot < 0) throw new Error(`Missing menu item ${text}: ${JSON.stringify(windowSummary())}`);
  clickSlot(slot);
}

function closeWindow() {
  if (currentForm) {
    client.queue("modal_form_response", { form_id: currentForm.id, has_response_data: false,
      has_cancel_reason: true, cancel_reason: "user_closed" });
    currentForm = null;
  }
  if (!currentWindow) return;
  client.queue("container_close", { window_id: currentWindow.window_id, window_type: currentWindow.window_type, server: false });
  currentWindow = null;
}

async function waitForForm(action) {
  const count = forms.length;
  await action();
  return await waitFor(() => forms.length > count && forms.at(-1), "translated Bedrock form");
}

function answerSubmissionForm(form, title, description, actionText) {
  if (form.data.type !== "custom_form") throw new Error(`Expected editable Bedrock form: ${JSON.stringify(form.data)}`);
  const response = form.data.content.map(component => {
    if (component.type === "label") return null;
    if (component.type === "input") return /description/i.test(component.text) ? description : title;
    if (component.type !== "dropdown") throw new Error(`Unexpected form component ${component.type}`);
    const index = component.options.findIndex(option => cleanText(option).includes(actionText));
    if (index < 0) throw new Error(`Missing form action ${actionText}`);
    return index;
  });
  client.queue("modal_form_response", {
    form_id: form.id, has_response_data: true, data: JSON.stringify(response), has_cancel_reason: false,
  });
  currentForm = null;
}

async function holdItem(name) {
  const items = inventories.get("inventory") ?? [];
  const slot = items.slice(0, 9).findIndex(item => itemName(item) === name || itemText(item).includes(name));
  if (slot < 0) throw new Error(`Hotbar item missing: ${name}; ${items.slice(0, 9).map(item => itemText(item)).join(" ")}`);
  client.queue("mob_equipment", { runtime_entity_id: client.entityId, item: serverboundItem(items[slot]), slot,
    selected_slot: slot, window_id: "inventory" });
  await delay(200);
  return { slot, item: serverboundItem(items[slot]) };
}

function serverboundItem(item) {
  // Serverbound descriptors may omit net IDs and client display NBT. Geyser uses
  // its authoritative inventory; clientbound net-ID encoding differs since 975.
  return { ...item, has_stack_id: false, block_runtime_id: 0,
    extra: { has_nbt: "false", can_place_on: [], can_destroy: [] } };
}

async function useItem(name, data = {}) {
  const held = await holdItem(name);
  client.queue("inventory_transaction", { transaction: {
    legacy: { legacy_request_id: 0 }, transaction_type: "item_use", actions: [],
    transaction_data: { action_type: "click_air", trigger_type: "player_input",
      block_position: { x: 0, y: 0, z: 0 }, face: 255, hotbar_slot: held.slot,
      hand: "main_hand", held_item: held.item, player_pos: position, click_pos: { x: 0, y: 0, z: 0 },
      block_runtime_id: 0, client_prediction: "success", client_cooldown_state: "off", ...data,
    },
  } });
}

async function createJourney() {
  await expectWindow(() => command("/hill175"), "Start The Journey");
  await expectWindow(() => clickText("Start The Journey"), "Create Entry");
  const before = forms.length;
  await expectMessage(() => clickText("Create Entry"), "Owner Mode");
  if (forms.slice(before).some(form => form.data.type === "custom_form"))
    throw new Error("Creating a build still interrupts arrival with a metadata form.");
  await expectWindow(() => command("/hill175"), "Continue The Journey");
  await expectWindow(() => clickText("Continue The Journey"), "Edit Details");
  const form = await waitForForm(() => clickText("Edit Details"));
  await expectWindow(() => answerSubmissionForm(form, "Bedrock Automated Build", "Saved through the Bedrock form.", "Save Details"), "Bedrock Automated Build");
  closeWindow();
}

async function cameraAndSubmission() {
  const before = floatingItems.length;
  const savedRotation = { x: pitch, z: yaw };
  await expectMessage(() => useItem("minecraft:ender_eye"), "Camera 1/3 saved");
  await waitFor(() => floatingItems.slice(before).some(packet => itemName(packet.item) === "minecraft:ender_eye"),
    "visible floating Bedrock camera item");
  await previewAndExitCamera(savedRotation);
  await expectWindow(() => command("/entry submit"), "Confirm Submission");
  await expectMessage(() => clickText("Confirm Submission"), "submitted", 120_000);
  closeWindow();
  await expectMessage(() => command("/entry unlock"), "unlocked");
}

async function previewAndExitCamera(expectedRotation) {
  const camerasBefore = cameraPackets.length;
  await expectMessage(() => command("/camera preview 1"), "Previewing camera");
  await waitFor(() => cameraPackets.slice(camerasBefore).find(packet => packet.instruction_set?.position)?.instruction_set,
    "Bedrock fixed-camera instruction");
  // Geyser first sees the entity's quantized spawn pitch and default head yaw.
  // Let the plugin's bounded startup retries (through tick 20) finish before
  // testing controller movement against the saved, fully synchronized pose.
  await delay(1200);
  const target = cameraPackets.slice(camerasBefore).findLast(packet => packet.instruction_set?.position)?.instruction_set;
  if (expectedRotation && (Math.abs(target?.rotation?.x - expectedRotation.x) > 0.01
      || Math.abs(target?.rotation?.z - expectedRotation.z) > 0.01)) {
    throw new Error(`Camera did not settle at its saved angle: ${JSON.stringify({expected: expectedRotation, actual: target?.rotation})}`);
  }
  await assertLockedCamera(target);
  await waitFor(() => (inventories.get("inventory") ?? []).some(item => itemText(item).includes("Exit Camera Preview")), "camera exit item");
  await expectMessage(() => useItem("Exit Camera Preview"), "Camera preview closed");
  await waitFor(() => cameraPackets.slice(camerasBefore).some(packet => packet.clear || packet.instruction_set?.default), "Bedrock camera reset");
}

async function assertLockedCamera(target) {
  const count = cameraPackets.length;
  sendInput("game_pad", { yaw: yaw + 35, head_yaw: yaw + 35, input_data: ["up"],
    move_vector: { x: 0, z: 1 }, position: { ...position, x: position.x + 1 } });
  await delay(150);
  const updated = await waitFor(() => cameraPackets.length > count && cameraPackets.at(-1)?.instruction_set?.position
    && cameraPackets.at(-1).instruction_set,
    "Bedrock camera pose after controller movement attempt");
  if (![target.rotation?.x, target.rotation?.z, updated.rotation?.x, updated.rotation?.z].every(Number.isFinite)) {
    throw new Error("Bedrock fixed-camera rotation was missing from its instruction.");
  }
  const delta = ["x", "y", "z"].map(axis => Math.abs(target.position[axis] - updated.position[axis]));
  if (delta.some(value => value > 0.01)) throw new Error("Controller input moved the fixed Bedrock camera.");
  if (Math.abs(target.rotation.x - updated.rotation.x) > 0.01
      || Math.abs(target.rotation.z - updated.rotation.z) > 0.01) {
    throw new Error(`Controller input rotated the fixed Bedrock camera: ${JSON.stringify({before: target.rotation, after: updated.rotation})}`);
  }
}

async function selectPlaceBuilding() {
  await expectWindow(() => command("/entry create place"), "Choose a Campus Area");
  await expectWindow(() => clickText("Choose a Single Building"), "Hill Campus Map");
  if (currentForm.data.type !== "form" || currentForm.data.buttons.length !== 37)
    throw new Error("Campus map must expose all 36 named buildings plus Back.");
  const building = cleanText(currentForm.data.buttons[0].text);
  await expectWindow(() => clickText(building), "Build Here");
  await expectMessage(() => clickText("Build Here"), "Owner Mode");
  const firstBounds = JSON.parse(readFileSync(path.join(repository, "src/main/resources/hill-buildings.yml"), "utf8")
    .match(/bounds-xz:\s*(\[[^\]]+\])/)[1]);
  const [minX, minZ, maxX, maxZ] = firstBounds;
  if (position.x < minX - 16 || position.x > maxX + 16 || position.z < minZ - 16 || position.z > maxZ + 16)
    throw new Error(`Place arrival is away from the selected building: ${JSON.stringify(position)}`);
  if (process.env.HILL175_BEDROCK_FIXTURES === "1") {
    const oldX = position.x;
    fixture("exterior-view");
    await waitFor(() => position.x > oldX + 60, "fixture arrival outside the editable building area");
    await delay(500);
    const savedRotation = { x: pitch, z: yaw };
    await expectMessage(() => useItem("minecraft:ender_eye"), "Camera 1/3 saved");
    await previewAndExitCamera(savedRotation);
  }
}

async function selectCampusArea() {
  await expectWindow(() => command("/entry delete"), "Confirm Delete");
  await expectMessage(() => clickText("Confirm Delete"), "deleted");
  await expectWindow(() => command("/entry create place"), "Choose a Campus Area");
  if (currentForm.data.buttons.length !== 9) throw new Error("All seven areas, single building and Back must be reachable.");
  await expectWindow(() => clickText("Arts Center and North Pond Shore"), "Build Here");
  await expectWindow(() => clickText("Choose Another Area"), "Choose a Campus Area");
  await expectWindow(() => clickText("Arts Center and North Pond Shore"), "Build Here");
  await expectMessage(() => clickText("Build Here"), "Owner Mode", 60000);
  await expectWindow(() => command("/hill175"), "Continue The Place");
  await expectWindow(() => clickText("Continue The Place"), "Build Boundary");
  await expectWindow(() => clickText("Build Boundary"), "Your Build Boundary");
  if (!JSON.stringify(currentForm.data).includes("520, -545")) throw new Error("Bedrock must show both exact area rectangles.");
  await expectWindow(() => clickText("Back to Build Options"), "Submit Entry");
  await expectWindow(() => clickText("Submit Entry"), "Save Camera 1");
  await expectWindow(() => clickText("Save Camera 1"), "Camera 1");
  await expectWindow(() => clickText("Back to Build Options"), "Submit Entry");
  await expectWindow(() => clickText("Submit Entry"), "Confirm Submission");
  await expectMessage(() => clickText("Confirm Submission"), "submitted", 120000);
  await expectWindow(() => command("/hill175"), "Continue The Place");
  await expectWindow(() => clickText("Continue The Place"), "Resume Editing");
  await expectMessage(() => clickText("Resume Editing"), "unlocked");
}

function fixture(action, fields = {}) {
  if (process.env.HILL175_BEDROCK_FIXTURES !== "1") {
    throw new Error("Block assertions require the disposable-server runner's console fixture channel.");
  }
  console.log(`SMOKE_FIXTURE ${JSON.stringify({ action, nickname: `.${username}`, ...fields })}`);
}

async function assertBlock(block, expected, marker) {
  await expectMessage(() => fixture("query-block", { position: block, expected, marker }), marker);
}

async function placeAndBreak() {
  await delay(400);
  fixture("give-stone");
  await waitFor(() => itemName((inventories.get("inventory") ?? [])[2]) === "minecraft:stone", "fixture stone in hotbar");
  const block = [Math.floor(position.x) + 1, 65, Math.floor(position.z) + 1];
  await assertBlock(block, "air", "BEDROCK_BEFORE_AIR");
  await useItem("minecraft:stone", { action_type: "click_block", face: 1,
    block_position: { x: block[0], y: block[1] - 1, z: block[2] },
    click_pos: { x: 0.5, y: 1, z: 0.5 } });
  await delay(300);
  await assertBlock(block, "stone", "BEDROCK_PLACED_STONE");
  sendInput("game_pad", { input_data: ["block_action"], block_action: [
    { action: "start_break", position: { x: block[0], y: block[1], z: block[2] }, face: 1 },
  ] });
  await delay(300);
  await assertBlock(block, "air", "BEDROCK_BROKEN_AIR");
}

async function gameplay() {
  validateTarget();
  connectClient();
  await measure("Bedrock UDP join and world spawn", () => waitFor(() => hasSpawned, "Bedrock spawn", 120_000));
  await delay(1500);
  await measure("registration derives the real Floodgate name", () => expectMessage(
    () => command(`/register ${password} ${password}`), "Registration complete", 30_000));
  await measure("native menu, direct build arrival, and optional details form", createJourney);
  if (process.env.HILL175_BEDROCK_FIXTURES === "1") {
    await measure("Bedrock block placement and controller-input breaking (console seeds material and asserts blocks)", placeAndBreak);
  }
  await measure("camera preview exit item and automatic submission/unlock", cameraAndSubmission);
  await measure("clickable campus map action and selected-building arrival", selectPlaceBuilding);
  await measure("campus area GUI, exact boundaries, guided camera capture and submission", selectCampusArea);
  clearInterval(heartbeat);
  await new Promise(resolve => { client.once("close", resolve); client.close(); });
  await measure("Bedrock reconnect retains both entries and form metadata", savedLogin);
  console.log(JSON.stringify({ protocol, schemaVersion: version, gameVersion,
    authentication: "isolated unsigned test only", timings }, null, 2));
}

function connectClient() {
  hasClosed = false;
  hasSpawned = false;
  failure = undefined;
  position = undefined;
  currentWindow = undefined;
  currentForm = undefined;
  inventories.clear();
  client = bedrock.createClient({ host, port, version, offline: true, username,
    skinData: { GameVersion: gameVersion },
    transport: "raknet", raknetBackend: "raknet-native", followPort: false,
    conLog: () => {}, connectTimeout: 90_000 });
  attachClientEvents();
}

async function savedLogin() {
  validateTarget();
  connectClient();
  await waitFor(() => hasSpawned, "reconnected Bedrock spawn", 60_000);
  await delay(1500);
  await expectMessage(() => command(`/login ${password}`), "Login successful", 30_000);
  await expectWindow(() => command("/hill175"), "Bedrock Automated Build");
  const ownEntries = currentForm?.data.type === "form"
    ? currentForm.data.buttons.filter(button => cleanText(button.text).startsWith("Continue "))
    : windowItems().slice(10, 12).filter(item => itemName(item) !== "minecraft:gray_stained_glass_pane");
  if (ownEntries.length !== 2) throw new Error("Linked Bedrock nickname did not retain both competition entries.");
  await expectWindow(() => clickText("Bedrock Automated Build"), "Enter Build");
  await expectMessage(() => clickText("Enter Build"), "Owner Mode");
  await previewAndExitCamera();
  await expectWindow(() => command("/hill175"), "Continue The Place");
  await expectWindow(() => clickText("Continue The Place"), "Build Boundary");
  await expectWindow(() => clickText("Build Boundary"), "Your Build Boundary");
  const boundary = JSON.stringify(currentForm.data);
  if (!boundary.includes("520, -545") || !boundary.includes("360, -400"))
    throw new Error("The saved compound area boundary did not survive reconnect or restart.");
}

async function rejectOffline() {
  validateTarget();
  const logFile = path.join(serverFolder, "logs", "latest.log");
  const previousLog = readFileSync(logFile, "utf8").length;
  let hasNegotiatedNetwork = false;
  client = bedrock.createClient({ host, port, version, offline: true, username,
    skinData: { GameVersion: gameVersion },
    transport: "raknet", raknetBackend: "raknet-native", followPort: false, conLog: () => {} });
  client.on("error", error => { failure = error; });
  client.on("network_settings", () => { hasNegotiatedNetwork = true; });
  client.on("spawn", () => { hasSpawned = true; });
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Unsigned admission did not complete.")), 20_000);
    client.once("close", () => { clearTimeout(timeout); resolve(); });
  });
  if (failure) throw failure;
  const log = readFileSync(logFile, "utf8").slice(previousLog);
  if (!hasNegotiatedNetwork || hasSpawned || !log.includes("Please log into Xbox")) {
    throw new Error("Secure bridge did not reject the unsigned Bedrock login with its Xbox requirement.");
  }
  console.log("PASS: secure bridge negotiates Bedrock protocol and rejects unsigned Xbox admission");
}

try {
  if (scenario === "reject-offline") await rejectOffline();
  else if (scenario === "gameplay") await gameplay();
  else if (scenario === "reconnect") await measure("Bedrock login and entries persist after Paper restart", savedLogin);
  else throw new Error(`Unknown scenario ${scenario}`);
  if (process.env.HILL175_BEDROCK_SMOKE_REPORT) {
    writeFileSync(process.env.HILL175_BEDROCK_SMOKE_REPORT, JSON.stringify({
      scenario, schemaVersion: version, gameVersion, protocol, authentication: "isolated unsigned test only", timings,
      cameraInstructions: cameraPackets.length,
      fixedCameraInstructions: cameraPackets.filter(packet => packet.instruction_set?.position).length,
      floatingCameraItems: floatingItems.filter(packet => itemName(packet.item) === "minecraft:ender_eye").length,
      mapPixelUpdates: mapPackets.filter(packet => packet.pixels?.length > 0).length,
    }, null, 2));
  }
} catch (error) {
  console.error(`FAIL: ${error.message}`);
  console.error(`Messages: ${transcript.slice(-25).join("\n")}`);
  if (currentWindow) console.error(`Menu: ${JSON.stringify(windowSummary())}`);
  if (currentForm) console.error(`Native form: ${JSON.stringify(currentForm.data)}`);
  console.error(`Stack responses: ${JSON.stringify(stackResponses.slice(-3))}`);
  console.error(`Hotbar: ${JSON.stringify((inventories.get("inventory") ?? []).slice(0, 9).map((item, slot) => ({
    slot, name: itemName(item), networkId: item?.network_id, count: item?.count,
  })))}`);
  console.error(`Inventory changes: ${JSON.stringify(inventoryChanges.slice(-8))}`);
  process.exitCode = 1;
} finally {
  clearInterval(heartbeat);
  client?.close();
  setTimeout(() => process.exit(process.exitCode ?? 0), 250);
}
