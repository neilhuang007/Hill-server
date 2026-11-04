import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const dependencyRoot = process.env.HILL175_SMOKE_DEPS
  ?? path.resolve(scriptDirectory, "..", "runtime", "smoke-bot", "mineflayer");
const requireDependencies = createRequire(path.join(dependencyRoot, "package.json"));
const mineflayer = existsSync(path.join(dependencyRoot, "index.js"))
  ? requireDependencies(path.join(dependencyRoot, "index.js"))
  : requireDependencies("mineflayer");
const { Vec3 } = requireDependencies("vec3");
const existingAccount = process.env.HILL175_SMOKE_EXISTING_ACCOUNT;
const username = existingAccount ?? `Place${String(Date.now()).slice(-10)}`;
const password = "SmokeTest123!";
const transcript = [];
const mapPackets = [];
const serverCorrections = [];
const draftLinks = [];
let worldName = "";
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const catalog = readFileSync(path.resolve(scriptDirectory, "..", "src", "main", "resources", "hill-buildings.yml"), "utf8");
const chapel = catalog.match(/  alumni-chapel:\r?\n[\s\S]*?bounds-xz: \[([^\]]+)\]/);
if (!chapel) throw new Error("The source catalog has no Alumni Chapel footprint");
const [minX, minZ, maxX, maxZ] = chapel[1].split(",").map(Number);
const region = { minX: minX - 16, minZ: minZ - 16, maxX: maxX + 16, maxZ: maxZ + 16 };

const bot = mineflayer.createBot({
  host: process.env.HILL175_SMOKE_HOST ?? "127.0.0.1",
  port: Number(process.env.HILL175_SMOKE_PORT ?? "25566"),
  username,
  auth: "offline",
  hideErrors: false,
  plugins: { team: false },
});
const trackWorld = (packet) => {
  if (typeof packet?.worldState?.name === "string") worldName = packet.worldState.name;
};
bot._client.on("login", trackWorld);
bot._client.on("respawn", trackWorld);
bot._client.on("map", (packet) => mapPackets.push(packet));
bot._client.on("position", (packet) => serverCorrections.push(packet));
bot.on("messagestr", (message) => {
  const clean = message.replaceAll(/\u00a7[0-9A-FK-OR]/gi, "");
  transcript.push(clean);
  console.log(clean);
});
bot.on("message", (message) => {
  const serialized = JSON.stringify(message.json ?? message);
  for (const match of serialized.matchAll(/https?:\/\/[^"\\\s]+\/preview\/[a-f0-9]+/g)) draftLinks.push(match[0]);
});

async function waitFor(predicate, description, timeout = 15_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${description}; world=${worldName}, mode=${bot.game.gameMode}`);
}

function itemText(item) {
  return [item?.customName, ...(item?.customLore ?? [])]
    .map((value) => typeof value === "string" ? value : JSON.stringify(value ?? "")).join("\n");
}

function findSlot(window, text) {
  const slot = window.slots.slice(0, window.inventoryStart).findIndex((item) => itemText(item).includes(text));
  if (slot < 0) throw new Error(`No menu card contains ${text}`);
  return slot;
}

async function openWindow(action, description) {
  const oldWindow = bot.currentWindow;
  await action();
  await waitFor(() => bot.currentWindow && bot.currentWindow !== oldWindow, description);
  return bot.currentWindow;
}

async function holdItem(name) {
  await waitFor(() => bot.inventory.slots.slice(36, 45).some((item) => item?.name === name), `${name} hotbar item`);
  const slot = bot.inventory.slots.slice(36, 45).findIndex((item) => item?.name === name);
  bot.setQuickBarSlot(slot);
  bot._client.write("held_item_slot", { slotId: slot });
  await delay(250);
}

async function useHeldItem() {
  bot.activateItem();
  await delay(150);
  bot.deactivateItem();
}

async function moveTo(target) {
  bot.physicsEnabled = false;
  const origin = bot.entity.position.clone();
  const steps = Math.max(1, Math.ceil(origin.distanceTo(target) / 0.4));
  for (let step = 1; step <= steps; step++) {
    const fraction = step / steps;
    const position = origin.scaled(1 - fraction).plus(target.scaled(fraction));
    bot.entity.position.set(position.x, position.y, position.z);
    bot._client.write("position", {
      x: position.x, y: position.y, z: position.z,
      flags: { onGround: false, hasHorizontalCollision: false },
    });
    await delay(60);
  }
  await delay(400);
  if (bot.entity.position.distanceTo(target) > 1.5) {
    throw new Error(`Movement to ${target} was corrected to ${bot.entity.position}; last correction ${JSON.stringify(serverCorrections.at(-1))}`);
  }
}

function isAir(position) {
  return ["air", "cave_air", "void_air"].includes(bot.blockAt(position, false)?.name);
}

function isFloor(position) {
  const block = bot.blockAt(position, false);
  return block?.boundingBox === "block"
    && !/leaves|cactus|magma|campfire|trapdoor|_door|chest|barrel|furnace|crafting|button|pressure_plate/.test(block.name);
}

function findPatch(isInterior) {
  const candidates = [];
  const startX = isInterior ? Math.max(minX + 2, -8) : region.minX + 2;
  const endX = isInterior ? Math.min(maxX - 2, 8) : minX - 2;
  const startZ = isInterior ? Math.max(minZ + 2, 0) : maxZ + 2;
  const endZ = isInterior ? Math.min(maxZ - 2, 24) : region.maxZ - 2;
  for (let x = startX; x <= endX; x++) {
    for (let z = startZ; z <= endZ; z++) {
      for (let y = 75; y <= (isInterior ? 94 : 125); y++) {
        const target = new Vec3(x, y, z);
        if (!isFloor(target.offset(0, -1, 0)) || !isAir(target) || !isAir(target.offset(0, 1, 0))) continue;
        if (!isAir(target.offset(2, 0, 0)) || !isAir(target.offset(2, 1, 0))) continue;
        candidates.push(target);
      }
    }
  }
  candidates.sort((left, right) => left.distanceTo(bot.entity.position) - right.distanceTo(bot.entity.position));
  if (!candidates.length) throw new Error(`No loaded safe ${isInterior ? "interior" : "exterior"} build patch`);
  return candidates[0];
}

async function placeAndBreak(target, description, shouldBreak = true) {
  await moveTo(target.offset(2.5, 0.05, 0.5));
  await waitFor(() => bot.game.gameMode === "creative", `owner mode at ${description}`);
  const Item = requireDependencies("prismarine-item")(bot.registry);
  await bot.creative.setInventorySlot(41, new Item(bot.registry.itemsByName.blue_wool.id, 1));
  bot.setQuickBarSlot(5);
  bot._client.write("held_item_slot", { slotId: 5 });
  await delay(200);
  const support = bot.blockAt(target.offset(0, -1, 0));
  console.log(`Build action: ${description}, target=${target}, support=${support?.name}, player=${bot.entity.position}`);
  await bot.placeBlock(support, new Vec3(0, 1, 0));
  await waitFor(() => bot.blockAt(target, false)?.name === "blue_wool", `placed block at ${description}`);
  if (!shouldBreak) return;
  await bot.dig(bot.blockAt(target));
  await waitFor(() => isAir(target), `broken block at ${description}`);
  console.log(`PASS: owner placed and broke a block ${description} at ${target}`);
}

async function resetBuilding(privateWorld) {
  await bot.waitForChunksToLoad();
  await delay(500);
  const marker = findPatch(false);
  await placeAndBreak(marker, "temporary reset marker", false);
  await holdItem("nether_star");
  const controls = await openWindow(useHeldItem, "private Place controls before reset");
  const confirm = await openWindow(() => bot.clickWindow(findSlot(controls, "Reset Entry"), 0, 0), "private Place reset confirmation");
  const start = transcript.length;
  await bot.clickWindow(findSlot(confirm, "Confirm Reset"), 0, 0);
  await waitFor(() => transcript.slice(start).some((line) => line.includes("Entry reset complete")), "private Place reset completion", 120_000);
  await waitFor(() => worldName === privateWorld && bot.game.gameMode === "creative", "owner mode in reset building");
  await bot.waitForChunksToLoad();
  await waitFor(() => isAir(marker), "original source terrain restored over the reset marker");
  console.log("PASS: private Place reset recreated the selected building and restored its source terrain");
}

function chapelPoint(u, v, y = 83) {
  // Preserved chapel-entry-v1-2x/profile.json rotation and south entrance route.
  const angle = 8.5 * Math.PI / 180;
  return new Vec3(2 * (u * Math.cos(angle) - v * Math.sin(angle)), y,
    2 * (u * Math.sin(angle) + v * Math.cos(angle)));
}

async function enterChapel() {
  await moveTo(bot.entity.position.offset(0, 128 - bot.entity.position.y, 0));
  await moveTo(chapelPoint(0, 34, 128));
  await moveTo(chapelPoint(0, 34, 83));
  await moveTo(chapelPoint(0, 31));
  await moveTo(chapelPoint(0.40431417487584653, 29.76720561369499));
  const door = bot.findBlock({ matching: (block) => /_door$/.test(block.name), maxDistance: 5 });
  if (!door) throw new Error("No door at the preserved Chapel south entrance");
  if (!door.getProperties().open) await bot.activateBlock(door);
  await delay(300);
  await moveTo(chapelPoint(-0.0021617057305829412, 27.047411989449717));
}

async function leaveChapel() {
  await moveTo(chapelPoint(-0.0021617057305829412, 27.047411989449717));
  await moveTo(chapelPoint(0.40431417487584653, 29.76720561369499));
  await moveTo(chapelPoint(0, 31));
  await moveTo(chapelPoint(0, 34));
}

async function retainPrivatePreview(privateWorld) {
  await moveTo(new Vec3(-28, 100, 68));
  await bot.lookAt(new Vec3(-2, 94, 22), true);
  bot.chat("/entry title Local preview — Chapel");
  await waitFor(() => transcript.some((line) => line.includes("Project title saved")), "private preview title");
  bot.chat("/entry description Local protocol smoke draft of the installed Hill campus. Retained privately for gallery inspection.");
  await waitFor(() => transcript.some((line) => line.includes("Project description saved")), "private preview description");
  bot.chat("/entry website");
  await waitFor(() => draftLinks.length > 0 || transcript.some((line) => line.includes("/preview/")), "private website link");
  const draftUrl = draftLinks.at(-1)
    ?? transcript.map((line) => line.match(/https?:\/\/\S+\/preview\/[a-f0-9]+/)?.[0]).find(Boolean);
  if (!draftUrl) throw new Error("The private preview URL was not sent to its owner");
  const url = new URL(draftUrl);
  let manifestResponse = await fetch(new URL(`/api${url.pathname}`, url));
  if (!manifestResponse.ok) throw new Error(`Private gallery returned HTTP ${manifestResponse.status}`);
  let manifest = await manifestResponse.json();
  if (!manifest.images?.length) {
    bot.chat("/camera save 1");
    await waitFor(() => transcript.some((line) => line.includes("Camera 1 image is ready")), "camera image capture", 120_000);
    manifestResponse = await fetch(new URL(`/api${url.pathname}`, url));
    manifest = await manifestResponse.json();
  }
  if (manifest.submitted || manifest.status !== "draft" || !manifest.images?.length) {
    throw new Error("Retained Chapel preview was not a private draft with an image");
  }
  const imageResponse = await fetch(new URL(manifest.images[0].url, url));
  if (!imageResponse.ok) throw new Error(`Camera image returned HTTP ${imageResponse.status}`);
  const outputDirectory = path.resolve(scriptDirectory, "..", "runtime", "smoke-building-selection");
  mkdirSync(outputDirectory, { recursive: true });
  const imagePath = path.join(outputDirectory, "chapel-camera-1.png");
  writeFileSync(imagePath, Buffer.from(await imageResponse.arrayBuffer()));
  const result = { username, worldName: privateWorld, draftUrl, title: manifest.title,
    status: manifest.status, entryId: manifest.id, imagePath, scope: "Local protocol evidence; private draft, not a submitted entry." };
  writeFileSync(path.join(outputDirectory, "result.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(`PASS: retained private Chapel preview ${draftUrl}; image ${imagePath}`);
}

async function runScenario() {
  await new Promise((resolve, reject) => {
    bot.once("spawn", resolve);
    bot.once("error", reject);
    bot.once("kicked", (reason) => reject(new Error(`Kicked: ${JSON.stringify(reason)}`)));
  });
  bot.chat(existingAccount ? `/login ${password}` : `/register ${username} ${password} ${password}`);
  await waitFor(() => transcript.some((line) => /Registration complete|Welcome to Hill|Login successful/.test(line)), "demo authentication");
  if (existingAccount) {
    bot.chat("/entry home");
  } else {
    bot.chat("/entry create place");
    await holdItem("filled_map");
    if (!bot.heldItem || bot.heldItem.name !== "filled_map") throw new Error("Building selection map is not held");
    await waitFor(() => mapPackets.some((packet) => (packet.icons?.length ?? 0) >= 30), "numbered building map packet");
    const buildings = await openWindow(useHeldItem, "building chooser from held map");
    const preview = await openWindow(() => bot.clickWindow(findSlot(buildings, "#6 Alumni Chapel"), 0, 0), "chapel confirmation");
    await bot.clickWindow(findSlot(preview, "Build Here"), 0, 0);
  }
  await waitFor(() => worldName.includes("hill_place_") && bot.game.gameMode === "creative", "private building arrival", 120_000);
  await bot.waitForChunksToLoad();
  await delay(1_000);
  const privateWorld = worldName;
  const arrival = bot.entity.position.clone();
  if (!isFloor(arrival.offset(0, -1, 0).floored())) throw new Error("Building arrival lacks a solid floor");
  console.log(`PASS: ${existingAccount ? "resumed saved Chapel entry" : "held map -> numbered chapel card -> confirmation -> private building"} ${privateWorld}`);
  if (process.env.HILL175_SMOKE_CAPTURE_ONLY === "1") {
    await retainPrivatePreview(privateWorld);
    return;
  }
  if (process.env.HILL175_SMOKE_RESET_ONLY === "1") {
    await resetBuilding(privateWorld);
    await retainPrivatePreview(privateWorld);
    return;
  }

  await placeAndBreak(findPatch(false), "outside the original footprint within its outdoor margin");
  await enterChapel();
  await placeAndBreak(findPatch(true), "inside the original building footprint");
  const mapStart = mapPackets.length;
  await holdItem("filled_map");
  await waitFor(() => mapPackets.slice(mapStart).some((packet) =>
    (packet.icons?.length ?? 0) >= 2 && packet.icons.some((icon) => icon.type === 0)), "building map markers and player cursor");
  console.log("PASS: campus map delivered building markers and the player's position cursor");

  await leaveChapel();
  await moveTo(bot.entity.position.offset(0, 128 - bot.entity.position.y, 0));
  await moveTo(new Vec3(region.minX - 2, 128, arrival.z));
  await waitFor(() => bot.game.gameMode === "spectator", "read-only mode beyond the build boundary");
  await moveTo(new Vec3(arrival.x, 128, arrival.z));
  await waitFor(() => bot.game.gameMode === "creative", "owner mode on boundary reentry");
  await moveTo(arrival);
  bot.chat("/hub");
  await waitFor(() => !worldName.includes("hill_place_"), "hub return");
  bot.chat("/entry home");
  await waitFor(() => worldName === privateWorld && bot.game.gameMode === "creative", "same saved building reentry");
  console.log("PASS: build boundary changed to read-only, reentry restored editing, and /hub -> /entry home retained the building");
  await resetBuilding(privateWorld);
  await retainPrivatePreview(privateWorld);
}

try {
  await runScenario();
} catch (error) {
  console.error(`FAIL: ${error.stack ?? error.message}`);
  console.error(`Transcript: ${transcript.join(" | ")}`);
  process.exitCode = 1;
} finally {
  bot.quit("Building selection smoke complete");
  bot.end("Building selection smoke complete");
  await delay(250);
}
process.exit(process.exitCode ?? 0);
