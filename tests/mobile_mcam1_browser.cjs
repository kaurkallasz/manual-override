/* Real player UI and optional camera fixture; never the hardware hub. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8146';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(root))throw Error('Use the isolated mobile fixture');
const overlaps=(a,b)=>a&&b&&a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
   const errors=[],hardware=[];page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(/\/mcam1\/|\/cartesian-xyz-test\//.test(r.url())&&r.method()==='POST')hardware.push(r.url());});
   await page.request.post(root+'/__test/camera',{data:{enabled:false}});
   await page.request.post(root+'/__test/mcam1',{data:{enabled:false}});
   assert((await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}})).ok());
   await page.goto(root+'/s/'+side+'/p/mobile-ltz/',{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>state?.status==='ready'&&!!view);
   assert.equal(await page.locator('#mcam1Video').isVisible(),false);
   assert.equal(await page.evaluate(()=>feedReady),true,'game starts without MCAM1');
   await page.request.post(root+'/__test/mcam1',{data:{enabled:true,stale:false,width:480,height:320}});
   await page.waitForFunction(()=>!document.getElementById('mcam1Video').hidden);
   assert.deepEqual(await page.locator('#mcam1Video').evaluate(c=>[c.width,c.height]),[240,160]);
   assert.equal(await page.locator('#mcam1Video').evaluate(c=>c.getContext('2d').getContextAttributes().willReadFrequently),true,'Inset uses the same software-backed camera surface');
   for(const [width,height] of [[844,390],[1180,820],[667,320],[568,320],[390,844],[320,568]]){
    await page.setViewportSize({width,height});await page.waitForTimeout(200);
    const box=await page.locator('#mcam1Video').boundingBox();
    assert(box&&box.width>0&&box.height>0,`${side} ${width}: visible inset`);
    assert(box.x>=0&&box.y>=0&&box.x+box.width<=width&&box.y+box.height<=height,`${side} ${width}: inset fits`);
    assert(box.width<=240.1&&box.height<=160.1,'at most half source size');
    if(width>=844)assert(Math.abs(box.width-240)<.1,`${side} ${width}: half-size display`);
    for(const selector of ['.connectionButtons','.playerLog','#cuePanel','.zoom','.xyzHeight','.telemetry']){
     for(const el of await page.locator(selector).all()){
      if(!await el.isVisible())continue;
      const control=await el.boundingBox();
      assert(!overlaps(box,control),`${side} ${width}: inset overlaps ${selector}: ${JSON.stringify({box,control})}`);
      if(selector==='#cuePanel')assert(box.x+box.width<=control.x,`${selector} stays on right`);
     }
    }
    if(width===844)await page.screenshot({path:`/tmp/mobile-mcam1-${side}.png`});
   }
   await page.setViewportSize({width:844,height:390});
   for(const [control,mode] of [[1,'joint'],[2,'xyz'],[3,'targeting'],[4,'cue']]){
    assert((await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control}})).ok());
    await page.waitForFunction(mode=>controlMode===mode,mode);
    await page.waitForTimeout(180);
    const box=await page.locator('#mcam1Video').boundingBox();
    assert(box&&box.width>0,`${side}: ${mode} displays MCAM1`);
    for(const selector of ['.connectionButtons','.jointControls','.xyzHeight','#cuePanel']){
     for(const el of await page.locator(selector).all()){
      if(await el.isVisible())assert(!overlaps(box,await el.boundingBox()),`${side}: ${mode} ${selector} clear`);
     }
    }
   }
   for(const [width,height] of [[320,240],[640,480],[480,320]]){
    await page.request.post(root+'/__test/mcam1',{data:{width,height}});
    await page.waitForFunction(([w,h])=>{const c=document.getElementById('mcam1Video');return !c.hidden&&c.width===w/2&&c.height===h/2;},[width,height]);
   }
   await page.request.post(root+'/__test/mcam1',{data:{stale:true}});
   await page.waitForFunction(()=>document.getElementById('mcam1Video').hidden);
   assert.equal(await page.evaluate(()=>feedReady),true,'stale MCAM1 does not stop the game');
   await page.request.post(root+'/__test/mcam1',{data:{stale:false}});
   await page.waitForFunction(()=>!document.getElementById('mcam1Video').hidden);
   await page.route('**/assets/mcam1.jpg*',r=>r.fulfill({status:503,body:'Unavailable'}));
   await page.waitForFunction(()=>document.getElementById('mcam1Video').hidden);
   assert.equal(await page.evaluate(()=>feedReady),true);
   await page.unroute('**/assets/mcam1.jpg*');
   await page.waitForFunction(()=>!document.getElementById('mcam1Video').hidden);
   // Metadata loss must expire the display even if JPEG HTTP still responds.
   await page.evaluate(()=>{liveFeed.stop();const original=mcam1Feed.update.bind(mcam1Feed);window.restoreMcam1Update=()=>mcam1Feed.update=original;mcam1Feed.update=()=>{};});
   await page.waitForFunction(()=>document.getElementById('mcam1Video').hidden);
   await page.evaluate(()=>{restoreMcam1Update();openEvents();});
   await page.waitForFunction(()=>!document.getElementById('mcam1Video').hidden);
   await page.request.post(root+'/__test/mcam1',{data:{enabled:false}});
   await page.waitForFunction(()=>document.getElementById('mcam1Video').hidden);
   assert.equal(await page.evaluate(()=>feedReady),true);
   assert.deepEqual(errors,[]);assert.deepEqual(hardware,[]);
   await page.close();
  }
  console.log('MCAM1 passed: both teams, optional startup, half-size modes, six layouts, stale/error/disabled hiding and recovery, no hardware commands.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
