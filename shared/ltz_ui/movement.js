/* Saved gripper paths and timed orc kills in one rotatable field replay. */
((root)=>{
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colors={green:'#49e59a',purple:'#c48bff'},views=new Map(),mounted=new Map(),floors=new Map();
const defaults=()=>({yaw:-.35,pitch:.66,zoom:1,time:0,speed:50,playing:true,visible:false,green:true,purple:true,last:0});
const clock=t=>`${Math.floor(t/60)}:${Math.floor(t%60).toString().padStart(2,'0')}`;
function html(data,key,heatmap=null,duration=0,resolveAsset=path=>'/s/gamemaster/p/photon-level/assets/'+path){
 const title='<h3>Level replay · 3D</h3>';
 if(!data&&!heatmap)return `<section class="ltzMovement">${title}<p>Movement was not recorded for this level. Kill locations are unavailable.</p></section>`;
 const available=['green','purple'].filter(s=>data?.arms?.[s]?.segments?.length);
 const notices=['green','purple'].map(s=>{const a=data?.arms?.[s];return !a?.segments?.length?`${s==='green'?'Green':'Purple'}: ${a?.error||'No movement recorded'}.`:a.status==='partial'?`${s==='green'?'Green':'Purple'}: gaps in recorded feedback${a.error?' · '+a.error:''}.`:'';}).filter(Boolean);
 if(!available.length&&!heatmap)return `<section class="ltzMovement">${title}<p>No movement was recorded.</p><p>${esc(notices.join(' '))}</p></section>`;
 const scene={...data,kill_heatmap:heatmap,duration_s:Math.max(data?.duration_s||0,Number(duration)||0,heatmap?.timeline?.events?.at(-1)?.[0]||0)};
 if(heatmap?.floor)scene.floor_urls=Object.fromEntries(Object.entries(heatmap.floor.assets).map(([id,path])=>[id,resolveAsset(path)]));
 const max=heatmap?Math.max(0,...heatmap.counts):0,total=heatmap?heatmap.counts.reduce((a,b)=>a+b,0):0;
 return `<section class="ltzMovement" data-movement-key="${esc(key)}" data-movement="${esc(JSON.stringify(scene))}" aria-label="Level replay with robot trails and orc heatmap">
 <div class="ltzHistoryTitle">${title}<span data-move-speed>50× playback</span></div>
 <div class="ltzMovementViewport"><canvas tabindex="0" role="img" aria-label="Rotatable 3D gamefield image with a timed orc kill heatmap and green and purple gripper trails. Drag to rotate, pinch or scroll to zoom. Arrow keys rotate; plus and minus zoom."></canvas></div><p class="ltzMovementHint">Recorded game data · drag to rotate · pinch / scroll to zoom</p><p class="ltzMovementFloorStatus">${heatmap?.floor?'Loading the saved gamefield artwork…':'Gamefield artwork was not saved for this level. Showing its recorded field geometry.'}</p>
 <div class="ltzMovementTools"><button type="button" data-move="reset">Reset View</button><button type="button" data-move="top">Top View</button>${['green','purple'].map(s=>`<button type="button" class="${s}" data-move="${s}" aria-pressed="true" ${available.includes(s)?'':'disabled'}><i></i>${s==='green'?'Green':'Purple'}</button>`).join('')}</div>
 <div class="ltzMovementPlayback"><button type="button" data-move="play" aria-label="Pause level playback">Pause</button><button type="button" data-move="replay">Replay</button><label class="ltzMovementSpeed">Speed<select aria-label="Playback speed"><option value="20">20×</option><option value="50" selected>50×</option><option value="100">100×</option></select></label><label class="ltzMovementTimeline">Level timeline<input type="range" min="0" max="${scene.duration_s}" step="0.1" value="0" aria-label="Level playback timeline"></label><output>0:00 / ${clock(scene.duration_s)}</output></div>
 ${heatmap?`<div class="ltzHeatLegend"><span>Fewer</span><i></i><span>Most · ${max.toLocaleString()} in one area</span></div><p class="ltzMovementHeatStatus"></p><p>${total?`${total.toLocaleString()} orcs mapped. Includes turret, force-field and core-purge kills.`:heatmap.unlocated?'No kill locations available for this level.':'No orcs were killed in this level.'}${heatmap.unlocated?` ${heatmap.unlocated.toLocaleString()} kills have no recorded location.`:''}</p>${heatmap.timeline?'':'<p class="ltzMovementNotice">Kill timing was not recorded. The floor shows the final heatmap throughout playback.</p>'}`:'<p>Kill locations were not recorded for this level.</p>'}
 ${available.length?'<p>Measured gripper paths · height above the calibrated surface in mm. ○ Start · ◇ End.</p>':''}${notices.length?`<p class="ltzMovementNotice">${esc(notices.join(' '))}</p>`:''}${available.some(s=>data.arms[s].truncated)?'<p>Earlier segments were omitted to keep this recording within its size limit.</p>':''}${available.some(s=>data.arms[s].simplified)?'<p>This long recording was simplified for display.</p>':''}
 </section>`;
}
function heatmapAt(heatmap,time){
 if(!heatmap)return {counts:[],unlocated:0};
 if(!heatmap.timeline)return {counts:heatmap.counts,unlocated:heatmap.unlocated};
 const counts=new Array(heatmap.counts.length).fill(0);let unlocated=0;
 for(const [at,cell,count]of heatmap.timeline.events){
  if(at>time)break;
  if(cell===-1)unlocated+=count;else counts[cell]+=count;
 }
 return {counts,unlocated};
}
function floorImage(floor,urls,width,height){
 const key=JSON.stringify([floor,urls,width,height]);
 if(floors.has(key))return floors.get(key);
 const promise=Promise.all(Object.entries(urls).map(([id,url])=>new Promise((resolve,reject)=>{
  const img=new Image(),timer=setTimeout(()=>finish(false),12000);
  function finish(ok){clearTimeout(timer);img.onload=img.onerror=null;ok?resolve([id,img]):reject(Error('Gamefield artwork is unavailable. Showing its recorded field geometry.'));}
  img.onload=()=>finish(true);img.onerror=()=>finish(false);img.src=url;
 }))).then(entries=>{
  const images=new Map(entries),bitmap=document.createElement('canvas'),scale=Math.min(1,1280/Math.max(width,height));
  bitmap.width=Math.max(1,Math.round(width*scale));bitmap.height=Math.max(1,Math.round(height*scale));
  const context=bitmap.getContext('2d');if(!context)throw Error('Gamefield artwork could not be drawn.');
  context.scale(bitmap.width/width,bitmap.height/height);context.fillStyle='#030609';context.fillRect(0,0,width,height);context.imageSmoothingEnabled=false;
  for(const layer of floor.layers){
   context.globalAlpha=layer.opacity;
   for(const item of layer.items){
    const img=images.get(item.asset_id);context.save();context.translate(item.origin_x,item.origin_y);context.rotate(item.rotation_degrees*Math.PI/180);
    const dest=[item.draw_x,item.draw_y,item.width,item.height];
    if(item.source)context.drawImage(img,...item.source,...dest);else context.drawImage(img,...dest);
    context.restore();
   }
  }
  return bitmap;
 }).catch(error=>{if(floors.get(key)===promise)floors.delete(key);throw error;});
 floors.set(key,promise);while(floors.size>4)floors.delete(floors.keys().next().value);
 return promise;
}
function recentKills(heatmap,time,windowSeconds){
 const cells=new Map();
 for(const [at,cell]of heatmap?.timeline?.events||[]){
  if(at>time)break;
  if(cell>=0&&time-at<windowSeconds)cells.set(cell,1-(time-at)/windowSeconds);
 }
 return cells;
}
function timedSegment(points,time){
 const out=[];
 for(const p of points){
  if(p[0]<=time){out.push(p);continue;}
  const previous=out.at(-1);
  if(previous&&p[0]>previous[0]){const t=(time-previous[0])/(p[0]-previous[0]);out.push([time,...p.slice(1).map((v,i)=>previous[i+1]+t*(v-previous[i+1]))]);}
  break;
 }
 return out;
}
function projection(p,view,center){
 const x=p[0]-center[0],y=p[1]-center[1],z=p[2]-center[2];
 const u=Math.cos(view.yaw)*x-Math.sin(view.yaw)*y,v=Math.sin(view.yaw)*x+Math.cos(view.yaw)*y;
 return [u,Math.sin(view.pitch)*v-Math.cos(view.pitch)*z,Math.cos(view.pitch)*v+Math.sin(view.pitch)*z];
}
function mount(container){
 for(const [node,dispose]of mounted)if(!node.isConnected){dispose();mounted.delete(node);}
 for(const section of container.querySelectorAll('[data-movement]')){
  if(mounted.has(section))continue;
  let data;try{data=JSON.parse(section.dataset.movement);}catch{continue;}
  const key=section.dataset.movementKey;
  if(!views.has(key))views.set(key,defaults());
  while(views.size>24)views.delete(views.keys().next().value);
  const view=views.get(key),canvas=section.querySelector('canvas'),ctx=canvas.getContext('2d');
  if(!ctx){section.querySelector('.ltzMovementViewport').textContent='3D drawing is unavailable in this browser.';continue;}
  const abort=new AbortController(),on=(el,type,fn,opts={})=>el.addEventListener(type,fn,{...opts,signal:abort.signal});
  const heatmap=data.kill_heatmap,metric=!!data.field;
  const field=data.field||{width_mm:heatmap.width,height_mm:heatmap.height,core:[heatmap.core[0]/heatmap.width,heatmap.core[1]/heatmap.height]};
  const w=field.width_mm,h=field.height_mm,duration=data.duration_s||0,heatMax=heatmap?Math.max(1,...heatmap.counts):1;
  view.time=Math.min(duration,view.time);
  const all=['green','purple'].flatMap(s=>(data.arms?.[s]?.segments||[]).flat());
  const min=[0,0,0],max=[w,h,metric?100:0];
  for(const p of all)for(let i=0;i<3;i++){min[i]=Math.min(min[i],p[i+1]);max[i]=Math.max(max[i],p[i+1]);}
  const zmax=metric?Math.ceil(Math.max(100,max[2])/100)*100:0;
  const center=min.map((v,i)=>(v+max[i])/2),bounds=[];
  for(const x of [min[0],max[0]])for(const y of [min[1],max[1]])for(const z of [min[2],Math.max(max[2],zmax)])bounds.push([x,y,z]);
  const slider=section.querySelector('input'),output=section.querySelector('output'),play=section.querySelector('[data-move="play"]'),speed=section.querySelector('select');
  let frame=0,dead=false,width=1,height=1,bitmap=null,floorState=heatmap?.floor?'loading':'unavailable';
  const pointers=new Map();let gesture=null;
  function controls(){
   speed.value=String(view.speed);section.querySelector('[data-move-speed]').textContent=`${view.speed}× playback`;
   slider.value=view.time;output.textContent=`${clock(view.time)} / ${clock(duration)}`;
   play.textContent=view.playing?'Pause':'Play';play.setAttribute('aria-label',(view.playing?'Pause':'Play')+' level playback');
   for(const s of ['green','purple'])section.querySelector(`[data-move="${s}"]`).setAttribute('aria-pressed',String(view[s]));
  }
  function draw(){
   const ratio=Math.min(2,root.devicePixelRatio||1),rect=canvas.getBoundingClientRect();
   width=Math.max(1,rect.width);height=Math.max(1,rect.height);
   if(canvas.width!==Math.round(width*ratio)||canvas.height!==Math.round(height*ratio)){canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);}
   ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
   const projected=bounds.map(p=>projection(p,view,center)),xs=projected.map(p=>p[0]),ys=projected.map(p=>p[1]);
   const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
   const scale=Math.min(Math.max(1,width-32)/Math.max(1,right-left),Math.max(1,height-60)/Math.max(1,bottom-top))*view.zoom;
   const at=p=>{const q=projection(p,view,center);return [width/2+(q[0]-(left+right)/2)*scale,height/2+(q[1]-(top+bottom)/2)*scale,q[2]];};
   const lines=[],labels=[];
   const line=(a,b,color,size=1,dash=[])=>{const p=at(a),q=at(b);lines.push({p,q,color,size,dash,depth:(p[2]+q[2])/2});};
   const polygon=(points,color)=>{ctx.fillStyle=color;ctx.beginPath();points.map(at).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill();};
   const corners=[[0,0,0],[w,0,0],[w,h,0],[0,h,0]];
   polygon(corners,'#10232e');
   if(bitmap){
    const [a,b,,d]=corners.map(at);ctx.save();
    ctx.transform((b[0]-a[0])/bitmap.width,(b[1]-a[1])/bitmap.width,(d[0]-a[0])/bitmap.height,(d[1]-a[1])/bitmap.height,a[0],a[1]);
    ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(bitmap,0,0);ctx.restore();
   }
   canvas.dataset.floor=floorState;
   const heat=heatmapAt(heatmap,view.time);
   if(heatmap){
    ctx.save();ctx.beginPath();corners.map(at).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.clip();
    const cw=w/heatmap.columns,ch=h/heatmap.rows;
    ctx.save();ctx.globalAlpha=bitmap ? .68 : 1;
    heat.counts.forEach((count,i)=>{if(!count)return;const x=i%heatmap.columns*cw,y=Math.floor(i/heatmap.columns)*ch,k=count/heatMax;polygon([[x,y,0],[x+cw,y,0],[x+cw,y+ch,0],[x,y+ch,0]],`hsl(${48-48*k} 94% ${28+34*k}%)`);});
    ctx.restore();
    const flashes=recentKills(heatmap,view.time,Math.max(2,view.speed*.35));
    for(const [cell,fade]of flashes){
     const x=(cell%heatmap.columns+.5)*cw,y=(Math.floor(cell/heatmap.columns)+.5)*ch;
     const r=Math.max(cw,ch)*(.45+(1-fade)*.7),points=[];
     for(let i=0;i<24;i++)points.push([x+Math.cos(i*Math.PI/12)*r,y+Math.sin(i*Math.PI/12)*r,0]);
     ctx.save();ctx.globalAlpha=fade*.65;polygon(points,'#ffe8b3');ctx.restore();
    }
    ctx.restore();canvas.dataset.killFlashes=String(flashes.size);
    const ground=([x,y])=>[x/heatmap.width*w,y/heatmap.height*h,0];
    if(!bitmap)for(const road of heatmap.roads||[])for(let i=1;i<road.length;i++)line(ground(road[i-1]),ground(road[i]),'#7694a577',2);
    if(!bitmap)for(const marker of heatmap.markers||[]){const p=at(ground(marker));ctx.fillStyle='#b6ced9';ctx.fillRect(p[0]-1.5,p[1]-1.5,3,3);}
    const mapped=heat.counts.reduce((a,b)=>a+b,0);
    section.querySelector('.ltzMovementHeatStatus').textContent=`${heatmap.timeline?'At '+clock(view.time):'Final heatmap'} · ${mapped.toLocaleString()} kills shown on the floor${heat.unlocated?' · '+heat.unlocated.toLocaleString()+' without a location':''}`;
    canvas.dataset.heatKills=String(mapped);canvas.dataset.heatUnlocated=String(heat.unlocated);
   }
   if(!bitmap)for(let i=0;i<=10;i++){line([w*i/10,0,0],[w*i/10,h,0],'#46627344');line([0,h*i/10,0],[w,h*i/10,0],'#46627344');}
   for(let i=0;i<4;i++)line(corners[i],corners[(i+1)%4],'#819cac',1.5);
   if(metric){
    line([0,0,0],[0,0,zmax],'#abc5d3',1,[3,4]);
    labels.push({p:at([0,0,zmax]),text:`Height · ${zmax} mm`,color:'#d2e1e8'});
   }
   const c=[field.core[0]*w,field.core[1]*h,0];labels.push({p:at(c),text:'Center',color:'#d2e1e8',marker:'center'});
   labels.push({p:at([w/2,0,0]),text:'Top of playfield',color:'#8da9ba'});
   const markers=[];
   for(const side of ['green','purple']){
    if(!view[side])continue;
    const segments=data.arms?.[side]?.segments||[];
    for(const original of segments){
     const points=timedSegment(original,view.time);
     for(let i=1;i<points.length;i++)line(points[i-1].slice(1),points[i].slice(1),colors[side],2.3);
    }
    const first=segments[0]?.[0],last=segments.at(-1)?.at(-1);
    if(first&&view.time>=first[0])markers.push({p:at(first.slice(1)),color:colors[side],kind:'start'});
    if(last&&view.time>=last[0]&&view.time>=duration)markers.push({p:at(last.slice(1)),color:colors[side],kind:'end'});
    // Only show a moving tip inside an observed segment; gaps stay blank.
    for(const segment of segments){
     if(segment.length&&view.time>=segment[0][0]&&view.time<=segment.at(-1)[0]){
      const p=timedSegment(segment,view.time).at(-1);if(p)markers.push({p:at(p.slice(1)),color:colors[side],kind:'tip'});
     }
    }
   }
   ctx.lineCap='round';ctx.lineJoin='round';
   for(const l of lines.sort((a,b)=>a.depth-b.depth)){ctx.strokeStyle=l.color;ctx.lineWidth=l.size;ctx.setLineDash(l.dash);ctx.beginPath();ctx.moveTo(l.p[0],l.p[1]);ctx.lineTo(l.q[0],l.q[1]);ctx.stroke();}ctx.setLineDash([]);
   for(const m of markers){const[x,y]=m.p;ctx.strokeStyle=m.color;ctx.fillStyle=m.kind==='tip'?m.color:'#101e29';ctx.lineWidth=2;ctx.beginPath();if(m.kind==='end'){ctx.moveTo(x,y-6);ctx.lineTo(x+6,y);ctx.lineTo(x,y+6);ctx.lineTo(x-6,y);ctx.closePath();}else ctx.arc(x,y,m.kind==='tip'?4:5,0,Math.PI*2);ctx.fill();ctx.stroke();}
   ctx.font='11px system-ui';ctx.textAlign='center';
   for(const l of labels){ctx.fillStyle=l.color;const half=ctx.measureText(l.text).width/2;ctx.fillText(l.text,Math.max(half+8,Math.min(width-half-8,l.p[0])),Math.max(16,Math.min(height-28,l.p[1]-9)));if(l.marker){ctx.beginPath();ctx.arc(l.p[0],l.p[1],3,0,Math.PI*2);ctx.fill();}}
   canvas.dataset.view=JSON.stringify([view.yaw,view.pitch,view.zoom]);canvas.dataset.time=String(view.time);controls();
  }
  const canPlay=()=>view.playing&&view.visible&&!document.hidden&&floorState!=='loading';
  function tick(now){
   frame=0;if(dead||!section.isConnected)return;
   if(canPlay()){
    if(view.last)view.time=Math.min(duration,view.time+Math.max(0,now-view.last)/1000*view.speed);
    view.last=now;
    if(view.time>=duration){view.playing=false;view.last=0;}
    draw();
   }else view.last=0;
   if(canPlay())frame=requestAnimationFrame(tick);
  }
  function render(){
   draw();
   if(canPlay()){
    // Anchor starts and speed changes immediately, including between frames.
    if(!view.last)view.last=performance.now();
    if(!frame)frame=requestAnimationFrame(tick);
   }
  }
  function pause(){view.playing=false;view.last=0;}
  on(section,'click',e=>{
   const button=e.target.closest('[data-move]');if(!button)return;
   const action=button.dataset.move;
   if(action==='reset'){Object.assign(view,{yaw:-.35,pitch:.66,zoom:1});}
   if(action==='top'){Object.assign(view,{yaw:0,pitch:Math.PI/2,zoom:1});}
   if(action==='green'||action==='purple')view[action]=!view[action];
   if(action==='play'){if(view.time>=duration)view.time=0;view.playing=!view.playing;view.last=0;}
   if(action==='replay'){view.time=0;view.playing=true;view.last=0;}
   render();
  });
  on(speed,'change',()=>{const value=Number(speed.value);if([20,50,100].includes(value)){view.speed=value;view.last=0;render();}});
  on(slider,'input',()=>{pause();view.time=Number(slider.value);render();});
  function geometry(){const p=[...pointers.values()];return p.length>=2?{distance:Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y),x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2}:p[0];}
  const zoom=amount=>view.zoom=Math.max(.35,Math.min(4,amount));
  on(canvas,'pointerdown',e=>{if(e.button!==0)return;e.preventDefault();canvas.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});gesture=geometry();});
  on(canvas,'pointermove',e=>{
   if(!pointers.has(e.pointerId))return;e.preventDefault();pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});const next=geometry();
   if(next.distance&&gesture?.distance)zoom(view.zoom*next.distance/gesture.distance);
   else if(gesture){view.yaw+=(next.x-gesture.x)*.008;view.pitch=Math.max(.08,Math.min(Math.PI/2,view.pitch+(next.y-gesture.y)*.008));}
   gesture=next;render();
  });
  for(const event of ['pointerup','pointercancel','lostpointercapture'])on(canvas,event,e=>{pointers.delete(e.pointerId);gesture=geometry();});
  on(canvas,'wheel',e=>{e.preventDefault();zoom(view.zoom*Math.exp(-e.deltaY*.001));render();},{passive:false});
  on(canvas,'keydown',e=>{
   const actions={ArrowLeft:()=>view.yaw-=.12,ArrowRight:()=>view.yaw+=.12,ArrowUp:()=>view.pitch=Math.min(Math.PI/2,view.pitch+.12),ArrowDown:()=>view.pitch=Math.max(.08,view.pitch-.12),'+':()=>zoom(view.zoom*1.1),'=':()=>zoom(view.zoom*1.1),'-':()=>zoom(view.zoom/1.1)};
   if(actions[e.key]){e.preventDefault();actions[e.key]();render();}
  });
  on(document,'visibilitychange',()=>{view.last=0;render();});
  const resize=new ResizeObserver(render);resize.observe(canvas);
  const intersection=new IntersectionObserver(entries=>{view.visible=entries[0].isIntersecting;view.last=0;render();},{threshold:.1});intersection.observe(canvas);
  mounted.set(section,()=>{dead=true;abort.abort();resize.disconnect();intersection.disconnect();cancelAnimationFrame(frame);view.last=0;});
  render();
  if(heatmap?.floor&&data.floor_urls){
   floorImage(heatmap.floor,data.floor_urls,heatmap.width,heatmap.height).then(image=>{
    if(dead)return;bitmap=image;floorState='ready';section.querySelector('.ltzMovementFloorStatus').textContent='Saved gamefield · kills and arm trails share the level timeline';render();
   }).catch(error=>{if(dead)return;section.querySelector('.ltzMovementFloorStatus').textContent=error.message;floorState='unavailable';render();});
  }
 }
}
// Endscreen DOM is replaced by SSE updates; release detached observers immediately.
if(root.MutationObserver&&root.document){const cleanup=new root.MutationObserver(()=>{for(const[node,dispose]of mounted)if(!node.isConnected){dispose();mounted.delete(node);}});cleanup.observe(document.documentElement,{childList:true,subtree:true});}
root.LTZMovement={html,mount};
if(typeof module!=='undefined')module.exports={html,timedSegment,projection,heatmapAt,recentKills};
})(typeof window==='undefined'?globalThis:window);
