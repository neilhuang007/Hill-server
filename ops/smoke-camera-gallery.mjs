import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

// A development-server functional check. It creates and deletes only its own fresh Journey entry.
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dependencyRoot = process.env.HILL175_SMOKE_DEPS ?? path.join(repositoryRoot, "runtime", "smoke-bot", "mineflayer");
const requireDependencies = createRequire(path.join(dependencyRoot, "package.json"));
const mineflayer = existsSync(path.join(dependencyRoot, "index.js"))
  ? requireDependencies(path.join(dependencyRoot, "index.js")) : requireDependencies("mineflayer");
const { Vec3 } = requireDependencies("vec3");
const host = process.env.HILL175_SMOKE_HOST ?? "127.0.0.1";
const port = Number(process.env.HILL175_SMOKE_PORT ?? "25566");
const galleryBase = process.env.HILL175_GALLERY_URL ?? "http://127.0.0.1:8788";
const nonce = String(Date.now()).slice(-9);
const password = "GallerySmoke123!";
const title = `Gallery fixture ${nonce}`;
const artifactDirectory = process.env.HILL175_GALLERY_ARTIFACTS
  ?? path.join(repositoryRoot, "runtime", "camera-gallery-smoke", nonce);
const clients = [];
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
let owner;
let entryId;
let privateToken;
let isOwnEntryDeleted = false;

async function waitFor(predicate, description, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const result = await predicate();
    if (result) return result;
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

async function connect(username) {
  const bot = mineflayer.createBot({ host, port, username, auth: "offline", hideErrors: false, plugins: { team: false } });
  clients.push(bot);
  bot.history = [];
  bot.on("messagestr", message => bot.history.push(message.replaceAll(/\u00a7[0-9A-FK-OR]/gi, "")));
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Player connection timed out")), 60_000);
    bot.once("spawn", () => { clearTimeout(timeout); resolve(); });
    bot.once("error", error => { clearTimeout(timeout); reject(error); });
    bot.once("kicked", reason => { clearTimeout(timeout); reject(new Error(`Connection rejected: ${JSON.stringify(reason)}`)); });
  });
  await command(bot, `/register ${username} ${password} ${password}`, /Registration complete|Welcome to Hill/, "development authentication");
  return bot;
}

async function command(bot, text, pattern, description) {
  const start = bot.history.length;
  bot.chat(text);
  const message = await waitFor(() => bot.history.slice(start).find(line => pattern.test(line)), description);
  await delay(250);
  return message;
}

async function openWindow(bot, action, description) {
  return await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { bot.removeListener("windowOpen", opened); reject(new Error(`No ${description} opened`)); }, 10_000);
    const opened = window => { clearTimeout(timeout); resolve(window); };
    bot.once("windowOpen", opened);
    action();
  });
}

async function confirmCommand(bot, text, pattern, description) {
  const window = await openWindow(bot, () => bot.chat(text), `${description} confirmation`);
  if (window.slots[4]?.name !== "lime_concrete") throw new Error(`${description} had no explicit confirmation`);
  const start = bot.history.length;
  await bot.clickWindow(4, 0, 0);
  await waitFor(() => bot.history.slice(start).some(line => pattern.test(line)), description, 90_000);
}

async function json(endpoint, expectedStatus = 200) {
  const response = await fetch(new URL(endpoint, galleryBase), { signal: AbortSignal.timeout(5_000) });
  if (response.status !== expectedStatus) throw new Error(`Gallery returned ${response.status}, expected ${expectedStatus}`);
  return expectedStatus === 200 ? await response.json() : null;
}

async function draft() {
  return await json(`/api/preview/${privateToken}`);
}

async function waitForImages(expectedSlots) {
  return await waitFor(async () => {
    const manifest = await draft();
    return expectedSlots.every(slot => manifest.images.some(image => image.slot === slot)) ? manifest : null;
  }, `automatic camera images ${expectedSlots.join(",")}`, 180_000);
}

async function buildFixture() {
  const Item = requireDependencies("prismarine-item")(owner.version);
  await owner.waitForChunksToLoad();
  const ground = owner.blockAt(owner.entity.position.offset(0, -1, 3).floored());
  if (!ground || ground.name === "air") throw new Error("The fresh Journey fixture has no buildable ground");
  await owner.creative.setInventorySlot(38, new Item(owner.registry.itemsByName.gold_block.id, 16));
  owner.setQuickBarSlot(2);
  await delay(400);
  await owner.placeBlock(ground, new Vec3(0, 1, 0));
  const basePosition = ground.position.offset(0, 1, 0);
  await waitFor(() => owner.blockAt(basePosition)?.name === "gold_block", "actual player block placement");
  await owner.lookAt(basePosition.offset(0.5, 0.5, 0.5), true);
}

async function capture(slot) {
  await command(owner, `/camera save ${slot}`, new RegExp(`Camera ${slot}/3 saved`), `save camera slot ${slot}`);
}

async function saveEvidence(manifest) {
  const image = manifest.images.find(image => image.slot === 1);
  const response = await fetch(new URL(image.url, galleryBase));
  const bytes = Buffer.from(await response.arrayBuffer());
  if (response.status !== 200 || !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) || bytes.length < 100) {
    throw new Error("The saved camera did not produce an actual PNG image");
  }
  await mkdir(artifactDirectory, { recursive: true });
  await writeFile(path.join(artifactDirectory, "actual-player-camera-1.png"), bytes);
  await json(`/api/entries/${entryId}`, 404);
  const publicImage = image.url.split("?")[0];
  const denied = await fetch(new URL(publicImage, galleryBase));
  if (denied.status !== 404) throw new Error("An unpublished camera image was accessible without its private capability");
}

function itemText(item) {
  return item ? JSON.stringify([item.customName, ...(item.customLore ?? [])]) : "";
}

async function visitOwnFixture(visitor) {
  let menu = await openWindow(visitor, () => visitor.chat("/entry visit"), "visitor browser");
  let slot = -1;
  for (let page = 0; page < 64; page++) {
    slot = menu.slots.slice(0, menu.inventoryStart).findIndex(item => itemText(item).includes(title));
    if (slot >= 0 || !itemText(menu.slots[53]).includes("Next Page")) break;
    menu = await openWindow(visitor, () => visitor.clickWindow(53, 0, 0), "next visitor page");
  }
  if (slot < 0) throw new Error("Visitor browser did not include the fresh fixture entry");
  const start = visitor.history.length;
  await visitor.clickWindow(slot, 0, 0);
  await waitFor(() => visitor.history.slice(start).some(line => line.includes("Visitor Mode")), "visitor arrival");
  await command(visitor, "/camera remove 1", /editable entry|own.*entry|your editable entry/i, "visitor camera-removal denial");
  await command(visitor, "/entry title Unauthorized", /not one of your entries|own.*entry/i, "visitor metadata denial");
}

async function verifyStablePreview() {
  const packets = [];
  const record = packet => packets.push(packet.cameraId);
  owner._client.on("camera", record);
  try {
    await command(owner, "/camera preview 3", /Previewing camera slot 3/, "explicit slot-three preview");
    await delay(1_500);
    if (!packets.some(id => id !== owner.entity.id)) throw new Error("The preview never focused its fixed camera entity");
    if (packets.length > 4) throw new Error(`The fixed camera was reset ${packets.length} times; interpolation would restart every tick`);
    const settledCount = packets.length;
    await delay(750);
    if (packets.length !== settledCount) throw new Error("A settled camera kept receiving focus resets");
    await command(owner, "/camera exit", /Camera preview closed/, "camera return");
  } finally {
    owner._client.removeListener("camera", record);
  }
}

async function deleteOwnEntry() {
  if (!owner || !entryId || isOwnEntryDeleted || !owner._client.socket?.writable) return;
  await command(owner, "/entry unlock", /Submission unlocked/, "cleanup unlock");
  await confirmCommand(owner, "/entry delete", /Entry deleted/, "delete only the fresh fixture entry");
  isOwnEntryDeleted = true;
  await json(`/api/entries/${entryId}`, 404);
  await json(`/api/preview/${privateToken}`, 404);
}

try {
  await json("/health");
  owner = await connect(`Gallery${nonce}`);
  await command(owner, "/entry create journey", /Journey entry created/, "fresh Journey entry");
  await command(owner, `/entry title ${title}`, /Project title saved/, "fixture entry title");
  await buildFixture();
  await capture(1);
  const link = await waitFor(() => owner.history.find(line => /\/preview\/[A-Za-z0-9_-]{22,64}/.test(line)), "private draft link", 180_000);
  privateToken = link.match(/\/preview\/([A-Za-z0-9_-]{22,64})/)[1];
  let manifest = await draft();
  entryId = manifest.id;
  manifest = await waitForImages([1]);
  await saveEvidence(manifest);
  await capture(2);
  await capture(3);
  await waitForImages([1, 2, 3]);
  await verifyStablePreview();
  await confirmCommand(owner, "/camera remove 2", /Camera pose 2 removed/, "remove only slot two");
  manifest = await draft();
  if (manifest.images.some(image => image.slot === 2)) throw new Error("Removed camera image remains accessible in its draft");
  await capture(2);
  await waitForImages([1, 2, 3]);
  await confirmCommand(owner, "/camera save 2", /Camera 2\/3 updated/, "explicit camera replacement");
  await waitForImages([1, 2, 3]);

  const visitor = await connect(`Guest${nonce}`);
  await visitOwnFixture(visitor);
  await command(owner, `/team invite ${visitor.username}`, /Invite sent/, "owner team invite");
  await command(visitor, `/team accept ${owner.username}`, /Team invite accepted/, "teammate acceptance");
  await command(visitor, "/entry description Shared automated fixture", /Project description saved/, "teammate metadata authority");
  await confirmCommand(owner, "/entry submit", /Preparing your submission images/, "automatic submission preparation");
  await waitFor(() => owner.history.some(line => line.includes("submitted, published, and locked")), "automatic image refresh and publication", 240_000);
  const published = await json(`/api/entries/${entryId}`);
  if (!published.submitted || published.images.length !== 3) throw new Error("Submission published before all three images were prepared");
  if (!(await json("/api/entries")).entries.some(entry => entry.id === entryId)) throw new Error("Submitted entry is absent from public listing");
  for (const image of published.images) {
    if (image.url.includes("token=")) throw new Error("Public gallery leaked a private preview capability");
    if ((await fetch(new URL(image.url, galleryBase))).status !== 200) throw new Error("A submitted image was unavailable");
  }
  await command(visitor, "/team leave", /submitted and locked|being prepared/i, "submitted teammate leave denial");
  await command(owner, "/entry title Locked title", /submitted and locked/i, "submitted metadata denial");
  if (owner.game.gameMode !== "spectator" || visitor.game.gameMode !== "spectator") throw new Error("Both submitted team members must be read-only spectators");
  const reviewWait = Math.max(0, Math.min(60_000, Number(process.env.HILL175_GALLERY_REVIEW_WAIT_MS ?? "0")));
  if (reviewWait > 0) {
    await writeFile(path.join(artifactDirectory, "review.json"), JSON.stringify({
      entryId, path: `/entries/${entryId}`, status: "submitted", expiresAfterMilliseconds: reviewWait,
    }, null, 2));
    console.log(`REVIEW_READY: ${artifactDirectory}`);
    await delay(reviewWait);
  }
  await command(owner, "/entry unlock", /Submission unlocked/, "unlock and unpublish");
  await json(`/api/entries/${entryId}`, 404);
  if ((await json("/api/entries")).entries.some(entry => entry.id === entryId)) throw new Error("Unlocked entry remains publicly listed");
  if ((await fetch(new URL(published.images[0].url, galleryBase))).status !== 404) throw new Error("Unlocked image remains publicly accessible");
  if ((await draft()).images.length !== 3) throw new Error("Unlock discarded the team's private prepared preview");
  await command(visitor, "/team leave", /left the team|Lobby|hub/i, "editable teammate leave");
  await deleteOwnEntry();
  await writeFile(path.join(artifactDirectory, "result.json"), JSON.stringify({
    status: "passed", checkedAt: new Date().toISOString(), entryId, deleted: isOwnEntryDeleted,
    image: "actual-player-camera-1.png", renderer: "Server-rendered block perspective, not a client framebuffer screenshot",
  }, null, 2));
  console.log(`PASS: player placement, actual PNG capture, three slots, replacement/removal, stable camera packets, visitor/team authority, automatic publication, lock/unlock, and deletion. Evidence: ${artifactDirectory}`);
} catch (error) {
  process.exitCode = 1;
  console.error(`FAIL: ${error.stack ?? error.message}`);
  for (const bot of clients) {
    const safeLines = bot.history.slice(-16).map(line => line.replaceAll(/\/preview\/[A-Za-z0-9_-]+/g, "/preview/[redacted]")
      .replaceAll(/token=[A-Za-z0-9_-]+/g, "token=[redacted]"));
    console.error(`${bot.username}: ${safeLines.join(" | ")}`);
  }
  try { await deleteOwnEntry(); } catch (cleanupError) { console.error(`Fresh fixture cleanup needs retry: ${cleanupError.message}`); }
} finally {
  for (const bot of clients) { bot.quit?.("Gallery functional check complete"); bot.end?.("Gallery functional check complete"); }
  await delay(250);
}
process.exit(process.exitCode ?? 0);
