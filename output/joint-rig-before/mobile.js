'use strict';
const $=id=>document.getElementById(id), local=location.pathname.startsWith('/s/'), base='/s/gamemaster/p/mobile-ltz-api/api/';
const api=path=>local?base+path:'api.php?path='+encodeURIComponent(path);
let publishedAssets={};
const viewport=new MobileViewport(), mapPointers=new Map(), controlPointers=new Set();
let state=null,view=null,session=null,sequence=0,lastFeed=0,feedReady=false,joints=[-80,-5,-5],pendingJoints=false,inflight=false,heartbeatAt=0,generation=0,runKey=null,gesture=null,wheelDrag=null,rendererLoading=null;
const newIdentity=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
const preference={get(key){try{return localStorage.getItem('mobile-ltz:'+key);}catch{return null;}},set(key,value){try{localStorage.setItem('mobile-ltz:'+key,value);}catch{}}};
let clientIdentity=preference.get('client');
if(!/^[a-f0-9]{32}$/.test(clientIdentity||'')){clientIdentity=newIdentity();preference.set('client',clientIdentity);}
let joinWanted=preference.get('stopped')!=='yes',joining=false,joinRequest=null,joinRetryAt=0,joinFailures=0,controllerId=null,commandStateAt=0;
function canJoin(){return feedReady&&MobileGameState.hasLevel(state?.level)&&state?.virtual_play&&!state.paused&&['setup','running'].includes(state.phase);}
const request=async(path,data)=>{
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
  try{
    let response;
    try{response=await fetch(api(path),{method:data?'POST':'GET',credentials:'same-origin',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,cache:'no-store',signal:controller.signal});}
    catch{throw Error(controller.signal.aborted?'Gamemaster timed out. Check the local relay.':'Cannot reach Gamemaster. Check the phone connection and local relay.');}
    if(response.status===401||response.redirected){if(!local&&!$('login').open)$('login').showModal();throw Error(path==='login'?'Wrong Green password.':'Sign in to Green to join.');}
    return await MobileNetwork.readJson(response);
  }finally{clearTimeout(timeout);}
};
const feedback=text=>{$('feedback').textContent=text;};
function syncViewport(){viewport.resize($('battlefield').clientWidth,$('battlefield').clientHeight);$('world').style.transform=viewport.css();$('zoomValue').textContent=(Math.round(viewport.zoom*10)/10)+'×';$('zoomOut').disabled=viewport.zoom<=1;$('zoomIn').disabled=viewport.zoom>=4;syncMinimap();}
function zoom(value){viewport.setZoom(value);syncViewport();}
$('zoomIn').onclick=()=>zoom(Math.floor(viewport.zoom+0.01)+1);$('zoomOut').onclick=()=>zoom(Math.ceil(viewport.zoom-0.01)-1);$('fit').onclick=()=>{viewport.fit();syncViewport();};
// The minimap has its own pointer ownership; navigation never enters the command queue.
let mapChoice=null,mapDrag=null,mapThumbnailAt=0,mapThumbnailKey=null,lastMapZoom=1;
const compactMap=matchMedia('(orientation: landscape) and (max-height: 359px)');
function syncMinimap(){
  if((viewport.zoom>1)!==(lastMapZoom>1))mapChoice=null;
  lastMapZoom=viewport.zoom;
  const open=mapChoice??(viewport.zoom>1&&!compactMap.matches);
  $('minimapPanel').hidden=!open;
  $('mapToggle').setAttribute('aria-expanded',String(open));
  $('mapToggle').setAttribute('aria-label',open?'Hide minimap':'Show minimap');
  $('mapToggle').setAttribute('aria-pressed',String(open));
  const b=viewport.bounds(),r=$('mapWindow');
  r.style.left=(b.x/viewport.w*100)+'%';r.style.top=(b.y/viewport.h*100)+'%';
  r.style.width=(b.width/viewport.w*100)+'%';r.style.height=(b.height/viewport.h*100)+'%';
  $('minimap').style.aspectRatio=viewport.w+'/'+viewport.h;
  refreshMapThumbnail();
}
function refreshMapThumbnail(){
  if($('minimapPanel').hidden)return;
  const key=runKey,now=performance.now();
  // Cache the tiny static overview; occasional refresh also picks up late artwork loads.
  if(key===mapThumbnailKey&&now-mapThumbnailAt<1000)return;
  mapThumbnailKey=key;mapThumbnailAt=now;
  const canvas=$('minimapCanvas'),ctx=canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(view?.levelReady)ctx.drawImage($('mapCanvas'),0,0,canvas.width,canvas.height);
}
$('mapToggle').onclick=()=>{mapChoice=$('minimapPanel').hidden;syncMinimap();};
compactMap.addEventListener('change',()=>{mapChoice=null;syncMinimap();});
function mapPoint(e){const r=$('minimap').getBoundingClientRect();return{x:(e.clientX-r.left)/r.width*viewport.w,y:(e.clientY-r.top)/r.height*viewport.h};}
$('minimap').addEventListener('pointerdown',e=>{
  if(mapDrag||e.button!==0)return;e.preventDefault();
  const p=mapPoint(e),b=viewport.bounds();
  const inside=p.x>=b.x&&p.x<=b.x+b.width&&p.y>=b.y&&p.y<=b.y+b.height;
  mapDrag={id:e.pointerId,x:e.clientX,y:e.clientY,dx:inside?viewport.cx-p.x:0,dy:inside?viewport.cy-p.y:0,moved:false};
  $('minimap').setPointerCapture(e.pointerId);$('minimap').focus({preventScroll:true});
});
$('minimap').addEventListener('pointermove',e=>{
  if(mapDrag?.id!==e.pointerId)return;
  if(!mapDrag.moved&&Math.hypot(e.clientX-mapDrag.x,e.clientY-mapDrag.y)<4)return;
  mapDrag.moved=true;const p=mapPoint(e);viewport.center(p.x+mapDrag.dx,p.y+mapDrag.dy);syncViewport();
});
$('minimap').addEventListener('pointerup',e=>{if(mapDrag?.id!==e.pointerId)return;if(!mapDrag.moved){const p=mapPoint(e);viewport.center(p.x,p.y);syncViewport();}mapDrag=null;});
for(const event of ['pointercancel','lostpointercapture'])$('minimap').addEventListener(event,()=>{mapDrag=null;});
$('minimap').addEventListener('keydown',e=>{
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(e.key))return;
  e.preventDefault();const b=viewport.bounds(),step=e.shiftKey ? 0.3 : 0.1;
  if(e.key==='Home')viewport.fit();else viewport.center(viewport.cx+({'ArrowLeft':-1,'ArrowRight':1}[e.key]||0)*b.width*step,viewport.cy+({'ArrowUp':-1,'ArrowDown':1}[e.key]||0)*b.height*step);
  syncViewport();
});
const jointModes=['j2','j3','fine'],pumpModes=['suction','off','blow'];
let jointSwitchDragging=false;
function showSwitch(id,index){
  const el=$(id);el.value=index;el.parentElement.dataset.position=index;
  el.setAttribute('aria-valuetext',(id==='jointMode'?['Joint 2','Joint 3','Fine control']:['Suction','Off','Blow'])[index]);
}
// One native vertical range per switch gives a continuous touch target and keyboard access.
for(const id of ['jointMode','pumpMode']){
  const el=$(id);
  el.addEventListener('input',()=>showSwitch(id,Number(el.value)));
  el.addEventListener('keydown',e=>{
    if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(e.key)||el.disabled)return;
    e.preventDefault();const before=Number(el.value),next=e.key==='Home'?0:e.key==='End'?2:Math.max(0,Math.min(2,before+(['ArrowDown','ArrowRight'].includes(e.key)?1:-1)));
    if(next!==before){showSwitch(id,next);el.dispatchEvent(new Event('change',{bubbles:true}));}
  });
}
let jointMode=['j2','j3','fine'].includes(preference.get('joint-mode'))?preference.get('joint-mode'):'j2';
function jointLimits(i){return state?.mobile_arm?.limits?.[i-1]||([[-160,160],[-25,85],[-25,105]][i-1]);}
function configureJointRanges(){
  for(const i of [2,3]){
    const el=$('j'+i),[lo,hi]=jointLimits(i),fine=jointMode==='fine',span=(hi-lo)/(fine?10:1);
    const low=fine?Math.max(lo,Math.min(hi-span,joints[i-1]-span/2)):lo;
    el.min=low.toFixed(2);el.max=(low+span).toFixed(2);el.step=fine?'0.05':'0.5';
    $('j'+i+'Row').hidden=jointMode!=='fine'&&jointMode!=='j'+i;
  }
  if(!jointSwitchDragging)showSwitch('jointMode',jointModes.indexOf(jointMode));
  document.querySelector('.rightControls').dataset.jointMode=jointMode;
  $('app').dataset.jointMode=jointMode;
}
$('jointMode').addEventListener('pointerdown',()=>{jointSwitchDragging=true;});
$('jointMode').addEventListener('pointerup',()=>{jointSwitchDragging=false;});
$('jointMode').addEventListener('pointercancel',()=>{jointSwitchDragging=false;showSwitch('jointMode',jointModes.indexOf(jointMode));});
$('jointMode').addEventListener('change',()=>{
  jointSwitchDragging=false;
  if(controlPointers.size){showSwitch('jointMode',jointModes.indexOf(jointMode));return;}
  jointMode=jointModes[Number($('jointMode').value)];preference.set('joint-mode',jointMode);
  configureJointRanges();updateJoints();renderControls();
});
function updateJoints(){
  for(let i=1;i<=3;i++){
    $('j'+i+'Value').textContent=(i===1?Math.round(joints[0]):jointMode==='fine'?joints[i-1].toFixed(2):Number(joints[i-1].toFixed(2)))+'°';
    if(i>1){const slider=$('j'+i);slider.value=joints[i-1];slider.setAttribute('aria-valuetext',joints[i-1].toFixed(2)+' degrees');slider.style.setProperty('--fill',Math.max(0,Math.min(100,(joints[i-1]-Number(slider.min))/(Number(slider.max)-Number(slider.min))*100))+'%');}
  }
  $('wheel').setAttribute('aria-valuenow',Math.round(joints[0]));$('wheel').setAttribute('aria-valuetext',Math.round(joints[0])+' degrees');$('ticks').setAttribute('transform',`rotate(${-joints[0]*.35} 120 136)`);
}
for(let i=-32;i<=32;i++){const angle=i*5*Math.PI/180;const tick=document.createElementNS('http://www.w3.org/2000/svg','line'),major=i%4===0;tick.setAttribute('x1',120+Math.sin(angle)*104);tick.setAttribute('y1',136-Math.cos(angle)*104);tick.setAttribute('x2',120+Math.sin(angle)*(major?86:94));tick.setAttribute('y2',136-Math.cos(angle)*(major?86:94));tick.style.opacity=major?'.85':'.4';$('ticks').append(tick);}
function available(){return !!session&&feedReady&&MobileGameState.hasLevel(state?.level)&&state?.virtual_play&&!state.paused&&['setup','running'].includes(state.phase);}
function renderControls(){const enabled=available();for(const id of ['j2','j3'])$(id).disabled=!enabled||(['j2','j3'].includes(id)&&jointMode!=='fine'&&jointMode!==id);$('pumpMode').disabled=!enabled||pendingPump;$('jointMode').disabled=controlPointers.size>0;$('wheel').setAttribute('aria-disabled',!enabled);$('connect').disabled=!!session||joining||!feedReady||!state?.virtual_play||!MobileGameState.hasLevel(state?.level)||state?.paused||!['setup','running'].includes(state?.phase);$('connection').textContent=!feedReady?'Reconnecting…':session?'Connected':!joinWanted?'Stopped':state?.paused?'Paused':canJoin()?'Joining…':state?.virtual_play?'Game ended':'Waiting for virtual play';$('connection').style.color=session?'#91efbc':'';}
async function executeCommand(action,extra={}){
  const mine=generation,payload={action,...extra};
  if(session){payload.session=session;payload.sequence=++sequence;}
  const result=await request('command',payload);
  if(mine!==generation){
    if(action==='connect'&&result.arm?.session)request('command',{action:'stop',session:result.arm.session}).catch(()=>{});
    return null;
  }
  if(Number.isFinite(result.server_time))commandStateAt=result.server_time;
  if(action==='connect'){session=result.arm.session;controllerId=result.arm.controller_id;sequence=0;heartbeatAt=performance.now();}
  if(result.arm){feedback(result.arm.message);if(!controlPointers.size&&!pendingJoints&&!inflight){joints=[...result.arm.targets];configureJointRanges();updateJoints();}}
  renderControls();return result;
}
let pendingPump=false,pumpDragging=false,confirmedPump='off';
let commandQueue=Promise.resolve();
function command(action,extra={}){const mine=generation;const next=commandQueue.catch(()=>{}).then(()=>{if(mine!==generation)return null;return executeCommand(action,extra);});commandQueue=next;return next;}
function clearInput(){jointSwitchDragging=false;showSwitch('jointMode',jointModes.indexOf(jointMode));pumpDragging=false;showSwitch('pumpMode',pumpModes.indexOf(confirmedPump));pendingJoints=false;controlPointers.clear();wheelDrag=null;mapPointers.clear();gesture=null;}
function suspend(reason='Reconnecting to virtual controls…'){
  const token=session;
  generation++;session=null;controllerId=null;joinRequest=null;clearInput();
  renderControls();feedback(reason);
  if(token)request('command',{action:'suspend',session:token}).catch(()=>{});
}
async function stop(reason='Stopped. Press Connect to resume.'){
  joinWanted=false;preference.set('stopped','yes');
  const token=session;generation++;session=null;controllerId=null;joinRequest=null;clearInput();renderControls();feedback(reason);
  try{await request('command',{action:'stop',...(token?{session:token}:{})});}catch{}
}
function keepJoined(now){
  if(!joinWanted||session||joining||!canJoin()||document.hidden||$('levels').open||$('login').open||now<joinRetryAt)return;
  joining=true;joinRequest??=newIdentity();const mine=generation;
  command('connect',{client_id:clientIdentity,request_id:joinRequest}).then(result=>{
    if(result&&mine===generation){joinRequest=null;joinFailures=0;}
  }).catch(error=>{if(mine===generation){feedback('Reconnecting automatically. '+error.message);joinFailures++;}}).finally(()=>{
    joining=false;joinRetryAt=performance.now()+Math.min(8000,1000*2**Math.min(joinFailures,3));renderControls();
  });
}
$('connect').onclick=()=>{joinWanted=true;preference.set('stopped','no');joinRetryAt=0;keepJoined(performance.now());};
$('stop').onclick=()=>stop();
$('pumpMode').addEventListener('pointerdown',()=>{pumpDragging=true;});
$('pumpMode').addEventListener('pointerup',()=>{pumpDragging=false;});
$('pumpMode').addEventListener('pointercancel',()=>{pumpDragging=false;showSwitch('pumpMode',pumpModes.indexOf(confirmedPump));});
$('pumpMode').addEventListener('change',async()=>{
  pumpDragging=false;
  const mode=pumpModes[Number($('pumpMode').value)];
  if(!available()||pendingPump||mode===confirmedPump){showSwitch('pumpMode',pumpModes.indexOf(confirmedPump));return;}
  pendingPump=true;$('pumpMode').setAttribute('aria-busy','true');renderControls();
  feedback(mode==='suction'?'Suction requested…':mode==='off'?'Pump off requested…':'Blow requested…');
  try{const result=await command('pump',{mode});if(result?.arm)confirmedPump=result.arm.pump;}
  catch(e){suspend('Reconnecting automatically. '+e.message);}
  finally{pendingPump=false;$('pumpMode').removeAttribute('aria-busy');showSwitch('pumpMode',pumpModes.indexOf(confirmedPump));renderControls();}
});
function target(i,value){if(!available()||(i>0&&jointMode!=='fine'&&jointMode!=='j'+(i+1)))return;const limits=state.mobile_arm?.limits||[[-160,160],[-25,85],[-25,105]];joints[i]=Math.max(limits[i][0],Math.min(limits[i][1],value));pendingJoints=true;updateJoints();}
for(const i of [2,3]){
  const el=$('j'+i);
  el.addEventListener('pointerdown',e=>{if(available()&&!el.disabled){controlPointers.add(e.pointerId);el.setPointerCapture(e.pointerId);$('jointMode').disabled=true;}});
  el.addEventListener('input',()=>target(i-1,+el.value));
  const released=e=>{
    controlPointers.delete(e.pointerId);
    if(!controlPointers.size){configureJointRanges();updateJoints();}
    renderControls();
  };
  el.addEventListener('pointerup',released);
  el.addEventListener('lostpointercapture',released);
  el.addEventListener('keyup',e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','PageUp','PageDown','Home','End'].includes(e.key)){configureJointRanges();updateJoints();}});
  el.addEventListener('pointercancel',()=>suspend('Touch cancelled. Rejoining virtual controls…'));
}
const wheel=$('wheel');
function wheelAngle(e){const r=wheel.getBoundingClientRect();return Math.atan2(e.clientX-r.left-r.width/2,r.top+r.width*(136/240)-e.clientY)*180/Math.PI;}
wheel.addEventListener('pointerdown',e=>{if(!available())return;e.preventDefault();wheel.setPointerCapture(e.pointerId);controlPointers.add(e.pointerId);wheelDrag={id:e.pointerId,last:wheelAngle(e)};});
wheel.addEventListener('pointermove',e=>{if(wheelDrag?.id!==e.pointerId||!available())return;e.preventDefault();const angle=wheelAngle(e);let delta=angle-wheelDrag.last;delta=(delta+540)%360-180;wheelDrag.last=angle;target(0,joints[0]-delta);});
wheel.addEventListener('pointerup',e=>{controlPointers.delete(e.pointerId);if(wheelDrag?.id===e.pointerId)wheelDrag=null;});wheel.addEventListener('pointercancel',()=>suspend('Touch cancelled. Rejoining virtual controls…'));
wheel.addEventListener('keydown',e=>{if(!available())return;const step=e.shiftKey?5:.5;if(['ArrowLeft','ArrowDown','ArrowRight','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();target(0,e.key==='Home'?-160:e.key==='End'?160:joints[0]+(['ArrowRight','ArrowDown'].includes(e.key)?-step:step));}});
const battlefield=$('battlefield');function relative(e){const r=battlefield.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
function gestureValue(){const [a,b]=[...mapPointers.values()];return a&&b?{x:(a.x+b.x)/2,y:(a.y+b.y)/2,d:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y))}:null;}
battlefield.addEventListener('pointerdown',e=>{mapPointers.set(e.pointerId,relative(e));battlefield.setPointerCapture(e.pointerId);gesture=gestureValue();});
battlefield.addEventListener('pointermove',e=>{if(!mapPointers.has(e.pointerId))return;mapPointers.set(e.pointerId,relative(e));const next=gestureValue();if(next&&gesture){e.preventDefault();viewport.setZoom(viewport.zoom*next.d/gesture.d,gesture.x,gesture.y);viewport.pan(next.x-gesture.x,next.y-gesture.y);syncViewport();}gesture=next;});
for(const name of ['pointerup','pointercancel'])battlefield.addEventListener(name,e=>{mapPointers.delete(e.pointerId);gesture=null;});
battlefield.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();const p=relative(e);viewport.setZoom(viewport.zoom*Math.exp(-e.deltaY*.01),p.x,p.y);syncViewport();},{passive:false});
function drawArm(arm){const canvas=$('armCanvas'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);if(!arm||!state?.virtual_play)return;const {base,elbow,tip}=arm;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#06170ea0';ctx.lineWidth=26;ctx.beginPath();ctx.moveTo(base.x,base.y);ctx.lineTo(elbow.x,elbow.y);ctx.lineTo(tip.x,tip.y);ctx.stroke();ctx.strokeStyle='#79dba8a6';ctx.lineWidth=11;ctx.stroke();for(const p of [base,elbow]){ctx.fillStyle='#172b22';ctx.strokeStyle='#b2f8ce';ctx.lineWidth=3;ctx.beginPath();ctx.arc(p.x,p.y,15,0,Math.PI*2);ctx.fill();ctx.stroke();}for(const t of arm.tags){ctx.fillStyle=arm.held_tag===t.id?'#c4ffdc':'#358b58';ctx.strokeStyle='#d3ffe5';ctx.lineWidth=2;ctx.beginPath();ctx.arc(t.x,t.y,21,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#f6fff9';ctx.font='600 15px system-ui';ctx.textAlign='center';ctx.fillText(t.id,t.x,t.y+5);}ctx.strokeStyle='#d1ffe1';ctx.lineWidth=2;ctx.beginPath();ctx.arc(tip.x,tip.y,32,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.moveTo(tip.x-40,tip.y);ctx.lineTo(tip.x-25,tip.y);ctx.moveTo(tip.x+25,tip.y);ctx.lineTo(tip.x+40,tip.y);ctx.moveTo(tip.x,tip.y-40);ctx.lineTo(tip.x,tip.y-25);ctx.stroke();}
function profile(value){const p=value?.player;$('profileStatus').textContent=p?`${p.name} · ${p.credits??0} saved credits`:'Choose a saved profile in LTZ Score for your progression.';for(let i=2;i<=4;i++){$('tier'+i).textContent=!p?'Progress unavailable':i<=(p.unlocked_control??p.max_control_tier??1)?'Unlocked · preview':'Locked · preview';}}
function applyState(value){state=value;lastFeed=performance.now();feedReady=value.status==='ready';view?.setFeedConnected(feedReady);const key=JSON.stringify([value.run_id,value.level_revision,value.level?.name]);if(value.level){viewport.w=value.level.width;viewport.h=value.level.height;}if(key!==runKey){runKey=key;viewport.fit();}syncViewport();view?.applyState(value);const sceneVisible=!!(value.virtual_play&&view?.levelReady);$('empty').hidden=sceneVisible;$('empty').style.display=sceneVisible?'none':'flex';$('emptyMessage').textContent=!feedReady?(value.error||'Waiting for Gamemaster…'):value.virtual_play?'Waiting for the live level…':'Ask Gamemaster to start a virtual game.';$('wave').textContent=value.wave||'—';$('core').textContent=value.core_max_hp?Math.round(value.core_hp/value.core_max_hp*100)+'%':'—';$('score').textContent=value.kills??0;$('mode').textContent=value.virtual_play?(value.phase==='setup'?'Ready · waiting for Start':'Simulation · practice'):'Physical mode';if(value.paused)$('mode').textContent='Paused';if(value.phase==='won')$('mode').textContent='Victory';if(value.phase==='overrun')$('mode').textContent='Core lost';const arm=value.mobile_arm;if(session&&(value.paused||!value.virtual_play||!['setup','running'].includes(value.phase)||(value.server_time>=commandStateAt&&(!arm?.connected||arm.controller_id!==controllerId))))suspend('Rejoining virtual controls…');if(arm){if(!controlPointers.size&&!pendingJoints&&!inflight){joints=[...arm.targets];configureJointRanges();updateJoints();}$('height').textContent=arm.tip.z<=80?'At pickup height':'Lower to pick / place';confirmedPump=pumpModes.includes(arm.pump)?arm.pump:'off';if(!pendingPump&&!pumpDragging)showSwitch('pumpMode',pumpModes.indexOf(confirmedPump));if(session&&!pendingPump)feedback(arm.message);}drawArm(arm);profile(value.mobile_progress);if(!session&&feedReady&&joinWanted)feedback(value.paused?'Game paused. Controls will resume automatically.':canJoin()?'Joining the virtual game automatically…':value.virtual_play?'Waiting for the next virtual game.':'Waiting for Gamemaster to select virtual play.');renderControls();}
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
async function ensureRenderer(){if(view)return;if(!rendererLoading)rendererLoading=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=api('renderer.js')+(local?'?':'&')+'v='+encodeURIComponent(document.documentElement.dataset.mobileBuild||'current');script.onload=resolve;script.onerror=()=>{script.remove();rendererLoading=null;reject(Error('Could not load game renderer.'));};document.head.append(script);});await rendererLoading;view=TowerDefenceView.create({sandboxRoot:'',resolveAsset:path=>(!local&&publishedAssets[path])||api('assets/'+path),mapCanvas:$('mapCanvas'),gameCanvas:$('gameCanvas'),onAssetError:feedback,onDiagnostics:showDiagnostics,onFps:fps=>{$('fps').textContent=Number.isFinite(fps)?Math.round(fps):'—';}});}
let pendingPresentation=null,presentationFrame=0;
function queuePresentation(value){
  pendingPresentation=value;
  if(!presentationFrame)presentationFrame=requestAnimationFrame(()=>{presentationFrame=0;const latest=pendingPresentation;pendingPresentation=null;applyState(latest);});
}
const gameState=new MobileGameState({apply:queuePresentation,load:async()=>{const value=await request('state');if(!local)liveFeed.offer(value.live_stream);return value;},error:error=>{$('emptyMessage').textContent=error.message;feedback(error.message);}});
let booting=false;
const liveFeed=new MobileNetwork.LiveFeed({url:api('events'),receive:(value,partial)=>gameState.receive(value,partial),recover:()=>gameState.recover(),onError:feedback});
function openEvents(){liveFeed.start();}
async function boot(){
  if(booting)return;booting=true;
  try{const initial=await request('state');if(!local){liveFeed.offer(initial.live_stream);try{publishedAssets=await MobileNetwork.readJson(await fetch('assets.json',{cache:'no-cache'}),'Artwork index');}catch{publishedAssets={};}}await ensureRenderer();gameState.receive(initial);openEvents();}
  catch(e){$('emptyMessage').textContent=e.message;feedback(e.message);setTimeout(()=>{if(!$('login').open&&!document.hidden)boot();},4000);}
  finally{booting=false;}
}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await request('login',{password:$('password').value});$('password').value='';$('loginError').textContent='';$('login').close();await boot();}catch(error){$('loginError').textContent=error.message;}};
$('levelsOpen').onclick=()=>{if(session)suspend('Controls paused while viewing the control path.');$('levels').showModal();};$('levelsClose').onclick=()=>$('levels').close();
$('expand').onclick=async()=>{if(session)suspend('Restoring controls after the view change…');if(document.fullscreenElement){await document.exitFullscreen();return;}if(window.parent!==window){window.parent.postMessage({type:'mobile-ltz:expand',expanded:!$('app').classList.contains('expanded')},location.origin);$('app').classList.toggle('expanded');$('expand').innerHTML=$('app').classList.contains('expanded')?'⤡ <span>Return</span>':'⤢ <span>Expand</span>';}else if($('app').requestFullscreen){try{await $('app').requestFullscreen();}catch{$('app').classList.toggle('expanded');}}else{$('app').classList.toggle('expanded');$('expand').innerHTML=$('app').classList.contains('expanded')?'⤡ <span>Return</span>':'⤢ <span>Expand</span>';}syncViewport();};
function resized(){if(controlPointers.size)suspend('Restoring controls after resizing…');syncViewport();}new ResizeObserver(resized).observe(battlefield);window.visualViewport?.addEventListener('resize',resized);document.addEventListener('fullscreenchange',()=>{syncViewport();$('expand').innerHTML=document.fullscreenElement?'⤡ <span>Return</span>':'⤢ <span>Expand</span>';});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden){liveFeed.stop();feedReady=false;$('fps').textContent='—';if(session)suspend('Paused while away. Controls will resume automatically.');}
  else if(view&&!$('login').open){gameState.recover();openEvents();}
});
window.addEventListener('pagehide',()=>{
  if(session){const token=session;generation++;session=null;clearInput();navigator.sendBeacon(api('command'),new Blob([JSON.stringify({action:'suspend',session:token})],{type:'application/json'}));}
  liveFeed.stop();view?.destroy();
});
setInterval(async()=>{if(gameState.needsLevel())gameState.recover();if(feedReady&&performance.now()-lastFeed>2500){feedReady=false;view?.setFeedConnected(false);if(session)suspend('Reconnecting to the live game automatically…');renderControls();}if(view&&!document.hidden&&!$('login').open)liveFeed.tick(!feedReady);keepJoined(performance.now());if(!available()||inflight)return;const now=performance.now();if(!pendingJoints&&now-heartbeatAt<500)return;inflight=true;const action=pendingJoints?'joints':'heartbeat';pendingJoints=false;heartbeatAt=now;try{await command(action,action==='joints'?{joints:[...joints]}:{});}catch(e){if(session)suspend('Reconnecting automatically. '+e.message);}finally{inflight=false;}},80);
window.addEventListener('pageshow',e=>{if(e.persisted){view=null;rendererLoading=null;session=null;boot();}});
configureJointRanges();updateJoints();syncViewport();boot();
