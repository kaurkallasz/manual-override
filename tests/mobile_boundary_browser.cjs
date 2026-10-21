// End-to-end mobile recovery with the real calibrated planner and fake robots.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117';
const points=[[.1,.2,150,-250],[.5,.15,280,-270],[.9,.2,410,-100],[.9,.8,410,100],[.5,.85,280,270],[.1,.8,150,250]];
const arm={points:Object.fromEntries(points.map(([u,v,x,y],i)=>['p'+(i+1),{camera:{u,v},pose:{x,y,z:60,r:9,set:true}}]))};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}),errors=[],verified=[];
 try{
  const setup=await browser.newPage();
  await setup.request.post(origin+'/__test/command',{data:{action:'reset'}});
  await setup.request.post(origin+'/__test/camera',{data:{enabled:true}});
  for(const team of ['green','purple']){
   await setup.request.post(origin+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:2}});
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true}),moves=[];
   const robot={pose:[225,0,60,9],target:[225,0,60,9],joints:[0,20,30,9],control_mode:'cartesian'};
   page.on('pageerror',e=>errors.push(team+': '+e.message));
   await page.route('**/auto-pickup-game/api/calibration2',route=>route.fulfill({json:{ok:true,calibration:{enabled:true,arms:{green:arm,purple:arm},shared_z:{transport_height:80},radius_min:220,radius_max:440}}}));
   let failure=null;
   await page.route('**/cartesian-xyz-test/api/**',route=>{
    const action=new URL(route.request().url()).pathname.split('/').at(-1);
    if(action==='config')return route.continue();
    const data=route.request().postDataJSON();
    if(action==='move'&&data){
     if(failure){const error=failure;failure=null;return route.fulfill({json:{ok:false,error}});}
     moves.push({start:robot.pose.slice(0,3),target:[data.x,data.y,data.z]});
     robot.pose=[data.x,data.y,data.z,9];robot.target=[...robot.pose];
    }
    if(action==='stop')robot.target=[...robot.pose];
    const observedAt=Date.now()/1000;
    return route.fulfill({json:{ok:true,connected:true,enabled:true,feedback_ok:true,last_feedback:observedAt,feedback_observed_at:observedAt,pump_mode:'off',...robot}});
   });
   await page.goto(origin+`/s/${team}/p/mobile-ltz/`);
   await page.waitForFunction(()=>physicalArm.arm()&&feedReady&&controlMode==='xyz').catch(async error=>{
    console.error(await page.evaluate(()=>({mode:controlMode,feedReady,physicalStatus:physicalArm.value?.status,error:physicalArm.error,game:state?.status,feedback:document.getElementById('feedback').textContent})));
    console.error(errors);throw error;
   });
   await page.locator('#connect').click();await page.waitForFunction(()=>!!session&&available());
   const frame=page.frames().find(f=>f.url().includes('/p/ltx/'));
   let token=await page.evaluate(()=>session);
   async function send(x,y,z=60){
    const camera=await frame.evaluate(p=>{const samples=cal2CalibrationSamples(),n=cal2CameraForRobotPose(samples,p),expected=cal2RawPose(samples,n.u,n.v);return {...(gid('flipToggle').checked?{u:1-n.u,v:1-n.v}:n),z:p.z,expected};},{x,y,z});
    await page.evaluate(({u,v,z})=>{xyzTarget={x:u*viewport.w,y:v*viewport.h,z};pendingXYZTarget=null;pendingXYZ=true;xyzEdit++;},camera);
    await page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight);
    return camera.expected;
   }
   await send(210,0);assert.equal(await page.evaluate(()=>session),token);assert.equal(moves.length,0,'Unsafe target sends no motion');
   robot.pose=[219,0,60,9];robot.target=[...robot.pose];
   await frame.waitForFunction(()=>playerJointStatus?.pose?.[0]===219);
   await send(225,0);assert.equal(await page.evaluate(()=>session),token);assert(Math.abs(robot.pose[0]-225)<.1,'Can retreat from a measured inner-boundary stop');
   await page.locator('#stop').click();await page.waitForFunction(()=>!session);
   robot.pose=[219,0,60,9];robot.target=[...robot.pose];
   await page.locator('#connect').click();await page.waitForFunction(()=>session&&available());token=await page.evaluate(()=>session);
   await send(225,0);assert(Math.abs(robot.pose[0]-225)<.1,'XYZ reconnect also permits a checked retreat');
   failure='joint target TCP is outside the Auto PP Cal 2 arm boundary';
   await send(250,0);assert.equal(await page.evaluate(()=>session),token,'Relay boundary rejection preserves the mobile session');
   await send(250,0);assert(Math.abs(robot.pose[0]-250)<.1);
   await setup.request.post(origin+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:3}});
   await page.waitForFunction(()=>controlMode==='targeting'&&available());
   robot.pose=[160,-240,60,9];robot.target=[...robot.pose];
   await frame.waitForFunction(()=>playerJointStatus?.pose?.[0]===160);
   const count=moves.length,expected=await send(160,240),route=moves.slice(count);
   assert(route.length>2,'Targeting automatically follows a multi-waypoint detour');
   for(const segment of route)assert(await frame.evaluate(({start,target})=>cal2DirectPathHasClearance({x:start[0],y:start[1],z:start[2]},{x:target[0],y:target[1],z:target[2]}),segment),'Every executed segment stays outside the inner exclusion');
   assert.equal(await page.evaluate(()=>session),token);assert(Math.hypot(robot.pose[0]-expected.x,robot.pose[1]-expected.y)<.01,'Detour reaches the calibrated camera target');
   failure='Robot feedback unavailable';await send(170,240);await page.waitForFunction(()=>!session);
   verified.push(team+' boundary hold, retreat, XYZ reconnect, relay rejection, targeting detour, fatal fault');
   await page.close();
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({verified,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
