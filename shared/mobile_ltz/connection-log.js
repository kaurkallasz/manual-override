/* Diagnostics never use the command queue and never replay control commands. */
class MobileConnectionLog {
 constructor({url,team,context=()=>({})}){
  Object.assign(this,{url,team,context});this.queue=[];this.busy=false;this.timer=null;this.last=new Map();
  this.prefix='mobile-ltz:connection-log:'+team+':';
  this.identity=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
  this.pageId=this.identity();this.key=this.prefix+this.pageId;
  try{
   // Recover a refreshed/closed tab's unsent evidence. Bound origin storage too.
   const keys=Object.keys(localStorage).filter(k=>k.startsWith(this.prefix));
   for(const key of keys.slice(-8)){
    const rows=JSON.parse(localStorage.getItem(key)||'[]');
    if(Array.isArray(rows))for(const row of rows.slice(-64))if(row?.version===1&&typeof row.id==='string'&&Date.now()/1000-row.client_at<172800)this.queue.push(row);
   }
   this.queue=this.queue.slice(-64);
   if(this.persist())for(const key of keys)if(key!==this.key)localStorage.removeItem(key);
  }catch{}
  window.addEventListener('online',()=>this.schedule(0));
  window.addEventListener('pagehide',()=>{this.persist();this.flush();});
  this.schedule(1000);
 }
 record(source,event,reason='',context={}){
  try{
   const key=source+':'+event+':'+reason,now=Date.now();
   if(now-(this.last.get(key)||0)<3000)return;
   this.last.set(key,now);if(this.last.size>100)this.last.delete(this.last.keys().next().value);
   const clean=value=>String(value).replace(/https?:\/\/\S+/g,'[url]').replace(/\b(?:password|token|authorization|cookie|session)\s*[:=]\s*\S+/gi,'[credential]').replace(/\b[a-f0-9]{32,}\b/gi,'[id]').slice(0,240);
   const details={...this.context(),...Object.fromEntries(Object.entries(context||{}).filter(([,v])=>v!=null)),page_id:this.pageId,hidden:document.hidden,focused:document.hasFocus(),online:navigator.onLine};
   for(const key of ['game_error','robot_error'])if(details[key]!=null)details[key]=clean(details[key]);
   this.queue.push({version:1,id:this.identity(),source,event,reason:clean(reason),client_at:now/1000,
    context:details});
   if(this.queue.length>64)this.queue.splice(0,this.queue.length-64);
   // Storage/network work is deferred so the caller can issue its Stop now.
   this.schedule(0);
  }catch{} // A diagnostic must never break a safety/control handler.
 }
 persist(){try{localStorage.setItem(this.key,JSON.stringify(this.queue));return true;}catch{return false;}}
 schedule(delay){clearTimeout(this.timer);this.timer=setTimeout(()=>{this.persist();this.flush();},delay);}
 async flush(){
  if(this.busy||!this.queue.length)return;
  this.busy=true;const row=this.queue[0],controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
  let retry=5000;
  try{
   const response=await fetch(this.url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(row),signal:controller.signal,keepalive:true,cache:'no-store'});
   const result=response.ok?await response.json():null;
   if(response.ok&&result?.ok===true||[400,413,415].includes(response.status)){
    this.queue=this.queue.filter(item=>item.id!==row.id);retry=100;
   }
  }catch{}finally{
   clearTimeout(timer);this.busy=false;this.persist();if(this.queue.length)this.schedule(retry);
  }
 }
}
