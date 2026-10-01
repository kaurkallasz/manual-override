// Real player pages, real GM commands, temporary profiles, fake robot transport.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],verified=[];
 try{
  const gm=await browser.newPage();gm.on('pageerror',error=>errors.push('GM: '+error.message));
  await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/');
  await gm.waitForSelector('#testMobileControl');
  await gm.request.post(origin+'/__test/camera',{data:{enabled:true}});
  const players=[],scores=[];
  for(const side of ['green','purple']){
   const score=await browser.newPage();score.on('pageerror',error=>errors.push(side+' score: '+error.message));
   await score.goto(origin+`/s/${side}/p/ltz-score/`);
   await score.waitForFunction(()=>document.getElementById('playerSelect').value);
   const page=await browser.newPage({viewport:{width:1000,height:900}});page.on('pageerror',error=>errors.push(side+': '+error.message));
   await page.addInitScript(side=>localStorage.setItem('auto-pickup-game-flip-'+side,'0'),side);
   const link=await score.locator('a', {hasText:'Open player controls'}).getAttribute('href');
   await page.goto(new URL(link,score.url()).href);
   await page.waitForSelector('#playerJointRig svg',{state:'attached'});
   assert.equal(await page.locator('#flipToggle').isChecked(),side==='purple','LTZ uses the player side, not an old commissioning preference');
   assert.deepEqual(await page.evaluate(()=>gameDisplayPoint(.2,.3)),side==='purple'?{u:.8,v:.7}:{u:.2,v:.3},'Camera overlays share the displayed orientation');
   assert(await page.locator('#nameGate').isHidden(),'LTZ does not require an unrelated Auto Pickup name');
   players.push({side,page});scores.push(score);
  }
  for(const tier of [1,2,3,4]){
   await gm.locator('#testOverride').check();
   await gm.locator('#testMobileControl').selectOption(String(tier));
   await gm.locator('#applyTestUnlocks').click();
   await gm.waitForFunction(t=>ui.state?.virtual_test_control===t,tier);
   for(const {side,page}of players){
    try{await page.waitForFunction(t=>document.getElementById('mobilePhysicalControl').value===String(t),tier,{timeout:8000});}
    catch(error){console.log(await page.evaluate(t=>({expected:t,select:document.getElementById('mobilePhysicalControl').value,tier:ltzTier,choice:mobileControlChoice,error:mobileGameError,actual:mobileGame?.virtual_test_control}),tier));throw error;}
    const panels=['jointAnglesPanel','tcpPosePanel','autoPickPlacePanel','autoPpxPanel'];
    const visible=await page.evaluate(ids=>ids.map(id=>!document.getElementById(id).hidden),panels);
    assert.deepEqual(visible,[tier===1,[2,3].includes(tier),tier===3,tier===4]);
    verified.push(side+': '+tier);
    if(tier===1){
     await page.waitForFunction(()=>!document.querySelector('[data-rig-axis="1"]').disabled);
     await page.evaluate(()=>{cal2JointSafetyGuard=()=>({format:'auto-pp-calibration-2-v1',polygon:[[250,0],[400,0],[400,200]],radius_min:220,radius_max:440,z_min:-150,z_max:230});});
     const before=Number(await page.locator('#ltxJ2').inputValue());
     await page.locator('[data-rig-axis="1"]').focus();await page.keyboard.press('ArrowUp');
     await page.waitForFunction(value=>Number(document.getElementById('ltxJ2').value)>value,before);
     const body=await page.request.get(origin+'/__test/robot-commands').then(r=>r.json());
     assert(body.some(command=>command.side===side&&command.action==='joint-move'&&command.data.j2>before&&command.data.ltz_action==='joint'));
     await page.locator('#jointAnglesPanel').scrollIntoViewIfNeeded();
     const fits=await page.evaluate(()=>{
      const host=document.getElementById('playerJointRig').getBoundingClientRect();
      return [...document.querySelectorAll('#playerJointRig .rigDrawing > g')].every(part=>{const r=part.getBoundingClientRect();return r.left>=host.left-2&&r.top>=host.top-2&&r.right<=host.right+2&&r.bottom<=host.bottom+2;});
     });
     assert(fits,'ordinary schematic contains the complete arm');
     await page.screenshot({path:`/tmp/ltz-${side}-ordinary-joints.png`});
    }
   }
   for(const score of scores){
    await score.waitForFunction(t=>document.getElementById('controlSelect').value===String(t),tier);
    assert.match(await score.locator('#runStatus').innerText(),/Game Master practice/);
   }
  }
  await gm.locator('#testOverride').uncheck();await gm.locator('#applyTestUnlocks').click();
  for(const {page}of players)await page.waitForFunction(()=>document.getElementById('mobilePhysicalControl').value==='1');
  for(const score of scores){await score.waitForFunction(()=>document.getElementById('controlSelect').value==='1');assert(!/Game Master practice/.test(await score.locator('#runStatus').innerText()));}
  for(const {side,page}of players){
   await page.locator('#flipToggle').setChecked(side!=='purple');
   await page.reload();await page.waitForSelector('#playerJointRig svg',{state:'attached'});
   assert.equal(await page.locator('#flipToggle').isChecked(),side!=='purple','An explicit player view override survives reload');
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({verified,schematic:'visible, interactive, measured outline, existing guarded transport',score:'practice grant and restoration',errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
