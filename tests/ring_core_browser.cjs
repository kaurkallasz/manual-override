/* Ring-only completion on the real GM/phone pages; fake camera/arms, temporary saves. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8140',output='output/ring-core-2026-10-18';
const server=spawn('.venv/bin/python',['tests/mobile_ltz_fixture.py','--port','8140','--isolate-imports'],{stdio:['ignore','pipe','pipe']});
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
  const phones={};
  gm.on('pageerror',e=>errors.push(e.message));
  await gm.goto(base+'/s/gamemaster/p/laser-tag-y/',{waitUntil:'domcontentloaded'});
  await gm.waitForFunction(()=>ui.state?.phase==='setup');
  await gm.evaluate(()=>command({action:'configure',settings:{first_wave_delay_s:300}}));
  for(const side of ['green','purple']){
   const p=phones[side]=await browser.newPage({viewport:{width:844,height:390}});
   p.on('pageerror',e=>errors.push(e.message));
   await p.goto(base+'/s/'+side+'/p/mobile-ltz/',{waitUntil:'domcontentloaded'});
   await p.locator('#journeyReady').click();
  }
  await gm.waitForFunction(()=>document.querySelector('#readinessSummary')?.textContent==='Both players ready · press Start');
  await gm.locator('#greenStartingAtom').selectOption('100');await gm.locator('#purpleStartingAtom').selectOption('102');
  await gm.locator('#start').click();await gm.waitForFunction(()=>ui.state?.phase==='running');
  for(const p of Object.values(phones))await p.locator('#coreObjective').filter({hasText:'Complete the ring'}).waitFor();
  await gm.evaluate(async()=>{
   for(const [i,marker] of [41,43,42,45,54,46,52,53].entries()){
    const socket=ui.state.level.sockets.find(s=>s.aruco_id===marker);
    await command({action:'operator_atom',socket_id:socket.socket_id||socket.id,atom_tag_id:i%2?102:100});
   }
  });
  await gm.waitForFunction(()=>ui.state.core_sequence.stage==='ring_ready');
  assert.equal(await gm.evaluate(()=>ui.state.kills),0);
  assert.equal(await gm.evaluate(()=>ui.state.turret_controls.core.blocked_reason),'');
  assert.match(await gm.locator('#mission').textContent(),/Ring complete: place/);
  for(const p of Object.values(phones))await p.locator('#coreObjective').filter({hasText:'Ring complete'}).waitFor();
  await phones.green.screenshot({path:output+'/ring-complete.png'});
  await gm.evaluate(()=>command({action:'operator_core',atom_tag_id:102}));
  for(const p of Object.values(phones))await p.locator('#coreObjective').filter({hasText:'Stack the Green Atom'}).waitFor();
  await gm.evaluate(()=>command({action:'operator_core',atom_tag_id:100}));
  await gm.waitForFunction(()=>ui.state.phase==='won'&&ui.state.journey.phase==='results');
  for(const [side,p] of Object.entries(phones)){
   await p.locator('.ltzLevelResult').waitFor();
   assert.equal(await p.locator('.ltzKillHero>strong').textContent(),'0');
   const state=await api('/s/gamemaster/p/photon-progress/api/state?side='+side);
   assert.equal(state.player.current_control_tier,2);assert.equal(state.player.levels.forcefield,2);
   assert.equal(state.player.wins,1);assert.equal(state.latest_result.statistics.total_kills,0);
   assert.equal(state.latest_result.victory_method,'center_stack');assert(state.latest_result.stack_bonus>0);
   await p.screenshot({path:output+'/'+side+'-zero-kill-results.png'});
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: both Ready, ring-only center unlock, zero-kill GM core stack, both phone objectives, saved L2/force-field unlock and zero-kill statistics; no browser exceptions');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-2500));process.exitCode=1;});
