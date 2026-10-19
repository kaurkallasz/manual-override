/* Actual phone and projector pages; real temporary server; no physical devices. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8139',output='output/level-results-2026-10-18';
const server=spawn('.venv/bin/python',['tests/level_results_fixture.py'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,value){const r=await fetch(base+path,value?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}:{});const d=await r.json();assert(r.ok,JSON.stringify(d));return d;}
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('Results fixture http:');i++)await wait(100);
  assert(logs.includes('Results fixture http:'),logs);fs.mkdirSync(output,{recursive:true});
  const seed=await api('/__test/seed-results',{});
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],green=await browser.newPage({viewport:{width:844,height:390}}),purple=await browser.newPage({viewport:{width:390,height:844}}),screen=await browser.newPage({viewport:{width:1440,height:1080}});
  for(const p of [green,purple,screen]){p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message));}
  await Promise.all([green.goto(base+'/s/green/p/mobile-ltz/'),purple.goto(base+'/s/purple/p/mobile-ltz/'),screen.goto(base+'/s/gamemaster/p/laser-tag-y/screen')]);
  await api('/__test/finish-level',{});
  await green.locator('.ltzLevelResult h2').filter({hasText:'Level 1 complete'}).waitFor();
  const count=()=>green.locator('.ltzKillHero>strong').textContent().then(v=>Number(v.replaceAll(',','')));
  const early=await count();await wait(650);const middle=await count();await wait(2300);const end=await count();
  assert(early<=middle&&middle<=end&&early<900,JSON.stringify({early,middle,end}));assert.equal(end,900);
  for(const p of [green,purple]){
   await p.locator('.ltzLevelResult h2').filter({hasText:'Level 1 complete'}).waitFor();
   assert.equal(await p.locator('.ltzUnlock').count(),2);
   assert.match(await p.locator('.ltzCompare').nth(0).textContent(),/\+80\.0%/);
   assert.match(await p.locator('.ltzCompare').nth(1).textContent(),/\+140\.0%/);
   assert.match(await p.locator('.ltzCompare').nth(2).textContent(),/ranks 2 \/ 3/);
   assert.equal(await p.locator('.ltzHistoryDot').count(),3);
   assert.equal(await p.locator('.ltzLevelUnlock').count(),1);
   assert(await p.locator('.ltzUnlock img').evaluateAll(imgs=>imgs.every(i=>i.complete&&i.naturalWidth>0)));
   assert(await p.locator('.ltzLevelResult').evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  }
  assert.deepEqual(await green.locator('.ltzKillSplit strong').allTextContents(),['450','300','150']);
  assert.deepEqual(await purple.locator('.ltzKillSplit strong').allTextContents(),['300','450','150']);
  await screen.waitForFunction(()=>latestState?.phase==='won'&&latestState?.result_save?.status==='saved');
  assert.equal(await screen.locator('#levelResults,.ltzLevelResult,.ltzScreenResults').count(),0);
  assert(await screen.locator('#gameCanvas').isVisible());
  assert(await screen.locator('#matchScoreHud').isVisible());
  assert(await screen.locator('#purpleScoreHud').isVisible());
  assert.deepEqual(await screen.locator('.ltzFieldScore strong').allTextContents(),['900','900']);
  await green.screenshot({path:output+'/green-counts.png'});
  assert(await green.locator('.ltzUnlock[data-waiting]').count()>0);
  await green.locator('.ltzHistoryPlot').scrollIntoViewIfNeeded();await wait(1900);
  assert.equal(await green.locator('.ltzHistoryPlot[data-waiting]').count(),0);
  assert(await green.locator('.ltzHistoryDot,.ltzHistoryLine').evaluateAll(nodes=>nodes.every(n=>getComputedStyle(n).opacity==='1')));
  await green.screenshot({path:output+'/green-journey.png'});
  await green.locator('.ltzUnlockSection').scrollIntoViewIfNeeded();await wait(1700);assert.equal(await green.locator('.ltzUnlock[data-waiting]').count(),0);await green.screenshot({path:output+'/green-unlocks.png'});
  await purple.screenshot({path:output+'/purple-portrait.png'});
  await screen.screenshot({path:output+'/projector.png'});
  // DOM replacement keeps the completed count-up instead of restarting at zero.
  await green.evaluate(()=>{const parent=document.querySelector('.ltzReceipt').parentElement;const receipt=parent.querySelector('.ltzReceipt');const copy=receipt.cloneNode(true);copy.removeAttribute('data-mounted');receipt.replaceWith(copy);LTZShop.mount(parent);});
  assert.equal(await count(),900);
  await purple.emulateMedia({reducedMotion:'reduce'});await purple.reload();
  await purple.locator('.ltzLevelResult').waitFor();
  assert.equal(await purple.locator('.ltzKillHero>strong').textContent(),'900');
  await purple.waitForFunction(()=>{const e=document.querySelector('.ltzUnlock');return e&&getComputedStyle(e).animationName==='none';});
  const results=await api('/s/gamemaster/p/photon-progress/api/event-results?event_id='+seed.event_id);
  assert.equal(results.results.total,5);assert.equal(results.results.rows.at(-1).total_kills,900);
  // Only both player buttons may advance the saved result into the next countdown.
  await green.locator('#journeyDoneShopping').click();
  assert.equal((await api('/s/gamemaster/p/laser-tag-y/api/state')).phase,'won');
  await purple.locator('#journeyDoneShopping').click();
  for(const p of [green,purple])await p.locator('#missionCountdown:not([hidden])').waitFor();
  const continued=await api('/s/gamemaster/p/laser-tag-y/api/state');
  assert.equal(continued.phase,'running');assert.equal(continued.contract_control_tier,2);
  assert.equal(continued.start_countdown.duration_s,5);
  await green.screenshot({path:output+'/green-auto-continue.png'});
  await purple.screenshot({path:output+'/purple-auto-continue.png'});
  // Actual GM Reset returns both connected phones to a fresh name prompt.
  const gm=await browser.newPage({viewport:{width:1440,height:1000}});
  gm.setDefaultTimeout(15000);gm.on('pageerror',e=>errors.push(e.message));
  await gm.goto(base+'/s/gamemaster/p/laser-tag-y/game');
  await gm.waitForFunction(()=>ui.state?.phase==='running');
  await gm.locator('#reset').click();
  await gm.waitForFunction(()=>ui.state?.phase==='setup'&&ui.state?.journey?.phase==='lobby');
  for(const [p,side] of [[green,'green'],[purple,'purple']]){
   await p.getByRole('heading',{name:'Choose your player',exact:true}).waitFor();
   await p.waitForFunction(()=>document.querySelector('#journeyPlayer')?.value===''&&document.querySelector('#journeyReady')?.disabled&&document.querySelector('#journeyNewName')?.disabled===false&&document.querySelector('#gameJourney')?.scrollTop===0&&!document.querySelector('#missionCountdown:not([hidden])'));
   assert.equal(await p.locator('#journeyPlayer').inputValue(),'');
   assert.equal(await p.locator('#journeyNewName').inputValue(),'');
   assert(await p.locator('#journeyNewName').isEnabled());
   assert(await p.locator('#journeyReady').isDisabled());
   assert.equal(await p.locator('.ltzLevelResult').count(),0);
   assert.equal(await p.locator('#missionCountdown:not([hidden])').count(),0);
   await p.screenshot({path:output+'/'+side+'-reset-name-selection.png'});
  }
  const reset=await api('/s/gamemaster/p/laser-tag-y/api/state');
  assert.equal(reset.next_loadouts.events.active_id,seed.event_id);
  assert.equal(reset.next_loadouts.saved_games.active_id,null);
  assert.deepEqual(reset.next_loadouts.teams,{});
  assert.deepEqual((await api('/s/gamemaster/p/photon-progress/api/event-results?event_id='+seed.event_id)).results,results.results);
  // Reset also clears drafts when neither phone has selected a player yet.
  for(const p of [green,purple])await p.locator('#journeyNewName').fill('Unsubmitted name');
  await gm.locator('#reset').click();
  for(const p of [green,purple])await p.waitForFunction(()=>document.querySelector('#journeyNewName')?.value==='');
  assert.deepEqual(errors,[]);console.log('PASS: player results, unobscured projector, automatic L2 continuation, GM Reset opens both name prompts in the same event, reduced motion and durable event results; no browser exceptions');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-2200));process.exitCode=1;});
