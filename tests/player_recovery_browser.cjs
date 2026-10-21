/* Real player refresh and two-player retry, with temporary saves and fake arms. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8146',output='output/player-recovery-2026-10-19';
const server=spawn('.venv/bin/python',['tests/player_recovery_fixture.py'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function state(){const r=await fetch(base+'/s/gamemaster/p/photon-game/api/state');assert(r.ok);return r.json();}
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('Recovery fixture ready');i++)await wait(100);
  assert(logs.includes('Recovery fixture ready'),logs);
  const before=await state(),run=before.journey.run_id;
  assert.equal(before.phase,'setup');assert.equal(before.journey.phase,'results');
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],phones=[];
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:390,height:844}});phones.push(page);
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/s/'+side+'/p/mobile-ltz/');
   await page.locator('.ltzReceipt h2').filter({hasText:'Game interrupted'}).waitFor();
   await page.reload();
   await page.getByRole('button',{name:'Retry level · Ready',exact:true}).waitFor();
   assert.match(await page.locator('.ltzReceipt').textContent(),/13 credits remaining/);
   assert.equal(await page.locator('.ltzSaving').count(),0);
  }
  fs.mkdirSync(output,{recursive:true});await phones[0].screenshot({path:output+'/interrupted-after-refresh.png'});
  await phones[0].getByRole('button',{name:'Retry level · Ready',exact:true}).click();
  await phones[0].locator('[data-result-choice="continue"][aria-pressed="true"]').waitFor();
  assert.equal((await state()).phase,'setup');
  await phones[0].reload();await phones[0].locator('[data-result-choice="continue"][aria-pressed="true"]').waitFor();
  await phones[1].getByRole('button',{name:'Retry level · Ready',exact:true}).click();
  for(const page of phones)await page.waitForFunction(()=>document.querySelector('#gameJourney').hidden);
  const after=await state();assert.equal(after.phase,'running');assert.notEqual(after.run_id,run);
  assert.equal(after.contract_control_tier,1);
  assert.equal(after.next_loadouts.saved_games.active_id,before.next_loadouts.saved_games.active_id);
  for(const side of ['green','purple']){
   const response=await fetch(base+'/s/gamemaster/p/photon-progress/api/state?side='+side),p=(await response.json()).player;
   assert.equal(p.credits,13);assert.equal(p.wins,0);
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: interrupted result survives both phone refreshes; one Ready waits; both retry the same level and pair with saved credits and no extra win; no browser errors');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-2500));process.exitCode=1;});
