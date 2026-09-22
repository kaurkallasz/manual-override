const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8127';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.request.post(root+'/__test/command',{data:{action:'reset'}});
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}});
  await page.goto(root+'/s/green/p/mobile-ltz/');
  await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='cue');
  await page.locator('.cueRow [data-field=destination]').selectOption('46');
  const cdp=await page.context().newCDPSession(page);
  const touch=(type,points=[])=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map((p,i)=>({x:p.x,y:p.y,id:i+1,radiusX:5,radiusY:5,force:1}))});
  const tap=async p=>{await touch('touchStart',[p]);await touch('touchEnd');};
  const waypoint=()=>page.evaluate(()=>state.mobile_arm.cue.waypoint);
  const tapWaypoint=async p=>{
   const expected=await page.evaluate(p=>viewport.point(p.x,p.y),p);
   await tap(p);
   await page.waitForFunction(expected=>{const p=state.mobile_arm.cue.waypoint;return p&&Math.hypot(p.x-expected.x,p.y-expected.y)<.1;},expected);
   await page.waitForFunction(()=>!cueBusy);
   const shown=await page.evaluate(()=>({transform:$('cueWaypointBullseye').getAttribute('transform'),expected:`translate(${state.mobile_arm.cue.waypoint.x} ${state.mobile_arm.cue.waypoint.y}) scale(${1/viewport.scale})`}));
   assert.equal(shown.transform,shown.expected,'blue target uses world coordinates');
   assert.equal(await page.locator('#cueWaypointRow').isVisible(),true);
   assert.equal(await page.locator('#cueWaypointBullseye').isVisible(),true);
  };
  const initial=await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints));
  await tapWaypoint({x:300,y:160});
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>state.mobile_arm.cue.status),'idle');
  assert.equal(await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints)),initial,'inserting before Play does not move');
  await page.locator('#cuePlay').click();
  await page.waitForFunction(()=>state.mobile_arm.cue.status==='running');
  assert.equal(await page.locator('#cuePlay').textContent(),'Ⅱ');
  await page.locator('#cuePlay').click();await page.waitForFunction(()=>state.mobile_arm.cue.status==='paused');
  const paused=await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints));
  await page.locator('#cueMinimize').click();
  assert.equal(await page.locator('#cuePlay').textContent(),'▶');
  await tapWaypoint({x:340,y:230});
  assert.equal(await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints)),paused,'replacement keeps pause');
  const before=await waypoint();
  // A finger drag and a two-finger camera gesture must not insert a waypoint.
  await touch('touchStart',[{x:300,y:160}]);await touch('touchMove',[{x:340,y:180}]);await touch('touchEnd');
  await touch('touchStart',[{x:300,y:160},{x:440,y:210}]);
  await touch('touchMove',[{x:280,y:160},{x:470,y:225}]);await touch('touchEnd');
  assert.deepEqual(await waypoint(),before);
  assert.ok(await page.evaluate(()=>viewport.zoom)>1);
  await tapWaypoint({x:360,y:175});
  await page.screenshot({path:'/tmp/mobile-waypoint-paused.png'});
  await page.locator('#cueWaypointCancel').click();await page.waitForFunction(()=>!state.mobile_arm.cue.waypoint);
  assert.equal(await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints)),paused);
  await tapWaypoint({x:370,y:190});
  await page.locator('#cuePlay').click();await page.waitForFunction(()=>state.mobile_arm.cue.status==='running');
  assert.equal(await page.locator('#cuePlay').textContent(),'Ⅱ','compact view toggles to Pause');
  await page.waitForFunction(()=>!state.mobile_arm.cue.waypoint,null,{timeout:20000});
  await page.waitForFunction(()=>state.mobile_arm.cue.status==='completed',null,{timeout:30000});
  assert.ok(await page.evaluate(()=>state.towers.some(t=>t.atom_tag_id===100&&t.aruco_id===46)),'previously unreachable marker 46 receives the piece');
  await page.waitForFunction(()=>$('xyzBullseyes').dataset.aligned==='true');
  await tapWaypoint({x:350,y:185});await page.locator('#cueStop').click();
  await page.waitForFunction(()=>!state.mobile_arm.cue.waypoint);
  await page.evaluate(()=>{viewport.fit();syncViewport();});
  await page.locator('#cueMinimize').click();
  // Verify the extra waypoint row remains usable across phone layouts.
  for(const [width,height] of [[844,390],[390,844],[568,320],[320,568]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(150);
   // A tested server command sets the same waypoint even when drawer overlays the map.
   await page.evaluate(()=>cueAction('cue_waypoint',{point:{x:viewport.w*.3,y:viewport.h*.4}}));
   await page.waitForFunction(()=>!!state.mobile_arm.cue.waypoint);
   await page.screenshot({path:`/tmp/mobile-waypoint-${width}x${height}.png`});
   const bounds=await page.locator('#cueWaypointCancel').boundingBox(),panel=await page.locator('#cuePanel').boundingBox();
   assert.ok(bounds.x>=panel.x&&bounds.x+bounds.width<=panel.x+panel.width&&bounds.y>=panel.y&&bounds.y+bounds.height<=panel.y+panel.height,'waypoint cancel fits drawer');
   const cueRow=await page.locator('.cueRow').first().boundingBox(),list=await page.locator('#cueRows').boundingBox();
   assert.ok(cueRow.y+cueRow.height<=list.y+list.height+.1,'waypoint and current cue row are both visible');
   await page.locator('#cueWaypointCancel').click();await page.waitForFunction(()=>!state.mobile_arm.cue.waypoint);
  }
  await page.locator('#stop').click();
  assert.deepEqual(errors,[]);
  console.log('Waypoint passed: queued tap, real touch replacement, pause, drag/pinch exclusion, zoom coordinates, cancel, resume, marker 46 placement, Play/Pause toggle and four layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
