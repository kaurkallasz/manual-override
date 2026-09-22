// Run against the isolated fixture: python tests/mobile_ltz_fixture.py --port 8127
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8127';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const operator=await browser.newPage();operator.on('pageerror',e=>errors.push(e.message));
  await page.request.post(root+'/__test/command',{data:{action:'reset'}});
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:null}});
  await operator.goto(root+'/s/gamemaster/p/laser-tag-y/');
  await operator.locator('#testUnlocks').waitFor({state:'visible'});
  await page.goto(root+'/s/green/p/mobile-ltz/');
  await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected');
  assert.equal(await page.locator('#jointRig').isVisible(),true);
  await page.locator('#levelsOpen').click();await page.waitForFunction(()=>!document.getElementById('mobileControl').disabled);
  assert.equal(await page.locator('#mobileControl option[value=xyz]').evaluate(el=>el.disabled),true);
  await operator.locator('#testOverride').check();
  await operator.locator('#testMobileControl').selectOption('2');
  // Unrelated state updates must preserve an unapplied choice.
  await operator.waitForTimeout(450);
  assert.equal(await operator.locator('#testMobileControl').inputValue(),'2');
  await operator.locator('#applyTestUnlocks').click();
  await page.waitForFunction(()=>!document.querySelector('#mobileControl option[value=xyz]').disabled);
  // Applying the higher unlock switches the connected phone automatically.
  await page.waitForFunction(()=>document.getElementById('app').dataset.controlMode==='xyz');
  await page.locator('#levelsClose').click();
  assert.equal(await page.locator('#jointRig').isVisible(),false);
  assert.equal(await page.locator('#wheel').isVisible(),false);
  assert.equal(await page.locator('#xyzBullseyes').isVisible(),true);
  await page.waitForFunction(()=>document.getElementById('xyzBullseyes').dataset.aligned==='true');
  // Move to a reachable point calculated from the fixture's known arm geometry.
  const start=await page.evaluate(()=>({...state.mobile_arm.tip}));
  await page.locator('#xyzX').evaluate(el=>{el.value=Number(el.value)-40;el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>document.getElementById('xyzBullseyes').dataset.aligned==='false');
  await page.screenshot({path:'/tmp/mobile-xyz-moving.png'});
  await page.waitForFunction(x=>state.mobile_arm.tip.x<x-30,start.x);
  await page.waitForFunction(()=>document.getElementById('xyzBullseyes').dataset.aligned==='true');
  for(const id of ['xyzXActual','xyzYActual','xyzZActual'])assert.equal(await page.locator('#'+id).isVisible(),true);
  await page.locator('#xyzPrecision').click();
  assert.equal(await page.locator('#xyzPrecision').getAttribute('aria-checked'),'true');
  assert.equal(await page.locator('#xyzX').getAttribute('step'),'0.1');
  await page.locator('#xyzPrecision').click();
  await page.locator('#xyzZ').press('ArrowRight');
  await page.waitForFunction(z=>Math.abs(state.mobile_arm.tip.z-z)>.1,start.z);
  const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
  for(const [width,height] of [[844,390],[390,844],[568,320],[320,568],[1024,768]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(200);
   const selectors=['.telemetry','.identity','#expand','.connectionControls','#xyzHeightControl','.xyzYControl','.xyzControls','#pumpButtons','#zPresetButtons'];
   const yRail=await page.locator('.xyzYControl').boundingBox();
   assert.ok(Math.abs(yRail.y-8)<1,'Y rail starts at the top safe margin');
   const zRail=await page.locator('#xyzHeightControl').boundingBox(),connection=await page.locator('.connectionControls').boundingBox();
   assert.ok(Math.abs(zRail.y-connection.y-connection.height-8)<1,'Z rail starts below Connect and Stop');
   assert.ok(Math.abs(connection.x-zRail.x)<1,'connection buttons align with the left rail');
   assert.equal(await page.locator('.zoom,.mapNavigation').count(),0,'zoom controls removed');
   const yInput=await page.locator('#xyzY').boundingBox();assert.ok(yInput.y+yInput.height<=yRail.y+yRail.height,'Y track fits its rail');
   assert.equal(await page.locator('#xyzY').evaluate(el=>getComputedStyle(el).writingMode),'vertical-lr');
   const boxes=[];for(const selector of selectors)boxes.push([selector,await page.locator(selector).boundingBox()]);
   await page.screenshot({path:`/tmp/mobile-xyz-${width}x${height}.png`});
   for(let i=0;i<boxes.length;i++){
    const [name,a]=boxes[i];assert.ok(a&&a.x>=0&&a.y>=0&&a.x+a.width<=width+.1&&a.y+a.height<=height+.1,`${width}x${height} ${name} fits ${JSON.stringify(a)}`);
    for(let j=i+1;j<boxes.length;j++)assert.ok(!overlap(a,boxes[j][1]),`${width}x${height} ${name} overlaps ${boxes[j][0]}`);
   }
  }
  // Pan/zoom never changes XYZ targets; both bullseyes share the map transform.
  const before=await page.evaluate(()=>JSON.stringify(xyzTarget));
  await page.locator('#battlefield').dispatchEvent('wheel',{ctrlKey:true,deltaY:-110,clientX:300,clientY:200});
  assert.equal(await page.evaluate(()=>JSON.stringify(xyzTarget)),before);
  await page.screenshot({path:'/tmp/mobile-xyz-zoom.png'});
  const guides=await page.evaluate(()=>{const d=$('xyzTargetGuides').getAttribute('d'),a=viewport.point(0,0),b=viewport.point(viewport.vw,viewport.vh);return {d,expected:`M${a.x} ${xyzTarget.y}H${b.x} M${xyzTarget.x} ${a.y}V${b.y}`};});
  assert.equal(guides.d,guides.expected,'guides span the screen at the target after zoom');
  await page.locator('#battlefield').dispatchEvent('wheel',{ctrlKey:true,deltaY:200,clientX:300,clientY:200});
  // The former unreachable edge is now reachable across the simulated map.
  await page.locator('#xyzX').evaluate(el=>{el.value=el.min;el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>Math.abs(state.mobile_arm.tip.x)<.2);
  assert.equal(await page.evaluate(()=>xyzError),'');
  assert.equal(await page.locator('#connection').textContent(),'Connected');
  await operator.locator('#testMobileControl').selectOption('4');await operator.locator('#applyTestUnlocks').click();
  await page.locator('#levelsOpen').click();await page.waitForFunction(()=>!document.getElementById('mobileControl').disabled);
  await page.waitForFunction(()=>document.querySelector('#mobileControl option[value=cue]').textContent==='Cue autonomy');
  assert.equal(await page.locator('#mobileControl option[value=cue]').evaluate(el=>el.disabled),false);
  await page.locator('#mobileControl').selectOption('joint');await page.waitForFunction(()=>document.getElementById('app').dataset.controlMode==='joint');
  await page.locator('#levelsClose').click();assert.equal(await page.locator('#jointRig').isVisible(),true);
  await page.reload();
  await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected'&&document.getElementById('app').dataset.controlMode==='cue');
  await page.locator('#levelsOpen').click();await page.waitForFunction(()=>!document.getElementById('mobileControl').disabled);await page.locator('#mobileControl').selectOption('xyz');
  await page.waitForFunction(()=>document.getElementById('app').dataset.controlMode==='xyz');await page.locator('#levelsClose').click();
  await operator.locator('#baseTestUnlocks').click();
  await operator.waitForFunction(()=>ui.state.virtual_test_control===1&&!document.getElementById('applyTestUnlocks').disabled&&document.getElementById('testMobileControl').value==='1');
  await page.waitForFunction(()=>document.getElementById('app').dataset.controlMode==='joint');
  await operator.locator('#testMobileControl').selectOption('2');await operator.locator('#applyTestUnlocks').click();
  await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected'&&document.getElementById('app').dataset.controlMode==='xyz');
  await page.locator('#levelsOpen').click();await page.waitForFunction(()=>!document.getElementById('mobileControl').disabled&&!document.querySelector('#mobileControl option[value=xyz]').disabled);
  await page.locator('#mobileControl').selectOption('xyz');await page.waitForFunction(()=>document.getElementById('app').dataset.controlMode==='xyz');await page.locator('#levelsClose').click();
  await page.locator('#stop').click();assert.equal(await page.locator('#xyzX').isDisabled(),true);
  await page.locator('#connect').click();await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected');
  assert.equal(await page.locator('#app').getAttribute('data-control-mode'),'xyz');
  await page.waitForFunction(()=>Math.abs(xyzTarget.x-state.mobile_arm.tip.x)<.1);
  await page.locator('#stop').click();
  assert.deepEqual(errors,[]);
  console.log('XYZ browser checks passed: operator unlocks, movement, indicators, convergence, layouts, zoom, rejection, mode switch and relock.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
