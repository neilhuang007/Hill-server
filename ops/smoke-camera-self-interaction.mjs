import { createRequire } from 'node:module';
import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'runtime/smoke-bot/mineflayer/package.json'));
const mineflayer = require(path.join(root, 'runtime/smoke-bot/mineflayer/index.js'));
const lines = [];
const report = { checks: [], kicked: null };
const bot = mineflayer.createBot({ host: process.env.HILL175_SMOKE_HOST ?? '127.0.0.1',
  port: Number(process.env.HILL175_SMOKE_PORT ?? 25568), username: 'Self' + String(Date.now()).slice(-9),
  auth: 'offline', plugins: { team: false } });
bot.on('messagestr', line => lines.push(line));
bot.on('kicked', reason => { report.kicked = reason; });
bot.on('error', error => { report.error = error.message; });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(test, label, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (report.kicked) throw Error('Disconnected: ' + JSON.stringify(report.kicked));
    if (test()) return;
    await delay(100);
  }
  throw Error('Timed out: ' + label);
}
async function command(value, expected) {
  const start = lines.length;
  bot.chat(value);
  await until(() => lines.slice(start).some(line => line.includes(expected)), expected);
}
try {
  await until(() => bot.entity && lines.some(line => line.includes('/register')), 'join', 60000);
  await command('/register LocalSelf123! LocalSelf123!', 'Registration complete');
  await command('/entry create journey', 'Journey entry created');
  await command('/camera save 1', 'Camera 1/3 saved');
  await command('/camera preview 1', 'Previewing camera slot 1');
  await delay(400);
  // A detached vanilla camera can raycast the player's own body on exit.
  bot._client.write('use_entity', { target: bot.entity.id, hand: 0,
    location: { x: 0, y: 1.6, z: 0 }, usingSecondaryAction: false });
  await delay(1000);
  if (report.kicked) throw Error('Camera self interaction disconnected player: ' + JSON.stringify(report.kicked));
  await until(() => lines.some(line => line.includes('Camera preview closed')), 'safe preview exit');
  report.checks.push('Camera body interaction exits preview without disconnect');
  await command('/camera preview 1', 'Previewing camera slot 1');
  await delay(400);
  bot._client.write('attack', { entityId: bot.entity.id });
  await delay(1000);
  if (report.kicked) throw Error('Camera self attack disconnected player: ' + JSON.stringify(report.kicked));
  const hubStart = lines.length;
  bot.chat('/hub');
  await until(() => lines.slice(hubStart).some(line => line.includes('Tip:')), 'hub navigation');
  report.checks.push('Camera body attack retains connection and hub navigation');
  report.passed = true;
  console.log('PASS: camera self interaction and attack remain connected');
} catch (error) {
  report.passed = false;
  report.failure = error.message;
  console.error('FAIL: ' + error.message);
  process.exitCode = 1;
} finally {
  report.messages = lines;
  const output = process.env.HILL175_CAMERA_SELF_REPORT ?? path.join(root, 'runtime/local-server-control/camera-self-report.json');
  mkdirSync(path.dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2));
  bot.quit();
}
