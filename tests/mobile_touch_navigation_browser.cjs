// Isolated fixture only; camera navigation must never issue arm commands.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
  await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
  let commands=0;const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/api/command'))commands++;});
  const root=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8117';
  await page.request.post(root+'/__test/command',{data:{action:'reset'}});
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:1}});
  await page.goto(root+'/s/green/p/mobile-ltz/');
  await page.waitForFunction(()=>Number(document.getElementById('fps').textContent)>0);
  assert.equal(await page.locator('.mapNavigation,.zoom').count(),0);
  const before=await page.locator('#world').getAttribute('style');
  await page.locator('#battlefield').dispatchEvent('wheel',{ctrlKey:true,deltaY:-150,clientX:420,clientY:180});
  assert.notEqual(await page.locator('#world').getAttribute('style'),before);
  assert.equal(await page.evaluate(()=>viewport.zoom),4);
  const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
  const selectors=['.telemetry','.identity','#expand','.connectionControls','#wheel','#j2','#j3'];
  for(const [width,height] of [[844,390],[390,844],[568,320],[320,568],[1024,768]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(150);
   const boxes=[];for(const selector of selectors)boxes.push([selector,await page.locator(selector).boundingBox()]);
   await page.screenshot({path:`/tmp/mobile-touch-${width}x${height}.png`});
   for(let i=0;i<boxes.length;i++){
    const [label,r]=boxes[i];assert.ok(r.x>=0&&r.y>=0&&r.x+r.width<=width+.1&&r.y+r.height<=height+.1,`${width}x${height}: ${label} fits`);
    for(let j=i+1;j<boxes.length;j++)assert.ok(!overlap(r,boxes[j][1]),`${width}x${height}: ${label} ${JSON.stringify(r)} overlaps ${boxes[j][0]} ${JSON.stringify(boxes[j][1])}`);
   }
   for(const selector of ['#j2','#j3'])assert.ok((await page.locator(selector).boundingBox()).height>=48);
   await page.screenshot({path:`/tmp/mobile-touch-${width}x${height}.png`});
  }
  await page.locator('#battlefield').dispatchEvent('wheel',{ctrlKey:true,deltaY:200,clientX:420,clientY:180});
  assert.equal(await page.evaluate(()=>viewport.zoom),1);
  assert.equal(commands,0);assert.deepEqual(errors,[]);
  // Touch/keyboard movement is tested only against the isolated virtual fixture.
  await page.setViewportSize({width:844,height:390});
  await page.locator('#connect').click();
  await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected');
  const j2Before=Number(await page.locator('#j2').inputValue());
  await page.locator('#j2').press('ArrowRight');
  await page.waitForFunction(before=>Number(document.querySelector('#j2').value)>before,j2Before);
  const j3Before=Number(await page.locator('#j3').inputValue());
  await page.locator('#j3').press('ArrowRight');
  await page.waitForFunction(before=>Number(document.querySelector('#j3').value)>before,j3Before);
  const dial=await page.locator('#wheel').boundingBox();
  const heading=()=>page.evaluate(()=>Math.atan2(state.mobile_arm.elbow.y-state.mobile_arm.base.y,state.mobile_arm.elbow.x-state.mobile_arm.base.x));
  const headingBefore=await heading();
  await page.mouse.move(dial.x+dial.width*.5,dial.y+20);await page.mouse.down();
  const angle=Number(await page.locator('#wheel').getAttribute('aria-valuenow'));
  await page.mouse.move(dial.x+dial.width*.7,dial.y+35,{steps:8});await page.mouse.up();
  assert.ok(Number(await page.locator('#wheel').getAttribute('aria-valuenow'))<angle,'clockwise drag decreases joint angle');
  await page.waitForFunction(before=>Math.abs(Math.atan2(state.mobile_arm.elbow.y-state.mobile_arm.base.y,state.mobile_arm.elbow.x-state.mobile_arm.base.x)-before)>.05,headingBefore);
  const clockwise=Number(await page.locator('#wheel').getAttribute('aria-valuenow'));
  await page.locator('#wheel').press('ArrowLeft');
  assert.ok(Number(await page.locator('#wheel').getAttribute('aria-valuenow'))>=clockwise,'Left reverses rotation direction');
  await page.mouse.move(dial.x+dial.width*.7,dial.y+35);await page.mouse.down();
  await page.mouse.move(dial.x+dial.width*.5,dial.y+20,{steps:8});await page.mouse.up();
  assert.ok(Number(await page.locator('#wheel').getAttribute('aria-valuenow'))>clockwise,'counterclockwise drag increases joint angle');
  await page.screenshot({path:'/tmp/mobile-touch-enabled.png'});
  await page.locator('#stop').click();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({viewports:5,zoom:4,tap:true,drag:true,keyboard:true,cameraCommands:0,fixtureCommands:commands,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
