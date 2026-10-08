// Native phone slider gestures against the temporary virtual fixture; no hardware.
// Start: python tests/mobile_ltz_fixture.py --port 8117
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],verified=[];
 try{
  for(const team of ['green','purple']){
   const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true}),moves=[];
   page.on('pageerror',e=>errors.push(team+': '+e.message));
   page.on('request',r=>{if(r.url().includes('/api/command')){const data=r.postDataJSON();if(data?.action==='xyz')moves.push(data);}});
   await page.request.post(origin+'/__test/command',{data:{action:'reset'}});
   await page.request.post(origin+'/__test/camera',{data:{enabled:false}});
   await page.request.post(origin+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:2}});
   await page.goto(origin+`/s/${team}/p/mobile-ltz/`);
   await page.waitForFunction(()=>controlMode==='xyz'&&manualAvailable());
   const initialRotation=team==='purple'?180:0,token=await page.evaluate(()=>session);
   assert.equal(await page.evaluate(()=>viewport.rotation),initialRotation);
   const settled=()=>page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight&&['x','y','z'].every(k=>Math.abs(state.mobile_arm.tip[k]-xyzTarget[k])<.2));
   const cdp=await page.context().newCDPSession(page);
   const touch=(type,p)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:p?[{x:p.x,y:p.y,id:1,radiusX:4,radiusY:4,force:1}]:[]});
   for(const rotation of [initialRotation,180-initialRotation]){
    if(await page.evaluate(()=>viewport.rotation)!==rotation){
     const before=await page.evaluate(()=>({...xyzTarget})),count=moves.length;
     await page.locator('#rotateView').click();await settled();
     assert.deepEqual(await page.evaluate(()=>({...xyzTarget})),before,'Rotation preserves the canonical target');
     assert.equal(moves.length,count,'Rotation itself sends no movement');
    }
    for(const fine of [false,true]){
     if(await page.evaluate(()=>xyzFine)!==fine)await page.locator('#xyzPrecision').click();
     for(const axis of ['x','y'])for(const direction of [-1,1]){
      await settled();
      const before=await page.evaluate(()=>({target:{...xyzTarget},screen:viewport.screen(xyzTarget.x,xyzTarget.y)}));
      const thumb=await page.locator('#xyz'+axis.toUpperCase()).evaluate((el,axis)=>{
       const r=el.getBoundingClientRect(),f=(Number(el.value)-Number(el.min))/(Number(el.max)-Number(el.min));
       return axis==='x'?{x:r.x+12+f*(r.width-24),y:r.y+r.height/2}:{x:r.x+r.width/2,y:r.y+12+f*(r.height-24)};
      },axis);
      await touch('touchStart',thumb);
      // Native range inputs wait for the platform's touch-drag slop.
      await touch('touchMove',{...thumb,[axis]:thumb[axis]+direction*20});
      await touch('touchEnd');await settled();
      const after=await page.evaluate(()=>({target:{...xyzTarget},tip:{...state.mobile_arm.tip},screen:viewport.screen(xyzTarget.x,xyzTarget.y),actual:viewport.screen(state.mobile_arm.tip.x,state.mobile_arm.tip.y)}));
      assert((after.screen[axis]-before.screen[axis])*direction>0,JSON.stringify({team,rotation,fine,axis,direction,before,after}));
      assert((after.actual[axis]-before.screen[axis])*direction>0,'Confirmed movement follows the finger on screen');
      const other=axis==='x'?'y':'x';
      assert(Math.abs(after.target[other]-before.target[other])<.001,'One slider does not change the other axis');
      assert(Math.abs(after.target.z-before.target.z)<.001,'XY does not change height');
      assert.equal(await page.evaluate(()=>session),token,'Movement preserves the connection');
      const count=moves.length;
      // Let the presentation-only actual indicator settle onto measured feedback.
      await page.waitForFunction(axis=>{const m=$('xyzActualBullseye').transform.baseVal.consolidate()?.matrix;return m&&Math.abs(m[axis==='x'?'e':'f']-state.mobile_arm.tip[axis])<.05;},axis);
      const display=await page.locator('#xyz'+axis.toUpperCase()).evaluate((el,axis)=>{
       const marker=document.getElementById(el.id+'Actual').getBoundingClientRect(),r=el.getBoundingClientRect();
       const f=(Number(el.value)-Number(el.min))/(Number(el.max)-Number(el.min));
       return {value:Number(el.value),text:document.getElementById(el.id+'Value').textContent,fill:parseFloat(el.style.getPropertyValue('--fill')),
        marker:axis==='x'?marker.x+marker.width/2:marker.y+marker.height/2,
        thumb:axis==='x'?r.x+12+f*(r.width-24):r.y+12+f*(r.height-24),fraction:f};
      },axis);
      assert(Math.abs(display.value-after.target[axis]*(rotation===180?-1:1))<.11,'Slider presents the current orientation');
      assert.equal(display.text,after.target[axis].toFixed(fine?1:0),'Readout retains map coordinates');
      assert(Math.abs(display.fill-display.fraction*100)<.02,'Fill follows the thumb');
      assert(Math.abs(display.marker-display.thumb)<1,'Measured indicator follows the same direction as the thumb: '+JSON.stringify({team,rotation,fine,axis,direction,display}));
      assert.equal(moves.length,count,'Rendering feedback cannot command movement');
     }
     const z=await page.evaluate(()=>xyzTarget.z);
     await page.locator('#xyzZIncrease').click();await settled();
     assert(Math.abs(await page.evaluate(()=>xyzTarget.z)-z-(fine?.1:1))<.001,'Height direction is independent of rotation');
     verified.push(`${team} ${rotation}° ${fine?'fine':'normal'} native X/Y touch and height`);
    }
    await page.locator('#xyzPrecision').click();
   }
   await page.screenshot({path:`/tmp/xyz-direction-${team}.png`});
   await page.locator('#stop').click();await page.close();
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({verified,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
