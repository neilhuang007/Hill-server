import { createRequire } from 'node:module';
import { createHash, randomUUID } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = process.env.HILL175_SMOKE_DEPS ?? path.join(root, 'runtime/smoke-bot/mineflayer');
const require = createRequire(path.join(dependencies, 'package.json'));
const mineflayer = require(path.join(dependencies, 'index.js'));
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25568);
if (!['127.0.0.1', 'localhost'].includes(host)) throw Error('This smoke uses a local development account and requires loopback.');
const output = process.env.HILL175_HELD_MAP_REPORT ?? path.join(root, 'runtime/local-server-control/held-campus-map-smoke-report.json');
const run = String(Date.now()).slice(-9);
const account = { name: 'HeldMap' + run, password: 'Local' + randomUUID().replaceAll('-', '') };
const credentialPath = path.join(root, 'runtime/local-server-control', 'held-campus-map-credentials-' + run + '.json');
mkdirSync(path.dirname(credentialPath), { recursive: true });
writeFileSync(credentialPath, JSON.stringify(account));
const report = { host, port, run, checks: [], limitations: [
  'Protocol packets verify the delivered map. Native screen rendering is not visually certified.',
  'No resource pack is accepted. Held artwork is delivered using native map packets.'
] };
const bots = [];
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const mapId = item => item?.components?.find(component => component.type === 'map_id')?.data;

async function until(condition, label, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const failed = bots.find(bot => !bot.closed && bot.failure);
    if (failed) throw Error(failed.failure);
    if (condition()) return;
    await delay(100);
  }
  throw Error('Timed out: ' + label);
}

async function check(label, action) {
  await action();
  report.checks.push(label);
  console.log('PASS: ' + label);
}

function collectMap(bot, packet) {
  const frame = bot.maps.get(packet.itemDamage) ?? { pixels: Buffer.alloc(16384), covered: new Uint8Array(16384), packets: [], maxIcons: 0 };
  frame.maxIcons = Math.max(frame.maxIcons, packet.icons?.length ?? 0);
  frame.packets.push({ columns: packet.columns, rows: packet.rows ?? 0, x: packet.x ?? 0,
    y: packet.y ?? 0, bytes: packet.data?.length ?? 0, icons: packet.icons?.length ?? 0, locked: packet.locked });
  bot.maps.set(packet.itemDamage, frame);
  if (!packet.columns) return;
  if (packet.x + packet.columns > 128 || packet.y + packet.rows > 128 || packet.data.length !== packet.columns * packet.rows) {
    bot.failure = 'Malformed map image packet'; return;
  }
  for (let row = 0; row < packet.rows; row++) {
    const start = (packet.y + row) * 128 + packet.x;
    packet.data.copy(frame.pixels, start, row * packet.columns, (row + 1) * packet.columns);
    frame.covered.fill(1, start, start + packet.columns);
  }
}

function watchInventory(bot) {
  const acknowledge = item => {
    const Item = require('prismarine-item')(bot.registry);
    const parsed = Item.fromNotch(item);
    if (parsed?.name === 'filled_map') bot.mapCorrections.push({ mapId: mapId(parsed), receivedAt: Date.now() });
  };
  bot._client.on('set_slot', packet => { if (packet.windowId === 0 && packet.slot === 44) acknowledge(packet.item); });
  bot._client.on('set_player_inventory', packet => { if ([8, 44].includes(packet.slotId)) acknowledge(packet.contents); });
  bot._client.on('window_items', packet => { if (packet.windowId === 0 && packet.items[44]) acknowledge(packet.items[44]); });
}

async function connect(returning = false) {
  const bot = mineflayer.createBot({ host, port, username: account.name, auth: 'offline', plugins: { team: false } });
  bots.push(bot);
  Object.assign(bot, { lines: [], maps: new Map(), dialogs: [], windows: [], packs: [], mapCorrections: [], worldName: '' });
  bot.on('messagestr', line => bot.lines.push(line));
  bot.on('error', error => { bot.failure = error.message; });
  bot.on('kicked', reason => { bot.failure = 'Kicked: ' + JSON.stringify(reason); });
  bot.on('end', () => { bot.hasEnded = true; });
  for (const event of ['login', 'respawn']) bot._client.on(event, packet => { bot.worldName = packet?.worldState?.name ?? bot.worldName; });
  bot._client.on('map', packet => collectMap(bot, packet));
  bot._client.on('show_dialog', packet => bot.dialogs.push(packet));
  bot._client.on('open_window', packet => bot.windows.push(packet));
  bot._client.on('add_resource_pack', packet => {
    bot.packs.push(packet);
    bot._client.write('resource_pack_receive', { uuid: packet.uuid, result: 1 });
  });
  watchInventory(bot);
  const prompt = returning ? '/login ' : '/register ';
  await until(() => bot.entity && bot.lines.some(line => line.includes(prompt)), 'account admission', 90000);
  bot.chat(returning ? `/login ${account.password}` : `/register ${account.password} ${account.password}`);
  await until(() => bot.lines.some(line => /Registration complete|Login successful/.test(line)), 'authentication');
  await until(() => bot.worldName.split(':').at(-1) === 'hill_campus' && bot.game.gameMode === 'creative', 'shared campus entry', 60000);
  return bot;
}

function assertTools(bot) {
  if (bot.inventory.slots[44]?.name !== 'filled_map') throw Error('Hotbar slot nine is not a filled map.');
  if (bot.inventory.slots[43]?.name !== 'clock') throw Error('Hotbar slot eight is not the undo clock.');
  const mapSlots = bot.inventory.slots.flatMap((item, slot) => item?.name === 'filled_map' ? [slot] : []);
  if (mapSlots.length !== 1 || mapSlots[0] !== 44) throw Error('The campus map is duplicated or outside slot nine: ' + mapSlots.join(','));
  if (!Number.isInteger(mapId(bot.inventory.slots[44]))) throw Error('The held map has no integer MAP_ID component.');
}

async function holdAndRead(bot) {
  assertTools(bot);
  const id = mapId(bot.inventory.slots[44]);
  bot.setQuickBarSlot(8);
  bot._client.write('held_item_slot', { slotId: 8 });
  await until(() => bot.heldItem?.name === 'filled_map' && mapId(bot.heldItem) === id, 'map selected in hand');
  await until(() => bot.maps.get(id)?.covered.every(value => value === 1), 'complete 128 by 128 map image');
  const frame = bot.maps.get(id);
  const colors = new Set(frame.pixels).size;
  if (colors < 16 || frame.pixels.filter(value => value >= 4).length < 8192) throw Error('Map pixels are empty or trivial.');
  if (frame.maxIcons !== 0) throw Error('The oblique illustration incorrectly contains map cursors.');
  return { mapId: id, width: 128, height: 128, colors, iconCount: frame.maxIcons,
    paletteSha256: createHash('sha256').update(frame.pixels).digest('hex'), packets: frame.packets.slice(0, 20) };
}

async function protectSlot(bot, action) {
  const originalId = mapId(bot.inventory.slots[44]);
  const before = bot.mapCorrections.length;
  action();
  await until(() => bot.mapCorrections.slice(before).some(item => item.mapId === originalId), 'authoritative map slot correction');
  await delay(400);
  assertTools(bot);
  if (mapId(bot.inventory.slots[44]) !== originalId) throw Error('Protected map changed identity.');
}

async function disconnect(bot) {
  bot.closed = true;
  bot.quit('Held campus map smoke');
  await until(() => bot.hasEnded, 'client disconnect', 10000);
}

try {
  const bot = await connect();
  report.minecraftVersion = bot.version;
  await check('Fresh registration gives one map in hotbar nine and undo clock in hotbar eight', async () => {
    await until(() => bot.inventory.slots[44]?.name === 'filled_map' && bot.inventory.slots[43]?.name === 'clock', 'campus tools');
    assertTools(bot);
  });
  await check('Held map receives complete detailed artwork without a misleading cursor', async () => { report.initialMap = await holdAndRead(bot); });
  await check('Creative overwrite is rejected with an authoritative map correction', async () => {
    const Item = require('prismarine-item')(bot.registry);
    await protectSlot(bot, () => bot._client.write('set_creative_slot', { slot: 44,
      item: Item.toNotch(new Item(bot.registry.itemsByName.stone.id, 1)) }));
  });
  await check('Dropping the held map is rejected and preserves slot nine', async () => {
    await protectSlot(bot, () => bot._client.write('block_dig', { status: 4, location: { x: 0, y: 0, z: 0 }, face: 0, sequence: 0 }));
  });
  await check('Right click in air opens a native dialog rather than an inventory window', async () => {
    const dialogs = bot.dialogs.length, windows = bot.windows.length;
    bot.activateItem();
    await until(() => bot.dialogs.length > dialogs, 'native campus dialog');
    await delay(400);
    if (bot.windows.length !== windows) throw Error('Air click also opened an inventory window.');
    const dialog = JSON.stringify(bot.dialogs.at(-1), (_key, value) => typeof value === 'bigint' ? value.toString() : value);
    if (!dialog.includes('Hill Campus Map')) throw Error('The native dialog is not the Hill Campus Map.');
    report.dialog = { packet: 'show_dialog', payloadBytes: Buffer.byteLength(dialog), inventoryWindowsOpened: 0,
      resourcePackAccepted: false, resourcePackOffersDeclined: bot.packs.length };
    bot.deactivateItem();
  });
  await check('Building navigation keeps the map and undo clock in their fixed slots', async () => {
    const previous = bot.entity.position.clone();
    bot.chat('/campus go alumni-chapel');
    await until(() => bot.entity.position.distanceTo(previous) > 4, 'navigation to Alumni Chapel');
    await delay(300);
    assertTools(bot);
    if (bot.worldName.split(':').at(-1) !== 'hill_campus') throw Error('Navigation left the shared campus.');
  });
  await disconnect(bot);
  const returning = await connect(true);
  await check('Reconnect preserves slot placement and delivers identical official map pixels', async () => {
    await until(() => returning.inventory.slots[44]?.name === 'filled_map', 'returning campus tools');
    report.reconnectedMap = await holdAndRead(returning);
    if (report.reconnectedMap.paletteSha256 !== report.initialMap.paletteSha256) throw Error('Official map pixels changed after reconnecting.');
  });
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.failure = error.stack ?? String(error);
  console.error(report.failure);
  process.exitCode = 1;
} finally {
  mkdirSync(path.dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2));
  for (const bot of bots) { bot.closed = true; bot.quit('Held campus map smoke complete'); }
  console.log('Report: ' + output);
}
await delay(500);
process.exit(process.exitCode ?? 0);
