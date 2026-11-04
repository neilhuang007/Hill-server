import { createRequire } from 'node:module';
import { createHash, randomUUID } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = process.env.HILL175_SMOKE_DEPS ?? path.join(root, 'runtime/smoke-bot/mineflayer');
const require = createRequire(path.join(dependencies, 'package.json'));
const mineflayer = require(path.join(dependencies, 'index.js'));
const nbt = require('prismarine-nbt');
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25568);
if (!['127.0.0.1', 'localhost'].includes(host)) throw Error('This smoke requires the local development server.');
const run = String(Date.now()).slice(-9);
const bots = [];
const report = { host, port, run, checks: [], limitations: [
  'Pack loading is simulated by protocol status after checking its downloaded bytes and SHA1.',
  'Protocol checks do not certify native image rendering or native Bedrock forms.',
  'The undo check invokes the real callback with an empty edit history; separate undo tests cover block restoration.'
] };
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function until(condition, label, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const failed = bots.find(bot => bot.failure);
    if (failed) throw Error(failed.username + ': ' + failed.failure);
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

function decodeDialog(packet) {
  const tag = packet.dialog?.data;
  if (tag?.type !== 'compound') throw Error('Expected an inline native dialog definition');
  const value = nbt.simplify(tag);
  // The native codec uses a single object when the body has only one element.
  value.body = value.body ? (Array.isArray(value.body) ? value.body : [value.body]) : [];
  const rawButtons = [...(tag.value.actions?.value.value ?? [])];
  if (tag.value.exit_action) rawButtons.push(tag.value.exit_action.value);
  const buttons = rawButtons.map(raw => {
    const button = nbt.simplify({ type: 'compound', value: raw });
    return { ...button, response: raw.action?.value.additions };
  });
  return { value, buttons, packet };
}

function connect(name) {
  const bot = mineflayer.createBot({ host, port, username: name, auth: 'offline', plugins: { team: false } });
  bots.push(bot);
  bot.lines = []; bot.packs = []; bot.dialogs = []; bot.inventoryOpens = 0; bot.dialogCloses = 0;
  bot.worldName = ''; bot.password = 'Local' + randomUUID().replaceAll('-', '');
  bot.on('messagestr', line => bot.lines.push(line));
  bot.on('error', error => { bot.failure = error.message; });
  bot.on('kicked', reason => { bot.failure = 'Kicked: ' + JSON.stringify(reason); });
  bot._client.on('open_window', () => { bot.inventoryOpens++; });
  bot._client.on('clear_dialog', () => { bot.dialogCloses++; });
  bot._client.on('add_resource_pack', packet => bot.packs.push(packet));
  bot._client.on('show_dialog', packet => {
    try { bot.dialogs.push(decodeDialog(packet)); }
    catch (error) { bot.failure = error.message; report.unparsedDialog = packet; }
  });
  for (const event of ['login', 'respawn']) {
    bot._client.on(event, packet => { bot.worldName = packet?.worldState?.name ?? bot.worldName; });
  }
  return bot;
}

async function admit(bot) {
  await until(() => bot.entity && bot.lines.some(line => line.includes('/register')), bot.username + ' admission', 60000);
}

async function login(bot) {
  await admit(bot);
  bot.chat('/register ' + bot.password + ' ' + bot.password);
  await until(() => bot.lines.some(line => line.includes('Registration complete')), bot.username + ' registration');
}

const current = bot => bot.dialogs.at(-1);
const plain = component => typeof component === 'string' ? component
  : Array.isArray(component) ? component.map(plain).join('')
  // Mixed NBT lists wrap simple string components in an empty name compound.
  : component && typeof component === 'object' ? (component.text ?? component[''] ?? '') + (component.extra ?? []).map(plain).join('') : '';
const title = dialog => plain(dialog.value.title);
const artwork = dialog => dialog.value.body?.find(body => body.type === 'minecraft:item'
  || JSON.stringify(body.contents ?? '').includes('hill175:campus/map_labels'));
const numberedButtons = dialog => dialog.buttons.filter(button => /^\d+\. /.test(plain(button.label)));
const horizontalDistance = (first, second) => Math.hypot(first.x - second.x, first.z - second.z);

function button(bot, label) {
  const found = current(bot)?.buttons.find(option => plain(option.label) === label);
  if (!found) throw Error('Missing dialog action: ' + label);
  return found;
}

function click(bot, option) {
  if (!option?.action?.id || option.response?.type !== 'compound') throw Error('Missing server supplied callback payload');
  // Preserve the exact typed NBT additions, including the generated callback UUID.
  bot._client.write('custom_click_action', { id: option.action.id,
    nbt: nbt.proto.createPacketBuffer('anonymousNbt', option.response) });
}

async function open(bot, action, expectedTitle) {
  const count = bot.dialogs.length;
  await action();
  await until(() => bot.dialogs.length > count && title(current(bot)) === expectedTitle, expectedTitle);
  return current(bot);
}

async function choose(bot, label, expectedTitle) {
  return open(bot, () => click(bot, button(bot, label)), expectedTitle);
}

function imageLabels(dialog) {
  const found = [];
  function visit(tag) {
    if (tag?.type === 'compound') {
      const raw = tag.value;
      if (raw.hover_event) {
        const hover = nbt.simplify(raw.hover_event);
        const label = plain(hover.contents ?? hover.value);
        const match = /^(\d+)\.\s/.exec(label);
        if (match) {
          const event = raw.click_event ? nbt.simplify(raw.click_event) : null;
          found.push({ number: Number(match[1]), label,
            action: event?.id ? { id: event.id } : null,
            response: raw.click_event?.value.payload });
        }
      }
      for (const value of Object.values(raw)) visit(value);
    } else if (tag?.type === 'list') {
      for (const value of tag.value.value) visit({ type: tag.value.type, value });
    }
  }
  visit(dialog.packet.dialog.data);
  return found;
}

function imageLabel(bot, number) {
  const option = imageLabels(current(bot)).find(value => value.number === number && value.action);
  if (!option) throw Error('Missing clickable image label ' + number);
  return option;
}

function assertArtwork(dialog, isCore) {
  const body = artwork(dialog);
  // Native plain_message widgets reserve four pixels of padding on each side.
  if (!body || body.type !== 'minecraft:plain_message' || body.width !== 370) {
    throw Error('Clickable school artwork is not the expected text image body');
  }
  if (plain(body.contents).split('\n').length !== 40) {
    report.artworkDiagnostic = body;
    throw Error('Clickable image has incorrect row count: ' + plain(body.contents).split('\n').length);
  }
  const labels = imageLabels(dialog);
  const numbers = [...new Set(labels.map(value => value.number))];
  if (!numbers.includes(6) || (isCore ? numbers.length >= 51 || numbers.length < 15 : numbers.length !== 51)) {
    throw Error('Unexpected image labels: ' + numbers.join(','));
  }
  const external = labels.filter(value => value.number === 28);
  if (external.some(value => value.action || !/outside/i.test(value.label))) {
    throw Error('The external golf course label must explain its boundary without teleporting');
  }
  return numbers;
}

async function loadedMap(bot) {
  await open(bot, () => bot.chat('/campus map'), 'Hill Campus Map');
  assertArtwork(current(bot), false);
}

function captureDialog(dialog, view) {
  const folder = process.env.HILL175_DIALOG_CAPTURE;
  if (!folder) return;
  mkdirSync(folder, { recursive: true });
  writeFileSync(path.join(folder, view + '-dialog.nbt'), nbt.writeUncompressed({ ...dialog.packet.dialog.data, name: '' }));
}

try {
  const owner = connect('Dialog' + run);
  await admit(owner);
  await check('Unauthenticated student cannot open a campus dialog', async () => {
    owner.chat('/campus map');
    await delay(800);
    if (owner.dialogs.length || owner.inventoryOpens) throw Error('Unauthenticated map interface was opened');
  });
  await login(owner);
  await open(owner, () => owner.chat('/campus map'), 'Hill Campus Map');
  await check('Campus opens a native dialog with named controls and no inventory window', async () => {
    if (owner.inventoryOpens || artwork(current(owner))) throw Error('Unexpected inventory or artwork before pack success');
    for (const label of ['Buildings', 'Zoom Buildings', 'Undo Last 15 Seconds', 'Close']) button(owner, label);
    if (current(owner).value.type !== 'minecraft:multi_action') throw Error('Expected the native multi action dialog');
  });
  await check('Optional map pack matches the SHA1 advertised by the server', async () => {
    await until(() => owner.packs.length > 0, 'map pack offer');
    const offer = owner.packs.at(-1);
    if (new URL(offer.url).pathname !== '/campus-pack.zip' || offer.forced) throw Error('Unexpected or mandatory pack');
    const response = await fetch(offer.url);
    if (!response.ok || response.headers.get('content-type') !== 'application/zip') throw Error('Map pack download failed');
    const bytes = Buffer.from(await response.arrayBuffer());
    const sha1 = createHash('sha1').update(bytes).digest('hex');
    if (sha1 !== offer.hash) throw Error('Pack hash does not match downloaded bytes');
    report.pack = { url: offer.url, sha1, bytes: bytes.length };
    await open(owner, () => owner._client.write('resource_pack_receive', { uuid: offer.uuid, result: 1 }), 'Hill Campus Map');
  });
  let unusedOldButton;
  await check('Declined pack still permits numbered building selection and pagination', async () => {
    if (artwork(current(owner))) throw Error('Declined resource pack still received custom artwork');
    unusedOldButton = button(owner, 'Zoom Buildings');
    await choose(owner, 'Buildings', 'Choose a Building');
    if (numberedButtons(current(owner)).length !== 12) throw Error('First building page did not contain twelve choices');
    const firstNumbers = numberedButtons(current(owner)).map(option => plain(option.label));
    await choose(owner, 'More Buildings', 'Choose a Building');
    if (numberedButtons(current(owner)).some(option => firstNumbers.includes(plain(option.label)))) throw Error('Pagination repeated the first page');
    await choose(owner, 'Previous Buildings', 'Choose a Building');
    button(owner, '6. Alumni Chapel');
  });
  await check('Unused buttons from a replaced dialog cannot navigate or teleport', async () => {
    const count = owner.dialogs.length;
    const position = owner.entity.position.clone();
    click(owner, unusedOldButton);
    await delay(700);
    if (owner.dialogs.length !== count || horizontalDistance(owner.entity.position, position) > 2) throw Error('Stale dialog callback was accepted');
  });
  await check('Loaded pack provides numbered image click targets and a distinct buildings zoom', async () => {
    await choose(owner, 'Back to Map', 'Hill Campus Map');
    const count = owner.packs.length;
    await choose(owner, 'Load School Map', 'Hill Campus Map');
    await until(() => owner.packs.length > count, 'explicit pack offer');
    const offer = owner.packs.at(-1);
    owner._client.write('resource_pack_receive', { uuid: offer.uuid, result: 3 });
    await open(owner, () => owner._client.write('resource_pack_receive', { uuid: offer.uuid, result: 0 }), 'Hill Campus Map');
    report.fullMapLabels = assertArtwork(current(owner), false);
    captureDialog(current(owner), 'full');
    await choose(owner, 'Zoom Buildings', 'Campus Buildings');
    report.coreMapLabels = assertArtwork(current(owner), true);
    captureDialog(current(owner), 'core');
    await choose(owner, 'Whole Campus', 'Hill Campus Map');
    assertArtwork(current(owner), false);
  });
  await check('Close invalidates all remaining buttons and pack status does not reopen it', async () => {
    const unused = imageLabel(owner, 6);
    const count = owner.dialogs.length;
    const closes = owner.dialogCloses;
    click(owner, button(owner, 'Close'));
    owner._client.write('resource_pack_receive', { uuid: owner.packs.at(-1).uuid, result: 0 });
    await until(() => owner.dialogCloses > closes, 'native dialog close');
    click(owner, unused);
    await delay(700);
    if (owner.dialogs.length !== count) throw Error('Closed menu was reopened by a stale callback or pack completion');
  });
  await loadedMap(owner);
  const guest = connect('DialogG' + run);
  await login(guest);
  await until(() => guest.worldName.split(':').at(-1) === 'hill_campus', 'second student shared campus');
  await check('Another authenticated student cannot use the owner destination callback', async () => {
    const position = guest.entity.position.clone();
    const ownerPosition = owner.entity.position.clone();
    const count = guest.dialogs.length;
    click(guest, imageLabel(owner, 6));
    await delay(800);
    if (guest.dialogs.length !== count || horizontalDistance(guest.entity.position, position) > 2
        || horizontalDistance(owner.entity.position, ownerPosition) > 2) throw Error('A forged owner callback changed a student destination');
  });
  let usedChapelLabel;
  await check('Clicking the Chapel image label teleports directly without a confirmation page', async () => {
    await loadedMap(owner);
    const dialogs = owner.dialogs.length;
    usedChapelLabel = imageLabel(owner, 6);
    click(owner, usedChapelLabel);
    await until(() => owner.worldName === guest.worldName && owner.game.gameMode === 'creative'
      && Math.abs(owner.entity.position.x + 2) < 8 && Math.abs(owner.entity.position.z - 63.5) < 8, 'Alumni Chapel destination', 60000);
    if (owner.dialogs.length !== dialogs) throw Error('Image label opened an extra confirmation page');
    report.destination = { world: owner.worldName, position: owner.entity.position.clone(), building: '6. Alumni Chapel' };
  });
  await check('A consumed image label cannot teleport the player again', async () => {
    owner.chat('/campus home');
    await until(() => owner.entity.position.x > 80, 'return to campus spawn');
    const position = owner.entity.position.clone();
    click(owner, usedChapelLabel);
    await delay(700);
    if (horizontalDistance(owner.entity.position, position) > 2) throw Error('Consumed image callback was replayed');
  });
  await check('Named building fallback also teleports in one click', async () => {
    owner.chat('/campus home');
    await until(() => owner.entity.position.x > 80, 'return to campus spawn');
    await loadedMap(owner);
    await choose(owner, 'Buildings', 'Choose a Building');
    const dialogs = owner.dialogs.length;
    click(owner, button(owner, '6. Alumni Chapel'));
    await until(() => Math.abs(owner.entity.position.x + 2) < 8 && Math.abs(owner.entity.position.z - 63.5) < 8, 'direct named destination');
    if (owner.dialogs.length !== dialogs) throw Error('Named building opened an extra confirmation page');
  });
  await check('A label in the building zoom teleports to its own destination', async () => {
    await loadedMap(owner);
    await choose(owner, 'Zoom Buildings', 'Campus Buildings');
    const dialogs = owner.dialogs.length;
    click(owner, imageLabel(owner, 50));
    await until(() => owner.entity.position.x >= 122 && owner.entity.position.x <= 339
      && owner.entity.position.z >= 166 && owner.entity.position.z <= 256, 'Shirley Quadrivium destination', 60000);
    if (owner.dialogs.length !== dialogs) throw Error('Zoom image label opened an extra confirmation page');
    report.zoomDestination = { world: owner.worldName, position: owner.entity.position.clone(), number: 50 };
  });
  await check('A field label teleports to the reviewed campus point', async () => {
    await loadedMap(owner);
    const dialogs = owner.dialogs.length;
    click(owner, imageLabel(owner, 20));
    await until(() => Math.abs(owner.entity.position.x - 967.5) < 20
      && Math.abs(owner.entity.position.z + 624.5) < 20, 'Nam Family Field destination', 60000);
    if (owner.dialogs.length !== dialogs || owner.worldName !== guest.worldName) throw Error('Field label did not directly navigate within the shared campus');
    report.fieldDestination = { world: owner.worldName, position: owner.entity.position.clone(), number: 20 };
  });
  await check('Undo button invokes the shared campus undo callback', async () => {
    await open(owner, () => owner.chat('/campus map'), 'Hill Campus Map');
    const start = owner.lines.length;
    click(owner, button(owner, 'Undo Last 15 Seconds'));
    await until(() => owner.lines.slice(start).some(line => line.includes('No safe building edits to undo from the last 15 seconds.')), 'undo callback result');
  });
  await check('Commands close and invalidate the current dialog without an inventory screen', async () => {
    await open(owner, () => owner.chat('/campus map'), 'Hill Campus Map');
    const unused = button(owner, 'Buildings');
    const count = owner.dialogs.length;
    const closes = owner.dialogCloses;
    owner.chat('/campus home');
    await until(() => owner.dialogCloses > closes, 'command invalidation closes dialog');
    click(owner, unused);
    await delay(700);
    if (owner.dialogs.length !== count || bots.some(bot => bot.inventoryOpens)) throw Error('An invalidated dialog opened a new interface');
  });
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.failure = error.stack ?? String(error);
  process.exitCode = 1;
  console.error(report.failure);
} finally {
  report.players = bots.map(bot => ({ username: bot.username, messages: bot.lines, failure: bot.failure,
    dialogCount: bot.dialogs.length, inventoryOpens: bot.inventoryOpens }));
  const output = process.env.HILL175_DIALOG_REPORT ?? path.join(root, 'runtime/local-server-control/dialog-smoke-report.json');
  mkdirSync(path.dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2));
  for (const bot of bots) bot.quit('Campus dialog smoke complete');
  console.log('Report: ' + output);
}
