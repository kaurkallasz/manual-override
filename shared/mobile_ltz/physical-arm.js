/* Presentation adapter only. LTX retains calibrated planning and the relay lease. */
class MobilePhysicalArm {
 constructor({frame,overlay,viewport,changed,team='green',diagnostic=()=>{}}){
  if(!['green','purple'].includes(team))throw Error('Unknown robot team.');
  Object.assign(this,{frame,overlay,viewport,changed,team});this.contract=team+'.mobile-arm';this.pending=new Map();this.counter=0;this.at=-Infinity;this.active=false;this.loading=false;this.retry=0;this.value=null;this.error='Loading calibrated '+team[0].toUpperCase()+team.slice(1)+' controls…';
  window.addEventListener('message',event=>this.receive(event));
  this.diagnostic=(...args)=>{try{diagnostic(...args);}catch{}};
 }
 post(value){this.frame.contentWindow?.postMessage({contract:this.contract,version:1,...value},location.origin);}
 receive(event){
  const d=event.data;
  if(event.source!==this.frame.contentWindow||event.origin!==location.origin||d?.contract!==this.contract||d.version!==1)return;
  if(d.type==='ready'){this.post({type:'ping'});return;}
  if(d.type==='diagnostic'){this.diagnostic('bridge',d.event,d.reason,d.context);return;}
  if(!['state','reply'].includes(d.type))return;
  this.value=d;this.at=performance.now();this.error=d.error||'Calibrated arm position unavailable.';
  const progress=d.active_command,waiting=this.pending.get(progress?.id),arm=this.arm();
  // Detours can take longer than a single target. Extend only the command the
  // calibrated owner is currently executing, with fresh same-session feedback.
  if(['xyz','cue_waypoint'].includes(waiting?.action)&&progress.action===waiting.action&&waiting.session&&progress.session===waiting.session&&arm?.session===waiting.session&&arm.connected&&arm.enabled&&!arm.control_pending&&performance.now()<waiting.deadline){
   clearTimeout(waiting.timer);waiting.timer=setTimeout(waiting.expire,Math.min(15000,waiting.deadline-performance.now()));
  }
  if(d.type==='reply'){
   const pending=this.pending.get(d.id);
   if(pending){clearTimeout(pending.timer);this.pending.delete(d.id);const arm=this.arm();d.ok&&arm?pending.resolve({ok:true,arm,server_time:Date.now()/1000}):pending.reject(Object.assign(Error(d.error||this.error),{code:d.code,arm}));}
  }
  this.draw();this.changed?.();
 }
 fresh(){return this.active&&performance.now()-this.at<1500;}
 diagnostics(){return {...this.value?.diagnostics,controller_age_ms:Number.isFinite(this.at)?performance.now()-this.at:null,pending_commands:this.pending.size,status:this.value?.status,robot_error:this.value?.error||this.value?.arm?.motion_error};}
 arm(){
  const a=this.value?.arm,p=p=>p&&['x','y','z'].every(k=>Number.isFinite(p[k]));
  if(!this.fresh()||this.value.status!=='ready'||!a||!p(a.tip)||!p(a.xyz_target)||!['joints','targets'].every(k=>Array.isArray(a[k])&&a[k].length===3&&a[k].every(Number.isFinite))||!Array.isArray(a.limits)||a.limits.length!==3||!a.limits.every(l=>Array.isArray(l)&&l.length===2&&l.every(Number.isFinite)&&l[0]<l[1])||!Array.isArray(a.xyz_limits?.z)||!a.xyz_limits.z.every(Number.isFinite))return null;
  const project=t=>({...t,x:t.x*this.viewport.w,y:t.y*this.viewport.h}),raw=a.coordinate_space==='robot-mm';
  const route=a.motion_path,motion_path=!raw&&typeof route?.id==='string'&&Array.isArray(route.points)&&route.points.length>=2&&route.points.length<=2048&&route.points.every(p)
   ?{id:route.id,points:route.points.map(project)}:null;
  return {...a,tip:raw?a.tip:project(a.tip),xyz_target:raw?a.xyz_target:project(a.xyz_target),xyz_limits:raw?a.xyz_limits:{x:[0,this.viewport.w],y:[0,this.viewport.h],z:a.xyz_limits.z},motion_path,tags:(a.tags||[]).filter(t=>Number.isFinite(t.x)&&Number.isFinite(t.y)).map(project),markers:(a.markers||[]).filter(t=>Number.isFinite(t.x)&&Number.isFinite(t.y)).map(project),cue:{...a.cue,waypoint:a.cue?.waypoint?project(a.cue.waypoint):null}};
 }
 async activate(active){
  if(this.active&&!active)this.stop('Physical controls deactivated.');this.active=active;this.draw();
  if(!active||this.frame.getAttribute('src')||this.loading||performance.now()<this.retry)return;
  if(!location.pathname.startsWith('/s/'+this.team+'/')){this.error='Physical controls require the local '+this.team+' hub page.';return;}
  this.loading=true;
  try{
   const response=await fetch('/s/'+this.team+'/p/mobile-ltz/api/physical-controller',{cache:'no-store'}),d=await response.json();
   if(!response.ok||d.contract!==this.team+'.robot-controller'||d.version!==1||d.status!=='ready'||d.path!=='/s/'+this.team+'/p/ltx/?ltz=1&mobile=1&bridge=1')throw Error(d.error||this.team+' controller unavailable.');
   this.frame.src=d.path;
  }catch(error){this.error=error.message;this.retry=performance.now()+4000;}
  finally{this.loading=false;}
 }
 command(data){
  if(['stop','suspend','disconnect'].includes(data.action)){this.stop(data.reason);return Promise.resolve({ok:true});}
  if(!this.fresh())return Promise.reject(Error(this.error));
  const payload={...data};
  if(payload.xyz&&this.value?.arm?.coordinate_space!=='robot-mm')payload.xyz={...payload.xyz,x:payload.xyz.x/this.viewport.w,y:payload.xyz.y/this.viewport.h};
  if(payload.action==='cue_waypoint'){const point=payload.point||payload;payload.x=point.x/this.viewport.w;payload.y=point.y/this.viewport.h;delete payload.point;}
  const id=String(++this.counter);
  return new Promise((resolve,reject)=>{
   const expire=()=>{this.diagnostic('controller','command_timeout','Physical controller timed out.',{...this.diagnostics(),action:payload.action});this.pending.delete(id);this.stop('Physical controller command timed out.');reject(Error('Physical controller timed out. Press Connect to resume.'));};
   this.pending.set(id,{resolve,reject,expire,timer:setTimeout(expire,15000),deadline:performance.now()+180000,action:payload.action,session:payload.session});
   this.post({type:'command',id,data:payload});
  });
 }
 stop(reason='Stopped. Connect to resume.'){
  this.post({type:'command',id:String(++this.counter),data:{action:'stop',reason}});
  for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(Error('Physical controls stopped.'));}this.pending.clear();
  if(this.value?.arm)this.value.arm={...this.value.arm,connected:false,session:null,controller_id:null};
 }
 tick(){if(this.active&&!document.hidden)this.post({type:'ping'});this.draw();}
 draw(){
  const g=this.value?.geometry,poly=p=>Array.isArray(p)&&p.length>=3&&p.length<=2000&&p.every(q=>Array.isArray(q)&&q.length===2&&q.every(n=>Number.isFinite(n)&&Math.abs(n)<=4));
  const visible=this.fresh()&&g&&poly(g.boundary)&&Array.isArray(g.excluded)&&g.excluded.length<=2000&&g.excluded.every(poly);
  this.overlay.toggleAttribute('hidden',!visible);if(!visible)return;
  const key=JSON.stringify([g,this.viewport.w,this.viewport.h]);if(key===this.drawKey)return;this.drawKey=key;
  const path=p=>'M'+p.map(q=>(q[0]*this.viewport.w).toFixed(2)+','+(q[1]*this.viewport.h).toFixed(2)).join('L')+'Z';
  this.overlay.setAttribute('viewBox',`0 0 ${this.viewport.w} ${this.viewport.h}`);
  this.overlay.querySelector('[data-reach-shade]').setAttribute('d',path([[0,0],[1,0],[1,1],[0,1]])+path(g.boundary)+g.excluded.map(path).join(''));
  this.overlay.querySelector('[data-reach-line]').setAttribute('d',path(g.boundary));
 }
}
