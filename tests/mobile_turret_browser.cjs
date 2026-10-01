const assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8127';
const team=process.env.MOBILE_TEST_TEAM==='purple'?'purple':'green',piece=team==='purple'?102:100;
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});try{
 const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});const errors=[],commands=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/api/command'))commands.push(r.postDataJSON());});
 await page.request.post(root+'/__test/camera',{data:{enabled:false,stale:false}});
 await page.request.post(root+'/__test/command',{data:{action:'reset'}});
 await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}});
 await page.goto(root+`/s/${team}/p/mobile-ltz/`);await page.waitForFunction(()=>state?.status==='ready'&&view?.levelReady&&controlMode==='cue');
 const socket=await page.evaluate(()=>state.level.sockets.find(s=>s.aruco_id===44).socket_id);
 await page.request.post(root+'/__test/command',{data:{action:'place',atom_tag_id:piece,socket_id:socket,team}});
 await page.waitForFunction(()=>turretOverlay.selected&&document.querySelector('[data-aim-handle=aim]'));
 assert.equal(await page.locator('[data-aim-handle]').count(),1,'one combined square');
 const cdp=await page.context().newCDPSession(page);
 const touch=(type,points=[])=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map((p,i)=>({x:p.x,y:p.y,id:i+1,radiusX:5,radiusY:5,force:1}))});
 const tower=()=>page.evaluate(()=>state.towers.find(t=>t.socket_id===turretOverlay.selected));
 const drag=async(kind,dx,dy)=>{
  const revision=(await tower()).aim_revision,el=page.locator(`[data-aim-handle=${kind}]`),b=await el.boundingBox(),p={x:b.x+b.width/2,y:b.y+b.height/2};
  await touch('touchStart',[p]);assert.equal(await page.evaluate(()=>turretOverlay.drag?.kind),kind);
  await touch('touchMove',[{x:p.x+dx,y:p.y+dy}]);await touch('touchEnd');
  await page.waitForFunction(rev=>!turretOverlay.saving&&turretOverlay.tower()?.aim_revision>rev,revision);
 };
 let before=await tower();await drag('aim',0,-45);let after=await tower();
 assert.notEqual(after.targeting.angle_degrees,before.targeting.angle_degrees);assert.notEqual(after.targeting.spread,before.targeting.spread,'one diagonal drag changes both direction and range');
 before=after;const angle=before.targeting.angle_degrees*Math.PI/180,direction=await page.evaluate(()=>viewport.direction);
 await drag('aim',20*Math.cos(angle)*direction,20*Math.sin(angle)*direction);after=await tower();assert.notEqual(after.targeting.spread,before.targeting.spread);
 assert.ok(Math.abs(after.targeting.angle_degrees-before.targeting.angle_degrees)<.001,'radial drag preserves direction');
 assert.equal(commands.filter(c=>['xyz','cue_waypoint','joints'].includes(c?.action)).length,0,'turret drag never moves arm or inserts waypoint');
 await page.screenshot({path:'/tmp/mobile-turret-virtual.png'});
 await page.getByRole('button',{name:'Close turret targeting'}).click();assert.equal(await page.locator('#turretOverlay').isVisible(),false);
 const p=await page.evaluate(()=>turretOverlay.point(state.towers[0]));await touch('touchStart',[p]);await touch('touchEnd');
 await page.waitForFunction(()=>turretOverlay.selected);assert.equal((await tower()).aim_revision,after.aim_revision);
 assert.equal(commands.filter(c=>c?.action==='cue_waypoint').length,0,'turret and close touches do not add cue waypoints');
 // Switch to real physical-mode rules with a deterministic synthetic camera source.
 await page.request.post(root+'/__test/camera',{data:{enabled:true,stale:false}});
 await page.waitForFunction(()=>!state.virtual_play&&turretOverlay.cameraReady());
 assert.equal(await page.locator('#playfieldVideo').isVisible(),true);
 assert.equal(await page.evaluate(()=>!!session),false,'aiming works without arm session');
 await drag('aim',20,-25);
 const aligned=await page.evaluate(()=>{const t=turretOverlay.tower(),p=turretOverlay.point(t),v=viewport;return {x:p.x,y:p.y,expectedX:v.vw/2+v.direction*((.1+.8*t.x/state.level.width)*v.w-v.cx)*v.scale,expectedY:v.vh/2+v.direction*((.05+.9*t.y/state.level.height)*v.h-v.cy)*v.scale};});
 assert.ok(Math.abs(aligned.x-aligned.expectedX)<.1&&Math.abs(aligned.y-aligned.expectedY)<.1,'overlay registered to camera');
 await page.screenshot({path:'/tmp/mobile-turret-video.png'});
 for(const [width,height] of [[390,844],[568,320],[320,568]]){
  await page.setViewportSize({width,height});await page.waitForTimeout(250);
  await page.waitForFunction(()=>turretOverlay.ready()&&document.querySelector('[data-aim-handle=aim]'));
  assert.deepEqual(errors,[]);
  assert.equal(await page.locator('[data-aim-handle]').count(),1,'one combined square');
  // Read visibility and geometry together: a camera freshness transition may
  // remove the handle between separate automation calls.
  const boxes=await page.waitForFunction(()=>{
   const nodes=[...document.querySelectorAll('[data-aim-handle]')];if(!turretOverlay.ready()||nodes.length!==1)return false;
   return nodes.map(el=>{const b=el.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};});
  }).then(handle=>handle.jsonValue());
  for(const b of boxes)assert.ok(b.x>=0&&b.y>=0&&b.x+b.width<=width+.1&&b.y+b.height<=height+.1);
  await page.screenshot({path:`/tmp/mobile-turret-video-${width}x${height}.png`});
 }
 await page.request.post(root+'/__test/camera',{data:{enabled:true,stale:true}});
 await page.waitForFunction(()=>state.mobile_camera?.status==='unavailable');
 assert.equal(await page.locator('[data-aim-handle]').count(),0);
 assert.equal(await page.locator('#turretAimStatus').count(),0);
 assert.match(await page.locator('#feedback').textContent(),/Tracking unavailable/);
 await page.request.post(root+'/__test/camera',{data:{enabled:true,stale:false}});
 await page.waitForFunction(()=>turretOverlay.cameraReady()&&document.querySelector('[data-aim-handle]'));
 await page.reload();await page.waitForFunction(()=>turretOverlay.selected&&turretOverlay.cameraReady());
 assert.ok((await tower()).aim_revision>=3,'aim survives reconnect');
 await page.request.post(root+'/__test/camera',{data:{enabled:false,stale:false}});
 assert.deepEqual(errors,[]);console.log('Turret overlay: automatic selection, direction/range drag, reopen, gesture isolation, physical aim, camera registration, four layouts, stale tracking and reconnect passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
