const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8127';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.request.post(root+'/__test/command',{data:{action:'reset'}});
  await page.request.post(root+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control:4}});
  await page.goto(root+'/s/green/p/mobile-ltz/');
  await page.waitForFunction(()=>$('connection').textContent==='Connected'&&controlMode==='cue');
  assert.equal(await page.locator('#cuePanel').isVisible(),true);
  assert.equal(await page.locator('#xyzX').isVisible(),false);assert.equal(await page.locator('#xyzY').isVisible(),false);
  assert.ok(await page.locator('.markerNumber:visible').count()>2);
  assert.ok((await page.locator('#markerLabels').textContent()).includes('#44'));
  const checkLabels=async()=>{
   const result=await page.evaluate(()=>{
    const origin=$('world').getBoundingClientRect(),scale=viewport.scale;
    return {offsetMarkers:state.level.sockets.some(s=>s.x!==s.marker_x||s.y!==s.marker_y),
     labels:[...state.level.sockets.map(s=>({id:s.aruco_id,x:s.marker_x,y:s.marker_y,size:s.marker_size})),
      {id:38,x:state.level.core.marker_x,y:state.level.core.marker_y,size:state.level.core.marker_size},
      ...state.mobile_arm.tags.map(t=>({...t,size:42}))].map(marker=>{
       const el=[...$('markerLabels').children].find(el=>el.textContent==='#'+marker.id),box=el.getBoundingClientRect();
       return {id:marker.id,font:parseFloat(getComputedStyle(el).fontSize),
        dx:box.x+box.width/2-(origin.x+marker.x*scale),dy:box.y-(origin.y+(marker.y+marker.size/2)*scale+4)};
      })};
   });
   assert.ok(result.offsetMarkers,'fixture includes codes offset from placement targets');
   for(const label of result.labels){
    assert.equal(label.font,16.5,'marker numbers are 50% larger');
    assert.ok(Math.abs(label.dx)<.1&&Math.abs(label.dy)<.1,`#${label.id} aligns below rendered code: ${JSON.stringify(label)}`);
   }
  };
  await checkLabels();
  await page.evaluate(()=>{viewport.setZoom(2,420,190);viewport.pan(-30,20);syncViewport();});
  await checkLabels();
  await page.evaluate(()=>{viewport.fit();syncViewport();});
  const row=i=>page.locator('.cueRow').nth(i);
  await row(0).locator('[data-field=destination]').selectOption('44');
  await page.locator('#cueAdd').click();await row(1).locator('[data-field=piece]').selectOption('101');await row(1).locator('[data-field=destination]').selectOption('55');
  await page.locator('#cueAdd').click();assert.equal(await page.locator('.cueRow').count(),3);
  await row(2).getByRole('button').click();assert.equal(await page.locator('.cueRow').count(),2);
  const checkBullseyes=async destination=>{
   await page.waitForFunction(id=>{
    const arm=state.mobile_arm,marker=arm.markers.find(m=>m.id===id);
    return $('xyzTargetBullseye').getAttribute('transform')===`translate(${marker.x} ${marker.y}) scale(${1/viewport.scale})`;
   },destination);
   const positions=await page.evaluate(()=>{
    const arm=state.mobile_arm,a=viewport.point(0,0),b=viewport.point(viewport.vw,viewport.vh),marker=arm.markers.find(m=>m.id===arm.cue.rows[arm.cue.index].destination);
    return {actual:$('xyzActualBullseye').getAttribute('transform'),expectedActual:`translate(${arm.tip.x} ${arm.tip.y}) scale(${1/viewport.scale})`,
     guides:$('xyzTargetGuides').getAttribute('d'),expectedGuides:`M${a.x} ${marker.y}H${b.x} M${marker.x} ${a.y}V${b.y}`,
     aligned:$('xyzBullseyes').dataset.aligned,expectedAligned:String(Math.hypot(marker.x-arm.tip.x,marker.y-arm.tip.y)<=2)};
   });
   assert.equal(positions.actual,positions.expectedActual,'red follows actual arm position');
   assert.equal(positions.guides,positions.expectedGuides,'green guides cross the cue destination');
   assert.equal(positions.aligned,positions.expectedAligned,'orange convergence uses the cue destination');
  };
  await page.locator('#cuePlay').click();
  await page.waitForFunction(()=>state.mobile_arm.cue.status==='running');
  await checkBullseyes(44);
  await page.waitForFunction(()=>state.mobile_arm.held_tag===100&&state.mobile_arm.cue.stage==='Move');
  await page.locator('#cuePlay').click();await page.waitForFunction(()=>state.mobile_arm.cue.status==='paused');
  await checkBullseyes(44);
  assert.equal(await page.locator('#xyzZ').isDisabled(),true);assert.equal(await page.locator('#pumpBlow').isDisabled(),true);
  const held=await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints));await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>JSON.stringify(state.mobile_arm.joints)),held);
  await page.locator('#cueMinimize').click();
  assert.equal(await page.locator('#cuePanel').getAttribute('data-minimized'),'true');
  assert.ok((await page.locator('#cuePanel').boundingBox()).height<250,'minimized panel shrinks to its contents');
  assert.equal(await row(0).getAttribute('data-active'),'true');
  assert.equal(await row(0).locator('.cueSummary').textContent(),'100 → 44');
  await page.screenshot({path:'/tmp/mobile-cue-minimized.png'});
  await page.locator('#cuePlay').click();
  await page.waitForFunction(()=>state.mobile_arm.cue.index===1&&state.mobile_arm.cue.status==='running');
  assert.equal(await row(1).getAttribute('data-active'),'true');
  await checkBullseyes(55);
  await page.waitForFunction(()=>state.mobile_arm.cue.status==='completed',null,{timeout:30000});
  assert.equal(await page.evaluate(()=>state.mobile_arm.held_tag),null);
  await page.waitForFunction(()=>$('xyzBullseyes').dataset.aligned==='true');
  assert.ok(await page.evaluate(()=>state.towers.some(t=>t.atom_tag_id===100&&t.aruco_id===44)));
  assert.ok(await page.evaluate(()=>state.towers.some(t=>t.atom_tag_id===101&&t.aruco_id===55)));
  await page.locator('#cueMinimize').click();
  const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
  for(const [width,height] of [[844,390],[390,844],[568,320],[320,568],[1024,768]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(160);
   assert.equal(Math.round((await page.locator('#cuePanel').boundingBox()).width),142,'cue editor has half the original 284px width');
   await checkLabels();
   const selectors=['.identity','.telemetry','#expand','.connectionControls','#xyzHeightControl','#zPresetButtons','#pumpButtons','#xyzPrecision','#cuePanel'];
   const boxes=[];for(const selector of selectors)boxes.push([selector,await page.locator(selector).boundingBox()]);
   await page.screenshot({path:`/tmp/mobile-cue-${width}x${height}.png`});
   for(let i=0;i<boxes.length;i++){
    const [name,a]=boxes[i];assert.ok(a&&a.x>=0&&a.y>=0&&a.x+a.width<=width+.1&&a.y+a.height<=height+.1,`${width}x${height}: ${name} fits ${JSON.stringify(a)}`);
    for(let j=i+1;j<boxes.length;j++)assert.ok(!overlap(a,boxes[j][1]),`${width}x${height}: ${name} overlaps ${boxes[j][0]}`);
   }
   assert.ok(await page.locator('#cueRows').evaluate(el=>el.clientHeight>=28),'rows retain a scrollable viewport');
   assert.ok(await page.locator('#cueRows').evaluate(el=>el.scrollWidth<=el.clientWidth),'row buttons fit without horizontal clipping');
  }
  await page.locator('#cueStop').click();await page.waitForFunction(()=>state.mobile_arm.cue.status==='stopped');
  assert.equal(await page.locator('.cueRow').count(),2);
  await page.locator('#stop').click();
  // Real settings form: stored team IDs replace the hard-coded ownership map.
  const operator=await browser.newPage();operator.on('pageerror',e=>errors.push(e.message));
  await operator.goto(root+'/s/gamemaster/p/photon-game/');
  await operator.waitForFunction(()=>!document.getElementById('save').disabled);
  for(const [id,value] of [['green_piece_1','104'],['green_piece_2','105'],['purple_piece_1','106'],['purple_piece_2','107']])await operator.locator('#'+id).fill(value);
  await operator.locator('#save').click();await operator.waitForFunction(()=>document.getElementById('status').textContent.includes('Saved revision'));
  await page.locator('#connect').click();
  await page.waitForFunction(()=>$('connection').textContent==='Connected'&&state.mobile_arm.tags[0].id===104);
  assert.ok(await page.locator('[data-field=piece]').first().locator('option[value="104"]').count());
  await operator.locator('#green_piece_1').fill('44');await operator.locator('#save').click();
  await operator.waitForFunction(()=>document.getElementById('status').textContent.includes('conflict'));
  assert.equal(await page.evaluate(()=>state.mobile_arm.tags[0].id),104,'invalid settings are atomic');
  await page.locator('#stop').click();
  // Leave the shared test fixture on default IDs for other regression suites.
  await operator.locator('#reset').click();await operator.waitForFunction(()=>document.getElementById('status').textContent.includes('Defaults restored'));
  assert.deepEqual(errors,[]);
  console.log('Cue passed: two placements, pause retains held piece, resume, active/minimized rows, add/remove, Stop, overlays, five layouts, settings IDs and collision rejection.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
