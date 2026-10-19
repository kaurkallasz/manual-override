(function(root){
'use strict';
// Read-only inset. Availability travels with game SSE; JPEG loads never gate play.
class MobileMcam1 {
 constructor(canvas,url){
  this.canvas=canvas;this.url=url;this.expires=0;this.next=0;this.pending=null;this.dimensions=null;
  this.layoutDirty=true;
  const invalidate=()=>{this.layoutDirty=true;},app=canvas.parentElement;
  // Camera frames do not change the layout. Re-measure only after a panel or
  // viewport changes, instead of forcing layout twice per JPEG.
  this.resizeObserver=new ResizeObserver(invalidate);
  for(const el of [app,...app.querySelectorAll('.connectionControls,.zoom,.connectionButtons,.playerLog,.xyzHeight,.leftControls,.jointControls,.xyzControls,.telemetry,#cuePanel,.xyzYControl')])this.resizeObserver.observe(el);
  this.layoutObserver=new MutationObserver(invalidate);
  this.layoutObserver.observe(app,{attributes:true,attributeFilter:['data-control-mode','class']});
  this.layoutObserver.observe(document.body,{attributes:true,attributeFilter:['class']});
  const cue=app.querySelector('#cuePanel');
  if(cue)this.layoutObserver.observe(cue,{attributes:true,attributeFilter:['data-minimized','hidden']});
 }
 update(value){
  const age=value?.server_time-value?.captured_at;
  if(value?.contract!=='mobile.mcam1'||value.version!==1||value.status!=='ready'
    ||!Number.isFinite(age)||age < -1||age>1.5||value.max_age_s!==1.5
    ||![value.width,value.height].every(n=>Number.isInteger(n)&&n>0&&n<=4096)){
   this.expires=0;this.stop();return;
  }
  const dimensions=[value.width,value.height];
  if(this.dimensions?.some((n,i)=>n!==dimensions[i]))this.stop();
  this.dimensions=dimensions;this.expires=performance.now()+(1.5-Math.max(0,age))*1000;
 }
 stop(){
  this.pending?.abort();this.pending=null;
  if(this.canvas.hidden)return;
  this.canvas.hidden=true;this.layoutDirty=true;
  this.canvas.parentElement.style.removeProperty('--mcam1-log-width');
  this.canvas.parentElement.style.removeProperty('--mcam1-log-top');
 }
 layout(){
  if(this.canvas.hidden||!this.layoutDirty)return;
  this.layoutDirty=false;
  const app=this.canvas.parentElement,box=app.getBoundingClientRect();
  const visible=selector=>[...app.querySelectorAll(selector)].filter(el=>el.getClientRects().length).map(el=>el.getBoundingClientRect());
  const connection=visible('.connectionControls')[0];
  // Use layout positions so Cue's slide-in animation cannot push the inset
  // temporarily over the panel while it is entering.
  const controls=[...app.querySelectorAll('#cuePanel,.jointControls,.xyzYControl')]
   .filter(el=>el.getClientRects().length&&el.offsetLeft>box.width/2);
  const top=(connection?.top??box.top+64)-box.top;
  const right=controls.length?Math.min(...controls.map(el=>el.offsetLeft))-8:box.width-14;
  // Leave the existing touch controls clear on narrow phones. Never enlarge
  // beyond half the source dimensions, and keep the source aspect ratio.
  let left=8,maxHeight=box.height-top-8;
  for(const r of visible('.zoom,.connectionButtons,.xyzHeight,.leftControls,.jointControls,.xyzControls,.telemetry')){
   if(r.bottom<=box.top+top||r.left>=box.left+right)continue;
   if(r.top<=box.top+top)left=Math.max(left,r.right-box.left+8);
   else if(r.right>box.left+right-this.canvas.width)maxHeight=Math.min(maxHeight,r.top-box.top-top-8);
  }
  const scale=Math.max(0,Math.min(1,(right-left)/this.canvas.width,maxHeight/this.canvas.height));
  this.canvas.style.width=this.canvas.width*scale+'px';
  this.canvas.style.height=this.canvas.height*scale+'px';
  this.canvas.style.left=right-this.canvas.width*scale+'px';
  this.canvas.style.top=top+'px';
  const logElement=app.querySelector('.playerLog'),log=logElement?.getBoundingClientRect();
  const leftEdge=box.left+right-this.canvas.width*scale;
  if(log&&getComputedStyle(logElement).position==='absolute'&&leftEdge-log.left<88){
   app.style.setProperty('--mcam1-log-top',this.canvas.height*scale+8+'px');
   app.style.removeProperty('--mcam1-log-width');
  }else{
   app.style.removeProperty('--mcam1-log-top');
   if(log&&log.top<box.top+top+this.canvas.height*scale&&log.bottom>box.top+top&&log.left<leftEdge)
    app.style.setProperty('--mcam1-log-width',Math.max(0,leftEdge-log.left-8)+'px');
   else app.style.removeProperty('--mcam1-log-width');
  }
 }
 tick(){
  const now=performance.now();
  if(document.hidden||now>=this.expires){this.stop();return;}
  this.layout();
  if(!this.pending&&now>=this.next)this.frame();
 }
 async frame(){
  const controller=new AbortController();this.pending=controller;
  const timeout=setTimeout(()=>controller.abort(),1200);
  let image;
  try{
   const response=await fetch(this.url(),{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(!response.ok||!response.headers.get('Content-Type')?.startsWith('image/jpeg'))throw Error('MCAM1 unavailable');
   image=await createImageBitmap(await response.blob());
   if(this.pending!==controller||controller.signal.aborted||document.hidden||performance.now()>=this.expires)return;
   if(image.width!==this.dimensions[0]||image.height!==this.dimensions[1])throw Error('MCAM1 mode changed');
   const canvas=this.canvas,width=Math.round(image.width*.5),height=Math.round(image.height*.5);
   if(canvas.hidden||canvas.width!==width||canvas.height!==height)this.layoutDirty=true;
   if(canvas.width!==width)canvas.width=width;
   if(canvas.height!==height)canvas.height=height;
   // Match the main camera's software-backed surface: repeated accelerated
   // canvas uploads can exhaust iPhone WebKit's native rendering memory.
   canvas.getContext('2d',{alpha:false,willReadFrequently:true}).drawImage(image,0,0,width,height);
   canvas.hidden=false;this.layout();this.next=performance.now()+50;
  }catch{
   if(this.pending===controller){this.stop();this.next=performance.now()+1000;}
  }finally{
   clearTimeout(timeout);image?.close();
   if(this.pending===controller)this.pending=null;
  }
 }
}
root.MobileMcam1=MobileMcam1;
})(window);
