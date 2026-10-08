/* Real cue recovery functions; fake time, camera and relay. No physical I/O. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('shared/robot_controls/controller.html','utf8');
function context(){
 let now=10000,delays=0;
 const c={Date:{now:()=>now},TEAM:'green',LTZ:true,AUTO_PPX:true,gameCalibration2:{revision:3},
  autoPpxTagRefreshPromise:null,autoPpxTagRefreshBusy:false,autoPpxCueMap:null,latestVisibleArucoTags:[],
  autoPpxVisionWait:null,autoPpxCueRunning:true,autoPpxAbort:false,
  autoPpxPaused:false,autoPpxPauseGeneration:0,autoPpxClickOverride:null,autoPpxClickOverrideGeneration:0,
  activeOperation:{operation_id:'pickup-one',physical_tag:100},mobileGame:{movable_piece_codes:{green:[100,101]}},
  window:{},gid:()=>({checked:false}),gameDisplayTag:t=>t,selectedAutoPpxCalibration:()=> 'cal2',
  loadGameCalibration2:async()=>{},renderAutoPpxTagOptions(){},updateAutoPpxControls(){},setAutoPpxStatus(){},
  mobileRobotReady:()=>true,waitForAutoPpxResume:async()=>{},autoPpxTagInsideActiveArea:()=>true,
  clickToPose:(x,y)=>({x:x*1000,y:y*1000,z:0}),autoPpxOffsetPose:p=>p,
  delay:async ms=>{if(++delays>200)throw Error('Test exceeded camera recovery delay budget');now+=ms;},tick:ms=>{now+=ms;},now:()=>now};
 vm.createContext(c);
 vm.runInContext(html.slice(html.indexOf('function autoPpxClearViewRow('),html.indexOf('async function captureAutoPpxQueuePoses(')),c);
 for(const [a,b] of [['function autoPpxCueMapKey()', 'async function activeGameTags()'],
                     ['function assertAutoPpxVisionSession()', 'async function refreshAutoPpxPhysicalEndpoint(']])
  vm.runInContext(html.slice(html.indexOf(a),html.indexOf(b)),c);
 c.observe=tags=>{c.autoPpxCueMap={status:'ready',frameAtLocal:now,calibrationRevision:c.gameCalibration2.revision,scope:'layout',epoch:'camera'};c.latestVisibleArucoTags=tags;};
 c.tag=(id,extra={})=>({id,nx:.3,ny:.4,fixed:id<100,visible:true,stable:true,lastSeenAt:now,...extra});
 return c;
}
// Exercise acquisition with the actual Cal 2 transforms, rather than the simple
// coordinate stub used by recovery-only cases. Different layers/arms deliberately
// disagree so a missing, doubled or wrong-arm correction cannot pass unnoticed.
function calibratedContext(team,rotated,c=context()){
 const samples=[[.2,.2],[.5,.2],[.8,.2],[.2,.8],[.5,.8],[.8,.8]];
 const arm=side=>({pickup_height:side==='green'?-100:-95,transport_height:-55,stack_drop_offset:31.5,
  points:Object.fromEntries(samples.map(([u,v],i)=>[i,{camera:{u,v},pose:{set:true,x:250+u*150+(side==='purple'?15:0),y:(v-.5)*100}}])),
  parallax_points:Object.fromEntries([[.2,.2],[.8,.2],[.2,.8],[.8,.8]].map(([u,v],i)=>[i,
   {ground:{u,v},raised:{u:u+(side==='green'?.04:-.03),v:v+.02}}]))});
 Object.assign(c,{TEAM:team,LTX:true,gameRadiusMin:220,gameRadiusMax:439,AUTO_PP_BASE_SAFE_RADIUS:220,
  AUTO_PP_PHYSICAL_TAG_HEIGHT_MM:31.5,gameReachWorkspace:{x:[-450,450],y:[-450,450]},ws:{z:[-150,230]},
  sliderEls:{z:{value:-55}},cal2PlanningBoundaryCache:null,cal2JointGuardCache:null,
  gameCalibration2:{revision:3,arms:{green:arm('green'),purple:arm('purple')}},
  gameDisplayPoint:(u,v)=>rotated?{u:1-u,v:1-v}:{u,v},
  gid:id=>({checked:id==='flipToggle'&&rotated,value:0,querySelectorAll:()=>[]}),autoPpxFineCalCorrection:()=>({dx:0,dy:0,dz:0})});
 c.gameArmCal2=(side=c.TEAM)=>c.gameCalibration2.arms[side];
 for(const [from,to] of [['function cal2MotionLimit(', 'function clipLtxArmSegment('],
  ['function cal2ConfiguredReach(', 'function cal2ReachBoundary('],
  ['function compensateCal2Parallax(', 'function syncTargetSliders('],
  ['function cal2RobotPlanningBoundary(', 'function cal2PathViolations('],
  ['function pointInsideRobotPolygon(', 'function jointPoseInsideCal2('],
  ['function autoPpxTune(', 'async function captureAutoPpxPoses(']])
  vm.runInContext(html.slice(html.indexOf(from),html.indexOf(to)),c);
 c.evidence=(id,u,v,extra={})=>{const p=c.gameDisplayPoint(u,v);return c.tag(id,{nx:p.u,ny:p.v,...extra});};
 c.diagnostics=[];c.window.mobileArmDiagnostic=(event,reason,details)=>c.diagnostics.push({event,reason,...details});
 return c;
}
test('100-series pickup and every 40/50-series drop retain their own calibration layer on both arms and views',async()=>{
 for(const team of ['green','purple'])for(const rotated of [false,true]){
  const c=calibratedContext(team,rotated),shift=team==='green'?.04:-.03;
  for(let id=40;id<60;id++){
   const physical=[100,105,150,199][id%4],saved={sourceTag:{id:physical},targetTag:{id}};
   c.activeOperation={operation_id:'row-'+id,physical_tag:physical};
   // The raised centre and flat centre represent the same physical XY point.
   const observed=[c.evidence(physical,.5+shift,.52),c.evidence(id,.5,.5)];
   c.refreshAutoPpxTags=async()=>c.observe(observed);
   const source=c.createAutoPpxEndpointResolver(saved,'source',id-40);
   const destination=c.createAutoPpxEndpointResolver(saved,'target',id-40);
   await source();await destination();
   const expectedX=team==='green'?325:340;
   for(const endpoint of ['source','target']){
    assert(Math.abs(saved[endpoint].x-expectedX)<1e-6,`${team} ${endpoint} #${id} X`);
    assert(Math.abs(saved[endpoint].y)<1e-6);
   }
   const pickupZ=team==='green'?-100:-95;
   assert.equal(c.autoPpxPickupZForPose(saved.sourceBase),pickupZ);
   assert.equal(c.autoPpxDropZForTarget(saved.targetBase,saved.targetTag),pickupZ+1,'Flat destinations never add the carried Atom height');
   // Approach/occlusion reuses independently retained source/destination poses.
   c.observe([]);await source();await destination();
   assert(Math.abs(saved.source.x-expectedX)<1e-6);assert(Math.abs(saved.target.x-expectedX)<1e-6);
   const records=c.diagnostics.filter(d=>d.event==='cue_target_acquired').slice(-2);
   assert.deepEqual(records.map(d=>d.calibration_layer),['raised-tag','ground']);
   for(const d of records){assert.equal(d.calibration_revision,3);assert.equal(d.placement_offset_mm,0);assert.equal(d.tuning_offset_mm,0);}
  }
 }
});
test('missing raised calibration stops a 100-series pickup while flat 40/50 destinations remain mapped',async()=>{
 const c=calibratedContext('green',false);c.gameArmCal2().parallax_points={};
 const saved={sourceTag:{id:100},targetTag:{id:59}};
 c.refreshAutoPpxTags=async()=>c.observe([c.evidence(100,.54,.52),c.evidence(59,.5,.5)]);
 await c.waitForAutoPpxMappedEndpoint(saved,'target',0);assert(Math.abs(saved.target.x-325)<1e-6);
 await assert.rejects(c.waitForAutoPpxMappedEndpoint(saved,'source',0),/Four raised-Atom/);
 assert.equal(saved.source,undefined);
});
test('a stacked drop uses the destination 100-series layer and reports additional XY tuning separately',async()=>{
 const c=calibratedContext('purple',true),saved={sourceTag:{id:100},targetTag:{id:103}};
 c.autoPpxFineCalCorrection=()=>({dx:3,dy:4,dz:0});
 c.refreshAutoPpxTags=async()=>c.observe([c.evidence(103,.47,.52)]);
 await c.createAutoPpxEndpointResolver(saved,'target',0)();
 assert(Math.abs(saved.targetBase.x-340)<1e-6);assert(Math.abs(saved.target.x-343)<1e-6);
 assert.equal(c.autoPpxDropZForTarget(saved.targetBase,saved.targetTag),-95+1+31.5);
 const record=c.diagnostics.at(-1);assert.equal(record.calibration_layer,'raised-tag');assert(Math.abs(record.tuning_offset_mm-5)<1e-9);
});
test('full cue execution commands raised-layer pickups and ground-layer 40/50 drops through release',async()=>{
 for(const team of ['green','purple'])for(const rotated of [false,true]){
  const rows=[{sourceTag:{id:100},targetTag:{id:42}},{sourceTag:{id:101},targetTag:{id:54}}];
  const c=calibratedContext(team,rotated,queueContext(rows)),hidden=new Set(),shift=team==='green'?.04:-.03;
  c.refreshAutoPpxTags=async()=>c.observe([
   c.evidence(42,.62,.45),c.evidence(54,.62,.45),
   ...[100,101].filter(id=>!hidden.has(id)).map(id=>c.evidence(id,.5+shift,.52))]);
  c.onMove=async label=>{if(label==='source hover'){hidden.add(c.activeOperation.physical_tag);await c.refreshAutoPpxTags();}};
  await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed',c.autoPpxCueError?.message);
  const pickupZ=team==='green'?-100:-95,armOffset=team==='green'?0:15;
  for(const move of c.moves.filter(m=>m.label==='source pickup'||m.label==='target drop')){
   const pickup=move.label==='source pickup';
   assert(Math.abs(move.pose.x-((pickup?325:343)+armOffset))<1e-6);
   assert(Math.abs(move.pose.y-(pickup?0:-5))<1e-6);
   assert.equal(move.pose.z,pickup?pickupZ:pickupZ+1);
  }
  const releases=c.events.filter(e=>e.name==='release_completed');assert.equal(releases.length,2);
  for(const event of releases){assert(Math.abs(event.release_pose.x-(343+armOffset))<1e-6);assert.equal(event.release_pose.z,pickupZ+1);}
 }
});
test('concurrent strict refresh awaits the in-flight camera read',async()=>{
 const c=context();let release,reads=0;
 c.readAutoPpxCueTargets=async()=>{reads++;await new Promise(r=>release=r);c.observe([c.tag(42)]);return c.latestVisibleArucoTags;};
 const first=c.refreshAutoPpxTags(),second=c.refreshAutoPpxTags({strict:true});
 await new Promise(setImmediate);assert.equal(reads,1);
 let settled=false;second.then(()=>settled=true);await new Promise(setImmediate);assert(!settled);
 release();assert.equal((await first)[0].id,42);await second;assert(settled);
});
test('failed in-flight refresh cannot pass strict cue validation using old data',async()=>{
 const c=context();c.observe([c.tag(42)]);c.readAutoPpxCueTargets=async()=>{throw Error('camera unavailable');};
 const first=c.refreshAutoPpxTags();await assert.rejects(c.refreshAutoPpxTags({strict:true}),/camera unavailable/);await first;
});
test('fixed destinations survive occlusion but a missing moving source waits and remaps',async()=>{
 const c=context(),saved={sourceTag:{id:100},targetTag:{id:42}};let polls=0,prompts=[];
 c.setAutoPpxStatus=text=>prompts.push(text);
 c.refreshAutoPpxTags=async()=>{polls++;c.observe(polls<3?[c.tag(42,{visible:false,lastSeenAt:1})]:[c.tag(100,{nx:.7}),c.tag(42)]);};
 await c.waitForAutoPpxMappedEndpoint(saved,'target',0);assert.equal(polls,1);assert.equal(saved.target.x,300);
 await c.waitForAutoPpxMappedEndpoint(saved,'source',0);assert.equal(saved.source.x,700);
 assert(prompts.some(t=>/Atom battery/.test(t)));assert.equal(c.autoPpxVisionWait,null);
});
test('qualified flickering sightings can acquire within 750 ms without inventing a live sighting',async()=>{
 const c=context(),saved={sourceTag:{id:100}};let reads=0;
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100,{visible:false,stable:false,acquirable:true,lastSeenAt:c.now()-600})]);};
 await c.waitForAutoPpxMappedEndpoint(saved,'source',0);assert.equal(reads,1);assert.equal(saved.source.x,300);
 assert.equal(saved.sourceTag.visible,false);assert.equal(saved.sourceTag.lastSeenAt,c.now()-600);
});
test('a visible but unqualified Atom says confirming, and expired evidence cannot start an approach',async()=>{
 const c=context(),saved={sourceTag:{id:100}},messages=[];let reads=0;
 c.setAutoPpxStatus=message=>messages.push(message);
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100,{acquirable:reads!==1,lastSeenAt:c.now()-(reads===2?800:100),nx:reads<3?.3:.6})]);};
 await c.waitForAutoPpxMappedEndpoint(saved,'source',0);assert.equal(reads,3);assert.equal(saved.source.x,600);
 assert(messages.some(t=>/Confirming piece #100/.test(t)));assert(!messages.some(t=>/battery/.test(t)));
});
test('click intervention invalidates the response in flight and waits until movement settles',async()=>{
 const c=context(),saved={sourceTag:{id:100}};let reads=0,settled=false;
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100,{nx:reads===1?.3:.8})]);if(reads===1){c.autoPpxClickOverrideGeneration++;c.autoPpxClickOverride={id:1};}};
 c.waitForAutoPpxResume=async()=>{if(c.autoPpxClickOverride){settled=true;c.autoPpxClickOverride=null;}};
 await c.waitForAutoPpxMappedEndpoint(saved,'source',2);
 assert(settled);assert.equal(reads,2);assert.equal(saved.source.x,800);
});
test('Stop during a camera request prevents a late response from resuming the cue',async()=>{
 const c=context(),saved={sourceTag:{id:100}};
 c.refreshAutoPpxTags=async()=>{c.observe([c.tag(100)]);c.autoPpxAbort=true;};
 await assert.rejects(c.waitForAutoPpxMappedEndpoint(saved,'source',0),/stopped/);assert.equal(saved.source,undefined);
});
test('known occupied fixed destination waits until the blocking Atom moves away',async()=>{
 const c=context(),saved={sourceTag:{id:100},targetTag:{id:42}};let reads=0,prompts=[];
 c.setAutoPpxStatus=text=>prompts.push(text);
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(42,{covered_by:reads<3?[103]:[]})]);};
 await c.waitForAutoPpxMappedEndpoint(saved,'target',0);assert.equal(reads,3);
 assert(prompts.some(t=>t.includes('covered by an Atom')));
});
test('reach rejection identifies the destination instead of asking to reveal the source',async()=>{
 const c=context(),saved={sourceTag:{id:100},targetTag:{id:45}};let reads=0,prompts=[];
 c.setAutoPpxStatus=text=>prompts.push(text);
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100),c.tag(45)]);};
 c.clickToPose=()=>{if(reads===1)throw Object.assign(Error('inside the red Cal 2 exclusion area'),{code:'motion_limit'});return {x:300,y:200,z:80};};
 await c.waitForAutoPpxMappedEndpoint(saved,'target',0);
 assert.equal(reads,2);assert(prompts.some(t=>/Row 1: destination #45 is mapped/.test(t)&&/red Cal 2/.test(t)));
 assert(!prompts.some(t=>/Waiting for piece #100|reveal the tag/.test(t)));
});
test('cue capture defers all pose conversion until the active row acquires its endpoints',async()=>{
 const c=context();let conversions=0;
 c.refreshGameField=async()=>{};c.autoPpxQueueIds=()=>[{source:'100',target:'42'},{source:'101',target:'45'}];
 c.refreshAutoPpxTags=async()=>[c.tag(100),c.tag(42),c.tag(101),c.tag(45)];
 c.clickToPose=()=>{conversions++;throw Error('A later row is unreachable');};
 vm.runInContext(html.slice(html.indexOf('async function captureAutoPpxQueuePoses('),html.indexOf('function autoPpxIsPhysicalTag(')),c);
 const rows=await c.captureAutoPpxQueuePoses();assert.equal(rows.length,2);assert.equal(conversions,0);
 assert(rows.every(row=>row.sourceBase===null&&row.targetBase===null));
});
test('cue capture preserves Clear view between placements from the submitted program',async()=>{
 const c=context();
 c.refreshGameField=async()=>{};
 c.autoPpxQueueIds=()=>{throw Error('The typed program must not be replaced by controller selects');};
 c.refreshAutoPpxTags=async()=>[c.tag(100),c.tag(42),c.tag(101),c.tag(45)];
 vm.runInContext(html.slice(html.indexOf('async function captureAutoPpxQueuePoses('),html.indexOf('function autoPpxIsPhysicalTag(')),c);
 const rows=await c.captureAutoPpxQueuePoses([{piece:100,destination:42},{action:'clear_view'},{piece:101,destination:45}]);
 assert.equal(rows.length,3);assert.equal(rows[0].sourceTag.id,100);
 assert.equal(JSON.stringify(rows[1]),'{"action":"clear_view","direction":"left","distance_cm":5}');
 assert.equal(rows[2].sourceTag.id,101);assert.equal(rows[2].targetTag.id,45);
});
test('height override waits for the pump, holds, then uses measured XY without lifting or detouring',async()=>{
 const c=context(),calls=[];let releasePump;
 c.waitForAutoPpxCueAtomic=async()=>new Promise(resolve=>releasePump=resolve);
 c.autoPpxClickOverrideWasSuperseded=()=>false;c.throwIfMotionInterrupted=fn=>{if(fn())throw Error('superseded');};
 c.api=async path=>{calls.push(path);return path==='/api/status'?{pose:[315,140,52]}:{ok:true};};
 c.assertAutoPpxPoseSafe=()=>{};c.moveToPose=async(p,label,wait,options)=>calls.push({p,label,wait,options});
 vm.runInContext(html.slice(html.indexOf('async function performAutoPpxClickOverride('),html.indexOf('async function handleVideoClick(')),c);
 const pending=c.performAutoPpxClickOverride({x:999,y:999,z:60},{id:1},{heightOnly:true});
 await new Promise(setImmediate);assert.equal(calls.length,0);releasePump();
 const actual=await pending;assert.deepEqual({...actual},{x:315,y:140,z:60});
 assert.deepEqual(calls.slice(0,2),['/api/stop','/api/status']);
 assert.equal(calls.length,3);assert.equal(calls[2].options.allowDetour,false);assert.equal(calls[2].wait,true);
 assert.equal(calls[2].label,'video override height');
});
test('image recovery during a tag-map hold lifts and moves through the existing override without changing suction',async()=>{
 for(const paused of [false,true]){
  const c=context(),calls=[],override={id:1};let releasePump;
  c.autoPpxPaused=paused;c.autoPpxCueMap={status:'unavailable',pending_fixed_ids:[54]};
  c.waitForAutoPpxCueAtomic=async()=>new Promise(resolve=>releasePump=resolve);
  c.autoPpxClickOverrideWasSuperseded=()=>false;c.throwIfMotionInterrupted=fn=>{if(fn())throw Error('superseded');};
  c.autoPpxTransportZ=()=>80;
  c.api=async path=>{calls.push(path);assert.equal(path,'/api/status','Recovery must not release suction');return {pose:[315,140,52],pump_mode:'suck'};};
  c.moveToPose=async(p,label,wait,options)=>calls.push({p,label,wait,options});
  vm.runInContext(html.slice(html.indexOf('async function performAutoPpxClickOverride('),html.indexOf('async function handleVideoClick(')),c);
  const pending=c.performAutoPpxClickOverride({x:400,y:200,z:60},override);
  await new Promise(setImmediate);assert.equal(calls.length,0);releasePump();
  const result=await pending;
  assert.deepEqual({...calls[1].p},{x:315,y:140,z:80});assert.equal(calls[1].label,'video override lift');
  assert.deepEqual({...result},{x:400,y:200,z:80});assert.equal(calls[2].label,'video target');
  assert(calls[1].wait&&calls[2].wait);assert.equal(calls[2].options.clickOverride,override);
  assert.equal(c.autoPpxPaused,paused);assert.equal(c.autoPpxCueMap.status,'unavailable','A recovery move does not certify the tag map');
 }
});
test('a superseded height override or failed hold cannot send its movement',async()=>{
 for(const failure of ['superseded','hold']){
  const c=context();let stale=false,moves=0;
  c.waitForAutoPpxCueAtomic=async()=>{};c.autoPpxClickOverrideWasSuperseded=()=>stale;
  c.throwIfMotionInterrupted=fn=>{if(fn())throw Error('superseded');};
  c.api=async()=>{stale=failure==='superseded';return {ok:failure!=='hold',error:'hold rejected'};};
  c.moveToPose=async()=>moves++;
  vm.runInContext(html.slice(html.indexOf('async function performAutoPpxClickOverride('),html.indexOf('async function handleVideoClick(')),c);
  await assert.rejects(c.performAutoPpxClickOverride({z:60},{id:1},{heightOnly:true}),/superseded|hold rejected/);
  assert.equal(moves,0);
 }
});
test('camera failure during motion holds without touching the pump and replans',async()=>{
 const c=context();let attempts=0,resolutions=0,calls=[];
 vm.runInContext(html.slice(html.indexOf('const AUTO_PPX_CUE_MOTION_LABELS ='),html.indexOf('async function moveToPoseAttempt(')),c);
 c.cal2BoundaryStop=null;c.log=()=>{};c.api=async path=>{calls.push(path);return {ok:true};};
 c.moveToPoseAttempt=async(p,label,wait,options)=>{
  if(++attempts===1){c.autoPpxCueMap.status='unavailable';assert(options.interruptWhen());throw Object.assign(Error('interrupted'),{motionInterrupted:true});}
  return p;
 };
 const result=await c.moveToPose({},'source hover',true,{resolveTarget:async()=>{resolutions++;c.observe([]);return {x:resolutions*100,y:0,z:80};}});
 assert.equal(result.x,200);assert.equal(resolutions,2);assert.deepEqual(calls,['/api/stop']);
});
test('a map recovered between interruption and catch still holds without invalidating its retained target',async()=>{
 const c=context();let attempts=0,holds=0,invalidations=0;
 vm.runInContext(html.slice(html.indexOf('const AUTO_PPX_CUE_MOTION_LABELS ='),html.indexOf('async function moveToPoseAttempt(')),c);
 c.cal2BoundaryStop=null;c.log=()=>{};c.api=async()=>{holds++;return {ok:true};};
 c.moveToPoseAttempt=async(p,label,wait,options)=>{
  if(++attempts===1){
   c.autoPpxCueMap.status='unavailable';assert(options.interruptWhen());
   c.observe([]);throw Object.assign(Error('interrupted'),{motionInterrupted:true});
  }
  return p;
 };
 await c.moveToPose({},'source hover',true,{resolveTarget:async()=>{c.observe([]);return {x:300,y:0,z:80};},invalidateTarget:()=>invalidations++});
 assert.equal(holds,1);assert.equal(invalidations,0);assert.equal(attempts,2);
});
test('a player override takes priority over a simultaneous camera hold',async()=>{
 const c=context();let attempts=0,holds=0;
 vm.runInContext(html.slice(html.indexOf('const AUTO_PPX_CUE_MOTION_LABELS ='),html.indexOf('async function moveToPoseAttempt(')),c);
 c.cal2BoundaryStop=null;c.log=()=>{};c.api=async()=>{holds++;return {ok:true};};
 c.moveToPoseAttempt=async(p,label,wait,options)=>{
  if(++attempts===1){
   c.autoPpxCueMap.status='unavailable';c.autoPpxClickOverrideGeneration++;
   assert(options.interruptWhen());throw Object.assign(Error('interrupted'),{motionInterrupted:true});
  }
  return p;
 };
 await c.moveToPose({},'source hover',true,{resolveTarget:async()=>{c.observe([]);return {x:300,y:0,z:80};}});
 assert.equal(holds,0,'Cue recovery must not stop the player override');assert.equal(attempts,2);
});
test('a moving Atom changing position interrupts its old motion target',async()=>{
 const c=context();let attempts=0,resolutions=0,holds=0;
 vm.runInContext(html.slice(html.indexOf('const AUTO_PPX_CUE_MOTION_LABELS ='),html.indexOf('async function moveToPoseAttempt(')),c);
 c.cal2BoundaryStop=null;c.log=()=>{};c.api=async()=>{holds++;return {ok:true};};
 c.moveToPoseAttempt=async(p,label,wait,options)=>{
  if(++attempts===1){c.tick(600);c.observe([c.tag(100,{nx:.7,acquirable:true})]);assert(options.interruptWhen());throw Object.assign(Error('moved'),{motionInterrupted:true});}
  return p;
 };
 await c.moveToPose({},'source pickup',true,{resolveTarget:async()=>{resolutions++;c.observe([c.tag(100,{nx:resolutions===1?.3:.7})]);return {};},endpointTag:()=>c.latestVisibleArucoTags[0]});
 assert.equal(resolutions,2);assert.equal(holds,1);
});
test('a recent contradictory position survives a missed frame and invalidates the retained approach',()=>{
 const c=context(),acquired=c.tag(100);c.tick(800);
 c.observe([c.tag(100,{nx:.7,visible:false,stable:false,acquirable:true,lastSeenAt:c.now()-600})]);
 assert(c.autoPpxCueEndpointChanged(acquired));
 c.tick(200);assert(!c.autoPpxCueEndpointChanged(acquired),'Expired positions cannot assert new movement');
});
test('an acquired Atom remains usable during this approach after its detection disappears',async()=>{
 const c=context(),saved={sourceTag:{id:100}};let reads=0;
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100)]);};
 const resolve=c.createAutoPpxEndpointResolver(saved,'source',0);
 await resolve();c.tick(20000);c.observe([]);await resolve();
 assert.equal(reads,1);assert.equal(saved.source.x,300);
 assert.equal(c.autoPpxCueEndpointChanged(saved.sourceTag),false);
});
test('each row needs a new observation, even with the same Atom and same saved queue object',async()=>{
 const c=context(),saved={sourceTag:{id:100}};
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(100)]);
 const first=c.createAutoPpxEndpointResolver(saved,'source',0);await first();
 const oldTag=c.latestVisibleArucoTags[0];c.tick(10);
 c.activeOperation={operation_id:'pickup-two',physical_tag:100};let reads=0,waits=0;
 c.refreshAutoPpxTags=async()=>c.observe(++reads===1?[oldTag]:[c.tag(100,{nx:.7})]);
 c.delay=async()=>{waits++;};
 await c.createAutoPpxEndpointResolver(saved,'source',1)();
 assert.equal(waits,1,'Even a 10ms-old previous-row sighting is not the new acquisition');
 assert.equal(saved.source.x,700);
 await assert.rejects(first(),/stopped/);
});
test('intervention, changed mapping identity and confirmed movement invalidate with an explicit reason',async()=>{
 for(const change of ['click','mapping','epoch','movement']){
  const c=context(),saved={sourceTag:{id:100}},diagnostics=[];let reads=0;
  c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
  c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100,{nx:reads===1?.3:.7})]);};
  const resolve=c.createAutoPpxEndpointResolver(saved,'source',0);await resolve();
  c.tick(600);
  if(change==='click')c.autoPpxClickOverrideGeneration++;
  if(change==='mapping')c.gameCalibration2.revision++;
  if(change==='epoch')Object.assign(c.autoPpxCueMap,{epoch:'new-camera',epoch_reason:'fixed_marker_changed',epoch_marker_id:42});
  if(change==='movement')c.observe([c.tag(100,{nx:.7,acquirable:true})]);
  await resolve();assert.equal(saved.source.x,700,change);
  assert.equal(diagnostics.filter(e=>e.event==='cue_target_invalidated').length,1);
  assert.equal(diagnostics.find(e=>e.event==='cue_target_invalidated').phase,
   change==='click'?'player_intervention':change==='movement'?'endpoint_changed':'mapping_changed');
  if(change==='epoch')assert.match(diagnostics.find(e=>e.event==='cue_target_invalidated').reason,/camera\/map epoch; fixed marker #42 moved/);
 }
});
test('camera expiry and unavailable polls preserve an occluded endpoint until the same map recovers',async()=>{
 for(const endpoint of ['source','target'])for(const failure of ['expired','unavailable','sse']){
  const c=context(),saved={sourceTag:{id:100},targetTag:{id:103}},diagnostics=[],messages=[];let reads=0;
  c.setAutoPpxStatus=text=>messages.push(text);
  c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
  c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100),c.tag(103,{nx:.8})]);};
  const resolve=c.createAutoPpxEndpointResolver(saved,endpoint,0);await resolve();
  const acquired={...saved[endpoint]},lastSeen=saved[endpoint==='source'?'sourceTag':'targetTag'].lastSeenAt;
  saved[endpoint].x=999; // Retained robot coordinates are independent of the row's mutable view.
  if(failure==='expired')c.tick(1600);
  if(failure==='unavailable')c.autoPpxCueMap.status='unavailable';
  if(failure==='sse')c.mobileGame.mobile_cue_targets={status:'unavailable'};
  c.refreshAutoPpxTags=async()=>{
   reads++;
   if(reads===2)throw Error('Temporary mapping failure');
   c.observe([]);delete c.mobileGame.mobile_cue_targets;
  };
  await resolve();assert.equal(reads,3);
  assert.deepEqual({...saved[endpoint]},acquired);
  assert.equal(saved[endpoint==='source'?'sourceTag':'targetTag'].lastSeenAt,lastSeen,'No invented fresh sighting');
  assert(diagnostics.some(e=>e.event==='cue_waiting'&&e.phase==='camera_retained'));
  assert(diagnostics.some(e=>e.event==='cue_mapping_recovered'));
  assert.match(messages.at(-1),/Camera mapping recovered\. Resuming/);
  assert(!diagnostics.some(e=>e.event==='cue_target_invalidated'));
 }
});
test('a single displaced unqualified detection does not discard the acquired source',async()=>{
 const c=context(),saved={sourceTag:{id:100}};let reads=0;
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(100,{acquirable:true})]);};
 const resolve=c.createAutoPpxEndpointResolver(saved,'source',0);await resolve();c.tick(100);
 c.observe([c.tag(100,{nx:.306,acquirable:false,stable:false})]);
 assert(!c.autoPpxCueEndpointChanged(saved.sourceTag));await resolve();
 assert.equal(reads,1);assert.equal(saved.source.x,300);
 c.observe([]);await resolve();assert.equal(reads,1);
});
test('Stop or loss of the physical connection during map recovery prevents resume',async()=>{
 for(const failure of ['stop','connection','operation']){
  const c=context(),saved={sourceTag:{id:100}};
  c.refreshAutoPpxTags=async()=>c.observe([c.tag(100)]);
  const resolve=c.createAutoPpxEndpointResolver(saved,'source',0);await resolve();c.autoPpxCueMap.status='unavailable';
  c.refreshAutoPpxTags=async()=>{
   c.observe([]);
   if(failure==='stop')c.autoPpxAbort=true;
   if(failure==='connection')c.mobileRobotReady=()=>false;
   if(failure==='operation')c.activeOperation={operation_id:'replacement'};
  };
  await assert.rejects(resolve(),/stopped|Connect to resume/);
 }
});
test('a missing Atom destination is retained only for its current drop approach',async()=>{
 const c=context(),saved={sourceTag:{id:100},targetTag:{id:103}};let reads=0;
 c.refreshAutoPpxTags=async()=>{reads++;c.observe([c.tag(103,{nx:.8})]);};
 const resolve=c.createAutoPpxEndpointResolver(saved,'target',0);await resolve();
 c.tick(5000);c.observe([]);await resolve();assert.equal(reads,1);assert.equal(saved.target.x,800);
 c.autoPpxAbort=true;await assert.rejects(resolve(),/stopped/);
});

// Run the actual queue loop and endpoint resolution, replacing only hardware,
// DOM and calibration geometry. Every move and pump command is recorded.
function queueContext(rows){
 const c=context();let counter=0,pose={x:100,y:200,z:80};const events=[],moves=[],pump=[];
 Object.assign(c,{events,moves,pump,crypto:{randomUUID:()=>String(++counter)},AUTO_PP_DROP_TOLERANCE_MM:3,
  autoPpxRunning:false,autoPpxCueOutcome:'idle',cal2BoundaryStop:null,gid:()=>({checked:false,querySelectorAll:()=>[]}),
  cancelAutoPpxClickOverride(){c.autoPpxClickOverride=null;},updateAutoPpxPauseControl(){},assertReadyForAutoAction(){},
  autoPpxQueueIds:()=>rows.map(r=>r.action==='clear_view'?{action:'clear_view'}:{source:r.sourceTag.id,target:r.targetTag.id}),captureAutoPpxQueuePoses:async()=>rows,
  autoPpxTransportZ:()=>80,autoPpxPickupZForPose:()=>20,autoPpxDropZForTarget:()=>25,
  autoPpxIsPhysicalTag:t=>t.id>=100,preflightAutoPpxQueue:async()=>{},updateAutoZReadout(){},log(){},
  runAutoPpxCueAtomic:async(label,fn)=>fn(),
  poseError:(actual,target)=>({max:Math.max(...['x','y','z'].map((axis,i)=>Math.abs(actual[i]-target[axis])))}),
  poseWithinTolerance:(error,tolerance)=>error.max<=tolerance,poseErrorText:error=>String(error?.max),
  laserIntent:async(name,data)=>events.push({name,...data}),
  setPumpMode:async(mode,label)=>{pump.push({mode,label});return {ok:true,command_seq:pump.length,pose:[pose.x,pose.y,pose.z]};},
  api:async(path)=>{if(path==='/api/status')return {pose:[pose.x,pose.y,pose.z],pump_mode:pump.at(-1)?.mode||'off'};assert.equal(path,'/api/stop');return {ok:true};},
  moveToPoseAttempt:async(p,label,wait,options)=>{
   moves.push({label,pose:{...p},row:c.activeOperation.queue_index});pose={...p};
   if(c.onMove)await c.onMove(label,options);
   if(options.interruptWhen?.())throw Object.assign(Error('interrupted'),{motionInterrupted:true});
   return {...p};
  }
 });
 vm.runInContext(html.slice(html.indexOf('const AUTO_PPX_CUE_MOTION_LABELS ='),html.indexOf('async function moveToPoseAttempt(')),c);
 vm.runInContext(html.slice(html.indexOf('async function ensureAutoPpxPickupReady('),html.indexOf('function requireScopedPumpReceipt(')),c);
 c.refreshAutoPpxPhysicalEndpoint=(saved,endpoint,index)=>c.waitForAutoPpxMappedEndpoint(saved,endpoint,index);
 vm.runInContext(html.slice(html.indexOf('function autoPpxClearViewTarget('),html.indexOf('async function stopAutoPpx()')),c);
 return c;
}
test('a completed saved cue runs again and acquires the piece at its new camera position',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}}]);let hidden=false,sourceX=.3;
 c.autoPpxQueueIds=()=>[{source:'100',target:'42'}];
 c.refreshGameField=async()=>{};
 c.refreshAutoPpxTags=async()=>{
  c.observe([c.tag(42,{nx:.8}),...(!hidden?[c.tag(100,{nx:sourceX})]:[])]);
  return c.latestVisibleArucoTags;
 };
 // Use the real capture path as well: each run creates fresh row evidence.
 vm.runInContext(html.slice(html.indexOf('async function captureAutoPpxQueuePoses('),html.indexOf('function autoPpxIsPhysicalTag(')),c);
 c.onMove=async label=>{if(label==='source hover'){hidden=true;await c.refreshAutoPpxTags();}};
 for(const x of [.3,.65]){
  sourceX=x;hidden=false;c.tick(1000);
  await c.runAutoPpx();
  assert.equal(c.autoPpxCueOutcome,'completed');assert.equal(c.autoPpxRunning,false);
 }
 assert.deepEqual(c.moves.filter(m=>m.label==='source pickup').map(m=>m.pose.x),[300,650]);
 const releases=c.events.filter(e=>e.name==='release_completed');
 assert.equal(releases.length,2);assert.notEqual(releases[0].operation_id,releases[1].operation_id);
 assert.equal(c.pump.filter(p=>p.mode==='suck').length,2);
});
function clearViewContext(clear={action:'clear_view'}){
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}},clear]);
 c.cal2CalibrationSamples=()=>[];
 c.cal2CameraForRobotPose=(_,p)=>({u:p.x/1000,v:p.y/1000});
 c.cal2PoseEvaluator=()=>((u,v)=>({x:u*1000,y:v*1000}));
 c.assertAutoPpxPoseSafe=()=>{};
 let hidden=false;
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(42,{nx:.8}),...(!hidden?[c.tag(100)]:[])]);
 c.onMove=async label=>{if(label==='source hover')hidden=true;};
 return c;
}
test('Clear view moves 50 mm after release and lift without another pickup or release',async()=>{
 for(const rotation of [0,180]){
  const c=clearViewContext();await c.runAutoPpx(null,{viewRotation:rotation});
  assert.equal(c.autoPpxCueOutcome,'completed',c.autoPpxCueError?.message);
  const clear=c.moves.at(-1);assert.equal(clear.label,'clear view');assert.equal(clear.row,2);
  assert.equal(clear.pose.x,rotation===0?750:850);assert.equal(clear.pose.y,400);assert.equal(clear.pose.z,80);
  assert.equal(c.moves.at(-2).label,'return to moving height');
  assert.equal(c.events.filter(e=>e.name==='release_completed').length,1);
  assert.equal(c.pump.filter(p=>p.mode==='suck').length,1);assert.equal(c.pump.at(-1).mode,'off');
 }
});
test('Clear view respects calibrated direction, physical distance and invalid geometry',()=>{
 const c=clearViewContext(),origin={x:300,y:200,z:80};
 c.cal2CameraForRobotPose=()=>({u:.5,v:.5});
 c.cal2PoseEvaluator=()=>((u,v)=>({x:600*u+100*v,y:800*u+300*v}));
 for(const flip of [false,true])for(const rotation of [0,180])for(const direction of ['left','right'])for(const distance_cm of [.1,5,7.5,50]){
  c.gid=()=>({checked:flip});const target=c.autoPpxClearViewTarget(origin,rotation,{action:'clear_view',direction,distance_cm});
  const sign=(flip?-1:1)*(rotation===180?1:-1)*(direction==='right'?-1:1),mm=distance_cm*10;
  assert(Math.abs(target.x-origin.x-sign*mm*.6)<1e-9);assert(Math.abs(target.y-origin.y-sign*mm*.8)<1e-9);
  assert(Math.abs(Math.hypot(target.x-origin.x,target.y-origin.y)-mm)<1e-9);assert.equal(target.z,80);
 }
 assert.throws(()=>c.autoPpxClearViewTarget(origin,90),/valid camera view/);
 c.cal2PoseEvaluator=()=>()=>({x:0,y:0});assert.throws(()=>c.autoPpxClearViewTarget(origin,0),/direction is unavailable/);
});
test('Clear view carries custom distance/direction into execution and rejects malformed rows',async()=>{
 const c=clearViewContext({action:'clear_view',direction:'right',distance_cm:7.5});
 await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed');assert.equal(c.moves.at(-1).pose.x,875);
 for(const row of [{action:'clear_view',direction:'up'},...[0,-1,50.1,NaN,Infinity,'5',true,null].map(distance_cm=>({action:'clear_view',distance_cm})),{action:'clear_view',distance:5}])assert.throws(()=>c.autoPpxClearViewRow(row),/Clear view/);
 assert(c.events.find(e=>e.name==='release_completed').pickupComplete,'Pickup completion is retained after a successful lift');
});
test('Clear view refuses an unsafe offset and paused motion retries the same target',async()=>{
 const blocked=clearViewContext();blocked.assertAutoPpxPoseSafe=()=>{throw Error('Clear view is outside the safe reach');};
 await blocked.runAutoPpx();assert.equal(blocked.autoPpxCueOutcome,'error');assert.equal(blocked.autoPpxCueError.index,1);
 assert(!blocked.moves.some(m=>m.label==='clear view'));assert.equal(blocked.events.filter(e=>e.name==='release_completed').length,1);
 const c=clearViewContext(),onMove=c.onMove;let interrupted=false;
 c.onMove=async(label,options)=>{await onMove(label,options);if(label==='clear view'&&!interrupted){interrupted=true;c.autoPpxPaused=true;}};
 c.waitForAutoPpxResume=async()=>{c.autoPpxPaused=false;};
 await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed');
 assert.deepEqual(c.moves.filter(m=>m.label==='clear view').map(m=>m.pose.x),[750,750]);
 assert.equal(c.events.filter(e=>e.name==='release_completed').length,1);
});
test('a hidden source completes pickup and drop; the following row waits and reacquires that Atom',async()=>{
 const rows=[{sourceTag:{id:100},targetTag:{id:42}},{sourceTag:{id:100},targetTag:{id:43}}];
 const c=queueContext(rows);let hidden=false,secondReacquired=false,prompts=[];
 c.setAutoPpxStatus=text=>prompts.push(text);
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(42),c.tag(43),...(!hidden?[c.tag(100,{nx:secondReacquired?.7:.3})]:[])]);
 c.onMove=async(label,options)=>{
  if(label==='source hover'){hidden=true;c.tick(5000);c.observe([c.tag(42),c.tag(43)]);assert(!options.interruptWhen());}
 };
 const delay=c.delay;
 c.delay=async ms=>{
  if(c.autoPpxVisionWait){
   assert.equal(c.activeOperation.queue_index,2,'No detection wait between approach and release');
   assert(c.events.some(e=>e.name==='release_completed'&&e.queue_index===1));
   assert.equal(c.moves.at(-1).label,'return to moving height');
   hidden=false;secondReacquired=true;
  }
  await delay(ms);
 };
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueOutcome,'completed');
 assert.equal(c.moves.length,12);assert.equal(c.events.filter(e=>e.name==='release_completed').length,2);
 assert.equal(c.moves.find(m=>m.row===1&&m.label==='source pickup').pose.x,300);
 assert.equal(c.moves.find(m=>m.row===2&&m.label==='source pickup').pose.x,700);
 assert.equal(c.pump.filter(p=>p.mode==='suck').length,2);
 assert(prompts.some(t=>/Atom battery/.test(t)));assert(!prompts.some(t=>/is held/.test(t)));
});
test('a hidden 100-series destination does not block descent or release within its row',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:103}}]);let sourceHidden=false,targetHidden=false;
 c.refreshAutoPpxTags=async()=>c.observe([...(sourceHidden?[]:[c.tag(100)]),...(targetHidden?[]:[c.tag(103,{nx:.7})])]);
 c.onMove=async(label,options)=>{
  if(label==='source hover')sourceHidden=true;
  if(label==='target hover')targetHidden=true;
  c.tick(1000);await c.refreshAutoPpxTags();assert(!options.interruptWhen?.());
 };
 const delay=c.delay;c.delay=async ms=>{assert.equal(c.autoPpxVisionWait,null);await delay(ms);};
 await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed');
 assert(c.events.some(e=>e.name==='release_completed'));assert.equal(c.moves.at(-1).label,'return to moving height');
});

test('real row execution holds through mapping outages and completes with source and destination tags hidden',async()=>{
 for(const failureStage of ['source hover','source pickup','target hover','target drop']){
  const c=queueContext([{sourceTag:{id:100},targetTag:{id:103}}]),diagnostics=[],holds=[];
  let sourceHidden=false,targetHidden=false,outage=false,injected=false,recoveryReads=0,pumpAtHold=0;
  c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
  c.refreshAutoPpxTags=async()=>{
   if(outage&&++recoveryReads<3){c.autoPpxCueMap.status='unavailable';return;}
   outage=false;c.observe([...(sourceHidden?[]:[c.tag(100)]),...(targetHidden?[]:[c.tag(103,{nx:.7})])]);
  };
  const api=c.api,delay=c.delay;
  c.api=async(path,...args)=>{if(path==='/api/stop'){holds.push(c.pump.at(-1).mode);pumpAtHold=c.pump.length;}return api(path,...args);};
  c.delay=async ms=>{
   if(outage){assert.equal(c.autoPpxVisionWait.phase,'camera_retained');assert.equal(c.pump.length,pumpAtHold);}
   await delay(ms);
  };
  c.onMove=async(label,options)=>{
   if(label==='source hover')sourceHidden=true;
   if(label==='target hover')targetHidden=true;
   if(label===failureStage&&!injected){
    injected=true;outage=true;c.autoPpxCueMap.status='unavailable';assert(options.interruptWhen());
   }
  };
  await c.runAutoPpx();
  assert.equal(c.autoPpxCueOutcome,'completed',failureStage+': '+c.autoPpxCueError?.message);
  assert.equal(holds.length,1);assert.equal(holds[0],failureStage.startsWith('source')?'off':'suck');
  assert.equal(c.moves.filter(m=>m.label===failureStage).length,2,'The interrupted stage retries');
  assert.deepEqual(c.moves.filter(m=>m.label===failureStage).map(m=>m.pose.x),failureStage.startsWith('source')?[300,300]:[700,700]);
  assert.equal(c.events.filter(e=>e.name==='release_completed').length,1);
  assert.equal(diagnostics.filter(e=>e.event==='cue_target_acquired'&&e.tag_id===100).length,1);
  assert.equal(diagnostics.filter(e=>e.event==='cue_target_acquired'&&e.tag_id===103).length,1);
  assert(!diagnostics.some(e=>e.event==='cue_target_invalidated'));
  assert(!diagnostics.some(e=>e.event==='cue_waiting'&&e.phase==='mapping'));
 }
});

test('the initial acquisition survives the preflight-to-approach handoff without another source sighting',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}}]);let sourceHidden=false,sourceReads=0;
 c.refreshAutoPpxTags=async()=>{if(!sourceHidden)sourceReads++;c.observe([c.tag(42),...(sourceHidden?[]:[c.tag(100)])]);};
 c.preflightAutoPpxQueue=async()=>{sourceHidden=true;c.tick(1000);c.observe([c.tag(42)]);};
 const delay=c.delay;c.delay=async ms=>{assert.equal(c.autoPpxVisionWait,null);await delay(ms);};
 await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed');
 assert.equal(sourceReads,2,'Destination preflight read plus one source acquisition; no duplicate resolver acquisition');
 assert.equal(c.pump.filter(p=>p.mode==='suck').length,1);
});

test('real camera owner outlier/recovery preserves a hidden pickup through descent and release',async()=>{
 // Generate actual owner envelopes instead of assuming that camera recovery
 // preserves epoch. A single fixed-tag outlier used to rotate it immediately.
 const frames=JSON.parse(require('node:child_process').execFileSync('python3',['-c',`
import importlib.util, json, sys
sys.path.insert(0, 'sandboxes/gamemaster/prototypes/photon-board')
spec=importlib.util.spec_from_file_location('cue_targets', 'sandboxes/gamemaster/prototypes/photon-board/cue_targets.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
owner=module.CueTargets()
def observe(now, x=.8, source=True):
    tags=[dict(id=42,nx=x,ny=.4,missing=0)]
    if source: tags.append(dict(id=100,nx=.3,ny=.4,missing=0))
    for tag in tags: tag['ncorners']=[[tag['nx']+x/1280,tag['ny']+y/720] for x,y in ((-20,-20),(20,-20),(20,20),(-20,20))]
    owner.update(dict(status='ready',source='camera',corrected=True,camera_identity='one',camera_revision='lens',width=1280,height=720,frame_at=now,visible_ids=[t['id'] for t in tags],detections=tags),now)
    return dict(owner.snapshot(now),server_time=now,scope='layout')
observe(10);observe(10.3)
print(json.dumps([observe(10.6),observe(16.6,x=.5,source=False),observe(17.2,source=False)]))
 `],{encoding:'utf8'}));
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}}]),diagnostics=[];
 let frameIndex=0,outlierReads=0,holds=0;
 c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
 c.readAutoPpxCueTargets=async()=>{
  if(frameIndex===1&&outlierReads++)frameIndex=2;
  const data=frames[frameIndex],tags=c.autoPpxCueProjectionTags(data,c.now());
  c.autoPpxCueMap={...data,frameAtLocal:c.now(),calibrationRevision:3};
  return tags;
 };
 const api=c.api;
 c.api=async(path,...args)=>{if(path==='/api/stop'){holds++;assert.equal(c.pump.at(-1).mode,'off');}return api(path,...args);};
 c.onMove=async label=>{
  if(label==='source pickup'&&frameIndex===0){frameIndex=1;c.tick(6000);await c.refreshAutoPpxTags();}
 };
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueOutcome,'completed',c.autoPpxCueError?.message);
 assert.equal(holds,1);assert.equal(frameIndex,2);
 assert.deepEqual(c.moves.filter(m=>m.label==='source pickup').map(m=>m.pose.x),[300,300]);
 assert.equal(diagnostics.filter(e=>e.event==='cue_target_acquired'&&e.tag_id===100).length,1);
 assert(!diagnostics.some(e=>e.event==='cue_target_invalidated'));
 assert.equal(c.events.filter(e=>e.name==='release_completed').length,1);
});

test('100 to 40 finishes without a camera hold while 40 is hidden and inactive 30 is misdetected',async()=>{
 const evidence=JSON.parse(require('node:child_process').execFileSync('python3',['-c',`
import importlib.util, json, sys
sys.path.insert(0, 'sandboxes/gamemaster/prototypes/photon-board')
spec=importlib.util.spec_from_file_location('cue_targets', 'sandboxes/gamemaster/prototypes/photon-board/cue_targets.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
owner=module.CueTargets(fixed_ids=[40,42]);legacy=module.CueTargets()
def observe(now, stage=0):
    tags=[dict(id=42,nx=.6,ny=.4,missing=0)]
    if stage < 2: tags.append(dict(id=40,nx=.8,ny=.4,missing=0))
    if stage == 0: tags.append(dict(id=100,nx=.3,ny=.4,missing=0))
    if stage == 0 or 2 <= stage <= 4: tags.append(dict(id=30,nx=.1 if stage==0 else .9,ny=.6,missing=0))
    for tag in tags: tag['ncorners']=[[tag['nx']+x/1280,tag['ny']+y/720] for x,y in ((-20,-20),(20,-20),(20,20),(-20,20))]
    runtime=dict(status='ready',source='camera',corrected=True,camera_identity='one',camera_revision='lens',width=1280,height=720,frame_at=now,visible_ids=[t['id'] for t in tags],detections=tags)
    owner.update(runtime,now);legacy.update(runtime,now)
    return dict(owner.snapshot(now),server_time=now,scope='layout'),legacy.snapshot(now)
observe(10);observe(10.3)
first,old=observe(10.6);epoch=old['epoch'];frames=[first,observe(10.9,1)[0]];legacy_hold=False
for n in range(240):
    value,old=observe(11.2+n*.3,n+2);frames.append(value)
    legacy_hold |= old['status']=='unavailable'
print(json.dumps(dict(frames=frames,legacy_hold=legacy_hold,legacy_reset=old['epoch']!=epoch)))
 `],{encoding:'utf8'}));
 assert(evidence.legacy_hold,'Unscoped policy reproduces the reported hold');
 assert(evidence.legacy_reset,'Repeated inactive detections even reset the unscoped map');
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:40}}]),diagnostics=[];
 let frameIndex=0,holds=0;
 c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
 c.readAutoPpxCueTargets=async()=>{
  const data=evidence.frames[frameIndex],tags=c.autoPpxCueProjectionTags(data,c.now());
  c.autoPpxCueMap={...data,frameAtLocal:c.now(),calibrationRevision:3};return tags;
 };
 const api=c.api;
 c.api=async(path,...args)=>{if(path==='/api/stop')holds++;return api(path,...args);};
 c.onMove=async(label,options)=>{
  if(label==='source hover'){frameIndex=1;c.tick(300);await c.refreshAutoPpxTags();}
  if(label==='target hover'){
   for(frameIndex=2;frameIndex<evidence.frames.length;frameIndex++){
    c.tick(300);await c.refreshAutoPpxTags();
    assert.equal(options.interruptWhen(),false,'Hidden target is not an in-motion timeout');
    assert.equal(c.pump.at(-1).mode,'suck');
   }
   frameIndex--;
  }
 };
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueOutcome,'completed',c.autoPpxCueError?.message);
 assert.equal(holds,0);
 assert.equal(c.moves.filter(m=>m.label==='target hover').length,1);
 assert.equal(c.moves.find(m=>m.label==='target drop').pose.x,800);
 assert.equal(c.events.filter(e=>e.name==='release_completed').length,1);
 assert(!diagnostics.some(e=>e.event==='cue_target_invalidated'||e.event==='cue_motion_held'));
});

test('100 to 49 finishes placement and Clear view through a distorted detection and long occlusion',async()=>{
 const frames=JSON.parse(require('node:child_process').execFileSync('python3',['-c',`
import json,sys
sys.path.insert(0, 'sandboxes/gamemaster/prototypes/photon-board')
from cue_targets import CueTargets
owner=CueTargets(fixed_ids=[40,42,43,44,49])
def observe(now, stage=0):
    positions={40:(.2,.2),42:(.8,.2),43:(.8,.8),44:(.2,.8)}
    if stage < 5: positions[49]=(.5 if stage<2 else .65,.5)
    if stage == 0: positions[100]=(.3,.4)
    tags=[]
    for ident,(x,y) in positions.items():
        size=90 if ident==49 and stage>=2 else 40
        tags.append(dict(id=ident,nx=x,ny=y,missing=0,ncorners=[[x+a/1280,y+b/720] for a,b in ((-size/2,-size/2),(size/2,-size/2),(size/2,size/2),(-size/2,size/2))]))
    owner.update(dict(status='ready',source='camera',corrected=True,camera_identity='one',camera_revision='lens',width=1280,height=720,frame_at=now,visible_ids=list(positions),detections=tags),now)
    return dict(owner.snapshot(now),server_time=now,scope='layout')
observe(10);observe(10.3)
print(json.dumps([observe(10.6),observe(10.9,1)]+[observe(11.2+n*.3,n+2) for n in range(210)]))
 `],{encoding:'utf8'}));
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:49}},{action:'clear_view'}]),diagnostics=[];
 c.cal2CalibrationSamples=()=>[];
 c.cal2CameraForRobotPose=(_,p)=>({u:p.x/1000,v:p.y/1000});
 c.cal2PoseEvaluator=()=>((u,v)=>({x:u*1000,y:v*1000}));
 c.assertAutoPpxPoseSafe=()=>{};
 let frameIndex=0,holds=0;
 c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
 c.readAutoPpxCueTargets=async()=>{
  const data=frames[frameIndex],tags=c.autoPpxCueProjectionTags(data,c.now());
  c.autoPpxCueMap={...data,frameAtLocal:c.now(),calibrationRevision:3};return tags;
 };
 const api=c.api;
 c.api=async(path,...args)=>{if(path==='/api/stop')holds++;return api(path,...args);};
 c.onMove=async(label,options)=>{
  if(label==='source hover'){frameIndex=1;c.tick(300);await c.refreshAutoPpxTags();}
  if(label==='target hover'){
   for(frameIndex=2;frameIndex<frames.length;frameIndex++){
    c.tick(300);await c.refreshAutoPpxTags();
    assert.equal(c.autoPpxCueMap.verification.status,'ready');
    assert.deepEqual([...c.autoPpxCueMap.pending_fixed_ids],[49]);
    assert.equal(options.interruptWhen(),false);
    assert.equal(c.pump.at(-1).mode,'suck');
    assert(!c.latestVisibleArucoTags.some(t=>t.id===49),'Bad geometry supplies no fresh target evidence');
   }
   frameIndex--;
  }
 };
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueOutcome,'completed',c.autoPpxCueError?.message);
 assert.equal(holds,0);
 assert.equal(c.moves.filter(m=>m.label==='target hover').length,1);
 assert.equal(c.moves.find(m=>m.label==='target drop').pose.x,500);
 assert.equal(c.moves.at(-1).label,'clear view');assert.equal(c.moves.at(-1).pose.x,450);
 assert.equal(c.events.filter(e=>e.name==='release_completed').length,1);
 assert.equal(c.pump.filter(p=>p.mode==='suck').length,1);assert.equal(c.pump.at(-1).mode,'off');
 assert(!diagnostics.some(e=>e.event==='cue_target_invalidated'||e.event==='cue_motion_held'));
});

test('quarantined destinations cannot start a new approach and still report blocking occupancy',async()=>{
 const c=context(),saved={sourceTag:{id:100},targetTag:{id:49}},messages=[];
 c.setAutoPpxStatus=message=>messages.push(message);
 let reads=0;
 c.refreshAutoPpxTags=async()=>{
  c.observe(++reads<3?[]:[c.tag(49,{nx:.7})]);
  c.autoPpxCueMap.quarantined_tags=reads<3?[{id:49,covered_by:[]}]:[];
 };
 await c.waitForAutoPpxMappedEndpoint(saved,'target',0);
 assert.equal(reads,3);assert.equal(saved.target.x,700);
 assert(messages.some(m=>m.includes('old position cannot start a new approach')));
 c.observe([]);c.autoPpxCueMap.quarantined_tags=[{id:49,covered_by:[103]}];
 assert(c.autoPpxCueEndpointChanged({id:49,fixed:true}));
 c.autoPpxCueMap.quarantined_tags[0].covered_by=[100];
 assert(!c.autoPpxCueEndpointChanged({id:49,fixed:true}),'Own carried piece is not another occupant');
});

test('a recovered map with a different identity cannot resume a hidden source at its old coordinates',async()=>{
 const c=context(),saved={sourceTag:{id:100}},diagnostics=[];
 c.window.mobileArmDiagnostic=(event,reason,details)=>diagnostics.push({event,reason,...details});
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(100)]);
 const resolve=c.createAutoPpxEndpointResolver(saved,'source',0);await resolve();
 c.autoPpxCueMap.status='unavailable';c.tick(2000);
 c.refreshAutoPpxTags=async()=>{c.observe([]);c.autoPpxCueMap.epoch='different-camera';};
 c.delay=async()=>{assert.equal(c.autoPpxVisionWait.phase,'mapping');c.autoPpxAbort=true;};
 await assert.rejects(resolve(),/stopped/);
 assert(diagnostics.some(e=>e.event==='cue_target_invalidated'&&e.phase==='mapping_changed'));
 assert(!diagnostics.some(e=>e.event==='cue_mapping_recovered'));
});

test('a revealed lower marker adds departure evidence without confirming grip or destination',async()=>{
 const c=context(),saved={sourceTag:{id:100},targetTag:{id:42}};let events=[];
 c.activeOperation.queue_index=1;
 c.window.mobileArmDiagnostic=(name,reason,context)=>events.push({name,reason,context});
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(100),c.tag(40,{visible:false,covered_by:[100]})]);
 await c.createAutoPpxEndpointResolver(saved,'source',0)();
 c.activeOperation.carryStartedAt=c.now();c.tick(300);c.observe([c.tag(40)]);
 c.observeAutoPpxSourceClearance();c.observeAutoPpxSourceClearance();
 const clearance=events.filter(e=>e.name==='cue_source_clear');
 assert.equal(clearance.length,1);assert.match(clearance[0].reason,/still needs visual confirmation/);
 assert.equal(c.activeOperation.sourceCleared,true);assert.equal(saved.source.x,300);
 assert.equal(saved.target,undefined);assert.equal(c.activeOperation.placementConfirmed,undefined);
});

test('startup failure survives camera refresh and a failed pump cleanup; a new run clears it',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:45}}]),diagnostics=[];
 const api=c.api;
 c.window.mobileArmDiagnostic=(event,reason,context)=>diagnostics.push({event,reason,context});
 c.assertReadyForAutoAction=()=>{throw Error('connect the arm first');};
 c.api=async()=>{throw Error('cleanup network unavailable');};
 // Simulate a periodic presentation update overwriting the old status field.
 const status={textContent:'Preparing cue'};const gid=c.gid;
 c.gid=id=>id==='autoPpxStatus'?status:gid(id);
 c.setAutoPpxStatus=text=>{status.textContent=text;};
 c.refreshAutoPpxTags=async()=>{status.textContent='16 tags ready';c.observe([c.tag(100),c.tag(45)]);};
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueOutcome,'error');assert.equal(c.autoPpxCueError.message,'connect the arm first');
 assert.equal(c.autoPpxCueError.stage,'Preparing cue');assert.equal(c.autoPpxCueError.index,0);
 assert.equal(c.autoPpxCueRunning,false);assert.equal(c.autoPpxRunning,false);assert.equal(c.moves.length,0);
 assert.equal(diagnostics[0].event,'cue_failed');assert.equal(diagnostics[0].reason,'connect the arm first');
 c.assertReadyForAutoAction=()=>{};c.api=api;
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(45),...(!c.activeOperation?.carryStartedAt?[c.tag(100)]:[])]);
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueOutcome,'completed');assert.equal(c.autoPpxCueError,null);
});

test('an exception while preparing cue controls uses the normal failure cleanup',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:45}}]),calls=[],gid=c.gid;
 c.gid=id=>{if(id==='autoPpxGo')throw Error('Cue controls unavailable');return gid(id);};
 c.api=async(path,data)=>{calls.push({path,data});return {ok:true};};
 await c.runAutoPpx();
 assert.equal(c.autoPpxCueError.message,'Cue controls unavailable');assert.equal(c.autoPpxCueOutcome,'error');
 assert.equal(c.autoPpxRunning,false);assert.equal(c.autoPpxCueRunning,false);
 assert.equal(calls[0].path,'/api/stop');assert.equal(calls[1].path,'/api/pump');assert.equal(calls[1].data.mode,'off');assert.equal(c.moves.length,0);
});

function loadPause(c){
 c.LTX=true;c.autoPpxPauseWaiting=false;
 const gid=c.gid;c.gid=id=>id==='autoPpxPause'?{setAttribute(){},classList:{toggle(){}}}:gid(id);
 vm.runInContext(html.slice(html.indexOf('function updateAutoPpxPauseControl('),html.indexOf('function cleanAutoPpxFinePoint(')),c);
}
test('Pause holds each moving stage, preserves suction and resumes the same retained endpoint',async()=>{
 for(const stage of ['source hover','source pickup','lift to moving height','target hover','target drop','return to moving height']){
  const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}}]);loadPause(c);
  let hidden=false,injected=false,pausedTicks=0,holdCount=0,movesAtPause,pumpAtPause;
  c.refreshAutoPpxTags=async()=>c.observe([c.tag(42),...(!hidden?[c.tag(100)]:[])]);
  const api=c.api,delay=c.delay;
  c.api=async(path,...args)=>{if(path==='/api/stop')holdCount++;return api(path,...args);};
  c.onMove=async(label)=>{
   if(label==='source hover'){hidden=true;c.observe([c.tag(42)]);}
   if(label===stage&&!injected){injected=true;movesAtPause=c.moves.length;pumpAtPause=c.pump.length;c.toggleAutoPpxPause();}
  };
  c.delay=async ms=>{
   if(c.autoPpxPaused){
    assert.equal(holdCount,1);assert.equal(c.moves.length,movesAtPause);assert.equal(c.pump.length,pumpAtPause);
    if(++pausedTicks===3)c.toggleAutoPpxPause();
   }
   await delay(ms);
  };
  await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed',stage+': '+c.autoPpxCueError?.message);
  assert.equal(holdCount,1);assert.equal(pausedTicks,3);assert.equal(c.moves.filter(m=>m.label===stage).length,2);
  assert.equal(c.pump.filter(p=>p.mode==='suck').length,1);
 }
});
test('a rapid Pause then Resume still holds and replans instead of losing the pause',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}}]);loadPause(c);let injected=false,holds=0;
 c.refreshAutoPpxTags=async()=>c.observe([c.tag(42),...(!c.activeOperation?.carryStartedAt?[c.tag(100)]:[])]);
 const api=c.api;c.api=async(path,...args)=>{if(path==='/api/stop')holds++;return api(path,...args);};
 c.onMove=async label=>{if(label==='source hover'&&!injected){injected=true;c.toggleAutoPpxPause();c.toggleAutoPpxPause();}};
 await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed');assert.equal(holds,1);
 assert.equal(c.moves.filter(m=>m.label==='source hover').length,2);
});
test('failed pickup uses only a fresh post-lift sighting of the source before release',()=>{
 for(const evidence of ['fresh','old','hidden','fixed','other-atom','unmapped','released','not-lifted']){
  const c=context();c.observe([]);c.activeOperation.pickupLiftedAt=c.now();
  c.activeOperation.sourceEvidence={mappingKey:c.autoPpxCueMapKey()};c.tick(10);
  const tag=c.tag(evidence==='fixed'?42:evidence==='other-atom'?101:100);
  if(evidence==='old')tag.lastSeenAt=c.activeOperation.pickupLiftedAt-1;
  if(evidence==='hidden')tag.visible=false;
  if(evidence==='released')c.activeOperation.releaseStartedAt=c.now();
  if(evidence==='not-lifted')delete c.activeOperation.pickupLiftedAt;
  c.observe([tag]);if(evidence==='unmapped')c.autoPpxCueMap.status='unavailable';
  c.observeAutoPpxPickupFailure();
  assert.equal(!!c.activeOperation.pickupFailure,evidence==='fresh',evidence);
  if(evidence==='fresh'){
   c.observe([]);assert.throws(()=>c.assertAutoPpxPickupNotFailed(),e=>e.code==='pickup_failed');
  }
 }
});
test('a visible source after pickup stops before release or the next row, retaining suction and the error',async()=>{
 for(const stage of ['after lift','target hover','target drop','paused']){
  const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}},{sourceTag:{id:101},targetTag:{id:43}}]);loadPause(c);
  let reveal=false,holds=0,holdBeforeFailure=false;const api=c.api,intent=c.laserIntent;
  c.api=async(path,...args)=>{if(path==='/api/stop')holds++;return api(path,...args);};
  c.laserIntent=async(name,data)=>{if(name==='operation_failed')holdBeforeFailure=holds>0;return intent(name,data);};
  c.refreshAutoPpxTags=async()=>{
   c.tick(5);c.observe([c.tag(42),c.tag(43),c.tag(101),
    ...(!c.activeOperation?.carryStartedAt||reveal||stage==='after lift'&&c.activeOperation.pickupLiftedAt?[c.tag(100)]:[])]);
  };
  c.onMove=async label=>{
   if(label===stage){reveal=true;await c.refreshAutoPpxTags();}
   if(stage==='paused'&&label==='target hover')c.toggleAutoPpxPause();
  };
  const delay=c.delay;c.delay=async ms=>{if(c.autoPpxPaused){reveal=true;await c.refreshAutoPpxTags();}await delay(ms);};
  await c.runAutoPpx();
  assert.equal(c.autoPpxCueOutcome,'error',stage);assert.match(c.autoPpxCueError.message,/Pickup failed: piece #100/);
  assert(holdBeforeFailure);assert(c.moves.every(m=>m.row===1));assert(!c.events.some(e=>e.name==='release_started'));
  assert.equal(c.pump.at(-1).mode,'suck');assert.equal(c.pump.filter(p=>p.mode==='suck').length,1);
  await c.refreshAutoPpxTags();assert.match(c.autoPpxCueError.message,/Pickup failed/);
 }
});
test('post-release source sightings and revealed fixed markers do not stop a completed pickup',async()=>{
 const c=queueContext([{sourceTag:{id:100},targetTag:{id:42}}]);
 c.refreshAutoPpxTags=async()=>{c.tick(5);c.observe([c.tag(40),c.tag(42),
  ...(!c.activeOperation?.carryStartedAt||c.activeOperation.releaseStartedAt?[c.tag(100)]:[])]);};
 c.onMove=async()=>c.refreshAutoPpxTags();
 await c.runAutoPpx();assert.equal(c.autoPpxCueOutcome,'completed');assert.equal(c.autoPpxCueError,null);
});

test('fresh source sighting after mapping recovery still fails pickup if the map epoch changed',()=>{
 const c=context();c.observe([]);c.activeOperation.pickupLiftedAt=c.now();
 c.activeOperation.sourceEvidence={mappingKey:c.autoPpxCueMapKey()};c.tick(500);
 c.observe([c.tag(100)]);c.autoPpxCueMap.epoch='recovered-camera';
 assert.throws(()=>c.assertAutoPpxPickupNotFailed(),e=>e.code==='pickup_failed');
});

test('a brief SSE sighting latches failure between acquisition polls without rewriting retained evidence',async()=>{
 const c=context();c.observe([]);c.autoPpxCueMap.frame_at=c.now()/1000;
 c.activeOperation.pickupLiftedAt=c.now();const retained=c.latestVisibleArucoTags;
 Object.assign(c,{performance:{now:c.now},mobileGameAt:c.now(),mobileGameError:'',lastMobileScope:null,
  lastMobileCalibration:3,renderMobileGameControls(){},haltMobileRobot(){}});
 vm.runInContext(html.slice(html.indexOf('async function applyMobileGame('),html.indexOf('async function readMobileGame(')),c);
 c.tick(100);
 const data={contract:'photon.game',version:2,server_time:c.now()/1000,mobile_rig_revision:3,
  mobile_cue_targets:{contract:'photon.board.cue-targets',version:1,status:'ready',coordinate_space:'corrected-camera-normalized',
   epoch:'camera',scope:'layout',server_time:c.now()/1000,frame_at:c.now()/1000,
   tags:[{id:100,nx:.3,ny:.4,visible:true,last_seen:c.now()/1000}]}};
 await c.applyMobileGame(data);
 assert.equal(c.latestVisibleArucoTags,retained);assert.equal(retained.length,0);
 data.mobile_cue_targets.tags=[];await c.applyMobileGame(data);
 assert.throws(()=>c.assertAutoPpxPickupNotFailed(),e=>e.code==='pickup_failed');
});
