/* Actual GM controls and authoritative saved presets; fake-hardware fixture only. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.INTENSITY_FIXTURE_URL||'http://127.0.0.1:56054';
const output=process.env.INTENSITY_OUTPUT||'/tmp/practice-intensity-views';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(origin))throw Error('Isolated fixture required');
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const checks=[];
 try{
  await page.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
  await page.locator('#testOverride').waitFor();
  await page.check('#testOverride');
  for(const tier of [2,3,4]){
   await page.selectOption('#testMobileControl',String(tier));
   await page.click('#applyTestUnlocks');
   await page.waitForFunction(t=>ui.state.spawn_intensity?.tier===t,tier);
   const state=await (await page.request.get(origin+'/s/gamemaster/p/photon-game/api/state')).json();
   const saved=state.next_match.tiers.find(p=>p.tier===tier);
   assert.equal(state.spawn_intensity.total,saved.total);
   assert.equal(state.spawn_intensity.wave_interval_s,saved.wave_interval_s);
   assert.equal(state.spawn_intensity.release_rate_multiplier,saved.release_rate_multiplier);
   checks.push({stage:'setup',tier,total:saved.total});
  }
  await page.click('#start');await page.waitForFunction(()=>ui.state.phase==='running');
  const original=await (await page.request.get(origin+'/s/gamemaster/p/photon-game/api/state')).json();
  for(const tier of [2,3,4]){
   await page.selectOption('#testMobileControl',String(tier));await page.click('#applyTestUnlocks');
   await page.waitForFunction(t=>ui.state.spawn_intensity?.tier===t&&ui.state.contract_control_tier===t,tier);
   const state=await (await page.request.get(origin+'/s/gamemaster/p/photon-game/api/state')).json();
   assert.equal(state.run_id,original.run_id);assert.equal(state.phase,'running');
   assert.equal(state.spawn_intensity.total,state.next_match.tiers.find(p=>p.tier===tier).total);
   assert.equal(state.progress.reward_enabled,false);
   assert.match(await page.locator('#testSpawnIntensity').innerText(),new RegExp(`Active intensity: L${tier}`));
   checks.push({stage:'running',tier,total:state.spawn_intensity.total});
  }
  await page.locator('#testUnlocks').screenshot({path:output+'/cue-l4.png'});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(output+'/results.json',JSON.stringify({checks,errors},null,2));
  console.log(JSON.stringify({checks,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
