/* Calibration geometry only: no browser, robot, network, or saved-state writes. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('shared/robot_controls/controller.html','utf8');
const purple=[
 [.7801,.4375,266.054,109.148],[.4646,.2918,186.293,-191.167],
 [.2734,.2972,187.297,-377.539],[.3322,.4714,282.517,-318.278],
 [.5356,.6789,396.103,-120.760],[.7813,.6752,391.575,111.744]
].map(([u,v,x,y])=>({u,v,x,y}));
const green=purple.map(p=>({...p,u:1-p.u,v:1-p.v,x:p.x+10,y:p.y+80}));
function controller(team='purple',rotated=true){
 const c={AUTO_PP_PHYSICAL_TAG_HEIGHT_MM:31.5,TEAM:team,LTZ:false,gameRadiusMin:150,gameRadiusMax:450,AUTO_PP_BASE_SAFE_RADIUS:220,
  gameReachWorkspace:{x:[-450,450],y:[-450,450]},ws:{z:[-150,230]},LTX:true,cal2JointGuardCache:null,
  gameCalibration2:{},cal2PlanningBoundaryCache:null,cal2ReachBoundaryCache:null,
  gameArmCal2:side=>({points:Object.fromEntries((side==='green'?green:purple).map((p,i)=>['p'+i,{camera:p,pose:{...p,set:true}}]))}),
  gameDisplayPoint:(u,v)=>rotated?{u:1-u,v:1-v}:{u,v}};
 vm.createContext(c);
 for(const [from,to] of [['function solveLinearSystem(', 'function clipLtxArmSegment('],
  ['function robotPointReachable(', 'function renderReachMask('],
  ['function cal2ConfiguredReach(', 'function cal2BoundarySvg('],
  ['function cal2CameraTargetPose(', 'function clickToPose('],
  ['function cal2RobotPlanningBoundary(', 'function cal2PathViolations('],
  ['function cal2JointSafetyGuard(', 'function jointPoseInsideCal2(']]){
  vm.runInContext(html.slice(html.indexOf(from),html.indexOf(to)),c);
 }
 return c;
}
test('collapsed Purple captures cannot produce a boundary, robot pose, inverse position, or joint guard',()=>{
 const c=controller(),bad=purple.map((p,i)=>({...p,x:325.408+i*.001,y:-24.225-i*.001}));
 for(const operation of [()=>c.cal2ReachBoundary(bad),()=>c.cal2RawPose(bad,.4,.4),
  ()=>c.cal2PoseEvaluator(bad),()=>c.cal2CameraForRobotPose(bad,{x:300,y:100})])
  assert.throws(operation,/captured robot positions overlap/);
 c.gameArmCal2=()=>({points:Object.fromEntries(bad.map((p,i)=>[i,{camera:p,pose:{...p,set:true}}]))});
 assert.throws(()=>c.cal2JointSafetyGuard(),/overlap/);
});
test('collinear or repeated camera and robot captures fail closed',()=>{
 const c=controller();
 assert.throws(()=>c.cal2ReachBoundary(purple.map((p,i)=>({...p,x:200+i*10,y:100+i*20}))),/two-dimensional field/);
 assert.throws(()=>c.cal2ReachBoundary(purple.map((p,i)=>({...p,u:.1+i*.05,v:.2+i*.1}))),/two-dimensional field/);
 assert.throws(()=>c.cal2ReachBoundary(purple.map(p=>({...p,u:.5,v:.5}))),/camera positions overlap/);
 assert.equal(c.robotPointReachable({x:NaN,y:0}),false);
 assert.equal(c.robotPointReachable(null),false);
});
test('valid Purple calibration stays separate from Green and maps its captured points correctly',()=>{
 const c=controller(),samples=c.cal2CalibrationSamples();
 for(let i=0;i<samples.length;i++){
  const p=c.cal2RawPose(samples,samples[i].u,samples[i].v);
  assert(Math.hypot(p.x-purple[i].x,p.y-purple[i].y)<.01);
 }
 const boundary=c.cal2ReachBoundary(samples),guard=c.cal2JointSafetyGuard();
 assert(boundary.length>=6);assert(guard.polygon.length>=6);
 assert.notDeepEqual(samples,c.cal2CalibrationSamples('green'));
 const area=Math.abs(boundary.reduce((sum,p,i)=>{const q=boundary[(i+1)%boundary.length];return sum+p.u*q.v-q.u*p.v;},0))/2;
 assert(area<.9,'Valid reach must not expand to the full camera');
});
test('180-degree calibration and mobile transforms do not double-rotate the Purple boundary',()=>{
 const normal=controller('purple',false),rotated=controller('purple',true);
 const a=normal.cal2ReachBoundary(normal.cal2CalibrationSamples());
 const b=rotated.cal2ReachBoundary(rotated.cal2CalibrationSamples()).map(p=>({u:1-p.u,v:1-p.v}));
 const distance=(p,polygon)=>Math.min(...polygon.map((q,i)=>{const r=polygon[(i+1)%polygon.length],du=r.u-q.u,dv=r.v-q.v,t=Math.max(0,Math.min(1,((p.u-q.u)*du+(p.v-q.v)*dv)/(du*du+dv*dv)));return Math.hypot(p.u-q.u-t*du,p.v-q.v-t*dv);}));
 for(const p of a)assert(distance(p,b)<1e-5);
 for(const p of b)assert(distance(p,a)<1e-5);
});
test('an older owner without a reach contract retains the captured robot envelope',()=>{
 const c=controller('green',false),samples=c.cal2CalibrationSamples(),at=c.cal2PoseEvaluator(samples);
 const polygon=c.calibrationConvexHull(samples.map(p=>({u:p.x,v:p.y}))).map(p=>[p.u,p.v]);
 for(const point of c.cal2ReachBoundary(samples)){
  const pose=at(point.u,point.v);assert(c.pointInsideRobotPolygon(pose.x,pose.y,polygon,0),'Every boundary vertex must respect the captured envelope');
 }
});
function expanded(c){
 const polygon=[[0,0],...Array.from({length:63},(_,i)=>{const a=(-155+i*5)*Math.PI/180;return [439*Math.cos(a),439*Math.sin(a)];})];
 c.gameRadiusMin=220;c.gameRadiusMax=439;
 c.gameCalibration2.motion_envelope={contract:'hhh.cal2.reach',version:1,status:'ready',physical_radius_max:440,margin_mm:1,
  guard:{format:'auto-pp-calibration-2-v1',polygon,radius_min:220,radius_max:439}};
 return polygon;
}
test('both arms expand past calibration centres while respecting the owner radius and rear exclusion',()=>{
 for(const team of ['green','purple'])for(const rotated of [false,true]){
  const c=controller(team,rotated),polygon=expanded(c),samples=c.cal2CalibrationSamples(),at=c.cal2PoseEvaluator(samples);
  const captured=c.calibrationConvexHull(samples.map(p=>({u:p.x,v:p.y}))).map(p=>[p.u,p.v]);
  assert.deepEqual(c.cal2RobotPlanningBoundary(),polygon);
  assert.deepEqual(JSON.parse(JSON.stringify(c.cal2JointSafetyGuard().polygon)),polygon);
  assert(c.pointInsideRobotPolygon(438,0,polygon,0));assert(!c.pointInsideRobotPolygon(440,0,polygon,0));
  assert(!c.pointInsideRobotPolygon(-300,0,polygon,0));assert(!c.robotPointReachable({x:219,y:0}));
  const mapped=c.cal2ReachBoundary(samples).map(p=>at(p.u,p.v));
  assert(mapped.some(p=>!c.pointInsideRobotPolygon(p.x,p.y,captured,0)),'Reach expands beyond sample centres');
  for(const p of mapped){assert(c.robotPointReachable(p));assert(c.pointInsideRobotPolygon(p.x,p.y,polygon,0));}
 }
});
test('malformed or over-limit owner envelopes fail closed and changed envelopes invalidate planning',()=>{
 const c=controller();expanded(c);const first=c.cal2RobotPlanningBoundary();
 c.gameCalibration2.motion_envelope.guard.polygon=[[240,-100],[400,-100],[400,100],[240,100]];
 assert.notEqual(c.cal2RobotPlanningBoundary(),first);
 for(const mutate of [v=>v.version=2,v=>v.guard.radius_max=450,v=>v.guard.polygon[0][0]=NaN]){
  expanded(c);mutate(c.gameCalibration2.motion_envelope);
  assert.throws(()=>c.cal2ReachBoundary(c.cal2CalibrationSamples()),/envelope unavailable/);
  assert.throws(()=>c.cal2RobotPlanningBoundary(),/envelope unavailable/);
 }
});
test('Purple raised-Atom correction rotates ground and raised samples together exactly once',()=>{
 const samples=Object.fromEntries([[31,.2,.25],[35,.75,.25],[33,.75,.7],[34,.2,.7]].map(([id,u,v])=>[id,
  {ground:{u,v},raised:{u:u+.03,v:v-.04}}]));
 for(const rotated of [false,true]){
  const c=controller('purple',rotated);c.gameArmCal2=()=>({parallax_points:samples});
  vm.runInContext(html.slice(html.indexOf('function compensateCal2Parallax('),html.indexOf('function cal2ClickToPose(')),c);
  for(const point of Object.values(samples)){
   const raised=c.gameDisplayPoint(point.raised.u,point.raised.v),ground=c.gameDisplayPoint(point.ground.u,point.ground.v);
   const corrected=c.compensateCal2Parallax(raised.u,raised.v,102);
   assert(Math.hypot(corrected.u-ground.u,corrected.v-ground.v)<1e-6);
   const flat=c.compensateCal2Parallax(ground.u,ground.v,31);
   assert.equal(flat.u,ground.u);assert.equal(flat.v,ground.v,'Flat markers receive no raised-Atom correction');
  }
  c.gameArmCal2=()=>({parallax_points:{31:samples[31]}});
  assert.throws(()=>c.compensateCal2Parallax(.5,.5,102),/Four raised-Atom/);
 }
});
test('calibration capture rejects wrong-team, missing, disconnected, or stale feedback',()=>{
 const capture=fs.readFileSync('sandboxes/green/prototypes/auto-pp-cal-2/calibrate2.html','utf8'),c={TEAM:'purple',Date};
 vm.createContext(c);vm.runInContext(capture.slice(capture.indexOf('function freshCapturePose('),capture.indexOf('async function capture(key)')),c);
 const good={side:'purple',connected:true,feedback_ok:true,last_feedback:Date.now()/1000,pose:[300,20,-99,0]};
 assert.equal(c.freshCapturePose(good),good.pose);
 for(const changes of [{side:'green'},{connected:false},{feedback_ok:false},{last_feedback:0},{last_feedback:undefined},{pose:[NaN,0,0,0]}])
  assert.throws(()=>c.freshCapturePose({...good,...changes}),/Fresh purple robot feedback/);
});
test('planning geometry is cached per capture set and rejects missing captures',()=>{
 const c=controller();c.cal2PlanningBoundaryCache=null;
 vm.runInContext(html.slice(html.indexOf('function cal2RobotPlanningBoundary('),html.indexOf('function cal2PathViolations(')),c);
 const boundary=c.cal2RobotPlanningBoundary();assert(boundary.length>=3);
 assert(boundary.every(([x,y])=>purple.some(p=>p.x===x&&p.y===y)),'Planner uses the same captured robot-space hull as the relay owner');
 assert.equal(c.cal2RobotPlanningBoundary(),boundary,'Unchanged samples reuse the validated robot-space boundary');
 c.gameRadiusMax=440;assert.notEqual(c.cal2RobotPlanningBoundary(),boundary,'Changed safety limits invalidate the cache');
 c.gameArmCal2=()=>({points:{}});assert.throws(()=>c.cal2RobotPlanningBoundary(),/all 6/,'Missing calibration cannot turn into an unrestricted path');
});

test('measured 40/42/45/47 destinations use the expanded guard with a bounded inward offset only for 42',()=>{
 const samples=[
  [.2399,.5707,271.938,142.851],[.5429,.7259,185.013,-157.921],[.7362,.7312,177.879,-344.528],
  [.6782,.5545,276.715,-290.064],[.4765,.3411,396.912,-94.723],[.2392,.3404,398.475,136.765]
 ].map(([u,v,x,y])=>({u,v,x,y}));
 for(const rotated of [false,true]){
  const c=controller('green',rotated),guard=expanded(c);
  c.LTZ=true;c.AUTO_PPX=true;c.sliderEls={z:{value:80}};c.selectedAutoPpxCalibration=()=> 'cal2';
  c.gameArmCal2=()=>({points:Object.fromEntries(samples.map((p,i)=>[i,{camera:p,pose:{...p,set:true}}]))});
  vm.runInContext(html.slice(html.indexOf('function cal2MotionLimit('),html.indexOf('function solveLinearSystem(')),c);
  vm.runInContext(html.slice(html.indexOf('function cal2CameraTargetPose('),html.indexOf('function clickToPose(')),c);
  // Force a coarse display contour to exclude everything. Actual robot geometry
  // remains the authority for selection and motion, not a sampled overlay.
  c.pointInsideCalibratedBoundary=()=>false;
  const tags=[[40,.3895,.2881],[42,.5022,.2878],[45,.6213,.3886],[47,.6796,.4934]];
  for(const [id,u,v] of tags){
   const camera=c.gameDisplayPoint(u,v),p=c.cal2ClickToPose(camera.u,camera.v,id);
   assert(c.pointInsideRobotPolygon(p.x,p.y,guard,0));assert(Math.hypot(p.x,p.y)<439);
   if(id===42)assert(p.placement_offset_mm>3&&p.placement_offset_mm<=5);
   else assert.equal(p.placement_offset_mm,undefined);
  }
  const edge=c.gameDisplayPoint(.5022,.2878);
  assert.deepEqual(c.cal2ClickToPose(edge.u,edge.v,100),c.cal2ClickToPose(edge.u,edge.v,42),'Pickup and drop share the edge correction');
  assert.deepEqual(c.cal2ClickToPose(edge.u,edge.v),c.cal2ClickToPose(edge.u,edge.v,42),'Image taps agree with the displayed selection arc');
  for(const p of [{x:465,y:0,z:80},{x:-442,y:0,z:80},{x:219,y:0,z:80}]){
   const result=c.cal2CameraTargetPose(p,42);assert.equal(result,p);
   assert.throws(()=>c.assertAutoPpxPoseSafe(result),e=>e.code==='motion_limit');
  }
 }
});

test('tag 100 after the marker 42 drop is inside the expanded camera arc and can be picked up',()=>{
 const samples=[
  [.2399,.5707,271.938,142.851],[.5429,.7259,185.013,-157.921],[.7362,.7312,177.879,-344.528],
  [.6782,.5545,276.715,-290.064],[.4765,.3411,396.912,-94.723],[.2392,.3404,398.475,136.765]
 ].map(([u,v,x,y])=>({u,v,x,y}));
 const parallax=Object.fromEntries([
  [31,.5429,.7259,.54807901,.73975381],[33,.6782,.5545,.69146105,.557243],
  [34,.4765,.3411,.47513153,.32833362],[35,.2392,.3404,.2207722,.32713734]
 ].map(([id,u,v,ru,rv])=>[id,{ground:{u,v},raised:{u:ru,v:rv}}]));
 for(const rotated of [false,true]){
  const c=controller('green',rotated),guard=expanded(c);
  c.gameArmCal2=()=>({points:Object.fromEntries(samples.map((p,i)=>[i,{camera:p,pose:{...p,set:true}}])),parallax_points:parallax});
  c.LTZ=true;c.AUTO_PPX=true;c.sliderEls={z:{value:-60.3775}};c.selectedAutoPpxCalibration=()=> 'cal2';
  vm.runInContext(html.slice(html.indexOf('function cal2MotionLimit('),html.indexOf('function solveLinearSystem(')),c);
  vm.runInContext(html.slice(html.indexOf('function compensateCal2Parallax('),html.indexOf('function syncTargetSliders(')),c);
  const tag=c.gameDisplayPoint(.5206,.2664),fit=c.cal2CalibrationSamples();
  const corrected=c.compensateCal2Parallax(tag.u,tag.v,100),raw=c.cal2RawPose(fit,corrected.u,corrected.v);
  assert(Math.abs(Math.hypot(raw.x,raw.y)-449.898)<.01,'Captured failing position stays in the regression');
  assert.throws(()=>c.assertAutoPpxPoseSafe({...raw,z:-60.3775}),e=>e.code==='motion_limit','Raw robot motion still cannot exceed the physical guard');
  const pickup=c.clickToPose(tag.u,tag.v,100);
  assert(pickup.placement_offset_mm>10&&pickup.placement_offset_mm<12);
  assert(c.pointInsideRobotPolygon(pickup.x,pickup.y,guard,0));
  assert(Math.hypot(pickup.x,pickup.y)<439);assert.equal(pickup.z,-60.3775);
  const boundary=c.cal2ReachBoundary(fit);
  assert(c.pointInsideRobotPolygon(tag.u,tag.v,boundary.map(p=>[p.u,p.v]),0),'The visible raised tag is inside the expanded whole arc');
  // Use the real bridge eligibility check, not only its rendering or labels.
  c.cuePoseAt=c.cal2PoseEvaluator(fit);
  c.autoPpxCueEndpointIssue=()=>''; // This geometry fixture supplies a ready camera.
  const bridge=fs.readFileSync('shared/mobile_ltz/arm-bridge.js','utf8');
  vm.runInContext(bridge.slice(bridge.indexOf('function cueTargetAvailability('),bridge.indexOf('function syncControlMode(')),c);
  const available=c.cueTargetAvailability({id:100,nx:tag.u,ny:tag.v,lastSeenAt:Date.now()});
  assert.equal(available.reachable,true);assert.equal(available.placement_offset_mm,pickup.placement_offset_mm);
 }
});

test('the camera edge allowance extends the whole arc, never the robot, base, rear or stale-owner guards',()=>{
 for(const team of ['green','purple']){
  const c=controller(team);c.LTZ=true;const guard=expanded(c);
  for(let degrees=-150;degrees<=150;degrees+=15){
   const a=degrees*Math.PI/180,p={x:460*Math.cos(a),y:460*Math.sin(a),z:80};
   const target=c.cal2CameraTargetPose(p,100);
   assert(target.placement_offset_mm>20&&target.placement_offset_mm<25);
   assert(c.pointInsideRobotPolygon(target.x,target.y,guard,0));assert(Math.hypot(target.x,target.y)<439);
   assert.equal(target.z,p.z);
  }
  for(const p of [{x:465,y:0},{x:219,y:0},{x:-450,y:0},{x:NaN,y:0}])
   assert.equal(c.cal2CameraTargetPose(p,100),p,'Unreachable input gains no allowance');
  c.gameCalibration2.motion_envelope.status='unavailable';
  assert.throws(()=>c.cal2CameraTargetPose({x:450,y:0},100),/envelope unavailable/);
  delete c.gameCalibration2.motion_envelope;
  const p={x:450,y:0};assert.equal(c.cal2CameraTargetPose(p,100),p,'Legacy owners gain no camera allowance');
 }
});

test('mobile reach shading uses the motion envelope rather than the narrower detour margin',()=>{
 const bridge=fs.readFileSync('shared/mobile_ltz/arm-bridge.js','utf8');
 const c={TEAM:'green',mobileGame:{mobile_safety:{status:'ready'}},rawCalibration:()=>false,
  gameArmCal2:()=>({}),gameCalibration2:{},gameRadiusMin:220,gameRadiusMax:439,ws:{},gid:()=>({checked:false}),
  geometry:null,geometryKey:'',geometryError:'',cuePoseAt:null,rawPoint:p=>p,
  cal2CalibrationSamples:()=>Array(6).fill({}),cal2JointSafetyGuard:()=>({radius_min:220,polygon:[]}),
  cal2ReachBoundary:()=>[{u:0,v:0},{u:1,v:0},{u:1,v:1},{u:0,v:1}],
  cal2PoseEvaluator:()=>u=>({x:u<.5?225:219,y:0}),cal2CameraTargetPose:p=>p,
  pointInsideConvexCalibration:()=>true,pointInsideRobotPolygon:()=>true,autoPpxPlanningRadiusMin:()=>230};
 vm.createContext(c);vm.runInContext(bridge.slice(bridge.indexOf('function reach('),bridge.indexOf('function cueTargetAvailability(')),c);
 c.reach();assert.equal(c.geometryError,'');
 assert.equal(c.geometry.excluded.length,22*32,'Only the 219 mm half is shaded; valid 225 mm points remain selectable');
 assert(c.geometry.excluded.every(cell=>cell.every(([u])=>u>=.5)));
});
