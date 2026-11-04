import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = process.env.HILL175_SMOKE_DEPS ?? path.join(root, 'runtime/smoke-bot/mineflayer');
const require = createRequire(path.join(dependencies, 'package.json'));
const mineflayer = require(path.join(dependencies, 'index.js'));
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25568);
const run = String(Date.now()).slice(-9);
const bots = [];
const report = { host, port, run, checks: [], limitations: [
  'Resource pack success is simulated by protocol status after its bytes and hash are verified.',
  'This does not certify native image rendering, pointer ergonomics or a native Bedrock form.',
  'Native screenshot helper is unavailable in this environment.'
] };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function itemText(item) { return JSON.stringify([item?.customName, item?.customLore]); }
function top(bot) { return bot.currentWindow?.slots.slice(0, bot.currentWindow.inventoryStart) ?? []; }
function model(item) { return item?.components?.find(component => component.type === 'item_model')?.data; }
function title(bot) { return JSON.stringify(bot.currentWindow?.title); }
async function until(test, label, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const failed = bots.find(bot => bot.failure);
    if (failed) throw Error(failed.username + ': ' + failed.failure);
    if (test()) return;
    await delay(100);
  }
  throw Error('Timed out: ' + label);
}
async function check(label, action) {
  await action();
  report.checks.push(label);
  console.log('PASS: ' + label);
}
function connect(name) {
  const bot = mineflayer.createBot({ host, port, username: name, auth: 'offline', plugins: { team: false } });
  bots.push(bot);
  bot.lines = []; bot.packs = []; bot.worldName = ''; bot.lastStateId = 0;
  bot.on('messagestr', line => bot.lines.push(line));
  bot.on('error', error => { bot.failure = error.message; });
  bot.on('kicked', reason => { bot.failure = 'Kicked: ' + JSON.stringify(reason); });
  for (const event of ['login', 'respawn']) bot._client.on(event, packet => { bot.worldName = packet?.worldState?.name ?? bot.worldName; });
  for (const event of ['window_items', 'set_slot']) bot._client.on(event, packet => { bot.lastStateId = packet.stateId ?? bot.lastStateId; });
  bot._client.on('add_resource_pack', packet => bot.packs.push(packet));
  return bot;
}
async function login(bot) {
  await until(() => bot.entity && bot.lines.some(line => line.includes('/register')), 'admission', 60000);
  bot.chat('/register CanvasLocal123! CanvasLocal123!');
  await until(() => bot.lines.some(line => line.includes('Registration complete')), 'authentication');
}
async function open(bot, action, expected) {
  const previous = bot.currentWindow;
  await action();
  await until(() => bot.currentWindow && bot.currentWindow !== previous && title(bot).includes(expected), expected);
}
async function click(bot, slot) { await bot.clickWindow(slot, 0, 0); await delay(150); }
function slotByText(bot, label) {
  const slot = top(bot).findIndex(item => itemText(item).includes(label));
  if (slot < 0) throw Error('Missing menu action: ' + label);
  return slot;
}
function rawClick(bot, windowId, slot) {
  bot._client.write('window_click', { windowId, stateId: bot.lastStateId, slot,
    mouseButton: 0, mode: 0, changedSlots: [], cursorItem: null });
}

try {
  const owner = connect('Canvas' + run);
  await until(() => owner.entity && owner.lines.some(line => line.includes('/register')), 'owner admission', 60000);
  await check('Unauthenticated student cannot open the campus selection', async () => {
    owner.chat('/campus');
    await delay(1000);
    if (owner.currentWindow) throw Error('Unauthenticated student opened a campus menu');
  });
  await login(owner);
  await open(owner, () => owner.chat('/campus map'), 'Choose your campus starting point');
  await check('Map has 45 server owned tiles, inactive border and clear named controls', async () => {
    const items = top(owner);
    if (items.length !== 54 || items.slice(0, 45).some(item => !item)) throw Error('Map tile coverage is incomplete');
    if (!itemText(items[0]).includes('Campus map border') || !itemText(items[8]).includes('Campus map border')) throw Error('Letterbox cells are not identified');
    if (!itemText(items[48]).includes('Explore Campus') || !itemText(items[50]).includes('Find a Building')) throw Error('Campus actions moved or are absent');
    if (items.slice(0, 45).some(model)) throw Error('Custom models were sent before resource pack success');
    const map = owner.currentWindow;
    await click(owner, 0);
    if (owner.currentWindow !== map) throw Error('Letterbox click selected an area');
  });
  await check('Optional pack matches its advertised SHA1 and fixed local HTTP route', async () => {
    await until(() => owner.packs.length > 0, 'resource pack offer');
    const offer = owner.packs.at(-1);
    const url = new URL(offer.url);
    if (url.pathname !== '/campus-pack.zip' || offer.forced) throw Error('Unexpected or mandatory campus pack');
    const response = await fetch(offer.url);
    if (!response.ok || response.headers.get('content-type') !== 'application/zip') throw Error('Pack HTTP route failed');
    const bytes = Buffer.from(await response.arrayBuffer());
    const hash = createHash('sha1').update(bytes).digest('hex');
    if (hash !== offer.hash) throw Error('Offered pack hash differs from downloaded bytes');
    report.pack = { url: offer.url, sha1: hash, bytes: bytes.length };
    owner._client.write('resource_pack_receive', { uuid: offer.uuid, result: 1 });
  });
  await check('Named building fallback works when the resource pack is declined', async () => {
    await open(owner, () => click(owner, 50), 'Choose a Building');
    await open(owner, () => click(owner, slotByText(owner, 'Alumni Chapel')), 'Confirm your destination');
    if (!itemText(top(owner)[13]).includes('Alumni Chapel')) throw Error('Selected building name is incorrect');
    await open(owner, () => click(owner, 23), 'Choose your campus starting point');
  });
  await check('Accepted pack applies the correct distinct item model to every map tile', async () => {
    const previousOffers = owner.packs.length;
    await open(owner, () => click(owner, 53), 'Choose your campus starting point');
    await until(() => owner.packs.length > previousOffers, 'new explicit pack offer');
    const offer = owner.packs.at(-1);
    owner._client.write('resource_pack_receive', { uuid: offer.uuid, result: 3 });
    owner._client.write('resource_pack_receive', { uuid: offer.uuid, result: 0 });
    await until(() => top(owner).slice(0, 45).every((item, slot) => model(item) === 'hill175:campus/tile_' + slot), 'tile model assignment');
  });
  let staleWindow;
  await check('Central image tile maps to Alumni Chapel and confirmation preserves the selection', async () => {
    staleWindow = owner.currentWindow.id;
    await open(owner, () => click(owner, 30), 'Choose a starting point in this area');
    await open(owner, () => click(owner, slotByText(owner, 'Alumni Chapel')), 'Confirm your destination');
    if (!itemText(top(owner)[13]).includes('Alumni Chapel')) throw Error('Map click selected the wrong building');
  });
  await check('Stale inventory packets and shift clicks cannot move a student', async () => {
    const confirmation = owner.currentWindow;
    const world = owner.worldName;
    rawClick(owner, staleWindow, 48);
    await delay(500);
    await owner.clickWindow(21, 0, 1);
    await delay(500);
    if (owner.currentWindow !== confirmation || owner.worldName !== world) throw Error('Stale or shifted click invoked a selection');
    await open(owner, () => click(owner, 23), 'Choose your campus starting point');
  });
  await check('Explore Campus enters the shared creative campus after confirmation', async () => {
    await open(owner, () => click(owner, 48), 'Confirm your destination');
    await click(owner, 21);
    await until(() => owner.worldName.split(':').at(-1) === 'hill_campus' && owner.game.gameMode === 'creative', 'shared campus arrival', 60000);
    report.world = owner.worldName;
  });
  await check('Another unauthenticated connection cannot act using the owner menu identifier', async () => {
    const guest = connect('CanvasG' + run);
    await until(() => guest.entity && guest.lines.some(line => line.includes('/register')), 'guest admission', 60000);
    rawClick(guest, staleWindow, 21);
    guest.chat('/campus');
    await delay(1000);
    if (guest.currentWindow || guest.worldName.split(':').at(-1) === 'hill_campus') throw Error('Guest entered the campus through a forged menu');
    if (owner.worldName !== report.world || owner.game.gameMode !== 'creative') throw Error('Guest changed the owner session');
    await login(guest);
    await open(guest, () => guest.chat('/campus map'), 'Choose your campus starting point');
    await open(guest, () => click(guest, 48), 'Confirm your destination');
    await click(guest, 21);
    await until(() => guest.worldName === owner.worldName && guest.game.gameMode === 'creative', 'both students in shared campus', 60000);
    report.checks.push('Two authenticated students join the same shared creative campus');
  });
  report.passed = true;
} catch (error) {
  report.passed = false; report.failure = error.stack ?? String(error); process.exitCode = 1;
  console.error(report.failure);
} finally {
  report.players = bots.map(bot => ({ username: bot.username, messages: bot.lines, failure: bot.failure }));
  const output = process.env.HILL175_CANVAS_REPORT ?? path.join(root, 'runtime/local-server-control/canvas-smoke-report.json');
  mkdirSync(path.dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2));
  for (const bot of bots) bot.quit('Campus map smoke complete');
  console.log('Report: ' + output);
}
