/* Real GM Reset and player Load during Purple calibration; no physical devices. */
const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8148',server=spawn('.venv/bin/python',['tests/reset_calibration_fixture.py'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data){const r=await fetch(base+path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const d=await r.json();assert(r.ok,JSON.stringify(d));return d;}
(async()=>{
 let browser;
 try{
  for(let i=0;i<200&&!logs.includes('Reset calibration fixture http:')&&server.exitCode===null;i++)await wait(100);
  assert(logs.includes('Reset calibration fixture http:'),logs);
  const seed=await api('/__test/reset-calibration-seed');
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],gm=await browser.newPage(),purple=await browser.newPage({viewport:{width:844,height:390}}),green=await browser.newPage();
  for(const p of [gm,purple,green]){p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message));}
  // Opening Game Master selects the game display; resume its paused lesson first.
  await gm.goto(base+'/s/gamemaster/p/laser-tag-y/');
  await gm.waitForFunction(()=>ui.state?.journey?.deferred_calibration);
  await gm.locator('#resumeCalibration').click();
  await gm.waitForFunction(()=>ui.state?.journey?.calibration_side==='purple');
  await Promise.all([purple.goto(base+'/s/purple/p/mobile-ltz/'),green.goto(base+'/s/green/p/mobile-ltz/')]);
  await purple.waitForSelector('[data-capture="30"].calibrated');
  const before=await purple.evaluate(()=>structuredClone(state.mobile_calibration.draft));
  await green.locator('.journeyWaiting').waitFor();
  await api('/__test/camera',{stale:true});
  await api('/__test/calibration-feedback',{connected:false});
  await api('/__test/reset-stop',{blocked:true});
  await gm.locator('#reset').click();
  await gm.waitForFunction(()=>ui.state?.journey?.phase==='lobby'&&ui.state?.phase==='setup');
  for(const p of [green,purple])await p.getByRole('heading',{name:'Choose your player',exact:true}).waitFor();
  const blockedState=await api('/s/gamemaster/p/mobile-ltz-api/api/state?side=purple');
  assert.equal(blockedState.mobile_motion_policy.blocked,true);
  assert.equal((await api('/s/gamemaster/p/playfield-areas/api/state')).calibration_side,null);
  await gm.screenshot({path:'/tmp/reset-calibration-gamemaster.png'});
  await api('/__test/reset-stop',{blocked:false});
  await api('/__test/calibration-feedback',{connected:true});
  await api('/__test/camera',{stale:false});
  await api('/s/purple/p/cartesian-xyz-test/api/enable',{});
  await purple.locator('#journeyToggle').click();
  await purple.locator('#journeySavedGame').selectOption(seed.game_id);
  await purple.locator('[data-saved-game="load"]').click();
  await purple.waitForSelector('[data-capture="30"].calibrated');
  const resumed=await purple.evaluate(()=>({side:state.journey.calibration_side,turn:state.journey.turn,id:state.mobile_calibration.id,draft:state.mobile_calibration.draft,captures:Object.keys(state.mobile_calibration.captures)}));
  assert.equal(resumed.side,'purple');assert.equal(resumed.turn,1);assert.equal(resumed.id,seed.session_id);
  assert.deepEqual(resumed.captures,['30']);assert.deepEqual(resumed.draft,before);
  await green.locator('.journeyWaiting').waitFor();
  assert.match(await green.locator('.journeyWaiting').textContent(),/Waiting for Purple/);
  assert.equal((await api('/s/gamemaster/p/playfield-areas/api/state')).calibration_side,'purple');
  await purple.screenshot({path:'/tmp/reset-calibration-purple-resumed.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: GM Reset works with stale camera and disconnected arms; player Load restores Purple turn 1 and point 30, while Green waits.');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);console.error(logs.slice(-3000));process.exitCode=1;});
