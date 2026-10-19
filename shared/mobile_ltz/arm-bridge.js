/* Team mobile-arm v1: mobile presentation over the existing calibrated LTX controller. */
(()=>{
'use strict';
if(!MOBILE_LTZ||!new URLSearchParams(location.search).has('bridge')||parent===window)return;
const bridgeContract=TEAM+'.mobile-arm';
let token=null,mode='joint',revision=0,parentAt=performance.now(),queue=Promise.resolve(),robot=null,robotAt=0;
let target=null,jointTarget=null,message='Connect '+TEAM+' to use the physical arm.',cueRows=[],cueStatus='idle',waypoint=null;
let geometry=null,geometryKey='',geometryError='',sequence=-1,epoch=0,sampling=null,modeChange=null;
let cuePoseAt=null;
let connectionSession=null,synchronizing=false,stopPending=Promise.resolve();
let activeCommand=null;
let motionPath=null,motionPathId=0;
const limitError=message=>Object.assign(Error(message),{code:'motion_limit'});
const targetError=message=>Object.assign(Error(message),{code:'target_unavailable'});
const finite=p=>p&&['x','y','z'].every(k=>Number.isFinite(p[k]));
function imagePointReady(){
 const camera=mobileGame?.mobile_camera,serverTime=mobileGame?.server_time;
 const receiptAge=performance.now()-mobileGameAt;
 if(camera?.status!=='ready'||!Number.isFinite(serverTime)||!Number.isFinite(camera.frame_at)
   ||!Number.isFinite(receiptAge)||receiptAge<0||!Number.isFinite(camera.width)||camera.width<=0
   ||!Number.isFinite(camera.height)||camera.height<=0||!Array.isArray(camera.matrix)
   ||camera.matrix.length!==8||!camera.matrix.every(Number.isFinite))return false;
 const frameAge=(serverTime-camera.frame_at)*1000;
 return frameAge>=-250&&Math.max(0,frameAge)+receiptAge<=1500;
}
const rawCalibration=()=>mobileGame?.journey?.phase==='calibration'&&mobileGame.mobile_calibration_connect===true&&!['tutorial','complete'].includes(mobileGame.mobile_calibration?.stage);
const connectionReady=()=>typeof mobileConnectionReady==='function'?mobileConnectionReady():mobileRobotReady();
const send=value=>parent.postMessage({contract:bridgeContract,version:1,...value,delay_sent_at:parent.mobileDelay?.active?parent.performance.now():undefined},location.origin);
const assertOK=value=>{if(!value?.ok)throw Object.assign(Error(value?.error||'Robot command failed'),{code:value?.code});return value;};
const feedbackFresh=value=>value?.feedback_ok===true&&Number.isFinite(value.last_feedback)&&Date.now()/1000-value.last_feedback>=0&&Date.now()/1000-value.last_feedback<1.5;
function diagnostics(){return {
 run_id:mobileGame?.run_id,phase:mobileGame?.phase,journey_phase:mobileGame?.journey?.phase,
 controller_game_age_ms:typeof mobileGameAt==='number'?performance.now()-mobileGameAt:null,
 parent_age_ms:performance.now()-parentAt,robot_age_ms:robotAt?performance.now()-robotAt:null,
 feedback_age_ms:Number.isFinite(robot?.last_feedback)?Date.now()-robot.last_feedback*1000:null,
 connected:!!robot?.connected,enabled:!!robot?.enabled,feedback_ok:!!robot?.feedback_ok,motion_ready:!!robot?.motion_ready,
 motion_epoch:robot?.motion_epoch,motion_invalidation:robot?.motion_invalidation,robot_mode:robot?.robot_mode,had_session:!!token,control_mode:mode,
 connection_ready:connectionReady(),paused:mobileGame?.paused,safety_status:mobileGame?.mobile_safety?.status,
 calibration_loading:typeof mobileCalibrationLoading!=='undefined'&&!!mobileCalibrationLoading,
 view_active:typeof mobileViewActive==='undefined'||mobileViewActive,
 game_error:typeof mobileGameError==='string'?mobileGameError:''};}
function diagnostic(event,reason,extra={}){try{
 const evidence={};
 if(parent.mobileDelay?.active){
  evidence.servo_error=robot?.servo_error;
  try{
   const board=autoPpxCueEvidence().data;
   if(board)evidence.board={status:board.status,error:board.error,epoch:board.epoch,frame_at:board.frame_at,
    pending_fixed_ids:board.pending_fixed_ids,blocked_fixed_ids:board.blocked_fixed_ids,board_motion_ids:board.board_motion_ids,
    quarantined_tags:board.quarantined_tags,verification:board.verification,...(typeof autoPpxCueGateDetails==='function'?autoPpxCueGateDetails():{})};
  }catch{} // Missing extra evidence must not suppress the original diagnostic.
 }
 send({type:'diagnostic',event,reason,context:{...diagnostics(),...evidence,...extra}});
}catch{}}
window.mobileArmDiagnostic=diagnostic;
function discardTargets(){revision++;target=null;jointTarget=null;motionPath=null;pauseUserMoves();autoPpxAbort=true;cancelAutoPpxClickOverride();waypoint=null;}
let positionSettled=false;
function acceptStatus(value){
 if(connectionSession&&value?.control_session!==connectionSession)return false;
 if(robot?.control_session===value?.control_session&&Number(value?.last_feedback)<Number(robot?.last_feedback)&&value?.feedback_ok)return false;
 const previousEpoch=robot?.motion_epoch,changed=robot&&robot.motion_epoch!==value?.motion_epoch;
 if(value?.last_feedback!==robot?.last_feedback||changed||value?.control_session!==robot?.control_session||value?.robot_mode!==robot?.robot_mode){
  const elapsed=value?.last_feedback-robot?.last_feedback;
  positionSettled=!!(feedbackFresh(value)&&feedbackFresh(robot)&&value.control_session===robot.control_session&&!changed
   &&value.robot_mode===5&&robot.robot_mode===5&&elapsed>=.06&&elapsed<=.35
   &&Array.isArray(value.pose)&&Array.isArray(robot.pose)&&value.pose.length>=3&&robot.pose.length>=3
   &&value.pose.slice(0,3).every((v,i)=>Number.isFinite(v)&&Number.isFinite(robot.pose[i])&&Math.abs(v-robot.pose[i])<=.05));
 }
 robot=value;robotAt=performance.now();
 if(token&&!synchronizing&&(changed||!value?.connected||!value?.enabled||!feedbackFresh(value)||value?.motion_ready!==true))
  halt('Arm position or feedback changed. Relock the arm and press Connect to synchronize.',changed?'motion_epoch_changed':!value?.connected?'robot_disconnected':!value?.enabled?'robot_disabled':!feedbackFresh(value)?'feedback_stale':'motion_not_ready',{previous_motion_epoch:previousEpoch});
 return true;
}
const rawPoint=p=>gid('flipToggle').checked?{u:1-p.u,v:1-p.v}:p;
function point(p){const n=rawPoint(cal2CameraForRobotPose(cal2CalibrationSamples(),p));return {x:n.u,y:n.v,z:p.z};}
// Read-only presentation of the route already checked by the existing planner.
// Sample in robot space before camera projection so warped paths stay curved.
window.mobileArmPath=plan=>{
 motionPath=null;
 try{
  if(!plan||!token||rawCalibration()||!geometry||!feedbackFresh(robot)||!Array.isArray(robot?.pose)
    ||!Array.isArray(plan)||!plan.length||plan.length>512||!plan.every(finite))return;
  let previous={x:robot.pose[0],y:robot.pose[1],z:robot.pose[2]};
  if(!finite(previous))return;
  const points=[point(previous)];
  for(const next of plan){
   const steps=Math.max(1,Math.ceil(Math.hypot(next.x-previous.x,next.y-previous.y,next.z-previous.z)/10));
   if(points.length+steps>2048)return;
   for(let i=1;i<=steps;i++)points.push(point(Object.fromEntries(['x','y','z'].map(k=>[k,previous[k]+(next[k]-previous[k])*i/steps]))));
   previous=next;
  }
  if(points.every(finite))motionPath={id:String(++motionPathId),points,scope:geometryKey};
 }catch{} // A drawing failure must never affect motion execution.
};
async function pose(p){
 if(!finite(p))throw Error('Invalid calibrated target.');
 if(p.x<0||p.x>1||p.y<0||p.y>1||p.z<ws.z[0]||p.z>ws.z[1])throw limitError('Target is outside the calibrated camera or height range.');
 let n=gameDisplayPoint(p.x,p.y),tagId=null;
 if(p.tag_id!=null){
  // Preview labels follow SSE, while the background acquisition poll runs
  // every 750 ms. Re-read the owner on Go instead of testing that older list
  // against the 500 ms sighting limit. Never fall back to an untagged point.
  const tags=await readAutoPpxCueTargets(true);
  if(!autoPpxCueMapReady())throw Error('Wait for fresh verified camera mapping before moving to an Atom.');
  const ids=mobileGame?.movable_piece_codes?.[TEAM]||mobileGame?.mobile_arm?.tags?.map(t=>t.id)||[];
  const tag=tags.find(t=>Number(t.id)===p.tag_id&&ids.includes(p.tag_id)&&!t.obscured
   &&Number.isFinite(t.lastSeenAt)&&Date.now()-t.lastSeenAt>=0&&Date.now()-t.lastSeenAt<=500
   &&Number(t.missing||0)<=.35&&Number.isFinite(t.nx)&&Number.isFinite(t.ny));
  if(!tag)throw targetError('Selected Atom is not currently visible or available to your team. Reveal it and select it again.');
  const issue=autoPpxCueEndpointIssue(tag,true);
  if(issue==='camera')throw Error('Wait for fresh verified camera mapping before moving to an Atom.');
  if(issue)throw targetError('Selected Atom has no verified camera position. Reveal it and select it again.');
  const raw=rawPoint({u:tag.nx,v:tag.ny});
  if(Math.hypot(raw.u-p.x,raw.v-p.y)>.025)throw targetError('Selected Atom moved. Select its current position and press Go again.');
  n={u:tag.nx,v:tag.ny};tagId=p.tag_id;
 }
 const result=clickToPose(n.u,n.v,tagId);result.z=p.z;
 try{assertAutoPpxPoseSafe(result,'mobile target');}catch(error){if(/^mobile target is (?:outside the (?:X workspace|Y workspace|safe reach)|too close to the robot base|inside the red Cal 2 exclusion area)/.test(error.message))throw limitError(error.message);throw error;}return result;
}
function reach(){
 if(rawCalibration()){geometry=null;cuePoseAt=null;geometryKey='';geometryError='';return;}
 if(mobileGame?.mobile_safety?.status!=='ready'){geometry=null;cuePoseAt=null;geometryKey='';geometryError=mobileGame?.mobile_safety?.error||'Validated Cal 2 safety limits unavailable.';return;}
 const key=JSON.stringify([gameArmCal2(),gameCalibration2?.motion_envelope,gameRadiusMin,gameRadiusMax,ws,gid('flipToggle').checked]);
 if(key===geometryKey)return;
 geometryKey=key;geometry=null;cuePoseAt=null;geometryError='';
 try{
  const samples=cal2CalibrationSamples(),guard=cal2JointSafetyGuard();if(samples.length<6)throw Error('Six-point arm calibration is required.');
  const boundary=cal2ReachBoundary(samples),at=cal2PoseEvaluator(samples),excluded=[];
  for(let y=0;y<32;y++)for(let x=0;x<44;x++){
   const u=(x+.5)/44,v=(y+.5)/32,p=cal2CameraTargetPose(at(u,v),null,guard);
   if(pointInsideConvexCalibration(boundary,u,v,.001)&&(!pointInsideRobotPolygon(p.x,p.y,guard.polygon,0)||Math.hypot(p.x,p.y)<guard.radius_min))
    excluded.push([[x/44,y/32],[(x+1)/44,y/32],[(x+1)/44,(y+1)/32],[x/44,(y+1)/32]].map(([u,v])=>{const p=rawPoint({u,v});return [p.u,p.v];}));
  }
  geometry={boundary:boundary.map(p=>{const n=rawPoint(p);return [n.u,n.v];}),excluded};
  cuePoseAt=at;
 }catch(error){geometryError=TEAM[0].toUpperCase()+TEAM.slice(1)+' · '+error.message;}
}
function cueTargetAvailability(tag,id=tag?.id){
 const issue=autoPpxCueEndpointIssue(tag||{id},true);
 if(issue==='camera'||issue==='quarantined'||tag&&issue==='region')return {mapping_ready:false,mapping_error:issue==='quarantined'?`Marker #${id} is disputed. Reveal it before a new approach.`:issue==='region'?`Endpoint #${id} is outside the verified board region.`:'Waiting for fresh camera mapping.'};
 if(!cuePoseAt||!tag||!tag.fixed&&Date.now()-tag.lastSeenAt>750)return {};
 try{
  const corrected=compensateCal2Parallax(tag.nx,tag.ny,tag.id);
  const target=cal2CameraTargetPose({...cuePoseAt(corrected.u,corrected.v),z:ws.z[1]},tag.id);
  assertAutoPpxPoseSafe(target,'Target');
  return {reachable:true,placement_offset_mm:target.placement_offset_mm||0};
 }catch(error){return {reachable:false,reason:error.message};}
}
function syncControlMode(){
 // Normal LTX telemetry can keep robotAt fresh forever. Apply Game's mode on
 // every published state, independently of whether sample() needs a new read.
 if(typeof mobileControlChoice!=='number')return;
 const desired=['joint','xyz','targeting','cue'][mobileControlChoice-1];
 if(desired&&desired!==mode)changeControlMode(desired);
}
function changeControlMode(desired){
 // Invalidate old gestures immediately, but retain the connection. Commands
 // stay locked until the existing relay confirms that its follower has stopped.
 const mine=++epoch,previous=modeChange;
 activeCommand=null;motionPath=null;
 pauseUserMoves();autoPpxAbort=true;cancelAutoPpxClickOverride();waypoint=null;
 mode=desired;revision++;target=null;jointTarget=null;cueStatus='stopped';
 message='Switching physical controls…';
 const change=(async()=>{
  if(previous)await previous;
  if(mine!==epoch)return;
  if(autoPpxCueRunning)await stopAutoPpx();
  if(token)assertOK(await api('/api/stop',{}));
  if(mine===epoch)message='Physical '+mode+' controls ready.';
 })().catch(error=>{if(mine===epoch)halt('Could not switch controls safely: '+error.message);})
 .finally(()=>{if(modeChange===change)modeChange=null;});
 modeChange=change;
 return change;
}
function snapshot(){
 const timing=parent.mobileDelay?.begin();try{return snapshotValue();}finally{parent.mobileDelay?.end('browser.iframe_snapshot',timing);}
}
function snapshotValue(){
 syncControlMode();
 if(cal2BoundaryStop&&token){
  if(cal2BoundaryStop.code!=='motion_limit')halt(cal2BoundaryStop.message);
  else{message=cal2BoundaryStop.message;target=null;jointTarget=null;}
 }
 reach();
 const fresh=robot&&performance.now()-robotAt<1500&&feedbackFresh(robot);
 const motionError=rawCalibration()||mobileGame?.mobile_safety?.status==='ready'?null:mobileGame?.mobile_safety?.error||'Validated Cal 2 safety limits unavailable.';
 // Keep measured joint/mm feedback available for connection recovery; never
 // project a position through an outdated camera fit or grant movement from it.
 const raw=rawCalibration()||!!motionError;
 let tip=null;try{if(fresh&&Array.isArray(robot.pose)){const pose={x:robot.pose[0],y:robot.pose[1],z:robot.pose[2]};tip=raw?pose:point(pose);}}catch{}
 const actual=Array.isArray(robot?.joints)?robot.joints.slice(0,3):null;
 const ready=!!(fresh&&(raw||geometry)&&tip&&finite(tip)&&actual?.length===3&&actual.every(Number.isFinite));
 const ids=new Set(mobileGame?.movable_piece_codes?.[TEAM]||mobileGame?.mobile_arm?.tags?.map(t=>t.id)||[]);
 const displayTags=autoPpxCueDisplayTags();
 const tags=displayTags.filter(t=>(t.fixed||!t.obscured&&Date.now()-Number(t.lastSeenAt||0)<=500&&Number(t.missing||0)<=.35)&&Number.isFinite(t.nx)&&Number.isFinite(t.ny)).map(t=>{const p=rawPoint({u:t.nx,v:t.ny});return {id:Number(t.id),x:p.u,y:p.v,cached:!!t.fixed&&!t.visible};});
 const choices=autoPpxCueCandidates(displayTags);
 for(const choice of [...choices.sources,...choices.destinations])Object.assign(choice,cueTargetAvailability(displayTags.find(t=>t.id===choice.id),choice.id));
 return {status:ready?'ready':'unavailable',diagnostics:diagnostics(),error:geometryError||(!fresh?'Robot feedback unavailable.':!ready?'Calibrated arm position unavailable.':null),geometry,active_command:activeCommand,
  arm:{side:TEAM,physical:true,session:token,controller_id:token,connected:!!token&&!!robot?.connected,enabled:!!robot?.enabled,
   joints:actual,targets:jointTarget||actual,limits:['j1','j2','j3'].map(k=>jointLimits[k]),tip,position_at:fresh?robot.last_feedback:null,position_settled:ready&&positionSettled,xyz_target:target||tip,
   coordinate_space:raw?'robot-mm':'camera-normalized',xyz_limits:raw?ws:{x:[0,1],y:[0,1],z:ws.z},control_mode:mode,control_revision:revision,control_pending:!!modeChange||synchronizing,
   pump:robot?.pump_mode==='suck'?'suction':robot?.pump_mode==='blow'?'blow':'off',message:motionError||[message,mobileGame?.mobile_safety?.camera_compatibility?.warning].filter(Boolean).join(' '),
   motion_ready:!motionError&&fresh&&robot?.motion_ready===true&&!synchronizing,motion_error:motionError,
   motion_path:ready&&!raw&&token&&robot?.enabled&&motionPath?.scope===geometryKey?{id:motionPath.id,points:motionPath.points}:null,
   tags:tags.filter(t=>ids.has(t.id)),markers:tags.filter(t=>!ids.has(t.id)),
   cue:{rows:cueRows,status:autoPpxCueRunning?(autoPpxPaused?'paused':autoPpxVisionWait?'waiting':'running'):cueStatus,
    error:autoPpxCueError?.message||'',failed_stage:autoPpxCueError?.stage||'',
    sources:choices.sources,destinations:choices.destinations,waiting:autoPpxVisionWait,picked_up:activeOperation?.pickupComplete===true,
    index:autoPpxCueError?.index??autoPpxVisionWait?.index??Math.max(0,Number(activeOperation?.queue_index||1)-1),stage:gid('autoPpxStatus').textContent,waypoint}}};
}
async function sample(fresh=false){
 if(sampling){await sampling;if(!fresh)return;}
 const mine=epoch;
 const pending=(async()=>{try{
  syncControlMode();const value=await api('/api/status',null,'GET');
  if(mine===epoch)applyStatus(value);
 }catch(error){if(mine===epoch){diagnostic('status_read_failed',error.message);robot=null;}}
 send({type:'state',...snapshot()});})();
 sampling=pending;try{await pending;}finally{if(sampling===pending)sampling=null;}
}
function halt(reason,event='halt',extra={}){
 const keepSuction=mobileCalibrationKeepsSuction(robot?.pump_mode);
 if(token)diagnostic(event,reason,extra);
 epoch++;activeCommand=null;message=reason+(keepSuction?' Suction kept on for calibration.':'');discardTargets();
 if(token){token=null;stopPending=stopPending.catch(()=>{}).then(async()=>{
  // Release motion control without dropping the Atom used for calibration.
  // This never switches suction on; ordinary play and blow still shut off.
  try{await api('/api/stop',{});if(!keepSuction)await api('/api/pump',{mode:'off'});}
  finally{assertOK(await api('/api/disconnect',{}));}
 });stopPending.catch(error=>diagnostic('disconnect_failed',error.message));}cueStatus='stopped';
}
function beginCueIntervention(p,{heightOnly=false}={}){
 const shown=point(p),mine=epoch,override=beginAutoPpxClickOverride(++videoClickSeq,heightOnly?'height':'point');
 const current=()=>mine===epoch&&autoPpxClickOverride?.id===override.id;
 waypoint=shown;target=shown;message=heightOnly?'Changing height; cue temporarily overridden.':'Moving to the selected point; cue temporarily overridden.';
 performAutoPpxClickOverride(p,override,{heightOnly}).then(reached=>{
  if(!current())return;
  if(reached)target=point(reached);
  waypoint=null;finishAutoPpxClickOverride(override,true);
 }).catch(async error=>{
  if(!current())return;
  // A failed intervention cannot silently resume the automated motion.
  if(autoPpxCueRunning&&!autoPpxPaused)toggleAutoPpxPause();
  cancelAutoPpxClickOverride();waypoint=null;
  const cancelledClick=videoClickSeq;
  try{assertOK(await api('/api/stop',{}));await sample();}
  catch(holdError){if(mine===epoch)halt('Could not hold the arm safely. Connect to resume.');return;}
  if(mine!==epoch||videoClickSeq!==cancelledClick)return;
  target=null;message=`${heightOnly?'Height':'Point'} override failed: ${error.message}. Cue remains paused.`;
  diagnostic('cue_override_failed',message,{action:heightOnly?'xyz':'cue_waypoint'});
 });
}
async function prepareCueRows(selected,data,mine){
 if(mode!=='cue'||ltzTier<4||autoPpxRunning||!Array.isArray(selected)||!selected.length||selected.length>32)throw Error('Cue is locked or invalid.');
 await refreshAutoPpxTags({strict:true});
 if(mine!==epoch||!token||data.session!==token||!mobileRobotReady()||mode!=='cue'||autoPpxRunning||!feedbackFresh(robot)||!robot?.enabled||robot?.motion_ready!==true)throw Error('Cue validation cancelled.');
 const candidates=autoPpxCueCandidates(),owned=new Set(candidates.sources.map(t=>t.id));
 for(const [i,r] of selected.entries()){
  if(r?.action==='clear_view'){
   if(i===0||selected[i-1]?.action)throw Error(`Row ${i+1}: Clear view must follow a placement.`);
   autoPpxClearViewRow(r);
   continue;
  }
  if(r?.action!==undefined)throw Error(`Row ${i+1}: unknown cue action.`);
  if(!r||!Number.isInteger(r.piece)||!owned.has(r.piece))throw Error(`Row ${i+1}: choose a piece belonging to ${TEAM}.`);
  if(!Number.isInteger(r.destination)||owned.has(r.destination)||!(r.destination>=30&&r.destination<=59||r.destination>=100&&r.destination<=199))throw Error(`Row ${i+1}: choose a fixed marker or another player's Atom destination.`);
 }
 // Keep the controller's placement selects synchronized on every fresh start.
 // The runner receives the full typed program, including Clear view rows.
 const placements=selected.filter(r=>r.action!=='clear_view');
 let rows=[...gid('autoPpxQueue').querySelectorAll('.autoPpxQueueRow')];
 while(rows.length<placements.length){addAutoPpxQueueRow(rows.at(-1));rows=[...gid('autoPpxQueue').querySelectorAll('.autoPpxQueueRow')];}
 while(rows.length>placements.length)rows.pop().remove();
 for(const [i,r] of placements.entries()){setAutoPpxStoredSelectValue(rows[i].querySelector('.autoPpxSource'),String(r.piece));setAutoPpxStoredSelectValue(rows[i].querySelector('.autoPpxTarget'),String(r.destination));}
 gid('autoPpxLoop').checked=false;cueRows=selected.map(r=>r.action==='clear_view'?autoPpxClearViewRow(r):{piece:r.piece,destination:r.destination});cueStatus='idle';autoPpxCueError=null;
}
async function command(data){
 syncControlMode();
 const action=data.action;const commandEpoch=epoch;
 if(['stop','suspend','disconnect'].includes(action)){halt('Stopped. Connect to resume.','parent_stop',{robot_error:typeof data.reason==='string'?data.reason.slice(0,240):null});return;}
 if(action==='heartbeat')return;
 if(action==='pump'&&data.mode==='off'){assertOK(await api('/api/pump',{mode:'off'}));return;}
 if(modeChange)await modeChange;
 if(commandEpoch!==epoch)throw Error('Control method changed.');
 if(action==='connect'){
  if(!connectionReady())throw Error(mobileGame?.mobile_motion_policy?.error||mobileGame?.mobile_safety?.error||'Wait for your calibration turn or fresh physical game state.');
  discardTargets();synchronizing=true;
  try{
   await stopPending;
   if(commandEpoch!==epoch)throw Error('Connection cancelled.');
   const connected=assertOK(await api('/api/connect',{mode:'relay',host:gid('relayHost').value,side:TEAM}));
   if(commandEpoch!==epoch){await api('/api/disconnect',{});throw Error('Connection cancelled.');}
   connectionSession=connected.control_session;robot=null;robotAt=0;cal2BoundaryStop=null;
   if(typeof connectionSession!=='string')throw Error('Fresh arm connection required.');
   await sample(true);
   if(commandEpoch!==epoch||!feedbackFresh(robot)||robot?.motion_ready!==true||!robot?.enabled)throw Error('Fresh, settled arm feedback required. Relock the arm and reconnect.');
   token='physical:'+Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');sequence=-1;
   message='Connected at the measured position. Move a control to begin.';
   diagnostic('connected',message);
  }catch(error){diagnostic('connect_failed',error.message);await api('/api/disconnect',{});throw error;}
  finally{synchronizing=false;}
  return;
 }
 const holding=action==='cue_pause'||action==='cue_stop';
 if(!holding&&!mobileRobotReady())throw Error(mobileGame?.mobile_motion_policy?.error||mobileGame?.mobile_safety?.error||'Wait for fresh, unpaused physical play and calibration readiness.');
 if(!token||data.session!==token)throw Error('Connect this mobile controller first.');
 if(!Number.isSafeInteger(data.sequence)||data.sequence<=sequence)throw Error('Obsolete physical command.');sequence=data.sequence;
 // Holding a cue needs the current authenticated session, not new motion readiness.
 if(action==='cue_pause'){if(autoPpxCueRunning&&!autoPpxPaused)toggleAutoPpxPause();return;}
 if(action==='cue_stop'){await stopAutoPpx();cueStatus='stopped';return;}
 if(action==='enable'){
  discardTargets();synchronizing=true;
  try{assertOK(await api('/api/enable',{}));await sample(true);if(commandEpoch!==epoch||!feedbackFresh(robot)||!robot?.motion_ready)throw Error('Reconnect to synchronize the arm.');message='Arm synchronized. Move a control to begin.';}
  catch(error){halt(error.message);throw error;}finally{synchronizing=false;}return;
 }
 if(action==='control_mode'){
  const tier={joint:1,xyz:2,targeting:3,cue:4}[data.mode];
  if(!tier||tier>ltzTier||tier!==ltzTier)throw Error('This control method is locked.');
  mobileControlChoice=tier;await changeControlMode(data.mode);return;
 }
 if(data.control_revision!=null&&data.control_revision!==revision)throw Error('Obsolete control mode.');
 const s=snapshot();if(s.status!=='ready'||!robot?.enabled||!s.arm.motion_ready)throw Error(s.arm.motion_error||s.error||'Enable the arm before moving.');
 const mine=epoch;
 if(autoPpxCueRunning&&['joints','xyz','pump'].includes(action)
   && !(action==='xyz'&&mode==='cue'&&data.height_only===true))throw Error('Stop the cue before manual control.');
 // Only the runner may clear its own abort when a new cue actually starts.
 if(!['cue_set','cue_play'].includes(action))autoPpxAbort=false;
 if(['joints','xyz'].includes(action))cal2BoundaryStop=null;
 if(action==='joints'){
  if(mode!=='joint'||!Array.isArray(data.joints)||data.joints.length!==3||!data.joints.every(Number.isFinite))throw Error('Invalid joint target.');
  const result=await api('/api/joint-move',{j1:data.joints[0],j2:data.joints[1],j3:data.joints[2],j4:robot.joints[3],cal2_guard:cal2JointSafetyGuard()});
  if(mine!==epoch)throw Error('Movement cancelled.');
  // Only a verified geometric rejection is recoverable. Missing calibration,
  // FK failures, lost feedback and network errors retain the fail-closed path.
  if(!result?.ok&&/^Auto PP Cal 2 blocked joint path at [\d.]+%: (?:joint target TCP (?:radius |Z |is outside)|Z ceiling [\d.-]+ mm exceeded)/.test(result?.error||''))throw limitError(result.error);
  assertOK(result);
  jointTarget=[...data.joints];message='Physical joint target sent.';
 }else if(action==='xyz'){
  if(!['xyz','targeting','cue'].includes(mode)||mode==='cue'&&data.height_only!==true)throw Error('Cue allows manual height only. Select XYZ or Targeting for XY.');
  try{
   let p;
   if(rawCalibration()){
    if(mode!=='xyz'||!finite(data.xyz))throw Error('Use XYZ to capture the calibration points.');
    p={...data.xyz,r:robot.pose[3]};
    if(data.height_only===true){p.x=robot.pose[0];p.y=robot.pose[1];}
    for(const axis of ['x','y','z'])if(!Array.isArray(ws[axis])||p[axis]<ws[axis][0]||p[axis]>ws[axis][1])throw limitError('Calibration target is outside the robot workspace.');
    // The same Cartesian route and Relay follower enforce physical reach,
    // whole-path validation, Z floor and exclusive lesson ownership.
    const result=await api('/api/move',p);
    if(mine!==epoch)throw Error('Movement cancelled.');
    if(!result?.ok&&/^joint target TCP (?:radius |Z |is outside)/.test(result?.error||''))throw limitError(result.error);
    assertOK(result);target={x:p.x,y:p.y,z:p.z};message='Calibration XYZ target sent.';return;
   }
   if(data.height_only===true){
    const z=data.xyz?.z;
    if(!Number.isFinite(z))throw Error('Invalid height.');
    if(z<ws.z[0]||z>ws.z[1])throw limitError('Height is outside the calibrated range.');
    // Use measured robot XY directly: inverting the camera warp for a height
    // step can introduce lateral motion, especially near the outer points.
    p={x:robot.pose[0],y:robot.pose[1],z,r:robot.pose[3]};
    if(mode==='cue'&&autoPpxCueRunning){beginCueIntervention(p,{heightOnly:true});return;}
    assertAutoPpxPoseSafe(p,'mobile target');
   }else p=await pose(data.xyz);
   if(mine!==epoch)throw Error('Movement cancelled.');
   await moveToPose(p,mode==='targeting'&&!data.height_only?'video target':'mobile XYZ',false,{allowDetour:mode==='targeting'&&!data.height_only,interruptWhen:()=>mine!==epoch||!mobileRobotReady()});
   if(mine!==epoch)throw Error('Movement cancelled.');
   target=data.height_only?point(p):{...data.xyz};message='Calibrated physical target sent.';
  }catch(error){
   // These are verified geometry rejections, not broken connections. Keep
   // calibration, feedback, planning faults and unknown errors fail-closed.
   if(/^(?:Z ceiling [\d.-]+ mm exceeded|target is outside the Auto PP Cal 2 arm limit|(?:mobile target|Auto PP Cal 2 target) is (?:outside the (?:X workspace|Y workspace|safe reach)|too close to the robot base|inside the red Cal 2 exclusion area)|joint target TCP (?:radius |Z |is outside))/.test(error.message))throw limitError(error.message);
   throw error;
  }
 }else if(action==='pump'){
  if(!['suction','blow','off'].includes(data.mode))throw Error('Invalid pump mode.');
  assertOK(await api('/api/pump',{mode:data.mode==='suction'?'suck':data.mode}));
 }else if(action==='cue_set'){
  await prepareCueRows(data.rows,data,mine);
 }else if(action==='cue_play'){
  if(mode!=='cue'||ltzTier<4)throw Error('Cue is locked.');
  if(data.rows!==undefined&&(!Array.isArray(data.rows)||data.rows.length!==cueRows.length||!data.rows.every((r,i)=>r&&(r.action==='clear_view'?cueRows[i].action==='clear_view'&&autoPpxClearViewRow(r).direction===cueRows[i].direction&&autoPpxClearViewRow(r).distance_cm===cueRows[i].distance_cm:!r.action&&!cueRows[i].action&&Number.isInteger(r.piece)&&Number.isInteger(r.destination)&&r.piece===cueRows[i].piece&&r.destination===cueRows[i].destination))))throw Error('Cue selection changed. Review the selected rows and press Play again.');
  if(autoPpxRunning&&(!autoPpxCueRunning||autoPpxAbort))throw Error('Previous cue is still stopping. Wait for it to finish, then press Play again.');
  if(autoPpxPaused)toggleAutoPpxPause();else if(!autoPpxRunning){
   const viewRotation=data.view_rotation===undefined?(TEAM==='purple'?180:0):data.view_rotation;
   if(viewRotation!==0&&viewRotation!==180)throw Error('Invalid cue camera view.');
   await prepareCueRows(cueRows,data,mine);
   cueStatus='running';autoPpxCueError=null;
   diagnostic('cue_start_requested',`Starting cue · player view ${viewRotation}°: `+cueRows.map(r=>r.action==='clear_view'?`Clear view ${r.distance_cm} cm ${r.direction}`:`${r.piece} → ${r.destination}`).join(', '),{action:'cue_play'});
   // Keep the command queue free for Stop and player intervention while the
   // cue runs, but observe failures outside the runner's own catch as well.
   const runEpoch=epoch;
   const program=cueRows.map(r=>({...r}));
   Promise.resolve().then(()=>{if(runEpoch===epoch)return runAutoPpx(program,{viewRotation});}).then(()=>{
    if(runEpoch===epoch)cueStatus=autoPpxCueOutcome;
   }).catch(error=>{
    if(runEpoch!==epoch)return;
    cueStatus='error';
    autoPpxCueError??={message:error.message||String(error),stage:gid('autoPpxStatus').textContent,index:0};
    diagnostic('cue_failed',autoPpxCueError.message,{action:'cue_play',queue_index:autoPpxCueError.index});
   }).finally(()=>{send({type:'state',...snapshot()});});
  }
 }else if(action==='cue_cancel_waypoint'){cancelAutoPpxClickOverride();waypoint=null;
 }else if(action==='cue_waypoint'){
  if(mode!=='cue'||ltzTier<4)throw Error('Select unlocked Cue autonomy first.');
  // A point on the corrected image uses the saved camera-to-robot calibration,
  // not a detected tag's coordinates. Keep recovery taps available when a
  // disputed/occluded tag holds cue acquisition, without accepting stale video.
  if(!imagePointReady())throw Error('Wait for a fresh corrected camera image before moving to a selected point.'+(mobileGame?.mobile_camera?.error?' '+mobileGame.mobile_camera.error:''));
  const p=await pose({x:data.x,y:data.y,z:autoPpxTransportZ()});
  if(mine!==epoch)throw Error('Movement cancelled.');
  if(autoPpxCueRunning){
   beginCueIntervention(p);
  }else{
   // A player-selected point is an ordinary calibrated image move. It needs
   // no cue rows or visible source Atom and never starts/restarts the cue.
   cal2BoundaryStop=null;
   await moveToPose(p,'video target',false,{allowDetour:true,interruptWhen:()=>mine!==epoch||!mobileRobotReady()});
   if(mine!==epoch)throw Error('Movement cancelled.');
   target={x:data.x,y:data.y,z:p.z};message='Moving to the selected point. Cue unchanged.';
  }
 }else throw Error('Unsupported physical command.');
}
window.addEventListener('message',event=>{
 const d=event.data;if(event.source!==parent||event.origin!==location.origin||d?.contract!==bridgeContract||d.version!==1)return;
 parentAt=performance.now();
 if(d.type==='ping'){
  // Safari throttles offscreen frame timers. The visible parent's heartbeat
  // drives freshness as well, without a second relay connection.
  if(performance.now()-robotAt>500)sample();else send({type:'state',...snapshot()});return;
 }
 if(d.type!=='command'||typeof d.id!=='string'||d.id.length>80||!d.data)return;
 if(['stop','suspend','disconnect'].includes(d.data.action)){halt('Stopped. Connect to resume.','parent_stop',{robot_error:typeof d.data.reason==='string'?d.data.reason.slice(0,240):null});send({type:'reply',id:d.id,ok:true,...snapshot()});return;}
 syncControlMode();
 const receivedEpoch=epoch;
 queue=queue.catch(()=>{}).then(async()=>{try{if(receivedEpoch!==epoch)throw Error('Command cancelled.');activeCommand={id:d.id,action:d.data.action,session:d.data.session};send({type:'state',...snapshot()});await command(d.data);await sample();send({type:'reply',id:d.id,ok:true,...snapshot()});}catch(error){
  diagnostic('command_failed',error.message,{action:d.data.action,code:error.code});
  let code=error.code;
  if(code==='motion_resync_required')halt(error.message);
  if(token&&(receivedEpoch!==epoch||error.message==='Obsolete control mode.'))code='control_changed';
  if(['motion_limit','target_unavailable'].includes(code)&&receivedEpoch===epoch&&token){
   // Stop the previous follower goal too; keep the lease and pump unchanged.
   // A Stop pressed while this request is pending must never revive its token.
   try{assertOK(await api('/api/stop',{}));await sample();jointTarget=null;target=null;motionPath=null;}
   catch(stopError){code=null;error=stopError;halt('Could not hold the arm safely. Connect to resume.');}
  }
  message=code==='motion_limit'?(/Z ceiling/.test(error.message)?error.message:'Safety limit reached. Choose a target inside the red boundary.'):code==='control_changed'?'Control method changed. Previous movement cancelled.':error.message;
  send({type:'reply',id:d.id,ok:false,...snapshot(),error:message,detail:error.message,code});
 }finally{if(activeCommand?.id===d.id)activeCommand=null;}});
});
setInterval(()=>{if(token&&(performance.now()-parentAt>1500||!connectionReady()||!feedbackFresh(robot)))halt('Mobile control paused. Press Connect to synchronize the arm.',performance.now()-parentAt>1500?'parent_timeout':!connectionReady()?'game_not_ready':'feedback_stale');},200);
setInterval(()=>send({type:'state',...snapshot()}),200);
// LTX owns telemetry sampling; reuse each accepted status instead of opening a second relay link.
const previousStatus=applyStatus;applyStatus=function(value){const timing=parent.mobileDelay?.begin();try{if(acceptStatus(value)){previousStatus(value);send({type:'state',...snapshot()});}}finally{parent.mobileDelay?.end('browser.status_apply',timing);}};
gid('webcamFeed').onerror=null;gid('webcamFeed').removeAttribute('src');
send({type:'ready'});sample();
})();
