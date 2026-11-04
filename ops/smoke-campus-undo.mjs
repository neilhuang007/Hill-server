import { createRequire } from 'node:module';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = process.env.HILL175_SMOKE_DEPS ?? path.join(root, 'runtime/smoke-bot/mineflayer');
const require = createRequire(path.join(dependencies, 'package.json'));
const mineflayer = existsSync(path.join(dependencies, 'index.js'))
  ? require(path.join(dependencies, 'index.js')) : require('mineflayer');
const { Vec3 } = require('vec3');
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25568);
const maximumMs = Number(process.env.HILL175_UNDO_TIMEOUT_MS ?? 600000);
const cases = process.env.HILL175_UNDO_SMOKE_CASES ?? 'all';
if (!['all', 'beds'].includes(cases)) throw Error('HILL175_UNDO_SMOKE_CASES must be all or beds.');
const output = path.resolve(process.env.HILL175_UNDO_REPORT ?? path.join(root, 'runtime/local-server-control/undo-smoke-report.json'));
if (!Number.isInteger(port) || port < 1 || port > 65535 || maximumMs < 30000 || !Number.isFinite(maximumMs)) {
  throw Error('Invalid smoke port or overall timeout.');
}
const run = Date.now().toString().slice(-9);
const password = 'Undo' + run + '!';
const report = { host, port, run, cases, startedAt: new Date().toISOString(), checks: [], messages: [], success: false };
const bots = [];
const owned = new Map();
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const coordinates = value => ({ x: value.x, y: value.y, z: value.z });
const isAir = block => block && ['air', 'cave_air', 'void_air'].includes(block.name);
let alice;
let bob;
let floor;
let finished = false;

function assert(condition, message) { if (!condition) throw Error(message); }
function connected() {
  const failed = bots.find(bot => bot.failure);
  if (failed) throw Error(`${failed.username}: ${failed.failure}`);
}

function save() {
  mkdirSync(path.dirname(output), { recursive: true });
  report.ownedBlocks = [...owned.values()].map(item => ({ position: coordinates(item.position), expected: [...item.expected] }));
  const json = JSON.stringify(report, null, 2);
  writeFileSync(output, json);
  const parts = path.parse(output);
  writeFileSync(path.join(parts.dir, parts.name + '-' + run + (parts.ext || '.json')), json);
}

async function until(predicate, description, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    connected();
    if (predicate()) return;
    await delay(100);
  }
  throw Error('Timed out: ' + description);
}

async function check(name, action) {
  const result = { name, success: false };
  report.checks.push(result);
  try { result.evidence = await action(); result.success = true; console.log('PASS: ' + name); }
  catch (error) { result.error = String(error.stack ?? error); throw error; }
  finally { save(); }
}

async function connect(name) {
  const bot = mineflayer.createBot({ host, port, username: name, auth: 'offline', plugins: { team: false } });
  bots.push(bot);
  bot.lines = [];
  bot.sequence = 0;
  const dimension = packet => { bot.worldId = packet?.worldState?.name?.split(':').at(-1) ?? bot.worldId; };
  bot._client.on('login', dimension);
  bot._client.on('respawn', dimension);
  bot.on('messagestr', text => {
    bot.lines.push(text);
    report.messages.push({ player: name, text });
    console.log(name + ': ' + text);
  });
  bot.on('error', error => { bot.failure = String(error); });
  bot.on('kicked', reason => { bot.failure = 'Kicked: ' + JSON.stringify(reason); });
  bot.on('end', reason => { if (!finished) bot.failure = 'Disconnected: ' + reason; });
  await until(() => bot.entity && bot.lines.some(text => /register|login/i.test(text)), 'login admission', 60000);
  bot.chat(`/register ${password} ${password}`);
  await until(() => bot.lines.some(text => /Registration complete/i.test(text)), 'development registration', 60000);
  await until(() => bot.worldId === 'hill_campus' && bot.game?.gameMode === 'creative', 'shared campus arrival', 120000);
  bot.physicsEnabled = false;
  await until(() => bot.blockAt(bot.entity.position.floored()) != null, 'campus chunks', 60000);
  return bot;
}

async function move(bot, target) {
  connected();
  bot.physicsEnabled = false;
  const start = bot.entity.position.clone();
  const steps = Math.max(1, Math.ceil(start.distanceTo(target) / 0.5));
  assert(steps <= 600, 'Smoke movement exceeds 300 blocks.');
  for (let step = 1; step <= steps; step++) {
    const current = start.scaled(1 - step / steps).plus(target.scaled(step / steps));
    bot.entity.position.set(current.x, current.y, current.z);
    bot._client.write('position', { x: current.x, y: current.y, z: current.z,
      flags: { onGround: false, hasHorizontalCollision: false } });
    await delay(50);
  }
  await delay(200);
  assert(bot.entity.position.distanceTo(target) < 1.5, 'Server corrected smoke movement.');
}

async function hold(bot, material) {
  const Item = require('prismarine-item')(bot.registry);
  const item = bot.registry.itemsByName[material];
  assert(item, 'Unknown item ' + material);
  await bot.creative.setInventorySlot(41, new Item(item.id, Math.min(32, item.stackSize ?? 64)));
  bot.setQuickBarSlot(5);
  bot._client.write('held_item_slot', { slotId: 5 });
  await delay(150);
}

function own(target, material) {
  let item = owned.get(target.toString());
  if (!item) { item = { position: target.clone(), expected: new Set() }; owned.set(target.toString(), item); }
  item.expected.add(material);
}

async function place(bot, target, material) {
  assert(isAir(bot.blockAt(target)), 'Occupied placement target ' + target);
  const offsets = [new Vec3(0, -1, 0), new Vec3(-1, 0, 0), new Vec3(1, 0, 0), new Vec3(0, 0, -1), new Vec3(0, 0, 1)];
  const offset = offsets.find(value => bot.blockAt(target.plus(value))?.boundingBox === 'block');
  assert(offset, 'Missing support ' + target);
  own(target, material);
  await move(bot, target.offset(0.5, 2, 0.5));
  await hold(bot, material);
  const support = target.plus(offset);
  const face = offset.scaled(-1);
  const cursor = new Vec3(0.5 + face.x * 0.5, 0.5 + face.y * 0.5, 0.5 + face.z * 0.5);
  await bot.lookAt(support.plus(cursor), true);
  const direction = face.y < 0 ? 0 : face.y > 0 ? 1 : face.z < 0 ? 2 : face.z > 0 ? 3 : face.x < 0 ? 4 : 5;
  bot._client.write('block_place', { location: support, direction, hand: 0,
    cursorX: cursor.x, cursorY: cursor.y, cursorZ: cursor.z,
    insideBlock: false, sequence: ++bot.sequence, worldBorderHit: false });
  bot.swingArm();
  await until(() => bot.blockAt(target)?.name === material, 'placed ' + material + ' at ' + target);
  await delay(200);
}

async function remove(bot, target) {
  if (isAir(bot.blockAt(target))) return;
  await move(bot, target.offset(0.5, 2, 0.5));
  await hold(bot, 'stick');
  await bot.lookAt(target.offset(0.5, 0.5, 0.5), true);
  // Raw Creative dig waits for the server packet. Mineflayer dig predicts AIR locally.
  bot._client.write('block_dig', { status: 0, location: target, face: 1, sequence: ++bot.sequence });
  await until(() => isAir(bot.blockAt(target)), 'server acknowledged block break ' + target);
  await delay(200);
}

async function undo(bot, useClock = false) {
  const index = bot.lines.length;
  if (useClock) {
    const slot = bot.inventory.slots.findIndex((item, index) => index >= 36 && index <= 44 && item?.name === 'clock');
    assert(slot >= 36, 'Protected Undo clock missing from hotbar.');
    bot.setQuickBarSlot(slot - 36);
    bot._client.write('held_item_slot', { slotId: slot - 36 });
    await delay(200);
    bot.activateItem();
  } else bot.chat('/campus undo');
  await until(() => bot.lines.slice(index).some(text => /Undid \d+ block changes|No safe building edits/.test(text)), 'Undo result');
  await delay(300);
  return bot.lines.slice(index).filter(text => /Undid |No safe |Skipped /.test(text));
}

async function setup() {
  alice = await connect('UndoA' + run);
  bob = await connect('UndoB' + run);
  const spawn = alice.entity.position.floored();
  let ground;
  for (let y = spawn.y + 4; y >= spawn.y - 24 && !ground; y--) {
    const candidate = new Vec3(spawn.x + 7, y, spawn.z + 2);
    if (alice.blockAt(candidate)?.boundingBox === 'block' && isAir(alice.blockAt(candidate.offset(0, 1, 0)))) ground = candidate;
  }
  assert(ground, 'No nearby solid support for isolated smoke platform.');
  floor = ground.offset(0, 5, 0);
  for (let x = 0; x < 5; x++) for (let z = 0; z < 5; z++) {
    for (let y = 0; y <= 3; y++) assert(isAir(alice.blockAt(floor.offset(x, y, z))), 'Platform envelope contains existing blocks.');
  }
  report.fixture = { world: 'hill_campus', ground: coordinates(ground), floor: coordinates(floor) };
  for (let height = 1; height <= 5; height++) await place(bob, ground.offset(0, height, 0), 'cobblestone');
  for (let x = 0; x < 5; x++) for (let z = 0; z < 5; z++) {
    if (x || z) await place(bob, floor.offset(x, 0, z), 'cobblestone');
  }
  save();
  // Fixture edits must expire before Bob's first Undo.
  if (cases === 'all') await delay(16000);
}

async function ordinaryChecks(target) {
  await check('Peer undo cannot reenable an older actor undo', async () => {
    await place(alice, target, 'stone');
    await until(() => bob.blockAt(target)?.name === 'stone', 'peer received placement');
    await remove(bob, target);
    const bobResult = await undo(bob);
    assert(bob.blockAt(target)?.name === 'stone', 'Peer Undo did not restore stone.');
    const aliceResult = await undo(alice);
    assert(alice.blockAt(target)?.name === 'stone', 'Alice Undo overwrote a peer restoration.');
    assert(aliceResult.some(text => /Skipped/.test(text)), 'Missing conflict feedback.');
    await remove(bob, target);
    return { position: coordinates(target), bobResult, aliceResult, retainedMaterial: 'stone' };
  });
  await check('Undo clock right click removes an ordinary placed block', async () => {
    await place(alice, target, 'stone');
    const result = await undo(alice, true);
    assert(isAir(alice.blockAt(target)), 'Placed stone was not removed.');
    return { result, finalMaterial: alice.blockAt(target).name };
  });
  await check('Ordinary break Undo restores the original block', async () => {
    await place(bob, target, 'stone');
    await until(() => alice.blockAt(target)?.name === 'stone', 'original stone visible');
    await remove(alice, target);
    const result = await undo(alice);
    assert(alice.blockAt(target)?.name === 'stone', 'Broken stone was not restored.');
    return { result, finalMaterial: 'stone' };
  });
  await check('Multiple edits of the same block reverse in chronological order', async () => {
    await remove(alice, target);
    await place(alice, target, 'bricks');
    await remove(alice, target);
    await place(alice, target, 'oak_planks');
    const result = await undo(alice);
    assert(alice.blockAt(target)?.name === 'stone', 'Edit sequence did not restore original stone.');
    await remove(bob, target);
    return { result, finalMaterial: 'stone' };
  });
  await check('Same material peer replacement is an ABA conflict', async () => {
    await place(alice, target, 'stone');
    await until(() => bob.blockAt(target)?.name === 'stone', 'peer sees original');
    await remove(bob, target);
    await place(bob, target, 'stone');
    const result = await undo(alice);
    assert(alice.blockAt(target)?.name === 'stone', 'Undo removed peer replacement.');
    assert(result.some(text => /Skipped/.test(text)), 'Missing same material conflict feedback.');
    await remove(bob, target);
    return { result, retainedMaterial: 'stone' };
  });
}

function groupAt(bot, target, material) {
  const offsets = material.endsWith('_door') ? [new Vec3(0, 1, 0)]
    : [new Vec3(1, 0, 0), new Vec3(-1, 0, 0), new Vec3(0, 0, 1), new Vec3(0, 0, -1)];
  const other = offsets.map(offset => target.plus(offset)).find(position => bot.blockAt(position)?.name === material);
  assert(other, 'Missing second part of ' + material);
  own(other, material);
  return [target, other].map(position => ({ position, stateId: bot.blockAt(position).stateId }));
}

async function groupChecks(target, material) {
  await check(material + ' placement Undo removes both parts', async () => {
    await place(alice, target, material);
    const group = groupAt(alice, target, material);
    const result = await undo(alice);
    assert(group.every(item => isAir(alice.blockAt(item.position))), 'Undo left an orphan ' + material + ' part.');
    return { result, parts: group.map(item => coordinates(item.position)) };
  });
  await check(material + ' break Undo restores both exact block states', async () => {
    await place(bob, target, material);
    await until(() => alice.blockAt(target)?.name === material, 'group visible to builder');
    const group = groupAt(alice, target, material);
    await remove(alice, target);
    assert(group.every(item => isAir(alice.blockAt(item.position))), 'Vanilla break left a group part.');
    const result = await undo(alice);
    assert(group.every(item => alice.blockAt(item.position)?.stateId === item.stateId), 'Undo did not restore exact paired states.');
    await remove(bob, target);
    return { result, parts: group.map(item => ({ position: coordinates(item.position), stateId: item.stateId })) };
  });
}

async function cleanup() {
  report.cleanup = { removed: 0, retained: [] };
  const bot = alice?.failure ? bob : alice;
  if (!bot?.entity) return;
  for (const item of [...owned.values()].sort((a, b) => b.position.y - a.position.y)) {
    const material = bot.blockAt(item.position)?.name;
    if (isAir(bot.blockAt(item.position))) continue;
    if (!item.expected.has(material)) {
      report.cleanup.retained.push({ position: coordinates(item.position), material: material ?? 'unloaded', reason: 'unexpected material' });
      continue;
    }
    try { await remove(bot, item.position); report.cleanup.removed++; }
    catch (error) { report.cleanup.retained.push({ position: coordinates(item.position), material, reason: error.message }); }
  }
  save();
}

const timer = setTimeout(() => {
  report.error = 'Overall smoke timeout. Inspect ownedBlocks before any cleanup.';
  report.completedAt = new Date().toISOString();
  save();
  finished = true;
  bots.forEach(bot => bot.quit());
  process.exit(1);
}, maximumMs);

try {
  await setup();
  const target = floor.offset(2, 1, 2);
  if (cases === 'all') {
    await ordinaryChecks(target);
    await groupChecks(target, 'oak_door');
  }
  await groupChecks(target, 'red_bed');
  await check('Edits older than fifteen seconds are not undone', async () => {
    await place(alice, target, 'stone');
    await delay(16000);
    const result = await undo(alice);
    assert(alice.blockAt(target)?.name === 'stone', 'Expired edit was undone.');
    assert(result.some(text => /No safe building edits/.test(text)), 'Missing expired history feedback.');
    return { result, retainedMaterial: 'stone', elapsedMs: 16000 };
  });
} catch (error) {
  report.error = String(error.stack ?? error);
  console.error(report.error);
} finally {
  try { await cleanup(); } catch (error) { report.cleanupError = String(error.stack ?? error); }
  finished = true;
  clearTimeout(timer);
  bots.forEach(bot => bot.quit());
  report.completedAt = new Date().toISOString();
  report.success = !report.error && !report.cleanupError && report.checks.length === (cases === 'all' ? 10 : 3)
    && report.checks.every(check => check.success) && report.cleanup?.retained.length === 0;
  save();
  console.log(JSON.stringify({ success: report.success, checks: report.checks.length, cleanup: report.cleanup, report: output }));
  process.exitCode = report.success ? 0 : 1;
}
