/* Real mobile UI, bridge and planner; isolated fixture + fake arm. No hardware. */
const assert=require('node:assert/strict'),{chromium,webkit}=require('playwright');
const root=process.env.MOBILE_RELOCK_TEST_URL||'http://127.0.0.1:8138';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(root))throw Error('Use an isolated loopback fixture, never the live hub.');
(async()=>{
 const useWebKit=process.env.MOBILE_TEST_BROWSER==='webkit';
 const browser=await (useWebKit?webkit:chromium).launch({headless:true,...(useWebKit?{}:{executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})});
 try{
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true,deviceScaleFactor:3});
   const errors=[],commands=[];page.on('pageerror',error=>errors.push(error.message));
   await page.request.post(root+'/__test/saved-calibrations');
   await page.request.post(root+'/__test/camera',{data:{enabled:true,width:3840,height:2160}});
   const initial=await (await page.request.get(root+'/s/gamemaster/p/mobile-ltz-api/api/state?side='+side)).json();
   let calibration=true,connections=0,gameLagMs=0;
   const robot={connected:false,enabled:true,robot_mode:5,motion_epoch:0,motion_ready:true,
    control_session:null,pose:[310,0,60,0],joints:[0,20,30,0],target:null,control_mode:'cartesian'};
   const snapshot=()=>({...initial,server_time:(Date.now()-gameLagMs)/1000,status:'ready',phase:'setup',paused:false,
    virtual_play:false,virtual_test_control:4,mobile_safety:{status:'ready'},
    journey:{phase:calibration?'calibration':'playing',calibration_side:calibration?side:null,active_side:calibration?side:null,session_id:'fixture-lesson'},
    mobile_calibration:calibration?{stage:'points',captures:{},draft:{points:{},parallax_points:{}},arrivals:[]}:null,mobile_calibration_connect:calibration,mobile_calibration_ready:calibration});
   // Keep fake game telemetry fresh in both real frames. A finite intercepted
   // SSE response would immediately fire onerror and invalidate the controller.
   await page.exposeFunction('relockSnapshot',snapshot);
   await page.addInitScript(()=>{
    const NativeEventSource=window.EventSource;
    window.EventSource=class extends EventTarget{
     constructor(url,options){
      super();
      if(!String(url).includes('/mobile-ltz-api/api/events'))return new NativeEventSource(url,options);
      this.readyState=1;
      this.timer=setInterval(async()=>{
       const data=await window.relockSnapshot();
       if(this.readyState!==1)return;
       const event=new MessageEvent('message',{data:JSON.stringify(data)});
       this.onmessage?.(event);this.dispatchEvent(event);
      },150);
     }
     close(){this.readyState=2;clearInterval(this.timer);}
    };
   });
   await page.route('**/p/mobile-ltz-api/api/state*',route=>route.fulfill({json:snapshot()}));
   await page.route('**/cartesian-xyz-test/api/**',async route=>{
    const action=new URL(route.request().url()).pathname.split('/').at(-1);
    if(action==='config')return route.continue();
    const data=route.request().postDataJSON();
    if(data){
     commands.push({action,data});
     if(action==='connect'){robot.connected=true;robot.control_session=side+':'+(++connections);robot.motion_epoch++;robot.target=null;}
     if(action==='disconnect'){robot.connected=false;robot.target=null;}
     if(action==='move'){robot.pose=['x','y','z','r'].map(k=>data[k]);robot.target=[...robot.pose];}
     if(action==='joint-move'){robot.joints=['j1','j2','j3','j4'].map(k=>data[k]);robot.target=[...robot.joints];}
     if(action==='stop')robot.target=null;
    }
    const observedAt=Date.now()/1000;
    return route.fulfill({json:{ok:true,...robot,feedback_ok:robot.connected,last_feedback:observedAt,feedback_observed_at:observedAt,pump_mode:'off'}});
   });
   try{
    await page.goto(root+`/s/${side}/p/mobile-ltz/`);
    await page.waitForFunction(()=>feedReady&&!document.getElementById('connect').disabled);
    const bridge=page.frames().find(frame=>frame.url().includes('/p/ltx/'));
    await bridge.waitForFunction(()=>mobileConnectionReady());
    await page.locator('#connect').click();
    await page.waitForFunction(()=>session&&available()&&controlMode==='xyz');
    const before=commands.filter(c=>['move','joint-move'].includes(c.action)).length;
    const priorSession=await page.evaluate(()=>session);
    gameLagMs=800;
    await page.waitForFunction(()=>physicalArm.value?.diagnostics?.feedback_game_delta_ms < -700);
    const priorFeedback=await page.evaluate(()=>physicalArm.value.arm.position_at);
    await page.waitForFunction(stamp=>physicalArm.value?.arm?.position_at>stamp+.6,priorFeedback);
    assert.equal(await page.evaluate(()=>session),priorSession,'Delayed game projection cannot invalidate fresh robot feedback');
    gameLagMs=0;
    // A physical unlock invalidates all old gestures before the arm is moved.
    robot.robot_mode=6;robot.motion_ready=false;robot.motion_epoch++;
    await page.waitForFunction(()=>!session&&!available());
    assert.equal(await page.locator('#xyzZIncrease').isDisabled(),true);
    robot.pose=[320,10,65,0];robot.joints=[-10,25,35,0];robot.robot_mode=5;robot.motion_ready=true;
    // Run the clock/unlock regression without the legacy cue-transition fixture.
    if(process.env.MOBILE_CLOCK_TEST_ONLY==='1'){
     await page.locator('#connect').click();
     await page.waitForFunction(()=>session&&available()&&controlMode==='xyz',null,{timeout:12000});
     assert.notEqual(await page.evaluate(()=>session),priorSession);
     assert.equal(commands.filter(c=>['move','joint-move'].includes(c.action)).length,before,'Reconnect cannot replay an old movement');
     assert.deepEqual(errors,[]);
     console.log('PASS '+side+': 800 ms Game delay preserves the session; unlock revokes it; reconnect synchronizes without motion');
     continue;
    }
    calibration=false;
    await page.waitForFunction(()=>state.journey.phase==='playing'&&controlMode==='cue');
    await page.locator('#connect').click();
    await page.waitForFunction(()=>session&&available()&&state.mobile_arm.control_mode==='cue',null,{timeout:12000});
    await page.waitForFunction(()=>document.getElementById('xyzBullseyes').dataset.aligned==='true');
    const guides=await page.locator('#xyzBullseyes .xyzGuides').evaluateAll(nodes=>nodes.map(node=>({
     id:node.id,filter:getComputedStyle(node).filter,width:node.getBoundingClientRect().width,height:node.getBoundingClientRect().height})));
    assert(guides.every(g=>g.filter==='none'),'Connecting at the measured pose must not add full-camera SVG filter surfaces: '+JSON.stringify(guides));
    assert.equal(await page.evaluate(()=>viewport.w),3840,'Connected-arm rendering preserves source camera coordinates');
    assert.notEqual(await page.evaluate(()=>session),priorSession);
    assert.equal(commands.filter(c=>['move','joint-move'].includes(c.action)).length,before,'Relock/Connect must not replay an old movement');
    assert.equal(await page.evaluate(()=>xyzTarget.z),65,'The reconnected controls follow the manually moved pose');
    // A fresh deliberate height command runs through the actual bridge/planner.
    await page.locator('#xyzZIncrease').click();
    await page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight&&state.mobile_arm.tip.z===66);
    assert.equal(robot.pose[2],66);assert.deepEqual(robot.pose.slice(0,2),[320,10]);
    // Repeat the cycle in normal play, independently of lesson transitions.
    robot.robot_mode=6;robot.motion_ready=false;robot.motion_epoch++;
    await page.waitForFunction(()=>!session&&!available());
    robot.pose=[315,5,62,0];robot.robot_mode=5;robot.motion_ready=true;
    const secondBefore=commands.filter(c=>c.action==='move').length;
    await page.locator('#connect').click();await page.waitForFunction(()=>session&&available());
    assert.equal(commands.filter(c=>c.action==='move').length,secondBefore);
    await page.locator('#xyzZIncrease').click();
    await page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight&&state.mobile_arm.tip.z===63);
    assert.equal(robot.pose[2],63);assert.deepEqual(robot.pose.slice(0,2),[315,5]);
    assert.deepEqual(errors,[]);
    console.log('PASS '+side+': calibration → unlock → relocate → relock → Connect → fresh movement, repeated without stale target replay');
   }catch(error){
    console.error(await page.evaluate(()=>({session:!!session,mode:controlMode,awaitingControlMode,available:available(),feedback:document.getElementById('feedback').textContent,bridge:physicalArm.value?.arm})));
    throw error;
   }finally{await page.close();}
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
