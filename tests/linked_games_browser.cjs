/* Real phone UI and owner routes against a temporary hub; no physical hardware. */
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),fs=require('node:fs');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8137',output='output/linked-games-2026-10-17';
const server=spawn('.venv/bin/python',['tests/ltz_admin_fixture.py','--port','8137'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,value){const r=await fetch(base+path,value?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}:{});const d=await r.json();assert(r.ok,d.error||JSON.stringify(d));return d;}
const gm=value=>api('/s/gamemaster/p/photon-game/api/command',value);
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('LTZ admin fixture:');i++)await wait(100);
  assert(logs.includes('LTZ admin fixture:'),logs);
  fs.mkdirSync(output,{recursive:true});
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/s/green/p/mobile-ltz/',{waitUntil:'domcontentloaded'});
  await page.locator('[data-saved-game="new"]').waitFor();
  await page.locator('[data-saved-game="new"]').click();
  await page.waitForFunction(()=>document.querySelector('#journeyMessage').textContent.includes('New game prepared'));
  await page.locator('[data-saved-game="save"]').click();
  await page.waitForFunction(()=>document.querySelector('#journeyMessage').textContent.includes('Game saved'));
  let state=await api('/s/gamemaster/p/photon-progress/api/state?side=green');
  const saved=state.saved_games.active_id;
  assert(saved);assert.equal(state.player.current_control_tier,1);
  const started=(await gm({action:'start',virtual_play:true,reward_enabled:false})).output;
  assert.equal(started.contract_control_tier,1);
  const forbidden=await fetch(base+'/s/gamemaster/p/photon-progress/api/player?side=purple',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'select',player_id:null})});
  assert.equal(forbidden.status,400);assert.match((await forbidden.json()).error,/pair is locked/);
  await gm({action:'test_end_match',run_id:started.run_id});
  for(const side of ['green','purple'])await api('/s/gamemaster/p/photon-game/api/player-admin',{action:'grant_credits',player_id:'ltz-test-'+side,amount:3000,operation_id:crypto.randomUUID()});
  state=await api('/s/gamemaster/p/photon-progress/api/state?side=green');
  const bought=await api('/s/gamemaster/p/photon-progress/api/player?side=green',{action:'purchase',track:'damage-machine-gun',level:2,revision:state.player.revision,catalog_revision:state.shop.catalog_revision,operation_id:crypto.randomUUID()});
  const expected=bought.result.balance;
  await page.waitForFunction(()=>document.querySelector('[data-saved-game="save"]')&&!document.querySelector('[data-saved-game="save"]').disabled);
  await page.locator('[data-saved-game="save"]').click();
  await page.waitForFunction(()=>document.querySelector('#journeyMessage').textContent.includes('Game saved'));
  await page.locator('[data-saved-game="new"]').click();
  await page.waitForFunction(()=>document.querySelector('#journeyMessage').textContent.includes('New game prepared'));
  state=await api('/s/gamemaster/p/photon-progress/api/state?side=purple');
  const other=state.players.find(p=>!p.is_test);
  await api('/s/gamemaster/p/photon-progress/api/player?side=purple',{action:'select',player_id:other.id});
  await page.locator('#journeySavedGame').selectOption(saved);
  await page.locator('[data-saved-game="load"]').click();
  await page.waitForFunction(()=>document.querySelector('#journeyMessage').textContent.includes('Linked players and saved progress loaded'));
  for(const side of ['green','purple']){
   state=await api('/s/gamemaster/p/photon-progress/api/state?side='+side);
   assert.equal(state.player.id,'ltz-test-'+side);
   assert.equal(state.player.credits,side==='green'?expected:3000);
   assert.equal(state.player.levels['damage-machine-gun'],side==='green'?2:1);
   assert.equal(state.saved_games.pair_locked,true);
  }
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('.savedGamePanel').waitFor();
  if(await page.locator('#journeyPlayer').count()===0)await page.locator('#journeyToggle').click();
  await page.waitForFunction(()=>document.querySelector('#journeyPlayer')?.disabled===true);
  await page.locator('.savedGamePanel').scrollIntoViewIfNeeded();
  await page.screenshot({path:output+'/green-phone.png'});
  await page.goto(base+'/s/purple/p/mobile-ltz/',{waitUntil:'domcontentloaded'});
  await page.locator('.savedGamePanel').waitFor();
  await page.locator('.savedGamePanel').scrollIntoViewIfNeeded();
  await page.screenshot({path:output+'/purple-phone.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: phone New/Save/Load, atomic linked pair, post-Start lock, both wallets, purchased upgrade and reload');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-2500));process.exitCode=1;});
