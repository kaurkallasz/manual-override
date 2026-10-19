/* Real GM and both phone pages, temporary data and fake arm feedback only. */
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),fs=require('node:fs');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8138',output='output/event-progression-2026-10-17';
const server=spawn('.venv/bin/python',['tests/mobile_ltz_fixture.py','--port','8138','--isolate-imports'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,value){const r=await fetch(base+path,value?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}:{});const d=await r.json();assert(r.ok,d.error||JSON.stringify(d));return d;}
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('Mobile fixture http:');i++)await wait(100);
  assert(logs.includes('Mobile fixture http:'),logs);fs.mkdirSync(output,{recursive:true});
  await api('/__test/camera',{enabled:true});
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],gm=await browser.newPage({viewport:{width:1440,height:1080}});
  const green=await browser.newPage({viewport:{width:844,height:390},deviceScaleFactor:1}),purple=await browser.newPage({viewport:{width:844,height:390},deviceScaleFactor:1});
  for(const p of [gm,green,purple]){p.setDefaultTimeout(12000);p.on('pageerror',e=>{errors.push(e.message);console.error('BROWSER',e.message);});}
  await gm.goto(base+'/s/gamemaster/p/laser-tag-y/',{waitUntil:'domcontentloaded'});
  await gm.locator('#eventSelect option[value="__create"]').waitFor({state:'attached'});
  await gm.locator('#eventSelect').selectOption('__create');await gm.locator('#eventName').fill('Browser event');
  await gm.locator('#eventCreateForm button[type="submit"]').click();
  await gm.waitForFunction(()=>document.querySelector('#eventSelect').selectedOptions[0]?.textContent==='Browser event');
  assert.equal(await gm.locator('#testUnlocks,#testPlayerPanel,#scoredPlay,#virtualPlay').count(),0);
  for(const [side,p] of [['green',green],['purple',purple]]){
   await p.goto(base+'/s/'+side+'/p/mobile-ltz/',{waitUntil:'domcontentloaded'});
   await p.locator('#journeyNewName').fill(side+' browser');await p.locator('#journeyCreate').click();
   await p.waitForFunction(()=>document.querySelector('.journeyPlayerSummary')?.textContent.includes('L1'));
  }
  await gm.waitForFunction(()=>document.querySelector('#greenReadyName')?.textContent==='green browser'&&document.querySelector('#purpleReadyName')?.textContent==='purple browser');
  assert.equal(await gm.locator('.ready-player[data-ready="true"]').count(),0);
  await green.locator('#journeyReady').click();
  await gm.waitForFunction(()=>document.querySelector('#greenReadyCard')?.dataset.ready==='true');
  assert.equal(await gm.locator('#purpleReadyLabel').textContent(),'Waiting for Ready');
  await purple.locator('#journeyReady').click();
  await gm.waitForFunction(()=>document.querySelector('#readinessSummary')?.textContent==='Both players ready · press Start');
  assert.equal(await gm.locator('.ready-player[data-ready="true"]').count(),2);
  await gm.locator('section.controls').filter({has:gm.locator('#playerReadiness')}).screenshot({path:output+'/both-players-ready.png'});
  await gm.locator('#greenStartingAtom').selectOption('100');await gm.locator('#purpleStartingAtom').selectOption('102');
  const commandUrl=base+'/s/gamemaster/p/laser-tag-y/api/command';
  await gm.route(commandUrl,route=>route.fulfill({status:500,contentType:'text/html',body:'<!doctype html><h1>Internal Server Error</h1>'}),{times:1});
  await gm.locator('#start').click();
  await gm.waitForFunction(()=>document.querySelector('#startStatus')?.textContent.includes('HTTP 500'));
  assert(!(await gm.locator('#startStatus').textContent()).includes('<!doctype'));
  await gm.locator('#start').click();await gm.waitForFunction(()=>!document.querySelector('#endMatch').disabled);
  assert.equal(await gm.locator('#playerReadiness').isVisible(),false);
  for(const p of [green,purple])await p.locator('#coreObjective').filter({hasText:'Complete the ring'}).waitFor();
  let state=await api('/s/gamemaster/p/photon-progress/api/state?side=green');const event=state.events.active_id,saved=state.saved_games.active_id;
  assert(state.saved_games.pair_locked);assert.equal(state.player.current_control_tier,1);
  await gm.locator('#endMatch').click();await gm.waitForFunction(()=>!document.querySelector('#unlockNextLevel').disabled);
  for(const [side,p] of [['green',green],['purple',purple]]){
   await p.waitForFunction(()=>document.querySelector('.ltzReceipt')?.textContent.includes('Ended by Game Master'));
   state=await api('/s/gamemaster/p/photon-progress/api/state?side='+side);assert.equal(state.player.credits,-500);
   assert.equal(state.player.levels[side==='green'?'damage-machine-gun':'damage-mortar'],2);
   assert.equal(await p.locator('[data-buy]').count(),0);await p.screenshot({path:output+'/'+side+'-results.png'});
  }
  await gm.locator('#unlockNextLevel').click();await gm.waitForFunction(()=>document.querySelector('#unlockNextLevel').disabled);
  await purple.waitForFunction(()=>document.querySelector('.ltzReceipt')?.textContent.includes('L2 XYZ'));
  await gm.screenshot({path:output+'/gamemaster.png',fullPage:true});
  await gm.locator('#continueMatch').click();await gm.waitForFunction(()=>!document.querySelector('#start').disabled);
  await green.waitForFunction(()=>document.querySelector('[data-saved-game="save"]')&&!document.querySelector('[data-saved-game="save"]').disabled);
  await green.locator('[data-saved-game="save"]').click();
  await green.waitForFunction(()=>document.querySelector('#journeyMessage')?.textContent.includes('Game saved'));
  await green.locator('[data-saved-game="new"]').click();
  await green.waitForFunction(()=>document.querySelector('#journeyMessage')?.textContent.includes('New game prepared'));
  state=await api('/s/gamemaster/p/photon-progress/api/state?side=green');assert.equal(state.player.current_control_tier,1);assert.equal(state.player.credits,-500);
  await green.locator('#journeySavedGame').selectOption(saved);await green.locator('[data-saved-game="load"]').click();
  await green.waitForFunction(()=>document.querySelector('#journeyMessage')?.textContent.includes('Linked players and saved progress loaded'));
  for(const side of ['green','purple']){state=await api('/s/gamemaster/p/photon-progress/api/state?side='+side);assert.equal(state.player.current_control_tier,2);assert.equal(state.player.credits,-500);assert.equal(state.events.active_id,event);}
  await purple.reload({waitUntil:'domcontentloaded'});await purple.waitForFunction(()=>document.querySelector('.journeyPlayerSummary')?.textContent.includes('L2'));
  const score=await browser.newPage();score.on('pageerror',e=>errors.push(e.message));await score.goto(base+'/s/green/p/ltz-score/',{waitUntil:'domcontentloaded'});await score.waitForFunction(()=>document.querySelector('#scoreValue')?.textContent==='-500');
  assert.deepEqual(errors,[]);console.log('PASS: event creation, both phones Ready shown live on GM, production-style import isolation, readable HTTP failures, successful Start, both L1 phones, linked pair, automatic GM purchases/debt, L2 override, save/new/load, score page; no browser exceptions');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-2500));process.exitCode=1;});
