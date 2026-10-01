(function(root){
'use strict';
// Read text first: Safari's Response.json() hides malformed/HTML proxy
// responses behind the unhelpful "expected pattern" DOM exception.
async function readJson(response,label='Gamemaster'){
  const status=response.status;
  const suffix=status>=400?` (HTTP ${status})`:'';
  let text;
  try{text=await response.text();}
  catch{throw Error(`${label} response was interrupted. Check the connection and try again.`);}
  let value;
  try{value=JSON.parse(text);}
  catch{throw Error(`${label} returned an invalid response${suffix}. Check that the local game and relay are running.`);}
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error(`${label} returned an invalid response${suffix}.`);
  if(!response.ok||value.ok===false)throw Error(value.error||`${label} is unavailable${suffix}.`);
  return value;
}
// One owner for retries. Close EventSource before scheduling our retry, so
// native retries cannot race the watchdog or visibility changes.
class FetchEventSource {
  constructor(url){this.controller=new AbortController();this.listeners={};this.closed=false;queueMicrotask(()=>this.read(url));}
  addEventListener(name,callback){this.listeners[name]=callback;}
  close(){this.closed=true;this.controller.abort();}
  async read(url){
    try{
      const response=await fetch(url,{headers:{Accept:'text/event-stream','ngrok-skip-browser-warning':'1'},credentials:'omit',mode:'cors',cache:'no-store',signal:this.controller.signal});
      if(!response.ok||!response.headers.get('Content-Type')?.includes('text/event-stream')||!response.body)throw Error('Live stream unavailable');
      const reader=response.body.getReader(),decoder=new TextDecoder();
      let buffer='',event='message',data=[],eventBytes=0;
      while(!this.closed){
        const chunk=await reader.read();if(chunk.done)break;
        buffer+=decoder.decode(chunk.value,{stream:true});
        if(buffer.length>8*1024*1024)throw Error('Live frame too large');
        let end;
        while((end=buffer.indexOf('\n'))>=0&&!this.closed){
          const line=buffer.slice(0,end).replace(/\r$/,'');buffer=buffer.slice(end+1);
          if(!line){
            if(data.length){const callback=event==='message'?this.onmessage:this.listeners[event];callback?.({data:data.join('\n')});}
            event='message';data=[];eventBytes=0;
          }else if(line.startsWith('data:')){
            const text=line.slice(5).replace(/^ /,'');data.push(text);eventBytes+=text.length;
            if(eventBytes>8*1024*1024)throw Error('Live frame too large');
          }else if(line.startsWith('event:'))event=line.slice(6).trim();
        }
      }
      // Incomplete tail is discarded; the retry receives a new full snapshot.
      if(!this.closed)this.onerror?.();
    }catch{if(!this.closed)this.onerror?.();}
  }
}
class LiveFeed {
  constructor({url,receive,recover,onError=()=>{},directSource=FetchEventSource}){Object.assign(this,{url,receive,recover,onError,directSource});this.fallbackUrl=url;this.directUntil=0;this.directCooldown=0;this.active=false;this.source=null;this.lastEvent=0;this.lastAttempt=0;this.retryAt=0;this.nextRecovery=0;this.failures=0;}
  offer(value){
    if(value?.contract!=='mobile.stream'||value.version!==1||!Number.isFinite(value.ttl_s)||value.ttl_s<10||value.ttl_s>600||performance.now()<this.directCooldown)return false;
    let url;try{url=new URL(value.url);}catch{return false;}
    if(url.protocol!=='https:'||url.username||url.password||url.pathname!=='/live/events'||!url.searchParams.get('token'))return false;
    this.directUntil=performance.now()+value.ttl_s*1000;
    if(this.url!==url.href){this.source?.close();this.source=null;this.url=url.href;this.retryAt=0;this.failures=0;if(this.active)this.open();}
    return true;
  }
  start(){if(this.active)return;this.active=true;this.open();}
  stop(){this.active=false;this.source?.close();this.source=null;this.retryAt=0;}
  retry(message){
    this.source?.close();this.source=null;
    this.retryAt=performance.now()+Math.min(8000,500*2**Math.min(this.failures++,4));
    if(this.url!==this.fallbackUrl&&this.failures>=2){this.url=this.fallbackUrl;this.directUntil=0;this.directCooldown=performance.now()+60000;}
    this.onError(message);
  }
  open(){
    if(!this.active||this.source)return;
    this.lastAttempt=performance.now();
    try{
      const Source=this.url===this.fallbackUrl?EventSource:this.directSource;
      const source=new Source(this.url);this.source=source;
      const receive=(event,partial)=>{
        if(this.source!==source)return;
        try{this.receive(JSON.parse(event.data),partial);this.lastEvent=performance.now();this.failures=0;}
        catch{this.retry('Live update interrupted. Reconnecting…');}
      };
      source.onmessage=e=>receive(e,false);
      source.addEventListener('update',e=>receive(e,true));
      source.onerror=()=>{if(this.source===source)this.retry('Reconnecting to live game…');};
    }catch{this.retry('Live stream unavailable. Reconnecting…');}
  }
  tick(stale=false){
    if(!this.active)return;
    const now=performance.now();
    if(this.url===this.fallbackUrl&&this.directCooldown>0&&now>=this.directCooldown&&now>=this.nextRecovery){this.nextRecovery=now+5000;this.recover();}
    if(this.url!==this.fallbackUrl&&now>this.directUntil){this.source?.close();this.source=null;this.url=this.fallbackUrl;this.directUntil=0;this.retryAt=now;}
    if(this.url!==this.fallbackUrl&&now>this.directUntil-60000&&now>=this.nextRecovery){this.nextRecovery=now+5000;this.recover();}
    if(this.source&&now-Math.max(this.lastEvent,this.lastAttempt)>12000)this.retry('Live stream stalled. Reconnecting…');
    if(!this.source&&now>=this.retryAt)this.open();
    if((stale||now-this.lastEvent>2500)&&now>=this.nextRecovery){this.nextRecovery=now+2000;this.recover();}
  }
}
root.MobileNetwork={readJson,LiveFeed,FetchEventSource};
if(typeof module!=='undefined')module.exports=root.MobileNetwork;
})(typeof window==='undefined'?globalThis:window);
