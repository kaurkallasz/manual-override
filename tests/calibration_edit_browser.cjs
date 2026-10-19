/* Real mobile/display routes, temporary calibration data and fake arms only. */
const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8147';
const server=spawn('.venv/bin/python',['tests/mobile_ltz_fixture.py','--port','8147'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(path,data){
 const r=await fetch(base+path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});
 const result=await r.json();assert(r.ok,JSON.stringify(result));return result;
}
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('Mobile fixture http:');i++)await wait(100);
  assert(logs.includes('Mobile fixture http:'),logs);
  await api('/__test/camera',{enabled:true});
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],screen=await browser.newPage({viewport:{width:1280,height:720}});
  screen.on('pageerror',e=>errors.push(e.message));
  // Expose only rendered sprite state for assertions; run the actual renderer.
  await screen.route('**/playfield-areas/screen?presentation=1',async route=>{
   const response=await route.fetch(),html=await response.text();
   await route.fulfill({response,body:html.replace('function applyState(data) {',
    'window.calibrationNumbers=()=>[...meshes.values()].filter(m=>m.userData.number.visible).map(m=>({marker:m.userData.markerId,rotation:m.userData.number.material.rotation}));\nfunction applyState(data) {')});
  });
  for(const side of ['green','purple']){
   await api(`/s/${side}/p/cartesian-xyz-test/api/enable`,{});
   await api('/s/gamemaster/p/photon-game/api/command',{action:'calibration_setup',side});
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
   page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+`/s/${side}/p/mobile-ltz/`);
   await page.waitForFunction(()=>state?.mobile_calibration_preparation?.ready);
   await page.waitForFunction(()=>state?.mobile_calibration_ready);
   if(side==='green')await screen.goto(base+'/s/gamemaster/p/playfield-areas/screen?presentation=1');
   await screen.waitForFunction(rotation=>window.calibrationNumbers?.().length===6&&calibrationNumbers().every(n=>n.rotation===rotation),side==='purple'?Math.PI:0);
   await screen.waitForFunction(()=>document.querySelector('#markerStatus').hidden);
   await screen.screenshot({path:`/tmp/calibration-edit-${side}-projector.png`});
   const field=()=>api('/s/gamemaster/p/playfield-areas/api/state');
   assert.equal((await field()).calibration_side,side);
   const saved=marker=>page.waitForFunction(m=>!!state.mobile_calibration.captures[m],String(marker));
   const capture=async marker=>{await page.locator(`[data-capture="${marker}"]`).click();await saved(marker);};
   await capture(30);
   await page.locator('[data-capture="30"]').click();
   await page.waitForFunction(()=>!state.mobile_calibration.captures['30']);
   assert.equal(await page.locator('[data-capture="30"]').getAttribute('aria-pressed'),'false');
   assert.equal((await field()).areas.find(a=>a.marker===30).show_area,false);
   for(const marker of [30,31,32,33,34,35])await capture(marker);
   await page.waitForSelector('[data-parallax="31"]');
   // The last arm capture remains editable after automatic stage advancement.
   await page.locator('.calibrationSavedPoints summary').click();
   await page.locator('[data-capture="35"]').click();
   await page.waitForFunction(()=>state.mobile_calibration.stage==='points');
   assert.equal(await page.evaluate(()=>state.mobile_calibration.pickup_height),null);
   assert(await page.locator('#calibrationComplete').isDisabled());
   await capture(35);
   await page.waitForSelector('[data-parallax="31"]');
   assert.equal(await page.evaluate(()=>Object.keys(state.mobile_calibration.captures).length),6);
   // Collapse instructions to leave the centre of the camera open for taps.
   await page.locator('#journeyToggle').click();
   const placeCrosshair=async()=>{
    const pos=await page.evaluate(()=>{const r=battlefield.getBoundingClientRect();return {x:r.left+r.width*.36,y:r.top+r.height*.82};});
    await page.touchscreen.tap(pos.x,pos.y);
    await page.waitForFunction(()=>document.querySelector('#calibrationCrosshair').dataset.mapped==='true');
   };
   await placeCrosshair();
   await page.locator('[data-parallax="31"]').click();
   await page.waitForFunction(()=>!!state.mobile_calibration.draft.parallax_points['31']);
   await page.waitForFunction(()=>MobileJourney.perspectiveTarget()?.mapped===false);
   assert(await page.locator('[data-parallax="31"]').isEnabled(),'Saved sample can be undone without a new crosshair');
   await page.locator('[data-parallax="31"]').click();
   await page.waitForFunction(()=>!state.mobile_calibration.draft.parallax_points['31']);
   assert.equal((await field()).areas.find(a=>a.marker===31).show_area,true);
   assert.equal(await page.evaluate(()=>Object.keys(state.mobile_calibration.captures).length),6);
   assert(await page.locator('[data-parallax="31"]').isDisabled(),'New samples still need a crosshair');
   await placeCrosshair();
   await page.locator('[data-parallax="31"]').click();
   await page.waitForFunction(()=>!!state.mobile_calibration.draft.parallax_points['31']);
   await page.screenshot({path:`/tmp/calibration-edit-${side}-phone.png`});
   await page.reload();
   await page.waitForSelector('[data-parallax="31"].calibrated');
   assert.equal(await page.locator('.ltzReceipt').count(),0,'Calibration stays free of the previous score window');
   await page.close();
   console.log(`PASS ${side}: save/undo/recapture for arm and raised samples, persistent state, projector orientation`);
  }
  const commands=await api('/__test/robot-commands');
  assert.equal(commands.filter(r=>['move','joint-move'].includes(r.action)).length,0,'Calibration edits never move the robot');
  assert.deepEqual(errors,[]);
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);console.error(logs.slice(-2500));process.exitCode=1;});
