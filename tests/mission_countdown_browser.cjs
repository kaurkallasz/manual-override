// Run mission_countdown_fixture.py first. Uses only temporary profiles and virtual game.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin='http://127.0.0.1:'+fs.readFileSync('/tmp/mission-countdown-port','utf8');
const output='output/get-ready-2026-10-13';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[];
 try{
  const green=await browser.newPage({viewport:{width:844,height:390}});
  const purple=await browser.newPage({viewport:{width:1024,height:768}});
  for(const page of [green,purple]){
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
  }
  const command=async action=>{const r=await green.request.post(origin+'/__test/command',{data:{action}});assert(r.ok(),await r.text());};
  const tick=async ticks=>{const r=await green.request.post(origin+'/__test/tick',{data:{ticks}});assert(r.ok(),await r.text());};
  const label=async (page,value)=>page.waitForFunction(value=>!document.querySelector('#missionCountdown').hidden&&document.querySelector('#missionCountdown span').textContent===value,value);
  await green.goto(origin+'/s/green/p/mobile-ltz/');
  await green.locator('#journeyNewName').fill('Mission Pilot');
  await green.locator('#journeyCreate').click();
  await green.locator('.missionBriefing').waitFor();
  assert.equal(await green.locator('.missionObjectives li').count(),3);
  assert.match(await green.locator('.missionBriefing').innerText(),/Mission Pilot.*Mission briefing/is);
  assert.match(await green.locator('.missionReminder').innerText(),/Don't forget to aim your turrets!/);
  assert.equal(await green.locator('.missionBriefing').evaluate(e=>getComputedStyle(e).backgroundColor),'rgba(16, 32, 24, 0.2)');
  assert.equal(await green.locator('#missionCountdown').isVisible(),false,'no waiting text over instructions');
  for(const [name,width,height] of [['phone-landscape',844,390],['phone-portrait',390,844],['tablet',1024,768]]){
   await green.setViewportSize({width,height});
   const bounds=await green.locator('.missionBriefing').evaluate(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,overflow:document.documentElement.scrollWidth>innerWidth};});
   assert(bounds.left>=0&&bounds.right<=width&&bounds.top>=0&&bounds.bottom<=height&&!bounds.overflow,name+' fits');
   await green.screenshot({path:`${output}/${name}.png`});
  }
  await green.locator('#journeyReady').click();await label(green,'Get ready');
  assert.equal(await green.locator('#gameJourney').isVisible(),false,'Ready closes the instructions');
  const waitingAnimation=await green.locator('#missionCountdown span').evaluate(e=>{
   const animation=e.getAnimations()[0],read=()=>({opacity:Number(getComputedStyle(e).opacity),scale:new DOMMatrix(getComputedStyle(e).transform).a});
   animation.pause();animation.currentTime=100;const first=read();animation.currentTime=1500;const later=read();
   const iterations=animation.effect.getTiming().iterations;animation.play();return {first,later,repeats:iterations===Infinity};
  });
  assert(waitingAnimation.repeats&&waitingAnimation.later.scale>waitingAnimation.first.scale&&waitingAnimation.later.opacity<waitingAnimation.first.opacity,'Get ready repeats the countdown grow/fade');
  for(const [name,width,height] of [['phone-landscape',844,390],['phone-portrait',390,844],['tablet',1024,768]]){
   await green.setViewportSize({width,height});
   const bounds=await green.locator('#missionCountdown span').evaluate(e=>{const a=e.getAnimations()[0];a.pause();a.currentTime=700;const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};});
   assert(bounds.left>=0&&bounds.right<=width&&bounds.top>=0&&bounds.bottom<=height,name+' Get ready fits');
   await green.screenshot({path:`${output}/get-ready-${name}.png`});
   await green.locator('#missionCountdown span').evaluate(e=>e.getAnimations()[0].play());
  }
  await green.setViewportSize({width:844,height:390});
  await green.reload();await label(green,'Get ready');
  await green.locator('#levelsOpen').click();await green.locator('#openPlayers').click();
  await green.locator('.missionBriefing').waitFor();assert.equal(await green.locator('#missionCountdown').isVisible(),false);
  await green.locator('#journeyReady').click();await label(green,'Get ready');
  await green.emulateMedia({reducedMotion:'reduce'});await green.waitForFunction(()=>!document.querySelector('#missionCountdown span').getAnimations().length);
  assert.equal(await green.locator('#missionCountdown span').innerText(),'Get ready');
  await green.emulateMedia({reducedMotion:'no-preference'});
  await purple.goto(origin+'/s/purple/p/mobile-ltz/');await purple.locator('.missionBriefing').waitFor();
  await purple.locator('#journeyReady').click();await label(purple,'Get ready');
  await command('start');
  for(const page of [green,purple]){await label(page,'5');assert.equal(await page.locator('.missionBriefing').count(),0);}
  const {first,later}=await green.locator('#missionCountdown span').evaluate(e=>{
   const animation=e.getAnimations()[0],read=()=>({opacity:Number(getComputedStyle(e).opacity),scale:new DOMMatrix(getComputedStyle(e).transform).a});
   animation.pause();animation.currentTime=100;const first=read();animation.currentTime=700;const later=read();animation.currentTime=0;animation.play();return {first,later};
  });
  assert(later.scale>first.scale&&later.opacity<first.opacity,'numerals grow and fade');
  await tick(6);await command('pause');
  await green.waitForFunction(()=>state.paused&&state.start_countdown.remaining_s===4.7);
  await green.screenshot({path:`${output}/countdown.png`});
  await command('resume');await tick(14);for(const page of [green,purple])await label(page,'4');
  await tick(20);for(const page of [green,purple])await label(page,'3');
  await command('pause');await tick(40);
  await purple.reload();await label(purple,'3');
  await purple.waitForFunction(()=>document.querySelector('#missionCountdown span').getAnimations()[0]?.playState==='paused');
  await command('resume');
  for(const value of ['2','1','GO!']){await tick(20);for(const page of [green,purple])await label(page,value);}
  await tick(20);for(const page of [green,purple])await page.waitForFunction(()=>document.querySelector('#missionCountdown').hidden);
  await purple.reload();await purple.waitForTimeout(500);assert.equal(await purple.locator('#missionCountdown').isVisible(),false);
  // A second start replaces the sequence; Reset clears it immediately.
  await command('reset');await command('start');await label(green,'5');
  await command('reset');await green.waitForFunction(()=>document.querySelector('#missionCountdown').hidden);
  // Reduced-motion users receive the same authoritative number without zoom.
  await green.emulateMedia({reducedMotion:'reduce'});
  await command('start');await label(green,'5');
  assert.equal(await green.locator('#missionCountdown span').evaluate(e=>e.getAnimations().length),0);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(output+'/browser-results.json',JSON.stringify({mission:true,opacity:.2,getReady:true,waitingAnimation,sequence:['5','4','3','2','1','GO!'],twoPlayers:true,reload:true,reopen:true,pause:true,reset:true,reducedMotion:true,animation:{first,later},errors},null,2));
  console.log('Mission/countdown browser checks passed: instructions, Get ready, responsive layout, both players, grow/fade, reopen/reload, countdown, pause, GO, reset and reduced motion.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
