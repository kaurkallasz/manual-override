/* Read-only presentation of Photon Game's release windows and simulation clock. */
(function(root){
'use strict';
const NS='http://www.w3.org/2000/svg';
const clock=s=>{s=Math.max(0,Math.floor(s));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;};
function progressTone(waves,time,phase){
 const active=phase==='running'&&waves.some(w=>w.state==='spawning');
 const next=waves.filter(w=>w.state==='upcoming').reduce((soonest,w)=>Math.min(soonest,w.start_s),Infinity);
 const remaining=next-time,warning=phase==='running'&&remaining<=30;
 const amount=active?1:warning?Math.min(1,1-remaining/30):0;
 const color=[54,224,124].map((v,i)=>Math.round(v+([245,166,35][i]-v)*amount));
 return {state:active?'spawning':warning?'warning':'clear',color:`rgb(${color.join(', ')})`};
}
function layout(waves,end){
 const lanes=[];
 const bars=waves.map(w=>{let lane=lanes.findIndex(v=>v<=w.start_s);if(lane<0)lane=lanes.length;lanes[lane]=w.end_s;
  return {...w,lane,x:20+960*w.start_s/end,width:Math.max(1,960*(w.end_s-w.start_s)/end)};});
 return {bars,lanes:Math.max(1,lanes.length)};
}
class WaveTimeline{
 constructor(container,{now=()=>performance.now(),raf=fn=>requestAnimationFrame(fn),cancel=id=>cancelAnimationFrame(id)}={}){
  Object.assign(this,{container,now,raf,cancel,frame:null,state:null,connected:true,signature:null,stamp:-Infinity});
  container.classList.add('ltzWaveTimeline');container.hidden=true;
  this.svg=this.node('svg',{viewBox:'0 0 1000 64',role:'img','aria-label':'Wave spawn timeline'});container.append(this.svg);
  this.labels=document.createElement('div');this.labels.className='ltzWaveLabels';this.labels.setAttribute('aria-hidden','true');
  for(const [key,className] of [['waveText','ltzWaveCurrent'],['caption','ltzWaveCaption'],['clockText','ltzWaveClock']]){
   this[key]=document.createElement('span');this[key].className=className;this.labels.append(this[key]);
  }
  container.append(this.labels);
  this.frame=this.raf(()=>this.tick());
 }
 node(tag,attrs={},text){const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!=null)n.textContent=text;return n;}
 update(state){
  const data=state?.wave_timeline;
  if(state?.journey?.phase==='calibration'||state?.status!=='ready'||data?.contract!=='photon.wave-timeline'||data.version!==1||data.status!=='ready'){
   this.container.hidden=true;this.state=null;return;
  }
  if(!Number.isFinite(data.time_s)||!Number.isFinite(data.end_s)||data.end_s<=0||!Array.isArray(data.waves)||data.waves.length>12
    ||data.waves.some(w=>!Number.isInteger(w.wave)||!['start_s','end_s','duration_s'].every(k=>Number.isFinite(w[k])&&w[k]>=0)||w.end_s<w.start_s)){
   this.container.hidden=true;this.state=null;return;
  }
  if(this.state?.run_id===state.run_id&&Number.isFinite(state.server_time)&&state.server_time<this.stamp)return;
  this.state=state;this.data=data;this.received=this.now();this.stamp=state.server_time;this.connected=true;this.container.hidden=false;
  const signature=JSON.stringify([state.run_id,data.end_s,data.waves]);
  if(signature!==this.signature){this.signature=signature;this.draw();}
  this.paint();
 }
 draw(){
  this.svg.replaceChildren();const data=this.data,{bars}=layout(data.waves,data.end_s);
  // The old track was 12 units tall with an 8-unit fill. Both are now 4×
  // thicker, and the bottom aligns with the former wave boxes at y=56.
  this.svg.append(this.node('rect',{x:18,y:8,width:964,height:48,class:'ltzWaveTrack'}));
  for(let i=0;i<80;i++)this.svg.append(this.node('rect',{x:20+i*12,y:16,width:10,height:32,class:'ltzWavePixel'}));
  // Elapsed time is one unbroken fill; only the future track has pixel gaps.
  this.progress=this.node('rect',{x:20,y:16,width:0,height:32,class:'ltzWaveProgress'});
  this.progressShine=this.node('rect',{x:20,y:16,width:0,height:8,class:'ltzWaveProgressShine'});
  this.svg.append(this.progress,this.progressShine);
  for(const w of bars){
   const g=this.node('g',{'data-wave':w.wave,class:`ltzWaveBar ${w.state}`});
   g.append(this.node('title',{},`Wave ${w.wave}: ${clock(w.start_s)}–${clock(w.end_s)} · ${Math.ceil(w.duration_s)}s spawning`));
   // Release windows are marks on the bar's edges, never separate boxes.
   for(const y of [8,52])g.append(this.node('rect',{x:w.x,y,width:w.width,height:4}));
   this.svg.append(g);
  }
  this.head=this.node('g',{class:'ltzWavePlayhead','data-playhead':'true'});
  this.head.append(this.node('line',{x1:0,x2:0,y1:8,y2:56}),this.node('path',{d:'M -5 8 H 5 V 12 H 2 V 15 H -2 V 12 H -5 Z'}));this.svg.append(this.head);
 }

 paint(){
  if(!this.state||this.container.hidden)return;
  const state=this.state,data=this.data,age=Math.max(0,(this.now()-this.received)/1000);
  const stale=!this.connected||(state.phase==='running'&&!state.paused&&age>1.5);
  const moving=state.phase==='running'&&!state.paused&&!stale;
  const time=data.time_s+(moving?Math.min(age,.25):0),width=960*Math.max(0,Math.min(1,time/data.end_s)),x=20+width;
  const tone=progressTone(data.waves,time,state.phase);
  this.progress.setAttribute('width',String(width));this.progressShine.setAttribute('width',String(width));
  this.svg.setAttribute('style',`--ltz-wave-color:${tone.color}`);
  this.container.dataset.tone=tone.state;
  this.head.setAttribute('transform',`translate(${x} 0)`);
  this.container.dataset.time=String(time);this.container.dataset.paused=String(!!state.paused);
  this.clockText.textContent=`${stale?'FEED PAUSED':state.paused?'PAUSED':state.phase==='setup'?'READY':'MATCH'}  ${clock(time)}`;
  const active=data.waves.filter(w=>w.state==='spawning'),next=data.waves.find(w=>w.state==='upcoming');
  let caption=active.length?`Wave ${active.map(w=>w.wave).join(' + ')} spawning`:state.phase==='setup'?'Ready to start':state.phase==='won'?'Match complete':state.phase==='overrun'?'Core lost':state.phase==='aborted'?'Match ended':'Between waves';
  if(next)caption+=`  ·  Wave ${next.wave} in ${clock(Math.max(0,next.start_s-time))}  ·  ${Math.ceil(next.duration_s)}s spawning`;
  else if(!active.length&&state.phase==='running')caption=`All waves released  ·  ${state.active_enemies||0} orcs remaining`;
  if(data.queued_orcs)caption+=`  ·  ${data.queued_orcs} queued`;
  const released=data.waves.filter(w=>w.state==='released'),current=active.at(-1)||released.at(-1);
  this.waveText.textContent=state.phase==='setup'?'PREPARE':`WAVE ${current?.wave||0} / ${data.waves.length}`;
  this.caption.textContent=state.phase==='won'?'MATCH COMPLETE':state.phase==='overrun'?'CORE LOST':state.phase==='aborted'?'MATCH ENDED':
   next?`NEXT ${next.wave} IN ${clock(Math.max(0,next.start_s-time))}`:active.length?'SPAWNING':state.phase==='running'?`${state.active_enemies||0} ORCS LEFT`:'READY';
  this.svg.setAttribute('aria-label',`${this.clockText.textContent}. ${caption}`);
 }
 setConnected(value){this.connected=value;this.paint();}
 tick(){this.paint();this.frame=this.raf(()=>this.tick());}
 destroy(){this.cancel(this.frame);this.frame=null;this.state=null;}
}
root.LTZWaveTimeline=WaveTimeline;
if(typeof module!=='undefined'&&module.exports)module.exports={WaveTimeline,layout,clock,progressTone};
})(typeof window==='undefined'?globalThis:window);
