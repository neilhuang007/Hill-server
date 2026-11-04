import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'runtime/smoke-bot/mineflayer/package.json'));
const mineflayer = require(path.join(root, 'runtime/smoke-bot/mineflayer/index.js'));
const { Vec3 } = require('vec3');
const host = process.env.HILL175_SMOKE_HOST ?? '127.0.0.1';
const port = Number(process.env.HILL175_SMOKE_PORT ?? 25568);
const run = String(Date.now()).slice(-8);
const password = 'LocalArea' + run + '!';
const report = { host, port, run, checks: [], messages: [] };
const output = process.env.HILL175_AREA_REPORT ?? path.join(root, 'runtime/area-work-20261029/java-area-result.json');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const bots = [];
async function until(check, label, timeout = 30000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (check()) return; await delay(100); }
  throw Error('Timed out: ' + label + '; clients=' + JSON.stringify(bots.map(bot=>({name:bot.username,world:bot.worldId,mode:bot.game?.gameMode}))));
}
function text(item) { return JSON.stringify([item?.customName, item?.customLore]); }
function top(bot) { return bot.currentWindow?.slots.slice(0, bot.currentWindow.inventoryStart) ?? []; }
function has(bot, label) { return top(bot).some(item => text(item).includes(label)); }
async function command(bot, value) { bot.chat(value); await delay(250); }
async function open(bot, action, label) {
  const previous = bot.currentWindow;
  await action();
  await until(() => bot.currentWindow && bot.currentWindow !== previous && has(bot, label), 'menu ' + label);
}
async function click(bot, label) {
  const slot = top(bot).findIndex(item => text(item).includes(label));
  if (slot < 0) throw Error('Missing action ' + label + ': ' + JSON.stringify(top(bot).map(text)));
  await bot.clickWindow(slot, 0, 0);
  await delay(250);
}
async function useTool(bot, label) {
  await until(() => bot.inventory.slots.slice(36, 45).some(item => text(item).includes(label)), 'hotbar ' + label);
  const slot = bot.inventory.slots.slice(36, 45).findIndex(item => text(item).includes(label));
  bot.setQuickBarSlot(slot);
  bot._client.write('held_item_slot', { slotId: slot });
  await delay(150);
  bot.activateItem(); await delay(180); bot.deactivateItem();
}
async function controls(bot) {
  if (bot.currentWindow) bot.closeWindow(bot.currentWindow);
  await useTool(bot, 'Entry Controls');
  await until(() => has(bot, 'Build Options'), 'entry controls');
}
async function connect(name) {
  const bot = mineflayer.createBot({host,port,username:name,auth:'offline',plugins:{team:false},hideErrors:false});
  bots.push(bot); bot.lines = []; bot.worldId = '';
  bot._client.on('login', packet => { bot.worldId = packet?.worldState?.name?.split(':').at(-1) ?? bot.worldId; });
  bot._client.on('respawn', packet => { bot.worldId = packet?.worldState?.name?.split(':').at(-1) ?? bot.worldId; });
  bot.on('messagestr', line => { bot.lines.push(line); report.messages.push(name + ': ' + line); console.log(name + ': ' + line); });
  bot.on('error', error => { report.messages.push(String(error)); });
  await until(() => bot.entity && bot.lines.some(line => /register|login/i.test(line)), 'student admission', 60000);
  await command(bot, `/register ${password} ${password}`);
  await until(() => bot.lines.some(line => /Registration complete|registered|logged in|authentication complete/i.test(line)), 'registration', 30000);
  return bot;
}
async function check(label, action) {
  await action(); report.checks.push(label); console.log('PASS: ' + label);
}
async function move(bot, point) {
  bot.physicsEnabled = false;
  const from = bot.entity.position.clone();
  const steps = Math.ceil(from.distanceTo(point) / 0.6);
  for (let index = 1; index <= steps; index++) {
    const p = from.scaled(1-index/steps).plus(point.scaled(index/steps));
    bot.entity.position.set(p.x,p.y,p.z);
    bot._client.write('position',{x:p.x,y:p.y,z:p.z,flags:{onGround:false,hasHorizontalCollision:false}});
    await delay(50);
  }
  await delay(400);
}
function findPatch(bot) {
  const origin=bot.entity.position.floored();
  for(let radius=1;radius<9;radius++) for(let dx=-radius;dx<=radius;dx++) for(let dz=-radius;dz<=radius;dz++) {
    const point=origin.offset(dx,0,dz);
    for(let dy=4;dy>=-8;dy--) {
      const p=point.offset(0,dy,0), floor=bot.blockAt(p.offset(0,-1,0));
      if(floor?.boundingBox==='block' && !/leaves|water|chest|door|fence|wall/.test(floor.name)
        && bot.blockAt(p)?.name==='air' && bot.blockAt(p.offset(0,1,0))?.name==='air') return p;
    }
  }
  throw Error('No safe loaded test patch');
}

try {
  const owner=await connect('Area'+run);
  const friend=await connect('Peer'+run);
  await check('Area selector, detail, back and confirmation',async()=>{
    await open(owner,()=>command(owner,'/competition'),'Start The Place');
    await open(owner,()=>click(owner,'Start The Place'),'Chapel and Warner');
    if(top(owner).filter(item=>item?.name==='grass_block').length!==7) throw Error('Seven areas must be visible');
    await open(owner,()=>click(owner,'Arts Center and North Pond Shore'),'Build Here');
    await open(owner,()=>click(owner,'Choose Another Area'),'Chapel and Warner');
    await open(owner,()=>click(owner,'Arts Center and North Pond Shore'),'Build Here');
    await click(owner,'Build Here');
    await until(()=>owner.worldId.startsWith('hill_place_') && owner.game.gameMode==='creative','private area creation',60000);
  });
  const world=owner.worldId;
  await check('Boundary and camera controls are reachable without commands',async()=>{
    await controls(owner);
    await open(owner,()=>click(owner,'Build Boundary'),'Where you can build');
    if(!JSON.stringify(top(owner).map(text)).includes('520, -545')) throw Error('Missing second area rectangle');
    await open(owner,()=>click(owner,'Back to Build Options'),'Build Options');
    await open(owner,()=>click(owner,'Submit Entry'),'Camera');
    owner.closeWindow(owner.currentWindow);
  });
  let patch;
  await check('Actual student places and breaks blocks',async()=>{
    await delay(2500); patch=findPatch(owner);
    await move(owner,patch.offset(2.5,1,0.5));
    const Item=require('prismarine-item')(owner.registry);
    await owner.creative.setInventorySlot(41,new Item(owner.registry.itemsByName.blue_wool.id,1));
    owner.setQuickBarSlot(5); owner._client.write('held_item_slot',{slotId:5});
    await delay(200);
    await owner.placeBlock(owner.blockAt(patch.offset(0,-1,0)),new Vec3(0,1,0));
    await until(()=>owner.blockAt(patch)?.name==='blue_wool','placed block');
    await owner.dig(owner.blockAt(patch));
    await until(()=>owner.blockAt(patch)?.name==='air','broken block');
  });
  await check('GUI invite and accept lead both students to the same world',async()=>{
    await controls(owner);
    await open(owner,()=>click(owner,'Team'),'Build together');
    await click(owner,'Invite '+friend.username);
    await open(friend,()=>command(friend,'/competition'),'Accept Team Invite');
    await click(friend,'Accept Team Invite');
    await until(()=>friend.worldId===world && friend.game.gameMode==='creative','shared team world');
    owner.closeWindow(owner.currentWindow);
  });
  await check('Save a camera, preview, exit and submit from the GUI',async()=>{
    await useTool(owner,'Capture Camera View');
    await until(()=>owner.lines.some(line=>/camera.*saved|saved.*camera/i.test(line)),'saved view');
    await controls(owner);
    await open(owner,()=>click(owner,'Camera Views'),'Camera');
    await open(owner,()=>click(owner,'Camera 1'),'Preview Camera');
    await click(owner,'Preview Camera');
    await until(()=>owner.inventory.slots.some(item=>text(item).includes('Exit Camera')),'camera exit item');
    await useTool(owner,'Exit Camera');
    await controls(owner);
    await open(owner,()=>click(owner,'Submit Entry'),'Confirm Submission');
    await click(owner,'Confirm Submission');
    await until(()=>owner.lines.some(line=>line.includes('submitted, published, and locked')),'automatic publication',120000);
    await until(()=>owner.game.gameMode!=='creative' && friend.game.gameMode!=='creative','submission locks both members');
  });
  await check('Resume editing withdraws submission and restores both students',async()=>{
    await controls(owner); await click(owner,'Resume Editing');
    await until(()=>owner.game.gameMode==='creative' && friend.game.gameMode==='creative','shared edit restoration');
  });
  await check('Team leave cancellation and confirmed leave',async()=>{
    await controls(friend);
    await open(friend,()=>click(friend,'Team'),'Build together');
    await open(friend,()=>click(friend,'Leave Team'),'Confirm Leave');
    await open(friend,()=>click(friend,'Back Without Changes'),'Build Options');
    await open(friend,()=>click(friend,'Team'),'Build together');
    await open(friend,()=>click(friend,'Leave Team'),'Confirm Leave');
    await click(friend,'Confirm Leave');
    await until(()=>friend.worldId!==world,'teammate returns to hub');
  });
  await check('Reset cancellation preserves the area; confirmed reset restores it',async()=>{
    await controls(owner);
    await open(owner,()=>click(owner,'Project Settings'),'Manage this project');
    await open(owner,()=>click(owner,'Reset'),'Confirm Reset');
    await open(owner,()=>click(owner,'Back Without Changes'),'Build Options');
    await open(owner,()=>click(owner,'Project Settings'),'Manage this project');
    await open(owner,()=>click(owner,'Reset'),'Confirm Reset');
    await click(owner,'Confirm Reset');
    await until(()=>owner.lines.some(line=>/reset complete|has been reset|entry reset/i.test(line)),'reset completed',60000);
  });
  await check('Delete cancellation and confirmed cleanup',async()=>{
    await controls(owner);
    await open(owner,()=>click(owner,'Project Settings'),'Manage this project');
    await open(owner,()=>click(owner,'Delete'),'Confirm Delete');
    await open(owner,()=>click(owner,'Back Without Changes'),'Build Options');
    await open(owner,()=>click(owner,'Project Settings'),'Manage this project');
    await open(owner,()=>click(owner,'Delete'),'Confirm Delete');
    await click(owner,'Confirm Delete');
    await until(()=>owner.worldId!==world,'project removed and player returned');
  });
  report.success=true;
} catch(error) { report.success=false; report.error=String(error.stack??error); console.error(error); process.exitCode=1; }
finally { for(const bot of bots) bot.quit(); mkdirSync(path.dirname(output),{recursive:true}); writeFileSync(output,JSON.stringify(report,null,2)); }
await delay(500); process.exit(process.exitCode??0);
