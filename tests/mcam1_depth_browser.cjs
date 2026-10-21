// Isolated browser fixture: all requests are mocked, no hub or hardware access.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const root=path.join(__dirname,'..'), web=path.join(root,'sandboxes/gamemaster/prototypes/mcam1-depth/web');
const output=path.join(root,'output/mcam1-depth-2026-10-19');fs.mkdirSync(output,{recursive:true});
const config={side:'green',horizontal_fov_deg:85,mount_rpy_deg:[180,0,0],camera_offset_mm:[0,0,80],contact_offset_mm:[0,0,0],follows_tool_rotation:true,mounting_confirmed:true,frame_delay_ms:50,timing_uncertainty_ms:20,timing_confirmed:false,min_baseline_mm:10,surface_roi:[.05,.1,.42,.8],atom_roi:[.5,.4,.2,.25],intrinsics:null};
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320"><rect width="480" height="320" fill="#343c45"/><path d="M0 80H480M0 160H480M0 240H480M80 0V320M160 0V320M240 0V320M320 0V320M400 0V320" stroke="#647582"/><rect x="248" y="140" width="72" height="72" fill="#586ea1"/><rect x="266" y="84" width="36" height="65" fill="#161b22"/></svg>';
const preview='data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64');
const fixture={contract:'hhh.mcam1.depth',version:1,automatic_motion_supported:true,status:'ready',observed_at:10,running:true,config,atom:{height_mm:31.5,width_mm:20,length_mm:20},message:'Surface tracked',error:null,camera:{width:480,height:320,frame_id:9,received_at:9.9,preview},motion:{pose:[200,30,44,0],speed_mm_s:18.5,phase:'slowing',pump_mode:'suck'},plane:{inliers:28,rms_mm:.4},plane_age_ms:100,measurement:{frame_id:9,received_at:9.9,preview,baseline_mm:20,interval_ms:900,points:[{x:.2,y:.3,depth_mm:112},{x:.3,y:.4,depth_mm:113}]},attachment:{state:'moves_with_head',reason:'Visual evidence during suction; grip is not pressure-verified'},clearance_if_held_mm:12.5,lens_samples:0};
fixture.measurement.distance_kind='lens_to_point';fixture.measurement.points=[];
for(let y=6;y<320;y+=12)for(let x=6;x<480;x+=12){
  if(x>240&&x<336&&y>60&&y<228)continue; // Unknown co-moving head and Atom.
  const distance=x>60&&x<192&&y>72&&y<228?80:((x-390)/50)**2+((y-180)/70)**2<1?140:240+y*.05;
  fixture.measurement.points.push({x:x/480,y:y/320,distance_mm:distance,depth_mm:distance-5});
}
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:1000}}), errors=[], writes=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
      window.EventSource=class{constructor(){window.depthStream=this;}close(){}};
      window.Worker=class{constructor(){window.depthWorker=this;setTimeout(()=>this.onmessage?.({data:{type:'ready',device:'fixture'}}),10);}postMessage(job){this.job=job;}terminate(){}};
      window.completeDepth=()=>{const w=window.depthWorker,values=Float32Array.from({length:48*32},(_,i)=>1+(i%48)/48+Math.floor(i/48)/64);w.onmessage({data:{type:'result',id:w.job.id,width:48,height:32,values}});};
    });
    await page.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url());
      if(req.method()==='POST'){
        writes.push({path:url.pathname,body:req.postDataJSON()});
        if(url.pathname.endsWith('/api/config')){fixture.config=req.postDataJSON();fixture.plane=null;fixture.measurement=null;fixture.clearance_if_held_mm=null;fixture.status='unavailable';return route.fulfill({json:{config:fixture.config}});}
        if(url.pathname.endsWith('/api/analysis')){fixture.running=req.postDataJSON().running;return route.fulfill({json:fixture});}
        return route.fulfill({status:400,json:{error:'Fixture does not accept this action'}});
      }
      if(url.pathname==='/theme.css')return route.fulfill({contentType:'text/css',body:fs.readFileSync(path.join(root,'hub/theme.css'),'utf8')});
      const name=url.pathname.endsWith('/')?'index.html':path.basename(url.pathname);
      if(['index.html','style.css','app.js'].includes(name))return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,name),'utf8')});
      return route.abort();
    });
    await page.goto('http://depth.test/s/gamemaster/p/mcam1-depth/');
    await page.waitForFunction(()=>window.depthStream?.onmessage);
    const emit=async()=>page.evaluate(s=>{window.lastDepthFixture=s;window.depthStream.onmessage({data:JSON.stringify(s)});},fixture);
    await emit();
    await page.evaluate(()=>{window.fixtureTimer=setInterval(()=>window.depthStream.onmessage({data:JSON.stringify(window.lastDepthFixture)}),100);});
    await page.waitForFunction(()=>document.getElementById('noVideo').hidden);
    await page.waitForFunction(()=>Number(document.getElementById('video').dataset.bricks)>500);
    const pixels=await page.evaluate(()=>{const c=document.getElementById('video').getContext('2d');return [c.getImageData(100,100,1,1).data,c.getImageData(400,280,1,1).data,c.getImageData(280,100,1,1).data].map(a=>Array.from(a));});
    assert.notDeepEqual(pixels[0],pixels[1],'Near and far objects must have different colors');
    assert(pixels[2].slice(0,3).every(c=>c<65),'Unknown head cells must stay dark');
    assert.match(await page.locator('#depthAxis').textContent(),/Distance from camera lens/);
    await page.locator('#fitRange').click();assert(Number(await page.locator('#far').inputValue())<300);
    await page.locator('#brickSize').selectOption('20');assert(Number(await page.locator('#video').getAttribute('data-bricks'))>100);
    await page.locator('#brickSize').selectOption('12');
    assert.match(await page.locator('#clearance').textContent(),/12.5 mm/);
    assert.equal(await page.locator('#attachment').textContent(),'Moves with head');
    assert.match(await page.locator('#motionDetail').textContent(),/slowing/);
    for(const width of [1280,768,390,320]){
      await page.setViewportSize({width,height:1000});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Layout fits at ${width}`);
      assert.equal(await page.locator('h1').count(),1);
      await page.evaluate(()=>clearInterval(window.fixtureTimer));
      await emit();
      await page.screenshot({path:path.join(output,`depth-${width}.png`),fullPage:true,animations:'disabled'});
      await page.evaluate(()=>{window.fixtureTimer=setInterval(()=>window.depthStream.onmessage({data:JSON.stringify(window.lastDepthFixture)}),100);});
    }
    await page.setViewportSize({width:1280,height:1000});
    await page.evaluate(()=>clearInterval(window.fixtureTimer));await emit();
    await page.locator('.viewer').screenshot({path:path.join(output,'depth-bricks-view.png')});
    await page.evaluate(()=>clearInterval(window.fixtureTimer));
    fixture.observed_at=11;await emit();
    await page.waitForFunction(()=>document.getElementById('video').dataset.bricks==='0');
    assert.equal(await page.locator('#depthNotice').isVisible(),true,'Expired depth must not silently show a normal camera view');
    fixture.config.mounting_confirmed=false;fixture.measurement=null;fixture.plane=null;fixture.clearance_if_held_mm=null;await emit();
    assert.match(await page.locator('#mountQuality').textContent(),/no setup needed/);
    fixture.motion=null;fixture.error='Green arm: disconnected';await emit();
    await page.waitForFunction(()=>window.depthWorker?.job);
    await page.evaluate(()=>window.completeDepth());
    await page.waitForFunction(()=>Number(document.getElementById('video').dataset.bricks)>900);
    assert.match(await page.locator('#depthAxis').textContent(),/Relative depth/);
    assert.equal(await page.locator('#near').isVisible(),false,'No made-up millimetre scale in video-only mode');
    assert.equal(await page.locator('#depthNotice').isVisible(),false,'No mount or arm feedback is required for AI depth');
    assert.match(await page.locator('#coverage').textContent(),/estimated bricks/);
    assert.equal(await page.locator('#clearance').textContent(),'—');
    await page.locator('.viewer').screenshot({path:path.join(output,'depth-without-setup.png')});
    fixture.motion={pose:[200,30,44,0],speed_mm_s:18.5,phase:'moving',pump_mode:'off'};fixture.error=null;
    const previousJob=await page.evaluate(()=>window.depthWorker.job.id);
    fixture.measurement={frame_id:10,received_at:10.95,captured_at_estimate:10.95,preview,width:480,height:320,method:'automatic_motion',distance_kind:'lens_to_point',baseline_mm:15,interval_ms:600,points:[]};
    for(let y=2;y<32;y+=4)for(let x=2;x<48;x+=4){const z=1/(.01*(1+x/48+y/64)+.002);fixture.measurement.points.push({x:x/48,y:y/32,depth_mm:z,distance_mm:z});}
    await emit();
    await page.waitForFunction(id=>window.depthWorker.job.id>id,previousJob);
    assert.equal(await page.evaluate(()=>window.depthWorker.job.preview),fixture.measurement.preview);
    await page.evaluate(()=>window.completeDepth());
    await page.waitForFunction(()=>document.getElementById('depthAxis').textContent.includes('AI fitted to arm-motion samples'));
    assert.equal(await page.locator('#near').isVisible(),true,'Consistent same-frame motion anchors can supply millimetres without mount setup');
    assert.equal(await page.locator('#clearance').textContent(),'—','AI scaling cannot invent Atom clearance');
    const scaledJob=await page.evaluate(()=>window.depthWorker.job.id);
    fixture.measurement={...fixture.measurement,frame_id:11,received_at:11.05,captured_at_estimate:11.05,points:[...fixture.measurement.points].map((p,i,a)=>({...p,depth_mm:a[a.length-1-i].depth_mm}))};fixture.observed_at=11.1;
    await emit();await page.waitForFunction(id=>window.depthWorker.job.id>id,scaledJob);await page.evaluate(()=>window.completeDepth());
    await page.waitForFunction(()=>document.getElementById('depthAxis').textContent.includes('Relative depth'));
    assert.equal(await page.locator('#near').isVisible(),false,'Inconsistent motion scale falls back to labelled relative depth');
    fixture.temporal_fusion_supported=true;
    fixture.measurement={...fixture.measurement,frame_id:12,received_at:11.1,captured_at_estimate:11.1,
      fusion:{state:'collecting',combined_points:0,max_views:2,rejected_observations:0},
      points:fixture.measurement.points.map((p,i)=>({...p,track_id:'1:'+i,depth_mm:120,distance_mm:120,views:2}))};
    fixture.observed_at=11.2;await emit();
    assert.equal(await page.locator('#fusionState').textContent(),'Collecting viewpoints');
    await page.locator('#view').selectOption('motion');
    await page.waitForFunction(()=>document.getElementById('frameInfo').textContent.includes('Measured depth'));
    assert.equal(await page.locator('#near').isVisible(),true,'Motion view exposes measurements before AI scale fitting');
    await page.locator('#view').selectOption('depth');
    const stableRange=[await page.locator('#near').inputValue(),await page.locator('#far').inputValue()];
    fixture.measurement={...fixture.measurement,frame_id:13,received_at:11.15,captured_at_estimate:11.15,
      fusion:{state:'refined',combined_points:96,max_views:5,rejected_observations:7},
      points:fixture.measurement.points.map(p=>({...p,views:5}))};await emit();
    await page.waitForFunction(()=>document.getElementById('frameInfo').textContent.startsWith('Motion refined')&&Number(document.getElementById('video').dataset.bricks)<200);
    assert.equal(await page.locator('#fusionState').textContent(),'Motion refined');
    assert.match(await page.locator('#fusionDetail').textContent(),/96 features combined.*5 viewpoints.*7 conflicting/);
    assert.match(await page.locator('#depthAxis').textContent(),/Distance from camera lens/,'Combined geometry must outrank the relative AI map, including a flat screen');
    assert.deepEqual([await page.locator('#near').inputValue(),await page.locator('#far').inputValue()],stableRange,'Distance colors stay on the selected millimetre scale');
    await page.locator('#video').scrollIntoViewIfNeeded();
    const fusedBox=await page.locator('#video').boundingBox();await page.mouse.move(fusedBox.x+fusedBox.width*(2/48),fusedBox.y+fusedBox.height*(2/32));
    assert.match(await page.locator('#brickReadout').textContent(),/120.0 mm.*5 viewpoints/);
    await page.locator('.viewer').screenshot({path:path.join(output,'depth-fused-viewpoints.png')});
    const fusedMeasurement=fixture.measurement;
    fixture.measurement=null;fixture.observed_at=16.2;
    fixture.camera={...fixture.camera,frame_id:100,received_at:16.19,preview:'data:image/svg+xml;base64,'+Buffer.from(svg.replace('#343c45','#cc2233')).toString('base64')};
    fixture.motion={...fixture.motion,pose:[214,30,44,0],speed_mm_s:0,phase:'stopped'};
    fixture.message='Waiting for 10–40 mm of translation with little rotation';
    await emit();await page.locator('#view').selectOption('motion');
    await page.waitForFunction(()=>document.getElementById('frameInfo').textContent.includes('frozen snapshot'));
    assert.match(await page.locator('#frameInfo').textContent(),/5.0 s old/);
    assert.equal(await page.locator('#fusionState').textContent(),'Last measured map');
    assert.equal(Number(await page.locator('#video').getAttribute('data-bricks')),96,'A short motion map remains inspectable after stopping');
    assert.match(await page.locator('#referenceLabel').textContent(),/frozen/);
    assert.deepEqual(await page.evaluate(()=>Array.from(document.getElementById('referenceVideo').getContext('2d').getImageData(10,10,1,1).data)),[52,60,69,255],'Frozen map retains its original camera frame, not the newer red frame');
    await page.locator('.viewer').screenshot({path:path.join(output,'depth-retained-motion.png')});
    fixture.error='Green arm: measured feedback is stale';await emit();
    await page.waitForFunction(()=>document.getElementById('video').dataset.bricks==='0');
    assert.equal(await page.locator('#fusionDetail').textContent(),fixture.error,'Expose the actual blocker instead of generic movement advice');
    assert.equal(await page.locator('#reference').isVisible(),false,'No reference claims to belong to a nonexistent map');
    assert.equal(await page.locator('#depthAxis').textContent(),'No measured distances yet');
    assert.equal(await page.locator('#depthNoticeTitle').textContent(),'Waiting for motion measurements');
    fixture.error=null;fixture.observed_at=16.3;await emit();
    assert.equal(Number(await page.locator('#video').getAttribute('data-bricks')),0,'Recovery must not resurrect discarded evidence');
    assert.match(await page.locator('#motionProgress').textContent(),/Automatic camera direction.*0.0 mm.*needs 10–40 mm/);
    assert.equal(await page.locator('#fusionDetail').textContent(),fixture.message);
    fixture.motion.pose=[228,30,44,0];fixture.observed_at=16.4;await emit();
    assert.match(await page.locator('#motionProgress').textContent(),/14.0 mm from recent views/);
    fixture.measurement={...fusedMeasurement,frame_id:101,received_at:16.39,captured_at_estimate:16.39};await emit();
    await page.waitForFunction(()=>document.getElementById('video').dataset.bricks==='96');
    fixture.measurement=null;fixture.camera.frame_id=1;await emit();
    await page.waitForFunction(()=>document.getElementById('video').dataset.bricks==='0');
    assert.equal(await page.locator('#fusionState').textContent(),'Waiting for measurements','Camera resets clear the old map');
    fixture.config.mounting_confirmed=true;await emit();
    await page.evaluate(()=>{window.fixtureTimer=setInterval(()=>window.depthStream.onmessage({data:JSON.stringify(window.lastDepthFixture)}),100);});
    await page.locator('#surfaceSelect').click();
    assert.equal(await page.locator('#view').inputValue(),'live','Region selection uses the camera image');
    await page.locator('#video').scrollIntoViewIfNeeded();
    const box=await page.locator('#video').boundingBox();
    await page.mouse.move(box.x+box.width*.1,box.y+box.height*.1);await page.mouse.down();
    await page.mouse.move(box.x+box.width*.4,box.y+box.height*.5,{steps:4});await page.mouse.up();
    assert.match(await page.locator('#dirty').textContent(),/Unsaved/);
    await page.locator('#save').click();
    await page.waitForFunction(()=>document.getElementById('actionStatus').textContent.includes('Setup saved'));
    assert.ok(Math.abs(writes[0].body.surface_roi[2]-.3)<.01);
    await emit();assert.equal(await page.locator('#clearance').textContent(),'—');
    await page.locator('#side').selectOption('purple');
    assert.equal(await page.locator('#mountConfirmed').isChecked(),false);
    await page.locator('#run').click(); // Pausing remains possible with unsaved setup edits.
    await page.waitForFunction(()=>document.getElementById('run').textContent==='Start analysis');
    await page.evaluate(()=>window.depthStream.onerror());
    assert.equal(await page.locator('#clearance').textContent(),'—');
    assert.equal(await page.locator('#fusionState').textContent(),'Unavailable');
    await page.locator('#view').selectOption('live');
    assert.equal(await page.locator('#noVideo').isVisible(),true);
    await page.evaluate(()=>clearInterval(window.fixtureTimer));
    await emit();
    await page.waitForFunction(()=>document.getElementById('run').disabled,{timeout:2500});
    assert.equal(await page.locator('#speed').textContent(),'—');
    assert.ok(writes.every(w=>/\/mcam1-depth\/api\/(config|analysis)$/.test(w.path)));
    assert.deepEqual(errors,[]);
    console.log('Passed: measured bricks, video-only relative depth, repeated-view refinement, retained and honestly aged motion snapshots, original-frame pairing, blocker diagnostics, measured travel, source resets, viewport sizes, ROI/save, pause, disconnect clearing, and no hardware requests.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
