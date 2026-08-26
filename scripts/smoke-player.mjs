import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const dependencyRoot = process.env.HILL175_SMOKE_DEPS
  ?? path.resolve(scriptDirectory, "..", "runtime", "smoke-bot", "mineflayer");
const requireFromDependencies = createRequire(path.join(dependencyRoot, "package.json"));
const mineflayer = existsSync(path.join(dependencyRoot, "index.js"))
  ? requireFromDependencies(path.join(dependencyRoot, "index.js"))
  : requireFromDependencies("mineflayer");

const host = process.env.HILL175_SMOKE_HOST ?? "127.0.0.1";
const port = Number(process.env.HILL175_SMOKE_PORT ?? "25566");
const scenario = process.argv[2] ?? "lobby-return";
const username = `Smoke${String(Date.now()).slice(-9)}`;
const password = "SmokeTest123!";
const transcript = [];

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
  return await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      bot.removeListener("windowOpen", onWindowOpen);
      reject(new Error(`Timed out waiting for ${description}`));
    }, timeoutMilliseconds);
    const onWindowOpen = (window) => {
      clearTimeout(timeout);
      resolve(window);
    };
    bot.once("windowOpen", onWindowOpen);
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

async function authenticate() {
  bot.chat(`/register ${username} ${password} ${password}`);
  await waitFor(
    () => transcript.some((line) => line.includes("Registration complete") || line.includes("Welcome to Hill")),
    "development identity approval",
  );
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
  await delay(500);
  const hotbar = bot.inventory.slots.slice(36, 45);
  console.log(`Hotbar: ${hotbar.map((item, slot) => item ? `${slot}:${item.name}` : `${slot}:empty`).join(", ")}`);
  const compassSlot = hotbar.findIndex((item) => item?.name === "compass");
  if (compassSlot < 0) {
    throw new Error("The Competition Compass was missing from the authenticated hub hotbar");
  }
  bot.setQuickBarSlot(compassSlot);
  bot._client.write("held_item_slot", { slotId: compassSlot });
  await delay(150);
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
  console.log("PASS: People entry imported the structure.nbt world and auto-teleported the player when ready");
}

const bot = mineflayer.createBot({
  host,
  port,
  username,
  auth: "offline",
  hideErrors: false,
});

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
    case "create-flow-popup":
      await createFlowPopupScenario();
      break;
    case "people-import":
      await peopleImportScenario();
      break;
    case "navigation":
      await helpScenario();
      await lobbyReturnScenario();
      break;
    default:
      throw new Error(`Unknown scenario: ${scenario}`);
  }
} catch (error) {
  fail(error.stack ?? error.message);
} finally {
  bot.quit("Smoke test complete");
  await delay(250);
}
