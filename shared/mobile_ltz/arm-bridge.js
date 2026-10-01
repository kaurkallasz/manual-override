/* Team mobile-arm v1: mobile presentation over the existing calibrated LTX controller. */
(()=>{
'use strict';
if(!MOBILE_LTZ||!new URLSearchParams(location.search).has('bridge')||parent===window)return;
const bridgeContract=TEAM+'.mobile-arm';
let token=null,mode='joint',revision=0,parentAt=performance.now(),queue=Promise.resolve(),robot=null,robotAt=0;
let target=null,jointTarget=null,message='Connect '+TEAM+' to use the physical arm.',cueRows=[],cueStatus='idle',waypoint=null;
let geometry=null,geometryKey='',geometryError='',sequence=-1,epoch=0,sampling=false,modeChange=null;
let activeCommand=null;
const limitError=message=>Object.assign(Error(message),{code:'motion_limit'});
const finite=p=>p&&['x','y','z'].every(k=>Number.isFinite(p[k]));
const rawCalibration=()=>mobileGame?.journey?.phase==='calibration'&&mobileGame.mobile_calibration_connect===true&&!['tutorial','complete'].includes(mobileGame.mobile_calibration?.stage);
const connectionReady=()=>typeof mobileConnectionReady==='function'?mobileConnectionReady():mobileRobotReady();
const send=value=>parent.postMessage({contract:bridgeContract,version:1,...value},location.origin);
const assertOK=value=>{if(!value?.ok)throw Error(value?.error||'Robot command failed');return value;};
const rawPoint=p=>gid('flipToggle').checked?{u:1-p.u,v:1-p.v}:p;
function point(p){const n=rawPoint(cal2CameraForRobotPose(cal2CalibrationSamples(),p));return {x:n.u,y:n.v,z:p.z};}
function pose(p){
 if(!finite(p))throw Error('Invalid calibrated target.');
 if(p.x<0||p.x>1||p.y<0||p.y>1||p.z<ws.z[0]||p.z>ws.z[1])throw limitError('Target is outside the calibrated camera or height range.');
 let n=gameDisplayPoint(p.x,p.y),tagId=null;
 if(p.tag_id!=null){
  const ids=mobileGame?.movable_piece_codes?.[TEAM]||mobileGame?.mobile_arm?.tags?.map(t=>t.id)||[];
  const tag=(latestVisibleArucoTags||[]).find(t=>Number(t.id)===p.tag_id&&ids.includes(p.tag_id)&&!t.obscured&&Date.now()-Number(t.lastSeenAt||0)<=500&&Number(t.missing||0)<=.35);
  if(!tag)throw Error('A fresh visible Atom belonging to this player is required.');
  const raw=rawPoint({u:tag.nx,v:tag.ny});
  if(Math.hypot(raw.u-p.x,raw.v-p.y)>.025)throw Error('Preview the current Atom position again.');
  n={u:tag.nx,v:tag.ny};tagId=p.tag_id;
 }
 const result=clickToPose(n.u,n.v,tagId);result.z=p.z;
 try{assertAutoPpxPoseSafe(result,'mobile target');}catch(error){if(/^mobile target is (?:outside the (?:X workspace|Y workspace|safe reach)|too close to the robot base|inside the red Cal 2 exclusion area)/.test(error.message))throw limitError(error.message);throw error;}return result;
}
function reach(){
 if(rawCalibration()){geometry=null;geometryKey='';geometryError='';return;}
 const key=JSON.stringify([gameArmCal2(),gameRadiusMin,gameRadiusMax,ws,gid('flipToggle').checked]);
 if(key===geometryKey)return;
 geometryKey=key;geometry=null;geometryError='';
 try{
  const samples=cal2CalibrationSamples();cal2JointSafetyGuard();if(samples.length<6)throw Error('Six-point arm calibration is required.');
  const boundary=cal2ReachBoundary(samples),at=cal2PoseEvaluator(samples),excluded=[];
  for(let y=0;y<32;y++)for(let x=0;x<44;x++){
   const u=(x+.5)/44,v=(y+.5)/32;
   if(pointInsideConvexCalibration(boundary,u,v,.001)&&Math.hypot(...Object.values(at(u,v)))<autoPpxPlanningRadiusMin())
    excluded.push([[x/44,y/32],[(x+1)/44,y/32],[(x+1)/44,(y+1)/32],[x/44,(y+1)/32]].map(([u,v])=>{const p=rawPoint({u,v});return [p.u,p.v];}));
  }
  geometry={boundary:boundary.map(p=>{const n=rawPoint(p);return [n.u,n.v];}),excluded};
 }catch(error){geometryError=TEAM[0].toUpperCase()+TEAM.slice(1)+' · '+error.message;}
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
 activeCommand=null;
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
 syncControlMode();
 if(cal2BoundaryStop&&token){
  if(cal2BoundaryStop.code!=='motion_limit')halt(cal2BoundaryStop.message);
  else{message=cal2BoundaryStop.message;target=null;jointTarget=null;}
 }
 reach();
 const fresh=robot&&performance.now()-robotAt<1500&&robot.feedback_ok!==false;
 const raw=rawCalibration();
 let tip=null;try{if(fresh&&Array.isArray(robot.pose)){const pose={x:robot.pose[0],y:robot.pose[1],z:robot.pose[2]};tip=raw?pose:point(pose);}}catch{}
 const actual=Array.isArray(robot?.joints)?robot.joints.slice(0,3):null;
 const ready=!!(fresh&&(raw||geometry)&&tip&&finite(tip)&&actual?.length===3&&actual.every(Number.isFinite));
 const ids=new Set(mobileGame?.movable_piece_codes?.[TEAM]||mobileGame?.mobile_arm?.tags?.map(t=>t.id)||[]);
 const tags=(latestVisibleArucoTags||[]).filter(t=>!t.obscured&&Date.now()-Number(t.lastSeenAt||0)<=500&&Number(t.missing||0)<=.35&&Number.isFinite(t.nx)&&Number.isFinite(t.ny)).map(t=>{const p=rawPoint({u:t.nx,v:t.ny});return {id:Number(t.id),x:p.u,y:p.v};});
 return {status:ready?'ready':'unavailable',error:geometryError||(!fresh?'Robot feedback unavailable.':!ready?'Calibrated arm position unavailable.':null),geometry,active_command:activeCommand,
  arm:{side:TEAM,physical:true,session:token,controller_id:token,connected:!!token&&!!robot?.connected,enabled:!!robot?.enabled,
   joints:actual,targets:jointTarget||actual,limits:['j1','j2','j3'].map(k=>jointLimits[k]),tip,xyz_target:target||tip,
   coordinate_space:raw?'robot-mm':'camera-normalized',xyz_limits:raw?ws:{x:[0,1],y:[0,1],z:ws.z},control_mode:mode,control_revision:revision,control_pending:!!modeChange,
   pump:robot?.pump_mode==='suck'?'suction':robot?.pump_mode==='blow'?'blow':'off',message,
   tags:tags.filter(t=>ids.has(t.id)),markers:tags.filter(t=>!ids.has(t.id)),
   cue:{rows:cueRows,status:autoPpxCueRunning?(autoPpxPaused?'paused':'running'):cueStatus,index:Math.max(0,Number(activeOperation?.queue_index||1)-1),stage:gid('autoPpxStatus').textContent,waypoint}}};
}
async function sample(){if(sampling)return;sampling=true;try{
 syncControlMode();
 robot=await api('/api/status',null,'GET');robotAt=performance.now();applyStatus(robot);}catch{robot=null;}finally{sampling=false;}send({type:'state',...snapshot()});}
function halt(reason){
 epoch++;activeCommand=null;message=reason;pauseUserMoves();autoPpxAbort=true;cancelAutoPpxClickOverride();waypoint=null;
 if(token){token=null;api('/api/stop',{}).catch(()=>{});api('/api/pump',{mode:'off'}).catch(()=>{});}cueStatus='stopped';
}
async function command(data){
 syncControlMode();
 const action=data.action;const commandEpoch=epoch;
 if(['stop','suspend','disconnect'].includes(action)){halt('Stopped. Connect to resume.');return;}
 if(action==='heartbeat')return;
 if(action==='pump'&&data.mode==='off'){assertOK(await api('/api/pump',{mode:'off'}));return;}
 if(modeChange)await modeChange;
 if(commandEpoch!==epoch)throw Error('Control method changed.');
 if(action==='connect'){
  if(!connectionReady())throw Error('Wait for your calibration turn or fresh physical game state.');
  assertOK(await api('/api/connect',{mode:'relay',host:gid('relayHost').value,side:TEAM}));
  cal2BoundaryStop=null;
  if(commandEpoch!==epoch){await api('/api/stop',{});throw Error('Connection cancelled.');}token='physical:'+Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');sequence=-1;await sample();message=robot?.enabled?'Connected. Physical controls ready.':'Connected. Enable the arm to move.';return;
 }
 if(!mobileRobotReady())throw Error('Wait for fresh, unpaused physical play and calibration readiness.');
 if(!token||data.session!==token)throw Error('Connect this mobile controller first.');
 if(!Number.isSafeInteger(data.sequence)||data.sequence<=sequence)throw Error('Obsolete physical command.');sequence=data.sequence;
 if(action==='enable'){assertOK(await api('/api/enable',{}));message='Physical arm enabled.';await sample();return;}
 if(action==='control_mode'){
  const tier={joint:1,xyz:2,targeting:3,cue:4}[data.mode];
  if(!tier||tier>ltzTier||(mobileGame?.virtual_test_control==null&&tier!==ltzTier))throw Error('This control method is locked.');
  mobileControlChoice=tier;await changeControlMode(data.mode);return;
 }
 if(data.control_revision!=null&&data.control_revision!==revision)throw Error('Obsolete control mode.');
 const s=snapshot();if(s.status!=='ready'||!robot?.enabled)throw Error(s.error||'Enable the arm before moving.');
 const mine=epoch;
 if(autoPpxCueRunning&&['joints','xyz','pump'].includes(action))throw Error('Stop the cue before manual control.');
 autoPpxAbort=false;
 if(['joints','xyz'].includes(action))cal2BoundaryStop=null;
 if(action==='joints'){
  if(mode!=='joint'||!Array.isArray(data.joints)||data.joints.length!==3||!data.joints.every(Number.isFinite))throw Error('Invalid joint target.');
  const result=await api('/api/joint-move',{j1:data.joints[0],j2:data.joints[1],j3:data.joints[2],j4:robot.joints[3],cal2_guard:cal2JointSafetyGuard()});
  // Only a verified geometric rejection is recoverable. Missing calibration,
  // FK failures, lost feedback and network errors retain the fail-closed path.
  if(!result?.ok&&/^Auto PP Cal 2 blocked joint path at [\d.]+%: joint target TCP (?:radius |Z |is outside)/.test(result?.error||''))throw limitError(result.error);
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
    assertAutoPpxPoseSafe(p,'mobile target');
   }else p=pose(data.xyz);
   await moveToPose(p,mode==='targeting'&&!data.height_only?'video target':'mobile XYZ',false,{allowDetour:mode==='targeting'&&!data.height_only,interruptWhen:()=>mine!==epoch||!mobileRobotReady()});
   target=data.height_only?point(p):{...data.xyz};message='Calibrated physical target sent.';
  }catch(error){
   // These are verified geometry rejections, not broken connections. Keep
   // calibration, feedback, planning faults and unknown errors fail-closed.
   if(/^(?:target is outside the Auto PP Cal 2 arm limit|(?:mobile target|Auto PP Cal 2 target) is (?:outside the (?:X workspace|Y workspace|safe reach)|too close to the robot base|inside the red Cal 2 exclusion area)|joint target TCP (?:radius |Z |is outside))/.test(error.message))throw limitError(error.message);
   throw error;
  }
 }else if(action==='pump'){
  if(!['suction','blow','off'].includes(data.mode))throw Error('Invalid pump mode.');
  assertOK(await api('/api/pump',{mode:data.mode==='suction'?'suck':data.mode}));
 }else if(action==='cue_set'){
  if(mode!=='cue'||ltzTier<4||autoPpxRunning||!Array.isArray(data.rows)||!data.rows.length||data.rows.length>32)throw Error('Cue is locked or invalid.');
  const candidates=s.arm;
  if(data.rows.some(r=>!candidates.tags.some(t=>t.id===r.piece)||!candidates.markers.some(t=>t.id===r.destination)))throw Error('Cue targets require current camera detections.');
  let rows=[...gid('autoPpxQueue').querySelectorAll('.autoPpxQueueRow')];
  while(rows.length<data.rows.length){addAutoPpxQueueRow(rows.at(-1));rows=[...gid('autoPpxQueue').querySelectorAll('.autoPpxQueueRow')];}
  while(rows.length>data.rows.length)rows.pop().remove();
  for(const [i,r] of data.rows.entries()){setAutoPpxStoredSelectValue(rows[i].querySelector('.autoPpxSource'),String(r.piece));setAutoPpxStoredSelectValue(rows[i].querySelector('.autoPpxTarget'),String(r.destination));}
  gid('autoPpxLoop').checked=false;cueRows=data.rows.map(r=>({...r}));cueStatus='idle';
 }else if(action==='cue_play'){
  if(mode!=='cue'||ltzTier<4)throw Error('Cue is locked.');
  if(autoPpxPaused)toggleAutoPpxPause();else if(!autoPpxRunning){cueStatus='running';runAutoPpx().finally(()=>{cueStatus=autoPpxAbort?'stopped':'completed';});}
 }else if(action==='cue_pause'){
  if(autoPpxCueRunning&&!autoPpxPaused)toggleAutoPpxPause();
 }else if(action==='cue_stop'){await stopAutoPpx();cueStatus='stopped';
 }else if(action==='cue_cancel_waypoint'){cancelAutoPpxClickOverride();waypoint=null;
 }else if(action==='cue_waypoint'){
  if(mode!=='cue'||!autoPpxCueRunning)throw Error('Start the cue before adding a waypoint.');
  const p=pose({x:data.x,y:data.y,z:autoPpxTransportZ()}),override=beginAutoPpxClickOverride(++videoClickSeq);
  waypoint={x:data.x,y:data.y,z:p.z};performAutoPpxClickOverride(p,override).then(()=>finishAutoPpxClickOverride(override,true)).catch(error=>{message=error.message;cancelAutoPpxClickOverride();}).finally(()=>{waypoint=null;});
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
 if(['stop','suspend','disconnect'].includes(d.data.action)){halt('Stopped. Connect to resume.');send({type:'reply',id:d.id,ok:true,...snapshot()});return;}
 syncControlMode();
 const receivedEpoch=epoch;
 queue=queue.catch(()=>{}).then(async()=>{try{if(receivedEpoch!==epoch)throw Error('Command cancelled.');activeCommand={id:d.id,action:d.data.action,session:d.data.session};send({type:'state',...snapshot()});await command(d.data);await sample();send({type:'reply',id:d.id,ok:true,...snapshot()});}catch(error){
  let code=error.code;
  if(token&&(receivedEpoch!==epoch||error.message==='Obsolete control mode.'))code='control_changed';
  if(code==='motion_limit'&&receivedEpoch===epoch&&token){
   // Stop the previous follower goal too; keep the lease and pump unchanged.
   // A Stop pressed while this request is pending must never revive its token.
   try{assertOK(await api('/api/stop',{}));await sample();jointTarget=null;target=null;}
   catch(stopError){code=null;error=stopError;halt('Could not hold the arm safely. Connect to resume.');}
  }
  message=code==='motion_limit'?'Safety limit reached. Choose a target inside the red boundary.':code==='control_changed'?'Control method changed. Previous movement cancelled.':error.message;
  send({type:'reply',id:d.id,ok:false,...snapshot(),error:message,detail:error.message,code});
 }finally{if(activeCommand?.id===d.id)activeCommand=null;}});
});
setInterval(()=>{if(token&&(performance.now()-parentAt>1500||!connectionReady()))halt('Mobile control paused: connection or game state unavailable.');},200);
setInterval(()=>send({type:'state',...snapshot()}),200);
// LTX owns telemetry sampling; reuse each accepted status instead of opening a second relay link.
const previousStatus=applyStatus;applyStatus=function(value){previousStatus(value);robot=value;robotAt=performance.now();};
gid('webcamFeed').onerror=null;gid('webcamFeed').removeAttribute('src');
send({type:'ready'});sample();
})();
