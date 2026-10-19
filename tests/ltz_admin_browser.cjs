const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.LTZ_ADMIN_ORIGIN||'http://127.0.0.1:8133',output='/tmp/ltz-admin-views';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],checks=[];
 try{
  const gm=await browser.newPage({viewport:{width:1440,height:1000}});gm.on('pageerror',e=>errors.push(e.message));
  await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
  await gm.locator('#creditGrantPlayer option').first().waitFor({state:'attached'});
  for(const side of ['green','purple']){
   await gm.selectOption('#creditGrantPlayer','ltz-test-'+side);await gm.fill('#creditGrantAmount','2000');
   await gm.click('#creditGrantSubmit');await gm.waitForFunction(()=>document.querySelector('#creditGrantStatus').textContent.includes('Wallet: 2,000'));
  }
  await gm.click('#start');await gm.waitForFunction(()=>document.querySelector('#phaseBadge').textContent==='running');
  await gm.click('#pause');await gm.waitForFunction(()=>document.querySelector('#phaseBadge').textContent==='Paused');
  await gm.click('#testEndMatch');await gm.waitForFunction(()=>document.querySelector('#testFlowStatus').textContent.includes('Test shop is open'));
  await gm.locator('#playerAdmin').screenshot({path:output+'/gamemaster.png'});
  for(const [name,side,width,height] of [['phone','green',667,320],['tablet','purple',1024,768]]){
   const page=await browser.newPage({viewport:{width,height}});page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
   await page.goto(origin+`/s/${side}/p/mobile-ltz/`);
   await page.locator('.ltzCard').first().waitFor();
   assert.match(await page.locator('.ltzWallet').innerText(),/2,000/);
   assert.match(await page.locator('#journeyContent').innerText(),/Practice shop/);
   assert.equal(await page.locator('.ltzCard').count(),15);
   await page.locator('[data-upgrade="damage-machine-gun"][data-level="2"]').click();
   await page.waitForFunction(()=>document.querySelector('.ltzWallet')?.innerText.includes('1,750'));
   assert.match(await page.locator('.ltzGrantNote').innerText(),/excluded from your scorecard/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:output+'/'+name+'.png'});checks.push({name,credits:1750,cards:15,overflow:false});await page.close();
  }
  await gm.click('#testNextLevel');await gm.waitForFunction(()=>document.querySelector('#testFlowStatus').textContent.includes('Level 2 prepared'));
  await gm.click('#start');await gm.waitForFunction(()=>document.querySelector('#phaseBadge').textContent==='running');
  const state=await (await gm.request.get(origin+'/s/gamemaster/p/photon-game/api/state')).json();
  assert.equal(state.contract_control_tier,2);assert.equal(state.player_progression.green.levels['damage-machine-gun'],2);
  assert.equal(state.player_progression.purple.levels['damage-machine-gun'],2);
  for(const side of ['green','purple']){
   const p=(await (await gm.request.get(origin+'/s/gamemaster/p/photon-progress/api/state?side='+side)).json()).player;
   assert.equal(p.lifetime_score,0);assert.equal(p.lifetime_credits_earned,0);assert.equal(p.wins,0);assert.equal(p.lifetime_granted_credits,2000);
  }
  const history=await (await gm.request.get(origin+'/s/gamemaster/p/photon-progress/api/history?side=green&combined=1')).json();assert.equal(history.history.total,0);
  assert.deepEqual(errors,[]);fs.writeFileSync(output+'/results.json',JSON.stringify({checks,nextTier:2,scoredRuns:0,errors},null,2));console.log(JSON.stringify({checks,nextTier:2,scoredRuns:0,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
