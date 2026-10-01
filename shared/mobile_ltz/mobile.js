'use strict';
const $=id=>document.getElementById(id), local=location.pathname.startsWith('/s/'), base='/s/gamemaster/p/mobile-ltz-api/api/';
const team=document.documentElement.dataset.mobileTeam==='purple'?'purple':'green',teamLabel=team[0].toUpperCase()+team.slice(1);
const api=path=>{const [name,search]=path.split('?',2),query=new URLSearchParams(search);if(local){if(team==='purple')query.set('side',team);return base+name+(query.size?'?'+query:'');}return 'api.php?team='+team+'&path='+encodeURIComponent(name)+(query.size?'&'+query:'');};
$('teamName').textContent=teamLabel;$('returnLink').href='/s/'+team+'/';
const preferencePrefix=team==='green'?'mobile-ltz:':'mobile-ltz:purple:';
let publishedAssets={};
const viewport=new MobileViewport(), mapPointers=new Map(), controlPointers=new Set();
let state=null,view=null,session=null,sequence=0,lastFeed=0,feedReady=false,joints=[-80,-5,-5],pendingJoints=false,inflight=false,heartbeatAt=0,generation=0,gesture=null,wheelDrag=null,rendererLoading=null;
const newIdentity=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
const preference={get(key){try{return localStorage.getItem(preferencePrefix+key);}catch{return null;}},set(key,value){try{localStorage.setItem(preferencePrefix+key,value);}catch{}}};
let clientIdentity=preference.get('client');
if(!/^[a-f0-9]{32}$/.test(clientIdentity||'')){clientIdentity=newIdentity();preference.set('client',clientIdentity);}
let joinWanted=preference.get('stopped')!=='yes',joining=false,joinRequest=null,joinRetryAt=0,joinFailures=0,controllerId=null,commandStateAt=0;
function transitionAllowsControls(){return !['calibration','upgrades','ready'].includes(state?.journey?.phase)||state?.journey?.active_side===team||Number.isInteger(state?.virtual_test_control)&&state?.journey?.phase!=='calibration';}
function canJoin(){return feedReady&&MobileGameState.hasLevel(state?.level)&&state?.virtual_play&&!state.paused&&transitionAllowsControls()&&(['setup','running'].includes(state.phase)||state.journey?.active_side===team);}
const request=async(path,data)=>{
  if(path==='command')data={...data,side:team};
  if(path==='command'&&data?.action!=='turret_aim'&&(data?.session?.startsWith('physical:')||(!state?.virtual_play&&!data?.session)))return physicalArm.command(data);
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
  try{
    let response;
    try{response=await fetch(api(path),{method:data?'POST':'GET',credentials:'same-origin',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,cache:'no-store',signal:controller.signal});}
    catch{throw Error(controller.signal.aborted?'Gamemaster timed out. Check the local relay.':'Cannot reach Gamemaster. Check the phone connection and local relay.');}
    if(response.status===401||response.redirected){if(!local&&!$('login').open)$('login').showModal();throw Error(path==='login'?'Wrong '+teamLabel+' password.':'Sign in to '+teamLabel+' to join.');}
    return await MobileNetwork.readJson(response);
  }finally{clearTimeout(timeout);}
};
viewport.setRotation(preference.get('rotation')==='180'||(preference.get('rotation')===null&&team==='purple')?180:0);
function syncRotationControl(){const rotated=viewport.rotation===180;$('rotateView').setAttribute('aria-pressed',String(rotated));$('rotateView').title=rotated?'Return to camera orientation':'Rotate the playfield 180°';}
syncRotationControl();
$('rotateView').onclick=()=>{if(controlPointers.size||mapPointers.size)return;viewport.setRotation(viewport.rotation===180?0:180);preference.set('rotation',String(viewport.rotation));syncRotationControl();syncViewport();updateXYZ();};
const feedbackLines=[];let feedbackPinnedUntil=0;
const feedback=(text,important=false)=>{
 text=String(text||'').trim();if(!text)return;
 if(important)feedbackPinnedUntil=performance.now()+8000;
 else if(performance.now()<feedbackPinnedUntil)return;
 if(feedbackLines[0]?.text===text&&(!important||feedbackLines[0].important))return;
 const duplicate=feedbackLines.findIndex(line=>line.text===text);if(duplicate>=0)feedbackLines.splice(duplicate,1);
 feedbackLines.unshift({text,important});feedbackLines.length=Math.min(5,feedbackLines.length);
 $('feedback').replaceChildren(...feedbackLines.map((line,i)=>{const row=document.createElement('div');row.textContent=line.text;if(line.important)row.setAttribute('class','urgent');if(i)row.setAttribute('aria-hidden','true');return row;}));
};
function syncViewport(){viewport.resize($('battlefield').clientWidth,$('battlefield').clientHeight);$('world').style.width=viewport.w+'px';$('world').style.height=viewport.h+'px';$('world').style.transform=viewport.css();layoutXYZ();drawXYZ();drawCalibrationCrosshair();drawMarkerLabels();if(typeof turretOverlay!=='undefined')turretOverlay.draw();}
const pumpModes=['suction','off','blow'];
function showPump(mode){
 for(const [id,value] of [['pumpSuck','suction'],['pumpBlow','blow']])$(id).setAttribute('aria-pressed',String(mode===value));
}
const jointControls=new MobileJointRig.JointControls();
const actualIndicators=[new MobileJointRig.IndicatorMotion(),new MobileJointRig.IndicatorMotion(),new MobileJointRig.IndicatorMotion()];
// XYZ shares the existing session and serialized command queue with Joint mode.
let controlMode='joint',controlRevision=0,switchBusy=false,xyzTarget=null,pendingXYZ=false,xyzSending=false,xyzFine=false,xyzPointer=null,xyzError='',xyzEdit=0;
let targetDrag=null,perspectiveDrag=null,cueTap=null,targetPreview=false,pendingXYZTarget=null;
const cartesian=()=>['xyz','targeting','cue'].includes(controlMode);
const xyzCenters={x:null,y:null,z:null};
const xyzIndicators={x:new MobileJointRig.IndicatorMotion(),y:new MobileJointRig.IndicatorMotion(),z:new MobileJointRig.IndicatorMotion()};
// Presets belong to this phone; recalling one still uses the validated XYZ queue.
let zPresets=[null,null,null],zPresetHold=null,zPresetClickUntil=0;
try{const raw=preference.get('z-presets');const saved=raw&&raw.length<1000?JSON.parse(raw):null;if(saved?.version===1&&Array.isArray(saved.slots)&&saved.slots.length===3)zPresets=saved.slots.map(v=>Number.isFinite(v)?v:null);}catch{}
const zPresetButtons=[1,2,3].map(i=>$('zPreset'+i));
function canUseZPresets(){return manualAvailable()&&!switchBusy&&cartesian()&&!document.hidden;}
function cancelZPresetHold(){
 const held=zPresetHold;zPresetHold=null;
 if(!held)return;
 clearTimeout(held.timer);held.button.removeAttribute('data-holding');
 if(held.pointer!=null){controlPointers.delete(held.pointer);if(held.button.hasPointerCapture(held.pointer))held.button.releasePointerCapture(held.pointer);}
}
function saveZPreset(index){
 if(!canUseZPresets()||!Number.isFinite(xyzTarget?.z))return;
 zPresets[index]=xyzTarget.z;
 let durable=true;
 try{localStorage.setItem(preferencePrefix+'z-presets',JSON.stringify({version:1,slots:zPresets}));}catch{durable=false;}
 updateZPresets();
 feedback(`Height ${index+1} saved: ${xyzTarget.z.toFixed(1)}.${durable?'':' Saved for this session only.'}`);
}
function recallZPreset(index){
 if(!canUseZPresets())return;
 const value=zPresets[index],limits=state?.mobile_arm?.xyz_limits?.z;
 if(value===null){feedback(`Hold ${index+1} for 3 seconds to save the selected height.`);return;}
 if(!limits||value<limits[0]||value>limits[1]){feedback(`Height ${index+1} is outside this level’s range. Hold to replace it.`);return;}
 xyzTarget.z=value;xyzCenters.z=null;pendingXYZTarget={...state.mobile_arm.tip,z:value};pendingXYZ=true;xyzEdit++;xyzError='';updateXYZ();
 feedback(`Height ${index+1}: ${value.toFixed(1)} requested.`);
}
function startZPresetHold(index,button,pointer=null,key=null){
 if(!canUseZPresets()||zPresetHold||controlPointers.size||mapPointers.size)return false;
 const held={index,button,pointer,key,started:performance.now(),saved:false};
 zPresetHold=held;button.dataset.holding='true';
 if(pointer!=null){controlPointers.add(pointer);button.setPointerCapture(pointer);}
 held.timer=setTimeout(()=>{if(zPresetHold===held&&canUseZPresets()){held.saved=true;button.removeAttribute('data-holding');saveZPreset(index);}},3000);
 return true;
}
function finishZPresetHold(){
 const held=zPresetHold;if(!held)return;
 const save=held.saved||performance.now()-held.started>=3000;
 if(!held.saved&&save)saveZPreset(held.index);
 cancelZPresetHold();zPresetClickUntil=performance.now()+500;
 if(!save)recallZPreset(held.index);
}
for(const [index,button] of zPresetButtons.entries()){
 button.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();if(startZPresetHold(index,button,e.pointerId))button.focus({preventScroll:true});});
 button.addEventListener('pointerup',e=>{if(zPresetHold?.button===button&&zPresetHold.pointer===e.pointerId)finishZPresetHold();});
 for(const type of ['pointercancel','lostpointercapture'])button.addEventListener(type,()=>{if(zPresetHold?.button===button)cancelZPresetHold();});
 button.addEventListener('keydown',e=>{if(![' ','Enter'].includes(e.key))return;e.preventDefault();if(!e.repeat)startZPresetHold(index,button,null,e.key);});
 button.addEventListener('keyup',e=>{if(zPresetHold?.button===button&&zPresetHold.key===e.key){e.preventDefault();finishZPresetHold();}});
 button.addEventListener('blur',()=>{if(zPresetHold?.button===button)cancelZPresetHold();});
 button.addEventListener('contextmenu',e=>e.preventDefault());
 button.addEventListener('click',e=>{e.preventDefault();if(e.detail===0&&performance.now()>zPresetClickUntil)recallZPreset(index);});
}
function updateZPresets(){
 const enabled=canUseZPresets();
 for(const [index,button] of zPresetButtons.entries()){
  const value=zPresets[index];button.disabled=!enabled;
  button.dataset.saved=String(value!==null);
  button.setAttribute('aria-pressed',String(value!==null&&Math.abs((xyzTarget?.z??Infinity)-value)<.1));
  button.setAttribute('aria-label',value===null?`Height preset ${index+1}, empty. Hold 3 seconds to save.`:`Height preset ${index+1}, ${value.toFixed(1)}. Tap to recall; hold 3 seconds to replace.`);
  button.title=value===null?'Hold 3 seconds to save':`${value.toFixed(1)} · tap to recall, hold 3 seconds to replace`;
 }
 if(!cartesian()||!xyzTarget)return;
 const panel=$('xyzHeightControl').getBoundingClientRect(),track=$('xyzZ').getBoundingClientRect();
 const svg=$('zPresetGuides');svg.setAttribute('viewBox',`0 0 ${panel.width+60} ${panel.height}`);
 const [lo,hi]=xyzBounds('z');
 for(const [index,value] of zPresets.entries()){
  const group=$('zPresetGuide'+(index+1)),visible=Number.isFinite(value)&&value>=lo&&value<=hi&&hi>lo;
  group.style.display=visible?'':'none';if(!visible)continue;
  const y=track.bottom-panel.top-12-(value-lo)/(hi-lo)*(track.height-24),x=track.left-panel.left+track.width/2;
  const b=zPresetButtons[index].getBoundingClientRect(),bx=b.left-panel.left,by=b.top-panel.top+b.height/2;
  group.querySelector('.zPresetMark').setAttribute('d',`M${x-12} ${y}H${x+12}`);
  group.querySelector('.zPresetLink').setAttribute('d',`M${x+12} ${y}H${x+23}L${bx-4} ${by}H${bx}`);
 }
}

function mobileUnlock(){const test=state?.virtual_test_control;return window.MobileJourney.calibrationSide(state)===team?(state.mobile_calibration?.stage==='tutorial'?3:2):Number.isInteger(test)?test:state?.mobile_progress?.player?.current_control_tier??0;}
function xyzBounds(axis){
 const limits=state?.mobile_arm?.xyz_limits?.[axis];
 if(!Array.isArray(limits)||!limits.every(Number.isFinite))return [0,1];
 // Present the battlefield span, expanding it if the arm is currently outside it.
 const value=xyzTarget?.[axis]??0,actual=state?.mobile_arm?.tip?.[axis]??value;
 const full=axis==='z'||state.mobile_arm?.coordinate_space==='robot-mm'?limits:[Math.max(limits[0],Math.min(0,value,actual)),Math.min(limits[1],Math.max(axis==='x'?viewport.w:viewport.h,value,actual))];
 if(xyzFine&&xyzCenters[axis]===null)xyzCenters[axis]=value;
 const zoomed=MobileJointRig.sliderBounds(full,xyzCenters[axis],xyzFine);
 if(xyzFine&&(value<zoomed[0]||value>zoomed[1]))xyzCenters[axis]=value;
 return MobileJointRig.sliderBounds(full,xyzCenters[axis],xyzFine);
}
// Only the controls use screen direction; goals, feedback and calibration stay
// in map coordinates. This sign converts either way, including fine ranges.
function xyzDirection(axis){return axis==='z'||state?.mobile_arm?.coordinate_space==='robot-mm'?1:viewport.direction;}
function xyzSliderBounds(axis){
 const [lo,hi]=xyzBounds(axis);return xyzDirection(axis)<0?[-hi,-lo]:[lo,hi];
}
function cancelXYZ(){
 cancelZPresetHold();targetDrag=null;perspectiveDrag=null;cueTap=null;
 pendingXYZ=false;targetPreview=false;pendingXYZTarget=null;xyzEdit++;xyzError='';
 const held=xyzPointer;xyzPointer=null;
 if(held){controlPointers.delete(held.id);if(held.el.hasPointerCapture(held.id))held.el.releasePointerCapture(held.id);}
 for(const axis of ['x','y','z'])xyzCenters[axis]=null;
}
let controlAssignment=null,awaitingControlMode=null;
function syncControlAssignment(){
 const key=JSON.stringify([state?.virtual_test_control,state?.mobile_progress?.player?.id,state?.mobile_progress?.player?.current_control_tier,window.MobileJourney.calibrationSide(state),state?.journey?.active_side,state?.journey?.session_id,state?.mobile_calibration?.stage]);
 if(key===controlAssignment)return;controlAssignment=key;
 cancelJointSliders();baseGoal=null;pendingJoints=false;cancelXYZ();xyzTarget=null;
 awaitingControlMode=['joint','xyz','targeting','cue'][Math.max(1,mobileUnlock())-1];controlMode=awaitingControlMode;
 presentControlMode(null);
 feedback(window.MobileJourney.calibrationSide(state)===team?(state.mobile_calibration?.stage==='perspective'?'Place a 100-series tag 3 cm above each outer reference; tap its centre or drag the crosshair, then save its reference number.':'Auto PP Cal 2 · place the arm on each target and save its number.'):controlMode[0].toUpperCase()+controlMode.slice(1)+' controls selected.');
}
function syncArmControls(arm,at=Infinity){
 if(!arm||at<commandStateAt||awaitingControlMode&&arm.control_mode!==awaitingControlMode)return;
 awaitingControlMode=null;
 const next=['xyz','targeting','cue'].includes(arm.control_mode)?arm.control_mode:'joint',revision=arm.control_revision??0;
 if(next!==controlMode||revision!==controlRevision){
  cancelJointSliders();baseGoal=null;pendingJoints=false;cancelXYZ();
  controlMode=next;controlRevision=revision;xyzTarget={...arm.tip};
 }
 if(!pendingXYZ&&!xyzSending&&!xyzPointer&&!targetDrag&&!targetPreview)xyzTarget={...(arm.xyz_target??arm.tip)};
 presentControlMode(arm);
}
function presentControlMode(arm){
 $('app').dataset.controlMode=controlMode;if(arm)syncCue(arm);
 const calibrationHeight=window.MobileJourney.calibrationSide(state)===team&&!['tutorial','complete'].includes(state.mobile_calibration?.stage);
 const heightPrecision=controlMode==='targeting'||calibrationHeight;
 const precision=$('xyzPrecision'),precisionParent=heightPrecision?$('zPresetButtons'):document.querySelector('.xyzControls');
 if(precision.parentElement!==precisionParent){
  if(heightPrecision)precisionParent.append(precision);
  else precisionParent.insertBefore(precision,$('xyzHint'));
 }
 for(const el of document.querySelectorAll('.xyzControls,.xyzHeight'))el.hidden=!cartesian()||(controlMode!=='xyz'&&el.classList.contains('xyzYControl'));
 layoutXYZ();
 $('xyzBullseyes').toggleAttribute('hidden',!cartesian());
 $('levelsOpen').innerHTML=(controlMode==='cue'?'Cue':controlMode==='targeting'?'Targeting':controlMode==='xyz'?'XYZ':'Joint')+' <span class="muted">⌄</span>';
 $('mobileControl').value=controlMode;
 for(const card of document.querySelectorAll('[data-control]'))card.classList.toggle('current',card.dataset.control===controlMode);
 updateXYZ();
}
function updateXYZ(){
 if(!xyzTarget)return;
 for(const axis of ['x','y','z']){
  const key=axis.toUpperCase(),el=$('xyz'+key),[lo,hi]=xyzSliderBounds(axis),value=xyzTarget[axis],sliderValue=value*xyzDirection(axis);
  el.min=lo;el.max=hi;el.step=xyzFine?.1:1;el.value=sliderValue;
  $('xyz'+key+'Value').textContent=value.toFixed(xyzFine?1:0);
  el.setAttribute('aria-valuetext',`${value.toFixed(1)} ${!state?.virtual_play&&axis==='z'?'millimeters':'map units'} target`);
  el.style.setProperty('--fill',Math.max(0,Math.min(100,(sliderValue-lo)/(hi-lo)*100))+'%');
 }
 for(const [id,axis,step] of xyzStepButtons){
  const button=$(id),amount=Math.abs(step)*(xyzFine?.1:1);
  button.querySelector('text').textContent=String(amount);button.dataset.step=String(amount);
  const direction=axis==='z'?(step>0?'Raise height':'Lower height'):`Move ${axis==='x'?(step>0?'right':'left'):(step>0?'down':'up')}`;
  const label=`${direction} by ${amount} ${amount===1?'unit':'units'}`;
  button.setAttribute('aria-label',label);button.title=label;
 }
 drawXYZ();updateZPresets();renderTargetMove();
}
function renderTargetMove(){
 const button=$('targetMove');button.hidden=controlMode!=='targeting';
 button.disabled=controlMode!=='targeting'||!targetPreview||!manualAvailable()||switchBusy||pendingXYZ||xyzSending||!!targetDrag||mapPointers.size>0;
}
function layoutXYZ(){
 const app=$('app').getBoundingClientRect();
 const header=document.querySelector('header').getBoundingClientRect();
 const telemetry=document.querySelector('.telemetry').getBoundingClientRect();
 const clearTop=Math.max(header.bottom,telemetry.bottom)+8;
 const connection=document.querySelector('.connectionControls');
 connection.style.top=(clearTop-app.top)+'px';
 $('cuePanel').style.top=(clearTop-app.top)+'px';
 $('cuePanel').style.setProperty('--cue-available',Math.max(0,app.height-(clearTop-app.top)-(parseFloat(getComputedStyle($('xyzHeightControl')).bottom)||80))+'px');
 if(!cartesian())return;
 const height=$('xyzHeightControl'),dockElement=document.querySelector('.xyzControls'),dock=dockElement.getBoundingClientRect();
 const bottom=parseFloat(getComputedStyle(height).bottom)||0;
 // Leave room for Connect/Stop above the left rail.
 const zTop=connection.getBoundingClientRect().bottom+8;
 height.style.height=Math.max(0,app.height-bottom-(zTop-app.top))+'px';
 const y=document.querySelector('.xyzYControl');
 const yTop=parseFloat(getComputedStyle(y).top)||8;
 y.style.height=Math.max(0,dock.top-app.top-yTop-8)+'px';
 const rail=height.getBoundingClientRect();
 const presetBottom=controlMode==='xyz'&&dockElement.getClientRects().length&&dock.left<rail.right+8+44?Math.min(rail.bottom,dock.top-8):rail.bottom;
 const span=Math.max(0,presetBottom-rail.top);
 const presets=$('zPresetButtons'),targeting=$('xyzPrecision').parentElement===presets;
 const extra=targeting?$('xyzPrecision').getBoundingClientRect().height+3*parseFloat(getComputedStyle(presets).gap):8;
 const size=Math.min(44,Math.max(targeting?24:28,(span-extra)/3)),stack=size*3+extra;
 presets.style.setProperty('--preset-size',size+'px');
 presets.style.top=Math.max(0,(span-stack)/2)+'px';
 updateZPresets();
}
function drawCalibrationCrosshair(){
 const target=window.MobileJourney?.perspectiveTarget(),svg=$('calibrationCrosshair');
 svg.toggleAttribute('hidden',!target);if(!target)return;
 svg.setAttribute('viewBox',`0 0 ${viewport.w} ${viewport.h}`);
 svg.dataset.mapped=String(target.mapped);
 svg.querySelector('g').setAttribute('transform',`translate(${target.camera.u*viewport.w} ${target.camera.v*viewport.h}) scale(${1/viewport.scale})`);
}
window.addEventListener('calibrationtargetchange',()=>{if(!window.MobileJourney.wantsPerspective())perspectiveDrag=null;layoutXYZ();drawCalibrationCrosshair();});
function drawXYZ(){
 if(state?.mobile_arm?.coordinate_space==='robot-mm'){$('xyzBullseyes').setAttribute('hidden','');return;}
 if(!cartesian()||!xyzTarget)return;
 const arm=state?.mobile_arm,tip=arm?.tip,svg=$('xyzBullseyes');
 // Cue previews the row's destination, including while paused. Intermediate
 // pickup/lift goals still drive the arm and Z slider through xyzTarget.
 const cue=arm?.cue,row=cue?.rows?.[cue.index];
 const destination=controlMode==='cue'&&(['running','paused'].includes(cue?.status)||cue?.waypoint)
  ?arm.markers?.find(marker=>marker.id===row?.destination):null;
 const target=destination??xyzTarget;
 const valid=tip&&['x','y','z'].every(k=>Number.isFinite(tip[k]));
 svg.toggleAttribute('hidden',!valid);
 if(!valid)return;
 const fresh=feedReady&&performance.now()-lastFeed<2500;
 // Two map units, independent of zoom. Z is intentionally a separate indicator.
 const aligned=fresh&&Math.hypot(target.x-tip.x,target.y-tip.y)<=2;
 svg.dataset.aligned=String(aligned);svg.dataset.stale=String(!fresh);
 svg.setAttribute('viewBox',`0 0 ${viewport.w} ${viewport.h}`);
 const edgeA=viewport.point(0,0),edgeB=viewport.point(viewport.vw,viewport.vh);
 const waypoint=controlMode==='cue'?cue?.waypoint:null;
 for(const id of ['cueWaypointGuides','cueWaypointBullseye'])$(id).toggleAttribute('hidden',!waypoint);
 if(waypoint){
  $('cueWaypointGuides').setAttribute('d',`M${edgeA.x} ${waypoint.y}H${edgeB.x} M${waypoint.x} ${edgeA.y}V${edgeB.y}`);
  $('cueWaypointBullseye').setAttribute('transform',`translate(${waypoint.x} ${waypoint.y}) scale(${1/viewport.scale})`);
  $('cueWaypointBullseye').setAttribute('aria-label',`Blue waypoint X ${waypoint.x.toFixed(1)}, Y ${waypoint.y.toFixed(1)}`);
 }
 for(const [id,p] of [['xyzTargetGuides',target],['xyzActualGuides',tip]])
  $(id).setAttribute('d',`M${edgeA.x} ${p.y}H${edgeB.x} M${p.x} ${edgeA.y}V${edgeB.y}`);
 for(const [id,p] of [['xyzTargetBullseye',target],['xyzActualBullseye',tip]]){
  $(id).setAttribute('transform',`translate(${p.x} ${p.y}) scale(${1/viewport.scale})`);
  $(id).setAttribute('aria-label',`${id==='xyzTargetBullseye'?'Target':'Actual'} X ${p.x.toFixed(1)}, Y ${p.y.toFixed(1)}`);
 }
 $('xyzAlignment').textContent=!fresh?'Position stale':aligned?'XY aligned':'Moving / offset';
 $('xyzAlignment').dataset.aligned=String(aligned);
}
function updateXYZMarkers(dt){
 if(!cartesian()||!xyzTarget)return;
 for(const axis of ['x','y','z']){
  const marker=$('xyz'+axis.toUpperCase()+'Actual'),confirmed=state?.mobile_arm?.tip?.[axis];
  const measured=xyzIndicators[axis].step(confirmed,dt,available()&&!document.hidden),value=Number.isFinite(measured)?measured*xyzDirection(axis):NaN,[lo,hi]=xyzSliderBounds(axis);
  marker.hidden=!Number.isFinite(value);if(marker.hidden)continue;
  marker.title=`Actual ${axis.toUpperCase()}: ${confirmed.toFixed(1)}`;
  marker.dataset.edge=value<lo?'low':value>hi?'high':'';
  let f=Math.max(0,Math.min(1,(value-lo)/(hi-lo)));
  if(axis==='y')f=1-f;
  marker.style[axis==='x'?'left':'bottom']=`calc(${f*100}% + ${12-24*f}px)`;
 }
 drawXYZ();
}
for(const axis of ['x','y','z']){
 const el=$('xyz'+axis.toUpperCase());
 el.addEventListener('pointerdown',e=>{
  if(!manualAvailable()||switchBusy||!cartesian()||(axis!=='z'&&controlMode!=='xyz')||controlPointers.size||mapPointers.size||e.button!==0){e.preventDefault();return;}
  xyzPointer={id:e.pointerId,el};controlPointers.add(e.pointerId);el.setPointerCapture(e.pointerId);
 });
 el.addEventListener('input',()=>{
  if(!manualAvailable()||switchBusy||!cartesian()||(axis!=='z'&&controlMode!=='xyz')||!xyzTarget||(controlPointers.size&&xyzPointer?.el!==el)){updateXYZ();return;}
  requestXYZAxis(axis,Number(el.value)*xyzDirection(axis));
 });
 for(const event of ['pointerup','lostpointercapture'])el.addEventListener(event,e=>{if(xyzPointer?.id===e.pointerId){controlPointers.delete(e.pointerId);xyzPointer=null;}});
 el.addEventListener('pointercancel',()=>suspend('Touch cancelled. Rejoining virtual controls…'));
}
function requestXYZAxis(axis,value){
 xyzTarget[axis]=value;if(axis!=='z')delete xyzTarget.tag_id;
 pendingXYZTarget=axis==='z'?{...state.mobile_arm.tip,z:value}:null;
 pendingXYZ=true;xyzEdit++;xyzError='';updateXYZ();
}
const xyzStepButtons=[
 ['xyzXDecrease','x',-10],['xyzXIncrease','x',10],
 ['xyzYDecrease','y',-10],['xyzYIncrease','y',10],
 ['xyzZDecrease','z',-1],['xyzZIncrease','z',1]
];
for(const [id,axis,step] of xyzStepButtons)$(id).addEventListener('click',()=>{
 if(!manualAvailable()||switchBusy||!cartesian()||(axis!=='z'&&controlMode!=='xyz')||document.hidden||controlPointers.size||mapPointers.size||!xyzTarget)return;
 const limits=state.mobile_arm?.xyz_limits?.[axis],current=xyzTarget[axis];
 if(!Array.isArray(limits)||limits.length!==2||!limits.every(Number.isFinite)||limits[0]>=limits[1]||!Number.isFinite(current))return;
 // Accumulate taps against the selected goal, not lagging robot feedback.
 // Like Joint, Fine tune divides arrow steps by ten without snapping the goal.
 const next=Math.max(limits[0],Math.min(limits[1],current+step*xyzDirection(axis)*(xyzFine?.1:1)));
 if(next!==current)requestXYZAxis(axis,next);
});
$('xyzPrecision').onclick=()=>{if(xyzPointer||targetDrag||perspectiveDrag||!manualAvailable())return;xyzFine=!xyzFine;for(const k of ['x','y','z'])xyzCenters[k]=null;$('xyzPrecision').setAttribute('aria-checked',String(xyzFine));updateXYZ();};
async function chooseControl(mode){
 if(!available()||switchBusy)return;
 switchBusy=true;clearInput();renderControls();feedback('Switching controls…');
 try{const result=await command('control_mode',{mode});if(result?.arm){feedback(mode==='cue'?'Build a cue and press Play.':mode==='targeting'?'Tap to preview a target, then press Go. Height stays separate.':mode==='xyz'?'Cartesian XYZ ready.':'Joint controls ready.');}}
 catch(e){feedback(e.message,true);}
 finally{switchBusy=false;$('mobileControl').value=controlMode;renderControls();}
}
$('mobileControl').onchange=()=>chooseControl($('mobileControl').value);

let cueDraft=[],cueDirty=false,cueBusy=false,cueSignature='',cueLastStatus='',markerSignature='',cueNotice='',cueLogNotice='';
const cueWaypointRow=$('cueWaypointRow');
function cueLocked(){return ['running','paused'].includes(state?.mobile_arm?.cue?.status);}
function manualAvailable(){return available()&&(state.virtual_play||state.mobile_arm?.enabled)&&!cueLocked()&&!cueBusy;}
function cueCandidates(){
 return {pieces:(state?.mobile_arm?.tags||[]).map(t=>t.id),markers:(state?.mobile_arm?.markers||[]).map(m=>m.id).sort((a,b)=>a-b)};
}
function cueDefaultRow(){const {pieces,markers}=cueCandidates();return {piece:pieces[0]??null,destination:markers[0]??null};}
function renderCueRows(){
 const {pieces,markers}=cueCandidates(),list=$('cueRows');list.replaceChildren(cueWaypointRow);
 cueDraft.forEach((row,index)=>{
  const item=document.createElement('div');item.className='cueRow';item.dataset.index=index;
  const summary=document.createElement('span');summary.className='cueSummary';summary.textContent=`${row.piece??'—'} → ${row.destination??'—'}`;item.append(summary);
  for(const [key,values,label] of [['piece',pieces,'Movable piece'],['destination',markers,'Destination marker']]){
   if(key==='destination'){const arrow=document.createElement('span');arrow.className='cueArrow';arrow.textContent='→';item.append(arrow);}
   const select=document.createElement('select');select.dataset.field=key;select.setAttribute('aria-label',`${label}, row ${index+1}`);
   const choices=values.includes(row[key])?values:[row[key],...values];
   for(const id of choices){const option=document.createElement('option');option.value=id??'';option.textContent=id==null?'Choose':String(id)+(values.includes(id)?'':' · missing');option.disabled=!values.includes(id);select.append(option);}
   select.value=row[key]??'';
   select.onchange=()=>{row[key]=Number(select.value);cueDirty=true;summary.textContent=`${row.piece} → ${row.destination}`;};item.append(select);
  }
  const remove=document.createElement('button');remove.textContent='−';remove.setAttribute('aria-label',`Remove row ${index+1}`);
  remove.onclick=()=>{cueDraft.splice(index,1);cueDirty=true;renderCueRows();updateCueControls();};item.append(remove);list.append(item);
 });
}
function updateCueControls(){
 const cue=state?.mobile_arm?.cue||{},running=cue.status==='running',disabled=!available()||switchBusy||cueBusy;
 for(const el of $('cueRows').querySelectorAll('.cueRow select,.cueRow button'))el.disabled=disabled||running;
 $('cueAdd').disabled=disabled||running||cueDraft.length>=32;
 $('cuePlay').disabled=disabled||!cueDraft.length;
 $('cueStop').disabled=disabled;
 $('cuePlay').textContent=running?'Ⅱ':'▶';$('cuePlay').setAttribute('aria-label',running?'Pause cue':cue.status==='paused'?'Resume cue':'Play cue');
 for(const [i,el] of [...$('cueRows').querySelectorAll('.cueRow')].entries()){
  el.dataset.active=String(!cueDirty&&i===cue.index&&['running','paused','error'].includes(cue.status));
  el.dataset.done=String(!cueDirty&&(cue.status==='completed'||i<cue.index));
 }
 const waypoint=cue.waypoint;
 cueWaypointRow.hidden=!waypoint;$('cueWaypointCancel').disabled=disabled;
 if(waypoint){
  $('cueWaypointLabel').textContent=`Blue · ${Math.round(waypoint.x)}, ${Math.round(waypoint.y)}`;
  const current=$('cueRows').querySelector(`.cueRow[data-index="${cue.index??0}"]`);
  if(cueWaypointRow.nextElementSibling!==current)$('cueRows').insertBefore(cueWaypointRow,current);
 }
 const statusKey=`${cue.status}:${cue.index}:${cue.stage}:${!!waypoint}`;
 if(statusKey!==cueLastStatus){
  cueLastStatus=statusKey;
  const active=waypoint?cueWaypointRow:$('cueRows').querySelector('[data-active=true]');
  if(active){const list=$('cueRows');if(active.offsetTop<list.scrollTop||active.offsetTop+active.offsetHeight>list.scrollTop+list.clientHeight)list.scrollTop=active.offsetTop;}
 }
 const notice=controlMode==='cue'?(cueNotice||cue.error||(cue.status==='running'?`Row ${cue.index+1} · ${cue.stage}`:cue.status==='paused'?`Paused · row ${cue.index+1}`:cue.status==='completed'?'Cue complete':cue.status==='stopped'?'Stopped · Play starts from row 1.':'Tap the map to insert a blue waypoint.')):'';
 if(notice&&notice!==cueLogNotice)feedback(notice,!!(cueNotice||cue.error));
 cueLogNotice=notice;
}
function syncCue(arm){
 $('cuePanel').hidden=controlMode!=='cue';
 const signature=JSON.stringify([arm.tags?.map(t=>t.id),arm.markers?.map(m=>m.id)]);
 let rebuild=signature!==cueSignature;cueSignature=signature;
 if(!cueDirty&&!cueBusy&&arm.cue?.rows?.length&&JSON.stringify(cueDraft)!==JSON.stringify(arm.cue.rows)){cueDraft=arm.cue.rows.map(r=>({...r}));rebuild=true;}
 if(!cueDraft.length&&!cueDirty&&controlMode==='cue'){cueDraft=[cueDefaultRow()];rebuild=true;}
 if(rebuild)renderCueRows();updateCueControls();drawMarkerLabels();
}
async function cueAction(action,fields={}){
 if(!available()||cueBusy||switchBusy)return;
 const height=Math.max(80,xyzTarget?.z??80);cueNotice='';
 cueBusy=true;cancelXYZ();updateCueControls();renderControls();
 try{
  if((action==='cue_play'||action==='cue_waypoint'&&!cueLocked())&&(cueDirty||JSON.stringify(cueDraft)!==JSON.stringify(state.mobile_arm.cue?.rows))){
   const result=await command('cue_set',{rows:cueDraft.map(r=>({...r})),control_revision:controlRevision});
   if(!result)return;cueDirty=false;
  }
  await command(action,{control_revision:controlRevision,height,...fields});
 }catch(e){cueNotice=e.message;cueLogNotice=e.message;feedback(e.message,true);}
 finally{cueBusy=false;renderControls();updateCueControls();}
}
$('cueAdd').onclick=()=>{if(cueDraft.length<32){cueDraft.push(cueDefaultRow());cueDirty=true;renderCueRows();updateCueControls();$('cueRows').scrollTop=$('cueRows').scrollHeight;}};
$('cuePlay').onclick=()=>cueAction(state?.mobile_arm?.cue?.status==='running'?'cue_pause':'cue_play');
$('cueStop').onclick=()=>cueAction('cue_stop');
$('cueWaypointCancel').onclick=()=>cueAction('cue_cancel_waypoint');
$('cueMinimize').onclick=()=>{const small=$('cuePanel').dataset.minimized!=='true';$('cuePanel').dataset.minimized=String(small);$('cueMinimize').textContent=small?'‹':'›';$('cueMinimize').setAttribute('aria-expanded',String(!small));$('cueMinimize').setAttribute('aria-label',small?'Expand cue':'Minimize cue');};
function drawMarkerLabels(){
 const calibrating=state?.journey?.phase==='calibration';
 const arm=state?.mobile_arm;if(!arm&&!calibrating){$('markerLabels').replaceChildren();markerSignature='';return;}
 const sockets=new Map((state.level?.sockets||[]).map(s=>[Number(s.aruco_id),s]));
 // Labels follow the rendered codes, whose centers can differ from arm placement targets.
 const markers=calibrating?(state.mobile_camera?.status==='ready'?state.mobile_camera.tags||[]:[]).map(t=>({id:t.id,x:t.u*viewport.w,y:t.v*viewport.h,kind:'calibration',size:24})):[...(arm.markers||[]).map(m=>{
  const visual=state.virtual_play?(m.kind==='core'?state.level?.core:sockets.get(m.id)):null;
  return {...m,x:visual?.marker_x??visual?.x??m.x,y:visual?.marker_y??visual?.y??m.y,
   size:visual?.marker_size??(m.kind==='core'?(state.core_aruco_code_footprint_px??116):(state.aruco_code_footprint_px??0))};
 }),...(arm.tags||[]).map(t=>({...t,kind:'piece',size:42}))];
 const signature=JSON.stringify(markers.map(m=>[m.id,m.kind]));
 if(signature!==markerSignature){markerSignature=signature;$('markerLabels').replaceChildren(...markers.map(m=>{const el=document.createElement('span');el.className='markerNumber';el.dataset.kind=m.kind;el.textContent='#'+m.id;return el;}));}
 for(const [i,m] of markers.entries()){
  const el=$('markerLabels').children[i];el.style.left=m.x+'px';el.style.top=(m.y+viewport.direction*m.size/2)+'px';el.style.transform=`rotate(${-viewport.rotation}deg) scale(${1/viewport.scale}) translate(-50%,4px)`;
 }
}

let baseGoal=null;
const sliderCenters=[null,null,null];
let jointFine=false,sliderPointer=null,rigPointer=null,sliderFrameAt=0;
const jointStepButtons=[
 ['baseLeft',0,1,'Rotate arm left'],['baseRight',0,-1,'Rotate arm right'],
 ['j2Decrease',1,-1,'Decrease shoulder J2'],['j2Increase',1,1,'Increase shoulder J2'],
 ['j3Decrease',2,-1,'Decrease elbow J3'],['j3Increase',2,1,'Increase elbow J3']
];
function jointBounds(axis){const b=state?.mobile_arm?.limits?.[axis];return Array.isArray(b)&&b.length===2&&b.every(Number.isFinite)&&b[0]<b[1]?b:[[-160,160],[-25,85],[-25,105]][axis];}
function sliderBounds(axis){
 const value=jointControls.value(axis,joints[axis]);
 if(jointFine&&sliderCenters[axis]===null)sliderCenters[axis]=value;
 const [lo,hi]=MobileJointRig.sliderBounds(jointBounds(axis),sliderCenters[axis],jointFine);
 // Re-anchor after a session reset or external target change, never during an ordinary drag.
 if(jointFine&&(value<lo-.00001||value>hi+.00001))sliderCenters[axis]=value;
 return MobileJointRig.sliderBounds(jointBounds(axis),sliderCenters[axis],jointFine);
}
function updateJoints(){
  const step=jointFine?.1:1;
  for(const [id,,,label] of jointStepButtons){const button=$(id);if(button.dataset.step===String(step))continue;button.dataset.step=String(step);button.querySelector('text').textContent=step+'°';button.title=label+' by '+step+'°';button.setAttribute('aria-label',label+' by '+step+' degree');}
  const baseBounds=jointBounds(0),baseValue=baseGoal??joints[0];
  $('j1Value').textContent=Number(baseValue.toFixed(1))+'°';
  $('wheel').setAttribute('aria-valuemin',baseBounds[0]);$('wheel').setAttribute('aria-valuemax',baseBounds[1]);
  $('wheel').setAttribute('aria-valuenow',baseValue);$('wheel').setAttribute('aria-valuetext',baseValue.toFixed(1)+' degrees target');
  $('baseSelector').setAttribute('transform',`rotate(${MobileJointRig.baseDialAngle(baseValue,baseBounds)} 120 136)`);
  for(const axis of [1,2]){const el=$('j'+(axis+1)),[lo,hi]=sliderBounds(axis),value=jointControls.value(axis,joints[axis]);el.min=lo;el.max=hi;el.step=jointFine?.05:.5;el.value=value;$('j'+(axis+1)+'Value').textContent=value.toFixed(jointFine?2:1)+'°';el.setAttribute('aria-valuetext',value.toFixed(jointFine?2:1)+' degrees target');el.style.setProperty('--fill',Math.max(0,Math.min(100,(value-lo)/(hi-lo)*100))+'%');}
}
let jointCaptionTop=null;
const jointRig=MobileJointRig.mount($('jointRig'),{
  state:()=>state?.mobile_arm,
  rightEdge:()=>document.querySelector('.jointControls').getBoundingClientRect().right,
  available:()=>controlMode==='joint'&&manualAvailable()&&!switchBusy&&!document.hidden,
  previewTargets:()=>jointControls.preview(joints),
  activeAxis:()=>rigPointer?.axis??jointControls.activeAxis,
  precision:()=>jointFine,
  goal:axis=>jointControls.value(axis,joints[axis]),
  begin:(axis,id)=>{if(controlPointers.size||mapPointers.size||sliderPointer)return false;controlPointers.add(id);rigPointer={axis,id};return true;},
  request:(axis,value)=>{const step=jointFine?.05:.5,[lo,hi]=jointBounds(axis);value=Math.max(lo,Math.min(hi,Math.round(value/step)*step));if(value!==jointControls.value(axis,joints[axis])){jointControls.request(axis,joints[axis],value);updateJoints();}},
  end:id=>{controlPointers.delete(id);if(rigPointer?.id===id)rigPointer=null;},
  cancel:()=>suspend('Sketch drag interrupted. Press Connect to resume.'),
  captionTop:(suggested,height)=>{
    const host=$('jointRig'),controls=document.querySelector('.jointControls'),app=$('app');
    const gap=6,maximum=app.clientHeight-host.offsetTop-controls.offsetHeight-height-gap-6;
    const top=Math.max(0,Math.min(maximum,(sliderPointer||rigPointer)&&jointCaptionTop!==null?jointCaptionTop:suggested));
    jointCaptionTop=top;controls.style.top=(host.offsetTop+top+height+gap)+'px';controls.style.bottom='auto';return top;
  }
});
function cancelJointSliders(){jointRig.cancelDrag();jointControls.cancel();sliderCenters.fill(null);const held=sliderPointer;sliderPointer=null;if(held){controlPointers.delete(held.id);if(held.el.hasPointerCapture(held.id))held.el.releasePointerCapture(held.id);}updateJoints();}
for(const axis of [1,2]){
 const el=$('j'+(axis+1));
 el.addEventListener('pointerdown',e=>{if(!available()||sliderPointer||controlPointers.size||mapPointers.size||e.button!==0){e.preventDefault();return;}sliderPointer={id:e.pointerId,el};controlPointers.add(e.pointerId);el.setPointerCapture(e.pointerId);});
 el.addEventListener('input',()=>{if(!available()||(controlPointers.size&&sliderPointer?.el!==el)){updateJoints();return;}jointControls.request(axis,joints[axis],Number(el.value));updateJoints();});
 const released=e=>{if(sliderPointer?.id!==e.pointerId)return;controlPointers.delete(e.pointerId);sliderPointer=null;jointRig.relayout();};
 el.addEventListener('pointerup',released);el.addEventListener('lostpointercapture',released);
 el.addEventListener('pointercancel',()=>suspend('Touch cancelled. Rejoining virtual controls…'));
}
$('jointPrecision').onclick=()=>{if(sliderPointer||rigPointer)return;jointFine=!jointFine;sliderCenters.fill(null);$('jointPrecision').setAttribute('aria-checked',String(jointFine));updateJoints();};
function updateActualMarkers(dt){
 const animate=available()&&!document.hidden&&performance.now()-lastFeed<2500;
 const baseValue=actualIndicators[0].step(state?.mobile_arm?.joints?.[0],dt,animate);
 $('baseActual').setAttribute('visibility',Number.isFinite(baseValue)?'visible':'hidden');
 if(Number.isFinite(baseValue)){$('baseActual').setAttribute('transform',`rotate(${MobileJointRig.baseDialAngle(baseValue,jointBounds(0))} 120 136)`);$('baseActual').setAttribute('aria-label',`Actual base: ${baseValue.toFixed(1)} degrees`);}
 for(const axis of [1,2]){
  const marker=$('j'+(axis+1)+'Actual'),confirmed=state?.mobile_arm?.joints?.[axis];
  const [physicalLo,physicalHi]=jointBounds(axis),[lo,hi]=sliderBounds(axis),value=actualIndicators[axis].step(Number.isFinite(confirmed)?Math.max(physicalLo,Math.min(physicalHi,confirmed)):null,dt,animate);
  marker.hidden=!Number.isFinite(value);if(marker.hidden)continue;
  marker.title=`Actual J${axis+1}: ${confirmed.toFixed(1)}°`;
  const key=[value.toFixed(4),lo,hi].join(',');if(marker.dataset.pose===key)continue;marker.dataset.pose=key;
  marker.dataset.edge=value<lo-.001?'low':value>hi+.001?'high':'';
  const fraction=Math.max(0,Math.min(1,(value-lo)/(hi-lo)));
  marker.style.left=`calc(${fraction*100}% + ${12-24*fraction}px)`;
 }
}
function advanceJointSliders(time){
 const dt=(time-sliderFrameAt)/1000;sliderFrameAt=time;updateActualMarkers(dt);updateXYZMarkers(dt);
 if(jointControls.moving){
  const confirmed=state?.mobile_arm?.joints;
  if(!available()||document.hidden||!Array.isArray(confirmed)||confirmed.length!==3||!confirmed.every(Number.isFinite)){cancelJointSliders();}
  else{for(const [axis,value] of jointControls.step(dt,confirmed,[jointBounds(1),jointBounds(2)],!state.virtual_play))target(axis,value);updateJoints();}
 }
 requestAnimationFrame(advanceJointSliders);
}
requestAnimationFrame(advanceJointSliders);
for(let i=0;i<=32;i++){const angle=(-90+i*180/32)*Math.PI/180;const tick=document.createElementNS('http://www.w3.org/2000/svg','line'),major=i%4===0;tick.setAttribute('x1',120+Math.sin(angle)*112);tick.setAttribute('y1',136-Math.cos(angle)*112);tick.setAttribute('x2',120+Math.sin(angle)*(major?105:108));tick.setAttribute('y2',136-Math.cos(angle)*(major?105:108));tick.style.opacity=major?'.65':'.3';$('ticks').append(tick);}
function available(){return !awaitingControlMode&&!state?.mobile_arm?.control_pending&&!!session&&feedReady&&MobileGameState.hasLevel(state?.level)&&(state.virtual_play||!!physicalArm.arm())&&!state.paused&&transitionAllowsControls()&&(['setup','running'].includes(state.phase)||state.journey?.active_side===team);}
function renderControls(){
 const physical=!!state&&!state.virtual_play;
 $('levelsOpen').disabled=false;updateCueControls();updateZPresets();
 const enabled=manualAvailable()&&!switchBusy;
 for(const id of ['xyzX','xyzY','xyzZ','xyzPrecision'])$(id).disabled=!enabled||!cartesian()||(controlMode!=='xyz'&&['xyzX','xyzY'].includes(id));
 renderTargetMove();
 $('mobileControl').disabled=!available()||switchBusy||state.virtual_test_control==null;
 for(const [name,tier] of [['xyz',2],['targeting',3],['cue',4]])$('mobileControl').querySelector('[value='+name+']').disabled=mobileUnlock()<tier;
 for(const id of ['j2','j3','jointPrecision'])$(id).disabled=!enabled;
 for(const id of ['pumpSuck','pumpBlow'])$(id).disabled=!enabled||pendingPump;
 for(const [id] of jointStepButtons)$(id).disabled=!enabled||controlMode!=='joint';
 for(const [id,axis] of xyzStepButtons)$(id).disabled=!enabled||!cartesian()||(axis!=='z'&&controlMode!=='xyz');
 $('wheel').setAttribute('aria-disabled',!enabled);
 const calibrationConnect=physical&&state.mobile_calibration_connect===true;
 $('connect').disabled=!!session||joining||!feedReady||!MobileGameState.hasLevel(state?.level)||state?.paused||(!calibrationConnect&&(!transitionAllowsControls()||!['setup','running'].includes(state?.phase)))||(physical&&!physicalArm.fresh());
 $('enableArm').hidden=!physical||!!state?.mobile_arm?.enabled;
 $('enableArm').disabled=!available();
 $('connection').textContent=!feedReady?'Reconnecting…':session?(physical&&!state.mobile_arm?.enabled?'Connected · disabled':'Connected'):state?.paused?'Paused':['won','overrun'].includes(state?.phase)&&state.journey?.active_side!==team?'Game ended':physical?teamLabel+' · disconnected':!joinWanted?'Stopped':canJoin()?'Joining…':'Game ended';
 $('connection').style.color=session?'#91efbc':'';
}

async function executeCommand(action,extra={}){
  const mine=generation,payload={action,...extra};
  if(session){payload.session=session;payload.sequence=++sequence;}
  let result;
  try{result=await request('command',payload);}
  catch(error){
   if(mine===generation&&error.code==='control_changed'&&session&&error.arm?.connected&&error.arm.session===session){
    clearInput();state.mobile_arm=error.arm;syncArmControls(error.arm);renderControls();feedback(error.message);return null;
   }
   throw error;
  }
  if(mine!==generation){
    if(action==='connect'&&result.arm?.session)request('command',{action:'stop',session:result.arm.session}).catch(()=>{});
    return null;
  }
  if(Number.isFinite(result.server_time))commandStateAt=result.server_time;
  if(action==='connect'){session=result.arm.session;controllerId=result.arm.controller_id;sequence=0;heartbeatAt=performance.now();}
  if(result.arm){if(state)state.mobile_arm=result.arm;syncArmControls(result.arm,result.server_time);if(!xyzError)feedback(result.arm.message);if(!controlPointers.size&&!pendingJoints&&!inflight){joints=result.arm.targets.map((v,i)=>i?jointControls.commanded(i,v):(baseGoal??v));updateJoints();}}
  renderControls();return result;
}
let pendingPump=false,confirmedPump='off',pumpStateAt=0;
let commandQueue=Promise.resolve();
function command(action,extra={}){const mine=generation;const next=commandQueue.catch(()=>{}).then(()=>{if(mine!==generation)return null;return executeCommand(action,extra);});commandQueue=next;return next;}
function recoverMotionLimit(error){
 if(error.code!=='motion_limit'||!session||!error.arm?.connected||error.arm.session!==session)return false;
 // Discard the rejected gesture and any coalesced goals, not the arm session.
 cancelXYZ();baseGoal=null;pendingJoints=false;wheelDrag=null;controlPointers.clear();cancelJointSliders();
 const arm=error.arm;state.mobile_arm=arm;joints=[...arm.joints];xyzTarget={...arm.tip};
 updateJoints();updateXYZ();renderControls();feedback(error.message,true);return true;
}
function clearInput(){cancelXYZ();baseGoal=null;cancelJointSliders();confirmedPump='off';showPump(confirmedPump);pendingJoints=false;controlPointers.clear();wheelDrag=null;mapPointers.clear();gesture=null;}
function suspend(reason='Reconnecting to virtual controls…'){
  const token=session;
  generation++;session=null;controllerId=null;joinRequest=null;clearInput();
  renderControls();feedback(reason,true);
  if(token)request('command',{action:'suspend',session:token}).catch(()=>{});
}
async function stop(reason='Stopped. Press Connect to resume.'){
  joinWanted=false;preference.set('stopped','yes');
  const token=session;generation++;session=null;controllerId=null;joinRequest=null;clearInput();renderControls();feedback(reason,true);
  try{await request('command',{action:'stop',...(token?{session:token}:{})});}catch{}
}
function keepJoined(now){
  if(!state?.virtual_play)return;
  if(!joinWanted||session||joining||!canJoin()||document.hidden||$('levels').open||$('login').open||now<joinRetryAt)return;
  joining=true;joinRequest??=newIdentity();const mine=generation;
  command('connect',{client_id:clientIdentity,request_id:joinRequest}).then(result=>{
    if(result&&mine===generation){joinRequest=null;joinFailures=0;}
  }).catch(error=>{if(mine===generation){feedback('Reconnecting automatically. '+error.message,true);joinFailures++;}}).finally(()=>{
    joining=false;joinRetryAt=performance.now()+Math.min(8000,1000*2**Math.min(joinFailures,3));renderControls();
  });
}
$('enableArm').onclick=()=>command('enable').catch(error=>feedback(error.message,true));
$('connect').onclick=()=>{if(state&&!state.virtual_play){joining=true;command('connect').catch(error=>feedback(error.message,true)).finally(()=>{joining=false;renderControls();});return;}joinWanted=true;preference.set('stopped','no');joinRetryAt=0;keepJoined(performance.now());};
$('stop').onclick=()=>stop();
for(const [id,selected] of [['pumpSuck','suction'],['pumpBlow','blow']])$(id).addEventListener('click',async()=>{
  if(!manualAvailable()||pendingPump)return;
  const mode=confirmedPump===selected?'off':selected;
  pendingPump=true;showPump(mode);$('pumpButtons').setAttribute('aria-busy','true');renderControls();
  feedback(mode==='suction'?'Suction requested…':mode==='off'?'Pump off requested…':'Blow requested…');
  try{const result=await command('pump',{mode});if(result?.arm){confirmedPump=pumpModes.includes(result.arm.pump)?result.arm.pump:'off';pumpStateAt=result.server_time??pumpStateAt;}}
  catch(e){suspend('Reconnecting automatically. '+e.message);}
  finally{pendingPump=false;$('pumpButtons').removeAttribute('aria-busy');showPump(confirmedPump);renderControls();}
});
function target(i,value){if(controlMode!=='joint'||switchBusy||!manualAvailable()||!Number.isFinite(value))return;const limits=state.mobile_arm?.limits||[[-160,160],[-25,85],[-25,105]];joints[i]=Math.max(limits[i][0],Math.min(limits[i][1],value));pendingJoints=true;updateJoints();}
const wheel=$('wheel');
function wheelPoint(e){const r=wheel.querySelector('svg').getBoundingClientRect(),x=(e.clientX-r.left)*240/r.width-120,y=136-(e.clientY-r.top)*160/r.height;return {angle:Math.atan2(x,y)*180/Math.PI,radius:Math.hypot(x,y)};}
function requestBase(value,snap=.5){
 if(controlMode!=='joint'||switchBusy||!manualAvailable()||document.hidden||!Number.isFinite(value))return;
 const [lo,hi]=jointBounds(0),next=Math.max(lo,Math.min(hi,snap?Math.round(value/snap)*snap:value));
 if(next===(baseGoal??joints[0]))return;
 baseGoal=next;target(0,baseGoal);
}
for(const [id,axis,direction] of jointStepButtons)$(id).addEventListener('click',()=>{
 if(controlMode!=='joint'||switchBusy||!manualAvailable()||document.hidden||controlPointers.size||mapPointers.size)return;
 // Step from the selected goal, including fractional angles and delayed feedback.
 const step=jointFine?.1:1;
 if(axis===0){requestBase((baseGoal??joints[0])+direction*step,0);return;}
 const current=jointControls.value(axis,joints[axis]),[lo,hi]=jointBounds(axis),next=Math.max(lo,Math.min(hi,current+direction*step));
 if(Math.abs(next-current)<.00000001)return;
 jointControls.request(axis,joints[axis],next);updateJoints();
});
wheel.addEventListener('pointerdown',e=>{if(e.button!==0||!available()||controlPointers.size||mapPointers.size)return;const p=wheelPoint(e);if(p.radius<72||Math.abs(p.angle)>90)return;e.preventDefault();wheel.setPointerCapture(e.pointerId);controlPointers.add(e.pointerId);wheelDrag={id:e.pointerId};requestBase(MobileJointRig.baseDialValue(p.angle,jointBounds(0)));});
wheel.addEventListener('pointermove',e=>{if(wheelDrag?.id!==e.pointerId||!available())return;e.preventDefault();const p=wheelPoint(e);if(p.radius<40||Math.abs(p.angle)>90)return;requestBase(MobileJointRig.baseDialValue(p.angle,jointBounds(0)));});
for(const event of ['pointerup','lostpointercapture'])wheel.addEventListener(event,e=>{controlPointers.delete(e.pointerId);if(wheelDrag?.id===e.pointerId)wheelDrag=null;});wheel.addEventListener('pointercancel',()=>suspend('Touch cancelled. Rejoining virtual controls…'));
wheel.addEventListener('keydown',e=>{if(!available()||controlPointers.size)return;const step=e.shiftKey?5:.5,[lo,hi]=jointBounds(0);if(['ArrowLeft','ArrowDown','ArrowRight','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();requestBase(e.key==='Home'?lo:e.key==='End'?hi:(baseGoal??joints[0])+(['ArrowRight','ArrowDown'].includes(e.key)?-step:step));}});
const battlefield=$('battlefield');function relative(e){const r=battlefield.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
function gestureValue(){const [a,b]=[...mapPointers.values()];return a&&b?{x:(a.x+b.x)/2,y:(a.y+b.y)/2,d:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y))}:null;}
// A single finger grabs the green target. A second finger switches to camera
// navigation; lifting it never silently starts a new arm drag.
battlefield.addEventListener('pointerdown',e=>{
 if(e.button!==0||controlPointers.size)return;
 const p=relative(e);mapPointers.set(e.pointerId,p);battlefield.setPointerCapture(e.pointerId);
 if(mapPointers.size>1){cueTap=null;targetDrag=null;perspectiveDrag=null;pendingXYZ=false;xyzEdit++;}
 else if(window.MobileJourney.wantsPerspective()){
  const point=viewport.point(p.x,p.y),camera=window.MobileJourney.perspectiveTarget().camera;
  cueTap={id:e.pointerId,point,screen:p,at:performance.now(),perspective:true};
  const target={x:camera.u*viewport.w,y:camera.v*viewport.h};
  // Use Targeting's 32 px grab area, drag offset and fine-tune scale, but keep
  // this optical cursor separate from all robot target/pending-command state.
  if(state.mobile_camera?.status==='ready'&&Math.hypot(point.x-target.x,point.y-target.y)*viewport.scale<=32){
   perspectiveDrag={id:e.pointerId,point,target,factor:xyzFine?.1:1,moved:false};e.preventDefault();
  }
 }
 else if(controlMode==='cue'&&available()&&!switchBusy&&!cueBusy){cueTap={id:e.pointerId,point:viewport.point(p.x,p.y),screen:p,at:performance.now()};}
 else if(controlMode==='targeting'&&manualAvailable()&&!switchBusy&&xyzTarget){
  cueTap={id:e.pointerId,point:viewport.point(p.x,p.y),screen:p,at:performance.now()};
  const point=viewport.point(p.x,p.y);
  if(Math.hypot(point.x-xyzTarget.x,point.y-xyzTarget.y)*viewport.scale<=32){
   targetDrag={id:e.pointerId,point,target:{...xyzTarget},factor:xyzFine?.1:1};
   e.preventDefault();
  }
 }
 gesture=gestureValue();
});
battlefield.addEventListener('pointermove',e=>{
 if(!mapPointers.has(e.pointerId))return;
 const p=relative(e);if(cueTap&&Math.hypot(p.x-cueTap.screen.x,p.y-cueTap.screen.y)>8)cueTap=null;mapPointers.set(e.pointerId,p);const next=gestureValue();
 if(next&&gesture){
  e.preventDefault();viewport.setZoom(viewport.zoom*next.d/gesture.d,gesture.x,gesture.y);
  viewport.pan(next.x-gesture.x,next.y-gesture.y);syncViewport();
 }else if(perspectiveDrag?.id===e.pointerId&&window.MobileJourney.wantsPerspective()){
  e.preventDefault();const point=viewport.point(p.x,p.y),drag=perspectiveDrag;
  if(Math.hypot(point.x-drag.point.x,point.y-drag.point.y)*viewport.scale>.1){
   drag.moved=true;
   window.MobileJourney.previewPerspective({
    u:Math.max(0,Math.min(1,(drag.target.x+(point.x-drag.point.x)*drag.factor)/viewport.w)),
    v:Math.max(0,Math.min(1,(drag.target.y+(point.y-drag.point.y)*drag.factor)/viewport.h)),
   });
  }
 }else if(targetDrag?.id===e.pointerId&&manualAvailable()&&!switchBusy){
  e.preventDefault();const point=viewport.point(p.x,p.y),drag=targetDrag;
  for(const axis of ['x','y']){
   const [lo,hi]=state.mobile_arm.xyz_limits[axis];
   xyzTarget[axis]=Math.max(lo,Math.min(hi,drag.target[axis]+(point[axis]-drag.point[axis])*drag.factor));
  }
  delete xyzTarget.tag_id;targetPreview=true;xyzEdit++;xyzError='';updateXYZ();
 }
 gesture=next;
});
function finishMapPointer(e,cancelled=false){
 const dragging=targetDrag?.id===e.pointerId,optical=perspectiveDrag?.id===e.pointerId?perspectiveDrag:null,tap=cueTap?.id===e.pointerId?cueTap:null;
 if(optical)perspectiveDrag=null;
 cueTap=null;
 if(tap?.perspective&&!optical?.moved&&!cancelled&&mapPointers.size===1&&performance.now()-tap.at<600)window.MobileJourney.previewPerspective({u:tap.point.x/viewport.w,v:tap.point.y/viewport.h});
 if(tap&&!tap.perspective&&!cancelled&&mapPointers.size===1&&performance.now()-tap.at<600&&controlMode==='targeting'&&manualAvailable()){
  if(tap.point.x>=0&&tap.point.x<=viewport.w&&tap.point.y>=0&&tap.point.y<=viewport.h){
   xyzTarget={...xyzTarget,x:tap.point.x,y:tap.point.y};delete xyzTarget.tag_id;
   if(!state.virtual_play){const near=(state.mobile_arm.tags||[]).filter(t=>Math.hypot(t.x-tap.point.x,t.y-tap.point.y)*viewport.scale<=24).sort((a,b)=>Math.hypot(a.x-tap.point.x,a.y-tap.point.y)-Math.hypot(b.x-tap.point.x,b.y-tap.point.y))[0];if(near){xyzTarget.x=near.x;xyzTarget.y=near.y;xyzTarget.tag_id=near.id;}}
   targetPreview=true;xyzEdit++;updateXYZ();feedback(xyzTarget.tag_id==null?'Target previewed. Press Go; height and pump stay separate.':`Atom ${xyzTarget.tag_id} previewed with perspective correction. Press Go; height and pump stay separate.`);
  }
 }
 if(tap&&!tap.perspective&&!cancelled&&mapPointers.size===1&&performance.now()-tap.at<600&&controlMode==='cue'&&available()){
  if(tap.point.x>=0&&tap.point.x<=viewport.w&&tap.point.y>=0&&tap.point.y<=viewport.h)cueAction('cue_waypoint',{point:tap.point});
  else feedback('Tap inside the battlefield to insert a waypoint.');
 }
 mapPointers.delete(e.pointerId);gesture=null;
 if(dragging){targetDrag=null;if(cancelled)suspend('Touch cancelled. Rejoining virtual controls…');}
 renderTargetMove();
}
battlefield.addEventListener('pointerup',e=>finishMapPointer(e));
for(const event of ['pointercancel','lostpointercapture'])battlefield.addEventListener(event,e=>finishMapPointer(e,true));
battlefield.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();cueTap=null;if(targetDrag||perspectiveDrag)return;const p=relative(e);viewport.setZoom(viewport.zoom*Math.exp(-e.deltaY*.01),p.x,p.y);syncViewport();},{passive:false});
$('targetMove').onclick=()=>{renderTargetMove();if($('targetMove').disabled)return;targetPreview=false;pendingXYZTarget=null;pendingXYZ=true;xyzEdit++;renderTargetMove();};
function drawArm(arm){const canvas=$('armCanvas'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);if(!arm||!state?.virtual_play)return;const {base,elbow,tip}=arm;if(controlMode==='joint'){ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#06170ea0';ctx.lineWidth=26;ctx.beginPath();ctx.moveTo(base.x,base.y);ctx.lineTo(elbow.x,elbow.y);ctx.lineTo(tip.x,tip.y);ctx.stroke();ctx.strokeStyle='#79dba8a6';ctx.lineWidth=11;ctx.stroke();for(const p of [base,elbow]){ctx.fillStyle='#172b22';ctx.strokeStyle='#b2f8ce';ctx.lineWidth=3;ctx.beginPath();ctx.arc(p.x,p.y,15,0,Math.PI*2);ctx.fill();ctx.stroke();}}for(const t of arm.tags){ctx.fillStyle=arm.held_tag===t.id?'#c4ffdc':'#358b58';ctx.strokeStyle='#d3ffe5';ctx.lineWidth=2;ctx.beginPath();ctx.arc(t.x,t.y,21,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#f6fff9';ctx.font='600 15px system-ui';ctx.textAlign='center';ctx.fillText(t.id,t.x,t.y+5);}if(cartesian())return;ctx.strokeStyle='#d1ffe1';ctx.lineWidth=2;ctx.beginPath();ctx.arc(tip.x,tip.y,32,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.moveTo(tip.x-40,tip.y);ctx.lineTo(tip.x-25,tip.y);ctx.moveTo(tip.x+25,tip.y);ctx.lineTo(tip.x+40,tip.y);ctx.moveTo(tip.x,tip.y-40);ctx.lineTo(tip.x,tip.y-25);ctx.stroke();}
function profile(value){
 const p=value?.player,tier=mobileUnlock(),test=state?.virtual_test_control!=null;
 $('profileStatus').textContent=test?`Practice unlock: tier ${tier}. Saved progress is unchanged.`:p?`${p.name} · ${p.credits??0} saved credits`:'Choose a saved profile in LTZ Score for your progression.';
 $('mobileControl').querySelector('[value=xyz]').textContent=tier>=2?'Cartesian XYZ':'Cartesian XYZ · locked';
 for(let i=2;i<=4;i++)$('tier'+i).textContent=i<=tier?'Unlocked · live':'Locked';
 $('mobileControl').querySelector('[value=targeting]').textContent=tier>=3?'Targeting':'Targeting · locked';
 $('mobileControl').querySelector('[value=cue]').textContent=tier>=4?'Cue autonomy':'Cue autonomy · locked';
}

// Reuse the mobile presentation; LTX owns calibration, planning and relay control.
const physicalArm=new MobilePhysicalArm({frame:$('physicalRobotFrame'),overlay:$('armReach'),viewport,team,changed:refreshPhysicalArm});
function physicalConnectionNotice(){
 if(state?.paused)return 'Game paused. Resume the game before connecting.';
 if(window.MobileJourney.calibrationSide(state)===team&&!state.mobile_calibration_ready)return state.mobile_calibration_error||state.journey?.motion_error||state.journey?.error||'Preparing your calibration. Waiting for fresh camera and enabled arm feedback.';
 if(!['setup','running'].includes(state?.phase)&&state?.journey?.active_side!==team)return 'Game ended. Gamemaster must Reset before reconnecting.';
 if(!transitionAllowsControls())return 'Waiting for the other player or shared game transition.';
 return physicalArm.arm()?'Press Connect to control '+teamLabel+'’s real arm.':physicalArm.error;
}
function refreshPhysicalArm(){
 if(!state||state.virtual_play)return;
 const arm=physicalArm.arm();state.mobile_arm=arm;
 if(session&&(!arm?.connected||arm.controller_id!==controllerId)){suspend('Physical feedback unavailable. Press Connect to resume.');}
 if(arm){
  syncArmControls(arm);
  if(!controlPointers.size&&!pendingJoints&&!inflight){joints=arm.targets.map((v,i)=>i?jointControls.commanded(i,v):(baseGoal??v));updateJoints();}
  if(!pendingPump){confirmedPump=pumpModes.includes(arm.pump)?arm.pump:'off';showPump(confirmedPump);}
  $('height').textContent=arm.tip.z.toFixed(1)+' mm';
  if(session)feedback(xyzError||arm.message);
 }else {$('xyzBullseyes').setAttribute('hidden','');feedback(physicalArm.error);}
 drawMarkerLabels();renderControls();
}
const turretOverlay=new MobileTurretOverlay({
 state:()=>state,viewport,team,fresh:()=>feedReady&&performance.now()-lastFeed<2500,
 busy:()=>!!targetDrag||!!xyzPointer||!!sliderPointer||controlPointers.size>0,
 cameraPointer:(id,p)=>{mapPointers.set(id,p);gesture=null;},
 hit:(x,y)=>view?.towerAtPoint(x,y),save:data=>request('command',data),
 frameURL:()=>api('assets/mobile-camera.jpg'),videoChanged:syncSceneNotice,message:feedback,
 confirm:tower=>{const index=state?.towers?.findIndex(t=>t.socket_id===tower.socket_id);if(index>=0)state.towers[index]=tower;}
});
let sceneNotice='';
function syncSceneNotice(){
 if(!state)return;
 const sceneVisible=state.virtual_play?!!view?.levelReady:turretOverlay.cameraReady();
 const notice=!feedReady?(state.error||'Waiting for Gamemaster…'):sceneVisible?'':state.virtual_play?'Waiting for the live level…':(state.mobile_camera?.error||(turretOverlay.imageAt?'Camera paused · showing last frame.':'Waiting for corrected live video…'));
 // Notices belong only in the left log. Frame callbacks log each transition once.
 const important=!feedReady?!!state.error:!state.virtual_play&&!!(state.mobile_camera?.error||turretOverlay.imageAt);
 if(notice&&notice!==sceneNotice)feedback(notice,important);
 sceneNotice=notice;
}
function applyState(value){if(state&&state.virtual_play!==value.virtual_play&&session)suspend('Play mode changed. Press Connect to resume.');if(!value.virtual_play)value={...value,mobile_arm:physicalArm.arm()};if(value.virtual_play&&state?.mobile_arm&&value.server_time<commandStateAt)value={...value,mobile_arm:state.mobile_arm};state=value;syncControlAssignment();document.body.classList.toggle('calibrating',value.journey?.phase==='calibration');window.MobileJourney?.update(value,request,async (target,preview=false)=>{if(!target)throw Error('Guided target unavailable');xyzTarget={x:target.camera[0]*viewport.w,y:target.camera[1]*viewport.h,z:target.pose[2]};targetPreview=preview;updateXYZ();if(preview)return;targetPreview=false;await request('command',{action:'xyz',session,sequence:++sequence,control_revision:state.mobile_arm?.control_revision,xyz:{...xyzTarget}});});lastFeed=performance.now();feedReady=value.status==='ready';view?.setFeedConnected(feedReady);viewport.configure(value);syncViewport();view?.applyState(value);syncSceneNotice();$('wave').textContent=value.wave||'—';$('core').textContent=value.core_max_hp?Math.round(value.core_hp/value.core_max_hp*100)+'%':'—';$('score').textContent=value.kills??0;$('mode').textContent=value.virtual_play?(value.phase==='setup'?'Ready · waiting for Start':'Simulation · practice'):'Physical mode';if(value.paused)$('mode').textContent='Paused';if(value.phase==='won')$('mode').textContent='Victory';if(value.phase==='overrun')$('mode').textContent='Core lost';const arm=value.mobile_arm;syncArmControls(arm,value.server_time);if(session&&(value.paused||(!['setup','running'].includes(value.phase)&&value.journey?.active_side!==team&&!value.mobile_calibration_connect)||(value.server_time>=commandStateAt&&(!arm?.connected||arm.controller_id!==controllerId))))suspend(value.virtual_play?'Rejoining virtual controls…':physicalConnectionNotice());if(arm){if(!controlPointers.size&&!pendingJoints&&!inflight){joints=arm.targets.map((v,i)=>i?jointControls.commanded(i,v):(baseGoal??v));updateJoints();}$('height').textContent=arm.tip.z<=80?'At pickup height':'Lower to pick / place';if(!pendingPump&&value.server_time>=pumpStateAt){confirmedPump=pumpModes.includes(arm.pump)?arm.pump:'off';showPump(confirmedPump);}if(session&&!pendingPump)feedback(xyzError||arm.message);}drawArm(arm);physicalArm.activate(!value.virtual_play);if(!value.virtual_play)refreshPhysicalArm();turretOverlay.sync();profile(value.mobile_progress);if(!session&&feedReady&&joinWanted)feedback(value.paused?'Game paused. Controls will resume automatically.':canJoin()?'Joining the virtual game automatically…':value.virtual_play?'Waiting for the next virtual game.':physicalConnectionNotice());renderControls();}
function showDiagnostics(value){
  window.mobilePerformance=Object.freeze({...value});
  document.querySelector('.diagnostics').title=value?`Source gap ${Math.round(value.sourceGapMs||0)} ms · Relay gap ${Math.round(value.gatewayGapMs||0)} ms · Receive gap ${Math.round(value.receiveGapMs||0)} ms · Correction ${Math.round(value.correctionPeakPx||0)} px`:"Waiting for delivery timing";
  const fields={updateHz:['updateHz',1],updateAge:['updateAgeMs',0],prediction:['predictionPercent',0],bufferMs:['bufferMs',0],framePeak:['peakFrameMs',0]};
  for(const [id,[key,digits]] of Object.entries(fields)){
    const number=value?.[key];$(id).textContent=Number.isFinite(number)?number.toFixed(digits):'—';
  }
  $('updateAge').dataset.stale=!!value&&value.updateAgeMs>500;
  $('framePeak').dataset.spike=!!value&&value.frameSpikes>0;
}
async function ensureRenderer(){if(view)return;if(!rendererLoading)rendererLoading=new Promise((resolve,reject)=>{const script=document.createElement('script');const url=api('renderer.js');script.src=url+(url.includes('?')?'&':'?')+'v='+encodeURIComponent(document.documentElement.dataset.mobileBuild||'current');script.onload=resolve;script.onerror=()=>{script.remove();rendererLoading=null;reject(Error('Could not load game renderer.'));};document.head.append(script);});await rendererLoading;view=TowerDefenceView.create({sandboxRoot:'',resolveAsset:path=>(!local&&publishedAssets[path])||api('assets/'+path),mapCanvas:$('mapCanvas'),gameCanvas:$('gameCanvas'),onAssetError:text=>feedback(text,true),onDiagnostics:showDiagnostics,onFps:fps=>{$('fps').textContent=Number.isFinite(fps)?Math.round(fps):'—';}});}
let pendingPresentation=null,presentationFrame=0;
function queuePresentation(value){
  pendingPresentation=value;
  if(!presentationFrame)presentationFrame=requestAnimationFrame(()=>{presentationFrame=0;const latest=pendingPresentation;pendingPresentation=null;applyState(latest);});
}
const gameState=new MobileGameState({apply:queuePresentation,load:async()=>{const value=await request('state');if(!local)liveFeed.offer(value.live_stream);return value;},error:error=>feedback(error.message,true)});
let booting=false;
const liveFeed=new MobileNetwork.LiveFeed({url:api('events'),receive:(value,partial)=>gameState.receive(value,partial),recover:()=>gameState.recover(),onError:text=>feedback(text,true)});
function openEvents(){liveFeed.start();}
async function boot(){
  if(booting)return;booting=true;
  try{const initial=await request('state');if(!local){liveFeed.offer(initial.live_stream);try{publishedAssets=await MobileNetwork.readJson(await fetch('assets.json',{cache:'no-cache'}),'Artwork index');}catch{publishedAssets={};}}await ensureRenderer();gameState.receive(initial);openEvents();}
  catch(e){feedback(e.message,true);setTimeout(()=>{if(!$('login').open&&!document.hidden)boot();},4000);}
  finally{booting=false;}
}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await request('login',{password:$('password').value});$('password').value='';$('loginError').textContent='';$('login').close();await boot();}catch(error){$('loginError').textContent=error.message;}};
$('levelsOpen').onclick=()=>{if(available())chooseControl(controlMode);else feedback('Connect to select controls.');$('levels').showModal();};$('levelsClose').onclick=()=>$('levels').close();
$('openPlayers').onclick=()=>{$('levels').close();window.MobileJourney.open();};
$('expand').onclick=async()=>{if(session)suspend('Restoring controls after the view change…');if(document.fullscreenElement){await document.exitFullscreen();return;}if(window.parent!==window){window.parent.postMessage({type:'mobile-ltz:expand',expanded:!$('app').classList.contains('expanded')},location.origin);$('app').classList.toggle('expanded');$('expand').innerHTML=$('app').classList.contains('expanded')?'⤡ <span>Return</span>':'⤢ <span>Expand</span>';}else if($('app').requestFullscreen){try{await $('app').requestFullscreen();}catch{$('app').classList.toggle('expanded');}}else{$('app').classList.toggle('expanded');$('expand').innerHTML=$('app').classList.contains('expanded')?'⤡ <span>Return</span>':'⤢ <span>Expand</span>';}syncViewport();};
function resized(){cueTap=null;perspectiveDrag=null;if(controlPointers.size||targetDrag)suspend('Restoring controls after resizing…');syncViewport();}new ResizeObserver(resized).observe(battlefield);window.visualViewport?.addEventListener('resize',resized);document.addEventListener('fullscreenchange',()=>{syncViewport();$('expand').innerHTML=document.fullscreenElement?'⤡ <span>Return</span>':'⤢ <span>Expand</span>';});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden){liveFeed.stop();feedReady=false;$('fps').textContent='—';if(session)suspend('Paused while away. Controls will resume automatically.');}
  else if(view&&!$('login').open){gameState.recover();openEvents();}
});
window.addEventListener('blur',()=>{cueTap=null;perspectiveDrag=null;if((controlPointers.size||targetDrag||jointControls.moving)&&session)suspend('Controls paused after focus changed.');});
window.addEventListener('pagehide',()=>{
  if(session){const token=session;generation++;session=null;clearInput();if(token.startsWith('physical:'))physicalArm.stop();else navigator.sendBeacon(api('command'),new Blob([JSON.stringify({action:'suspend',session:token})],{type:'application/json'}));}
  liveFeed.stop();turretOverlay.stopVideo();view?.destroy();
});
setInterval(async()=>{
 if(gameState.needsLevel())gameState.recover();
 if(feedReady&&performance.now()-lastFeed>2500){feedReady=false;view?.setFeedConnected(false);if(session)suspend('Reconnecting to the live game automatically…');renderControls();}
 if(view&&!document.hidden&&!$('login').open)liveFeed.tick(!feedReady);
 turretOverlay.video();turretOverlay.draw();physicalArm.tick();if(state&&!state.virtual_play)refreshPhysicalArm();
 keepJoined(performance.now());if(!available()||inflight||switchBusy)return;
 const now=performance.now();if(!pendingJoints&&!pendingXYZ&&now-heartbeatAt<500)return;
 inflight=true;const action=pendingXYZ&&cartesian()?'xyz':pendingJoints&&controlMode==='joint'?'joints':'heartbeat';
 const edit=xyzEdit,extra=action==='xyz'?{xyz:{...(pendingXYZTarget??xyzTarget)},height_only:pendingXYZTarget!==null,control_revision:controlRevision}:action==='joints'?{joints:[...joints],control_revision:controlRevision}:{};
 pendingJoints=false;pendingXYZ=false;pendingXYZTarget=null;xyzSending=action==='xyz';heartbeatAt=now;
 try{const result=await command(action,extra);if(action==='xyz'&&result?.arm&&edit===xyzEdit){xyzError='';feedback(result.arm.message);}}
 catch(e){
  if(recoverMotionLimit(e)){
   // Remain connected; the next deliberate gesture can move away from the limit.
  }else if(state?.virtual_play&&action==='xyz'&&session&&e.message.toLowerCase().includes('target')){
   if(edit===xyzEdit){xyzError=e.message;feedback(xyzError,true);xyzTarget={...(state.mobile_arm.xyz_target??state.mobile_arm.tip)};updateXYZ();}
  }else if(session)suspend('Reconnecting automatically. '+e.message);
 }finally{inflight=false;xyzSending=false;renderTargetMove();}
},80);
window.addEventListener('pageshow',e=>{if(e.persisted){view=null;rendererLoading=null;session=null;boot();}});
updateJoints();syncViewport();boot();
