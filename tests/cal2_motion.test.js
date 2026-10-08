/* Real planner functions; deterministic geometry, no hardware or network. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/robot_controls/controller.html','utf8');
function planner(polygon){
 const c={gameRadiusMin:220,gameRadiusMax:440,AUTO_PP_BASE_SAFE_RADIUS:220,AUTO_PP_OUTER_GUARD_MM:4,AUTO_PP_ROUTE_CLEARANCE_MM:25,AUTO_PP_PATH_STEP_MM:25,
  gameReachWorkspace:{x:[-450,450],y:[-450,450]},ws:{z:[-150,230]},log(){},boundary:polygon};
 vm.createContext(c);
 for(const [from,to] of [['function cal2MotionLimit(', 'function solveLinearSystem('],
  ['function segmentDistanceFromBase(', 'async function executeCal2Plan('],
  ['function pointInsideRobotPolygon(', 'function jointPoseInsideCal2(']])
  vm.runInContext(source.slice(source.indexOf(from),source.indexOf(to)),c);
 c.cal2RobotPlanningBoundary=()=>c.boundary;
 return c;
}
const p=(x,y,z=60)=>({x,y,z}),square=[[-450,-450],[450,-450],[450,450],[-450,450]];
test('executed checked detour is published for drawing without modifying waypoints or commands',async()=>{
 const paths=[],moves=[],plan=[p(300,40),p(280,80)];
 const c={AUTO_PP_PATH_STEP_MM:25,window:{mobileArmPath:points=>paths.push(points)},log(){},autoPpxAbort:false,throwIfMotionInterrupted(){},assertAutoPpxPoseSafe(){},syncTargetSliders(){},showZFloor(){},
  api:async(_,point)=>{moves.push(point);return {ok:true};},waitForPose:async()=>({ok:true})};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('async function executeCal2Plan('),source.indexOf('async function routeCal2TransportAroundBase(')),c);
 assert.equal(await c.executeCal2Plan(plan,'test'),plan[1]);assert.equal(paths[0],plan);assert.deepEqual(moves,plan);
 c.window.mobileArmPath=()=>{throw Error('drawing failed');};await c.executeCal2Plan(plan,'test');assert.equal(moves.length,4);
});
test('transport uses the selected arm height and preserves the legacy shared fallback',()=>{
 for(const file of ['shared/robot_controls/controller.html','sandboxes/green/prototypes/auto-pickup-game/controller.html']){
  const html=fs.readFileSync(file,'utf8'),c={selectedAutoPpxCalibration:()=> 'cal2',gameCalibration2:{shared_z:{transport_height:60}},arm:{transport_height:50}};
  c.gameArmCal2=()=>c.arm;vm.createContext(c);
  vm.runInContext(html.slice(html.indexOf('function autoPpxTransportZ('),html.indexOf('function autoPpxStackDropOffset(')),c);
  assert.equal(c.autoPpxTransportZ(),50);c.arm={transport_height:65};assert.equal(c.autoPpxTransportZ(),65);
  c.arm={};assert.equal(c.autoPpxTransportZ(),60);
  c.arm={transport_height:NaN};assert.throws(()=>c.autoPpxTransportZ(),/not calibrated/);
 }
});
test('XYZ holds at the inner barrier; Targeting/Cue find a checked route around it',()=>{
 const c=planner(square),start=p(300,0),target=p(-300,0);
 assert.throws(()=>c.planCal2Movement(start,target,'mobile XYZ',{allowDetour:false}),e=>e.code==='motion_limit');
 const plan=c.planCal2Movement(start,target,'video target');assert(plan.length>2);
 let cursor=start;
 for(const point of plan){assert(c.cal2DirectPathHasClearance(cursor,point));cursor=point;}
 assert.deepEqual({...plan.at(-1)},target);
});
test('routing goes around a concave calibrated exclusion, not through the red notch',()=>{
 const c=planner([[240,-120],[400,-120],[400,120],[350,120],[350,-40],[290,-40],[290,120],[240,120]]);
 const start=p(260,60),target=p(380,60),began=performance.now();
 assert.throws(()=>c.planCal2Movement(start,target,'mobile XYZ',{allowDetour:false}),e=>e.code==='motion_limit');
 const plan=c.planCal2Movement(start,target,'cue target');assert(plan.some(point=>point.y<=-40));
 let cursor=start;for(const point of plan){assert(c.cal2DirectPathHasClearance(cursor,point));cursor=point;}
 assert(performance.now()-began<1200,'Route planning must not starve the 1.5-second feedback watchdog');
});
test('a bounded overshoot can retreat without reconnecting, and padding does not trap valid height steps',()=>{
 const c=planner(square);
 for(const [start,target] of [[p(219,0),p(225,0)],[p(443,0),p(435,0)],[p(225,0),p(225,0,61)]])
  assert.equal(c.planCal2Movement(start,target,'mobile XYZ',{allowDetour:false}).length,1);
 assert.throws(()=>c.planCal2Movement(p(209,0),p(250,0),'mobile XYZ'),e=>e.code==='motion_limit');
 assert.throws(()=>c.planCal2Movement(p(219,0),p(200,120),'mobile XYZ',{allowDetour:false}),e=>e.code==='motion_limit');
 c.boundary=[[240,-100],[400,-100],[400,100],[240,100]];
 assert.equal(c.planCal2Movement(p(237,0),p(250,0),'mobile XYZ',{allowDetour:false}).length,1);
 assert.throws(()=>c.planCal2Movement(p(225,0),p(250,0),'mobile XYZ'),e=>e.code==='motion_limit');
});
test('invalid destinations are recoverable; malformed geometry and feedback remain faults',()=>{
 const c=planner(square);
 for(const target of [p(210,0),p(441,0),p(300,0,231)])
  assert.throws(()=>c.planCal2Movement(p(300,0),target,'video target'),e=>e.code==='motion_limit');
 assert.throws(()=>c.planCal2Movement(p(NaN,0),p(300,0),'video target'),e=>!e.code);
 c.cal2RobotPlanningBoundary=()=>{throw Error('Six-point calibration unavailable');};
 assert.throws(()=>c.planCal2Movement(p(300,0),p(310,0),'video target'),e=>!e.code);
});
test('mobile watchdog holds unsafe motion without starting a concurrent recovery move',async()=>{
 const c=planner(square),calls=[];
 Object.assign(c,{AUTO_PPX:true,MOBILE_LTZ:true,cal2BaseGuardBusy:false,cal2RecoveryBusy:false,cal2BoundaryStop:null,autoPpxAbort:false,
  api:async(path)=>{calls.push(path);return {ok:true};},setAutoPpxStatus(){}});
 vm.runInContext(source.slice(source.indexOf('async function guardCal2BaseApproach('),source.indexOf('async function waitForCal2BaseGuard(')),c);
 const status=(x,target)=>({enabled:true,control_mode:'cartesian',pose:[x,0,60],target:[target,0,60]});
 await c.guardCal2BaseApproach(status(219,225));assert.deepEqual(calls,[],'An inward retreat is not stopped');
 await c.guardCal2BaseApproach(status(219,219));assert.deepEqual(calls,[],'An idle boundary stop does not auto-nudge');
 await c.guardCal2BaseApproach(status(225,210));assert.deepEqual(calls,['/api/stop']);assert.equal(c.cal2BoundaryStop.code,'motion_limit');
 c.api=async()=>({ok:false,error:'Lost relay'});
 await c.guardCal2BaseApproach(status(225,210));assert(!c.cal2BoundaryStop.code,'Failed hold is a connection fault');
});

test('cue detours can start and finish in the permitted edge bands without a safe-point detour first',()=>{
 const c=planner(square);c.gameRadiusMax=439;
 for(const radius of [220,225,438.5]){
  const start=p(radius,0),target=p(-radius,0);
  c.assertAutoPpxPoseSafe(start);c.assertAutoPpxPoseSafe(target);
  const plan=c.planCal2Movement(start,target,'source hover');
  assert(plan.length>1,'The straight route crosses the base and requires routing');
  let cursor=start;
  for(const point of plan){
   c.assertAutoPpxPoseSafe(point);
   assert(c.cal2DirectPathHasClearance(cursor,point),'Every executed segment respects the actual movement limits');
   cursor=point;
  }
  assert.deepEqual({...plan.at(-1)},target,'The requested pickup endpoint is preserved');
 }
});

test('a permitted 225 mm arm position is not reported unsafe or automatically nudged by the desktop guard',async()=>{
 const c=planner(square),calls=[];
 Object.assign(c,{AUTO_PPX:true,MOBILE_LTZ:false,cal2BaseGuardBusy:false,cal2RecoveryBusy:false,
  api:async(path)=>{calls.push(path);return {ok:true};},setAutoPpxStatus(){}});
 vm.runInContext(source.slice(source.indexOf('async function guardCal2BaseApproach('),source.indexOf('async function waitForCal2BaseGuard(')),c);
 await c.guardCal2BaseApproach({enabled:true,control_mode:'cartesian',pose:[225,0,60],target:[225,0,61]});
 assert.deepEqual(calls,[],'A safe vertical move must not trigger a hold or a radial recovery');
});
