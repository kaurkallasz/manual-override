/* Passive, bounded delay.analysis v1 client. No timers or uploads while off. */
(function(root){
'use strict';
class MobileDelayTrace {
 constructor({url,team,context=()=>({})}){
  Object.assign(this,{url,team,context});this.active=false;this.revision=-1;this.capture=null;this.queue=[];this.dropped=0;this.busy=false;this.timer=null;this.frame=null;this.observer=null;this.until=0;
  this.clientId=Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
 }
 configure(control){
  if(control?.contract!=='delay.analysis'||control.version!==1||!Number.isInteger(control.revision)||control.revision<this.revision)return;
  if(control.recording&&typeof control.capture_id!=='string')return;
  const changed=this.capture!==control.capture_id;
  this.revision=control.revision;this.capture=control.capture_id;
  if(!control.recording){this.stop();return;}
  if(changed){this.queue=[];this.dropped=0;this.lastReceive=null;}
  this.until=performance.now()+Math.min(4000,Math.max(500,control.lease_ms||4000));
  if(this.active)return;
  this.active=true;this.lastTick=performance.now();this.lastFlush=0;this.lastFrame=null;
  this.timer=setInterval(()=>{
   const now=performance.now();if(now>this.until){this.stop();return;}
   this.record('browser.event_loop_lag',this.lastTick+100,Math.max(0,now-this.lastTick-100));this.lastTick=now;
   if(now-this.lastFlush>=500){this.lastFlush=now;this.flush();}
  },100);
  const frame=()=>{if(!this.active)return;const now=performance.now();if(this.lastFrame!=null)this.record('browser.frame_gap',this.lastFrame,now-this.lastFrame);this.lastFrame=now;this.frame=requestAnimationFrame(frame);};
  this.frame=requestAnimationFrame(frame);
  if(typeof PerformanceObserver!=='undefined'&&PerformanceObserver.supportedEntryTypes?.includes('longtask')){
   try{this.observer=new PerformanceObserver(list=>{for(const e of list.getEntries())this.record('browser.long_task',e.startTime,e.duration);});this.observer.observe({type:'longtask',buffered:false});}catch{this.observer=null;}
  }
  this.flush();
 }
 stop(){
  const was=this.active;this.active=false;clearInterval(this.timer);cancelAnimationFrame(this.frame);this.timer=this.frame=null;
  this.observer?.disconnect();this.observer=null;const finalEvents=this.queue.splice(0,100);this.dropped+=this.queue.length;this.queue=[];this.controller?.abort();this.controller=null;
  if(was)this.sendAcknowledgement(finalEvents);
 }
 begin(){return this.active?{at:performance.now(),capture:this.capture}:null;}
 end(name,token){if(token&&token.capture===this.capture)this.record(name,token.at,performance.now()-token.at);}
 record(name,start,duration,extra={}){
  if(!this.active||performance.now()>this.until||!Number.isFinite(duration)||duration<0)return;
  if(this.queue.length>=512){this.dropped++;return;}
  const context=this.context()||{};
  this.queue.push({name,start_ms:start,duration_ms:duration,sequence:context.sequence,run_id:context.run_id,hidden:document.hidden,...extra});
 }
 receive(value){
  const state=value?.contract==='hub.live'?value.state:value;this.configure(state?.delay_analysis);
  if(!this.active)return;
  const now=performance.now();if(this.lastReceive!=null)this.record('browser.receive_gap',this.lastReceive,now-this.lastReceive,{sequence:state?.delivery?.sequence});this.lastReceive=now;
  const gateway=state?.delivery?.delay_gateway;
  if(gateway&&gateway.capture_id===this.capture){
   for(const [key,name] of [['receive_gap_ms','gateway.receive_gap'],['parse_ms','gateway.parse'],['queue_ms','gateway.queue']]){
    if(Number.isFinite(gateway[key])&&gateway[key]>=0)this.record(name,now,gateway[key],{sequence:state.delivery.sequence});
   }
  }
 }
 payload(events){return {contract:'delay.analysis',version:1,capture_id:this.capture,revision:this.revision,client_id:this.clientId,recording:this.active,dropped:this.dropped,events};}
 async sendAcknowledgement(events=[]){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),2000);
  try{await fetch(this.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(this.payload(events)),credentials:'same-origin',signal:controller.signal});}catch{}finally{clearTimeout(timer);}
 }
 async flush(){
  if(!this.active||this.busy)return;this.busy=true;
  const controller=new AbortController();this.controller=controller;
  const timer=setTimeout(()=>controller.abort(),2000),events=this.queue.splice(0,100),capture=this.capture;
  try{
   const response=await fetch(this.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(this.payload(events)),credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(!response.ok)throw Error('Diagnostic batch rejected');
   const control=await response.json();if(this.capture===capture)this.configure(control);
  }catch{if(this.capture===capture)this.dropped+=events.length;}finally{clearTimeout(timer);if(this.controller===controller)this.controller=null;this.busy=false;}
 }
}
root.MobileDelayTrace=MobileDelayTrace;
if(typeof module!=='undefined')module.exports=MobileDelayTrace;
})(typeof window==='undefined'?globalThis:window);
