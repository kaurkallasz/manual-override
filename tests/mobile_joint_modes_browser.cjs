// Legacy entry point, now verifies the slider controls and read-only joint illustration against the isolated fixture.
// Run with NODE_PATH pointing to Playwright, after tests/mobile_ltz_fixture.py is started.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
 await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
 const errors=[],moves=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/api/command')&&r.postDataJSON()?.action==='joints')moves.push(r.postDataJSON().joints);});
 await page.goto((process.env.MOBILE_TEST_URL||'http://127.0.0.1:8117')+'/s/green/p/mobile-ltz/');await page.waitForFunction(()=>Number(document.getElementById('fps').textContent)>0);
 assert.equal(await page.locator('#jointMode,.rigHead,.rigElbow').count(),0);assert.equal(await page.locator('#j3').isDisabled(),true);
 await page.locator('#connect').click();await page.locator('#j3').waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('#j3').disabled);
 const settled=async()=>{await page.waitForFunction(()=>!jointControls.moving&&state.mobile_arm.joints.every((v,i)=>Math.abs(v-state.mobile_arm.targets[i])<.001));return page.evaluate(()=>state.mobile_arm.targets.slice());};
 const initial=await settled();await page.locator('#j3').press('ArrowRight');await page.waitForFunction(v=>state.mobile_arm.targets[2]>v,initial[2]);const h=await settled();assert.equal(h[1],initial[1]);assert.equal(h[0],initial[0]);
 await page.locator('#j2').press('ArrowRight');await page.waitForFunction(v=>state.mobile_arm.targets[1]>v,h[1]);const e=await settled();assert.equal(e[2],h[2]);assert.equal(e[0],h[0]);
 const count=moves.length;await page.locator('#jointPrecision').click();await page.waitForTimeout(150);assert.equal(moves.length,count);
 await page.locator('#j3').press('ArrowRight');await page.waitForFunction(v=>state.mobile_arm.targets[2]>v,e[2]);const fine=await settled();assert.ok(Math.abs(fine[2]-e[2]-.05)<1e-7);
 // The illustration is read-only; targets remain unchanged when clicking its body.
 const countBefore=moves.length,rig=await page.locator('#jointRig').boundingBox();await page.mouse.click(rig.x+rig.width/2,rig.y+rig.height/2);await page.waitForTimeout(200);assert.equal(moves.length,countBefore);
 assert.equal(await page.locator('#jointRig button,#jointRig input').count(),0);
 for(const [width,height] of [[844,390],[390,844],[568,320],[320,568],[1024,768]]){
  await page.setViewportSize({width,height});await page.waitForTimeout(150);const frame=await page.locator('#jointRig').boundingBox();assert.ok(frame.height<=height/2+1);
  const anchor=await page.evaluate(()=>{const el=document.querySelector('.rigShoulder'),matrix=el.getScreenCTM(),dock=document.querySelector('.jointControls').getBoundingClientRect();return {x:matrix.e,y:matrix.f,gap:dock.top-matrix.f,right:dock.right};});
  assert.ok(anchor.gap>=24&&anchor.gap<=65,`arm base stays directly above sliders: ${JSON.stringify(anchor)}`);
  assert.ok(anchor.x<anchor.right&&anchor.x>anchor.right-100,'arm base remains on the right side of the sliders');
  for(const sel of ['#j3','#j2','#jointPrecision','#wheel','#stop']){const b=await page.locator(sel).boundingBox();assert.ok(b.x>=0&&b.y>=0&&b.x+b.width<=width+.1&&b.y+b.height<=height+.1,`${sel} fits ${width}x${height}`);}
  await page.screenshot({path:`/tmp/mobile-rig-${width}x${height}.png`});
 }
 await page.locator('#stop').click();await page.waitForFunction(()=>document.querySelector('#j3').disabled);assert.deepEqual(errors,[]);console.log('Slider axis isolation, precision, read-only rig, phone layouts and disabled-state checks passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
