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
 const c={TEAM:team,gameRadiusMin:150,gameRadiusMax:450,AUTO_PP_BASE_SAFE_RADIUS:220,
  gameReachWorkspace:{x:[-450,450],y:[-450,450]},ws:{z:[-150,230]},LTX:true,cal2JointGuardCache:null,
  gameArmCal2:side=>({points:Object.fromEntries((side==='green'?green:purple).map((p,i)=>['p'+i,{camera:p,pose:{...p,set:true}}]))}),
  gameDisplayPoint:(u,v)=>rotated?{u:1-u,v:1-v}:{u,v}};
 vm.createContext(c);
 for(const [from,to] of [['function solveLinearSystem(', 'function clipLtxArmSegment('],
  ['function robotPointReachable(', 'function renderReachMask('],
  ['function cal2ReachBoundary(', 'function cal2BoundarySvg('],
  ['function cal2JointSafetyGuard(', 'function pointInsideRobotPolygon(']]){
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
