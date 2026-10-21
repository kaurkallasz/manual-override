/* Real two-phone disagreement, refreshed choices, old errors and delayed replies. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8146',output='output/player-agreement-2026-10-19';
const server=spawn('.venv/bin/python',['tests/player_recovery_fixture.py'],{stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function state(){const r=await fetch(base+'/s/gamemaster/p/photon-game/api/state');assert(r.ok);return r.json();}
async function choices(page,green,purple){
 await page.waitForFunction(({green,purple})=>document.querySelector('[data-player-choice="green"]')?.textContent.includes(green)&&document.querySelector('[data-player-choice="purple"]')?.textContent.includes(purple),{green,purple});
 assert.match(await page.locator('.ltzChoiceStatus').textContent(),/choices differ/i);
}
(async()=>{
 let browser,releaseReply=()=>{},replyDone;
 try{
  for(let i=0;i<100&&!logs.includes('Recovery fixture ready');i++)await wait(100);
  assert(logs.includes('Recovery fixture ready'),logs);
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[],green=await browser.newPage({viewport:{width:390,height:844}}),purple=await browser.newPage({viewport:{width:844,height:390}}),score=await browser.newPage({viewport:{width:1280,height:900}});
  for(const page of [green,purple,score]){page.setDefaultTimeout(12000);page.on('pageerror',e=>errors.push(e.message));}
  await Promise.all([green.goto(base+'/s/green/p/mobile-ltz/'),purple.goto(base+'/s/purple/p/mobile-ltz/'),score.goto(base+'/s/green/p/ltz-score/')]);
  const before=await state(),run=before.journey.run_id;
  let failOnce=true,holdNext=false,requests=0;
  await green.route(/\/api\/journey(?:\?|$)/,async route=>{
   requests++;
   if(failOnce){failOnce=false;return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({ok:false,error:'Wait for this pair’s level result to finish saving'})});}
   if(holdNext){holdNext=false;const response=await route.fetch();await new Promise(resolve=>releaseReply=resolve);await route.fulfill({response});replyDone();return;}
   return route.continue();
  });
  await green.locator('[data-result-choice="continue"]').click();
  await green.waitForFunction(()=>document.querySelector('#journeyMessage').textContent.includes('finish saving'));
  await green.locator('[data-result-choice="continue"]').click();
  await green.locator('[data-result-choice="continue"][aria-pressed="true"]').waitFor();
  assert.equal(await green.locator('#journeyMessage').textContent(),'','A successful choice must clear the old save error');
  await purple.locator('[data-result-choice="replay_game"]').click();
  for(const page of [green,purple,score])await choices(page,'Retry level','Replay whole game');
  assert.equal((await state()).phase,'setup');
  await green.reload();await choices(green,'Retry level','Replay whole game');
  fs.mkdirSync(output,{recursive:true});await green.screenshot({path:output+'/different-choices.png'});
  // Keep an old button and a successful old HTTP reply until the next run starts.
  const delivered=new Promise(resolve=>replyDone=resolve);
  holdNext=true;await green.locator('[data-result-choice="replay_level"]').click();
  for(const page of [green,purple,score])await choices(page,'Replay last level','Replay whole game');
  await purple.evaluate(()=>window.oldResultButton=document.querySelector('[data-result-choice="new"]'));
  await purple.locator('[data-result-choice="replay_level"]').click();
  for(const page of [green,purple])await page.waitForFunction(()=>document.querySelector('#gameJourney').hidden);
  releaseReply();await delivered;
  await green.waitForFunction(()=>document.querySelector('#gameJourney').hidden&&document.querySelector('#journeyMessage').textContent==='');
  let latePosts=0;purple.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/api/journey'))latePosts++;});
  await purple.evaluate(()=>window.oldResultButton.onclick());
  assert.equal(latePosts,0,'An old result button must not submit a choice for the active match');
  assert.equal(await purple.locator('#journeyMessage').textContent(),'');
  const after=await state();assert.equal(after.phase,'running');assert.notEqual(after.run_id,run);assert.equal(after.contract_control_tier,1);
  assert.equal(after.journey.continued_from,run);
  assert.notEqual(after.next_loadouts.saved_games.active_id,before.next_loadouts.saved_games.active_id);
  assert.equal(requests,3);
  assert.deepEqual(errors,[]);
  console.log('PASS: old save error clears; all screens show both choices; disagreement waits through refresh; matching replay starts once; delayed replies and old buttons cannot revive the end screen or target the new game');
 }finally{releaseReply();await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-2000));process.exitCode=1;});
