const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(){
 let now=0,id=0,control={contract:'delay.analysis',version:1,capture_id:'a'.repeat(32),revision:1,recording:true,lease_ms:4000};
 const intervals=new Map(),frames=new Map(),uploads=[];
 const sandbox={crypto:require('node:crypto').webcrypto,performance:{now:()=>now},document:{hidden:false},AbortController,
  setInterval:fn=>{intervals.set(++id,fn);return id;},clearInterval:key=>intervals.delete(key),
  requestAnimationFrame:fn=>{frames.set(++id,fn);return id;},cancelAnimationFrame:key=>frames.delete(key),
  setTimeout:()=>++id,clearTimeout:()=>{},
  fetch:async(url,options)=>{uploads.push(JSON.parse(options.body));return {ok:true,json:async()=>control};}};
 sandbox.window=sandbox;
 vm.runInNewContext(fs.readFileSync('shared/mobile_ltz/delay-trace.js','utf8'),sandbox);
 const recorder=new sandbox.MobileDelayTrace({url:'/diagnostics',team:'green',context:()=>({sequence:12,run_id:'fixture',secret:'never-record'})});
 return {recorder,intervals,frames,uploads,get control(){return control;},set control(v){control=v;},advance(value){now=value;for(const fn of [...intervals.values()])fn();}};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('off creates no polling, frame callbacks, observer or uploads; stop acknowledges once',async()=>{
 const f=fixture();assert.equal(f.recorder.begin(),null);assert.equal(f.intervals.size,0);assert.equal(f.frames.size,0);assert.equal(f.uploads.length,0);
 f.recorder.configure(f.control);await settle();assert.equal(f.recorder.active,true);assert.equal(f.intervals.size,1);
 f.control={...f.control,recording:false,revision:2};f.recorder.configure(f.control);await settle();
 assert.equal(f.recorder.active,false);assert.equal(f.intervals.size,0);assert.equal(f.frames.size,0);
 assert.equal(f.uploads.at(-1).recording,false);const count=f.uploads.length;
 f.recorder.configure(f.control);f.advance(10000);await settle();assert.equal(f.uploads.length,count);
});
test('lost control updates expire recording even without PerformanceObserver support',async()=>{
 const f=fixture();f.recorder.configure(f.control);await settle();f.advance(4100);await settle();
 assert.equal(f.recorder.active,false);assert.equal(f.intervals.size,0);assert.equal(f.frames.size,0);
});
test('old enabled snapshots cannot undo Stop; records and batches stay bounded',async()=>{
 const f=fixture();const old=f.control;f.recorder.configure(old);await settle();
 for(let i=0;i<600;i++)f.recorder.record('browser.apply',i,5);
 assert.equal(f.recorder.queue.length,512);assert.equal(f.recorder.dropped,88);
 await f.recorder.flush();assert.equal(f.uploads.at(-1).events.length,100);
 assert.ok(!JSON.stringify(f.uploads).includes('never-record'));
 f.control={...old,revision:2,recording:false};f.recorder.configure(f.control);await settle();
 f.recorder.configure(old);assert.equal(f.recorder.active,false);
});
test('the real controller status API measures routine polls without extra requests',async()=>{
 const html=fs.readFileSync('shared/robot_controls/controller.html','utf8'),timings=[],requests=[];
 let now=0;const state={feedback_ok:true};
 const context={MOBILE_LTZ:true,LTZ:false,window:{},BASE:'/s/green/p/ltx/',AbortController,setTimeout,clearTimeout,
  parent:{mobileDelay:{begin:()=>now,end:(name,at)=>timings.push({name,duration:now-at})}},
  fetch:async(url,options)=>{requests.push({url,options});now+=37;return {json:async()=>state};}};
 vm.runInNewContext(html.slice(html.indexOf('async function api('),html.indexOf('function report(')),context);
 assert.equal(await context.api('/api/status',null,'GET'),state);
 assert.deepEqual(timings,[{name:'browser.status_request',duration:37}]);
 assert.equal(requests.length,1);assert.equal(requests[0].options.method,'GET');
});
