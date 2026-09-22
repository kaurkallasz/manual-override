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
  this.o=options;this.selected=null;this.known=new Map();this.confirmed=new Map();this.run=null;this.draft=null;this.drag=null;this.saving=false;this.epoch=0;this.imageAt=0;this.frameBusy=false;this.frameNext=0;
  this.host=document.getElementById('turretOverlay');this.svg=this.host.querySelector('svg');this.panel=document.getElementById('turretAimPanel');
  this.image=document.getElementById('playfieldVideo');
  this.panel.querySelector('button').onclick=()=>this.close();
  for(const event of ['pointerdown','pointermove','pointerup'])this.panel.addEventListener(event,e=>e.stopPropagation());
  this.svg.addEventListener('pointerdown',e=>this.down(e));
  const map=document.getElementById('battlefield');
  map.addEventListener('pointerdown',e=>this.down(e),true);
  map.addEventListener('pointermove',e=>this.move(e),true);
  map.addEventListener('pointerup',e=>this.up(e),true);
  map.addEventListener('pointercancel',e=>this.up(e,true),true);
  map.addEventListener('lostpointercapture',e=>{if(this.drag?.id===e.pointerId)this.up(e,true);},true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){this.cancel();this.imageAt=0;}});
 }
 key(t){return t.aim_instance||`${t.atom_tag_id}:${t.activation_started_at}`;}
 tower(){return this.o.state()?.towers?.find(t=>t.socket_id===this.selected&&t.owner==='green'&&!t.destroyed);}
 cameraReady(){const c=this.o.state()?.mobile_camera;return c?.status==='ready'&&this.imageAt>0&&!this.image.hidden&&this.image.complete&&this.image.naturalWidth>0&&Date.now()/1000-c.frame_at<2&&performance.now()-this.imageAt<2000;}
 ready(){const s=this.o.state();return this.o.fresh()&&s&&!s.paused&&['setup','running'].includes(s.phase)&&(s.virtual_play||this.cameraReady());}
 sync(){
  const s=this.o.state();if(!s)return;
  const run=JSON.stringify([s.run_id,s.level_revision]);
  if(run!==this.run){this.close();this.known.clear();this.confirmed.clear();this.run=run;}
  for(const [i,t] of (s.towers||[]).entries()){const ack=this.confirmed.get(t.socket_id);if(ack&&this.key(ack)===this.key(t)&&ack.aim_revision>t.aim_revision)s.towers[i]=ack;}
  const friendly=(s.towers||[]).filter(t=>t.owner==='green'&&!t.destroyed);
  const added=friendly.filter(t=>this.known.get(t.socket_id)!==this.key(t));
  this.known=new Map(friendly.map(t=>[t.socket_id,this.key(t)]));
  if(added.length&&!this.drag&&!this.saving)this.select(added[added.length-1]);
  if(this.selected&&!this.tower())this.close();
  if(this.drag&&(!this.ready()||this.key(this.tower()||{})!==this.drag.key||this.tower()?.aim_revision!==this.drag.revision))this.cancel();
  this.draw();this.video();
 }
 select(t){this.cancel();this.selected=t.socket_id;this.drawKey=null;this.draft=null;this.notice='Drag square to aim and set range';this.draw();}
 close(){this.cancel();this.selected=null;this.drawKey=null;this.draft=null;this.draw();}
 cancel(){this.drag=null;this.draft=null;this.epoch++;}
 point(p){
  const s=this.o.state(),v=this.o.viewport;let q=p;
  if(!s.virtual_play){const c=s.mobile_camera;if(c?.status!=='ready')return null;const n=project(c.matrix,p.x/s.level.width,p.y/s.level.height);q={x:n.x*v.w,y:n.y*v.h};}
  return {x:v.vw/2+(q.x-v.cx)*v.scale,y:v.vh/2+(q.y-v.cy)*v.scale};
 }
 world(p){
  const s=this.o.state(),v=this.o.viewport,q=v.point(p.x,p.y);if(s.virtual_play)return q;
  const n=inversePoint(s.mobile_camera.matrix,q.x/v.w,q.y/v.h);return n&&{x:n.x*s.level.width,y:n.y*s.level.height};
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
   if(s.virtual_play){const w=this.world(p);hit=this.o.hit?.(w.x,w.y);if(hit?.owner!=='green'||hit.destroyed)hit=null;}
   if(!hit)hit=(s.towers||[]).filter(t=>t.owner==='green'&&!t.destroyed).map(t=>({t,p:this.point(t)})).filter(a=>a.p&&Math.hypot(a.p.x-p.x,a.p.y-p.y)<=24).sort((a,b)=>Math.hypot(a.p.x-p.x,a.p.y-p.y)-Math.hypot(b.p.x-p.x,b.p.y-p.y))[0]?.t;
  }
  if(!(handle&&t)&&!hit)return;
  e.preventDefault();e.stopImmediatePropagation();
  if(hit)this.select(hit);
  const turret=hit||t;
  this.draft={angle:turret.targeting.angle_degrees,spread:turret.targeting.spread};
  this.drag={id:e.pointerId,kind:handle||'select',screen:p,pointer:this.world(p),start:{...this.draft},key:this.key(turret),revision:turret.aim_revision,run:this.o.state().run_id,epoch:this.epoch};
  document.getElementById('battlefield').setPointerCapture(e.pointerId);
  this.draw();
 }
 move(e){
  if(this.drag?.id!==e.pointerId)return;e.preventDefault();e.stopImmediatePropagation();
  this.drag.screen=this.relative(e);
  if(this.drag.kind==='select')return;
  const t=this.tower();if(!t||!this.ready()){this.cancel();return;}
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
  if(cancelled||drag.kind==='select'||!t||!this.ready()){this.draft=null;this.draw();return;}
  this.saving=true;this.notice='Saving…';this.draw();
  try{
   const result=await this.o.save({action:'turret_aim',socket_id:t.socket_id,atom_tag_id:t.atom_tag_id,
    activation_started_at:t.activation_started_at,aim_instance:t.aim_instance,aim_revision:drag.revision,run_id:drag.run,
    angle_degrees:draft.angle,spread:draft.spread});
   if(!result.ok)throw Error(result.error||'Could not save aim.');
   this.confirmed.set(result.tower.socket_id,result.tower);this.o.confirm(result.tower);
   if(drag.epoch===this.epoch)this.notice='Saved';
  }catch(error){if(drag.epoch===this.epoch)this.notice=error.message;}
  finally{this.saving=false;this.draft=null;this.draw();}
 }
 safeBox(p,width,height,extra=[]){
  const v=this.o.viewport,map=document.getElementById('battlefield').getBoundingClientRect();
  const rects=[...document.querySelectorAll('header,.connectionControls,#xyzHeightControl,#zPresetButtons,#pumpButtons,#xyzPrecision,.jointControls,#wheel,#cuePanel')]
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
  const s=this.o.state(),t=this.tower(),v=this.o.viewport;
  this.host.hidden=!t;this.panel.hidden=!t;if(!t)return;
  const key=JSON.stringify([t.socket_id,t.x,t.y,t.targeting,this.draft,this.notice,this.saving,this.ready(),s.virtual_play,s.mobile_camera,v.vw,v.vh,v.cx,v.cy,v.scale]);
  if(key===this.drawKey)return;this.drawKey=key;
  const stale=!this.ready();this.host.dataset.stale=String(stale);
  const c=this.point(t);if(!c){this.svg.replaceChildren();this.panel.style.left='150px';this.panel.style.top='120px';this.status('Tracking unavailable');return;}
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
  const handle=(name,p,label)=>{const box=this.safeBox({x:p.x-24,y:p.y-24},48,48,handleBoxes);handleBoxes.push(box);const x=box.x+24,y=box.y+24;return `<path class="aimLine" stroke-dasharray="3 4" d="M${p.x} ${p.y}L${x} ${y}"/><g data-aim-handle="${name}" role="button" aria-label="${label}" transform="translate(${x} ${y})"><circle class="aimTouch" r="24"/><rect x="-15" y="-15" width="30" height="30" rx="2"/><text y="5">✥</text></g>`;};
  this.svg.innerHTML=`<path class="aimArea" d="${path}"/><path class="aimLine" d="M${c.x} ${c.y}L${end.x} ${end.y}"/><circle class="aimBase" cx="${c.x}" cy="${c.y}" r="22"/>${!stale&&!this.saving?handle('aim',end,g.directional?'Drag fire direction and range':'Drag firing range'):''}`;
  const panel=this.safeBox({x:c.x-66,y:c.y+30},164,68,handleBoxes);
  this.panel.style.left=panel.x+'px';this.panel.style.top=panel.y+'px';
  this.status(stale?(s.virtual_play?'Controls unavailable':'Tracking unavailable'):this.notice||'Drag square to aim and set range',`${t.tower_type.replaceAll('_',' ')} · ${Math.round(range)}${g.directional?' · '+Math.round(d.angle)+'°':''}`);
 }
 status(message,title){document.getElementById('turretAimTitle').textContent=title||'Turret';document.getElementById('turretAimStatus').textContent=message;}
 async video(){
  const s=this.o.state(),physical=s&&!s.virtual_play;
  document.getElementById('app').dataset.playfield=physical?'video':'virtual';
  if(!physical){this.image.hidden=true;this.imageAt=0;return;}
  if(this.frameBusy||performance.now()<this.frameNext||document.hidden)return;
  this.frameBusy=true;this.frameNext=performance.now()+150;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),5000);
  try{
   const response=await fetch(this.o.frameURL(),{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(!response.ok||!response.headers.get('content-type')?.startsWith('image/jpeg'))throw Error('Video unavailable');
   const blob=await response.blob(),url=URL.createObjectURL(blob),old=this.frameURL;this.frameURL=url;
   this.image.src=url;await this.image.decode();if(old)URL.revokeObjectURL(old);
   this.imageAt=performance.now();this.image.hidden=!!this.o.state()?.virtual_play;
  }catch{this.imageAt=0;this.image.hidden=true;this.frameNext=performance.now()+1500;}
  finally{clearTimeout(timeout);this.frameBusy=false;this.draw();}
 }
}
root.MobileTurretOverlay=TurretOverlay;
if(typeof module!=='undefined')module.exports={project,inversePoint};
})(typeof window==='undefined'?globalThis:window);
