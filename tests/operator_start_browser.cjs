/* Real operator/player UIs against an isolated fake-hardware match. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.OPERATOR_FIXTURE_URL||'http://127.0.0.1:56056';
const output=process.env.OPERATOR_OUTPUT||'/tmp/operator-start-views';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(origin))throw Error('Isolated fixture required');
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],checks=[];
 try{
  const gm=await browser.newPage({viewport:{width:1440,height:1100}});gm.on('pageerror',e=>errors.push(e.message));
  await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
  await gm.waitForFunction(()=>!document.querySelector('#start').disabled);
  assert.match(await gm.locator('#playerReadiness').innerText(),/Green: Not ready · Purple: Not ready/);
  await gm.click('#start');await gm.waitForFunction(()=>ui.state.phase==='running');
  checks.push('Start accepts both players not ready');
  await gm.click('#testEndMatch');await gm.waitForFunction(()=>ui.state.journey.practice_shop);
  const players=[];
  for(const [side,width,height] of [['green',667,320],['purple',1024,768]]){
   const page=await browser.newPage({viewport:{width,height}});players.push(page);page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
   await page.goto(origin+`/s/${side}/p/mobile-ltz/`);
   await page.locator('#journeyDoneShopping').waitFor();
   if(side==='green'){
    await page.click('#journeyDoneShopping');await page.locator('#gameJourney').waitFor({state:'hidden'});
    await gm.waitForFunction(()=>document.querySelector('#playerReadiness').textContent.includes('Green: Ready · Purple: Not ready'));
   }else{await page.click('#journeyClose');await page.locator('#gameJourney').waitFor({state:'hidden'});}
   // Multiple real SSE snapshots must not reopen a dismissed panel.
   await page.waitForTimeout(1800);assert(await page.locator('#gameJourney').isHidden());
   await page.click('#levelsOpen');await page.click('#openPlayers');await page.locator('#gameJourney').waitFor({state:'visible'});
   await page.click('#journeyClose');await page.locator('#gameJourney').waitFor({state:'hidden'});
   await page.screenshot({path:`${output}/${side}-controls.png`});
   checks.push(side+': shop dismisses, stays closed and can reopen');
  }
  assert(await gm.locator('#testNextLevel').isEnabled());
  await gm.locator('.actions').first().screenshot({path:output+'/operator-actions.png'});
  await gm.click('#testNextLevel');await gm.waitForFunction(()=>ui.state.phase==='setup'&&ui.state.journey.phase==='lobby');
  assert.equal(await gm.evaluate(()=>Object.keys(ui.state.journey.ready).length),0);
  await gm.click('#start');await gm.waitForFunction(()=>ui.state.phase==='running');
  assert.equal(await gm.evaluate(()=>ui.state.contract_control_tier),2);
  for(const page of players)await page.locator('#gameJourney').waitFor({state:'hidden'});
  checks.push('Next level and Start advance with Purple not ready; shop clears on both players');
  await gm.click('#testEndMatch');await gm.waitForFunction(()=>ui.state.journey.phase==='upgrades');
  await gm.click('#reset');await gm.waitForFunction(()=>ui.state.phase==='setup');
  assert(await gm.locator('#start').isEnabled());
  await gm.click('#start');await gm.waitForFunction(()=>ui.state.phase==='running');
  assert.equal(await gm.evaluate(()=>ui.state.contract_control_tier),2);
  for(const page of players)await page.locator('#gameJourney').waitFor({state:'hidden'});
  checks.push('Start closes shopping at the current tier without Ready taps');
  assert.deepEqual(errors,[]);fs.writeFileSync(output+'/results.json',JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
