/* Contract and hardware routing tests with a fake relay. Never moves hardware. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const TEAM=process.env.MOBILE_TEST_TEAM==='purple'?'purple':'green';
let jointFailure=null,holdFailure=null,moveFailure=null,holdWait=null,jointWait=null,moveWait=null,clickedTags=[];
let now=100,calls=[],posted=[],listener,intervals=[],robot={connected:true,enabled:true,feedback_ok:true,last_feedback:Date.now()/1000,robot_mode:5,motion_ready:true,motion_epoch:0,control_session:'initial',pose:[300,100,50,9],joints:[0,20,30,9],pump_mode:'off'};
const parent={postMessage:d=>posted.push(d)},nodes=new Map();
const gid=id=>{if(!nodes.has(id))nodes.set(id,{checked:false,value:'http://relay.test',textContent:'Ready',removeAttribute(){}});return nodes.get(id);};
// Purple's stored calibration view is rotated. Its bridge must still send raw
// camera coordinates to the mobile viewport and use calibrated robot poses.
gid('flipToggle').checked=TEAM==='purple';
const displayPoint=(u,v)=>gid('flipToggle').checked?{u:1-u,v:1-v}:{u,v};
const ctx={TEAM,MOBILE_LTZ:true,URLSearchParams,location:{search:'?ltz=1&mobile=1&bridge=1',origin:'http://test'},parent,window:{addEventListener:(name,fn)=>{listener=fn;}},performance:{now:()=>now},Date,crypto:{getRandomValues:array=>array.fill(1)},setInterval:fn=>intervals.push(fn),gid,
 gameArmCal2:()=>({points:6}),gameCalibration2:{},gameRadiusMin:150,gameRadiusMax:440,ws:{z:[-150,230]},jointLimits:{j1:[-160,160],j2:[-25,85],j3:[-25,105]},
 cal2CalibrationSamples:()=>Array(6).fill({}),cal2JointSafetyGuard:()=>({format:'auto-pp-calibration-2-v1',radius_min:220,polygon:[[1,2],[3,4],[5,6]]}),cal2ReachBoundary:()=>[[.1,.1],[.9,.1],[.9,.9],[.1,.9]].map(([u,v])=>displayPoint(u,v)),
 cal2PoseEvaluator:()=>()=>({x:300,y:0}),pointInsideConvexCalibration:()=>true,pointInsideRobotPolygon:()=>true,compensateCal2Parallax:(u,v)=>({u,v}),cal2CameraTargetPose:p=>p,autoPpxPlanningRadiusMin:()=>220,cal2CameraForRobotPose:(_,p)=>displayPoint(p.x/1000,p.y/1000),gameDisplayPoint:displayPoint,clickToPose:(u,v,id)=>{clickedTags.push(id);const p=displayPoint(u,v);return {x:p.u*1000,y:p.v*1000,z:50,r:9};},assertAutoPpxPoseSafe(){},
 mobileGameAt:now,mobileGame:{server_time:10000,mobile_camera:{status:'ready',frame_at:10000,width:1280,height:720,matrix:[1,0,0,0,1,0,0,0]},virtual_test_control:4,mobile_arm:{tags:[{id:101}]},mobile_safety:{status:'ready'}},latestVisibleArucoTags:[],autoPpxCueRunning:false,autoPpxRunning:false,autoPpxPaused:false,autoPpxAbort:false,activeOperation:null,cal2BoundaryStop:null,
 autoPpxVisionWait:null,autoPpxCueOutcome:'idle',autoPpxCueError:null,autoPpxClickOverride:null,
 autoPpxTransportZ:()=>80,autoPpxCueMapReady:()=>true,autoPpxCueEndpointIssue:()=>'',autoPpxCueDisplayTags:()=>ctx.latestVisibleArucoTags,autoPpxCueCandidates:()=>({sources:[{id:101}],destinations:[{id:42,cached:true}]}),refreshAutoPpxTags:async()=>[],
 readAutoPpxCueTargets:async force=>{assert.equal(force,true);return ctx.latestVisibleArucoTags;},
 ltzTier:4,mobileControlChoice:1,mobileRobotReady:()=>true,pauseUserMoves(){},cancelAutoPpxClickOverride(){},applyStatus(){},
 api:async(path,data)=>{calls.push({path,data});if(path==='/api/stop'&&holdWait)await holdWait;if(path==='/api/joint-move'&&jointWait)await jointWait;if(path==='/api/connect'){robot={...robot,control_session:'relay:'+calls.length,motion_epoch:robot.motion_epoch+1,last_feedback:Date.now()/1000};return {ok:true,control_session:robot.control_session};}return path==='/api/status'?{...robot}:path==='/api/joint-move'&&jointFailure?{ok:false,error:jointFailure}:path==='/api/stop'&&holdFailure?{ok:false,error:holdFailure}:{ok:true};},moveToPose:async(p,label,wait,options)=>{if(moveFailure)throw typeof moveFailure==='string'?Error(moveFailure):moveFailure;calls.push({path:'planned',p,label,options});if(moveWait)await moveWait;},
};vm.createContext(ctx);
const controller=fs.readFileSync('shared/robot_controls/controller.html','utf8');
vm.runInContext(controller.slice(controller.indexOf('function mobileCalibrationKeepsSuction('),controller.indexOf('function haltMobileRobot(')),ctx);
vm.runInContext(controller.slice(controller.indexOf('function autoPpxClearViewRow('),controller.indexOf('async function captureAutoPpxQueuePoses(')),ctx);
vm.runInContext(fs.readFileSync('shared/mobile_ltz/arm-bridge.js','utf8'),ctx);
const flush=async()=>{for(let i=0;i<12;i++)await new Promise(r=>setImmediate(r));};
let id=0,session,seq=0,revision=0;
async function command(data,origin='http://test',contract=TEAM+'.mobile-arm'){const key=String(++id);listener({origin,source:parent,data:{contract,version:1,type:'command',id:key,data:{control_revision:revision,...data,...(session?{session,sequence:++seq}:{})}}});await flush();const reply=posted.find(p=>p.id===key);if(reply?.arm)revision=reply.arm.control_revision;return reply;}
(async()=>{
 await flush();assert.equal(posted.at(-1).status,'ready');
 assert.equal(posted.at(-1).arm.position_at,robot.last_feedback,'Position timestamp is the measurement time');
 const boardEvidence={status:'partial',epoch:7,pending_fixed_ids:[48],verification:{anchor_ids:[40,41,42,43],hull:[[0,0],[1,0],[0,1]]}};
 ctx.autoPpxCueEvidence=()=>({data:boardEvidence});parent.performance={now:()=>now};
 ctx.window.mobileArmDiagnostic('cue_motion_held','off',{tag_id:49});
 assert.equal(posted.pop().context.board,undefined,'Extra decision evidence is off with recording');
 parent.mobileDelay={active:true,begin:()=>null,end:()=>{}};ctx.applyStatus({...robot,servo_error:'Fixture IPC timeout'});
 ctx.window.mobileArmDiagnostic('cue_motion_held','on',{tag_id:49});
 const captured=posted.pop();assert.deepEqual(captured.context.board.verification,boardEvidence.verification);
 assert.equal(captured.context.servo_error,'Fixture IPC timeout');
 ctx.autoPpxCueEvidence=()=>{throw Error('unavailable evidence');};
 ctx.window.mobileArmDiagnostic('cue_motion_held','still reported',{tag_id:49});
 assert.equal(posted.pop().reason,'still reported');
 delete parent.mobileDelay;ctx.applyStatus(robot);
 const publishedAt=posted.at(-1).arm.position_at;
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 assert.equal(posted.at(-1).arm.position_at,publishedAt,'Republishing cannot retimestamp a measurement');
 assert.equal(posted.at(-1).arm.position_settled,false,'Repeated copies of one measurement cannot confirm a stop');
 const original=robot;
 const feedback=async fields=>{await new Promise(resolve=>setTimeout(resolve,100));robot={...robot,...fields,last_feedback:Date.now()/1000};ctx.applyStatus(robot);};
 await feedback({});
 assert.equal(posted.at(-1).arm.position_settled,true,'Two distinct fresh stationary idle poses confirm a display stop');
 assert.equal(posted.at(-1).arm.position_at,robot.last_feedback,'Status is published immediately without waiting for the bridge timer');
 await feedback({pose:[301,100,50,9]});
 assert.equal(posted.at(-1).arm.position_settled,false,'Idle mode alone does not imply that the arm is stationary');
 await feedback({robot_mode:7});
 assert.equal(posted.at(-1).arm.position_settled,false,'Running status cannot confirm a stop');
 await feedback(original);
 ctx.mobileGame.mobile_safety={status:'unavailable',error:'Green camera correction changed. Recalibrate before moving.'};
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 assert.equal(posted.at(-1).status,'ready','Measured feedback remains usable for connection recovery');assert.equal(posted.at(-1).geometry,null);assert.equal(posted.at(-1).arm.motion_ready,false);assert.match(posted.at(-1).arm.message,/camera correction changed/);
 assert.equal(posted.at(-1).arm.coordinate_space,'robot-mm','Do not use an outdated camera fit to show the measured position');
 const blockedConnect=await command({action:'connect'});assert(blockedConnect.ok);session=blockedConnect.arm.session;
 const staleMoveCount=calls.filter(c=>c.path==='/api/joint-move').length;
 const blockedMove=await command({action:'joints',joints:[1,22,33],control_revision:revision});assert(!blockedMove.ok);assert.match(blockedMove.error,/camera correction changed/);
 assert.equal(calls.filter(c=>c.path==='/api/joint-move').length,staleMoveCount);
 ctx.mobileGame.mobile_safety={status:'ready'};
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 assert.equal(posted.at(-1).status,'ready');assert(posted.at(-1).geometry,'Readiness recovers even when saved geometry is unchanged');
 const samples=calls.filter(c=>c.path==='/api/status').length;now+=700;
 listener({source:parent,origin:'http://test',data:{contract:TEAM+'.mobile-arm',version:1,type:'ping'}});await flush();
 assert(calls.filter(c=>c.path==='/api/status').length>samples,'Parent heartbeat refreshes feedback even when iframe timers are throttled');
 assert.equal(await command({action:'connect'},'http://evil'),undefined);
 assert.equal(await command({action:'connect'},'http://test',(TEAM==='green'?'purple':'green')+'.mobile-arm'),undefined,'A team cannot use the other arm bridge');
 let reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;assert(session.startsWith('physical:'));
 const movesBeforePath=calls.filter(c=>c.path==='/api/move'||c.path==='planned').length;
 ctx.window.mobileArmPath([{x:320,y:100,z:60},{x:350,y:200,z:60}]);
 reply=await command({action:'state'});
 assert(reply.arm.motion_path.points.length>3,'Robot segments are sampled before camera projection');
 assert(Math.abs(reply.arm.motion_path.points[0].x-.3)<1e-9);
 assert(Math.abs(reply.arm.motion_path.points.at(-1).x-.35)<1e-9);
 assert(Math.abs(reply.arm.motion_path.points.at(-1).y-.2)<1e-9,'Purple calibration is returned to raw camera orientation');
 assert.equal(calls.filter(c=>c.path==='/api/move'||c.path==='planned').length,movesBeforePath,'Path telemetry never sends movement');
 ctx.window.mobileArmPath(null);reply=await command({action:'state'});assert.equal(reply.arm.motion_path,null);
 // The shared controller receives these bounds from the relay. The bridge
 // must pass them through to both teams' mobile height sliders unchanged.
 ctx.ws.z=[-102,80];reply=await command({action:'state'});
 assert.deepEqual(Array.from(reply.arm.xyz_limits.z),[-102,80]);
 ctx.ws.z=[-102,65];reply=await command({action:'state'});
 assert.deepEqual(Array.from(reply.arm.xyz_limits.z),[-102,65]);
 ctx.ws.z=[-150,230];
 assert.equal(calls.find(c=>c.path==='/api/connect').data.side,TEAM);assert(!calls.some(c=>c.path==='/api/enable'),'Connect must not enable');
 reply=await command({action:'joints',joints:[1,22,33],control_revision:revision});assert(reply.ok);
 const move=calls.find(c=>c.path==='/api/joint-move');assert.equal(move.data.j4,9);assert.equal(move.data.cal2_guard.format,'auto-pp-calibration-2-v1');
 // Reconnect follows the arm after manual relocation; never replay old goals.
 const originalRobot={...robot};
 await command({action:'stop'});
 robot={...robot,joints:[-30,40,55,9],pose:[350,90,70,9]};ctx.applyStatus(robot);
 const beforeReconnectMoves=calls.filter(c=>c.path==='/api/joint-move'||c.path==='planned').length;
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 assert.deepEqual(Array.from(reply.arm.targets),[-30,40,55]);
 assert.equal(calls.filter(c=>c.path==='/api/joint-move'||c.path==='planned').length,beforeReconnectMoves);
 // An old status response cannot overwrite the replacement connection.
 ctx.applyStatus(originalRobot);
 reply=await command({action:'heartbeat'});assert.deepEqual(Array.from(reply.arm.joints),[-30,40,55]);
 // A brief physical unlock invalidates the session even if relocked immediately.
 robot={...robot,robot_mode:6,motion_ready:false,motion_epoch:robot.motion_epoch+1};ctx.applyStatus(robot);
 const unlockLog=posted.findLast(p=>p.type==='diagnostic'&&p.event==='motion_epoch_changed');
 assert(unlockLog,'Physical unlock records its exact disconnect cause');
 assert.equal(unlockLog.context.robot_mode,6);assert.equal(unlockLog.context.motion_ready,false);
 assert(!('session' in unlockLog.context));assert(!('token' in unlockLog.context));
 robot={...robot,robot_mode:5,motion_ready:true,joints:[-35,42,53,9]};ctx.applyStatus(robot);
 reply=await command({action:'heartbeat'});assert.equal(reply.arm.session,null);
 assert.deepEqual(Array.from(reply.arm.targets),[-35,42,53]);
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 // Stop while a joint command reply is delayed. Its eventual success must not
 // repopulate an old goal or contaminate a later Connect.
 let finishJoint;jointWait=new Promise(resolve=>finishJoint=resolve);
 const pendingMoveId=String(id+1);await command({action:'joints',joints:[1,22,33]});
 await command({action:'stop'});finishJoint();jointWait=null;await flush();
 assert.equal(posted.find(p=>p.id===pendingMoveId).ok,false);
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 assert.deepEqual(Array.from(reply.arm.targets),[-35,42,53]);
 robot={...originalRobot,control_session:robot.control_session,motion_epoch:robot.motion_epoch,last_feedback:Date.now()/1000};ctx.applyStatus(robot);
 reply=await command({action:'joints',joints:[1,22,33]});assert(reply.ok);
 const tokenBefore=session;
 jointFailure='Auto PP Cal 2 blocked joint path at 100%: joint target TCP radius 211.5 mm is outside the Auto PP Cal 2 limit 220.0-450.0 mm';
 const connectCount=calls.filter(c=>c.path==='/api/connect').length,pumpCount=calls.filter(c=>c.path==='/api/pump').length;
 reply=await command({action:'joints',joints:[1,22,75],control_revision:revision});
 assert(!reply.ok);assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,tokenBefore);assert(reply.arm.connected);
 assert.deepEqual(Array.from(reply.arm.targets),robot.joints.slice(0,3));
 assert(calls.slice(-4).some(c=>c.path==='/api/stop'));assert.equal(calls.filter(c=>c.path==='/api/pump').length,pumpCount,'Boundary rejection keeps the gripper state');
 jointFailure=null;reply=await command({action:'joints',joints:[1,22,25],control_revision:revision});assert(reply.ok,'A safe retreat works with the existing session');
 jointFailure='Auto PP Cal 2 blocked joint path at 50%: Z ceiling 80 mm exceeded by joint path (82.0 mm)';
 reply=await command({action:'joints',joints:[1,22,25],control_revision:revision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);assert.match(reply.error,/Z ceiling 80/);jointFailure=null;
 assert.equal(calls.filter(c=>c.path==='/api/connect').length,connectCount);
 jointFailure='could not verify joint target against Auto PP Cal 2: feedback unavailable';
 reply=await command({action:'joints',joints:[1,22,25],control_revision:revision});assert(!reply.ok);assert.notEqual(reply.code,'motion_limit','Unknown/FK faults are not recoverable boundary events');jointFailure=null;
 ctx.ltzTier=3;const beforeModeRevision=revision;reply=await command({action:'control_mode',mode:'targeting'});assert(reply.ok);assert.equal(reply.arm.control_revision,beforeModeRevision+1);
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60},control_revision:revision});assert(reply.ok);assert(Math.abs(calls.find(c=>c.path==='planned').p.x-300)<1e-9);assert(Math.abs(calls.find(c=>c.path==='planned').p.y-400)<1e-9);assert.equal(calls.find(c=>c.path==='planned').p.z,60);
 // XYZ goals also reset to measured feedback after reconnection.
 const beforeXYZReconnect={...robot};
 await command({action:'stop'});robot={...robot,pose:[370,80,90,9]};ctx.applyStatus(robot);
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 assert.deepEqual({...reply.arm.xyz_target},{...reply.arm.tip});
 assert(Math.abs(reply.arm.xyz_target.x-.37)<1e-9);assert.equal(reply.arm.xyz_target.z,90);
 robot={...beforeXYZReconnect,control_session:robot.control_session,motion_epoch:robot.motion_epoch,last_feedback:Date.now()/1000};ctx.applyStatus(robot);
 const own=TEAM==='green'?100:102,tagPoint=displayPoint(.3,.4);
 assert.equal(calls.find(c=>c.path==='planned').options.allowDetour,true,'Targeting can route around an excluded area');
 ctx.mobileGame.movable_piece_codes={[TEAM]:[own]};ctx.latestVisibleArucoTags=[{id:own,nx:tagPoint.u,ny:tagPoint.v,lastSeenAt:Date.now(),missing:0}];
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(reply.ok);assert.equal(clickedTags.at(-1),own,'Visible owned Atom reaches the raised-tag correction once');
 // Reproduce Go between the 500 ms expiry and the 750 ms background poll:
 // the latest owner observation is fresh even though the polled list is stale.
 const readTags=ctx.readAutoPpxCueTargets;
 ctx.latestVisibleArucoTags[0].lastSeenAt=Date.now()-600;
 ctx.readAutoPpxCueTargets=async force=>{assert.equal(force,true);return [{...ctx.latestVisibleArucoTags[0],lastSeenAt:Date.now()}];};
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(reply.ok,'Go refreshes acquisition instead of rejecting a healthy preview');assert.equal(clickedTags.at(-1),own);
 const freshTag={...ctx.latestVisibleArucoTags[0],lastSeenAt:Date.now()};
 for(const [label,tag] of [['foreign',{...freshTag,id:own+1}],['stale',{...freshTag,lastSeenAt:Date.now()-600}],['hidden',{...freshTag,obscured:true}],['moved',{...freshTag,nx:tagPoint.u+.1}],['future',{...freshTag,lastSeenAt:Date.now()+1000}],['invalid',{...freshTag,nx:NaN}]]){
  ctx.readAutoPpxCueTargets=async()=>[tag];
  const before=calls.length,clicked=clickedTags.length;
  reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});
  assert(!reply.ok,label);assert.equal(reply.code,'target_unavailable',label);assert.equal(reply.arm.session,session);assert(reply.arm.connected);
  assert.equal(clickedTags.length,clicked,'Rejected '+label+' target has no untagged fallback');
  assert(calls.slice(before).some(c=>c.path==='/api/stop'),'Rejecting '+label+' holds the previous goal');
  assert(!calls.slice(before).some(c=>['planned','/api/move','/api/pump','/api/disconnect','/api/connect'].includes(c.path)),label+' preserves pump and session without movement');
 }
 ctx.readAutoPpxCueTargets=async()=>{throw Error('Camera owner unavailable');};
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(!reply.ok);assert.notEqual(reply.code,'target_unavailable','Unknown camera/transport faults are not recoverable target rejections');
 ctx.readAutoPpxCueTargets=async()=>[freshTag];ctx.autoPpxCueMapReady=()=>false;
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(!reply.ok);assert.notEqual(reply.code,'target_unavailable','Unverified mapping stays fail-closed');ctx.autoPpxCueMapReady=()=>true;
 ctx.autoPpxCueEndpointIssue=()=> 'quarantined';
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(!reply.ok);assert.equal(reply.code,'target_unavailable');assert.equal(reply.arm.session,session);
 ctx.autoPpxCueEndpointIssue=()=> 'camera';
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(!reply.ok);assert.notEqual(reply.code,'target_unavailable');ctx.autoPpxCueEndpointIssue=()=>'';
 ctx.readAutoPpxCueTargets=async()=>[];holdFailure='Relay connection lost';
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});assert(!reply.ok);assert.notEqual(reply.code,'target_unavailable');assert.equal(reply.arm.session,null,'A target rejection cannot retain control when its hold fails');
 holdFailure=null;reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 // A delayed camera read must not restart a target after the player presses Stop.
 let finishTags;ctx.readAutoPpxCueTargets=()=>new Promise(resolve=>finishTags=resolve);
 const pendingTagId=String(id+1),beforeTagMoves=calls.filter(c=>c.path==='planned').length;
 await command({action:'xyz',xyz:{x:.3,y:.4,z:60,tag_id:own},control_revision:revision});
 await command({action:'stop'});finishTags([{...freshTag,lastSeenAt:Date.now()}]);await flush();
 assert.equal(posted.find(p=>p.id===pendingTagId).ok,false);assert.equal(calls.filter(c=>c.path==='planned').length,beforeTagMoves);
 ctx.readAutoPpxCueTargets=readTags;ctx.latestVisibleArucoTags=[];
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 reply=await command({action:'xyz',xyz:{x:2,y:.4,z:60},control_revision:revision});assert(!reply.ok);assert.equal(reply.code,'motion_limit');assert.match(reply.detail,/outside/);assert.equal(reply.arm.session,session);
 holdFailure='Relay connection lost';
 reply=await command({action:'xyz',xyz:{x:2,y:.4,z:60},control_revision:revision});assert(!reply.ok);assert.notEqual(reply.code,'motion_limit');assert.equal(reply.arm.session,null,'Failed safe hold releases the mobile session');
 holdFailure=null;reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 reply=await command({action:'xyz',xyz:{x:.3,y:.4,z:60},control_revision:-1});assert(!reply.ok);assert.equal(reply.code,'control_changed');assert.equal(reply.arm.session,session);
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
 // Cue submission refreshes the map instead of rejecting a 600ms-old UI snapshot.
 revision=posted.at(-1).arm.control_revision;
 const cueSource={value:''},cueTarget={value:''};
 const cueRow={querySelector:selector=>selector==='.autoPpxSource'?cueSource:cueTarget};gid('autoPpxQueue').querySelectorAll=()=>[cueRow];
 ctx.setAutoPpxStoredSelectValue=(node,value)=>{node.value=value;};
 ctx.latestVisibleArucoTags=[{id:101,nx:.3,ny:.4,lastSeenAt:Date.now()-600,missing:0}];
 let finishMap,reads=0;ctx.refreshAutoPpxTags=async()=>{reads++;await new Promise(resolve=>finishMap=resolve);};
 const pendingCueId=String(id+1);await command({action:'cue_set',rows:[{piece:101,destination:42}]});
 assert.equal(reads,1);assert.equal(posted.find(p=>p.id===pendingCueId),undefined,'Map read must finish before queue validation');
 finishMap();await flush();assert(posted.find(p=>p.id===pendingCueId).ok);
 const beforeMismatch=calls.length;
 reply=await command({action:'cue_play',rows:[{piece:101,destination:47}]});
 assert(!reply.ok);assert.match(reply.error,/selection changed/);assert.equal(calls.length,beforeMismatch,'Mismatched target never starts the cue');
 const cancelledCueId=String(id+1);await command({action:'cue_set',rows:[{piece:101,destination:42}]});
 await command({action:'stop'});finishMap();await flush();assert(!posted.find(p=>p.id===cancelledCueId).ok,'Stop wins over a late camera response');
 ctx.refreshAutoPpxTags=async()=>[];
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 ctx.latestVisibleArucoTags=[];
 // Idle map clicks use the existing calibrated image planner, with no
 // source Atom or cue rows required, and preserve queue and pump state.
 const beforeTap=reply.arm.cue,previousPump=robot.pump_mode,pumpCalls=calls.filter(c=>c.path==='/api/pump').length;
 reply=await command({action:'cue_waypoint',x:.32,y:.42});assert(reply.ok);
 let idleMove=calls.filter(c=>c.path==='planned').at(-1);
 assert(Math.abs(idleMove.p.x-320)<1e-9&&Math.abs(idleMove.p.y-420)<1e-9);assert.equal(idleMove.p.z,80);assert.equal(idleMove.p.r,9);assert.equal(idleMove.label,'video target');assert.equal(idleMove.options.allowDetour,true);
 assert.equal(reply.arm.xyz_target.x,.32);assert.equal(reply.arm.xyz_target.y,.42);
 assert.deepEqual(reply.arm.cue.rows,beforeTap.rows);assert.equal(reply.arm.cue.status,beforeTap.status);
 assert.equal(reply.arm.cue.waypoint,null);assert.equal(robot.pump_mode,previousPump);
 assert.equal(calls.filter(c=>c.path==='/api/pump').length,pumpCalls);
 ctx.autoPpxCueMapReady=()=>false;
 ctx.mobileGame.mobile_cue_targets={status:'unavailable',error:'Checking fixed marker #54 after a conflicting camera detection.',pending_fixed_ids:[54]};
 reply=await command({action:'cue_waypoint',x:.32,y:.42});assert(reply.ok,'A fresh calibrated image can reposition the arm despite a tag-map hold');
 assert.equal(calls.filter(c=>c.path==='/api/pump').length,pumpCalls);
 const plannedCount=calls.filter(c=>c.path==='planned').length;
 const camera={...ctx.mobileGame.mobile_camera};
 for(const change of [{status:'unavailable'},{frame_at:9998},{frame_at:10001},{frame_at:NaN},{width:0},{matrix:[1,2]}]){
  ctx.mobileGame.mobile_camera={...camera,...change};
  reply=await command({action:'cue_waypoint',x:.32,y:.42});assert(!reply.ok);assert.match(reply.error,/camera image/i);
 }
 ctx.mobileGame.mobile_camera=camera;ctx.mobileGameAt=now-1600;
 reply=await command({action:'cue_waypoint',x:.32,y:.42});assert(!reply.ok,'An old game receipt cannot keep a camera frame fresh');
 ctx.mobileGameAt=now;
 ctx.autoPpxCueMapReady=()=>true;
 for(const point of [{x:-.1,y:.5},{x:.5,y:NaN},{x:.5,y:1.1}]){
  reply=await command({action:'cue_waypoint',...point});assert(!reply.ok);
 }
 assert.equal(calls.filter(c=>c.path==='planned').length,plannedCount);
 let finishIdle;moveWait=new Promise(resolve=>finishIdle=resolve);
 const idleId=String(id+1);await command({action:'cue_waypoint',x:.35,y:.4});
 assert.equal(posted.find(p=>p.id===idleId),undefined);
 await command({action:'stop'});finishIdle();moveWait=null;await flush();
 assert(!posted.find(p=>p.id===idleId).ok,'Stop wins over an idle detour completion');
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 assert.equal(reply.arm.cue.waypoint,null);assert(Math.abs(reply.arm.xyz_target.x-robot.pose[0]/1000)<1e-9);
 // An active or paused cue still uses its existing intervention owner.
 let overrides=0;
 ctx.videoClickSeq=0;ctx.beginAutoPpxClickOverride=(seq,kind)=>ctx.autoPpxClickOverride={id:seq,clickSeq:seq,kind};
 ctx.performAutoPpxClickOverride=async p=>{overrides++;return p;};ctx.finishAutoPpxClickOverride=()=>{ctx.autoPpxClickOverride=null;};
 ctx.cancelAutoPpxClickOverride=()=>{ctx.autoPpxClickOverride=null;};
 ctx.toggleAutoPpxPause=()=>{ctx.autoPpxPaused=!ctx.autoPpxPaused;};
 // Hold commands still authenticate but bypass stale mapping/new-motion gates.
 ctx.autoPpxCueRunning=true;ctx.mobileRobotReady=()=>false;
 const beforePausePumps=calls.filter(c=>c.path==='/api/pump').length;
 reply=await command({action:'cue_pause',control_revision:-1});assert(reply.ok);assert(ctx.autoPpxPaused);
 assert.equal(calls.filter(c=>c.path==='/api/pump').length,beforePausePumps);
 const validSession=session;session='invalid';ctx.autoPpxPaused=false;
 reply=await command({action:'cue_pause'});assert(!reply.ok);assert(!ctx.autoPpxPaused);
 session=validSession;ctx.stopAutoPpx=async()=>{ctx.autoPpxCueRunning=false;};
 reply=await command({action:'cue_stop',control_revision:-1});assert(reply.ok);assert(!ctx.autoPpxCueRunning);
 ctx.mobileRobotReady=()=>true;

 for(const paused of [false,true]){
  ctx.autoPpxCueRunning=true;ctx.autoPpxPaused=paused;
  ctx.autoPpxCueMapReady=()=>false;robot.pump_mode='suck';
  const beforeImagePumps=calls.filter(c=>c.path==='/api/pump').length;
  reply=await command({action:'cue_waypoint',x:.31,y:.41});assert(reply.ok);
  assert.equal(ctx.autoPpxPaused,paused);assert.equal(robot.pump_mode,'suck');
  assert.equal(calls.filter(c=>c.path==='/api/pump').length,beforeImagePumps,'Recovery image click preserves suction');
 }
 assert.equal(overrides,2);ctx.autoPpxCueRunning=ctx.autoPpxPaused=false;ctx.autoPpxCueMapReady=()=>true;robot.pump_mode='off';
 // Cue height uses measured XY directly and cannot sneak in a lateral target.
 let cueRevision=posted.at(-1).arm.control_revision;
 reply=await command({action:'xyz',height_only:true,xyz:{x:.8,y:.9,z:51},control_revision:cueRevision});assert(reply.ok);
 let planned=calls.filter(c=>c.path==='planned').at(-1);assert.equal(planned.p.x,robot.pose[0]);assert.equal(planned.p.y,robot.pose[1]);assert.equal(planned.p.z,51);
 assert.equal(planned.options.allowDetour,false,'Manual height never moves sideways around a barrier');
 reply=await command({action:'xyz',xyz:{x:.8,y:.9,z:51},control_revision:cueRevision});assert(!reply.ok,'Cue cannot send manual XY');
 const interventions=[];
 const heightRows=JSON.stringify(reply.arm.cue.rows);
 ctx.performAutoPpxClickOverride=async(p,override,options)=>{interventions.push({p,override,options});return p;};
 for(const paused of [false,true]){
  ctx.autoPpxCueRunning=true;ctx.autoPpxPaused=paused;
  reply=await command({action:'xyz',height_only:true,xyz:{x:.9,y:.9,z:52},control_revision:cueRevision});assert(reply.ok);
  const intervention=interventions.at(-1);
  assert.equal(intervention.options.heightOnly,true);assert.equal(intervention.override.kind,'height');
  assert.equal(intervention.p.x,robot.pose[0]);assert.equal(intervention.p.y,robot.pose[1]);assert.equal(intervention.p.z,52);
  assert.equal(ctx.autoPpxPaused,paused);assert.equal(JSON.stringify(reply.arm.cue.rows),heightRows);
 }
 const interventionCount=interventions.length;
 reply=await command({action:'xyz',height_only:true,xyz:{z:NaN},control_revision:cueRevision});assert(!reply.ok);assert.equal(interventions.length,interventionCount);
 reply=await command({action:'xyz',height_only:true,xyz:{z:999},control_revision:cueRevision});assert(!reply.ok);assert.equal(interventions.length,interventionCount);
 ctx.autoPpxPaused=false;
 const pumpsBeforeFailure=calls.filter(c=>c.path==='/api/pump').length;
 ctx.performAutoPpxClickOverride=async()=>{throw Object.assign(Error('Height outside the permitted area'),{code:'motion_limit'});};
 reply=await command({action:'xyz',height_only:true,xyz:{z:55},control_revision:cueRevision});assert(reply.ok);
 assert(ctx.autoPpxPaused,'A rejected override cannot silently resume the cue');
 assert.equal(calls.filter(c=>c.path==='/api/pump').length,pumpsBeforeFailure,'Failed override preserves suction');
 assert.equal(ctx.autoPpxClickOverride,null);
 let finishOld,finishNew;
 ctx.performAutoPpxClickOverride=()=>new Promise(resolve=>{if(!finishOld)finishOld=resolve;else finishNew=resolve;});
 await command({action:'xyz',height_only:true,xyz:{z:55},control_revision:cueRevision});
 await command({action:'xyz',height_only:true,xyz:{z:56},control_revision:cueRevision});
 finishOld({x:1,y:2,z:55});await flush();assert(ctx.autoPpxClickOverride,'Old completion must not end the newest override');
 await command({action:'stop'});finishNew({x:1,y:2,z:56});await flush();assert.equal(posted.at(-1).arm.session,null,'Stop prevents a late height completion restoring the session');
 ctx.autoPpxCueRunning=ctx.autoPpxPaused=false;
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 cueRevision=reply.arm.control_revision;
 moveFailure='joint target TCP is outside the Auto PP Cal 2 arm boundary';
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);
 moveFailure='Z ceiling 80 mm exceeded; choose a lower target';
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);assert.match(reply.error,/Z ceiling 80/);
 moveFailure='Cannot validate Cartesian path: safety limits missing';
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert(!reply.ok);assert.notEqual(reply.code,'motion_limit');moveFailure=null;
 moveFailure=Object.assign(Error('mobile XYZ start is inside the red Cal 2 exclusion area'),{code:'motion_limit'});
 reply=await command({action:'xyz',height_only:true,xyz:{z:51},control_revision:cueRevision});assert.equal(reply.code,'motion_limit');assert.equal(reply.arm.session,session);
 moveFailure=null;reply=await command({action:'xyz',height_only:true,xyz:{z:52},control_revision:cueRevision});assert(reply.ok,'A valid move recovers after a typed planner limit');
 // An unchanged saved cue can start again after completion or Stop. Each new
 // run rebuilds the controller selects and refreshes mapping, just as cue_set
 // does, even if a camera-options refresh changed the hidden selections.
 let cueStarts=0,mapReads=0;
 ctx.refreshAutoPpxTags=async()=>{mapReads++;};
 ctx.runAutoPpx=async()=>{
  cueStarts++;
  assert.equal(cueSource.value,'101');assert.equal(cueTarget.value,'42');
  assert.equal(gid('autoPpxLoop').checked,false);
  ctx.autoPpxCueOutcome='completed';
 };
 for(let run=0;run<3;run++){
  if(run===2)await command({action:'cue_stop'});
  cueSource.value='';cueTarget.value='47';gid('autoPpxLoop').checked=true;
  // Receipt field order has no bearing on which saved cue was requested.
  reply=await command({action:'cue_play',rows:[run===1?{destination:42,piece:101}:{piece:101,destination:42}]});
  assert(reply.ok);assert.equal(reply.arm.cue.status,'completed');
  assert.equal(cueStarts,run+1);assert.equal(mapReads,run+1);
 }
 ctx.autoPpxRunning=ctx.autoPpxCueRunning=ctx.autoPpxPaused=true;
 reply=await command({action:'cue_play',rows:[{piece:101,destination:42}]});
 assert(reply.ok);assert(!ctx.autoPpxPaused,'Resume continues the existing run');
 assert.equal(cueStarts,3);assert.equal(mapReads,3,'Resume must not rebuild or reacquire the queue');
 ctx.autoPpxCueRunning=false;ctx.autoPpxAbort=true;
 reply=await command({action:'cue_play',rows:[{piece:101,destination:42}]});
 assert(!reply.ok);assert.match(reply.error,/still stopping/);
 assert.equal(ctx.autoPpxAbort,true,'A rejected restart must preserve the old runner abort');
 assert.equal(cueStarts,3);assert.equal(mapReads,3);
 ctx.autoPpxRunning=false;
 // A global Stop arriving during fresh-start validation invalidates that
 // pending start. A late camera result cannot restart the arm.
 let finishReplayMap;
 ctx.refreshAutoPpxTags=async()=>new Promise(resolve=>finishReplayMap=resolve);
 const pendingReplayId=String(id+1);await command({action:'cue_play',rows:[{piece:101,destination:42}]});
 assert.equal(posted.find(p=>p.id===pendingReplayId),undefined);
 await command({action:'stop'});finishReplayMap();await flush();
 assert(!posted.find(p=>p.id===pendingReplayId).ok);assert.equal(cueStarts,3);
 ctx.refreshAutoPpxTags=async()=>[];
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 cueRevision=reply.arm.control_revision;
 // The controller's retained failure crosses the bridge even after its status
 // element or active operation changes. Play remains asynchronous for Stop.
 let receivedProgram,receivedOptions;
 ctx.runAutoPpx=async(program,options)=>{receivedProgram=program;receivedOptions=options;ctx.autoPpxCueOutcome='completed';};
 const clearRows=[{piece:101,destination:42},{action:'clear_view'}];
 reply=await command({action:'cue_set',rows:clearRows});assert(reply.ok);assert.equal(reply.arm.cue.rows[1].action,'clear_view');
 reply=await command({action:'cue_play',rows:clearRows,view_rotation:180});assert(reply.ok);
 assert.equal(receivedProgram[1].action,'clear_view');assert.equal(receivedOptions.viewRotation,180);
 assert.equal(receivedProgram[1].direction,'left');assert.equal(receivedProgram[1].distance_cm,5,'Legacy rows preserve the default move');
 reply=await command({action:'cue_play',rows:clearRows});assert(reply.ok);
 assert.equal(receivedOptions.viewRotation,TEAM==='purple'?180:0,'A legacy Play must retain the player side, not assume Green camera orientation');
 reply=await command({action:'cue_play',rows:clearRows,view_rotation:0});assert(reply.ok);
 assert.equal(receivedOptions.viewRotation,0,'An explicit unrotated view still overrides the player default');
 const customRows=[clearRows[0],{action:'clear_view',direction:'right',distance_cm:7.5}];
 reply=await command({action:'cue_set',rows:customRows});assert(reply.ok);
 reply=await command({action:'cue_play',rows:clearRows});assert(!reply.ok,'An old distance/direction receipt cannot execute changed rows');
 reply=await command({action:'cue_play',rows:customRows,view_rotation:180});assert(reply.ok);
 assert.equal(receivedProgram[1].direction,'right');assert.equal(receivedProgram[1].distance_cm,7.5);
 ctx.activeOperation={queue_index:1,physical_tag:101,pickupComplete:false};reply=await command({action:'heartbeat'});assert.equal(reply.arm.cue.picked_up,false);
 ctx.activeOperation.pickupComplete=true;reply=await command({action:'heartbeat'});assert.equal(reply.arm.cue.picked_up,true);ctx.activeOperation=null;
 reply=await command({action:'cue_set',rows:clearRows});assert(reply.ok);
 assert.equal(cueSource.value,'101');assert.equal(cueTarget.value,'42','Clear view is not treated as a tag selector');
 for(const rows of [[{action:'clear_view'}],[...clearRows,{action:'clear_view'}],[{piece:101,destination:42},{action:'clear_view',distance:999}]]){
  reply=await command({action:'cue_set',rows});assert(!reply.ok);assert.match(reply.error,/Clear view/);
 }
 reply=await command({action:'cue_play',rows:clearRows,view_rotation:90});assert(!reply.ok);assert.match(reply.error,/camera view/);
 reply=await command({action:'cue_set',rows:[{piece:101,destination:42}]});assert(reply.ok);
 ctx.runAutoPpx=async()=>{
  ctx.autoPpxCueOutcome='error';ctx.autoPpxCueError={message:'pump receipt rejected',stage:'Checking pump',index:1};
  gid('autoPpxStatus').textContent='16 tags ready';
 };
 reply=await command({action:'cue_play'});assert(reply.ok);
 assert.equal(reply.arm.cue.status,'error');assert.equal(reply.arm.cue.error,'pump receipt rejected');
 assert.equal(reply.arm.cue.failed_stage,'Checking pump');assert.equal(reply.arm.cue.index,1);
 assert(posted.some(p=>p.type==='diagnostic'&&p.event==='cue_start_requested'));
 ctx.runAutoPpx=async()=>{throw Error('Unexpected cue startup failure');};
 await command({action:'cue_play'});
 assert.equal(posted.at(-1).arm.cue.error,'Unexpected cue startup failure');
 assert(posted.some(p=>p.type==='diagnostic'&&p.event==='cue_failed'&&p.reason==='Unexpected cue startup failure'));
 let finishCue;
 ctx.runAutoPpx=async()=>{
  assert.equal(ctx.autoPpxCueError,null,'Retry clears the previous failure');
  ctx.autoPpxRunning=ctx.autoPpxCueRunning=true;
  await new Promise(resolve=>finishCue=resolve);
  ctx.autoPpxRunning=ctx.autoPpxCueRunning=false;ctx.autoPpxCueOutcome='completed';
 };
 reply=await command({action:'cue_play'});assert(reply.ok);assert.equal(reply.arm.cue.status,'running');
 await command({action:'stop'});finishCue();await flush();
 assert.equal(posted.at(-1).arm.cue.status,'stopped','Late completion cannot replace Stop');
 assert.equal(posted.at(-1).arm.session,null);
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
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
 ctx.mobileGame={journey:{phase:'calibration',calibration_side:TEAM},mobile_calibration_connect:true,mobile_calibration:{stage:'points'}};
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
 // Disconnecting, unlocking and losing the page during calibration must
 // release motion control without dropping an attached Atom.
 ctx.mobileGame.mobile_safety={status:'ready'};
 for(const stage of ['points','perspective','tutorial'])for(const action of ['stop','disconnect','suspend','unlock','watchdog']){
  ctx.mobileGame.mobile_calibration.stage=stage;
  robot={...robot,enabled:true,motion_ready:true,pump_mode:'suck',last_feedback:Date.now()/1000};
  ctx.applyStatus(robot);reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
  const before=calls.length;
  if(action==='unlock'){
   robot={...robot,enabled:false,motion_ready:false,motion_epoch:robot.motion_epoch+1};ctx.applyStatus(robot);await flush();
  }else if(action==='watchdog'){
   now+=1600;intervals.forEach(fn=>fn());await flush();
  }else await command({action});
  const cleanup=calls.slice(before);
  assert(cleanup.some(c=>c.path==='/api/stop'),stage+' '+action+' still stops motion');
  assert(cleanup.some(c=>c.path==='/api/disconnect'),stage+' '+action+' still releases control');
  assert(!cleanup.some(c=>c.path==='/api/pump'),stage+' '+action+' leaves suction unchanged');
  assert.equal(posted.at(-1).arm.session,null);
  assert.match(posted.at(-1).arm.message,/Suction kept on/);
 }
 for(const pump of ['off','blow']){
  robot={...robot,enabled:true,motion_ready:true,pump_mode:pump,last_feedback:Date.now()/1000};ctx.applyStatus(robot);
  reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
  const before=calls.length;await command({action:'disconnect'});
  assert(calls.slice(before).some(c=>c.path==='/api/pump'&&c.data.mode==='off'),'Only suction is retained during calibration');
 }
 robot={...robot,pump_mode:'suck',last_feedback:Date.now()/1000};ctx.applyStatus(robot);
 reply=await command({action:'connect'});assert(reply.ok);session=reply.arm.session;
 const explicitOff=calls.length;await command({action:'pump',mode:'off'});
 assert(calls.slice(explicitOff).some(c=>c.path==='/api/pump'&&c.data.mode==='off'),'Explicit pump-off is never suppressed');
 const gameplayStop=calls.length;ctx.mobileGame.journey.phase='playing';await command({action:'stop'});
 assert(calls.slice(gameplayStop).some(c=>c.path==='/api/pump'&&c.data.mode==='off'),'Gameplay disconnect still turns suction off');
 // Parent projection, same-origin checks, normalized commands, stale-state gating.
 let receive,output=[],shade={},line={},hidden;
 const frame={contentWindow:{postMessage:d=>output.push(d)},getAttribute:()=>'/bridge'};
 const overlay={toggleAttribute:(k,v)=>hidden=v,setAttribute(){},querySelector:q=>({setAttribute:(k,v)=>(q.includes('shade')?shade:line)[k]=v})};
 let timerId=0;const timers=new Map(),advance=ms=>{now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}};
 const pc={window:{addEventListener:(k,f)=>receive=f},location:{origin:'http://test',pathname:'/s/'+TEAM+'/'},performance:{now:()=>now},Date,document:{hidden:false},setTimeout:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id)};vm.createContext(pc);vm.runInContext(fs.readFileSync('shared/mobile_ltz/physical-arm.js','utf8')+'\nthis.Adapter=MobilePhysicalArm;',pc);
 const adapterLogs=[];
 const adapter=new pc.Adapter({frame,overlay,viewport:{w:1000,h:500,rotation:TEAM==='purple'?180:0},team:TEAM,diagnostic:(...args)=>{adapterLogs.push(args);throw Error('test unavailable logger');}});adapter.active=true;
 const snapshot=posted.find(p=>p.status==='ready'&&p.arm?.session&&p.arm.motion_ready);receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,contract:(TEAM==='green'?'purple':'green')+'.mobile-arm'}});assert.equal(adapter.arm(),null,'Opposite-team feedback is ignored');
 receive({source:frame.contentWindow,origin:'http://evil',data:snapshot});assert.equal(adapter.arm(),null);
 receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,type:'state'}});assert(Math.abs(adapter.arm().tip.x-300)<1e-9);assert(Math.abs(adapter.arm().tip.y-50)<1e-9);assert.equal(hidden,false);assert.match(shade.d,/M0.00,0.00/);assert.match(line.d,/100.00,50.00/);
 for(const rotation of [0,180]){
  adapter.viewport.rotation=rotation;
  for(const stale of [undefined,180-rotation]){
   const play=adapter.command({action:'cue_play',view_rotation:stale}),id=output.at(-1).id;
   assert.equal(output.at(-1).data.view_rotation,rotation,'Clear view always uses the current player viewport at dispatch');
   receive({source:frame.contentWindow,origin:'http://test',data:{...snapshot,type:'reply',id,ok:true}});await play;
  }
 }
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
 publish();long=adapter.command({action:'cue_waypoint',session:snapshot.arm.session,point:{x:250,y:375}});longId=output.at(-1).id;
 for(let i=0;i<4;i++){advance(10000);publish({active_command:{id:longId,action:'cue_waypoint',session:snapshot.arm.session}});}
 assert(adapter.pending.has(longId),'Idle click detours use the same bounded fresh-progress timeout as XYZ');
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
 assert(adapterLogs.some(([source,event])=>source==='controller'&&event==='command_timeout'));
 assert.equal(output.at(-1).data.reason,'Physical controller command timed out.','Diagnostic failure cannot prevent Stop or lose its reason');
 console.log('PASS: reconnect/manual relocation, brief unlock, delayed move/status, session/revision checks, joint guard, calibrated XY/Z, pump-off, stop, projection and expiry');
})().catch(e=>{console.error(e);process.exitCode=1;});
