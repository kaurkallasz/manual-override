// Run against the isolated virtual fixture on port 8127.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8127';
const team=process.env.MOBILE_TEST_TEAM==='purple'?'purple':'green';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
  const errors=[],moves=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().endsWith('/api/command')){const data=r.postDataJSON();if(data?.action==='xyz')moves.push(data);}});
  await page.request.post(root+'/__test/command',{data:{action:'reset'}});
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:3}});
  await page.goto(root+`/s/${team}/p/mobile-ltz/`);
  await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='targeting');
  assert.equal(await page.locator('#targetMove').textContent(),'Go');
  assert.equal(await page.locator('#targetMove').isDisabled(),true,'No target has been mapped yet');
  assert.equal(await page.locator('#targetMove').evaluate(el=>getComputedStyle(el).boxShadow),'none');
  for(const id of ['xyzX','xyzY','jointRig','wheel'])assert.equal(await page.locator('#'+id).isVisible(),false,id+' hidden');
  for(const id of ['xyzZ','xyzZActual','xyzBullseyes','xyzPrecision','zPreset1','zPreset2','zPreset3'])assert.equal(await page.locator('#'+id).isVisible(),true,id+' retained');
  const cdp=await page.context().newCDPSession(page);
  const touch=(type,points=[])=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map((p,i)=>({x:p.x,y:p.y,id:i+1,radiusX:5,radiusY:5,force:1}))});
  const target=()=>page.evaluate(()=>viewport.screen(xyzTarget.x,xyzTarget.y));
  const settled=()=>page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight&&Math.hypot(state.mobile_arm.tip.x-xyzTarget.x,state.mobile_arm.tip.y-xyzTarget.y)<.2);
  const start=await page.evaluate(()=>({...xyzTarget,scale:viewport.scale,direction:viewport.direction}));
  let p=await target();await touch('touchStart',[p]);
  assert.equal(await page.evaluate(()=>!!targetDrag),true,'finger grabs bullseye');
  await touch('touchMove',[{x:p.x-18,y:p.y+3}]);
  await page.waitForFunction(()=>$('xyzBullseyes').dataset.aligned==='false');
  await page.screenshot({path:'/tmp/mobile-targeting-drag.png'});
  await touch('touchEnd');
  await page.waitForFunction(()=>!$('targetMove').disabled);
  assert.equal(moves.length,0,'Mapping a preview does not move the arm');
  assert.notEqual(await page.locator('#targetMove').evaluate(el=>getComputedStyle(el).boxShadow),'none','A new target lights Go');
  await page.screenshot({path:`/tmp/mobile-targeting-${team}-go-ready.png`});
  await page.locator('#targetMove').click();await settled();
  assert.equal(await page.locator('#targetMove').isDisabled(),true,'Submitted targets cannot be sent twice');
  let result=await page.evaluate(()=>({...xyzTarget}));
  assert.ok(Math.abs(result.x-(start.x-18*start.direction/start.scale))<.2,'touch maps screen X into world X');
  assert.ok(Math.abs(result.y-(start.y+3*start.direction/start.scale))<.2,'touch maps screen Y into world Y');
  assert.ok(Math.abs(result.z-start.z)<.001,'drag preserves height');
  await page.locator('#xyzPrecision').click();
  p=await target();const fineStart={...result};await touch('touchStart',[p]);await touch('touchMove',[{x:p.x-20,y:p.y+10}]);await touch('touchEnd');await page.locator('#targetMove').click();await settled();
  result=await page.evaluate(()=>({...xyzTarget}));
  assert.ok(Math.abs(result.x-fineStart.x+2*start.direction/start.scale)<.2,'fine drag is one tenth');
  assert.ok(Math.abs(result.y-fineStart.y-1*start.direction/start.scale)<.2);
  await page.locator('#xyzZ').press('ArrowRight');
  await page.waitForFunction(z=>Math.abs(state.mobile_arm.tip.z-z)>.05,result.z);await settled();
  // Saving and recalling Z in Targeting preserves the dragged XY position.
  await page.locator('#zPreset1').focus();await page.keyboard.down('Space');await page.waitForTimeout(3100);await page.keyboard.up('Space');
  assert.equal(await page.locator('#zPreset1').getAttribute('data-saved'),'true');
  const saved=await page.evaluate(()=>({...xyzTarget}));
  await page.locator('#xyzZ').press('ArrowRight');await settled();
  await page.locator('#zPreset1').click();await settled();
  result=await page.evaluate(()=>({...xyzTarget}));for(const key of ['x','y','z'])assert.ok(Math.abs(saved[key]-result[key])<.02,'preset retains '+key);
  // Background taps do not teleport; two fingers remain camera-only.
  const before=moves.length;await touch('touchStart',[{x:500,y:240}]);await touch('touchEnd');await page.waitForTimeout(200);assert.equal(moves.length,before);
  p=await target();await touch('touchStart',[p]);await touch('touchStart',[p,{x:p.x+80,y:p.y+30}]);
  assert.equal(await page.evaluate(()=>targetDrag),null);
  await touch('touchMove',[{x:p.x-10,y:p.y},{x:p.x+100,y:p.y+40}]);await touch('touchEnd');await page.waitForTimeout(200);
  assert.ok(await page.evaluate(()=>viewport.zoom)>1);assert.equal(moves.length,before,'pinch issues no arm movement');
  await page.evaluate(()=>{viewport.fit();syncViewport();});
  // A cancelled active touch goes through the established suspension path.
  p=await target();await touch('touchStart',[p]);await touch('touchCancel');
  await page.waitForFunction(()=>!targetDrag&&!pendingXYZ);
  await page.waitForFunction(()=>$('connection').textContent==='Connected');
  const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
  for(const [width,height] of [[844,390],[390,844],[568,320],[320,568],[1024,768]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(200);
   const selectors=['.telemetry','.identity','#expand','.connectionControls','#xyzHeightControl','#xyzPrecision','#pumpButtons','#zPreset1','#zPreset2','#zPreset3','#targetMove'];
   const boxes=[];for(const selector of selectors)boxes.push([selector,await page.locator(selector).boundingBox()]);
   await page.screenshot({path:`/tmp/mobile-targeting-${width}x${height}.png`});
   for(let i=0;i<boxes.length;i++){
    const [name,a]=boxes[i];assert.ok(a&&a.x>=0&&a.y>=0&&a.x+a.width<=width+.1&&a.y+a.height<=height+.1,`${width}x${height} ${name} fits ${JSON.stringify(a)}`);
    for(let j=i+1;j<boxes.length;j++)assert.ok(!overlap(a,boxes[j][1]),`${width}x${height}: ${name} overlaps ${boxes[j][0]}`);
   }
   const pump=await page.locator('#pumpButtons').boundingBox(),fine=await page.locator('#xyzPrecision').boundingBox(),third=await page.locator('#zPreset3').boundingBox(),go=await page.locator('#targetMove').boundingBox();
   assert.ok(Math.abs(fine.x-third.x)<1&&Math.abs(fine.width-third.width)<1,'Fine tune aligns with the numbered presets');
   const gap=await page.locator('#zPresetButtons').evaluate(el=>parseFloat(getComputedStyle(el).gap));
   assert.ok(Math.abs(fine.y-third.y-third.height-gap)<1,'Fine tune sits directly below preset 3');
   assert.ok(Math.abs(go.x-pump.x-pump.width-8)<1&&Math.abs(go.y-pump.y)<1,'Go aligns beside Suck/Blow');
   assert.ok(Math.abs(go.width-pump.width)<1&&Math.abs(go.height-pump.height)<1,'Go matches the combined pump button size');
  }
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}});
  await page.reload();await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='cue');
  assert.equal(await page.locator('#targetMove').isVisible(),false,'Go belongs only to Targeting');
  assert.equal(await page.locator('#xyzPrecision').evaluate(el=>el.parentElement.classList.contains('xyzControls')),true,'Cue restores its precision dock');
  await page.locator('#stop').click();assert.equal(await page.locator('#xyzZ').isDisabled(),true);
  assert.equal(await page.evaluate(()=>targetDrag),null);
  assert.deepEqual(errors,[]);
  console.log('Targeting passed: preview-only touch drag, glowing Go submission, fine adjustment, unchanged Z, presets, pinch isolation, cancellation, five aligned layouts, mode switch and Stop.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
