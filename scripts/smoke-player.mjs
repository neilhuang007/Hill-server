import { createRequire } from "node:module";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const dependencyRoot = process.env.HILL175_SMOKE_DEPS
  ?? path.resolve(scriptDirectory, "..", "runtime", "smoke-bot", "mineflayer");
const requireFromDependencies = createRequire(path.join(dependencyRoot, "package.json"));
const mineflayer = existsSync(path.join(dependencyRoot, "index.js"))
  ? requireFromDependencies(path.join(dependencyRoot, "index.js"))
  : requireFromDependencies("mineflayer");
const nbt = requireFromDependencies("prismarine-nbt");
const { Vec3 } = requireFromDependencies("vec3");

const host = process.env.HILL175_SMOKE_HOST ?? "127.0.0.1";
const port = Number(process.env.HILL175_SMOKE_PORT ?? "25566");
const scenario = process.argv[2] ?? "lobby-return";
const username = `Smoke${String(Date.now()).slice(-9)}`;
const password = "SmokeTest123!";
const transcript = [];
const currentWorldNames = new WeakMap();

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function fail(message) {
  console.error(`FAIL: ${message}`);
  if (transcript.length > 0) {
    console.error("Transcript:");
    for (const line of transcript) console.error(`  ${line}`);
  }
  process.exitCode = 1;
}

async function waitFor(predicate, description, timeoutMilliseconds = 10_000) {
  const deadline = Date.now() + timeoutMilliseconds;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

async function waitForWindow(action, description, timeoutMilliseconds = 10_000) {
  return await waitForBotWindow(bot, action, description, timeoutMilliseconds);
}

async function waitForBotWindow(targetBot, action, description, timeoutMilliseconds = 10_000) {
  return await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      targetBot.removeListener("windowOpen", onWindowOpen);
      reject(new Error(`Timed out waiting for ${description}`));
    }, timeoutMilliseconds);
    const onWindowOpen = (window) => {
      clearTimeout(timeout);
      resolve(window);
    };
    targetBot.once("windowOpen", onWindowOpen);
    action();
  });
}

async function expectSingleWindow(action, description, timeoutMilliseconds = 10_000) {
  const opened = [];
  const onWindowOpen = (window) => opened.push(window);
  bot.on("windowOpen", onWindowOpen);
  try {
    await action();
    await waitFor(() => opened.length > 0, description, timeoutMilliseconds);
    await delay(750);
  } finally {
    bot.removeListener("windowOpen", onWindowOpen);
  }
  if (opened.length !== 1) {
    throw new Error(`${description} opened ${opened.length} inventory windows instead of exactly one`);
  }
  return opened[0];
}

async function waitForPacket(packetName, action, description, timeoutMilliseconds = 10_000) {
  return await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      bot._client.removeListener(packetName, onPacket);
      reject(new Error(`Timed out waiting for ${description}`));
    }, timeoutMilliseconds);
    const onPacket = (packet) => {
      clearTimeout(timeout);
      resolve(packet);
    };
    bot._client.once(packetName, onPacket);
    action();
  });
}

function windowTitle(window) {
  if (typeof window.title === "string") return window.title;
  if (window.title?.text) return window.title.text;
  return JSON.stringify(window.title);
}

function topInventorySummary(window) {
  return window.slots
    .slice(0, window.inventoryStart)
    .map((item, slot) => item ? `${slot}:${item.name}` : null)
    .filter(Boolean)
    .join(", ");
}

function componentText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function angleDistance(left, right) {
  const fullTurn = Math.PI * 2;
  const difference = Math.abs(left - right) % fullTurn;
  return Math.min(difference, fullTurn - difference);
}

function itemUiText(item) {
  if (!item) return "";
  return [item.customName, ...(item.customLore ?? [])].map(componentText).join("\n");
}

function hotbarSummary() {
  return bot.inventory.slots
    .slice(36, 45)
    .map((item, slot) => item ? `${slot}:${item.name}:${itemUiText(item)}` : `${slot}:empty`)
    .join(", ");
}

function hasHotbarItem(name, text) {
  return bot.inventory.slots
    .slice(36, 45)
    .some((item) => item?.name === name && (!text || itemUiText(item).includes(text)));
}

async function holdHotbarItem(name) {
  await delay(500);
  const hotbar = bot.inventory.slots.slice(36, 45);
  console.log(`Hotbar: ${hotbar.map((item, slot) => item ? `${slot}:${item.name}` : `${slot}:empty`).join(", ")}`);
  const slot = hotbar.findIndex((item) => item?.name === name);
  if (slot < 0) {
    throw new Error(`Expected ${name} in the authenticated hotbar`);
  }
  console.log(`Selected item components: ${JSON.stringify(hotbar[slot].components ?? [])}`);
  bot.setQuickBarSlot(slot);
  bot._client.write("held_item_slot", { slotId: slot });
  await delay(150);
  return slot;
}

async function categoryNpcs() {
  const expectedEquipment = new Map([
    ["HillJourney", ["bricks", "compass"]],
    ["HillPlace", ["bookshelf", "writable_book"]],
    ["HillPeople", ["compass", "oak_sapling"]],
  ]);
  await waitFor(
    () => [...expectedEquipment.keys()].every((name) =>
      Object.values(bot.entities).filter((entity) => entity.username === name).length === 1),
    "all three player category NPC profiles",
  );
  await delay(500);
  const npcs = [...expectedEquipment.keys()].map((name) =>
    Object.values(bot.entities).find((entity) => entity.username === name));
  for (const npc of npcs) {
    const [mainHand, offHand] = expectedEquipment.get(npc.username);
    if (npc.type !== "player") {
      throw new Error(`${npc.username} rendered as ${npc.type} instead of a player entity`);
    }
    if (npc.heldItem?.name !== mainHand || npc.equipment?.[1]?.name !== offHand) {
      throw new Error(`${npc.username} equipment was ${npc.heldItem?.name}/${npc.equipment?.[1]?.name}; expected ${mainHand}/${offHand}`);
    }
    const listed = bot.players[npc.username]?.listed;
    if (listed !== false && listed !== 0) {
      throw new Error(`${npc.username} tab-list state was ${String(listed)} instead of false`);
    }
  }
  return npcs;
}

async function nearestCategoryNpc() {
  return (await categoryNpcs())
    .sort((left, right) => left.position.distanceTo(bot.entity.position) - right.position.distanceTo(bot.entity.position))[0];
}

async function nearestCameraMarker(targetBot = bot) {
  await waitFor(
    () => Object.values(targetBot.entities).some((entity) => entity.name === "armor_stand"),
    "a saved camera marker",
  );
  const marker = Object.values(targetBot.entities)
    .filter((entity) => entity.name === "armor_stand")
    .sort((left, right) => left.position.distanceTo(targetBot.entity.position) - right.position.distanceTo(targetBot.entity.position))[0];
  const hasMetadataNumber = (entity, expected) => Object.values(entity.metadata ?? {})
    .some((value) => typeof value === "number" && Math.abs(value - expected) < 0.001);
  await waitFor(
    () => Object.values(targetBot.entities).some((entity) =>
      entity.name === "interaction"
      && hasMetadataNumber(entity, 0.8)
      && hasMetadataNumber(entity, 1.2)),
    "an expanded camera-marker hitbox",
    3_000,
  );
  const hitbox = Object.values(targetBot.entities)
    .filter((entity) => entity.name === "interaction"
      && hasMetadataNumber(entity, 0.8)
      && hasMetadataNumber(entity, 1.2))
    .sort((left, right) => left.position.distanceTo(marker.position) - right.position.distanceTo(marker.position))[0];
  if (hitbox.position.distanceTo(marker.position) > 1.1) {
    throw new Error(`Expanded camera hitbox was ${hitbox.position.distanceTo(marker.position).toFixed(3)} blocks from its marker`);
  }
  return hitbox;
}

async function approachEntity(entity) {
  const horizontalDistance = () => Math.hypot(
    bot.entity.position.x - entity.position.x,
    bot.entity.position.z - entity.position.z,
  );
  bot.physicsEnabled = true;
  await bot.lookAt(entity.position.offset(0, 1, 0), true);
  bot.setControlState("sprint", false);
  bot.setControlState("forward", true);
  try {
    // Drive the bot through vanilla movement so Paper validates the same path
    // a human player would take, including collision and teleport corrections.
    await waitFor(() => horizontalDistance() <= 2.6, "walking within reach of the NPC", 20_000);
  } finally {
    bot.clearControlStates();
  }
  await delay(750);
  await bot.lookAt(entity.position.offset(0, 1, 0), true);
}

async function authenticate() {
  bot.chat(`/register ${username} ${password} ${password}`);
  await waitFor(
    () => transcript.some((line) => line.includes("Registration complete") || line.includes("Welcome to Hill")),
    "development identity approval",
  );
}

async function authenticationLockScenario() {
  const lockedPosition = bot.entity.position.clone();
  const lockedYaw = bot.entity.yaw;
  const lockedPitch = bot.entity.pitch;
  let repeatedTitles = 0;
  const onTitle = () => repeatedTitles++;
  bot._client.on("set_title_text", onTitle);
  try {
    await bot.look(lockedYaw + 1.1, Math.max(-1.2, Math.min(1.2, lockedPitch + 0.45)), true);
    await delay(5_500);
  } finally {
    bot._client.removeListener("set_title_text", onTitle);
  }

  const positionShift = bot.entity.position.distanceTo(lockedPosition);
  const yawShift = angleDistance(bot.entity.yaw, lockedYaw);
  const pitchShift = Math.abs(bot.entity.pitch - lockedPitch);
  const failures = [];
  if (positionShift > 0.15 || yawShift > 0.05 || pitchShift > 0.05) {
    failures.push(
      `Authentication lobby failed to lock the complete viewpoint (position ${positionShift.toFixed(3)}, yaw ${yawShift.toFixed(3)}, pitch ${pitchShift.toFixed(3)})`,
    );
  }
  if (repeatedTitles < 1) {
    failures.push("Authentication title was not refreshed while the player remained unauthenticated");
  }
  if (failures.length > 0) {
    throw new Error(failures.join("; "));
  }
  console.log("PASS: unauthenticated title remained continuous and the complete viewpoint stayed locked");
}

async function lobbyReturnScenario() {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry") || line.includes("entry created")),
    "Journey entry creation",
  );

  const buildPosition = bot.entity.position.clone();
  const buildDimension = bot.game.dimension;
  bot.chat("/lobby");
  await delay(1_500);

  const movedDistance = bot.entity.position.distanceTo(buildPosition);
  const changedDimension = bot.game.dimension !== buildDimension;
  const rejected = transcript.some((line) =>
    line.includes("Unknown or incomplete command")
      || line.includes("Unknown command")
      || line.includes("Only Hill competition commands are enabled"),
  );
  if (rejected || (!changedDimension && movedDistance < 8)) {
    throw new Error(`/lobby did not return the player to the lobby (dimension ${buildDimension} -> ${bot.game.dimension}, moved ${movedDistance.toFixed(2)} blocks)`);
  }

  console.log(`PASS: /lobby returned the player from a build (${buildDimension} -> ${bot.game.dimension})`);
}

async function helpScenario() {
  const transcriptStart = transcript.length;
  bot.chat("/help");
  await waitFor(
    () => transcript.slice(transcriptStart).some((line) => line.includes("Hill 175 Commands")),
    "Hill command help",
  );
  const response = transcript.slice(transcriptStart);
  if (response.some((line) => line.includes("Only Hill competition commands are enabled"))) {
    throw new Error("/help was blocked by the competition command allowlist");
  }
  for (const command of ["/lobby", "/entry", "/team", "/camera", "/rules"]) {
    if (!response.some((line) => line.includes(command))) {
      throw new Error(`/help did not mention ${command}`);
    }
  }
  console.log("PASS: /help listed the Hill competition commands");
}

async function menuPopupScenario() {
  const commandWindow = await waitForWindow(
    () => bot.chat("/hill175"),
    "competition menu from /hill175",
  );
  const commandTitle = windowTitle(commandWindow);
  console.log(`Opened ${commandTitle}: ${topInventorySummary(commandWindow)}`);
  if (!commandTitle.includes("Hill 175") || commandWindow.inventoryStart < 9) {
    throw new Error("/hill175 did not open the competition inventory UI");
  }
  console.log("PASS: /hill175 opened the competition inventory UI");
}

async function itemPopupScenario() {
  await holdHotbarItem("compass");
  const supportBlock = bot.blockAt(bot.entity.position.offset(0, -1, 0));
  if (!supportBlock) {
    throw new Error("Could not find a nearby support block to right-click with the Competition Compass");
  }
  await bot.lookAt(supportBlock.position.offset(0.5, 0.5, 0.5), true);
  const itemWindow = await waitForWindow(
    () => {
      void bot.activateBlock(supportBlock);
    },
    "competition menu from right-clicking the Compass",
  );
  const itemTitle = windowTitle(itemWindow);
  console.log(`Opened by item ${itemTitle}: ${topInventorySummary(itemWindow)}`);
  if (!itemTitle.includes("Hill 175")) {
    throw new Error("Right-clicking the Competition Compass opened the wrong UI");
  }
  console.log("PASS: right-clicking the Competition Compass opened the inventory UI");
}

async function itemAirPopupScenario() {
  const compassSlot = await holdHotbarItem("compass");
  const beforeItem = bot.inventory.slots[36 + compassSlot];
  const beforeCount = beforeItem.count;
  const beforeFood = bot.food;
  const consumable = beforeItem.components?.find((component) => component.type === "consumable");
  if (!consumable || consumable.data?.animation !== "none") {
    throw new Error("Competition Compass was missing its no-animation air-use component");
  }
  console.log(`Use item protocol support: own=${bot.supportFeature("useItemWithOwnPacket")} blockPlace=${bot.supportFeature("useItemWithBlockPlace")}`);
  const itemWindow = await expectSingleWindow(
    async () => bot.activateItem(),
    "competition menu from right-clicking the Compass into empty air",
  );
  const itemTitle = windowTitle(itemWindow);
  console.log(`Opened from air use ${itemTitle}: ${topInventorySummary(itemWindow)}`);
  if (!itemTitle.includes("Hill 175")) {
    throw new Error("Right-clicking the Competition Compass into empty air opened the wrong UI");
  }
  await delay(250);
  const afterItem = bot.inventory.slots[36 + compassSlot];
  if (!afterItem || afterItem.count !== beforeCount || bot.food !== beforeFood) {
    throw new Error("Using the Competition Compass consumed an item or changed the player's food level");
  }
  bot.deactivateItem();
  console.log("PASS: right-clicking the Competition Compass into empty air opened exactly one inventory UI");
}

async function lobbyItemAirScenario() {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry created")),
    "Journey entry creation",
  );
  const buildDimension = bot.game.dimension;
  const buildPosition = bot.entity.position.clone();
  await holdHotbarItem("ender_pearl");
  const transcriptStart = transcript.length;
  bot.activateItem();
  await waitFor(
    () => transcript.slice(transcriptStart).some((line) => line.includes("right-click the Compass or a category guide")),
    "lobby teleport from right-clicking the Ender Pearl into empty air",
  );
  const changedDimension = bot.game.dimension !== buildDimension;
  const movedDistance = bot.entity.position.distanceTo(buildPosition);
  if (!changedDimension && movedDistance < 8) {
    throw new Error(`Lobby item announced a return but did not move the player (${movedDistance.toFixed(2)} blocks)`);
  }
  bot.deactivateItem();
  console.log("PASS: native-use lobby item triggered from empty air");
}

async function npcInteractionsScenario() {
  const npcs = await categoryNpcs();
  console.log(`Verified player NPC profiles: ${npcs.map((npc) => `${npc.username}=${npc.heldItem.name}/${npc.equipment[1].name}`).join(", ")}`);
  const npc = npcs
    .sort((left, right) => left.position.distanceTo(bot.entity.position) - right.position.distanceTo(bot.entity.position))[0];
  await approachEntity(npc);
  console.log(`Testing category NPC entity ${npc.id} at ${npc.position}`);

  const rightClickWindow = await expectSingleWindow(
    async () => {
      // Vanilla may surface both main- and off-hand Bukkit interaction events;
      // two packets make the once-only behavior deterministic in this harness.
      bot._client.write("use_entity", {
        target: npc.id,
        hand: 0,
        location: { x: 0, y: 1, z: 0 },
        usingSecondaryAction: false,
      });
      bot._client.write("use_entity", {
        target: npc.id,
        hand: 1,
        location: { x: 0, y: 1, z: 0 },
        usingSecondaryAction: false,
      });
    },
    "category GUI from right-clicking a category NPC",
  );
  if (!windowTitle(rightClickWindow).includes("Create")) {
    throw new Error(`Right-clicking the NPC opened the wrong GUI: ${windowTitle(rightClickWindow)}`);
  }
  bot.closeWindow(rightClickWindow);
  await delay(300);

  const leftClickWindow = await expectSingleWindow(
    async () => {
      bot._client.write("attack", { entityId: npc.id });
      bot.swingArm();
    },
    "category GUI from left-clicking a category NPC",
  );
  if (!windowTitle(leftClickWindow).includes("Create")) {
    throw new Error(`Left-clicking the NPC opened the wrong GUI: ${windowTitle(leftClickWindow)}`);
  }
  console.log("PASS: all three hidden-tab player NPCs rendered with equipment; right-click and left-click opened the category GUI exactly once");
}

async function npcLeftClickScenario() {
  const npc = await nearestCategoryNpc();
  await approachEntity(npc);
  console.log(`Testing left-click on category NPC entity ${npc.id} at ${npc.position}`);
  const leftClickWindow = await expectSingleWindow(
    async () => {
      bot._client.write("attack", { entityId: npc.id });
      bot.swingArm();
    },
    "category GUI from left-clicking a category NPC",
  );
  if (!windowTitle(leftClickWindow).includes("Create")) {
    throw new Error(`Left-clicking the NPC opened the wrong GUI: ${windowTitle(leftClickWindow)}`);
  }
  console.log("PASS: left-clicking a category NPC opened exactly one category GUI");
}

async function createFlowPopupScenario() {
  const mainWindow = await waitForWindow(
    () => bot.chat("/hill175"),
    "competition menu",
  );
  const journeySlot = mainWindow.slots
    .slice(0, mainWindow.inventoryStart)
    .findIndex((item) => item?.name === "bricks");
  if (journeySlot < 0) {
    throw new Error(`Journey creation card was missing: ${topInventorySummary(mainWindow)}`);
  }

  const confirmationWindow = await waitForWindow(
    () => bot.clickWindow(journeySlot, 0, 0),
    "Journey creation confirmation",
  );
  const confirmationTitle = windowTitle(confirmationWindow);
  console.log(`Opened ${confirmationTitle}: ${topInventorySummary(confirmationWindow)}`);
  if (!confirmationTitle.includes("Journey")) {
    throw new Error("Clicking the Journey card did not open its next UI step");
  }
  console.log("PASS: Journey creation progressed from the main GUI to a category-specific popup");
}

async function submissionDialogScenario() {
  const submissionTitle = "Smoke Dialog Title";
  const submissionDescription = "Smoke dialog description saved from the real protocol callback.";
  const mainWindow = await waitForWindow(
    () => bot.chat("/hill175"),
    "competition menu",
  );
  const journeySlot = mainWindow.slots
    .slice(0, mainWindow.inventoryStart)
    .findIndex((item) => item?.name === "bricks");
  if (journeySlot < 0) {
    throw new Error(`Journey creation card was missing: ${topInventorySummary(mainWindow)}`);
  }
  const confirmationWindow = await waitForWindow(
    () => bot.clickWindow(journeySlot, 0, 0),
    "Journey creation confirmation",
  );
  const createSlot = confirmationWindow.slots
    .slice(0, confirmationWindow.inventoryStart)
    .findIndex((item) => item?.name === "lime_concrete");
  if (createSlot < 0) {
    throw new Error(`Create button was missing: ${topInventorySummary(confirmationWindow)}`);
  }

  const dialogPacket = await waitForPacket(
    "show_dialog",
    () => bot.clickWindow(createSlot, 0, 0),
    "editable submission dialog after creation confirmation",
  );
  const dialogText = JSON.stringify(dialogPacket);
  console.log(`Received submission dialog: ${dialogText}`);
  if (!dialogText.includes("title") || !dialogText.includes("description")) {
    throw new Error("Submission dialog did not expose both title and description inputs");
  }

  const actionIds = [...dialogText.matchAll(/[a-z0-9_.-]+:[a-z0-9_./-]+/gi)]
    .map((match) => match[0]);
  const saveActionId = actionIds.find((id) => id === "hill175:save_submission");
  if (!saveActionId) {
    throw new Error("Could not identify the submission dialog save callback");
  }
  const responseTag = nbt.comp({
    title: nbt.string(submissionTitle),
    description: nbt.string(submissionDescription),
  });
  const responsePacket = {
    id: saveActionId,
    // ByteBufCodecs.optionalTagCodec uses the root TAG_End marker for absent;
    // a present value begins directly with its anonymous root tag. The patched
    // protocol schema owns the surrounding VarInt length prefix.
    nbt: nbt.proto.createPacketBuffer("anonymousNbt", responseTag),
  };
  const encodedResponse = bot._client.serializer.createPacketBuffer({
    name: "custom_click_action",
    params: responsePacket,
  });
  console.log(`Encoded dialog response: ${encodedResponse.toString("hex")}`);
  const entryWindowPromise = waitForWindow(
    () => bot._client.write("custom_click_action", responsePacket),
    "entry controls after saving submission details",
  );
  const entryWindow = await entryWindowPromise;
  const summaryText = entryWindow.slots
    .slice(0, entryWindow.inventoryStart)
    .map(itemUiText)
    .join("\n");
  if (!summaryText.includes(submissionTitle) || !summaryText.includes(submissionDescription)) {
    throw new Error(`Saved submission metadata was missing from the entry GUI: ${summaryText}`);
  }
  console.log("PASS: creation opened an editable dialog and saved title/description into the entry GUI");
}

async function confirmationNavigationScenario() {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry created")),
    "Journey entry creation",
  );

  await holdHotbarItem("nether_star");
  const buildOptions = await waitForWindow(
    () => bot.activateItem(),
    "Build Options from Entry Controls",
  );
  if (!windowTitle(buildOptions).includes("Build Options")) {
    throw new Error(`Entry Controls opened the wrong GUI: ${windowTitle(buildOptions)}`);
  }
  const ownerHotbar = bot.inventory.slots.slice(36, 45).map((item) => item?.name ?? "empty");
  for (const removedTool of ["barrier", "tripwire_hook"]) {
    if (ownerHotbar.includes(removedTool)) {
      throw new Error(`${removedTool} remained in the owner hotbar instead of Build Options`);
    }
  }

  const resetWindow = await waitForWindow(
    () => bot.clickWindow(22, 0, 0),
    "Reset confirmation from Build Options",
  );
  if (!windowTitle(resetWindow).includes("Reset this entry?")) {
    throw new Error(`Reset Build Option skipped confirmation: ${windowTitle(resetWindow)}`);
  }
  const buildOptionsAfterResetCancel = await waitForWindow(
    () => bot.clickWindow(6, 0, 0),
    "Build Options after cancelling Reset",
  );
  if (!windowTitle(buildOptionsAfterResetCancel).includes("Build Options")) {
    throw new Error("Reset confirmation did not return to Build Options");
  }

  const categoryWindow = await waitForWindow(
    () => bot.clickWindow(20, 0, 0),
    "category selector from Build Options",
  );
  if (!windowTitle(categoryWindow).includes("Change Category")) {
    throw new Error(`Category Build Option opened the wrong GUI: ${windowTitle(categoryWindow)}`);
  }
  const categoryConfirmation = await waitForWindow(
    () => bot.clickWindow(13, 0, 0),
    "category-change confirmation",
  );
  if (!windowTitle(categoryConfirmation).includes("Replace with")) {
    throw new Error(`Category change skipped confirmation: ${windowTitle(categoryConfirmation)}`);
  }
  const categoryWindowAfterCancel = await waitForWindow(
    () => bot.clickWindow(6, 0, 0),
    "category selector after cancelling category change",
  );
  const buildOptionsAfterCategoryCancel = await waitForWindow(
    () => bot.clickWindow(26, 0, 0),
    "Build Options after leaving category selector",
  );
  if (!windowTitle(categoryWindowAfterCancel).includes("Change Category")
    || !windowTitle(buildOptionsAfterCategoryCancel).includes("Build Options")) {
    throw new Error("Category-change cancellation did not return through the expected menus");
  }

  const lockWindow = await waitForWindow(
    () => bot.clickWindow(21, 0, 0),
    "Lock confirmation from Build Options",
  );
  if (!windowTitle(lockWindow).includes("Lock this submission?")) {
    throw new Error(`Lock Build Option skipped confirmation: ${windowTitle(lockWindow)}`);
  }
  const buildOptionsAfterLockCancel = await waitForWindow(
    () => bot.clickWindow(6, 0, 0),
    "Build Options after cancelling Lock",
  );
  if (!windowTitle(buildOptionsAfterLockCancel).includes("Build Options")) {
    throw new Error("Lock confirmation did not return to Build Options");
  }
  const deleteWindow = await waitForWindow(
    () => bot.clickWindow(23, 0, 0),
    "Delete confirmation from Build Options",
  );
  if (!windowTitle(deleteWindow).includes("Delete this entry?")) {
    throw new Error(`Delete Build Option skipped confirmation: ${windowTitle(deleteWindow)}`);
  }
  const buildOptionsAfterDeleteCancel = await waitForWindow(
    () => bot.clickWindow(6, 0, 0),
    "Build Options after cancelling Delete",
  );
  bot.closeWindow(buildOptionsAfterDeleteCancel);

  bot.chat("/hub");
  await waitFor(
    () => transcript.some((line) => line.includes("right-click the Compass or a category guide")),
    "hub return after confirmation checks",
  );
  await delay(500);
  const hotbarNames = bot.inventory.slots.slice(36, 45).map((item) => item?.name ?? "empty");
  for (const leaked of ["barrier", "tripwire_hook", "spyglass", "nether_star"]) {
    if (hotbarNames.includes(leaked)) {
      throw new Error(`Owner-only ${leaked} leaked into the hub hotbar`);
    }
  }
  console.log("PASS: Build Options owns reset/lock/delete/category change and owner tools do not leak into the hub");
}

async function verifyVisitorCannotRemoveCamera(entryTitle) {
  const visitorUsername = `Visit${String(Date.now()).slice(-9)}`;
  const visitorTranscript = [];
  const visitor = mineflayer.createBot({
    host,
    port,
    username: visitorUsername,
    auth: "offline",
    hideErrors: false,
    plugins: { team: false },
  });
  visitor.on("messagestr", (message) => {
    visitorTranscript.push(message.replaceAll(/\u00a7[0-9A-FK-OR]/gi, ""));
  });
  try {
    await new Promise((resolve) => visitor.once("spawn", resolve));
    visitor.chat(`/register ${visitorUsername} ${password} ${password}`);
    await waitFor(
      () => visitorTranscript.some((line) => line.includes("Registration complete")),
      "visitor authentication",
    );

    let visits = await waitForBotWindow(
      visitor,
      () => visitor.chat("/entry visit"),
      "visitor entry browser",
    );
    let visitSlot = -1;
    for (let page = 0; page < 32; page += 1) {
      visitSlot = visits.slots
        .slice(0, visits.inventoryStart)
        .findIndex((item) => itemUiText(item).includes(entryTitle));
      if (visitSlot >= 0 || !itemUiText(visits.slots[53]).includes("Next Page")) break;
      visits = await waitForBotWindow(
        visitor,
        () => visitor.clickWindow(53, 0, 0),
        `visitor entry browser page ${page + 2}`,
      );
    }
    if (visitSlot < 0) {
      throw new Error(`Visitor browser did not contain ${entryTitle}: ${topInventorySummary(visits)}`);
    }
    const arrivalStart = visitorTranscript.length;
    visitor.clickWindow(visitSlot, 0, 0);
    await waitFor(
      () => visitorTranscript.slice(arrivalStart).some((line) => line.includes("Visitor Mode")),
      "visitor entry arrival",
    );
    await delay(500);

    const marker = await nearestCameraMarker(visitor);
    const previewStart = visitorTranscript.length;
    visitor._client.write("use_entity", {
      target: marker.id,
      hand: 0,
      location: { x: 0, y: 1, z: 0 },
      usingSecondaryAction: false,
    });
    await waitFor(
      () => visitorTranscript.slice(previewStart).some((line) => line.includes("Previewing camera slot 1")),
      "visitor camera-marker preview",
    );
    await delay(500);
    if (visitor.inventory.slots.slice(36, 45).some((item) => item?.name === "red_dye")) {
      throw new Error("Visitor received the owner-only Remove This Camera item");
    }

    const deniedStart = visitorTranscript.length;
    visitor.chat("/camera remove 1");
    await waitFor(
      () => visitorTranscript.slice(deniedStart).some((line) => line.includes("Open one of your entries first")),
      "visitor camera-removal denial",
    );
    if (visitorTranscript.slice(deniedStart).some((line) => line.includes("Camera pose 1 removed"))) {
      throw new Error("Visitor command removed the owner's camera");
    }

    const exitSlot = visitor.inventory.slots.slice(36, 45).findIndex((item) => item?.name === "barrier");
    if (exitSlot < 0) {
      throw new Error("Visitor camera preview had no exit item");
    }
    visitor.setQuickBarSlot(exitSlot);
    visitor._client.write("held_item_slot", { slotId: exitSlot });
    const exitStart = visitorTranscript.length;
    visitor.activateItem();
    await waitFor(
      () => visitorTranscript.slice(exitStart).some((line) => line.includes("Camera preview closed")),
      "visitor camera exit",
    );
    visitor.deactivateItem();
  } finally {
    visitor.quit("Visitor camera smoke complete");
    await delay(250);
  }
}

async function cameraViewScenario() {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry created")),
    "Journey entry creation",
  );
  await delay(500);

  const cameraEntryTitle = `Camera-${username}`;
  const titleTranscriptStart = transcript.length;
  bot.chat(`/entry title ${cameraEntryTitle}`);
  await waitFor(
    () => transcript.slice(titleTranscriptStart).some((line) => line.includes("Project title saved")),
    "camera smoke entry title",
  );

  const savedFeetPosition = bot.entity.position.clone();
  const saveTranscriptStart = transcript.length;
  await holdHotbarItem("ender_eye");
  const openedDuringCapture = [];
  const onCaptureWindowOpen = (window) => openedDuringCapture.push(window);
  bot.on("windowOpen", onCaptureWindowOpen);
  bot.activateItem();
  await waitFor(
    () => transcript.slice(saveTranscriptStart).some((line) => line.includes("Camera 1/3 saved")),
    "direct camera pose capture",
  );
  bot.deactivateItem();
  await delay(250);
  bot.removeListener("windowOpen", onCaptureWindowOpen);
  if (openedDuringCapture.length !== 0) {
    throw new Error(`Direct camera capture opened ${openedDuringCapture.length} GUI windows`);
  }

  const previewTranscriptStart = transcript.length;
  let bossBarPackets = 0;
  let titlePackets = 0;
  const cameraPackets = [];
  const onBossBar = () => bossBarPackets++;
  const onTitle = () => titlePackets++;
  const onCamera = (packet) => cameraPackets.push(packet.cameraId);
  bot._client.on("boss_bar", onBossBar);
  bot._client.on("set_title_text", onTitle);
  bot._client.on("camera", onCamera);
  bot.chat("/camera preview");
  await waitFor(
    () => transcript.slice(previewTranscriptStart).some((line) => line.includes("Previewing camera slot 1")),
    "camera preview",
  );
  await delay(500);
  bot._client.removeListener("boss_bar", onBossBar);
  bot._client.removeListener("set_title_text", onTitle);
  bot._client.removeListener("camera", onCamera);
  if (bossBarPackets === 0 || titlePackets === 0) {
    throw new Error(`Camera preview did not render both persistent and title displays (boss bar ${bossBarPackets}, title ${titlePackets})`);
  }
  if (!cameraPackets.some((cameraId) => cameraId !== bot.entity.id)) {
    throw new Error(`Camera preview never focused a fixed client camera entity: ${JSON.stringify(cameraPackets)}`);
  }

  const feetShift = bot.entity.position.distanceTo(savedFeetPosition);
  if (feetShift > 0.15) {
    throw new Error(`Camera preview shifted the player ${feetShift.toFixed(3)} blocks instead of preserving the full-screen eye view`);
  }

  const lockedYaw = bot.entity.yaw;
  const lockedPitch = bot.entity.pitch;
  await bot.look(lockedYaw + 0.8, Math.max(-1.2, Math.min(1.2, lockedPitch + 0.35)), true);
  await delay(500);
  const yawShift = Math.abs(bot.entity.yaw - lockedYaw);
  const pitchShift = Math.abs(bot.entity.pitch - lockedPitch);
  if (bot.entity.position.distanceTo(savedFeetPosition) > 0.15 || yawShift > 0.05 || pitchShift > 0.05) {
    throw new Error(`Camera preview failed to lock movement/rotation (yaw ${yawShift.toFixed(3)}, pitch ${pitchShift.toFixed(3)})`);
  }

  let closeTranscriptStart = transcript.length;
  await holdHotbarItem("barrier");
  bot.activateItem();
  await waitFor(
    () => transcript.slice(closeTranscriptStart).some((line) => line.includes("Camera preview closed")),
    "right-click camera preview exit item",
  );
  bot.deactivateItem();

  let marker = await nearestCameraMarker();
  let markerPreviewStart = transcript.length;
  bot._client.write("use_entity", {
    target: marker.id,
    hand: 0,
    location: { x: 0, y: 1, z: 0 },
    usingSecondaryAction: false,
  });
  await waitFor(
    () => transcript.slice(markerPreviewStart).some((line) => line.includes("Previewing camera slot 1")),
    "right-click camera marker preview",
  );

  closeTranscriptStart = transcript.length;
  await holdHotbarItem("barrier");
  const leftClickBlock = bot.blockAt(bot.entity.position.offset(0, -1, 0).floored());
  if (!leftClickBlock) {
    throw new Error("Could not find a nearby block for the left-click preview-exit check");
  }
  bot._client.write("block_dig", {
    status: 0,
    location: leftClickBlock.position,
    face: 1,
  });
  bot.swingArm();
  await waitFor(
    () => transcript.slice(closeTranscriptStart).some((line) => line.includes("Camera preview closed")),
    "left-click camera preview exit item",
  );

  marker = await nearestCameraMarker();
  markerPreviewStart = transcript.length;
  bot._client.write("attack", { entityId: marker.id });
  bot.swingArm();
  await waitFor(
    () => transcript.slice(markerPreviewStart).some((line) => line.includes("Previewing camera slot 1")),
    "left-click camera marker preview",
  );

  await verifyVisitorCannotRemoveCamera(cameraEntryTitle);

  const removeTranscriptStart = transcript.length;
  await holdHotbarItem("red_dye");
  const removeConfirmation = await waitForWindow(
    () => bot.activateItem(),
    "active camera removal confirmation",
  );
  bot.deactivateItem();
  if (!windowTitle(removeConfirmation).includes("Remove camera 1?")) {
    throw new Error(`Owner removal item opened the wrong UI: ${windowTitle(removeConfirmation)}`);
  }
  bot.clickWindow(4, 0, 0);
  await waitFor(
    () => transcript.slice(removeTranscriptStart).some((line) => line.includes("Camera pose 1 removed")),
    "active camera removal",
  );

  console.log("PASS: direct camera capture, fixed client camera, locked view, owner/visitor marker clicks, both exits, and owner-only removal UI worked");
}

async function cameraHeldUseScenario() {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry created")),
    "Journey entry creation",
  );
  await delay(500);

  const hotbar = bot.inventory.slots.slice(36, 45);
  const cameraSlot = hotbar.findIndex((item) => item?.name === "ender_eye" || item?.name === "spyglass");
  if (cameraSlot < 0) {
    throw new Error("Expected a Camera Controls item in the owner hotbar");
  }
  const cameraMaterial = hotbar[cameraSlot].name;
  bot.setQuickBarSlot(cameraSlot);
  bot._client.write("held_item_slot", { slotId: cameraSlot });
  await delay(150);

  const transcriptStart = transcript.length;
  const opened = [];
  const onWindowOpen = (window) => opened.push(window);
  bot.on("windowOpen", onWindowOpen);
  try {
    for (let attempt = 0; attempt < 5; attempt++) {
      bot.activateItem();
      await delay(80);
    }
    bot.deactivateItem();
    await delay(750);
  } finally {
    bot.removeListener("windowOpen", onWindowOpen);
  }

  const cameraSaves = transcript.slice(transcriptStart)
    .filter((line) => /Camera [1-3]\/3 (saved|updated)\./.test(line));
  const failures = [];
  if (cameraMaterial === "spyglass") {
    failures.push("Camera Controls still uses the zooming spyglass");
  }
  if (cameraSaves.length !== 1) {
    failures.push(`one held camera use saved ${cameraSaves.length} poses instead of exactly one`);
  }
  if (cameraMaterial === "ender_eye") {
    if (opened.length !== 0) {
      failures.push(`direct camera capture opened ${opened.length} menus instead of none`);
    }
  }
  if (failures.length > 0) {
    throw new Error(failures.join("; "));
  }
  console.log("PASS: one held camera-item use captured one view directly, opened no GUI, and saved no duplicates");
}

async function movePlayerLinearly(target) {
  bot.physicsEnabled = false;
  const start = bot.entity.position.clone();
  const steps = Math.max(1, Math.ceil(start.distanceTo(target) / 0.4));
  for (let step = 1; step <= steps; step++) {
    const fraction = step / steps;
    const position = start.scaled(1 - fraction).plus(target.scaled(fraction));
    bot.entity.position.set(position.x, position.y, position.z);
    bot._client.write("position", {
      x: position.x,
      y: position.y,
      z: position.z,
      flags: { onGround: true, hasHorizontalCollision: false },
    });
    await delay(60);
  }
}

async function plotResetReentryScenario() {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry created")),
    "Journey entry creation",
  );
  await holdHotbarItem("nether_star");
  await waitForWindow(() => bot.activateItem(), "Build Options before reset");
  await waitForWindow(() => bot.clickWindow(22, 0, 0), "Reset confirmation");
  const resetTranscriptStart = transcript.length;
  bot.clickWindow(4, 0, 0);
  await waitFor(
    () => transcript.slice(resetTranscriptStart).some((line) => line.includes("Entry reset complete")),
    "completed plot reset",
    30_000,
  );
  await waitFor(() => bot.game.gameMode === "creative", "Creative Mode after plot reset");

  const ownerPosition = bot.entity.position.clone();
  await movePlayerLinearly(ownerPosition.offset(40, 0, 0));
  await waitFor(() => bot.game.gameMode === "spectator", "Spectator Mode outside the owned plot");
  await movePlayerLinearly(ownerPosition);
  await waitFor(() => bot.game.gameMode === "creative", "Creative Mode after plot re-entry");
  console.log("PASS: completed reset, boundary exit, and re-entry restored Creative Mode");
}

async function entryActionOutsideScenario(action) {
  bot.chat("/entry create journey");
  await waitFor(
    () => transcript.some((line) => line.includes("Journey entry created")),
    "Journey entry creation",
  );
  const entryPosition = bot.entity.position.clone();
  await movePlayerLinearly(entryPosition.offset(40, 0, 0));
  await waitFor(() => bot.game.gameMode === "spectator", "Spectator Mode outside the affected plot");
  const outsidePosition = bot.entity.position.clone();
  const outsideDimension = bot.game.dimension;

  await holdHotbarItem("nether_star");
  const buildOptions = await waitForWindow(() => bot.activateItem(), `Build Options before ${action}`);
  if (!windowTitle(buildOptions).includes("Build Options")) {
    throw new Error(`Entry Controls opened ${windowTitle(buildOptions)} instead of Build Options`);
  }
  const actionSlot = action === "reset" ? 22 : 23;
  const confirmation = await waitForWindow(
    () => bot.clickWindow(actionSlot, 0, 0),
    `${action} confirmation outside the plot`,
  );
  if (!windowTitle(confirmation).toLowerCase().includes(action)) {
    throw new Error(`${action} confirmation opened the wrong GUI: ${windowTitle(confirmation)}`);
  }

  const transcriptStart = transcript.length;
  await bot.clickWindow(4, 0, 0);
  const completionText = action === "reset" ? "Entry reset complete" : "Entry deleted";
  await waitFor(
    () => transcript.slice(transcriptStart).some((line) => line.includes(completionText)),
    `${action} completion outside the plot`,
    30_000,
  );
  await delay(750);

  const movedDistance = bot.entity.position.distanceTo(outsidePosition);
  if (bot.game.dimension !== outsideDimension || movedDistance > 1.5) {
    throw new Error(
      `Entry ${action} moved an owner who was outside the build (dimension ${outsideDimension} -> ${bot.game.dimension}, distance ${movedDistance.toFixed(2)})`,
    );
  }
  console.log(`PASS: entry ${action} left the outside owner in place while completing safely`);
}

async function movementKitStabilityScenario() {
  await delay(500);
  let hotbarMutations = 0;
  const onSetSlot = (packet) => {
    const slot = packet.slot ?? packet.slotId;
    if (Number.isInteger(slot) && slot >= 36 && slot <= 44) hotbarMutations++;
  };
  const onWindowItems = () => {
    hotbarMutations++;
  };
  bot._client.on("set_slot", onSetSlot);
  bot._client.on("window_items", onWindowItems);
  try {
    bot.physicsEnabled = false;
    const start = bot.entity.position.clone();
    for (let step = 1; step <= 8; step++) {
      const x = start.x + step * 0.4;
      bot.entity.position.set(x, start.y, start.z);
      bot._client.write("position", {
        x,
        y: start.y,
        z: start.z,
        flags: { onGround: true, hasHorizontalCollision: false },
      });
      await delay(100);
    }
    await delay(750);
  } finally {
    bot._client.removeListener("set_slot", onSetSlot);
    bot._client.removeListener("window_items", onWindowItems);
  }
  if (hotbarMutations !== 0) {
    throw new Error(`Walking across the hub refreshed the inventory ${hotbarMutations} times`);
  }
  console.log("PASS: normal hub movement did not clear or refresh the Hill hotbar");
}

function currentDimension(targetBot) {
  const tracked = currentWorldNames.get(targetBot);
  if (tracked) return tracked;
  return typeof targetBot.game?.dimension === "string"
    ? targetBot.game.dimension
    : JSON.stringify(targetBot.game?.dimension ?? "");
}

function isPrimarySurvivalDimension(targetBot) {
  const dimension = currentDimension(targetBot);
  return dimension === "minecraft:overworld" || dimension === "overworld";
}

function trackCurrentWorld(targetBot) {
  const update = (packet) => {
    const name = packet?.worldState?.name;
    if (typeof name === "string") currentWorldNames.set(targetBot, name);
  };
  targetBot._client.on("login", update);
  targetBot._client.on("respawn", update);
}

async function survivalGuideNpc() {
  await waitFor(
    () => Object.values(bot.entities).filter((entity) => entity.username === "HillSurvival").length === 1,
    "Survival Guide player NPC",
  );
  const npc = Object.values(bot.entities).find((entity) => entity.username === "HillSurvival");
  if (npc.type !== "player"
    || npc.heldItem?.name !== "grass_block"
    || npc.equipment?.[1]?.name !== "compass") {
    throw new Error(`Survival Guide rendered incorrectly: ${npc.type} ${npc.heldItem?.name}/${npc.equipment?.[1]?.name}`);
  }
  if (bot.players.HillSurvival?.listed !== false && bot.players.HillSurvival?.listed !== 0) {
    throw new Error(`Survival Guide tab-list state was ${String(bot.players.HillSurvival?.listed)} instead of false`);
  }
  const expected = new Vec3(70.5, 66.0, 31.5);
  if (npc.position.distanceTo(expected) > 0.05) {
    throw new Error(`Survival Guide spawned at ${npc.position} instead of ${expected}`);
  }
  return npc;
}

async function enterSurvivalThroughGuide() {
  const npc = await survivalGuideNpc();
  await approachEntity(npc);
  const menu = await expectSingleWindow(
    async () => {
      bot._client.write("use_entity", {
        target: npc.id,
        hand: 0,
        location: { x: 0, y: 1, z: 0 },
        usingSecondaryAction: false,
      });
      bot._client.write("use_entity", {
        target: npc.id,
        hand: 1,
        location: { x: 0, y: 1, z: 0 },
        usingSecondaryAction: false,
      });
    },
    "Survival Guide entry menu",
  );
  if (!windowTitle(menu).includes("Enter Survival") || menu.slots[4]?.name !== "grass_block") {
    throw new Error(`Survival Guide opened the wrong one-item UI: ${windowTitle(menu)} [${topInventorySummary(menu)}]`);
  }
  bot.clickWindow(4, 0, 0);
  await waitFor(
    () => isPrimarySurvivalDimension(bot),
    "primary survival Overworld",
    20_000,
  );
  await delay(750);
}

async function survivalWorldScenario() {
  await enterSurvivalThroughGuide();
  if (String(bot.game?.gameMode).toLowerCase() !== "survival") {
    throw new Error(`Survival Guide left the player in ${String(bot.game?.gameMode)} mode`);
  }
  const competitionItems = new Set(["compass", "ender_eye", "barrier", "written_book", "nether_star"]);
  if (bot.inventory.slots.slice(36, 45).some((item) => competitionItems.has(item?.name))) {
    throw new Error("Competition hotbar items leaked into survival inventory");
  }

  bot.physicsEnabled = true;
  const initialPosition = bot.entity.position.clone();
  bot.setControlState("forward", true);
  await delay(1_500);
  bot.clearControlStates();
  await delay(500);
  const savedPosition = bot.entity.position.clone();
  if (savedPosition.distanceTo(initialPosition) < 0.4) {
    throw new Error("Survival movement was unexpectedly locked");
  }

  bot.chat("/hub");
  await waitFor(
    () => currentDimension(bot).includes("hill_hub"),
    "hub return from survival",
    20_000,
  );
  await delay(750);
  await enterSurvivalThroughGuide();
  if (bot.entity.position.distanceTo(savedPosition) > 1.0) {
    throw new Error(`Survival re-entry did not restore location (shift ${bot.entity.position.distanceTo(savedPosition).toFixed(2)})`);
  }

  bot.quit("Survival resume reconnect smoke");
  bot.end("Survival resume reconnect smoke");
  await delay(750);
  const resumeTranscript = [];
  const resumeBot = mineflayer.createBot({
    host,
    port,
    username,
    auth: "offline",
    hideErrors: false,
    plugins: { team: false },
  });
  trackCurrentWorld(resumeBot);
  resumeBot.on("messagestr", (message) => {
    resumeTranscript.push(message.replaceAll(/\u00a7[0-9A-FK-OR]/gi, ""));
  });
  try {
    await new Promise((resolve) => resumeBot.once("spawn", resolve));
    resumeBot.chat(`/login ${password}`);
    await waitFor(
      () => resumeTranscript.some((line) => line.includes("Login successful")),
      "survival reconnect login",
    );
    await waitFor(
      () => isPrimarySurvivalDimension(resumeBot),
      "automatic survival resume after authentication",
      20_000,
    );
    await delay(750);
    if (String(resumeBot.game?.gameMode).toLowerCase() !== "survival") {
      throw new Error(`Reconnect resumed in ${String(resumeBot.game?.gameMode)} mode`);
    }
    if (resumeBot.entity.position.distanceTo(savedPosition) > 1.0) {
      throw new Error(`Reconnect did not restore survival location (shift ${resumeBot.entity.position.distanceTo(savedPosition).toFixed(2)})`);
    }
  } finally {
    resumeBot.quit("Survival smoke complete");
    resumeBot.end("Survival smoke complete");
    await delay(250);
  }

  console.log("PASS: Survival Guide NPC, one-item menu, unrestricted movement, scoped inventory, hub re-entry, and reconnect resume worked");
}

async function peopleImportScenario() {
  bot.chat("/entry create people");
  await waitFor(
    () => transcript.some((line) => line.includes("People entry created.")),
    "People entry creation",
  );
  await waitFor(
    () => transcript.some((line) => line.includes("structure.nbt")),
    "People structure import announcement",
  );
  await waitFor(
    () => transcript.some((line) => line.includes("Owner Mode: you may build inside this entry.")),
    "People world ready",
    60_000,
  );
  const campusSentinel = new Vec3(-1, 94, 0);
  await waitFor(
    () => bot.blockAt(campusSentinel, false) != null,
    "the campus sentinel chunk",
  );
  const sentinelBlock = bot.blockAt(campusSentinel, false);
  if (sentinelBlock?.name !== "gray_concrete") {
    throw new Error(
      `People world sentinel ${campusSentinel} was ${sentinelBlock?.name ?? "unloaded"}; expected gray_concrete from the LiDAR campus road`,
    );
  }
  console.log("PASS: People entry imported the LiDAR structure.nbt world, matched the campus sentinel, and auto-teleported the player");
}

function currentWorldFolder() {
  const dimension = currentDimension(bot);
  const worldName = dimension.includes(":") ? dimension.split(":").at(-1) : dimension;
  const candidates = [
    path.resolve(scriptDirectory, "..", "runtime", "server", "world", "dimensions", "minecraft", worldName),
    path.resolve(scriptDirectory, "..", "runtime", "server", worldName),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

async function peopleVoxelEarthTemplateScenario() {
  bot.chat("/entry create people");
  await waitFor(
    () => transcript.some((line) => line.includes("People entry created.")),
    "People entry creation",
    120_000,
  );
  await waitFor(
    () => currentDimension(bot).includes("hill_people_"),
    "teleport into a private People world",
    120_000,
  );
  await waitFor(
    () => transcript.some((line) => line.includes("Owner Mode: you may build inside this entry.")),
    "People owner mode",
    120_000,
  );

  const folder = currentWorldFolder();
  if (!folder) {
    throw new Error(`Could not resolve current People world folder for ${currentDimension(bot)}`);
  }
  const manifestPath = path.join(folder, "voxelearth-hill-manifest.json");
  if (!existsSync(manifestPath)) {
    throw new Error(`People world does not contain VoxelEarth manifest: ${manifestPath}`);
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (manifest?.format !== "voxelearth-hill-campus-v1") {
    throw new Error(`Unexpected VoxelEarth manifest format: ${manifest?.format}`);
  }
  if (manifest?.voxelGrid !== 64 || manifest?.blocksPerMetre !== 1) {
    throw new Error(`Unexpected VoxelEarth v5 scale: grid ${manifest?.voxelGrid}, ${manifest?.blocksPerMetre} blocks/metre`);
  }
  const regionDir = path.join(folder, "region");
  const regionFiles = readdirSync(regionDir).filter((name) => name.endsWith(".mca"));
  const regionBytes = regionFiles.reduce((sum, name) => sum + statSync(path.join(regionDir, name)).size, 0);
  if ((manifest?.result?.keptVoxels ?? 0) < 8_000_000) {
    throw new Error(`VoxelEarth groundfill v5 manifest kept only ${manifest?.result?.keptVoxels ?? 0} voxels`);
  }
  if (regionFiles.length < 20 || regionBytes < 40_000_000) {
    throw new Error(`VoxelEarth People world has weak region output: ${regionFiles.length} files, ${regionBytes} bytes`);
  }
  await waitFor(
    () => hasHotbarItem("filled_map", "People Campus Chart"),
    `People Campus Chart filled_map in hotbar: ${hotbarSummary()}`,
    30_000,
  );

  await delay(2_000);
  const below = bot.blockAt(bot.entity.position.offset(0, -1, 0).floored(), false);
  if (!below || below.name === "air" || below.name === "void_air") {
    throw new Error(`People world spawn is not standing on solid VoxelEarth terrain: ${below?.name ?? "unloaded"}`);
  }

  console.log(`PASS: People entry cloned VoxelEarth groundfill v5 template from ${folder}; ${manifest.result.keptVoxels} kept voxels, ${regionFiles.length} region files, chart map present, standing on ${below.name}`);
}

const bot = mineflayer.createBot({
  host,
  port,
  username,
  auth: "offline",
  hideErrors: false,
  // The pinned Mineflayer fork does not yet decode Minecraft 26.2's team
  // component shape. Team state is irrelevant to these interaction checks.
  plugins: { team: false },
});
trackCurrentWorld(bot);

bot.on("messagestr", (message) => {
  const clean = message.replaceAll(/\u00a7[0-9A-FK-OR]/gi, "");
  transcript.push(clean);
  console.log(clean);
});

bot.once("error", (error) => {
  fail(error.stack ?? error.message);
});

bot.once("kicked", (reason) => {
  fail(`Kicked: ${typeof reason === "string" ? reason : JSON.stringify(reason)}`);
});

try {
  await new Promise((resolve) => bot.once("spawn", resolve));
  if (scenario === "authentication-lock") {
    await authenticationLockScenario();
  } else {
    await authenticate();

    switch (scenario) {
    case "lobby-return":
      await lobbyReturnScenario();
      break;
    case "help":
      await helpScenario();
      break;
    case "menu-popup":
      await menuPopupScenario();
      break;
    case "item-popup":
      await itemPopupScenario();
      break;
    case "item-air-popup":
      await itemAirPopupScenario();
      break;
    case "lobby-item-air":
      await lobbyItemAirScenario();
      break;
    case "npc-interactions":
      await npcInteractionsScenario();
      break;
    case "npc-left-click":
      await npcLeftClickScenario();
      break;
    case "create-flow-popup":
      await createFlowPopupScenario();
      break;
    case "submission-dialog":
      await submissionDialogScenario();
      break;
    case "confirmation-navigation":
      await confirmationNavigationScenario();
      break;
    case "camera-view":
      await cameraViewScenario();
      break;
    case "camera-held-use":
      await cameraHeldUseScenario();
      break;
    case "plot-reset-reentry":
      await plotResetReentryScenario();
      break;
    case "entry-reset-outside":
      await entryActionOutsideScenario("reset");
      break;
    case "entry-delete-outside":
      await entryActionOutsideScenario("delete");
      break;
    case "movement-kit-stability":
      await movementKitStabilityScenario();
      break;
    case "survival-world":
      await survivalWorldScenario();
      break;
    case "people-import":
      await peopleImportScenario();
      break;
    case "people-voxelearth-template":
      await peopleVoxelEarthTemplateScenario();
      break;
    case "navigation":
      await helpScenario();
      await lobbyReturnScenario();
      break;
    default:
      throw new Error(`Unknown scenario: ${scenario}`);
    }
  }
} catch (error) {
  fail(error.stack ?? error.message);
} finally {
  bot.quit("Smoke test complete");
  bot.end("Smoke test complete");
  await delay(250);
}

// The pinned Mineflayer fork can retain internal timers after its sockets close.
// Every scenario has completed its cleanup above, so exit deterministically for
// CI, deployment scripts, and repeated local smoke passes.
process.exit(process.exitCode ?? 0);
