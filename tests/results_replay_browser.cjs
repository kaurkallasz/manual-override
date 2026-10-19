/* Real phone / stats pages against an isolated Game and Progress instance. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8142',output='output/results-replay-2026-10-19';
const server=spawn('.venv/bin/python',['tests/results_replay_fixture.py'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,value){const r=await fetch(base+path,value?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}:{});const d=await r.json();assert(r.ok,JSON.stringify(d));return d;}
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('Replay fixture http:');i++)await wait(100);
  assert(logs.includes('Replay fixture http:'),logs);fs.mkdirSync(output,{recursive:true});
  const initial=await api('/__test/final-level',{});
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],green=await browser.newPage({viewport:{width:844,height:390}}),purple=await browser.newPage({viewport:{width:390,height:844}}),score=await browser.newPage({viewport:{width:1280,height:900}}),screen=await browser.newPage({viewport:{width:1440,height:900}});
  for(const p of [green,purple,score,screen]){p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message));}
  await Promise.all([green.goto(base+'/s/green/p/mobile-ltz/'),purple.goto(base+'/s/purple/p/mobile-ltz/'),score.goto(base+'/s/green/p/ltz-score/'),screen.goto(base+'/s/gamemaster/p/laser-tag-y/screen')]);
  for(const p of [green,purple,score]){
   await p.locator('.ltzLevelResult h2').filter({hasText:'You Win! Game Over'}).waitFor();
   assert.equal(await p.locator('[data-result-choice="continue"]').count(),0);
   assert.equal(await p.locator('[data-result-choice]').count(),3);
   const map=p.locator('.ltzLevelResult .ltzHeatmap');await map.evaluate(e=>e.scrollIntoView({block:'center'}));
   assert.match(await map.textContent(),/30 in one area/);assert.match(await map.textContent(),/35 orcs mapped/);
   assert.equal(await map.locator('rect').count(),3);
   assert(await map.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  }
  await purple.screenshot({path:output+'/victory-heatmap-portrait.png'});
  await green.locator('.ltzLevelResult h2').evaluate(e=>e.scrollIntoView());await green.screenshot({path:output+'/victory-landscape.png'});
  await score.screenshot({path:output+'/stats-heatmap-desktop.png'});
  // Finish the replay too: import isolation used to fail here in production.
  let replayRun=initial.run_id;
  for(let attempt=0;attempt<2;attempt++){
   for(const p of [green,purple])await p.locator('[data-result-choice="replay_level"]').click();
   await green.waitForFunction(()=>document.querySelector('#gameJourney').hidden);
   const playing=await api('/s/gamemaster/p/photon-game/api/state');
   assert.equal(playing.phase,'running');assert.equal(playing.contract_control_tier,4);assert.notEqual(playing.run_id,replayRun);
   replayRun=playing.run_id;
   if(attempt===0){
    const pending=await api('/__test/finish-pending',{});assert.equal(pending.result_save.status,'saving');
    for(const p of [green,purple,score]){
     try{await p.locator('.ltzPendingResult h2').filter({hasText:'You Win! Game Over'}).waitFor();}
     catch(error){console.error('Pending result failure',p.url(),await p.locator('#journeyContent,#tracks').textContent(),errors);throw error;}
     assert.equal(await p.locator('[data-result-choice]:enabled').count(),0);
     assert.match(await p.locator('.ltzPendingResult .ltzHeatmap').textContent(),/35 orcs mapped/);
    }
    await purple.reload();await purple.locator('.ltzPendingResult h2').filter({hasText:'You Win! Game Over'}).waitFor();
    await purple.screenshot({path:output+'/victory-save-pending.png'});
    await api('/__test/retry-save',{});
   }else await api('/__test/finish',{});
   for(const p of [green,purple,score]){
    await p.locator(`.ltzLevelResult[data-result="${replayRun}"] h2`).filter({hasText:'You Win! Game Over'}).waitFor();
    await p.locator('[data-result-choice="replay_level"]:enabled').waitFor();
   }
  }
  // Different choices wait; a matching choice from the stats page launches once.
  await green.locator('[data-result-choice="replay_level"]').click();
  await purple.locator('[data-result-choice="replay_game"]').click();
  assert.equal((await api('/s/gamemaster/p/photon-game/api/state')).phase,'won');
  await score.locator('[data-result-choice="replay_game"]').click();
  await green.waitForFunction(()=>document.querySelector('#gameJourney').hidden);
  let next=await api('/s/gamemaster/p/photon-game/api/state');assert.equal(next.phase,'running');assert.equal(next.contract_control_tier,1);assert.notEqual(next.run_id,initial.run_id);
  await api('/__test/ring/complete',{});
  for(const p of [green,purple,screen])await p.locator('.ltzRingNotice').filter({hasText:'Ring activated!'}).waitFor();
  await api('/__test/ring/break',{});
  for(const p of [green,purple,screen])await p.locator('.ltzRingNotice').filter({hasText:'Complete the ring again before the center reactivates'}).waitFor();
  await green.screenshot({path:output+'/ring-incomplete.png'});
  await green.reload();await green.locator('.ltzRingNotice').filter({hasText:'Ring incomplete!'}).waitFor();
  await api('/__test/ring/repair',{});await green.locator('.ltzRingNotice').filter({hasText:'Ring activated!'}).waitFor();
  await api('/__test/finish',{});
  for(const p of [green,purple])await p.locator('.ltzLevelResult h2').filter({hasText:'Level 1 complete'}).waitFor();
  assert.match(await green.locator('.ltzLevelResult .ltzHeatmap').textContent(),/No orcs were killed/);
  for(const p of [green,purple])await p.locator('[data-result-choice="new"]').click();
  for(const p of [green,purple])await p.locator('#journeyNewName').waitFor();
  assert.equal(Object.keys((await api('/s/gamemaster/p/photon-progress/api/state?side=green')).roster).length,0);
  assert.deepEqual(errors,[]);
  console.log('PASS: repeated L4 replay wins under production import isolation, victory/heatmap during save failure and reconnect, save recovery, matching replay choices, L1 restart, ring notices, zero-kill result, New game, no browser errors');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-3000));process.exitCode=1;});
