/* Isolated virtual game only; never point at the physical hub. */
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8134';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(root))throw Error('Use an isolated fixture.');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.request.post(root+'/__test/command',{data:{action:'reset'}});
   await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:3}});
   await page.goto(root+'/s/'+side+'/p/mobile-ltz/');
   await page.waitForFunction(()=>!!session&&controlMode==='targeting'&&view?.levelReady);
   await page.evaluate(async()=>{
    const point={x:viewport.w*(team==='green'?.32:.68),y:viewport.h*(team==='green'?.3:.7),z:state.mobile_arm.tip.z};
    await command('xyz',{xyz:point,control_revision:state.mobile_arm.control_revision});
   });
   await page.waitForFunction(()=>!$('xyzArmTrajectory').hasAttribute('hidden')&&$('xyzArmTrajectory').getTotalLength()>50);
   await page.waitForFunction(()=>{const p=displayedArmTip(),start=xyzPathProgress?.points?.[0];return start&&Math.hypot(p.x-start.x,p.y-start.y)>10;});
   const sample=await page.evaluate(()=>new Promise(resolve=>{
    const begin=performance.now(),red=new Set(),raw=new Set(),lengths=[];
    function frame(){
     red.add($('xyzActualBullseye').getAttribute('transform'));raw.add(JSON.stringify(state.mobile_arm.tip));
     lengths.push($('xyzArmTrajectory').getTotalLength());
     if(performance.now()-begin>=1100)resolve({red:red.size,raw:raw.size,first:lengths[0],last:lengths.at(-1),growth:Math.max(...lengths.slice(1).map((v,i)=>v-lengths[i]))});
     else requestAnimationFrame(frame);
    }frame();
   }));
   assert(sample.red>=25,JSON.stringify(sample));assert(sample.red>sample.raw*1.5,JSON.stringify(sample));
   assert(sample.last<sample.first);assert(sample.growth<.1,'Passed path must not regrow');
   assert.equal(await page.locator('#xyzArmTrajectory').evaluate(el=>getComputedStyle(el).strokeDasharray),'8px, 6px');
   await page.screenshot({path:'/tmp/arm-trajectory-'+side+'.png'});
   await page.waitForFunction(()=>$('xyzArmTrajectory').hasAttribute('hidden')&&$('xyzBullseyes').dataset.aligned==='true',{},{timeout:30000});
   // Render a physical-style source timeline in the isolated UI. No commands:
   // repeated publications and uneven arrivals must not restart easing.
   const speed=await page.evaluate(()=>new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(Error('Synthetic display check timed out')),8000);
    liveFeed.stop();gameState.apply=()=>{};joinWanted=false;session=null;
    const begin=performance.now(),stamp=Date.now()/1000;
    state={...state,virtual_play:false,mobile_arm:{...state.mobile_arm,session:'display-test',position_at:stamp,position_settled:false,tip:{x:0,y:100,z:60},motion_path:{id:'display-test',points:[{x:0,y:100,z:60},{x:500,y:100,z:60}]}}};
    const arm=state.mobile_arm;physicalArm.arm=()=>arm;physicalArm.tick=()=>{};
    xyzTarget={x:500,y:100,z:60};xyzMotionScope=null;drawXYZ();
    let index=0,previous=null,stoppedAt=null;const speeds=[],stoppedPositions=[];
    function frame(){
     const elapsed=performance.now()-begin;lastFeed=performance.now();feedReady=true;
     const next=(index+1)*100+[20,5,25,10,15][index%5];
     if(index<30&&elapsed>=next){index++;arm.position_at=stamp+index*.1;arm.tip.x=index*10;}
     if(elapsed>=3200&&stoppedAt===null){arm.position_at=stamp+3.2;arm.position_settled=true;stoppedAt=elapsed;}
     const transform=$('xyzActualBullseye').getAttribute('transform'),x=Number(transform.match(/translate\(([^ ]+)/)[1]),t=xyzMotion.frameAt;
     if(elapsed>600&&elapsed<2900&&previous&&x!==previous.x&&t>previous.t)speeds.push((x-previous.x)*1000/(t-previous.t));
     if(stoppedAt!==null&&elapsed-stoppedAt>=50)stoppedPositions.push(x);
     if(!previous||x!==previous.x)previous={x,t};
     if(elapsed>=3800){clearTimeout(timeout);resolve({frames:speeds.length,min:Math.min(...speeds),max:Math.max(...speeds),stoppedPositions});}
     else requestAnimationFrame(frame);
    }frame();
   }));
   assert(speed.frames>=50,JSON.stringify(speed));assert(speed.min>95&&speed.max<105,JSON.stringify(speed));
   assert(speed.stoppedPositions.length>=10);assert(speed.stoppedPositions.every(x=>x===300),'Confirmed stop must have no display tail or movement toward the goal at 500');
   assert.deepEqual(errors,[]);
   console.log('PASS '+side+': '+sample.red+' displayed positions / '+sample.raw+' feedback positions; dashed route erased; 100 ms jittered feedback speed '+speed.min.toFixed(2)+'–'+speed.max.toFixed(2)+' units/sec; confirmed stop has no display tail');
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
