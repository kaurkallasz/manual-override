/* Native selection must never compete with game gestures. Fake hardware only. */
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8146';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(root))throw Error('Isolated fixture required');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const team of ['green','purple']){
   const page=await browser.newPage({viewport:{width:1180,height:820}}),errors=[],commands=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/api/command'))commands.push(r.postDataJSON());});
   await page.addInitScript(()=>{localStorage.setItem('mobile-ltz:stopped','yes');localStorage.setItem('mobile-ltz:purple:stopped','yes');});
   await page.request.post(root+'/__test/camera',{data:{enabled:false,stale:false}});
   await page.goto(`${root}/s/${team}/p/mobile-ltz/`);
   await page.waitForFunction(()=>state?.status==='ready'&&view?.levelReady);
   for(const physical of [false,true]){
    if(physical){await page.request.post(root+'/__test/camera',{data:{enabled:true,stale:false}});await page.waitForFunction(()=>!state.virtual_play&&turretOverlay.cameraReady());}
    assert.equal(await page.locator('#battlefield').evaluate(el=>getComputedStyle(el).webkitUserSelect),'none');
    // A restored/programmatic range must also recover, including a range
    // containing the entire world rather than a text node inside it.
    await page.evaluate(()=>{const range=document.createRange();range.selectNode(document.getElementById('world'));getSelection().removeAllRanges();getSelection().addRange(range);});
    await page.waitForFunction(()=>getSelection().isCollapsed);
    assert.deepEqual(await page.locator('#battlefield').evaluate(el=>['selectstart','dragstart'].map(type=>el.dispatchEvent(new Event(type,{bubbles:true,cancelable:true})))),[false,false]);
    const box=await page.locator('#battlefield').boundingBox();
    await page.mouse.move(box.x+box.width*.5,box.y+box.height*.3);
    await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5,{steps:12});await page.mouse.up();
    assert.equal(await page.evaluate(()=>getSelection().isCollapsed),true);
    assert.equal(await page.evaluate(()=>mapPointers.size),0,'selection prevention preserves pointer release');
    // Escape and an ordinary click clear a stale range synchronously, before
    // the asynchronous selectionchange notification arrives.
    for(const event of ['keydown','pointerdown'])assert.equal(await page.evaluate(event=>{
     const field=document.getElementById('battlefield'),range=document.createRange();range.selectNode(field);
     getSelection().removeAllRanges();getSelection().addRange(range);
     document.dispatchEvent(event==='keydown'?new KeyboardEvent(event,{key:'Escape',bubbles:true}):new PointerEvent(event,{bubbles:true}));
     return getSelection().isCollapsed;
    },event),true);
   }
   // Copying status text and selecting/editing form values remain native.
   await page.evaluate(()=>{const range=document.createRange();range.selectNodeContents(document.getElementById('mode'));getSelection().removeAllRanges();getSelection().addRange(range);});
   await page.waitForTimeout(40);assert.equal(await page.evaluate(()=>getSelection().toString()),'Physical mode');
   await page.evaluate(()=>{getSelection().removeAllRanges();document.getElementById('login').showModal();});
   await page.locator('#password').fill('editable');await page.locator('#password').selectText();
   assert.deepEqual(await page.locator('#password').evaluate(el=>[el.selectionStart,el.selectionEnd]),[0,8]);
   await page.keyboard.type('replacement');assert.equal(await page.locator('#password').inputValue(),'replacement');
   assert.deepEqual(errors,[]);
   assert.equal(commands.filter(c=>['xyz','joints','cue_waypoint','turret_aim'].includes(c?.action)).length,0);
   await page.close();
  }
  console.log('Both teams: native selection/drag blocked, stale range clears on selectionchange/Escape/click, pointer release and editable/copyable text preserved.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
