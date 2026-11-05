// Real Java and Bedrock command clients. World assertions use the disposable runner's console.
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const platform = process.argv[2] ?? 'java';
const phase = process.argv[3] ?? 'flow';
const fixture = process.env.HILL175_RECOVERY_FIXTURE;
if (!fixture || !existsSync(path.join(fixture, '.hill175-smoke-fixture')) || !readFileSync(path.join(fixture, 'server.properties'), 'utf8').includes('server-ip=127.0.0.1')) throw Error('Use a disposable loopback recovery fixture.');
const run = String(Date.now()).slice(-8);
const accountFile = path.join(fixture, 'recovery-' + platform + '-account.json');
const account = (platform === 'bedrock' || phase !== 'flow') && existsSync(accountFile) ? JSON.parse(readFileSync(accountFile, 'utf8'))
  : { name: (platform === 'bedrock' ? '.' : '') + 'Rec' + run, password: 'Fixture' + randomUUID().replaceAll('-', '') };
const { name, password } = account;
writeFileSync(accountFile, JSON.stringify(account));
const messages = [], checks = [];
const report = { platform, name, checks, messages, success: false };
report.packets = {};
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let client, heartbeat, failure;
let currentForm, bedrockPosition, bedrockInventory = [];
let javaDialog, javaNbt;
const previewFlow = process.env.HILL175_RECOVERY_PREVIEW === '1';
function itemText(item) { return JSON.stringify([item?.customName, item?.customLore, item?.extra?.nbt], (_, value) => typeof value === 'bigint' ? String(value) : value); }
function menuHas(text) { return platform === 'java' ? client.currentWindow?.slots.slice(0, client.currentWindow.inventoryStart).some(item => itemText(item).includes(text)) : currentForm?.data.buttons?.some(button => button.text.includes(text)); }
async function choose(text) {
  await until(() => menuHas(text), 'menu choice ' + text);
  if (platform === 'java') {
    const slot = client.currentWindow.slots.slice(0, client.currentWindow.inventoryStart).findIndex(item => itemText(item).includes(text));
    await client.clickWindow(slot, 0, 0);
  } else {
    const form = currentForm;
    const index = form.data.buttons.findIndex(button => button.text.includes(text)); currentForm = null;
    client.queue('modal_form_response', { form_id: form.id, has_response_data: true, data: JSON.stringify(index), has_cancel_reason: false });
  }
  await delay(300);
}
async function tool(slot, text) {
  await until(() => itemText(platform === 'java' ? client.inventory.slots[36 + slot] : bedrockInventory[slot]).includes(text), 'hotbar ' + text);
  if (platform === 'java') {
    client.setQuickBarSlot(slot); client._client.write('held_item_slot', { slotId: slot });
    await delay(200); client.activateItem(); await delay(100); client.deactivateItem();
  } else {
    const item = { ...bedrockInventory[slot], has_stack_id: false, block_runtime_id: 0, extra: { has_nbt: 'false', can_place_on: [], can_destroy: [] } };
    client.queue('mob_equipment', { runtime_entity_id: client.entityId, item, slot, selected_slot: slot, window_id: 'inventory' });
    await delay(200);
    client.queue('inventory_transaction', { transaction: { legacy: { legacy_request_id: 0 }, transaction_type: 'item_use', actions: [], transaction_data: {
      action_type: 'click_air', trigger_type: 'player_input', block_position: { x: 0, y: 0, z: 0 }, face: 255, hotbar_slot: slot,
      hand: 'main_hand', held_item: item, player_pos: bedrockPosition, click_pos: { x: 0, y: 0, z: 0 }, block_runtime_id: 0, client_prediction: 'success', client_cooldown_state: 'off',
    } } });
  }
}
async function enterPreview() {
  await tool(8, 'Hill Campus Map');
  if (platform === 'java') {
    await until(() => javaDialog && JSON.stringify(javaNbt.simplify(javaDialog)).includes('Staff Recovery'), 'map staff recovery button');
    const raw = javaDialog.value.actions.value.value.find(button => JSON.stringify(javaNbt.simplify({ type: 'compound', value: button }).label).includes('Staff Recovery'));
    if (!raw) { report.dialog = javaNbt.simplify(javaDialog); throw Error('Staff Recovery native callback missing.'); }
    client._client.write('custom_click_action', { id: raw.action.value.id.value,
      nbt: javaNbt.proto.createPacketBuffer('anonymousNbt', raw.action.value.additions) });
    javaDialog = null;
  } else await choose('Staff Recovery');
  await choose('Hunt and Sweeney');
  await expect(() => choose(report.snapshot.slice(0, 8)), /Recovery preview ready:/, 180000);
  await expect(() => fixtureCommand('load-preview'), /RECOVERY_PREVIEW_POSITION/);
  await delay(1500);
  await expect(() => fixtureCommand('assert-preview'), /RECOVERY_PREVIEW_EXACT/);
}

async function until(predicate, label, timeout = 45000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (failure) throw failure;
    const previewFailure = messages.find(line => line.startsWith('Could not open that preview:'));
    if (previewFailure) throw Error(previewFailure);
    const value = predicate(); if (value) return value;
    await delay(100);
  }
  throw Error('Timed out: ' + label + '\n' + messages.slice(-15).join('\n'));
}
function fixtureCommand(action, fields = {}) { console.log('SMOKE_RECOVERY ' + JSON.stringify({ action, name, ...fields })); }
async function expect(action, pattern, timeout) {
  const start = messages.length; await action();
  return until(() => messages.slice(start).find(line => pattern.test(line)), String(pattern), timeout);
}
async function check(name, action) { await action(); checks.push(name); console.log('PASS: ' + name); }
function command(text) {
  if (platform === 'java') client.chat(text);
  else client.queue('command_request', { command: text, origin: { type: 'player', uuid: randomUUID(), request_id: '', player_entity_id: 0n }, internal: false, version: 'latest' });
}

async function connect(reconnecting = false) {
  const admissionStart = messages.length;
  failure = undefined;
  if (platform === 'java') {
    const require = createRequire(path.join(root, 'runtime/smoke-bot/mineflayer/package.json'));
    javaNbt = require('prismarine-nbt');
    client = require(path.join(root, 'runtime/smoke-bot/mineflayer/index.js')).createBot({ host: '127.0.0.1', port: Number(process.env.HILL175_RECOVERY_JAVA_PORT), username: name, auth: 'offline', plugins: { team: false } });
    client.on('messagestr', line => { messages.push(line); console.log(name + ': ' + line); });
    client.on('error', error => { failure = error; });
    client.on('kicked', reason => { failure = Error(JSON.stringify(reason)); });
    client._client.on('packet', (data, metadata) => { report.packets[metadata.name] = (report.packets[metadata.name] ?? 0) + 1; });
    client._client.on('show_dialog', packet => { javaDialog = packet.dialog?.data; });
    await until(() => client.entity && messages.slice(admissionStart).some(line => /\/register |\/login /.test(line)), 'Java admission', 90000);
  } else {
    const require = createRequire(path.join(root, 'runtime/bedrock-protocol-smoke/package.json'));
    client = require('bedrock-protocol').createClient({ host: '127.0.0.1', port: Number(process.env.HILL175_RECOVERY_BEDROCK_PORT), version: '1.26.51', offline: true, username: name.slice(1), skinData: { GameVersion: '1.26.52' }, transport: 'raknet', raknetBackend: 'raknet-native', followPort: false, conLog: () => {}, connectTimeout: 90000 });
    let spawned = false, position, yaw = 0, pitch = 0, tick = 0n, teleport = false;
    const record = packet => {
      if (packet.runtime_id != null && String(packet.runtime_id) !== String(client.entityId)) return;
      position = packet.position ?? packet.player_position; yaw = packet.yaw ?? yaw; pitch = packet.pitch ?? pitch; teleport = true;
      bedrockPosition = position;
    };
    client.on('spawn', () => { spawned = true; });
    client.on('start_game', record); client.on('move_player', record);
    client.on('change_dimension', packet => {
      record(packet); client.queue('player_action', { runtime_entity_id: client.entityId, action: 'dimension_change_ack', position: { x: 0, y: 0, z: 0 }, result_position: { x: 0, y: 0, z: 0 }, face: 0 });
    });
    client.on('text', packet => { const line = packet.message.replace(/§./g, ''); messages.push(line); console.log(name + ': ' + line); });
    client.on('modal_form_request', packet => { currentForm = { id: packet.form_id, data: JSON.parse(packet.data) }; });
    client.on('inventory_content', packet => { if (packet.window_id === 'inventory') bedrockInventory = packet.input; });
    client.on('inventory_slot', packet => { if (packet.window_id === 'inventory') bedrockInventory[packet.slot] = packet.item; });
    client.on('error', error => { failure = error; });
    client.on('kick', packet => { failure = Error(packet.message); });
    heartbeat = setInterval(() => {
      if (!position || !client.entityId) return;
      try {
        client.queue('player_auth_input', { pitch, yaw, position, move_vector: { x: 0, z: 0 }, head_yaw: yaw,
          input_data: teleport ? ['handled_teleport'] : [], input_mode: 'touch', play_mode: 'normal', interaction_model: 'touch',
          interact_rotation: { x: pitch, z: yaw }, tick: ++tick, delta: { x: 0, y: 0, z: 0 }, analogue_move_vector: { x: 0, z: 0 }, camera_orientation: { x: 0, y: 0, z: 1 }, raw_move_vector: { x: 0, z: 0 } });
        teleport = false;
      } catch (error) { failure = error; }
    }, 50);
    await until(() => spawned, 'Bedrock UDP admission', 90000);
    await delay(1500);
  }
  const returning = reconnecting || messages.slice(admissionStart).some(line => line.includes('/login '));
  await expect(() => command(returning ? `/login ${password}` : `/register ${password} ${password}`), /Registration complete|Login successful/, 45000);
  await delay(2500);
  command('/campus home');
  await delay(1500);
  await expect(() => fixtureCommand('campus'), /RECOVERY_CAMPUS/);
}

try {
  await connect();
  if (phase !== 'flow') {
    report.snapshot = JSON.parse(readFileSync(path.join(fixture, 'recovery-' + platform + '.json'), 'utf8')).snapshot;
    if (phase === 'prepare-restart') {
      await expect(() => fixtureCommand('grant'), /RECOVERY_GRANT/); await delay(500);
      await expect(() => fixtureCommand('inventory'), /RECOVERY_INVENTORY/);
      await expect(() => fixtureCommand('damage'), /RECOVERY_DAMAGED/);
      await enterPreview();
      const ended = new Promise(resolve => client.once(platform === 'java' ? 'end' : 'close', resolve));
      fixtureCommand('restart'); await Promise.race([ended, delay(45000)]);
      report.checks.push('server stopped while an actual preview was open');
    } else if (phase === 'after-restart') {
      await expect(() => fixtureCommand('assert-canceled'), /RECOVERY_CANCEL_EXACT/);
      report.checks.push('inventory recovered after server restart without restoring live blocks');
    } else throw Error('Unknown smoke phase.');
  } else {
  await check(platform + ' student cannot use recovery controls', () => expect(() => command('/campusbackup save'), /Only campus staff/));
  await expect(() => fixtureCommand('grant'), /RECOVERY_GRANT/);
  await delay(1200);
  await check('LuckPerms grants only the assigned area without operator access', async () => {
    await expect(() => command('/campusbackup areas'), /area-s7/);
    await expect(() => command('/campusbackup restore 00000000 area-s1 confirm'), /do not have recovery access/);
    await expect(() => command('/op RecoveryIntruder'), /Unknown|permission|not have access|not allowed|Only Hill competition commands/i);
  });
  await expect(() => fixtureCommand('seed'), /RECOVERY_SEEDED/);
  await check('staff captures a verified Restic snapshot', async () => {
    const line = await expect(() => command('/campusbackup save'), /Campus backup saved: /, 180000);
    report.snapshot = line.split('Campus backup saved: ')[1].trim();
  });
  await expect(() => fixtureCommand('damage'), /RECOVERY_DAMAGED/);
  await check('area restoration requires explicit confirmation', async () => {
    await expect(() => command(`/campusbackup restore ${report.snapshot} area-s7`), /Confirm with/);
    await expect(() => fixtureCommand('assert-damaged'), /RECOVERY_STILL_DAMAGED/);
  });
  if (previewFlow) {
    await check('staff selects an area and version and enters an isolated read only preview', enterPreview);
    await check('cancel returns inventory and leaves the live campus unchanged', async () => {
      await expect(() => tool(8, 'Cancel Preview'), /Recovery preview canceled/);
      await expect(() => fixtureCommand('assert-canceled'), /RECOVERY_CANCEL_EXACT/);
    });
    await enterPreview();
    await check('disconnecting during preview preserves the player inventory', async () => {
      clearInterval(heartbeat);
      const ended = new Promise(resolve => client.once(platform === 'java' ? 'end' : 'close', resolve));
      if (platform === 'java') client.quit(); else client.close();
      await Promise.race([ended, delay(5000)]); await delay(800);
      await connect(true);
      await expect(() => fixtureCommand('assert-canceled'), /RECOVERY_CANCEL_EXACT/);
    });
    await enterPreview();
    await check('hotbar opens another version selection and replaces the temporary world', async () => {
      await tool(4, 'Choose Another Version');
      await expect(() => choose(report.snapshot.slice(0, 8)), /Recovery preview ready:/, 180000);
      await expect(() => fixtureCommand('load-preview'), /RECOVERY_PREVIEW_POSITION/);
      await delay(1500);
      await expect(() => fixtureCommand('assert-preview'), /RECOVERY_PREVIEW_EXACT/);
    });
  }
  await check('area restore finishes while the client stays connected', () => expect(
    () => previewFlow ? tool(0, 'Confirm Restore') : command(`/campusbackup restore ${report.snapshot} area-s7 confirm`), /Campus area restored: area-s7/, 240000));
  await check('saved block and chest contents return while adjacent area stays changed', () => expect(() => fixtureCommand('assert-restored'), /RECOVERY_EXACT_RESTORE/));
  await check('staff can list recovery points after restoration', () => expect(() => command('/campusbackup list'), new RegExp(report.snapshot.slice(0, 8))));
  }
  report.success = true;
} catch (error) { report.error = String(error.stack ?? error); console.error(report.error); process.exitCode = 1; }
finally {
  clearInterval(heartbeat);
  if (platform === 'java') client?.quit(); else client?.close();
  writeFileSync(path.join(fixture, 'recovery-' + platform + (phase === 'flow' ? '' : '-' + phase) + '.json'), JSON.stringify(report, null, 2));
}
await delay(500);
process.exit(process.exitCode ?? 0);
