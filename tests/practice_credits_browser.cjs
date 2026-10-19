const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.PRACTICE_CREDITS_ORIGIN||'http://127.0.0.1:'+fs.readFileSync('/tmp/practice-credits-port','utf8');
const output='output/practice-credits-2026-10-13';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],checks=[];
 try{
  for(const [name,side,width,height] of [['phone','green',844,390],['tablet','purple',1024,768]]){
   const page=await browser.newPage({viewport:{width,height}});page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
   await page.goto(origin+`/s/${side}/p/mobile-ltz/`);
   await page.locator('.ltzCard').first().waitFor();
   assert.match(await page.locator('.ltzWallet').innerText(),/885 credits available/);
   assert.match(await page.locator('.ltzReceipt').innerText(),/Practice · 885 credits banked/i);
   assert.match(await page.locator('.ltzReceipt').innerText(),/670/);
   assert.equal(await page.locator('.ltzCard').count(),15);
   const buy=page.locator('[data-upgrade="damage-machine-gun"][data-level="2"]');
   assert(await buy.isEnabled());await buy.click();
   await page.waitForFunction(()=>document.querySelector('.ltzWallet')?.innerText.includes('635 credits available'));
   await page.reload();await page.locator('.ltzCard').first().waitFor();
   assert.match(await page.locator('.ltzWallet').innerText(),/635 credits available/);
   assert.equal(await buy.innerText(),'Owned');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:output+'/'+name+'.png'});checks.push({name,banked:885,balance:635,purchased:'Machine Gun L2',reload:true});
   await page.close();
  }
  const score=await browser.newPage({viewport:{width:1280,height:900}});score.on('pageerror',e=>errors.push(e.message));
  await score.goto(origin+'/s/green/p/ltz-score/');await score.locator('.ltzCard').first().waitFor();
  assert.match(await score.locator('.ltzReceipt').innerText(),/885 credits banked/i);
  assert.match(await score.locator('.ltzWallet').innerText(),/635 credits available/);
  await score.screenshot({path:output+'/score.png'});
  const state=await(await score.request.get(origin+'/s/gamemaster/p/photon-game/api/state')).json();
  const next=await score.request.post(origin+'/s/gamemaster/p/photon-game/api/command',{data:{action:'next_level',run_id:state.run_id}});assert(next.ok());
  const started=await score.request.post(origin+'/s/gamemaster/p/photon-game/api/command',{data:{action:'start',virtual_play:true,reward_enabled:false}});assert(started.ok());
  const game=await(await score.request.get(origin+'/s/gamemaster/p/photon-game/api/state')).json();
  for(const side of ['green','purple']){
   assert.equal(game.player_progression[side].levels['damage-machine-gun'],2);
   const p=await(await score.request.get(origin+'/s/gamemaster/p/photon-progress/api/state?side='+side)).json();
   assert.equal(p.player.credits,635);assert.equal(p.player.lifetime_practice_credits,885);assert.equal(p.player.wins,0);assert.equal(p.player.attempts,0);assert.equal(p.player.lifetime_credits_earned,0);
  }
  assert.deepEqual(errors,[]);
  const result={checks,nextMatchUsesUpgrades:true,scoredWins:0,errors};
  fs.writeFileSync(output+'/browser-results.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
