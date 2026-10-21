/* Real player/score views, temporary stores and synthetic feedback only. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8157',output=process.env.MOVEMENT_OUTPUT||'output/robot-movement';
const server=spawn('.venv/bin/python',['tests/robot_movement_fixture.py'],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(p,value={}){const r=await fetch(base+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});assert(r.ok,await r.clone().text());return r.json();}
(async()=>{
 let browser;
 try{
  for(let i=0;i<100&&!logs.includes('Movement fixture ready');i++)await wait(100);
  assert(logs.includes('Movement fixture ready'),logs);fs.mkdirSync(output,{recursive:true});
  await api('/__test/movement',{pending:true});
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors=[];
  const pending=await browser.newPage({viewport:{width:390,height:844}});pending.on('pageerror',e=>errors.push(e.message));
  await pending.goto(base+'/s/purple/p/mobile-ltz/');
  const pendingCanvas=pending.locator('.ltzPendingResult [data-movement] canvas');await pendingCanvas.waitFor();
  await pendingCanvas.evaluate(e=>e.scrollIntoView({block:"center"}));await pendingCanvas.focus();await pendingCanvas.press('ArrowRight');
  const pendingView=await pendingCanvas.getAttribute('data-view');assert(pendingView);
  await api('/__test/movement-save');
  const savedCanvas=pending.locator('.ltzLevelResult [data-movement] canvas');await savedCanvas.waitFor();
  assert.equal(await savedCanvas.getAttribute('data-view'),pendingView);await pending.close();
  for(const [name,url,size]of [
   ['portrait','/s/purple/p/mobile-ltz/',{width:390,height:844}],
   ['desktop','/s/green/p/ltz-score/',{width:1280,height:960}],
  ].filter(([name])=>!process.env.MOVEMENT_VIEW||name===process.env.MOVEMENT_VIEW)){
   const page=await browser.newPage({viewport:size,hasTouch:name==='portrait'});page.on('pageerror',e=>errors.push(e.message));
   await page.clock.install({time:new Date()});
   await page.goto(base+url);await page.locator('.ltzLevelResult [data-movement]').waitFor();
   const panel=page.locator('.ltzLevelResult [data-movement]');
   await panel.evaluate(e=>e.scrollIntoView({block:"center"}));
   await page.waitForFunction(()=>document.querySelector('.ltzLevelResult [data-movement] canvas')?.dataset.floor==='ready');
   await page.clock.pauseAt(new Date(Date.now()+1000));
   const canvas=panel.locator('canvas');
   assert.match(await panel.textContent(),/20× playback/);
   assert.equal(await page.locator('.ltzLevelResult .ltzHeatmap').count(),0);
   assert.equal(await panel.locator('canvas').count(),1);
   assert.equal(await canvas.getAttribute('data-floor'),'ready');
   assert.match(await panel.textContent(),/Recorded game data/);
   assert(await panel.evaluate(e=>Object.values(JSON.parse(e.dataset.movement).floor_urls).every(url=>!url.includes('camera')&&!url.includes('mcam1'))));
   await panel.locator('[data-move="replay"]').click();await page.clock.runFor(1000);
   let time=Number(await canvas.getAttribute('data-time'));assert(time>=19&&time<=21,`20x after 1s: ${time}`);
   await panel.locator('[data-move="play"]').click();const stopped=Number(await canvas.getAttribute('data-time'));
   await page.clock.runFor(1000);assert.equal(Number(await canvas.getAttribute('data-time')),stopped);
   assert.equal(await canvas.getAttribute('data-heat-kills'),'0');
   // Rotate through actual pointer gestures; zoom via wheel.
   const box=await canvas.boundingBox(),before=await canvas.getAttribute('data-view');
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+55,box.y+box.height/2+25,{steps:5});await page.mouse.up();
   assert.notEqual(await canvas.getAttribute('data-view'),before);
   const rotated=await canvas.getAttribute('data-view');await page.mouse.wheel(0,-150);await page.clock.runFor(50);assert.notEqual(await canvas.getAttribute('data-view'),rotated);
   if(name==='portrait'){
    const cdp=await page.context().newCDPSession(page),cx=box.x+box.width/2,cy=box.y+box.height/2;
    const zoomBefore=JSON.parse(await canvas.getAttribute('data-view'))[2];
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx-35,y:cy},{x:cx+35,y:cy}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx-65,y:cy},{x:cx+65,y:cy}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    assert(JSON.parse(await canvas.getAttribute('data-view'))[2]>zoomBefore);await cdp.detach();
   }
   const savedView=await canvas.getAttribute('data-view');
   // Results replace their DOM when SSE changes. Exercise the same mount path.
   await panel.evaluate(node=>{const replacement=node.cloneNode(true);node.replaceWith(replacement);LTZMovement.mount(replacement.parentElement);});
   assert.equal(await canvas.getAttribute('data-view'),savedView);assert.equal(Number(await canvas.getAttribute('data-time')),stopped);
   await panel.locator('[data-move="top"]').click();assert.equal(JSON.parse(await canvas.getAttribute('data-view'))[1],Math.PI/2);
   await panel.locator('[data-move="reset"]').click();
   for(const [at,kills]of [[0,0],[60,10],[299,10],[300,20],[540,30],[100,10],[600,30]]){
    await panel.locator('input').fill(String(at));assert.equal(Number(await canvas.getAttribute('data-time')),at);
    assert.equal(Number(await canvas.getAttribute('data-heat-kills')),kills,`heatmap at ${at}`);
    assert.equal(Number(await canvas.getAttribute('data-kill-flashes')),[60,300,540].includes(at)?1:0);
    if(at===300)await panel.screenshot({path:path.join(output,`game-data-replay-${name}.png`)});
   }
   for(const side of ['green','purple']){
    const toggle=panel.locator(`[data-move="${side}"]`);await toggle.click();assert.equal(await toggle.getAttribute('aria-pressed'),'false');await toggle.click();
   }
   const pixels=await canvas.evaluate(c=>{const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let green=0,purple=0,heat=0;for(let i=0;i<d.length;i+=4){if(d[i]===73&&d[i+1]===229&&d[i+2]===154)green++;if(d[i]===196&&d[i+1]===139&&d[i+2]===255)purple++;if(d[i]>130&&d[i]>d[i+1]*1.4&&d[i]>d[i+2]*1.4)heat++;}return {green,purple,heat};});
   assert(pixels.green>20&&pixels.purple>20&&pixels.heat>5,JSON.stringify(pixels));
   assert(await panel.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
   await panel.screenshot({path:path.join(output,`robot-movement-${name}.png`)});
   await panel.locator('[data-move="replay"]').click();await page.clock.runFor(15000);
   assert(Math.abs(Number(await canvas.getAttribute('data-time'))-300)<1);
   await page.clock.runFor(15100);assert.equal(Number(await canvas.getAttribute('data-time')),600);
   assert.equal(await panel.locator('[data-move="play"]').textContent(),'Play');
   for(const [speed,seconds]of [[50,12],[100,6]]){
    await panel.locator('select').selectOption(String(speed));
    assert.match(await panel.textContent(),new RegExp(speed+'× playback'));
    await panel.locator('[data-move="replay"]').click();await page.clock.runFor(seconds*500);
    const halfway=Number(await canvas.getAttribute('data-time'));assert(Math.abs(halfway-300)<2,`${speed}x halfway: ${halfway}`);
    await page.clock.runFor(seconds*500+100);assert.equal(Number(await canvas.getAttribute('data-time')),600);
    assert.equal(await canvas.getAttribute('data-heat-kills'),'30');
   }
   await panel.locator('input').fill('100');await panel.locator('select').selectOption('20');
   await panel.locator('[data-move="play"]').click();await page.clock.runFor(1000);
   const switchTime=Number(await canvas.getAttribute('data-time')),switchView=await canvas.getAttribute('data-view');
   await panel.locator('select').selectOption('100');assert.equal(Number(await canvas.getAttribute('data-time')),switchTime);
   await page.clock.runFor(1000);const switchedTime=Number(await canvas.getAttribute('data-time'));assert(Math.abs(switchedTime-switchTime-100)<2,`speed change: ${switchTime} -> ${switchedTime}; canvas ${JSON.stringify(await canvas.boundingBox())}`);
   assert.equal(await canvas.getAttribute('data-view'),switchView);
   await panel.locator('[data-move="play"]').click();
   await panel.evaluate(node=>{const replacement=node.cloneNode(true);node.replaceWith(replacement);LTZMovement.mount(replacement.parentElement);});
   assert.equal(await panel.locator('select').inputValue(),'100');
   // Historical heatmaps have no invented timing and still get the same floor view.
   await page.evaluate(()=>{const data=JSON.parse(document.querySelector('[data-movement]').dataset.movement),h={...data.kill_heatmap};delete h.timeline;delete h.floor;const fixture=document.createElement('div');fixture.id='legacyFixture';fixture.innerHTML=LTZMovement.html(null,'legacy',h,600);document.body.append(fixture);LTZMovement.mount(fixture);});
   const legacy=page.locator('#legacyFixture');assert.match(await legacy.textContent(),/Kill timing was not recorded/);
   assert.equal(await legacy.locator('canvas').getAttribute('data-heat-kills'),'30');
   await legacy.locator('input').fill('0');assert.equal(await legacy.locator('canvas').getAttribute('data-heat-kills'),'30');
   await legacy.evaluate(e=>e.remove());
   // Loading artwork holds the data clock; failures then unblock geometry playback.
   let releaseFloor;const loadingFloor=new Promise(resolve=>releaseFloor=resolve);
   await page.route('**/missing-floor.png',async route=>{await loadingFloor;await route.abort();});
   await page.evaluate(()=>{const data=JSON.parse(document.querySelector('[data-movement]').dataset.movement),fixture=document.createElement('div');fixture.id='missingFloorFixture';fixture.innerHTML=LTZMovement.html(data,'missing-floor',data.kill_heatmap,600,()=>'/missing-floor.png');document.body.append(fixture);LTZMovement.mount(fixture);});
   const missing=page.locator('#missingFloorFixture');
   await missing.locator('canvas').evaluate(e=>e.scrollIntoView({block:'center'}));
   await page.clock.runFor(2000);assert.equal(await missing.locator('canvas').getAttribute('data-time'),'0');
   assert.equal(await missing.locator('canvas').getAttribute('data-floor'),'loading');releaseFloor();
   for(let i=0;i<100&&await missing.locator('canvas').getAttribute('data-floor')!=='unavailable';i++)await wait(30);
   assert.equal(await missing.locator('canvas').getAttribute('data-floor'),'unavailable');
   assert.match(await missing.textContent(),/Gamefield artwork is unavailable/);
   await missing.locator('input').fill('600');assert.equal(await missing.locator('canvas').getAttribute('data-heat-kills'),'30');
   assert.equal(await missing.locator('canvas').getAttribute('data-floor'),'unavailable');await missing.evaluate(e=>e.remove());
   await page.clock.resume();await page.reload();await page.locator('.ltzLevelResult [data-movement]').waitFor();
   assert.equal(await page.locator('.ltzLevelResult [data-movement]').evaluate(e=>JSON.parse(e.dataset.movement).duration_s),600);
   await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: 20x/50x/100x complete 600s in 30/12/6s; saved artwork floor, synchronized heatmap and kill flashes, rewind, speed changes, legacy/missing artwork; pause, replay, seek, pointer rotation, zoom, view retention, colors, phone/desktop layout, reload, no browser errors');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);console.error(logs.slice(-4000));process.exitCode=1;});
