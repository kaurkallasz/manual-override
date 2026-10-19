/* Isolated virtual fixture only. Never connect this test to the live hub. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8134';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const side of ['green','purple']){
   const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}});
   await page.goto(root+'/s/'+side+'/p/mobile-ltz/');
   await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='cue');
   const dismissBriefing=async()=>{if(await page.locator('#journeyClose').isVisible())await page.locator('#journeyClose').tap();};
   await dismissBriefing();
   // A fixture can survive earlier runs; start with a clean operator draft.
   while(await page.locator('.cueRow').count())await page.getByRole('button',{name:'Remove row 1',exact:true}).tap();
   await page.locator('#cueAdd').tap();
   await page.locator('.cueRow [data-field=destination]').selectOption('44');
   assert.equal(await page.locator('.cueRow').count(),2,'Clear view is included by default');
   await page.getByRole('button',{name:'Remove row 2',exact:true}).tap();
   assert.equal(await page.locator('.cueRow').count(),1,'Minus removes only Clear view');
   await page.getByRole('button',{name:'Add clear view after row 1'}).tap();
   assert.equal(await page.locator('.cueRow').count(),2);
   assert.equal(await page.locator('.cueRow').nth(1).locator('.cueSummary').textContent(),'← Clear view · 5 cm');
   const distance=page.getByRole('spinbutton',{name:'Clear view distance in centimetres, row 2'});
   assert.equal(await distance.inputValue(),'5');
   assert.equal(await page.getByRole('button',{name:'Clear view left, row 2',exact:true}).getAttribute('aria-pressed'),'true');
   for(const size of [{width:844,height:390},{width:390,height:844}]){
    await page.setViewportSize(size);
    assert(await page.locator('#cueRows').evaluate(el=>el.scrollWidth<=el.clientWidth),'Rows fit the cue panel');
    assert(await page.locator('#cuePlay').isVisible());
    await page.screenshot({path:`/tmp/clear-view-${side}-${size.width}x${size.height}.png`});
   }
   const expected=await page.evaluate(()=>({x:state.mobile_arm.markers.find(m=>m.id===44).x+(viewport.rotation===180?50:-50),piece:cueDraft[0].piece}));
   const startWithPickup=async destination=>{
    const source=await page.evaluate(()=>state.mobile_arm.tags.find(t=>t.id===cueDraft[0].piece));
    assert.equal(await page.locator('#cuePickupBullseye').isVisible(),false);
    await page.locator('#cuePlay').tap();
    await page.waitForFunction(()=>state.mobile_arm.cue.status==='running'&&!$('cuePickupBullseye').hasAttribute('hidden'));
    const actual=await page.evaluate(id=>{
     const dest=state.mobile_arm.markers.find(t=>t.id===id);
     return {source:$('cuePickupBullseye').getAttribute('transform'),scale:viewport.scale,
      color:getComputedStyle($('cuePickupBullseye')).stroke,
      target:$('xyzTargetBullseye').getAttribute('transform'),expected:`translate(${dest.x} ${dest.y}) scale(${1/viewport.scale})`};
    },destination);
    assert.equal(actual.source,`translate(${source.x} ${source.y}) scale(${1/actual.scale})`);
    assert.equal(actual.color,'rgb(54, 245, 255)','Pickup is cyan');
    assert.equal(actual.target,actual.expected,'Existing final destination stays unchanged');
   };
   await startWithPickup(44);
   assert(await page.locator('#rotateView').isDisabled(),'The player view stays fixed during Clear view playback');
   await page.locator('#cuePlay').tap();await page.waitForFunction(()=>state.mobile_arm.cue.status==='paused');
   assert(await page.locator('#rotateView').isDisabled(),'Pause retains the same player view');
   assert(await distance.isDisabled(),'A running or paused program retains its committed clearance');
   for(const size of [{width:844,height:390},{width:390,height:844}]){
    await page.setViewportSize(size);
    assert(await page.locator('#cuePickupBullseye').isVisible());
    await page.screenshot({path:`/tmp/cue-pickup-${side}-${size.width}x${size.height}.png`});
   }
   await page.locator('#cuePlay').tap();
   await page.waitForFunction(()=>state.mobile_arm.held_tag===cueDraft[0].piece,null,{timeout:90000});
   await page.waitForFunction(()=>$('cuePickupBullseye').hasAttribute('hidden'));
   await page.waitForFunction(()=>state.mobile_arm.cue.status==='completed'||state.mobile_arm.cue.status==='error',null,{timeout:90000});
   const arm=await page.evaluate(()=>state.mobile_arm);
   assert.equal(arm.cue.status,'completed',arm.cue.error);assert.equal(arm.cue.index,1);
   assert(await page.locator('#rotateView').isEnabled(),'View rotation is available after cue completion');
   assert(Math.abs(arm.tip.x-expected.x)<.01);assert.equal(arm.held_tag,null);assert.equal(arm.pump,'off');
   assert(await page.evaluate(()=>{const arm=state.mobile_arm,dest=arm.markers.find(m=>m.id===44);return viewport.screen(arm.tip.x,arm.tip.y).x<viewport.screen(dest.x,dest.y).x;}),'Left Clear view moves left on the player screen');
   assert.equal(await page.locator('#cuePickupBullseye').isVisible(),false,'Completion clears pickup preview');
   const destination=page.locator('.cueRow [data-field=destination]');
   assert(await destination.locator('option').count()>1,'Completion preserves target choices');
   await destination.selectOption('42');
   await distance.fill('');assert(await page.locator('#cuePlay').isDisabled(),'An empty distance cannot run');
   await distance.fill('7.5');await page.getByRole('button',{name:'Clear view right, row 2',exact:true}).tap();
   const rightX=await page.evaluate(()=>state.mobile_arm.markers.find(m=>m.id===42).x+(viewport.rotation===180?-75:75));
   await startWithPickup(42);
   await page.waitForFunction(()=>state.mobile_arm.cue.rows[0]?.destination===42&&state.mobile_arm.cue.status==='completed',null,{timeout:90000});
   assert(Math.abs(await page.evaluate(()=>state.mobile_arm.tip.x)-rightX)<.01,'Configured distance/direction reaches the expected point');
   assert(await page.evaluate(()=>{const arm=state.mobile_arm,dest=arm.markers.find(m=>m.id===42);return viewport.screen(arm.tip.x,arm.tip.y).x>viewport.screen(dest.x,dest.y).x;}),'Right Clear view moves right on the player screen');
   await page.reload();await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='cue');await dismissBriefing();
   assert.equal(await distance.inputValue(),'7.5');
   assert.equal(await page.getByRole('button',{name:'Clear view right, row 2',exact:true}).getAttribute('aria-pressed'),'true');
   await page.screenshot({path:`/tmp/clear-view-configurable-${side}.png`});
   await page.getByRole('button',{name:'Remove row 2',exact:true}).tap();
   await destination.selectOption('40');await startWithPickup(40);
   await page.waitForFunction(()=>state.mobile_arm.cue.rows.length===1&&state.mobile_arm.cue.rows[0]?.destination===40&&state.mobile_arm.cue.status==='completed',null,{timeout:90000});
   await page.reload();await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='cue');await dismissBriefing();
   assert.equal(await page.locator('.cueRow').count(),1,'Saved opt-out survives a page reload');
   assert.deepEqual(errors,[]);await page.close();
   console.log(`PASS ${side}: cyan pickup and unchanged destination, default/removable Clear view, layout, three successive destinations, saved opt-out`);
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
