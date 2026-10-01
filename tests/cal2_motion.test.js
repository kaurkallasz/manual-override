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
