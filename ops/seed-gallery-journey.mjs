import {createRequire} from "node:module";
import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";

// Creates a clearly labelled local exhibition example through normal player actions.
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const dependencies=path.join(root,"runtime/smoke-bot/mineflayer");
const require=createRequire(path.join(dependencies,"package.json"));
const mineflayer=require(path.join(dependencies,"index.js"));
const {Vec3}=require("vec3");
const existingAccount=process.env.HILL175_EXAMPLE_ACCOUNT;
const captureOnly=process.env.HILL175_EXAMPLE_CAPTURE_ONLY==="1";
const username=existingAccount??`Demo${String(Date.now()).slice(-9)}`;
const password="LocalGalleryExample123!";
const history=[];
const bot=mineflayer.createBot({host:"127.0.0.1",port:25566,username,auth:"offline",plugins:{team:false}});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
bot.on("messagestr",text=>history.push(text));
async function waitFor(predicate,label,timeout=30000) {
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline) {const result=await predicate();if(result)return result;await delay(100);}
  throw new Error(`Timeout: ${label}`);
}
async function command(text,expected,timeout=30000) {
  const start=history.length;bot.chat(text);
  return waitFor(()=>history.slice(start).find(line=>expected.test(line)),text.split(" ").slice(0,2).join(" "),timeout);
}
async function menu(action) {
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error("Menu timeout")),10000);
    bot.once("windowOpen",window=>{clearTimeout(timer);resolve(window);});action();
  });
}
try {
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error("Join timeout")),60000);
    bot.once("spawn",()=>{clearTimeout(timer);resolve();});bot.once("error",reject);
  });
  if(existingAccount) {
    await command(`/login ${password}`,/Login successful/);
    await command("/entry home",/Owner Mode|Visitor Mode|submitted|locked/);
    if(captureOnly)await command("/entry unlock",/Submission unlocked/);
    for(const slot of captureOnly?[1,2,3]:[1]) {
      await menu(()=>bot.chat(`/camera remove ${slot}`));
      await bot.clickWindow(4,0,0);
      await delay(300);
    }
  } else {
    await command(`/register ${username} ${password} ${password}`,/Registration complete/);
    await command("/entry create journey",/Journey entry created/);
  }
  await command("/entry title Smoke test - Hill 175 monument",/Project title saved/);
  await command("/entry description Local smoke-test example. Built by an automated player and submitted through the normal camera flow.",/Project description saved/);
  await bot.waitForChunksToLoad();
  const start=bot.entity.position.clone();
  const ground=bot.blockAt(start.offset(0,-1,5).floored());
  if(!ground||ground.name==="air")throw new Error("No solid Journey ground");
  const origin=ground.position.offset(-6,1,0);
  const Item=require("prismarine-item")(bot.version);
  const materials=["smooth_quartz","blue_concrete","gold_block"];
  const hotbarSlots=[2,4,5];
  for(let i=0;i<materials.length;i++)await bot.creative.setInventorySlot(36+hotbarSlots[i],new Item(bot.registry.itemsByName[materials[i]].id,64));
  const glyph=["0101110111","1100010100","0100100111","0100100001","1110100111"];
  for(let y=0;y<(captureOnly?0:7);y++) {
    for(let x=0;x<13;x++) {
      const target=origin.offset(x,y,0);
      const frame=y===0||y===6||x===0||x===12;
      const material=frame?0:(x>=2&&x<=11&&glyph[5-y]?.[x-2]==="1"?2:1);
      if(bot.blockAt(target)?.name===materials[material])continue;
      await bot.creative.flyTo(target.offset(.5,1,-2.5));
      const support=bot.blockAt(target.offset(0,-1,0));
      if(!support||support.name==="air")throw new Error(`Missing support at ${target}`);
      bot.setQuickBarSlot(hotbarSlots[material]);
      await delay(80);
      await bot.placeBlock(support,new Vec3(0,1,0));
      await waitFor(()=>bot.blockAt(target)?.name===materials[material],"placed monument block",10000);
    }
    console.log(`Monument row ${y+1}/7 placed through player packets.`);
  }
  const focus=origin.offset(6.5,3.2,.5);
  const views=[origin.offset(6.5,3.3,-10),origin.offset(-3,5,-8),origin.offset(16,5,-8)];
  for(let index=0;index<views.length;index++) {
    await bot.creative.flyTo(views[index]);
    await bot.lookAt(focus,true);
    await delay(500);
    await command(`/camera save ${index+1}`,new RegExp(`Camera ${index+1}/3 saved`));
  }
  const link=await waitFor(()=>history.find(line=>/\/preview\/[A-Za-z0-9_-]{22,64}/.test(line)),"preview link",180000);
  const token=link.match(/\/preview\/([A-Za-z0-9_-]{22,64})/)[1];
  const preview=await (await fetch(`http://127.0.0.1:8788/api/preview/${token}`)).json();
  await menu(()=>bot.chat("/entry submit"));
  const submitStart=history.length;
  await bot.clickWindow(4,0,0);
  await waitFor(()=>history.slice(submitStart).some(line=>line.includes("submitted, published, and locked")),"public submission",240000);
  const entry=await (await fetch(`http://127.0.0.1:8788/api/entries/${preview.id}`)).json();
  if(entry.images.length!==3)throw new Error("Expected three public camera images");
  const output=path.join(root,"runtime/gallery-journey-example");await mkdir(output,{recursive:true});
  await writeFile(path.join(output,"result.json"),JSON.stringify({username,entryId:entry.id,url:`http://localhost:8788/entries/${entry.id}`,title:entry.title,submitted:true},null,2));
  for(const image of entry.images)await writeFile(path.join(output,`camera-${image.slot}.png`),Buffer.from(await(await fetch(`http://127.0.0.1:8788${image.url}`)).arrayBuffer()));
  console.log(`Published local smoke example: http://localhost:8788/entries/${entry.id}`);
}catch(error){console.error(error.stack);console.error(history.slice(-10).join("\n"));process.exitCode=1;}
finally{bot.quit();bot.end();await delay(250);}
process.exit(process.exitCode??0);
