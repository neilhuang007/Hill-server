import { createRequire } from 'node:module';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'runtime/smoke-bot/mineflayer/package.json'));
const mineflayer = require(path.join(root, 'runtime/smoke-bot/mineflayer/index.js'));
const { Vec3 } = require('vec3');
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25569);
const fixture = process.env.HILL175_SMOKE_SERVER;
if (!['127.0.0.1', 'localhost'].includes(host) || !fixture || !existsSync(path.join(fixture, '.hill175-smoke-fixture'))) {
  throw Error('Set HILL175_SMOKE_SERVER to a prepared disposable loopback fixture.');
}
const properties = readFileSync(path.join(fixture, 'server.properties'), 'utf8');
if (!properties.includes('server-ip=127.0.0.1') || !properties.includes('server-port=' + port)) throw Error('Fixture address does not match the requested server.');
const output = process.env.HILL175_CAMPUS_BACKUP_REPORT ?? path.join(root, 'runtime/campus-backup-smoke/flow-report.json');
const phase = process.argv[2] ?? 'flow';
const previous = existsSync(output) ? JSON.parse(readFileSync(output, 'utf8')) : {};
const run = String(Date.now()).slice(-7);
const credential = name => ({ name, password: 'Fixture' + randomUUID().replaceAll('-', '') });
const credentials = phase === 'flow' ? {
  owner: credential('CBStudent' + run), peer: credential('CBPeer' + run),
  later: credential('CBLater' + run), reviewer: previous.credentials?.reviewer ?? credential('BlueprintReview'),
} : previous.credentials;
const report = phase === 'flow' ? { host, port, run, credentials, checks: [], messages: [] } : previous;
const bots = [];
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function until(condition, label, timeout = 45000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (condition()) return; await delay(100); }
  throw Error('Timed out: ' + label);
}

function saveReport() { mkdirSync(path.dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2)); }
async function check(name, action) { await action(); report.checks.push(phase + ': ' + name); saveReport(); console.log('PASS: ' + name); }
async function command(bot, text) { bot.chat(text); await delay(250); }

async function connect(account, returning = false) {
  const bot = mineflayer.createBot({ host, port, username: account.name, auth: 'offline', plugins: { team: false } });
  bots.push(bot); bot.lines = []; bot.worldId = '';
  bot._client.on('login', packet => { bot.worldId = packet?.worldState?.name?.split(':').at(-1) ?? bot.worldId; });
  bot._client.on('respawn', packet => { bot.worldId = packet?.worldState?.name?.split(':').at(-1) ?? bot.worldId; });
  bot.on('messagestr', line => { bot.lines.push(line); report.messages.push(account.name + ': ' + line); console.log(account.name + ': ' + line); });
  bot.on('error', error => { report.messages.push(account.name + ': ' + String(error)); });
  bot.on('kicked', reason => { report.messages.push(account.name + ': kicked ' + JSON.stringify(reason)); });
  await until(() => bot.entity && bot.lines.some(line => /register|login/i.test(line)), 'admission ' + account.name, 90000);
  if (returning && !bot.lines.some(line => /\/login /.test(line))) throw Error('Existing identity was lost for ' + account.name);
  const isRegistered = returning || bot.lines.some(line => /\/login /.test(line));
  await command(bot, isRegistered ? `/login ${account.password}` : `/register ${account.password} ${account.password}`);
  await until(() => bot.lines.some(line => /Registration complete|Login successful|logged in|authentication complete/i.test(line)), 'authentication ' + account.name);
  await command(bot, '/campus home');
  await until(() => bot.worldId === 'hill_campus' && bot.game.gameMode === 'creative', 'shared campus admission ' + account.name, 120000);
  await delay(1800);
  return bot;
}

function findPatch(bot) {
  const origin = bot.entity.position.floored();
  for (let radius = 2; radius < 9; radius++) for (let dx = -radius; dx <= radius; dx++) for (let dz = -radius; dz <= radius; dz++) {
    for (let dy = 4; dy >= -10; dy--) {
      const point = origin.offset(dx, dy, dz), floor = bot.blockAt(point.offset(0, -1, 0));
      if (floor?.boundingBox === 'block' && !/leaves|water|chest|door|fence|wall|glass/.test(floor.name)
          && bot.blockAt(point)?.name === 'air' && bot.blockAt(point.offset(0, 1, 0))?.name === 'air') return point;
    }
  }
  throw Error('No loaded test patch beside the shared campus spawn.');
}

async function move(bot, target) {
  bot.physicsEnabled = false;
  const from = bot.entity.position.clone();
  const count = Math.ceil(from.distanceTo(target) / 0.6);
  for (let step = 1; step <= count; step++) {
    const point = from.scaled(1 - step / count).plus(target.scaled(step / count));
    bot.entity.position.set(point.x, point.y, point.z);
    bot._client.write('position', { x: point.x, y: point.y, z: point.z, flags: { onGround: false, hasHorizontalCollision: false } });
    await delay(50);
  }
  await delay(350);
}

async function place(bot, point, name) {
  await move(bot, point.offset(2.5, 1, 0.5));
  const Item = require('prismarine-item')(bot.registry);
  await bot.creative.setInventorySlot(41, new Item(bot.registry.itemsByName[name].id, 1));
  bot.setQuickBarSlot(5); bot._client.write('held_item_slot', { slotId: 5 }); await delay(200);
  if (bot.blockAt(point)?.name !== 'air') {
    await bot.dig(bot.blockAt(point));
    await delay(200);
    await until(() => bot.blockAt(point)?.name === 'air', 'cleared test block');
  }
  await bot.placeBlock(bot.blockAt(point.offset(0, -1, 0)), new Vec3(0, 1, 0));
  try { await until(() => bot.blockAt(point)?.name === name, 'placed ' + name, 7000); }
  catch (error) {
    report.placementFailure = { name, point, mode: bot.game.gameMode, world: bot.worldId,
      position: bot.entity.position, held: bot.heldItem?.name, hotbar: bot.inventory.slots[41]?.name,
      actual: bot.blockAt(point)?.name,
      nearby: Object.values(bot.entities).filter(entity => entity.position.distanceTo(point) < 4)
        .map(entity => ({ name: entity.username ?? entity.name, position: entity.position })) };
    console.error(JSON.stringify(report.placementFailure));
    throw error;
  }
}

async function backup(bot) {
  const start = bot.lines.length;
  await command(bot, '/campusbackup save');
  await until(() => bot.lines.slice(start).some(line => line.startsWith('Campus backup saved: ')), 'verified campus backup', 180000);
  return bot.lines.slice(start).find(line => line.startsWith('Campus backup saved: ')).slice('Campus backup saved: '.length);
}

async function flow() {
  const owner = await connect(credentials.owner);
  const peer = await connect(credentials.peer);
  const reviewer = await connect(credentials.reviewer, Boolean(previous.credentials?.reviewer));
  await check('authenticated students enter one shared creative campus', async () => {
    if (owner.worldId !== peer.worldId || owner.worldId !== 'hill_campus') throw Error('Students are not sharing the campus.');
  });
  const point = findPatch(owner);
  report.block = { x: point.x, y: point.y, z: point.z };
  await check('one student builds and another immediately sees the change', async () => {
    await place(owner, point, 'blue_wool');
    await until(() => peer.blockAt(point)?.name === 'blue_wool', 'shared block replication');
  });
  await check('students cannot create or restore staff backups', async () => {
    let start = owner.lines.length;
    await command(owner, '/campusbackup save');
    await until(() => owner.lines.slice(start).some(line => /Only campus staff/.test(line)), 'backup permission rejection');
    start = owner.lines.length;
    await command(owner, '/campusbackup restore unavailable confirm');
    await until(() => owner.lines.slice(start).some(line => /Only campus staff/.test(line)), 'restore permission rejection');
  });
  await check('staff snapshot records the shared campus', async () => { report.backupId = await backup(reviewer); });
  await check('a new account can register after the recovery point', async () => {
    await connect(credentials.later);
    report.identityCreatedAfterBackup = credentials.later.name;
  });
  await check('later shared edit supplies the restore comparison', async () => {
    await place(peer, point, 'gold_block');
    await until(() => owner.blockAt(point)?.name === 'gold_block', 'second student edit replicated');
    report.restoreExpected = 'blue_wool'; report.restoreBefore = 'gold_block';
  });
  await check('staff can list the chosen recovery point', async () => {
    const start = reviewer.lines.length;
    await command(reviewer, '/campusbackup list');
    await until(() => reviewer.lines.slice(start).some(line => line.includes(report.backupId)), 'listed recovery point');
  });
}

async function requestRestore() {
  const reviewer = await connect(credentials.reviewer, true);
  await command(reviewer, `/campusbackup restore ${report.backupId} confirm`);
  await until(() => reviewer.lines.some(line => line.includes('restarting to restore')), 'restore scheduled');
  report.restoreRequested = true;
}

async function resumed() {
  const owner = await connect(credentials.owner, true);
  const later = await connect(credentials.later, true);
  const point = new Vec3(report.block.x, report.block.y, report.block.z);
  const expected = phase === 'restored' ? report.restoreExpected : report.restoreBefore;
  await check(phase === 'restored' ? 'chosen recovery point restores real campus blocks' : 'shared edits survive a normal restart', async () => {
    await until(() => owner.blockAt(point)?.name === expected && later.blockAt(point)?.name === expected, 'saved campus block ' + expected);
  });
  await check('student identity created after backup is preserved', async () => {
    if (!later.lines.some(line => /\/login /.test(line))) throw Error('Later account reverted to unregistered state.');
    if (later.worldId !== 'hill_campus') throw Error('Later account cannot access the restored campus.');
  });
}

try {
  if (phase === 'flow') await flow();
  else if (phase === 'request-restore') await requestRestore();
  else if (phase === 'restart' || phase === 'restored') await resumed();
  else throw Error('Choose flow, restart, request-restore, or restored.');
  report.success = true; report.lastPhase = phase;
} catch (error) {
  report.success = false; report.lastPhase = phase; report.error = String(error.stack ?? error); console.error(error); process.exitCode = 1;
} finally {
  for (const bot of bots) bot.quit();
  saveReport();
}
await delay(500);
process.exit(process.exitCode ?? 0);
