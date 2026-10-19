/* Player-owned aiming UI. Game owns weapon geometry, revisions and placements. */
(function(root){
'use strict';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function project(h,x,y){const d=h[6]*x+h[7]*y+1;return {x:(h[0]*x+h[1]*y+h[2])/d,y:(h[3]*x+h[4]*y+h[5])/d};}
function inversePoint(h,u,v){
 const a=h[0]-u*h[6],b=h[1]-u*h[7],c=u-h[2],d=h[3]-v*h[6],e=h[4]-v*h[7],f=v-h[5],det=a*e-b*d;
 return Math.abs(det)<1e-10?null:{x:(c*e-b*f)/det,y:(a*f-c*d)/det};
}
class TurretOverlay{
 constructor(options){
  this.o=options;this.team=options.team||'green';this.selected=null;this.known=new Map();this.confirmed=new Map();this.run=null;this.draft=null;this.drag=null;this.saving=false;this.epoch=0;this.imageAt=0;this.frameRequest=null;this.frameNext=0;
  this.host=document.getElementById('turretOverlay');this.svg=this.host.querySelector('svg');this.panel=document.getElementById('turretAimPanel');
  this.image=document.getElementById('playfieldVideo');
  // These nodes also own the touch hit target. Camera packets must never
  // replace them while the browser is delivering a gesture.
  this.svg.innerHTML='<path class="aimArea"/><path class="aimLine" data-aim-ray/><circle class="aimBase" r="22"/><path class="aimLine" data-aim-leader stroke-dasharray="3 4"/><g data-aim-handle="aim" role="button"><circle class="aimTouch" r="24"/><rect x="-15" y="-15" width="30" height="30" rx="2"/><text y="5">✥</text></g>';
  this.nodes={area:this.svg.querySelector('.aimArea'),ray:this.svg.querySelector('[data-aim-ray]'),base:this.svg.querySelector('.aimBase'),leader:this.svg.querySelector('[data-aim-leader]'),handle:this.svg.querySelector('[data-aim-handle]')};
  this.registration=null;this.cameraPacket=null;this.pendingAim=null;
  this.panel.querySelector('button').onclick=()=>this.close();
  for(const event of ['pointerdown','pointermove','pointerup'])this.panel.addEventListener(event,e=>e.stopPropagation());
  this.svg.addEventListener('pointerdown',e=>this.down(e));
  const map=document.getElementById('battlefield');
  map.addEventListener('pointerdown',e=>this.down(e),true);
  map.addEventListener('pointermove',e=>this.move(e),true);
  map.addEventListener('pointerup',e=>this.up(e),true);
  map.addEventListener('pointercancel',e=>this.up(e,true),true);
  map.addEventListener('lostpointercapture',e=>{if(this.drag?.id===e.pointerId)this.up(e,true);},true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){this.cancel();this.registration=null;this.stopVideo();}});
 }
 key(t){return t.aim_instance||`${t.atom_tag_id}:${t.activation_started_at}`;}
 tower(){return this.o.state()?.towers?.find(t=>t.socket_id===this.selected&&t.owner===this.team&&!t.destroyed);}
 cameraReady(){const c=this.o.state()?.mobile_camera;return c?.status==='ready'&&this.imageAt>0&&!this.image.hidden&&this.image.width>0&&this.image.height>0&&Date.now()/1000-c.frame_at<2&&performance.now()-this.imageAt<2000;}
 ready(){const s=this.o.state();return this.o.fresh()&&s&&s.journey?.phase!=='calibration'&&!s.paused&&['setup','running'].includes(s.phase)&&(s.virtual_play||this.cameraReady());}
 projection(){
  const s=this.o.state(),c=s?.mobile_camera,t=c?.tracking,now=performance.now();
  const scope=JSON.stringify([s?.run_id,s?.level_revision,s?.virtual_play,s?.level?.width,s?.level?.height,
   t?.camera_identity,t?.camera_revision,t?.width??c?.width,t?.height??c?.height]);
  if(scope!==this.projectionScope){this.registration=null;this.projectionScope=scope;}
  if(c!==this.cameraPacket){
   this.cameraPacket=c;
   const age=(Number.isFinite(s?.server_time)?s.server_time:Date.now()/1000)-c?.frame_at;
   if(c?.status==='ready'&&Number.isFinite(age)&&age>=-.25&&age<1.5
      &&Array.isArray(c.matrix)&&c.matrix.length===8&&c.matrix.every(Number.isFinite)){
    const previous=this.registration;
    // One second of display/gesture continuity, bounded by the original
    // frame's 1.5 s freshness. Repeated packets cannot renew the same frame.
    let expires=now+Math.min(1000,(1.5-Math.max(0,age))*1000);
    if(previous?.frame===c.frame_at)expires=Math.min(expires,previous.expires);
    if(previous&&[[0,0],[1,0],[1,1],[0,1]].some(([x,y])=>{
     const a=project(previous.matrix,x,y),b=project(c.matrix,x,y);return Math.hypot(a.x-b.x,a.y-b.y)>.018;
    }))this.cancel();
    this.registration={scope,matrix:[...c.matrix],frame:c.frame_at,expires};
   }else if(c?.status!=='unavailable'||t?.contract!=='photon.board.camera-markers'||t.version!==1||t.status!=='ready'
      ||t.source!=='camera'||t.coordinate_space!=='corrected-camera-normalized')this.registration=null;
  }
  return this.registration?.expires>now?this.registration:null;
 }
 continuityReady(){
  const s=this.o.state();
  return !document.hidden&&this.o.fresh()&&s&&s.journey?.phase!=='calibration'&&!s.paused&&['setup','running'].includes(s.phase)
   &&(s.virtual_play||this.projection()&&this.imageAt>0&&!this.image.hidden&&performance.now()-this.imageAt<2000);
 }
 gestureScope(){const s=this.o.state(),v=this.o.viewport;this.projection();return JSON.stringify([this.projectionScope,s?.virtual_play,v.w,v.h,v.vw,v.vh,v.cx,v.cy,v.scale,v.rotation]);}
 currentGesture(drag){const scope=this.gestureScope(),continuous=this.continuityReady(),t=this.tower();return drag.epoch===this.epoch&&continuous&&this.key(t||{})===drag.key&&t?.aim_revision===drag.revision&&drag.scope===scope;}
 sync(){
  const s=this.o.state();if(!s)return;
  if(s.journey?.phase==='calibration'){this.close();this.refreshVideo();return;}
  const run=JSON.stringify([s.run_id,s.level_revision]);
  if(run!==this.run){this.close();this.known.clear();this.confirmed.clear();this.run=run;}
  for(const [i,t] of (s.towers||[]).entries()){const ack=this.confirmed.get(t.socket_id);if(ack&&this.key(ack)===this.key(t)&&ack.aim_revision>t.aim_revision)s.towers[i]=ack;}
  const friendly=(s.towers||[]).filter(t=>t.owner===this.team&&!t.destroyed);
  const added=friendly.filter(t=>this.known.get(t.socket_id)!==this.key(t));
  this.known=new Map(friendly.map(t=>[t.socket_id,this.key(t)]));
  if(added.length&&!this.drag&&!this.saving)this.select(added[added.length-1]);
  if(this.selected&&!this.tower())this.close();
  if(this.drag&&!this.currentGesture(this.drag))this.cancel();
  this.draw();this.refreshVideo();
 }
 select(t){this.cancel();this.selected=t.socket_id;this.drawKey=null;this.draft=null;this.notice='Drag square to aim and set range';this.noticeImportant=false;this.draw();}
 close(){this.cancel();this.selected=null;this.drawKey=null;this.draft=null;this.draw();}
 release(id){const map=document.getElementById('battlefield');if(id!==undefined&&map.hasPointerCapture(id))map.releasePointerCapture(id);}
 cancel(){const id=this.drag?.id;this.drag=null;this.draft=null;this.epoch++;this.release(id);}
 point(p){
  const s=this.o.state(),v=this.o.viewport;let q=p;
  if(!s.virtual_play){const c=this.projection();if(!c)return null;const n=project(this.drag?.matrix||this.pendingAim?.matrix||c.matrix,p.x/s.level.width,p.y/s.level.height);q={x:n.x*v.w,y:n.y*v.h};}
  return v.screen(q.x,q.y);
 }
 world(p){
  const s=this.o.state(),v=this.o.viewport,q=v.point(p.x,p.y);if(s.virtual_play)return q;
  const c=this.projection();if(!c)return null;
  const n=inversePoint(this.drag?.matrix||this.pendingAim?.matrix||c.matrix,q.x/v.w,q.y/v.h);return n&&{x:n.x*s.level.width,y:n.y*s.level.height};
 }
 relative(e){const b=document.getElementById('battlefield').getBoundingClientRect();return {x:e.clientX-b.left,y:e.clientY-b.top};}
 down(e){
  if(e.button!==0||e.target.closest?.('#turretAimPanel'))return;
  if(this.drag&&this.drag.id!==e.pointerId){const first=this.drag;this.cancel();this.o.cameraPointer?.(first.id,first.screen);this.draw();return;}
  if(!this.ready()||this.saving||this.o.busy())return;
  const p=this.relative(e),t=this.tower(),handle=e.target.closest?.('[data-aim-handle]')?.dataset.aimHandle;
  let hit=null;
  if(!handle){
   const s=this.o.state();
   if(s.virtual_play){const w=this.world(p);hit=this.o.hit?.(w.x,w.y);if(hit?.owner!==this.team||hit.destroyed)hit=null;}
   if(!hit)hit=(s.towers||[]).filter(t=>t.owner===this.team&&!t.destroyed).map(t=>({t,p:this.point(t)})).filter(a=>a.p&&Math.hypot(a.p.x-p.x,a.p.y-p.y)<=24).sort((a,b)=>Math.hypot(a.p.x-p.x,a.p.y-p.y)-Math.hypot(b.p.x-p.x,b.p.y-p.y))[0]?.t;
  }
  if(!(handle&&t)&&!hit)return;
  e.preventDefault();e.stopImmediatePropagation();
  if(hit)this.select(hit);
  const turret=hit||t;
  this.draft={angle:turret.targeting.angle_degrees,spread:turret.targeting.spread};
  this.drag={id:e.pointerId,kind:handle||'select',screen:p,pointer:this.world(p),start:{...this.draft},key:this.key(turret),revision:turret.aim_revision,run:this.o.state().run_id,epoch:this.epoch,
   scope:this.gestureScope(),matrix:this.projection()?.matrix};
  if(!this.drag.pointer){this.cancel();return;}
  document.getElementById('battlefield').setPointerCapture(e.pointerId);
  this.draw();
 }
 move(e){
  if(this.drag?.id!==e.pointerId)return;e.preventDefault();e.stopImmediatePropagation();
  this.drag.screen=this.relative(e);
  if(this.drag.kind==='select')return;
  const t=this.tower();if(!t||!this.currentGesture(this.drag)){this.cancel();this.draw();return;}
  const pointer=this.world(this.relative(e));if(!pointer)return;
  const start=this.drag.start,a=start.angle*Math.PI/180,g=t.targeting.control,range=g.range_at_spread_0+(g.range_at_spread_1-g.range_at_spread_0)*start.spread;
  const radius=range;
  const p={x:t.x+Math.cos(a)*radius+pointer.x-this.drag.pointer.x,y:t.y+Math.sin(a)*radius+pointer.y-this.drag.pointer.y};
  const aim=root.TowerDefenceView.geometry.towerAimFromPoint(t.targeting,t.x,t.y,p.x,p.y,this.draft.angle);
  this.draft={angle:aim.angle,spread:aim.spread};
  this.draw();
 }
 async up(e,cancelled=false){
  if(this.drag?.id!==e.pointerId)return;e.preventDefault();e.stopImmediatePropagation();
  const drag=this.drag,t=this.tower(),draft=this.draft;this.drag=null;
  this.release(e.pointerId);
  if(cancelled||drag.kind==='select'||!t||!this.currentGesture(drag)){this.draft=null;this.draw();return;}
  this.saving=true;this.pendingAim=drag;this.notice=this.ready()?'Saving…':'Waiting for tracking to save aim…';this.noticeImportant=false;this.draw();
  try{
   // Retain only the draft through a brief detector miss. The existing server
   // camera guard must still approve a fresh registration when saving.
   const deadline=performance.now()+1000;
   while(!this.ready()){
    if(!this.currentGesture(drag)||performance.now()>=deadline)throw Error('Tracking unavailable. Select the turret and try again.');
    await new Promise(resolve=>setTimeout(resolve,25));
   }
   if(!this.currentGesture(drag))throw Error('Turret or camera view changed. Select the turret again.');
   const result=await this.o.save({action:'turret_aim',socket_id:t.socket_id,atom_tag_id:t.atom_tag_id,
    activation_started_at:t.activation_started_at,aim_instance:t.aim_instance,aim_revision:drag.revision,run_id:drag.run,
    angle_degrees:draft.angle,spread:draft.spread});
   if(!result.ok)throw Error(result.error||'Could not save aim.');
   const current=this.tower();
   if(drag.epoch!==this.epoch||this.o.state()?.run_id!==drag.run||this.key(current||{})!==drag.key)return;
   if(!result.tower||result.tower.socket_id!==t.socket_id||this.key(result.tower)!==drag.key)throw Error('Turret changed. Select it again.');
   if(current.aim_revision>result.tower.aim_revision)return;
   this.confirmed.set(result.tower.socket_id,result.tower);this.o.confirm(result.tower);
   if(drag.epoch===this.epoch)this.notice='Saved';
  }catch(error){if(drag.epoch===this.epoch){this.notice=error.message;this.noticeImportant=true;}}
  finally{this.saving=false;this.pendingAim=null;this.draft=null;this.draw();}
 }
 safeBox(p,width,height,extra=[]){
  const v=this.o.viewport,map=document.getElementById('battlefield').getBoundingClientRect();
  const rects=[...document.querySelectorAll('header,.connectionControls,#xyzHeightControl,#zPresetButtons,#pumpButtons,#xyzPrecision,.jointControls,#wheel,#cuePanel,#mcam1Video')]
   .filter(el=>el.getClientRects().length&&getComputedStyle(el).display!=='none').map(el=>{const r=el.getBoundingClientRect();return {x:r.left-map.left,y:r.top-map.top,width:r.width,height:r.height};}).concat(extra);
  let best=null,score=Infinity;
  const test=(x,y)=>{x=clamp(x,4,Math.max(4,v.vw-width-4));y=clamp(y,4,Math.max(4,v.vh-height-4));
   const area=rects.reduce((sum,r)=>sum+Math.max(0,Math.min(x+width,r.x+r.width+4)-Math.max(x,r.x-4))*Math.max(0,Math.min(y+height,r.y+r.height+4)-Math.max(y,r.y-4)),0);
   const cost=area*1e6+(x-p.x)**2+(y-p.y)**2;if(cost<score){score=cost;best={x,y,width,height};}};
  test(p.x,p.y);
  if(score>1e5)for(let y=4;y<v.vh-height;y+=20)for(let x=4;x<v.vw-width;x+=20)test(x,y);
  return best;
 }
 draw(){
  if(!this.svg)return;
  this.projection();
  if(this.drag&&!this.currentGesture(this.drag))this.cancel();
  const s=this.o.state(),t=this.tower(),v=this.o.viewport;
  this.host.hidden=!t;this.panel.hidden=!t;if(!t)return;
  const inset=document.getElementById('mcam1Video');
  const layout=[document.getElementById('app').dataset.controlMode,document.getElementById('cuePanel').dataset.minimized,inset?.hidden,inset?.getAttribute('style')];
  const key=JSON.stringify([t.socket_id,t.x,t.y,t.targeting,this.draft,this.notice,this.saving,this.ready(),this.continuityReady(),s.virtual_play,this.drag?.matrix||this.pendingAim?.matrix||this.projection()?.matrix,v.vw,v.vh,v.cx,v.cy,v.scale,v.rotation,layout]);
  if(key===this.drawKey)return;this.drawKey=key;
  const stale=!this.continuityReady();this.host.dataset.stale=String(stale);
  const c=this.point(t);this.svg.style.visibility=c?'visible':'hidden';
  if(!c){this.panel.style.left='150px';this.panel.style.top='120px';this.status('Tracking unavailable',null,true);return;}
  const d=this.draft||{angle:t.targeting.angle_degrees,spread:t.targeting.spread},g=t.targeting.control;
  const range=g.range_at_spread_0+(g.range_at_spread_1-g.range_at_spread_0)*d.spread,angle=d.angle*Math.PI/180;
  const at=(r,a)=>({x:t.x+r*Math.cos(a),y:t.y+r*Math.sin(a)}),points=[];
  const interpolate=name=>g[name+'_at_spread_0']+(g[name+'_at_spread_1']-g[name+'_at_spread_0'])*d.spread;
  if(g.target_point){const target=at(range,angle),r=interpolate('blast_radius');for(let i=0;i<=48;i++)points.push({x:target.x+r*Math.cos(i*Math.PI/24),y:target.y+r*Math.sin(i*Math.PI/24)});}
  else if(!g.directional){for(let i=0;i<=64;i++)points.push(at(range,i*Math.PI/32));}
  else{const half=interpolate('half_angle')*Math.PI/180;points.push(t);for(let i=0;i<=40;i++)points.push(at(range,angle-half+2*half*i/40));points.push(t);}
  const path=points.map(p=>this.point(p)).filter(Boolean).map((p,i)=>`${i?'L':'M'}${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ')+' Z';
  const end=this.point(at(range,angle));
  this.svg.setAttribute('viewBox',`0 0 ${v.vw} ${v.vh}`);
  // Edge-clamped handles remain reachable while their lines retain the true geometry.
  const handleBoxes=[];
  const attr=(el,name,value)=>{value=String(value);if(el.getAttribute(name)!==value)el.setAttribute(name,value);};
  const n=this.nodes;
  attr(n.area,'d',path);attr(n.ray,'d',`M${c.x} ${c.y}L${end.x} ${end.y}`);attr(n.base,'cx',c.x);attr(n.base,'cy',c.y);
  n.handle.style.display=n.leader.style.display=!stale&&!this.saving?'':'none';
  if(!stale&&!this.saving){
   const box=this.safeBox({x:end.x-24,y:end.y-24},48,48);handleBoxes.push(box);
   const x=box.x+24,y=box.y+24;
   attr(n.leader,'d',`M${end.x} ${end.y}L${x} ${y}`);attr(n.handle,'transform',`translate(${x} ${y})`);
   attr(n.handle,'aria-label',g.directional?'Drag fire direction and range':'Drag firing range');
   attr(n.handle,'aria-disabled',!this.ready());
  }
  const panel=this.safeBox({x:c.x-66,y:c.y+30},164,38,handleBoxes);
  this.panel.style.left=panel.x+'px';this.panel.style.top=panel.y+'px';
  this.status(stale?(s.virtual_play?'Controls unavailable':'Tracking unavailable'):this.notice||'Drag square to aim and set range',`${t.tower_type.replaceAll('_',' ')} · ${Math.round(range)}${g.directional?' · '+Math.round(d.angle)+'°':''}`,stale||!!this.noticeImportant);
 }
 status(message,title,important=false){
  document.getElementById('turretAimTitle').textContent=title||'Turret';
  const key=JSON.stringify([message,important]);
  if(key!==this.logNotice){this.logNotice=key;this.o.message?.(message,important);}
 }
 refreshVideo(){
  const s=this.o.state();
  this.image.hidden=!s||s.virtual_play||document.hidden||!this.imageAt;
  this.o.videoChanged?.();
 }
 stopVideo(){
  this.frameRequest?.abort();this.frameRequest=null;this.frameNext=0;this.imageAt=0;
  if(this.fpsSampleStartedAt!=null){this.fpsSampleStartedAt=null;this.fpsFrames=0;this.o.onFps?.(null);}
  this.image.hidden=true;
  this.refreshVideo();
 }
 async video(){
  const s=this.o.state(),physical=s&&!s.virtual_play;
  document.getElementById('app').dataset.playfield=physical?'video':'virtual';
  if(!physical||document.hidden||this.o.videoActive?.()===false){this.stopVideo();return;}
  const now=performance.now();
  if(this.fpsSampleStartedAt==null){this.fpsSampleStartedAt=now;this.fpsFrames=0;}
  const elapsed=now-this.fpsSampleStartedAt;
  // Count completed camera paints, including zero during a stalled stream.
  if(elapsed>=1000){
   this.o.onFps?.(this.fpsFrames*1000/elapsed);
   this.fpsSampleStartedAt=now;this.fpsFrames=0;
  }
  this.refreshVideo();
  if(this.frameRequest||performance.now()<this.frameNext)return;
  const started=performance.now(),controller=new AbortController();
  this.frameRequest=controller;this.frameNext=started+80;
  const timeout=setTimeout(()=>controller.abort(),2000);let url,onAbort,next;
  try{
   const response=await fetch(this.o.frameURL(),{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(!response.ok||!response.headers.get('content-type')?.startsWith('image/jpeg'))throw Error('Video unavailable');
   url=URL.createObjectURL(await response.blob());
   // Keep one compositor surface for the lifetime of the page. Even swapping
   // decoded <img> nodes can flash in Safari; draw a completed JPEG onto the
   // existing canvas without clearing it between frames.
   next=new Image();next.src=url;
   await Promise.race([next.decode(),new Promise((_,reject)=>{onAbort=()=>reject(Error('Video request cancelled'));controller.signal.addEventListener('abort',onAbort,{once:true});if(controller.signal.aborted)onAbort();})]);
   if(controller.signal.aborted||this.frameRequest!==controller||document.hidden||!this.o.state()||this.o.state().virtual_play||performance.now()-started>=2000)return;
   // Request a software-backed surface for successive JPEG frames. On iPhone
   // WebKit the accelerated path accumulated over 2 GB of native rendering
   // memory even with one canvas and prompt release of the decoded images.
   const context=this.image.getContext('2d',{alpha:false,willReadFrequently:true});
   if(!context||!next.naturalWidth||!next.naturalHeight)throw Error('Video decode unavailable');
   // Camera coordinates remain at source resolution in the viewport. Only the
   // presentation surface is bounded: uploading 4K at every JPEG costs four
   // times as many pixels as 1080p, even on a small phone display.
   const scale=Math.min(1,1920/next.naturalWidth,1080/next.naturalHeight);
   const width=Math.round(next.naturalWidth*scale),height=Math.round(next.naturalHeight*scale);
   if(this.image.width!==width)this.image.width=width;
   if(this.image.height!==height)this.image.height=height;
   context.drawImage(next,0,0,width,height);
   this.fpsFrames++;
   this.imageAt=started;
  }catch{
   // Keep the last completed frame on screen during a transport gap.
   // Freshness still expires after two seconds and disables camera aiming.
   if(this.frameRequest===controller)this.frameNext=performance.now()+150;
  }finally{
   if(onAbort)controller.signal.removeEventListener('abort',onAbort);
   // The persistent canvas owns the visible frame now. Releasing the decoder
   // explicitly keeps successive high-resolution JPEGs from waiting for GC.
   next?.removeAttribute('src');
   if(url)URL.revokeObjectURL(url);clearTimeout(timeout);
   if(this.frameRequest===controller){this.frameRequest=null;this.refreshVideo();this.draw();}
  }
 }
}
root.MobileTurretOverlay=TurretOverlay;
if(typeof module!=='undefined')module.exports={project,inversePoint,TurretOverlay};
})(typeof window==='undefined'?globalThis:window);
