// Real buttons/routes and owner persistence, temporary data, fake sensors/relay.
const assert=require('node:assert/strict'),{chromium}=require('playwright'),{PNG}=require('pngjs');
const origin='http://127.0.0.1:8117';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],verified=[];
 try{
  const gm=await browser.newPage();gm.on('pageerror',error=>errors.push('GM: '+error.message));
  await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/');await gm.waitForFunction(()=>ui.state?.status==='ready');
  await gm.request.post(origin+'/__test/camera',{data:{enabled:true}});
  const players=[];
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
   page.on('pageerror',error=>errors.push(side+': '+error.message));
   await page.goto(origin+`/s/${side}/p/mobile-ltz/`);await page.waitForFunction(()=>document.getElementById('app').dataset.playfield==='video');
   await page.locator('#levelsOpen').click();await page.locator('#openPlayers').click();
   await page.waitForSelector('#gameJourney.playerPrompt');
   assert((await page.locator('#gameJourney').boundingBox()).height<540,'Compact player entry box');
   assert.equal(await page.locator('.journeyGraph').count(),0,'History does not crowd the name prompt');
   await page.locator('#journeyNewName').fill(side+' review');await page.locator('#journeyCreate').click();
   await page.waitForFunction(n=>document.querySelector('#journeyPlayer option:checked')?.textContent.includes(n),side+' review');
   await page.screenshot({path:`/tmp/progression-${side}-name-box.png`});players.push({side,page});
  }
  for(const [index,mode]of ['joint','xyz','targeting','cue'].entries()){
   await gm.locator('#testOverride').check();await gm.locator('#testMobileControl').selectOption(String(index+1));await gm.locator('#applyTestUnlocks').click();
   try{await gm.waitForFunction(t=>ui.state?.virtual_test_control===t,index+1);}catch(error){console.log(await gm.evaluate(()=>({tier:ui.state.virtual_test_control,choice:document.getElementById('testMobileControl').value,message:document.getElementById('testUnlockStatus').textContent})));throw error;}
   for(const {side,page}of players){await page.waitForFunction(mode=>document.getElementById('app').dataset.controlMode===mode,mode);verified.push(side+' '+mode);}
  }
  await gm.evaluate(()=>applyState({...ui.state,server_time:ui.state.server_time-1,virtual_test_control:1},'SSE'));
  assert.equal(await gm.evaluate(()=>ui.state.virtual_test_control),4,'An older stream update cannot undo the applied command');
  assert.equal(await gm.locator('#scoredPlay').isChecked(),false);
  await gm.locator('#start').click();await gm.waitForFunction(()=>ui.state?.phase==='running');
  assert.equal(await gm.evaluate(()=>ui.state.progress.reward_enabled),false);
  for(const {page}of players)await page.waitForSelector('#gameJourney',{state:'hidden'});
  await gm.locator('#reset').click();await gm.waitForFunction(()=>ui.state?.phase==='setup');
  const screen=await browser.newPage();screen.on('pageerror',error=>errors.push('Screen: '+error.message));await screen.goto(origin+'/s/gamemaster/p/laser-tag-y/screen');
  const before=await gm.request.get(origin+'/s/gamemaster/p/playfield-areas/api/state').then(r=>r.json());
  let greenTargets;const displayWrites=[];
  screen.on('request',request=>{if(request.method()==='PATCH'&&request.url().includes('/playfield-areas/'))displayWrites.push(request.url());});
  for(const [button,side]of [['calibrateGreen','green'],['calibratePurple','purple'],['calibrateBoth','green']]){
   await gm.locator('#'+button).click();await gm.waitForFunction(s=>ui.state.journey?.active_side===s,side);
   assert.equal(await gm.locator('#calibrationDisplay').count(),0,'GM observes the camera, never the projected target editor');
   await gm.waitForFunction(()=>{const image=document.getElementById('boardCamera');return !image.hidden&&image.naturalWidth>0&&document.getElementById('stage').classList.contains('calibration-camera');});
   assert.match(await gm.locator('#boardCamera').getAttribute('src'),/^data:image\/jpeg;base64,/);
   assert.equal(await gm.locator('.camera-view').evaluate(el=>getComputedStyle(el).transform),'none','All outer targets remain in the full camera frame');
   await screen.waitForSelector('#calibrationDisplay');
   assert.equal(await screen.locator('#calibrationDisplay').getAttribute('src'),'/s/gamemaster/p/playfield-areas/screen?presentation=1');
   const canvas=screen.frameLocator('#calibrationDisplay').locator('canvas').first();
   await canvas.waitFor({state:'visible'});
   assert.equal(await gm.evaluate(()=>ui.state.virtual_play),false);
   const active=players.find(p=>p.side===side).page,waiting=players.find(p=>p.side!==side).page;
   await active.waitForSelector('body.calibrating #gameJourney.calibrationLesson');
   await active.waitForFunction(()=>document.querySelector('[data-capture="30"]')?.matches(':enabled'));
   assert.equal(await active.locator('#mapCanvas').isVisible(),false);assert.equal(await active.locator('#gameCanvas').isVisible(),false);
   await waiting.waitForFunction(()=>document.getElementById('journeyContent').textContent.includes('Waiting for'));
   assert.equal(await waiting.locator('#journeyContent h2').textContent(),'Upgrades');
   assert.equal(await waiting.locator('[data-upgrade]').count(),5);
   await active.locator('[data-capture="30"]').click();await active.waitForSelector('[data-capture="30"].calibrated');
   const field=await gm.request.get(origin+'/s/gamemaster/p/playfield-areas/api/state').then(r=>r.json());
   if(side==='green'&&!greenTargets)greenTargets=field.areas;
   for(const area of field.areas){
    const green=greenTargets.find(a=>a.marker===area.marker),sign=side==='purple'?-1:1;
    assert.equal(area.x,green.x*sign,side+' projected target X');
    assert.equal(area.z,green.z*sign,side+' projected target Y');
   }
   assert.equal(await active.evaluate(()=>state.mobile_calibration.display_camera_view),side==='purple'?'rot180':'normal');
   assert.equal(await active.evaluate(()=>viewport.rotation),side==='purple'?180:0,'Phone rotates camera and its overlays together');
   assert.deepEqual(field.areas.map(a=>a.marker).sort((a,b)=>a-b),[30,31,32,33,34,35]);
   assert.deepEqual(field.areas.filter(a=>a.color==='#33ff88').map(a=>a.marker),[30]);
   assert.equal(await gm.locator('#start').isDisabled(),true);
   await gm.locator('#stage').screenshot({path:`/tmp/progression-${button}-camera.png`});await screen.screenshot({path:`/tmp/progression-${button}-external.png`});await active.screenshot({path:`/tmp/progression-${side}-calibration.png`});
   if(side==='purple'){
    // Even direct events inside the frame cannot zoom, orbit or save the projection.
    await screen.waitForTimeout(500);
    const pixels=await canvas.screenshot({path:'/tmp/calibration-projection-before.png'});
    await canvas.dispatchEvent('wheel',{deltaY:-500,clientX:250,clientY:200});
    await canvas.dispatchEvent('pointerdown',{pointerId:1,pointerType:'mouse',button:0,clientX:250,clientY:200});
    await canvas.dispatchEvent('pointermove',{pointerId:1,pointerType:'mouse',buttons:1,clientX:400,clientY:300});
    await canvas.dispatchEvent('pointerup',{pointerId:1,pointerType:'mouse',button:0,clientX:400,clientY:300});
    await canvas.dispatchEvent('keydown',{key:'r',bubbles:true});
    await screen.waitForTimeout(400);
    const afterPixels=await canvas.screenshot({path:'/tmp/calibration-projection-after.png'});
    const a=PNG.sync.read(pixels),b=PNG.sync.read(afterPixels);
    assert.equal(a.width,b.width);assert.equal(a.height,b.height);
    let maxDelta=0;for(let i=0;i<a.data.length;i++)maxDelta=Math.max(maxDelta,Math.abs(a.data[i]-b.data[i]));
    // Capture glow eases asymptotically; allow two color levels, no geometry shift.
    assert(maxDelta<=2,`Presentation camera moved (max pixel delta ${maxDelta})`);
    assert.deepEqual(displayWrites,[],'Presentation sends no field or camera mutations');
   }
   verified.push(button+' GM camera + oriented external targets + durable glow');
  }
  await gm.locator('#cancelCalibration').click();await gm.waitForFunction(()=>!document.getElementById('stage').classList.contains('calibration-camera'));
  await screen.waitForSelector('#calibrationDisplay',{state:'hidden'});
  const restored=await gm.request.get(origin+'/s/gamemaster/p/playfield-areas/api/state').then(r=>r.json());
  assert.deepEqual(restored.areas,before.areas);assert.deepEqual(restored.settings,before.settings);
  verified.push('Direct Green → Purple → Both test switching, safe cancellation and field/view restoration');
  // Reproduce the venue failure: restored practice + offline arm, then reload Y.
  await gm.locator('#calibrateGreen').click();await gm.waitForFunction(()=>ui.state.journey.active_side==='green');
  await gm.request.post(origin+'/__test/calibration-feedback',{data:{connected:false}});
  await gm.request.post(origin+'/__test/calibration-restart',{data:{legacy_active_id:true}});
  await gm.reload();await gm.waitForFunction(()=>ui.state?.journey?.phase==='lobby');
  await screen.waitForSelector('#calibrationDisplay',{state:'hidden'});
  assert.equal(await gm.evaluate(()=>ui.state.journey.motion_blocked),true,'Screen exit does not waive pending arm stop');
  assert.equal(await gm.locator('#start').isDisabled(),true);
  const bar=await gm.locator('.display-controls').boundingBox(),stage=await gm.locator('#stage').boundingBox();
  assert(bar.y+bar.height<=stage.y,'Game/Green/Purple controls remain above the camera');
  for(const [button,side]of [['calibratePurple','purple'],['calibrateGreen','green']]){
   await gm.locator('#'+button).click();
   await gm.waitForFunction(s=>ui.state.journey.phase==='calibration'&&ui.state.journey.queue[0]===s,side);
   await screen.waitForSelector('#calibrationDisplay');
   await gm.waitForFunction(()=>document.getElementById('calibrationStatus').textContent.includes('Targets ready for the external screen'));
   const field=await gm.request.get(origin+'/s/gamemaster/p/playfield-areas/api/state').then(r=>r.json());
   for(const area of field.areas){const base=greenTargets.find(a=>a.marker===area.marker),sign=side==='purple'?-1:1;assert.equal(area.x,base.x*sign);assert.equal(area.z,base.z*sign);}
   assert.equal(await gm.evaluate(()=>ui.state.journey.active_side),null,'Offline preview never activates the lesson');
   assert.match(await gm.locator('#calibrationStatus').textContent(),/stop/);
   const selected=players.find(p=>p.side===side).page,partner=players.find(p=>p.side!==side).page;
   // Cold-opening the phone while only the display is reserved used to show
   // "Waiting for calibration to finish calibration" on BOTH phones.
   await selected.reload();
   await selected.waitForSelector('#gameJourney.calibrationLesson');
   assert.match(await selected.locator('#journeyContent').textContent(),/Auto PP Cal 2/);
   assert.equal(await selected.locator('.calibrationPoints button').count(),6);
   assert.equal(await selected.locator('[data-capture="30"]').isDisabled(),true,'Preview cannot capture without an active lesson');
   assert.match(await selected.locator('.calibrationStatus').textContent(),/stop/);
   assert.equal(await selected.locator('#app').getAttribute('data-control-mode'),'xyz');
   await selected.locator('#journeyToggle').click();assert.equal(await selected.locator('#journeyContent').isVisible(),false);
   await selected.locator('#journeyToggle').click();assert.equal(await selected.locator('#journeyContent').isVisible(),true);
   await partner.waitForFunction(()=>document.querySelector('#journeyContent h2')?.textContent==='Upgrades');
   assert.match(await partner.locator('.journeyWaiting').textContent(),new RegExp('Waiting for '+side,'i'));
   assert.equal(await partner.locator('[data-upgrade]').count(),5);
   await selected.screenshot({path:`/tmp/mobile-${side}-calibration-pending.png`});
   await partner.screenshot({path:`/tmp/mobile-${partner===players[0].page?'green':'purple'}-upgrade-wait.png`});
  }
  await gm.locator('#cancelCalibration').click();await gm.waitForFunction(()=>ui.state.journey.phase==='lobby');
  await screen.waitForSelector('#calibrationDisplay',{state:'hidden'});
  await gm.waitForTimeout(600);assert.equal(await gm.evaluate(()=>ui.state.journey.phase),'lobby');
  await gm.screenshot({path:'/tmp/y-game-screen-navigation.png'});
  await gm.request.post(origin+'/__test/calibration-feedback',{data:{connected:true}});
  await gm.waitForFunction(()=>ui.state.journey.motion_blocked===false);
  await gm.locator('#calibratePurple').click();await gm.waitForFunction(()=>ui.state.journey.active_side==='purple');
  const purple=players.find(p=>p.side==='purple').page;
  await purple.waitForFunction(()=>document.querySelector('[data-capture="30"]')?.matches(':enabled'));
  await purple.locator('[data-capture="30"]').click();await purple.waitForSelector('[data-capture="30"].calibrated');
  await gm.locator('#cancelCalibration').click();await gm.waitForFunction(()=>ui.state.journey.phase==='lobby');
  verified.push('Reload defaults to game; offline Green/Purple preview + exit work; motion stays blocked until measured stop recovery');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({verified,start:'actual GM Start → practice running; both player lobbies close',profiles:'compact matching name box for both teams',errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
