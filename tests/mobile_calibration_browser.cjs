/* Real mobile lesson/bridge/routes. The fixture uses temporary files and fake arms. */
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[];
 try{
  const gm=await browser.newPage();gm.on('pageerror',e=>errors.push(e.message));
  await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/');await gm.waitForFunction(()=>ui.state?.status==='ready');
  await gm.request.post(origin+'/__test/camera',{data:{enabled:true}});
  for(const side of ['green','purple']){
   await gm.request.post(origin+'/__test/camera',{data:{hidden_markers:[31,32,33,34,35]}});
   await gm.request.post(origin+'/__test/calibration-feedback',{data:{connected:false}});
   await gm.locator(side==='green'?'#calibrateGreen':'#calibratePurple').click();
   await gm.waitForFunction(s=>ui.state.journey.calibration_side===s,side);
   const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});page.on('pageerror',e=>errors.push(side+': '+e.message));
   await page.goto(origin+`/s/${side}/p/mobile-ltz/`);
   await page.waitForFunction(()=>document.querySelector('#connect')?.matches(':enabled'));
   assert.equal(await page.locator('[data-capture="30"]').isDisabled(),true,'No lesson before fresh hardware');
   await page.waitForSelector('[data-capture="30"].identified');
   assert.equal(await page.locator('.calibrationPoints .identified').count(),1);
   assert.equal(await page.locator('[data-capture="30"]').evaluate(el=>getComputedStyle(el).opacity),'1','Identified marker glows even before Connect');
   assert.match(await page.locator('.calibrationLocated').textContent(),/1\/6 markers identified/);
   assert.equal(await page.evaluate(()=>state.mobile_calibration),null,'Detection precedes a live arm lesson');
   await gm.request.post(origin+'/__test/camera',{data:{hidden_markers:[]}});
   await page.waitForFunction(()=>document.querySelector('.calibrationLocated')?.textContent.includes('Ready to capture'));
   assert.equal(await page.locator('.calibrationPoints .identified').count(),6);
   assert.equal(await page.locator('[data-capture="30"]').isDisabled(),true,'Optical readiness grants no arm access');
   await page.screenshot({path:`/tmp/${side}-calibration-ready.png`});
   await gm.request.post(origin+'/__test/camera',{data:{hidden_markers:[30]}});
   await page.waitForFunction(()=>state.mobile_camera.tags.some(t=>t.id===30&&t.cached));
   await page.locator('#connect').click();
   try{await page.waitForFunction(()=>session&&state.mobile_calibration_ready&&available()&&state.mobile_arm.coordinate_space==='robot-mm');}
   catch(e){console.log(await page.evaluate(()=>({feedback:document.querySelector('#feedback').textContent,cal:state.mobile_calibration_error,arm:state.mobile_arm,bridge:physicalArm.value})));throw e;}
   const box=await page.locator('#gameJourney').boundingBox();assert(box.y<100,'Instructions start at upper right');
   for(const selector of ['#xyzX','#xyzY','#xyzBullseyes','#calibrationCrosshair'])assert.equal(await page.locator(selector).isVisible(),false,selector+' hidden before six-point calibration');
   assert.equal(await page.locator('#xyzZ').isVisible(),true,'Height remains available');
   assert.equal(await page.locator('#xyzPrecision').isVisible(),true,'Height fine tune remains beside the saved heights');
   await page.locator('#xyzPrecision').click();
   assert.equal(await page.locator('#xyzZIncrease').getAttribute('data-step'),'0.1');
   await page.locator('#xyzPrecision').click();
   await page.waitForFunction(()=>document.querySelectorAll('#markerLabels .markerNumber').length===6);
   assert.equal(await page.locator('#markerLabels .markerNumber').first().isVisible(),true,'Calibration labels are actually displayed');
   assert.equal(await page.locator('#markerLabels .markerNumber').first().evaluate(el=>getComputedStyle(el).color),'rgb(81, 255, 145)');
   assert.equal(await gm.locator('#arucoCacheControls').isVisible(),false);
   await page.waitForFunction(()=>document.querySelector('.calibrationLocated')?.textContent.startsWith('6/6'));
   await gm.request.post(origin+'/__test/camera',{data:{hidden_markers:[30]}});
   await page.waitForFunction(()=>state.mobile_camera.tags.some(t=>t.id===30&&t.cached));
   assert.equal(await page.locator('#markerLabels .markerNumber').count(),6,'Cached target remains labelled while covered');
   await page.locator('#journeyToggle').click();
   assert.equal(await page.locator('#journeyContent').isVisible(),false);
   assert.equal(await page.locator('[data-capture]:visible').count(),6,'All six buttons remain accessible with instructions folded');
   await page.screenshot({path:`/tmp/${side}-calibration-six-collapsed.png`});
   for(const marker of [30,31,32,33,34,35]){
    await page.locator(`[data-capture="${marker}"]`).click();
    await page.waitForFunction(m=>!!state.mobile_calibration.captures[m],String(marker));
   }
   assert.equal(await page.evaluate(()=>Object.values(state.mobile_calibration.draft.points).find(p=>p.marker===30).camera_cached),true,'Occluded capture uses cached optics and live pose');
   await gm.request.post(origin+'/__test/camera',{data:{hidden_markers:[]}});
   await page.waitForSelector('[data-parallax="31"]');
   assert.equal(await page.locator('[data-capture]').count(),0,'Four raised references replace the six arm capture buttons');
   assert.equal(await page.locator('[data-parallax]:visible').count(),4,'All four raised references remain accessible while folded');
   assert.equal(await page.locator('#calibrationCrosshair').isVisible(),true,'Calibration crosshair appears after the sixth point');
   assert.equal(await page.locator('[data-parallax="31"]').isDisabled(),true,'Place the crosshair before saving');
   assert.equal(await page.locator('#calibrationComplete').isDisabled(),true,'Incomplete samples cannot complete the turn');
   await page.locator('#journeyToggle').click();
   assert.match(await page.locator('#calibrationIntro').textContent(),/physical 100-series ArUco tag 3 cm above/);
   await page.screenshot({path:`/tmp/${side}-calibration-perspective.png`});
   await page.locator('[data-height="pickup_height"]').click();
   await gm.request.post(origin+'/__test/calibration-feedback',{data:{z:60}});
   await page.locator('[data-height="transport_height"]').click();
   await page.locator('#journeyToggle').click();
   const movesBefore=await gm.request.get(origin+'/__test/robot-commands').then(r=>r.json()).then(rows=>rows.filter(r=>['move','joint-move'].includes(r.action)).length);
   const cdp=await page.context().newCDPSession(page);
   const touch=(type,points=[])=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map((p,i)=>({x:p.x,y:p.y,id:i+1,radiusX:5,radiusY:5,force:1}))});
   for(const [i,marker] of [31,35,33,34].entries()){
    // Taps at four distinct image locations exercise viewport inversion,
    // including Purple's 180-degree view. No robot command comes from a tap.
    const uv=[[.4,.4],[.6,.4],[.6,.6],[.4,.6]][i];
    const pos=await page.evaluate(([u,v])=>{const p=viewport.screen(u*viewport.w,v*viewport.h),r=battlefield.getBoundingClientRect();return{x:p.x+r.left,y:p.y+r.top};},uv);
    await page.touchscreen.tap(pos.x,pos.y);
    await page.waitForFunction(()=>document.querySelector('#calibrationCrosshair').dataset.mapped==='true');
    assert.equal(await page.evaluate(m=>!!state.mobile_calibration.draft.parallax_points[m],String(marker)),false,'Image tap positions the crosshair without saving');
    const preview=await page.evaluate(()=>MobileJourney.perspectiveTarget().camera);
    assert(Math.abs(preview.u-uv[0])<.004&&Math.abs(preview.v-uv[1])<.004,'Crosshair uses canonical camera coordinates for either orientation');
    const reticle=await page.locator('#calibrationCrosshair g').boundingBox();
    assert(Math.abs(reticle.x+reticle.width/2-pos.x)<2&&Math.abs(reticle.y+reticle.height/2-pos.y)<2,'Visible crosshair follows the finger even in Purple rotation');
    const fine=i%2===1;
    if(fine)await page.locator('#xyzPrecision').click();
    const metrics=await page.evaluate(()=>({w:viewport.w,h:viewport.h,scale:viewport.scale,direction:viewport.direction}));
    // Start off-centre, inside Targeting's grab area. A short fine drag must
    // survive release even below the tap-cancellation threshold of 8 px.
    const dx=fine?6:-18,dy=fine?3:9,start={x:pos.x+4,y:pos.y+3};
    await touch('touchStart',[start]);assert.equal(await page.evaluate(()=>!!perspectiveDrag),true);
    await touch('touchMove',[{x:start.x+dx,y:start.y+dy}]);await touch('touchEnd');
    const factor=fine?.1:1,expected=[uv[0]+dx*metrics.direction*factor/metrics.scale/metrics.w,uv[1]+dy*metrics.direction*factor/metrics.scale/metrics.h];
    const dragged=await page.evaluate(()=>MobileJourney.perspectiveTarget().camera);
    assert(Math.abs(dragged.u-expected[0])<.0001&&Math.abs(dragged.v-expected[1])<.0001,'Drag preserves the grab offset, orientation and fine-tune scale');
    const draggedReticle=await page.locator('#calibrationCrosshair g').boundingBox();
    assert(Math.abs(draggedReticle.x+draggedReticle.width/2-pos.x-dx*factor)<2&&Math.abs(draggedReticle.y+draggedReticle.height/2-pos.y-dy*factor)<2,'Visible crosshair follows regular/fine drag');
    assert.equal(await page.evaluate(m=>!!state.mobile_calibration.draft.parallax_points[m],String(marker)),false,'Dragging never saves a sample');
    if(fine)await page.locator('#xyzPrecision').click();
    if(i===0){
     const center={x:draggedReticle.x+draggedReticle.width/2,y:draggedReticle.y+draggedReticle.height/2};
     const connection=await page.locator('#connection').textContent();
     await touch('touchStart',[center]);await touch('touchCancel');
     assert.equal(await page.evaluate(()=>perspectiveDrag),null);
     assert.equal(await page.locator('#connection').textContent(),connection,'Optical drag cancellation does not suspend the robot connection');
     const zoomBefore=await page.evaluate(()=>viewport.zoom);
     await touch('touchStart',[center]);await touch('touchStart',[center,{x:center.x+60,y:center.y+30}]);
     assert.equal(await page.evaluate(()=>perspectiveDrag),null,'Second finger hands the gesture to camera navigation');
     await touch('touchMove',[{x:center.x-8,y:center.y},{x:center.x+75,y:center.y+35}]);
     await touch('touchEnd',[{x:center.x-8,y:center.y}]);
     await touch('touchMove',[{x:center.x-12,y:center.y+2}]);await touch('touchEnd');
     assert(await page.evaluate(()=>viewport.zoom)>zoomBefore);
     assert.deepEqual(await page.evaluate(()=>MobileJourney.perspectiveTarget().camera),dragged,'Pinch and the remaining finger cannot restart an optical drag');
     await page.evaluate(()=>{viewport.fit();syncViewport()});
     await page.screenshot({path:`/tmp/${side}-calibration-crosshair-drag.png`});
    }
    await page.locator(`[data-parallax="${marker}"]`).click();
    await page.waitForFunction(m=>!!state.mobile_calibration.draft.parallax_points[m],String(marker));
    const saved=await page.evaluate(m=>state.mobile_calibration.draft.parallax_points[m],String(marker));
    assert(Math.abs(saved.raised.u-expected[0])<.0001&&Math.abs(saved.raised.v-expected[1])<.0001,'Saved drag position remains canonical');assert.equal(saved.height_mm,30);
    await page.waitForSelector(`[data-parallax="${marker}"].calibrated`);
    assert.equal(await page.locator('#journeyContent').isVisible(),false,'Saving does not unfold the instructions');
   }
   assert.match(await page.locator('.perspectiveCount').textContent(),/4\/4/);
   await page.screenshot({path:`/tmp/${side}-calibration-four-collapsed.png`});
   const movesAfter=await gm.request.get(origin+'/__test/robot-commands').then(r=>r.json()).then(rows=>rows.filter(r=>['move','joint-move'].includes(r.action)).length);
   assert.equal(movesAfter,movesBefore,'Crosshair taps, drags, cancellation, pinch and raised samples never command robot movement');
   if(side==='purple'){
    // Already validated sessions also have a way out without pickup exercises.
    await page.locator('#journeyToggle').click();
    await page.locator('#calibrationCommit').click();
    try{await page.waitForFunction(()=>state.mobile_calibration.stage==='tutorial');}
    catch(e){console.log(await page.locator('#journeyMessage').textContent());throw e;}
    assert.equal(await page.locator('#calibrationCrosshair').isVisible(),false);
    await page.waitForFunction(()=>document.querySelectorAll('#savedCalibration option').length>=2);
    const option=await page.locator('#savedCalibration option').nth(1).getAttribute('value');
    await page.locator('#savedCalibration').selectOption(option);await page.waitForSelector('#savedCalibrationDetails');
    assert.equal(await page.locator('#savedCalibrationDetails tbody tr').count(),6);
    assert.match(await page.locator('#savedCalibrationDetails').textContent(),/4\/4 saved/);
    await page.locator('#journeyToggle').click();
   }
   assert.equal(await page.locator('#journeyContent').isVisible(),false);
   assert.equal(await page.locator('#calibrationComplete').isVisible(),true,'Completion remains accessible with steps folded');
   assert.equal(await page.locator('#calibrationComplete').isEnabled(),true,'All measured targets and heights allow completion');
   await page.screenshot({path:`/tmp/${side}-calibration-ready-to-complete.png`});
   await page.locator('#calibrationComplete').click();
   try{await page.waitForFunction(()=>state.journey.phase==='lobby')}
   catch(e){console.log(await page.locator('#journeyMessage').textContent());throw e}
   await gm.waitForFunction(()=>ui.state.journey.phase==='lobby');
   assert.equal(await page.locator('#calibrationCrosshair').isVisible(),false,'Finished calibration leaves the optical controls');
   const history=await page.request.get(origin+`/s/gamemaster/p/mobile-ltz-api/api/calibrations?side=${side}`).then(r=>r.json());
   assert(history.rows.every(r=>r.side===side),'History stays per arm');
   assert.equal(history.selection,'latest','A new completed lesson becomes the default');
   assert.equal(history.active_id,history.latest_id,'The newly captured rig is installed automatically');
   await page.screenshot({path:`/tmp/${side}-calibration-saved.png`});
   await page.close();await gm.request.post(origin+'/__test/calibration-feedback',{data:{z:10}});
  }
  assert.deepEqual(errors,[]);console.log('PASS both players: six captures → four tap/drag samples with fine tune, pinch and cancellation → visible completion while folded → saved calibration and return to game, including previously validated tutorial sessions; no robot movement');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
