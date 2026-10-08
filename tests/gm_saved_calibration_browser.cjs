/* Actual GM/Game/Cal 2 routes, temporary persistence and fake arms only. */
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117',base=origin+'/s/gamemaster/p/laser-tag-y';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')posts.push(r.url())});
  await page.request.post(origin+'/__test/saved-calibrations');
  await page.request.post(origin+'/__test/camera',{data:{enabled:true,stale:false,calibration_revision:'current-camera'}});
  // Preview must obtain the real camera even when the game is in virtual mode.
  await page.request.post(base+'/api/command',{data:{action:'set_virtual',virtual_play:true}});
  await page.goto(base+'/');await page.waitForFunction(()=>ui.state?.status==='ready');
  await page.waitForFunction(()=>!document.querySelector('[data-history-preview]').disabled);
  assert.equal(await page.locator('[data-history-select]').inputValue(),'latest');
  for(const side of ['green','purple']){
   await page.locator('[data-history-side]').selectOption(side);
   await page.waitForFunction(s=>document.querySelector(`[data-history-select] option[value="rig:${s}:2"]`),side);
   await page.locator('[data-history-select]').selectOption(`rig:${side}:2`);
   assert.equal(await page.locator('[data-history-warning]').isVisible(),true);
   assert.match(await page.locator('[data-history-warning]').textContent(),/less precise.*All control levels remain available/);
   assert.equal(await page.locator('[data-history-apply]').isDisabled(),false);
   const before=posts.length;
   if(await page.locator('[data-history-preview]').getAttribute('aria-pressed')==='false')await page.locator('[data-history-preview]').click();
   try{await page.waitForSelector('#savedCalibrationOverlay:visible')}
   catch(error){console.log(await page.evaluate(()=>({preview:savedCalibrations.isPreview(),image:{hidden:boardCamera.hidden,w:boardCamera.naturalWidth,h:boardCamera.naturalHeight},status:document.querySelector('[data-history-status]').textContent,camera:cameraState.textContent,phase:ui.state?.phase})));throw error}
   assert.equal(await page.locator('#boardCamera').isVisible(),true);
   assert.equal(await page.locator('[data-saved-marker]').count(),6);
   assert.equal(await page.locator('[data-saved-raised]').count(),4);
   assert.equal(await page.locator('#stage').evaluate(el=>el.classList.contains('rendered')),false);
   assert.equal(await page.evaluate(()=>ui.state.virtual_play),true,'Preview changes no game mode');
   const history=await page.request.get(base+'/api/calibrations?side='+side).then(r=>r.json());
   const row=history.rows.find(r=>r.id===`rig:${side}:2`),p=row.draft.points.p1;
   const bounds=await page.locator('[data-saved-marker="30"]').evaluate(el=>({x:parseFloat(el.getAttribute('x'))+parseFloat(el.getAttribute('width'))/2,y:parseFloat(el.getAttribute('y'))+parseFloat(el.getAttribute('height'))/2}));
   assert(Math.abs(bounds.x-p.camera.u*1280)<.001&&Math.abs(bounds.y-p.camera.v*720)<.001,'Overlay uses canonical camera coordinates without another Purple rotation');
   assert.equal(posts.length,before,'Selecting and previewing send no mutations');
   await page.screenshot({path:`/tmp/gm-${side}-saved-calibration.png`});
   await page.locator('[data-history-apply]').click();
   await page.waitForFunction(()=>document.querySelector('[data-history-status]').textContent.startsWith('Calibration applied.'));
   const restored=await page.request.get(base+'/api/calibrations?side='+side).then(r=>r.json());
   assert.equal(restored.active_id,`rig:${side}:2`);assert.equal(restored.latest_id,`rig:${side}:3`);
   assert.equal(restored.selection,`rig:${side}:2`);
   assert.equal(restored.rows.find(r=>r.active).camera_compatibility.status,'approximate');
   assert.equal(await page.locator('[data-history-warning]').isVisible(),true);
   await page.locator('[data-history-select]').selectOption('latest');
   await page.locator('[data-history-apply]').click();
   await page.waitForFunction(()=>document.querySelector('[data-history-status]').textContent.startsWith('Calibration applied.'));
   const latest=await page.request.get(base+'/api/calibrations?side='+side).then(r=>r.json());
   assert.equal(latest.active_id,`rig:${side}:3`);assert.equal(latest.selection,'latest');
  }
  await page.request.post(origin+'/__test/camera',{data:{calibration_revision:'fixture'}});
  await page.locator('[data-history-refresh]').click();
  await page.waitForSelector('[data-history-warning]',{state:'hidden'});
  await page.locator('[data-history-apply]').click();
  await page.waitForFunction(()=>document.querySelector('[data-history-status]').textContent.startsWith('Calibration applied.'));
  // A failed current camera must never leave historical targets on a blank view.
  await page.request.post(origin+'/__test/camera',{data:{stale:true}});
  await page.waitForSelector('#savedCalibrationOverlay',{state:'hidden'});
  await page.request.post(origin+'/__test/camera',{data:{stale:false}});
  // Toggle preview to reconnect the stream ended by the fixture's outage.
  await page.locator('[data-history-preview]').click();await page.locator('[data-history-preview]').click();
  await page.waitForSelector('#savedCalibrationOverlay:visible');
  // Applying from a calibration practice screen restores the game through Journey.
  await page.locator('#calibratePurple').click();await page.waitForFunction(()=>ui.state.journey.phase==='calibration');
  await page.locator('[data-history-apply]').click();
  await page.waitForFunction(()=>document.querySelector('[data-history-status]').textContent.startsWith('Calibration applied.'));
  assert.equal(await page.evaluate(()=>ui.state.journey.phase),'lobby');
  await page.request.post(origin+'/__test/command',{data:{action:'start'}});
  await page.waitForFunction(()=>ui.state.phase==='running');
  assert.equal(await page.locator('[data-history-apply]').isDisabled(),true);
  const denied=await page.request.post(base+'/api/command',{data:{action:'calibration_apply',side:'purple',id:'latest'}});
  assert.equal(denied.status(),400);assert.match((await denied.json()).error,/End the current game/);
  const robot=await page.request.get(origin+'/__test/robot-commands').then(r=>r.json());
  assert.equal(robot.filter(r=>['move','joint-move','enable'].includes(r.action)).length,0);
  await page.request.post(origin+'/__test/command',{data:{action:'reset'}});
  assert.deepEqual(errors,[]);console.log('PASS GM saved calibrations: both arms, latest default, canonical camera overlay, read-only preview, restore/latest apply, camera failure, practice exit and running-game rejection');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
