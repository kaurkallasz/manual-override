// Isolated fixture only. Three-second stores must never send motion commands.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8127';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const errors=[],motions=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().endsWith('/api/command')){const d=r.postDataJSON();if(d?.action==='xyz')motions.push(d);}});
  await page.request.post(root+'/__test/command',{data:{action:'reset'}});
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:2}});
  await page.goto(root+'/s/green/p/mobile-ltz/');
  await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected'&&document.getElementById('app').dataset.controlMode==='xyz');
  const original=await page.evaluate(()=>({...xyzTarget}));
  const hold=async(n)=>{const b=await page.locator('#zPreset'+n).boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.waitForTimeout(3150);await page.mouse.up();};
  // Empty tap gives instructions; a short hold does not save.
  await page.locator('#zPreset1').click();assert.equal(motions.length,0);
  await page.locator('#zPreset1').focus();await page.keyboard.down('Space');await page.waitForTimeout(400);await page.keyboard.up('Space');
  assert.equal(await page.locator('#zPreset1').getAttribute('data-saved'),'false');
  await hold(1);assert.equal(motions.length,0,'storing a height never moves the arm');
  assert.equal(await page.locator('#zPreset1').getAttribute('data-saved'),'true');
  assert.ok(await page.locator('#zPresetGuide1 .zPresetMark').getAttribute('d'));
  await page.locator('#xyzZ').evaluate((el,z)=>{el.value=z;el.dispatchEvent(new Event('input',{bubbles:true}));},original.z+5);
  await page.waitForFunction(z=>Math.abs(state.mobile_arm.xyz_target.z-z)<1,original.z+5);
  const second=await page.evaluate(()=>xyzTarget.z),count=motions.length;
  await hold(2);assert.equal(motions.length,count);
  await page.locator('#zPreset3').focus();await page.keyboard.down('Space');await page.waitForTimeout(3150);await page.keyboard.up('Space');
  assert.equal(await page.locator('#zPreset3').getAttribute('data-saved'),'true');
  await page.locator('#zPreset1').click();
  await page.waitForFunction(z=>Math.abs(state.mobile_arm.xyz_target.z-z)<.01,original.z);
  assert.equal(motions.at(-1).xyz.x,original.x);assert.equal(motions.at(-1).xyz.y,original.y);
  // Cancelled holds never overwrite; the two stored heights survive reload.
  await page.locator('#zPreset2').focus();await page.keyboard.down('Space');await page.waitForTimeout(300);await page.locator('#xyzX').focus();await page.keyboard.up('Space');
  assert.equal(await page.evaluate(()=>zPresets[1]),second);
  await page.reload();await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected');
  assert.deepEqual(await page.evaluate(()=>zPresets),[original.z,second,second]);
  await page.locator('#zPreset2').click();await page.waitForFunction(z=>Math.abs(state.mobile_arm.xyz_target.z-z)<.01,second);
  await page.locator('#xyzPrecision').click();await page.screenshot({path:'/tmp/mobile-z-presets-fine.png'});await page.locator('#xyzPrecision').click();
  const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
  for(const [width,height] of [[844,390],[390,844],[568,320],[320,568],[1024,768]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(180);
   const buttons=await page.locator('#zPresetButtons').boundingBox();
   assert.ok(buttons.x>=0&&buttons.y>=0&&buttons.x+buttons.width<=width&&buttons.y+buttons.height<=height);
   for(const selector of ['.connectionControls','.xyzControls','#xyzHeightControl','.xyzYControl','.telemetry','#pumpButtons'])assert.ok(!overlap(buttons,await page.locator(selector).boundingBox()),`${width}x${height}: preset buttons overlap ${selector}`);
   const aligned=await page.evaluate(()=>{const line=document.querySelector('#zPresetGuide1 .zPresetMark').getAttribute('d').match(/^M([\d.e+-]+) ([\d.e+-]+)/),panel=$('xyzHeightControl').getBoundingClientRect(),track=$('xyzZ').getBoundingClientRect(),[lo,hi]=xyzBounds('z');return {actual:Number(line[2])+panel.top,expected:track.bottom-12-(zPresets[0]-lo)/(hi-lo)*(track.height-24)};});
   assert.ok(Math.abs(aligned.actual-aligned.expected)<.1,'stored height marker remains aligned');
   await page.screenshot({path:`/tmp/mobile-z-presets-${width}x${height}.png`});
  }
  await page.locator('#stop').click();for(const n of [1,2,3])assert.equal(await page.locator('#zPreset'+n).isDisabled(),true);
  assert.deepEqual(errors,[]);console.log('Z presets passed: hold timing, no motion on store, tap recall, XY preservation, cancellation, persistence, fine scale and five layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
