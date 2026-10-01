/* Contract and hardware routing tests with a fake relay. Never moves hardware. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const TEAM=process.env.MOBILE_TEST_TEAM==='purple'?'purple':'green';
let jointFailure=null,holdFailure=null,moveFailure=null,holdWait=null,clickedTags=[];
let now=100,calls=[],posted=[],listener,intervals=[],robot={connected:true,enabled:true,feedback_ok:true,pose:[300,100,50,9],joints:[0,20,30,9],pump_mode:'off'};
const parent={postMessage:d=>posted.push(d)},nodes=new Map();
const gid=id=>{if(!nodes.has(id))nodes.set(id,{checked:false,value:'http://relay.test',textContent:'Ready',removeAttribute(){}});return nodes.get(id);};
// Purple's stored calibration view is rotated. Its bridge must still send raw
// camera coordinates to the mobile viewport and use calibrated robot poses.
gid('flipToggle').checked=TEAM==='purple';
const displayPoint=(u,v)=>gid('flipToggle').checked?{u:1-u,v:1-v}:{u,v};
const ctx={TEAM,MOBILE_LTZ:true,URLSearchParams,location:{search:'?ltz=1&mobile=1&bridge=1',origin:'http://test'},parent,window:{addEventListener:(name,fn)=>{listener=fn;}},performance:{now:()=>now},Date,crypto:{getRandomValues:array=>array.fill(1)},setInterval:fn=>intervals.push(fn),gid,
 gameArmCal2:()=>({points:6}),gameRadiusMin:150,gameRadiusMax:440,ws:{z:[-150,230]},jointLimits:{j1:[-160,160],j2:[-25,85],j3:[-25,105]},
 cal2CalibrationSamples:()=>Array(6).fill({}),cal2JointSafetyGuard:()=>({format:'auto-pp-calibration-2-v1',polygon:[[1,2],[3,4],[5,6]]}),cal2ReachBoundary:()=>[[.1,.1],[.9,.1],[.9,.9],[.1,.9]].map(([u,v])=>displayPoint(u,v)),
 cal2PoseEvaluator:()=>()=>({x:300,y:0}),pointInsideConvexCalibration:()=>true,autoPpxPlanningRadiusMin:()=>220,cal2CameraForRobotPose:(_,p)=>displayPoint(p.x/1000,p.y/1000),gameDisplayPoint:displayPoint,clickToPose:(u,v,id)=>{clickedTags.push(id);const p=displayPoint(u,v);return {x:p.u*1000,y:p.v*1000,z:50,r:9};},assertAutoPpxPoseSafe(){},
 mobileGame:{virtual_test_control:4,mobile_arm:{tags:[{id:101}]}},latestVisibleArucoTags:[],autoPpxCueRunning:false,autoPpxRunning:false,autoPpxPaused:false,autoPpxAbort:false,activeOperation:null,cal2BoundaryStop:null,
 ltzTier:4,mobileControlChoice:1,mobileRobotReady:()=>true,pauseUserMoves(){},cancelAutoPpxClickOverride(){},applyStatus(){},
 api:async(path,data)=>{calls.push({path,data});if(path==='/api/stop'&&holdWait)await holdWait;return path==='/api/status'?robot:path==='/api/joint-move'&&jointFailure?{ok:false,error:jointFailure}:path==='/api/stop'&&holdFailure?{ok:false,error:holdFailure}:{ok:true};},moveToPose:async(p,label,wait,options)=>{if(moveFailure)throw typeof moveFailure==='string'?Error(moveFailure):moveFailure;calls.push({path:'planned',p,label,options});},
};vm.createContext(ctx);vm.runInContext(fs.readFileSync('shared/mobile_ltz/arm-bridge.js','utf8'),ctx);
const flush=async()=>{for(let i=0;i<12;i++)await new Promise(r=>setImmediate(r));};
let id=0,session,seq=0;
async function command(data,origin='http://test',contract=TEAM+'.mobile-arm'){const key=String(++id);listener({origin,source:parent,data:{contract,version:1,type:'command',id:key,data:{...data,...(session?{session,sequence:++seq}:{})}}});await flush();return posted.find(p=>p.id===key);}
(async()=>{
 await flush();assert.equal(posted.at(-1).status,'ready');
 const samples=calls.filter(c=>c.path==='/api/status').length;now+=700;
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 assert(calls.filter(c=>c.path==='/api/status').length>samples,'Parent heartbeat refreshes feedback even when iframe timers are throttled');
 assert.equal(await command({action:'connect'},'http://evil'),undefined);
 assert.equal(await command({action:'connect'},'http://test',(TEAM==='green'?'purple':'green')+'.mobile-arm'),undefined,'A team cannot use the other arm bridge');
 let reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;assert(session.startsWith('physical:'));
 assert.equal(calls.find(c=>c.path==='/api/connect').data.side,TEAM);assert(!calls.some(c=>c.path==='/api/enable'),'Connect must not enable');
 reply=await command({action:'joints',joints:[1,22,33],control_revision:0});assert(reply.ok);
 const move=calls.find(c=>c.path==='/api/joint-move');assert.equal(move.data.j4,9);assert.equal(move.data.cal2_guard.format,'auto-pp-calibration-2-v1');
 const tokenBefore=session;
 jointFailure='Auto PP Cal 2 blocked joint path at 100%: joint target TCP radius 211.5 mm is outside the Auto PP Cal 2 limit 220.0-450.0 mm';
 const connectCount=calls.filter(c=>c.path==='/api/connect').length,pumpCount=calls.filter(c=>c.path==='/api/pump').length;
 reply=await command({action:'joints',joints:[1,22,75],control_revision:0});
 assert(!reply.ok);assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,tokenBefore);assert(reply.arm.connected);
 assert.deepEqual(Array.from(reply.arm.targets),robot.joints.slice(0,3));
 assert.equal(calls.at(-2).path,'/api/stop');assert.equal(calls.filter(c=>c.path==='/api/pump').length,pumpCount,'Boundary rejection keeps the gripper state');
 jointFailure=null;reply=await command({action:'joints',joints:[1,22,25],control_revision:0});assert(reply.ok,'A safe retreat works with the existing session');
 assert.equal(calls.filter(c=>c.path==='/api/connect').length,connectCount);
 jointFailure='could not verify joint target against Auto PP Cal 2: feedback unavailable';
 reply=await command({action:'joints',joints:[1,22,25],control_revision:0});assert(!reply.ok);assert.notEqual(reply.code,'motion_limit','Unknown/FK faults are not recoverable boundary events');jointFailure=null;
 reply=await command({action:'control_mode',mode:'targeting'});assert(reply.ok);assert.equal(reply.arm.control_revision,1);
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60},control_revision:1});assert(reply.ok);assert(Math.abs(calls.find(c=>c.path==='planned').p.x-300)<1e-9);assert(Math.abs(calls.find(c=>c.path==='planned').p.y-400)<1e-9);assert.equal(calls.find(c=>c.path==='planned').p.z,60);
 const own=TEAM==='green'?100:102,tagPoint=displayPoint(.3,.4);
 assert.equal(calls.find(c=>c.path==='planned').options.allowDetour,true,'Targeting can route around an excluded area');
 ctx.mobileGame.movable_piece_codes={[TEAM]:[own]};ctx.latestVisibleArucoTags=[{id:own,nx:tagPoint.u,ny:tagPoint.v,lastSeenAt:Date.now(),missing:0}];
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:1});assert(reply.ok);assert.equal(clickedTags.at(-1),own,'Visible owned Atom reaches the raised-tag correction once');
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own+1},control_revision:1});assert(!reply.ok,'A forged foreign Atom cannot grant a pickup target');
 ctx.latestVisibleArucoTags[0].lastSeenAt=Date.now()-600;
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:1});assert(!reply.ok,'Stale Atom capture has no flat-target fallback');ctx.latestVisibleArucoTags=[];
 reply=await command({action:'xyz',xyz:{x:2,y:.4,z:60},control_revision:1});assert(!reply.ok);assert.equal(reply.code,'motion_limit');assert.match(reply.detail,/outside/);assert.equal(reply.arm.session,session);
 holdFailure='Relay connection lost';
 reply=await command({action:'xyz',xyz:{x:2,y:.4,z:60},control_revision:1});assert(!reply.ok);assert.notEqual(reply.code,'motion_limit');assert.equal(reply.arm.session,null,'Failed safe hold releases the mobile session');
 holdFailure=null;reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60},control_revision:0});assert(!reply.ok);assert.equal(reply.code,'control_changed');assert.equal(reply.arm.session,session);
 robot.feedback_ok=false;
 ctx.applyStatus(robot);const count=calls.filter(c=>c.path==='/api/joint-move').length;
 reply=await command({action:'joints',joints:[1,22,33]});assert(!reply.ok);assert.equal(calls.filter(c=>c.path==='/api/joint-move').length,count);
 reply=await command({action:'pump',mode:'off'});assert(reply.ok,'Pump off survives stale feedback');
 reply=await command({action:'stop'});assert(reply.ok);assert.equal(reply.arm.session,null);assert(calls.some(c=>c.path==='/api/stop'));
 // Every GM-selected physical test tier defaults to that mode on either arm.
 robot.feedback_ok=true;
 for(const [index,expected] of ['joint','xyz','targeting','cue'].entries()){
  const tier=index+1;ctx.mobileGame.virtual_test_control=tier;ctx.ltzTier=tier;ctx.mobileControlChoice=tier;
  reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
  assert.equal(reply.arm.control_mode,expected,TEAM+' GM tier '+tier);
  reply=await command({action:'control_mode',mode:expected});assert(reply.ok);
  if(tier<4){reply=await command({action:'control_mode',mode:'cue'});assert(!reply.ok);}
  await command({action:'stop'});
 }
 // A connected bridge still adopts GM changes when normal feedback suppresses sample().
 for(const [index,expected] of ['joint','xyz','targeting','cue'].entries()){
  const beforeSession=session;
  ctx.mobileControlChoice=index+1;ctx.ltzTier=index+1;ctx.mobileGame.virtual_test_control=index+1;
  const beforeSamples=calls.filter(c=>c.path==='/api/status').length;
  now+=100;ctx.applyStatus(robot);
  listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
  assert.equal(calls.filter(c=>c.path==='/api/status').length,beforeSamples,'Continuous feedback does not force a new sample');
  const next=posted.at(-1);assert.equal(next.arm.control_mode,expected,TEAM+' feedback-only switch '+expected);
  if(index===0){reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;}
  else assert.equal(next.arm.session,beforeSession,'A changed control mode keeps the existing connection after holding');
 }
 // Cue height uses measured XY directly and cannot sneak in a lateral target.
 const cueRevision=posted.at(-1).arm.control_revision;
 reply=await command({action:'xyz',height_only:true,xyz:{x:.8,y:.9,z:51},control_revision:cueRevision});assert(reply.ok);
 let planned=calls.filter(c=>c.path==='planned').at(-1);assert.equal(planned.p.x,robot.pose[0]);assert.equal(planned.p.y,robot.pose[1]);assert.equal(planned.p.z,51);
 assert.equal(planned.options.allowDetour,false,'Manual height never moves sideways around a barrier');
 reply=await command({action:'xyz',xyz:{x:.8,y:.9,z:51},control_revision:cueRevision});assert(!reply.ok,'Cue cannot send manual XY');
 ctx.autoPpxCueRunning=true;
 reply=await command({action:'xyz',height_only:true,xyz:{z:52},control_revision:cueRevision});assert(!reply.ok,'Cue execution owns height too');ctx.autoPpxCueRunning=false;
 moveFailure='joint target TCP is outside the Auto PP Cal 2 arm boundary';
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);
 moveFailure='Cannot validate Cartesian path: safety limits missing';
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert(!reply.ok);assert.notEqual(reply.code,'motion_limit');moveFailure=null;
 moveFailure=Object.assign(Error('mobile XYZ start is inside the red Cal 2 exclusion area'),{code:'motion_limit'});
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);
 moveFailure=null;reply=await command({action:'xyz',height_only:true,xyz:{z:52},control_revision:cueRevision});assert(reply.ok,'A valid move recovers after a typed planner limit');
 // While Stop is pending, publish a locked mode with the same session. Old
 // revision commands are cancelled safely; a failed Stop drops the lease.
 let releaseHold;holdWait=new Promise(resolve=>releaseHold=resolve);
 ctx.mobileControlChoice=2;
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 assert.equal(posted.at(-1).arm.session,session);assert.equal(posted.at(-1).arm.control_pending,true);
 const obsolete=command({action:'xyz',xyz:{x:.3,y:.4,z:51},control_revision:cueRevision});releaseHold();holdWait=null;reply=await obsolete;assert.equal(reply.code,'control_changed');assert.equal(reply.arm.session,session);
 holdFailure='Relay unavailable';ctx.mobileControlChoice=3;
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 reply=await command({action:'heartbeat'});assert.equal(reply.arm.session,null,'A failed mode-switch hold must not retain control');holdFailure=null;
 // Calibration starts without an old camera fit: setup may connect, but only
 // a live grant permits raw millimetre moves through the existing route.
 ctx.mobileGame={journey:{phase:'calibration'},mobile_calibration_connect:true,mobile_calibration:{stage:'points'}};
 ctx.mobileControlChoice=2;ctx.ltzTier=2;ctx.ws={x:[-440,440],y:[-440,440],z:[-150,230]};
 ctx.cal2CalibrationSamples=()=>[];ctx.mobileConnectionReady=()=>true;ctx.mobileRobotReady=()=>false;
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 assert.equal(reply.arm.coordinate_space,'robot-mm');assert.equal(reply.arm.tip.x,robot.pose[0]);
 const rawRevision=reply.arm.control_revision,rawCount=calls.filter(c=>c.path==='/api/move').length;
 reply=await command({action:'xyz',xyz:{x:310,y:100,z:50},control_revision:rawRevision});assert(!reply.ok);
 assert.equal(calls.filter(c=>c.path==='/api/move').length,rawCount,'Display setup never permits motion');
 ctx.mobileRobotReady=()=>true;
 reply=await command({action:'xyz',xyz:{x:310,y:100,z:50},control_revision:rawRevision});assert(reply.ok);
 assert.deepEqual({...calls.filter(c=>c.path==='/api/move').at(-1).data},{x:310,y:100,z:50,r:9});
 reply=await command({action:'xyz',xyz:{x:600,y:100,z:50},control_revision:rawRevision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);
 // Parent projection, same-origin checks, normalized commands, stale-state gating.
 let receive,output=[],shade={},line={},hidden;
 const frame={contentWindow:{postMessage:d=>output.push(d)},getAttribute:()=>'/bridge'};
 const overlay={toggleAttribute:(k,v)=>hidden=v,setAttribute(){},querySelector:q=>({setAttribute:(k,v)=>(q.includes('shade')?shade:line)[k]=v})};
 let timerId=0;const timers=new Map(),advance=ms=>{now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}};
 const pc={window:{addEventListener:(k,f)=>receive=f},location:{origin:'http://test',pathname:'/s/'+TEAM+'/'},performance:{now:()=>now},Date,document:{hidden:false},setTimeout:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id)};vm.createContext(pc);vm.runInContext(fs.readFileSync('shared/mobile_ltz/physical-arm.js','utf8')+'\nthis.Adapter=MobilePhysicalArm;',pc);
 const adapter=new pc.Adapter({frame,overlay,viewport:{w:1000,h:500},team:TEAM});adapter.active=true;
 const snapshot=posted.find(p=>p.status==='ready'&&p.arm?.session);receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,contract:(TEAM==='green'?'purple':'green')+'.mobile-arm'}});assert.equal(adapter.arm(),null,'Opposite-team feedback is ignored');
 receive({source:frame.contentWindow,origin:'http://evil',data:snapshot});assert.equal(adapter.arm(),null);
 receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,type:'state'}});assert(Math.abs(adapter.arm().tip.x-300)<1e-9);assert(Math.abs(adapter.arm().tip.y-50)<1e-9);assert.equal(hidden,false);assert.match(shade.d,/M0.00,0.00/);assert.match(line.d,/100.00,50.00/);
 const limited=adapter.command({action:'joints',joints:[1,2,3]});const limitedId=output.at(-1).id;
 receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,type:'reply',id:limitedId,ok:false,code:'motion_limit',error:'Safety limit reached.'}});
 await assert.rejects(limited,e=>e.code==='motion_limit'&&e.arm.connected&&e.arm.session===snapshot.arm.session);
 assert.equal(output.at(-1).id,limitedId,'A rejected target must not send Stop/disconnect from the adapter');
 const pending=adapter.command({action:'xyz',xyz:{x:500,y:125,z:60}});assert.equal(output.at(-1).data.xyz.x,.5);assert.equal(output.at(-1).data.xyz.y,.25);
 const waypointPending=adapter.command({action:'cue_waypoint',point:{x:250,y:375}});assert.equal(output.at(-1).data.x,.25);assert.equal(output.at(-1).data.y,.75);assert.equal(output.at(-1).data.point,undefined);
 adapter.stop();await assert.rejects(pending,/stopped/);await assert.rejects(waypointPending,/stopped/);now+=1600;assert.equal(adapter.arm(),null);adapter.draw();assert.equal(hidden,true);
 const publish=extra=>receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,type:'state',...extra}});
 publish();let long=adapter.command({action:'xyz',session:snapshot.arm.session,xyz:{x:500,y:125,z:60}}),longId=output.at(-1).id;
 for(let i=0;i<4;i++){advance(10000);publish({active_command:{id:longId,action:'xyz',session:snapshot.arm.session}});}
 assert(adapter.pending.has(longId),'A healthy active detour remains connected beyond 15 seconds');
 receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,type:'reply',id:longId,ok:true}});await long;
 for(const invalid of ['wrong-id','wrong-session','unavailable']){
  publish();long=adapter.command({action:'xyz',session:snapshot.arm.session,xyz:{x:500,y:125,z:60}});longId=output.at(-1).id;
  const failed=assert.rejects(long,/timed out/);advance(14000);
  publish({status:invalid==='unavailable'?'unavailable':'ready',active_command:{id:invalid==='wrong-id'?'old':longId,action:'xyz',session:invalid==='wrong-session'?'old':snapshot.arm.session}});
  advance(1001);await failed;assert.equal(adapter.pending.size,0,invalid+' cannot keep a command alive');
 }
 publish();long=adapter.command({action:'xyz',session:snapshot.arm.session,xyz:{x:500,y:125,z:60}});longId=output.at(-1).id;
 const bounded=assert.rejects(long,/timed out/);
 for(let i=0;i<17;i++){advance(10000);publish({active_command:{id:longId,action:'xyz',session:snapshot.arm.session}});}
 advance(10000);await bounded;assert.equal(adapter.pending.size,0,'Even fresh progress has a three-minute absolute deadline');
 console.log('PASS: bridge origin/session/revision checks, real joint guard, calibrated XY/Z, pump-off, stop, projection and expiry');
})().catch(e=>{console.error(e);process.exitCode=1;});
