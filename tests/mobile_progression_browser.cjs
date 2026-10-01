// Real shared phone UI + isolated simulation fixture. No hardware or venue data.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const base='http://127.0.0.1:8117';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],verified=[];
 try{
  for(const team of ['green','purple']){
   const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
   page.on('pageerror',e=>errors.push(team+': '+e.message));
   await page.request.post(base+'/__test/camera',{data:{enabled:false}});
   await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
   await page.goto(`${base}/s/${team}/p/mobile-ltz/`);
   await page.waitForFunction(()=>view?.levelReady);
   for(const [index,mode]of ['joint','xyz','targeting','cue'].entries()){
    const response=await page.request.post(base+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:index+1}});
    assert(response.ok());
    await page.waitForFunction(expected=>document.getElementById('app').dataset.controlMode===expected,mode);
    assert.equal(await page.locator('#mobileControl').inputValue(),mode);
    verified.push(team+': '+mode);
    if(mode==='targeting')await page.screenshot({path:`/tmp/ltz-${team}-targeting.png`});
   }
   // Freeze incoming test state while exercising presentation-only fixtures.
   await page.evaluate(()=>{gameState.apply=()=>{};liveFeed.stop();liveFeed.tick=()=>{};});
   await page.waitForTimeout(100);
   await page.evaluate(team=>{
    window.testCommands=[];
    const levels=Object.fromEntries(['damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'].map(k=>[k,1]));
    const p={id:team+'-profile',revision:1,name:team+' tester',current_control_tier:3,wins_by_tier:[3,3,0,0],levels,credits:1200,lifetime_score:1800,wins:6,attempts:8};
    const rows=Array.from({length:6},(_,i)=>({run_id:'run-'+i,finished_at:1780000000+i*1500,outcome:'won',score:100+i*10,active_seconds:1500-i*40,control_tier:3,cohort:i<3?'cohort-a':'cohort-b',
     participants:[{player_id:p.id,name:p.name,side:team,control_tier:3,levels}],metadata:{level_id:'test-map',settings:{wave_count:12},preset:{name:'Test preset'}},calibration_milestones:i===0?{[p.id]:'milestone'}:{},released_orcs:300,completion_awarded:true,telemetry:{first_placement_s:{green:180,purple:240},pause_count:1,outcome_reason:'all waves cleared'}}));
    window.testPresentation={virtual_test_control:null,journey:{phase:'upgrades',revision:1,deadline:Date.now()/1000+30,server_time:Date.now()/1000},mobile_progress:{player:p,players:[p]}};
    window.testRequest=async(path,value)=>{testCommands.push({path,value});return path.startsWith('history')?{history:{rows}}:{};};
    MobileJourney.update(testPresentation,testRequest,async()=>{});
   },team);
   await page.waitForSelector('.journeyGraph circle');
   assert.equal(await page.locator('.journeyGraph circle').count(),12);
   assert.equal(await page.locator('.journeyGraph polyline').count(),8,'means stay within their cohorts');
   await page.locator('.journeyGraph circle').first().focus();await page.keyboard.press('Enter');
   await page.waitForFunction(()=>document.getElementById('journeyRunDetails').textContent.includes('run-0'));
   await page.locator('[data-upgrade="damage-mortar"]').click();
   assert(await page.evaluate(()=>testCommands.some(c=>c.path==='player'&&c.value.action==='purchase')));
   await page.locator('[data-filter="tier"]').selectOption('3');
   assert(await page.evaluate(()=>testCommands.some(c=>c.path.includes('tier=3')&&c.path.includes('combined=1'))));
   await page.screenshot({path:`/tmp/ltz-${team}-stats.png`});
   await page.locator('#journeyRunDetails').scrollIntoViewIfNeeded();
   await page.screenshot({path:`/tmp/ltz-${team}-stats-details.png`});
   await page.evaluate(team=>{
    const j={phase:'calibration',revision:2,deadline:Date.now()/1000-10,server_time:Date.now()/1000,active_side:team};
    const cal={id:'cal:'+team,stage:'points',captures:{30:{pose:[1,2,3]},31:{pose:[2,3,4]}},arrivals:[],draft:{parallax_points:{}}};
    testPresentation={...testPresentation,journey:j,mobile_calibration:cal,mobile_calibration_ready:true,
     mobile_calibration_preparation:{ready:true,marker_positions:Object.fromEntries([30,31,32,33,34,35].map(i=>[i,{}]))}};
    document.body.classList.add('calibrating');
    MobileJourney.update(testPresentation,testRequest,async()=>{});
   },team);
   assert.equal(await page.locator('.calibrationPoints .calibrated').count(),2);
   await page.locator('[data-capture="32"]').click();
   assert(await page.evaluate(()=>testCommands.some(c=>c.value?.action==='capture'&&c.value.marker===32)));
   await page.screenshot({path:`/tmp/ltz-${team}-calibration.png`});
   await page.setViewportSize({width:844,height:390});
   await page.screenshot({path:`/tmp/ltz-${team}-calibration-landscape.png`});
   await page.setViewportSize({width:568,height:320});
   await page.evaluate(team=>{testPresentation.journey.active_side=team==='green'?'purple':'green';testPresentation.journey.revision++;MobileJourney.update(testPresentation,testRequest,async()=>{});},team);
   assert.equal(await page.locator('#journeyContent h2').textContent(),'Upgrades');
   assert.match(await page.locator('.journeyWaiting').textContent(),/Waiting for .* to finish calibration/);
   assert.equal(await page.locator('[data-upgrade]').count(),5);
   await page.screenshot({path:`/tmp/ltz-${team}-waiting-compact.png`});
   await page.evaluate(team=>{
    testPresentation.journey={...testPresentation.journey,calibration_side:team,active_side:null,error:'Fresh arm feedback required',revision:4};
    testPresentation.mobile_calibration=null;testPresentation.mobile_calibration_ready=false;
    MobileJourney.update(testPresentation,testRequest,async()=>{});
   },team);
   assert.equal(await page.locator('.calibrationPoints button').count(),6);
   assert.equal(await page.locator('[data-capture="30"]').isDisabled(),true);
   assert.match(await page.locator('.calibrationStatus').textContent(),/Fresh arm feedback required/);
   await page.locator('#journeyToggle').click();assert.equal(await page.locator('#journeyContent').isVisible(),false);
   await page.locator('#journeyToggle').click();assert.equal(await page.locator('#journeyContent').isVisible(),true);
   await page.evaluate(team=>{
    testPresentation.journey.calibration_side=team==='green'?'purple':'green';testPresentation.journey.revision++;
    testPresentation.mobile_progress={player:null,players:[]};MobileJourney.update(testPresentation,testRequest,async()=>{});
   },team);
   assert.equal(await page.locator('#journeyContent h2').textContent(),'Upgrades');
   assert.equal(await page.locator('.journeyUpgrades button:disabled').count(),5);
   await page.close();
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({verified,stats:'graphs, cohort means, keyboard details, purchases, filters',calibration:'six markers, saved glows, capture action, waiting partner',errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
