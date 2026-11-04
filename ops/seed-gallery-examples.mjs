import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Uses the retained local Chapel fixture from smoke-building-selection.mjs.
// Default publishes Place/People demos; "repair" revisits them through owner menus.
// All world edits, camera saves and submissions use the normal player protocol.
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDirectory, "..");
const fixture = JSON.parse(readFileSync(path.join(root, "runtime", "smoke-building-selection", "result.json"), "utf8"));
const dependencyRoot = process.env.HILL175_SMOKE_DEPS ?? path.join(root, "runtime", "smoke-bot", "mineflayer");
const requireDependencies = createRequire(path.join(dependencyRoot, "package.json"));
const mineflayer = existsSync(path.join(dependencyRoot, "index.js"))
  ? requireDependencies(path.join(dependencyRoot, "index.js")) : requireDependencies("mineflayer");
const { Vec3 } = requireDependencies("vec3");
const transcript = [];
const links = [];
const resultsPath = path.join(root, "runtime", "gallery-smoke-building-examples.json");
const examples = existsSync(resultsPath) ? JSON.parse(readFileSync(resultsPath, "utf8")) : [];
const outputDirectory = path.join(root, "runtime", "gallery-smoke-building-examples");
let worldName = "";
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const bot = mineflayer.createBot({
  host: process.env.HILL175_SMOKE_HOST ?? "127.0.0.1",
  port: Number(process.env.HILL175_SMOKE_PORT ?? "25566"),
  username: fixture.username,
  auth: "offline",
  plugins: { team: false },
});
const trackWorld = (packet) => {
  if (typeof packet?.worldState?.name === "string") worldName = packet.worldState.name;
};
bot._client.on("login", trackWorld);
bot._client.on("respawn", trackWorld);
bot.on("messagestr", (message) => {
  const clean = message.replaceAll(/\u00a7[0-9A-FK-OR]/gi, "");
  transcript.push(clean);
  console.log(clean);
});
bot.on("message", (message) => {
  for (const match of JSON.stringify(message.json ?? message).matchAll(/https?:\/\/[^"\\\s]+\/(?:preview|entries)\/[a-f0-9-]+/g)) {
    links.push(match[0]);
  }
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
  if (slot < 0) throw new Error(`Missing menu card: ${text}`);
  return slot;
}

async function command(commandText, expectedText, timeout = 15_000) {
  const start = transcript.length;
  bot.chat(commandText);
  await waitFor(() => transcript.slice(start).some((line) => line.includes(expectedText)), expectedText, timeout);
}

async function moveTo(target) {
  bot.physicsEnabled = false;
  const start = bot.entity.position.clone();
  const steps = Math.max(1, Math.ceil(start.distanceTo(target) / 0.4));
  for (let step = 1; step <= steps; step++) {
    const fraction = step / steps;
    const position = start.scaled(1 - fraction).plus(target.scaled(fraction));
    bot.entity.position.set(position.x, position.y, position.z);
    bot._client.write("position", { x: position.x, y: position.y, z: position.z,
      flags: { onGround: false, hasHorizontalCollision: false } });
    await delay(60);
  }
  await delay(400);
  if (bot.entity.position.distanceTo(target) > 1.5) throw new Error(`Movement was corrected at ${target}`);
}

function chapelPoint(u, v, y = 83) {
  const angle = 8.5 * Math.PI / 180;
  return new Vec3(2 * (u * Math.cos(angle) - v * Math.sin(angle)), y,
    2 * (u * Math.sin(angle) + v * Math.cos(angle)));
}

async function enterChapel() {
  await moveTo(bot.entity.position.offset(0, 128 - bot.entity.position.y, 0));
  await moveTo(chapelPoint(0, 34, 128));
  await moveTo(chapelPoint(0, 34));
  await moveTo(chapelPoint(0, 31));
  await moveTo(chapelPoint(0.40431417487584653, 29.76720561369499));
  const door = bot.findBlock({ matching: (block) => /_door$/.test(block.name), maxDistance: 5 });
  if (!door) throw new Error("Chapel entrance door not loaded");
  if (!door.getProperties().open) await bot.activateBlock(door);
  await moveTo(chapelPoint(-0.0021617057305829412, 27.047411989449717));
}

async function addAisleRunner() {
  const Item = requireDependencies("prismarine-item")(bot.registry);
  await moveTo(new Vec3(-3.5, 83.05, 25.5));
  await bot.creative.setInventorySlot(41, new Item(bot.registry.itemsByName.blue_carpet.id, 16));
  bot.setQuickBarSlot(5);
  bot._client.write("held_item_slot", { slotId: 5 });
  await delay(200);
  let placed = 0;
  for (const z of [24, 25, 26]) {
    const target = new Vec3(-6, 83, z);
    if (bot.blockAt(target, false)?.name === "blue_carpet") continue;
    if (bot.blockAt(target, false)?.name !== "air") continue;
    const support = bot.blockAt(target.offset(0, -1, 0));
    if (support?.name !== "smooth_stone") continue;
    await bot.placeBlock(support, new Vec3(0, 1, 0));
    await waitFor(() => bot.blockAt(target, false)?.name === "blue_carpet", "placed blue aisle carpet");
    placed++;
  }
  console.log(`Placed ${placed} blue carpet blocks through normal Creative use.`);
}

async function saveCamera(slot, position, target) {
  await moveTo(position);
  await bot.lookAt(target, true);
  bot._client.write("look", { yaw: (Math.PI - bot.entity.yaw) * 180 / Math.PI,
    pitch: -bot.entity.pitch * 180 / Math.PI,
    flags: { onGround: false, hasHorizontalCollision: false } });
  await delay(500);
  const start = transcript.length;
  const oldWindow = bot.currentWindow;
  bot.chat(`/camera save ${slot}`);
  await waitFor(() => (bot.currentWindow && bot.currentWindow !== oldWindow)
    || transcript.slice(start).some((line) => line.includes("Generating a server-rendered image")), `camera ${slot} save action`);
  if (bot.currentWindow && bot.currentWindow !== oldWindow) {
    await bot.clickWindow(findSlot(bot.currentWindow, "Confirm Replace"), 0, 0);
  }
  await waitFor(() => transcript.slice(start).some((line) => line.includes(`Camera ${slot} image is ready`)),
    `camera ${slot} image`, 180_000);
}

async function draftLink() {
  const start = links.length;
  bot.chat("/entry website");
  await waitFor(() => links.length > start, "current entry website link");
  return links.at(-1);
}

async function titleAndDescribe(title, description) {
  await command(`/entry title ${title}`, "Project title saved");
  await command(`/entry description ${description}`, "Project description saved");
}

async function submitAndRecord(category) {
  const previewUrl = await draftLink();
  const oldWindow = bot.currentWindow;
  bot.chat("/entry submit");
  await waitFor(() => bot.currentWindow && bot.currentWindow !== oldWindow, "normal submission confirmation");
  const start = transcript.length;
  await bot.clickWindow(findSlot(bot.currentWindow, "Confirm Submission"), 0, 0);
  await waitFor(() => transcript.slice(start).some((line) => line.includes("Entry submitted, published, and locked")),
    `${category} published submission`, 240_000);
  const preview = new URL(previewUrl);
  const response = await fetch(new URL(`/api${preview.pathname}`, preview));
  if (!response.ok) throw new Error(`Preview manifest returned ${response.status}`);
  const manifest = await response.json();
  if (!manifest.submitted || manifest.status !== "submitted") throw new Error("Entry did not become submitted");
  const publicUrl = new URL(`/entries/${manifest.id}`, preview).href;
  for (const image of manifest.images) {
    const imageResponse = await fetch(new URL(image.url, preview));
    if (!imageResponse.ok) throw new Error(`Published image returned ${imageResponse.status}`);
    writeFileSync(path.join(outputDirectory, `${category.toLowerCase()}-camera-${image.slot}.png`),
      Buffer.from(await imageResponse.arrayBuffer()));
  }
  const example = { category, title: manifest.title, entryId: manifest.id, publicUrl,
    previewUrl, imageCount: manifest.images.length, submitted: true, username: fixture.username };
  const index = examples.findIndex((previous) => previous.category === category);
  if (index < 0) examples.push(example);
  else examples[index] = example;
  writeFileSync(resultsPath, JSON.stringify(examples, null, 2) + "\n");
  console.log(`PUBLISHED: ${JSON.stringify(example)}`);
}

async function seedPlace() {
  bot.chat("/entry home");
  await waitFor(() => worldName === fixture.worldName && bot.game.gameMode === "creative", "retained editable Chapel entry");
  await bot.waitForChunksToLoad();
  await titleAndDescribe("Smoke test — Chapel remodel", "Demo entry: a short blue aisle runner in the installed Chapel shell. Front, side and interior views demonstrate the gallery; this is an automated staff smoke example.");
  await enterChapel();
  await addAisleRunner();
  await saveCamera(3, chapelPoint(0, 24), chapelPoint(0, 7, 85));
  await moveTo(chapelPoint(0, 27.047411989449717));
  await moveTo(chapelPoint(0.40431417487584653, 29.76720561369499));
  await moveTo(chapelPoint(0, 34));
  await moveTo(chapelPoint(0, 34, 128));
  await moveTo(new Vec3(34, 128, 30));
  await saveCamera(2, new Vec3(34, 98, 30), new Vec3(0, 94, 15));
  await submitAndRecord("Place");
}

async function seedPeople() {
  await command("/entry create people", "People entry created", 180_000);
  await waitFor(() => worldName.includes("hill_people_") && bot.game.gameMode === "creative", "private People campus arrival", 180_000);
  await bot.waitForChunksToLoad();
  await titleAndDescribe("Smoke test — Hill scene", "Demo campus scene from the installed Hill template. Two saved views around the Quad, Ryan Library and academic buildings. Created by the local automated smoke client for gallery browsing.");
  await saveCamera(1, new Vec3(206, 105, 45), new Vec3(270, 99, 46));
  await saveCamera(2, new Vec3(145, 108, 35), new Vec3(110, 94, 95));
  await submitAndRecord("People");
}

async function openOwnedExample(category, title) {
  const oldWindow = bot.currentWindow;
  bot.chat("/entry list");
  await waitFor(() => bot.currentWindow && bot.currentWindow !== oldWindow, "own entries menu");
  const main = bot.currentWindow;
  await bot.clickWindow(findSlot(main, title), 0, 0);
  await waitFor(() => bot.currentWindow && bot.currentWindow !== main, "example build controls");
  await bot.clickWindow(findSlot(bot.currentWindow, "Enter Build"), 0, 0);
  await waitFor(() => worldName.includes(`hill_${category.toLowerCase()}_`), `existing ${category} arrival`);
  await command("/entry unlock", "Submission unlocked");
  await waitFor(() => bot.game.gameMode === "creative", `editable ${category} example`);
  await bot.waitForChunksToLoad();
}

async function repairPlaceViews() {
  await openOwnedExample("Place", "Smoke test — Chapel remodel");
  await enterChapel();
  await saveCamera(3, chapelPoint(0, 24), chapelPoint(0, 7, 85));
  await moveTo(chapelPoint(0, 27.047411989449717));
  await moveTo(chapelPoint(0.40431417487584653, 29.76720561369499));
  await moveTo(chapelPoint(0, 34));
  await moveTo(chapelPoint(0, 34, 128));
  await moveTo(new Vec3(34, 128, 30));
  await saveCamera(2, new Vec3(34, 98, 30), new Vec3(0, 94, 15));
  await submitAndRecord("Place");
}

async function repairPeopleViews() {
  await openOwnedExample("People", "Smoke test — Hill scene");
  await saveCamera(1, new Vec3(206, 105, 45), new Vec3(270, 99, 46));
  await saveCamera(2, new Vec3(145, 108, 35), new Vec3(110, 94, 95));
  await submitAndRecord("People");
}

try {
  mkdirSync(outputDirectory, { recursive: true });
  await new Promise((resolve, reject) => {
    bot.once("spawn", resolve);
    bot.once("error", reject);
    bot.once("kicked", (reason) => reject(new Error(`Kicked: ${JSON.stringify(reason)}`)));
  });
  await command("/login SmokeTest123!", "Login successful");
  if (process.argv[2] === "repair") {
    await repairPlaceViews();
    await repairPeopleViews();
  } else {
    await seedPlace();
    await seedPeople();
  }
} catch (error) {
  console.error(error.stack ?? error.message);
  process.exitCode = 1;
} finally {
  bot.quit("Public gallery examples retained");
  bot.end("Public gallery examples retained");
  await delay(250);
}
process.exit(process.exitCode ?? 0);
