/* Real UI against the isolated fixture, with delayed renderer/controller. No hardware. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8134';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(root))throw Error('Use an isolated loopback fixture, never the live hub.');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
   const errors=[],commands=[];page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/cartesian-xyz-test/'))commands.push(r.url());});
   await page.request.post(root+'/__test/camera',{data:{enabled:true}});
   const initial=await (await page.request.get(root+'/s/gamemaster/p/mobile-ltz-api/api/state?side='+side)).json();
   const piece=side==='green'?100:102;
   function snapshot(){
    const now=Date.now()/1000;
    return {...initial,virtual_play:false,virtual_test_control:4,server_time:now,mobile_arm:null,
     movable_piece_codes:{green:[100,101],purple:[102,103]},
     mobile_camera:{...initial.mobile_camera,tracking:{contract:'photon.board.camera-markers',version:1,status:'ready',source:'camera',
      coordinate_space:'corrected-camera-normalized',server_time:now,frame_at:now,max_age_s:1.5,
      tags:[{id:40,camera:[.2,.3],last_seen:now},{id:piece,camera:[.4,.6],last_seen:now}]}},
     mobile_cue_targets:{contract:'photon.board.cue-targets',version:1,status:'ready',source:'camera',
      coordinate_space:'corrected-camera-normalized',server_time:now,frame_at:now,tags:[
       {id:40,nx:.2,ny:.3,last_seen:now,fixed:true,visible:true},
       {id:piece,nx:.4,ny:.6,last_seen:now,fixed:false,visible:true}]}};
   }
   let finishRenderer,finishController,finishStream,rendererRequested=false,controllerRequested=false;
   const rendererGate=new Promise(r=>finishRenderer=r),controllerGate=new Promise(r=>finishController=r),streamGate=new Promise(r=>finishStream=r);
   await page.route('**/p/mobile-ltz-api/api/state*',r=>r.fulfill({json:snapshot()}));
   await page.route('**/p/mobile-ltz-api/api/events*',async r=>{await streamGate;await r.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify(snapshot())+'\n\n'});});
   await page.route('**/p/mobile-ltz-api/api/renderer.js*',async r=>{rendererRequested=true;await rendererGate;await r.continue();});
   await page.route('**/p/mobile-ltz/api/physical-controller',async r=>{controllerRequested=true;await controllerGate;await r.fulfill({status:503,json:{error:'Fixture arm disconnected'}});});
   try{
    await page.goto(root+'/s/'+side+'/p/mobile-ltz/',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelectorAll('#markerLabels .markerNumber').length===2);
    assert(rendererRequested);assert(controllerRequested);
    assert(await page.locator('#markerLabels .markerNumber').first().isVisible());
    assert.deepEqual(await page.locator('#markerLabels .markerNumber').allTextContents(),['#40','#'+piece]);
    assert.deepEqual(await page.evaluate(()=>({rendererReady:!!view,arm:state.mobile_arm,motionAvailable:available()})),
     {rendererReady:false,arm:null,motionAvailable:false});
    // The feed is deliberately held: no old movable or fixed label may linger.
    await page.waitForFunction(()=>document.querySelectorAll('#markerLabels .markerNumber').length===0);
    finishStream();
    await page.waitForFunction(()=>document.querySelectorAll('#markerLabels .markerNumber').length===2);
    finishRenderer();
    await page.waitForFunction(()=>!!view);
    assert.equal(await page.evaluate(()=>available()),false);
    const held=snapshot();held.mobile_cue_targets={...held.mobile_cue_targets,status:'unavailable',tags:[],error:'Checking fixed marker #49'};
    held.mobile_camera.status='unavailable';held.mobile_camera.error='Not enough markers for alignment';
    await page.evaluate(value=>applyState(value),held);
    assert.deepEqual(await page.locator('#markerLabels .markerNumber').allTextContents(),['#40','#'+piece]);
    assert.equal(await page.evaluate(()=>available()),false);
    assert.equal(await page.evaluate(()=>state.mobile_cue_targets.status),'unavailable');
    await page.screenshot({path:'/tmp/tracking-startup-'+side+'.png'});
    assert.deepEqual(errors,[]);assert.deepEqual(commands,[]);
    console.log('PASS '+side+': tracking before renderer/controller, survives cue-map/alignment holds, stale expiry, recovery, no motion');
   }finally{finishRenderer();finishController();finishStream();await page.close();}
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
