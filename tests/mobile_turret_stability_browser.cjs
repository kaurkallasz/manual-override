/* Sustained native touch gestures through marker misses; isolated camera only. */
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8146';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(root))throw Error('Isolated fixture required');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const team of ['green','purple']){
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true}),errors=[],commands=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(r.url().includes('/api/command')&&r.method()==='POST')commands.push(r.postDataJSON());});
   await page.addInitScript(()=>{localStorage.setItem('mobile-ltz:stopped','yes');localStorage.setItem('mobile-ltz:purple:stopped','yes');});
   await page.request.post(root+'/__test/camera',{data:{enabled:false,stale:false,hidden_markers:[]}});
   await page.request.post(root+'/__test/command',{data:{action:'reset'}});
   await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}});
   await page.goto(root+`/s/${team}/p/mobile-ltz/`);
   await page.waitForFunction(()=>state?.status==='ready'&&view?.levelReady);
   const socket=await page.evaluate(()=>state.level.sockets.find(s=>s.aruco_id===44).socket_id);
   await page.request.post(root+'/__test/command',{data:{action:'place',atom_tag_id:team==='green'?100:102,socket_id:socket,team}});
   await page.request.post(root+'/__test/camera',{data:{enabled:true}});
   await page.waitForFunction(()=>!state.virtual_play&&turretOverlay.selected&&turretOverlay.ready()&&document.querySelector('[data-aim-handle]'));
   const sourceDimensions=await page.evaluate(()=>[viewport.w,viewport.h]);
   const jpeg=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=3840;c.height=2160;const p=c.getContext('2d');p.fillStyle='#183c29';p.fillRect(0,0,c.width,c.height);return c.toDataURL('image/jpeg').split(',')[1];});
   await page.route('**/assets/mobile-camera.jpg*',r=>r.fulfill({contentType:'image/jpeg',body:Buffer.from(jpeg,'base64')}));
   await page.waitForFunction(()=>turretOverlay.image.width===1920&&turretOverlay.image.height===1080);
   assert.deepEqual(await page.evaluate(()=>[viewport.w,viewport.h]),sourceDimensions,'preview raster size never changes calibrated coordinates');
   // The oversized image above checks coordinate isolation. Return to the
   // fixture preview before timing sub-second camera gaps and touch gestures.
   await page.unroute('**/assets/mobile-camera.jpg*');
   await page.waitForFunction(()=>turretOverlay.image.width===1280&&turretOverlay.image.height===720);
   const cdp=await page.context().newCDPSession(page);
   const touch=(type,points=[])=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map((p,i)=>({x:p.x,y:p.y,id:i+1,radiusX:5,radiusY:5,force:1}))});
   const begin=async()=>{
    const b=await page.locator('[data-aim-handle=aim]').boundingBox(),p={x:b.x+b.width/2,y:b.y+b.height/2};
    await touch('touchStart',[p]);assert.equal(await page.evaluate(()=>turretOverlay.drag?.kind),'aim');return p;
   };
   const drop=async()=>{
    const ids=await page.evaluate(()=>state.level.sockets.map(s=>s.aruco_id));
    await page.request.post(root+'/__test/camera',{data:{hidden_markers:ids}});
    await page.waitForFunction(()=>state.mobile_camera.status==='unavailable');
   };
   const restore=async()=>{
    await page.request.post(root+'/__test/camera',{data:{hidden_markers:[]}});
    await page.waitForFunction(()=>turretOverlay.ready());
   };
   const revision=()=>page.evaluate(()=>turretOverlay.tower().aim_revision);
   await page.evaluate(()=>{window.aimHandle=document.querySelector('[data-aim-handle]');window.cone=document.querySelector('.aimArea');window.replacements=0;new MutationObserver(records=>{replacements+=records.filter(r=>r.type==='childList').length;}).observe(turretOverlay.svg,{childList:true});});
   await page.waitForTimeout(600);
   assert.deepEqual(await page.evaluate(()=>({same:aimHandle===document.querySelector('[data-aim-handle]'),replacements})),{same:true,replacements:0},'camera packets keep the same cone and handle nodes');
   let rev=await revision(),p=await begin();
   await touch('touchMove',[{x:p.x+14,y:p.y-18}]);
   await drop();
   assert.equal(await page.evaluate(()=>turretOverlay.drag?.kind),'aim','brief registration loss preserves the gesture');
   assert(await page.locator('.aimArea').isVisible(),'cone remains visible through a brief miss');
   await touch('touchMove',[{x:p.x+30,y:p.y-35}]);
   await restore();await touch('touchEnd');
   await page.waitForFunction(rev=>!turretOverlay.saving&&turretOverlay.tower().aim_revision>rev,rev);
   // Release during the gap: keep the draft, but send nothing before fresh registration.
   rev=await revision();p=await begin();await touch('touchMove',[{x:p.x-20,y:p.y+12}]);
   await drop();const count=commands.filter(c=>c.action==='turret_aim').length;
   await touch('touchEnd');
   assert.equal(await page.evaluate(()=>turretOverlay.saving),true);
   assert.equal(commands.filter(c=>c.action==='turret_aim').length,count);
   await restore();await page.waitForFunction(rev=>!turretOverlay.saving&&turretOverlay.tower().aim_revision>rev,rev);
   // Prolonged rejection invalidates the draft; recovery must never replay it.
   p=await begin();await touch('touchMove',[{x:p.x+25,y:p.y-20}]);
   await drop();rev=await revision();await touch('touchEnd');
   await page.waitForFunction(()=>!turretOverlay.saving&&turretOverlay.drag===null);
   await restore();await page.waitForTimeout(200);
   assert.equal(await revision(),rev);
   assert.equal(await page.evaluate(()=>turretOverlay.draft),null);
   assert.equal(await page.evaluate(()=>window.aimHandle===document.querySelector('[data-aim-handle]')),true);
   assert.equal(commands.filter(c=>['xyz','joints','cue_waypoint'].includes(c.action)).length,0);
   assert.deepEqual(errors,[]);
   await page.screenshot({path:`/tmp/turret-stable-${team}.png`});await page.close();
  }
  console.log('Both teams: stable SVG nodes, touch drag across marker gaps, delayed save only after fresh alignment, expiry without replay, no arm commands.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
