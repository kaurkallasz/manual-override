/* Run: node tests/mobile_video_smoke.cjs. No camera, browser or robot required. */
const assert=require('node:assert/strict');
const {TurretOverlay}=require('../shared/mobile_ltz/turret-overlay.js');
let now=100,wall=100000,nextURL=0,decodeGate=null;
const urls=new Set(),revoked=[],decoders=[];
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
class MockImage{
 constructor(){this.hidden=false;this.complete=false;this.naturalWidth=0;this.id='';this.alt='';decoders.push(this);}
 set src(v){this._src=v;this.complete=false;this.naturalWidth=0;}
 get src(){return this._src;}
 async decode(){if(decodeGate)await decodeGate.promise;this.complete=true;this.naturalWidth=1280;this.naturalHeight=720;}
 replaceWith(next){assert(next.complete&&next.naturalWidth,'Never attach an undecoded frame');assert.equal(displayed,this);displayed=next;}
 removeAttribute(){this._src='';this.complete=false;this.naturalWidth=0;}
}
const displayed={hidden:true,id:'playfieldVideo',_width:0,_height:0,resizes:0,draws:[],
 get width(){return this._width;},set width(v){this._width=v;this.resizes++;},
 get height(){return this._height;},set height(v){this._height=v;this.resizes++;},
 getContext(type,options){assert.equal(type,'2d');assert.deepEqual(options,{alpha:false,willReadFrequently:true});return {drawImage:image=>{assert(image.complete&&image.naturalWidth,'Only paint fully decoded frames');this.draws.push(image.src);}};},
};
Object.defineProperty(globalThis,'performance',{value:{now:()=>now}});
Date.now=()=>wall;
globalThis.Image=MockImage;
URL.createObjectURL=()=>{const u=`blob:${++nextURL}`;urls.add(u);return u;};
URL.revokeObjectURL=u=>{assert(urls.delete(u),'URL revoked once');revoked.push(u);};
const app={dataset:{}};
globalThis.document={hidden:false,getElementById:id=>{assert.equal(id,'app');return app;}};
const state={virtual_play:false,phase:'running',mobile_camera:{status:'ready',frame_at:wall/1000}};
let notifications=0;const fps=[];
const overlay=Object.assign(Object.create(TurretOverlay.prototype),{
 o:{state:()=>state,fresh:()=>true,frameURL:()=>'/frame',videoChanged:()=>notifications++,onFps:value=>fps.push(value)},
 image:displayed,imageAt:0,frameRequest:null,frameNext:0,draw:()=>{},
});
const ok=()=>({ok:true,headers:{get:()=> 'image/jpeg'},blob:async()=>({})});
globalThis.fetch=async()=>ok();
const advance=ms=>{now+=ms;wall+=ms;state.mobile_camera.frame_at=wall/1000;};
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
(async()=>{
 await overlay.video();assert(overlay.cameraReady());assert.equal(urls.size,0);
 assert.ok(decoders.every(image=>!image.src),'A painted JPEG releases its source decoder before GC');
 const first=displayed,firstURL=first.draws.at(-1);
 advance(160);decodeGate=deferred();const loading=overlay.video();await flush();
 assert.equal(displayed,first);assert.equal(displayed.draws.at(-1),firstURL);assert(overlay.cameraReady(),'Pending decode must not disable aiming or blink');
 await overlay.video();assert.equal(urls.size,1,'Only one pending frame');
 decodeGate.resolve();await loading;decodeGate=null;
 assert.equal(overlay.image,first,'Canvas identity stays fixed');assert.notEqual(displayed.draws.at(-1),firstURL);assert(overlay.cameraReady());assert.equal(displayed.resizes,2,'Same-size updates never clear the canvas');assert.equal(urls.size,0);
 advance(160);globalThis.fetch=async()=>{throw Error('Dropped frame');};
 const good=displayed;await overlay.video();assert.equal(displayed,good);assert(overlay.cameraReady());
 advance(2100);overlay.refreshVideo();assert(!displayed.hidden,'Transport gaps retain the last picture');assert(!overlay.ready(),'Expired video disables aim without another SSE event');
 globalThis.fetch=async()=>ok();await overlay.video();assert(overlay.cameraReady(),'Recovers after a dropped frame');
 advance(160);decodeGate=deferred();const bad=overlay.video();await flush();decodeGate.reject(Error('Invalid JPEG'));await bad;decodeGate=null;
 assert(overlay.cameraReady());assert.equal(urls.size,0,'Decode failures release their URL');
 advance(160);decodeGate=deferred();const late=overlay.video();await flush();state.virtual_play=true;await overlay.video();assert(displayed.hidden);assert.equal(overlay.frameRequest,null);
 state.virtual_play=false;decodeGate.resolve();await late;decodeGate=null;assert(displayed.hidden,'Old decode must not revive after switching modes');assert.equal(urls.size,0);
 await overlay.video();assert(overlay.cameraReady());
 advance(160);decodeGate=deferred();const hidden=overlay.video();await flush();document.hidden=true;overlay.stopVideo();decodeGate.resolve();await hidden;decodeGate=null;
 assert(displayed.hidden);assert.equal(urls.size,0);document.hidden=false;
 await overlay.video();assert(overlay.cameraReady(),'Can resume from pagehide/visibility');
 advance(160);decodeGate=deferred();const slow=overlay.video();await flush();advance(2100);decodeGate.resolve();await slow;decodeGate=null;
 assert(!displayed.hidden,'Slow frames do not blank the last picture');assert(!overlay.cameraReady(),'Slow frame is not assigned a fresh timestamp');assert.equal(urls.size,0);
 state.mobile_camera.frame_at=wall/1000-10;await overlay.video();assert(!overlay.cameraReady(),'Stale tracking still fails closed');
 // A decoder that never finishes cannot hold the request slot or blob forever.
 state.mobile_camera.frame_at=wall/1000;advance(160);decodeGate=deferred();
 const hung=overlay.video();await flush();overlay.frameRequest.abort();await hung;
 assert.equal(overlay.frameRequest,null);assert.equal(urls.size,0);
 decodeGate=null;advance(160);await overlay.video();assert(overlay.cameraReady());
 overlay.stopVideo();assert.equal(urls.size,0);assert(notifications>0);
 assert.equal(fps.at(-1),null,'Stopping video clears the FPS sample');
 fps.length=0;
 for(let i=0;i<5;i++){await overlay.video();advance(200);}
 globalThis.fetch=async()=>{throw Error('Dropped frame');};
 await overlay.video();assert.equal(fps.at(-1),5,'FPS counts completed paints over elapsed time');
 advance(1000);await overlay.video();assert.equal(fps.at(-1),0,'A stalled camera reports zero FPS');
 overlay.stopVideo();assert.equal(fps.at(-1),null);
 state.virtual_play=true;const samples=fps.length;
 await overlay.video();assert.equal(fps.length,samples,'Inactive camera does not clear virtual FPS');
 state.virtual_play=false;globalThis.fetch=async()=>ok();
 await overlay.video();advance(1000);await overlay.video();assert.equal(fps.at(-1),1,'Resume starts a fresh sample');
 document.hidden=true;await overlay.video();assert.equal(fps.at(-1),null,'Hidden page resets camera FPS');
 console.log('PASS: camera FPS sampling, stalls, mode/visibility resets, persistent canvas, cancellation, recovery and URL cleanup');
})().catch(e=>{console.error(e);process.exitCode=1;});
