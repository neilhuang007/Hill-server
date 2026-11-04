import { createRequire } from 'node:module';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencyRoot = process.env.HILL175_SMOKE_DEPS ?? path.join(root, 'runtime/smoke-bot/mineflayer');
const require = createRequire(path.join(dependencyRoot, 'package.json'));
const mineflayer = existsSync(path.join(dependencyRoot, 'index.js'))
  ? require(path.join(dependencyRoot, 'index.js')) : require('mineflayer');
const { Vec3 } = require('vec3');
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25568);
const campusWorld = process.env.HILL175_SMOKE_CAMPUS_WORLD ?? 'hill_campus';
const maximumMs = Number(process.env.HILL175_SAFETY_TIMEOUT_MS ?? 720000);
const recoverySource = process.argv[2] === '--cleanup-report' ? process.argv[3] : null;
if (process.argv.length > 2 && !recoverySource) throw Error('Usage: node ops/smoke-campus-safety.mjs [--cleanup-report <previous report>]');
const output = path.resolve(process.env.HILL175_SAFETY_REPORT ?? path.join(root, 'runtime/local-server-control',
  recoverySource ? 'safety-cleanup-report.json' : 'safety-smoke-report.json'));
if (!Number.isInteger(port) || port < 1 || port > 65535 || !Number.isFinite(maximumMs) || maximumMs < 10000) {
  throw Error('Invalid smoke port or overall timeout.');
}
const run = Date.now().toString().slice(-9);
const outputParts = path.parse(output);
const runOutput = path.join(outputParts.dir, `${outputParts.name}-${run}${outputParts.ext || '.json'}`);
const password = 'Safety' + run + '!';
const report = { mode: recoverySource ? 'cleanup-only' : 'shared-campus-safety', host, port, run,
  startedAt: new Date().toISOString(), checks: [], messages: [], actionbars: [], entities: [], success: false };
const bots = [];
const placedBlocks = new Map();
const fluidTargets = new Map();
let owner;
let timedOut = false;
const solidProducts = new Set(['stone', 'cobblestone', 'obsidian']);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const point = value => ({ x: value.x, y: value.y, z: value.z });
const air = block => block && ['air', 'cave_air', 'void_air'].includes(block.name);

function assert(condition, message) { if (!condition) throw Error(message); }

function assertConnected() {
  const failed = bots.find(bot => bot.failure);
  if (failed) throw Error(`${failed.username}: ${failed.failure}`);
}

async function until(predicate, label, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    assertConnected();
    if (predicate()) return;
    await delay(100);
  }
  throw Error(`Timed out: ${label}; ${bots.map(bot => `${bot.username} ${bot.worldId} ${bot.game?.gameMode}`).join(', ')}`);
}

async function bounded(action, label, timeout = 15000) {
  let timer;
  try {
    return await Promise.race([Promise.resolve().then(action), new Promise((_, reject) => {
      timer = setTimeout(() => reject(Error(`Timed out: ${label}`)), timeout);
    })]);
  } finally { clearTimeout(timer); }
}

async function check(name, action) {
  const result = { name, success: false };
  report.checks.push(result);
  try {
    result.evidence = await action();
    result.success = true;
    console.log('PASS: ' + name);
  } catch (error) {
    result.error = String(error.stack ?? error);
    console.error('FAIL: ' + name + ': ' + error.message);
  }
  writeReport();
}

function writeReport() {
  mkdirSync(path.dirname(output), { recursive: true });
  report.ownedBlocks = [...placedBlocks.values()].map(value => ({ position: point(value.position), expected: value.material }));
  report.fluidTargets = [...fluidTargets.values()].map(point);
  const json = JSON.stringify(report, null, 2);
  writeFileSync(runOutput, json);
  writeFileSync(output, json);
}

async function command(bot, value) { bot.chat(value); await delay(250); }

async function connect(name, authenticate = true) {
  const bot = mineflayer.createBot({ host, port, username: name, auth: 'offline', plugins: { team: false }, hideErrors: false });
  bots.push(bot);
  bot.lines = [];
  bot.overlays = [];
  bot.entityEvents = [];
  bot.packetSequence = 0;
  bot.corrections = [];
  bot.worldId = '';
  const world = packet => { bot.worldId = packet?.worldState?.name?.split(':').at(-1) ?? bot.worldId; };
  bot._client.on('login', world);
  bot._client.on('respawn', world);
  bot._client.on('position', packet => { bot.corrections.push(packet); });
  bot.on('messagestr', text => {
    bot.lines.push(text);
    report.messages.push({ player: name, text });
    console.log(name + ': ' + text);
  });
  bot.on('error', error => { bot.failure = String(error); });
  bot.on('kicked', reason => { bot.failure = 'Kicked: ' + JSON.stringify(reason); });
  bot.on('end', reason => { if (!bot.finished) bot.failure = 'Disconnected: ' + reason; });
  const overlay = packet => {
    const text = JSON.stringify(packet);
    bot.overlays.push(text);
    report.actionbars.push({ player: name, packet });
  };
  bot._client.on('action_bar', overlay);
  bot._client.on('system_chat', packet => { if (packet.isActionBar) overlay(packet); });
  bot.on('entitySpawn', entity => {
    const event = { name: entity.name, type: entity.type, id: entity.id, position: point(entity.position), at: Date.now() };
    bot.entityEvents.push(event);
    if (['creeper', 'cod', 'tnt', 'tnt_minecart'].includes(entity.name)) report.entities.push({ player: name, ...event });
  });
  await until(() => bot.entity && bot.lines.some(line => /register|login/i.test(line)), 'admission', 60000);
  if (!authenticate) return bot;
  await command(bot, `/register ${password} ${password}`);
  await until(() => bot.lines.some(line => /Registration complete/i.test(line)), 'development registration', 60000);
  return bot;
}

async function move(bot, target) {
  assertConnected();
  bot.physicsEnabled = false;
  const start = bot.entity.position.clone();
  const steps = Math.max(1, Math.ceil(start.distanceTo(target) / 0.5));
  assert(steps <= 600, 'Test movement exceeds 300 blocks; use campus navigation first.');
  for (let step = 1; step <= steps; step++) {
    assertConnected();
    const current = start.scaled(1 - step / steps).plus(target.scaled(step / steps));
    bot.entity.position.set(current.x, current.y, current.z);
    bot._client.write('position', { x: current.x, y: current.y, z: current.z,
      flags: { onGround: false, hasHorizontalCollision: false } });
    await delay(50);
  }
  await delay(200);
  assert(bot.entity.position.distanceTo(target) < 1.5, 'Server corrected the test movement away from its target.');
}

async function hold(bot, material, count = 16) {
  const Item = require('prismarine-item')(bot.registry);
  const item = bot.registry.itemsByName[material];
  assert(item, 'Client registry is missing ' + material);
  await bounded(() => bot.creative.setInventorySlot(41, new Item(item.id, count)), 'Creative item ' + material);
  bot.setQuickBarSlot(5);
  bot._client.write('held_item_slot', { slotId: 5 });
  await delay(150);
}

async function place(bot, target, material = 'cobblestone', replaceFluid = false) {
  const current = bot.blockAt(target)?.name;
  assert(air(bot.blockAt(target)) || (replaceFluid && ['water', 'lava'].includes(current)), 'Construction target is occupied: ' + target);
  const directions = [new Vec3(0, -1, 0), new Vec3(-1, 0, 0), new Vec3(1, 0, 0), new Vec3(0, 0, -1), new Vec3(0, 0, 1)];
  const offset = directions.find(value => bot.blockAt(target.plus(value))?.boundingBox === 'block');
  assert(offset, 'No solid support for test placement at ' + target);
  await move(bot, target.offset(0.5, 2.0, 0.5));
  if (bot.heldItem?.name !== material) await hold(bot, material);
  await interactBlock(bot, target.plus(offset), offset.scaled(-1));
  try {
    await until(() => bot.blockAt(target)?.name === material, 'server acknowledged ' + material);
  } catch (error) {
    throw Error(`${error.message}; target=${target}; actual=${bot.blockAt(target)?.name}; held=${bot.heldItem?.name}; `
      + `position=${bot.entity.position}; correction=${JSON.stringify(bot.corrections.at(-1))}`);
  }
  placedBlocks.set(target.toString(), { position: target.clone(), material });
}

async function interactBlock(bot, support, face = new Vec3(0, 1, 0)) {
  const cursor = new Vec3(0.5 + face.x * 0.5, 0.5 + face.y * 0.5, 0.5 + face.z * 0.5);
  await bot.lookAt(support.plus(cursor), true);
  const direction = face.y < 0 ? 0 : face.y > 0 ? 1 : face.z < 0 ? 2 : face.z > 0 ? 3 : face.x < 0 ? 4 : 5;
  bot._client.write('block_place', { location: support, direction, hand: 0,
    cursorX: cursor.x, cursorY: cursor.y, cursorZ: cursor.z,
    insideBlock: false, sequence: ++bot.packetSequence, worldBorderHit: false });
  bot.swingArm();
}

async function breakCreative(bot, target) {
  await move(bot, target.offset(0.5, 2.0, 0.5));
  if (bot.heldItem?.name !== 'stick') await hold(bot, 'stick', 1);
  await bot.lookAt(target.offset(0.5, 0.5, 0.5), true);
  bot._client.write('block_dig', { status: 0, location: target, face: 1, sequence: ++bot.packetSequence });
  await until(() => air(bot.blockAt(target)), 'server acknowledged removal at ' + target);
}

function findRigOrigin(bot) {
  const start = bot.entity.position.floored();
  const candidates = [];
  for (let dx = -16; dx <= 16; dx++) for (let dz = -16; dz <= 16; dz++) {
    for (let dy = -8; dy <= 4; dy++) {
      const base = start.offset(dx, dy, dz);
      const floor = bot.blockAt(base.offset(0, -1, 0));
      if (floor?.boundingBox !== 'block' || /leaves|chest|barrel|door|campfire/.test(floor.name)) continue;
      if (!air(bot.blockAt(base)) || !air(bot.blockAt(base.offset(0, 1, 0)))) continue;
      if (!clearVolume(bot, base.offset(0, 4, 0), 7, 6, 6)) continue;
      if (![0, 1, 2, 3].every(y => air(bot.blockAt(base.offset(0, y, 0))))) continue;
      candidates.push(base);
    }
  }
  candidates.sort((left, right) => left.distanceTo(start) - right.distanceTo(start));
  assert(candidates.length, 'No loaded clear space near campus spawn for a contained test rig.');
  return candidates[0];
}

function clearVolume(bot, base, width, height, depth) {
  for (let x = 0; x < width; x++) for (let y = 0; y < height; y++) for (let z = 0; z < depth; z++) {
    if (!air(bot.blockAt(base.offset(x, y, z)))) return false;
  }
  return true;
}

async function createRig(bot, origin) {
  for (let y = 0; y < 4; y++) await place(bot, origin.offset(0, y, 0));
  const base = origin.offset(0, 4, 0);
  for (let x = 0; x < 7; x++) {
    for (let z = 0; z < 6; z++) await place(bot, base.offset(x, 0, z));
    console.log(`Rig platform: ${x + 1}/7 rows acknowledged by server`);
  }
  const lateralWalls = [[0, 1], [3, 1], [1, 0], [2, 0], [1, 2], [2, 2]];
  for (const [x, z] of lateralWalls) await place(bot, base.offset(x, 1, z));
  const verticalWalls = [[4, 4], [6, 4], [5, 3], [5, 5]];
  for (const y of [1, 2]) for (const [x, z] of verticalWalls) await place(bot, base.offset(x, y, z));
  return { base, lateralLava: base.offset(1, 1, 1), lateralWater: base.offset(2, 1, 1),
    lower: base.offset(5, 1, 4), upper: base.offset(5, 2, 4), marker: base.offset(1, 1, 4) };
}

async function useOn(bot, target, material, face = new Vec3(0, 1, 0)) {
  await move(bot, target.offset(0.5, 2.8, 0.5));
  await hold(bot, material, 1);
  await interactBlock(bot, target, face);
  await delay(300);
}

async function bucketInto(bot, target, material, support = target.offset(0, -1, 0), face = new Vec3(0, 1, 0)) {
  fluidTargets.set(target.toString(), target.clone());
  await move(bot, target.offset(0.5, 2.4, 0.5));
  await hold(bot, material, 1);
  await bot.lookAt(support.offset(0.5, 0.5, 0.5).plus(face.scaled(0.501)), true);
  bot.activateItem();
  await delay(300);
  bot.deactivateItem();
}

async function enterCampus(bot) {
  if (bot.worldId !== campusWorld) await command(bot, '/campus home');
  await until(() => bot.worldId === campusWorld && bot.game.gameMode === 'creative', 'shared campus admission', 120000);
  await bounded(() => bot.waitForChunksToLoad(), 'campus chunks', 60000);
}

function lobbyPatch(bot) {
  const start = bot.entity.position.floored();
  for (let dx = -3; dx <= 3; dx++) for (let dz = -3; dz <= 3; dz++) for (let dy = -3; dy <= 1; dy++) {
    const target = start.offset(dx, dy, dz);
    const floor = bot.blockAt(target.offset(0, -1, 0));
    if (floor?.boundingBox === 'block' && air(bot.blockAt(target)) && target.distanceTo(start) <= 3) return target;
  }
  throw Error('No nearby loaded lobby floor for the admission protection probe.');
}

async function cleanupRig() {
  if (!owner || owner.failure || owner.worldId !== campusWorld) return { success: false, reason: 'Builder is unavailable for cleanup.' };
  const cleanup = { success: true, removed: 0, retained: [] };
  const anchor = [...placedBlocks.values()][0]?.position ?? [...fluidTargets.values()][0];
  if (anchor && !owner.blockAt(anchor)) {
    const altitude = Math.max(200, owner.entity.position.y + 5, anchor.y + 8);
    await move(owner, new Vec3(owner.entity.position.x, altitude, owner.entity.position.z));
    await move(owner, new Vec3(anchor.x + 3.5, altitude, anchor.z + 2.5));
    await move(owner, anchor.offset(3.5, 8.0, 2.5));
    await until(() => owner.blockAt(anchor) != null, 'rig chunks reloaded for cleanup', 30000);
  }
  const fluids = [...fluidTargets.values()].sort((left, right) => right.y - left.y);
  for (const target of fluids) {
    const material = owner.blockAt(target)?.name;
    if (['water', 'lava'].includes(material)) await place(owner, target, 'glass', true);
    else if (solidProducts.has(material)) placedBlocks.set(target.toString(), { position: target, material });
  }
  const blocks = [...placedBlocks.values()].sort((left, right) => right.position.y - left.position.y);
  for (const { position, material } of blocks) {
    const current = owner.blockAt(position)?.name;
    if (air(owner.blockAt(position))) continue;
    if (current !== material) { cleanup.retained.push({ position: point(position), expected: material, actual: current }); continue; }
    await breakCreative(owner, position);
    cleanup.removed++;
  }
  cleanup.success = cleanup.retained.length === 0;
  return cleanup;
}

async function prepareRecovery() {
  const previous = JSON.parse(readFileSync(path.resolve(recoverySource), 'utf8'));
  assert(previous.world === campusWorld && /^Safe\d+$/.test(previous.owner ?? ''), 'Recovery needs a known safety smoke report for this campus.');
  assert(previous.rigOrigin && previous.rig, 'Report does not identify a test rig.');
  const origin = new Vec3(previous.rigOrigin.x, previous.rigOrigin.y, previous.rigOrigin.z);
  const permitted = new Set(['stone', 'cobblestone', 'glass', 'tnt', 'blue_wool', 'red_wool']);
  const position = record => {
    const value = new Vec3(record.x, record.y, record.z);
    assert([value.x, value.y, value.z].every(Number.isInteger) && value.distanceTo(origin) < 20, 'Recovery coordinate exceeds the recorded rig.');
    return value;
  };
  for (const block of previous.ownedBlocks ?? previous.cleanup?.retained ?? []) {
    assert(permitted.has(block.expected), 'Recovery refuses an unexpected block material.');
    const target = position(block.position);
    placedBlocks.set(target.toString(), { position: target, material: block.expected });
  }
  for (const key of ['lateralLava', 'lateralWater', 'lower', 'upper']) {
    const target = position(previous.rig[key]);
    fluidTargets.set(target.toString(), target);
  }
  owner = await connect('Clean' + run);
  await enterCampus(owner);
  report.owner = owner.username;
  report.world = owner.worldId;
  report.recoveredRun = previous.run;
  report.rigOrigin = previous.rigOrigin;
  report.rig = previous.rig;
  report.success = true;
}

async function main() {
  owner = await connect('Safe' + run);
  report.owner = owner.username;
  await enterCampus(owner);
  report.world = owner.worldId;
  const origin = findRigOrigin(owner);
  report.rigOrigin = point(origin);
  await check('Owner can place and break an actual stone block', async () => {
    await place(owner, origin, 'stone');
    await breakCreative(owner, origin);
    return { position: point(origin), placed: 'stone', final: owner.blockAt(origin).name };
  });
  assert(report.checks.at(-1).success, 'The server did not allow ordinary owner building.');
  const rig = await createRig(owner, origin);
  report.rig = Object.fromEntries(Object.entries(rig).map(([key, value]) => [key, point(value)]));
  await check('TNT ignition cannot prime or explode', async () => {
    await place(owner, rig.marker, 'tnt');
    const started = Date.now();
    await useOn(owner, rig.marker, 'flint_and_steel');
    await delay(5500);
    const primed = owner.entityEvents.filter(entity => entity.at >= started && /^(tnt|primed_tnt)$/.test(entity.name));
    assert(owner.blockAt(rig.marker)?.name === 'tnt', 'TNT disappeared after ignition.');
    assert(primed.length === 0, 'Primed TNT appeared in the client entity stream.');
    assert(owner.blockAt(rig.marker.offset(0, -1, 0))?.name === 'cobblestone', 'Explosion damaged the test floor.');
    await breakCreative(owner, rig.marker);
    return { observationMs: 5500, primedEntities: primed.length, tntPersisted: true, floorIntact: true };
  });
  await check('Creeper spawn eggs do not create mobs', async () => {
    const started = Date.now();
    await useOn(owner, rig.marker.offset(0, -1, 0), 'creeper_spawn_egg');
    await delay(1500);
    const spawned = owner.entityEvents.filter(entity => entity.at >= started && entity.name === 'creeper');
    assert(spawned.length === 0, 'Creeper spawned after a spawn egg interaction.');
    return { usedItem: 'creeper_spawn_egg', spawnedCreepers: spawned.length };
  });
  await check('Creature buckets do not place a mob or liquid', async () => {
    const started = Date.now();
    await bucketInto(owner, rig.lower, 'cod_bucket');
    await delay(1500);
    const spawned = owner.entityEvents.filter(entity => entity.at >= started && entity.name === 'cod');
    assert(spawned.length === 0, 'Cod spawned from the creature bucket.');
    assert(air(owner.blockAt(rig.lower)), 'Creature bucket was not rejected before placing water.');
    return { usedItem: 'cod_bucket', spawnedCod: spawned.length, target: owner.blockAt(rig.lower).name };
  });
  await check('Water beside lava cannot cast obsidian or cobblestone', async () => {
    await bucketInto(owner, rig.lateralLava, 'lava_bucket');
    await until(() => owner.blockAt(rig.lateralLava)?.name === 'lava', 'lava source placement');
    await bucketInto(owner, rig.lateralWater, 'water_bucket');
    await until(() => owner.blockAt(rig.lateralWater)?.name === 'water', 'water source placement');
    await delay(3500);
    const state = [rig.lateralLava, rig.lateralWater].map(position => ({ position: point(position), block: owner.blockAt(position)?.name }));
    assert(state.every(value => !solidProducts.has(value.block)), 'Fluid contact formed a cast product: ' + JSON.stringify(state));
    return { sourcesObserved: ['lava', 'water'], final: state };
  });
  await check('Lava flowing down into water cannot cast stone', async () => {
    // A failed creature bucket check may already have left water in this independent basin.
    if (owner.blockAt(rig.lower)?.name !== 'water') await bucketInto(owner, rig.lower, 'water_bucket');
    await until(() => owner.blockAt(rig.lower)?.name === 'water', 'lower water source');
    await bucketInto(owner, rig.upper, 'lava_bucket', rig.upper.offset(1, 0, 0), new Vec3(-1, 0, 0));
    await until(() => owner.blockAt(rig.upper)?.name === 'lava', 'upper lava source');
    await delay(4500);
    const state = [rig.lower, rig.upper].map(position => ({ position: point(position), block: owner.blockAt(position)?.name }));
    assert(state.every(value => !solidProducts.has(value.block)), 'Downward lava formed a cast product: ' + JSON.stringify(state));
    assert(state[0].block === 'water' && state[1].block === 'lava', 'Both fluid sources must remain present.');
    return { sourcesObserved: ['water', 'lava'], final: state };
  });
  await check('Two authenticated students share edits in both directions', async () => {
    const peer = await connect('Peer' + run);
    report.peer = peer.username;
    await enterCampus(peer);
    assert(peer.worldId === owner.worldId, 'Students were sent to different campus worlds.');
    await move(peer, rig.marker.offset(2.5, 2.0, 0.5));
    await place(owner, rig.marker, 'blue_wool');
    await until(() => peer.blockAt(rig.marker)?.name === 'blue_wool', 'peer receives owner placement');
    await breakCreative(peer, rig.marker);
    await until(() => air(owner.blockAt(rig.marker)), 'owner receives peer removal');
    await place(peer, rig.marker, 'red_wool');
    await until(() => owner.blockAt(rig.marker)?.name === 'red_wool', 'owner receives peer placement');
    await breakCreative(owner, rig.marker);
    await until(() => air(peer.blockAt(rig.marker)), 'peer receives owner removal');
    return { world: owner.worldId, ownerPlacement: 'blue_wool', peerPlacement: 'red_wool', bothObservedRemovals: true };
  });
  await check('Unregistered clients remain isolated and cannot edit the lobby', async () => {
    const guest = await connect('Guest' + run, false);
    report.unregisteredGuest = guest.username;
    await bounded(() => guest.waitForChunksToLoad(), 'lobby chunks', 60000);
    const lobby = guest.worldId;
    assert(lobby !== campusWorld && guest.game.gameMode !== 'creative', 'Unregistered player entered an editable campus.');
    await command(guest, '/campus home');
    await delay(1000);
    assert(guest.worldId === lobby && guest.worldId !== campusWorld, 'Campus command bypassed registration.');
    const target = lobbyPatch(guest);
    const floor = target.offset(0, -1, 0);
    const before = guest.blockAt(floor).stateId;
    const Item = require('prismarine-item')(guest.registry);
    guest._client.write('set_creative_slot', { slot: 41, item: Item.toNotch(new Item(guest.registry.itemsByName.stone.id, 1)) });
    guest._client.write('held_item_slot', { slotId: 5 });
    await interactBlock(guest, floor);
    guest._client.write('block_dig', { status: 0, location: floor, face: 1, sequence: ++guest.packetSequence });
    guest._client.write('block_dig', { status: 2, location: floor, face: 1, sequence: ++guest.packetSequence });
    await delay(1000);
    assert(air(guest.blockAt(target)), 'Unregistered placement changed the lobby.');
    assert(guest.blockAt(floor).stateId === before, 'Unregistered breaking changed the lobby.');
    return { lobbyWorld: lobby, campusEntryDenied: true, placementUnchanged: true, floorStateUnchanged: true };
  });
  await check('Nearby building name arrives as a native actionbar packet', async () => {
    const catalog = readFileSync(path.join(root, 'src/main/resources/hill-buildings.yml'), 'utf8');
    const chapel = catalog.match(/  alumni-chapel:\r?\n\s+name:\s*"([^"]+)"/);
    assert(chapel, 'Bundled catalog must contain Alumni Chapel.');
    const started = owner.overlays.length;
    await command(owner, '/campus go alumni-chapel');
    await until(() => owner.overlays.slice(started).some(packet => packet.includes(chapel[1])), 'building actionbar caption', 30000);
    return { building: 'alumni-chapel', expectedName: chapel[1], packet: owner.overlays.slice(started).find(packet => packet.includes(chapel[1])) };
  });
  report.success = report.checks.length === 9 && report.checks.every(result => result.success);
}

let timeout;
try {
  await Promise.race([recoverySource ? prepareRecovery() : main(), new Promise((_, reject) => {
    timeout = setTimeout(() => { timedOut = true; reject(Error('Overall campus safety smoke timeout')); }, maximumMs);
  })]);
} catch (error) {
  report.error = String(error.stack ?? error);
  report.success = false;
  console.error(error);
} finally {
  clearTimeout(timeout);
  try {
    report.cleanup = timedOut ? { success: false, reason: 'Overall timeout; preserve the fixture for recovery.' }
      : await bounded(cleanupRig, 'test rig cleanup', 180000);
  } catch (error) { report.cleanup = { success: false, error: String(error) }; }
  if (!report.cleanup.success) report.success = false;
  report.finishedAt = new Date().toISOString();
  for (const bot of bots) { bot.finished = true; bot.quit('Campus safety smoke finished'); }
  writeReport();
}
console.log((report.success ? 'PASS' : 'FAIL') + ': report ' + output);
await delay(400);
process.exit(report.success ? 0 : 1);
